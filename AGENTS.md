# Dirac_solver — Agent Onboarding Guide

> AI-agent-facing project reference. If you are an autonomous coding agent reading this file, you know nothing about the project yet; this document is your single source of truth.

---

## 1. Project Overview

**Dirac_solver** is a web-based solver for relativistic quantum mechanics (Dirac equation) and strong-field physics (TDDFT). It integrates:

- **Octopus DFT engine** (C++/Fortran) for real quantum-chemistry calculations (ground-state DFT, time-dependent DFT, Casida).
- **OpenClaw multi-agent automation** (Planner → Executor → Reviewer) for autonomous task dispatch, benchmark validation, and failure recovery.
- A **React + Vite frontend** for scientific parameter configuration and visualization.
- A **Node.js + LangGraph backend orchestrator** that routes tasks, proxies to compute engines, and manages state.
- A **Python FastAPI MCP adapter** (`backend_engine/`) that serves as a local fallback solver and knowledge-base RAG endpoint.

The system is designed to run on a remote HPC (CentOS 7, IP `10.72.212.33`) accessed via SSH alias `dirac-key`, with local Windows development through a RaiDrive CIFS mount at `Z:\.openclaw\workspace\projects\Dirac`.

---

## 2. Technology Stack

| Layer | Technology | Key Files |
|-------|-----------|-----------|
| **Frontend** | React 19, Vite 4, TypeScript 5, Tailwind CSS 3, XYFlow | `frontend/src/App.tsx`, `frontend/package.json` |
| **Orchestrator API** | Node.js 20, Express 5, TypeScript 5, LangGraph, Zod | `src/server.ts`, `src/physics_engine.ts`, `src/langgraph_agent.ts` |
| **Compute Engine (Primary)** | Octopus DFT inside Docker, Python MCP server | `docker/Dockerfile`, `docker/workspace/server.py` |
| **Compute Engine (Fallback)** | Python FastAPI, NumPy, SciPy, sparse eigensolvers | `backend_engine/main.py`, `backend_engine/kb_rag.py` |
| **Visualization** | Matplotlib (1D/2D), VisIt (3D isosurface) | `src/render_mpl.py`, `src/visit_renderer.ts` |
| **Automation** | OpenClaw multi-agent framework, Feishu bot | `scripts/dispatch_dirac_task.py`, `scripts/run_multi_agent_orchestration.py` |
| **Knowledge Base** | ChromaDB vector store, RAG | `knowledge_base/`, `backend_engine/kb_rag.py` |
| **State / Persistence** | JSON state files (ground truth) | `state/dirac_solver_progress_sync.json`, `state/dirac_exec_queue.json` |

---

## 3. Repository Layout

