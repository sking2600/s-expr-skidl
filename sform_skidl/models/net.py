"""
Net class for electrical connections.

Tracks pin connections and supports SKiDL-style connection syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .pin import Pin
    from .part import Part


@dataclass
class Net:
    """
    Represents an electrical net connecting multiple pins.
    
    Supports SKiDL-style connection operators:
        net += pin           # Connect pin to net
        net += [pins]        # Connect multiple pins
        net & part1 & part2  # Series connection
    
    Attributes:
        name: Net name (e.g., "VCC", "GND", "Net1").
    """
    name: str = ""
    _pins: list[Pin] = field(default_factory=list, repr=False)
    _uuid: str = field(default_factory=lambda: str(uuid.uuid4()), repr=False)
    
    # Class-level net counter for auto-naming
    _counter: int = 0
    
    def __post_init__(self):
        if not self.name:
            Net._counter += 1
            self.name = f"Net{Net._counter}"
    
    @property
    def pins(self) -> list[Pin]:
        """List of connected pins (read-only)."""
        return list(self._pins)
    
    @property
    def is_power(self) -> bool:
        """True if net contains power pins."""
        return any(p.is_power for p in self._pins)
    
    @property
    def drive_pin(self) -> Pin | None:
        """Find the pin driving this net (Output or PowerOut)."""
        from .pin import PinType
        drivers = [p for p in self._pins if p.pin_type in (PinType.OUTPUT, PinType.POWER_OUT)]
        if drivers:
            return drivers[0]
        # Fallback to bidirectional
        bidir = [p for p in self._pins if p.pin_type == PinType.BIDIRECTIONAL]
        return bidir[0] if bidir else None
    
    def _add_pin(self, pin: Pin):
        """Internal: add pin to this net."""
        if pin not in self._pins:
            self._pins.append(pin)
    
    def _remove_pin(self, pin: Pin):
        """Internal: remove pin from this net."""
        if pin in self._pins:
            self._pins.remove(pin)
    
    def __iadd__(self, other) -> Net:
        """
        Connect pins to this net using += operator.
        
        Examples:
            net += pin
            net += [pin1, pin2]
            net += part  # connects all pins
        """
        from .pin import Pin
        from .part import Part
        
        if isinstance(other, Pin):
            other.connect(self)
        elif isinstance(other, Part):
            # Connect all pins of the part
            for pin in other._pins.values():
                pin.connect(self)
        elif hasattr(other, "__iter__"):
            for item in other:
                self.__iadd__(item)
        else:
            raise TypeError(f"Cannot connect {type(other)} to Net")
        
        return self
    
    def __and__(self, other) -> "Net":
        """
        Series connection operator.
        
        Creates connections: net & part1 & part2 connects them in series.
        For 2-pin parts, this chains pin[2] of one to pin[1] of next.
        
        Example:
            vin & r1 & vout & r2 & gnd  # Voltage divider
        """
        from .part import Part
        from .pin import Pin
        
        if isinstance(other, Part):
            # For series connection, connect this net to first pin
            pins = list(other._pins.values())
            if pins:
                pins[0].connect(self)
            # Return a _ChainedPart to track which pin to use next
            if len(pins) > 1:
                return _ChainedPart(other, pins[-1])
            return self
        elif isinstance(other, Pin):
            other.connect(self)
            return self
        elif isinstance(other, Net):
            # Merge nets - connect all pins from other to self
            for pin in other._pins:
                pin._net = self
                self._add_pin(pin)
            return self
        else:
            raise TypeError(f"Cannot chain {type(other)} with &")
    
    def __rand__(self, other) -> "Net":
        """Right-hand & operator for chaining."""
        return self.__and__(other)
    
    def __or__(self, other) -> "Net":
        """
        Parallel connection operator.
        
        Connects items to the same net (parallel connection).
        
        Example:
            gnd | r1[2] | c1[2]  # Connect multiple items to GND
        """
        from .pin import Pin
        from .part import Part
        
        if isinstance(other, Pin):
            other.connect(self)
        elif isinstance(other, Part):
            # Connect all pins of part to this net
            for pin in other._pins.values():
                pin.connect(self)
        elif isinstance(other, Net):
            # Merge other net into this one
            for pin in list(other._pins):
                pin._net = self
                self._add_pin(pin)
        elif hasattr(other, '__iter__'):
            for item in other:
                self.__or__(item)
        else:
            raise TypeError(f"Cannot combine {type(other)} with | operator")
        
        return self
    
    def __ror__(self, other) -> "Net":
        """Right-hand | operator."""
        return self.__or__(other)


class _ChainedPart:
    """Helper class for tracking series connections through parts."""
    
    def __init__(self, part, exit_pin):
        self.part = part
        self.exit_pin = exit_pin  # The pin to connect to the next element
    
    def __and__(self, other) -> "Net":
        """Continue the chain from the exit pin."""
        from .part import Part
        from .pin import Pin
        
        if isinstance(other, Net):
            # Connect exit pin to the target net
            self.exit_pin.connect(other)
            return other
        elif isinstance(other, Part):
            # Create connection through this part
            pins = list(other._pins.values())
            if pins:
                # Connect our exit pin to the next part's first pin via a new net
                intermediate = Net()
                self.exit_pin.connect(intermediate)
                pins[0].connect(intermediate)
            # Return chained part for further chaining
            if len(pins) > 1:
                return _ChainedPart(other, pins[-1])
            return intermediate if pins else self
        elif isinstance(other, Pin):
            intermediate = Net()
            self.exit_pin.connect(intermediate)
            other.connect(intermediate)
            return intermediate
        else:
            raise TypeError(f"Cannot chain {type(other)} with &")
    
    def __rand__(self, other):
        return self.__and__(other)
    
    def __contains__(self, pin: Pin) -> bool:
        """Check if pin is connected to this net."""
        return pin in self._pins
    
    def __len__(self) -> int:
        """Number of connected pins."""
        return len(self._pins)
    
    def __repr__(self) -> str:
        pin_refs = [p.ref for p in self._pins[:3]]
        if len(self._pins) > 3:
            pin_refs.append("...")
        return f"Net({self.name!r}, pins=[{', '.join(pin_refs)}])"
