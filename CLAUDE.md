# Dirac_solver

> Web solver for relativistic quantum mechanics (Dirac equation) and strong-field physics (TDDFT), powered by Octopus DFT engine and OpenClaw multi-agent automation.

---

## 项目概览

| 字段 | 内容 |
|------|------|
| **类型** | 科学研究 + Web 应用 + 自动化框架 |
| **核心** | 3D 相对论量子力学求解器（Dirac）+ 时变密度泛函（TDDFT）|
| **计算引擎** | Octopus（DFT/TDDFT，C++/Fortran）|
| **前端** | React + Vite（Windows）|
| **后端编排** | Node.js + LangGraph Agentic State Graph |
| **自动化** | OpenClaw（PlannER→EXECUTOR→REVIEWER 三层）|
| **飞书集成** | 双 Bot 架构（Scholar/feishu-bot）|
| **运行平台** | 远端 HPC（10.72.212.33，SSH: `dirac-key`）|

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
| 3001 | Node API |
| 5173 | Vite 前端 |
| 8000 | Octopus MCP |
| 8001 | Harness 主入口 |
| 8101 | Harness 兜底入口 |

---

## 目录结构

```
Dirac/
├── scripts/                    # 自动化脚本
│   ├── dispatch_dirac_task.py  # 任务分发入口
│   ├── dirac_exec_worker.py   # 队列 Worker
│   ├── run_multi_agent_orchestration.py  # 多 Agent 编排
│   ├── execute_replan_packet.py           # 重规划执行
│   ├── monitor_5173_health.py            # 服务健康检查
│   ├── monitor_feishu_signal.py           # 飞书信号监控
│   ├── cleanup_harness_reports.py         # 报告清理
│   ├── replay_ch4_frontend_convergence.py # CH4 参数复现
│   ├── validate_hydrogen_three_step.py    # Hydrogen 三步验证
│   └── run_dirac_debug_ops.py             # 调试快照
│
├── orchestration/              # OpenClaw 策略配置
│   ├── task_dispatch_rules.json           # 关键词路由规则
│   ├── execution_wake_state_machine.json  # L0/L1 状态机
│   ├── openclaw_exec_policy.json          # 执行策略
│   ├── agent_skills_manifest.json         # Agent 技能清单
│   └── contracts/                          # 交接包模板
│
├── state/                      # 状态真值（判定成功/失败的唯一依据）
│   ├── dirac_solver_progress_sync.json    # 全局进度同步
│   ├── dirac_exec_queue.json              # 任务队列
│   ├── copilot_openclaw_bridge.json       # 执行总线桥接
│   └── multi_agent_learning_state.json    # 失败知识库
│
├── docs/                      # 文档
│   ├── dirac_openclaw_full_workflow_status_*.md  # 总览（主入口）
│   ├── harness_reports/                          # 参数收敛报告
│   │   ├── parameter_convergence_log.md
│   │   └── octopus_case_optimal_parameters_*.md
│   └── hpc-end-to-end-runbook-zh.md
│
├── frontend/                   # React + Vite 前端
├── backend_engine/             # Python MCP 服务（适配器层）
├── knowledge_base/             # 语料/向量库（重建中）
├── .github/                    # OpenClaw Agent/Skill 定义
│   ├── agents/                 # dirac-planner/executor/reviewer
│   └── skills/                 # 5 个核心 Skill
└── OpenClaw/                  # OpenClaw 框架（远端）

# 争议项（暂留，待进一步清理）
├── @Octopus_docs/             # Octopus 参考文档
├── harness_logs/              # 历史测试数据
├── generated_inputs/          # Octopus 输入模板
├── src/                      # TypeScript 源码
└── tests/                    # 测试
```

---

## 常用命令

### 预检（连接后第一步）
```bash
# 检查服务端口
ssh dirac-key "(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep -E ':(3001|5173|8000|8001|8101)\b'"

# 检查 API 健康
curl -s http://127.0.0.1:3001/api/automation/dispatch/latest
curl -s http://127.0.0.1:8001/harness/case_registry
```

### 自动分发执行
```bash
python scripts/dispatch_dirac_task.py \
  --task "Dirac_solver 调试 run_id=<ts>" \
  --source cli-smoke \
  --execute \
  --exec-timeout-seconds 240 \
  --auto-execute-replan \
  --sync-state state/dirac_solver_progress_sync.json
```

### 参数收敛复跑
```bash
python scripts/replay_ch4_frontend_convergence.py --api-base http://10.72.212.33:3001 --request-timeout 360
python scripts/validate_hydrogen_three_step.py --api-base http://10.72.212.33:3001 --timeout 240
```

### 调试快照
```bash
python scripts/run_dirac_debug_ops.py --mode snapshot
```

### 报告清理
```bash
python scripts/cleanup_harness_reports.py
```

---

## OpenClaw 工作流

### 执行链
```
任务文本 → 关键词路由 → 分发器 → 队列 →
Worker 执行 → OpenClaw 编排（Planner→Executor→Reviewer）→
状态同步 → 报告
```

### 成功判定（必须同时满足）
1. `state/dirac_solver_progress_sync.json` 中 `workflow_state = DONE`
2. `workflow_event = REVIEW_PASS`
3. 报告文件存在于 `docs/harness_reports/`

### 失败类型（参考 `state/multi_agent_learning_state.json`）
| 类型 | 频率 | 处理 |
|------|------|------|
| `endpoint_or_service` | 高 | 检查端口 8000/8001/8101 进程 |
| `planner_executor_chain_break` | 中 | 检查交接包契约 |
| `case_scope_mismatch` | 低 | 确认案例参数 |
| `benchmark_provenance` | 低 | 核对基准数据来源 |

---

## 已知问题

- **8000/8001/8101 端口互占**：有时 Octopus MCP 进程占错端口，先查 `ss -lntp`
- **Hydrogen 三步法偶尔不一致**：backend/frontend 参数对齐不足，保留失败样本用于回归
- **Knowledge Base 未构建完成**：当前 corpus 无 chunks/vector_store，需重建
- **Scholar's Tea 双 Bot**：与 OpenClaw Dirac Bot 并行，互不干扰

---

## 参考文档

| 文档 | 用途 |
|------|------|
| `docs/dirac_openclaw_full_workflow_status_*.md` | 总览主文档（必读）|
| `docs/hpc-end-to-end-runbook-zh.md` | HPC 全流程操作手册 |
| `docs/harness_reports/parameter_convergence_log.md` | 参数收敛轨迹 |
| `docs/harness_reports/octopus_case_optimal_parameters_*.md` | 最新最优参数 |
| `@Octopus_docs/Octopus_Operation_Handbook.md` | Octopus 操作手册 |
| `orchestration/execution_wake_state_machine.json` | 状态机定义 |

---

## 故障排查顺序

```
1. SSH/tunnel 是否抖动
2. 3001/8000/8001 是否都在正确进程上
3. 8000 是否为 Octopus MCP（非误占进程）
4. state 三件套是否一致
5. 再看参数与物理口径
```

---

## 开发规范

- **禁止在根目录创建散落文档**：所有文档归入 `docs/`
- **禁止 commit .log/.tmp/.bak 文件**：由 hooks 自动过滤
- **状态文件为唯一真值**：不以终端输出判定成功/失败
- **Scholar's Tea Bot 隔离**：不在 Dirac 工作区操作飞书 Bot 相关路径
