"""
BOM (Bill of Materials) generation with pluggable vendor exporters.

Provides flexible export to various PCB vendor formats.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.part import Part


@dataclass
class BOMItem:
    """A single line in the BOM."""
    designators: list[str] = field(default_factory=list)
    value: str = ""
    footprint: str = ""
    quantity: int = 0
    description: str = ""
    # Vendor fields (extensible)
    fields: dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        self.quantity = len(self.designators)


class BOMExporter(ABC):
    """
    Base class for BOM exporters.
    
    Extend this to add support for new PCB vendors.
    
    Example:
        class PCBWayExporter(BOMExporter):
            name = "pcbway"
            
            def get_columns(self):
                return ["Part Number", "Description", "Qty", "Designator"]
    """
    name: str = "generic"
    
    @abstractmethod
    def get_columns(self) -> list[str]:
        """Return column headers for this vendor's format."""
        pass
    
    @abstractmethod
    def format_row(self, item: BOMItem) -> list[str]:
        """Format a BOM item as a row for this vendor."""
        pass
    
    def export(self, items: list[BOMItem], path: str | Path):
        """Export BOM items to a CSV file."""
        path = Path(path)
        with path.open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(self.get_columns())
            for item in items:
                writer.writerow(self.format_row(item))


class GenericExporter(BOMExporter):
    """Generic BOM format with common columns."""
    name = "generic"
    
    def get_columns(self) -> list[str]:
        return ["Designator", "Value", "Footprint", "Quantity", "MPN", "Manufacturer"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            ",".join(sorted(item.designators)),
            item.value,
            item.footprint,
            str(item.quantity),
            item.fields.get("mpn", ""),
            item.fields.get("manufacturer", ""),
        ]


class JLCPCBExporter(BOMExporter):
    """
    JLCPCB BOM format.
    
    JLCPCB expects: Designator, Footprint, Quantity, LCSC Part #
    """
    name = "jlcpcb"
    
    def get_columns(self) -> list[str]:
        return ["Designator", "Footprint", "Quantity", "LCSC Part #"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            ",".join(sorted(item.designators)),
            item.footprint,
            str(item.quantity),
            item.fields.get("jlcpcb", item.fields.get("lcsc", "")),
        ]


class MouserExporter(BOMExporter):
    """Mouser BOM format."""
    name = "mouser"
    
    def get_columns(self) -> list[str]:
        return ["Mouser Part Number", "Qty", "Customer Ref"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.fields.get("mouser", item.fields.get("mpn", "")),
            str(item.quantity),
            ",".join(sorted(item.designators)),
        ]


class DigikeyExporter(BOMExporter):
    """Digi-Key BOM format."""
    name = "digikey"
    
    def get_columns(self) -> list[str]:
        return ["Digi-Key Part Number", "Quantity", "Customer Reference"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.fields.get("digikey", item.fields.get("mpn", "")),
            str(item.quantity),
            ",".join(sorted(item.designators)),
        ]


class PCBWayExporter(BOMExporter):
    """PCBWay BOM format for assembly service."""
    name = "pcbway"
    
    def get_columns(self) -> list[str]:
        return ["Item", "Designator", "Package", "Quantity", "MPN", "Manufacturer"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.value,
            ",".join(sorted(item.designators)),
            item.footprint,
            str(item.quantity),
            item.fields.get("mpn", ""),
            item.fields.get("manufacturer", ""),
        ]


class ArrowExporter(BOMExporter):
    """Arrow Electronics BOM format."""
    name = "arrow"
    
    def get_columns(self) -> list[str]:
        return ["Arrow Part Number", "Manufacturer Part Number", "Qty", "Reference"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.fields.get("arrow", ""),
            item.fields.get("mpn", ""),
            str(item.quantity),
            ",".join(sorted(item.designators)),
        ]


class NewarkExporter(BOMExporter):
    """Newark/element14/Farnell BOM format."""
    name = "newark"
    
    def get_columns(self) -> list[str]:
        return ["Newark Part Number", "Quantity", "Description", "Reference"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.fields.get("newark", item.fields.get("farnell", "")),
            str(item.quantity),
            f"{item.value} {item.footprint}",
            ",".join(sorted(item.designators)),
        ]


class LCSCExporter(BOMExporter):
    """LCSC direct BOM format (alternative to JLCPCB)."""
    name = "lcsc"
    
    def get_columns(self) -> list[str]:
        return ["LCSC Part Number", "Quantity", "Remark"]
    
    def format_row(self, item: BOMItem) -> list[str]:
        return [
            item.fields.get("lcsc", item.fields.get("jlcpcb", "")),
            str(item.quantity),
            ",".join(sorted(item.designators)),
        ]


# Registry of available exporters
_exporters: dict[str, type[BOMExporter]] = {
    "generic": GenericExporter,
    "jlcpcb": JLCPCBExporter,
    "mouser": MouserExporter,
    "digikey": DigikeyExporter,
    "pcbway": PCBWayExporter,
    "arrow": ArrowExporter,
    "newark": NewarkExporter,
    "farnell": NewarkExporter,  # Alias for newark
    "lcsc": LCSCExporter,
}


def register_exporter(exporter_class: type[BOMExporter]):
    """
    Register a custom BOM exporter.
    
    Example:
        class MyVendorExporter(BOMExporter):
            name = "myvendor"
            ...
        
        register_exporter(MyVendorExporter)
    """
    _exporters[exporter_class.name] = exporter_class


