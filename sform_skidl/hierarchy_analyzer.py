"""
Hierarchy Analysis for Schematic Generation.
"""

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Set, Dict, List

from .models.part import Part
from .models.net import Net

@dataclass
class HierarchyNode:
    name: str  # Hierarchy path (e.g. "", "regulator_1")
    parts: List[Part] = field(default_factory=list)
    children: Dict[str, 'HierarchyNode'] = field(default_factory=dict)
    ports: List[Net] = field(default_factory=list)  # Nets that cross boundary (List to avoid hash requirement)
    
    @property
    def is_root(self):
        return self.name == ""

class HierarchyAnalyzer:
    def __init__(self, parts: List[Part], nets: List[Net]):
        self.parts = parts
        self.nets = nets
        self.nodes: Dict[str, HierarchyNode] = {}
        
    def analyze(self) -> HierarchyNode:
        # 1. Partition Parts
        for part in self.parts:
            # part.hierarchy assumed to be set (default "")
            h_path = getattr(part, "hierarchy", "")
            if h_path not in self.nodes:
                self.nodes[h_path] = HierarchyNode(name=h_path)
            self.nodes[h_path].parts.append(part)
            
        # Ensure Root exists
        if "" not in self.nodes:
            self.nodes[""] = HierarchyNode(name="")
            
        # 2. Analyze Nets for Ports
        # Map NetID -> Set of Hierarchy Paths it touches
        net_ownership: Dict[int, Set[str]] = defaultdict(set)
        net_map: Dict[int, Net] = {}
        
        for net in self.nets:
            net_id = id(net)
            net_map[net_id] = net
            for pin in net.pins:
                if pin.part:
                    h_path = getattr(pin.part, "hierarchy", "")
                    net_ownership[net_id].add(h_path)
                    
        # 3. Identify Ports
        root = self.nodes[""]
        
        for h_path, node in self.nodes.items():
            if h_path == "": continue
            
            # Check Nets
            for net_id, owners in net_ownership.items():
                if h_path in owners:
                    # Does it touch others?
                    if len(owners) > 1:
                        # Shared net -> PORT
                        net = net_map[net_id]
                        if net not in node.ports:
                            node.ports.append(net)
                        pass

        # 4. Build Tree
        return root

    def get_sheet_structure(self) -> Dict[str, HierarchyNode]:
        return self.nodes
