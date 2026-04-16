/**
 * visit_renderer.ts
 * Windows/Linux VisIt headless rendering helper.
 * VisIt runs on the host; paths must be host absolute paths.
 */

import { spawn } from "child_process";
import fs from "fs";
import path from "path";

export interface VisItRenderOptions {
    /** Absolute Windows path to the .py script to run */
    scriptPath: string;
    /** Absolute Windows path where VisIt will write the PNG */
    outputPngPath: string;
    /** Timeout in ms (default 90 000) */
    timeoutMs?: number;
    /** Explicit path to visit.exe if not on PATH */
    visitExePath?: string;
}

export interface VisItRenderResult {
    success: boolean;
    pngPath?: string;
    pngBase64?: string;
    stderr?: string;
    durationMs?: number;
    reason?: string;
}

// ─── VisIt installation ──────────────────────────────────────────────────────

// Resolved from VISIT_EXE env var; falls back to bare "visit" (must be on PATH)
export const VISIT_EXE = process.env.VISIT_EXE ?? "visit";

let _visitPath: string | null | undefined;
let _visitTemporarilyDisabledReason: string | null = null;

/** Returns the path to visit.exe, or null if not found. Cached after first call. */
export function findVisItExe(explicitPath?: string): string | null {
    if (_visitPath !== undefined) return _visitPath;

    const candidates = [
        explicitPath,
        VISIT_EXE,
        // Fallback: rely on PATH (shell resolves the name)
        "visit",
    ].filter(Boolean) as string[];

    for (const candidate of candidates) {
        // Absolute / relative path with separators — check file existence directly
        if (candidate.includes("\\") || candidate.includes("/")) {
            if (fs.existsSync(candidate)) {
                _visitPath = candidate;
                return candidate;
            }
        } else {
            // Bare name — verify it's actually on PATH via `which` (Linux/Mac) or `where` (Win)
            try {
                const { execSync } = require("child_process");
                const cmd = process.platform === "win32" ? `where ${candidate}` : `which ${candidate}`;
                execSync(cmd, { stdio: "ignore" });
                _visitPath = candidate;
                return candidate;
            } catch {
                // Not found on PATH
            }
        }
    }
    _visitPath = null;
    return null;
}

export function isVisItAvailable(visitExePath?: string): boolean {
    if (_visitTemporarilyDisabledReason) {
        return false;
    }
    return findVisItExe(visitExePath) !== null;
}

// ─── Core render function ─────────────────────────────────────────────────────

export async function renderWithVisIt(
    opts: VisItRenderOptions
): Promise<VisItRenderResult> {
    const envTimeout = Number(process.env.VISIT_TIMEOUT_MS ?? 0);
    const effectiveDefault = Number.isFinite(envTimeout) && envTimeout > 0 ? envTimeout : 12_000;
    const { scriptPath, outputPngPath, timeoutMs = effectiveDefault, visitExePath } = opts;
    const start = Date.now();

    if (_visitTemporarilyDisabledReason) {
        return {
            success: false,
            reason: `VisIt disabled for this session: ${_visitTemporarilyDisabledReason}`,
            durationMs: 0,
        };
    }

    const resolvedExe = findVisItExe(visitExePath);
    if (!resolvedExe) {
        return {
            success: false,
            reason: `VisIt not found. Set VISIT_EXE env var to your visit executable path, or ensure "visit" is on PATH.`,
        };
    }

    if (!fs.existsSync(scriptPath)) {
        return { success: false, reason: `Script not found: ${scriptPath}` };
    }

    return new Promise((resolve) => {
        console.log(`[VisIt] Spawning: ${resolvedExe} -nowin -cli -s ${scriptPath}`);
        const proc = spawn(resolvedExe, ["-nowin", "-cli", "-s", scriptPath], {
            shell: false,
            windowsHide: process.platform === 'win32',
        });

        let stderr = "";
        let stdout = "";
        let settled = false;
        const settle = (r: VisItRenderResult) => {
            if (!settled) { settled = true; resolve(r); }
        };

        proc.stderr?.on("data", (d: Buffer) => { stderr += d.toString(); });
        proc.stdout?.on("data", (d: Buffer) => { stdout += d.toString(); });

        // Catch ENOENT / permission errors so the server never crashes
        proc.on("error", (err: NodeJS.ErrnoException) => {
            clearTimeout(timer);
            if (err.code === "ENOENT") {
                _visitTemporarilyDisabledReason = `executable not found (${resolvedExe})`;
            }
            settle({
                success: false,
                reason: err.code === "ENOENT"
                    ? `VisIt executable not found: "${resolvedExe}". VisIt works only on the Windows host — set VISIT_EXE in .env.`
                    : `Failed to spawn VisIt: ${err.message}`,
                durationMs: Date.now() - start,
            });
        });

        const timer = setTimeout(() => {
            proc.kill("SIGKILL");
            _visitTemporarilyDisabledReason = `timeout after ${timeoutMs}ms`;
            settle({
                success: false,
                reason: `VisIt timed out after ${timeoutMs}ms`,
                stderr,
                durationMs: Date.now() - start,
            });
        }, timeoutMs);

        proc.on("close", (code) => {
            clearTimeout(timer);
            const baseName = outputPngPath.replace(/\.png$/i, "");
            const framedPath = `${baseName}0000.png`;
            const actualPath = fs.existsSync(outputPngPath)
                ? outputPngPath
                : fs.existsSync(framedPath) ? framedPath : null;
            let pngBase64: string | undefined;
            if (actualPath) {
                pngBase64 = fs.readFileSync(actualPath).toString("base64");
            }
            settle({
                success: code === 0 && actualPath !== null,
                pngPath: actualPath ?? undefined,
                pngBase64,
                stderr: stderr || undefined,
                durationMs: Date.now() - start,
                reason: code !== 0 ? `VisIt exited with code ${code}` : (!actualPath ? "PNG not produced" : undefined),
            });
            if (code !== 0 || !actualPath) {
                _visitTemporarilyDisabledReason = code !== 0
                    ? `non-zero exit (${code})`
                    : "png not produced";
            }
        });
    });
}

