# Octopus DFT/TDDFT Benchmark Results

> 收敛的仿真参数、计算结果、参考结果、参考来源的统一记录文档。
> 每个成功的案例都应合并到本文档中。

---

## Case: N Atom Ground-State (Octopus Tutorial 16)

### Case ID
`n_atom_gs_official`

### Status
✅ Resolved — Unit confirmed as eV via NIST SRD 141 cross-validation

### Provenance

| Field | Value |
|-------|-------|
| **Primary Source** | [Octopus Tutorial 16 — Total Energy Convergence](https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/) |
| **Source Type** | `official_tutorial` |
| **Software Version** | Octopus 16 |
| **Extraction Date** | 2026-04-16 |
| **Confidence Tier** | **A-ready** |

### System Definition

| Parameter | Value |
|-----------|-------|
| Element | Nitrogen (N) |
| Z (nuclear charge) | 7 |
| Valence electrons | 5 (pseudopotential; 1s² core replaced) |
| Calculation Mode | `gs` |
| XC Functional | LDA |
| Pseudopotential | Standard N pseudopotential (`species_pseudo = set | standard`) |
| Geometry | Single atom at origin; no periodicity (`PeriodicDimensions = 0`) |

### Simulation Parameters (Converged)

| Parameter | Value |
|-----------|-------|
| Spacing | **0.18 Å** |
| BoxShape | sphere (default for atoms) |
| Radius | 10.0 Å |
| ExtraStates | 1 |
| UnitsOutput | **eV** (confirmed; `UnitsOutput = eV_Angstrom` recommended) |

### Calculation Results

| Quantity | Calculated Value (eV) | Calculated Value (Ha) |
|----------|----------------------:|----------------------:|
| Total Energy | **-262.24120934** | **-9.64** |
| s eigenvalue | **-18.282871** | **-0.672** |
| p eigenvalue | **-7.302321** | **-0.268** |

> Unit confirmed: **eV** (not Ha). Cross-validated against NIST SRD 141 LDA eigenvalues (< 1% mismatch).

### Reference Results

| Quantity | Reference Value (eV) | Reference Value (Ha) | Source |
|----------|---------------------:|---------------------:|--------|
| Total Energy (finest grid, 0.14 Å) | -261.78536939 | -9.62 | Octopus tutorial finest grid |
| s eigenvalue (finest grid) | -18.389733 | -0.676 | Octopus tutorial finest grid |
| p eigenvalue (finest grid) | -7.248998 | -0.266 | Octopus tutorial finest grid |
| **NIST LDA 2s eigenvalue** | **-18.40 eV** | **-0.676 Ha** | **NIST SRD 141** |
| **NIST LDA 2p eigenvalue** | **-7.25 eV** | **-0.266 Ha** | **NIST SRD 141** |

### Grid Convergence Data

| Spacing (Å) | Total Energy (eV) | s eigenvalue (eV) | p eigenvalue (eV) |
|------------:|------------------:|------------------:|------------------:|
| 0.26 | -256.56821110 | -19.856261 | -6.753304 |
| 0.24 | -260.26243468 | -18.816304 | -7.085017 |
| 0.22 | -262.60722773 | -18.190679 | -7.321580 |
| 0.20 | -262.93542233 | -18.096058 | -7.363758 |
| **0.18** | **-262.24120934** | **-18.282871** | **-7.302321** |
| 0.16 | -261.80059176 | -18.390775 | -7.251466 |
| 0.14 | -261.81955799 | -18.386174 | -7.256961 |

### Verification

- ✅ NIST SRD 141 cross-validation: 2s eigenvalue (-18.28 eV) matches NIST LDA (-18.40 eV) within 0.6%
- ✅ NIST SRD 141 cross-validation: 2p eigenvalue (-7.30 eV) matches NIST LDA (-7.25 eV) within 0.7%
- [TODO] Executor run at spacing = 0.18 Å → compare against -262.24120934 eV
- [TODO] Reviewer PASS gate → record outcome here

### Known Limitations

1. **Pseudopotential only**: 5 valence electrons; 1s² core replaced by pseudopotential
2. **LDA only**: No PBE/GGA variants provided in tutorial
3. **Computational reference, not experimental**

---

## Template for New Cases

When adding a new successful case, copy this template:

```markdown
---

## Case: [CASE NAME]

### Case ID
`[case_id]`

### Status
✅ Converged & Verified / 🔄 In Progress

### Provenance

| Field | Value |
|-------|-------|
| **Primary Source** | [URL or reference] |
| **Source Type** | `official_tutorial` / `literature` / `experiment` / etc. |
| **Software Version** | [version if applicable] |
| **Extraction Date** | YYYY-MM-DD |

### System Definition
[TABLE: element, Z, valence electrons, calculation mode, XC functional, pseudopotential, geometry]

### Simulation Parameters (Converged)
[TABLE: spacing, box shape, radius, and other key parameters]

### Calculation Results
[TABLE with calculated values in appropriate units]

### Reference Results
[TABLE with reference values, units, and sources]

### Grid Convergence Data (if applicable)
[TABLE with spacing scan or other convergence data]

### Verification
- Executor run: [date] → [outcome]
- Reviewer PASS: [date] → [outcome]

### Known Limitations
[List any limitations]
```

---

_This document is the single source of truth for all benchmark results._
_Update after each successful case completion._
