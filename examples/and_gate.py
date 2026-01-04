#!/usr/bin/env python3
"""
Discrete AND Gate Example

Demonstrates more complex circuit design with transistors and resistors,
matching the original SKiDL example from the documentation.
"""

from sform_skidl import *

# Reset any previous circuit state
reset_circuit()

# Create part templates
def make_transistor():
    """Create a PNP transistor part."""
    from sform_skidl.models.pin import Pin, PinType
    from sform_skidl.models.symbol import Symbol
    
    symbol = Symbol(
        name="Q_PNP_CBE",
        properties={"Reference": "Q", "Value": "Q_PNP_CBE"},
        pins=[
            Pin("1", "C", PinType.PASSIVE),  # Collector
            Pin("2", "B", PinType.INPUT),    # Base
            Pin("3", "E", PinType.PASSIVE),  # Emitter
        ],
    )
    return Part("Device", "Q_PNP_CBE", dest=TEMPLATE, _symbol=symbol)

def make_resistor(value="10K"):
    """Create a resistor part template."""
    return Part("Device", "R", value=value, dest=TEMPLATE)

# Create templates
q_template = make_transistor()
r_template = make_resistor()

# Create nets
gnd = Net("GND")
vcc = Net("VCC")
a = Net("A")
b = Net("B")
a_and_b = Net("A_AND_B")

# Instantiate parts
q1 = q_template()
q2 = q_template()
r1, r2, r3, r4, r5 = [Part("Device", "R", value="10K") for _ in range(5)]

# Make connections for the AND gate
# Input A through R1 to Q1 base, Q1 collector through R4 to Q2 base
a += r1["1"]
r1["2"] += q1["B"]
q1["C"] += r4["1"]
r4["2"] += q2["B"]
q2["C"] += a_and_b
a_and_b += r5["1"]
r5["2"] += gnd

# Input B through R2 to Q1 base
b += r2["1"]
r2["2"] += q1["B"]

# Q1 collector to ground through R3
q1["C"] += r3["1"]
r3["2"] += gnd

# VCC to emitters
vcc += q1["E"]
vcc += q2["E"]

# Run ERC
print("Running ERC...")
errors = ERC()

# Generate outputs
print("\nGenerating schematic...")
generate_schematic("and_gate.kicad_sch", title="Discrete AND Gate")

print("\nGenerating netlist...")
generate_netlist("and_gate.net")

print("\nCircuit summary:")
circuit = get_circuit()
print(f"  Parts: {len(circuit.parts)}")
print(f"  Nets: {len(circuit.nets)}")
for net in circuit.nets:
    if net.pins:
        print(f"    Net {net.name}: {len(net.pins)} connections")
