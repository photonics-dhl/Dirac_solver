# H₂O Ground-State Reference — A-Ready ✅

> **Status (2026-04-16)**: Provenance verified. This file is now A-ready for strict benchmark comparison.

## Reference Summary

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_gs_reference` |
| **Metric** | `total_energy_hartree` |
| **Reference Value** | `-76.4389 Ha` |
| **Uncertainty** | ±0.002 Ha |
| **Confidence Tier** | **A-ready** |
| **Methodology** | CCSD(T)-R12/CBS (FCI/CCSD(T) limit) |
| **Primary Source** | Helgaker et al., J. Chem. Phys. 106, 9639 (1997) — DOI: 10.1063/1.474518 |

## Caveats

- Nonrelativistic, Born-Oppenheimer, static nuclei value
- Relativistic corrections (~-0.003 to -0.005 Ha) NOT included
- Zero-point energy NOT included
- This is the **target** for the calculation phase — Octopus/Dirac calculations aim to reproduce this value

## Full Provenance

See: `knowledge_base/corpus/h2o_gs_reference_provenance.md`
