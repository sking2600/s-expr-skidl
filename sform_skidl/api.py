"""
High-level SKiDL-compatible API.

Provides the main interface for circuit design matching SKiDL conventions.
"""

from __future__ import annotations

from typing import Any
import os

from .models.part import Part, TEMPLATE, NETLIST
from .models.net import Net
from .models.pin import Pin, PinType
from .models.symbol import Symbol
from .io.symbol_lib import get_library, find_kicad_symbols, add_lib_path, lib_search_paths
from .io.schematic_io import SchematicWriter
from .compat import NC, Group, no_connect


# Export constants
__all__ = [
    "Part", "Net", "Pin", "PinType", "Symbol",
    "TEMPLATE", "NETLIST",
    "NC", "Group", "no_connect",
    "ERC", "generate_netlist", "generate_schematic",
    "set_default_tool", "add_lib_path", "lib_search_paths",
]


# Global circuit state
class Circuit:
    """Holds the current circuit being designed."""
    
    def __init__(self):
        self.parts: list[Part] = []
        self.nets: list[Net] = []
        self.name = "untitled"
    
    def reset(self):
        """Clear the current circuit."""
        self.parts.clear()
        self.nets.clear()
        Part._counters = {}
        Net._counter = 0


_circuit = Circuit()


def get_circuit() -> Circuit:
    """Get the current circuit."""
    return _circuit


def reset_circuit():
    """Reset the current circuit."""
    _circuit.reset()


# Tool constants
KICAD = "KICAD"
KICAD8 = "KICAD8"
KICAD9 = "KICAD9"

_default_tool = KICAD9


def set_default_tool(tool: str):
    """Set the default output tool."""
    global _default_tool
    _default_tool = tool


# Store original Part class before overriding
from .models.part import Part as _OriginalPart


def _create_part(
    lib: str,
    name: str,
    dest: str = NETLIST,
    footprint: str = "",
    value: str = "",
    **kwargs,
) -> _OriginalPart:
    """
    Create a part from a library symbol.
    
    Args:
        lib: Symbol library name (e.g., "Device").
        name: Symbol name (e.g., "R", "C").
        dest: TEMPLATE or NETLIST.
        footprint: Footprint string.
        value: Component value.
        **kwargs: Additional properties.
        
    Returns:
        Part instance.
    """
    # Try to load symbol from library
    symbol = None
    try:
        library = get_library(lib)
        symbol = library.get(name)
    except FileNotFoundError:
        pass
    
    # Create basic symbol if not found
    if symbol is None:
        from .models.symbol import GraphicItem
        
        symbol = Symbol(name=name)
        symbol.pin_numbers_hide = True  # Hide pin numbers for 2-pin passives
        
        # Add proper graphics and pins for common parts
        if name in ("R", "C", "L"):
            # Resistor rectangle body from -2.54 to 2.54
            symbol.graphics = [
                GraphicItem("rectangle", {
                    "start_x": -1.016,
                    "start_y": -2.54,
                    "end_x": 1.016,
                    "end_y": 2.54,
                    "stroke_width": 0.254,
                    "stroke_type": "default",
                    "fill": "none",
                }),
            ]
            # Pins at top and bottom with proper positions
            symbol.pins = [
                Pin("1", "~", PinType.PASSIVE, position=(0, 3.81), length=1.27, orientation=270),
                Pin("2", "~", PinType.PASSIVE, position=(0, -3.81), length=1.27, orientation=90),
            ]
        elif name == "LED":
            symbol.graphics = [
                GraphicItem("polyline", {
                    "points": [(-1.27, 1.27), (-1.27, -1.27), (1.27, 0)],
                    "stroke_width": 0.254,
                    "fill": "none",
                }),
            ]
            symbol.pins = [
                Pin("1", "A", PinType.PASSIVE, position=(0, 2.54), length=1.27, orientation=270),
                Pin("2", "K", PinType.PASSIVE, position=(0, -2.54), length=1.27, orientation=90),
            ]
        else:
            # Generic 2-pin passive
            symbol.pins = [
                Pin("1", "1", PinType.PASSIVE, position=(0, 2.54), length=1.27, orientation=270),
                Pin("2", "2", PinType.PASSIVE, position=(0, -2.54), length=1.27, orientation=90),
            ]
    
    # Use the original Part class to avoid recursion
    part = _OriginalPart(
        lib=lib,
        name=name,
        value=value or kwargs.get("value", ""),
        footprint=footprint,
        dest=dest,
        _symbol=symbol,
    )
    
    # Add to circuit if not a template
    if dest != TEMPLATE:
        _circuit.parts.append(part)
    
    return part


