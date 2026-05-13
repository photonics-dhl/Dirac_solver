# Multi-Agent Orchestration Report

## Primary Acceptance (Physical Delta First)

- Physics Equivalence: True
- Provenance Complete: True
- Execution Health: False
- Primary Verdict: PASS

## Case Delta Board

| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Physics Fields |
|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|
| he_atom | E1 | -2.89111865 | - | - | 0.019866886552843282 | 0.03 | True | True | True |

## Final Verdict

- Verdict: PASS
- Case: he_atom
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

- No remediation needed.

## Artifact

- JSON: docs/harness_reports/multi_agent_orchestration_he_atom_20260425T182919Z.json

## Invocation

```bash
python scripts/run_multi_agent_orchestration.py --api-base http://127.0.0.1:3004 --harness-base http://127.0.0.1:8101 --case-id he_atom --max-iterations 3 --octopus-molecule He --octopus-calc-mode gs --skills-manifest /data/home/zju321/.openclaw/workspace/projects/Dirac/orchestration/agent_skills_manifest.json
```
