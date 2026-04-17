# Notes: OpenClaw Permission and Multi-Agent Automation

## Findings
- OpenClaw shell capability is enabled in ~/.openclaw/openclaw.json via env.shellEnv.enabled=true.
- Device scope approval state is tracked under ~/.openclaw/devices/paired.json and identity token files.
- Dirac already has role contracts and an orchestration runner but lacks a unified trigger+dispatch wrapper.

## Implementation Direction
- Add governance policy JSON (allow/approval/deny command classes).
- Add script to audit effective permission readiness before automation run.
- Add trigger/dispatcher script that routes CLI/Feishu command text to orchestration runner.
- Update collaboration design docs with operational contract between Copilot and OpenClaw.

## Implemented
- `orchestration/openclaw_exec_policy.json`
- `orchestration/task_dispatch_rules.json`
- `scripts/audit_openclaw_permissions.py`
- `scripts/ensure_openclaw_exec.py`
- `scripts/dispatch_dirac_task.py`
- `src/server.ts` new endpoints:
	- `/api/automation/exec-readiness`
	- `/api/automation/ensure-exec`
	- `/api/automation/dispatch`
- Updated docs:
	- `docs/agent_skill_collaboration_design.md`
	- `docs/dirac_solver_operation_guide.md`
	- `docs/openclaw_copilot_operating_model.md`

## Verification Results
- Permission audit reports `execution_ready=True` in current environment.
- Ensure script can auto-adjust shell timeout baseline (set to 60000ms) and preserve scope checks.
- Dispatcher routes `Dirac_solver 调试` to `openclaw-executor` with `run_orchestration` action.
- Dispatcher preflight now runs ensure+audit before execution and records both in dispatch report.
- Execute mode correctly enforces blocking reviewer gate (`--strict`) and returns non-zero on FAIL.

## 2026-04-04 Stability Push Notes

### Repeated Strict Regression
- Executed 5 consecutive strict dispatch runs using reviewer strict gate.
- Batch summary: total=5, pass=5, fail=0, pass_rate=100.0%.

### Evidence Artifacts
- `docs/harness_reports/task_dispatch_20260404T112154Z.json`
- `docs/harness_reports/task_dispatch_20260404T112203Z.json`
- `docs/harness_reports/harness_master_aggregate_20260404T112219Z.md`

### Lessons to Keep
- Strict gate is stable only when planner/executor/reviewer required-output contracts stay aligned with `orchestration/agent_skills_manifest.json`.
- Regression should be judged by repeated strict DONE transitions, not single PASS snapshots.
- After major batches, run report aggregation and cleanup to keep handoff evidence focused and lightweight.

## 2026-04-04 Extended Stabilization Results

### Long Soak
- Executed 20 strict dispatcher runs (`--reviewer-strict`).
- Batch summary: total=20, strict_pass=20, strict_pass_rate=100.0%.
- Validation criteria used: `execution_exit_code=0`, `workflow_state=DONE`, `workflow_event=REVIEW_PASS`.

### Queue-Worker Burst Validation
- Injected 5 tasks into `state/dirac_exec_queue.json` with source `codex-queue-stress`.
- Ran worker consumption with `python scripts/dirac_exec_worker.py --max-jobs 5`.
- Result: 5/5 tasks reached `status=done`, each ACK reported `dispatch_status=success` and `workflow_state=DONE`.

### Evidence Artifacts
- `docs/harness_reports/soak_batch_20_strict_latest.json`
- `docs/harness_reports/soak_batch_20_strict_summary_latest.json`
- `docs/harness_reports/queue_stress_task_ids_latest.json`
- `docs/harness_reports/queue_worker_stress_latest.json`
- `docs/harness_reports/harness_master_aggregate_20260404T113438Z.json`

### Operational Conclusion
- Current strict orchestration path is stable under 20-run soak.
- Execution bus queue-worker path is stable under burst size 5.
- Next optional gate for production confidence: increase queue burst to >=20 tasks and include deliberate retry/failure injection paths.
