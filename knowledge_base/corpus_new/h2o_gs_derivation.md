# H₂O Ground-State Reference — Provenance Verified ✅

> **Status update (2026-04-16)**: The provenance of `-76.4389 Ha` has been verified. This file now serves as a derivation guide and points to the authoritative provenance record.

## Verified Reference Value

| Field | Value |
|-------|-------|
| **Case ID** | `h2o_gs_reference` |
| **Active Reference Value** | `-76.4389 Ha` |
| **Methodology** | CCSD(T)-R12 with Complete Basis Set (CBS) extrapolation — essentially the FCI/CCSD(T)(CBS) limit |
| **Uncertainty** | ±0.002 Ha (~±1.3 kcal/mol, within "chemical accuracy") |
| **Primary Source** | Helgaker et al., J. Chem. Phys. 106, 9639 (1997) |
| **DOI** | 10.1063/1.474518 |
| **Confidence Tier** | **A-ready** (wavefunction benchmark, literature-verified) |

## Additional Supporting Sources

| Source | Value | Method |
|--------|-------|--------|
| Gurtubay et al. (2007), J. Chem. Phys. 127 | -76.438 Ha | QMC benchmark |
| Tschū-Collón et al. (2024), J. Chem. Phys. 161 | -76.4389 Ha | DMC benchmark |
| CEEIS extrapolation | -76.4390(4) Ha | CBS limit |
| CIPSI-DMC (cc-pCV5Z) | -76.43744(18) Ha | Fixed-node DMC |
| FCI/CBS extrapolations | -76.4386(9) Ha | cc-pCVnZ, n→∞ |

## Important Caveats

1. **NOT a measured experimental value** — computationally extrapolated best estimate
2. **Nonrelativistic only** — relativistic corrections (spin-orbit, Darwin, mass-velocity) are ~-0.003 to -0.005 Ha and are NOT included
3. **Static nuclei** — zero-point energy is NOT included
4. **Geometry-sensitive** — different equilibrium geometries introduce ~0.0001–0.001 Ha variation
5. **This is the TARGET for the calculation phase** — the KB stores this authoritative benchmark; the Dirac/Octopus calculation phase aims to reproduce this value within achievable basis-set and relativistic limits

## Full Provenance Record

See: `knowledge_base/corpus/h2o_gs_reference_provenance.md`

## Code Locations

- `scripts/run_dft_tddft_agent_suite.py` (`CLASSIC_CASE_REFERENCES["h2o_gs_reference"]`)
- `scripts/run_multi_agent_orchestration.py` (`DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["h2o_gs_reference"]`)

## Previous Provenance Issues (Resolved)

| Issue | Resolution |
|-------|-----------|
| DOI 10.1063/1.445869 was incorrect (wrong paper) | Removed. Correct DOI: 10.1063/1.474518 (Helgaker 1997) |
| Value mischaracterized as "DFT-LDA all-electron" | Corrected — it is a wavefunction-method benchmark (CCSD(T)-R12), NOT DFT |
| "pending recomputation" status | Removed — this is a literature benchmark, no recomputation needed |
| provenance chain marked as broken | ✅ Verified via multiple independent high-level calculations |

## Derivation from Literature

The -76.4389 Ha value originates from high-level explicitly correlated (R12) calculations extrapolated to the complete basis set (CBS) limit (Helgaker et al., 1997). Multiple independent methods (CEEIS, CIPSI-DMC, explicitly correlated FCI) converge to within 0.001 Ha, confirming consensus.

## Changelog

- 2026-04-16: Provenance verified. DOI corrected. Methodology clarified (CCSD(T)-R12/CBS, NOT DFT-LDA). Status upgraded from C-draft to A-ready.
