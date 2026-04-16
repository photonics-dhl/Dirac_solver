---
name: dirac_executor
description: Use for Dirac execution stage to run harness and Octopus with endpoint fallback and audit artifacts.
---

# Dirac Executor Skill

## Use When
- Planner handoff is complete and execution can start.
- Environment may expose inconsistent endpoint sets.

## Outputs
- execution_mode
- simple_harness.passed
- simple_harness.best_relative_error
- octopus.passed
- benchmark_review.final_verdict
- benchmark_review.delta.relative_error
- benchmark_review.next_action

## Checklist
1. Try iterate endpoint first.
2. If iterate endpoint fails, fallback to run_case endpoint.
3. Trigger Octopus only when simple_harness.passed is true.
4. Persist JSON/MD artifact paths for reviewer.
5. Run benchmark delta review for the selected case and expose reviewer next action.