```
Dirac/
├── src/                          # TypeScript orchestrator source
│   ├── server.ts                 # Express API entry point (port 3001/3004)
│   ├── physics_engine.ts         # Physics pipeline: local Python ↔ Octopus MCP routing
│   ├── langgraph_agent.ts        # LangGraph state-machine agent
│   ├── http_request.ts           # HTTP client wrapper with timeouts
│   ├── visit_renderer.ts         # VisIt headless 3D render integration
│   └── render_mpl.py             # Matplotlib 1D/2D rendering script
│
├── frontend/                     # React + Vite UI
│   ├── src/App.tsx               # Main solver UI (COMSOL-style panels)
│   ├── src/DevFlowDashboard.tsx  # Dev-flow dashboard
│   ├── src/ResultsPanel.tsx      # Results / benchmark review panel
│   ├── src/Mol3DViewer.tsx       # 3D molecule viewer
│   ├── src/GeometryEditor.tsx    # Custom atom geometry editor
│   ├── package.json              # Vite dev server (port 5173)
│   └── .env.development          # VITE_API_BASE_URL, VITE_MCP_BASE_URL
│
├── backend_engine/               # Python FastAPI MCP adapter + RAG
│   ├── main.py                   # FastAPI app (port 8001): /solve, /harness, /kb/query
│   ├── kb_rag.py                 # ChromaDB knowledge-base service
│   └── requirements.txt          # fastapi, uvicorn, numpy, scipy, pydantic, chromadb
│
├── scripts/                      # Automation, dispatch, monitoring (Python + PowerShell)
│   ├── dispatch_dirac_task.py            # Main task dispatch entry point
│   ├── run_multi_agent_orchestration.py  # OpenClaw orchestrator
│   ├── dirac_exec_worker.py              # Execution-queue worker
│   ├── dc.ps1                            # Service startup script (PowerShell)
│   ├── connect_server.ps1                # SSH tunnel + service bootstrap
│   ├── feishu_notify.py                  # Feishu (Lark) bot notifications
│   ├── monitor_5173_health.py            # Frontend health monitor
│   ├── replay_ch4_frontend_convergence.py# CH4 convergence validation
│   ├── validate_hydrogen_three_step.py   # H atom 3-step validation
│   └── ... (50+ scripts)
│
├── orchestration/                # OpenClaw policy configuration
│   ├── task_dispatch_rules.json          # Intent routing rules (keywords → actions)
│   ├── agent_skills_manifest.json        # Planner / Executor / Reviewer contracts
│   ├── openclaw_exec_policy.json         # Execution governance (full-auto mode)
│   ├── execution_wake_state_machine.json # L0/L1 state machine
│   ├── coding_gateway_config.json        # Coding-gateway routing
│   └── contracts/                        # Handoff / review / escalation packet templates
│
├── state/                        # Runtime state — THE SINGLE SOURCE OF TRUTH
│   ├── dirac_solver_progress_sync.json   # Global workflow progress
│   ├── dirac_exec_queue.json             # Pending execution queue
│   ├── copilot_openclaw_bridge.json      # Execution bus bridge
│   ├── coding_gateway_tasks.json         # Coding gateway task registry
│   └── coding_gateway_runs/              # Per-run execution records
│
├── docs/                         # Documentation and harness reports
│   ├── harness_reports/                  # OpenClaw execution reports (48h TTL)
│   ├── octopus/                          # Octopus reference docs (handbooks, parsing guides)
│   ├── octopus_case_convergence.md       # ✅ Verified convergence parameters (PP Mode baseline)
│   ├── octopus_user_guide.md             # Octopus MCP operation manual (Chinese)
│   ├── development_lessons_20260418.md   # Development experience notes
│   └── openclaw_operating_model.md       # OpenClaw operating model
│
├── knowledge_base/               # RAG corpus and vector store
│   ├── corpus_new/                       # Verified reference data + provenance
│   ├── corpus_mp/                        # Materials Project reference data
│   ├── vector_store/                     # ChromaDB embeddings (136 vectors)
│   ├── metadata/                         # RAG metadata
│   └── benchmark_cases.json              # Harness case registry
│
├── benchmarks/                   # HPC Octopus benchmark cases + pseudopotentials
│   ├── *.upf                             # Pseudopotential files (C.upf, H.upf, etc.)
│   ├── *.hgh                             | HGH pseudopotentials
│   ├── bench_multi.sh                    # PBS benchmark script
│   └── inp/                              # Octopus input templates
│
├── docker/                       # Docker configuration for Octopus MCP
│   ├── Dockerfile                        # Based on registry.gitlab.com/octopus-code/octopus:latest
│   ├── docker-compose.yml                # Octopus MCP container (port 8000)
│   ├── docker-compose.gpu.yml            # GPU override (12G memory + nvidia)
│   └── workspace/server.py               # Octopus MCP server (copied into image)
│
├── deploy/                       # Cloud deployment scripts
│   ├── setup_cloud.sh                    # One-time Ubuntu 24.04 bootstrap
│   ├── start_all.bat                     # Windows batch startup
│   └── update_cloud.sh                   # Update script
│
├── .github/                      # Agent definitions and skills
│   ├── agents/                           # dirac-planner, dirac-executor, dirac-reviewer, dirac-debugger
│   ├── skills/                           # 5 core OpenClaw skills
│   └── copilot-instructions.md           # Role definition for Copilot/Claude
│
├── run/                          # HPC runtime output directories
├── tests/                        # Test directory (currently empty; validation is harness-driven)
├── logs/                         # Runtime logs (gitignored)
├── package.json                  # Root Node.js dependencies
├── tsconfig.json                 # TypeScript compiler config (CommonJS, ES2022, outDir ./dist)
├── requirements.txt              # Minimal Python deps (openai, python-dotenv)
└── .env.example                  # Environment variable template
```

