# Multi-Agent Orchestration Report

## Primary Acceptance (Physical Delta First)

- Physics Equivalence: False
- Provenance Complete: False
- Execution Health: False
- Primary Verdict: FAIL

## Case Delta Board

| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Physics Fields |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| - | E1 | -0.95649283 | - | - | -1.0 | 0.03 | False | False | False |

## Final Verdict

- Verdict: FAIL
- Case: 
- Threshold: 0.03
- Harness Passed: False
- Octopus Passed: True
- KB Richness OK: True
- Retrieval Skill OK: True
- UI OK: True
- Skill Contracts OK: False

## Roles

- Planner: case and tolerance planning, execution budget.
- Planner Skill: dirac.planner.v1 | contract=False
- Executor: harness iterative execution and Octopus run.
- Executor Skill: dirac.executor.v1 | contract=True
- Reviewer: strict checks for accuracy/KB/UI/completion and remediation suggestions.
- Reviewer Skill: dirac.reviewer.v1 | contract=True

## Suggestions

- Reviewer: accuracy gate failed; rerun harness with finer discretization and inspect comparator mapping.
- Reviewer: benchmark delta is not aligned with threshold; check comparator mapping and expected tolerance.
- Reviewer: benchmark provenance is unverified; missing required evidence fields: source_numeric_verified,source_url,software_version,pseudopotential_ids,geometry_ref.
- Reviewer: planner->executor continuity gate failed; force remote OpenClaw-first remediation and rerun strict workflow.
- Reviewer: physics result is incomplete; missing required fields: benchmark_delta.relative_error.
- Reviewer: agent skill contracts are incomplete; inspect planner/executor missing outputs before release.

## Artifact

- JSON: docs/harness_reports/multi_agent_orchestration__20260426T093110Z.json

## Invocation

```bash
python scripts/run_multi_agent_orchestration.py --api-base http://10.72.212.33:3004 --harness-base http://10.72.212.33:8101 --case-id  --max-iterations 6 --octopus-molecule H2 --octopus-calc-mode gs --skills-manifest /data/home/zju321/.openclaw/workspace/projects/Dirac/orchestration/agent_skills_manifest.json
```
