# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Dirac_solver

> Web solver for relativistic quantum mechanics (Dirac equation) and strong-field physics (TDDFT), powered by Octopus DFT engine (16.0) + VASP PAW-PBE, orchestrated by OpenClaw multi-agent automation.

---

## 项目概览

| 字段 | 内容 |
|------|------|
| **类型** | 科学研究 + Web 应用 + 自动化框架 |
| **核心** | 3D 相对论量子力学求解器（Dirac）+ 时变密度泛函（TDDFT）|
| **计算引擎** | Octopus 16.0 (DFT/TDDFT, Fortran/C++) + VASP 6.x (DFT, PAW-PBE) |
| **前端** | React 19 + Vite 4 + TypeScript + Tailwind CSS 3 |
| **后端** | Dual-server: MCP DFT server (Starlette, port 8000) + Harness/local1D server (FastAPI, port 8001) |
| **自动化** | OpenClaw（Planner→Executor→Reviewer 三层）|
| **飞书集成** | 双 Bot 架构（Scholar/feishu-bot）|
| **运行平台** | 远端 HPC CentOS 7（10.72.212.33，SSH: `dirac-key`）|

---

## 路径架构（必须牢记）

> 本地 Windows 通过 RaiDrive CIFS 挂载访问服务器文件。

| 标识 | 路径 | 说明 |
|------|------|------|
| **本地 Windows** | `C:\Users\Mac\` | Windows 宿主机 home |
| **服务器 CentOS 7** | `/data/home/zju321/` | HPC 实际文件系统 |
| **RaiDrive 挂载** | `Z:\` = `\\RaiDrive-Mac\SFTP\` | CIFS 映射到服务器 data/home/zju321 |
| **OpenClaw 根目录** | `Z:\.openclaw` | 服务器上的 .openclaw |
| **项目目录** | `Z:\.openclaw\workspace\projects\Dirac` | 本 workspace 实际路径 |
| **VASP POTCAR** | `/data/home/Hzk-14/pot/potpaw_PBE.54/` | PAW-PBE 赝势库 |
| **VASP binary** | `/data/software/AMD/vasp_std` | HPC VASP executable |

**关键约束**：OpenClaw 部署在**服务器**，所有涉及 `.openclaw` 路径必须用 RaiDrive 挂载路径，不能用本地 Windows 路径。

---

## 远端连接

```bash
# 启动全套服务（推荐）
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell

# 仅 SSH 连接
ssh dirac-key
```

**服务端口（远端）**：

| 端口 | 服务 | 文件 |
|------|------|------|
| 3004 | Node API (LangGraph orchestration，前端中转) | — |
| 5173 | Vite 前端 dev server | `frontend/` |
| 8000 | DFT 计算后端：Octopus/VASP MCP (Starlette + SSE transport) | `docker/workspace/server.py` |
| 8001 | local1D 求解器 + KB RAG + Harness 基准 (FastAPI) | `backend_engine/main.py` |
| 8101 | 备用入口 | — |

---

## 目录结构（关键路径）

```
Dirac/
├── CLAUDE.md                          # 项目指南（本文件）
├── scripts/                           # 自动化脚本（核心编排）
│   ├── dispatch_dirac_task.py          # 任务分发入口
│   ├── run_multi_agent_orchestration.py  # OpenClaw 编排器
│   ├── dirac_exec_worker.py            # 队列 Worker
│   └── dc.ps1                         # 服务启动
├── orchestration/                     # OpenClaw 策略配置
│   ├── task_dispatch_rules.json        # 关键词路由规则
│   └── contracts/                      # 交接包模板
├── state/                             # 运行时状态（唯一真值）
├── docker/workspace/                   # 服务器端 Python 服务
│   ├── server.py                       # MCP server：Octopus + VASP 后端，PBS 调度
│   └── vasp_backend.py                 # VASP INCAR/POSCAR/KPOINTS/POTCAR 生成
├── frontend/                          # React + Vite 前端
│   └── src/
│       ├── App.tsx                     # 主组件（engine 切换、compute 流程）
│       ├── ResultsPanel.tsx            # 结果展示 + 对比视图
│       ├── Mol3DViewer.tsx             # 3D 分子可视化（Three.js）
│       ├── GeometryEditor.tsx          # 自定义原子坐标编辑器
│       └── DevFlowDashboard.tsx        # 开发流程监控面板
├── backend_engine/                    # Harness + local1D solver + KB RAG (FastAPI, port 8001)
│   ├── main.py
│   └── kb_rag.py                      # KB RAG 服务
├── knowledge_base/                    # 知识库
│   ├── corpus_new/                     # 参考值文档（含 VASP GS reference）
│   ├── vector_store/                   # Chroma 向量数据库
│   └── corpus_manifest.json
├── docs/                              # 文档
│   ├── octopus_case_convergence.md     # ✅ 已验证收敛参数（PP Mode 真值）
│   ├── octopus_user_guide.md           # Octopus MCP 操作手册
│   ├── tddft/                          # TDDFT 分析：脚本 + 数据 + 图表
│   │   ├── analyze_*_spectrum.py       # 光谱分析脚本
│   │   ├── plot_*_spectrum.py          # 出版级图表生成
│   │   └── data/                       # cross_section_vector 原始数据 + .npz
│   └── harness_reports/               # OpenClaw 执行报告（48h内）
├── benchmarks/                        # HPC Octopus benchmark
├── rules/                             # 故障排查 + 开发规范
├── tests/                             # 测试目录（当前为空，无测试套件）
└── logs/                              # 运维日志
```

---

## 编排调度流程（OpenClaw）

```
User/CLI 任务 → dispatch_dirac_task.py
  → 关键词匹配 task_dispatch_rules.json（9 条规则）
  → 分配 Agent 角色: supervisor | planner | executor | reviewer
  → run_multi_agent_orchestration.py（三层循环）
     Planner: 分析任务、搜索知识库、生成执行计划
     Executor: 调用 MCP 工具（run_octopus/run_vasp）、监控 PBS
     Reviewer: 对比 benchmark 参考值、判定 PASS/FAIL
  → 结果写入 state/ + 报告写入 docs/harness_reports/
