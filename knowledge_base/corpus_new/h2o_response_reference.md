# H₂O Response Properties Reference — Octopus Official Tutorial

> **Status (2026-05-05)**: Official Octopus tutorial data. No ground-state total energy reference available in official tutorials for H₂O.
> **Source**: Octopus Documentation 12/16, Sternheimer Linear Response + Vibrational Modes tutorials

## Important Note

**Octopus official tutorials do NOT provide a ground-state total energy reference for H₂O.** The molecule appears only in response-property tutorials (Sternheimer linear response, vibrational modes, PCM solvation), which focus on derived properties rather than absolute total energies.

---

## Sternheimer Linear Response (Electric-Dipole Response)

| Parameter | Value |
|-----------|-------|
| **Source tutorial** | [Sternheimer linear response](https://octopus-code.org/documentation/12/tutorial/unsorted/sternheimer_linear_response/) |
| **Coordinates** (Bohr) | O(0.000, -0.554, 0.000), H(±1.430, 0.554, 0.000) |
| **BoxShape** | `minimum` (default) |
| **Radius** | 10 Bohr = **5.29 Å** |
| **Spacing** | 0.435 Bohr = **0.23 Å** |
| **ConvRelDens** | 1e-6 |
| **XCFunctional** | LDA (default) |

### Static Polarizability Tensor

| Component | Value (bohr³) | Value (Å³) |
|-----------|--------------:|-----------:|
| α_xx | 10.239 | 1.517 |
| α_yy | 10.772 | 1.596 |
| α_zz | 9.677 | 1.434 |
| **Isotropic average α_iso** | **10.229** | **1.516** |

> Conversion: 1 bohr³ = 0.14818 Å³

### Dynamic Polarizability

Frequencies calculated: ω = 0.00, 0.15, 0.30 Hartree
- Broadening: η = 0.1 eV
- Linear solver: `qmr_dotp`

---

## Vibrational Modes (Sternheimer Linear Response)

| Parameter | Value |
|-----------|-------|
| **Source tutorial** | [Vibrational Modes](https://octopus-code.org/documentation/main/tutorial/unsorted/vibrational_modes/) |
| **Initial geometry** (Å) | O(0.000, 0.000, 0.0), H(±0.757, 0.586, 0.0) |
| **BoxShape** | `minimum` |
| **Spacing** | 0.16 Å |
| **Radius** | 4.5 Å |
| **FilterPotentials** | `filter_ts` |
| **GOMethod** | `fire` |

### Calculated Frequencies

| Mode | Frequency (cm⁻¹) | Classification |
|------|-----------------:|----------------|
| 1 | 3722.8 | Asymmetric stretch |
| 2 | 3619.5 | Symmetric stretch |
| 3 | 1539.1 | Bending |
| 4-6 | ~283, 196, 156 | Translation/Rotation (spurious) |
| 7-9 | -215, -259, -262 | Imaginary (geometry not converged) |

> ⚠️ **Caveat**: Negative frequencies indicate the initial geometry was not at the true energy minimum. The tutorial is illustrative, not a converged production result.

### Experimental Reference

| Mode | Experimental (cm⁻¹) | Description |
|------|--------------------:|-------------|
| ν₁ (symmetric stretch) | 3657 | A₁ |
| ν₂ (bending) | 1595 | A₁ |
| ν₃ (asymmetric stretch) | 3756 | B₂ |

### Comparison

| Quantity | Tutorial (cm⁻¹) | Experimental (cm⁻¹) | Error |
|----------|----------------:|--------------------:|------:|
| Symmetric stretch | 3619.5 | 3657 | **1.0%** |
| Bending | 1539.1 | 1595 | **3.5%** |
| Asymmetric stretch | 3722.8 | 3756 | **0.9%** |

> Despite the negative spurious modes, the physical vibrational frequencies are within 1-3.5% of experiment.

---

## Implications for H₂O Ground-State Reference

Since Octopus official tutorials do not provide a ground-state total energy for H₂O, the `-17.17 Ha` value used in `h2o_gs_official` remains a **self-consistent working reference** without independent tutorial verification.

**Recommended alternative validation strategies:**

1. **Physical observables** (independent of absolute energy):
   - Dipole moment: experimental 1.85 D
   - HOMO energy: experimental vertical ionization ~12.6 eV
   - Bond lengths/angles: experimental 0.958 Å / 104.5°
   - Vibrational frequencies: experimental 1595, 3657, 3756 cm⁻¹

2. **Cross-code verification**:
   - Run same geometry with Quantum ESPRESSO / ABINIT using same Troullier-Martins LDA pseudopotentials
   - Compare total energy and eigenvalues

3. **Atomization energy**:
   - Calculate E(2H) + E(O) - E(H₂O) with same settings
   - Compare to experimental 9.51 eV

## Full Provenance

- Sternheimer tutorial: Andrade et al., J. Chem. Phys. **126**, 184106 (2007)
- Vibrational modes tutorial: Octopus official documentation
- Experimental H₂O data: NIST Chemistry WebBook

## Code Locations

- `knowledge_base/corpus_new/h2o_gs_pseudopotential_reference.md`
- `docs/octopus_case_convergence.md`

## Changelog

- **2026-05-05**: Created. Explicitly documents the absence of H₂O ground-state total energy in Octopus official tutorials. Provides response-property references as alternative benchmarks.
