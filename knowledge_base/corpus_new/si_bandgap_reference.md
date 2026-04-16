# Si Band Gap Reference (Sanity Anchor — Octopus Tutorial + Experiment)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `si_bandgap_reference` |
| **Category** | DFT / band structure / semiconductor |
| **Primary Source** | [Octopus Tutorial 16](https://www.octopus-code.org/documentation/16/) |
| **Secondary Source** | `@Octopus_docs/UI_User_Guide.md` (Chinese system user guide) |
| **Source Type** | `official_tutorial` + `experimental_literature` |
| **Confidence Tier** | **B-needs-evidence** |

> **Provenance Note**: The Si band gap values are textbook-level DFT knowledge commonly cited in Octopus documentation. However, this KB entry relies on the UI_User_Guide for the specific numbers; the exact Tutorial 16 page containing these values should be verified.

## System Definition

- **Material**: Crystalline silicon (Si)
- **Structure**: Face-centered cubic (diamond structure)
- **Calculation Mode**: `gs` (ground state for band structure), then `unocc` or `em` for response
- **Periodicity**: 3D periodic (PeriodicDimensions = 3)

## Reference Band Gap Data

| XC Functional | Band Gap (eV) | Notes |
|---------------|-------------:|-------|
| **LDA** | **~0.5** | Known to severely underestimate |
| **GGA (PBE)** | **~0.7** | Underestimates, less severe than LDA |
| **Experiment** | **~1.1** | Room-temperature experimental value |

> **Source text (UI_User_Guide.md)**: "LDA 带隙约 0.5 eV（实验 1.1 eV，GGA 约 0.7 eV）"

## Usage Classification

> **⚠️ Sanity Anchor Only — Not a Strict Benchmark**

This case is **NOT** a strict pass-fail scalar. It serves as:
1. **Sanity check**: Confirm the computed band gap is in the physically plausible range
2. **Systematic bias indicator**: Report how far the computed gap deviates from experiment
3. **XC functional comparison**: Use LDA vs GGA difference as an error estimate

## Reviewer Rule

```
si_bandgap_tolerance = {
    "lda": { "lo": 0.3, "hi": 0.7 },   # eV; warn if outside
    "gga": { "lo": 0.5, "hi": 0.9 },   # eV; warn if outside
    "experiment": 1.1                          # reference only
}

def check_si_bandgap(computed_gap_eV, xc_functional):
    range = si_bandgap_tolerance.get(xc_functional, {})
    if range and (computed_gap_eV < range["lo"] or computed_gap_eV > range["hi"]):
        return "WARN: computed band gap outside expected range"
    else:
        return "PASS: sanity check ok"
```

## Reproducibility Metadata

- `xc`: Variable (LDA or GGA; must be explicitly stated in artifact)
- `pseudo_family`: Standard pseudopotential for Si
- `grid`: k-mesh ( Monkhorst-Pack or similar); must be documented
- `geometry_ref`: Si crystal structure (diamond, experimental lattice constant ~5.43 Å)
- **Missing**: Specific k-mesh density used in tutorial calculation

## Known Limitations

1. **No exact tutorial URL**: The specific Octopus Tutorial 16 page with Si band structure example was not directly verified
2. **Wide tolerance**: The 0.3–0.7 eV range for LDA is approximate
3. **Temperature**: Experimental gap is at room temperature; DFT is at 0 K
4. **Not a primary benchmark**: This is a sanity anchor, not a case for strict quantitative comparison

## Action Items (for A-ready upgrade)

- [ ] Verify the specific Octopus Tutorial 16 page for Si band structure
- [ ] Extract k-mesh parameters from tutorial
- [ ] Replace approximate ranges with exact computed values from tutorial output
- [ ] Add lattice constant and crystal structure parameters

## Changelog

- 2026-04-16: Extracted from UI_User_Guide.md. Classified as B-tier sanity anchor. Not suitable for strict quantitative comparison until tutorial URL is verified and exact parameters are extracted.
