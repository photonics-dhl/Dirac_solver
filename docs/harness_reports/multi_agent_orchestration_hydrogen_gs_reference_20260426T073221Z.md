# Multi-Agent Orchestration Report

## Primary Acceptance (Physical Delta First)

- Physics Equivalence: False
- Provenance Complete: True
- Execution Health: False
- Primary Verdict: FAIL

## Case Delta Board

| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Physics Fields |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| hydrogen_gs_reference | E1 | -0.36284088 | - | - | 0.27431824000000005 | 0.03 | False | True | True |

## Final Verdict

- Verdict: FAIL
- Case: hydrogen_gs_reference
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
- Reviewer: repeated failure fingerprint detected; enabling anti-repeat remediation packet with a changed execution path.

## Artifact

- JSON: docs/harness_reports/multi_agent_orchestration_hydrogen_gs_reference_20260426T073221Z.json

## Invocation

```bash
python scripts/run_multi_agent_orchestration.py --api-base http://127.0.0.1:3004 --harness-base http://127.0.0.1:8101 --case-id hydrogen_gs_reference --max-iterations 3 --octopus-molecule H --octopus-calc-mode gs --skills-manifest /data/home/zju321/.openclaw/workspace/projects/Dirac/orchestration/agent_skills_manifest.json
```
