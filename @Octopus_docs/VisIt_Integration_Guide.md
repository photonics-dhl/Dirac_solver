# VisIt Integration Guide

Reference for invoking VisIt in headless mode from the Node.js LangGraph orchestrator on Windows,  
and for writing the Python VisIt control scripts that it executes.

---

## 1. Architecture Overview

```
Node.js (port 3001)
  └── renderVisualizationNode
        └── child_process.spawn("powershell", ["-c", "visit -nowin -cli -s <script.py>"])
              → VisIt (Windows native, headless)
                    └── Python VisIt API script
                          ├── OpenDatabase("E:\...\output\density.nc")
                          ├── DefineExpressions / AddPlot / DrawPlots
                          ├── SaveWindow("E:\...\output\render.png")
                          └── sys.exit(0)
```

**Critical rules from copilot-instructions.md:**
- VisIt runs on the **Windows host** — all paths in VisIt scripts MUST be Windows absolute paths.
- Docker/Python MCP uses Linux paths — never mix them in a VisIt script.
- Always terminate VisIt scripts with `SaveWindow()` + `sys.exit(0)`.

---

## 2. VisIt Invocation from Node.js (TypeScript)

Add this helper to `src/langgraph_agent.ts` or a new `src/visit_renderer.ts`:

```typescript
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

interface VisItRenderOptions {
  scriptPath: string;       // Absolute Windows path to the .py script
  outputPngPath: string;    // Absolute Windows path for the output PNG
  timeoutMs?: number;       // Default: 60000 (60s)
}

interface VisItRenderResult {
  success: boolean;
  pngPath?: string;
  stderr?: string;
  durationMs?: number;
}

export async function renderWithVisIt(
  opts: VisItRenderOptions
): Promise<VisItRenderResult> {
  const { scriptPath, outputPngPath, timeoutMs = 60_000 } = opts;
  const start = Date.now();

  return new Promise((resolve) => {
    // visit.exe must be on PATH, or use full path e.g. "C:\VisIt\visit.exe"
    const proc = spawn("visit", ["-nowin", "-cli", "-s", scriptPath], {
      shell: false,
      windowsHide: true,
    });

    let stderr = "";
    proc.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });

    const timer = setTimeout(() => {
      proc.kill();
      resolve({ success: false, stderr: "VisIt timeout after " + timeoutMs + "ms" });
    }, timeoutMs);

    proc.on("close", (code) => {
      clearTimeout(timer);
      const existed = fs.existsSync(outputPngPath);
      resolve({
        success: code === 0 && existed,
        pngPath: existed ? outputPngPath : undefined,
        stderr: stderr || undefined,
        durationMs: Date.now() - start,
      });
    });
  });
}
```

---

## 3. VisIt Script Templates

### 3.1 Template A — 1D Wavefunction Plot (from ASCII `.y=0,z=0` file)

```python
"""
VisIt script: render_wavefunction_1d.py
Input: whitespace-delimited ASCII file (x, wf_real, wf_imag columns)
Output: PNG line plot of |ψ|² and Re(ψ)
"""
import sys, os

# --- PARAMETERS (injected by Node.js via Jinja2 template) ---
input_ascii = r"{{ ascii_path }}"     # e.g. E:\...\static\wf-st00001.y=0,z=0
output_png  = r"{{ output_png }}"     # e.g. E:\...\output\wf_state1.png
state_label = "{{ state_label }}"     # e.g. "State 1 (E = -0.503 H)"

# --- Open database ---
OpenDatabase(input_ascii)

# --- Plot real part ---
AddPlot("Curve", "wf_real")
DrawPlots()

# --- Annotation ---
a = GetAnnotationAttributes()
a.userInfoFlag = 0
a.databaseInfoFlag = 0
a.legendInfoFlag = 1
SetAnnotationAttributes(a)

# --- Save ---
s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.width, s.height = 800, 500
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
```

### 3.2 Template B — 2D Electron Density Pseudocolor (from `density.nc`)

```python
"""
VisIt script: render_density_2d.py
Input: NetCDF density file, renders xy-plane at z=0
Output: Pseudocolor PNG of ρ(x,y,0)
"""
import sys

# --- PARAMETERS ---
nc_path    = r"{{ nc_path }}"
output_png = r"{{ output_png }}"
colormap   = "{{ colormap | default('hot') }}"

OpenDatabase(nc_path)

AddPlot("Pseudocolor", "density")
p = PseudocolorAttributes()
p.colorTableName = colormap
p.minFlag, p.maxFlag = 1, 1
p.min, p.max = 0.0, {{ density_max | default(1.0) }}
SetPlotOptions(p)

# Slice at z=0
AddOperator("Slice")
sl = SliceAttributes()
sl.axisType = sl.ZAxis
sl.originType = sl.Intercept
sl.originIntercept = 0.0
sl.project2d = 1
SetOperatorOptions(sl)

DrawPlots()

s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.width, s.height = 800, 800
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
```

### 3.3 Template C — 3D Isosurface of Electron Density

```python
"""
VisIt script: render_density_3d_isosurface.py
Input: NetCDF density file
Output: 3D isosurface PNG
"""
import sys

nc_path    = r"{{ nc_path }}"
output_png = r"{{ output_png }}"
iso_value  = {{ iso_value | default(0.01) }}

OpenDatabase(nc_path)

AddPlot("Contour", "density")
c = ContourAttributes()
c.contourNLevels = 1
c.contourValue = (iso_value,)
c.colorType = c.ColorBySingleColor
c.singleColor = (0, 212, 255, 200)   # accent cyan, 78% opacity
SetPlotOptions(c)

DrawPlots()

# Set a good 3D view angle
v = GetView3D()
v.viewNormal = (-0.5, 0.5, 0.7)
v.viewUp = (0, 0, 1)
SetView3D(v)

s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.width, s.height = 900, 700
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
```

