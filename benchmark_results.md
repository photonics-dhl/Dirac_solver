# Octopus DFT/TDDFT Benchmark Results

> 收敛的仿真参数、计算结果、参考结果、参考来源的统一记录文档。
> 每个成功的案例都应合并到本文档中。

---

## Case: N Atom Ground-State (Octopus Tutorial 16)

### Case ID
`n_atom_gs_official`

### Status
⚠️ Converged — Unit Ambiguous (Ha vs eV unresolved; re-run with UnitsOutput=eV_Angstrom required)

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
| UnitsOutput | default (Hartree) — **not** eV_Angstrom |

### Calculation Results

| Quantity | Calculated Value (Ha) | Calculated Value (eV) |
|----------|----------------------:|----------------------:|
| Total Energy | **-262.24120934** | **-7136.7** |
| s eigenvalue | **-18.282871** | **-497.6** |
| p eigenvalue | **-7.302321** | **-198.8** |

> Conversion: 1 Ha = 27.211386 eV

### Reference Results

| Quantity | Reference Value (Ha) | Reference Value (eV) | Source |
|----------|---------------------:|---------------------:|--------|
| Total Energy (finest grid, 0.14 Å) | -261.78536939 | -7125.2 | gnuplot offset in tutorial |
| s eigenvalue (finest grid) | -18.389733 | -500.4 | gnuplot offset in tutorial |
| p eigenvalue (finest grid) | -7.248998 | -197.3 | gnuplot offset in tutorial |

### Grid Convergence Data

| Spacing (Å) | Total Energy (Ha) | s eigenvalue (Ha) | p eigenvalue (Ha) |
|------------:|------------------:|------------------:|------------------:|
| 0.26 | -256.56821110 | -19.856261 | -6.753304 |
| 0.24 | -260.26243468 | -18.816304 | -7.085017 |
| 0.22 | -262.60722773 | -18.190679 | -7.321580 |
| 0.20 | -262.93542233 | -18.096058 | -7.363758 |
| **0.18** | **-262.24120934** | **-18.282871** | **-7.302321** |
| 0.16 | -261.80059176 | -18.390775 | -7.251466 |
| 0.14 | -261.81955799 | -18.386174 | -7.256961 |

### Verification

- [TODO] Executor run at spacing = 0.18 Å → compare against -262.24120934 Ha
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
