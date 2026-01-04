"""
Bus class for grouping multiple nets.

Provides SKiDL-compatible bus operations including indexing, slicing,
and element-wise connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Union
import re

if TYPE_CHECKING:
    from .pin import Pin
    from .part import Part

from .net import Net


@dataclass
class Bus:
    """
    Represents a group of related nets (a bus).
    
    Supports SKiDL-style operations:
        bus = Bus("DATA", 8)     # Create 8-bit bus (DATA0..DATA7)
        bus[0]                   # Access net by index
        bus[0:4]                 # Slice to sub-bus
        bus += other_bus         # Element-wise connection
        bus += [pins]            # Connect pins to bus nets
    
    Attributes:
        name: Bus name (e.g., "DATA", "ADDR").
        width: Number of nets in the bus.
    """
    name: str = ""
    _nets: list[Net] = field(default_factory=list, repr=False)
    
    # Class-level counter for anonymous buses
    _counter: int = 0
    
    def __init__(
        self, 
        name: str = "", 
        width: int = 0,
        *args,  # Additional nets/pins to include
    ):
        """
        Initialize a bus.
        
        Args:
            name: Bus name. If empty, auto-generated.
            width: Number of nets to create. If 0 and args provided, 
                   width is determined by args.
            *args: Nets, pins, or other items to include in the bus.
        """
        if not name:
            Bus._counter += 1
            name = f"Bus{Bus._counter}"
        
        self.name = name
        self._nets = []
        
        # Create nets based on width
        if width > 0:
            for i in range(width):
                self._nets.append(Net(f"{name}{i}"))
        
        # Add any additional items from args
        for item in args:
            if isinstance(item, Net):
                self._nets.append(item)
            elif isinstance(item, Bus):
                self._nets.extend(item._nets)
            elif hasattr(item, '__iter__'):
                for sub in item:
                    if isinstance(sub, Net):
                        self._nets.append(sub)
    
    @property
    def width(self) -> int:
        """Number of nets in the bus."""
        return len(self._nets)
    
    @property
    def nets(self) -> list[Net]:
        """List of nets in the bus (read-only copy)."""
        return list(self._nets)
    
    def __len__(self) -> int:
        """Number of nets in the bus."""
        return len(self._nets)
    
    def __getitem__(self, key: int | slice | str) -> Net | "Bus":
        """
        Access nets by index, slice, or name pattern.
        
        Examples:
            bus[0]       # First net
            bus[0:4]     # Sub-bus with first 4 nets
            bus[-1]      # Last net
        """
        if isinstance(key, int):
            return self._nets[key]
        elif isinstance(key, slice):
            return Bus(f"{self.name}_slice", 0, *self._nets[key])
        elif isinstance(key, str):
            # Find net by name
            for net in self._nets:
                if net.name == key:
                    return net
            raise KeyError(f"No net named {key!r} in bus {self.name}")
        else:
            raise TypeError(f"Bus indices must be int, slice, or str, not {type(key)}")
    
    def __iter__(self) -> Iterator[Net]:
        """Iterate over nets in the bus."""
        return iter(self._nets)
    
    def __iadd__(self, other) -> "Bus":
        """
        Connect items to bus nets using += operator.
        
        Element-wise connection for equal-width buses/lists.
        
        Examples:
            bus1 += bus2           # Connect net[i] to net[i]
            bus += [pin1, pin2]    # Connect pin[i] to net[i]
            bus += part['D0:D7']   # Connect matching pins
        """
        from .pin import Pin
        from .part import Part
        
        if isinstance(other, Bus):
            if len(other) != len(self):
                raise ValueError(
                    f"Bus width mismatch: {self.name}[{len(self)}] vs {other.name}[{len(other)}]"
                )
            for my_net, other_net in zip(self._nets, other._nets):
                # Merge nets by moving pins from other_net to my_net
                for pin in list(other_net.pins):  # Copy list to allow modification
                    pin.disconnect()  # Disconnect from old net
                    pin.connect(my_net)  # Connect to new net
            return self
        
        elif isinstance(other, Net):
            # Connect single net to all bus nets (creates short - usually an error)
            raise ValueError(
                f"Cannot connect single Net to Bus (would short all {len(self)} nets). "
                "Use explicit indexing: bus[i] += net"
            )
        
        elif isinstance(other, Pin):
            # Connect single pin to all bus nets (creates short - usually an error)  
            raise ValueError(
                f"Cannot connect single Pin to Bus (would short all {len(self)} nets). "
                "Use explicit indexing: bus[i] += pin"
            )
        
        elif hasattr(other, '__iter__'):
            items = list(other)
            if len(items) != len(self):
                raise ValueError(
                    f"Length mismatch: bus[{len(self)}] vs items[{len(items)}]"
                )
            for net, item in zip(self._nets, items):
                if isinstance(item, Pin):
                    item.connect(net)
                elif isinstance(item, Net):
                    for pin in item.pins:
                        pin.connect(net)
                else:
                    raise TypeError(f"Cannot connect {type(item)} to Bus")
            return self
        
        else:
            raise TypeError(f"Cannot connect {type(other)} to Bus")
    
    def __repr__(self) -> str:
        return f"Bus({self.name!r}, width={len(self)})"


class PinGroup:
    """
    A group of pins from a part, behaving like a bus for connections.
    
    Returned by Part[...] when multiple pins are matched.
    Supports += operator for element-wise connection.
    """
    
    def __init__(self, pins: list, part=None):
        """
        Initialize pin group.
        
        Args:
            pins: List of Pin objects.
            part: Parent part (for reference in error messages).
        """
        self._pins = list(pins)
        self._part = part
    
    @property
    def pins(self) -> list:
        """List of pins in this group."""
        return list(self._pins)
    
    def __len__(self) -> int:
        return len(self._pins)
    
    def __iter__(self):
        return iter(self._pins)
    
    def __getitem__(self, key: int | slice):
        """Access pins by index or slice."""
        if isinstance(key, int):
            return self._pins[key]
        elif isinstance(key, slice):
            return PinGroup(self._pins[key], self._part)
        raise TypeError(f"PinGroup indices must be int or slice")
    
    def __iadd__(self, other) -> "PinGroup":
        """
        Connect pins to nets/bus using += operator.
        
        Examples:
            part['A0:A7'] += bus    # Connect pins to bus nets
            part['D'] += [nets]     # Connect pins to list of nets
        """
        if isinstance(other, Bus):
            if len(other) != len(self):
                raise ValueError(
                    f"Width mismatch: {len(self)} pins vs bus[{len(other)}]"
                )
            for pin, net in zip(self._pins, other._nets):
                pin.connect(net)
            return self
        
        elif isinstance(other, Net):
            # Connect all pins to same net
            for pin in self._pins:
                pin.connect(other)
            return self
        
        elif hasattr(other, '__iter__'):
            items = list(other)
            if len(items) != len(self):
                raise ValueError(
                    f"Length mismatch: {len(self)} pins vs {len(items)} items"
                )
            for pin, item in zip(self._pins, items):
                if isinstance(item, Net):
                    pin.connect(item)
                else:
                    raise TypeError(f"Cannot connect Pin to {type(item)}")
            return self
        
        else:
            raise TypeError(f"Cannot connect {type(other)} to PinGroup")
    
    def __repr__(self) -> str:
        refs = [p.ref for p in self._pins[:3]]
        if len(self._pins) > 3:
            refs.append("...")
        return f"PinGroup([{', '.join(refs)}])"
