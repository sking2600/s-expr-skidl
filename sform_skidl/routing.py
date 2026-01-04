"""
Grid-based Manhattan Router for Schematic generation.
"""

from dataclasses import dataclass
from typing import List, Tuple, Set
import heapq
import math

@dataclass(frozen=True)
class Point:
    x: float
    y: float
    
    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)
        
    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)
        
    def __lt__(self, other):
        return (self.x, self.y) < (other.x, other.y)
        
    def dist(self, other):
        return abs(self.x - other.x) + abs(self.y - other.y)

@dataclass
class Rect:
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    
    def expand(self, margin: float):
        return Rect(self.min_x - margin, self.min_y - margin, 
                   self.max_x + margin, self.max_y + margin)
    
    def contains(self, p: Point) -> bool:
        return (self.min_x <= p.x <= self.max_x) and (self.min_y <= p.y <= self.max_y)

class Router:
    def __init__(self, grid_size=1.27):
        self.grid_size = grid_size
        self.obstacles: List[Rect] = []
        
    def add_obstacle(self, x, y, width, height):
        # x, y is center
        half_w = width / 2
        half_h = height / 2
        # Add slight margin to avoid grazing
        r = Rect(x - half_w, y - half_h, x + half_w, y + half_h)
        self.obstacles.append(r.expand(self.grid_size * 0.5))
        
    def _snap(self, val):
        return round(val / self.grid_size) * self.grid_size
        
    def route(self, start: Tuple[float, float], end: Tuple[float, float]) -> List[Tuple[float, float]]:
        # A* Search
        start_p = Point(self._snap(start[0]), self._snap(start[1]))
        end_p = Point(self._snap(end[0]), self._snap(end[1]))
        
        if start_p == end_p:
            return [start, end]
            
        open_set = []
        heapq.heappush(open_set, (0, start_p))
        
        came_from = {}
        g_score = {start_p: 0}
        f_score = {start_p: start_p.dist(end_p)}
        
        # Directions: Up, Down, Left, Right
        directions = [Point(0, self.grid_size), Point(0, -self.grid_size), 
                      Point(self.grid_size, 0), Point(-self.grid_size, 0)]
        
        visited = set()
        
        # Limit search to avoid infinite loops in open space
        max_steps = 2000 
        steps = 0
        
        while open_set:
            steps += 1
            if steps > max_steps:
                # Fallback to direct routing if stuck
                return [start, (end[0], start[1]), end]
                
            current = heapq.heappop(open_set)[1]
            
            if current == end_p:
                return self._reconstruct_path(came_from, current)
                
            visited.add(current)
            
            for d in directions:
                neighbor = current + d
                
                # Check bounds/obstacles
                # Allow endpoint to be inside obstacle (it's the pin)
                is_blocked = False
                if neighbor != start_p and neighbor != end_p:
                    for obs in self.obstacles:
                        if obs.contains(neighbor):
                            is_blocked = True
                            break
                
                if is_blocked:
                    continue
                    
                # Cost: Base 1. Penalty for turns?
                # Simple implementation: Cost = distance
                tentative_g = g_score[current] + self.grid_size
                
                # Penalty for turning
                if current in came_from:
                    prev = came_from[current]
                    prev_dir = current - prev
                    curr_dir = neighbor - current
                    if prev_dir != curr_dir:
                        tentative_g += self.grid_size # Turn cost
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + neighbor.dist(end_p)
                    if neighbor not in [i[1] for i in open_set]:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
                        
        # Fallback
        return [start, (end[0], start[1]), end]

    def _reconstruct_path(self, came_from, current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return [(p.x, p.y) for p in path]
