"""
S-expression parser for KiCad file formats.

Parses KiCad's S-expression format (based on Specctra DSN) into nested Python
lists. Handles quoted strings, atoms, and nested expressions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

# Type alias for parsed S-expression data
SExpr = Union[str, list["SExpr"]]


class ParseError(Exception):
    """Raised when S-expression parsing fails."""

    def __init__(self, message: str, position: int, context: str = ""):
        self.position = position
        self.context = context
        super().__init__(f"{message} at position {position}" + 
                        (f": {context}" if context else ""))


class Tokenizer:
    """Tokenizer for S-expression text."""
    
    # Token patterns
    TOKEN_PATTERNS = [
        ("LPAREN", r"\("),
        ("RPAREN", r"\)"),
        ("STRING", r'"(?:[^"\\]|\\.)*"'),
        ("ATOM", r'[^\s()"]+'),
        ("WHITESPACE", r"\s+"),
    ]
    
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.pattern = re.compile(
            "|".join(f"(?P<{name}>{pattern})" 
                    for name, pattern in self.TOKEN_PATTERNS)
        )
    
    def tokens(self):
        """Yield tokens from the input text."""
        while self.pos < len(self.text):
            match = self.pattern.match(self.text, self.pos)
            if not match:
                raise ParseError(
                    "Unexpected character",
                    self.pos,
                    repr(self.text[self.pos:self.pos+10])
                )
            
            kind = match.lastgroup
            value = match.group()
            self.pos = match.end()
            
            if kind == "WHITESPACE":
                continue
            
            yield kind, value


def _unescape_string(s: str) -> str:
    """Unescape a quoted string, handling common escape sequences."""
    # Remove surrounding quotes
    s = s[1:-1]
    # Handle escape sequences - order matters for backslash
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            next_char = s[i + 1]
            if next_char == 'n':
                result.append('\n')
            elif next_char == 'r':
                result.append('\r')
            elif next_char == 't':
                result.append('\t')
            elif next_char == '"':
                result.append('"')
            elif next_char == '\\':
                result.append('\\')
            else:
                result.append(s[i:i+2])  # Keep unknown escapes as-is
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _convert_atom(value: str):
    """Convert an atom to appropriate type (int, float, or string)."""
    # Try integer first
    try:
        return int(value)
    except ValueError:
        pass
    
    # Try float
    try:
        return float(value)
    except ValueError:
        pass
    
    # Return as string
    return value


def parse(text: str) -> list[SExpr]:
    """
    Parse S-expression text into nested Python lists.
    
    Args:
        text: S-expression text to parse.
        
    Returns:
        List of parsed S-expressions (usually one root element).
        
    Raises:
        ParseError: If the text contains invalid S-expression syntax.
        
    Example:
        >>> parse('(symbol "R1" (value "10K"))')
        [['symbol', 'R1', ['value', '10K']]]
    """
    tokenizer = Tokenizer(text)
    tokens = list(tokenizer.tokens())
    
    if not tokens:
        return []
    
    results = []
    idx = 0
    
    def parse_expr(start: int) -> tuple[SExpr, int]:
        """Parse a single expression starting at token index."""
        kind, value = tokens[start]
        
        if kind == "LPAREN":
            # Parse list
            items = []
            idx = start + 1
            
            while idx < len(tokens):
                k, v = tokens[idx]
                if k == "RPAREN":
                    return items, idx + 1
                
                item, idx = parse_expr(idx)
                items.append(item)
            
            raise ParseError("Unclosed parenthesis", start)
        
        elif kind == "STRING":
            return _unescape_string(value), start + 1
        
        elif kind == "ATOM":
            # Try to convert numeric atoms to numbers
            return _convert_atom(value), start + 1
        
        elif kind == "RPAREN":
            raise ParseError("Unexpected closing parenthesis", start)
        
        else:
            raise ParseError(f"Unexpected token type: {kind}", start)
    
    while idx < len(tokens):
        expr, idx = parse_expr(idx)
        results.append(expr)
    
    return results


def parse_file(path: Path | str) -> list[SExpr]:
    """
    Parse S-expression file.
    
    Args:
        path: Path to the file to parse.
        
    Returns:
        List of parsed S-expressions.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        ParseError: If the file contains invalid syntax.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse(text)
