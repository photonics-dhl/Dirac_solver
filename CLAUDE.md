# Dirac_solver

> Web solver for relativistic quantum mechanics (Dirac equation) and strong-field physics (TDDFT), powered by Octopus DFT engine and OpenClaw multi-agent automation.

---

## 项目概览

| 字段 | 内容 |
|------|------|
| **类型** | 科学研究 + Web 应用 + 自动化框架 |
| **核心** | 3D 相对论量子力学求解器（Dirac）+ 时变密度泛函（TDDFT）|
| **计算引擎** | Octopus（DFT/TDDFT，C++/Fortran）|
| **前端** | React + Vite |
| **后端编排** | Node.js + LangGraph Agentic State Graph |
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
| **OpenClaw 根目录** | `Z:\.openclaw` = `\\RaiDrive-Mac\SFTP\.openclaw` | 服务器上的 .openclaw |
| **项目目录** | `Z:\.openclaw\workspace\projects\Dirac` | 本 workspace 实际路径 |

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
| 端口 | 服务 |
|------|------|
| 3004 | Node API |
| 5173 | Vite 前端 |
| 8000 | Octopus MCP |
| 8001 | Harness 主入口 |
| 8101 | Harness 兜底入口 |

---

## 目录结构

```
Dirac/
├── scripts/                          # 自动化脚本（核心）
│   ├── dispatch_dirac_task.py        # 任务分发入口
│   ├── run_multi_agent_orchestration.py  # OpenClaw 编排器
│   ├── execute_replan_packet.py      # 重规划执行
│   ├── dirac_exec_worker.py          # 队列 Worker
│   ├── audit_openclaw_permissions.py # 预检：OpenClaw 权限
│   ├── ensure_openclaw_exec.py       # 预检：执行环境
│   ├── cleanup_harness_reports.py    # 报告清理
│   ├── feishu_notify.py              # 飞书通知
│   ├── llm_client.py                 # LLM 调用
│   ├── dc.ps1                       # 服务启动
│   ├── connect_server.ps1            # 服务器连接
│   ├── replay_ch4_frontend_convergence.py  # CH4 参数复现验证
│   ├── validate_hydrogen_three_step.py     # Hydrogen 三步验证
│   ├── run_kb_reliable_autopilot.py  # KB 自动驾驶
│   ├── build_research_kb.py          # KB 构建
│   ├── octopus_parallel_benchmark.py  # HPC Octopus benchmark
│   ├── run_benchmark_param_search.py  # 参数搜索
│   ├── run_harness_acceptance.py      # Harness 验收
│   ├── run_harness_sweep.py          # Harness 扫描
│   ├── run_vector_kb_ops.py          # 向量 KB 操作
│   ├── generate_explanation.py       # 解释生成
│   ├── visitlog.py                   # 可视化
│   ├── run_dirac_debug_ops.py        # 调试快照
│   ├── monitor_5173_health.py       # 服务健康检查
│   └── monitor_feishu_signal.py     # 飞书信号监控
│
├── orchestration/                    # OpenClaw 策略配置
│   ├── task_dispatch_rules.json       # 关键词路由规则
│   ├── execution_wake_state_machine.json  # L0/L1 状态机
│   ├── openclaw_exec_policy.json      # 执行策略
│   ├── coding_gateway_config.json     # 编码网关配置
│   ├── agent_skills_manifest.json    # Agent 技能清单
│   └── contracts/                     # 交接包模板
│       ├── handoff_packet.template.v1.json
│       ├── review_verdict.template.v1.json
│       ├── escalation_packet.template.v1.json
│       └── progress_sync.template.v1.json
│
├── state/                            # 运行时状态（唯一真值）
│   ├── dirac_solver_progress_sync.json   # 全局进度同步
│   ├── dirac_exec_queue.json             # 任务队列
│   ├── copilot_openclaw_bridge.json      # 执行总线桥接
│   ├── multi_agent_learning_state.json   # 失败知识库
│   ├── coding_gateway_tasks.json          # 编码网关任务
│   └── coding_gateway_runs/               # 编码网关运行记录
│
├── docs/                             # 文档（已验证）
│   ├── octopus/                        # Octopus 参考文档
│   │   ├── Octopus_Operation_Handbook.md
│   │   ├── Octopus_Knowledge_Base.md
│   │   ├── Output_Fields_Explanation.md
│   │   ├── Output_Parsing_Manual.md
│   │   ├── UI_User_Guide.md
│   │   ├── VisIt_Integration_Guide.md
│   │   ├── octopus_input_generator.py
│   │   └── scripts/octopus_analyzer.py
│   ├── harness_reports/               # OpenClaw 执行报告（48h内）
│   ├── octopus_case_convergence.md     # ✅ 已验证收敛参数（PP Mode 基准）
│   ├── octopus_user_guide.md          # ✅ Octopus MCP 操作手册
│   ├── development_lessons_20260418.md  # 开发经验
│   └── openclaw_operating_model.md    # OpenClaw 运作模型
│
├── knowledge_base/                    # 知识库
│   ├── corpus_new/                    # ✅ 知识来源（case 参考值 + provenance）
│   │   ├── n_atom_gs_official.md      # N 原子 GS 参考值
│   │   ├── h_atom_gs_nist_reference.md # H 原子 NIST 参考
│   │   ├── ch4_gs_reference.md        # CH4 GS 参考
│   │   ├── h2o_gs_reference.md       # H2O GS 参考
│   │   ├── executor_guide.md          # Executor 执行指南
│   │   └── ...（其他 case 参考文档）
│   ├── vector_store/                  # ✅ Chroma 向量数据库（136 embeddings）
│   ├── metadata/                      # RAG 元数据
│   └── corpus_manifest.json          # 知识库清单
│
├── benchmarks/                        # HPC Octopus benchmark 工具
│   ├── bench.sh / bench_multi.sh      # PBS benchmark 脚本
│   ├── inp                            # Octopus 输入模板
│   ├── *.csv                          # benchmark 结果
│   └── *.upf                          # 赝势文件
│
├── frontend/                         # React + Vite 前端
├── backend_engine/                    # Python MCP 服务（适配器层）
│   ├── main.py                        # MCP server 主逻辑
│   └── kb_rag.py                      # KB RAG 服务
├── src/                              # TypeScript 源码
├── docker/                           # Docker 配置
│   └── workspace/server.py            # Octopus MCP server（在服务器上）
├── deploy/                           # 部署脚本
├── external/                         # 外部集成
├── tests/                            # 测试目录
├── logs/                             # 运维日志
├── run/                              # HPC 运行目录
│   └── bench_multi/                   # 多进程 benchmark
└── CLAUDE.md                         # 项目说明（本文档）
```

