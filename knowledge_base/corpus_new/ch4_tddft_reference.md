# CH₄ TDDFT / Optical Response Reference — Octopus Official Tutorial

> **Status (2026-05-05)**: Official Octopus tutorial data. Provenance verified.
> **Source**: Octopus Documentation 16, Optical Response tutorials
> **Pseudopotential**: `standard` (PSF, Troullier-Martins)

## Reference Summary

| Case ID | Method | First Peak | Source |
|---------|--------|-----------|--------|
| `ch4_tddft_absorption` | Time-propagation TDDFT | **~9.2 eV** | Octopus Tutorial |
| `ch4_tddft_casida` | Casida linear response | **9.278 eV** | Octopus Tutorial |
| `ch4_tddft_triplet` | Time-propagation (kick_spin) | **~9.05 eV** | Octopus Tutorial |

## Ground-State Parameters (for TDDFT initial state)

| Parameter | Value |
|-----------|-------|
| **Pseudopotential** | `standard` (PSF, C.psf + H.psf) |
| **BoxShape** | `minimum` |
| **Radius** | 3.5 Å (time-prop) / 6.5 Å (converged spectrum) |
| **Spacing** | 0.18 Å (time-prop) / 0.24 Å (converged) |
| **CH bond length** | 1.097 Å |
| **XCFunctional** | LDA (default) |
| **Total Energy** | -218.870 eV |

## TDDFT Time-Propagation Parameters

| Parameter | Value |
|-----------|-------|
| **CalculationMode** | `td` |
| **TDPropagator** | `aetrs` |
| **TDTimeStep** | 0.0023 /eV |
| **TDMaxSteps** | 4350 |
| **Propagation time** | ~10 ℏ/eV |
| **TDDeltaStrength** | 0.01/angstrom |
| **TDPolarizationDirection** | 1 (x) |
| **ExtraStates** | 0 (propagate only occupied states) |

## Spectral Properties

### Singlet Absorption (dipole response)

| Property | Value |
|----------|-------|
| **First peak position** | ~**9.2 eV** |
| **Peak width** | Artificial, ∝ 1/propagation_time |
| **f-sum rule** (to 20 eV) | 3.68 (incomplete, should → 8 for full spectrum) |
| **Static polarizability** | 2.06 Å³ |

### Convergence Requirements

| Parameter | Sufficient Value | Convergence Criterion |
|-----------|-----------------:|----------------------|
| **Spacing** | 0.24 Å | Peak position within 0.1 eV |
| **Radius** | 6.5 Å | First peak within 0.1 eV |
| **Propagation time** | 10 ℏ/eV | Peak width resolution |

### Literature Comparison

| Source | Method | First Peak (eV) | Notes |
|--------|--------|-----------------|-------|
| **Octopus time-propagation** | Real-space TDDFT | **~9.2** | This tutorial |
| **Octopus Casida** | Linear response | **9.278** | Degeneracy 3 |
| **Matsuzawa et al. (2001)** | TDDFT | **9.25** | J. Phys. Chem. A 105, 4953 |
| **Experiment** | — | **9.6** | Vacuum UV absorption |

### Triplet Excitations

| Method | First Triplet Peak |
|--------|-------------------:|
| Time-propagation (kick_spin) | **~9.05 eV** |
| Casida (CasidaCalcTriplet=yes) | Similar to time-prop |

## Casida Linear Response Details

**Parameters:**
- Radius = 6.5 Å, Spacing = 0.24 Å
- ExtraStates = 12 (converged 10, buffer 2)
- CasidaKohnShamStates = "1-10"

**Excitation energies:**

| State | Energy (eV) | Degeneracy | Oscillator Strength |
|-------|------------:|-----------:|--------------------:|
| 1-3 | **9.278** | 3 | 0.095 (each) |
| 4-5 | 10.249 | 2 | ~0 |
| 6-8 | 10.265 | 3 | 0.010 |

**Dominant transition (State 1):**
- HOMO → LUMO (state 3 → state 5): ~74.7%
- Small contributions from other transitions

## Full Provenance

- Octopus Tutorial: [Optical spectra from time-propagation](https://octopus-code.org/documentation/16/tutorial/response/optical_spectra_from_time-propagation/)
- Octopus Tutorial: [Convergence of the optical spectra](https://octopus-code.org/documentation/16/tutorial/response/convergence_of_the_optical_spectra/)
- Octopus Tutorial: [Optical spectra from Casida](https://octopus-code.org/documentation/16/tutorial/response/optical_spectra_from_casida/)
- Octopus Tutorial: [Triplet excitations](https://octopus-code.org/documentation/16/tutorial/response/triplet_excitations/)
- Matsuzawa et al. (2001): *Time-Dependent Density Functional Theory Calculations of Photoabsorption Spectra in the Vacuum Ultraviolet Region*, J. Phys. Chem. A **105**, 4953–4962. DOI: 10.1021/jp003937v

## Code Locations

- `scripts/run_dft_tddft_agent_suite.py` (`CLASSIC_CASE_REFERENCES`)
- `scripts/run_multi_agent_orchestration.py` (`DEFAULT_CASE_REFERENCE_ENERGY_HARTREE`)

## Changelog

- **2026-05-05**: Created from Octopus official tutorial documentation. First verified external reference for CH4 TDDFT absorption peak.
