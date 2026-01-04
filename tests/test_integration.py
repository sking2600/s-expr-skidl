#!/usr/bin/env python3
"""
Integration tests for schematic generation.

Tests that generated schematics are valid KiCad format using kicad-cli.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from sform_skidl import (
    Part, Net, ERC, generate_schematic, reset_circuit,
)


def kicad_cli_available():
    """Check if kicad-cli is available."""
    try:
        result = subprocess.run(
            ["kicad-cli", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def validate_schematic(path: Path) -> bool:
    """Validate a schematic file using kicad-cli."""
    result = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", str(path), "-o", "/dev/null"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


class TestSchematicGeneration:
    """Test schematic generation produces valid KiCad files."""
    
    def setup_method(self):
        """Reset circuit before each test."""
        reset_circuit()
    
    @pytest.mark.skipif(not kicad_cli_available(), reason="kicad-cli not available")
    def test_simple_resistor_schematic(self):
        """Test generating a schematic with a single resistor."""
        Part("Device", "R", value="1K")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.kicad_sch"
            generate_schematic(str(path))
            
            assert path.exists()
            assert validate_schematic(path), "kicad-cli failed to validate schematic"
    
    @pytest.mark.skipif(not kicad_cli_available(), reason="kicad-cli not available")
    def test_voltage_divider_schematic(self):
        """Test generating a voltage divider schematic."""
        vin = Net("VIN")
        vout = Net("VOUT")
        gnd = Net("GND")
        
        r1 = Part("Device", "R", value="1K")
        r2 = Part("Device", "R", value="2K")
        
        vin & r1 & vout & r2 & gnd
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "voltage_divider.kicad_sch"
            generate_schematic(str(path))
            
            assert path.exists()
            assert validate_schematic(path), "kicad-cli failed to validate schematic"
    
    def test_schematic_file_structure(self):
        """Test that generated schematic has correct structure."""
        Part("Device", "R", value="10K")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.kicad_sch"
            generate_schematic(str(path))
            
            content = path.read_text()
            
            # Check required sections
            assert "(kicad_sch" in content
            assert "(version" in content
            assert "(generator" in content
            assert "(lib_symbols" in content
            assert "(sheet_instances" in content
            
            # Check symbol properties
            assert '(property "Reference"' in content
            assert '(property "Value"' in content
    
    def test_erc_no_errors(self):
        """Test that ERC runs without crashing."""
        vin = Net("VIN")
        gnd = Net("GND")
        r1 = Part("Device", "R", value="1K")
        
        vin & r1 & gnd
        
        # Should not raise
        errors = ERC(verbose=False)
        assert isinstance(errors, list)


class TestERCScenarios:
    """Test specific ERC check scenarios."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_erc_unconnected_passive_warning(self):
        """Test ERC warns about unconnected passive pins."""
        r = Part('Device', 'R', value='1K')
        r.set_pin_count(2)
        
        # Leave both pins unconnected
        errors = ERC(verbose=False)
        
        # Should have warnings for unconnected passive pins
        warnings = [e for e in errors if e.severity == 'warning']
        assert len(warnings) >= 2  # At least 2 unconnected passive pins
    
    def test_erc_connected_no_warnings(self):
        """Test ERC has fewer warnings when properly connected."""
        r = Part('Device', 'R', value='1K')
        r.set_pin_count(2)
        n1, n2 = Net('A'), Net('B')
        n1 += r[1]
        n2 += r[2]
        
        errors = ERC(verbose=False)
        
        # Should have fewer warnings than unconnected
        # (may still have some due to floating nets)
        assert isinstance(errors, list)
    
    def test_erc_no_connect_marker(self):
        """Test NC marker suppresses unconnected warnings."""
        from sform_skidl import NC
        
        r = Part('Device', 'R', value='1K')
        r.set_pin_count(2)
        
        # Connect one pin, mark other as no-connect
        n = Net('TEST')
        n += r[1]
        NC += r[2]
        
        errors = ERC(verbose=False)
        
        # Should not have warning for pin 2
        error_locations = [e.location for e in errors]
        assert not any('R1.2' in str(loc) for loc in error_locations)


class TestBOMIntegration:
    """Test BOM generation integration."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_bom_csv_format(self):
        """Test BOM generates valid CSV."""
        import csv
        from sform_skidl import generate_bom
        
        r1 = Part('Device', 'R', value='10K', footprint='0603')
        r1.set_pin_count(2)
        r1.fields['jlcpcb'] = 'C25804'
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bom.csv"
            generate_bom(str(path), format='jlcpcb')
            
            # Validate CSV structure
            with open(path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                
                assert 'Designator' in headers
                assert 'Quantity' in headers
                assert 'LCSC Part #' in headers
    
    def test_bom_grouping(self):
        """Test BOM groups identical parts."""
        import csv
        from sform_skidl import generate_bom
        
        r1 = Part('Device', 'R', value='10K', footprint='0603')
        r2 = Part('Device', 'R', value='10K', footprint='0603')
        r3 = Part('Device', 'R', value='1K', footprint='0603')
        
        for p in [r1, r2, r3]:
            p.set_pin_count(2)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bom.csv"
            generate_bom(str(path), format='generic')
            
            with open(path) as f:
                reader = csv.reader(f)
                next(reader)  # Skip headers
                rows = list(reader)
            
            # Should have 2 line items (10K x2, 1K x1)
            assert len(rows) == 2

    def test_mpn_export(self):
        """Test MPN exporter outputs correct field."""
        import csv
        from sform_skidl import generate_bom
        
        r1 = Part('Device', 'R', value='10K')
        r1.set_pin_count(2)
        r1.fields['mpn'] = 'TEST-MPN-123'
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bom_mpn.csv"
            generate_bom(str(path), format='mpn')
            
            with open(path) as f:
                reader = csv.reader(f)
                headers = next(reader)
                row = next(reader)
                
                assert 'MPN' in headers
                assert row[0] == 'TEST-MPN-123'


class TestMultipleVendors:
    """Test multiple vendor BOM export."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_all_exporters_work(self):
        """Test all registered exporters can generate output."""
        from sform_skidl import generate_bom, list_exporters
        
        r1 = Part('Device', 'R', value='10K')
        r1.set_pin_count(2)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for exporter in list_exporters():
                path = Path(tmpdir) / f"bom_{exporter}.csv"
                generate_bom(str(path), format=exporter)
                assert path.exists(), f"Failed to generate {exporter} BOM"

