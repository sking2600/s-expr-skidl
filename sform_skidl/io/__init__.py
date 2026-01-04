"""I/O modules for KiCad file formats."""

from .symbol_lib import (
    read_symbol_library,
    write_symbol_library,
    find_kicad_symbols,
    SymbolLibrary,
    add_lib_path,
    lib_search_paths,
    clear_lib_paths,
    auto_discover_libs,
    search_parts,
    list_libraries,
)
from .schematic_io import SchematicWriter

__all__ = [
    "read_symbol_library",
    "write_symbol_library",
    "find_kicad_symbols",
    "SymbolLibrary",
    "SchematicWriter",
    "add_lib_path",
    "lib_search_paths",
    "clear_lib_paths",
    "auto_discover_libs",
    "search_parts",
    "list_libraries",
]
