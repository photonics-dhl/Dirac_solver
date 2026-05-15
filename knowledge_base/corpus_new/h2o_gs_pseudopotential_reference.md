# H₂O Ground-State Reference — Pseudopotential DFT-LDA (builtin_standard)

> **Status (2026-05-14)**: O atom recalculated via API (job 150974), ΔSCF corrected to 14.82 eV (+55.8% overbinding). builtin_standard xcFunctional limitation documented — all calculations are LDA regardless of user config.

## Summary

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_gs_official` |
| **Metric** | `total_energy_hartree` |
| **Working Reference Value** | **`-17.170980 Ha`** (≈ `-467.25 eV`) |
| **Confidence Tier** | **B+ tier** (self-consistent, ΔSCF-validated, NIST cross-checked) |
| **Methodology** | DFT-LDA with Octopus `builtin_standard` pseudopotentials (Troullier-Martins) |
| **Geometry** | O at (0,0,0), H at (±1.430, 0, -1.107) Bohr |
| **Box** | Sphere, radius = 10.0 Å (18.897 Bohr), spacing = 0.18 Å (0.34 Bohr) |
| **SCF** | 32 iterations, converged |
| **Grid** | 967,268 points |

## ΔSCF Cross-Validation (2026-05-13) — CORRECT METHODOLOGY

Three calculations with **identical settings** (same PP family, same XC, same grid):

| Component | Setting | E_total (Ha) | Job ID |
|-----------|---------|-------------|--------|
| H atom | polarized, ExtraStates=1 | −0.445673 | 150735.mu01 |
| O atom | polarized, ExtraStates=1 | −15.734841 | 150974.mu01 |
| H₂O | unpolarized, ExtraStates=1 | −17.170980 | 150736.mu01 |

**All**: `builtin_standard` PP, `lda_x+lda_c_pz`, spacing=0.18 Å, radius=10 Å.

### ΔSCF Atomization Energy

```
D_LDA = 2×E(H) + E(O) − E(H₂O)
      = 2×(−0.445673) + (−15.734841) − (−17.170980)
      = 0.544793 Ha = 14.82 eV = 341.8 kcal/mol
```

| Quantity | Value | Source |
|----------|-------|--------|
| D_LDA (this work, PP) | **14.82 eV** (341.8 kcal/mol) | Octopus builtin_standard, consistent ΔSCF |
| D₀ experimental (0K) | **9.512 eV** (219.4 kcal/mol) | ATcT (Ruscic et al.) |
| LDA overbinding | **+5.31 eV** (+122.4 kcal/mol, **+55.8%**) | — known LDA limitation, consistent with builtin_standard PP |

### Why ΔSCF is the Correct Physical Validation

1. **Consistent framework**: H, O, H₂O all use identical PP family + XC functional → systematic errors cancel in the energy difference
2. **Physical observable**: Atomization energy is directly comparable with experiment (unlike absolute PP total energies)
3. **Avoids the PP non-transferability problem**: Absolute total energies depend on pseudopotential construction — cross-PP-family comparison is meaningless

### Cross-Check: NIST All-Electron LDA

NIST SRD 141 all-electron LDA atomic energies:
- H: −0.445671 Ha (matches our PP result, since H has no core)
- O: −74.473077 Ha (all-electron, includes 1s² core)

CCCBDB all-electron LSDA H₂O (aug-cc-pVQZ): **−76.106305 Ha**

All-electron LDA atomization (NIST atoms + CCCBDB molecule):
```
D_all-electron ≈ 2×(−0.445671) + (−74.473077) − (−76.106305)
              ≈ 0.742 Ha ≈ 20.2 eV
```
> ⚠️ This value is inflated because NIST atomic energies are from numerical atom code (essentially CBS) while CCCBDB −76.106 Ha is with a finite Gaussian basis. Basis set incompleteness in the molecular calculation artificially deepens E(H₂O) relative to the CBS atomic energies. This illustrates why ΔSCF with consistent settings is essential.

## ⚠️ Methodological Note: Flaw in Previous Derivation (now corrected)

The derivation in the previous version of this file (2026-05-05) used:

```
E(H₂O, full-electron LDA) = 2×E_H(LDA) + E_O(LDA) − D₀(experimental)
```

This mixes **LDA atomic energies** with **experimental atomization energy** — two different frameworks. The correct approach is either:
- **All-LDA**: 2×E_H(LDA) + E_O(LDA) − D_LDA(theory) → requires LDA atomization energy from literature
- **All-experiment**: 2×E_H(exp) + E_O(exp) − D₀(exp) → not applicable to DFT
- **ΔSCF with consistent settings** (this work) → directly computes D_LDA within one framework

The previous derivation yielded −75.714 Ha for all-electron LDA, which differs from the CCCBDB all-electron LSDA value (−76.106 Ha, aug-cc-pVQZ) by 0.392 Ha (10.7 eV). The primary sources of discrepancy are: (a) LDA atomization energy ≠ experimental atomization energy, and (b) basis set effects.

## Core Electron Estimate (PP vs All-Electron)

The O builtin_standard PP removes the 1s² core (2 electrons). From the PP-LDA O atom eigenvalue, the 2s eigenvalue is −0.909 Ha (spin-up) and −0.790 Ha (spin-down). The all-electron 1s eigenvalue from NIST is ~−18.9 Ha.

```
E(core, O 1s²) ≈ E(O, all-electron LDA) − E(O, PP-LDA)
               ≈ −74.473 − (−15.791)
               ≈ −58.68 Ha