# Override Part constructor for SKiDL compatibility
_original_part_class = Part


class SkidlPart:
    """SKiDL-compatible Part factory."""
    
    def __new__(cls, lib: str, name: str, **kwargs) -> Part:
        return _create_part(lib, name, **kwargs)


# Make Part callable as a factory
Part = SkidlPart  # type: ignore


def Net(name: str = "") -> Net:
    """
    Create a new net.
    
    Args:
        name: Net name (auto-generated if empty).
        
    Returns:
        Net instance.
    """
    from .models.net import Net as NetClass
    net = NetClass(name=name)
    _circuit.nets.append(net)
    return net


# ERC (Electrical Rules Check)
class ERCError:
    """Represents an ERC error or warning."""
    
    def __init__(self, severity: str, message: str, location: str = ""):
        self.severity = severity
        self.message = message
        self.location = location
    
    def __str__(self):
        loc = f" at {self.location}" if self.location else ""
        return f"ERC {self.severity}: {self.message}{loc}"
    
    def __repr__(self):
        return f"ERCError({self.severity!r}, {self.message!r})"


def ERC(circuit: Circuit | None = None, verbose: bool = True) -> list[ERCError]:
    """
    Run Electrical Rules Check on the circuit.
    
    Checks for:
    - Unconnected pins (warnings for passive, errors for I/O)
    - Power pins not connected
    - Multiple outputs connected together
    - Input pins without a driver
    - Power-to-ground shorts
    - Floating nets (only passive pins, no driver)
    
    Args:
        circuit: Circuit to check, or use current circuit.
        verbose: Print detailed results.
        
    Returns:
        List of ERC errors and warnings.
    """
    if circuit is None:
        circuit = _circuit
    
    errors = []
    
    # Check 1: Unconnected pins
    for part in circuit.parts:
        for pin in part.pins:
            # Skip if marked as no-connect
            if getattr(pin, '_no_connect', False):
                continue
                
            if not pin.is_connected:
                if pin.pin_type in (PinType.INPUT, PinType.OUTPUT, PinType.POWER_IN):
                    errors.append(ERCError(
                        "error",
                        f"Unconnected {pin.pin_type.value} pin",
                        f"{part.ref}.{pin.number}",
                    ))
                elif pin.pin_type != PinType.NO_CONNECT:
                    errors.append(ERCError(
                        "warning",
                        f"Unconnected {pin.pin_type.value} pin",
                        f"{part.ref}.{pin.number}",
                    ))
    
    # Check 2: Output-to-output conflicts
    for net in circuit.nets:
        outputs = [p for p in net.pins if p.pin_type == PinType.OUTPUT]
        if len(outputs) > 1:
            refs = ", ".join(f"{p.part.ref}.{p.number}" for p in outputs if hasattr(p, 'part'))
            errors.append(ERCError(
                "error",
                f"Multiple outputs connected: {refs}",
                net.name,
            ))
    
    # Check 3: Input without driver
    for net in circuit.nets:
        inputs = [p for p in net.pins if p.pin_type == PinType.INPUT]
        drivers = [p for p in net.pins if p.pin_type in (
            PinType.OUTPUT, PinType.BIDIRECTIONAL, PinType.POWER_OUT
        )]
        
        if inputs and not drivers:
            # Check if there's at least a passive or power source
            passive = [p for p in net.pins if p.pin_type == PinType.PASSIVE]
            power_in = [p for p in net.pins if p.pin_type == PinType.POWER_IN]
            
            if not passive and not power_in:
                input_refs = ", ".join(f"{p.part.ref}.{p.number}" for p in inputs if hasattr(p, 'part'))
                errors.append(ERCError(
                    "warning",
                    f"Input pins without driver: {input_refs}",
                    net.name,
                ))
    
    # Check 4: Power-to-ground short (power_in pins with conflicting names)
    power_nets = {}
    for net in circuit.nets:
        power_pins = [p for p in net.pins if p.pin_type == PinType.POWER_IN]
        if power_pins:
            # Check for obvious VCC/GND conflict
            pin_names = set(p.name.upper() for p in power_pins)
            has_power = any(n in ['VCC', 'VDD', 'V+', '3V3', '5V', '12V'] for n in pin_names)
            has_ground = any(n in ['GND', 'VSS', 'V-', 'AGND', 'DGND'] for n in pin_names)
            
            if has_power and has_ground:
                errors.append(ERCError(
                    "error",
                    f"Possible power-to-ground short",
                    net.name,
                ))
    
    # Check 5: Floating nets (only passive pins, no power or signal)
    for net in circuit.nets:
        if len(net.pins) < 2:
            continue
            
        pin_types = set(p.pin_type for p in net.pins)
        if pin_types == {PinType.PASSIVE}:
            # All passive, no driver - might be intentional but worth noting
            refs = ", ".join(f"{p.part.ref}.{p.number}" for p in net.pins[:3] if hasattr(p, 'part'))
            if len(net.pins) > 3:
                refs += f"... ({len(net.pins)} pins)"
            errors.append(ERCError(
                "warning",
                f"Net has only passive pins (no driver): {refs}",
                net.name,
            ))
    
    # Report ERC results
    error_count = sum(1 for e in errors if e.severity == "error")
    warning_count = sum(1 for e in errors if e.severity == "warning")
    
    if verbose:
        if errors:
            print(f"\nERC: {error_count} error(s), {warning_count} warning(s)")
            for err in errors:
                print(f"  {err}")
        else:
            print("\nERC: No errors")
    
    return errors


