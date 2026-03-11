"""
render_mpl.py  —  Dark-themed matplotlib renderer for Octopus output.

Usage:
    python render_mpl.py <input_file> <plot_type> <output_png> [isovalue] [colormap]

plot_type:
  wavefunction_1d      — 1D wavefunction from .y=0,z=0 file
  density_2d           — 1D density line from .y=0,z=0 file  (legacy fallback)
  density_2d_cube      — True 2D heatmap: 3 orthogonal slices from .cube file
  density_3d_iso       — 3D isosurface panels from .cube file (4 panels + MIP)
  wavefunction_2d_cube — Re(ψ) + |ψ|² 2D slice from .cube file
"""
import sys
import os
import gc
import numpy as np
import matplotlib
matplotlib.use("Agg")   # headless
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Dark theme ────────────────────────────────────────────────────
BG = "#0a0e1a"
ACCENT = "#00d4ff"
ACCENT2 = "#f472b6"
MUTED = "#8892a4"
GRID_COLOR = "#1f2937"


def apply_dark_style(fig, ax):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID_COLOR)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.title.set_color("#e2e8f0")
    ax.grid(True, color=GRID_COLOR, linewidth=0.6, linestyle="--", alpha=0.6)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.tick_params(which="minor", colors=GRID_COLOR, length=2)


# ══════════════════════════════════════════════════════════════════
# Gaussian Cube File Parser
# ══════════════════════════════════════════════════════════════════

def parse_cube_file(path: str):
    """
    Parse a Gaussian .cube file (Octopus output format).
    Returns: (data, x, y, z)
      data  — numpy float32 array shape (NX, NY, NZ)
      x,y,z — 1D coordinate arrays in Bohr
    """
    with open(path, 'r') as f:
        lines = f.readlines()

    # Lines 0-1: comments
    # Line 2: n_atoms  ox  oy  oz
    p = lines[2].split()
    n_atoms = abs(int(p[0]))   # negative for MO cubes
    ox, oy, oz = float(p[1]), float(p[2]), float(p[3])

    # Lines 3-5: NX/NY/NZ and orthogonal step vectors
    p3 = lines[3].split(); NX = int(p3[0]); dx = abs(float(p3[1]))
    p4 = lines[4].split(); NY = int(p4[0]); dy = abs(float(p4[2]))
    p5 = lines[5].split(); NZ = int(p5[0]); dz = abs(float(p5[3]))

    data_start = 6 + n_atoms

    raw = []
    for line in lines[data_start:]:
        raw.extend(float(v) for v in line.split())

    expected = NX * NY * NZ
    raw = raw[:expected]
    data = np.array(raw, dtype=np.float32).reshape((NX, NY, NZ))

    x = ox + np.arange(NX) * dx
    y = oy + np.arange(NY) * dy
    z = oz + np.arange(NZ) * dz

    del raw
    gc.collect()
    return data, x, y, z


# ══════════════════════════════════════════════════════════════════
# Shared helper
# ══════════════════════════════════════════════════════════════════

def _dark_cbar(fig, im, ax, label: str):
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(colors=MUTED, labelsize=7)
    cbar.set_label(label, color=MUTED, fontsize=8)
    cbar.outline.set_edgecolor(GRID_COLOR)
    return cbar


# ══════════════════════════════════════════════════════════════════
# 1D Renderers (axis_x files)
# ══════════════════════════════════════════════════════════════════

def parse_octopus_slice(path: str):
    """Parse Octopus .y=0,z=0 file (x, Re[, Im] columns)."""
    cols = []
    with open(path, "r") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            try:
                cols.append([float(p) for p in parts])
            except ValueError:
                continue
    if not cols:
        raise ValueError(f"No data in {path}")
    arr = np.array(cols)
    x = arr[:, 0]
    col1 = arr[:, 1] if arr.shape[1] > 1 else np.zeros_like(x)
    col2 = arr[:, 2] if arr.shape[1] > 2 else None
    return x, col1, col2


