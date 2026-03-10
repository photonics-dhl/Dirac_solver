import sys, os

input_path = r"E:\PostGraduate\Dirac_solver\@Octopus_docs\output\wf-st00001.y=0,z=0"
output_png = r"E:\PostGraduate\Dirac_solver\@Octopus_docs\output\render_smoke_test.png"

# Convert Octopus 3-column ASCII to VisIt Ultra 2-column format
ultra_path = input_path + ".ultra"
xs, res_vals, ims = [], [], []
with open(input_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith('#') or not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            res_vals.append(float(parts[1]))
            if len(parts) >= 3:
                ims.append(float(parts[2]))

with open(ultra_path, 'w') as f:
    f.write("# Re(psi)\n")
    for x, y in zip(xs, res_vals):
        f.write(f"{x} {y}\n")
    if ims:
        f.write("# Im(psi)\n")
        for x, y in zip(xs, ims):
            f.write(f"{x} {y}\n")

OpenDatabase(ultra_path)
AddPlot("Curve", "Re(psi)")
DrawPlots()

a = GetAnnotationAttributes()
a.userInfoFlag = 0
a.databaseInfoFlag = 0
SetAnnotationAttributes(a)

s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.width, s.height = 900, 500
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
