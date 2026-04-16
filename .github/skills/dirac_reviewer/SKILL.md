---
name: dirac_reviewer
description: Use for strict production gate reviews of Dirac orchestration outputs across physics quality, KB quality, UI readiness, and contract completion.
---

# Dirac Reviewer Skill

## Use When
- Execution artifacts are ready for release decision.

## Outputs
- checks.accuracy_ok
- checks.benchmarks_aligned_ok
- checks.kb_richness_ok
- checks.octopus_ok
- checks.ui_ok
- checks.ui_rendering_ok
- checks.skills_contracts_ok
- repair_type
- repair_confidence
- final_verdict

## Checklist
1. Validate relative_error <= threshold.
2. Compare TDDFT observables against classic Octopus benchmark cases and flag material deviations.
3. Validate KB hit count and unique source diversity.
4. Review UI aesthetics and operability with desktop + mobile evidence, not URL reachability only.
5. Require benchmark delta review fields (relative_error/threshold/margin) before final PASS.
5. Validate planner/executor/reviewer output contracts are complete.
6. Return PASS only when all checks are true.