def render_wavefunction_1d(input_path: str, output_png: str):
    x, re_psi, im_psi = parse_octopus_slice(input_path)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    apply_dark_style(fig, ax)

    ax.plot(x, re_psi, color=ACCENT, linewidth=1.8, label=r"Re($\psi$)")
    ax.fill_between(x, re_psi, alpha=0.12, color=ACCENT)

    if im_psi is not None:
        ax.plot(x, im_psi, color=ACCENT2, linewidth=1.4, linestyle="--", label=r"Im($\psi$)")

    ax.axhline(0, color=MUTED, linewidth=0.5, alpha=0.5)
    ax.set_xlabel("x  (Bohr)", fontsize=9)
    ax.set_ylabel(r"$\psi(x)$  (arb. units)", fontsize=9)

    fname = os.path.basename(input_path)
    state_label = ""
    if "st" in fname:
        import re
        m = re.search(r"st0*(\d+)", fname)
        if m:
            state_label = f" — State {m.group(1)}"

    ax.set_title(f"Kohn-Sham Wavefunction{state_label}", fontsize=10, pad=8)
    leg = ax.legend(fontsize=8, framealpha=0.1, edgecolor=GRID_COLOR, facecolor=BG)
    for text in leg.get_texts():
        text.set_color("#e2e8f0")

    plt.tight_layout(pad=1.2)
    fig.savefig(output_png, dpi=120, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"[mpl] Saved wavefunction_1d: {output_png}")


def render_density_2d_legacy(input_path: str, output_png: str):
    """Legacy 1D density line (fallback when no cube file available)."""
    x, rho, _ = parse_octopus_slice(input_path)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    apply_dark_style(fig, ax)

    ax.plot(x, rho, color="#a78bfa", linewidth=1.8, label=r"$\rho(x)$")
    ax.fill_between(x, rho, where=rho >= 0, alpha=0.15, color="#a78bfa")

    ax.axhline(0, color=MUTED, linewidth=0.5, alpha=0.5)
    ax.set_xlabel("x  (Bohr)", fontsize=9)
    ax.set_ylabel(r"$\rho(x)$  (e/Bohr)", fontsize=9)
    ax.set_title("Electron Density — y=0, z=0 slice (1D, no cube)", fontsize=10, pad=8)
    leg = ax.legend(fontsize=8, framealpha=0.1, edgecolor=GRID_COLOR, facecolor=BG)
    for text in leg.get_texts():
        text.set_color("#e2e8f0")

    plt.tight_layout(pad=1.2)
    fig.savefig(output_png, dpi=120, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"[mpl] Saved density_2d legacy: {output_png}")


# ══════════════════════════════════════════════════════════════════
# 2D Heatmap from Cube File — Three Orthogonal Slices
# ══════════════════════════════════════════════════════════════════