---

## 成功判定（唯一真值）

必须同时满足：
1. `state/dirac_solver_progress_sync.json` → `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. 报告文件存在于 `docs/harness_reports/`

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

---

## Octopus 计算参数（已验证）

> 详见 `docs/octopus_case_convergence.md`（PP Mode）

| 原子 | 模式 | spacing | radius | XC | 特征值误差 | 状态 |
|------|------|---------|--------|-----|---------|------|
| N | PP LDA | 0.18 Å | **10.0 Å** | lda_x+lda_c_pz | s: **0.4%** | ✅ |
| H | PP PBE | 0.18 Å | 10.0 Å | gga_x_pbe+gga_c_pbe | 1s: **0.03%** | ✅ |
| He | PP LDA | 0.15 Å | 10.0 Å | lda_x+lda_c_pz | 1s: 1.8% | ✅ |

**注意**：`octopus_user_guide.md` 是操作手册，`octopus_case_convergence.md` 是已验证参数真值。

---

## 故障排查顺序

```
1. SSH/tunnel 是否抖动
2. 3004/8000/8001/8101 是否都在正确进程上
3. 8000 是否为 Octopus MCP（非误占进程）
4. Octopus MCP 是否超时（检查是否有 stuck 进程）
5. state 三件套是否一致
6. 再看参数与物理口径
```

---

## 开发规范

- **文档归入 `docs/`**：禁止在根目录创建散落文档
- **RaiDrive 路径优先**：涉及 `.openclaw` 必须用 `Z:\.openclaw` 而非 `C:\Users\Mac\.openclaw`
- **状态文件为唯一真值**：不以终端输出判定成功/失败
- **禁止 commit .log/.tmp/.bak**：hooks 自动过滤

---

## 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| **Harness iterate 给出过小 spacing** | 待修复 | gridSpacing=0.05 natural units 导致 Octopus 不收敛 |
| **Knowledge Base corpus_mp** | 待重建 | 需添加 Materials Project 参考数据 |
| **node-v16.20.2-linux-x64** | 保留 | 服务器 HPC 工具链，勿删 |
| **Scholar's Tea 双 Bot** | 正常 | 与 OpenClaw Dirac Bot 并行，互不干扰 |
