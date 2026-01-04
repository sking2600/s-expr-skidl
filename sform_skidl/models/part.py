"""
Part class for circuit design.

High-level component abstraction with SKiDL-compatible API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
import uuid
import copy

from .pin import Pin, PinType
from .symbol import Symbol

if TYPE_CHECKING:
    from .net import Net


# Destination constants
TEMPLATE = "template"
NETLIST = "netlist"


@dataclass
class Part:
    """
    Represents a circuit component (part).
    
    Supports SKiDL-style instantiation and pin access:
        r = Part("Device", "R", value="10K", footprint="...")
        r[1]       # Access pin by number
        r["VCC"]   # Access pin by name
        r["1 2"]   # Access multiple pins
    
    Attributes:
        lib: Symbol library name (e.g., "Device").
        name: Symbol name (e.g., "R", "C").
        ref: Reference designator (e.g., "R1", "U2").
        value: Component value.
        footprint: Footprint library:name.
        fields: Extra fields (jlcpcb, mpn, manufacturer, etc.).
    """
    lib: str
    name: str
    ref: str = ""
    value: str = ""
    footprint: str = ""
    dest: str = NETLIST
    
    # Extra fields for BOM/vendor data
    fields: dict[str, str] = field(default_factory=dict, repr=False)
    
    # Internal state
    _symbol: Symbol | None = field(default=None, repr=False)
    _pins: dict[str, Pin] = field(default_factory=dict, repr=False)
    _uuid: str = field(default_factory=lambda: str(uuid.uuid4()), repr=False)
    
    # Class-level reference counters
    _ref_counters: dict[str, int] = field(default_factory=dict, repr=False, init=False)
    
    def __post_init__(self):
        """Initialize part with symbol and pins."""
        # Capture hierarchy context
        try:
            from ..hierarchy import get_hierarchy_prefix
            self.hierarchy = get_hierarchy_prefix().rstrip(".")
        except ImportError:
            self.hierarchy = ""

        # Auto-generate reference if not provided
        if not self.ref and self.dest != TEMPLATE:
            prefix = self._get_ref_prefix()
            if not hasattr(Part, '_counters'):
                Part._counters = {}
            Part._counters[prefix] = Part._counters.get(prefix, 0) + 1
            self.ref = f"{prefix}{Part._counters[prefix]}"
        
        # Create symbol if not provided
        if self._symbol is None:
            self._symbol = Symbol(name=self.name)
        
        # Copy pins from symbol
        for pin in self._symbol.pins:
            pin_copy = copy.copy(pin)
            pin_copy._part = self
            self._pins[pin_copy.number] = pin_copy
            if pin_copy.name and pin_copy.name != pin_copy.number:
                self._pins[pin_copy.name] = pin_copy
    
    def _get_ref_prefix(self) -> str:
        """Get reference designator prefix based on part type."""
        if self._symbol:
            return self._symbol.reference
        
        # Common prefixes
        prefixes = {
            "R": "R", "C": "C", "L": "L",
            "D": "D", "LED": "D",
            "Q": "Q", "MOSFET": "Q",
            "U": "U", "IC": "U",
            "J": "J", "P": "P",
            "SW": "SW", "F": "F",
        }
        return prefixes.get(self.name.upper(), "U")
    
    def __getitem__(self, key: str | int) -> "Pin | PinGroup":
        """
        Access pins by number, name, regex pattern, or space-separated list.
        
        Examples:
            part[1]         # Pin by number
            part["VCC"]     # Pin by name
            part["1 2"]     # Multiple pins -> PinGroup
            part["A.*"]     # Regex pattern -> PinGroup
            part["D0:D7"]   # Range notation -> PinGroup
        """
        import re
        from .bus import PinGroup
        
        if isinstance(key, int):
            key = str(key)
        
        # Check for space-separated pin list
        if " " in key:
            pins = [self._get_single_pin(k.strip()) for k in key.split()]
            return PinGroup(pins, self)
        
        # Check for range notation D0:D7
        if ":" in key and not key.startswith("r'"):
            parts = key.split(":")
            if len(parts) == 2:
                # Try to expand range
                start, end = parts
                # Extract prefix and numbers
                match_start = re.match(r'^([A-Za-z_]*)(\d+)$', start)
                match_end = re.match(r'^([A-Za-z_]*)(\d+)$', end)
                if match_start and match_end:
                    prefix_s, num_s = match_start.groups()
                    prefix_e, num_e = match_end.groups()
                    if prefix_s == prefix_e:
                        pins = []
                        for i in range(int(num_s), int(num_e) + 1):
                            name = f"{prefix_s}{i}"
                            if name in self._pins:
                                pins.append(self._pins[name])
                        if pins:
                            return PinGroup(pins, self)
        
        # Check for regex pattern (contains regex metacharacters)
        if any(c in key for c in ['*', '+', '?', '[', ']', '(', ')', '|', '^', '$', '.']):
            try:
                pattern = re.compile(key)
                matching_pins = []
                seen = set()
                for pin_key, pin in self._pins.items():
                    if id(pin) not in seen:
                        if pattern.match(pin.name) or pattern.match(pin.number):
                            matching_pins.append(pin)
                            seen.add(id(pin))
                if matching_pins:
                    return PinGroup(matching_pins, self)
                raise KeyError(f"No pins matching pattern {key!r} in {self.ref}")
            except re.error:
                pass  # Fall through to exact match
        
        # Exact match lookup
        return self._get_single_pin(key)
    
    def _get_single_pin(self, key: str) -> "Pin":
        """Get a single pin by exact name or number."""
        if key in self._pins:
            return self._pins[key]
        raise KeyError(f"Part {self.ref} has no pin {key!r}")
    
    def __call__(self, count: int = 1, **kwargs) -> Part | list[Part]:
        """
        Create one or more instances of this part (template mode).
        
        Examples:
            r = Part("Device", "R", dest=TEMPLATE)
            r1, r2 = r(2)  # Create two resistors
        """
        if count == 1:
            return Part(
                lib=self.lib,
                name=self.name,
                value=kwargs.get("value", self.value),
                footprint=kwargs.get("footprint", self.footprint),
                dest=NETLIST,
                _symbol=self._symbol,
            )
        
        return [self(**kwargs) for _ in range(count)]
    
    def __mul__(self, count: int) -> list[Part]:
        """Create multiple instances: 2 * Part(...) or Part(...) * 2."""
        return self(count)
    
    def __rmul__(self, count: int) -> list[Part]:
        """Right multiplication: 2 * Part(...)."""
        return self(count)
    
    def copy(self, **overrides) -> "Part":
        """
        Create a deep copy of this part with new reference designator.
        
        Args:
            **overrides: Override any Part attributes (value, footprint, etc.)
            
        Returns:
            New Part instance with same properties but new ref.
            
        Example:
            r1 = Part('Device', 'R', value='10K')
            r2 = r1.copy()  # New part R2 with same value
            r3 = r1.copy(value='20K')  # R3 with different value
        """
        return Part(
            lib=overrides.get('lib', self.lib),
            name=overrides.get('name', self.name),
            value=overrides.get('value', self.value),
            footprint=overrides.get('footprint', self.footprint),
            dest=overrides.get('dest', NETLIST),
            _symbol=self._symbol,
        )
    
    @property
    def is_template(self) -> bool:
        """True if this part is a template."""
        return self.dest == TEMPLATE

    @property
    def pins(self) -> list[Pin]:
        """List of all unique pins."""
        seen = set()
        result = []
        for pin in self._pins.values():
            if id(pin) not in seen:
                seen.add(id(pin))
                result.append(pin)
        return result
    
    @property 
    def pin_count(self) -> int:
        """Number of pins."""
        return len(self.pins)
    
    def set_pin_count(self, count: int) -> Part:
        """Set number of pins for generic parts like resistors."""
        from .pin import Pin, PinType, PinStyle
        
        self._pins.clear()
        
        # Determine positions based on pin count
        # NOTE: KiCad Schematic Coordinate System has +Y going DOWN.
        if count == 2:
            # Standard vertical passive (R, C, D, L)
            # Pin 1 (Top) -> Negative Y
            p1 = Pin(number='1', name='1', pin_type=PinType.PASSIVE, style=PinStyle.LINE)
            p1.position = (0.0, -2.54)
            p1.orientation = 270  # Point down (visually Up in symbol editor? check later)
            p1._part = self
            self._pins['1'] = p1
            
            # Pin 2 (Bottom) -> Positive Y
            p2 = Pin(number='2', name='2', pin_type=PinType.PASSIVE, style=PinStyle.LINE)
            p2.position = (0.0, 2.54)
            p2.orientation = 90  # Point up
            p2._part = self
            self._pins['2'] = p2
        else:
            # Generic fanout for other counts
            for i in range(1, count + 1):
                pin = Pin(number=str(i), name=str(i), pin_type=PinType.PASSIVE)
                pin._part = self
                # Alternate left/right
                x = -5.08 if i % 2 else 5.08
                # Fan out vertically centered
                y = (i-1) * 2.54
                pin.position = (x, y)
                self._pins[str(i)] = pin
        
        return self
    
    def add_pin(self, pin: Pin) -> Part:
        """Add a pin to this part."""
        pin._part = self
        self._pins[pin.number] = pin
        if pin.name and pin.name != pin.number:
            self._pins[pin.name] = pin
        return self
    
    def no_connect(self, *pin_keys) -> Part:
        """Mark pins as intentionally unconnected."""
        from ..compat import NC
        for key in pin_keys:
            # Handle list strings "1 2 3"
            if isinstance(key, str) and " " in key:
                for k in key.split():
                    self[k.strip()] & NC
            else:
                self[key] & NC
        return self

    def __repr__(self) -> str:
        return f"Part({self.lib!r}, {self.name!r}, ref={self.ref!r}, value={self.value!r})"


def create_resistor(value: str = "", footprint: str = "") -> Part:
    """Create a 2-pin resistor part."""
    symbol = Symbol(
        name="R",
        properties={"Reference": "R", "Value": value or "R"},
        pins=[
            Pin("1", "1", PinType.PASSIVE, position=(-2.54, 0), orientation=0),
            Pin("2", "2", PinType.PASSIVE, position=(2.54, 0), orientation=180),
        ],
    )
    return Part(lib="Device", name="R", value=value, footprint=footprint, _symbol=symbol)


def create_capacitor(value: str = "", footprint: str = "") -> Part:
    """Create a 2-pin capacitor part."""
    symbol = Symbol(
        name="C",
        properties={"Reference": "C", "Value": value or "C"},
        pins=[
            Pin("1", "1", PinType.PASSIVE, position=(-2.54, 0), orientation=0),
            Pin("2", "2", PinType.PASSIVE, position=(2.54, 0), orientation=180),
        ],
    )
    return Part(lib="Device", name="C", value=value, footprint=footprint, _symbol=symbol)