def render_density_2d_cube(cube_path: str, output_png: str, colormap: str = "plasma"):
    """
    True 2D electron density map — three orthogonal slices from .cube file:
    XY plane (z=center), XZ plane (y=center), YZ plane (x=center).
    """
    data, x, y, z = parse_cube_file(cube_path)

    ix = len(x) // 2
    iy = len(y) // 2
    iz = len(z) // 2

    sl_xy = np.abs(data[:, :, iz]).T    # (NY, NX)
    sl_xz = np.abs(data[:, iy, :]).T    # (NZ, NX)
    sl_yz = np.abs(data[ix, :, :]).T    # (NZ, NY)

    vmax = max(sl_xy.max(), sl_xz.max(), sl_yz.max())
    if vmax <= 0:
        vmax = 1.0

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=110)
    fig.patch.set_facecolor(BG)

    panel_data = [
        (sl_xy, x, y, "x (Bohr)", "y (Bohr)", f"XY  (z={z[iz]:.2f} Bohr)"),
        (sl_xz, x, z, "x (Bohr)", "z (Bohr)", f"XZ  (y={y[iy]:.2f} Bohr)"),
        (sl_yz, y, z, "y (Bohr)", "z (Bohr)", f"YZ  (x={x[ix]:.2f} Bohr)"),
    ]

    for ax, (sl, xa, ya, xl, yl, ttl) in zip(axes, panel_data):
        apply_dark_style(fig, ax)
        im = ax.imshow(
            sl, origin="lower", aspect="auto",
            extent=[xa[0], xa[-1], ya[0], ya[-1]],
            cmap=colormap, vmin=0, vmax=vmax,
            interpolation="bilinear",
        )
        try:
            Xa, Ya = np.meshgrid(xa, ya)
            ax.contour(Xa, Ya, sl, levels=5, colors="white", alpha=0.25, linewidths=0.5)
        except Exception:
            pass
        _dark_cbar(fig, im, ax, "ρ (e/Bohr³)")
        ax.set_xlabel(xl, fontsize=8)
        ax.set_ylabel(yl, fontsize=8)
        ax.set_title(ttl, fontsize=9, pad=5, color="#e2e8f0")

    fig.suptitle("Electron Density — Orthogonal Cross Sections",
                 color="#e2e8f0", fontsize=11, fontweight="light", y=1.01)
    plt.tight_layout(pad=1.5)
    fig.savefig(output_png, dpi=110, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    del data
    gc.collect()
    print(f"[mpl] Saved density_2d_cube: {output_png}")


# ══════════════════════════════════════════════════════════════════
# 3D Isosurface Panels from Cube File
# ══════════════════════════════════════════════════════════════════

def render_density_3d_iso(cube_path: str, output_png: str,
                           isovalue: float = None, colormap: str = "hot"):
    """
    3D electron density: 4 panels (XY, XZ, YZ slices + max-intensity projection).
    Isosurface level shown as a cyan contour on each slice.
    No VisIt required — pure matplotlib.
    """
    data, x, y, z = parse_cube_file(cube_path)

    vmax = float(data.max())
    if vmax <= 0:
        vmax = 1.0
    data_norm = data / vmax

    if isovalue is None:
        isovalue = 0.15   # 15% of maximum density

    ix = len(x) // 2
    iy = len(y) // 2
    iz = len(z) // 2

    sl_xy = data_norm[:, :, iz].T     # (NY, NX)
    sl_xz = data_norm[:, iy, :].T     # (NZ, NX)
    sl_yz = data_norm[ix, :, :].T     # (NZ, NY)
    mip   = data_norm.max(axis=2).T   # max projection along z: (NY, NX)

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=100)
    fig.patch.set_facecolor(BG)

    panels = [
        (axes[0, 0], sl_xy, x, y, "x (Bohr)", "y (Bohr)", f"XY  z={z[iz]:.2f} Bohr"),
        (axes[0, 1], sl_xz, x, z, "x (Bohr)", "z (Bohr)", f"XZ  y={y[iy]:.2f} Bohr"),
        (axes[1, 0], sl_yz, y, z, "y (Bohr)", "z (Bohr)", f"YZ  x={x[ix]:.2f} Bohr"),
        (axes[1, 1], mip,   x, y, "x (Bohr)", "y (Bohr)", "Max Intensity Projection (z-axis)"),
    ]

    for ax, sl, xa, ya, xl, yl, ttl in panels:
        apply_dark_style(fig, ax)
        im = ax.imshow(
            sl, origin="lower", aspect="auto",
            extent=[xa[0], xa[-1], ya[0], ya[-1]],
            cmap=colormap, vmin=0, vmax=1.0,
            interpolation="bilinear",
        )
        try:
            Xa, Ya = np.meshgrid(xa, ya)
            ax.contour(Xa, Ya, sl, levels=[isovalue],
                       colors="#00d4ff", linewidths=1.2, alpha=0.85)
            ax.contour(Xa, Ya, sl, levels=[isovalue * 0.5],
                       colors="#00d4ff", linewidths=0.5, alpha=0.35, linestyles="--")
        except Exception:
            pass
        _dark_cbar(fig, im, ax, "ρ/ρ_max")
        ax.set_xlabel(xl, fontsize=8)
        ax.set_ylabel(yl, fontsize=8)
        ax.set_title(ttl, fontsize=9, pad=5, color="#e2e8f0")

    fig.suptitle(
        f"3D Electron Density  —  Isosurface iso={isovalue:.2f}  (cyan contour)",
        color="#e2e8f0", fontsize=11, fontweight="light", y=1.01,
    )
    plt.tight_layout(pad=1.8)
    fig.savefig(output_png, dpi=100, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    del data, data_norm
    gc.collect()
    print(f"[mpl] Saved density_3d_iso: {output_png}")


# ══════════════════════════════════════════════════════════════════
# 2D Wavefunction from Cube File
# ══════════════════════════════════════════════════════════════════

def render_wavefunction_2d_cube(cube_path: str, output_png: str, colormap: str = "RdBu"):
    """
    Wavefunction 2D visualization: Re(ψ) + |ψ|² side by side, z=center slice.
    """
    data, x, y, z = parse_cube_file(cube_path)
    iz = len(z) // 2

    psi = data[:, :, iz].T    # (NY, NX)
    psi_sq = psi ** 2

    import re as _re
    fname = os.path.basename(cube_path)
    m = _re.search(r"st0*(\d+)", fname)
    state_label = f" — State {m.group(1)}" if m else ""

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=110)
    fig.patch.set_facecolor(BG)
    extent = [x[0], x[-1], y[0], y[-1]]

    # Left: Re(ψ) with diverging colormap centered at 0
    ax = axes[0]
    apply_dark_style(fig, ax)
    vabs = max(abs(psi.min()), abs(psi.max()), 1e-10)
    im = ax.imshow(psi, origin="lower", aspect="auto", extent=extent,
                   cmap=colormap, vmin=-vabs, vmax=vabs, interpolation="bilinear")
    try:
        Xa, Ya = np.meshgrid(x, y)
        ax.contour(Xa, Ya, psi, levels=8, colors="white", alpha=0.25, linewidths=0.5)
        ax.contour(Xa, Ya, psi, levels=[0], colors="#aaaaaa", linewidths=1.0, linestyles="--")
    except Exception:
        pass
    _dark_cbar(fig, im, ax, "ψ (arb. u.)")
    ax.set_xlabel("x (Bohr)", fontsize=9)
    ax.set_ylabel("y (Bohr)", fontsize=9)
    ax.set_title(f"Re(ψ){state_label}", fontsize=10, pad=6, color="#e2e8f0")

    # Right: |ψ|²
    ax2 = axes[1]
    apply_dark_style(fig, ax2)
    im2 = ax2.imshow(psi_sq, origin="lower", aspect="auto", extent=extent,
                     cmap="plasma", vmin=0, interpolation="bilinear")
    _dark_cbar(fig, im2, ax2, "|ψ|² (arb. u.)")
    ax2.set_xlabel("x (Bohr)", fontsize=9)
    ax2.set_ylabel("y (Bohr)", fontsize=9)
    ax2.set_title(f"|ψ|² probability density{state_label}", fontsize=10, pad=6, color="#e2e8f0")

    fig.suptitle(f"Kohn-Sham Wavefunction  (z = {z[iz]:.2f} Bohr slice)",
                 color="#e2e8f0", fontsize=11, fontweight="light", y=1.02)
    plt.tight_layout(pad=1.5)
    fig.savefig(output_png, dpi=110, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    del data
    gc.collect()
    print(f"[mpl] Saved wavefunction_2d_cube: {output_png}")


# ══════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python render_mpl.py <input_file> <plot_type> <output_png> [isovalue] [colormap]",
              file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    plot_type  = sys.argv[2]
    out_png    = sys.argv[3]
    raw_iso    = sys.argv[4] if len(sys.argv) > 4 else ''
    isovalue   = float(raw_iso) if raw_iso else None   # empty string → None
    colormap   = sys.argv[5] if len(sys.argv) > 5 else None

    if not os.path.isfile(input_file):
        print(f"[mpl] ERROR: input file not found: {input_file}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)

    if plot_type == "wavefunction_1d":
        render_wavefunction_1d(input_file, out_png)
    elif plot_type == "density_2d":
        render_density_2d_legacy(input_file, out_png)
    elif plot_type == "density_2d_cube":
        render_density_2d_cube(input_file, out_png, colormap=colormap or "plasma")
    elif plot_type == "density_3d_iso":
        render_density_3d_iso(input_file, out_png,
                              isovalue=isovalue, colormap=colormap or "hot")
    elif plot_type == "wavefunction_2d_cube":
        render_wavefunction_2d_cube(input_file, out_png, colormap=colormap or "RdBu")
    else:
        print(f"[mpl] Unknown plot_type: {plot_type}", file=sys.stderr)
        sys.exit(3)
