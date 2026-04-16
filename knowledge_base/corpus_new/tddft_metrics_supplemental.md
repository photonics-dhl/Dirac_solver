# TDDFT Calculation Metrics — Supplemental Reference

> **Purpose**: Document the spectral point-count metrics used in the current workflow, and flag them as operational parameters rather than physical benchmarks.

## TDDFT Output Metrics (from run_dft_tddft_agent_suite.py)

These metrics are extracted from `static/density_diff` or equivalent TDDFT output files.

### H₂O TDDFT Absorption (cross_section_points)

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_tddft_absorption` (secondary metric) |
| **Metric** | `cross_section_points` |
| **Reference** | 2000 |
| **Unit** | spectral points |
| **Tolerance** | 5% relative |
| **Source** | Code default (not from literature) |
| **Confidence Tier** | **C-draft** (operational parameter, not physical benchmark) |

> **Note**: `cross_section_points` is the number of energy points used to resolve the absorption spectrum. This is a **calculation parameter**, not a physical quantity. It should not be used as a benchmark for accuracy. The relevant physical metric is the **peak position** (eV), not the number of points.

### H₂O TDDFT Dipole Response (dipole_points)

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_tddft_dipole_response` |
| **Metric** | `dipole_points` |
| **Reference** | 221 |
| **Unit** | spectral points |
| **Tolerance** | 8% relative |
| **Source** | Code default (not from literature) |
| **Confidence Tier** | **C-draft** (operational parameter) |

> **Note**: `dipole_points` counts the number of dipole response spectrum data points. This is a numerical resolution parameter, not a physical observable.

---

## Octopus TDDFT Calculation Modes

### Mode: Casida (Linear Response)

```
CalculationMode = casida
```

- Solves the Casida equation (linear response TDDFT)
- Outputs excitation energies and oscillator strengths
- Best for systems with < ~50 atoms
- Produces peak positions directly

### Mode: Time Propagation (Real-Time TDDFT)

```
CalculationMode = td
```

- Propagates the time-dependent KS equations
- Requires applying a perturbation (dipole delta pulse)
- Extracts spectrum via Fourier transform of dipole moment
- Produces full absorption spectrum

### Key Input Parameters (Real-Time TDDFT)

| Parameter | Typical Value | Notes |
|-----------|-------------|-------|
| `TimeStep` | 0.005–0.02 Eh⁻¹ | Must satisfy dt << 1/ω_max |
| `SimulationTime` | 20–100 Eh⁻¹ | Must be long enough for frequency resolution ΔE ≈ 2π/T |
| `TDMaximumIter` | 5000–20000 | Depends on TimeStep |
| `TDPolarization` | 1 0 0 | Direction of perturbation |
| `TDDeltaStrength` | 0.01–0.1 | Perturbation strength |

### Frequency Resolution

```
ΔE (eV) = 2π / SimulationTime (Eh⁻¹) × 27.2114
```

For ΔE = 0.1 eV resolution:
- SimulationTime ≈ 2π × 27.2114 / 0.1 ≈ 1709 Eh⁻¹

### Practical Example (H₂O, ~10 eV maximum excitation)

```bash
CalculationMode = gs
UnitsOutput = eV_Angstrom
Spacing = 0.18*angstrom
Radius = 3.5*angstrom
# (add H2O coordinates)

CalculationMode = td
FromScratch = yes
TDSpacePropagator = aetrs
TimeStep = 0.01
SimulationTime = 50
TDMaximumIter = 5000
TDPolarization = 1 | 0 | 0
TDDeltaStrength = 0.05
```

---

## Known Gaps

1. **Peak position not in CLASSIC_CASE_REFERENCES**: The TDDFT cases use `cross_section_points` as metric, not `peak_position_eV`
2. **No TDDFT reference values from Octopus Tutorial**: The specific H₂O TDDFT calculation (mode, parameters) is not documented in the current KB
3. **H₂O first absorption peak**: Should be ~7.5 eV (LDA), but this is not in the official reference cases yet

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/run_dft_tddft_agent_suite.py` | `h2o_tddft_absorption`, `h2o_tddft_dipole_response` in `SUITE_CASES` |

## Changelog

- 2026-04-16: Created. Documented that point-count metrics are operational parameters, not physical benchmarks. Flagged the gap in peak position references.
