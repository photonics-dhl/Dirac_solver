import os
import subprocess

work_dir = '/workspace/test_oct_7'
os.makedirs(work_dir, exist_ok=True)

inp_content = """CalculationMode = gs
Dimensions = 1
BoxShape = sphere
Spacing = 0.1
Radius = 5.0
ExtraStates = 2

%Output
  wfs
  potential
%
OutputFormat = axis_x

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
with open(os.path.join(work_dir, 'oct_out.log'), 'w') as stdout_f:
    with open(os.path.join(work_dir, 'oct_err.log'), 'w') as stderr_f:
        subprocess.run(['octopus'], cwd=work_dir, stdout=stdout_f, stderr=stderr_f)

print("Done running.")
subprocess.run(['find', work_dir])
