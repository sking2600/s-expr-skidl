"""
Hierarchy support for subcircuits and interfaces.

Provides SKiDL-compatible hierarchical design features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable
import contextvars

from .models.net import Net


# Context variable for tracking subcircuit hierarchy
_subcircuit_stack: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    '_subcircuit_stack', default=[]
)


def get_hierarchy_prefix() -> str:
    """Get current hierarchical prefix for naming."""
    stack = _subcircuit_stack.get()
    if stack:
        return ".".join(stack) + "."
    return ""


class SubCircuitContext:
    """Context manager for subcircuit scope."""
    
    def __init__(self, name: str):
        self.name = name
        self._token = None
    
    def __enter__(self):
        stack = _subcircuit_stack.get().copy()
        stack.append(self.name)
        self._token = _subcircuit_stack.set(stack)
        return self
    
    def __exit__(self, *args):
        if self._token:
            _subcircuit_stack.reset(self._token)


def subcircuit(func: Callable) -> Callable:
    """
    Decorator to create a reusable subcircuit.
    
    The decorated function acts as a circuit module that can be
    instantiated multiple times. Parameters are typically nets
    that connect to the subcircuit's ports.
    
    Example:
        @subcircuit
        def voltage_divider(vin, vout, gnd, r_top='1K', r_bot='1K'):
            from sform_skidl import Part
            r1 = Part('Device', 'R', value=r_top)
            r2 = Part('Device', 'R', value=r_bot)
            vin & r1 & vout & r2 & gnd
        
        # Usage
        vcc, mid, gnd_net = Net('VCC'), Net('MID'), Net('GND')
        voltage_divider(vcc, mid, gnd_net)
        voltage_divider(vcc, mid2, gnd_net, r_top='2K')  # Another instance
    """
    # Track instance count for unique naming
    func._instance_count = 0
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        func._instance_count += 1
        instance_name = f"{func.__name__}_{func._instance_count}"
        
        with SubCircuitContext(instance_name):
            return func(*args, **kwargs)
    
    # Mark as subcircuit for introspection
    wrapper._is_subcircuit = True
    wrapper._wrapped_func = func
    
    return wrapper


@dataclass
class Interface:
    """
    Named collection of nets for passing to subcircuits.
    
    Provides a convenient way to group related signals.
    
    Example:
        i2c = Interface(sda=Net('SDA'), scl=Net('SCL'))
        i2c_device(i2c.sda, i2c.scl, addr=0x50)
        
        # Or using dict-style access
        for name, net in i2c.items():
            print(f"{name}: {net}")
    """
    _nets: dict[str, Net] = field(default_factory=dict)
    
    def __init__(self, **kwargs):
        """Create interface with named nets."""
        object.__setattr__(self, '_nets', {})
        for name, value in kwargs.items():
            if isinstance(value, Net):
                self._nets[name] = value
            else:
                raise TypeError(f"Interface values must be Net, got {type(value)}")
    
    def __getattr__(self, name: str) -> Net:
        """Access net by attribute name."""
        if name.startswith('_'):
            raise AttributeError(name)
        nets = object.__getattribute__(self, '_nets')
        if name in nets:
            return nets[name]
        raise AttributeError(f"Interface has no net '{name}'")
    
    def __setattr__(self, name: str, value: Net):
        """Set net by attribute name."""
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        elif isinstance(value, Net):
            self._nets[name] = value
        else:
            raise TypeError(f"Interface values must be Net, got {type(value)}")
    
    def __getitem__(self, name: str) -> Net:
        """Dict-style access to nets."""
        return self._nets[name]
    
    def __iter__(self):
        """Iterate over net names."""
        return iter(self._nets)
    
    def items(self):
        """Return (name, net) pairs."""
        return self._nets.items()
    
    def keys(self):
        """Return net names."""
        return self._nets.keys()
    
    def values(self):
        """Return nets."""
        return self._nets.values()
    
    def __repr__(self):
        nets = ", ".join(f"{k}={v.name}" for k, v in self._nets.items())
        return f"Interface({nets})"
