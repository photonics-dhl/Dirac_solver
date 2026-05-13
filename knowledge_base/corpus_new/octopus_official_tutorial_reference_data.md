# Octopus 官方教程参考数据汇总

> **Source**: Octopus-code.org Documentation 16 (and legacy versions)
> **Retrieved**: 2026-05-05
> **Important**: Octopus official tutorials predominantly use **PSF pseudopotentials** (`standard` set), NOT `builtin_standard`. These are distinct pseudopotential families and their absolute total energies are NOT directly comparable.

---

## ⚠️ Critical Finding: Pseudopotential Mismatch

| Pseudopotential Set | Format | Location | Used in Tutorials |
|---------------------|--------|----------|-------------------|
| `standard` | PSF (semilocal, Kleinman-Bylander) | `share/octopus/pseudopotentials/PSF/` | ✅ Tutorial 16 (N, CH4) |
| `builtin_standard` | Built-in Troullier-Martins | Compiled into Octopus binary | ❌ NOT used in official tutorials |
| `hgh` | HGH pseudopotentials | `share/octopus/pseudopotentials/HGH/` | He atom tutorial |

> **Implication**: The reference values from Tutorial 16 (-262.24 eV for N, -218.28 eV for CH4) are for **PSF pseudopotentials**. If your calculation uses `builtin_standard`, the absolute total energy will differ even for identical geometries and grid parameters.

---

## Ground State References

### N Atom (Tutorial: Basic Input Options + Total Energy Convergence)

| Parameter | Value |
|-----------|-------|
| **Pseudopotential** | `standard` (PSF, N.psf) |
| **BoxShape** | `sphere` |
| **Radius** | 5.0 Å |
| **Spacing** | 0.18 Å |
| **XCFunctional** | LDA (default) |
| **Valence charge** | 5.0 |
| **Occupations** | 2, 1, 1, 1 (closed-shell, unpolarized) |

**Convergence with spacing:**

| Spacing (Å) | Total Energy (eV) | s eigenvalue (eV) | p eigenvalue (eV) |
|------------:|------------------:|------------------:|------------------:|
| 0.26 | -256.568 | -19.856 | -6.753 |
| 0.24 | -260.262 | -18.816 | -7.085 |
| 0.22 | -262.607 | -18.191 | -7.322 |
| 0.20 | -262.935 | -18.096 | -7.364 |
| **0.18** | **-262.241** | **-18.283** | **-7.302** |
| 0.16 | -261.801 | -18.391 | -7.251 |
| 0.14 | -261.820 | -18.386 | -7.257 |

**Reference value (converged, sp=0.18Å):**
- Total Energy: **-262.241 eV** = **-9.637 Ha**
- s eigenvalue: **-18.283 eV**
- p eigenvalue: **-7.302 eV**

> Note: The energy at sp=0.18Å (-262.241 eV) is very close to the converged value. The minimum is at sp=0.20Å (-262.935 eV), but sp=0.18Å is within ~0.7 eV (0.3%) of the converged value.

---

### CH4 Methane (Tutorial: Total Energy Convergence)

| Parameter | Value |
|-----------|-------|
| **Pseudopotential** | `standard` (PSF, C.psf + H.psf) |
| **BoxShape** | `minimum` (default, union of spheres) |
| **Radius** | 3.5 Å |
| **Spacing** | 0.18 Å |
| **CH bond length** | 1.2 Å (initial) / 1.097 Å (TD propagation) |
| **XCFunctional** | LDA (default) |

**Convergence with spacing (CH=1.2Å, R=3.5Å):**

| Spacing (Å) | Total Energy (eV) |
|------------:|------------------:|
| 0.22 | -219.038 |
| 0.20 | -218.584 |
| **0.18** | **-218.280** |
| 0.16 | -218.200 |
| 0.14 | -218.179 |
| 0.12 | -218.160 |
| 0.10 | -218.139 |

**Convergence with radius (sp=0.18Å, CH=1.2Å):**

| Radius (Å) | Total Energy (eV) |
|-----------:|------------------:|
| 2.5 | -218.071 |
| 3.0 | -218.246 |
| **3.5** | **-218.280** |
| 4.0 | -218.286 |
| 4.5 | -218.288 |
| 5.0 | -218.288 |

**Converged reference value:**
- Total Energy: **-218.29 eV** = **-8.024 Ha**

**Eigenvalues (sp=0.22Å, CH=1.2Å):**

| #st | Eigenvalue (eV) | Occupation |
|-----|----------------:|-----------:|
| 1 | -15.991 | 2.000 |
| 2 | -9.066 | 2.000 |
| 3 | -9.066 | 2.000 |
| 4 | -9.066 | 2.000 |
| 5 | 0.268 | 0.000 (LUMO) |
| 6-8 | 1.928 | 0.000 |

**Geometry Optimization (Tutorial: Geometry Optimization):**

| CH distance (Å) | Total Energy (eV) |
|----------------:|------------------:|
| 0.90 | -215.311 |
| 0.95 | -217.099 |
| 1.00 | -218.182 |
| 1.05 | -218.729 |
| **1.10** | **-218.869** |
| 1.15 | -218.693 |
| 1.20 | -218.279 |
| 1.25 | -217.689 |
| 1.30 | -216.966 |

- **Optimized CH bond length**: **1.095 Å** (from FIRE optimization)
- **Experimental CH bond length**: **1.094 Å**
- **Optimized total energy**: **-218.877 eV**

**TD Propagation initial state (CH=1.097Å, sp=0.18Å, R=3.5Å):**
- Total Energy: **-218.870 eV** = **-8.043 Ha**

> Note: The energy difference between CH=1.2Å (-218.28 eV) and CH=1.097Å (-218.87 eV) is ~0.6 eV, showing geometry sensitivity.

