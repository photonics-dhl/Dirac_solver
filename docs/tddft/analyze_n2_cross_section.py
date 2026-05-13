"""N2 cross-section: convert to photoabsorption units + experimental calibration."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
from pathlib import Path
from scipy.signal import find_peaks

data = np.load(Path.home() / ".claude/temp/n2_spectrum_analysis.npz")
energy_ev = data['energy_ev']
energy_ha = data['energy_ha']
strength = data['strength']  # S(w) in 1/Ha
peaks = data['peaks']

H2EV = 27.211386245988
# c in atomic units
c_au = 137.035999084
# 1 Bohr = 0.529177210903 Å
bohr_to_angstrom = 0.529177210903
# 1 barn = 1e-8 Å² → 1 Bohr² in Mb (megabarns)
bohr2_to_Mb = (bohr_to_angstrom)**2 * 100  # 1 Bohr^2 = 0.28 Å² = 28 Mb... let me recalculate
# 1 Bohr^2 = (0.529177 Å)² = 0.28003 Å² = 2.8003 × 10⁻⁹ m²...
# Actually 1 barn = 10⁻²⁸ m², 1 Mb = 10⁻²² m² = 10⁻²²/10⁻²⁰ = 0.01 Å²... let me be careful
# 1 barn = 100 fm² = 10⁻²⁸ m²
# 1 Å² = 10⁻²⁰ m²
# 1 Mb = 10⁻³ barn = 10⁻³¹ m²... no
# 1 Mb = 10⁻³ × 10⁻²⁸ = 10⁻³¹ m²? No wait:
# 1 barn = 10⁻²⁴ cm² = 10⁻²⁸ m²
# 1 Mb = 10⁶ barn = 10⁶ × 10⁻²⁸ = 10⁻²² m²... no:
# "milli" = 10⁻³? Or "mega" = 10⁶?
# In nuclear/atomic physics: 1 barn = 10⁻²⁴ cm². 1 Mb = 10⁻³ barn = 10⁻²⁷ cm².
# No: 1 mb = 10⁻³ barn, 1 Mb = 10⁶ barn? That doesn't make sense.
# Actually: 1 b (barn) = 10⁻²⁴ cm². 1 Mb (megabarn) = 10⁶ b = 10⁻¹⁸ cm².
# Wait no: M = mega = 10⁶? Or m = milli = 10⁻³?
# In photoabsorption: cross sections are usually in Mb where M = mega = 10⁶
# But 1 Mb = 10⁶ barn = 10⁻¹⁸ cm²... that's huge
# Actually in atomic photoionization: 1 Mb = 10⁻¹⁸ cm² (megabarn)
# OK: 1 barn = 10⁻²⁴ cm², 1 Mb = 10⁶ × 10⁻²⁴ = 10⁻¹⁸ cm² = 10⁻²² m²
# 1 Bohr² = (5.29177 × 10⁻¹¹ m)² = 2.8003 × 10⁻²¹ m²
# 1 Bohr² = 2.8003 × 10⁻²¹ / 10⁻²² Mb = 28.003 Mb
# So conversion: cross_section [Mb] = sigma [Bohr²] × 28.003

# Actually, I should double-check. Let me Google the conversion.
# 1 Bohr radius = 0.529177... Å = 5.29177... × 10⁻¹¹ m
# 1 Bohr² = 0.28003... Å²
# 1 barn = 10⁻²⁸ m² = 10⁻²⁴ cm² = 10⁻⁸ Å²?...
# Actually: 1 Å = 10⁻¹⁰ m, so 1 Å² = 10⁻²⁰ m²
# 1 barn = 10⁻²⁸ m² = 10⁻⁸ Å²
# 1 Bohr² = 0.28003 Å² = 0.28003 × 10⁸ barn = 2.8003 × 10⁷ barn... that can't be right
# Let me redo: 1 barn = 10⁻²⁸ m²
# 1 Bohr² = (5.29177 × 10⁻¹¹)² m² = 2.800 × 10⁻²¹ m²
# 1 Bohr² / 1 barn = 2.800 × 10⁻²¹ / 10⁻²⁸ = 2.800 × 10⁷ barn
# 1 Bohr² = 28,000,000 barn = 28 Mb? (if M = mega = 10⁶)
# Wait: 28 × 10⁶ barn = 28 megabarn. That seems too large.
#
# Hmm, actually I think the convention varies. In atomic physics,
# photoionization cross sections are often in Mb (megabarns = 10⁶ barn).
# But 28 Mb per Bohr² seems too large.
#
# Let me re-derive more carefully:
# 1 Bohr = a₀ = 0.529177... × 10⁻¹⁰ m
# 1 Bohr² = a₀² = 2.8003 × 10⁻²¹ m²
# 1 barn = 10⁻²⁸ m²
# So 1 Bohr² = 2.8003 × 10⁷ barn
# 1 Mb = 10⁻¹⁸ cm² = 10⁻²² m²
# 1 Bohr² / 1 Mb = 2.8003 × 10⁻²¹ / 10⁻²² = 28.003
# So 1 Bohr² = 28.003 Mb. Yes!

# The photoabsorption cross section σ(ω) in atomic units relates to the
# dynamic polarizability α(ω) via:
# σ(ω) = (4πω/c) Im[α(ω)]
# In atomic units: σ(ω) [Bohr²] = (4πω/c) Im[α(ω)]
# where c = 137.036 in atomic units.

# The Strength Function S(ω) from oct-propagation_spectrum:
# S(ω) = (2/π) × ω × Tr[Im σ(ω)] / 3  (for isotropic averaging)
# Actually, for a specific polarization direction:
# S(ω) = (2/π) × ω × Im[σ_xx(ω)]
# So: Im[σ_xx(ω)] = (π/2ω) × S(ω)

# Photoabsorption cross section:
# σ_abs(ω) = (4πω/c) × Im[α_xx(ω)]
# For a delta-kick spectrum, σ_xx(ω) ≡ α_xx(ω) (dynamic polarizability)
# So: σ_abs(ω) = (4πω/c) × Im[σ_xx(ω)]
#              = (4πω/c) × (π/2ω) × S(ω)
#              = (2π²/c) × S(ω)

# In atomic units (Bohr²):
# sigma_abs = (2 * pi^2 / c) * S(w)
#           = (2 * pi^2 / 137.036) * S(w)
#           = 0.14407 * S(w)

print("N2 PHOTOABSORPTION CROSS SECTION ANALYSIS")
print("=" * 60)

# Convert StrengthFunction to cross section in Bohr²
c_au = 137.035999084
conv_factor = 2 * np.pi**2 / c_au  # = 0.14407
sigma_bohr2 = conv_factor * strength  # Photoabsorption cross section in Bohr²

# Convert to Mb (megabarns)
bohr2_to_Mb = 28.003
sigma_Mb = sigma_bohr2 * bohr2_to_Mb

# Filter to 4-20 eV
mask = energy_ev >= 4.0
e_plot = energy_ev[mask]
cs_Mb = sigma_Mb[mask]

# Peak detection in cross section
cs_peaks, cs_props = find_peaks(cs_Mb, height=0.5, distance=30, prominence=0.3)

print(f"\nConversion: sigma_abs [Bohr^2] = (2*pi^2/c) * S(w) = {conv_factor:.4f} * S(w)")
print(f"1 Bohr^2 = {bohr2_to_Mb:.1f} Mb (megabarns)")
print(f"Energy: {e_plot[0]:.0f} - {e_plot[-1]:.0f} eV, step = {(e_plot[1]-e_plot[0]):.3f} eV")
print()

print("ABSORPTION CROSS SECTION PEAKS:")
print(f"{'E(eV)':>8s}  {'S(w)':>10s}  {'sigma(Bohr^2)':>14s}  {'sigma(Mb)':>10s}")
print("-" * 52)
for pk in cs_peaks:
    idx = np.where(energy_ev == e_plot[pk])[0][0]
    print(f"{energy_ev[idx]:8.3f}  {strength[idx]:10.4f}  {sigma_bohr2[idx]:14.4f}  {sigma_Mb[idx]:10.2f}")

# Top peaks
top_cs = np.argsort(cs_Mb)[-8:][::-1]
print(f"\nTOP PEAKS IN CROSS SECTION (Mb):")
for rank, idx in enumerate(top_cs, 1):
    print(f"  {rank}. {e_plot[idx]:8.3f} eV  {cs_Mb[idx]:8.2f} Mb  (S={strength[mask][idx]:.4f})")

# Experimental comparison
# N2 photoabsorption cross section at peak: ~23 Mb at ~12.7 eV (b¹Πu)
print(f"\n{'='*60}")
print("EXPERIMENTAL COMPARISON (N2 photoabsorption)")
print(f"{'='*60}")
print(f"  Computed peak: {e_plot[top_cs[0]]:.2f} eV, {cs_Mb[top_cs[0]]:.1f} Mb")
print(f"  Experimental b¹Πu peak: ~12.7 eV, ~23 Mb")
print(f"  Energy shift: +{e_plot[top_cs[0]] - 12.7:.2f} eV")
if len(cs_peaks) > 1:
    print(f"  Second peak: {e_plot[cs_peaks[1]]:.2f} eV, {cs_Mb[cs_peaks[1]]:.1f} Mb")

# Oscillator strength
# f = (2/pi) * integral of Im[alpha(w)] * w dw...
# f = integral of S(w) dw ≈ sum_i S(wi) * dw
dw_ha = energy_ha[1] - energy_ha[0]
f_sum = np.sum(strength) * dw_ha
print(f"\n  Integrated S(w) = {f_sum:.3f}")
print(f"  Thomas-Reiche-Kuhn sum rule: f_sum = N_elec = 10 (all-electron)")
print(f"  Effective valence electrons: {f_sum:.1f}")

# Dipole moment and static polarizability check
alpha_static = 11.025  # Bohr^3 from sum rule in file header
print(f"\n  Static polarizability: {alpha_static:.1f} Bohr^3 = {alpha_static * 0.1481847:.2f} A^3")
print(f"  Experimental: 11.74 Bohr^3")
print(f"  Error: {(alpha_static - 11.74)/11.74*100:.1f}%")

# Save cross section data
np.savez(
    Path.home() / ".claude/temp/n2_cross_section_Mb.npz",
    energy_ev=e_plot,
    cross_section_Mb=cs_Mb,
    cross_section_Bohr2=sigma_bohr2[mask],
)
print(f"\nSaved cross section data to n2_cross_section_Mb.npz")
