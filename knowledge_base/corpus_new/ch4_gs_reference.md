# CH₄ (Methane) Ground-State Reference (Verified — Octopus Tutorial 16)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `ch4_gs_reference` |
| **Category** | DFT ground-state / molecular / convergence study |
| **Primary Source** | [Octopus Tutorial 16 — Total Energy Convergence](https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/) |
| **Source Type** | `official_tutorial` |
| **Extracted By** | Direct HTML extraction from official page (2026-04-16) |
| **Software Version** | Octopus 16 |
| **System** | CH₄ molecule (methane) |
| **Units** | **eV** (script uses `UnitsOutput = eV_Angstrom`) |
| **Confidence Tier** | **A-ready** |

## System Definition

- **Formula**: CH₄ (tetrahedral geometry)
- **Valence electrons**: 10 (under pseudopotential for C and H)
- **Calculation Mode**: `gs`
- **Geometry**: C at origin; H at tetrahedral positions with bond length CH = 1.2 Å
- **Pseudopotential**: Default (no explicit `%Species` block; Octopus uses built-in standard pseudopotentials)
- **XC Functional**: LDA

## Grid Convergence Data (Spacing Scan)

> **Unit**: eV (because `UnitsOutput = eV_Angstrom` is set in the input)
> **Source**: PRE 9 table in official tutorial HTML

| Spacing (Å) | Total Energy (eV) | Total Energy (Ha) |
|------------:|------------------:|------------------:|
| 0.22 | -219.03767589 | -8.0495 |
| 0.20 | -218.58409056 | -8.0328 |
| **0.18** | **-218.27963068** | **-8.0216** |
| 0.16 | -218.20008101 | -8.0187 |
| 0.14 | -218.17904584 | -8.0179 |
| 0.12 | -218.15967953 | -8.0172 |
| 0.10 | -218.13929288 | -8.0165 |

## Convergence Statement (verbatim from tutorial)

> "As you can see from this picture, the total energy is converged to within 0.1 eV
> for a spacing of 0.18 Å."

## Convergence Check

| Pair | ΔE (eV) | Notes |
|------|----------|-------|
| 0.20 → 0.18 | 0.304 | |
| 0.18 → 0.16 | 0.080 | **< 0.1 eV ✅** |
| 0.16 → 0.14 | 0.021 | |
| 0.14 → 0.12 | 0.019 | |
| 0.12 → 0.10 | 0.020 | |

The 0.1 eV convergence criterion is satisfied between 0.18 → 0.16 Å.

## Recommended Reference Value at spacing = 0.18 Å

| Quantity | Value | Unit |
|----------|------:|------|
| Total Energy | **-218.27963068** | **eV** |
| Total Energy | **-8.0216** | **Ha** |

## Octopus Input File (from tutorial)

```bash
CalculationMode = gs
UnitsOutput = eV_Angstrom
FromScratch = yes
Radius = 3.5*angstrom
Spacing = 0.22*angstrom
CH = 1.2*angstrom
%Coordinates
  "C" | 0 | 0 | 0
  "H" | CH/sqrt(3) | CH/sqrt(3) | CH/sqrt(3)
  "H" | -CH/sqrt(3) | -CH/sqrt(3) | CH/sqrt(3)
  "H" | CH/sqrt(3) | -CH/sqrt(3) | -CH/sqrt(3)
  "H" | -CH/sqrt(3) | CH/sqrt(3) | -CH/sqrt(3)
%
EigenSolver = chebysheet_filter
ExtraStates = 4
```

> **Note**: For convergence study, change `Spacing` to sweep values: 0.22, 0.20, 0.18, 0.16, 0.14, 0.12, 0.10 Å.
> For production run, use `Spacing = 0.18*angstrom`.

## Reproducibility Metadata

- `xc`: LDA
- `pseudo_family`: Default (standard C and H pseudopotentials; Octopus auto-selects)
- `grid`: Spacing variable
- `geometry_ref`: CH₄ tetrahedral; CH bond length = 1.2 Å
- `convergence_criterion`: ΔE < 0.1 eV between adjacent spacings

## Usage in Reviewer

- Compare computed total energy at **spacing = 0.18 Å** against **-218.27963068 eV** (= -8.0216 Ha)
- Tolerance: `tolerance_relative: 0.01` (1%)
- **Unit must be stated** — eV (native) and Ha (converted)

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/run_dft_tddft_agent_suite.py` | `ch4_gs_reference` in `CLASSIC_CASE_REFERENCES` |
| `orchestration/execution_wake_state_machine.json` | `ch4_gs_reference` in `golden_cases` |

## Known Limitations

1. **Pseudopotential only**: 10 valence electrons; core electrons replaced by pseudopotentials
2. **LDA only**: No PBE/GGA variants in tutorial
3. **Bond length not converged**: CH = 1.2 Å is a starting guess (tutorial mentions geometry optimization later)

## Changelog

- 2026-04-16: Re-extracted from raw HTML (PRE 9 table). Corrected units — energies are in **eV**, not Ha. Updated reference value and conversion to Ha.