---

## TDDFT / Optical Response References

### CH4 Absorption Spectrum (Tutorial: Optical Spectra from Time-Propagation)

| Parameter | Value |
|-----------|-------|
| **Pseudopotential** | `standard` (PSF) |
| **BoxShape** | `minimum` |
| **Radius** | 3.5 Å |
| **Spacing** | 0.18 Å |
| **CH bond length** | 1.097 Å |
| **TDPropagator** | `aetrs` |
| **TDTimeStep** | 0.0023 /eV |
| **TDMaxSteps** | 4350 |
| **Propagation time** | ~10 ℏ/eV |
| **TDDeltaStrength** | 0.01/angstrom |
| **TDPolarizationDirection** | 1 (x) |

**Spectral properties:**
- **First absorption peak**: ~**9.2 eV** (singlet)
- **f-sum rule** (to 20 eV): **3.68** (should be ~8 for full spectrum)
- **Static polarizability** (from sum rule): **2.06 Å³**

### CH4 Absorption Spectrum Convergence (Tutorial: Convergence of Optical Spectra)

**Spacing convergence:**
- sp=0.24 Å is sufficient to converge peak positions to within 0.1 eV

**Radius convergence:**
- R=6.5 Å is necessary to converge the first peak (~9.2 eV) to within 0.1 eV

**Literature comparison:**
- **Octopus time-propagation**: ~9.2 eV
- **Octopus Casida**: 9.278 eV
- **Matsuzawa et al. (2001) TDDFT**: **9.25 eV**
- **Experimental**: **9.6 eV**

### CH4 Casida (Tutorial: Optical Spectra from Casida)

| Parameter | Value |
|-----------|-------|
| **Radius** | 6.5 Å |
| **Spacing** | 0.24 Å |
| **ExtraStates** | 12 (converged 10) |

**Excitation energies:**

| State | Energy (eV) | Degeneracy | Oscillator strength |
|-------|------------:|-----------:|--------------------:|
| 1-3 | **9.278** | 3 (triply degenerate) | 0.095 |
| 4-5 | 10.249 | 2 | ~0 |
| 6-8 | 10.265 | 3 | 0.010 |

**Transition analysis (State 1 at 9.278 eV):**
- Dominant transition: HOMO → LUMO (state 3 → state 5, ~74.7%)
- Small contributions from other transitions

### CH4 Triplet Excitations (Tutorial: Triplet Excitations)

**Time-propagation results:**
- **First triplet transition**: **9.05 eV**
- Slightly lower than the first singlet (9.2 eV), as expected

**Casida triplet results:**
- Available via `CasidaCalcTriplet = yes`
- Spectrum qualitatively similar to time-propagation

---

## H2O Water Molecule References

### H2O Sternheimer Linear Response (Tutorial: Sternheimer Linear Response)

| Parameter | Value |
|-----------|-------|
| **Coordinates** (Bohr) | O(0.000, -0.554, 0.000), H(±1.430, 0.554, 0.000) |
| **BoxShape** | Not specified (default = minimum) |
| **Radius** | 10 (Bohr, from input) = **5.29 Å** |
| **Spacing** | 0.435 (Bohr) = **0.23 Å** |
| **ConvRelDens** | 1e-6 |

**Static polarizability tensor** (at ω=0):

| Component | Value (bohr³) |
|-----------|--------------:|
| α_xx | 10.239 |
| α_yy | 10.772 |
| α_zz | 9.677 |
| **Isotropic average** | **10.229** |

> 1 bohr³ = 0.14818 Å³, so α_iso ≈ 1.516 Å³

**Dynamic polarizability frequencies:**
- ω = 0.00, 0.15, 0.30 Hartree (with η = 0.1 eV broadening)

### H2O Vibrational Modes (Tutorial: Vibrational Modes)

| Parameter | Value |
|-----------|-------|
| **Initial geometry** (Å) | O(0.000, 0.000, 0.0), H(±0.757, 0.586, 0.0) |
| **BoxShape** | `minimum` |
| **Spacing** | 0.16 Å |
| **Radius** | 4.5 Å |
| **FilterPotentials** | `filter_ts` |
| **GOMethod** | `fire` |

**Calculated vibrational frequencies** (before full optimization):

| Mode | Frequency (cm⁻¹) | Type |
|------|-----------------:|------|
| 1 | 3722.8 | Asymmetric stretch |
| 2 | 3619.5 | Symmetric stretch |
| 3 | 1539.1 | Bending |
| 4-6 | ~282, 196, 156 | Translations/Rotations (spurious) |
| 7-9 | -215, -259, -262 | Imaginary (geometry not fully optimized) |

**Experimental vibrational frequencies:**
- ν₁ (symmetric stretch): ~3657 cm⁻¹
- ν₂ (bending): ~1595 cm⁻¹
- ν₃ (asymmetric stretch): ~3756 cm⁻¹

> Note: The negative frequencies indicate the geometry was not fully optimized before vibrational mode calculation. The tutorial is illustrative, not a converged production run.

---

## Sodium Trimer (Tutorial: Geometry Optimization)

| Parameter | Value |
|-----------|-------|
| **Method** | `go` with `GOMethod = cg_bfgs` |
| **Spacing** | 0.3 Å |
| **Radius** | 6.0 Å |
| **BoxShape** | `minimum` |

**Optimized energy**: **-16.89 eV**

---

## Code Locations

- `scripts/run_multi_agent_orchestration.py` (orchestrator references)
- `scripts/run_dft_tddft_agent_suite.py` (suite references)
- `docs/octopus_case_convergence.md` (convergence log)

## Changelog

- **2026-05-05**: Created. Comprehensive compilation of Octopus official tutorial reference data. Explicitly identified PSF vs builtin_standard pseudopotential mismatch.
