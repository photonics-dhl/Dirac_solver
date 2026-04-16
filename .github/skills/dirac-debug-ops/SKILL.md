---
name: dirac-debug-ops
description: Use when the user asks to debug Dirac_solver execution, verify OpenClaw execution capability, or validate state synchronization across queue, bridge, and progress sync files.
---

# Dirac Debug Ops Skill

## Use When
- User reports "cannot execute", "no state sync", or "only trigger text seen".
- Need one command to capture execution bus truth and Octopus runtime evidence.
- Need controlled dispatch test with before/after snapshots.

## Primary Tool
- `scripts/run_dirac_debug_ops.py`

## Typical Commands
```bash
# Snapshot only (non-intrusive)
python scripts/run_dirac_debug_ops.py --mode snapshot

# Dispatch only (route + execute)
python scripts/run_dirac_debug_ops.py --mode dispatch --task "Dirac_solver 调试" --execute --auto-replan

# Full check: snapshot -> dispatch -> snapshot
python scripts/run_dirac_debug_ops.py --mode full --task "Dirac_solver 调试 /auto smoke" --execute --auto-replan
```

## Required Outputs
- Worker status (`pid`, `alive`).
- Queue depth and latest task status.
- Bridge `execution_bus.last_task` snapshot.
- Progress sync (`state/dirac_solver_progress_sync.json`) phase/checks.
- Octopus evidence fields when available:
  - SCF convergence and iterations
  - total energy
  - HOMO/LUMO and gap
  - TD energy trajectory (`step`, `time`, `total_energy`)

## Rules
1. Prefer `--mode snapshot` first when diagnosing production issues.
2. For dispatch tests, include both before and after snapshots.
3. If dispatch is blocked, return exact `dispatch_status` and `failure_reason` from tool output.
4. Never conclude "no execution capability" without queue + bridge + sync evidence.
