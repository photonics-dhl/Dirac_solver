import asyncio
import json
import math
import os
import shlex
import re
import shutil
import subprocess
import time
import sys
import traceback
from typing import Optional
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse

import vasp_backend

# _parse_length helper
def _parse_length(val):
    import re
    s = str(val).strip()
    m = re.match(r"^([+-]?[\d.]+)\*(\w+)$", s, re.I)
    if m:
        num, unit = float(m.group(1)), m.group(2).lower()
        if unit in {"angstrom", "ang", "a"}:
            return num * 1.8897261328856432
        return num
    m = re.match(r"^([+-]?[\d.]+)\s*(angstrom|ang|a|bohr|b)?$", s, re.I)
    if m:
        num = float(m.group(1))
        if m.group(2) and m.group(2).lower() in {"angstrom", "ang", "a"}:
            num *= 1.8897261328856432
        return num
    try:
        return float(s)
    except:
        return 0.0


try:
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    import mcp.types as types
    MCP_AVAILABLE = True
except Exception:
    Server = None
    SseServerTransport = None
    types = None
    MCP_AVAILABLE = False


def render_density_snapshots(static_dir: str) -> dict:
    """Render density_2d + density_3d PNGs from density.cube, return base64 snapshots."""
    import base64
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cube_path = os.path.join(static_dir, "density.cube")
    if not os.path.exists(cube_path):
        # Try work_dir parent
        parent_static = os.path.join(os.path.dirname(static_dir), "static")
        cube_path_alt = os.path.join(parent_static, "density.cube")
        if os.path.exists(cube_path_alt):
            cube_path = cube_path_alt
        else:
            print(f"[render] No density.cube found, skipping render snapshots")
            return {}

    snapshots = {}
    try:
        # Parse Gaussian cube file
        with open(cube_path, 'r') as f:
            _ = f.readline()  # comment 1
            _ = f.readline()  # comment 2
            # Line 3: n_atoms  x_origin  y_origin  z_origin
            parts = f.readline().split()
            n_atoms = int(parts[0])
            # Lines 4-6: n_axis  vx  vy  vz  (one per axis)
            nx = int(f.readline().split()[0])
            ny = int(f.readline().split()[0])
            nz = int(f.readline().split()[0])
            # Skip atom position records
            for _ in range(n_atoms):
                f.readline()
            data = np.zeros((nx, ny, nz), dtype=np.float64)
            idx = 0
            for line in f:
                for val in line.split():
                    ix, iy, iz = np.unravel_index(idx, (nx, ny, nz))
                    data[ix, iy, iz] = float(val)
                    idx += 1
                    if idx >= nx * ny * nz:
                        break
                if idx >= nx * ny * nz:
                    break

        BG = '#0d1117'

        # --- Density 2D: 3 orthogonal slices ---
        iz_mid, iy_mid, ix_mid = nz // 2, ny // 2, nx // 2
        sl_xy = np.abs(data[:, :, iz_mid]).T
        sl_xz = np.abs(data[:, iy_mid, :]).T
        sl_yz = np.abs(data[ix_mid, :, :]).T
        vmax = max(sl_xy.max(), sl_xz.max(), sl_yz.max(), 1e-10)

        fig, axes = plt.subplots(1, 3, figsize=(12, 4), dpi=100)
        fig.patch.set_facecolor(BG)
        for ax in axes:
            ax.set_facecolor(BG)
            ax.tick_params(colors='#8b949e', labelsize=7)
            for spine in ax.spines.values():
                spine.set_color('#30363d')

        panels = [
            (sl_xy, "XY (z=mid)"),
            (sl_xz, "XZ (y=mid)"),
            (sl_yz, "YZ (x=mid)"),
        ]
        for ax, (sl, title) in zip(axes, panels):
            ax.imshow(sl, origin="lower", aspect="auto", cmap="plasma",
                      vmin=0, vmax=vmax, interpolation="bilinear")
            ax.set_title(title, fontsize=9, color='#c9d1d9', pad=3)
        fig.suptitle("Electron Density — Orthogonal Slices",
                     color='#c9d1d9', fontsize=11, fontweight="light", y=1.01)
        plt.tight_layout(pad=1.2)

        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            fig.savefig(tmp.name, dpi=100, bbox_inches="tight", facecolor=BG, edgecolor="none")
            plt.close(fig)
            with open(tmp.name, 'rb') as img_f:
                snapshots['density_2d_png'] = base64.b64encode(img_f.read()).decode('ascii')
            os.unlink(tmp.name)

        # --- Density 3D: isosurface via render_mpl.py (marching cubes) ---
        render_mpl_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "render_mpl.py"))
        if os.path.isfile(render_mpl_path):
            import subprocess
            tmp_png_3d = tempfile.mktemp(suffix='.png')
            try:
                proc = subprocess.run(
                    [sys.executable, render_mpl_path, cube_path, "density_3d_iso", tmp_png_3d, "0.05", "hot"],
                    capture_output=True, text=True, timeout=90)
                if proc.returncode == 0 and os.path.isfile(tmp_png_3d):
                    with open(tmp_png_3d, 'rb') as img_f:
                        snapshots['density_3d_png'] = base64.b64encode(img_f.read()).decode('ascii')
                    print(f"[render] 3D snapshot via marching_cubes: {len(snapshots['density_3d_png'])//1024}KB")
                else:
                    print(f"[render] render_mpl.py 3D failed: {proc.stderr[:200]}")
            except subprocess.TimeoutExpired:
                print("[render] render_mpl.py 3D timed out (90s)")
            finally:
                if os.path.isfile(tmp_png_3d):
                    os.unlink(tmp_png_3d)
        if 'density_3d_png' not in snapshots:
            # Fallback: simple MIP if render_mpl.py unavailable
            mip_xy = np.max(data, axis=2).T
            mip_max = max(mip_xy.max(), 1e-10)
            fig2, ax2 = plt.subplots(1, 1, figsize=(5, 4), dpi=100)
            fig2.patch.set_facecolor(BG); ax2.set_facecolor(BG)
            ax2.tick_params(colors='#8b949e', labelsize=7)
            ax2.imshow(mip_xy, origin="lower", aspect="auto", cmap="hot",
                       vmin=0, vmax=mip_max, interpolation="bilinear")
            ax2.set_title("MIP (fallback)", fontsize=9, color='#c9d1d9')
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                fig2.savefig(tmp.name, dpi=100, bbox_inches="tight", facecolor=BG, edgecolor="none")
                plt.close(fig2)
                with open(tmp.name, 'rb') as img_f:
                    snapshots['density_3d_png'] = base64.b64encode(img_f.read()).decode('ascii')
                os.unlink(tmp.name)

        del data
        import gc; gc.collect()
        print(f"[render] Generated density snapshots: 2d={len(snapshots.get('density_2d_png',''))//1024}KB, 3d={len(snapshots.get('density_3d_png',''))//1024}KB")
    except Exception as e:
        print(f"[render] Density snapshot failed: {e}")
        import traceback; traceback.print_exc()

    return snapshots


def sanitize_floats(obj):
    """Recursively replace NaN/Inf with 0.0 so JSON serialization never crashes."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj
from jinja2 import Template

mcp_server = Server("octopus-physics-mcp") if MCP_AVAILABLE else None


def resolve_output_dir() -> str:
    configured = os.environ.get("OCTOPUS_OUTPUT_DIR", "").strip()
    if configured:
        return configured
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "run", "octopus_output"))


def resolve_repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _extract_llm_output_file(stdout_text: str) -> Optional[str]:
    for line in reversed(stdout_text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("status") == "success":
                return str(obj.get("file", "")).strip() or None
        except Exception:
            continue
    return None


def _read_lines_safe(path: str, max_lines: int = 80) -> list[str]:
    if not os.path.exists(path):
        return []
    lines: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
    except Exception:
        return []
    return lines


def _parse_cross_section_header(work_dir: str) -> dict:
    cs_path = os.path.join(work_dir, "cross_section_vector")
    if not os.path.exists(cs_path):
        return {}

    header: dict[str, str] = {}
    for raw in _read_lines_safe(cs_path, max_lines=100):
        s = raw.strip()
        if not s.startswith("#"):
            continue
        content = s[1:].strip()
        if not content:
            continue
        if "=" in content:
            k, v = content.split("=", 1)
            header[k.strip().lower()] = v.strip()
            continue
        parts = content.split()
        if len(parts) >= 2:
            key = " ".join(parts[:-1]).strip().lower()
            val = parts[-1].strip()
            header[key] = val
    return header


def _summarize_dos_file(work_dir: str) -> dict:
    candidates = [
        os.path.join(work_dir, "static", "total-dos.dat"),
        os.path.join(work_dir, "static", "dos.dat"),
        os.path.join(work_dir, "total-dos.dat"),
    ]
    dos_path = next((p for p in candidates if os.path.exists(p)), "")
    if not dos_path:
        return {}

    energies: list[float] = []
    dos_vals: list[float] = []
    try:
        with open(dos_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                cols = s.split()
                if len(cols) < 2:
                    continue
                try:
                    e = float(cols[0])
                    d = float(cols[1])
                except Exception:
                    continue
                energies.append(e)
                dos_vals.append(d)
    except Exception:
        return {"path": dos_path}

    out = {"path": dos_path, "points": len(energies)}
    if energies:
        out["energy_min"] = min(energies)
        out["energy_max"] = max(energies)
    if dos_vals:
        i_peak = max(range(len(dos_vals)), key=lambda i: dos_vals[i])
        out["peak_energy"] = energies[i_peak]
        out["peak_dos"] = dos_vals[i_peak]
    return out


def _td_walltime_to_seconds(wt: str) -> int:
    """Convert PBS walltime 'HH:MM:SS' or 'HH:MM:SS,HH:MM:SS' to seconds."""
    parts = wt.split(",")[0].strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 3600 + int(parts[1]) * 60
    return int(parts[0]) * 3600


def _read_units_output_from_inp(work_dir: str) -> Optional[str]:
    for name in ["inp_td", "inp_gs", "inp"]:
        p = os.path.join(work_dir, name)
        if not os.path.exists(p):
            continue
        for line in _read_lines_safe(p, max_lines=160):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"^UnitsOutput\s*=\s*(.+)$", s, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return None


def _collect_run_image_paths(work_dir: str, max_images: int = 6) -> list[str]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".svg"}
    out: list[str] = []
    for root, _, files in os.walk(work_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in exts:
                continue
            out.append(os.path.join(root, name))
            if len(out) >= max_images:
                return out
    return out


def _build_fallback_run_explanation(work_dir: str, config: dict, result_data: dict) -> str:
    calc_mode = str(config.get("calcMode", "gs"))
    molecule = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", "Unknown")))
    spacing = config.get("octopusSpacing", config.get("gridSpacing", "-"))
    radius = config.get("octopusRadius", config.get("spatialRange", "-"))

    molecular = result_data.get("molecular") or {}
    spectrum = molecular.get("optical_spectrum") or {}
    run_dir = (result_data.get("scheduler") or {}).get("run_dir")

    lines = [
        "# Run Quick Guide",
        "",
        "本说明为本地快速解读（不调用 LLM），用于帮助理解本次 run 输出中各字段的数据类型。",
        "",
        "## Basic Info",
        f"- molecule: {molecule}",
        f"- calcMode: {calc_mode}",
        f"- spacing: {spacing}",
        f"- radius/range: {radius}",
        f"- run_dir: {run_dir or '(local-temp)'}",
        "",
        "## Field Type Guide",
        f"- eigenvalues: list[number], count={len(result_data.get('eigenvalues') or [])}",
        f"- total_energy: number | null, value={result_data.get('total_energy')}",
        f"- converged: boolean, value={result_data.get('converged')}",
        f"- scf_iterations: integer, value={result_data.get('scf_iterations')}",
        f"- molecular.energy_levels: list[number], count={len(molecular.get('energy_levels') or [])}",
        f"- molecular.homo_energy: number | null, value={molecular.get('homo_energy')}",
        f"- molecular.lumo_energy: number | null, value={molecular.get('lumo_energy')}",
        f"- molecular.optical_spectrum.energy_ev: list[number], count={len(spectrum.get('energy_ev') or [])}",
        f"- molecular.optical_spectrum.cross_section: list[number], count={len(spectrum.get('cross_section') or [])}",
        f"- scheduler: object | null, present={bool(result_data.get('scheduler'))}",
        "",
        "## Output Files",
        "- static/info: text file, SCF summary and eigenvalue info.",
        "- static/convergence: text table, iteration convergence history.",
        "- td.general/*: time-series outputs in TD mode.",
        "- cross_section_vector: tabular text spectrum (if TD spectrum generated).",
        "- octopus.stdout / octopus.stderr: solver logs for debugging.",
        "",
    ]
    return "\n".join(lines)


def write_run_explanation(work_dir: str, config: dict, result_data: dict) -> Optional[dict]:
    enabled = os.environ.get("OCTOPUS_RUN_EXPLANATION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not work_dir or not os.path.isdir(work_dir):
        return None

    file_name = os.environ.get("OCTOPUS_RUN_EXPLANATION_FILE", "RUN_EXPLANATION.md").strip() or "RUN_EXPLANATION.md"
    explanation_path = os.path.join(work_dir, file_name)

    fallback_md = _build_fallback_run_explanation(work_dir, config, result_data)
    try:
        with open(explanation_path, "w", encoding="utf-8") as f:
            f.write(fallback_md)
    except Exception as e:
        print(f"[WARN] Failed to write fallback explanation: {e}")
        return None

    return {
        "file": file_name,
        "path": explanation_path,
        "used_llm": False,
        "status": "local-quick-guide",
    }


def cleanup_octopus_run_dirs(runs_dir: str, active_run_dir: Optional[str] = None) -> None:
    """Cleanup old Octopus run directories with retention and age policy."""
    enabled = os.environ.get("OCTOPUS_RUN_CLEANUP_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    try:
        keep_latest = int(os.environ.get("OCTOPUS_RUN_RETENTION_COUNT", "20"))
    except ValueError:
        keep_latest = 20
    keep_latest = max(0, keep_latest)

    try:
        max_age_hours = float(os.environ.get("OCTOPUS_RUN_MAX_AGE_HOURS", "168"))
    except ValueError:
        max_age_hours = 168.0
    max_age_seconds = max(0.0, max_age_hours) * 3600.0

    keep_failed = os.environ.get("OCTOPUS_RUN_KEEP_FAILED", "true").strip().lower() in {"1", "true", "yes", "on"}

    if not os.path.isdir(runs_dir):
        return

    now = time.time()
    candidates = []
    for name in os.listdir(runs_dir):
        if not name.startswith("octopus_"):
            continue
        full_path = os.path.join(runs_dir, name)
        if not os.path.isdir(full_path):
            continue
        if active_run_dir and os.path.abspath(full_path) == os.path.abspath(active_run_dir):
            continue
        try:
            mtime = os.path.getmtime(full_path)
        except OSError:
            continue
        candidates.append((full_path, mtime))

    candidates.sort(key=lambda item: item[1], reverse=True)

    for index, (run_path, mtime) in enumerate(candidates):
        age_seconds = max(0.0, now - mtime)
        delete_by_count = index >= keep_latest
        delete_by_age = age_seconds > max_age_seconds
        if not (delete_by_count or delete_by_age):
            continue

        exitcode_path = os.path.join(run_path, "octopus.exitcode")
        if keep_failed and os.path.exists(exitcode_path):
            try:
                rc_text = open(exitcode_path, "r", encoding="utf-8").read().strip()
                rc_value = int(rc_text)
                if rc_value != 0:
                    continue
            except Exception:
                continue

        try:
            shutil.rmtree(run_path, ignore_errors=True)
            print(f"[DEBUG] cleanup removed old run dir: {run_path}")
        except Exception as e:
            print(f"[WARN] cleanup failed for {run_path}: {e}")


def prepare_reusable_run_dir(runs_dir: str, run_dir_name: str) -> str:
    """Prepare a stable run directory by removing previous contents."""
    run_dir_name = (run_dir_name or "octopus_latest").strip() or "octopus_latest"
    work_dir = os.path.join(runs_dir, run_dir_name)
    os.makedirs(work_dir, exist_ok=True)

    for entry in os.listdir(work_dir):
        entry_path = os.path.join(work_dir, entry)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path, ignore_errors=True)
            else:
                os.remove(entry_path)
        except Exception as e:
            print(f"[WARN] failed to clear reusable run entry {entry_path}: {e}")

    return work_dir

# ─── Octopus inp templates ────────────────────────────────────────

POTENTIAL_TEMPLATES = {
    "Harmonic": '"0.5*x^2"',
    "FiniteWell": '"-{depth}*step({hw}-abs(x))"',
    "FreeSpace": '"0"',
}

# Real 3D Coordinates (Angstroms roughly for demonstration, Octopus default is Ang if Units=eV_Angstrom, otherwise Bohr)
# We will use default atomic units (Bohr), but these serve as a demo structure
MOLECULES = {
    "H": [
        " 'H' | 0.0 | 0.0 | 0.0 "
    ],
    "N_atom": [
        " 'N' | 0.0 | 0.0 | 0.0 "
    ],
    "O": [
        " 'O' | 0.0 | 0.0 | 0.0 "
    ],
    "C": [
        " 'C' | 0.0 | 0.0 | 0.0 "
    ],
    "He": [
        " 'He' | 0.0 | 0.0 | 0.0 "
    ],
    "H2": [
        " 'H' | 0.0 | 0.0 | -0.7 " ,
        " 'H' | 0.0 | 0.0 | 0.7 "
    ],
    "N2": [
        " 'N' | 0.0 | 0.0 | -1.03 " ,
        " 'N' | 0.0 | 0.0 | 1.03 "
    ],
    "CH4": [
        " 'C' | 0.0 | 0.0 | 0.0 " ,
        # CH = 1.2 A = 2.26767 Bohr; each Cartesian component = 2.26767/sqrt(3) = 1.30927 Bohr
        " 'H' | 1.30927 | 1.30927 | 1.30927 " ,
        " 'H' | -1.30927 | -1.30927 | 1.30927 " ,
        " 'H' | 1.30927 | -1.30927 | -1.30927 " ,
        " 'H' | -1.30927 | 1.30927 | -1.30927 "
    ],
    "Benzene": [
        " 'C' | 0.000000 |  1.396000 | 0.000000 ",
        " 'C' | 1.208966 |  0.698000 | 0.000000 ",
        " 'C' | 1.208966 | -0.698000 | 0.000000 ",
        " 'C' | 0.000000 | -1.396000 | 0.000000 ",
        " 'C' |-1.208966 | -0.698000 | 0.000000 ",
        " 'C' |-1.208966 |  0.698000 | 0.000000 ",
        " 'H' | 0.000000 |  2.484000 | 0.000000 ",
        " 'H' | 2.151214 |  1.242000 | 0.000000 ",
        " 'H' | 2.151214 | -1.242000 | 0.000000 ",
        " 'H' | 0.000000 | -2.484000 | 0.000000 ",
        " 'H' |-2.151214 | -1.242000 | 0.000000 ",
        " 'H' |-2.151214 |  1.242000 | 0.000000 "
    ],
    # ── New molecules added 2026-03 ──
    "CO": [
        " 'C' | 0.0 | 0.0 | -1.066 ",
        " 'O' | 0.0 | 0.0 |  1.066 ",
    ],
    "H2O": [
        " 'O' | 0.0    | 0.0 |  0.0   ",
        " 'H' | 1.430  | 0.0 | -1.107 ",
        " 'H' |-1.430  | 0.0 | -1.107 ",
    ],
    "NH3": [
        " 'N' | 0.0    |  0.000 |  0.0   ",
        " 'H' | 0.0    |  1.771 | -0.627 ",
        " 'H' | 1.533  | -0.886 | -0.627 ",
        " 'H' |-1.533  | -0.886 | -0.627 ",
    ],
    "C2H4": [
        " 'C' | 0.0    |  0.0  |  1.261 ",
        " 'C' | 0.0    |  0.0  | -1.261 ",
        " 'H' | 1.745  |  0.0  |  2.332 ",
        " 'H' |-1.745  |  0.0  |  2.332 ",
        " 'H' | 1.745  |  0.0  | -2.332 ",
        " 'H' |-1.745  |  0.0  | -2.332 ",
    ],
    "Li": [" 'Li' | 0.0 | 0.0 | 0.0 "],
    "Na": [" 'Na' | 0.0 | 0.0 | 0.0 "],
    "LiH": [
        " 'Li' | 0.0 | 0.0 | -1.511 ",
        " 'H'  | 0.0 | 0.0 |  1.511 ",
    ],
    # Periodic crystals — use ReducedCoordinates in generate_inp()
    "Si": [
        " 'Si' | 0.0   | 0.0   | 0.0   ",
        " 'Si' | 2.566 | 2.566 | 2.566 ",
    ],
    "Al2O3": [
        " 'Al' | 0.0   | 0.0   |  2.263 ",
        " 'Al' | 0.0   | 0.0   | -2.263 ",
        " 'O'  | 2.386 | 0.0   |  0.0   ",
        " 'O'  |-1.193 | 2.067 |  0.0   ",
        " 'O'  |-1.193 |-2.067 |  0.0   ",
    ],
}

# 2D coordinates (Bohr) — bond axes rotated into the xy-plane
MOLECULES_2D = {
    "H": [" 'H' | 0.0 | 0.0 "],
    "He": [" 'He' | 0.0 | 0.0 "],
    "H2": [
        " 'H' | -0.7 | 0.0 ",
        " 'H' |  0.7 | 0.0 ",
    ],
    "N2": [
        " 'N' | -1.03 | 0.0 ",
        " 'N' |  1.03 | 0.0 ",
    ],
    "CH4": [
        " 'C' |  0.000 |  0.000 ",
        " 'H' |  0.69282 |  0.69282 ",
        " 'H' | -0.69282 |  0.69282 ",
        " 'H' | -0.69282 | -0.69282 ",
        " 'H' |  0.69282 | -0.69282 ",
    ],
    "Benzene": [
        " 'C' |  0.000000 |  1.396000 ",
        " 'C' |  1.208966 |  0.698000 ",
        " 'C' |  1.208966 | -0.698000 ",
        " 'C' |  0.000000 | -1.396000 ",
        " 'C' | -1.208966 | -0.698000 ",
        " 'C' | -1.208966 |  0.698000 ",
        " 'H' |  0.000000 |  2.484000 ",
        " 'H' |  2.151214 |  1.242000 ",
        " 'H' |  2.151214 | -1.242000 ",
        " 'H' |  0.000000 | -2.484000 ",
        " 'H' | -2.151214 | -1.242000 ",
        " 'H' | -2.151214 |  1.242000 ",
    ],
    # ── New molecules added 2026-03 ──
    "CO":  [" 'C' | -1.066 | 0.0 ", " 'O' |  1.066 | 0.0 "],
    "H2O": [" 'O' |  0.0   | 0.0 ", " 'H' |  1.430 | -1.107 ", " 'H' | -1.430 | -1.107 "],
    "NH3": [
        " 'N' |  0.0   |  0.0   ",
        " 'H' |  1.771 | -0.627 ",
        " 'H' | -0.886 | -0.627 ",
    ],
    "C2H4": [
        " 'C' |  1.261 |  0.0   ",
        " 'C' | -1.261 |  0.0   ",
        " 'H' |  2.332 |  1.745 ",
        " 'H' |  2.332 | -1.745 ",
        " 'H' | -2.332 |  1.745 ",
        " 'H' | -2.332 | -1.745 ",
    ],
    "Li":  [" 'Li' | 0.0 | 0.0 "],
    "Na":  [" 'Na' | 0.0 | 0.0 "],
    "LiH": [" 'Li' | -1.511 | 0.0 ", " 'H' |  1.511 | 0.0 "],
    "Si":  [" 'Si' | 0.0 | 0.0 "],  # periodic: use ReducedCoordinates
    "Al2O3": [" 'Al' | 0.0 | 0.0 ", " 'O' |  2.386 | 0.0 "],  # simplified
}

octopus_inp_template = Template("""CalculationMode = gs
Dimensions = {{ dimensions }}
BoxShape = sphere
Spacing = {{ grid_spacing }}
Radius = {{ radius }}

