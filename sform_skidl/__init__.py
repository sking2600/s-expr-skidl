"""
sform-skidl: SKiDL-compatible API for KiCad modern S-expression formats.

This package provides a Pythonic interface for designing electronic circuits
with direct output to KiCad 6+ file formats (.kicad_sym, .kicad_sch).

Example:
    from sform_skidl import *
    
    # Create nets
    vin, vout, gnd = Net('VIN'), Net('VOUT'), Net('GND')
    
    # Create parts
    r1 = Part("Device", "R", value="1K", footprint="Resistor_SMD:R_0805")
    r2 = Part("Device", "R", value="2K", footprint="Resistor_SMD:R_0805")
    
    # Connect circuit
    vin & r1 & vout & r2 & gnd
    
    # Generate outputs
    ERC()
    generate_schematic("voltage_divider.kicad_sch")
"""

__version__ = "0.1.0"

# Core API
from .api import (
    Part, Net, Pin, PinType, Symbol,
    TEMPLATE, NETLIST,
    ERC, generate_netlist, generate_schematic,
    set_default_tool, get_circuit, reset_circuit,
    KICAD, KICAD8, KICAD9,
)
from .models.bus import Bus, PinGroup

# Hierarchy
from .hierarchy import subcircuit, Interface

# S-expression tools
from .sexpr import parse, parse_file, serialize, serialize_to_file

# I/O modules
from .io import (
    read_symbol_library, write_symbol_library,
    find_kicad_symbols, SymbolLibrary, SchematicWriter,
    add_lib_path, lib_search_paths, clear_lib_paths,
    auto_discover_libs, search_parts, list_libraries,
)

# BOM generation
from .bom import generate_bom, register_exporter, BOMExporter, reduce_bom, list_exporters

# Compatibility features
from .compat import Group, NC, no_connect

# Parts database
from .parts_db import PartsDatabase, get_parts_db, load_parts_db, load_bundled_parts

# Network topology
from .network import Network, tee, star

# SPICE output
from .spice import generate_spice

__all__ = [
    # Version
    "__version__",
    # Core API
    "Part", "Net", "Pin", "PinType", "Symbol",
    "Bus", "PinGroup",
    "subcircuit", "Interface",
    "TEMPLATE", "NETLIST",
    "ERC", "generate_netlist", "generate_schematic",
    "set_default_tool", "get_circuit", "reset_circuit",
    "KICAD", "KICAD8", "KICAD9",
    # S-expression
    "parse", "parse_file", "serialize", "serialize_to_file",
    # I/O
    "read_symbol_library", "write_symbol_library",
    "find_kicad_symbols", "SymbolLibrary", "SchematicWriter",
    "add_lib_path", "lib_search_paths", "clear_lib_paths",
    "auto_discover_libs", "search_parts", "list_libraries",
    # BOM
    "generate_bom", "register_exporter", "BOMExporter", "reduce_bom", "list_exporters",
    # Compatibility
    "Group", "NC", "no_connect",
    # Parts database
    "PartsDatabase", "get_parts_db", "load_parts_db", "load_bundled_parts",
    # Network
    "Network", "tee", "star",
    # SPICE
    "generate_spice",
]