---

## 4. Script Generation in Python MCP (`generate_visit_script`)

Add this MCP tool to `docker/workspace/server.py`:

```python
from jinja2 import Environment, FileSystemLoader
import os

VISIT_TEMPLATE_DIR = "/workspace/templates/visit"

@mcp.tool()
async def generate_visit_script(
    plot_type: str,        # "wavefunction_1d" | "density_2d" | "density_3d"
    input_path: str,       # WINDOWS path to the data file (VisIt runs on Windows)
    output_png: str,       # WINDOWS path for the output PNG
    **kwargs               # Template-specific params (iso_value, colormap, etc.)
) -> dict:
    """
    Generates a VisIt Python script from a Jinja2 template.
    Returns the WINDOWS path to the written script file (in mounted volume).
    """
    template_map = {
        "wavefunction_1d": "render_wavefunction_1d.py.j2",
        "density_2d":      "render_density_2d.py.j2",
        "density_3d":      "render_density_3d_isosurface.py.j2",
    }
    if plot_type not in template_map:
        return {"success": False, "error": f"Unknown plot_type: {plot_type}"}

    env = Environment(
        loader=FileSystemLoader(VISIT_TEMPLATE_DIR),
        autoescape=False,
    )
    tmpl = env.get_template(template_map[plot_type])
    rendered = tmpl.render(
        nc_path=input_path,
        ascii_path=input_path,
        output_png=output_png,
        **kwargs
    )

    # Write to a path accessible from both Docker volume and Windows host
    script_linux_path = f"/workspace/output/visit_render_{plot_type}.py"
    with open(script_linux_path, "w") as f:
        f.write(rendered)

    # Return Windows path (same volume, different mount point)
    script_windows_path = output_png.rsplit("\\", 1)[0] + f"\\visit_render_{plot_type}.py"
    return {"success": True, "script_windows_path": script_windows_path}
```

---

## 5. LangGraph `renderVisualizationNode` Skeleton

```typescript
// In src/langgraph_agent.ts
import { renderWithVisIt } from "./visit_renderer.js";
import type { DiracSolverState } from "./langgraph_agent.js";

export async function renderVisualizationNode(
  state: DiracSolverState
): Promise<Partial<DiracSolverState>> {
  const { octopusRunDir, parsedResults } = state;
  if (!parsedResults?.info?.converged) {
    return { renderResult: { success: false, reason: "Skipped: GS not converged" } };
  }

  // 1. Ask MCP to generate the VisIt script
  const scriptResp = await callMcpTool("generate_visit_script", {
    plot_type: "wavefunction_1d",
    // Windows absolute path — Docker volume maps to z:\.openclaw\workspace\projects\Dirac\docker\workspace\output\
    input_path: octopusRunDir.replace("/workspace/output", "z:\\.openclaw\\workspace\\projects\\Dirac\\docker\\workspace\\output") + "\\static\\wf-st00001.y=0,z=0",
    output_png: octopusRunDir.replace("/workspace/output", "z:\\.openclaw\\workspace\\projects\\Dirac\\docker\\workspace\\output") + "\\render_wf1.png",
    state_label: `State 1 (E = ${parsedResults.info.eigenvalues[0]?.eigenvalue_hartree.toFixed(4)} H)`,
  });

  if (!scriptResp.success) {
    return { renderResult: { success: false, reason: scriptResp.error } };
  }

  // 2. Invoke VisIt on Windows host
  const renderResult = await renderWithVisIt({
    scriptPath: scriptResp.script_windows_path,
    outputPngPath: scriptResp.script_windows_path.replace("visit_render_wavefunction_1d.py", "render_wf1.png"),
    timeoutMs: 90_000,
  });

  return { renderResult };
}
```

---

## 6. Docker Volume ↔ Windows Path Mapping

This project uses the following volume mount (defined in `docker/docker-compose.yml`):

```yaml
volumes:
  - ./workspace:/workspace
```

| Context | Path |
| :--- | :--- |
| Docker / Python MCP | `/workspace/output/` |
| Windows / Node.js / VisIt | `z:\.openclaw\workspace\projects\Dirac\docker\workspace\output\` |

The **path translation function** to keep in `src/langgraph_agent.ts`:

```typescript
const DOCKER_OUTPUT = "/workspace/output";
const WINDOWS_OUTPUT = "z:\\.openclaw\\workspace\\projects\\Dirac\\docker\\workspace\\output";

export function dockerToWindowsPath(linuxPath: string): string {
  return linuxPath.replace(DOCKER_OUTPUT, WINDOWS_OUTPUT).replace(/\//g, "\\");
}
```

---

## 7. Troubleshooting

| Symptom | Likely Cause | Fix |
| :--- | :--- | :--- |
| `visit: command not found` | VisIt not on system PATH | Add `C:\VisIt\` (or actual install dir) to Windows PATH env var |
| `PNG not generated` | Script crashed before `SaveWindow()` | Check `proc.stderr` in Node.js — usually a VisIt database open error |
| `Database not found` | Wrong Windows path or missing output | Verify `docker-compose` volume mount and that Octopus actually wrote the file |
| Empty white image | Density all-zeros or isosurface value too high | Use `probe_density_metadata()` to check max value, adjust `iso_value` |
| VisIt hangs indefinitely | Deadlock on display init despite `-nowin` | Add `-nowin -nosplash -noint` flags |
| `AttributeError: module 'visit' has no attribute...` | VisIt Python API version mismatch | Match VisIt script API calls to the installed VisIt version (check `visit --version`) |
| File permission denied | Docker volume mounted read-only | Check `docker-compose.yml` — volume should be `rw` (default), not `ro` |
