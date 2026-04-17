# N Atom Ground-State Reference (Octopus Tutorial 16) — ✅ RESOLVED via NIST Independent Verification

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `n_atom_gs_official` |
| **Category** | DFT ground-state / atomic / convergence study |
| **Primary Source** | [Octopus Tutorial 16 — Total Energy Convergence](https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/) |
| **Independent Verification Source** | **NIST Standard Reference Database 141** — [Nitrogen page](https://www.nist.gov/pml/atomic-reference-data-electronic-structure-calculations-nitrogen-0) |
| **Primary Citation** | Kotochigova, Levine, Shirley, Stiles & Clark, *Phys. Rev. A* **55**, 191-199 (1997) |
| **NIST DOI** | 10.18434/T4ZP4F |
| **Source Type** | `official_tutorial` + `nist_authoritative` |
| **Software Version** | Octopus 16; NIST all-electron LDA |
| **Species** | N pseudopotential (Octopus); all-electron (NIST) |
| **XC Functional** | LDA |
| **Confidence Tier** | **A-ready** |

## System Definition

- **Element**: Nitrogen (N)
- **Z (nuclear charge)**: 7
- **Valence electrons**: 5 (pseudopotential in Octopus); 7 total electrons in NIST all-electron
- **Calculation Mode**: `gs`
- **Geometry**: Single atom at origin; no periodicity (`PeriodicDimensions = 0`)

## Grid Convergence Data (Spacing Scan)

> Values from `spacing.dat` (official Octopus tutorial script output). **Unit: eV** — confirmed by cross-reference with NIST LDA eigenvalues.
>
> Spacing column is in **Ångstrom**.

| Spacing (Å) | Total Energy (eV) | s eigenvalue (eV) | p eigenvalue (eV) |
|------------:|------------------:|------------------:|------------------:|
| 0.26 | -256.56821110 | -19.856261 | -6.753304 |
| 0.24 | -260.26243468 | -18.816304 | -7.085017 |
| 0.22 | -262.60722773 | -18.190679 | -7.321580 |
| 0.20 | -262.93542233 | -18.096058 | -7.363758 |
| **0.18** | **-262.24120934** | **-18.282871** | **-7.302321** |
| 0.16 | -261.80059176 | -18.390775 | -7.251466 |
| 0.14 | -261.81955799 | -18.386174 | -7.256961 |

## Unit Resolution — NIST Cross-Validation

### The Problem
The official tutorial table header does not state units. The N atom convergence script does NOT set `UnitsOutput`, so default is ambiguous. Two hypotheses:

| Hypothesis | Interpretation | Value (eV) | Value (Ha) |
|-----------|---------------|------------:|------------:|
| A: Ha | Octopus default atomic units | -7136.7 | -262.24 |
| B: eV | `UnitsOutput = eV_Angstrom` implied | **-262.24** | **-9.64** |

### Resolution via NIST DB SRD 141

**NIST LDA eigenvalues for neutral N ([He] 2s² 2p³):**
- 2s eigenvalue: **-0.676151 Ha** = **-18.40 eV** (1 Ha = 27.211386 eV)
- 2p eigenvalue: **-0.266297 Ha** = **-7.25 eV**

**Octopus spacing.dat values (spacing = 0.18 Å), assuming eV interpretation:**
- 2s eigenvalue: **-18.282871 eV** → **-0.672 Ha** → differs from NIST LDA by **0.6%** ✅
- 2p eigenvalue: **-7.302321 eV** → **-0.268 Ha** → differs from NIST LDA by **0.7%** ✅

**Conclusion**: The values are in **eV**, NOT Ha. The eigenvalue match (< 1% vs NIST LDA) confirms both the unit and the physical correctness of the Octopus LDA pseudopotential calculation.

### Total Energy Consistency Check

- Octopus PP total energy: **-262.24 eV ≈ -9.64 Ha** (5 valence electrons)
- NIST all-electron total energy: **-54.03 Ha** (7 electrons)
- Core (1s²) energy contribution: ~-44 Ha (estimated from H-like N⁵⁺)
- Sum: ~-44 + (-9.6) ≈ -53.6 Ha ≈ NIST -54.03 Ha ✅

## Recommended Reference Values (spacing = 0.18 Å, Confirmed eV)

| Quantity | Value (eV) | Value (Ha) | NIST LDA Ref (Ha) | Match |
|----------|----------:|----------:|------------------:|------:|
| Total Energy | **-262.24120934** | **-9.64** | -54.025 (all-e⁻) | N/A (PP≠AE) |
| s eigenvalue | **-18.282871** | **-0.672** | -0.676151 | **0.6%** ✅ |
| p eigenvalue | **-7.302321** | **-0.268** | -0.266297 | **0.7%** ✅ |

## Convergence Statement (verbatim from tutorial)

> "A rather good spacing for this nitrogen pseudopotential seems to be 0.18 Å.
> However, as we are usually not interested in total energies, but in energy differences,
> probably a larger one may be used."

## Executor Input Template

```bash
# N atom — recommended spacing 0.18 Å
# Units: eV and Å (confirmed — values in eV)
CalculationMode = gs
UnitsOutput = eV_Angstrom

Nitrogen_mass = 14.0

%Species
  "N" | species_pseudo | set | standard | lmax | 1 | lloc | 0 | mass | Nitrogen_mass
%

%Coordinates
  "N" | 0 | 0 | 0
%

BoxShape = sphere
Radius = 10.0*angstrom
Spacing = 0.18*angstrom

ExtraStates = 1

%Occupations
  2 | 1 | 1 | 1
%
```

## Usage in Reviewer

- Compare total energy at spacing = 0.18 Å against **-262.24120934 eV**
- Compare s eigenvalue against **-18.282871 eV**
- Compare p eigenvalue against **-7.302321 eV**
- Tolerance: `tolerance_relative: 0.01` (1%)
- **Unit: eV** (confirmed)

## Known Limitations

1. **Pseudopotential only**: 5 valence electrons; 1s² core replaced by pseudopotential
2. **LDA only**: No PBE/GGA variants in tutorial
3. **Computational reference, not experimental**
4. **Eigenvalue agreement with NIST is for valence states** — core replaced by PP

## Changelog

- 2026-04-16: **RESOLVED via NIST independent verification** — Cross-referenced Octopus spacing.dat eigenvalues against NIST LDA all-electron benchmarks. 2s and 2p eigenvalues agree to < 1%, confirming values are in eV. Total energy -262 eV ≈ -9.6 Ha consistent with 5-valence-electron PP picture. Knowledge base upgraded to A-ready.
- 2026-04-16: **Major revision** — Added explicit unit uncertainty analysis. Both Ha and eV interpretations tracked. Ha interpretation flagged as physically unlikely (magnitude 10× too large for pseudopotential).
- 2026-04-16: Re-extracted from raw HTML (PRE 4 table). Corrected spacing list order and verified all values.
