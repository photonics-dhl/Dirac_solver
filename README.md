# Dirac_solver

> Web solver for relativistic quantum mechanics (Dirac equation) and strong-field physics (TDDFT), powered by Octopus DFT engine and OpenClaw multi-agent automation.

## Architecture

```
User Task → OpenClaw Planner → Executor → Reviewer → Report
                ↓
        Octopus DFT Engine (HPC)
                ↓
        React + Vite Frontend ←→ Node.js API
```

## Core Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Dirac Solver** | Octopus DFT | Relativistic quantum mechanics computations |
| **Frontend** | React + Vite | Scientific visualization UI |
| **Orchestration** | OpenClaw (Planner→Executor→Reviewer) | Multi-agent task automation |
| **Backend** | Node.js + LangGraph | State graph and API |
| **Bot** | Feishu integration | Notifications and user interaction |

## Key Directories

```
Dirac/
├── scripts/           # Automation entry points (dispatch, worker, monitoring)
├── orchestration/      # OpenClaw policy: routing rules, state machine, contracts
├── state/              # Ground truth for success/failure (DO NOT judge by terminal output)
├── docs/               # Workflow status, HPC runbook, harness reports
├── frontend/           # React + Vite UI
├── backend_engine/     # Python MCP adapter layer
├── .github/
│   ├── agents/        # OpenClaw agent definitions (planner/executor/reviewer)
│   └── skills/        # 5 core skills
└── OpenClaw/          # OpenClaw framework (on remote HPC)
```

## Success Criteria

All three must be satisfied simultaneously:
1. `state/dirac_solver_progress_sync.json` → `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. Report exists in `docs/harness_reports/`

**Never judge success by terminal output — only by state files.**

## Common Tasks

```bash
# Start services (recommended)
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell

# Dispatch a task
python scripts/dispatch_dirac_task.py \
  --task "Dirac_solver debug run_id=<ts>" \
  --source cli-smoke --execute \
  --exec-timeout-seconds 240 \
  --auto-execute-replan \
  --sync-state state/dirac_solver_progress_sync.json

# Replay CH4 convergence
python scripts/replay_ch4_frontend_convergence.py --api-base http://10.72.212.33:3001 --request-timeout 360

# Validate Hydrogen 3-step
python scripts/validate_hydrogen_three_step.py --api-base http://10.72.212.33:3001 --timeout 240
```

## Troubleshooting Order

1. Check SSH/tunnel connectivity
2. Verify ports 3001/8000/8001/8101 are on correct processes (`ss -lntp`)
3. Confirm 8000 is Octopus MCP (not misbehaving process)
4. Check state file consistency in `state/`
5. Then validate physical parameters

## Known Issues

- **Port conflicts**: 8000/8001/8101 occasionally grabbed by wrong process → check `ss -lntp`
- **Hydrogen 3-step**: Backend/frontend parameter alignment occasionally inconsistent
- **Knowledge Base**: Vector store needs reconstruction (no chunks yet)

## Platform

- **Remote HPC**: 10.72.212.33 (SSH: `dirac-key`)
- **Services**: 3001 (API), 5173 (Vite), 8000 (Octopus MCP), 8001/8101 (Harness)

## Development Tips

- All docs go in `docs/`, never scatter documents in root
- No `.log/.tmp/.bak` files committed — hooks filter these
- When debugging, start with `ss -lntp` on the remote server
- Dual-bot: OpenClaw Dirac bot and Hermes Scholar bot run independently

## Memory & Sync

Project memory is at `.claude/memory/` (indexed in `MEMORY.md`). Use Unison to sync:
```bash
# Local → Server sync
D:\Softwares_new\unison-2.53.8-windows-x86_64\bin\unison.exe claude -batch
```
