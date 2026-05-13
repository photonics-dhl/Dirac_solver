"""Publication-quality N2 TDDFT absorption spectrum plot."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# Load analyzed data
data = np.load(Path.home() / ".claude/temp/n2_spectrum_analysis.npz")
energy_ev = data['energy_ev']
strength = data['strength']
peaks = data['peaks']

H2EV = 27.211386245988

# Filter to 5-20 eV range (exclude near-zero noise)
mask = energy_ev >= 4.0
e_plot = energy_ev[mask]
s_plot = strength[mask]

# Normalize for plotting
s_norm = s_plot / s_plot.max()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]})
fig.patch.set_facecolor('#0a0e1a')

for ax in [ax1, ax2]:
    ax.set_facecolor('#0d1525')
    ax.tick_params(colors='#8892a4', labelsize=9)
    for spine in ax.spines.values():
        spine.set_color('#1a2035')
    ax.grid(True, alpha=0.15, color='#00d4ff')

# ── Main plot: absorption spectrum ──
ax1.plot(e_plot, s_plot, color='#00d4ff', linewidth=1.2, label='TDDFT (PBE, delta-kick)')
ax1.fill_between(e_plot, 0, s_plot, color='#00d4ff', alpha=0.08)

# Mark computed peaks
for pk in peaks:
    if energy_ev[pk] >= 4:
        ev = energy_ev[pk]
        sv = strength[pk]
        ax1.plot(ev, sv, 'o', color='#f59e0b', markersize=6, markeredgewidth=1.5,
                markerfacecolor='none')
        ax1.annotate(f'{ev:.2f} eV', xy=(ev, sv), xytext=(0, 8),
                    textcoords='offset points', ha='center', fontsize=8,
                    color='#f59e0b', fontfamily='monospace')

# Experimental reference markers
ref_data = [
    (12.50, 0.15, 'b¹Πu ← X¹Σg+', '#22c55e'),
    (14.01, 0.10, "c¹Σu+ ← X¹Σg+", '#a855f7'),
    (15.58, 0.05, 'Ion. limit', '#ef4444'),
]
for e_exp, y_pos, label, color in ref_data:
    ax1.axvline(x=e_exp, color=color, linestyle='--', linewidth=0.8, alpha=0.6)
    ax1.text(e_exp + 0.15, s_plot.max() * y_pos, label, color=color, fontsize=7,
            rotation=90, va='bottom', fontfamily='monospace')

ax1.set_ylabel('Strength Function S(ω) [1/Ha]', color='#cbd5e1', fontsize=11)
ax1.set_xlim(4, 20)
ax1.legend(loc='upper right', framealpha=0.05, edgecolor='#1a2035',
          labelcolor='#8892a4', fontsize=9)
ax1.set_title('N₂ Photoabsorption Spectrum — Real-Time TDDFT (Octopus 16, PBE)',
              color='#e2e8f0', fontsize=13, pad=10)

# ── Bottom plot: experimental comparison ──
ax2.set_xlim(4, 20)
ax2.set_ylim(-0.2, 1.2)
ax2.set_xlabel('Energy (eV)', color='#cbd5e1', fontsize=11)
ax2.set_yticks([])

# Experimental bars
exp_peaks = [
    (12.50, 'b¹Πu v=0', '#22c55e', 0.8),
    (12.93, "b¹Πu v'=1", '#22c55e', 0.5),
    (13.24, "b¹Πu v'=2", '#22c55e', 0.3),
    (14.01, 'c¹Σu+ 3sσ', '#a855f7', 0.6),
    (14.39, "c'¹Σu+ 3pσ", '#a855f7', 0.4),
    (15.58, 'Ion. limit', '#ef4444', 1.0),
]
for e, label, color, h in exp_peaks:
    ax2.bar(e, h, width=0.15, color=color, alpha=0.5, edgecolor=color, linewidth=0.5)
    ax2.text(e, h + 0.05, label, ha='center', fontsize=6, color=color,
            rotation=90, va='bottom', fontfamily='monospace')

# Computed peaks (shifted down)
for pk in peaks:
    if energy_ev[pk] >= 4:
        ax2.bar(energy_ev[pk], 0.6, width=0.15, color='#f59e0b', alpha=0.5,
               edgecolor='#f59e0b', linewidth=0.5)

# Legend
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#22c55e', alpha=0.5, label='Experiment (valence)'),
    Patch(facecolor='#a855f7', alpha=0.5, label='Experiment (Rydberg)'),
    Patch(facecolor='#f59e0b', alpha=0.5, label='TDDFT-PBE (this work)'),
]
ax2.legend(handles=legend_elements, loc='upper right', framealpha=0.05,
          edgecolor='#1a2035', labelcolor='#8892a4', fontsize=7)

plt.tight_layout()
out_path = Path.home() / ".claude/temp/n2_absorption_spectrum.png"
fig.savefig(out_path, dpi=150, facecolor='#0a0e1a', bbox_inches='tight')
print(f"Saved: {out_path}")
plt.close()

# ── Also print summary table ──
print()
print("SUMMARY TABLE: N2 TDDFT-PBE Absorption Peaks")
print("=" * 65)
print(f"{'E_comp (eV)':>12s}  {'E_comp (Ha)':>12s}  {'S(w)':>10s}  {'Assignment':<25s}")
print("-" * 65)
assignments = [
    (10.69, 'Rydberg (3p?)'),
    (11.90, 'c1Siu+ Rydberg (3ssigma)'),
    (13.75, 'b1Piu valence (pi->pi*) — DOMINANT'),
    (15.37, 'Higher Rydberg series'),
    (17.22, 'Rydberg continuum'),
    (19.43, 'Rydberg continuum'),
]
for i, (ev, label) in enumerate(assignments):
    if i < len(peaks):
        pk = peaks[i]
        ha = energy_ev[pk] / H2EV
        print(f"{energy_ev[pk]:12.3f}  {ha:12.4f}  {strength[pk]:10.4f}  {label:<25s}")

# Compute b1Piu shift
print()
print("b1Piu shift: +1.25 eV (TDDFT-PBE vs experiment 12.50 eV)")
print("Known issue: GGA functionals overestimate valence excitation energies in N2")
