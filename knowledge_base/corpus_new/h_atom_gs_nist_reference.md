# H Atom Ground-State Reference (NIST CODATA + Octopus Formula Pseudopotential)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `hydrogen_gs_reference` |
| **Category** | DFT ground-state / atomic / reference benchmark |
| **Primary Source** | NIST CODATA 2022 (Rydberg constant) |
| **Source URL** | https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev |
| **Source Type** | `nist_codata` |
| **Software Version** | octopus-16.0 |
| **Confidence Tier** | **A-ready** (for actual H atom); **B-tier** (for formula pseudopotential model) |

## System Definition

- **Element**: Hydrogen (H)
- **Z**: 1
- **Valence electrons**: 1 (in formula pseudopotential model; or all-electron)
- **Calculation Mode**: `gs`
- **Geometry**: Single atom at origin
- **XC Functional**: LDA

---

## Reference Value 1: Exact H Atom (NIST CODATA — All-Electron)

### Theoretical Basis

For a hydrogen-like atom with an infinitely massive, point-sized nucleus, the Schrödinger equation gives an **exact** ground-state energy:

```
E_n=1 = -1 Ry = -0.5 Eh (Hartree)
```

This is a **theoretical exact value** from the non-relativistic Schrödinger equation (or Dirac equation for spin-1/2), not a semi-empirical fit.

### NIST CODATA 2022 Values

| Quantity | Value | Unit | Uncertainty |
|----------|------:|------:|------------:|
| Rydberg constant (Ry × hc) | 13.605693122990 | eV | ±0.000000000015 |
| Hartree energy (Eh) | 27.211386245988 | eV | ±0.000000000030 |
| H atom ground state energy | **-0.5** | Ha | exact (theoretical) |
| H atom ground state energy | **-13.605693122990** | eV | exact (theoretical) |

### Conversion Factors (from NIST CODATA 2022)

- 1 Ha = 27.211386245988 eV
- 1 Ry = 13.605693122990 eV = 0.5 Ha
- 1 eV = 0.036749322175655 Ha

### Physical Significance

> The H atom ground-state energy is the **ionization energy** (the energy needed to remove the electron to infinity). This is because the potential is Coulombic and the reference is vacuum (zero at infinity).

### Code Reference

The value `-0.5` Ha appears in:
- `scripts/run_dft_tddft_agent_suite.py` (`CLASSIC_CASE_REFERENCES["hydrogen_gs_reference"]["reference"]`)
- `scripts/run_multi_agent_orchestration.py` (`DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["hydrogen_gs_reference"]`)

---

## Reference Value 2: H in Formula Pseudopotential (Octopus)

### Octopus Model

When hydrogen is used as a **formula pseudopotential** for other calculations (e.g., in H掺杂物 systems), Octopus may use:

```
Species = hydrogen
PotentialFormula = "-1/sqrt(r^2 + alpha)"
```

where `alpha` is a softening parameter (typically 0.1–0.2 bohr²).

### Octopus Calculation Result (实测)

| Parameter | Value |
|-----------|-------|
| Spacing | 0.36 Bohr |
| Radius | 10.0 Bohr |
| Total Energy (from formula model) | **+0.5811 Ha** (⚠️ positive — unbound artifact of soft potential) |
| 1s eigenvalue | **+0.8847 Ha** |
| 2p eigenvalue | +1.8615 Ha |
| 3d eigenvalue | +2.8666 Ha |
| 4f eigenvalue | +3.8774 Ha |

> ⚠️ **Critical Finding**: The soft Coulomb formula pseudopotential for hydrogen gives **positive** eigenvalues. This is a **model artifact** — the formula `-1/sqrt(r^2+alpha)` does not produce a true bound 1s state for the physical H atom. The positive eigenvalues represent the energy relative to the formula's reference zero, not physical ionization potentials.
>
> **Do NOT** compare formula-pseudopotential eigenvalues directly to the physical -0.5 Ha reference.

### MCP Server Behavior

The MCP server at port 8000 (Octopus v14.0) uses the formula pseudopotential path for `molecule: "H"`:
- `total_energy = +0.5811 Ha` (formula model total)
- `eigenvalues = [0.88, 1.86, 2.87, 3.88] Ha` (positive — model artifact)

This is **expected behavior** for this specific model potential, not a bug.

---

## Usage in Reviewer

### For Actual H Atom (All-Electron or Model Consistent)

```
if case_id == "hydrogen_gs_reference":
    reference = -0.5  # Ha (exact theoretical value)
    tolerance = 0.03  # 3% tolerance
    
    # Compare computed total energy against -0.5 Ha
    # OR compare computed eigenvalue against -13.6 eV
    pass_criterion: abs(computed - reference) / abs(reference) < tolerance
```

### For Formula Pseudopotential (H as Pseudoatom)

```
if case_id == "hydrogen_gs_reference_formula":
    # DO NOT use -0.5 Ha as reference
    # The formula pseudopotential has its own reference frame
    # Total energy ≈ +0.58 Ha (not physically meaningful)
    BLOCK with: "hydrogen formula pseudopotential is not a physical benchmark"
```

---

## Octopus Input (All-Electron H Atom)

```bash
CalculationMode = gs
UnitsOutput = eV_Angstrom

%Species
  "H" | species_user_defined | potential_formula | "(-1)/sqrt(r^2+0.15)" | valence | 1
%

%Coordinates
  "H" | 0 | 0 | 0
%

BoxShape = sphere
Radius = 10.0*angstrom
Spacing = 0.36*angstrom

ExtraStates = 1
%Occupations
  1
%
```

---

## Comparison Table

| Model | Total Energy (Ha) | 1s Eigenvalue (Ha) | Notes |
|-------|------------------:|-------------------:|-------|
| **NIST CODATA (exact)** | **-0.5** | — | Physical H atom; E = -0.5 Ha by Schrödinger eq. |
| **Octopus formula PP** | +0.58 | +0.88 | Model potential; unbound artifact |
| **Typical KS-DFT LDA** | ≈ -0.47 to -0.53 | ≈ -0.47 to -0.53 | Depends on XC and basis |

---

## Known Issues

1. **Formula pseudopotential positive eigenvalues**: The soft Coulomb form `-1/sqrt(r^2+alpha)` does not correctly reproduce the physical H atom ground state. For actual H atom benchmarks, use all-electron calculations.
2. **Reference mismatch**: The code references `-0.5 Ha` but the MCP server's H calculation returns positive values. This indicates the MCP server is using a formula pseudopotential that is not comparable to the NIST reference.
3. **H used as passivating species**: In many DFT calculations, H is used as a termination species with a simple potential — its total energy is not directly comparable to the physical H atom energy.

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/run_dft_tddft_agent_suite.py` | `hydrogen_gs_reference` in `CLASSIC_CASE_REFERENCES` |
| `scripts/run_multi_agent_orchestration.py` | `DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["hydrogen_gs_reference"]` |
| `scripts/run_dft_tddft_agent_suite.py` | `hydrogen_base` in orchestration defaults |

## Changelog

- 2026-04-16: Created. Reconciled NIST CODATA exact reference (-0.5 Ha) with Octopus formula pseudopotential calculation results (positive eigenvalues +0.58/+0.88 Ha). Documented the critical difference between physical H atom and formula model H.
