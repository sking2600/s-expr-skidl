"""Unit tests for S-expression parser and writer."""

import pytest
from sform_skidl.sexpr import parse, serialize


class TestParser:
    """Tests for the S-expression parser."""
    
    def test_parse_empty(self):
        """Empty input returns empty list."""
        assert parse("") == []
    
    def test_parse_simple_list(self):
        """Parse simple list with atoms."""
        result = parse("(foo bar baz)")
        assert result == [["foo", "bar", "baz"]]
    
    def test_parse_nested_lists(self):
        """Parse nested lists."""
        result = parse("(outer (inner value))")
        assert result == [["outer", ["inner", "value"]]]
    
    def test_parse_quoted_strings(self):
        """Parse quoted strings."""
        result = parse('(property "Key" "Value with spaces")')
        assert result == [["property", "Key", "Value with spaces"]]
    
    def test_parse_escaped_strings(self):
        """Parse strings with escape sequences."""
        result = parse(r'(text "Line1\nLine2")')
        assert result == [["text", "Line1\nLine2"]]
    
    def test_parse_numbers(self):
        """Numbers are parsed as int/float values."""
        result = parse("(at 10.5 -20.3 90)")
        assert result == [["at", 10.5, -20.3, 90]]
    
    def test_parse_multiple_expressions(self):
        """Parse multiple top-level expressions."""
        result = parse("(a) (b)")
        assert result == [["a"], ["b"]]
    
    def test_parse_whitespace_handling(self):
        """Whitespace is normalized."""
        result = parse("(  foo   bar\n\tbaz  )")
        assert result == [["foo", "bar", "baz"]]
    
    def test_parse_kicad_symbol_header(self):
        """Parse realistic KiCad symbol library header."""
        text = '(kicad_symbol_lib (version 20231120) (generator "test"))'
        result = parse(text)
        assert result == [[
            "kicad_symbol_lib",
            ["version", 20231120],
            ["generator", "test"]
        ]]
    
    def test_parse_symbol_with_properties(self):
        """Parse symbol with properties."""
        text = '''
        (symbol "R"
            (property "Reference" "R" (at 0 0 0))
            (property "Value" "R" (at 0 -2.54 0))
        )
        '''
        result = parse(text)
        assert result[0][0] == "symbol"
        assert result[0][1] == "R"
        assert result[0][2][0] == "property"


class TestWriter:
    """Tests for the S-expression writer."""
    
    def test_serialize_simple_list(self):
        """Serialize simple list."""
        result = serialize(["foo", "bar", "baz"])
        assert result == "(foo bar baz)"
    
    def test_serialize_quoted_strings(self):
        """Strings with spaces are quoted."""
        result = serialize(["property", "Key", "Value with spaces"])
        assert result == '(property "Key" "Value with spaces")'
    
    def test_serialize_numbers(self):
        """Numbers are formatted correctly."""
        result = serialize(["at", 10.5, -20.3, 90])
        assert result == "(at 10.5 -20.3 90)"
    
    def test_serialize_float_precision(self):
        """Float precision is limited."""
        result = serialize(["at", 1.123456789])
        # Should not have excessive decimal places
        assert "1.123456" in result or "1.12345" in result
    
    def test_serialize_nested_inline(self):
        """Simple nested lists stay inline."""
        result = serialize(["at", 10, 20, 0], compact=True)
        assert result == "(at 10 20 0)"
    
    def test_serialize_booleans(self):
        """Booleans become yes/no."""
        result = serialize(["in_bom", True])
        assert result == "(in_bom yes)"
        result = serialize(["hide", False])
        assert result == "(hide no)"
    
    def test_serialize_escape_quotes(self):
        """Quotes in strings are escaped."""
        result = serialize(["text", 'Say "Hello"'])
        assert result == r'(text "Say \"Hello\"")'


class TestRoundTrip:
    """Test parse -> serialize -> parse round-trips."""
    
    def test_roundtrip_simple(self):
        """Simple expression round-trips."""
        original = "(foo bar (nested value))"
        parsed1 = parse(original)
        serialized = serialize(parsed1[0], compact=True)
        parsed2 = parse(serialized)
        assert parsed1 == parsed2
    
    def test_roundtrip_with_strings(self):
        """Quoted strings round-trip."""
        original = '(property "Key" "Value")'
        parsed1 = parse(original)
        serialized = serialize(parsed1[0], compact=True)
        parsed2 = parse(serialized)
        assert parsed1 == parsed2
    
    def test_roundtrip_kicad_header(self):
        """KiCad header round-trips."""
        original = '(kicad_symbol_lib (version 20231120) (generator "sform_skidl"))'
        parsed1 = parse(original)
        serialized = serialize(parsed1[0], compact=True)
        parsed2 = parse(serialized)
        assert parsed1 == parsed2