```

**关键词路由示例**：
- `n_atom_gs_official`, `ch4_gs` → `dirac_standard_case_orchestration` (supervisor)
- `/auto`, `自动调试` → `auto_default_orchestration`
- `refactor`, `fix bug` → `code_implementation` (copilot-executor)
- `review`, `质量门禁` → `quality_review` (reviewer)

## 知识库结构

```
knowledge_base/
├── corpus_new/          # 参考值文档（人工编写，核心真值）
├── corpus_mp/           # Materials Project 自动抓取（H2O/Si/CH4/H2）
├── vector_store/        # ChromaDB 持久化（5 collection UUID）+ chroma.sqlite3
├── metadata/            # PDF 源索引 + 摄入日志
└── corpus_manifest.json
```

**KB RAG** (`backend_engine/kb_rag.py`): ChromaDB 默认嵌入，`/kb/query` 支持 top_k + topic_tag 过滤。

## 客户端 MCP 配置

`.mcp.json` 配置 Claude Code 可用 MCP 服务器：`semantic-scholar`, `paper-search`, `github`, `mermaid`, `puppeteer`, `fetch`, `memory`, `tavily-search`（经本地代理 `http://127.0.0.1:7890`）。

---

## 前后端架构

### 后端（双服务器）

**Port 8000 — DFT 计算后端** (`docker/workspace/server.py`, 3061 行):
Starlette + MCP SSE transport。唯一能提交 Octopus/VASP 作业的服务。

- **REST endpoints**: `/health` (GET), `/solve` (POST, Octopus), `/solve_vasp` (POST, VASP)
- **MCP tools** (SSE `/sse` + `/messages`): `run_octopus`, `run_vasp`, `parse_results`
- **PBS 调度**: 通过 `qsub` 提交作业到 HPC 队列
- **Octopus 执行**: udocker 容器 `registry.gitlab.com/octopus-code/octopus:16.0`
- **VASP 执行**: 直接二进制 `/data/software/AMD/vasp_std` 或 PBS
- 辅助模块: `vasp_backend.py` (INCAR/POSCAR/KPOINTS/POTCAR 生成，424 行)

**Port 8001 — Harness + local1D 后端** (`backend_engine/main.py`, 1899 行):
FastAPI。提供轻量级 Dirac/Schrödinger 数值求解（非 DFT）、知识库 RAG、基准测试框架。

