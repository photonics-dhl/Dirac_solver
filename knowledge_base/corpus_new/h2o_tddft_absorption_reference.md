# H₂O TDDFT Absorption Reference (Verified — Octopus Tutorial + UI Guide)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_tddft_absorption` |
| **Category** | TDDFT / optical absorption / response function |
| **Primary Source (Official Tutorial)** | [Octopus Tutorial 16](https://www.octopus-code.org/documentation/16/) |
| **Secondary Source (Operational)** | `@Octopus_docs/UI_User_Guide.md` (Chinese system user guide) |
| **Source Type** | `official_tutorial` (primary), `user_guide` (secondary/operational) |
| **Confidence Tier** | **B-needs-evidence** |

> **Provenance Note**: The official Octopus Tutorial 16 lists an H₂O optical absorption example. The specific numerical window [7.0, 8.0] eV is documented in the UI_User_Guide with citation to Octopus official material. For strict benchmarks, verify the peak position directly from the Octopus tutorial example output.

## System Definition

- **Formula**: H₂O
- **Geometry**: Equilibrium geometry (neutral singlet)
- **Calculation Mode**: `td` (time-dependent DFT), preceded by `gs`
- **XC Functional**: LDA (default)
- **Pseudopotential**: Standard pseudopotentials for O and H

## Reference Statement (from UI_User_Guide.md)

> "第一个吸收峰约在 7–8 eV（H₂O 的 first singlet excitation ~7.5 eV，LDA 低估约 0.5 eV）"

English translation:
> "The first absorption peak is approximately 7–8 eV (H₂O first singlet excitation ~7.5 eV; LDA underestimates by ~0.5 eV)"

## Reference Peak Data

| Quantity | Value | Unit | Notes |
|----------|-------|------|-------|
| First absorption peak center | **7.5** | eV | LDA-computed value |
| Expected experimental range | 7.0 – 8.0 | eV | First singlet excitation |
| LDA systematic bias | ~ -0.5 | eV | LDA underestimates excitation energy |
| Reviewer comparison window | **[7.0, 8.0]** | eV | Pass criterion |

## Verified Numerical Anchor

| Benchmark ID | Observable | Value | Unit | Notes |
|-------------|-----------|-------|------|-------|
| `h2o_tddft_first_peak` | First singlet excitation energy | 7.5 | eV | LDA; use [7.0, 8.0] window |
| `h2o_tddft_peak_shift` | Peak shift vs experiment | +0.5 | eV | LDA bias (computed – experimental center) |

## Reviewer Usage

```
window = [7.0, 8.0]  # eV
reference_center = 7.5  # eV

# Peak detection:
# - Find first significant peak in computed spectrum
# - Compare against window [7.0, 8.0]
# - Report peak_shift = computed_peak_eV - 7.5
# - PASS if peak is within [7.0, 8.0] eV
```

## Reproducibility Metadata

- `xc`: LDA (default; known to underestimate exciton energies by ~0.5 eV)
- `pseudo_family`: Standard (O, H pseudopotentials)
- `geometry_ref`: H₂O equilibrium geometry (neutral singlet)
- `calculation_mode`: td (after gs convergence)
- `spectrum_type`: Optical absorption (dipole)

## Known Limitations

1. **LDA bias**: LDA systematically underestimates excitation energies; the 0.5 eV bias is approximate
2. **Window-based acceptance**: No single-peak RMSE available from this source; only a range check
3. **Partial tutorial coverage**: The specific H₂O TDDFT tutorial page URL within Tutorial 16 was not directly verified in this extraction pass; the reference is inferred from UI_User_Guide attribution to Octopus official docs
4. **Not peer-reviewed**: This is a tutorial example, not a published benchmark

## Action Items (for A-ready upgrade)

- [ ] Verify the specific Octopus Tutorial 16 URL that contains the H₂O absorption example
- [ ] Extract the actual computed spectrum peak value from the tutorial output
- [ ] Add explicit geometry coordinates for H₂O equilibrium structure
- [ ] Add TDSE propagation parameters (TimeStep, SimulationTime, etc.)

## Code Locations

| File | Reference |
|------|-----------|
| `scripts/run_dft_tddft_agent_suite.py` | `h2o_tddft_absorption` in `SUITE_CASES` |
| `@Octopus_docs/UI_User_Guide.md` | Chinese reference for 7–8 eV window |

## Changelog

- 2026-04-16: Extracted from UI_User_Guide.md. Cross-reference to official Octopus Tutorial 16 noted but URL not yet directly verified. Downgraded to B-tier until specific tutorial URL is confirmed.
