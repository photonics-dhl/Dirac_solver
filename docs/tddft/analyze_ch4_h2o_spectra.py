"""CH4 & H2O TDDFT absorption spectrum analysis + cross-section conversion."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
from pathlib import Path
from scipy.signal import find_peaks

H2EV = 27.211386245988
c_au = 137.035999084
conv_factor = 2 * np.pi**2 / c_au  # S(w) → sigma_abs [Bohr^2]
bohr2_to_Mb = 28.003

def load_csv(path):
    raw = Path(path).read_text().splitlines()
    rows = []
    for line in raw:
        if line.startswith('#') or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 5:
            rows.append([float(x) for x in parts])
    d = np.array(rows)
    return d[:, 0], d[:, 1], d[:, 2], d[:, 3], d[:, 4]  # E_Ha, sigma1, sigma2, sigma3, S

def analyze(name, label, energy_ha, strength):
    energy_ev = energy_ha * H2EV
    sigma_bohr2 = conv_factor * strength
    sigma_Mb = sigma_bohr2 * bohr2_to_Mb

    mask = energy_ev >= 3.0
    e_plot = energy_ev[mask]
    s_plot = strength[mask]
    cs_Mb = sigma_Mb[mask]

    peaks, props = find_peaks(strength, height=0.3, distance=25, prominence=0.2)
    # Filter peaks to >3 eV
    peaks = [p for p in peaks if energy_ev[p] >= 3.0]

    print(f"\n{'='*70}")
    print(f"  {label} ABSORPTION SPECTRUM")
    print(f"{'='*70}")
    print(f"  Energy range: {e_plot[0]:.1f} – {e_plot[-1]:.1f} eV, step = {(e_plot[1]-e_plot[0]):.3f} eV")

    print(f"\n  PEAKS (S(w) > 0.3):")
    print(f"  {'E(eV)':>8s}  {'E(Ha)':>10s}  {'S(w)':>10s}  {'σ(Mb)':>10s}")
    print(f"  {'-'*44}")
    for pk in peaks:
        ev = energy_ev[pk]
        ha = energy_ha[pk]
        sw = strength[pk]
        smb = sigma_Mb[pk]
        print(f"  {ev:8.3f}  {ha:10.4f}  {sw:10.4f}  {smb:10.2f}")

    # Top peaks
    top = np.argsort(strength)[-8:][::-1]
    top = [t for t in top if energy_ev[t] >= 3.0]
    print(f"\n  TOP PEAKS BY S(w):")
    for rank, idx in enumerate(top[:6], 1):
        print(f"    {rank}. {energy_ev[idx]:8.3f} eV  S={strength[idx]:.4f}  σ={sigma_Mb[idx]:.1f} Mb")

    # Sum rule
    dw = energy_ha[1] - energy_ha[0]
    f_sum = np.sum(strength) * dw
    print(f"\n  Integrated S(w) = {f_sum:.3f} (effective valence electrons)")

    return energy_ev, strength, sigma_bohr2, sigma_Mb, peaks

# CH4
e_ha_ch4, s1, s2, s3, s_ch4 = load_csv(Path.home() / ".claude/temp/ch4_cross_section_vector.txt")
e_ev_ch4, s_ch4_full, sig_b2_ch4, sig_mb_ch4, peaks_ch4 = analyze("ch4", "CH₄", e_ha_ch4, s_ch4)

# H2O
e_ha_h2o, s1, s2, s3, s_h2o = load_csv(Path.home() / ".claude/temp/h2o_cross_section_vector.txt")
e_ev_h2o, s_h2o_full, sig_b2_h2o, sig_mb_h2o, peaks_h2o = analyze("h2o", "H₂O", e_ha_h2o, s_h2o)

# Save for plotting
np.savez(Path.home() / ".claude/temp/ch4_spectrum_analysis.npz",
    energy_ev=e_ev_ch4, energy_ha=e_ha_ch4, strength=s_ch4,
    sigma_bohr2=sig_b2_ch4, sigma_Mb=sig_mb_ch4, peaks=peaks_ch4)
np.savez(Path.home() / ".claude/temp/h2o_spectrum_analysis.npz",
    energy_ev=e_ev_h2o, energy_ha=e_ha_h2o, strength=s_h2o,
    sigma_bohr2=sig_b2_h2o, sigma_Mb=sig_mb_h2o, peaks=peaks_h2o)
print("\nSaved: ch4_spectrum_analysis.npz, h2o_spectrum_analysis.npz")