---

## 4. Build and Run Commands

### 4.1 Prerequisites

- **Node.js 20+**
- **Python 3.11+** with `pip`
- **Docker** (for Octopus MCP)
- **VisIt** (optional, for 3D visualization; set `VISIT_EXE` in `.env`)
- **SSH access** to remote HPC (`dirac-key` alias configured in `~/.ssh/config`)

### 4.2 Install Dependencies

```bash
# Node.js orchestrator
npm install

# React frontend
cd frontend && npm install && cd ..

# Python backend engine
pip install -r backend_engine/requirements.txt

# Octopus Docker image
cd docker && docker build -t octopus-mcp-server:latest . && cd ..
```

### 4.3 Environment Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:
- `PORT` — Node API port (default `3001`)
- `OCTOPUS_MCP_URL` — Octopus Docker endpoint (`http://localhost:8000`)
- `LOCAL_ENGINE_URL` — Python fallback endpoint (`http://localhost:8001`)
- `WORKSPACE_ROOT` — Absolute path to this repo
- `OCTOPUS_OUTPUT_DIR` — Where Octopus writes results
- `VISIT_EXE` — VisIt executable path (or bare `visit` if on PATH)
- `ZCHAT_API_KEY` / `ZCHAT_BASE_URL` — LLM credentials for AI physics explanations

### 4.4 Start Services

**Recommended (PowerShell, local development with remote HPC):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell
```

This script:
1. Opens SSH tunnels for ports `3001`, `5173`, `8000`, `8001`, `8101`
2. Starts/restarts remote services
3. Keeps tunnels alive

**Manual / cloud (Linux):**

```bash
# 1. Octopus MCP (Docker)
docker compose -f docker/docker-compose.yml up -d

# 2. Python backend engine
uvicorn backend_engine.main:app --host 0.0.0.0 --port 8001

# 3. Node.js orchestrator
npx ts-node src/server.ts        # dev mode
# or
node dist/server.js              # after tsc build

# 4. React frontend
cd frontend && npm run dev       # port 5173
```

### 4.5 Frontend Build

```bash
cd frontend
npm run build     # Outputs to frontend/dist/
npm run preview   # Preview production build
```

---

## 5. Architecture and Data Flow

```
User Task / Frontend
        │
        ▼
