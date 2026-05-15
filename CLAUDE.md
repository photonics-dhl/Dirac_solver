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
# 启动全套服务
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell
# 仅 SSH
ssh dirac-key
```

| 端口 | 服务 | 源文件 |
|------|------|--------|
| 3004 | Node API (LangGraph orchestration) | — |
| 5173 | Vite 前端 dev server | `frontend/` |
| 8000 | DFT 计算后端 (Octopus/VASP MCP) | `docker/workspace/server.py` |
| 8001 | local1D solver + KB RAG + Harness | `backend_engine/main.py` |
| 8101 | 备用入口 | — |

---

## 目录结构（关键路径）

```
Dirac/
├── scripts/                      # 自动化编排脚本
├── orchestration/                # OpenClaw 策略 + 交接包模板
├── state/                        # 运行时状态（唯一真值）
├── docker/workspace/             # MCP server (Octopus+VASP, PBS)
├── backend_engine/               # Harness + local1D + KB RAG
├── frontend/src/                 # React 主组件
├── knowledge_base/               # corpus_new/ + vector_store/ + manifest
├── docs/                         # 收敛验证 + 用户手册 + TDDFT 分析
├── rules/                        # 开发规范 + 故障排查 + 详细配置
├── benchmarks/                   # HPC Octopus benchmark
└── logs/                         # 运维日志
```

---

## 规则索引（渐进式披露）

> CLAUDE.md 只放指针。正文在 `rules/`，详细流程在 `docs/`。

| 需要了解 | 文件 |
|----------|------|
| 前后端架构、数据流、前端开发 | [rules/architecture.md](rules/architecture.md) |
| OpenClaw 编排流程、关键词路由、知识库 | [rules/orchestration.md](rules/orchestration.md) |
| 常用命令（预检/分发/VASP/PBS）| [rules/commands.md](rules/commands.md) |
| Octopus 16.0 行为、PP Mode 真值、容器复用 | [rules/octopus-behavior.md](rules/octopus-behavior.md) |
| VASP 6.x 配置路径、参数、元素支持 | [rules/vasp-config.md](rules/vasp-config.md) |
| HPC 硬件拓扑、并行策略、PBS 监控 | [rules/hpc-operations.md](rules/hpc-operations.md) |
| 开发规范（文档归位、状态文件、禁 commit 项）| [rules/dev-conventions.md](rules/dev-conventions.md) |
| 故障排查顺序 | [rules/troubleshooting.md](rules/troubleshooting.md) |
| Octopus MCP 用户操作手册 | [docs/octopus_user_guide.md](docs/octopus_user_guide.md) |
| PP Mode 收敛验证（唯一真值）| [docs/octopus_case_convergence.md](docs/octopus_case_convergence.md) |
| TDDFT 分析管道（脚本+公式）| [docs/tddft/](docs/tddft/) |
| 跨会话决策交接 | [HANDOFF.md](HANDOFF.md) |

---

## 成功判定（唯一真值）

必须同时满足：
1. `state/dirac_solver_progress_sync.json` → `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. 报告文件存在于 `docs/harness_reports/`

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

### 防卡死深入诊断
- 2026-05-14 诊断：Puppeteer MCP Chrome 进程泄漏（15 孤儿进程/1.2GB）→ 主因；npx 冷启动链阻塞 → 次因。详见记忆文件中 session-stall 相关记录。
