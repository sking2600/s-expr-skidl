"""
Vendor-agnostic parts database and resolver.

Users can define parts generically, then use a parts database
to resolve vendor-specific part numbers for BOM export.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.part import Part


@dataclass
class PartSpec:
    """
    Vendor-agnostic part specification.
    
    Matches parts generically and resolves to vendor-specific numbers.
    Supports stock type filtering for JLCPCB basic/extended parts.
    
    Tolerance/rating matching uses hierarchy: stricter specs satisfy looser requirements.
    e.g., a 1% resistor in the database can satisfy a part spec'd as 5%.
    """
    type: str  # 'R', 'C', 'L', 'LED', 'opamp', etc.
    value: str = ""
    package: str = ""  # '0402', '0603', 'SOT-23'
    tolerance: str = ""  # '1%', '5%', '10%'
    rating: str = ""  # voltage, current, power (e.g., '50V', '0.25W')
    description: str = ""  # additional matching criteria
    
    # Stock type: 'basic', 'extended', 'any'
    stock_type: str = "any"
    
    # Vendor part numbers
    vendors: dict[str, str] = field(default_factory=dict)
    
    # Alternative generic parts
    alternatives: list[str] = field(default_factory=list)
    
    # Tolerance hierarchy (lower index = tighter tolerance, can substitute for higher)
    _TOLERANCE_ORDER = ['0.1%', '0.5%', '1%', '2%', '5%', '10%', '20%']
    
    # Voltage rating hierarchy (higher voltage can substitute for lower)
    _VOLTAGE_ORDER = ['6.3V', '10V', '16V', '25V', '35V', '50V', '63V', '100V', '200V', '250V']
    
    def matches(self, part: "Part", require_stock_type: str | None = None) -> bool:
        """Check if this spec matches a Part."""
        # Stock type filtering
        if require_stock_type and require_stock_type != "any":
            if self.stock_type != "any" and self.stock_type != require_stock_type:
                return False
        
        if self.type and not part.name.upper().startswith(self.type.upper()):
            return False
        if self.value and part.value != self.value:
            return False
        if self.package and self.package not in part.footprint:
            return False
        
        # Tolerance matching: database spec must be same or tighter than part requirement
        if self.tolerance and hasattr(part, 'fields'):
            part_tol = part.fields.get('tolerance', '')
            if part_tol and not self._tolerance_compatible(self.tolerance, part_tol):
                return False
        
        return True
    
    def _tolerance_compatible(self, db_tolerance: str, part_tolerance: str) -> bool:
        """
        Check if database tolerance satisfies part requirement.
        
        A tighter tolerance (lower %) can substitute for a looser one.
        e.g., 1% can substitute for 5%.
        """
        try:
            db_idx = self._TOLERANCE_ORDER.index(db_tolerance)
            part_idx = self._TOLERANCE_ORDER.index(part_tolerance)
            return db_idx <= part_idx  # DB tolerance is same or tighter
        except ValueError:
            # Unknown tolerance, require exact match
            return db_tolerance == part_tolerance


class PartsDatabase:
    """
    Vendor-agnostic parts database.
    
    Users define parts generically, and the database provides
    vendor-specific part numbers.
    
    Example:
        db = PartsDatabase()
        db.add('R', '10K', '0603', jlcpcb='C25804', mouser='603-RC0603FR-0710KL')
        
        # Later, resolve for a circuit
        db.apply_to_circuit(circuit)
        generate_bom('jlcpcb.csv', format='jlcpcb')
    """
    
    def __init__(self, stock_type: str = "any"):
        """
        Initialize parts database.
        
        Args:
            stock_type: Default stock filter ('basic', 'extended', 'any')
                       'basic' = JLCPCB basic parts (no extra fee)
                       'extended' = JLCPCB extended parts
                       'any' = no filter
        """
        self._specs: list[PartSpec] = []
        self.stock_type = stock_type
    
    def add(
        self,
        type: str,
        value: str = "",
        package: str = "",
        tolerance: str = "",
        rating: str = "",
        stock_type: str = "any",
        **vendors,
    ):
        """
        Add a part to the database.
        
        Args:
            type: Part type ('R', 'C', 'L', 'LED', etc.)
            value: Component value ('10K', '100nF')
            package: Package size ('0402', '0603', 'SOT-23')
            tolerance: Tolerance ('1%', '5%')
            rating: Voltage/power rating ('50V', '0.1W')
            stock_type: 'basic', 'extended', or 'any'
            **vendors: Vendor part numbers (jlcpcb='C25804', mouser='...')
        """
        spec = PartSpec(
            type=type,
            value=value,
            package=package,
            tolerance=tolerance,
            rating=rating,
            stock_type=stock_type,
            vendors=vendors,
        )
        self._specs.append(spec)
    
    def find(self, part: "Part", stock_type: str | None = None) -> PartSpec | None:
        """Find matching spec for a part, optionally filtering by stock type."""
        filter_type = stock_type or self.stock_type
        for spec in self._specs:
            if spec.matches(part, require_stock_type=filter_type):
                return spec
        return None
    
    def apply_to_part(self, part: "Part", stock_type: str | None = None) -> bool:
        """
        Apply vendor fields to a part from database.
        
        Returns True if a match was found.
        """
        spec = self.find(part, stock_type)
        if spec:
            for vendor, number in spec.vendors.items():
                part.fields[vendor] = number
            return True
        return False
    
    def apply_to_circuit(self, circuit=None, stock_type: str | None = None, verbose: bool = True):
        """
        Apply vendor fields to all parts in circuit.
        
        Args:
            circuit: Circuit to apply to (uses current if None)
            stock_type: Filter by 'basic', 'extended', or 'any'
            verbose: Print detailed diagnostics
        """
        from .api import get_circuit
        
        if circuit is None:
            circuit = get_circuit()
        
        matched = 0
        unmatched = []
        missing_vendors = []  # Parts matched but missing some vendor numbers
        
        for part in circuit.parts:
            spec = self.find(part, stock_type)
            if spec:
                for vendor, number in spec.vendors.items():
                    part.fields[vendor] = number
                matched += 1
                
                # Check which important vendors are missing
                for vendor in ['jlcpcb', 'mouser', 'digikey']:
                    if vendor not in spec.vendors:
                        missing_vendors.append((part.ref, part.value, vendor))
            else:
                # Diagnose why it didn't match
                reason = self._diagnose_no_match(part, stock_type)
                unmatched.append((part.ref, part.name, part.value, part.footprint, reason))
        
        # Print results
        filter_desc = f" (stock={stock_type or self.stock_type})" if (stock_type or self.stock_type) != "any" else ""
        print(f"Parts database{filter_desc}: {matched} matched, {len(unmatched)} unmatched")
        
        if verbose and unmatched:
            print("\n⚠️  UNMATCHED PARTS:")
            for ref, name, value, footprint, reason in unmatched:
                print(f"  {ref}: {name} {value} ({footprint})")
                print(f"       → {reason}")
        
        if verbose and missing_vendors:
            # Group by vendor
            by_vendor = {}
            for ref, value, vendor in missing_vendors:
                by_vendor.setdefault(vendor, []).append(f"{ref} ({value})")
            
            print("\n📋 MISSING VENDOR NUMBERS:")
            for vendor, parts in sorted(by_vendor.items()):
                print(f"  {vendor}: {', '.join(parts[:5])}")
                if len(parts) > 5:
                    print(f"       ... and {len(parts) - 5} more")
        
        return matched, unmatched
    
    def _diagnose_no_match(self, part, stock_type: str | None) -> str:
        """Diagnose why a part didn't match any spec."""
        filter_type = stock_type or self.stock_type
        
        # Check if there's a partial match
        for spec in self._specs:
            # Check type match
            if not part.name.upper().startswith(spec.type.upper()):
                continue
            
            # Type matches, check value
            if spec.value and spec.value != part.value:
                return f"Value mismatch: database has '{spec.type}' with values {self._list_available_values(spec.type)}"
            
            # Check package
            if spec.package and spec.package not in part.footprint:
                return f"Package mismatch: database has '{spec.value}' in {self._list_available_packages(spec.type, part.value)}"
            
            # Check stock type
            if filter_type != "any" and spec.stock_type != filter_type:
                return f"Stock type mismatch: part is '{spec.stock_type}', filter requires '{filter_type}'"
        
        return f"No matching spec in database for type '{part.name}'"
    
    def _list_available_values(self, part_type: str) -> str:
        """List available values for a part type."""
        values = set()
        for spec in self._specs:
            if spec.type.upper() == part_type.upper() and spec.value:
                values.add(spec.value)
        if values:
            return ', '.join(sorted(values)[:5]) + ('...' if len(values) > 5 else '')
        return "(none defined)"
    
    def _list_available_packages(self, part_type: str, value: str) -> str:
        """List available packages for a part type and value."""
        packages = set()
        for spec in self._specs:
            if spec.type.upper() == part_type.upper():
                if not spec.value or spec.value == value:
                    if spec.package:
                        packages.add(spec.package)
        if packages:
            return ', '.join(sorted(packages))
        return "(none defined)"
    
    def load_csv(self, path: str | Path):
        """
        Load parts database from CSV file.
        
        CSV format: type,value,package,tolerance,rating,jlcpcb,mouser,digikey,...
        """
        path = Path(path)
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendors = {}
                core_fields = {'type', 'value', 'package', 'tolerance', 'rating'}
                for key, val in row.items():
                    if key not in core_fields and val:
                        vendors[key] = val
                
                self.add(
                    type=row.get('type', ''),
                    value=row.get('value', ''),
                    package=row.get('package', ''),
                    tolerance=row.get('tolerance', ''),
                    rating=row.get('rating', ''),
                    **vendors,
                )
    
    def save_csv(self, path: str | Path):
        """Save parts database to CSV file."""
        path = Path(path)
        
        # Collect all vendor columns
        vendor_cols = set()
        for spec in self._specs:
            vendor_cols.update(spec.vendors.keys())
        vendor_cols = sorted(vendor_cols)
        
        with path.open('w', newline='') as f:
            fieldnames = ['type', 'value', 'package', 'tolerance', 'rating'] + vendor_cols
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for spec in self._specs:
                row = {
                    'type': spec.type,
                    'value': spec.value,
                    'package': spec.package,
                    'tolerance': spec.tolerance,
                    'rating': spec.rating,
                }
                row.update(spec.vendors)
                writer.writerow(row)


