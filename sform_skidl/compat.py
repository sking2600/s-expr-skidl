"""
Additional SKiDL compatibility features.

Group - PCB layout grouping hints
NC - No-connect marker for unused pins
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.part import Part
    from .models.net import Net
    from .models.pin import Pin


@dataclass
class Group:
    """
    Groups parts for PCB layout hints.
    
    Parts in a group are kept together during layout.
    This is metadata for PCB tools, does not affect netlist.
    
    Example:
        with Group("Power Section"):
            u1 = Part('Device', 'LM7805')
            c1, c2 = Part('Device', 'C', dest=TEMPLATE)(2)
    """
    name: str
    parts: list = field(default_factory=list)
    
    def __enter__(self):
        """Context manager for grouping parts."""
        from .api import get_circuit
        self._circuit = get_circuit()
        self._start_count = len(self._circuit.parts)
        return self
    
    def __exit__(self, *args):
        """Capture parts created in context."""
        self.parts = self._circuit.parts[self._start_count:]
        for part in self.parts:
            part._group = self.name
    
    def add(self, *parts):
        """Add parts to group manually."""
        for part in parts:
            self.parts.append(part)
            part._group = self.name


class _NoConnect:
    """
    Singleton for marking pins as intentionally unconnected.
    
    Suppresses ERC warnings for unused pins.
    
    Example:
        u1['NC'] += NC      # Mark no-connect pin
        NC += u1['PA5']     # Unused GPIO
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __iadd__(self, other):
        """NC += pin marks pin as no-connect."""
        self._mark(other)
        return self
    
    def __radd__(self, other):
        """pin += NC also works."""
        self._mark(other)
        return self
    
    def _mark(self, item):
        """Mark pin as no-connect."""
        from .models.pin import Pin
        
        if isinstance(item, Pin):
            item._no_connect = True
        elif hasattr(item, '__iter__'):
            for pin in item:
                if isinstance(pin, Pin):
                    pin._no_connect = True
    
    def __repr__(self):
        return "NC"


# Singleton instance
NC = _NoConnect()


def no_connect(*pins):
    """
    Mark pins as intentionally unconnected.
    
    Alternative function syntax for NC marker.
    
    Example:
        no_connect(u1['NC1'], u1['NC2'])
        no_connect(u1['PA5 PA6 PA7'])
    """
    for pin in pins:
        NC += pin
