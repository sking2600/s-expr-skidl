"""
Network topology helpers for complex net connections.

Provides tee() and star() for common connection patterns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.net import Net
    from .models.pin import Pin
    from .models.part import Part


class Network:
    """
    Network topology helper for connecting multiple items.
    
    Provides tee() and star() connection patterns commonly used
    in power distribution and signal routing.
    
    Example:
        # Tee connection (daisy-chain with stub)
        Network.tee(vcc, [r1[1], r2[1], r3[1]])
        
        # Star connection (central node to all)
        Network.star(gnd, [c1[2], c2[2], c3[2], c4[2]])
    """
    
    @staticmethod
    def tee(net: "Net", items: list, stub_net: "Net | None" = None) -> "Net":
        """
        Create a tee connection pattern.
        
        Connects items in a chain with the net, optionally with a stub.
        
        Args:
            net: The main net to connect to.
            items: List of pins or parts to connect.
            stub_net: Optional stub net branching off.
            
        Returns:
            The net with all connections made.
            
        Example:
            Network.tee(vcc, [u1['VCC'], u2['VCC'], u3['VCC']])
        """
        for item in items:
            net += item
        
        if stub_net is not None:
            # Merge stub into main net
            stub_net += net
        
        return net
    
    @staticmethod
    def star(center_net: "Net", items: list) -> "Net":
        """
        Create a star connection pattern.
        
        All items connect to a central net (common for power/ground).
        
        Args:
            center_net: The central net all items connect to.
            items: List of pins or parts to connect.
            
        Returns:
            The center net with all connections made.
            
        Example:
            Network.star(gnd, [r1[2], r2[2], c1[2], c2[2]])
        """
        for item in items:
            center_net += item
        return center_net
    
    @staticmethod
    def bus_connect(bus, pins: list) -> None:
        """
        Connect a bus to a list of pins element-wise.
        
        Args:
            bus: Bus object with multiple nets.
            pins: List of pins (same length as bus).
            
        Raises:
            ValueError: If lengths don't match.
        """
        if len(bus) != len(pins):
            raise ValueError(f"Bus length {len(bus)} != pins length {len(pins)}")
        
        for net, pin in zip(bus, pins):
            net += pin


def tee(net: "Net", items: list, stub_net: "Net | None" = None) -> "Net":
    """Convenience function for Network.tee()."""
    return Network.tee(net, items, stub_net)


def star(center_net: "Net", items: list) -> "Net":
    """Convenience function for Network.star()."""
    return Network.star(center_net, items)