# Global default database
_default_db: PartsDatabase | None = None


def get_parts_db() -> PartsDatabase:
    """Get or create the default parts database."""
    global _default_db
    if _default_db is None:
        _default_db = PartsDatabase()
    return _default_db


def load_parts_db(path: str | Path) -> PartsDatabase:
    """Load a parts database from CSV."""
    db = PartsDatabase()
    db.load_csv(path)
    global _default_db
    _default_db = db
    return db


def load_bundled_parts(categories: list[str] | None = None) -> PartsDatabase:
    """
    Load bundled parts database with common JLCPCB basic parts.
    
    Args:
        categories: List of categories to load. Options:
                   - 'resistors' (24 common values)
                   - 'capacitors' (21 common values)
                   - 'discretes' (LEDs, diodes, transistors)
                   - 'ics' (regulators, op-amps, logic)
                   If None, loads all categories.
    
    Returns:
        PartsDatabase populated with bundled parts.
        
    Example:
        # Load all bundled parts
        db = load_bundled_parts()
        
        # Load only resistors and capacitors
        db = load_bundled_parts(['resistors', 'capacitors'])
        
        # Apply to circuit
        db.apply_to_circuit()
    
    Note:
        You can always override database values by directly assigning:
        r1.fields['jlcpcb'] = 'C12345'  # Takes precedence
    """
    from pathlib import Path
    
    db = PartsDatabase()
    
    # Find bundled data directory
    data_dir = Path(__file__).parent / 'data'
    
    available = {
        'resistors': 'resistors_basic.csv',
        'capacitors': 'capacitors_basic.csv',
        'discretes': 'discretes_basic.csv',
        'ics': 'ics_basic.csv',
    }
    
    if categories is None:
        categories = list(available.keys())
    
    loaded = 0
    for cat in categories:
        if cat in available:
            csv_path = data_dir / available[cat]
            if csv_path.exists():
                db.load_csv(csv_path)
                loaded += 1
    
    global _default_db
    _default_db = db
    
    print(f"Loaded {len(db._specs)} parts from {loaded} categories")
    return db

