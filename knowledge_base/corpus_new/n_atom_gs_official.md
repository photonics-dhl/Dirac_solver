# N Atom Ground-State Reference (Octopus Tutorial 16) — UNIT UNCERTAINTY

> ⚠️ **STATUS: UNIT CANNOT BE DETERMINED UNAMBIGUOUSLY FROM TUTORIAL ALONE**
>
> The values in the official Octopus Tutorial 16 spacing scan table are **numerically identical** regardless of unit (Ha or eV), making the unit ambiguous from the table alone. This document tracks both interpretations. **Resolution requires re-running the N atom convergence script with `UnitsOutput = eV_Angstrom` explicitly set.**

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `n_atom_gs_official` |
| **Category** | DFT ground-state / atomic / convergence study |
| **Primary Source** | [Octopus Tutorial 16 — Total Energy Convergence](https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/) |
| **Source Type** | `official_tutorial` |
| **Extracted By** | Direct HTML extraction from official page (2026-04-16) |
| **Software Version** | Octopus 16 |
| **Species** | N pseudopotential (`species_pseudo = set | standard`; 5 valence electrons) |
| **XC Functional** | LDA (default in Octopus) |
| **Confidence Tier** | **B-UNVERIFIED** (unit ambiguous) |

## System Definition

- **Element**: Nitrogen (N)
- **Z (nuclear charge)**: 7
- **Valence electrons**: 5 (pseudopotential; 1s² core represented by pseudopotential)
- **Calculation Mode**: `gs`
- **Geometry**: Single atom at origin; no periodicity (`PeriodicDimensions = 0`)

## Grid Convergence Data (Spacing Scan)

> Values from `spacing.dat` (official tutorial script output). **Unit is NOT stated in the table header.**
>
> Spacing column is in **Ångstrom**.

| Spacing (Å) | Total Energy | s eigenvalue | p eigenvalue |
|------------:|-------------:|-------------:|-------------:|
| 0.26 | -256.56821110 | -19.856261 | -6.753304 |
| 0.24 | -260.26243468 | -18.816304 | -7.085017 |
| 0.22 | -262.60722773 | -18.190679 | -7.321580 |
| 0.20 | -262.93542233 | -18.096058 | -7.363758 |
| **0.18** | **-262.24120934** | **-18.282871** | **-7.302321** |
| 0.16 | -261.80059176 | -18.390775 | -7.251466 |
| 0.14 | -261.81955799 | -18.386174 | -7.256961 |

## Unit Analysis

### Hypothesis 1: Values in Hartree (Ha)
> N atom script does NOT set `UnitsOutput`, so Octopus defaults to atomic units (Hartree).

| Quantity | Value (Ha) | Value (eV) |
|----------|----------:|----------:|
| Total Energy (0.18 Å) | -262.24120934 | **-7136.7** |
| s eigenvalue | -18.282871 | -497.6 |
| p eigenvalue | -7.302321 | -198.8 |

**Problem**: -262 Ha ≈ -7136 eV is ~10× too large in magnitude for a 5-valence-electron N pseudopotential calculation. Cross-reference: O atom (Z=8, all-electron 8e) = -68.32 Ha; N atom (Z=7, all-electron 7e) ≈ -54 Ha; N pseudopotential (5e) should be ≈ -10 to -30 Ha.

**Verdict**: ⚠️ **Unlikely** — magnitude inconsistent with physics

### Hypothesis 2: Values in Electronvolts (eV)
> N atom script uses default Octopus output; table header does not indicate units.

| Quantity | Value (eV) | Value (Ha) |
|----------|----------:|----------:|
| Total Energy (0.18 Å) | -262.24120934 | **-9.64** |
| s eigenvalue | -18.282871 | -0.67 |
| p eigenvalue | -7.302321 | -0.27 |

**Cross-validation**:
- s eigenvalue -18 eV ≈ -0.67 Ha: Reasonable for a 2s orbital in N pseudopotential (effective Z~4-5)
- p eigenvalue -7 eV ≈ -0.26 Ha: Reasonable for a 2p orbital
- Total energy -262 eV ≈ -9.6 Ha: Reasonable for 5 valence electrons

**Verdict**: ✅ **Physically plausible**

### Gnuplot Offset Evidence (PROBLEMATIC)

The gnuplot script in the tutorial:
```gnuplot
set ylabel "Error (eV)"
plot "spacing.dat" u 1:($2+261.78536939) ...
```

The offset +261.78536939 appears to be in Ha (it's added to the tabulated values to get the error in eV). But this is **circular** — it assumes the input values are Ha to make the offset work as eV error. If the values were actually in eV, then +261.78 would be an absurd offset (261.78 eV ≈ 9.6 Ha).

**Conclusion**: The gnuplot evidence is **not definitive** because the offset interpretation assumes the very unit being questioned.

## Recommended Reference Values (spacing = 0.18 Å)

### If values are in Ha (⚠️ unlikely):
| Quantity | Ha |
|----------|---:|
| Total Energy | -262.24120934 |
| s eigenvalue | -18.282871 |
| p eigenvalue | -7.302321 |

### If values are in eV (✅ plausible):
| Quantity | eV |
|----------|---:|
| Total Energy | -262.24120934 |
| s eigenvalue | -18.282871 |
| p eigenvalue | -7.302321 |

## Action Required

**Re-run the convergence script with explicit `UnitsOutput = eV_Angstrom`** to disambiguate. The N atom input template in this document already includes this setting.

## Executor Input Template (FIXED)

```bash
# N atom — recommended spacing 0.18 Å
# Units: eV and Å (UnitsOutput = eV_Angstrom)
# ⚠️ Include UnitsOutput to ensure eV output
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

## Usage in Reviewer (PENDING UNIT RESOLUTION)

- **Unit must be confirmed** before setting reviewer reference values
- Convergence study script MUST be re-run with `UnitsOutput = eV_Angstrom` explicitly
- If confirmed as eV: compare against **-262.24120934 eV**
- Tolerance: `tolerance_relative: 0.01` (1%)

## Known Limitations

1. **UNIT UNCERTAINTY**: Cannot determine Ha vs eV from tutorial data alone
2. **Pseudopotential only**: 5 valence electrons; 1s² core replaced
3. **LDA only**: No PBE/GGA variants
4. **Computational reference, not experimental**
5. **Convergence criterion**: 0.1 eV illustrated graphically; discrete ΔE exceeds it at 0.18→0.16

## Changelog

- 2026-04-16: **Major revision** — Added explicit unit uncertainty analysis. Both Ha and eV interpretations tracked. Ha interpretation flagged as physically unlikely (magnitude 10× too large). Action item: re-run with `UnitsOutput = eV_Angstrom` to resolve.
- 2026-04-16: Re-extracted from raw HTML (PRE 4 table). Corrected spacing list order and verified all values.