def get_exporter(name: str) -> BOMExporter:
    """Get an exporter by name."""
    if name not in _exporters:
        available = ", ".join(_exporters.keys())
        raise ValueError(f"Unknown BOM format: {name!r}. Available: {available}")
    return _exporters[name]()


def generate_bom(
    path: str | Path,
    format: str = "generic",
    circuit=None,
    group_by: str = "value+footprint",
):
    """
    Generate a Bill of Materials.
    
    Args:
        path: Output file path.
        format: Exporter format ("generic", "jlcpcb", "mouser", "digikey").
        circuit: Circuit to export (uses current if None).
        group_by: How to group parts ("value+footprint", "mpn", "none").
        
    Example:
        generate_bom("bom.csv")
        generate_bom("jlcpcb.csv", format="jlcpcb")
    """
    from .api import get_circuit
    
    if circuit is None:
        circuit = get_circuit()
    
    # Group parts into BOM items
    groups: dict[str, BOMItem] = defaultdict(
        lambda: BOMItem(designators=[], fields={})
    )
    
    for part in circuit.parts:
        # Create grouping key
        if group_by == "none":
            key = part.ref
        elif group_by == "mpn":
            key = part.fields.get("mpn", f"{part.value}|{part.footprint}")
        else:  # value+footprint (default)
            key = f"{part.value}|{part.footprint}"
        
        # Add to group
        item = groups[key]
        item.designators.append(part.ref)
        item.value = part.value
        item.footprint = part.footprint
        item.description = part.name
        
        # Merge fields (vendor part numbers)
        for field_name, field_value in part.fields.items():
            if field_value:
                item.fields[field_name] = field_value
    
    # Calculate quantities
    items = []
    for item in groups.values():
        item.quantity = len(item.designators)
        items.append(item)
    
    # Sort by designator
    items.sort(key=lambda x: x.designators[0] if x.designators else "")
    
    # Export
    exporter = get_exporter(format)
    exporter.export(items, path)
    
    print(f"BOM: {len(items)} line items, {sum(i.quantity for i in items)} total parts")
    print(f"  → {path}")


def reduce_bom(circuit=None, verbose: bool = True, apply: bool = False) -> dict[str, list[str]]:
    """
    Analyze BOM for consolidation opportunities.
    
    Identifies parts that can be merged using stricter specifications.
    e.g., use 1 part for both 1% and 5% tolerance requirements.
    
    By default, this only REPORTS suggestions without modifying parts.
    Set apply=True to actually update part tolerances.
    
    Args:
        circuit: Circuit to analyze (uses current if None)
        verbose: Print consolidation report
        apply: If True, actually modify part tolerances. If False (default),
               only report opportunities without changing anything.
        
    Returns:
        Dict mapping new part key to list of refs that could be consolidated.
        
    Example:
        reduce_bom()                  # Preview only
        reduce_bom(apply=True)        # Apply consolidations
    """
    from .api import get_circuit
    
    if circuit is None:
        circuit = get_circuit()
    
    # Tolerance hierarchy for consolidation
    TOLERANCE_ORDER = ['0.1%', '0.5%', '1%', '2%', '5%', '10%', '20%']
    
    # Group parts by type+value+footprint, ignoring tolerance
    groups: dict[str, list] = {}
    for part in circuit.parts:
        # Key without tolerance
        key = f"{part.name}|{part.value}|{part.footprint}"
        groups.setdefault(key, []).append(part)
    
    consolidations = {}
    savings = 0
    
    for key, parts in groups.items():
        if len(parts) <= 1:
            continue
        
        # Get tolerances for each part
        tolerances = {}
        for p in parts:
            tol = p.fields.get('tolerance', '5%')  # Default 5%
            try:
                idx = TOLERANCE_ORDER.index(tol)
            except ValueError:
                idx = 4  # Default to 5% if unknown
            tolerances[p.ref] = (idx, tol)
        
        # Find the tightest (lowest index) tolerance
        min_idx = min(t[0] for t in tolerances.values())
        tightest_tol = TOLERANCE_ORDER[min_idx]
        
        # Check if we can consolidate (all parts could use the tightest)
        could_consolidate = []
        for p in parts:
            p_idx = tolerances[p.ref][0]
            if p_idx >= min_idx:  # Can use tighter tolerance
                could_consolidate.append(p)
        
        if len(could_consolidate) > 1:
            # We can consolidate these parts
            refs = [p.ref for p in could_consolidate]
            new_key = f"{parts[0].name} {parts[0].value} {parts[0].footprint} {tightest_tol}"
            consolidations[new_key] = refs
            
            # Only update parts if apply=True
            if apply:
                for p in could_consolidate:
                    p.fields['tolerance'] = tightest_tol
            
            # Count unique line items saved
            unique_tolerances = len(set(t[1] for t in tolerances.values()))
            if unique_tolerances > 1:
                savings += unique_tolerances - 1
    
    if verbose:
        if consolidations:
            print(f"\n🔧 BOM REDUCTION: {savings} line items can be consolidated\n")
            for new_part, refs in consolidations.items():
                print(f"  {new_part}")
                print(f"    → {', '.join(refs)}")
            print()
        else:
            print("\n✓ BOM already optimized - no consolidation opportunities found\n")
    
    return consolidations


def list_exporters() -> list[str]:
    """List all available BOM exporter formats."""
    return list(_exporters.keys())
