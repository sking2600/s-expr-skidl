from sform_skidl import *

# 1. Load the bundled parts database (resistors, caps, etc.)
# This loads data from csvs like sform_skidl/data/resistors_basic.csv
db = load_bundled_parts()

# 2. Define generic parts in your circuit
# You only need to specify parameters that match columns in the CSV (value, package, etc.)
r1 = Part('Device', 'R', value='10K', footprint='0603')
c1 = Part('Device', 'C', value='100nF', footprint='0402')

print("\n--- Before Auto-Population ---")
print(f"R1 fields: {r1.fields}")
print(f"C1 fields: {c1.fields}")

# 3. Apply database to the circuit
# This searches the DB for matches and injects 'lcsc' and 'mpn' fields
db.apply_to_circuit()

print("\n--- After Auto-Population ---")
print(f"R1 lcsc: {r1.fields.get('lcsc')}")
print(f"R1 mpn:  {r1.fields.get('mpn')}")
print(f"C1 lcsc: {c1.fields.get('lcsc')}")
print(f"C1 mpn:  {c1.fields.get('mpn')}")

# 4. Generate BOMs
# generate_bom('bom_jlc.csv', format='jlcpcb')
# generate_bom('bom_mpn.csv', format='mpn')
