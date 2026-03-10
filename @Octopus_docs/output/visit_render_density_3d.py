import sys
# 3D electron density isosurface
nc_path    = r"E:\PostGraduate\Dirac_solver\@Octopus_docs\output\density.y=0,z=0"
output_png = r"E:\PostGraduate\Dirac_solver\@Octopus_docs\output\render_density_3d.png"

OpenDatabase(nc_path)
AddPlot("Contour", "density")
c = ContourAttributes()
c.contourNLevels = 1
c.contourValue = (0.01,)
c.colorType = c.ColorBySingleColor
c.singleColor = (0, 212, 255, 200)
SetPlotOptions(c)
DrawPlots()

v = GetView3D()
v.viewNormal = (-0.5, 0.5, 0.7)
v.viewUp = (0, 0, 1)
SetView3D(v)

s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.family = 0
s.width, s.height = 900, 700
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