ExtraStates = {{ extra_states }}

%Output
  wfs
  potential
  eigenvalues
%
OutputFormat = axis_x

%Species
  "Particle" | species_user_defined | potential_formula | {{ potential_formula }} | valence | 1
%

%Coordinates
  "Particle" | 0
%
""")


def _collect_element_symbols(coords: list) -> set:
    """Collect unique element symbols from coordinate entries."""
    elements_in_mol = set()
    for line in coords:
        if isinstance(line, dict):
            sym = str(line.get("symbol", "")).strip()
            if sym:
                elements_in_mol.add(sym)
            continue
        m_sym = re.search(r"'([A-Za-z]{1,2})'", str(line))
        if m_sym:
            elements_in_mol.add(m_sym.group(1))
    return elements_in_mol


def _build_pseudo_species_block(elements_in_mol: set, pseudopotential_set: str = "standard") -> str:
    """Build PP-mode %Species lines for all elements in the molecule.

    For pseudopotential_set="standard", uses HGH explicit file paths for elements
    that are NOT in the PSF standard set (e.g. He is only in HGH, not PSF).
    Elements in the PSF set use the "set | standard" syntax.
    For non-standard sets, uses explicit UPF file paths from OCTOPUS_PP_PATH.

    Args:
        elements_in_mol: set of element symbols (e.g. {'H', 'N'})
        pseudopotential_set: PP set name ("standard" for HGH built-in, else UPF)
    """
    pp_path = os.environ.get("OCTOPUS_PP_PATH", "").strip()
    use_built_in = pseudopotential_set.strip().lower() == "standard" or not pp_path
    # Elements NOT in Octopus PSF standard set but available as HGH files
    _hgh_only = {"He"}
    _hgh_path = "/app/share/octopus/pseudopotentials/HGH/lda"
    lines = []
    for sym in sorted(elements_in_mol):
        if not use_built_in:
            lines.append(f'  "{sym}" | species_pseudo | file | "{sym}.upf"')
        elif sym in _hgh_only:
            lines.append(f'  "{sym}" | species_pseudo | file | "{_hgh_path}/{sym}.hgh"')
        else:
            lines.append(f'  "{sym}" | species_pseudo | set | standard | lmax | 1 | lloc | 0')
    return "%Species\n" + "\n".join(lines) + "\n%"


def _build_formula_species_block(elements_in_mol: set, alpha_overrides: dict = None) -> str:
    """Build formula-based %Species lines for all detected elements.

    Args:
        elements_in_mol: set of element symbols (e.g. {'H', 'O'})
        alpha_overrides: optional dict of symbol -> alpha values
                         e.g. {'H': 0.05, 'He': 0.1}
                         Global default alpha can be set via '_default': 0.1
    """
    # Per-element alpha overrides from config (softCoreAlpha param)
    # Supports: {'H': 0.05, 'He': 0.1} or {'_default': 0.1}
    global_default_alpha = 0.1
    if isinstance(alpha_overrides, dict):
        global_default_alpha = float(alpha_overrides.get("_default", global_default_alpha))
    # Hardcoded formula map: symbol -> (formula, valence)
    formula_map = {
        # Soft-core Coulomb: -1/sqrt(r^2+α) with larger α for better SCF convergence
        # α=0.1 gives V(0)=-10 Ha (vs -1000 for α=1e-4), reducing the deep-well artifact
        "H": ("-1/sqrt(r^2+0.1)", 1),
        # Other elements
        "He": ("-2/sqrt(r^2+0.01)", 2),
        "Li": ("-1/sqrt(r^2+0.01)", 1),
        "C": ("-4/sqrt(r^2+0.01)", 4),
        "N": ("-5/sqrt(r^2+0.01)", 5),
        "O": ("-6/sqrt(r^2+0.01)", 6),
        "Na": ("-1/sqrt(r^2+0.04)", 1),
        "Si": ("-4/sqrt(r^2+0.01)", 4),
        "Al": ("-3/sqrt(r^2+0.01)", 3),
    }
    lines = []
    for sym in sorted(elements_in_mol):
        # Resolve alpha: per-element override > global default
        elem_alpha = global_default_alpha
        if isinstance(alpha_overrides, dict):
            elem_alpha = float(alpha_overrides.get(sym, alpha_overrides.get("_default", global_default_alpha)))
        if sym in formula_map:
            _, valence = formula_map[sym]
            # Use per-element override alpha, falling back to formula_map default
            formula_str = f"-1/sqrt(r^2+{elem_alpha})" if valence == 1 else f"-{valence}/sqrt(r^2+{elem_alpha})"
            lines.append(
                f"  '{sym}' | species_user_defined | potential_formula | \"{formula_str}\" | valence | {valence}"
            )
        else:
            # Unknown element — use generic 1-electron approximation
            lines.append(
                f"  '{sym}' | species_user_defined | potential_formula | \"-1/sqrt(r^2+{elem_alpha})\" | valence | 1"
            )
    return "\n".join(lines)


# ─── Helper: resolve Octopus udocker container ────────────────────

def _resolve_octopus_udocker_container(udocker_bin: str) -> str:
    """Return an existing Octopus udocker container ID, or raise RuntimeError."""
    container_name = os.environ.get("OCTOPUS_UDOCKER_CONTAINER", "").strip()
    if container_name:
        return container_name
    import subprocess as _sp
    try:
        _r = _sp.run([udocker_bin, "ps"], capture_output=True, text=True, timeout=30)
        out = (_r.stdout or "") + "\n" + (_r.stderr or "")
        for _line in out.splitlines():
            if "octopus" in _line:
                return _line.split()[0]
    except Exception as _e:
        print(f"[WARN] _resolve_octopus_udocker_container subprocess failed: {_e}", flush=True)
    raise RuntimeError(
        "No Octopus udocker container found. "
        "Run 'udocker pull registry.gitlab.com/octopus-code/octopus:16.0' and "
        "'udocker create --name=octopus registry.gitlab.com/octopus-code/octopus:16.0'"
    )


# ─── Helper: run Octopus and parse results ────────────────────────

def generate_inp(config: dict, is_td: bool = False, is_casida: bool = False, is_vib: bool = False) -> str:
    """Generate an Octopus inp file from physics config."""
    engine_mode = config.get("engineMode", "octopus3D")
    dim_str = config.get("octopusDimensions", "3D")

    if engine_mode == "octopus3D" and dim_str != "1D":
        mol_raw = config.get("molecule", config.get("moleculeName", config.get("molecule_name", config.get("octopusMolecule", "H2"))))
        # mol_raw can be a string name ("H2") or a dict {"name": "H2", "atoms": [...]}
        if isinstance(mol_raw, dict):
            molecule = mol_raw.get("name", "H2")
            custom_atoms = mol_raw.get("atoms", None)
        else:
            molecule = mol_raw
            custom_atoms = None

        # Case-insensitive molecule lookup
        if custom_atoms is None and molecule not in MOLECULES:
            mol_lower = molecule.lower()
            for key in MOLECULES:
                if key.lower() == mol_lower:
                    molecule = key
                    break
        # Map bare element symbols to MOLECULES keys for single atoms
        # e.g., 'N' -> 'N_atom', 'O' -> 'O', 'C' -> 'C', 'He' -> 'He'
        if custom_atoms is None and molecule not in MOLECULES:
            _element_to_molecule = {"N": "N_atom", "He": "He", "Li": "Li", "Na": "Na", "O": "O", "C": "C"}
            if molecule in _element_to_molecule:
                molecule = _element_to_molecule[molecule]

        dimensions = 2 if dim_str == "2D" else 3

        # Build coords_str from custom atoms if provided, else from MOLECULES table
        if custom_atoms:
            coords_lines = [f"  '{a['symbol']}' | {a['x']} | {a['y']} | {a['z']}" for a in custom_atoms]
            coords_str = "\n".join(coords_lines)
        elif dimensions == 2:
            coords = MOLECULES_2D.get(molecule, MOLECULES_2D.get("H2", [" 'H' | 0.0 | 0.0 "]))
            coords_str = "\n".join(coords)
        else:
            coords = MOLECULES.get(molecule, MOLECULES["H2"])
            coords_str = "\n".join(coords)

        # Molecule Mode (2D or 3D)
        inp = f"Dimensions = {dimensions}\n"
        calc_mode = 'td' if is_td else ('casida' if is_casida else ('vib_modes' if is_vib else 'gs'))
        inp += f"CalculationMode = {calc_mode}\n"
        # Geometry optimization (GO) support
        go_method = str(config.get("GOMethod", config.get("goMethod", "")) or "").strip()
        if go_method:
            valid_go = {"steepest_descent", "fire", "cg", "bfgs"}
            go_lower = go_method.lower()
            if go_lower in valid_go:
                inp += f"GOMethod = {go_lower}\n"
                # If GO is active, we're in go mode, not gs mode
                if calc_mode == 'gs':
                    inp = inp.replace("CalculationMode = gs\n", "CalculationMode = go\n")
                # GO-specific defaults
                go_tol = config.get("GOTolerance", "0.0001")
                inp += f"GOTolerance = {go_tol}\n"
                go_max_iter = int(config.get("GOMaxIter", 200))
                inp += f"GOMaxIter = {go_max_iter}\n"
            else:
                print(f"[WARN] Unknown GOMethod='{go_method}'. Supported: {', '.join(sorted(valid_go))}. Ignoring.", flush=True)
        inp += "\n"
        
        # Grid parameters from config
        spacing = _parse_length(config.get("octopusSpacing", config.get("gridSpacing", config.get("spacing", "0.3"))))
        # Priority: octopusRadius (a real radius) > spatialRange/2 (spatialRange is a diameter) > radius > default
        # IMPORTANT: only halve when falling back to spatialRange — if octopusRadius is explicitly set it is already a radius.
        if "octopusRadius" in config:
            radius = _parse_length(config["octopusRadius"])
        elif "spatialRange" in config:
            radius = _parse_length(config["spatialRange"]) / 2.0  # spatialRange is diameter
        else:
            radius = _parse_length(config.get("radius", 10.0))

        # Length unit normalization:
        # - default keeps backward-compatible behavior (Bohr)
        # - when explicitly set to Angstrom, convert spacing/radius to Bohr once here
        length_unit = str(config.get("octopusLengthUnit", config.get("octopusInputUnit", "bohr")) or "bohr").strip().lower()
        if length_unit in {"angstrom", "ang", "a", "ev_angstrom", "ev-angstrom"}:
            ang_to_bohr = 1.8897261328856432
            spacing = float(spacing) * ang_to_bohr
            radius = float(radius) * ang_to_bohr
            print(f"[INFO] Converted octopusSpacing/octopusRadius from Angstrom to Bohr: spacing={spacing}, radius={radius}", flush=True)

        # Auto-expand radius so all atoms fit inside the global sphere (BoxShape=sphere is centered at origin).
        # Any atom with dist_from_origin > radius is outside the simulation box and will cause nonsensical SCF or timeout.
        import math as _math
        if custom_atoms:
            _atom_coords = custom_atoms
        elif dimensions == 2:
            _atom_coords = MOLECULES_2D.get(molecule, [])
        else:
            _atom_coords = MOLECULES.get(molecule, [])
        _max_dist = 0.0
        for _a in _atom_coords:
            if isinstance(_a, dict):
                _d = _math.sqrt(float(_a.get('x', 0))**2 + float(_a.get('y', 0))**2 + float(_a.get('z', 0))**2)
            else:
                # parse "  'H' | x | y | z " or "  'H' | x | y " strings
                _parts = [p.strip() for p in str(_a).split('|')]
                try:
                    _coords = [float(_parts[i]) for i in range(1, min(4, len(_parts)))]
                    _d = _math.sqrt(sum(c**2 for c in _coords))
                except (ValueError, IndexError):
                    _d = 0.0
            if _d > _max_dist:
                _max_dist = _d
        base_padding = float(config.get("octopusBoxPadding", os.environ.get("OCTOPUS_BOX_PADDING_BOHR", "5.0")))
        if bool(config.get("fastPath", False)):
            fast_padding_cap = float(os.environ.get("OCTOPUS_FAST_BOX_PADDING_BOHR", "2.5"))
            base_padding = min(base_padding, fast_padding_cap)
        _min_required_radius = _max_dist + base_padding
        if radius < _min_required_radius:
            print(f"[WARN] Box radius {radius} Bohr too small for geometry (max atom dist={_max_dist:.2f} Bohr). Auto-expanding to {_min_required_radius:.1f} Bohr.", flush=True)
            radius = round(_min_required_radius, 1)

        # Guard against OOM: if effective box volume at the chosen spacing would produce >8M grid points, raise spacing.
        _effective_diam = 2.0 * float(radius)
        _npts_per_axis = _effective_diam / spacing
        _total_pts = _npts_per_axis ** 3
        if _total_pts > 8_000_000:
            _safe_spacing = round((_effective_diam / (8_000_000 ** (1/3))), 2)
            print(f"[WARN] Spacing={spacing} with radius={radius} → {_total_pts/1e6:.1f}M grid points (exceeds 8M limit). Clamping spacing to {_safe_spacing} Bohr.", flush=True)
            spacing = max(float(spacing), _safe_spacing)

        raw_radius = str(config.get("octopusRadius", config.get("radius", "")))
        raw_spacing = str(config.get("octopusSpacing", config.get("gridSpacing", config.get("spacing", ""))))
        # Unit suffix for generated input. Values are always in Bohr internally (after
        # Angstrom→Bohr conversion on lines 676-678). Default to NO suffix — raw numbers
        # only — because the Octopus 16 udocker container rejects "*bohr" in Radius/Spacing.
        # Only add a suffix if one was explicitly present in the raw config string.
        default_suffix = ""
        if "*angstrom" in raw_radius.lower():
            inp_radius = raw_radius
        elif "*bohr" in raw_radius.lower():
            inp_radius = raw_radius
        else:
            inp_radius = f"{radius:.10g}{default_suffix}"
        if "*angstrom" in raw_spacing.lower():
            inp_spacing = raw_spacing
        elif "*bohr" in raw_spacing.lower():
            inp_spacing = raw_spacing
        else:
            inp_spacing = f"{spacing:.10g}{default_suffix}"
        inp += f"Radius = {inp_radius}\n"
        inp += f"Spacing = {inp_spacing}\n\n"
        print(f"[DEBUG] Generated Octopus input: Radius={radius} Bohr, Spacing={spacing} Bohr, "
              f"TotalPoints={_npts_per_axis**3:.0f} ({_npts_per_axis:.1f}^3)", flush=True)
        
        species_mode = str(config.get("speciesMode", "builtin_standard") or "builtin_standard").strip().lower().replace("-", "_")
        xc_functional = config.get("xcFunctional", config.get("xc_functional", "lda_x+lda_c_pz"))

        # Octopus 16.0 Casida kernel only accepts LDA — force it regardless of user config
        if is_casida:
            if xc_functional != "lda_x+lda_c_pz":
                print(f"[INFO] Casida mode: overriding XC '{xc_functional}' → 'lda_x+lda_c_pz' "
                      "(Octopus 16.0 Casida kernel only supports LDA)", flush=True)
            xc_functional = "lda_x+lda_c_pz"

        # all_coords is used by all species_mode branches
        all_coords = custom_atoms if custom_atoms else (
            MOLECULES_2D.get(molecule, []) if dimensions == 2 else MOLECULES.get(molecule, [])
        )

        if species_mode == "formula":
            inp += "%Species\n"
            # softCoreAlpha: can be a float (global default) or dict of {symbol: alpha}
            # Also accept snake_case soft_core_alpha for MCP client compatibility
            # If not explicitly provided, pass None so formula_map uses its element-specific defaults
            _alpha_raw = config.get("softCoreAlpha", config.get("soft_core_alpha", None))
            if _alpha_raw is not None:
                # Normalize to dict format: float -> {"_default": float}
                if isinstance(_alpha_raw, (int, float)):
                    soft_core_alpha = {"_default": float(_alpha_raw)}
                else:
                    soft_core_alpha = _alpha_raw
                inp += _build_formula_species_block(_collect_element_symbols(all_coords), alpha_overrides=soft_core_alpha) + "\n"
            else:
                inp += _build_formula_species_block(_collect_element_symbols(all_coords), alpha_overrides=None) + "\n"
            inp += "%\n\n"
        elif species_mode == "builtin_standard":
            # FromScratch only for GS — TD/Casida need restart/ from converged GS
            if not (is_td or is_casida or is_vib):
                inp += "FromScratch = yes\n\n"
            # Match direct_test3 output convention; MOLECULES dict coords are in Bohr
            # NOTE: UnitsOutput=eV_Angstrom causes Octopus to interpret TDTimeStep
            # in hbar/eV instead of hbar/Hartree. The TDTimeStep compensation is
            # applied at the TDTimeStep write site below.
            inp += "UnitsOutput = eV_Angstrom\n\n"
            xc_functional = None
            _user_xc = config.get("xcFunctional", config.get("xc_functional", ""))
            if _user_xc and _user_xc not in ("lda_x+lda_c_pz", "lda_x", "LDA"):
                print(f"[WARN] builtin_standard PP uses its own LDA XC — ignoring xcFunctional='{_user_xc}'", flush=True)
            # N builtin_standard PP has LCAO orbital radii > 10.6 Å — cap them
            _lcao_cap_elements = {"N", "N_atom"}
            elem_symbols = _collect_element_symbols(all_coords)
            if any(e in _lcao_cap_elements for e in elem_symbols):
                lcao_max = float(config.get("lcaoMaximumOrbitalRadius", 20.0))
                inp += f"LCAOMaximumOrbitalRadius = {lcao_max}\n\n"
                print(f"[INFO] builtin_standard with N: capping LCAOMaximumOrbitalRadius={lcao_max}", flush=True)
        elif species_mode == "pseudo":
            if dimensions != 3:
                raise ValueError(
                    f"speciesMode='pseudo' requires Dimensions=3 (got {dimensions})."
                )
            pseudopotential_set = str(config.get("pseudopotentialSet", "standard") or "standard").strip()
            # PseudopotentialSet is only valid for built-in sets (e.g. "standard").
            # Non-standard sets (upf, oncv, etc.) use explicit %Species file paths.
            if pseudopotential_set.lower() == "standard":
                inp += f"PseudopotentialSet = {pseudopotential_set}\n\n"
            # Generate %Species block for PP mode — must precede %Coordinates
            inp += _build_pseudo_species_block(_collect_element_symbols(all_coords), pseudopotential_set) + "\n\n"
            # Auto-select XC to match pseudopotential set:
            #   'standard' (HGH, built-in) → LDA PP → keep LDA XC
            #   non-standard (ONCV, UPF files) → PBE PP → auto-select PBE XC
            _user_xc = config.get("xcFunctional", config.get("xc_functional", ""))
            if not _user_xc or _user_xc == "lda_x+lda_c_pz":
                is_standard_pp = pseudopotential_set.strip().lower() == "standard"
                if not is_standard_pp:
                    xc_functional = "gga_x_pbe+gga_c_pbe"
                    print(f"[INFO] speciesMode=pseudo with PseudopotentialSet='{pseudopotential_set}': "
                          "auto-selecting PBE XC to match non-standard pseudopotentials", flush=True)
                else:
                    print("[INFO] speciesMode=pseudo with PseudopotentialSet='standard': "
                          "keeping LDA XC (HGH PP set is LDA-based)", flush=True)
        elif species_mode == "all_electron":
            all_electron_type = str(config.get("allElectronType", "full_gaussian") or "full_gaussian").strip()
            valid_ae_types = {"full_delta", "full_gaussian", "full_anc"}
            if all_electron_type not in valid_ae_types:
                raise ValueError(
                    f"allElectronType='{all_electron_type}' not supported. "
                    f"Must be one of: {', '.join(sorted(valid_ae_types))}"
                )
            if str(config.get("pseudopotentialSet", "")).strip():
                raise ValueError("PseudopotentialSet is incompatible with speciesMode='all_electron'.")

            # Octopus default is PseudopotentialSet=standard; force none to activate true all-electron lane.
            inp += "PseudopotentialSet = none\n"
            inp += f"AllElectronType = {all_electron_type}\n"

            if "allElectronSigma" in config:
                inp += f"AllElectronSigma = {float(config['allElectronSigma'])}\n"
            if "allElectronANCParam" in config:
                inp += f"AllElectronANCParam = {config['allElectronANCParam']}\n"

            inp += "\n"
        else:
            raise ValueError(
                f"Unsupported speciesMode='{species_mode}'. Must be one of: 'builtin_standard', 'formula', 'pseudo', 'all_electron'."
            )

        inp += "%Coordinates\n"
        inp += coords_str + "\n"
        inp += "%\n\n"

        # Explicitly disable external PSF requirement
        inp += "LCAOReadWeights = no\n\n"

        # SCF convergence tuning — especially important for custom-potential multi-atom geometries
        # where LCAO initial guess is unavailable and Broyden can oscillate.
        # Smaller Mixing (0.1 vs default 0.3) + more history steps = more stable convergence.
        max_scf = int(config.get("octopusMaxScfIterations", os.environ.get("OCTOPUS_MAX_SCF_ITERATIONS", "200")))
        if bool(config.get("fastPath", False)):
            fast_cap = int(os.environ.get("OCTOPUS_FAST_MAX_SCF_ITERATIONS", "80"))
            max_scf = min(max_scf, max(10, fast_cap))

        inp += "Mixing = 0.1\n"
        inp += "MixNumberSteps = 16\n"
        # Octopus uses MaximumIter (not MaxSCFIterations)
        inp += f"MaximumIter = {max_scf}\n"
        # Octopus convergence criteria: ConvAbsDens / ConvRelDens (SCFTolerance is not a valid variable)
        scf_tol_raw = config.get("SCFTolerance", config.get("scfTolerance"))
        if scf_tol_raw is not None:
            try:
                scf_tol = float(scf_tol_raw)
                inp += f"ConvAbsDens = {scf_tol:.0e}\n"
                inp += f"ConvRelDens = {scf_tol:.0e}\n"
            except (ValueError, TypeError):
                inp += "ConvAbsDens = 1e-6\n"
                inp += "ConvRelDens = 1e-6\n"
        else:
            inp += "ConvAbsDens = 1e-6\n"
            inp += "ConvRelDens = 1e-6\n"

        # Periodic system support: LatticeVectors + KPoints
        # _CRYSTAL_DEFAULT_PD: fallback if the UI sends no periodicDimensions for a known crystal.
        # User's explicit config["periodicDimensions"] always takes precedence so they can simulate
        # e.g. a 1D Si waveguide (PeriodicDimensions=1) instead of bulk (3).
        _CRYSTAL_DEFAULT_PD = {"Si": 3, "Al2O3": 3}
        _user_pd = config.get("periodicDimensions")
        if _user_pd is not None:
            if isinstance(_user_pd, str):
                pd_key = _user_pd.strip().lower()
                if pd_key in {"", "none", "off", "isolated", "false", "no", "0"}:
                    periodic_dims = 0
                elif pd_key in {"x", "1d", "1"}:
                    periodic_dims = 1
                elif pd_key in {"xy", "2d", "2"}:
                    periodic_dims = 2
                elif pd_key in {"xyz", "3d", "3"}:
                    periodic_dims = 3
                else:
                    periodic_dims = int(_user_pd)
            else:
                periodic_dims = int(_user_pd)
        else:
            periodic_dims = _CRYSTAL_DEFAULT_PD.get(molecule, 0)
        if periodic_dims > 0:
            inp += f"PeriodicDimensions = {periodic_dims}\n"
            # Mixed periodicity (1D or 2D periodic + remaining finite directions with sphere bc)
            # requires ExperimentalFeatures = yes in Octopus ≥ 13
            if periodic_dims < dimensions:
                inp += "ExperimentalFeatures = yes\n"
            # Use provided latticeVectors or built-in defaults
            lv = config.get("latticeVectors")
            if not lv:
                # Crystal-specific 3D primitive vectors (only for pd==3)
                if periodic_dims == 3 and molecule == "Si":
                    lv = [[0.0, 5.132, 5.132], [5.132, 0.0, 5.132], [5.132, 5.132, 0.0]]
                elif periodic_dims == 3 and molecule == "Al2O3":
                    lv = [[5.128, -2.564, 0.0], [0.0, 4.440, 0.0], [0.0, 0.0, 13.900]]
                elif periodic_dims == 2 and molecule == "Al2O3":
                    # Al₂O₃ (0001) slab: in-plane vectors from the hexagonal cell
                    lv = [[5.128, -2.564, 0.0], [0.0, 4.440, 0.0]]
                elif periodic_dims == 2 and molecule == "Si":
                    # Si(001) surface: a/√2 ≈ 7.255 Bohr in-plane, user can override via latticeA/B
                    a = float(config.get("latticeA", 7.255))
                    b = float(config.get("latticeB", a))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0]]
                elif periodic_dims == 1:
                    _crystal_a1d = {"Si": 10.263, "Al2O3": 5.128}
                    a_def = _crystal_a1d.get(molecule, 10.0)
                    lv = [[float(config.get("latticeA", a_def)), 0.0, 0.0]]
                elif periodic_dims == 2:
                    a = float(config.get("latticeA", 10.0))
                    b = float(config.get("latticeB", 10.0))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0]]
                else:
                    a = float(config.get("latticeA", 10.0))
                    b = float(config.get("latticeB", a))
                    c = float(config.get("latticeC", a))
                    lv = [[a, 0.0, 0.0], [0.0, b, 0.0], [0.0, 0.0, c]]
            inp += "%LatticeVectors\n"
            for v in lv:
                inp += f"  {v[0]} | {v[1]} | {v[2]}\n"
            inp += "%\n"
            kgrid = config.get("kpointsGrid", "2 2 2")
            k_parts = kgrid.replace(',', ' ').split()
            # For mixed-periodicity systems, only fill k-points along periodic axes;
            # set k=1 for all finite (non-periodic) directions to avoid spurious bands.
            if periodic_dims == 1:
                k_parts = [k_parts[0], "1", "1"]
            elif periodic_dims == 2:
                k_parts = [k_parts[0], k_parts[1] if len(k_parts) > 1 else "2", "1"]
            inp += "%KPointsGrid\n"
            inp += f"  {'  |  '.join(k_parts[:3])}\n"
            inp += "%\n"
            inp += "\n"

        mixing_scheme = config.get("mixingScheme", config.get("mixing_scheme", "broyden"))
        spin = config.get("spinComponents", config.get("spin_components", "unpolarized"))
        eigensolver = str(config.get("octopusEigenSolver", config.get("eigenSolver", "")) or "").strip()
        # Ground-state defaults to 1 extra state (enough for most atoms/molecules);
        # TD/spectra mode keeps a higher default since more unoccupied states are needed.
        default_extra_states = 4 if is_td else 1
        extra_states_3d = int(config.get("octopusExtraStates", config.get("extra_states", config.get("extraStates", default_extra_states))))
        # Charged system support: ExtraElectrons (positive = extra electrons, negative = fewer electrons)
        # Also accept netCharge as convenience: NetCharge=+1 means cation (remove 1 electron → ExtraElectrons=-1)
        extra_elec = config.get("extraElectrons", config.get("ExtraElectrons", None))
        if extra_elec is None:
            net_charge = config.get("netCharge", config.get("NetCharge", 0))
            if net_charge != 0:
                extra_elec = -int(net_charge)
        inp += f"ExtraStates = {extra_states_3d}\n"
        if extra_elec is not None and int(extra_elec) != 0:
            inp += f"ExtraElectrons = {int(extra_elec)}\n"

        # OEP/HF functionals use special Octopus variables (not libxc strings)
        # hartree_fock: use TheoryLevel = hartree_fock (NOT XCFunctional = hartree_fock)
        # exx: pure Hartree-Fock exact exchange, used with TheoryLevel = hartree_fock
        # oep_kli / oep_slater: OEP-based approximations
        _OEP_MAP = {
            "hartree_fock": None,  # handled via TheoryLevel below
            "exx":         ("exx", ""),
            "oep_kli":     ("lda_x", "OEPLevel = kli"),
            "oep_slater":  ("lda_x", "OEPLevel = slater"),
        }
        if xc_functional == "hartree_fock":
            # Pure Hartree-Fock: set TheoryLevel, skip XCFunctional line for this case
            inp += "TheoryLevel = hartree_fock\n"
        elif xc_functional in _OEP_MAP:
            _xc_mapped, _oep_line = _OEP_MAP[xc_functional]
            inp += f"XCFunctional = {_xc_mapped}\n"
            if _oep_line:
                inp += f"{_oep_line}\n"
        elif xc_functional is not None:
            inp += f"XCFunctional = {xc_functional}\n"
        if xc_functional is not None:
            inp += f"MixingScheme = {mixing_scheme}\n"
            if spin != "unpolarized":
                inp += f"SpinComponents = {spin}\n"
        if eigensolver:
            inp += f"EigenSolver = {eigensolver}\n"

        # Non-uniform / curvilinear mesh options
        deriv_order = int(config.get("derivativesOrder", 4))
        if deriv_order != 4:
            inp += f"DerivativesOrder = {deriv_order}\n"
        curv_method = config.get("curvMethod", "uniform")
        if curv_method == "gygi":
            inp += "CurvMethod = gygi\n"
            inp += f"CurvGygiA = {float(config.get('curvGygiAlpha', 2.0))}\n"
        if config.get("doubleGrid", False):
            inp += "DoubleGrid = yes\n"

        if is_td:
            # TDDFT Delta-kick + output
            # Octopus 16+: use TDDeltaStrength/TDDeltaKickTime instead of
            # the deprecated %TDFunctions/%TDExternalFields tdf_delta syntax
            steps = config.get("octopusTdSteps", config.get("tdSteps", config.get("TDMaxSteps", 5000)))
            td_dt_raw = float(config.get("octopusTdTimeStep", config.get("TDTimeStep", 0.05)))
            propagator = config.get("octopusPropagator", "aetrs")
            excitation_type = config.get("tdExcitationType", "delta")
            polarization = int(config.get("tdPolarization", 1))  # 1=x, 2=y, 3=z
            amplitude = float(config.get("tdFieldAmplitude", 0.01))

            # UnitsOutput=eV_Angstrom makes Octopus interpret TDTimeStep in hbar/eV,
            # but user supplies atomic units (hbar/Hartree). Convert: dt_input = dt_au / Ha_to_eV
            td_dt_for_inp = td_dt_raw / 27.2114

            inp += f"TDPropagator = {propagator}\n"
            inp += f"TDMaxSteps = {steps}\n"
            inp += f"TDTimeStep = {td_dt_for_inp}\n"

            if excitation_type == "delta":
                # Broadband delta-kick (best for optical spectra)
                inp += f"TDDeltaStrength = {amplitude}\n"
                inp += "TDDeltaKickTime = 0.0\n"
                inp += f"TDPolarizationDirection = {polarization}\n\n"

                # Free electron probe alongside delta kick
                # Octopus 16.3 electric_field format:
                #   type | pol_x | pol_y | pol_z | amplitude | "func_name"  (name LAST)
                if str(config.get("feProbeEnabled", False)).lower() not in ("false", "0", "", "none"):
                    fe_v     = float(config.get("feProbeVelocity", 0.5))
                    fe_y0    = float(config.get("feProbeY0", 2.0))
                    fe_z0    = float(config.get("feProbeZ0", 0.0))
                    fe_q     = float(config.get("feProbeCharge", -1.0))
                    c_au     = 137.036
                    v_au     = fe_v * c_au
                    t_center = float(steps) * float(td_dt_raw) / 2.0
                    neg_q    = -fe_q  # = +1 for electron (q=-1)
                    r3 = (f"(({v_au:.4f}*(t-{t_center:.3f}))^2"
                          f"+{fe_y0:.4f}^2+{fe_z0:.4f}^2+0.01)^1.5")
                    Ex = f"({neg_q:.6f}*({v_au:.4f}*(t-{t_center:.3f})))/({r3})"
                    Ey = f"({neg_q:.6f}*{fe_y0:.6f})/({r3})"
                    inp += "# ── Free Electron Probe (Coulomb E-field at molecule) ──\n"
                    inp += "%TDExternalFields\n"
                    inp += '  electric_field | 1 | 0 | 0 | 1.0 | "probe_x"\n'
                    inp += '  electric_field | 0 | 1 | 0 | 1.0 | "probe_y"\n'
                    inp += "%\n"
                    inp += "%TDFunctions\n"
                    inp += f'  "probe_x" | tdf_from_expr | "{Ex}"\n'
                    inp += f'  "probe_y" | tdf_from_expr | "{Ey}"\n'
                    inp += "%\n\n"
            else:
                # External field via %TDExternalFields + %TDFunctions
                # Octopus 16.3 electric_field format:
                #   type | pol_x | pol_y | pol_z | amplitude | "func_name"  (name LAST)
                pol_vec = {1: "1 | 0 | 0", 2: "0 | 1 | 0", 3: "0 | 0 | 1"}[polarization]
                ext_fields = [f'  electric_field | {pol_vec} | {amplitude} | "td_pulse"']
                td_funcs: list = []
                if excitation_type == "gaussian":
                    sigma = float(config.get("tdGaussianSigma", 5.0))
                    t0    = float(config.get("tdGaussianT0",   10.0))
                    # tdf_gaussian: height | center | width  (height=1 → amplitude controlled by TDExternalFields)
                    td_funcs.append(f'  "td_pulse" | tdf_gaussian | 1.0 | {t0} | {sigma}')
                elif excitation_type == "sin":
                    freq = float(config.get("tdSinFrequency", 0.057))
                    td_funcs.append(f'  "td_pulse" | tdf_from_expr | "sin({freq}*t)"')
                elif excitation_type == "continuous_wave":
                    freq = float(config.get("tdSinFrequency", 0.057))
                    td_funcs.append(f'  "td_pulse" | tdf_from_expr | "cos({freq}*t)"')

                # Append probe if enabled — same %TDExternalFields block
                if str(config.get("feProbeEnabled", False)).lower() not in ("false", "0", "", "none"):
                    fe_v     = float(config.get("feProbeVelocity", 0.5))
                    fe_y0    = float(config.get("feProbeY0", 2.0))
                    fe_z0    = float(config.get("feProbeZ0", 0.0))
                    fe_q     = float(config.get("feProbeCharge", -1.0))
                    c_au     = 137.036
                    v_au     = fe_v * c_au
                    t_center = float(steps) * float(td_dt_raw) / 2.0
                    neg_q    = -fe_q
                    r3 = (f"(({v_au:.4f}*(t-{t_center:.3f}))^2"
                          f"+{fe_y0:.4f}^2+{fe_z0:.4f}^2+0.01)^1.5")
                    Ex = f"({neg_q:.6f}*({v_au:.4f}*(t-{t_center:.3f})))/({r3})"
                    Ey = f"({neg_q:.6f}*{fe_y0:.6f})/({r3})"
                    ext_fields.append('  electric_field | 1 | 0 | 0 | 1.0 | "probe_x"')
                    ext_fields.append('  electric_field | 0 | 1 | 0 | 1.0 | "probe_y"')
                    td_funcs.append(f'  "probe_x" | tdf_from_expr | "{Ex}"')
                    td_funcs.append(f'  "probe_y" | tdf_from_expr | "{Ey}"')

                inp += "%TDExternalFields\n"
                inp += "\n".join(ext_fields) + "\n"
                inp += "%\n"
                inp += "%TDFunctions\n"
                inp += "\n".join(td_funcs) + "\n"
                inp += "%\n\n"

            inp += "%TDOutput\n"
            inp += "  multipoles\n"
            inp += "  energy\n"
            inp += "%\n"

            # Spectrum post-processing parameters (used by oct-propagation_spectrum)
            if excitation_type == "delta":
                inp += "PropagationSpectrumMaxEnergy = 0.735\n"   # 20 eV in Ha
                inp += "PropagationSpectrumEnergyStep = 0.001\n" # ~0.027 eV
                inp += "PropagationSpectrumBroadening = 0.005\n"  # ~0.14 eV Lorentzian
        elif is_casida:
            # Casida linear response — reads restart GS, computes excitation energies.
            # Primary method for finite-molecule optical spectra (Octopus Tutorial 16).
            casida_states = str(config.get("casidaKohnShamStates", "1-8"))
            inp += f"CasidaKohnShamStates = \"{casida_states}\"\n"
            casida_trans_dens = int(config.get("casidaTransitionDensities", 0))
            if casida_trans_dens > 0:
                inp += f"CasidaTransitionDensities = {casida_trans_dens}\n"
            # Need enough unoccupied states to cover CasidaKohnShamStates range
            _user_set_extra = any(k in config for k in (
                "octopusExtraStates", "extra_states", "extraStates"))
            if not _user_set_extra:
                # Parse max KS state from range (e.g. "1-16" → 16)
                _casida_parts = casida_states.replace('"', '').strip().split("-")
                _max_ks = int(_casida_parts[-1]) if _casida_parts else 8
                # H2O has 5 occupied states; ExtraStates = max_ks - 5 (minimum)
                _min_extra = max(8, _max_ks - 3)  # conservative: assume ~3-5 occupied
                extra_states_3d = max(extra_states_3d, _min_extra)
            inp += f"ExtraStates = {extra_states_3d}\n"
            inp += "%Output\n"
            inp += "  wfs\n"
            inp += "  eigenvalues\n"
            inp += "%\n"
            inp += "OutputFormat = axis_x\n"
        elif is_vib:
            # Vibrational modes — finite differences of forces
            inp += "ResponseMethod = finite_differences\n"
            inp += "CalcInfrared = yes\n"
            _vib_disp = float(config.get("vibDisplacement", 0.01))
            inp += f"Displacement = {_vib_disp}\n"
            inp += f"ExtraStates = {extra_states_3d}\n"
        else:
            # Ground State: output BOTH axis slices (*.y=0,z=0) AND full 3D cube files
            target_calc_mode = str(config.get("calcMode", "gs")).strip().lower()
            if target_calc_mode == "td":
                # TD absorption needs enough unoccupied states for a meaningful spectrum.
                # Only apply the floor when the user hasn't explicitly set extraStates —
                # small molecules (H2O, CH4) may not converge with 12 extra states
                # when LCAO AOs < total states.
                _user_set_extra = any(k in config for k in (
                    "octopusExtraStates", "extra_states", "extraStates"))
                if not _user_set_extra:
                    extra_states_3d = max(extra_states_3d, 8)
            inp += f"ExtraStates = {extra_states_3d}\n"
            inp += "%Output\n"
            inp += "  wfs\n"
            inp += "  density\n"
            inp += "  potential\n"   # v0 + vh + vxc + vks files (all components)
            inp += "  eigenvalues\n"
            inp += "  dos\n"
            inp += "  elf\n"         # Electron Localization Function
            if periodic_dims > 0:
                inp += "  stress\n"  # Stress tensor (periodic systems only)
            inp += "%\n"
            # axis_x: 1D line-scan files (fast, for wavefunction 1D plots)
            # cube: full 3D volumetric data (for proper 2D heatmaps and 3D isosurfaces)
            inp += "OutputFormat = cube + axis_x\n"

        return inp

    # Original 1D local physics configuration behavior
    potential_type = config.get("potentialType", "Harmonic")
    grid_spacing = config.get("octopusSpacing", config.get("gridSpacing", 0.1))
    spatial_extent = config.get("octopusRadius", config.get("spatialRange", 10.0) / 2.0)
    dimensions = 1 if config.get("octopusDimensions", config.get("dimensionality", "1D")) == "1D" else (2 if config.get("octopusDimensions", config.get("dimensionality")) == "2D" else 3)
    extra_states = max(0, config.get("octopusExtraStates", config.get("extraStates", 3)))

    if potential_type == "Harmonic":
        formula = '"0.5*x^2"'
    elif potential_type == "FiniteWell":
        depth = abs(config.get("potentialStrength", 10.0))
        hw = config.get("wellWidth", 1.0) / 2.0
        formula = f'"-{depth}*step({hw}-abs(x))"'
    elif potential_type == "InfiniteWell":
        hw = config.get("wellWidth", 1.0) / 2.0
        formula = f'"-1000*step({hw}-abs(x))"'
    elif potential_type == "Coulomb":
        Z = abs(config.get("potentialStrength", 1.0))
        formula = f'"-{Z}/sqrt(x^2+0.01)"'  # Regularized Coulomb
    else:
        formula = '"0"'

    return octopus_inp_template.render(
        dimensions=dimensions,
        grid_spacing=grid_spacing,
        radius=spatial_extent,
        extra_states=extra_states,
        potential_formula=formula,
    )


def parse_octopus_info(info_path: str) -> dict:
    """Parse Octopus static/info file for eigenvalues and energies."""
    result = {"eigenvalues": [], "eigenvalue_entries": [], "total_energy": None, "converged": False, "scf_iterations": 0}

    if not os.path.exists(info_path):
        return result

    with open(info_path, "r") as f:
        content = f.read()

    # Check convergence — handle multiple Octopus convergence messages
    # Octopus 16 writes:
    #   - "SCF converged in N iterations" (full convergence)
    #   - "SCF *not* converged!" (hit max iterations without meeting tolerance)
    #   - "restarting mixing" (Octopus auto-recovered and continues)
    m = re.search(r"SCF converged in\s+(\d+)\s+iterations", content)
    if m:
        result["converged"] = True
        result["scf_iterations"] = int(m.group(1))
    elif re.search(r"SCF\s+\*not\*\s+converged", content, re.IGNORECASE):
        # Hit max iterations but may have achieved reasonable accuracy
        # Parse final energy and density residuals to assess actual convergence
        m_nc = re.search(r"SCF\s+did\s+not\s+converge\s+in\s+(\d+)\s+iterations", content, re.IGNORECASE)
        result["scf_iterations"] = int(m_nc.group(1)) if m_nc else 0
        # Check if abs_energy and abs_dens from Convergence section are within reasonable tolerance
        abs_energy_match = re.search(r"abs_energy\s*=\s*([+-]?\d+\.\d+(?:[eE][-+]?\d+)?)", content)
        abs_dens_match = re.search(r"abs_dens\s*=\s*([+-]?\d+\.\d+(?:[eE][-+]?\d+)?)", content)
        rel_energy_match = re.search(r"rel_energy\s*=\s*([+-]?\d+\.\d+(?:[eE][-+]?\d+)?)\s*\(", content)
        if abs_energy_match and abs_dens_match:
            abs_energy = float(abs_energy_match.group(1))
            abs_dens = float(abs_dens_match.group(1))
            rel_energy = float(rel_energy_match.group(1)) if rel_energy_match else None
            # Soft convergence: allow near-converged runs that terminated at max iterations.
            # The SCF is oscillating (Broyden) but the energy is physically meaningful.
            # Thresholds: rel_energy <= 2e-3 (0.1% relative, ~0.03 eV for N atom),
            # abs_energy <= 5e-2 (50 meV), density drift <= 2e-1.
            soft_ok = (rel_energy is not None and rel_energy <= 2e-3) or abs_energy <= 5e-2
            if soft_ok and abs_dens <= 2e-1:
                result["converged"] = True
            else:
                result["converged"] = False
        else:
            result["converged"] = False
    else:
        m_nc = re.search(r"SCF\s+did\s+not\s+converge\s+in\s+(\d+)\s+iterations", content, re.IGNORECASE)
        if m_nc:
            result["converged"] = False
            result["scf_iterations"] = int(m_nc.group(1))

    # Parse eigenvalues block - handle scientific notation and flexible whitespace
    # Octopus 16.3 might use different header formats
    header_pattern = re.compile(r"#st\s+Spin\s+Eigenvalue.*Occupation")
    # Also handle simpler headers or variations
    simple_header = re.compile(r"State\s+Energy\s+Occupation")
    alternate_header = re.compile(r"Eigenvalues\s+\[H\]")
    
    lines = content.split("\n")
    in_ev_block = False
    for line in lines:
        if header_pattern.search(line) or simple_header.search(line) or alternate_header.search(line):
            in_ev_block = True
            continue
        if in_ev_block:
            stripped = line.strip()
            # Stop if we hit Energy block or an empty line
            if not stripped or stripped.startswith("Energy") or stripped.startswith("---"):
                break
            parts = stripped.split()
            # Format: #st Spin Eigenvalue Occupation
            if len(parts) >= 3:
                try:
                    val_match = re.findall(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?", line)
                    if val_match:
                        ev = float(val_match[0])
                        result["eigenvalues"].append(ev)
                        # Try to parse occupation (last numeric column)
                        try:
                            occ = float(val_match[-1]) if len(val_match) >= 2 else 2.0
                        except (ValueError, IndexError):
                            occ = 2.0
                        state_idx = int(parts[0]) if parts[0].isdigit() else len(result["eigenvalue_entries"]) + 1
                        spin_label = parts[1] if len(parts) > 2 and not parts[1].replace('.','').replace('-','').replace('e','').replace('E','').replace('+','').isdigit() else "up"
                        result["eigenvalue_entries"].append({
                            "state": state_idx,
                            "spin": spin_label,
                            "eigenvalue_hartree": ev,
                            "occupation": occ,
                        })
                except (ValueError, IndexError):
                    pass

    # Parse total energy
    m = re.search(r"Total\s+=\s+([-\d.]+)", content)
    if m:
        result["total_energy"] = float(m.group(1))

    result["engine"] = "octopus-16.0"
    return result

def get_atom_positions(molecule: str, dimensions: int = 3, custom_atoms: list = None) -> list:
    """Return list of {symbol, x, y, z} for frontend geometry visualization."""
    import re as _re
    if custom_atoms:
        return [{"symbol": a["symbol"], "x": float(a.get("x", 0)),
                 "y": float(a.get("y", 0)), "z": float(a.get("z", 0))} for a in custom_atoms]
    lines = (MOLECULES_2D if dimensions == 2 else MOLECULES).get(molecule, [])
    atoms = []
    for line in lines:
        parts = [p.strip().strip("'") for p in line.split("|")]
        if len(parts) < 2:
            continue
        try:
            sym = parts[0]
            coords = [float(p) for p in parts[1:4]]
            while len(coords) < 3:
                coords.append(0.0)
            atoms.append({"symbol": sym, "x": coords[0], "y": coords[1], "z": coords[2]})
        except ValueError:
            pass
    return atoms

def parse_octopus_wfs_1d(static_dir: str) -> dict:
    """Parse 1D text files (vks and wf-st) into arrays."""
    import glob
    result = {"x_grid": [], "potential": [], "wavefunctions": []}
    if not os.path.exists(static_dir):
        return result
        
    # Read potential
    vks_path = os.path.join(static_dir, "vks.y=0,z=0")
    if os.path.exists(vks_path):
        with open(vks_path, "r") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        x = float(parts[0])
                        v = float(parts[1])
                        result["x_grid"].append(x)
                        result["potential"].append(v)
                    except ValueError:
                        pass

    # Read individual potential components (v0=external, vh=Hartree, vxc=XC)
    for _key, _fname in [("v0", "v0.y=0,z=0"), ("vh", "vh.y=0,z=0"), ("vxc", "vxc.y=0,z=0")]:
        _fpath = os.path.join(static_dir, _fname)
        if os.path.exists(_fpath):
            _data: list = []
            with open(_fpath) as _fh:
                for _line in _fh:
                    if _line.startswith("#"):
                        continue
                    _parts = _line.split()
                    if len(_parts) >= 2:
                        try:
                            _data.append(float(_parts[1]))
                        except ValueError:
                            pass
            if _data:
                result[_key] = _data
    
    # Read wavefunctions
    wf_files = sorted(glob.glob(os.path.join(static_dir, "wf-st*.y=0,z=0")))
    for wf_file in wf_files:
        wf_data = []
        with open(wf_file, "r") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # parts[1] is Re, parts[2] is Im (usually 0 for bound state string)
                        val = float(parts[1])
                        wf_data.append(val)
                    except ValueError:
                        pass
        if wf_data:
            result["wavefunctions"].append(wf_data)

    # Read electron density 1D slice
    density_path = os.path.join(static_dir, "density.y=0,z=0")
    if os.path.exists(density_path):
        density_data = []
        with open(density_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        density_data.append(float(parts[1]))
                    except ValueError:
                        pass
        if density_data:
            result["density"] = density_data

    return result

def parse_octopus_cross_section(work_dir: str) -> dict:
    """Parse cross_section_vector from oct-propagation_spectrum.

    Octopus 16 format (5 columns). Units depend on UnitsOutput:
      a.u. (default): Energy[Hartree], sigma(1-3)[Bohr²], S(ω)[1/Hartree]
      eV_Angstrom:    Energy[eV],      sigma(1-3)[Å²],    S(ω)[1/eV]

    When eV output, sigma columns are already cross-section in Å² — read directly.
    When a.u. output, convert via σ_abs = (2π²/c) × S(ω) [Bohr²] then × 0.280032.
    """
    HARTREE_TO_EV = 27.2114
    C_AU = 137.035999084
    CONV_FACTOR = 2 * math.pi**2 / C_AU
    BOHR2_TO_ANG2 = 0.280032

    cs_path = os.path.join(work_dir, "cross_section_vector")
    result = {"energy_ev": [], "cross_section": []}

    if not os.path.exists(cs_path):
        return result

    units_are_ev = False
    with open(cs_path, "r") as f:
        for line in f:
            if '[eV]' in line and '[A^2]' in line:
                units_are_ev = True
                continue
            if '[Hartree]' in line:
                units_are_ev = False
                continue
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 5 or any(v.lower() == 'nan' for v in parts):
                continue
            try:
                if units_are_ev:
                    energy_ev = float(parts[0])
                    sigma_ang2 = float(parts[1])
                else:
                    energy_ha = float(parts[0])
                    strength = float(parts[4])
                    if strength <= 0:
                        continue
                    sigma_ang2 = CONV_FACTOR * strength * BOHR2_TO_ANG2
                    energy_ev = energy_ha * HARTREE_TO_EV
                if sigma_ang2 > 0 and energy_ev > 0.01:
                    result["energy_ev"].append(round(energy_ev, 6))
                    result["cross_section"].append(round(sigma_ang2, 10))
            except (ValueError, IndexError):
                pass
    return result


HARTREE_TO_EV = 27.211386245988


def parse_octopus_casida(work_dir: str) -> dict:
    """Parse Casida linear response excitation energies.

    Octopus 16 writes casida/ directory in work_dir with either:
      casida/casida — summary: idx, E[eV], <x>[A], <y>[A], <z>[A], <f>
      casida/eps_diff — detailed: From, To, E[H], <x>[b], <y>[b], <z>[b], <f>
    Returns a dict with 'excitations' (list of {energy_ev, oscillator_strength})
    and flat arrays 'energies_ev' / 'oscillator_strengths'.
    """
    HToEV = HARTREE_TO_EV
    candidates = [
        os.path.join(work_dir, "casida", "casida"),
        os.path.join(work_dir, "static", "casida"),
        os.path.join(work_dir, "casida", "eps_diff"),
        os.path.join(work_dir, "static", "eps_diff"),
    ]
    casida_path = ""
    for p in candidates:
        if os.path.exists(p):
            casida_path = p
            break

    result: dict = {"excitations": [], "energies_ev": [], "oscillator_strengths": []}
    if not casida_path:
        return result

    is_eps_diff = os.path.basename(casida_path) == "eps_diff"

    # Detect energy unit from header line
    _energy_unit_is_hartree = True  # default: assume Hartree
    with open(casida_path, "r") as _hf:
        for _hl in _hf:
            if "E [eV]" in _hl:
                _energy_unit_is_hartree = False
                break
            elif "E [H]" in _hl:
                _energy_unit_is_hartree = True
                break

    with open(casida_path, "r") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith("#"):
                continue
            # Skip header lines
            if "E [eV]" in line or "<f>" in line or "E [H]" in line or "From  To" in line:
                continue
            parts = line_stripped.split()
            if len(parts) >= 6:
                try:
                    if is_eps_diff:
                        # Format: From To E[H] <x>[b] <y>[b] <z>[b] <f>
                        energy_ha = float(parts[2])
                        energy = energy_ha * HToEV
                        osc = float(parts[6])
                    else:
                        # Format: idx E[unit] <x>[b] <y>[b] <z>[b] <f>
                        _raw_e = float(parts[1])
                        energy = _raw_e * HToEV if _energy_unit_is_hartree else _raw_e
                        osc = float(parts[5])
                    result["excitations"].append({
                        "energy_ev": round(energy, 6),
                        "oscillator_strength": round(osc, 8),
                    })
                    result["energies_ev"].append(round(energy, 6))
                    result["oscillator_strengths"].append(round(osc, 8))
                except (ValueError, IndexError):
                    pass
    return result


def parse_octopus_vib_modes(work_dir: str) -> dict:
    """Parse vibrational frequencies and IR intensities from Octopus vib_modes output.

    Octopus writes:
      vib_modes/normal_frequencies_lr — # Mode  Frequency [cm-1]
      vib_modes/infrared — IR intensities per mode (if CalcInfrared=yes)
    Returns dict with modes[], frequencies_cm[], ir_intensities[].
    """
    import re
    result: dict = {"modes": [], "frequencies_cm": [], "ir_intensities": []}

    # Parse frequencies
    freq_path = os.path.join(work_dir, "vib_modes", "normal_frequencies_lr")
    if not os.path.exists(freq_path):
        # Try alternate locations
        for alt in [
            os.path.join(work_dir, "vib_modes", "normal_frequencies_fd"),
            os.path.join(work_dir, "vib_modes", "normal_frequencies"),
            os.path.join(work_dir, "static", "normal_frequencies_lr"),
        ]:
            if os.path.exists(alt):
                freq_path = alt
                break

    if not os.path.exists(freq_path):
        print(f"[WARN] vibrational frequencies file not found in {work_dir}")
        return result

    with open(freq_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    mode_idx = int(parts[0])
                    freq_cm = float(parts[1])
                    result["modes"].append(mode_idx)
                    result["frequencies_cm"].append(freq_cm)
                except (ValueError, IndexError):
                    pass

    # Parse IR intensities
    ir_path = os.path.join(work_dir, "vib_modes", "infrared")
    if os.path.exists(ir_path):
        ir_values = []
        with open(ir_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        # Format varies: mode intensity or mode dx dy dz intensity
                        ir_values.append(abs(float(parts[-1])))
                    except (ValueError, IndexError):
                        pass
        # Match IR values to modes (may be fewer if some modes are translations/rotations)
        for i in range(min(len(ir_values), len(result["frequencies_cm"]))):
            result["ir_intensities"].append(round(ir_values[i], 6))
        # Pad missing IR intensities with zeros
        while len(result["ir_intensities"]) < len(result["frequencies_cm"]):
            result["ir_intensities"].append(0.0)

    n_modes = len(result["frequencies_cm"])
    n_ir = len(result["ir_intensities"])
    print(f"[DEBUG] parse_octopus_vib_modes: {n_modes} frequencies, {n_ir} IR intensities")
    return result


def parse_octopus_convergence(static_dir: str) -> dict:
    """Parse static/convergence for SCF energy diff per iteration."""
    path = os.path.join(static_dir, "convergence")
    result: dict = {"iterations": [], "energy_diff": []}
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        result["iterations"].append(int(float(parts[0])))
                        result["energy_diff"].append(abs(float(parts[2])))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[WARN] parse_octopus_convergence: {e}")
    return result


def parse_octopus_dos(static_dir: str) -> dict:
    """Parse static/total-dos.dat (or equivalent) for Density of States."""
    import glob as _glob
    HARTREE_TO_EV = 27.2114
    result: dict = {"energy_ev": [], "dos": []}
    candidates = _glob.glob(os.path.join(static_dir, "*dos*"))
    if not candidates:
        return result
    dos_path = sorted(candidates)[0]
    try:
        with open(dos_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        result["energy_ev"].append(float(parts[0]) * HARTREE_TO_EV)
                        result["dos"].append(float(parts[1]))
                    except ValueError:
                        pass
    except Exception as e:
        print(f"[WARN] parse_octopus_dos: {e}")
    return result


def parse_go_min_xyz(work_dir: str) -> dict:
    """Parse min.xyz (optimized geometry from GO calculation).

    Returns optimized geometry data or empty dict if file not found.
    """
    min_xyz_path = os.path.join(work_dir, "min.xyz")
    result: dict = {"found": False, "num_atoms": 0, "atoms": [], "comment": ""}
    if not os.path.exists(min_xyz_path):
        return result
    try:
        with open(min_xyz_path, "r") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return result
        num_atoms = int(lines[0].strip())
        comment = lines[1].strip()
        result["found"] = True
        result["num_atoms"] = num_atoms
        result["comment"] = comment
        for i in range(2, min(2 + num_atoms, len(lines))):
            parts = lines[i].split()
            if len(parts) >= 4:
                result["atoms"].append({
                    "symbol": parts[0],
                    "x": float(parts[1]),
                    "y": float(parts[2]),
                    "z": float(parts[3]),
                })
    except Exception as e:
        print(f"[WARN] parse_go_min_xyz: {e}")
    return result


def parse_go_convergence(work_dir: str) -> dict:
    """Parse go/convergence for geometry optimization trajectory.

    Columns: iter | energy | max_force | ...
    Returns forces by iteration.
    """
    go_conv_path = os.path.join(work_dir, "go", "convergence")
    result: dict = {"found": False, "iterations": [], "energy": [], "max_force": []}
    if not os.path.exists(go_conv_path):
        return result
    try:
        with open(go_conv_path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        result["iterations"].append(int(parts[0]))
                        result["energy"].append(float(parts[1]))
                        result["max_force"].append(float(parts[2]))
                    except ValueError:
                        pass
        if result["iterations"]:
            result["found"] = True
    except Exception as e:
        print(f"[WARN] parse_go_convergence: {e}")
    return result


def parse_td_dipole(td_dir: str) -> dict:
    """Parse td.general/multipoles for dipole moment vs time.

    Octopus multipoles file format (lmax=1, 3D):
      col 0: iter  col 1: time  col 2: electronic_charge  col 3: <x>  col 4: <y>  col 5: <z>

    Truncates at first NaN/Inf to avoid FFT corruption from diverged propagation.
    """
    path = os.path.join(td_dir, "multipoles")
    result: dict = {"time": [], "dipole_x": [], "dipole_y": [], "dipole_z": []}
    if not os.path.exists(path):
        return result
    try:
        import math
        with open(path, "r") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        tv = float(parts[1])
                        dx = float(parts[3])
                        dy = float(parts[4])
                        dz = float(parts[5])
                        # Stop at first NaN/Inf — propagation diverged
                        if not (math.isfinite(tv) and math.isfinite(dx)
                                and math.isfinite(dy) and math.isfinite(dz)):
                            break
                        result["time"].append(tv)
                        result["dipole_x"].append(dx)
                        result["dipole_y"].append(dy)
                        result["dipole_z"].append(dz)
                    except ValueError:
                        break
        print(f"[DEBUG] parse_td_dipole: {len(result['time'])} valid steps "
              f"(truncated at NaN/Inf)" if len(result['time']) < 10 else
              f"[DEBUG] parse_td_dipole: {len(result['time'])} steps")
    except Exception as e:
        print(f"[WARN] parse_td_dipole: {e}")
    return result


def compute_radiation_spectrum(td_dipole: dict) -> dict:
    """Far-field emission power spectrum P(ω) ∝ ω²|d(ω)|² from Larmor formula.
    A direct observable: intensity of photons emitted at each energy.
    """
    import numpy as np
    t = np.array(td_dipole.get("time", []), dtype=float)
    if len(t) < 8:
        return {"frequency_ev": [], "intensity": []}
    dt = float(t[1] - t[0])
    n  = len(t)
    dx = np.nan_to_num(np.array(td_dipole["dipole_x"], dtype=float))
    dy = np.nan_to_num(np.array(td_dipole["dipole_y"], dtype=float))
    dz = np.nan_to_num(np.array(td_dipole["dipole_z"], dtype=float))
    # DC-remove + Hann window to suppress spectral leakage
    win = np.hanning(n)
    dx_w = (dx - dx.mean()) * win
    dy_w = (dy - dy.mean()) * win
    dz_w = (dz - dz.mean()) * win
    # Ordinary frequency in a.u. → angular frequency → eV
    freq_au = np.fft.rfftfreq(n, d=dt)   # units: 1/t_au
    omega_au = 2.0 * np.pi * freq_au          # angular freq in a.u.
    omega_ev = omega_au * 27.2114              # eV (1 Ha = 27.2114 eV)
    d_sq = (np.abs(np.fft.rfft(dx_w))**2 +
            np.abs(np.fft.rfft(dy_w))**2 +
            np.abs(np.fft.rfft(dz_w))**2)
    power = omega_au**2 * d_sq                 # P(ω) ∝ ω²|d(ω)|²
    # Dynamic range: show all positive frequencies up to Nyquist
    nyquist_ev = float(omega_ev[-1])
    upper_ev   = min(nyquist_ev, 500.0)        # cap at 500 eV to avoid pure noise
    mask  = (omega_ev > 0.0) & (omega_ev <= upper_ev)
    p_sel = power[mask]
    p_max = float(p_sel.max()) if p_sel.size > 0 else 1.0
    return {
        "frequency_ev": omega_ev[mask].tolist(),
        "intensity":    (p_sel / max(p_max, 1e-30)).tolist(),
    }


def compute_eels_spectrum(td_dipole: dict, config: dict) -> dict:
    """Energy Loss Spectroscopy (EELS) from TDDFT + electron probe.
    EELS(ω) = (ω/π) · Im[ −d(ω) · E*_probe(ω) ]
    The probe E-field is the dipole-approximation Coulomb field at the molecule.
    """
    import numpy as np
    t = np.array(td_dipole.get("time", []), dtype=float)
    if len(t) < 8:
        return {"energy_ev": [], "eels": []}
    dt       = float(t[1] - t[0])
    n        = len(t)
    steps    = int(config.get("octopusTdSteps", config.get("TDMaxSteps", 5000)))
    td_dt_c  = float(config.get("octopusTdTimeStep", config.get("TDTimeStep", 0.05)))
    fe_v     = float(config.get("feProbeVelocity", 0.5))
    fe_y0    = float(config.get("feProbeY0", 2.0))
    fe_z0    = float(config.get("feProbeZ0", 0.0))
    fe_q     = float(config.get("feProbeCharge", -1.0))
    v_au     = fe_v * 137.036
    t_center = steps * td_dt_c / 2.0
    neg_q    = -fe_q  # +1 for electron
    # Reconstruct probe Coulomb E-field at molecule (origin)
    r3       = ((v_au * (t - t_center))**2 + fe_y0**2 + fe_z0**2 + 0.01)**1.5
    E_px     = neg_q * (v_au * (t - t_center)) / r3
    E_py     = neg_q * fe_y0 / r3
    dx = np.nan_to_num(np.array(td_dipole["dipole_x"], dtype=float))
    dy = np.nan_to_num(np.array(td_dipole["dipole_y"], dtype=float))
    win      = np.hanning(n)
    freq_au  = np.fft.rfftfreq(n, d=dt)
    omega_au = 2.0 * np.pi * freq_au
    omega_ev = omega_au * 27.2114
    dx_f = np.fft.rfft((dx - dx.mean()) * win)
    dy_f = np.fft.rfft((dy - dy.mean()) * win)
    Ex_f = np.fft.rfft(E_px * win)
    Ey_f = np.fft.rfft(E_py * win)
    cross = -(dx_f * np.conj(Ex_f) + dy_f * np.conj(Ey_f))
    eels  = (omega_au / np.pi) * np.imag(cross)
    nyquist_ev = float(omega_ev[-1])
    upper_ev   = min(nyquist_ev, 500.0)
    mask     = (omega_ev > 0.0) & (omega_ev <= upper_ev)
    eels_sel = np.clip(eels[mask], 0.0, None)
    e_max    = float(eels_sel.max()) if eels_sel.size > 0 else 1.0
    return {
        "energy_ev": omega_ev[mask].tolist(),
        "eels":      (eels_sel / max(e_max, 1e-30)).tolist(),
    }


def compute_hhg_spectrum(td_dipole: dict) -> dict:
    """High Harmonic Generation (HHG) spectrum from strong-field TDDFT.
    Identifies harmonic peaks in the radiation spectrum and returns
    labeled harmonic orders with energies and intensities.
    """
    import numpy as np
    rad = compute_radiation_spectrum(td_dipole)
    freq_ev = np.array(rad.get("frequency_ev", []), dtype=float)
    intensity = np.array(rad.get("intensity", []), dtype=float)
    if len(freq_ev) < 5:
        return {"harmonic_order": [], "harmonic_energy_ev": [], "harmonic_intensity": []}
    # Simple numpy-based peak detection (avoids scipy import issues on HPC)
    min_dist = max(5, len(intensity) // 200)
    peaks = []
    for i in range(1, len(intensity) - 1):
        if intensity[i] > 0.01 and intensity[i] >= intensity[i - 1] and intensity[i] >= intensity[i + 1]:
            if not peaks or (i - peaks[-1]) >= min_dist:
                peaks.append(i)
    if len(peaks) == 0:
        return {"harmonic_order": [], "harmonic_energy_ev": [], "harmonic_intensity": []}
    peak_energies = freq_ev[peaks]
    peak_intensities = intensity[peaks]
    # Sort by energy
    order = np.argsort(peak_energies)
    peak_energies = peak_energies[order]
    peak_intensities = peak_intensities[order]
    # Assign harmonic orders based on fundamental spacing
    # First significant peak = fundamental (H1)
    harmonic_orders = list(range(1, len(peak_energies) + 1))
    return {
        "harmonic_order": harmonic_orders,
        "harmonic_energy_ev": peak_energies.tolist(),
        "harmonic_intensity": peak_intensities.tolist(),
    }


def choose_octopus_exec_strategy() -> str:
    strategy = os.environ.get("OCTOPUS_EXEC_STRATEGY", "auto").strip().lower()
    if strategy in {"direct", "hpc"}:
        return strategy
    if shutil.which("qsub") and shutil.which("qstat"):
        return "hpc"
    return "direct"


async def query_free_pbs_nodes(pbsnodes_bin: str, min_ncpus: int) -> list[tuple[str, int]]:
    proc = await asyncio.create_subprocess_exec(
        pbsnodes_bin,
        "-a",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    text = (out + err).decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"pbsnodes failed: {text.strip()}")

    blocks = re.split(r"\n\s*\n", text)
    free_nodes: list[tuple[str, int]] = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        node = lines[0].strip()
        if "=" in node:
            continue

        state = ""
        avail_ncpus: Optional[int] = None
        assigned_ncpus: Optional[int] = None

        for ln in lines[1:]:
            s = ln.strip()
            if s.startswith("state ="):
                state = s.split("=", 1)[1].strip().lower()
            elif s.startswith("resources_available.ncpus ="):
                try:
                    avail_ncpus = int(s.split("=", 1)[1].strip())
                except Exception:
                    pass
            elif s.startswith("resources_assigned.ncpus ="):
                try:
                    assigned_ncpus = int(s.split("=", 1)[1].strip())
                except Exception:
                    pass

        state_tokens = {tok.strip() for tok in state.split(",") if tok.strip()}
        if "free" not in state_tokens:
            continue
        # Exclude unhealthy or non-runnable nodes even if state text still contains "free".
        if state_tokens.intersection({"down", "offline", "unknown", "state-unknown", "job-exclusive", "job-shared"}):
            continue

        if avail_ncpus is not None and assigned_ncpus is not None:
            free_cores = max(0, avail_ncpus - assigned_ncpus)
        elif avail_ncpus is not None:
            free_cores = avail_ncpus
        else:
            free_cores = 0

        if free_cores >= max(1, min_ncpus):
            free_nodes.append((node, free_cores))

    free_nodes.sort(key=lambda x: x[1], reverse=True)
    return free_nodes


async def run_octopus_direct(octo_cmd: list[str], work_dir: str, timeout_seconds: int = 300):
    process = await asyncio.create_subprocess_exec(
        *octo_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir
    )
    stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    return process.returncode, stdout_data, stderr_data, {"strategy": "direct"}


async def run_octopus_hpc(
    octo_cmd: list[str],
    work_dir: str,
    timeout_seconds: int = 1800,
    fast_path: bool = False,
    config: Optional[dict] = None,
    pbs_walltime: Optional[str] = None,
):
    qsub_bin = shutil.which("qsub")
    qstat_bin = shutil.which("qstat")
    pbsnodes_bin = shutil.which("pbsnodes")
    if not qsub_bin or not qstat_bin:
        raise RuntimeError("HPC strategy requested but qsub/qstat not available")

    primary_queue = os.environ.get("OCTOPUS_PBS_QUEUE", "workq")
    queue_candidates = os.environ.get("OCTOPUS_PBS_QUEUE_CANDIDATES", "workq")
    queues = [q.strip() for q in queue_candidates.split(",") if q.strip()]
    if primary_queue and primary_queue not in queues:
        queues.insert(0, primary_queue)
    if not queues:
        queues = ["workq"]
    ncpus_env = "OCTOPUS_FAST_PBS_NCPUS" if fast_path else "OCTOPUS_PBS_NCPUS"
    mpiprocs_env = "OCTOPUS_FAST_PBS_MPIPROCS" if fast_path else "OCTOPUS_PBS_MPIPROCS"
    cfg = config if isinstance(config, dict) else {}
    ncpus_override = cfg.get("octopusNcpus")
    mpiprocs_override = cfg.get("octopusMpiprocs")

    if ncpus_override is not None:
        ncpus = int(ncpus_override)
    else:
        ncpus = int(os.environ.get(ncpus_env, os.environ.get("OCTOPUS_PBS_NCPUS", "32")))

    if mpiprocs_override is not None:
        mpiprocs = int(mpiprocs_override)
    else:
        mpiprocs = int(os.environ.get(mpiprocs_env, os.environ.get("OCTOPUS_PBS_MPIPROCS", str(ncpus))))

    mpiprocs = min(mpiprocs, 16)

    max_payload_ncpus = int(os.environ.get("OCTOPUS_MAX_NCPUS_PAYLOAD", "256"))
    if ncpus_override is not None and ncpus > max_payload_ncpus:
        raise RuntimeError(
            f"Invalid PBS resources: payload ncpus={ncpus} exceeds max {max_payload_ncpus}"
        )
    if ncpus <= 0 or mpiprocs <= 0:
        raise RuntimeError(f"Invalid PBS resources: ncpus={ncpus}, mpiprocs={mpiprocs}")
    if mpiprocs > ncpus:
        raise RuntimeError(f"Invalid PBS resources: mpiprocs({mpiprocs}) > ncpus({ncpus})")
    print(
        f"[DEBUG] run_octopus_hpc fast_path={fast_path} timeout={timeout_seconds}s ncpus={ncpus} mpiprocs={mpiprocs}",
        flush=True,
    )
    walltime = pbs_walltime or os.environ.get("OCTOPUS_PBS_WALLTIME", "01:00:00")
    job_name = os.environ.get("OCTOPUS_PBS_JOB_NAME", "dirac_octopus")
    env_script = os.environ.get("OCTOPUS_HPC_ENV_SCRIPT", "/data/apps/intel/2018u3/env.sh")
    poll_interval_env = "OCTOPUS_FAST_PBS_POLL_INTERVAL" if fast_path else "OCTOPUS_PBS_POLL_INTERVAL"
    poll_interval = int(os.environ.get(poll_interval_env, os.environ.get("OCTOPUS_PBS_POLL_INTERVAL", "3")))
    pmix_gds = os.environ.get("OCTOPUS_PMIX_GDS", "hash")
    pmix_psec = os.environ.get("OCTOPUS_PMIX_PSEC", "native")
    mpi_tmpdir = os.environ.get("OCTOPUS_MPI_TMPDIR", os.path.join(work_dir, ".mpi_tmp"))
    precheck_free = False  # disabled
    bind_free_node = os.environ.get("OCTOPUS_PBS_BIND_FREE_NODE", "true").strip().lower() in {"1", "true", "yes", "on"}
    pbs_cmd_timeout = max(5, int(os.environ.get("OCTOPUS_PBS_CMD_TIMEOUT_SECONDS", "300")))

    async def _communicate_with_timeout(proc: asyncio.subprocess.Process, label: str) -> tuple[bytes, bytes]:
        try:
            return await asyncio.wait_for(proc.communicate(), timeout=pbs_cmd_timeout)
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
            except ProcessLookupError:
                # Process can already be gone when timeout cancellation races with process exit.
                pass
            try:
                await proc.wait()
            except ProcessLookupError:
                pass
            raise RuntimeError(f"{label} timed out after {pbs_cmd_timeout}s") from exc

    resource_selector_base = f"select=1:ncpus={ncpus}:mpiprocs={mpiprocs}"
    resource_selector = resource_selector_base
    free_nodes: list[tuple[str, int]] = []
    selected_node = ""
    precheck_history: list[dict[str, object]] = []

    async def _refresh_submission_target(attempt_label: str) -> str:
        nonlocal free_nodes, selected_node
        selector = resource_selector_base
        selected_node = ""

        if precheck_free and pbsnodes_bin:
            free_nodes = await query_free_pbs_nodes(pbsnodes_bin, mpiprocs)
            if not free_nodes:
                raise RuntimeError(
                    f"No free compute node currently has >= {mpiprocs} free cores before {attempt_label}. "
                    f"Please retry later or request fewer cores."
                )
            selected_node = free_nodes[0][0]
            precheck_history.append(
                {
                    "attempt": attempt_label,
                    "selected_node": selected_node,
                    "free_nodes_count": len(free_nodes),
                    "top_free_cores": free_nodes[0][1],
                }
            )
            if bind_free_node:
                selector = f"{selector}:vnode={selected_node}"

        return selector

    resource_selector = await _refresh_submission_target("initial")

    def selector_has_requested_resources(selector_text: str) -> bool:
        normalized = re.sub(r"\s+", "", selector_text or "")
        return f"ncpus={ncpus}" in normalized and f"mpiprocs={mpiprocs}" in normalized

    shell_cmd = " ".join(shlex.quote(x) for x in octo_cmd)
    launcher = os.environ.get("OCTOPUS_PBS_LAUNCHER", "auto").strip().lower()
    cmd_has_mpirun = any(os.path.basename(str(x)).startswith("mpirun") for x in octo_cmd)
    cmd_has_udocker = any(os.path.basename(str(x)).startswith("udocker") for x in octo_cmd)
    cmd_runs_octopus = any(str(x) == "octopus" or str(x).endswith("/octopus") for x in octo_cmd)

    chosen_launcher = launcher
    if launcher == "auto":
        chosen_launcher = "container-mpirun" if cmd_has_udocker else "mpirun"

    if chosen_launcher == "container-mpirun" and cmd_has_udocker and cmd_runs_octopus:
        if octo_cmd and (str(octo_cmd[-1]) == "octopus" or str(octo_cmd[-1]).endswith("/octopus")):
            container_cmd = octo_cmd[:-1] + ["mpirun", "-np", str(mpiprocs), "octopus"]
            shell_cmd = " ".join(shlex.quote(x) for x in container_cmd)
    elif chosen_launcher == "mpirun" and cmd_runs_octopus and not cmd_has_mpirun:
        shell_cmd = f"mpirun -np {mpiprocs} {shell_cmd}"

    job_script = os.path.join(work_dir, "octopus_job.pbs")
    pbs_out = os.path.join(work_dir, "pbs.out")
    pbs_err = os.path.join(work_dir, "pbs.err")
    selected_queue = queues[0]
    with open(job_script, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n")
        f.write(f"#PBS -N {job_name}\n")
        f.write(f"#PBS -q {selected_queue}\n")
        f.write(f"#PBS -l {resource_selector}\n")
        f.write(f"#PBS -l walltime={walltime}\n")
        f.write(f"#PBS -o {pbs_out}\n")
        f.write(f"#PBS -e {pbs_err}\n")
        f.write("set +e\n")
        f.write(f"cd {shlex.quote(work_dir)}\n")
        if env_script:
            f.write(f"if [ -f {shlex.quote(env_script)} ]; then source {shlex.quote(env_script)}; fi\n")
        f.write(f"mkdir -p {shlex.quote(mpi_tmpdir)}\n")
        f.write(f"export TMPDIR={shlex.quote(mpi_tmpdir)}\n")
        f.write(f"export PMIX_SYSTEM_TMPDIR={shlex.quote(mpi_tmpdir)}\n")
        f.write(f"export PMIX_SERVER_TMPDIR={shlex.quote(mpi_tmpdir)}\n")
        f.write(f"export PMIX_MCA_gds={shlex.quote(pmix_gds)}\n")
        f.write(f"export PMIX_MCA_psec={shlex.quote(pmix_psec)}\n")
        f.write(f"{shell_cmd} > octopus.stdout 2> octopus.stderr\n")
        f.write("rc=$?\n")
        f.write("echo $rc > octopus.exitcode\n")
        f.write("exit $rc\n")

    submit_out = b""
    submit_err = b""
    submitted = False
    for candidate_queue in queues:
        resource_selector = await _refresh_submission_target(f"qsub:{candidate_queue}")
        with open(job_script, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n")
            f.write(f"#PBS -N {job_name}\n")
            f.write(f"#PBS -q {candidate_queue}\n")
            f.write(f"#PBS -l {resource_selector}\n")
            f.write(f"#PBS -l walltime={walltime}\n")
            f.write(f"#PBS -o {pbs_out}\n")
            f.write(f"#PBS -e {pbs_err}\n")
            f.write("set +e\n")
            f.write(f"cd {shlex.quote(work_dir)}\n")
            if env_script:
                f.write(f"if [ -f {shlex.quote(env_script)} ]; then source {shlex.quote(env_script)}; fi\n")
            f.write(f"mkdir -p {shlex.quote(mpi_tmpdir)}\n")
            f.write(f"export TMPDIR={shlex.quote(mpi_tmpdir)}\n")
            f.write(f"export PMIX_SYSTEM_TMPDIR={shlex.quote(mpi_tmpdir)}\n")
            f.write(f"export PMIX_SERVER_TMPDIR={shlex.quote(mpi_tmpdir)}\n")
            f.write(f"export PMIX_MCA_gds={shlex.quote(pmix_gds)}\n")
            f.write(f"export PMIX_MCA_psec={shlex.quote(pmix_psec)}\n")
            f.write("rm -f octopus.exitcode\n")  # purge stale artifact from previous shared-dir run
            f.write(f"{shell_cmd} > octopus.stdout 2> octopus.stderr\n")
            f.write("rc=$?\n")
            f.write("echo $rc > octopus.exitcode\n")
            f.write("exit $rc\n")

        submit_proc = await asyncio.create_subprocess_exec(
            qsub_bin,
            job_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        submit_out, submit_err = await _communicate_with_timeout(submit_proc, "qsub")
        if submit_proc.returncode == 0:
            selected_queue = candidate_queue
            submitted = True
            break

    if not submitted:
        raise RuntimeError(f"qsub failed: {submit_err.decode('utf-8', errors='replace')}")

    job_id = submit_out.decode("utf-8", errors="replace").strip().split()[0]

    verify_proc = await asyncio.create_subprocess_exec(
        qstat_bin,
        "-f",
        job_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
    )
    verify_out, verify_err = await _communicate_with_timeout(verify_proc, "qstat verify")
    verify_text = (verify_out + verify_err).decode("utf-8", errors="replace")
    if verify_proc.returncode != 0:
        historical_proc = await asyncio.create_subprocess_exec(
            qstat_bin,
            "-x",
            "-f",
            job_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        hist_out, hist_err = await _communicate_with_timeout(historical_proc, "qstat historical verify")
        historical_text = (hist_out + hist_err).decode("utf-8", errors="replace")
        if historical_proc.returncode == 0:
            verify_text = historical_text
        elif "Job has finished" in verify_text or "Unknown Job" in verify_text or "Unknown Job Id" in verify_text:
            # Some PBS installations require historical query for completed jobs.
            verify_text = ""
        else:
            raise RuntimeError(f"qstat verify failed for {job_id}: {verify_text}")

    m_sel = re.search(r"Resource_List\.select\s*=\s*(.+)", verify_text)
    verify_selector = m_sel.group(1).strip() if m_sel else ""
    if verify_selector and not selector_has_requested_resources(verify_selector):
        raise RuntimeError(
            f"PBS resource mismatch for {job_id}: requested {resource_selector}, actual {verify_selector or 'unknown'}"
        )
    started = time.time()
    last_state = "Q"
    last_exec_vnode = ""
    exit_code_path = os.path.join(work_dir, "octopus.exitcode")
    # Purge stale exit artifacts before polling to prevent false-positive
    # completion detection. The PBS script also does rm -f, but that only
    # executes after the job starts running on a compute node — timing gap.
    for _stale in ["octopus.exitcode"]:
        _sp = os.path.join(work_dir, _stale)
        try:
            os.remove(_sp)
        except OSError:
            pass
    while True:
        if time.time() - started > timeout_seconds:
            raise asyncio.TimeoutError(f"PBS job {job_id} timed out after {timeout_seconds}s")

        # If job wrapper has already produced an exit code, trust local artifact completion
        # instead of waiting indefinitely for PBS metadata to settle.
        if os.path.exists(exit_code_path):
            try:
                exit_text = open(exit_code_path, "r", encoding="utf-8").read().strip()
            except Exception:
                exit_text = ""
            if exit_text:
                last_state = "C"
                break

        stat_proc = await asyncio.create_subprocess_exec(
            qstat_bin,
            "-f",
            job_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        stat_out, stat_err = await _communicate_with_timeout(stat_proc, "qstat poll")
        stat_text = (stat_out + stat_err).decode("utf-8", errors="replace")
        m_state = re.search(r"job_state\s*=\s*([A-Z])", stat_text)
        m_exec = re.search(r"exec_vnode\s*=\s*(.+)", stat_text)
        if m_exec:
            last_exec_vnode = m_exec.group(1).strip()
        if m_state:
            last_state = m_state.group(1)
            if last_state in {"C", "E", "F"}:
                break
        elif stat_proc.returncode != 0 and ("Unknown Job Id" in stat_text or "Unknown Job" in stat_text or "Job has finished" in stat_text):
            last_state = "C"
            break

        await asyncio.sleep(max(1, poll_interval))

    rc = 1
    if os.path.exists(exit_code_path):
        try:
            rc = int(open(exit_code_path, "r", encoding="utf-8").read().strip())
        except Exception:
            rc = 1
    else:
        # udocker may not propagate exit codes through PBS. If PBS says job
        # finished and stdout contains "Calculation ended", treat as success.
        if last_state in {"C", "E", "F"}:
            _stdout_preview = b""
            _sp = os.path.join(work_dir, "octopus.stdout")
            if os.path.exists(_sp):
                try:
                    _stdout_preview = open(_sp, "rb").read(50000)
                except Exception:
                    pass
            if b"Calculation ended" in _stdout_preview:
                print(f"[INFO] PBS job {job_id} finished without exitcode but stdout shows success → rc=0")
                rc = 0

    stdout_path = os.path.join(work_dir, "octopus.stdout")
    stderr_path = os.path.join(work_dir, "octopus.stderr")
    stdout_data = b""
    stderr_data = b""
    if os.path.exists(stdout_path):
        stdout_data = open(stdout_path, "rb").read()
    if os.path.exists(stderr_path):
        stderr_data = open(stderr_path, "rb").read()

    if not last_exec_vnode:
        # Workaround for PBS installs where poll qstat -f omits exec_vnode but qstat -f -H (history) exposes it.
        # Try historical query before trusting local exit-code.
        hist_proc = await asyncio.create_subprocess_exec(
            qstat_bin, "-x", "-f", "-H", job_id,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=work_dir,
        )
        hist_out, hist_err = await _communicate_with_timeout(hist_proc, "qstat hist")
        hist_text = (hist_out + hist_err).decode("utf-8", errors="replace")
        m_hist_exec = re.search(r"exec_vnode\s*=\s*(.+)", hist_text)
        if m_hist_exec:
            last_exec_vnode = m_hist_exec.group(1).strip()
        else:
            # Last resort: trust local exit-code when job ran to completion.
            if os.path.exists(exit_code_path):
                last_exec_vnode = "unknown"
            elif rc == 0 or b"Calculation ended on" in stdout_data:
                last_exec_vnode = "unknown"
            else:
                raise RuntimeError(
                    f"PBS job {job_id} never reported exec_vnode; job may not have run on a compute node"
                )

    meta = {
        "strategy": "hpc",
        "run_dir": os.path.basename(work_dir),
        "job_id": job_id,
        "job_state": last_state,
        "queue": selected_queue,
        "ncpus": ncpus,
        "mpiprocs": mpiprocs,
        "launcher": chosen_launcher,
        "mpi_tmpdir": mpi_tmpdir,
        "pmix_gds": pmix_gds,
        "precheck_free": precheck_free,
        "bind_free_node": bind_free_node,
        "selected_node": selected_node,
        "free_nodes_count": len(free_nodes),
        "precheck_history": precheck_history,
        "exec_vnode": last_exec_vnode,
        "resource_selector": resource_selector,
    }
    return rc, stdout_data, stderr_data, meta


async def run_octopus_calculation(config: dict) -> dict:
    """Run an Octopus calculation and return parsed results."""
    print(f"[DEBUG] run_octopus_calculation starting...")
    # Log received parameters for diagnosis
    print(f"[DEBUG] Received config keys: {list(config.keys())}")
    print(f"[DEBUG] octopusSpacing={config.get('octopusSpacing', 'MISSING')} | "
          f"octopusRadius={config.get('octopusRadius', 'MISSING')} | "
          f"spatialRange={config.get('spatialRange', 'MISSING')} | "
          f"lengthUnit={config.get('octopusLengthUnit', config.get('octopusInputUnit', 'not_set'))}")
    engine_mode = config.get("engineMode", "octopus3D")
    print(f"[DEBUG] engineMode from config = {repr(engine_mode)} | expected: 'octopus3D'")
    calc_mode = str(config.get("calcMode", "gs")).strip().lower()
    molecule_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", config.get("molecule_name", ""))))
    molecule_name = molecule_raw.get("name", "") if isinstance(molecule_raw, dict) else str(molecule_raw or "")
    auto_fast_path = engine_mode == "octopus3D" and calc_mode == "gs" and molecule_name.strip().lower() == "h2"
    if auto_fast_path and not bool(config.get("fastPath", False)):
        fast_spacing = float(os.environ.get("OCTOPUS_FAST_SPACING_BOHR", "0.5"))
        fast_radius = float(os.environ.get("OCTOPUS_FAST_RADIUS_BOHR", "3.0"))
        fast_padding = float(os.environ.get("OCTOPUS_FAST_BOX_PADDING_BOHR", "2.5"))
        fast_scf_cap = int(os.environ.get("OCTOPUS_FAST_MAX_SCF_ITERATIONS", "80"))
        cfg_spacing = _parse_length(config.get("octopusSpacing", config.get("gridSpacing", fast_spacing)))
        cfg_radius = _parse_length(config.get("octopusRadius", config.get("radius", fast_radius)))
        cfg_scf = int(config.get("octopusMaxScfIterations", fast_scf_cap))
        config = {
            **config,
            "fastPath": True,
            "skipRunExplanation": True,
            "octopusSpacing": max(cfg_spacing, fast_spacing),
            "octopusRadius": min(cfg_radius, fast_radius),
            "octopusBoxPadding": fast_padding,
            "octopusMaxScfIterations": min(cfg_scf, fast_scf_cap),
        }
        print("[DEBUG] Auto-enabled fastPath for H2 GS run", flush=True)
    skip_run_explanation = bool(config.get("skipRunExplanation", False))
    exec_strategy = choose_octopus_exec_strategy()
    runs_dir = os.path.join(resolve_output_dir(), "runs")
    os.makedirs(runs_dir, exist_ok=True)

    reusable_run_name = os.environ.get("OCTOPUS_REUSABLE_RUN_DIR", "octopus_latest")
    if exec_strategy == "local":
        reusable_run_name = os.environ.get("OCTOPUS_REUSABLE_RUN_DIR_LOCAL", reusable_run_name)
    else:
        reusable_run_name = os.environ.get("OCTOPUS_REUSABLE_RUN_DIR_HPC", reusable_run_name)

    work_dir = prepare_reusable_run_dir(runs_dir, reusable_run_name)
    
    try:
        # 1. ALWAYS Run Ground State First
        inp_content_gs = generate_inp(config, is_td=False)
        print(f"[DEBUG] Generated Octopus Inp (GS):\n{inp_content_gs}")
        with open(os.path.join(work_dir, "inp"), "w") as f:
            f.write(inp_content_gs)
        with open(os.path.join(work_dir, "inp_gs"), "w") as f:
            f.write(inp_content_gs)

        def octopus_cmd_for_workdir(cwd: str):
            if shutil.which("octopus"):
                return ["octopus"]

            udocker_bin = os.environ.get("UDOCKER_BIN", os.path.expanduser("~/.local/bin/udocker"))
            container_name = _resolve_octopus_udocker_container(udocker_bin)
            if os.path.exists(udocker_bin):
                pp_path = os.environ.get("OCTOPUS_PP_PATH", "")
                cmd = [
                    udocker_bin,
                    "run",
                    f"--volume={cwd}:/work",
                    "--workdir=/work",
                ]
                if pp_path:
                    # Copy UPF files to work directory so container can access them
                    for sym in ["C", "H", "O", "N", "He", "S", "P", "Fe"]:
                        src = os.path.join(pp_path, f"{sym}.upf")
                        if os.path.exists(src):
                            shutil.copy2(src, os.path.join(cwd, f"{sym}.upf"))
                    cmd.append("--env=OCTOPUS_PP_PATH=/work")
                cmd.extend([container_name, "octopus"])
                return cmd

            extra = os.environ.get("OCTOPUS_CMD", "").strip()
            if extra:
                return shlex.split(extra)

            raise RuntimeError("No Octopus executable found (native or udocker).")

        octo_cmd = octopus_cmd_for_workdir(work_dir)

        # Run Octopus GS
        if exec_strategy == "hpc":
            use_fast_path = bool(config.get("fastPath", False))
            hpc_timeout_seconds = int(os.environ.get("OCTOPUS_FAST_HPC_TIMEOUT_SECONDS", "150")) if use_fast_path else 3600
            print(
                f"[DEBUG] run_octopus_calculation strategy=hpc fast_path={use_fast_path} hpc_timeout_seconds={hpc_timeout_seconds}",
                flush=True,
            )
            try:
                rc, stdout_gs, stderr_gs, run_meta = await run_octopus_hpc(
                    octo_cmd,
                    work_dir,
                    timeout_seconds=hpc_timeout_seconds,
                    fast_path=use_fast_path,
                    config=config,
                )
            except Exception as hpc_exc:
                if not use_fast_path:
                    raise
                fallback_timeout = int(os.environ.get("OCTOPUS_FAST_DIRECT_TIMEOUT_SECONDS", "180"))
                print(
                    f"[WARN] HPC fastPath failed ({hpc_exc}); falling back to direct run (timeout={fallback_timeout}s)",
                    flush=True,
                )
                rc, stdout_gs, stderr_gs, run_meta = await run_octopus_direct(
                    octo_cmd,
                    work_dir,
                    timeout_seconds=fallback_timeout,
                )
                run_meta["strategy"] = "direct_fallback"
                run_meta["hpc_error"] = str(hpc_exc)
        else:
            molecule_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", config.get("molecule_name", "H2"))))
            molecule_name = molecule_raw.get("name", "H2") if isinstance(molecule_raw, dict) else str(molecule_raw or "H2")
            small_molecule_timeout = {
                "H": 120,
                "H2": 120,
                "He": 300,
                "Li": 180,
                "H2O": 600,
                "CH4": 600,
                "NH3": 600,
                "CO": 600,
                "N2": 600,
            }
            gs_timeout = small_molecule_timeout.get(molecule_name, 300)
            rc, stdout_gs, stderr_gs, run_meta = await run_octopus_direct(octo_cmd, work_dir, timeout_seconds=gs_timeout)

        print(
            f"[DEBUG] Octopus execution meta: strategy={run_meta.get('strategy')} "
            f"queue={run_meta.get('queue', '-') } ncpus={run_meta.get('ncpus', '-') } "
            f"mpiprocs={run_meta.get('mpiprocs', '-') }"
        )

        if rc != 0:
            err_msg = stderr_gs.decode("utf-8", errors="replace")
            print(f"[ERROR] Octopus GS failed Code {rc}: {err_msg}")
            # Still return partial data if info file exists, otherwise error
            info_path = os.path.join(work_dir, "static", "info")
            if not os.path.exists(info_path):
                msg = f"Octopus GS failed: {err_msg}"
                if run_meta.get("strategy") == "hpc":
                    msg = f"{msg} (PBS job {run_meta.get('job_id', 'unknown')}, state={run_meta.get('job_state', 'unknown')})"
                return {"status": "error", "message": msg, "engine": "octopus-16.0"}

        stdout_text = stdout_gs.decode("utf-8", errors="replace")
        stderr_text = stderr_gs.decode("utf-8", errors="replace")
        if "Octopus will run in *serial*" in stdout_text:
            print("[WARN] Octopus reported serial execution mode")
        elif "Parallelization" in stdout_text:
            print("[DEBUG] Octopus parallelization section detected in stdout")
        
        # Parse GS info
        info_path = os.path.join(work_dir, "static", "info")
        parsed_gs = parse_octopus_info(info_path)

        # Unit conversion: if UnitsOutput = eV_Angstrom, Octopus outputs energy in eV.
        # Reference values are in Hartree, so convert back to maintain consistency.
        inp_path = os.path.join(work_dir, "inp")
        units_output = None
        if os.path.exists(inp_path):
            with open(inp_path, "r") as f:
                for line in f:
                    m = re.match(r"^\s*UnitsOutput\s*=\s*(\S+)", line, re.IGNORECASE)
                    if m:
                        units_output = m.group(1).strip()
                        break
        if units_output and "eV" in units_output:
            HARTREE_TO_EV = 27.2114
            # Octopus wrote energies in eV — convert back to Hartree for internal consistency
            if parsed_gs.get("total_energy") is not None:
                parsed_gs["total_energy"] = parsed_gs["total_energy"] / HARTREE_TO_EV
            if parsed_gs.get("eigenvalues"):
                parsed_gs["eigenvalues"] = [e / HARTREE_TO_EV for e in parsed_gs["eigenvalues"]]
            for entry in parsed_gs.get("eigenvalue_entries", []):
                if "eigenvalue_hartree" in entry:
                    entry["eigenvalue_hartree"] = entry["eigenvalue_hartree"] / HARTREE_TO_EV

        # Base JSON Response structure
        response_data = {
            "status": "success" if (parsed_gs["converged"] or rc == 0) else "warning",
            "eigenvalues": parsed_gs["eigenvalues"],
            "total_energy": parsed_gs["total_energy"],
            "converged": parsed_gs["converged"],
            "scf_iterations": parsed_gs["scf_iterations"],
            "engine": "octopus-16.0",
            "stdout_tail": stdout_text[-1000:] if stdout_text else "",
            "stderr_tail": stderr_text[-1000:] if stderr_text else "",
            "returncode": rc,
        }
        if run_meta.get("strategy") == "hpc":
            response_data["scheduler"] = run_meta

        if engine_mode == "octopus3D":
            use_fast_path = bool(config.get("fastPath", False))

            if use_fast_path:
                HARTREE_TO_EV = 27.2114
                evals = parsed_gs.get("eigenvalues") or []
                evals_eV = [e * HARTREE_TO_EV for e in evals]
                negative_evals = [e for e in evals_eV if e < 0]
                positive_evals = [e for e in evals_eV if e >= 0]
                homo_eV = max(negative_evals) if negative_evals else None
                lumo_eV = min(positive_evals) if positive_evals else None
                _mol_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", config.get("molecule_name", "H2"))))
                _mol_name = _mol_raw.get("name", "H2") if isinstance(_mol_raw, dict) else _mol_raw

                response_data["molecular"] = {
                    "moleculeName": _mol_name,
                    "calcMode": calc_mode,
                    "energy_levels": evals_eV,
                    "homo_energy": homo_eV,
                    "lumo_energy": lumo_eV,
                    "total_energy_hartree": parsed_gs.get("total_energy"),
                    "scf_iterations": parsed_gs.get("scf_iterations", 0),
                    "converged": parsed_gs.get("converged", False),
                    "fast_path_minimal": True,
                }

                response_data = sanitize_floats(response_data)
                cleanup_octopus_run_dirs(runs_dir, active_run_dir=work_dir)
                return response_data

            # Populate molecular specific fields from GS
            evals = parsed_gs["eigenvalues"]
            homo_energy = None
            lumo_energy = None

            if parsed_gs.get("eigenvalue_entries"):
                occupied = [e["eigenvalue_hartree"] for e in parsed_gs["eigenvalue_entries"] if e.get("occupation", 0) > 0.5]
                unoccupied = [e["eigenvalue_hartree"] for e in parsed_gs["eigenvalue_entries"] if e.get("occupation", 0) <= 0.5]
                homo_energy = max(occupied) if occupied else None
                lumo_energy = min(unoccupied) if unoccupied else None
            elif evals:
                # Fallback: negative eigenvalues = occupied, positive = virtual
                negative_evals = [e for e in evals if e < 0]
                positive_evals = [e for e in evals if e >= 0]
                homo_energy = max(negative_evals) if negative_evals else None
                lumo_energy = min(positive_evals) if positive_evals else None

            # Persist results to workspace/output for host mapping if needed
            output_dir = resolve_output_dir()
            os.makedirs(output_dir, exist_ok=True)
            # Copy static files if they exist
            static_dir = os.path.join(work_dir, "static")
            if os.path.exists(static_dir):
                for item in os.listdir(static_dir):
                    s = os.path.join(static_dir, item)
                    d = os.path.join(output_dir, item)
                    if os.path.isfile(s):
                        shutil.copy2(s, d)

            # Parse 1D slice wavefunctions (produced by OutputFormat = axis_x)
            wfs_data = parse_octopus_wfs_1d(static_dir)
            if wfs_data["x_grid"]:
                response_data["x_grid"] = wfs_data["x_grid"]
                response_data["potential"] = wfs_data["potential"]
                response_data["wavefunctions"] = wfs_data["wavefunctions"]
            if wfs_data.get("density"):
                response_data["density_1d"] = wfs_data["density"]
            # Potential breakdown: v0=external, vh=Hartree, vxc=XC, vks=total KS
            _pc = {k: wfs_data[k] for k in ("v0", "vh", "vxc") if wfs_data.get(k)}
            if _pc:
                _pc["vks"] = wfs_data.get("potential", [])
                response_data["potential_components"] = _pc

            # Convert eigenvalues Hartree → eV for frontend display
            HARTREE_TO_EV = 27.2114
            evals_eV = [e * HARTREE_TO_EV for e in evals]
            homo_eV = homo_energy * HARTREE_TO_EV if homo_energy is not None else None
            lumo_eV = lumo_energy * HARTREE_TO_EV if lumo_energy is not None else None

            # Proper HOMO/LUMO from parsed_gs occupation numbers
            occupied_eig = [
                e["eigenvalue_hartree"] * HARTREE_TO_EV
                for e in parsed_gs.get("eigenvalue_entries", [])
                if e.get("occupation", 0) > 0.5
            ]
            unoccupied_eig = [
                e["eigenvalue_hartree"] * HARTREE_TO_EV
                for e in parsed_gs.get("eigenvalue_entries", [])
                if e.get("occupation", 0) <= 0.5
            ]
            if occupied_eig:
                homo_eV = max(occupied_eig)
            if unoccupied_eig:
                lumo_eV = min(unoccupied_eig)

            # Resolve molecule name (can be string or dict with name key)
            _mol_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", config.get("molecule_name", "H2"))))
            _mol_name = _mol_raw.get("name", "H2") if isinstance(_mol_raw, dict) else _mol_raw

            # Atom positions for frontend geometry visualization
            _custom_atoms = config.get("customAtoms") or config.get("atoms")
            _dims = int(config.get("octopusDimensions", config.get("dimensionality", 3)) if config.get("octopusDimensions", config.get("dimensionality", "3D")) not in ("1D", "2D", "3D") else (1 if config.get("octopusDimensions","3D")=="1D" else (2 if config.get("octopusDimensions","3D")=="2D" else 3)))
            # Read box radius using the same priority logic as generate_inp (no halving when octopusRadius is explicit)
            if "octopusRadius" in config:
                _box_radius = _parse_length(config["octopusRadius"])
            elif "spatialRange" in config:
                _box_radius = _parse_length(config["spatialRange"]) / 2.0
            else:
                _box_radius = _parse_length(config.get("radius", 10.0))

            response_data["molecular"] = {
                "moleculeName": _mol_name,
                "calcMode": calc_mode,
                "energy_levels": evals_eV,
                "homo_energy": homo_eV,
                "lumo_energy": lumo_eV,
                "total_energy_hartree": parsed_gs.get("total_energy"),
                "scf_iterations": parsed_gs.get("scf_iterations", 0),
                "converged": parsed_gs.get("converged", False),
                "atom_positions": get_atom_positions(_mol_name, _dims, _custom_atoms),
                "box_radius": _box_radius,
            }
            print(f"[DEBUG] response_data['molecular'] set: {response_data.get('molecular')}")
            response_data["molecular"]["convergence_data"] = parse_octopus_convergence(static_dir)
            response_data["molecular"]["dos_data"] = parse_octopus_dos(static_dir)

            # Render density snapshots from the actual calculation's density.cube
            render_snaps = render_density_snapshots(static_dir)
            if render_snaps:
                response_data["molecular"]["render_snapshots"] = render_snaps

            # GO (geometry optimization) output
            go_data = parse_go_min_xyz(work_dir)
            if go_data.get("found"):
                response_data["molecular"]["optimized_geometry"] = go_data
            go_conv = parse_go_convergence(work_dir)
            if go_conv.get("found"):
                response_data["molecular"]["go_convergence"] = go_conv

            # 2. If TD mode is requested, run TD propagation now that GS is done
            restart_dir = os.path.join(work_dir, "restart")
            can_run_td = bool(parsed_gs["converged"]) or (rc == 0 and os.path.isdir(restart_dir))
            if calc_mode == "td" and can_run_td:
                print(f"[DEBUG] TD mode requested: calcMode={calc_mode}, converged={parsed_gs['converged']}")
                
                # **KEY FIX**: Don't delete restart. Instead, generate TD inp and let Octopus
                # use the restart files for initialization. Just need to continue from where GS left off.
                # The restart/ folder contains the converged density matrix, which TD needs.
                print(f"[DEBUG] Keeping restart directory for TD initialization")
                
                # Generate and write TD input
                inp_content_td = generate_inp(config, is_td=True)
                inp_path = os.path.join(work_dir, "inp")
                with open(inp_path, "w") as f:
                    f.write(inp_content_td)
                with open(os.path.join(work_dir, "inp_td"), "w") as f:
                    f.write(inp_content_td)
                print(f"[DEBUG] TD inp file written, size={len(inp_content_td)} bytes")

                # Purge stale td.general/ from previous reusable-dir run
                for _td_stale in ["td.general"]:
                    _td_stale_path = os.path.join(work_dir, _td_stale)
                    if os.path.exists(_td_stale_path):
                        shutil.rmtree(_td_stale_path, ignore_errors=True)
                        print(f"[DEBUG] Purged stale {_td_stale}/ from work_dir")

                # Preserve GS logs before running TD stage (TD may overwrite octopus.stdout/err)
                _gs_stdout = os.path.join(work_dir, "octopus.stdout")
                _gs_stderr = os.path.join(work_dir, "octopus.stderr")
                if os.path.exists(_gs_stdout):
                    shutil.copy2(_gs_stdout, os.path.join(work_dir, "octopus_gs.stdout"))
                if os.path.exists(_gs_stderr):
                    shutil.copy2(_gs_stderr, os.path.join(work_dir, "octopus_gs.stderr"))
                
                # Run TD octopus with the same strategy as GS
                print(f"[DEBUG] Starting TD octopus stage in {work_dir} (strategy={exec_strategy})")
                _td_walltime = config.get("octopusPbsWalltime") or config.get("pbsWalltime")
                _td_timeout = int(_td_walltime_to_seconds(_td_walltime)) if _td_walltime else 3600
                # Ensure timeout is at least as long as walltime + 2 min buffer
                _td_timeout = max(_td_timeout, 3600)
                if exec_strategy == "hpc":
                    rc_td, stdout_td, stderr_td, td_meta = await run_octopus_hpc(
                        octo_cmd,
                        work_dir,
                        timeout_seconds=_td_timeout,
                        fast_path=bool(config.get("fastPath", False)),
                        config=config,
                        pbs_walltime=_td_walltime,
                    )
                else:
                    rc_td, stdout_td, stderr_td, td_meta = await run_octopus_direct(octo_cmd, work_dir, timeout_seconds=3600)
                print(f"[DEBUG] TD stage completed, returncode={rc_td}, meta={td_meta}")
                
                # Log TD output
                stdout_td_str = stdout_td.decode("utf-8", errors="replace")
                stderr_td_str = stderr_td.decode("utf-8", errors="replace")
                
                print(f"[DEBUG] TD stdout length={len(stdout_td_str)}, stderr length={len(stderr_td_str)}")
                
                if stderr_td_str:
                    print(f"[DEBUG] TD stderr (last 500 chars):\n{stderr_td_str[-500:]}")
                
                if rc_td != 0:
                    print(f"[ERROR] TD octopus failed with return code {rc_td}")
                    if stdout_td_str:
                        print(f"[ERROR] TD stdout (last 800):\n{stdout_td_str[-800:]}")
                
                # Check if TD created output directories
                td_dir = os.path.join(work_dir, "td.general")
                print(f"[DEBUG] Checking for td.general directory: {td_dir}")
                if os.path.exists(td_dir):
                    td_files = os.listdir(td_dir)
                    print(f"[DEBUG] ✓ td.general created with {len(td_files)} files")
                    if td_files:
                        print(f"[DEBUG] Files in td.general: {td_files[:10]}")
                else:
                    print(f"[ERROR] ✗ td.general directory NOT created by TD octopus")
                
                stdout_text += "\n--- TD Run ---\n" + stdout_td_str[-500:]
                response_data["stdout_tail"] = stdout_text[-1500:]
                response_data["molecular"]["td_executed"] = os.path.exists(td_dir)
                
                # Now run oct-propagation_spectrum to get the cross section
                if os.path.exists(td_dir):
                    print(f"[DEBUG] Starting oct-propagation_spectrum in {work_dir}")
                    stderr_spec_str = ""
                    spectrum_data = {"energy_ev": [], "cross_section": []}
                    spectrum_warning = None

                    def spectrum_cmd_for_workdir(cwd: str):
                        if shutil.which("oct-propagation_spectrum"):
                            return ["oct-propagation_spectrum"]

                        udocker_bin = os.environ.get("UDOCKER_BIN", os.path.expanduser("~/.local/bin/udocker"))
                        container_name = _resolve_octopus_udocker_container(udocker_bin)
                        if os.path.exists(udocker_bin):
                            return [
                                udocker_bin,
                                "run",
                                f"--volume={cwd}:/work",
                                "--workdir=/work",
                                container_name,
                                "oct-propagation_spectrum",
                            ]
                        raise FileNotFoundError("oct-propagation_spectrum not found in PATH and udocker is unavailable")

                    try:
                        spec_cmd = spectrum_cmd_for_workdir(work_dir)
                        process_spec = await asyncio.create_subprocess_exec(
                            *spec_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=work_dir
                        )

                        try:
                            stdout_spec, stderr_spec = await asyncio.wait_for(
                                process_spec.communicate(), timeout=600
                            )
                            print(f"[DEBUG] oct-propagation_spectrum completed, returncode={process_spec.returncode}")
                            stderr_spec_str = stderr_spec.decode("utf-8", errors="replace")
                        except asyncio.TimeoutError:
                            print(f"[ERROR] oct-propagation_spectrum timed out")
                            process_spec.kill()
                            spectrum_warning = "oct-propagation_spectrum timed out"

                        if stderr_spec_str:
                            print(f"[DEBUG] oct-propagation_spectrum stderr (last 300 chars):\n{stderr_spec_str[-300:]}")

                        # Check for cross_section_vector (written to work_dir root, not td.general/)
                        cs_path = os.path.join(work_dir, "cross_section_vector")
                        print(f"[DEBUG] Checking for cross_section_vector at {cs_path}")
                        if os.path.exists(cs_path):
                            cs_size = os.path.getsize(cs_path)
                            print(f"[DEBUG] ✓ cross_section_vector found, size={cs_size} bytes")
                        else:
                            print(f"[ERROR] ✗ cross_section_vector NOT found")
                            td_cs = os.path.join(td_dir, "cross_section_vector")
                            if os.path.exists(td_cs):
                                print(f"[DEBUG] Found in td.general/ instead: {td_cs}")
                            root_files = os.listdir(work_dir)
                            print(f"[DEBUG] Work dir files: {[f for f in root_files if 'cross' in f.lower() or 'spectrum' in f.lower()]}")

                        spectrum_data = parse_octopus_cross_section(work_dir)
                        print(f"[DEBUG] parse_octopus_cross_section: energy_ev={len(spectrum_data.get('energy_ev', []))} points, cs={len(spectrum_data.get('cross_section', []))} points")
                    except FileNotFoundError:
                        spectrum_warning = "oct-propagation_spectrum not found in PATH; skipping optical spectrum extraction"
                        print(f"[WARN] {spectrum_warning}")

                    if spectrum_warning:
                        spectrum_data["warning"] = spectrum_warning
                    response_data["molecular"]["optical_spectrum"] = spectrum_data
                    # Parse dipole time series from td.general/multipoles
                    td_dipole_data = parse_td_dipole(td_dir)
                    print(f"[DEBUG] parse_td_dipole: {len(td_dipole_data.get('time', []))} steps")
                    response_data["molecular"]["td_dipole"] = td_dipole_data

                    # Far-field radiation spectrum P(ω) ∝ ω²|d(ω)|²
                    if len(td_dipole_data.get("time", [])) >= 8:
                        response_data["molecular"]["radiation_spectrum"] = \
                            compute_radiation_spectrum(td_dipole_data)
                        print(f"[DEBUG] radiation_spectrum: "
                              f"{len(response_data['molecular']['radiation_spectrum'].get('frequency_ev', []))} pts")

                    # EELS from probe (only if probe was active)
                    if config.get("feProbeEnabled") and len(td_dipole_data.get("time", [])) >= 8:
                        response_data["molecular"]["eels_spectrum"] = \
                            compute_eels_spectrum(td_dipole_data, config)
                        print(f"[DEBUG] eels_spectrum: "
                              f"{len(response_data['molecular']['eels_spectrum'].get('energy_ev', []))} pts")

                    # HHG harmonics spectrum (for strong-field / sin / CW excitation)
                    excitation_type = config.get("tdExcitationType", "delta")
                    if excitation_type != "delta" and len(td_dipole_data.get("time", [])) >= 8:
                        hhg_data = compute_hhg_spectrum(td_dipole_data)
                        if hhg_data.get("harmonic_energy_ev"):
                            response_data["molecular"]["hhg_spectrum"] = hhg_data
                            print(f"[DEBUG] hhg_spectrum: "
                                  f"{len(hhg_data.get('harmonic_energy_ev', []))} harmonics")

                    # Persist TD output to /workspace/output for host access
                    output_dir = resolve_output_dir()
                    os.makedirs(output_dir, exist_ok=True)
                    # Copy td.general/ directory
                    td_out = os.path.join(output_dir, "td.general")
                    if os.path.exists(td_out):
                        shutil.rmtree(td_out, ignore_errors=True)
                    shutil.copytree(td_dir, td_out)
                    print(f"[DEBUG] ✓ Copied td.general/ to {td_out}")
                    # Copy cross_section_vector if at root level
                    cs_path = os.path.join(work_dir, "cross_section_vector")
                    if os.path.exists(cs_path):
                        shutil.copy2(cs_path, os.path.join(output_dir, "cross_section_vector"))
                        print(f"[DEBUG] ✓ Copied cross_section_vector to {output_dir}")
                else:
                    print(f"[DEBUG] Skipping oct-propagation_spectrum because td.general not found")
                    response_data["molecular"]["optical_spectrum"] = {"energy_ev": [], "cross_section": []}
            elif calc_mode == "casida" and can_run_td:
                print(f"[DEBUG] Casida mode requested: calcMode={calc_mode}, converged={parsed_gs['converged']}")
                print(f"[DEBUG] Keeping restart directory for Casida initialization")

                inp_content_casida = generate_inp(config, is_td=False, is_casida=True)
                inp_path = os.path.join(work_dir, "inp")
                with open(inp_path, "w") as f:
                    f.write(inp_content_casida)
                with open(os.path.join(work_dir, "inp_casida"), "w") as f:
                    f.write(inp_content_casida)
                print(f"[DEBUG] Casida inp file written, size={len(inp_content_casida)} bytes")

                # Purge stale casida/ from previous reusable-dir run so parse doesn't find phantom data
                for _casida_stale in ["casida"]:
                    _casida_stale_path = os.path.join(work_dir, _casida_stale)
                    if os.path.exists(_casida_stale_path):
                        shutil.rmtree(_casida_stale_path, ignore_errors=True)
                        print(f"[DEBUG] Purged stale {_casida_stale}/ from work_dir")
                _static_casida = os.path.join(work_dir, "static", "casida")
                if os.path.exists(_static_casida):
                    os.remove(_static_casida)
                    print(f"[DEBUG] Purged stale static/casida from work_dir")

                print(f"[DEBUG] Starting Casida octopus stage in {work_dir} (strategy={exec_strategy})")
                _casida_walltime = config.get("octopusPbsWalltime") or config.get("pbsWalltime")
                _casida_timeout = int(_td_walltime_to_seconds(_casida_walltime)) if _casida_walltime else 3600
                _casida_timeout = max(_casida_timeout, 3600)
                if exec_strategy == "hpc":
                    rc_casida, stdout_casida, stderr_casida, casida_meta = await run_octopus_hpc(
                        octo_cmd,
                        work_dir,
                        timeout_seconds=_casida_timeout,
                        fast_path=bool(config.get("fastPath", False)),
                        config=config,
                        pbs_walltime=_casida_walltime,
                    )
                else:
                    rc_casida, stdout_casida, stderr_casida, casida_meta = await run_octopus_direct(
                        octo_cmd, work_dir, timeout_seconds=3600
                    )
                print(f"[DEBUG] Casida stage completed, returncode={rc_casida}, meta={casida_meta}")

                stdout_casida_str = stdout_casida.decode("utf-8", errors="replace") if stdout_casida else ""
                stderr_casida_str = stderr_casida.decode("utf-8", errors="replace") if stderr_casida else ""

                if rc_casida != 0:
                    print(f"[ERROR] Casida octopus failed with return code {rc_casida}")
                    if stdout_casida_str:
                        print(f"[ERROR] Casida stdout (last 800):\n{stdout_casida_str[-800:]}")

                stdout_text += "\n--- Casida Run ---\n" + stdout_casida_str[-500:]
                response_data["stdout_tail"] = stdout_text[-1500:]
                casida_data = parse_octopus_casida(work_dir)
                n_exc = len(casida_data.get("energies_ev", []))
                print(f"[DEBUG] parse_octopus_casida: {n_exc} excitations")
                response_data["molecular"]["casida"] = casida_data
                response_data["molecular"]["casida_executed"] = n_exc > 0

                output_dir = resolve_output_dir()
                os.makedirs(output_dir, exist_ok=True)
                casida_src = os.path.join(work_dir, "casida", "casida")
                if not os.path.exists(casida_src):
                    casida_src = os.path.join(work_dir, "static", "casida")
                if os.path.exists(casida_src):
                    shutil.copy2(casida_src, os.path.join(output_dir, "casida"))
                    print(f"[DEBUG] Copied casida to {output_dir}")
            # ── Vibrational Modes ──
            elif calc_mode == "vib" and can_run_td:
                print(f"[DEBUG] Vibrational modes requested, converged={parsed_gs['converged']}")

                inp_content_vib = generate_inp(config, is_vib=True)
                with open(os.path.join(work_dir, "inp"), "w") as f:
                    f.write(inp_content_vib)
                with open(os.path.join(work_dir, "inp_vib"), "w") as f:
                    f.write(inp_content_vib)
                print(f"[DEBUG] Vib inp written, size={len(inp_content_vib)} bytes")

                # Purge stale vib_modes/
                _vib_stale = os.path.join(work_dir, "vib_modes")
                if os.path.exists(_vib_stale):
                    shutil.rmtree(_vib_stale, ignore_errors=True)

                _vib_walltime = config.get("octopusPbsWalltime") or config.get("pbsWalltime")
                _vib_timeout = int(_td_walltime_to_seconds(_vib_walltime)) if _vib_walltime else 7200
                _vib_timeout = max(_vib_timeout, 7200)
                print(f"[DEBUG] Starting vib_modes stage in {work_dir} (timeout={_vib_timeout}s)")
                if exec_strategy == "hpc":
                    rc_vib, stdout_vib, stderr_vib, vib_meta = await run_octopus_hpc(
                        octo_cmd, work_dir, timeout_seconds=_vib_timeout,
                        fast_path=False, config=config, pbs_walltime=_vib_walltime,
                    )
                else:
                    rc_vib, stdout_vib, stderr_vib, vib_meta = await run_octopus_direct(
                        octo_cmd, work_dir, timeout_seconds=_vib_timeout
                    )
                print(f"[DEBUG] Vib stage completed, rc={rc_vib}")

                stdout_vib_str = stdout_vib.decode("utf-8", errors="replace") if stdout_vib else ""
                if rc_vib != 0:
                    print(f"[ERROR] Vib octopus failed rc={rc_vib}")
                    if stdout_vib_str:
                        print(f"[ERROR] Vib stdout (last 800):\n{stdout_vib_str[-800:]}")

                stdout_text += "\n--- Vib Run ---\n" + stdout_vib_str[-500:]
                response_data["stdout_tail"] = stdout_text[-1500:]
                vib_data = parse_octopus_vib_modes(work_dir)
                n_vib = len(vib_data.get("frequencies_cm", []))
                print(f"[DEBUG] parse_octopus_vib_modes: {n_vib} modes")
                response_data["molecular"]["vib_modes"] = vib_data
                response_data["molecular"]["vib_executed"] = n_vib > 0

                # Copy vib output to results
                output_dir = resolve_output_dir()
                os.makedirs(output_dir, exist_ok=True)
                for _vib_file in ["normal_frequencies_lr", "infrared"]:
                    _src = os.path.join(work_dir, "vib_modes", _vib_file)
                    if os.path.exists(_src):
                        shutil.copy2(_src, os.path.join(output_dir, _vib_file))
                        print(f"[DEBUG] Copied {_vib_file} to {output_dir}")

            elif calc_mode == "td":
                skip_reason = (
                    f"TD skipped because GS is not ready (converged={parsed_gs.get('converged', False)}, "
                    f"scf_iterations={parsed_gs.get('scf_iterations', 0)}, returncode={rc}, "
                    f"restart_exists={os.path.isdir(restart_dir)})."
                )
                print(f"[WARN] {skip_reason}")
                response_data["status"] = "warning"
                response_data["molecular"]["td_executed"] = False
                response_data["molecular"]["td_skipped_reason"] = skip_reason
                response_data["molecular"]["optical_spectrum"] = {
                    "energy_ev": [],
                    "cross_section": [],
                    "warning": skip_reason,
                }
            elif calc_mode == "casida":
                skip_reason = (
                    f"Casida skipped because GS is not ready (converged={parsed_gs.get('converged', False)}, "
                    f"scf_iterations={parsed_gs.get('scf_iterations', 0)}, returncode={rc}, "
                    f"restart_exists={os.path.isdir(restart_dir)})."
                )
                print(f"[WARN] {skip_reason}")
                response_data["status"] = "warning"
                response_data["molecular"]["casida_executed"] = False
                response_data["molecular"]["casida_skipped_reason"] = skip_reason
                response_data["molecular"]["casida"] = {
                    "excitations": [],
                    "energies_ev": [],
                    "oscillator_strengths": [],
                    "warning": skip_reason,
                }
            elif calc_mode == "vib":
                skip_reason = (
                    f"Vib skipped because GS is not ready (converged={parsed_gs.get('converged', False)}, "
                    f"scf_iterations={parsed_gs.get('scf_iterations', 0)}, returncode={rc}, "
                    f"restart_exists={os.path.isdir(restart_dir)})."
                )
                print(f"[WARN] {skip_reason}")
                response_data["status"] = "warning"
                response_data["molecular"]["vib_executed"] = False
                response_data["molecular"]["vib_skipped_reason"] = skip_reason
                response_data["molecular"]["vib_modes"] = {
                    "modes": [], "frequencies_cm": [], "ir_intensities": [], "warning": skip_reason,
                }

        else:
            # 1D Local Physics mode outputs
            static_dir = os.path.join(work_dir, "static")
            wfs_data = parse_octopus_wfs_1d(static_dir)
            response_data["x_grid"] = wfs_data["x_grid"]
            response_data["potential"] = wfs_data["potential"]
            response_data["wavefunctions"] = wfs_data["wavefunctions"]

        explanation_meta = None if skip_run_explanation else write_run_explanation(work_dir, config, response_data)
        if explanation_meta:
            response_data["run_explanation"] = explanation_meta
            if response_data.get("molecular") is not None:
                response_data["molecular"]["run_explanation"] = explanation_meta

        return response_data

    except asyncio.TimeoutError:
        return {"status": "error", "message": "Octopus computation timed out"}
    except Exception as e:
        err_text = (str(e) or repr(e) or e.__class__.__name__).strip()
        print(f"[ERROR] solve_handler: {err_text}")
        traceback.print_exc()
        return {"status": "error", "message": err_text}
    finally:
        if exec_strategy == "hpc" and runs_dir:
            cleanup_octopus_run_dirs(runs_dir, active_run_dir=work_dir)


# ─── VASP Calculation ──────────────────────────────────────────────

async def run_vasp_calculation(config: dict) -> dict:
    """Run a VASP DFT calculation via PBS and return parsed results.

    Supports NELECT-based charge control for ΔSCF ionization potential
    (impossible with Octopus 16).

    VASP binaries and libraries must be accessible on the HPC server.
    Requires PBS job scheduler."""
    calc_mode = str(config.get("calcMode", "gs")).strip().lower()
    molecule_raw = config.get("octopusMolecule", config.get("molecule", config.get("moleculeName", config.get("molecule_name", ""))))
    molecule_name = (
        molecule_raw.get("name", "") if isinstance(molecule_raw, dict)
        else str(molecule_raw or "")
    )
    custom_atoms = config.get("customAtoms")
    elements = []

    if custom_atoms and isinstance(custom_atoms, list):
        for a in custom_atoms:
            sym = a.get("symbol", a.get("element", "H"))
            if sym.capitalize() not in elements:
                elements.append(sym.capitalize())
    elif molecule_name.upper() in vasp_backend._MOLECULES:
        mol_data = vasp_backend._MOLECULES[molecule_name.upper()]
        for sym, *_ in mol_data["atoms"]:
            if sym.capitalize() not in elements:
                elements.append(sym.capitalize())
    elif molecule_name in vasp_backend._ATOMIC_COORDS:
        elements.append(molecule_name.capitalize())
    elif molecule_name:
        # Try to parse as a chemical formula (e.g. "H2O" → H, O; "CH4" → C, H)
        _formula_syms = re.findall(r'[A-Z][a-z]?', molecule_name)
        if _formula_syms:
            for sym in _formula_syms:
                if sym.capitalize() not in elements:
                    elements.append(sym.capitalize())
        else:
            # Single element name
            elements.append(molecule_name.capitalize())
    # else: molecule_name is empty → elements stays empty → handled by error check below

    print(f"[DEBUG] run_vasp_calculation: system={molecule_name} elements={elements}")

    # Determine execution strategy
    exec_strategy = os.environ.get("OCTOPUS_EXEC_STRATEGY", "").strip().lower()
    if exec_strategy not in ("direct", "hpc"):
        exec_strategy = "hpc" if (shutil.which("qsub") and shutil.which("qstat")) else "direct"

    # ── Pre-flight checks ──────────────────────────────────────────
    # VASP binary
    if not os.path.isfile(vasp_backend.VASP_BIN):
        return {"status": "error", "message": f"VASP binary not found: {vasp_backend.VASP_BIN}"}
    # POTCAR directory
    if not os.path.isdir(vasp_backend.VASP_POTCARS_DIR):
        return {"status": "error", "message": f"POTCARS directory not found: {vasp_backend.VASP_POTCARS_DIR}"}
    # Required elements
    if not elements:
        return {"status": "error", "message": "No elements found in molecule/atom specification"}

    # Disk space check (warn if < 1 GB free in work directory parent)
    try:
        import shutil as _shutil
        disk_usage = _shutil.disk_usage(os.path.dirname(resolve_output_dir()))
        free_gb = disk_usage.free / (1024 ** 3)
        if free_gb < 1.0:
            print(f"[WARN] Low disk space: {free_gb:.1f} GB free")
    except Exception:
        pass  # Disk check is advisory only

    runs_dir = os.path.join(resolve_output_dir(), "runs")
    os.makedirs(runs_dir, exist_ok=True)
    work_dir = os.path.join(runs_dir, "vasp_latest")
    # Clean previous run artifacts to prevent WAVECAR/CHGCAR leakage
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    try:
        # Generate VASP input files
        incar = vasp_backend.generate_vasp_incar(config)
        poscar = vasp_backend.generate_vasp_poscar(config)
        kpoints = vasp_backend.generate_vasp_kpoints(config)

        # Assemble POTCAR
        potcar = vasp_backend.assemble_potcar(elements)

        # Write input files
        for fname, content in [
            ("INCAR", incar), ("POSCAR", poscar),
            ("KPOINTS", kpoints), ("POTCAR", potcar),
        ]:
            path = os.path.join(work_dir, fname)
            with open(path, "w") as f:
                f.write(content)
            print(f"[DEBUG] Wrote {fname} to {path}")

        # Execute
        if exec_strategy == "hpc":
            ncpus = int(config.get("octopusNcpus", config.get("ncpus", 1)))
            queue = os.environ.get("OCTOPUS_PBS_QUEUE", "workq")
            walltime = pbs_walltime or os.environ.get("OCTOPUS_PBS_WALLTIME", "01:00:00")
            job_name = os.environ.get("OCTOPUS_PBS_JOB_NAME", "dirac_vasp")

            pbs_script = vasp_backend.build_vasp_pbs_script(
                work_dir=work_dir, queue=queue, ncpus=ncpus,
                walltime=walltime, job_name=job_name,
            )
            pbs_path = os.path.join(work_dir, "vasp_job.pbs")
            with open(pbs_path, "w") as f:
                f.write(pbs_script)

            # Submit via qsub and poll
            import asyncio
            qsub_proc = await asyncio.create_subprocess_exec(
                "qsub", pbs_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_data, stderr_data = await qsub_proc.communicate()
            qsub_output = (stdout_data + stderr_data).decode("utf-8", errors="replace").strip()
            print(f"[DEBUG] qsub output: {qsub_output}")

            job_id = None
            m = re.search(r"(\d+\.\w+)", qsub_output)
            if m:
                job_id = m.group(1)
            if not job_id:
                return {"status": "error", "message": f"PBS submission failed: {qsub_output}"}

            # Poll for completion
            qstat_bin = "qstat"
            poll_interval = int(os.environ.get("OCTOPUS_PBS_POLL_INTERVAL", "3"))
            timeout = int(os.environ.get("OCTOPUS_PBS_CMD_TIMEOUT_SECONDS", "1800"))
            elapsed = 0
            state = "Q"
            outcar_path = os.path.join(work_dir, "OUTCAR")

            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                proc = await asyncio.create_subprocess_exec(
                    qstat_bin, "-f", job_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out, err = await proc.communicate()
                qstat_text = (out + err).decode("utf-8", errors="replace")
                if proc.returncode != 0:
                    # Job may have completed and left queue — check output
                    if os.path.exists(outcar_path):
                        print(f"[DEBUG] qstat failed (job likely done), OUTCAR exists → treating as complete")
                        state = "C"
                        break
                    continue
                m_state = re.search(r"job_state\s*=\s*(\w+)", qstat_text)
                if m_state:
                    state = m_state.group(1)
                if state in ("C", "E", "F"):
                    break

            if state not in ("C",):
                # Final check: OUTCAR may exist even if PBS tracking lost the job
                if os.path.exists(outcar_path):
                    print(f"[DEBUG] PBS timeout but OUTCAR exists → treating as complete")
                else:
                    return {"status": "error", "message": f"PBS job {job_id} did not complete (state={state})"}

        else:
            # Direct execution
            import asyncio
            proc = await asyncio.create_subprocess_exec(
                vasp_backend.VASP_BIN,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env={
                    **os.environ,
                    "LD_LIBRARY_PATH": (
                        vasp_backend.VASP_LD_LIBRARY_PATH + ":"
                        + os.environ.get("LD_LIBRARY_PATH", "")
                    ),
                },
            )
            try:
                direct_timeout = int(os.environ.get("VASP_DIRECT_TIMEOUT_SECONDS", "600"))
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=direct_timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return {"status": "error", "message": f"VASP direct execution timed out after {direct_timeout}s"}

        # Parse results
        outcar_path = os.path.join(work_dir, "OUTCAR")
        results = vasp_backend.parse_vasp_outcar(outcar_path)

        # Parse EIGENVAL if available
        eigenval_path = os.path.join(work_dir, "EIGENVAL")
        if os.path.exists(eigenval_path):
            eigen_data = vasp_backend.parse_vasp_eigenval(eigenval_path)
            results["band_structure"] = eigen_data

        response_data = {
            "status": "success" if results.get("scf_converged") else "convergence_warning",
            "backend": "vasp",
            "execution_strategy": exec_strategy,
            "work_dir": work_dir,
            "total_energy_ev": results["total_energy_ev"],
            "fermi_energy_ev": results["fermi_energy_ev"],
            "magnetization": results["magnetization"],
            "eigenvalues_ev": results["band_energies_ev"],
            "occupations": results["occupations"],
            "nelect": results["nelect"],
            "nbands": results["nbands"],
            "scf_iterations": results["scf_iterations"],
            "elements": elements,
            "molecule": molecule_name,
        }

        return sanitize_floats(response_data)

    except Exception as e:
        err_text = (str(e) or repr(e) or e.__class__.__name__).strip()
        print(f"[ERROR] run_vasp_calculation: {err_text}")
        traceback.print_exc()
        return {"status": "error", "message": err_text}


# ─── REST endpoints ───────────────────────────────────────────────

async def health_handler(request: Request):
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "engine": "octopus-16.0"})


async def solve_handler(request: Request):
    """REST endpoint compatible with physics_engine.ts pipeline."""
    print(f"[DEBUG] solve_handler received request")
    try:
        config = await request.json()
        print(f"[DEBUG] solve_handler parsed config: {config}")
    except Exception as e:
        print(f"[ERROR] solve_handler failed to parse JSON: {e}")
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    print(f"[DEBUG] solve_handler calling run_octopus_calculation")
    result = await run_octopus_calculation(config)
    print(f"[DEBUG] solve_handler received result: {result.get('status')}")

    # Format response to match the existing PhysicsResult interface
    eigenvalues = result.get("eigenvalues", [])
    x_grid = result.get("x_grid", [])
    potential_V = result.get("potential", [])
    wfs = result.get("wavefunctions", [])
    
    # Format wavefunctions for frontend (assuming non-relativistic / single component for now)
    formatted_wfs = []
    for w in wfs:
        formatted_wfs.append({
            "psi_up": w,
            "psi_down": [0.0] * len(w)
        })

    # If no wfs parsed, fallback to empty arrays
    if not formatted_wfs:
        formatted_wfs = [{"psi_up": [], "psi_down": []} for _ in eigenvalues]

    response = {
        "status": result.get("status", "error"),
        "eigenvalues": eigenvalues,
        "total_energy": result.get("total_energy") or (result.get("molecular", {}) or {}).get("total_energy_hartree"),
        "converged": result.get("converged", False),
        "scf_iterations": result.get("scf_iterations", 0),
        "engine": result.get("engine", "octopus-16.0"),
        "scheduler": result.get("scheduler"),
        "problemType": "molecular" if result.get("molecular") else config.get("problemType", "boundstate"),
        "matrix_info": {
            "size": len(x_grid) if x_grid else len(eigenvalues),
            "non_zeros": 0,
            "isHermitian": True,
        },
        "x_grid": x_grid,
        "potential_V": potential_V,
        "wavefunctions": formatted_wfs,
        "molecular": result.get("molecular"),
        "run_explanation": result.get("run_explanation"),
        "density_1d": result.get("density_1d", []),
        "potential_components": result.get("potential_components"),
        "stdout_tail": result.get("stdout_tail", ""),
        "stderr_tail": result.get("stderr_tail", ""),
        "returncode": result.get("returncode"),
        "casida_excitations": result.get("casida_excitations") or (result.get("molecular", {}).get("casida", {}).get("excitations", [])),
        "casida_executed": result.get("casida_executed") or result.get("molecular", {}).get("casida_executed", False),
        "casida_data": result.get("molecular", {}).get("casida"),
        "td_executed": result.get("td_executed") or result.get("molecular", {}).get("td_executed", False),
        "td_spectrum": result.get("td_spectrum") or result.get("molecular", {}).get("optical_spectrum"),
        "message": (
            result.get("stderr_tail")
            or result.get("message")
            or result.get("stdout_tail")
            or "Octopus engine returned an error with no diagnostic text"
        ),
    }
    return JSONResponse(sanitize_floats(response))


async def solve_vasp_handler(request: Request):
    """REST endpoint for VASP DFT calculations with PAW pseudopotentials."""
    print("[DEBUG] solve_vasp_handler received request")
    try:
        config = await request.json()
        print(f"[DEBUG] solve_vasp_handler parsed config: {config}")
    except Exception as e:
        print(f"[ERROR] solve_vasp_handler failed to parse JSON: {e}")
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    result = await run_vasp_calculation(config)
    print(f"[DEBUG] solve_vasp_handler received result: {result.get('status')}")

    return JSONResponse(sanitize_floats({
        "status": result.get("status", "error"),
        "backend": "vasp",
        "total_energy_ev": result.get("total_energy_ev"),
        "fermi_energy_ev": result.get("fermi_energy_ev"),
        "magnetization": result.get("magnetization"),
        "eigenvalues_ev": result.get("eigenvalues_ev", []),
        "occupations": result.get("occupations", []),
        "nelect": result.get("nelect"),
        "nbands": result.get("nbands"),
        "scf_iterations": result.get("scf_iterations", 0),
        "execution_strategy": result.get("execution_strategy"),
        "molecule": result.get("molecule"),
        "elements": result.get("elements", []),
        "message": result.get("message"),
    }))


# ─── MCP tool handlers (kept for MCP SDK clients) ─────────────────
sse_transport = None

if MCP_AVAILABLE:
    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name == "run_octopus":
            result = await run_octopus_calculation(arguments)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        if name == "run_vasp":
            result = await run_vasp_calculation(arguments)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        if name == "parse_results":
            run_dir = arguments.get("run_dir", "/workspace/output")
            static_dir = os.path.join(run_dir)
            info_path = os.path.join(static_dir, "info")
            out: dict = {"run_dir": run_dir}
            if os.path.exists(info_path):
                out["info"] = parse_octopus_info(info_path)
            wfs = parse_octopus_wfs_1d(static_dir)
            out["available_states"] = len(wfs.get("wavefunctions", []))
            out["x_grid"] = wfs.get("x_grid", [])
            out["potential"] = wfs.get("potential", [])
            out["wavefunctions"] = wfs.get("wavefunctions", [])
            return [types.TextContent(type="text", text=json.dumps(out, indent=2))]
        return [types.TextContent(type="text", text="Unknown tool.")]

    @mcp_server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="run_octopus",
                description="Run an Octopus DFT calculation with the given physics config.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "calcMode": {"type": "string", "description": "Calculation mode: 'gs' (ground state, default), 'td' (time-dependent delta-kick after GS), 'casida' (linear response excitation energies after GS, best for finite molecules), 'go' (geometry optimization). Use with GOMethod for GO."},
                        "engineMode": {"type": "string", "description": "'octopus3D' (molecular DFT, default) or 'local1D' (model potentials)."},
                        "speciesMode": {"type": "string", "description": "Pseudopotential mode: 'builtin_standard' (default, no explicit Species block), 'standard' (PSF Troullier-Martins), 'pseudo' (UPF files), 'formula' (soft-core Coulomb), 'all_electron'."},
                        "octopusMolecule": {"type": "string", "description": "Built-in molecule name: H2, H2O, CH4, 'N_atom', NH3, CO, Si, etc."},
                        "octopusSpacing": {"type": "number", "description": "Grid spacing in Bohr (or with unit suffix like '0.18*angstrom')."},
                        "octopusRadius": {"type": "number", "description": "Simulation box radius in Bohr."},
                        "xcFunctional": {"type": "string", "description": "XC functional. Default: 'lda_x+lda_c_pz'. Also: 'gga_x_pbe+gga_c_pbe', 'hartree_fock', 'exx'."},
                        "mixingScheme": {"type": "string", "description": "SCF mixing scheme. Default: 'broyden'."},
                        "spinComponents": {"type": "string", "description": "'unpolarized' (default) or 'polarized'."},
                        "extraStates": {"type": "integer", "description": "Extra unoccupied states for SCF convergence. Default: 1 (GS), 12 (TD)."},
                        "GOMethod": {"type": "string", "description": "Geometry optimization method: 'fire', 'steepest_descent', 'cg', 'bfgs'. Also sets CalculationMode=go."},
                        "GOTolerance": {"type": "number", "description": "GO force tolerance. Default: 0.0001."},
                        "GOMaxIter": {"type": "integer", "description": "Max GO iterations. Default: 200."},
                        "maxScfIterations": {"type": "integer", "description": "Max SCF iterations. Default: 200."},
                        "scfTolerance": {"type": "number", "description": "SCF density tolerance. Default: 1e-6."},
                        "periodicDimensions": {"type": "integer", "description": "Number of periodic dimensions for solids (e.g., 3 for Si)."},
                        "latticeVectors": {"type": "array", "description": "Lattice vectors for periodic systems."},
                        "kpointsGrid": {"type": "string", "description": "K-points grid string (e.g., '2 2 2')."},
                        "octopusTdSteps": {"type": "integer", "description": "Number of TD propagation steps. Default: 200."},
                        "TDTimeStep": {"type": "number", "description": "TD time step. Default: 0.002."},
                        "tdExcitationType": {"type": "string", "description": "TD excitation: 'delta' (default), 'gaussian', 'sin', 'continuous_wave'."},
                        "tdPolarization": {"type": "integer", "description": "Kick polarization direction: 1=x, 2=y, 3=z. Default: 1."},
                        "tdFieldAmplitude": {"type": "number", "description": "TD field amplitude. Default: 0.01."},
                        "customAtoms": {"type": "array", "description": "Custom atom list: [{'symbol': 'H', 'x': 0, 'y': 0, 'z': 0}, ...]."},
                        "casidaKohnShamStates": {"type": "string", "description": "KS state range for Casida linear response, e.g. '1-8'. Default: '1-8'."},
                        "lcaoMaximumOrbitalRadius": {"type": "number", "description": "Cap LCAO orbital radius (Bohr) for builtin_standard species with large orbitals (e.g. N). Default: 20."},
                        "casidaTransitionDensities": {"type": "integer", "description": "Number of excitations to compute transition densities for. Default: 0."},
                        "fastPath": {"type": "boolean", "description": "Enable fast-path execution with reduced defaults."},
                    }
                }
            ),
            types.Tool(
                name="run_vasp",
                description="Run VASP DFT calculation with PAW pseudopotentials via PBS or direct execution. Supports NELECT-based charge control for ΔSCF ionization potential (impossible with Octopus 16). Currently supports H and O elements (PAW_RPBE).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "calcMode": {"type": "string", "description": "Calculation mode: 'gs' (ground state, default), 'go' (geometry optimization)."},
                        "octopusMolecule": {"type": "string", "description": "Built-in molecule or atom: 'H2O', 'CH4', 'H', 'O', 'N', 'C'."},
                        "customAtoms": {"type": "array", "description": "Custom atom list: [{'symbol': 'H', 'x': 0, 'y': 0, 'z': 0}, ...]."},
                        "xcFunctional": {"type": "string", "description": "XC functional: 'PBE' (default), 'LDA', 'HF'."},
                        "spinComponents": {"type": "string", "description": "'unpolarized' (default) or 'polarized'."},
                        "encut": {"type": "integer", "description": "Plane-wave cutoff in eV. Default: 400."},
                        "ediff": {"type": "number", "description": "SCF convergence criterion. Default: 1e-6."},
                        "ismear": {"type": "integer", "description": "Smearing method: 0=Gaussian (default)."},
                        "sigma": {"type": "number", "description": "Smearing width in eV. Default: 0.01."},
                        "nelect": {"type": "number", "description": "Total electron count. Set to N-1 for ΔSCF cation calculation."},
                        "netCharge": {"type": "number", "description": "Net charge. Alternative to nelect."},
                        "nbands": {"type": "integer", "description": "Number of bands."},
                        "prec": {"type": "string", "description": "Precision: 'Normal' (default), 'Accurate'."},
                        "vaspBox": {"type": "number", "description": "Box size in Angstrom. Default: 10.0."},
                        "kpointsType": {"type": "string", "description": "K-point type: 'gamma' (default) or 'monkhorst'."},
                        "extraIncarTags": {"type": "object", "description": "Extra INCAR tags as key-value pairs."},
                    }
                }
            ),
            types.Tool(
                name="parse_results",
                description="Parse Octopus output files from a completed run directory. Returns eigenvalues, wavefunctions, and convergence data.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "run_dir": {"type": "string", "description": "Linux path to the output directory (e.g. /workspace/output)"},
                    },
                    "required": ["run_dir"],
                }
            ),
        ]

    async def sse_handler(request: Request):
        global sse_transport
        transport = SseServerTransport("/messages")
        sse_transport = transport
        async def run_server():
            try:
                await mcp_server.run(transport.async_stream(), transport.async_send)
            except Exception as e:
                print(f"SSE Server error: {e}")
        asyncio.create_task(run_server())
        return await transport.handle_sse(request)

    async def messages_handler(request: Request):
        global sse_transport
        if sse_transport is None:
            return JSONResponse({"error": "No SSE connection established"}, status_code=400)
        await sse_transport.handle_post_message(request)
        return JSONResponse({"status": "accepted"})
else:
    async def sse_handler(_request: Request):
        return JSONResponse({"error": "MCP package not installed"}, status_code=503)

    async def messages_handler(_request: Request):
        return JSONResponse({"error": "MCP package not installed"}, status_code=503)


from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# ─── Starlette app with all routes ────────────────────────────────

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

routes = [
    Route("/health", endpoint=health_handler, methods=["GET"]),
    Route("/solve", endpoint=solve_handler, methods=["POST"]),
    Route("/solve_vasp", endpoint=solve_vasp_handler, methods=["POST"]),
]

if MCP_AVAILABLE:
    routes.append(Route("/sse", endpoint=sse_handler, methods=["GET"]))
    routes.append(Route("/messages", endpoint=messages_handler, methods=["POST"]))

starlette_app = Starlette(routes=routes, middleware=middleware)

if __name__ == "__main__":
    print("Starting Octopus Physics MCP Server on port 8000...")
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level="debug")
