"""Publication-quality CH4 & H2O TDDFT absorption spectrum plots."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.signal import find_peaks

H2EV = 27.211386245988
c_au = 137.035999084
conv_factor = 2 * np.pi**2 / c_au
bohr2_to_Mb = 28.003

def load_npz(name):
    d = np.load(Path.home() / f".claude/temp/{name}_spectrum_analysis.npz")
    return d['energy_ev'], d['strength'], d['sigma_Mb'], d['peaks']

def plot_spectrum(name, label, energy_ev, strength, sigma_Mb, peaks, ref_data, xlim=(3, 20)):
    mask = energy_ev >= xlim[0]
    e_plot = energy_ev[mask]
    s_plot = strength[mask]
    cs_Mb = sigma_Mb[mask]

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor('#0a0e1a')
    ax.set_facecolor('#0d1525')
    ax.tick_params(colors='#8892a4', labelsize=10)
    for spine in ax.spines.values():
        spine.set_color('#1a2035')
    ax.grid(True, alpha=0.15, color='#00d4ff')

    # Strength function
    ax.plot(e_plot, s_plot, color='#00d4ff', linewidth=1.2, label='S(ω) [1/Ha]')
    ax.fill_between(e_plot, 0, s_plot, color='#00d4ff', alpha=0.06)

    # Mark computed peaks
    for pk in peaks:
        if energy_ev[pk] >= xlim[0] and energy_ev[pk] <= xlim[1]:
            ev = energy_ev[pk]
            sv = strength[pk]
            ax.plot(ev, sv, 'o', color='#f59e0b', markersize=7, markeredgewidth=1.5,
                    markerfacecolor='none')
            ax.annotate(f'{ev:.2f}', xy=(ev, sv), xytext=(0, 9),
                        textcoords='offset points', ha='center', fontsize=8,
                        color='#f59e0b', fontfamily='monospace')

    # Experimental reference markers
    for e_exp, label_text, color, y_pos in ref_data:
        ax.axvline(x=e_exp, color=color, linestyle='--', linewidth=0.8, alpha=0.6)
        ax.text(e_exp + 0.1, s_plot.max() * y_pos, label_text, color=color, fontsize=7,
                rotation=90, va='bottom', fontfamily='monospace')

    # Cross-section axis (right)
    ax2 = ax.twinx()
    ax2.set_ylabel('Photoabsorption Cross Section (Mb)', color='#22c55e', fontsize=11)
    ax2.plot(e_plot, cs_Mb, color='#22c55e', linewidth=0.8, alpha=0.5)
    ax2.tick_params(colors='#22c55e', labelsize=9)
    ax2.set_ylim(0, cs_Mb.max() * 1.15)

    ax.set_xlim(*xlim)
    ax.set_ylabel('Strength Function S(ω) [1/Ha]', color='#cbd5e1', fontsize=11)
    ax.set_xlabel('Energy (eV)', color='#cbd5e1', fontsize=11)
    ax.set_title(f'{label} Photoabsorption Spectrum — TDDFT-PBE (Octopus 16)', color='#e2e8f0', fontsize=13, pad=10)
    ax.legend(loc='upper right', framealpha=0.05, edgecolor='#1a2035', labelcolor='#8892a4', fontsize=9)

    plt.tight_layout()
    out = Path.home() / f".claude/temp/{name}_absorption_spectrum.png"
    fig.savefig(out, dpi=150, facecolor='#0a0e1a', bbox_inches='tight')
    plt.close()
    print(f"Saved: {out}")

# ── CH4 ──
e_ch4, s_ch4, cs_ch4, pk_ch4 = load_npz("ch4")
ch4_ref = [
    (8.5,  'Onset (HOMO→3s)', '#ef4444', 0.15),
    (9.7,  '3pt₂ (HOMO→3p)', '#a855f7', 0.3),
    (11.7, '3dt₂ (HOMO→3d)', '#22c55e', 0.5),
    (14.0, '4s/4p Rydberg', '#f59e0b', 0.6),
]
plot_spectrum("ch4", "CH₄", e_ch4, s_ch4, cs_ch4, pk_ch4, ch4_ref)

# ── H2O ──
e_h2o, s_h2o, cs_h2o, pk_h2o = load_npz("h2o")
h2o_ref = [
    (7.4,  'A¹B₁ (HOMO→3sa₁)', '#22c55e', 0.15),
    (9.7,  'B¹A₁ (3pb₂)', '#a855f7', 0.25),
    (12.6, 'Ion. limit', '#ef4444', 0.5),
    (14.5, 'C¹B₁ (3pa₁)', '#f59e0b', 0.6),
]
plot_spectrum("h2o", "H₂O", e_h2o, s_h2o, cs_h2o, pk_h2o, h2o_ref)

# ── Combined comparison plot ──
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.patch.set_facecolor('#0a0e1a')

axes[0, 0].set_facecolor('#0d1525')
axes[0, 1].set_facecolor('#0d1525')
axes[1, 0].set_facecolor('#0d1525')
axes[1, 1].set_facecolor('#0d1525')

# CH4 S(w)
ax = axes[0, 0]
mask4 = e_ch4 >= 3
ax.plot(e_ch4[mask4], s_ch4[mask4], color='#00d4ff', linewidth=1.0)
for pk in pk_ch4:
    if e_ch4[pk] >= 3:
        ax.axvline(x=e_ch4[pk], color='#f59e0b', linestyle='--', linewidth=0.5, alpha=0.7)
ax.set_title('CH₄ — S(ω)', color='#e2e8f0', fontsize=11)
ax.set_xlabel('eV', color='#8892a4', fontsize=9)
ax.set_ylabel('1/Ha', color='#8892a4', fontsize=9)
ax.tick_params(colors='#8892a4', labelsize=8)
ax.set_xlim(3, 20)
ax.grid(True, alpha=0.1, color='#00d4ff')

# H2O S(w)
ax = axes[0, 1]
mask2 = e_h2o >= 3
ax.plot(e_h2o[mask2], s_h2o[mask2], color='#00d4ff', linewidth=1.0)
for pk in pk_h2o:
    if e_h2o[pk] >= 3:
        ax.axvline(x=e_h2o[pk], color='#f59e0b', linestyle='--', linewidth=0.5, alpha=0.7)
ax.set_title('H₂O — S(ω)', color='#e2e8f0', fontsize=11)
ax.set_xlabel('eV', color='#8892a4', fontsize=9)
ax.set_ylabel('1/Ha', color='#8892a4', fontsize=9)
ax.tick_params(colors='#8892a4', labelsize=8)
ax.set_xlim(3, 20)
ax.grid(True, alpha=0.1, color='#00d4ff')

# CH4 cross-section
ax = axes[1, 0]
ax.plot(e_ch4[mask4], cs_ch4[mask4], color='#22c55e', linewidth=1.0)
for pk in pk_ch4:
    if e_ch4[pk] >= 3:
        ax.axvline(x=e_ch4[pk], color='#f59e0b', linestyle='--', linewidth=0.5, alpha=0.7)
ax.set_title('CH₄ — σ(ω) [Mb]', color='#e2e8f0', fontsize=11)
ax.set_xlabel('eV', color='#8892a4', fontsize=9)
ax.set_ylabel('Mb', color='#8892a4', fontsize=9)
ax.tick_params(colors='#8892a4', labelsize=8)
ax.set_xlim(3, 20)
ax.grid(True, alpha=0.1, color='#00d4ff')

# H2O cross-section
ax = axes[1, 1]
ax.plot(e_h2o[mask2], cs_h2o[mask2], color='#22c55e', linewidth=1.0)
for pk in pk_h2o:
    if e_h2o[pk] >= 3:
        ax.axvline(x=e_h2o[pk], color='#f59e0b', linestyle='--', linewidth=0.5, alpha=0.7)
ax.set_title('H₂O — σ(ω) [Mb]', color='#e2e8f0', fontsize=11)
ax.set_xlabel('eV', color='#8892a4', fontsize=9)
ax.set_ylabel('Mb', color='#8892a4', fontsize=9)
ax.tick_params(colors='#8892a4', labelsize=8)
ax.set_xlim(3, 20)
ax.grid(True, alpha=0.1, color='#00d4ff')

fig.suptitle('TDDFT-PBE Photoabsorption Spectra (Octopus 16, Real-Time δ-kick)', color='#e2e8f0', fontsize=13)
plt.tight_layout()
out2 = Path.home() / ".claude/temp/ch4_h2o_combined_spectrum.png"
fig.savefig(out2, dpi=150, facecolor='#0a0e1a', bbox_inches='tight')
plt.close()
print(f"Saved: {out2}")

# ── Summary table ──
print()
print("SUMMARY: CH₄ & H₂O TDDFT-PBE Absorption Peaks")
print("=" * 70)
print(f"{'Molecule':>8s}  {'E(eV)':>8s}  {'S(w)':>8s}  {'σ(Mb)':>8s}  {'Assignment':<30s}")
print("-" * 70)

ch4_assign = [
    (9.13, "HOMO→3s Rydberg (T₂)"),
    (10.37, "HOMO→3p/4s Rydberg"),
    (11.69, "HOMO→3d Rydberg"),
    (13.49, "4s/4p/3d mixed Rydberg"),
    (16.15, "σ(C-H) → σ* continuum — DOMINANT"),
    (18.28, "Higher Rydberg series"),
    (19.48, "Rydberg convergence → IP"),
]
for i, (ev, label) in enumerate(ch4_assign):
    if i < len(pk_ch4) and e_ch4[pk_ch4[i]] >= 3:
        pk = pk_ch4[i]
        print(f"{'CH4':>8s}  {e_ch4[pk]:8.3f}  {s_ch4[pk]:8.4f}  {cs_ch4[pk]:8.2f}  {label:<30s}")

h2o_assign = [
    (9.67, "B¹A₁ (HOMO→3pb₂) Rydberg"),
    (12.46, "C¹B₁ (HOMO→3pa₁) mixed"),
    (14.03, "D¹A₁ (3sa₁→4s/4p)"),
    (15.63, "Higher Rydberg series"),
    (18.10, "2b₂ → 4a₁ continuum — DOMINANT"),
]
print()
for i, (ev, label) in enumerate(h2o_assign):
    if i < len(pk_h2o) and e_h2o[pk_h2o[i]] >= 3:
        pk = pk_h2o[i]
        print(f"{'H2O':>8s}  {e_h2o[pk]:8.3f}  {s_h2o[pk]:8.4f}  {cs_h2o[pk]:8.2f}  {label:<30s}")

# Casida vs TDDFT comparison
print()
print("CASIDA (LR) vs TDDFT (RT) COMPARISON:")
print(f"  CH₄  Casida 1st: 9.184 eV  |  TDDFT 1st: {e_ch4[pk_ch4[0]]:.2f} eV")
# H₂O Casida from Octopus 16 builtin_standard LDA (job 151384, 2026-05-14)
h2o_casida_1st = 6.674
print(f"  H₂O  Casida 1st: {h2o_casida_1st:.3f} eV  |  TDDFT 1st: {e_h2o[pk_h2o[0]]:.2f} eV")
print(f"  Δ(CH₄): {e_ch4[pk_ch4[0]] - 9.184:+.2f} eV")
# WARNING: H₂O TDDFT data from earlier run with insufficient propagation (98 eV resolution).
# The 3 eV Casida-vs-TDDFT gap for H₂O reflects the failed TDDFT, not a real discrepancy.
print(f"  Δ(H₂O): {e_h2o[pk_h2o[0]] - h2o_casida_1st:+.2f} eV (TDDFT data unreliable — 98 eV resolution)")