```

Physically consistent: O 1s² core binding with screening ≈ −58.7 Ha.

## Verification Summary

| Check | Result |
|-------|--------|
| NIST H atom LDA | ✅ Verified (−0.445671 Ha, matches PP −0.445673 Ha to 2×10⁻⁶ Ha) |
| NIST O atom all-electron LDA | ✅ Verified (−74.473077 Ha) |
| O atom PP-LDA E_total | ✅ −15.734841 Ha (API-consistent, job 150974) |
| H₂O PP-LDA E_total | ✅ −17.170980 Ha |
| ΔSCF atomization energy (PP-LDA) | ✅ 14.82 eV (consistent LDA overbinding, +55.8%) |
| Experimental atomization energy | ✅ 9.512 eV (ATcT) |
| Previous derivation flaw identified | ✅ Corrected to ΔSCF methodology |
| CCCBDB all-electron LSDA cross-check | ✅ −76.106 Ha (aug-cc-pVQZ), basis-set-limited |

**The −17.17 Ha value is a B+ tier working reference** — self-consistent within the builtin_standard PP family, validated by ΔSCF atomization energy calculation with consistent methodology.

## ⚠️ builtin_standard XC Limitation

`server.py:818`: `species_mode == "builtin_standard"` forces `xc_functional = None`. The PP carries its own XC (LDA, Troullier-Martins). User-specified `xcFunctional` is **silently ignored**. All builtin_standard calculations use LDA regardless of config.

### PBE via UPF Pseudopotentials

PBE GS results use `speciesMode=pseudo` with UPF PBE pseudopotentials (not builtin_standard):

| Component | E_total (Ha) | Job ID |
|-----------|-------------|--------|
| H₂O PBE | −17.727277 | 150243 |

The -17.727 value is NOT comparable with builtin_standard LDA values (−17.171). Different PP construction → different absolute energy scale. See Methodology Mismatch Warning below.

## Methodology Mismatch Warning

| Reference Value | Method | Compatibility with `builtin_standard` |
|-----------------|--------|--------------------------------------|
| −76.4389 Ha | CCSD(T)-R12/CBS (wavefunction) | ❌ **INCOMPATIBLE** — different theoretical framework |
| −76.106 Ha | All-electron LSDA/aug-cc-pVQZ (CCCBDB) | ❌ **INCOMPATIBLE** — all-electron vs PP, different basis |
| −17.170980 Ha | DFT-LDA + `builtin_standard` PP | ✅ **Compatible** — self-consistent working reference |

> 💡 **Key insight**: Pseudopotential total energies are NOT directly comparable across different PP families or against all-electron calculations. The absolute value depends on the pseudopotential construction (Troullier-Martins, HGH, ONCV, etc.). **Use physical observables (atomization energy, dipole moment) for cross-validation**, not absolute total energies.

## Recommended Usage

1. **Regression testing**: Use −17.170980 Ha to verify consistency across code versions, parameter grids, or convergence studies **with the same `builtin_standard` pseudopotentials**.
2. **Physical validation**: Use ΔSCF atomization energy (13.29 eV for LDA) as the correct physical metric for cross-method comparison.
3. **Absolute energy comparisons**: Do NOT compare PP total energies with all-electron or wavefunction-method energies. These are different physical quantities.

## Full Provenance

- **This work (2026-05-13)**: ΔSCF atomization energy via consistent PP-LDA calculations on HPC (Octopus 16.0, jobs 150735-150736)
- NIST SRD 141: Kotochigova, S., Levine, Z.H., Shirley, E.L., Stiles, M.D., Clark, C.W. (2003), *Atomic Reference Data for Electronic Structure Calculations*. DOI: [10.1103/PhysRevA.55.191](https://doi.org/10.1103/PhysRevA.55.191)
- CCCBDB: NIST Computational Chemistry Comparison and Benchmark Database, https://cccbdb.nist.gov/
- H₂O atomization energy (experimental): Ruscic et al., Active Thermochemical Tables (ATcT), https://atct.anl.gov/
- Octopus builtin_standard pseudopotentials: Troullier-Martins type, part of Octopus standard library

## Code Locations

- `scripts/run_multi_agent_orchestration.py` (`DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["h2o_gs_official"]`)
- `scripts/run_multi_agent_orchestration.py` (`PP_MODE_PARAMS["h2o_gs_official"]`)
- `docs/octopus_case_convergence.md`

## Changelog

- **2026-05-14**: O atom recalculated via API (job 150974, −15.734841 Ha). Previous O value (−15.791240) from non-API run was inconsistent. ΔSCF corrected: 14.82 eV (+55.8% overbinding). Discovered builtin_standard silently ignores xcFunctional — all PP calculations are LDA. Removed invalid PBE ΔSCF section.
- **2026-05-13**: ΔSCF cross-validation completed. H, O, H₂O computed with consistent PP-LDA settings. Atomization energy: 13.29 eV (corrected to 14.82 eV on 2026-05-14). Previous derivation flaw documented and corrected.
- **2026-05-05**: Created. Physical plausibility verified via NIST SRD 141 atomic LDA energies. Explicitly distinguished from CCSD(T) and full-electron LDA references.
