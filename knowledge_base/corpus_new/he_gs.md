# He Atom Ground-State Reference (Octopus PP LDA + NIST Cross-Validation)

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `he_gs` |
| **Category** | DFT ground-state / atomic |
| **Primary Source** | [NIST Standard Reference Database 141](https://www.nist.gov/pml/atomic-reference-data-electronic-structure-calculations-helium) — Kotochigova et al., *Phys. Rev. A* **55**, 191-199 (1997) |
| **NIST DOI** | 10.18434/T4ZP4F |
| **Software** | Octopus 16 (udocker container) |
| **Confidence Tier** | **B-tier** — NIST all-electron reference is traceable, but comparison is all-electron vs pseudopotential (apples-to-oranges). Use as sanity check, not strict benchmark. |

## System Definition

- **Formula**: He
- **Calculation Mode**: gs
- **XC Functional**: lda_x + lda_c_pz
- **Pseudopotential**: HGH LDA (`species_pseudo | file | '/path/He.hgh'`)
- **Spacing**: 0.15 Å
- **Radius**: 10.0 Å
- **BoxShape**: sphere

## Reference Values

| Quantity | Value | Unit | Source |
|----------|------:|------|--------|
| Total Energy (NIST LDA all-electron) | **-2.8348** | Ha | NIST SRD 141 |
| Total Energy (Octopus PP LDA HGH) | -2.891119 | Ha | Computed 2026-04-26 |
| 1s eigenvalue (NIST LDA) | -0.5175 | Ha | NIST SRD 141 |
| 1s eigenvalue (Octopus PP) | -0.581 | Ha | Computed |
| Deviation (total energy) | 1.99% | — | PP vs all-electron |

> **Note**: He has only 2 electrons (1s²). The HGH pseudopotential replaces the 1s² core, but He's 1s IS the valence — so the PP-removed electron scenario is degenerate. The 1.99% energy difference reflects pseudopotential transferability error for this lightest 2-electron system. For validation purposes, prefer the ΔSCF method rather than absolute energy comparison.

## Measured Results

> Auto-synced from orchestrator 2026-04-26

| Date | Etot (Ha) | Ref (Ha) | Error | Parameters |
|------|-----------|----------|-------|------------|
| 2026-04-26 | -2.891119 | -2.8348 (NIST AE-LDA) | 1.99% | sp=0.15Å R=10.0Å lda_x+lda_c_pz |

## Reproducibility Metadata

- `xc`: lda_x + lda_c_pz
- `spacing`: 0.15 Å
- `radius`: 10.0 Å
- `species_mode`: pseudo (HGH LDA)
- `scf_tolerance`: default (1e-6)
- `extra_states`: default (1)

## Changelog

- 2026-05-11: Cleaned auto-sync artifacts (removed 4 duplicate Measured Results sections). Downgraded from A-ready to B-tier — NIST reference is all-electron, Octopus uses PP; absolute energy comparison is not strictly valid.
- 2026-04-26: Auto-synced from orchestrator result (verdict=PASS, error=1.99%)
