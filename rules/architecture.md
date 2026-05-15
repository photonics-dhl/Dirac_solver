# Backend & Frontend Architecture

## Backend (Dual-Server)

### Port 8000 — DFT 计算后端 (`docker/workspace/server.py`, 3061 行)

Starlette + MCP SSE transport。唯一能提交 Octopus/VASP 作业的服务。

- **REST endpoints**: `/health` (GET), `/solve` (POST, Octopus), `/solve_vasp` (POST, VASP)
- **MCP tools** (SSE `/sse` + `/messages`): `run_octopus`, `run_vasp`, `parse_results`
- **PBS 调度**: 通过 `qsub` 提交作业到 HPC 队列
- **Octopus 执行**: udocker 容器 `registry.gitlab.com/octopus-code/octopus:16.0`
- **VASP 执行**: 直接二进制 `/data/software/AMD/vasp_std` 或 PBS
- 辅助模块: `vasp_backend.py` (INCAR/POSCAR/KPOINTS/POTCAR 生成，424 行)

### Port 8001 — Harness + local1D 后端 (`backend_engine/main.py`, 1899 行)

FastAPI。提供轻量级 Dirac/Schrödinger 数值求解（非 DFT）、知识库 RAG、基准测试框架。

- **REST endpoints**: `/solve` (local1D Dirac), `/kb/ingest_markdown`, `/kb/query`, `/harness/case_registry`, `/harness/capability_matrix`, `/harness/run_case`, `/harness/iterate_case`
- **KB RAG**: `backend_engine/kb_rag.py` — ChromaDB 向量存储 + 语料库检索
- **Harness**: 控制回路（desired_state → controller → solver → quality_feedback），自动网格细化
- **Case 类型**: `boundstate_1d`, `dft_gs_3d`, `response_td`, `periodic_bands`, `hpc_scaling`

## Frontend (React + Vite, port 5173)

三引擎模式：`local1D` | `octopus3D` | `vasp`

**Vite 代理路由** (`frontend/vite.config.ts`):
- `/api/*` → port 8000 (DFT 后端)
- `/solve_vasp` → port 8000 (VASP 直接调用)

**数据流**：
- **local1D**: 前端 → Node API (3004) → 本地数值求解 → 直接返回
- **Octopus**: 前端 → `/api/physics/stream` (SSE) → Node API (3004) → MCP `run_octopus` (8000)
- **VASP**: 前端 → `POST /solve_vasp` → 直接到 port 8000

## Frontend Dev

```bash
cd frontend
npm run dev          # Vite dev server（远端 5173）
npm run build        # TypeScript 编译 + Vite 构建
npm run preview      # 预览生产构建
```

No test suite. `tests/` is empty.
