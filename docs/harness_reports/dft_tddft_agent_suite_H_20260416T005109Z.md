# DFT/TDDFT Agent Suite Report

## Verdict

- Molecule: H
- Final Verdict: FAIL
- Passed Cases: 0/1

## Case Results

| Scenario | Mode | Status | Engine | Metric | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | Error |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| hydrogen_gs_reference | gs | FAIL | octopus-mcp | total_energy_hartree (Ha) | -68.3228 | -0.5 | -67.8228 | 135.646 | 0.03 | False |  |
|  |  |  |  | homo_energy_ev (eV) | -1859.16 | -13.6057 | -1845.55 | 135.646 | 0.08 | False | secondary-check |

## Curve Evidence

### hydrogen_gs_reference (FAIL)
- No curve artifacts were generated.


## Repeat-Run Statistics

- hydrogen_gs_reference: runs=1, pass_rate=0.0
  - total_energy_hartree: mean=-68.3228, std=0
  - cross_section_points: mean=0, std=0
  - dipole_points: mean=0, std=0
  - computation_time_sec: mean=61.904, std=0

## Reviewer Checks

- all_cases_passed: False
- gs_converged: True
- absorption_cross_section_ready: True
- dipole_response_ready: True
- radiation_spectrum_ready: True
- eels_spectrum_ready: True
- absorption_curve_evidence: True
- dipole_curve_evidence: True
- radiation_curve_evidence: True
- eels_curve_evidence: True
- external_reference_alignment: True
- all_octopus_engine: True
- all_within_reference_tolerance: False
- all_homo_within_tolerance: False
- all_provenance_verified: True
- all_reference_model_aligned: True

## Suggestions

- One or more benchmark deltas exceed tolerance; adjust Octopus discretization/time-step and rerun.
- Hydrogen HOMO deviates from reference; tighten discretization and confirm orbital extraction assumptions.

## Artifact

- JSON: /data/home/zju321/.openclaw/workspace/projects/Dirac/docs/harness_reports/dft_tddft_agent_suite_H_20260416T005109Z.json

## Invocation

```bash
python scripts/run_dft_tddft_agent_suite.py --api-base http://127.0.0.1:3001 --molecule H --td-steps 260 --td-time-step 0.04
```