- **REST endpoints**: `/solve` (local1D Dirac), `/kb/ingest_markdown`, `/kb/query`, `/harness/case_registry`, `/harness/capability_matrix`, `/harness/run_case`, `/harness/iterate_case`
- **KB RAG**: `backend_engine/kb_rag.py` — ChromaDB 向量存储 + 语料库检索
- **Harness**: 控制回路（desired_state → controller → solver → quality_feedback），自动网格细化
- **Case 类型**: `boundstate_1d`, `dft_gs_3d`, `response_td`, `periodic_bands`, `hpc_scaling`

### 前端（React + Vite, port 5173）

三引擎模式：`local1D` | `octopus3D` | `vasp`

**Vite 代理路由** (`frontend/vite.config.ts`):
- `/api/*` → port 8000 (DFT 后端)
- `/solve_vasp` → port 8000 (VASP 直接调用)

**数据流**：
- **local1D 流程**: 前端 → Node API (3004) → 本地数值求解 → 直接返回
- **Octopus 流程**: 前端 → `/api/physics/stream` (SSE) → Node API (3004) → MCP `run_octopus` (8000)
- **VASP 流程**: 前端 → `POST /solve_vasp` → 直接到 port 8000

### 前端开发

```bash
cd frontend
npm run dev          # 启动 Vite dev server（远端 5173）
npm run build        # TypeScript 编译 + Vite 构建
npm run preview      # 预览生产构建
```

无测试套件。`tests/` 目录为空。

---

## 常用命令

### 预检（连接后第一步）

```bash
ssh dirac-key "(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep -E ':(3004|5173|8000|8001|8101)\b'"
curl -s http://127.0.0.1:3004/api/automation/dispatch/latest
curl -s http://127.0.0.1:8001/harness/case_registry
```

### 自动分发执行

```bash
python scripts/dispatch_dirac_task.py \
  --task 'n_atom_gs_official' \
  --source cli \
  --execute \
  --exec-timeout-seconds 300 \
  --sync-state state/dirac_solver_progress_sync.json
```

### 报告清理

```bash
python scripts/cleanup_harness_reports.py
```

### VASP 直接调用

```bash
curl -s -X POST http://127.0.0.1:8000/solve_vasp \
  -H 'Content-Type: application/json' \
  -d '{"octopusMolecule":"H2O","xcFunctional":"PBE","spinComponents":"unpolarized","encut":520,"ediff":1e-6,"prec":"Accurate","vaspBox":10.0}' | python -m json.tool
```

### PBS 作业监控

```bash
qstat -f JOBID | grep -E 'walltime|Job_Name|queue'    # 详细状态
qstat | grep $(whoami) | head -10                       # 我的所有作业
tracejob JOBID                                          # 作业生命周期
```

---

## 计算引擎详情

### Octopus 16.0（udocker 容器）

**PP Mode 已验证参数**（真值：`docs/octopus_case_convergence.md`）：

| 原子 | 模式 | spacing | radius | XC | 特征值误差 | 状态 |
|------|------|---------|--------|-----|---------|------|
| N | PP LDA | 0.18 Å | 10.0 Å | lda_x+lda_c_pz | s: 0.4% | ✅ |
| H | PP PBE | 0.18 Å | 10.0 Å | gga_x_pbe+gga_c_pbe | 1s: 0.03% | ✅ |
| He | PP LDA | 0.15 Å | 10.0 Å | lda_x+lda_c_pz | 1s: 1.8% | ✅ |

**关键 Octopus 16.0 行为**：
- **FromScratch + CalculationMode=td/casida 不会自动运行 GS**。需要两步：先 `CalculationMode=gs`，再 `CalculationMode=td/casida` 且 `FromScratch=no`
- **Casida XC Kernel 仅支持 LDA**。PBE/GGA 触发 fatal error: "Only LDA functionals are authorized in XCKernel"
- **ScaLAPACKCompatible=yes 需要 ExperimentalFeatures=yes**，否则 fatal error
- **`TDOutput=cross_section_vector` 不存在** — 用 `oct-propagation_spectrum` 后处理工具生成
- **udocker 容器复用**：避免每次 ~40s 镜像提取开销
  ```bash
  CONTAINER=$(udocker ps | grep octopus | head -1 | awk '{print $1}')
  udocker run --volume=/data/home/zju321:/data/home/zju321 \
    --env="OMP_NUM_THREADS=16" $CONTAINER \
    bash -c "cd /workdir && mpirun -np 4 --bind-to core /app/bin/octopus"
  ```

### VASP 6.x（PAW-PBE）

