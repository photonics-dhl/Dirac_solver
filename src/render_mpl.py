"""
render_mpl.py  —  Dark-themed matplotlib renderer for 1D/2D Octopus output files.
Usage:
    python render_mpl.py <input_file> <plot_type> <output_png>

plot_type: wavefunction_1d | density_2d
input: .y=0,z=0 file (whitespace-delimited, # comments)
"""
import sys
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")   # headless
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

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


# ── Dark theme ────────────────────────────────────────────────────────────────
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
    print(f"[mpl] Saved {output_png}")


def render_density_2d(input_path: str, output_png: str):
    x, rho, _ = parse_octopus_slice(input_path)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    apply_dark_style(fig, ax)

    ax.plot(x, rho, color="#a78bfa", linewidth=1.8, label=r"$\rho(x)$")
    ax.fill_between(x, rho, where=rho >= 0, alpha=0.15, color="#a78bfa")

    ax.axhline(0, color=MUTED, linewidth=0.5, alpha=0.5)
    ax.set_xlabel("x  (Bohr)", fontsize=9)
    ax.set_ylabel(r"$\rho(x)$  (e/Bohr)", fontsize=9)
    ax.set_title("Electron Density — y=0, z=0 slice", fontsize=10, pad=8)
    leg = ax.legend(fontsize=8, framealpha=0.1, edgecolor=GRID_COLOR, facecolor=BG)
    for text in leg.get_texts():
        text.set_color("#e2e8f0")

    plt.tight_layout(pad=1.2)
    fig.savefig(output_png, dpi=120, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"[mpl] Saved {output_png}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python render_mpl.py <input_file> <plot_type> <output_png>", file=sys.stderr)
        sys.exit(1)

    input_file, plot_type, out_png = sys.argv[1], sys.argv[2], sys.argv[3]

    if not os.path.isfile(input_file):
        print(f"[mpl] ERROR: input file not found: {input_file}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)

    if plot_type == "wavefunction_1d":
        render_wavefunction_1d(input_file, out_png)
    elif plot_type == "density_2d":
        render_density_2d(input_file, out_png)
    else:
        print(f"[mpl] Unknown plot_type: {plot_type}", file=sys.stderr)
        sys.exit(3)
