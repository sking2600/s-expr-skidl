"""
S-expression writer for KiCad file formats.

Serializes Python nested lists back into formatted S-expression text
compatible with KiCad tools.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

# Type alias for S-expression data
SExpr = Union[str, int, float, list["SExpr"]]

# Tokens that start a new indented block
BLOCK_TOKENS = {
    "kicad_symbol_lib", "kicad_sch", "kicad_pcb",
    "symbol", "lib_symbols", "property", "pin",
    "rectangle", "circle", "arc", "polyline", "text",
    "wire", "junction", "label", "global_label",
    "effects", "font", "stroke", "fill",
}

# Simple tokens that stay on same line
INLINE_TOKENS = {
    "at", "xy", "pts", "start", "end", "center", "mid",
    "size", "width", "height", "length", "offset",
    "thickness", "color", "diameter", "radius",
    "version", "generator", "uuid", "id",
    "type", "layer", "layers", "unit",
    "in_bom", "on_board", "justify", "hide",
}


def _needs_quoting(s: str) -> bool:
    """Check if a string needs to be quoted."""
    if not s:
        return True
    # KiCad tokens are lowercase with underscores only
    # Quote anything else (including property values with uppercase)
    if re.search(r'[\s()"\\]', s):
        return True
    # Quote strings that aren't valid tokens (contain uppercase or other chars)
    if not re.match(r'^[a-z_][a-z0-9_]*$', s):
        return True
    return False


def _escape_string(s: str) -> str:
    """Escape a string for S-expression output."""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    return f'"{s}"'


def _format_value(value: SExpr) -> str:
    """Format a single value (atom, string, or number)."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    elif isinstance(value, (int, float)):
        # Format floats without unnecessary precision
        if isinstance(value, float):
            formatted = f"{value:.6f}".rstrip("0").rstrip(".")
            return formatted
        return str(value)
    elif isinstance(value, str):
        if _needs_quoting(value):
            return _escape_string(value)
        return value
    else:
        raise TypeError(f"Unsupported value type: {type(value)}")


def _is_simple_list(lst: list) -> bool:
    """Check if a list should be rendered inline (no nested lists)."""
    if not lst:
        return True
    
    # Check first element for token hint
    if lst and isinstance(lst[0], str):
        token = lst[0]
        if token in INLINE_TOKENS:
            return True
        if token in BLOCK_TOKENS:
            return False
    
    # Lists without nested lists can be inline
    return not any(isinstance(item, list) for item in lst)


def serialize(data: SExpr, indent: int = 2, compact: bool = False) -> str:
    """
    Serialize nested Python lists to S-expression text.
    
    Args:
        data: Nested list structure to serialize.
        indent: Number of spaces for indentation.
        compact: If True, minimize whitespace.
        
    Returns:
        Formatted S-expression string.
        
    Example:
        >>> serialize(['symbol', 'R1', ['value', '10K']])
        '(symbol "R1"\\n  (value "10K")\\n)'
    """
    lines = []
    
    def write_list(lst: list, depth: int = 0):
        """Recursively write a list expression."""
        if not lst:
            lines.append("()")
            return
        
        prefix = "" if compact else " " * (depth * indent)
        
        # Check if this list should be inline
        if _is_simple_list(lst) or compact:
            parts = [_format_value(item) if not isinstance(item, list) 
                    else serialize(item, indent, compact=True) 
                    for item in lst]
            lines.append(f"{prefix}({' '.join(parts)})")
            return
        
        # Multi-line list
        token = lst[0] if lst and isinstance(lst[0], str) else ""
        
        # Opening with first element
        first_parts = []
        rest_start = 0
        
        for i, item in enumerate(lst):
            if isinstance(item, list):
                rest_start = i
                break
            first_parts.append(_format_value(item))
            rest_start = i + 1
        
        opening = f"{prefix}({' '.join(first_parts)}"
        
        if rest_start >= len(lst):
            # No nested lists
            lines.append(f"{opening})")
            return
        
        lines.append(opening)
        
        # Write nested elements
        for item in lst[rest_start:]:
            if isinstance(item, list):
                write_list(item, depth + 1)
            else:
                inner_prefix = " " * ((depth + 1) * indent)
                lines.append(f"{inner_prefix}{_format_value(item)}")
        
        # Closing
        lines.append(f"{prefix})")
    
    if isinstance(data, list):
        write_list(data)
    else:
        return _format_value(data)
    
    return "\n".join(lines)


def serialize_to_file(data: SExpr, path: Path | str, indent: int = 2):
    """
    Serialize S-expression data to a file.
    
    Args:
        data: Nested list structure to serialize.
        path: Output file path.
        indent: Number of spaces for indentation.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = serialize(data, indent)
    path.write_text(text + "\n", encoding="utf-8")
