"""
Pin model for symbol and part pins.

Defines electrical types and graphical styles matching KiCad's pin definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .net import Net
    from .part import Part


class PinType(Enum):
    """Electrical type of a pin, matching KiCad's pin_electrical_type."""
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    FREE = "free"
    UNSPECIFIED = "unspecified"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"


class PinStyle(Enum):
    """Graphical style of a pin, matching KiCad's pin_graphic_style."""
    LINE = "line"
    INVERTED = "inverted"
    CLOCK = "clock"
    INVERTED_CLOCK = "inverted_clock"
    INPUT_LOW = "input_low"
    CLOCK_LOW = "clock_low"
    OUTPUT_LOW = "output_low"
    EDGE_CLOCK_HIGH = "edge_clock_high"
    NON_LOGIC = "non_logic"


@dataclass
class Pin:
    """
    Represents a symbol or part pin.
    
    Attributes:
        number: Pin number (string, e.g., "1", "A1").
        name: Pin name (e.g., "VCC", "GND", "D0").
        pin_type: Electrical type for ERC.
        style: Graphical style.
        position: (x, y) coordinates in mm.
        length: Pin length in mm.
        orientation: Rotation angle (0, 90, 180, 270).
    """
    number: str
    name: str = ""
    pin_type: PinType = PinType.PASSIVE
    style: PinStyle = PinStyle.LINE
    position: tuple[float, float] = (0.0, 0.0)
    length: float = 2.54
    orientation: int = 0
    
    # Runtime connections (not serialized)
    _net: Net | None = field(default=None, repr=False, compare=False)
    _part: Part | None = field(default=None, repr=False, compare=False)
    _uuid: str = field(default_factory=lambda: str(uuid.uuid4()), repr=False)
    
    # Aliases for this pin (alternate names)
    aliases: list[str] = field(default_factory=list, repr=False)
    
    def add_alias(self, *names: str) -> "Pin":
        """
        Add alternate names for this pin.
        
        Example:
            pin.add_alias('VCC', '3V3', 'POWER')
        """
        for name in names:
            if name not in self.aliases:
                self.aliases.append(name)
        return self

    @property
    def is_power(self) -> bool:
        """True if pin is a power pin."""
        return self.pin_type in (PinType.POWER_IN, PinType.POWER_OUT)
    
    @property
    def net(self) -> Net | None:
        """Net this pin is connected to."""
        return self._net
    
    @property
    def part(self) -> Part | None:
        """Part this pin belongs to."""
        return self._part
    
    @property
    def is_connected(self) -> bool:
        """True if pin is connected to a net."""
        return self._net is not None
    
    @property
    def ref(self) -> str:
        """Full reference like 'R1.1' or 'U2.VCC'."""
        if self._part:
            return f"{self._part.ref}.{self.number}"
        return self.number
    
    def connect(self, net: Net):
        """Connect this pin to a net."""
        if self._net is not None and self._net is not net:
            raise ValueError(f"Pin {self.ref} already connected to {self._net.name}")
        self._net = net
        net._add_pin(self)
    
    def disconnect(self):
        """Disconnect this pin from its net."""
        if self._net:
            self._net._remove_pin(self)
            self._net = None
    
    def to_sexpr(self) -> list:
        """Convert pin to S-expression for symbol definition."""
        x, y = self.position
        return [
            "pin", self.pin_type.value, self.style.value,
            ["at", x, y, self.orientation],
            ["length", self.length],
            ["name", self.name, ["effects", ["font", ["size", 1.27, 1.27]]]],
            ["number", self.number, ["effects", ["font", ["size", 1.27, 1.27]]]],
        ]
    
    @classmethod
    def from_sexpr(cls, data: list) -> Pin:
        """Create Pin from S-expression data."""
        # data = ['pin', type, style, ['at', x, y, angle], ...]
        pin_type = PinType(data[1])
        style = PinStyle(data[2])
        
        position = (0.0, 0.0)
        orientation = 0
        length = 2.54
        name = ""
        number = ""
        
        for item in data[3:]:
            if isinstance(item, list):
                if item[0] == "at":
                    position = (float(item[1]), float(item[2]))
                    if len(item) > 3:
                        orientation = int(float(item[3]))
                elif item[0] == "length":
                    length = float(item[1])
                elif item[0] == "name":
                    name = item[1] if len(item) > 1 else ""
                elif item[0] == "number":
                    number = item[1] if len(item) > 1 else ""
        
        return cls(
            number=number,
            name=name,
            pin_type=pin_type,
            style=style,
            position=position,
            length=length,
            orientation=orientation,
        )

    def __and__(self, other) -> Any:
        """Chaining operator: pin & other."""
        from ..compat import NC
        if other is NC:
            self._no_connect = True
            return self

        from .net import Net
        if self._net is None:
            from ..api import Net as NetFactory
            net = NetFactory()
            net += self
        return self._net & other

    def __rand__(self, other) -> Any:
        """Right chaining operator."""
        return self.__and__(other)

    def __or__(self, other) -> Any:
        """Parallel operator: pin | other."""
        from .net import Net
        if self._net is None:
            from ..api import Net as NetFactory
            net = NetFactory()
            net += self
        return self._net | other

    def __ror__(self, other) -> Any:
        """Right parallel operator."""
        return self.__or__(other)