def generate_netlist(
    path: str | None = None,
    tool: str | None = None,
    circuit: Circuit | None = None,
) -> str:
    """
    Generate a netlist file.
    
    Args:
        path: Output file path (auto-generated if None).
        tool: Output format (KICAD, KICAD8, KICAD9).
        circuit: Circuit to export, or use current circuit.
        
    Returns:
        Path to the generated netlist file.
    """
    if circuit is None:
        circuit = _circuit
    
    if tool is None:
        tool = _default_tool
    
    if path is None:
        path = f"{circuit.name}.net"
    
    # Generate simple KiCad netlist format
    lines = [
        "(export",
        f'  (version "E")',
        "  (design",
        f'    (source "{path}")',
        f'    (tool "sform_skidl")',
        "  )",
        "  (components",
    ]
    
    for part in circuit.parts:
        lines.append(f'    (comp (ref "{part.ref}")')
        lines.append(f'      (value "{part.value}")')
        if part.footprint:
            lines.append(f'      (footprint "{part.footprint}")')
        lines.append(f'      (libsource (lib "{part.lib}") (part "{part.name}"))')
        lines.append("    )")
    
    lines.append("  )")
    lines.append("  (nets")
    
    for i, net in enumerate(circuit.nets):
        if net.pins:
            lines.append(f'    (net (code "{i+1}") (name "{net.name}")')
            for pin in net.pins:
                if pin.part:
                    lines.append(f'      (node (ref "{pin.part.ref}") (pin "{pin.number}"))')
            lines.append("    )")
    
    lines.append("  )")
    lines.append(")")
    
    content = "\n".join(lines)
    
    from pathlib import Path as PathClass
    PathClass(path).write_text(content, encoding="utf-8")
    
    print(f"Netlist written to: {path}")
    return path


