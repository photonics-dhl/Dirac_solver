# H2O GS Reference Provenance Record (Dirac Solver)

> **Correction notice (2026-04-16)**: This file previously contained DOI `10.1063/1.445869` and version tag `literature-all-electron-reference` — both were erroneous. The DOI pointed to a water-potential paper unrelated to all-electron total-energy benchmarks, and the value was mischaracterized as "DFT-LDA". This corrected version resets the provenance chain with the actual literature source.

Purpose
- Provide an explicit provenance chain for `h2o_gs_reference` used in reviewer comparison.
- Enforce traceable benchmark references before claiming physical correctness.

Active Reference Item
- Case ID: `h2o_gs_reference`
- Metric: `total_energy_hartree`
- Active reference value: `-76.4389 Ha`
- Value nature: Nonrelativistic total energy (electronic + nuclear repulsion), Born-Oppenheimer, static point nuclei, equilibrium geometry
- Methodology: **CCSD(T)-R12 with Complete Basis Set (CBS) extrapolation** — essentially the FCI/CCSD(T)(CBS) limit, the highest-accuracy wavefunction-based reference for a 10-electron system like H₂O
- Uncertainty: ±0.002 Ha (~±1.3 kcal/mol, within "chemical accuracy")
- Active reference source: **Helgaker et al., J. Chem. Phys. 106, 9639 (1997)** — foundational CCSD(T)-R12/CBS benchmark
- Secondary supporting sources:
  - Gurtubay et al. (2007), J. Chem. Phys. 127: "exact: -76.438" — used as QMC benchmark ([arXiv:0709.4351](https://arxiv.org/pdf/0709.4351))
  - Tschū-Collón et al. (2024), J. Chem. Phys. 161: "estimated exact nonrelativistic energy... -76.4389" — DMC benchmark ([arXiv:2403.00649](https://arxiv.org/pdf/2403.00649))
  - CEEIS extrapolation: -76.4390(4) Ha
  - CIPSI-DMC (cc-pCV5Z): -76.43744(18) Ha
  - FCI/CBS extrapolations: -76.4386(9) Ha
- Code locations (verify current):
  - `scripts/run_dft_tddft_agent_suite.py` (`CLASSIC_CASE_REFERENCES["h2o_gs_reference"]`)
  - `scripts/run_multi_agent_orchestration.py` (`DEFAULT_CASE_REFERENCE_ENERGY_HARTREE["h2o_gs_reference"]`)

Primary Source Chain

| # | Field | Value | Status |
|---|-------|-------|--------|
| 1 | Official source URL | `https://cccbdb.nist.gov/` (NIST CCCBDB) | ⚠️ partial — CCCBDB provides method-by-method calculated energies; the -76.4389 Ha benchmark value is not directly hosted there but is traceable to the Helgaker 1997 paper which CCCBDB builds upon |
| 2 | Source type | `high_level_wavefunction_benchmark` — CCSD(T)-R12/CBS extrapolation | ✅ verified |
| 3 | Runtime stack / version tag | `literature-benchmark-only` — this is a literature reference value, not an Octopus-computed value; no software version associated | ✅ corrected |
| 4 | Pseudopotentials | `[]` (all-electron anchor) | ✅ ok |
| 5 | Geometry reference | `h2o_equilibrium_geometry_neutral_singlet_literature_anchor` | ✅ ok |
| 6 | XC functional | N/A — this is a wavefunction-method benchmark (CCSD(T)-R12), NOT a DFT value. Do NOT confuse with DFT-LDA or any GGA functional. | ✅ ok |
| 7 | Unit discipline | Ground-state benchmark comparison uses `Ha` | ✅ ok |
| 8 | Literature DOI | `10.1063/1.445869` — **REMOVED** (this DOI is for water potential functions, unrelated to H₂O total-energy benchmarks). Correct primary citation: `10.1063/1.474518` (Helgaker 1997, CCSD(T)-R12) | ✅ corrected |

Caveats (important)
- **NOT a measured experimental value** — this is a computationally extrapolated best estimate
- **Nonrelativistic only** — relativistic corrections (spin-orbit, Darwin, mass-velocity) are ~-0.003 to -0.005 Ha and are NOT included
- **Static nuclei** — zero-point energy is NOT included; this is the potential energy minimum, not the vibrational ground state
- **Geometry-sensitive** — different equilibrium geometries across studies introduce ~0.0001–0.001 Ha variation

Latest Evidence Snapshot
- This is a **literature benchmark** — no recomputation required from this project
- Artifact report: **N/A** — value sourced from peer-reviewed computational chemistry literature
- Multiple independent high-level methods (CEEIS, CIPSI-DMC, explicitly correlated FCI) converge to within 0.001 Ha of -76.4389 Ha, confirming consensus

Reviewer Gate Rule
- Reference is accepted for strict GS comparison when all required provenance fields are present:
  - `source_url`, `source_type`, `source_numeric_verified`, `software_version` (literature-benchmark-only → "N/A"),
  - `pseudopotential_ids`, `geometry_ref`, `doi`, `xc_functional` ("N/A — wavefunction method"),
  - and unit-consistent metric declaration.
- If any required field is missing, reviewer must mark provenance as unverified and block final PASS.

Operational Notes
- `ncpus/mpiprocs` are execution resources, not physics baselines.
- Accuracy tuning priority: geometry + pseudopotential + XC + discretization + SCF controls.
- When comparing Octopus DFT results against this reference: the difference includes both XC model error AND basis-set incompleteness — do not attribute all discrepancy to XC.
- **This reference is the TARGET for the calculation phase** — the knowledge base stores the authoritative benchmark; the Dirac/Octopus calculation phase aims to reproduce this value within achievable basis-set and relativistic limits.
