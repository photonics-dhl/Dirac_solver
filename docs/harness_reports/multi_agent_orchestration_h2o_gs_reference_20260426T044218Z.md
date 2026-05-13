# Multi-Agent Orchestration Report

## Primary Acceptance (Physical Delta First)

- Physics Equivalence: False
- Provenance Complete: False
- Execution Health: False
- Primary Verdict: FAIL

## Case Delta Board

| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Physics Fields |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| h2o_gs_reference | E1 | -17.1965819 | - | - | 0.7750283965363186 | 0.03 | False | False | True |

## Final Verdict

- Verdict: FAIL
- Case: h2o_gs_reference
- Threshold: 0.03
- Harness Passed: False
- Octopus Passed: True
- KB Richness OK: True
- Retrieval Skill OK: True
- UI OK: True
- Skill Contracts OK: True

## Roles

- Planner: case and tolerance planning, execution budget.
- Planner Skill: dirac.planner.v1 | contract=True
- Executor: harness iterative execution and Octopus run.
- Executor Skill: dirac.executor.v1 | contract=True
- Reviewer: strict checks for accuracy/KB/UI/completion and remediation suggestions.
- Reviewer Skill: dirac.reviewer.v1 | contract=True

## Suggestions

- Reviewer: benchmark delta is not aligned with threshold; check comparator mapping and expected tolerance.
- Reviewer: benchmark provenance is unverified; missing required evidence fields: pseudopotential_ids.

## Artifact

- JSON: docs/harness_reports/multi_agent_orchestration_h2o_gs_reference_20260426T044218Z.json

## Invocation

```bash
python scripts/run_multi_agent_orchestration.py --api-base http://127.0.0.1:3004 --harness-base http://127.0.0.1:8101 --case-id h2o_gs_reference --max-iterations 3 --octopus-molecule H2O --octopus-calc-mode gs --skills-manifest /data/home/zju321/.openclaw/workspace/projects/Dirac/orchestration/agent_skills_manifest.json
```
