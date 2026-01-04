"""
Tests for new SKiDL features: Network, SPICE, Part.copy(), Pin.aliases.
"""

import pytest
import tempfile
from pathlib import Path

from sform_skidl import (
    Part, Net, reset_circuit,
    Network, tee, star,
    generate_spice,
)


class TestNetwork:
    """Tests for Network topology helpers."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_star_connection(self):
        """Test star topology connects all items to center."""
        gnd = Net('GND')
        r1 = Part('Device', 'R', value='1K')
        r2 = Part('Device', 'R', value='1K')
        c1 = Part('Device', 'C', value='100nF')
        
        for p in [r1, r2, c1]:
            p.set_pin_count(2)
        
        # Star connect pin 2 of all to GND
        star(gnd, [r1[2], r2[2], c1[2]])
        
        assert len(gnd.pins) == 3
        assert r1[2].net is gnd
        assert r2[2].net is gnd
        assert c1[2].net is gnd
    
    def test_tee_connection(self):
        """Test tee topology connects all items to net."""
        vcc = Net('VCC')
        r1 = Part('Device', 'R', value='1K')
        r2 = Part('Device', 'R', value='1K')
        
        for p in [r1, r2]:
            p.set_pin_count(2)
        
        tee(vcc, [r1[1], r2[1]])
        
        assert len(vcc.pins) == 2
        assert r1[1].net is vcc
    
    def test_network_class_methods(self):
        """Test Network class static methods."""
        gnd = Net('GND')
        r1 = Part('Device', 'R', value='1K')
        r1.set_pin_count(2)
        
        Network.star(gnd, [r1[2]])
        assert r1[2].net is gnd


class TestSpice:
    """Tests for SPICE netlist generation."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_generate_spice_string(self):
        """Test SPICE netlist generation returns string."""
        r1 = Part('Device', 'R', value='1K')
        r1.set_pin_count(2)
        
        n1, n2 = Net('IN'), Net('GND')
        n1 += r1[1]
        n2 += r1[2]
        
        spice = generate_spice()
        
        # Check for resistor line (R followed by digits)
        assert 'R' in spice and '1K' in spice
        assert '.end' in spice
    
    def test_generate_spice_file(self):
        """Test SPICE netlist saves to file."""
        r1 = Part('Device', 'R', value='10K')
        r1.set_pin_count(2)
        
        n1, n2 = Net('VIN'), Net('GND')
        n1 += r1[1]
        n2 += r1[2]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'test.spice'
            generate_spice(str(path))
            
            assert path.exists()
            content = path.read_text()
            # Check for resistor and value
            assert 'R' in content and '10K' in content


class TestPartCopy:
    """Tests for Part.copy() method."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_copy_basic(self):
        """Test Part.copy() creates new instance."""
        r1 = Part('Device', 'R', value='10K')
        r1.set_pin_count(2)
        
        r2 = r1.copy()
        
        assert r2 is not r1
        assert r2.value == '10K'
        assert r2.ref != r1.ref  # Different ref
    
    def test_copy_with_override(self):
        """Test Part.copy() with value override."""
        r1 = Part('Device', 'R', value='10K')
        r1.set_pin_count(2)
        
        r2 = r1.copy(value='20K')
        
        assert r2.value == '20K'
        assert r1.value == '10K'  # Original unchanged


class TestPinAliases:
    """Tests for Pin.aliases feature."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_add_alias(self):
        """Test adding aliases to a pin."""
        r1 = Part('Device', 'R', value='1K')
        r1.set_pin_count(2)
        
        pin = r1[1]
        pin.add_alias('VCC', '3V3')
        
        assert 'VCC' in pin.aliases
        assert '3V3' in pin.aliases
    
    def test_add_alias_no_duplicates(self):
        """Test aliases don't duplicate."""
        r1 = Part('Device', 'R', value='1K')
        r1.set_pin_count(2)
        
        pin = r1[1]
        pin.add_alias('VCC')
        pin.add_alias('VCC')  # Duplicate
        
        assert pin.aliases.count('VCC') == 1
