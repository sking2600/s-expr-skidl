"""
Symbol model for KiCad symbol definitions.

Represents symbols as defined in .kicad_sym files with properties,
pins, and graphical items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid

from .pin import Pin


@dataclass
class GraphicItem:
    """Base class for symbol graphical items (rectangles, circles, etc.)."""
    item_type: str  # rectangle, circle, arc, polyline, text
    data: dict = field(default_factory=dict)
    
    def to_sexpr(self) -> list:
        """Convert to S-expression."""
        # If we have raw S-expression data (from library), return it directly
        if "raw" in self.data:
            return self.data["raw"]
        
        if self.item_type == "rectangle":
            return [
                "rectangle",
                ["start", self.data.get("start_x", 0), self.data.get("start_y", 0)],
                ["end", self.data.get("end_x", 0), self.data.get("end_y", 0)],
                ["stroke", ["width", self.data.get("stroke_width", 0.254)],
                          ["type", self.data.get("stroke_type", "default")]],
                ["fill", ["type", self.data.get("fill", "none")]],
            ]
        elif self.item_type == "circle":
            return [
                "circle",
                ["center", self.data.get("center_x", 0), self.data.get("center_y", 0)],
                ["radius", self.data.get("radius", 1)],
                ["stroke", ["width", self.data.get("stroke_width", 0.254)],
                          ["type", self.data.get("stroke_type", "default")]],
                ["fill", ["type", self.data.get("fill", "none")]],
            ]
        elif self.item_type == "polyline":
            pts = self.data.get("points", [(0, 0)])
            pts_sexpr = ["pts"] + [["xy", x, y] for x, y in pts]
            return [
                "polyline",
                pts_sexpr,
                ["stroke", ["width", self.data.get("stroke_width", 0)],
                          ["type", self.data.get("stroke_type", "default")]],
                ["fill", ["type", self.data.get("fill", "none")]],
            ]
        else:
            return [self.item_type]


@dataclass
class SymbolUnit:
    """Represents a unit of a multi-unit symbol."""
    unit_num: int
    style: int = 1  # Body style (1 = normal, 2 = alternate)
    pins: list[Pin] = field(default_factory=list)
    graphics: list[GraphicItem] = field(default_factory=list)


@dataclass
class Symbol:
    """
    Represents a KiCad symbol definition.
    
    Attributes:
        name: Symbol name (e.g., "R", "C", "LM7805").
        properties: Dict of properties (Reference, Value, Footprint, etc.).
        pins: List of symbol pins.
        graphics: List of graphical items.
        units: List of symbol units for multi-unit symbols.
    """
    name: str
    extends: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    pins: list[Pin] = field(default_factory=list)
    graphics: list[GraphicItem] = field(default_factory=list)
    units: list[SymbolUnit] = field(default_factory=list)
    
    # Symbol options
    in_bom: bool = True
    on_board: bool = True
    pin_numbers_hide: bool = False
    pin_names_hide: bool = False
    pin_names_offset: float = 1.016
    
    _uuid: str = field(default_factory=lambda: str(uuid.uuid4()), repr=False)
    
    def __post_init__(self):
        """Set default properties if not provided."""
        if "Reference" not in self.properties:
            self.properties["Reference"] = "U"
        if "Value" not in self.properties:
            self.properties["Value"] = self.name
    
    @property
    def reference(self) -> str:
        """Symbol reference designator prefix."""
        return self.properties.get("Reference", "U")
    
    @property
    def value(self) -> str:
        """Symbol value."""
        return self.properties.get("Value", self.name)
    
    @property
    def footprint(self) -> str | None:
        """Footprint library:name if set."""
        return self.properties.get("Footprint")
    
    @footprint.setter
    def footprint(self, value: str):
        self.properties["Footprint"] = value
    
    def get_pin(self, key: str) -> Pin | None:
        """Get pin by number or name."""
        for pin in self.pins:
            if pin.number == key or pin.name == key:
                return pin
        return None
    
    def to_sexpr(self) -> list:
        """Convert symbol to S-expression for .kicad_sym file."""
        result = ["symbol", self.name]
        
        # Pin numbers visibility (required for KiCad 9)
        pin_numbers = ["pin_numbers"]
        if self.pin_numbers_hide:
            pin_numbers.append(["hide", "yes"])
        result.append(pin_numbers)
        
        # Pin names (required for KiCad 9)
        pin_names = ["pin_names"]
        if self.pin_names_offset != 1.016:
            pin_names.append(["offset", self.pin_names_offset])
        else:
            pin_names.append(["offset", 0])
        if self.pin_names_hide:
            pin_names.append(["hide", "yes"])
        result.append(pin_names)
        
        # BOM and board presence
        result.append(["exclude_from_sim", "no"])
        result.append(["in_bom", "yes" if self.in_bom else "no"])
        result.append(["on_board", "yes" if self.on_board else "no"])
        
        # Properties
        prop_id = 0
        for key, value in self.properties.items():
            effects = ["effects", ["font", ["size", 1.27, 1.27]]]
            if key in ("Footprint", "Datasheet", "Description"):
                effects.append(["hide", "yes"])
            prop = [
                "property", key, value,
                ["at", 0, prop_id * -2.54, 0],
                effects,
            ]
            result.append(prop)
            prop_id += 1
        
        # Create unit 0_1 for graphics (shared between units)
        if self.graphics:
            graphics_unit = ["symbol", f"{self.name}_0_1"]
            for graphic in self.graphics:
                graphics_unit.append(graphic.to_sexpr())
            result.append(graphics_unit)
        
        # Create unit 1_1 for pins 
        pins_unit = ["symbol", f"{self.name}_1_1"]
        for pin in self.pins:
            pins_unit.append(pin.to_sexpr())
        result.append(pins_unit)
        
        return result
    
    @classmethod
    def from_sexpr(cls, data: list) -> Symbol:
        """Create Symbol from S-expression data."""
        # data = ['symbol', 'NAME', ...]
        name = data[1]
        extends = None
        properties = {}
        pins = []
        graphics = []
        in_bom = True
        on_board = True
        
        for item in data[2:]:
            if not isinstance(item, list):
                continue
            
            token = item[0]
            
            if token == "extends":
                extends = item[1]
            
            if token == "property":
                key = item[1]
                value = item[2] if len(item) > 2 else ""
                properties[key] = value
            
            elif token == "pin":
                pins.append(Pin.from_sexpr(item))
            
            elif token in ("rectangle", "circle", "arc", "polyline", "text"):
                graphics.append(GraphicItem(item_type=token, data={"raw": item}))
            
            elif token == "in_bom":
                in_bom = item[1] == "yes" if len(item) > 1 else True
            
            elif token == "on_board":
                on_board = item[1] == "yes" if len(item) > 1 else True
            
            elif token == "symbol":
                # Nested unit symbol - extract pins and graphics
                for subitem in item[2:]:
                    if isinstance(subitem, list):
                        if subitem[0] == "pin":
                            pins.append(Pin.from_sexpr(subitem))
                        elif subitem[0] in ("rectangle", "circle", "arc", "polyline"):
                            graphics.append(GraphicItem(item_type=subitem[0], data={"raw": subitem}))
        
        return cls(
            name=name,
            extends=extends,
            properties=properties,
            pins=pins,
            graphics=graphics,
            in_bom=in_bom,
            on_board=on_board,
        )
