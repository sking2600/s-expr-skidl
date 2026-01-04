"""
Tests for Bus, PinGroup, subcircuit, and Interface features.
"""

import pytest
from sform_skidl import (
    Bus, PinGroup, Part, Net, Pin, PinType,
    subcircuit, Interface,
    reset_circuit, get_circuit,
)


class TestBus:
    """Tests for Bus class."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_bus_creation_with_width(self):
        """Bus creates nets named NAME0, NAME1, etc."""
        b = Bus('DATA', 8)
        assert len(b) == 8
        assert b.width == 8
        assert b[0].name == 'DATA0'
        assert b[7].name == 'DATA7'
    
    def test_bus_indexing(self):
        """Bus supports positive and negative indexing."""
        b = Bus('ADDR', 4)
        assert b[0].name == 'ADDR0'
        assert b[-1].name == 'ADDR3'
    
    def test_bus_slicing(self):
        """Bus slicing returns sub-bus."""
        b = Bus('D', 8)
        sub = b[2:5]
        assert isinstance(sub, Bus)
        assert len(sub) == 3
        assert sub[0].name == 'D2'
    
    def test_bus_iteration(self):
        """Bus is iterable over nets."""
        b = Bus('X', 3)
        names = [net.name for net in b]
        assert names == ['X0', 'X1', 'X2']
    
    def test_bus_element_wise_connection(self):
        """Bus += Bus connects nets element-wise."""
        b1 = Bus('A', 4)
        b2 = Bus('B', 4)
        
        # Create pins and connect to b2
        p = Part('Device', 'R')
        p.set_pin_count(4)
        for i, pin in enumerate(p.pins):
            pin.connect(b2[i])
        
        # Connect buses - should move pins from b2 to b1
        b1 += b2
        
        # Pins should now be on b1 nets (moved from b2)
        assert len(b1[0].pins) == 1
        assert len(b2[0].pins) == 0  # Pin was moved
    
    def test_bus_width_mismatch_raises(self):
        """Bus += with mismatched widths raises ValueError."""
        b1 = Bus('A', 4)
        b2 = Bus('B', 3)
        
        with pytest.raises(ValueError, match="width mismatch"):
            b1 += b2


class TestPinGroup:
    """Tests for PinGroup class."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_pingroup_from_multi_pin_access(self):
        """Part[...] returns PinGroup for multiple pins."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        pg = p['1 2']
        assert isinstance(pg, PinGroup)
        assert len(pg) == 2
    
    def test_pingroup_bus_connection(self):
        """PinGroup += Bus connects element-wise."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        bus = Bus('D', 2)
        pg = p['1 2']
        pg += bus
        
        assert p['1'].net.name == 'D0'
        assert p['2'].net.name == 'D1'


class TestRegexPinLookup:
    """Tests for regex pin pattern matching."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_regex_pin_lookup_by_number(self):
        """Part['[12]'] returns pins matching number pattern."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        # Access pins 1 and 2 by regex on number
        pins = p['[12]']
        assert isinstance(pins, PinGroup)
        assert len(pins) == 2
    
    def test_space_separated_pin_access(self):
        """Part['1 2 3'] returns multiple pins as PinGroup."""
        p = Part('Device', 'R')
        p.set_pin_count(4)
        
        all_pins = p['1 2 3']
        assert isinstance(all_pins, PinGroup)
        assert len(all_pins) == 3


class TestSubcircuit:
    """Tests for @subcircuit decorator."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_subcircuit_unique_refs(self):
        """Multiple subcircuit calls create unique refs."""
        @subcircuit
        def divider(vin, vout, gnd):
            r1 = Part('Device', 'R', value='1K')
            r2 = Part('Device', 'R', value='1K')
            vin & r1 & vout & r2 & gnd
            return r1, r2
        
        # Create nets
        vcc, m1, m2, gnd_net = Net('VCC'), Net('M1'), Net('M2'), Net('GND')
        
        # Instantiate twice
        a1, a2 = divider(vcc, m1, gnd_net)
        b1, b2 = divider(vcc, m2, gnd_net)
        
        # Refs should be unique (4 distinct refs)
        refs = {a1.ref, a2.ref, b1.ref, b2.ref}
        assert len(refs) == 4  # All unique
    
    def test_subcircuit_preserves_function_name(self):
        """Subcircuit wrapper preserves function metadata."""
        @subcircuit
        def my_circuit():
            pass
        
        assert my_circuit.__name__ == 'my_circuit'
        assert my_circuit._is_subcircuit is True


class TestInterface:
    """Tests for Interface class."""
    
    def setup_method(self):
        reset_circuit()
    
    def test_interface_creation(self):
        """Interface stores named nets."""
        i2c = Interface(sda=Net('SDA'), scl=Net('SCL'))
        
        assert i2c.sda.name == 'SDA'
        assert i2c.scl.name == 'SCL'
    
    def test_interface_iteration(self):
        """Interface is iterable over names."""
        intf = Interface(a=Net('A'), b=Net('B'))
        names = list(intf.keys())
        assert set(names) == {'a', 'b'}
    
    def test_interface_items(self):
        """Interface.items() returns (name, net) pairs."""
        intf = Interface(x=Net('X'))
        items = list(intf.items())
        assert len(items) == 1
        assert items[0][0] == 'x'
        assert items[0][1].name == 'X'
    
    def test_interface_dict_access(self):
        """Interface supports dict-style access."""
        intf = Interface(sig=Net('SIG'))
        assert intf['sig'].name == 'SIG'
    
    def test_interface_repr(self):
        """Interface has readable repr."""
        intf = Interface(clk=Net('CLK'))
        assert 'clk=CLK' in repr(intf)