// ─── Script generator (Jinja2-style template filling) ─────────────────────────

const WORKSPACE_ROOT = process.env.WORKSPACE_ROOT ?? process.cwd();
// Maps Docker /workspace/output → host output directory (env-var driven)
const DOCKER_TO_HOST_OUTPUT = process.env.OCTOPUS_OUTPUT_DIR
    ?? path.join(WORKSPACE_ROOT, '@Octopus_docs', 'output');

export function dockerPathToHost(containerPath: string): string {
    const resolved = containerPath.replace('/workspace/output', DOCKER_TO_HOST_OUTPUT);
    // On Windows normalize forward slashes to backslashes
    return process.platform === 'win32' ? resolved.replaceAll('/', '\\') : resolved;
}

export interface VisItScriptParams {
    plotType: "wavefunction_1d" | "density_2d" | "density_3d";
    inputHostPath: string;
    outputPngHostPath: string;
    stateLabel?: string;
    isoValue?: number;
    colormap?: string;
    densityMax?: number;
}

/** Writes a VisIt Python render script and returns its host path */
export function writeVisItScript(params: VisItScriptParams): string {
    const {
        plotType, inputHostPath, outputPngHostPath,
        stateLabel = "State", isoValue = 0.01,
        colormap = "hot", densityMax = 1.0,
    } = params;

    const scriptDir = DOCKER_TO_HOST_OUTPUT;
    fs.mkdirSync(scriptDir, { recursive: true });
    const scriptPath = path.join(scriptDir, `visit_render_${plotType}.py`);

    let content = "";

    // Helper for Python raw strings (handles backslashes on Windows)
    const pyPath = (p: string) => process.platform === 'win32' ? `r"${p}"` : `"${p}"`;

    if (plotType === "wavefunction_1d") {
        content = `import sys, os

input_path = ${pyPath(inputHostPath)}
output_png = ${pyPath(outputPngHostPath)}

# Convert Octopus 3-column ASCII to VisIt Ultra 2-column format
ultra_path = input_path + ".ultra"
xs, res, ims = [], [], []
with open(input_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith('#') or not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            res.append(float(parts[1]))
            if len(parts) >= 3:
                ims.append(float(parts[2]))

with open(ultra_path, 'w') as f:
    f.write("# Re(psi)\\n")
    for x, y in zip(xs, res):
        f.write(f"{x} {y}\\n")
    if ims:
        f.write("# Im(psi)\\n")
        for x, y in zip(xs, ims):
            f.write(f"{x} {y}\\n")

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
s.family = 0
s.width, s.height = 900, 500
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
`;
    } else if (plotType === "density_2d") {
        // density.y=0,z=0 is a 1D slice (x, rho) — same Ultra conversion
        content = `import sys, os

input_path = ${pyPath(inputHostPath)}
output_png = ${pyPath(outputPngHostPath)}

ultra_path = input_path + ".ultra"
xs, rhos = [], []
with open(input_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith('#') or not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            xs.append(float(parts[0]))
            rhos.append(float(parts[1]))

with open(ultra_path, 'w') as f:
    f.write("# rho(x)\\n")
    for x, y in zip(xs, rhos):
        f.write(f"{x} {y}\\n")

OpenDatabase(ultra_path)
AddPlot("Curve", "rho(x)")
DrawPlots()

a = GetAnnotationAttributes()
a.userInfoFlag = 0
a.databaseInfoFlag = 0
SetAnnotationAttributes(a)

s = SaveWindowAttributes()
s.fileName = output_png
s.format = s.PNG
s.family = 0
s.width, s.height = 900, 500
s.screenCapture = 0
SetSaveWindowAttributes(s)
SaveWindow()
sys.exit(0)
`;
    } else {
        // density_3d isosurface
        content = `import sys
# 3D electron density isosurface
nc_path    = ${pyPath(inputHostPath)}
output_png = ${pyPath(outputPngHostPath)}

OpenDatabase(nc_path)
AddPlot("Contour", "density")
c = ContourAttributes()
c.contourNLevels = 1
c.contourValue = (${isoValue},)
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
`;
    }

    fs.writeFileSync(scriptPath, content, "utf8");
    return scriptPath;
}