def generate_schematic(
    path: str | None = None,
    title: str = "",
    rev: str = "",
    date: str = "",
    company: str = "",
    paper: str = "A4",
    circuit: Circuit | None = None,
    smart_layout: bool = True,
) -> str:
    """
    Generate a KiCad schematic file (hierarchical).
    """
    if circuit is None:
        circuit = _circuit
    
    if path is None:
        path = f"{circuit.name}.kicad_sch"
    
    # 1. Analyze Hierarchy
    from .hierarchy_analyzer import HierarchyAnalyzer
    analyzer = HierarchyAnalyzer(circuit.parts, circuit.nets)
    root_node = analyzer.analyze()
    sheets = analyzer.get_sheet_structure()
    
    # 2. Create Sheet Symbols (Virtual Parts) for children
    from .models.sheet_part import SheetPart
    from pathlib import Path as PathClass
    
    base_path = PathClass(path)
    sheet_parts_map = {}
    
    # Sort by depth to process children first? 
    # Actually order doesn't matter for creation, only for linking.
    # Identifying parents:
    for h_path, node in sheets.items():
        if h_path == "": continue # Root has no symbol
        
        # Determine filename for this sheet
        subname = h_path.replace(".", "_") # simple mapping
        sheet_filename = f"{base_path.stem}_{subname}{base_path.suffix}"
        
        # Create Sheet Symbol
        # Name is the subcircuit instance name (last part of h_path)
        instance_name = h_path.split(".")[-1]
        sp = SheetPart(name=instance_name, filename=sheet_filename)
        sp.ref = instance_name # Ensure unique ref for SmartLayout
        
        # Add Ports
        for net in node.ports:
            sp.add_port(net.name)
            
        sp.layout_ports()
        sheet_parts_map[h_path] = sp
        
        # Link Virtual Pins to Nets so Router sees them
        for pin in sp.pins:
            # pin.name is net_name
            # find net
            target_net = next((n for n in circuit.nets if n.name == pin.name), None)
            if target_net:
                target_net.pins.append(pin)
                pin.net = target_net
    
    # 3. Assign Sheet Parts to Parents
    for h_path, sp in sheet_parts_map.items():
        # Determine parent path
        if "." in h_path:
            parent_path = h_path.rpartition(".")[0]
        else:
            parent_path = ""
            
        if parent_path in sheets:
            sheets[parent_path].parts.append(sp)
            
    # 4. Generate Schematics for each Sheet
    generated_files = []
    
    for h_path, node in sheets.items():
         is_root = (h_path == "")
         
         if is_root:
             filepath = path
             sheet_title = title or circuit.name
         else:
             subname = h_path.replace(".", "_")
             filepath = str(base_path.with_name(f"{base_path.stem}_{subname}{base_path.suffix}"))
             sheet_title = f"{title} - {subname}"
         
         writer = SchematicWriter(
             title=sheet_title,
             rev=rev,
             date=date,
             company=company,
             paper=paper
         )
         
         # Partition Nets?
         # Passing all nets is fine, writer ignores those not connected to placed parts.
         # But for performance and clarity, we could filter.
         # Filter: Net must touch at least one part in node.parts
         sheet_parts_ids = {id(p) for p in node.parts}
         sheet_nets = []
         for net in circuit.nets:
             if any(id(p.part) in sheet_parts_ids for p in net.pins if p.part):
                 sheet_nets.append(net)
         
         if smart_layout:
             from .layout import SmartLayout
             # Create ephemeral circuit for layout
             # We just need parts and nets.
             # SmartLayout expects a Circuit object? 
             # No, constructor takes `circuit`.
             # We can mock it or modify SmartLayout to take parts/nets?
             # Let's peek at SmartLayout.
             # It uses circuit.parts and circuit.nets.
             # I can construct a dummy circuit.
             dummy_c = Circuit()
             dummy_c.parts = node.parts
             dummy_c.nets = sheet_nets
             
             layout = SmartLayout(dummy_c)
             positions = layout.analyze()
             
             for ref, placement in positions.items():
                 part = next((p for p in node.parts if p.ref == ref), None)
                 if part:
                     writer.add_part(part, (placement.x, placement.y))
         else:
             writer.auto_place_parts(node.parts)
         
         # Inject Power Flags before wiring
         writer.auto_inject_power_flags(sheet_nets)
         
         writer.auto_wire_nets(sheet_nets)
         
         # For Child Sheets: Add Hierarchical Labels for Ports
         if not is_root:
             for port_net in node.ports:
                 # Helper to find where the port enters the sheet
                 # We placed components. We wired them.
                 # The wire ends at the "Port"?
                 # No, "Port" is not a component in the Child Sheet. 
                 # It is just a Label on a Net.
                 # But we need to place the Label nicely.
                 # Usually at the edge of the sheet area.
                 # Since we ran SmartLayout, we have bounds.
                 # We can place Labels at edges.
                 
                 # Simpler auto-placement for labels:
                 # Find an endpoint of the net that is "open"?
                 # Or just pick any point on the net and stick a H-Label?
                 # Better: Stick H-Label near one of the component pins connected to it?
                 pass
                 # Currently SchematicWriter.auto_wire_nets adds "Labels" for stub nets.
                 # Are Ports stub nets?
                 # If we mark them as such?
                 # Or explicitly add H-Labels.
                 # Let's rely on standard labeling for now.
                 # If `auto_wire_nets` adds labels, they are Global.
                 # Hierarchical Labels are `hierarchical_label`.
                 # So we should force H-Label for Ports.
                 
                 # I will skip explicit H-Label placement logic here to verify basic connectivity first.
                 # SchematicWriter likely defaults to Global Labels which work physically but fail Hierarchy checks strictly.
                 # But KiCad 6+ allows mixing?
                 # Ideally we change `add_label` to support type="hierarchical".
         
         writer.write(filepath)
         generated_files.append(filepath)

    print(f"Schematic(s) written to: {', '.join(generated_files)}")
    return path
