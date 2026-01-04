"""
Additional tests to improve coverage of core modules.
"""

import pytest
from sform_skidl import (
    Part, Net, Pin, PinType, Bus, PinGroup,
    reset_circuit, get_circuit, ERC,
    generate_schematic, generate_netlist,
    auto_discover_libs, list_libraries, search_parts,
    TEMPLATE, NETLIST,
)
from sform_skidl.models.symbol import Symbol


class TestNetOperators:
    """Tests for Net connection operators."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_net_iadd_single_pin(self):
        """net += pin connects pin to net."""
        n = Net('TEST')
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        n += p[1]
        assert p[1].net is n
        assert len(n.pins) == 1
    
    def test_net_iadd_multiple_pins(self):
        """net += [pins] connects all pins."""
        n = Net('TEST')
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        n += [p[1], p[2], p[3]]
        assert len(n.pins) == 3
        for i in [1, 2, 3]:
            assert p[str(i)].net is n
    
    def test_net_iadd_part(self):
        """net += part connects all pins of part."""
        n = Net('TEST')
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        n += p  # Connect whole part
        assert len(n.pins) == 2
    
    def test_net_series_connection(self):
        """net & part & net creates series connection."""
        vin = Net('VIN')
        vout = Net('VOUT')
        r = Part('Device', 'R')
        r.set_pin_count(2)
        
        vin & r & vout
        
        # Pin 1 should be connected to vin, pin 2 to vout
        assert r[1].net is vin
        assert r[2].net is vout
    
    def test_net_series_chain(self):
        """Chained series: vin & r1 & mid & r2 & gnd."""
        vin = Net('VIN')
        mid = Net('MID')
        gnd = Net('GND')
        r1 = Part('Device', 'R')
        r1.set_pin_count(2)
        r2 = Part('Device', 'R')
        r2.set_pin_count(2)
        
        vin & r1 & mid & r2 & gnd
        
        assert r1[1].net is vin
        assert r1[2].net is mid
        assert r2[1].net is mid
        assert r2[2].net is gnd
    
    def test_net_is_power(self):
        """Net.is_power detects power pins."""
        n = Net('VCC')
        sym = Symbol(name='PWR', pins=[
            Pin('1', 'VCC', PinType.POWER_IN),
        ])
        p = Part('power', 'VCC', _symbol=sym)
        n += p[1]
        
        assert n.is_power is True
    
    def test_net_counter(self):
        """Auto-named nets use counter."""
        reset_circuit()
        n1 = Net()
        n2 = Net()
        
        assert n1.name.startswith('Net')
        assert n2.name.startswith('Net')
        assert n1.name != n2.name
    
    def test_net_parallel_operator(self):
        """Net | pin connects pin to net."""
        n = Net('GND')
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        n | p[1] | p[2]
        
        assert len(n.pins) == 2
        assert p[1].net is n
        assert p[2].net is n
    
    def test_net_parallel_with_part(self):
        """Net | part connects all pins."""
        n = Net('VCC')
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        n | p
        
        assert len(n.pins) == 2
    
    def test_net_parallel_with_list(self):
        """Net | [pins] connects all pins in list."""
        n = Net('SIG')
        p1 = Part('Device', 'R')
        p1.set_pin_count(1)
        p2 = Part('Device', 'R')
        p2.set_pin_count(1)
        
        n | [p1[1], p2[1]]
        
        assert len(n.pins) == 2
    
    def test_chained_part_to_pin(self):
        """_ChainedPart & Pin creates intermediate net."""
        vin = Net('VIN')
        r = Part('Device', 'R')
        r.set_pin_count(2)
        p_end = Part('Device', 'R')
        p_end.set_pin_count(1)
        
        vin & r & p_end[1]
        
        assert r[1].net is vin
        assert r[2].net is p_end[1].net


class TestPartFactory:
    """Tests for Part instantiation and template mode."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_part_template_instantiation(self):
        """Template part can create multiple instances."""
        r_template = Part('Device', 'R', dest=TEMPLATE)
        r1 = r_template()
        r2 = r_template()
        
        assert r1.ref != r2.ref
        assert r1.ref.startswith('R')
    
    def test_part_multiplication(self):
        """part * n creates n instances."""
        r = Part('Device', 'R', dest=TEMPLATE)
        resistors = r * 3
        
        assert len(resistors) == 3
        refs = {r.ref for r in resistors}
        assert len(refs) == 3  # All unique
    
    def test_part_set_pin_count(self):
        """set_pin_count creates numbered pins."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        assert len(p.pins) == 4
        assert p[1] is not None
        assert p[4] is not None
    
    def test_part_add_pin(self):
        """add_pin adds new pin to part."""
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        new_pin = Pin('3', 'EXTRA', PinType.PASSIVE)
        p.add_pin(new_pin)
        
        assert p[3] is new_pin
        assert p['EXTRA'] is new_pin


class TestERC:
    """Tests for Electrical Rules Check."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_erc_returns_list(self):
        """ERC returns list of errors/warnings."""
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        result = ERC()
        assert isinstance(result, list)
    
    def test_erc_connected_circuit(self):
        """ERC can run on connected circuit with fewer warnings."""
        n1 = Net('N1')
        n2 = Net('N2')
        p = Part('Device', 'R')
        p.set_pin_count(2)
        
        n1 += p[1]
        n2 += p[2]
        
        result = ERC()
        assert isinstance(result, list)


