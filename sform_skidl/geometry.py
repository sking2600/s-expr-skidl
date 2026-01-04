"""
Geometry primitives for schematic layout.

Handles coordinate systems, transformations, and distance calculations
uniformly across the library.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class Point:
    """A point in 2D space."""
    x: float
    y: float

    def __lt__(self, other: Point) -> bool:
        return (self.x, self.y) < (other.x, other.y)
    
    def __add__(self, other: Point | Vector | tuple) -> Point:
        if isinstance(other, (Point, Vector)):
            return Point(self.x + other.x, self.y + other.y)
        return Point(self.x + other[0], self.y + other[1])
    
    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

@dataclass
class Vector:
    """A vector in 2D space."""
    dx: float
    dy: float
    
    @property
    def magnitude(self) -> float:
        return math.hypot(self.dx, self.dy)

class Transform:
    """
    Affine transformation for symbol placement.
    
    KiCad Rotation reference (Counter-Clockwise):
    - 0: No rotation
    - 90: Rotated 90 deg CCW
    """
    def __init__(self, x: float, y: float, rotation: int = 0):
        self.x = x
        self.y = y
        self.rotation = rotation
    
    def transform_point(self, pt: tuple[float, float] | Point) -> Point:
        """Apply rotation then translation to a point relative to (0,0)."""
        px = pt.x if isinstance(pt, Point) else pt[0]
        py = pt.y if isinstance(pt, Point) else pt[1]
        
        # Apply Rotation
        # Standard math CCW rotation:
        # x' = x cos θ - y sin θ
        # y' = x sin θ + y cos θ
        
        rad = math.radians(self.rotation)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        # Determine integer-like rotation for precision
        if self.rotation % 90 == 0:
            rot = self.rotation % 360
            if rot == 0:
                rx, ry = px, py
            elif rot == 90:
                rx, ry = -py, px  # CCW 90: (1,0) -> (0,1) | (0,1) -> (-1,0) -> x=0, y=1?
                # KiCad 90 is R 90.
                # If point is (10, 0) (Right), R90 puts it at (0, 10) (Bottom? No, Up in Math).
                # In KiCad (+Y Down), Up is -Y.
                # So if we use Math coords internally, (0, 10) is Up.
                # If we use KiCad coords internally, (0, 10) is Down.
                # Let's STICK TO KICAD COORDS consistently.
                # In KiCad Editor: (+X Right, +Y Down).
                # Rotation is CCW (Standard).
                # If I have a point at (10, 0) (Right). Rotate 90 CCW.
                # It goes UP. Up is -Y. So (0, -10).
                # Math: (10,0) -> (0, 10). (+Y is Up).
                # So KiCad R90 behavior: (x, y) -> (y, -x).
                rx, ry = py, -px
            elif rot == 180:
                rx, ry = -px, -py
            elif rot == 270:
                rx, ry = -py, px
            else:
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
        else:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            
        # Apply Translation
        return Point(rx + self.x, ry + self.y)

def kicad_rotation_matrix(rot: int, x: float, y: float) -> tuple[float, float]:
    """
    Apply KiCad specific rotation to a point (x,y).
    KiCad Coordinate System: +X Right, +Y Down.
    Rotation is Counter-Clockwise.
    """
    rot = rot % 360
    if rot == 0:
        return x, y
    elif rot == 90:
        return y, -x 
    elif rot == 180:
        return -x, -y
    elif rot == 270:
        return -y, x
    return x, y # Fallback
