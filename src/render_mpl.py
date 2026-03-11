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

def render_density_2d_cube(cube_path: str, output_png: str, colormap: str = "plasma",
                           slice_pos: float = None, slice_axis: str = 'z'):
    """
    True 2D electron density map — three orthogonal slices from .cube file.
    slice_axis ('x','y','z') selects which panel is moved by slice_pos.
    The other two panels remain at the box centre.
    """
    data, x, y, z = parse_cube_file(cube_path)

    def _nearest(arr, val):
        if val is None:
            return len(arr) // 2
        return int(np.abs(arr - val).argmin())

    ix = _nearest(x, slice_pos if slice_axis == 'x' else None)
    iy = _nearest(y, slice_pos if slice_axis == 'y' else None)
    iz = _nearest(z, slice_pos if slice_axis == 'z' else None)

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
                           isovalue: float = None, colormap: str = "hot",
                           slice_pos: float = None, slice_axis: str = 'z'):
    """
    Electron cloud visualization: 3D volumetric scatter cloud (left) +
    max-intensity projection with contours (right).
    Shows the actual 3D spatial extent of the electron density, unlike
    the 2D slice mode which repeats the same information.
    """
    from mpl_toolkits.mplot3d import Axes3D   # noqa: F401

    data, x, y, z = parse_cube_file(cube_path)
    vmax = float(data.max())
    if vmax <= 1e-30:
        vmax = 1e-30
    data_norm = data / vmax

    cloud_thresh = isovalue if (isovalue is not None) else 0.05

    # ── Extract voxel coordinates above threshold ─────────────────
    X3, Y3, Z3 = np.meshgrid(x, y, z, indexing='ij')
    mask = data_norm > cloud_thresh
    xs = X3[mask].ravel()
    ys = Y3[mask].ravel()
    zs = Z3[mask].ravel()
    vs = data_norm[mask].ravel()

    # Downsample: weight high-density voxels more (they convey most info)
    MAX_PTS = 4000
    if len(xs) > MAX_PTS:
        p = (vs ** 0.4)
        p /= p.sum()
        idx = np.random.choice(len(xs), MAX_PTS, replace=False, p=p)
        xs, ys, zs, vs = xs[idx], ys[idx], zs[idx], vs[idx]

    # Sort low-density first so high-density paints on top (painter's algo)
    order = np.argsort(vs)
    xs, ys, zs, vs = xs[order], ys[order], zs[order], vs[order]

    # ── Figure layout ─────────────────────────────────────────────
    fig = plt.figure(figsize=(13, 6), dpi=110, facecolor=BG)

    # ── Panel 1: 3D electron cloud scatter ───────────────────────
    ax3d = fig.add_subplot(121, projection='3d', facecolor=BG)

    cmap_fn = plt.get_cmap(colormap)
    # Multi-layer: plot quartile bands with increasing alpha for cloud depth
    bands = [(0.00, 0.20, 0.12, 4),
             (0.20, 0.45, 0.22, 10),
             (0.45, 0.70, 0.40, 24),
             (0.70, 0.90, 0.65, 50),
             (0.90, 1.01, 0.90, 80)]
    for lo, hi, alpha, sz in bands:
        bm = (vs >= lo) & (vs < hi)
        if bm.sum() == 0:
            continue
        colors_rgba = cmap_fn(vs[bm])
        colors_rgba[:, 3] = alpha
        ax3d.scatter(xs[bm], ys[bm], zs[bm],
                     c=colors_rgba, s=sz,
                     depthshade=True, linewidths=0)

    # Axis appearance
    ax3d.xaxis.pane.fill = False
    ax3d.yaxis.pane.fill = False
    ax3d.zaxis.pane.fill = False
    for pane in (ax3d.xaxis.pane, ax3d.yaxis.pane, ax3d.zaxis.pane):
        pane.set_edgecolor(GRID_COLOR)
    ax3d.tick_params(colors=MUTED, labelsize=7)
    ax3d.set_xlabel("x (Bohr)", fontsize=7, color=MUTED, labelpad=2)
    ax3d.set_ylabel("y (Bohr)", fontsize=7, color=MUTED, labelpad=2)
    ax3d.set_zlabel("z (Bohr)", fontsize=7, color=MUTED, labelpad=2)
    ax3d.set_title("Electron Cloud  (3D)", fontsize=9, color="#e2e8f0", pad=6)

    # Equal axes: force same range on all three axes
    _all = np.concatenate([xs, ys, zs])
    _mid = (_all.max() + _all.min()) / 2.0
    _hw  = max((_all.max() - _all.min()) / 2.0, 0.5)
    ax3d.set_xlim(_mid - _hw, _mid + _hw)
    ax3d.set_ylim(_mid - _hw, _mid + _hw)
    ax3d.set_zlim(_mid - _hw, _mid + _hw)
    try:
        ax3d.set_box_aspect([1, 1, 1])
    except Exception:
        pass
    ax3d.view_init(elev=25, azim=45)

    # ── Panel 2: max-intensity projection + contours ──────────────
    ax2d = fig.add_subplot(122)
    apply_dark_style(fig, ax2d)

    mip = data_norm.max(axis=2).T   # (NY, NX) — project along z
    im = ax2d.imshow(
        mip, origin="lower", aspect="equal",
        extent=[x[0], x[-1], y[0], y[-1]],
        cmap=colormap, vmin=0, vmax=1.0,
        interpolation="gaussian",
    )
    Xm, Ym = np.meshgrid(x, y)
    contour_levels = [cloud_thresh, min(0.35, 0.35), min(0.70, 0.70)]
    contour_levels = sorted(set(lv for lv in contour_levels if 0 < lv < 1))
    if contour_levels:
        ax2d.contour(Xm, Ym, mip, levels=contour_levels,
                     colors=["#3b82f6", "#00d4ff", "white"],
                     linewidths=[0.6, 1.1, 1.6],
                     alpha=0.85)
    _dark_cbar(fig, im, ax2d, "ρ/ρ_max")
    ax2d.set_xlabel("x (Bohr)", fontsize=8)
    ax2d.set_ylabel("y (Bohr)", fontsize=8)
    ax2d.set_title("Max-Intensity Projection  (XY plane, z-integrated)",
                   fontsize=9, color="#e2e8f0")

    fig.suptitle(
        f"3D Electron Density  —  cloud threshold {cloud_thresh:.2f}ρ_max  ·  {colormap} colormap",
        color="#e2e8f0", fontsize=10, fontweight="light", y=1.01,
    )
    plt.tight_layout(pad=1.6)
    fig.savefig(output_png, dpi=110, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    del data, data_norm, X3, Y3, Z3
    gc.collect()
    print(f"[mpl] Saved density_3d_cloud: {output_png}")


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
    raw_sp     = sys.argv[6] if len(sys.argv) > 6 else ''
    slice_pos  = float(raw_sp) if raw_sp else None     # slice position in Bohr
    slice_axis = sys.argv[7] if len(sys.argv) > 7 else 'z'  # which axis slice_pos applies to

    if not os.path.isfile(input_file):
        print(f"[mpl] ERROR: input file not found: {input_file}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)

    if plot_type == "wavefunction_1d":
        render_wavefunction_1d(input_file, out_png)
    elif plot_type == "density_2d":
        render_density_2d_legacy(input_file, out_png)
    elif plot_type == "density_2d_cube":
        render_density_2d_cube(input_file, out_png, colormap=colormap or "plasma",
                               slice_pos=slice_pos, slice_axis=slice_axis)
    elif plot_type == "density_3d_iso":
        render_density_3d_iso(input_file, out_png,
                              isovalue=isovalue, colormap=colormap or "hot",
                              slice_pos=slice_pos, slice_axis=slice_axis)
    elif plot_type == "wavefunction_2d_cube":
        render_wavefunction_2d_cube(input_file, out_png, colormap=colormap or "RdBu")
    else:
        print(f"[mpl] Unknown plot_type: {plot_type}", file=sys.stderr)
        sys.exit(3)
