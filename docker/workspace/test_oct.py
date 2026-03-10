import os
import subprocess

work_dir = '/tmp/test_oct_4'
os.makedirs(work_dir, exist_ok=True)

inp_content = """CalculationMode = gs
Dimensions = 1
BoxShape = sphere
Spacing = 0.1
Radius = 5.0
ExtraStates = 2
Output = wfs + potential

%Species
  "Particle" | species_user_defined | potential_formula | "0.5*x^2" | valence | 1
%

%Coordinates
  "Particle" | 0
%
"""

with open(os.path.join(work_dir, 'inp'), 'w') as f:
    f.write(inp_content)

print("Running octopus...")
res = subprocess.run(['octopus'], cwd=work_dir, capture_output=True, text=True)

print("\n=== FILES GENERATED ===")
subprocess.run(['find', work_dir])
