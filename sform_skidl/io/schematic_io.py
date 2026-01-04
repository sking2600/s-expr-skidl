"""
Schematic writer for .kicad_sch files.

Generates KiCad schematic files with simple grid-based auto-placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import uuid

from ..sexpr import serialize_to_file
from ..models.part import Part
from ..models.net import Net


@dataclass
class PlacedPart:
    """A part placed on the schematic."""
    part: Part
    position: tuple[float, float]
    rotation: int = 0


@dataclass
class WireSegment:
    """A wire segment connecting two points."""
    start: tuple[float, float]
    end: tuple[float, float]


class SchematicWriter:
    """
    Generates KiCad schematic files (.kicad_sch).
    
    Uses simple grid-based placement algorithm.
    """
    
    # Grid constants (in mm)
    GRID_SPACING = 25.4  # 1 inch
    START_X = 50.8       # Starting X position
    START_Y = 50.8       # Starting Y position
    PARTS_PER_ROW = 4
    
    def __init__(
        self,
        title: str = "",
        version: int = 20250114,
        paper: str = "A4",
        rev: str = "",
        date: str = "",
        company: str = "",
    ):
        """
        Initialize schematic writer.
        
        Args:
            title: Schematic title.
            version: KiCad file format version.
            paper: Paper size (A4, A3, Letter, etc.).
        """
        self.title = title
        self.version = version
        self.paper = paper
        self.rev = rev
        self.date = date
        self.company = company
        self._uuid = str(uuid.uuid4())
        
        self._placed_parts: list[PlacedPart] = []
        self._wires: list[WireSegment] = []
        self._junctions: list[tuple[float, float]] = []
        self._labels: list[tuple[str, tuple[float, float]]] = []
    
    def add_part(self, part: Part, position: tuple[float, float] | None = None, rotation: int = 0):
        """
        Add a part to the schematic.
        
        Args:
            part: Part to add.
            position: (x, y) position, or None for auto-placement.
            rotation: Rotation in degrees (0, 90, 180, 270).
        """
        if position is None:
            position = self._next_position()
        
        self._placed_parts.append(PlacedPart(part, position, rotation))
    
    def add_wire(self, start: tuple[float, float], end: tuple[float, float]):
        """Add a wire segment."""
        self._wires.append(WireSegment(start, end))
    
    def add_junction(self, position: tuple[float, float]):
        """Add a junction point."""
        self._junctions.append(position)
    
    def add_label(self, name: str, position: tuple[float, float], rotation: int = 0):
        """Add a net label."""
        self._labels.append((name, position, rotation))
    
    def _next_position(self) -> tuple[float, float]:
        """Calculate next auto-placement position."""
        n = len(self._placed_parts)
        row = n // self.PARTS_PER_ROW
        col = n % self.PARTS_PER_ROW
        x = self.START_X + col * self.GRID_SPACING
        y = self.START_Y + row * self.GRID_SPACING
        return (x, y)
    
    def auto_place_parts(self, parts: list[Part]):
        """Auto-place a list of parts on the schematic."""
        for part in parts:
            self.add_part(part)

    def auto_inject_power_flags(self, nets: list[Net]):
        """
        Automatically add PWR_FLAG symbols to power nets that lack a driver.
        This suppresses KiCad ERC "Net has only passive pins" warnings.
        """
        from .symbol_lib import get_library
        from ..models.pin import PinType
        
        # Power net names (case insensitive)
        power_names = {'vcc', 'vdd', 'v+', '3v3', '5v', '12v', 'vin', 'gnd', 'vss', 'batt+'}
        
        for net in nets:
            if not net.name: continue
            
            # Check if likely power net
            is_power_net = net.name.lower() in power_names or net.name.lower().startswith(('vcc', 'vdd', 'gnd'))
            
            if not is_power_net: continue
            
            # Check for driver
            has_driver = any(p.pin_type == PinType.POWER_OUT for p in net.pins)
            
            if not has_driver and net.pins:
                # Add PWR_FLAG
                # Find a location near the first pin
                # We need a location.
                # Use get_pin_pos logic?
                # We can replicate simple location logic.
                
                # We need to instantiate a PWR_FLAG part.
                # Assuming "power" library exists and is loaded.
                # KiCad v6+ uses "power" lib.
                # user needs "power.kicad_sym" available? 
                # Or we use a virtual definition.
                # Let's try "power:PWR_FLAG".
                
                # Check if we have the symbol
                # If not, we might fail.
                # Ideally check if lib loaded.
                
                pwr_flag = Part(lib="power", name="PWR_FLAG", footprint="", value="PWR_FLAG")
                pwr_flag.ref = f"#FLG_{net.name}" # Virtual ref
                
                # Find placement
                # Just pick first pin pos and offset
                # But we don't know absolute pos until layout?
                # Layout HAPPENED already by the time proper verify runs?
                # Usually `auto_place_parts` happened.
                
                # Find a pin that IS placed
                target_pos = None
                for pin in net.pins:
                    if pin.part:
                        for placed in self._placed_parts:
                            if placed.part == pin.part:
                                # Get absolute pos
                                from ..geometry import kicad_rotation_matrix
                                dx, dy = pin.position
                                rx, ry = kicad_rotation_matrix(placed.rotation, dx, dy)
                                target_pos = (placed.position[0] + rx, placed.position[1] - ry)
                                break
                    if target_pos: break
                    
                if target_pos:
                    # Place flag nearby (e.g. 5mm Up or Left)
                    # PWR_FLAG usually connects at bottom.
                    # Place it 5mm above?
                    flag_pos = (target_pos[0], target_pos[1] - 5.08)
                    
                    self.add_part(pwr_flag, flag_pos)
                    
                    # Connect wire
                    # Flag pin 1 is usually at (0,0) of symbol
                    # So absolute pos of pin is flag_pos.
                    self.add_wire(target_pos, flag_pos)
                    print(f"  [AUTO-PWR] Injected PWR_FLAG on net {net.name}")

    
    def verify_wiring(self, auto_fix: bool = True):
        """
        Verify wiring integrity and optionally fix issues.
        """
        from ..geometry import Point, kicad_rotation_matrix
        
        print("\nVerifying schematic wiring...")
        warnings = []
        fixed_count = 0
        
        # Helper: Build set of all wire endpoints (with tolerance) to check connectivity
        def get_endpoints():
            eps = []
            for w in self._wires:
                eps.append(w.start)
                eps.append(w.end)
            return eps
            
        endpoints = get_endpoints()
            
        def is_connected(pos, current_endpoints):
            for ep in current_endpoints:
                if abs(ep[0] - pos[0]) < 0.05 and abs(ep[1] - pos[1]) < 0.05:
                    return True
            return False
            
        # Check pins of complex parts
        for placed in self._placed_parts:

            # Check each pin
            for pin in placed.part.pins:
                # Calculate absolute pin pos 
                px, py = placed.position
                dx, dy = pin.position
                rot = placed.rotation
                
                rx, ry = kicad_rotation_matrix(rot, dx, dy)
                # KiCad Symbol Y is Up, Schematic Y is Down -> Subtract RY
                abs_pos = (px + rx, py - ry)
                
                net = pin.net
                
                # Logic: Is this pin SUPPOSED to be connected?
                # 1. It has a net assigned.
                # 2. Net is not NO_CONNECT (implied by having a net object usually, unless skidl NC)
                # 3. If net name is "NC" or similar, skip? (SKiDL uses None for NC often)
                
                should_connect = False
                if net:
                    if net.name and "N/C" in net.name:
                         should_connect = False
                    elif len(net.pins) > 1:
                         should_connect = True
                    elif net.name and not net.name.startswith("Net"):
                         should_connect = True
                
                status = "Connected" if is_connected(abs_pos, endpoints) else "OPEN"
                
                if should_connect and status == "OPEN":
                     msg = f"Pin {placed.part.ref}.{pin.name} ({net.name}) at {abs_pos} seems unconnected."
                     warnings.append(msg)
                     
                     if auto_fix:
                        print(f"  [AUTO-FIX] {msg} -> Adding rescue wire.")
                        # ... (Auto fix logic same as before) ...
                        # ...
                        target_pos = None
                        for lbl_name, lbl_pos, _ in self._labels:
                            if lbl_name == net.name:
                                target_pos = lbl_pos
                                break
                        
                        stub_len = 5.08
                        # Try to point away from center
                        if abs(rx) > abs(ry):
                            stub_dx = stub_len if rx >= 0 else -stub_len
                            stub_dy = 0
                        else:
                            stub_dx = 0
                            stub_dy = stub_len if ry >= 0 else -stub_len
                            
                        end_pos = (abs_pos[0] + stub_dx, abs_pos[1] + stub_dy)
                        
                        self.add_wire(abs_pos, end_pos)
                        
                        rot = 0
                        if stub_dx < -0.1: rot = 180
                        elif stub_dy < -0.1: rot = 90
                        elif stub_dy > 0.1: rot = 270
                        
                        self.add_label(net.name, end_pos, rotation=rot)
                        
                        endpoints.append(abs_pos)
                        endpoints.append(end_pos)
                        fixed_count += 1
                        
                elif status == "OPEN":
                     # Diagnostic for why we skipped it
                     # print(f"    [SKIP] Pin {pin.name} ({net.name if net else 'None'}) - Not required.")
                     pass
        
        if warnings:
            print(f"  Finding: {len(warnings)} wiring issues found.")
            if auto_fix:
                print(f"  Action: Fixed {fixed_count} connections.")
        else:
            print("  OK: All pinned connections verified.")

    def auto_wire_nets(self, nets: list[Net]):
        """
        Auto-generate wires and labels for connected nets.
        Strategy: Stub Routing for 'stub_prefixes', Direct Routing for others.
        """
        from ..geometry import Point, kicad_rotation_matrix
        
        # Prefixes that trigger stub routing (Complex parts)
        stub_prefixes = ('U', 'IC', 'MCU', 'J', 'P', 'CONN', 'Q', 'D', 'T')
        
        for net in nets:
            pins = net.pins
            if not pins:
                continue
                
            is_stub_net = False
            has_name = net.name and not net.name.startswith("Net")
            
            for pin in pins:
                if pin.part:
                    ref = pin.part.ref or ""
                    if any(ref.startswith(pre) for pre in stub_prefixes):
                        if has_name:
                            is_stub_net = True
                            break
            
            # Helper: Get absolute position of a pin applying rotation
            def get_pin_pos(pin):
                if pin.part:
                    for placed in self._placed_parts:
                        if placed.part is pin.part:
                            px, py = placed.position
                            dx, dy = pin.position
                            rot = placed.rotation
                            
                            rx, ry = kicad_rotation_matrix(rot, dx, dy)
                            # KiCad Symbol Y is Up, Schematic Y is Down -> Subtract RY
                            return (px + rx, py - ry)
                return (0, 0)
            
            # Helper: Get direction vector for stub
            def get_stub_vector(start_pos, pin):
                center = (0,0)
                if pin.part:
                    for placed in self._placed_parts:
                        if placed.part is pin.part:
                            center = placed.position
                            break
                rel_x = start_pos[0] - center[0]
                rel_y = start_pos[1] - center[1]
                stub_len = 2.54 * 2
                
                if abs(rel_x) > abs(rel_y):
                    return (stub_len if rel_x >= 0 else -stub_len, 0)
                else:
                    return (0, stub_len if rel_y >= 0 else -stub_len)

            if is_stub_net and has_name:
                for pin in pins:
                    start_pos = get_pin_pos(pin)
                    stub_dx, stub_dy = get_stub_vector(start_pos, pin)
                    end_pos = (start_pos[0] + stub_dx, start_pos[1] + stub_dy)
                    
                    self.add_wire(start_pos, end_pos)
                    
                    # Calculate label rotation based on stub direction
                    # Net Label Orientation:
                    # 0: Right (standard)
                    # 90: Up
                    # 180: Left
                    # 270: Down
                    
                    rot = 0
                    if stub_dx < 0: rot = 180   # Stub goes Left -> Flag points Left
                    elif stub_dy < 0: rot = 90  # Stub goes Up -> Flag points Up? (KiCad +Y Down: neg Y is Up)
                    elif stub_dy > 0: rot = 270 # Stub goes Down -> Flag points Down
                    
                    self.add_label(net.name, end_pos, rotation=rot)
            else:
                # Direct Routing (Manhattan)
                # Initialize router if not exists
                if not hasattr(self, '_router'):
                    from ..routing import Router
                    self._router = Router()
                    # Add obstacles
                    for placed in self._placed_parts:
                        # Estimate bbox from pins
                        min_x, max_x, min_y, max_y = 0,0,0,0
                        has_pins = False
                        
                        # Use geometry to get absolute pin positions
                        # Note: We can reuse get_pin_pos logic but independent of specific pin
                        # Just iterate all pins of the part
                        # Or simpler: Approx size 10x10mm for small, more for large?
                        # Better: Iterate pins.
                        for p in placed.part.pins:
                            dx, dy = p.position
                            rx, ry = kicad_rotation_matrix(placed.rotation, dx, dy)
                            px, py = placed.position
                            abs_x, abs_y = px + rx, py - ry
                            
                            if not has_pins:
                                min_x, max_x = abs_x, abs_x
                                min_y, max_y = abs_y, abs_y
                                has_pins = True
                            else:
                                min_x = min(min_x, abs_x)
                                max_x = max(max_x, abs_x)
                                min_y = min(min_y, abs_y)
                                max_y = max(max_y, abs_y)
                        
                        if has_pins:
                            width = max_x - min_x
                            height = max_y - min_y
                            cx = (min_x + max_x) / 2
                            cy = (min_y + max_y) / 2
                            self._router.add_obstacle(cx, cy, width, height)

                pin_positions = [get_pin_pos(p) for p in pins]
                for i in range(len(pin_positions) - 1):
                    p1 = pin_positions[i]
                    p2 = pin_positions[i + 1]
                    
                    # Route path
                    path = self._router.route(p1, p2)
                    
                    for k in range(len(path) - 1):
                         self.add_wire(path[k], path[k+1])
                         
                    if i > 0: self.add_junction(p1)
                    if i == 0 and has_name:
                        # Add label at convenient spot on first segment?
                        # Or center of first segment
                        if len(path) > 1:
                            seg_start = path[0]
                            seg_end = path[1]
                            label_x = (seg_start[0] + seg_end[0]) / 2
                            label_y = (seg_start[1] + seg_end[1]) / 2
                            # Offset Y slightly
                            self.add_label(net.name, (label_x, label_y - 1.27))
    
    def _build_lib_symbols(self) -> list:
        """Build lib_symbols section with all used symbols."""
        symbols = {}
        for placed in self._placed_parts:
            if placed.part._symbol:
                sym = placed.part._symbol
                lib_id = f"{placed.part.lib}:{sym.name}"
                if lib_id not in symbols:
                    symbols[lib_id] = sym
        
        if not symbols:
            return ["lib_symbols"]
        
        lib_symbols = ["lib_symbols"]
        for lib_id, symbol in symbols.items():
            # Create embedded symbol with lib_id as name
            sexpr = symbol.to_sexpr()
            # Replace symbol name with lib_id 
            sexpr[1] = lib_id
            # Fix unit symbol names to include lib prefix
            for i, item in enumerate(sexpr):
                if isinstance(item, list) and item[0] == "symbol" and len(item) > 1:
                    unit_name = item[1]
                    if "_0_1" in unit_name or "_1_1" in unit_name:
                        # Replace simple name with prefixed name
                        item[1] = unit_name.replace(symbol.name, lib_id.split(":")[-1])
            lib_symbols.append(sexpr)
        
        return lib_symbols
    
    def _build_symbol_instance(self, placed: PlacedPart) -> list:
        """Build a symbol instance for a placed part."""
        part = placed.part
        x, y = placed.position
        
        lib_id = f"{part.lib}:{part.name}"
        
        instance = [
            "symbol",
            ["lib_id", lib_id],
            ["at", x, y, placed.rotation],
            ["unit", 1],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes" if part._symbol and part._symbol.in_bom else "yes"],
            ["on_board", "yes" if part._symbol and part._symbol.on_board else "yes"],
            ["dnp", "no"],
            ["uuid", str(uuid.uuid4())],
        ]
        
        # Calculate bounding box from pins to avoid overlap
        # Initialize with (0,0) implied center
        min_x, max_x = 0.0, 0.0
        min_y, max_y = 0.0, 0.0
        
        has_pins = False
        for pin in part.pins:
            has_pins = True
            # Symbol space coordinates
            dx, dy = pin.position
            # Map to Schematic Space relative to center (Note: Symbol Y Up -> Sch Y Down means Flip Y)
            # However, for bounding box size, we just care about extents.
            # Let's verify rotation? 
            # If we place text relative to (x,y), we should consider unrotated bounds usually
            # But the TEXT moves with rotation? 
            # KiCad properties move with the symbol.
            # So we should calculate bounds in SYMBOL SPACE.
            
            # Pin Position in Symbol Space (KiCad format, Y is Up?)
            # Actually, standard KiCad symbols: Pin Y is usually positive for top pins?
            # Let's check: U1 pin 1 at -20.32, 17.78.
            # So Left, Up.
            # BBox should cover -20.32 to +...
            
            min_x = min(min_x, dx)
            max_x = max(max_x, dx)
            min_y = min(min_y, dy)
            max_y = max(max_y, dy)
            
        # Add some margin
        margin = 2.54
        
        # Determine placements in Symbol Space
        # Ref usually at Top
        # Value usually at Bottom
        # KiCad Symbol Y+ is UP? 
        # If Pin 1 is at Y=17.78 (Top), then Top is +Y.
        # So Ref should be at max_y + margin.
        # Value at min_y - margin.
        
        ref_y = max_y + margin
        val_y = min_y - margin
        
        # Adjust visual spacing if no pins (fallback)
        if not has_pins:
            ref_y = 2.54
            val_y = -2.54

        # Add properties with proper formatting
        props = [
            ("Reference", part.ref, 0, ref_y, False),    # Centered Above
            ("Value", part.value or part.name, 0, val_y, False), # Centered Below
        ]
        if part.footprint:
            props.append(("Footprint", part.footprint, 0, val_y - 2.54, True))
        
        for key, value, dx, dy, hidden in props:
            # Note: dx, dy are in Symbol Space. 
            # In KiCad 6+, properties are children of symbol instance and inherit rotation?
            # Yes, "at" inside symbol instance is relative to instance "at".
            # Does it rotate with symbol?
            # Usually yes.
            # But wait. My previous code was:
            # ["at", x + dx, y + dy, 0]
            # This is absolute coordinate in Schematic Space!
            # If I use absolute coordinates, I MUST rotate dx, dy manually if I want them relative to rotated symbol.
            # OR I simply place them relative to (0,0) and let KiCad handle?
            # The S-Expr structure for symbol instance property:
            # (property "Reference" "U1" (at X Y R) ...)
            # The X,Y are ABSOLUTE in the sheet.
            # So I MUST calculate absolute position.
            
            # Rotation Logic:
            # schematic_pos = placed_center + rotated(prop_pos)
            # Prop Pos: (dx, dy) in Symbol Space.
            # Symbol Space Y is Up. Schematic Y is Down.
            # So just like pins:
            # rx, ry = rotation_matrix(placed.rotation, dx, dy)
            # abs_x = x + rx
            # abs_y = y - ry   <-- Flip Y logic
            
            from ..geometry import kicad_rotation_matrix
            rx, ry = kicad_rotation_matrix(placed.rotation, dx, dy)
            prop_x = x + rx
            prop_y = y - ry
            
            prop = [
                "property", key, value,
                ["at", prop_x, prop_y, 0], # Text rotation 0 (always reading upright?)
            ]
            effects = ["effects", ["font", ["size", 1.27, 1.27]]]
            if hidden:
                effects.append(["hide", "yes"])
                
            prop.append(effects)
            instance.append(prop)
        
        # Add pin UUIDs
        for pin in part.pins:
            instance.append([
                "pin", pin.number,
                ["uuid", str(uuid.uuid4())],
            ])
        
        # Add instances section
        instance.append([
            "instances",
            ["project", "",
                ["path", f"/{self._uuid}",
                    ["reference", part.ref],
                    ["unit", 1],
                ],
            ],
        ])
        
        return instance
    
    def _build_wire(self, wire: WireSegment) -> list:
        """Build a wire section."""
        return [
            "wire",
            ["pts",
                ["xy", wire.start[0], wire.start[1]],
                ["xy", wire.end[0], wire.end[1]],
            ],
            ["stroke", ["width", 0], ["type", "default"]],
            ["uuid", str(uuid.uuid4())],
        ]
    
    def _build_junction(self, pos: tuple[float, float]) -> list:
        """Build a junction section."""
        return [
            "junction",
            ["at", pos[0], pos[1]],
            ["diameter", 0],
            ["color", 0, 0, 0, 0],
            ["uuid", str(uuid.uuid4())],
        ]
    
    def _build_label(self, name: str, pos: tuple[float, float], rotation: int = 0) -> list:
        """
        Build a label section.
        
        Uses global_label with flag shape for better visibility.
        Detects shape based on net name or usage (e.g. VCC/GND/Input/Output).
        """
        # Determine label style
        shape = "input"  # Default flag shape (points right)
        
        # Simple heuristics for shape
        lower_name = name.lower()
        if any(x in lower_name for x in ['out', 'tx', 'mosi', 'scl', 'clk']):
            shape = "output"  # Points right (arrow)
        elif any(x in lower_name for x in ['in', 'rx', 'miso']):
            shape = "input"   # Points right (flat left, arrow right) - KiCad conventions vary
        elif any(x in lower_name for x in ['bidir', 'data', 'sda', 'io']):
            shape = "bidirectional"
        
        return [
            "global_label", name,
            ["shape", shape],
            ["at", pos[0], pos[1], rotation],
            ["fields_autoplaced"],
            ["effects", 
                ["font", ["size", 1.27, 1.27]], 
                ["justify", "left"]
            ],
            ["uuid", str(uuid.uuid4())],
        ]
    
    def build(self) -> list:
        """Build the complete schematic S-expression."""
        schematic = [
            "kicad_sch",
            ["version", self.version],
            ["generator", "sform_skidl"],
            ["generator_version", "0.1"],
            ["uuid", self._uuid],
            ["paper", self.paper],
        ]
        
        # Title block
        tb = ["title_block"]
        if self.title: tb.append(["title", self.title])
        if self.date: tb.append(["date", self.date])
        if self.rev: tb.append(["rev", self.rev])
        if self.company: tb.append(["company", self.company])
        schematic.append(tb)
        
        # Library symbols
        schematic.append(self._build_lib_symbols())
        
        # Wires
        for wire in self._wires:
            schematic.append(self._build_wire(wire))
        
        # Junctions
        for junction in self._junctions:
            schematic.append(self._build_junction(junction))
        
        # Labels
        for item in self._labels:
            if len(item) == 3:
                name, pos, rot = item
            else:
                name, pos = item
                rot = 0
            schematic.append(self._build_label(name, pos, rot))
        
        # Symbol instances
        for placed in self._placed_parts:
            # Check for special Sheet Part (for hierarchy)
            if hasattr(placed.part, "is_sheet") and placed.part.is_sheet:
                 schematic.append(self._build_sheet_instance(placed))
            else:
                 schematic.append(self._build_symbol_instance(placed))
        
        # Sheet instances (Metadata)
        schematic.append([
            "sheet_instances",
            ["path", "/",
                ["page", "1"],
            ],
        ])
        
        return schematic

    def _build_sheet_instance(self, placed: PlacedPart) -> list:
        """Build a hierarchical sheet instance."""
        part = placed.part
        x, y = placed.position
        width, height = 20.32, 20.32 # Default size, should scale with pins?
        
        # Calculate size based on pins (Ports)
        # Pins are distributed on edges?
        # Layout Engine treats it as a box.
        # But we need to define the Size W/H to fit the pins.
        # Let's simple check pin bounds if set, or default.
        
        sheet = [
            "sheet",
            ["at", x, y],
            ["size", width, height], # Fixed for now
            ["fields",
                ["field", ["name", "Sheetname"], ["id", 0], ["value", part.name]],
                ["field", ["name", "FileName"], ["id", 1], ["value", part.value]], # value stores filename
            ],
        ]
        
        # Add Sheet Pins (Ports)
        for pin in part.pins:
             # Pin pos relative to sheet? or absolute?
             # KiCad Sheet Pin: (pin "Name" type (at X Y 0) ...)
             # X,Y are RELATIVE to Sheet Top-Left (at X Y)? NO.
             # S-expr docs: (at x y angle) relative to parent?
             # Sheet is an object.
             # Pins are children.
             # In KiCad 6+, sheet pins have absolute coordinates? Or relative?
             # Usually Relative to the Sheet Origin (Top Left).
             
             # My Part pin positions are relative to Center.
             # So I map them to Sheet coordinates.
             # Note: Sheet Origin is typically Top-Left in internal representation?
             # Or Center?
             # KiCad standard: Sheet (at X Y) is Top-Left corner.
             # So if Part Center is (Cx, Cy).
             # Sheet (at Cx-W/2, Cy-H/2).
             # Pin at (Px, Py) relative to Center.
             # Pin Sheet Pos = (W/2 + Px, H/2 + Py). (Applying Y flip).
             
             # Need to confirm KiCad Sheet Origin. It is Top-Left.
             pass
             
        # Placeholder for now, will refine when implementing phase 3
        return sheet
    
    def write(self, path: Path | str):
        """
        Write schematic to a .kicad_sch file.
        
        Args:
            path: Output file path.
        """

        self.verify_wiring()
        schematic = self.build()
        serialize_to_file(schematic, Path(path))
