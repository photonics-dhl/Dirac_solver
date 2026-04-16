---
name: dirac_planner
description: Use for Dirac benchmark planning when selecting case scope, tolerance gates, and execution budgets before running harness/Octopus.
---

# Dirac Planner Skill

## Use When
- A run must choose or confirm benchmark case.
- Acceptance thresholds need explicit confirmation.
- Retry, timeout, and iteration budget need deterministic bounds.

## Outputs
- selected_case
- threshold
- max_iterations
- execution_budget.retry_budget
- execution_budget.timeout_seconds
- workflow.stage_order
- workflow.main_controls
- review_plan.benchmark_delta_required

## Checklist
1. Confirm case is enabled in case registry.
2. Confirm threshold comes from registry or approved override.
3. Set max_iterations in range [1,10].
4. Provide explicit retry and timeout budgets.
5. Ensure workflow uses setup -> execute -> review and main controls remain Execute/Pause.
6. Mark benchmark delta review as required gate before release.
