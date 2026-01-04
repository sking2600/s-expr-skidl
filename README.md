# sform-skidl

**SKiDL-compatible API for KiCad Modern S-Expression Formats**

Python library for programmatic circuit design with KiCad 9 schematic output.

## Features

- **SKiDL-compatible API** (`Part`, `Net`, `&`, `|`, `+=`)
- **Robust Schematic Generation**:
    - **Manhattan Routing**: A* algorithm routes wires around components.
    - **Auto-Verification**: Proactively fixes missed connections with stub wires.
    - **Physical Correctness**: Solves Y-axis inversion issues between symbols/schematics.
- **True Hierarchical Design**:
    - Generates multi-sheet output (Root + Sub-sheets).
    - Auto-manages Ports and Hierarchical Labels.
- **Smart Layout**:
    - Connectors (`J*`, `P*`) forced to sheet edges.
    - Dynamic text placement preventing label overlap.
- **Automated ERC Hygiene**:
    - Auto-injects `PWR_FLAG` symbols on undriven power rails.
- **BOM generation** for 9 vendors (JLCPCB, Mouser, Digikey, PCBWay, Arrow, Newark, Farnell, LCSC)
- **Parts database** with vendor-agnostic specs and stock type filtering
- **BOM reduction** to consolidate compatible parts

## Quick Start

```python
from sform_skidl import *

vin, vout, gnd = Net('VIN'), Net('VOUT'), Net('GND')
r1 = Part("Device", "R", value="1K")
r2 = Part("Device", "R", value="2K")

vin & r1 & vout & r2 & gnd

generate_schematic(
    "divider.kicad_sch", 
    title="Voltage Divider", 
    rev="1.0", 
    company="MyCorp"
)
generate_bom("bom.csv", format="jlcpcb")
```

## BOM & Vendor Support

### Simplified Columns
The parts database now exclusively supports:
- `lcsc`: LCSC Part Number (for JLCPCB Assembly)
- `mpn`: Manufacturer Part Number (for all other vendors)

### Quick Start: Bundled Parts Database
```python
# Load 84 common JLCPCB basic parts (resistors, caps, LEDs, ICs)
db = load_bundled_parts()

r1 = Part('Device', 'R', value='10K', footprint='0603')
db.apply_to_circuit()  # Auto-resolves 'lcsc' and 'mpn' fields

generate_bom('jlcpcb.csv', format='jlcpcb')
generate_bom('bom.csv', format='mpn')
```

### Auto-Population Script
Can be run as a standalone script to verify your database matches:
```python
# scripts/auto_populate.py
from sform_skidl import *

db = load_bundled_parts()
r1 = Part('Device', 'R', value='10K', footprint='0603')

# Database injects 'lcsc' and 'mpn' fields automatically
db.apply_to_circuit()

print(f"LCSC: {r1.fields.get('lcsc')}") # -> C25804
```

### Direct Vendor Override (Escape Hatch)
```python
r1 = Part('Device', 'R', value='10K')
r1.fields['lcsc'] = 'C12345'  # Always takes precedence
r1.fields['mpn'] = 'RC0603FR-0710KL'
```

### Supported Formats
```python
list_exporters()
# → ['generic', 'jlcpcb', 'lcsc', 'mpn']
```

| Format | Primary Use Case | Key Column | Includes Designators? |
| :--- | :--- | :--- | :--- |
| **`jlcpcb`** | **PCB Assembly** (JLCPCB) | `LCSC Part #` | ✅ Yes (Required for placement) |
| **`lcsc`** | **Purchasing Parts** (LCSC) | `LCSC Part #` | ❌ No (Just Quantity & Ref) |
| **`mpn`** | **Purchasing Parts** (Mouser, etc.)| `MPN` | ❌ No (Just Quantity & Ref) |
| **`generic`**| **Review / Documentation** | `MPN` + Details | ✅ Yes (Full Detail) |

#### Format Details
*   **`jlcpcb`**: Used for uploading to JLCPCB's assembly service. Includes designators (e.g. `R1`, `C3`) so placement machines know where to put the part `C25804`.
*   **`lcsc`**: Used for ordering parts from LCSC.com. Optimized for purchasing agents who just need the part number and total quantity.
*   **`mpn`**: Used for "BOM Import" tools on sites like **Mouser** or **DigiKey**. Provides the Manufacturer Part Number and quantity for quick ordering.
*   **`generic`**: Full documentation including Value, Footprint, and Manufacturer. Useful for manual verification (e.g. checking that `RC0603...` is actually a 10K resistor).

### Custom Parts Database
```python
db = PartsDatabase()
db.add('R', '10K', '0603', stock_type='basic', lcsc='C25804', mpn='RC0603FR...')
```

### Load from CSV
```python
db = load_parts_db('my_parts.csv')
# CSV: type,value,package,tolerance,stock_type,lcsc,mpn
```

### BOM Reduction
```python
reduce_bom()              # Preview opportunities
reduce_bom(apply=True)    # Apply consolidations
```

### Tolerance Matching
1% resistor in database satisfies 5% requirement (stricter is OK).


## Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `+=` | Connect | `vcc += r1[1]` |
| `&` | Series | `vin & r1 & vout` |
| `\|` | Parallel | `gnd \| r1[2] \| c1[2]` |

## Hierarchy

```python
@subcircuit
def voltage_divider(vin, vout, gnd):
    r1 = Part('Device', 'R', value='10K')
    r2 = Part('Device', 'R', value='20K')
    vin & r1 & vout & r2 & gnd

voltage_divider(vcc, mid, gnd)  # R1, R2
voltage_divider(vcc, mid2, gnd) # R3, R4 (unique refs)
```

## ERC (Electrical Rules Check)

```python
ERC()  # Run checks, print results
ERC(verbose=False)  # Silent mode, returns list
```

**Checks Performed:**
1. Unconnected pins (error for I/O, warning for passive)
2. Multiple outputs connected (short circuit)
3. Input pins without driver
4. Power-to-ground shorts (VCC connected to GND)
5. Floating nets (only passive pins)

**NC Marker:**
```python
NC += u1['NC']  # Suppress warning for unused pin
no_connect(u1['PA5'])  # Alternative syntax
```

## API Reference

| Function | Description |
|----------|-------------|
| `generate_schematic(path, title, rev, ...)` | Generate `.kicad_sch` with metadata |
| `generate_bom(path, format)` | Generate BOM (concise formats: `jlcpcb`, `mpn`, `generic`) |
| `reduce_bom(apply=False)` | Preview/apply BOM consolidation |
| `auto_discover_libs()` | Find KiCad libraries |
| `search_parts(pattern)` | Search all libraries |
| `@subcircuit` | Reusable circuit modules |

## License

MIT