class TestBusAdvanced:
    """Additional Bus tests for coverage."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_bus_name_access(self):
        """Bus[name] finds net by name."""
        b = Bus('DATA', 4)
        net = b['DATA2']
        assert net.name == 'DATA2'
    
    def test_bus_name_not_found_raises(self):
        """Bus[invalid_name] raises KeyError."""
        b = Bus('DATA', 4)
        with pytest.raises(KeyError):
            _ = b['NOTFOUND']
    
    def test_bus_single_net_error(self):
        """Bus += Net raises error (would short)."""
        b = Bus('DATA', 4)
        n = Net('SINGLE')
        
        with pytest.raises(ValueError, match="short"):
            b += n
    
    def test_bus_single_pin_error(self):
        """Bus += Pin raises error (would short)."""
        b = Bus('DATA', 4)
        p = Part('Device', 'R')
        p.set_pin_count(1)
        
        with pytest.raises(ValueError, match="short"):
            b += p[1]


class TestPinGroupAdvanced:
    """Additional PinGroup tests."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_pingroup_connect_to_single_net(self):
        """PinGroup += Net connects all pins to same net."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        pg = p['1 2']
        n = Net('COMMON')
        pg += n
        
        assert p[1].net is n
        assert p[2].net is n
    
    def test_pingroup_length_mismatch_raises(self):
        """PinGroup += [nets] with wrong length raises."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        pg = p['1 2 3']
        
        with pytest.raises(ValueError, match="mismatch"):
            pg += [Net(), Net()]  # Only 2 nets for 3 pins


class TestLibraryFunctions:
    """Tests for library discovery and search."""
    
    def test_auto_discover_libs(self):
        """auto_discover_libs finds KiCad libraries."""
        result = auto_discover_libs()
        # On a system with KiCad installed, this should return True
        assert isinstance(result, bool)
    
    def test_list_libraries_returns_list(self):
        """list_libraries returns list of strings."""
        auto_discover_libs()
        libs = list_libraries()
        assert isinstance(libs, list)
    
    def test_search_parts_returns_tuples(self):
        """search_parts returns (lib, symbol) tuples."""
        auto_discover_libs()
        results = search_parts('R', max_results=5)
        assert isinstance(results, list)
        if results:
            assert isinstance(results[0], tuple)
            assert len(results[0]) == 2


class TestSchematicGeneration:
    """Tests for schematic file generation."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_generate_schematic_creates_file(self, tmp_path):
        """generate_schematic creates valid file."""
        r = Part('Device', 'R')
        r.set_pin_count(2)
        n1, n2 = Net('A'), Net('B')
        n1 += r[1]
        n2 += r[2]
        
        output = tmp_path / "test.kicad_sch"
        generate_schematic(str(output))
        
        assert output.exists()
        content = output.read_text()
        assert 'kicad_sch' in content
        assert 'symbol' in content
