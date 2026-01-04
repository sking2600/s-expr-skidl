"""
Additional coverage tests for api.py, bus.py, and symbol_lib.py.
"""

import pytest
import tempfile
from pathlib import Path
from sform_skidl import (
    Part, Net, Pin, PinType, Bus, PinGroup,
    reset_circuit, get_circuit,
    generate_schematic, generate_netlist,
    auto_discover_libs, list_libraries, search_parts,
    add_lib_path, clear_lib_paths, lib_search_paths,
    SymbolLibrary, find_kicad_symbols,
    TEMPLATE, NETLIST,
)
from sform_skidl.models.symbol import Symbol, GraphicItem


class TestPartFactoryAdvanced:
    """Tests for Part factory and symbol loading from api.py."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_part_with_value_and_footprint(self):
        """Part accepts value and footprint parameters."""
        r = Part('Device', 'R', value='10K', footprint='Resistor_SMD:R_0603')
        assert r.value == '10K'
        assert r.footprint == 'Resistor_SMD:R_0603'
    
    def test_part_custom_ref(self):
        """Part can have custom reference designator."""
        p = Part('Device', 'R')
        p.set_pin_count(2)
        # Ref is auto-generated, check it starts with R
        assert p.ref.startswith('R')
    
    def test_part_pins_property(self):
        """Part.pins returns list of unique pins."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        pins = p.pins
        assert len(pins) == 4
        assert len(set(id(pin) for pin in pins)) == 4  # All unique
    
    def test_part_pin_count_property(self):
        """Part.pin_count returns number of pins."""
        p = Part('Device', 'R')
        p.set_pin_count(3)
        
        assert p.pin_count == 3


class TestBusEdgeCases:
    """Tests for Bus edge cases and error paths."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_bus_anonymous_name(self):
        """Bus without name gets auto-generated name."""
        b = Bus(width=4)
        assert b.name.startswith('Bus')
    
    def test_bus_from_nets(self):
        """Bus can be created from existing nets."""
        n1 = Net('A')
        n2 = Net('B')
        b = Bus('AB', 0, n1, n2)
        
        assert len(b) == 2
        assert b[0] is n1
    
    def test_bus_from_other_bus(self):
        """Bus can include nets from another bus."""
        b1 = Bus('X', 2)
        b2 = Bus('Y', 0, b1)
        
        assert len(b2) == 2
    
    def test_bus_nets_property(self):
        """Bus.nets returns copy of nets list."""
        b = Bus('D', 4)
        nets = b.nets
        assert len(nets) == 4
        assert nets is not b._nets  # Should be copy
    
    def test_bus_type_error(self):
        """Bus indexing with wrong type raises TypeError."""
        b = Bus('X', 4)
        with pytest.raises(TypeError):
            _ = b[3.14]  # Float not allowed
    
    def test_bus_iadd_type_error(self):
        """Bus += wrong type raises TypeError or ValueError."""
        b = Bus('X', 4)
        with pytest.raises((TypeError, ValueError)):
            b += "string"  # String not allowed
    
    def test_bus_iadd_list_length_mismatch(self):
        """Bus += list with wrong length raises ValueError."""
        b = Bus('X', 4)
        with pytest.raises(ValueError, match="mismatch"):
            b += [Net(), Net()]  # Only 2 for 4-wide bus


class TestPinGroupEdgeCases:
    """Tests for PinGroup edge cases."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_pingroup_slicing(self):
        """PinGroup supports slicing."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        pg = p['1 2 3 4']
        sub = pg[1:3]
        
        assert isinstance(sub, PinGroup)
        assert len(sub) == 2
    
    def test_pingroup_type_error(self):
        """PinGroup += wrong type raises TypeError or error."""
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        pg = p['1 2']
        with pytest.raises((TypeError, ValueError)):
            pg += "string"
    
    def test_pingroup_list_wrong_type(self):
        """PinGroup += [non-Net] raises TypeError."""
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        pg = p['1 2']
        with pytest.raises(TypeError):
            pg += ["a", "b"]


class TestSymbolLibraryFunctions:
    """Tests for symbol library functions."""
    
    def test_find_kicad_symbols(self):
        """find_kicad_symbols returns Path or None."""
        result = find_kicad_symbols()
        assert result is None or isinstance(result, Path)
    
    def test_add_and_clear_lib_paths(self):
        """add_lib_path and clear_lib_paths work correctly."""
        clear_lib_paths()
        assert len(lib_search_paths) == 0
        
        add_lib_path('/tmp')
        assert Path('/tmp') in lib_search_paths
        
        clear_lib_paths()
        assert len(lib_search_paths) == 0
    
    def test_add_lib_path_no_duplicates(self):
        """add_lib_path doesn't add duplicates."""
        clear_lib_paths()
        add_lib_path('/tmp')
        add_lib_path('/tmp')
        
        count = sum(1 for p in lib_search_paths if p == Path('/tmp').resolve())
        assert count == 1
        
        clear_lib_paths()


class TestNetlistGeneration:
    """Tests for netlist generation."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_generate_netlist_creates_file(self):
        """generate_netlist creates valid file."""
        r = Part('Device', 'R')
        r.set_pin_count(2)
        n1, n2 = Net('A'), Net('B')
        n1 += r[1]
        n2 += r[2]
        
        with tempfile.NamedTemporaryFile(suffix='.net', delete=False) as f:
            path = f.name
        
        generate_netlist(path)
        
        content = Path(path).read_text()
        assert 'export' in content or 'netlist' in content.lower()
        Path(path).unlink()


class TestCircuitManagement:
    """Tests for circuit state management."""
    
    def test_get_circuit_returns_circuit(self):
        """get_circuit returns Circuit object."""
        reset_circuit()
        circuit = get_circuit()
        
        assert hasattr(circuit, 'parts')
        assert hasattr(circuit, 'nets')
    
    def test_reset_circuit_clears_state(self):
        """reset_circuit clears parts and nets."""
        Part('Device', 'R').set_pin_count(2)
        Net('TEST')
        
        reset_circuit()
        circuit = get_circuit()
        
        assert len(circuit.parts) == 0