┌───────────────────┐
│  Node.js API      │  src/server.ts (Express)
│  (Port 3001/3004) │  • /api/simulate        → LangGraph agent
└───────────────────┘  • /api/physics/run     → physics_engine.ts
        │              • /api/physics/stream   → SSE streaming pipeline
        │              • /api/physics/visualize → Matplotlib / VisIt
        │              • /api/mcp/health       → Octopus health proxy
        │              • /api/harness/*        → Harness benchmark proxy
        ▼
┌───────────────────┐
│ physics_engine.ts │  Routing logic:
│                   │  • engineMode='octopus3D' → Octopus MCP (port 8000)
│                   │  • engineMode='local1D'   → Python backend (port 8001)
└───────────────────┘
        │                    │
        ▼                    ▼
┌──────────────┐    ┌──────────────────┐
│ Octopus MCP  │    │ Python FastAPI   │
│ Docker 8000  │    │ backend_engine   │
│ server.py    │    │ main.py :8001    │
└──────────────┘    └──────────────────┘
        │                    │
        ▼                    ▼
   Octopus DFT         Local quantum solver
   (GS / TD / UNOCC)   (1D/2D bound-state,
                        time-evolution,
                        scattering)
```

---

## 6. Code Organization and Module Divisions

### 6.1 TypeScript Backend (`src/`)

- **`server.ts`** — Express app. Defines all REST endpoints. Proxies to harness (port 8001/8101) and Octopus MCP (port 8000). Manages `dev_state.json` for the DevFlow dashboard and async explanation jobs.
- **`physics_engine.ts`** — Core physics pipeline. Routes between Octopus DFT and local Python solver. Emits SSE events (`log`, `heartbeat`, `result`). Updates persistent `computation_log.md`.
- **`langgraph_agent.ts`** — LangGraph state machine. Invoked by `/api/simulate` for agentic parameter refinement.
- **`visit_renderer.ts`** — VisIt integration: script generation, headless rendering, Docker-path-to-host-path translation.
- **`http_request.ts`** — Thin fetch wrapper with configurable timeouts.

### 6.2 React Frontend (`frontend/src/`)

- **`App.tsx`** — Main application shell. Two tabs: "Dirac Solver" and "Dev Flow".
- **`DevFlowDashboard.tsx`** — Real-time visualization of agent state graph and logs.
- **`ResultsPanel.tsx`** — Displays eigenvalues, wavefunctions, molecular data, harness benchmark reviews.
- **`Mol3DViewer.tsx`** — 3D molecule preview using XYFlow / custom WebGL.
- **`GeometryEditor.tsx`** — Custom atomic geometry input.

### 6.3 Python Backend (`backend_engine/`)

- **`main.py`** — FastAPI application with endpoints:
  - `POST /solve` — Local quantum solver (1D finite-difference Hamiltonian)
  - `POST /harness/run_case` — Single-case benchmark harness
  - `POST /harness/iterate_case` — Iterative parameter sweep harness
  - `GET /harness/case_registry` — Case type registry
  - `POST /kb/query` — RAG query against ChromaDB
  - `POST /kb/ingest` — Knowledge-base ingestion
- **`kb_rag.py`** — ChromaDB vector store initialization and querying.

### 6.4 OpenClaw Automation (`scripts/`)

Key scripts every agent should know:

| Script | Purpose |
|--------|---------|
| `dispatch_dirac_task.py` | Dispatch a task with `--task`, `--source`, `--execute` flags |
| `run_multi_agent_orchestration.py` | Full Planner→Executor→Reviewer loop |
| `dirac_exec_worker.py` | Queue worker that reads `state/dirac_exec_queue.json` |
| `feishu_notify.py` | Send notifications to Feishu (Lark) |
| `dc.ps1` | One-command service startup + SSH tunnel |
| `replay_ch4_frontend_convergence.py` | Validate CH4 convergence against known good parameters |
| `validate_hydrogen_three_step.py` | Validate H atom GS→TD→review pipeline |
| `monitor_5173_health.py` | Health-check the Vite frontend |
| `cleanup_harness_reports.py` | Delete harness reports older than 48h |

---

## 7. Development Conventions

### 7.1 File and Directory Rules

- **All documentation belongs in `docs/`**. Do not create scattered documents in the repository root.
- **State files are the single source of truth**. Never judge success or failure by terminal output alone. Always inspect `state/dirac_solver_progress_sync.json`.
- **Use RaiDrive paths for `.openclaw` references on Windows**. The canonical local path is `Z:\.openclaw\workspace\projects\Dirac`. Do not use `C:\Users\Mac\.openclaw`.
- **Never commit `.log`, `.tmp`, `.bak` files**. These are filtered by git hooks and `.gitignore`.

### 7.2 Success Criteria (Ground Truth)

A task is considered **complete** only when **all three** conditions are met simultaneously:

1. `state/dirac_solver_progress_sync.json` → `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. A report file exists in `docs/harness_reports/`

### 7.3 State Files

| File | Purpose |
|------|---------|
| `state/dirac_solver_progress_sync.json` | Global workflow state (`RECEIVED` → `PLANNED` → `EXECUTING` → `REVIEWING` → `DONE` / `BLOCKED`) |
| `state/dirac_exec_queue.json` | Pending execution tasks with priority and timeout |
| `state/copilot_openclaw_bridge.json` | Execution bus bridge between Copilot and OpenClaw |
| `state/multi_agent_learning_state.json` | Failure-pattern knowledge base |
| `dev_state.json` | Real-time dev-flow dashboard state (updated by `physics_engine.ts`) |

### 7.4 Port Allocation

| Port | Service | Notes |
|------|---------|-------|
| 3001 / 3004 | Node.js API | Primary orchestrator API |
| 5173 | Vite frontend | React dev server |
| 8000 | Octopus MCP | Docker container; must be Octopus, not a misbehaving process |
| 8001 | Harness / Python backend | FastAPI harness and local solver |
| 8101 | Harness fallback | Secondary harness entry |

**Troubleshooting order when things break:**
1. Check SSH/tunnel connectivity.
2. Verify ports `3004`, `5173`, `8000`, `8001`, `8101` are bound to the correct processes (`ss -lntp`).
3. Confirm port `8000` is Octopus MCP (not a stale process).
4. Check Octopus MCP for stuck/timeout processes.
5. Inspect `state/` files for consistency.
6. Only then validate physical parameters.

### 7.5 Git Hygiene

- `.env` and `.env.local` are gitignored — never commit secrets.
- `node_modules/`, `__pycache__/`, `.venv/` are gitignored.
- Octopus large binary outputs (`.obf`, `.nc`, `.vtk`, `.cube`, `td.general/`, `restart/`) are gitignored.
- `logs/`, `dev_state.json`, `computation_log.md` are gitignored (machine-local state).

---

## 8. Testing and Validation

### 8.1 Test Strategy

There is **no traditional unit-test suite** in `tests/` (the directory is currently empty). Validation is **harness-driven** and **benchmark-driven**:

- **Harness cases** are defined in `knowledge_base/benchmark_cases.json`. Each case specifies:
  - `default_config` — physics parameters
  - `theory` — reference values (e.g., NIST energies)
  - `tolerance.relative_error_max` — pass threshold (typically 3%)
  - `comparator` — how to evaluate (e.g., `infinite_well_ground_state`, `h2o_gs_reference_energy`)

- **Approved golden cases** (verified, UI-exposed):
  - `ch4_gs_reference` — Methane ground state
  - `n_atom_gs_official` — Nitrogen atom ground state
  - `infinite_well_v1` — 1D infinite well analytic benchmark
  - `harmonic_oscillator_v1` — 1D harmonic oscillator analytic benchmark

- **Pending cases** (under validation):
  - `hydrogen_gs_reference`, `h2o_gs_reference`, `h2o_tddft_*` variants

### 8.2 Running Validation Scripts

```bash
# CH4 convergence replay (validates frontend ↔ backend parameter alignment)
python scripts/replay_ch4_frontend_convergence.py --api-base http://10.72.212.33:3001 --request-timeout 360

# Hydrogen 3-step validation (GS → TD → review)
python scripts/validate_hydrogen_three_step.py --api-base http://10.72.212.33:3001 --timeout 240

# Dispatch a standard task
python scripts/dispatch_dirac_task.py \
  --task 'n_atom_gs_official' \
  --source cli \
  --execute \
  --exec-timeout-seconds 300 \
  --sync-state state/dirac_solver_progress_sync.json

# Cleanup old harness reports
python scripts/cleanup_harness_reports.py
```

### 8.3 Octopus Convergence Parameters (Verified Baseline)

Verified parameters for PP Mode are documented in `docs/octopus_case_convergence.md`:

| Atom | Mode | spacing | radius | XC | Eigenvalue Error | Status |
|------|------|---------|--------|----|-----------------|--------|
| N | PP LDA | 0.18 Å | **10.0 Å** | lda_x+lda_c_pz | s: **0.4%** | ✅ |
| H | PP PBE | 0.18 Å | 10.0 Å | gga_x_pbe+gga_c_pbe | 1s: **0.03%** | ✅ |
| He | PP LDA | 0.15 Å | 10.0 Å | lda_x+lda_c_pz | 1s: 1.8% | ✅ |

**Important:** `docs/octopus_user_guide.md` is the **operation manual**; `docs/octopus_case_convergence.md` is the **verified parameter ground truth**.

---

## 9. Deployment

### 9.1 Docker (Octopus MCP)

```bash
cd docker
docker compose up -d          # Start Octopus MCP on port 8000
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d  # GPU mode
```

The Octopus container is built from `registry.gitlab.com/octopus-code/octopus:latest` with Python MCP server (`workspace/server.py`) layered on top.

### 9.2 Cloud Bootstrap (Ubuntu 24.04)

```bash
sudo bash deploy/setup_cloud.sh
# Then edit .env with ZCHAT_API_KEY, and run:
./start_all.sh
```

This installs Docker, Node.js 20, Python deps, builds the Octopus image, and opens firewall ports (`3001`, `5173`, `8000`).

### 9.3 Windows Local Development

Use `scripts/dc.ps1` for integrated SSH tunnel + service management. The project is accessed through RaiDrive mount `Z:\.openclaw\workspace\projects\Dirac`.

---

## 10. Security Considerations

- **`.env` contains secrets** (`ZCHAT_API_KEY`). It is gitignored. Never commit it.
- **SSH keys** for `dirac-key` are stored in `.ssh/` (gitignored).
- **OpenClaw execution policy** (`orchestration/openclaw_exec_policy.json`) is configured for `full_auto` mode on the remote HPC with auditable guardrails. All commands are logged to `docs/harness_reports/`.
- **State files** (`state/*.json`) contain runtime metadata but no credentials. They are gitignored because they are machine-local and managed by the harness.
- **The `.mcp.json` file** in the project root configures local MCP servers (tavily-search, semantic-scholar, github, etc.). Some entries contain API keys (e.g., Gemini). Treat this file as sensitive.

---

## 11. Common Pitfalls for Agents

1. **Assuming `engineMode` defaults to Octopus 3D.** The default is `local1D`. Any real molecular calculation **must** explicitly set `engineMode: 'octopus3D'`.
2. **Judging success by console output.** Always check `state/dirac_solver_progress_sync.json` for `workflow_state` and `workflow_event`.
3. **Using wrong paths on Windows.** Always use the RaiDrive mount `Z:\.openclaw\...` when referencing the project from Windows. The server path is `/data/home/zju321/...`.
4. **Port 8000 conflicts.** Verify with `ss -lntp` that port 8000 is owned by the Octopus Docker container, not a stale Python process.
5. **VisIt not found.** If `VISIT_EXE` is not set or VisIt is not on PATH, 3D density visualization falls back to Matplotlib isosurface panels (lower quality).
6. **Knowledge Base chunks missing.** The vector store exists but primary corpus chunks may need reconstruction. Check `knowledge_base/vector_store/` status before relying on RAG.

---

## 12. Key Documentation References

| Document | Language | Content |
|----------|----------|---------|
| `README.md` | English | High-level architecture, common tasks, troubleshooting order |
| `CLAUDE.md` | Chinese | Detailed directory map, verified parameters, dev conventions |
| `docs/octopus_user_guide.md` | Chinese | Octopus MCP operation manual (Formula / PP / All-Electron modes) |
| `docs/octopus_case_convergence.md` | Mixed | Verified convergence parameters (ground truth) |
| `docs/openclaw_operating_model.md` | English | OpenClaw workflow and state-machine documentation |
| `docs/development_lessons_20260418.md` | Mixed | Development experience and incident retrospectives |
| `.github/copilot-instructions.md` | English | Role definition and 3-tier architecture rules for Copilot agents |

---

*Last updated: 2026-05-05 — generated from live codebase analysis.*
