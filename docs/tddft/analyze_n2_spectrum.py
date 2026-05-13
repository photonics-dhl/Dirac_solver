"""N2 TDDFT absorption spectrum analysis + experimental calibration."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
from pathlib import Path

# ── Load data ──
data_path = Path.home() / ".claude/temp/n2_cross_section_vector.txt"
raw = data_path.read_text().splitlines()

rows = []
for line in raw:
    if line.startswith('#') or not line.strip():
        continue
    parts = line.split()
    if len(parts) >= 5:
        rows.append([float(x) for x in parts])

data = np.array(rows)
energy_ha = data[:, 0]
sigma_re = data[:, 1]   # sigma(1) = Re[sigma_xx(w)] in Bohr^2
sigma_2  = data[:, 2]   # sigma(2) ~ 0 (off-diag)
sigma_3  = data[:, 3]   # sigma(3) ~ 0 (off-diag)
strength = data[:, 4]   # StrengthFunction S(w) in 1/Ha

energy_ev = energy_ha * 27.211386245988
H2EV = 27.211386245988

print(f"Data points: {len(energy_ha)}")
print(f"Energy range: {energy_ev[0]:.2f} – {energy_ev[-1]:.2f} eV")
print(f"Energy step: {(energy_ev[1] - energy_ev[0]):.4f} eV")
print()

# ── Peak detection ──
from scipy.signal import find_peaks

# Absorption peaks = peaks in StrengthFunction S(w)
peaks, props = find_peaks(strength, height=0.5, distance=30, prominence=0.5)

print("=" * 70)
print("ABSORPTION PEAKS (StrengthFunction S(w))")
print("=" * 70)
print(f"{'Energy (eV)':>12s}  {'Energy (Ha)':>12s}  {'S(w) [1/Ha]':>14s}  {'Re[sigma]':>12s}")
print("-" * 70)
for pk in peaks:
    print(f"{energy_ev[pk]:12.3f}  {energy_ha[pk]:12.4f}  {strength[pk]:14.6f}  {sigma_re[pk]:12.4f}")

# ── Top peaks ──
print()
print("TOP 10 STRONGEST PEAKS (by S(w)):")
top_idx = np.argsort(strength)[-10:][::-1]
for rank, idx in enumerate(top_idx, 1):
    print(f"  {rank:2d}. {energy_ev[idx]:8.3f} eV ({energy_ha[idx]:.4f} Ha)  S={strength[idx]:.4f}")

# ── Experimental reference ──
ref_peaks = [
    (12.50, "b1Piu v=0 <- X1Sg+ (valence pi->pi*)", "strong"),
    (12.93, "b1Piu v'=1 <- X1Sg+", "strong"),
    (13.24, "b1Piu v'=2 <- X1Sg+", "strong"),
    (14.01, "c1Siu+ <- X1Sg+ (3s-sigma Rydberg)", "medium"),
    (14.39, "c'1Siu+ <- X1Sg+ (3p-sigma Rydberg)", "medium"),
    (15.58, "Ionization limit X2Sg+", "threshold"),
]

print()
print("=" * 70)
print("EXPERIMENTAL REFERENCES (N2, gas phase photoabsorption)")
print("=" * 70)
for e, label, cat in ref_peaks:
    print(f"  {e:6.2f} eV  {label}  [{cat}]")

# ── Match computed to experimental ──
print()
print("=" * 70)
print("COMPUTED vs EXPERIMENTAL MATCHING")
print("=" * 70)
print(f"{'E_comp(eV)':>10s}  {'E_exp(eV)':>10s}  {'Delta':>8s}  {'Assignment':<45s}")

for e_exp, label, cat in ref_peaks:
    # Find nearest computed peak
    if len(peaks) == 0:
        continue
    distances = np.abs(energy_ev[peaks] - e_exp)
    best = np.argmin(distances)
    e_comp = energy_ev[peaks[best]]
    delta = e_comp - e_exp
    print(f"{e_comp:10.3f}  {e_exp:10.2f}  {delta:+8.3f}  {label:<45s}")

# ── Sum rules ──
print()
print("=" * 70)
print("SUM RULES & STATIC PROPERTIES")
print("=" * 70)
print(f"Static polarizability (sum rule): 11.025 Bohr^3 = {11.025 * 0.1481847:.3f} A^3")
print(f"Experimental alpha(N2):           11.74 Bohr^3 = 1.74 A^3")
print(f"Error: {(11.025 - 11.74) / 11.74 * 100:.1f}%")
print(f"Electronic sum rule: 3.023 electrons (valence only, PP)")
print()

# ── Save for plotting ──
np.savez(
    Path.home() / ".claude/temp/n2_spectrum_analysis.npz",
    energy_ev=energy_ev, energy_ha=energy_ha,
    sigma_re=sigma_re, strength=strength,
    peaks=peaks,
)
print("Saved: n2_spectrum_analysis.npz")
