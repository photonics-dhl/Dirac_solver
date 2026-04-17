# Dirac Operating Model: Copilot + OpenClaw

## Objective
Define executable role boundaries and handoff protocol so Dirac automation is predictable, auditable, and scalable.

## Role split

- `copilot-executor` (this assistant)
  - Owns implementation and verification execution loops.
  - Produces auditable code changes, test evidence, and run artifacts.

- `openclaw-planner`
  - Owns planning, decomposition, and task strategy.
  - Produces task plan, constraints, acceptance criteria, and iteration budgets.
  - For complex coding tasks beyond copilot execution capacity, escalates to OpenClaw advanced model (for example Claude 4.6) and returns a concrete handoff packet.

- `openclaw-executor`
  - Owns repetitive execution loops: service bootstrap, orchestration runs, artifact generation, status sync.
  - Runs only under policy from `orchestration/openclaw_exec_policy.json`.

- `openclaw-reviewer`
  - Owns blocking review gate and remediation guidance.
  - Requires reviewer checks all pass before release.

## Trigger sources

- CLI trigger: `python scripts/dispatch_dirac_task.py --task "Dirac_solver 调试" --source cli --execute`
- Feishu trigger: same task text, source=`feishu` in dispatcher invocation.
- Feishu `/auto` trigger: `/auto <natural language task>` is force-routed to Dirac execution as `Dirac_solver 调试 <natural language task>` and enters the same execution bus.
- Hook ordering invariant: on `message:received`, dispatch decision runs before sync hard-guard context injection, and all routing checks read immutable original user text.

## Cyber-Employee Closed Loop (Execution Bus)

- Feishu trigger now enters a queue first (`state/dirac_exec_queue.json`) instead of relying on one-shot HTTP dispatch.
- Queue worker (`scripts/dirac_exec_worker.py`) consumes queued tasks, executes `dispatch_dirac_task.py --execute --auto-execute-replan`, and writes ACK back to queue and bridge state.
- Persistent worker daemon (`scripts/run_dirac_exec_worker.sh`) is started by `start_all.sh` and writes logs to `logs/dirac_exec_worker.log`.
- Bridge state (`state/copilot_openclaw_bridge.json`) now includes `execution_bus.last_task` so OpenClaw can report deterministic execution status.
- Running tasks that become stale are re-queued with backoff; retry policy is bounded by `max_attempts`.
- Hook keeps a fallback path to direct `/api/automation/dispatch` when queue write fails.

## Bot response contract (anti-false-denial)

OpenClaw bot must not directly respond with generic denial like "no terminal permission" without checking capability endpoints first.

Required check order:

1. `POST /api/automation/exec-readiness`
2. `POST /api/automation/ensure-exec` (when readiness is false)
3. `POST /api/automation/dispatch`

Response policy:

- If `execution_ready=true`, bot should execute and report real workflow status.
- If blocked, bot must report structured cause from dispatcher: `blocked_permissions`, `blocked_reviewer_gate`, or `execution_failed`.
- Generic text-only denial is considered invalid behavior.

## Contract and gate rules

1. Planner (OpenClaw) must output plan/budget/constraints contract.
2. Executor (Copilot) must output implementation/run mode + harness + octopus contract.
3. Reviewer (OpenClaw) must output all checks and final verdict.
4. `--strict` is mandatory in orchestration to enforce blocking behavior.

## Ops Skills For Runtime Evidence

- Vector KB operations skill: `.github/skills/dirac-vector-kb-ops/SKILL.md`
  - Tool: `python scripts/run_vector_kb_ops.py --mode full --base-url http://127.0.0.1:8001`
- Dirac debug operations skill: `.github/skills/dirac-debug-ops/SKILL.md`
  - Tool: `python scripts/run_dirac_debug_ops.py --mode snapshot`
  - End-to-end probe: `python scripts/run_dirac_debug_ops.py --mode full --task "Dirac_solver 调试 /auto smoke" --execute --auto-replan`

## Operational policy

- Permission readiness must be audited before automation:
  - `python scripts/audit_openclaw_permissions.py --policy orchestration/openclaw_exec_policy.json`
- Only proceed when `execution_ready=true`.

## Failure protocol

- If orchestration exits non-zero due reviewer FAIL:
  - Do not release.
  - Feed reviewer suggestions back to planner.
  - Re-run dispatcher with updated constraints.

## Frontend White-Screen Regression Guard

When changing frontend rendering paths (especially `frontend/src/App.tsx`), the following checks are mandatory before claiming completion:

1. Compile gate (remote runtime):
  - `cd frontend && node ../node-v16.20.2-linux-x64/bin/node ./node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`
2. Live module gate (Vite endpoint sanity):
  - Verify `GET /src/App.tsx` is non-empty JS payload (not `Content-Length: 0`).
3. Browser gate:
  - Reload `http://<host>:5173/` and confirm UI renders (no blank page).
4. Log gate:
  - Check `logs/vite.log` for no active `Internal server error` on `App.tsx`.

Incident reference:
- 2026-04-05 white-screen recurrence was caused by a removed icon import (`FlaskConical`) still referenced in JSX render path. This is treated as a release-blocking regression class.