**配置路径**：
- Binary: `/data/software/AMD/vasp_std`
- POTCAR: `/data/home/Hzk-14/pot/potpaw_PBE.54/`
- LD_LIBRARY_PATH: `/data/home/Hzk-20/anaconda3/lib:/data/home/Hzk-14/deepmd-kit/lib`

**标准参数**：ENCUT=520 eV, EDIFF=1e-6, PREC=Accurate, ISMEAR=0, SIGMA=0.01, Gamma-only k-points, 8-10 Å cubic box

**支持元素**：H, C, N, O（PAW_RPBE POTCAR；扩展需添加 POTCAR 文件）

**ΔSCF 电离势**：通过 `nelect=N-1` 参数支持阳离子计算

**参考数据**：`knowledge_base/corpus_new/vasp_gs_reference.md` — 原子 + 分子 GS 参考值

### TDDFT 分析管道

`docs/tddft/` 包含完整分析工具链：
```bash
# 运行 oct-propagation_spectrum（在服务器上）
cd /workdir && /app/bin/oct-propagation_spectrum < /dev/null
# 输出 cross_section_vector → 复制到 docs/tddft/data/

# 分析光谱（本地）
python docs/tddft/analyze_ch4_h2o_spectra.py   # 峰值检测 + 截面转换
python docs/tddft/plot_ch4_h2o_spectra.py       # 生成出版级 PNG

# 吸收截面转换公式
# σ_abs(ω) [Bohr²] = (2π²/c) × S(ω) ≈ 0.14407 × S(ω)
# 1 Bohr² ≈ 28.003 Mb (megabarns)
```

**分辨率限制**：ΔE = 2π/T。T=200 a.u. → ΔE=0.85 eV；T=1000 a.u. → ΔE=0.17 eV（光谱级）

---

## 成功判定（唯一真值）

必须同时满足：
1. `state/dirac_solver_progress_sync.json` → `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. 报告文件存在于 `docs/harness_reports/`

---

## HPC 硬件拓扑

| Node | CPU | Cores | NUMA nodes | Cores/NUMA |
|------|-----|-------|-----------|------------|
| cn01-cn15 | Intel Xeon Platinum 8369B | 64 | 2 | 32 |
| fat01 | AMD EPYC 7H12 | 128 (64 alloc) | 8 | 16 |

**并行策略**：
- 小体系（~1M grid points, ≤16 KS states）：纯 OMP (np=1, OMP_NUM_THREADS=64) — MPI overhead 不值得
- 大体系（>5M grid points）：`mpirun -np 4` + `OMP_NUM_THREADS=16` + `ParDomains=4`
- Intel Xeon: `--map-by socket --bind-to socket`
- AMD EPYC: `--map-by numa --bind-to numa`

---

## 监控注意事项

- **NFS 输出缓冲**：PBS 脚本 shell 重定向到 NFS 文件可能延迟数小时。用 `wc -l td.general/energy` 追踪进度，不依赖重定向日志
- **PBS CPU vs Walltime**：`qstat` "Time Use" 显示 CPU 时间（user+system），非 walltime。多线程作业 CPU 时间 = 10-20× walltime。用 `qstat -f JOBID | grep walltime` 取真实耗时
- **PBS 目录碰撞**：同时运行的作业共享同一工作目录会相互破坏 input/state。不同计算类型用独立目录

---

## 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| **Harness iterate 给出过小 spacing** | 待修复 | gridSpacing=0.05 natural units 导致 Octopus 不收敛 |
| **Knowledge Base corpus_mp** | 待重建 | 需添加 Materials Project 参考数据 |
| **node-v16.20.2-linux-x64** | 保留 | 服务器 HPC 工具链，勿删 |
| **VASP 仅支持 H/C/N/O** | 需扩展 | 添加更多 POTCAR 文件即可 |

---

## 防卡死规则（Anti-Stuck Protocol）

### 循环中断
1. 同一命令失败 2 次 → 立即停止重试，分析根因
2. 30 秒无响应 → 输出状态，不要持续静默思考
3. MCP 工具调用失败 → 回退到 Bash/Read/Write
4. WebSearch/WebFetch 失败 → 告知用户，最多重试 1 次

### MCP 使用限制
- 优先用内置工具（Read/Write/Edit/Glob/Grep/Bash），MCP 仅作补充
- MCP diagram/mermaid → 仅在用户明确需要图表时使用

### Session 管理
- 每完成一个任务后自我评估是否需要 `/compact`
- 上下文使用超过 70% → 主动提示压缩
