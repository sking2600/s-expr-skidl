"""
Symbol library reader/writer for .kicad_sym files.

Parses KiCad symbol library files from the installation directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from ..sexpr import parse, parse_file, serialize, serialize_to_file
from ..models.symbol import Symbol
from ..models.pin import Pin


# Custom library search paths (checked before KiCad installation)
lib_search_paths: list[Path] = []


def add_lib_path(path: str | Path):
    """
    Add a custom symbol library search path.
    
    Custom paths are searched before the KiCad installation directory.
    
    Args:
        path: Directory containing .kicad_sym files.
        
    Example:
        add_lib_path('.')  # Search current directory
        add_lib_path('/path/to/symbols')
    """
    path = Path(path).resolve()
    if path not in lib_search_paths:
        lib_search_paths.insert(0, path)  # Add to front for priority


def clear_lib_paths():
    """Clear all custom library search paths."""
    lib_search_paths.clear()


def find_kicad_symbols() -> Path | None:
    """
    Find KiCad symbol library directory.
    
    Checks in order:
    1. KICAD_SYMBOL_DIR environment variable
    2. Common installation paths
    
    Returns:
        Path to symbol directory, or None if not found.
    """
    # Check environment variable first
    env_path = os.environ.get("KICAD_SYMBOL_DIR")
    if env_path:
        path = Path(env_path)
        if path.is_dir():
            return path
    
    # Common installation paths
    common_paths = [
        # Linux
        Path("/usr/share/kicad/symbols"),
        Path("/usr/local/share/kicad/symbols"),
        Path.home() / ".local/share/kicad/symbols",
        # Flatpak
        Path.home() / ".var/app/org.kicad.KiCad/data/symbols",
        # macOS
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
        # Windows common paths (via WSL or native)
        Path("C:/Program Files/KiCad/share/kicad/symbols"),
        Path("C:/Program Files/KiCad/8.0/share/kicad/symbols"),
    ]
    
    for path in common_paths:
        if path.is_dir():
            return path
    
    return None


def auto_discover_libs() -> bool:
    """
    Automatically discover and add KiCad symbol library path.
    
    Searches for KiCad installation and adds the symbols directory
    to lib_search_paths. Call this at startup to enable automatic
    library resolution.
    
    Returns:
        True if a library path was found and added, False otherwise.
        
    Example:
        from sform_skidl import auto_discover_libs
        auto_discover_libs()  # Now Part('Device', 'R') works automatically
    """
    symbols_dir = find_kicad_symbols()
    if symbols_dir:
        if symbols_dir not in lib_search_paths:
            lib_search_paths.append(symbols_dir)
        return True
    return False


def search_parts(pattern: str, library: str | None = None, max_results: int = 20) -> list[tuple[str, str]]:
    """
    Search for parts matching a pattern across libraries.
    
    Performs case-insensitive substring matching on symbol names.
    
    Args:
        pattern: Search pattern (substring match).
        library: Optional library name to search in. If None, searches all.
        max_results: Maximum number of results to return.
        
    Returns:
        List of (library_name, symbol_name) tuples.
        
    Example:
        results = search_parts('555')  # Find all 555 timer variants
        results = search_parts('LM78', library='Regulator_Linear')
    """
    import re
    
    pattern_lower = pattern.lower()
    results = []
    
    # Get libraries to search
    if library:
        libs_to_search = [library]
    else:
        libs_to_search = list_libraries()
    
    for lib_name in libs_to_search:
        try:
            lib = get_library(lib_name)
            for symbol_name in lib:
                if pattern_lower in symbol_name.lower():
                    results.append((lib_name, symbol_name))
                    if len(results) >= max_results:
                        return results
        except (FileNotFoundError, ValueError):
            continue
    
    return results


def list_libraries(symbols_dir: Path | None = None) -> list[str]:
    """
    List available symbol libraries.
    
    Args:
        symbols_dir: Path to symbols directory, or auto-detect.
        
    Returns:
        List of library names (without .kicad_sym extension).
    """
    if symbols_dir is None:
        symbols_dir = find_kicad_symbols()
    
    if symbols_dir is None:
        return []
    
    return sorted([
        f.stem for f in symbols_dir.glob("*.kicad_sym")
    ])


class SymbolLibrary:
    """
    Represents a KiCad symbol library.
    
    Can load symbols on-demand from .kicad_sym files.
    """
    
    def __init__(self, name: str, path: Path | None = None):
        """
        Initialize symbol library.
        
        Args:
            name: Library name (e.g., "Device", "Connector").
            path: Path to .kicad_sym file, or auto-locate.
        """
        self.name = name
        self._path = path
        self._symbols: dict[str, Symbol] = {}
        self._loaded = False
    
    @property
    def path(self) -> Path | None:
        """Path to the library file."""
        if self._path:
            return self._path
        
        # Check custom search paths first
        for search_dir in lib_search_paths:
            lib_path = search_dir / f"{self.name}.kicad_sym"
            if lib_path.exists():
                self._path = lib_path
                return lib_path
        
        # Fall back to KiCad installation
        symbols_dir = find_kicad_symbols()
        if symbols_dir:
            lib_path = symbols_dir / f"{self.name}.kicad_sym"
            if lib_path.exists():
                self._path = lib_path
                return lib_path
        
        return None
    
    def _load(self):
        """Load symbols from file."""
        if self._loaded:
            return
        
        path = self.path
        if path is None:
            raise FileNotFoundError(f"Symbol library '{self.name}' not found")
        
        data = parse_file(path)
        if not data:
            return
        
        root = data[0]
        if root[0] != "kicad_symbol_lib":
            raise ValueError(f"Invalid symbol library file: {path}")
        
        for item in root:
            if isinstance(item, list) and item[0] == "symbol":
                symbol = Symbol.from_sexpr(item)
                self._symbols[symbol.name] = symbol
        
        self._loaded = True
    
    def get(self, name: str) -> Symbol | None:
        """Get a symbol by name, resolving inheritance if needed."""
        self._load()
        symbol = self._symbols.get(name)
        if symbol is None:
            return None
        
        # Resolve inheritance (extends)
        if symbol.extends:
            import copy
            # Recursively get base symbol
            parent = self.get(symbol.extends)
            if parent:
                # Create a merged copy
                # 1. Start with parent
                merged = copy.deepcopy(parent)
                # 2. Update metadata
                merged.name = symbol.name
                merged.extends = symbol.extends
                # 3. Update properties from derived
                merged.properties.update(symbol.properties)
                # 4. In KiCad 6+, if derived has pins/graphics, they usually override.
                # However, derived symbols often just have 'extends' and properties.
                if symbol.pins:
                    merged.pins = copy.deepcopy(symbol.pins)
                if symbol.graphics:
                    merged.graphics = copy.deepcopy(symbol.graphics)
                return merged
                
        return symbol
    
    def __getitem__(self, name: str) -> Symbol:
        """Get a symbol by name, raising KeyError if not found."""
        symbol = self.get(name)
        if symbol is None:
            raise KeyError(f"Symbol '{name}' not found in library '{self.name}'")
        return symbol
    
    def __contains__(self, name: str) -> bool:
        """Check if a symbol exists in the library."""
        self._load()
        return name in self._symbols
    
    def __iter__(self) -> Iterator[str]:
        """Iterate over symbol names."""
        self._load()
        return iter(self._symbols)
    
    def symbols(self) -> list[Symbol]:
        """Get all symbols in the library."""
        self._load()
        return list(self._symbols.values())


# Cache of loaded libraries
_library_cache: dict[str, SymbolLibrary] = {}


def get_library(name: str) -> SymbolLibrary:
    """
    Get a symbol library by name (cached).
    
    Args:
        name: Library name (e.g., "Device").
        
    Returns:
        SymbolLibrary instance.
    """
    if name not in _library_cache:
        _library_cache[name] = SymbolLibrary(name)
    return _library_cache[name]


def read_symbol_library(path: Path | str) -> dict[str, Symbol]:
    """
    Read all symbols from a .kicad_sym file.
    
    Args:
        path: Path to the symbol library file.
        
    Returns:
        Dict mapping symbol names to Symbol objects.
    """
    lib = SymbolLibrary("", Path(path))
    lib._path = Path(path)
    lib._load()
    return lib._symbols.copy()


def write_symbol_library(
    symbols: dict[str, Symbol],
    path: Path | str,
    version: int = 20231120,
    generator: str = "sform_skidl",
):
    """
    Write symbols to a .kicad_sym file.
    
    Args:
        symbols: Dict mapping names to Symbol objects.
        path: Output file path.
        version: KiCad file format version.
        generator: Generator name for metadata.
    """
    root = [
        "kicad_symbol_lib",
        ["version", version],
        ["generator", generator],
    ]
    
    for symbol in symbols.values():
        root.append(symbol.to_sexpr())
    
    serialize_to_file(root, Path(path))
