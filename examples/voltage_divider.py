#!/usr/bin/env python3
"""
Voltage Divider Example

Demonstrates basic SKiDL-style circuit design using sform-skidl.
Creates a simple voltage divider with two resistors.
"""

from sform_skidl import *

# Reset any previous circuit state
reset_circuit()

# Create nets
vin = Net('VIN')
vout = Net('VOUT')
gnd = Net('GND')

# Create resistors using the series connection operator
r1 = Part("Device", "R", value="1K", footprint="Resistor_SMD:R_0805_2012Metric")
r2 = Part("Device", "R", value="2K", footprint="Resistor_SMD:R_0805_2012Metric")

# Connect the voltage divider: VIN -> R1 -> VOUT -> R2 -> GND
vin & r1 & vout & r2 & gnd

# Run Electrical Rules Check
print("Running ERC...")
errors = ERC()

# Generate outputs
print("\nGenerating schematic...")
generate_schematic("voltage_divider.kicad_sch", title="Voltage Divider")

print("\nGenerating netlist...")
generate_netlist("voltage_divider.net")

print("\nCircuit summary:")
print(f"  Parts: {len(get_circuit().parts)}")
print(f"  Nets: {len(get_circuit().nets)}")
for part in get_circuit().parts:
    print(f"    {part.ref}: {part.name} = {part.value}")
