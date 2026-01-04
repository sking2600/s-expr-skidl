"""
Smart schematic layout algorithms.

Provides intelligent component placement based on:
- Signal flow analysis (inputs left, outputs right)
- Subcircuit grouping
- Power rail placement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.part import Part
    from .models.net import Net
    from .models.circuit import Circuit


@dataclass
class LayoutConfig:
    """Configuration for schematic layout."""
    grid_size: float = 2.54  # mm (100 mil)
    part_spacing_x: float = 25.4  # mm between parts horizontally
    part_spacing_y: float = 15.24  # mm between parts vertically
    group_spacing: float = 30.0  # mm between groups
    power_margin: float = 20.0  # mm margin for power rails


@dataclass
class PartPlacement:
    """Placement information for a part."""
    part: "Part"
    x: float = 0.0
    y: float = 0.0
    column: int = 0  # Signal flow column (0=input, higher=output)
    group: str = ""  # Grouping identifier


class SmartLayout:
    """
    Smart schematic layout engine.
    
    Analyzes circuit connectivity to determine optimal component placement.
    """
    
    def __init__(self, circuit: "Circuit", config: LayoutConfig | None = None):
        self.circuit = circuit
        self.config = config or LayoutConfig()
        self.placements: dict[str, PartPlacement] = {}
        
        # Power net names (case insensitive matching)
        self._power_names = {'vcc', 'vdd', 'v+', '3v3', '5v', '12v', 'vin'}
        self._ground_names = {'gnd', 'vss', 'v-', 'agnd', 'dgnd', 'ground'}
    
    def analyze(self) -> dict[str, PartPlacement]:
        """
        Analyze circuit and compute placements.
        
        Returns:
            Dict mapping part ref to PartPlacement.
        """
        # Step 1: Identify power nets
        power_nets = self._identify_power_nets()
        
        # Step 2: Compute signal flow columns
        columns = self._compute_signal_flow()
        
        # Step 3: Group parts
        groups = self._group_parts()
        
        # Step 4: Assign positions
        self._assign_positions(columns, groups)
        
        return self.placements
    
    def _identify_power_nets(self) -> tuple[set, set]:
        """Identify power and ground nets."""
        power = set()
        ground = set()
        
        for net in self.circuit.nets:
            name_lower = net.name.lower()
            if name_lower in self._power_names:
                power.add(net.name)
            elif name_lower in self._ground_names:
                ground.add(net.name)
        
        return power, ground
    
    def _compute_signal_flow(self) -> dict[str, int]:
        """
        Compute signal flow column for each part.
        
        Uses BFS from input parts to determine column (distance from inputs).
        """
        from .models.pin import PinType
        
        columns = {}
        
        # Find parts with power_in pins but no input pins (likely input stage)
        # Find parts with output pins (likely output stage)
        input_parts = set()
        output_parts = set()
        
        for part in self.circuit.parts:
            has_input = any(p.pin_type == PinType.INPUT for p in part.pins)
            has_output = any(p.pin_type == PinType.OUTPUT for p in part.pins)
            has_power = any(p.pin_type == PinType.POWER_IN for p in part.pins)
            
            if has_input and not has_output:
                input_parts.add(part.ref)
            elif has_output and not has_input:
                output_parts.add(part.ref)
        
        # BFS to assign columns
        visited = set()
        queue = []
        
        # Start with parts connected to "input-like" nets
        for part in self.circuit.parts:
            if part.ref in input_parts:
                columns[part.ref] = 0
                queue.append(part)
                visited.add(part.ref)
        
        # If no clear inputs, start with first part
        if not queue and self.circuit.parts:
            part = self.circuit.parts[0]
            columns[part.ref] = 0
            queue.append(part)
            visited.add(part.ref)
        
        # BFS to propagate columns
        while queue:
            current = queue.pop(0)
            current_col = columns.get(current.ref, 0)
            
            # Find connected parts through nets
            for pin in current.pins:
                if pin.net:
                    for other_pin in pin.net.pins:
                        if hasattr(other_pin, 'part') and other_pin.part:
                            other_ref = other_pin.part.ref
                            if other_ref not in visited:
                                visited.add(other_ref)
                                columns[other_ref] = current_col + 1
                                queue.append(other_pin.part)
        
        # Assign remaining parts to middle column
        max_col = max(columns.values()) if columns else 0
        mid_col = max_col // 2
        for part in self.circuit.parts:
            if part.ref not in columns:
                columns[part.ref] = mid_col
        
        return columns
    
    def _group_parts(self) -> dict[str, str]:
        """
        Group parts by subcircuit or power domain.
        
        Returns:
            Dict mapping part ref to group name.
        """
        groups = {}
        
        for part in self.circuit.parts:
            # Check for subcircuit group
            if hasattr(part, '_group') and part._group:
                groups[part.ref] = part._group
            else:
                # Default group by ref prefix
                prefix = ''.join(c for c in part.ref if c.isalpha())
                groups[part.ref] = prefix or 'misc'
        
        return groups
    
    def _assign_positions(
        self,
        columns: dict[str, int],
        groups: dict[str, str],
    ):
        """Assign X/Y positions based on columns and groups."""
        cfg = self.config
        
        # Organize by column, then by group within column
        by_column: dict[int, list] = {}
        for part in self.circuit.parts:
            col = columns.get(part.ref, 0)
            by_column.setdefault(col, []).append(part)
        
        # Sort columns
        sorted_cols = sorted(by_column.keys())
        
        # Assign positions
        for col_idx, col in enumerate(sorted_cols):
            parts_in_col = by_column[col]
            
            # Sort by group within column
            parts_in_col.sort(key=lambda p: groups.get(p.ref, ''))
            
            # Determine X position
            x = col_idx * cfg.part_spacing_x + cfg.power_margin
            
            # Connector override
            # If part is connector, force to edge
            # Input-side (col 0 or 1) -> Left Edge (0 or small margin)
            # Output-side (col Max) -> Right Edge?
            # Or just use current flow logic?
            # Current flow puts inputs at 0. Outputs at Max.
            # But we want to ensure separation if they are mixed with other components.
            # Let's add a "Connector Zone" margin?
            
            pass
            
            current_group = None
            y_offset = cfg.power_margin
            
            for part in parts_in_col:
                group = groups.get(part.ref, '')
                
                # Check for Connector
                ref_prefix = ''.join(c for c in part.ref if c.isalpha())
                is_conn = ref_prefix in ('J', 'P', 'CONN')
                
                final_x = x
                if is_conn:
                     if col_idx == 0:
                         final_x = cfg.power_margin / 2 # Far Left
                     elif col_idx == len(sorted_cols) - 1:
                         # Far Right (push out a bit more)
                         final_x = x + cfg.part_spacing_x 
                
                # Add extra spacing between groups
                if current_group is not None and group != current_group:
                    y_offset += cfg.group_spacing - cfg.part_spacing_y
                
                self.placements[part.ref] = PartPlacement(
                    part=part,
                    x=final_x,
                    y=y_offset,
                    column=col,
                    group=group,
                )
                
                y_offset += cfg.part_spacing_y
                current_group = group
    
    def get_positions(self) -> dict[str, tuple[float, float]]:
        """Get simple dict of ref -> (x, y) positions."""
        return {
            ref: (p.x, p.y)
            for ref, p in self.placements.items()
        }


def compute_layout(circuit=None) -> dict[str, tuple[float, float]]:
    """
    Compute smart layout for a circuit.
    
    Args:
        circuit: Circuit to layout (uses current if None).
        
    Returns:
        Dict mapping part ref to (x, y) position in mm.
        
    Example:
        positions = compute_layout()
        for ref, (x, y) in positions.items():
            print(f"{ref}: ({x}, {y})")
    """
    from .api import get_circuit
    
    if circuit is None:
        circuit = get_circuit()
    
    layout = SmartLayout(circuit)
    layout.analyze()
    return layout.get_positions()
