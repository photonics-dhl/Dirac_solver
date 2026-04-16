# Dirac OpenClaw 全自动工作流与工程全景总文档

更新日期: 2026-04-14
维护目标: 作为 Dirac_solver 当前阶段的唯一综合说明文档，集中描述已完成能力、运行方式、参数收敛证据、知识库构建链路、工作区架构、状态文件、长期记忆要点与故障处置。

---

## 1. 总览结论

### 1.1 当前能力结论

- 全自动链路已具备完整骨架: 任务分发 -> 队列执行 -> 多代理编排 -> Reviewer 判定 -> 状态同步 -> Feishu/面板可见。
- 远端优先执行模式已固化: 通过 dirac-key + 远端服务启动，避免本地假阳性运行态。
- 状态真值链路已固化: 以 state 目录三份核心状态文件为主，不以聊天文本判定成功。

### 1.2 参数收敛阶段结论

- CH4 前端等效复现:
  - 已出现 PASS 记录（0.16A 尾段窗口判据 <= 0.1 eV）。
  - 也保留了 FAIL/超时记录，用于稳定性回归与重跑验证。
- Hydrogen:
  - 已有 PASS 记录（相对误差 <= 3%）在参数收敛日志中。
  - 三步法记录中仍有不一致或未对齐样本，已明确归档用于后续稳定化。

### 1.3 文档与产物治理结论

- 已执行中间报告清理策略后，docs/harness_reports 仅保留参数收敛主报告与总览报告（并保留 curve_artifacts 目录）。
- 当前参数证据主入口:
  - docs/harness_reports/parameter_convergence_log.md
  - docs/harness_reports/octopus_case_optimal_parameters_20260413.md

---

## 2. OpenClaw 全自动工作流（当前实现）

### 2.1 目标与原则

- 目标: 将 /auto 与 Dirac_solver 调试类任务稳定映射到可执行总线，而不是一次性文本响应。
- 原则:
  - 远端优先
  - 证据优先
  - 状态文件优先
  - Reviewer 与收敛门控优先

### 2.2 入口与触发

- CLI 触发: scripts/dispatch_dirac_task.py
- 队列消费: scripts/dirac_exec_worker.py
- 持久 worker 启动器: scripts/run_dirac_exec_worker.sh
- 恢复调试触发: task 文本包含 恢复调试 时走 resume_debug_session 路由

### 2.3 核心执行链

1. 任务进入分发器（dispatch）
2. 写入队列（state/dirac_exec_queue.json）
3. Worker 消费并执行自动路由（含 replan）
4. 更新 bridge（state/copilot_openclaw_bridge.json）
5. 更新全局同步状态（state/dirac_solver_progress_sync.json）
6. Reviewer 输出门控结论
7. 生成报告与可见状态

### 2.4 关键策略文件

- orchestration/task_dispatch_rules.json
- orchestration/execution_wake_state_machine.json
- orchestration/openclaw_exec_policy.json
- orchestration/agent_skills_manifest.json
- orchestration/coding_gateway_config.json

### 2.5 必查真值文件（判定成功/失败）

- state/dirac_solver_progress_sync.json
- state/dirac_exec_queue.json
- state/copilot_openclaw_bridge.json
- docs/harness_reports/task_dispatch_*.json（若存在）

### 2.6 服务基线（远端）

- 3001: Node API
- 5173: Frontend
- 8000: Octopus MCP
- 8001: Harness 主入口
- 8101: Harness 兜底入口

---

## 3. 参数收敛与案例现状（截至 2026-04-14）

数据来源:
- docs/harness_reports/parameter_convergence_log.md
- docs/harness_reports/octopus_case_optimal_parameters_20260413.md

### 3.1 Hydrogen 收敛轨迹

- 早期多轮为 FAIL（相对误差高于 3%）。
- 已出现 PASS 组合:
  - spacing = 0.36
  - radius = 7.0
  - max_scf_iterations = 260
  - scf_tolerance = 1e-6
  - computed = -0.48519720 Ha
  - relative_delta = 0.029606
  - verdict = PASS

说明:
- 三步法中还存在 backend/frontend 一致性不足样本，这些失败记录被保留用于稳定性回归。

### 3.2 CH4 收敛轨迹

- 前端等效复现存在历史 FAIL（例如尾段 0.101233 eV）。
- 也已出现 PASS 记录（0.16A 窗口尾段带宽 <= 0.1 eV）:
  - Tail band from 0.16A = 0.069876 eV
  - Official criterion = PASS

说明:
- CH4 个别采样点出现 timeout/error，属于运行稳定性问题，不影响已有 PASS 参数组合作为当前最优参考。

### 3.3 N atom 与其它案例

- N atom 官方口径总能量/误差曲线复现实验在收敛日志中已有 PASS 记录。
- H2O 相关条目同时存在 FAIL 与 PASS 历史轮次，说明该链路已可执行，但受运行态与参数/资源策略影响。

### 3.4 当前推荐的参数策略（执行层）

- 先采用“已验证 PASS 的历史参数组”进行复跑确认。
- 若出现 timeout/error，先修复服务链路再重试，不立即改物理参数。
- 保留失败样本，避免只保留成功样本导致信息偏置。

---

## 4. 知识库构建（KB）体系与操作

### 4.1 KB 目录结构

- knowledge_base/corpus: 核心文档语料
- knowledge_base/metadata: 来源索引、网页锚点、抓取状态
- knowledge_base/chunks: 分块中间产物
- knowledge_base/vector_store: 向量库落地
- knowledge_base/quarantine: 隔离来源
- knowledge_base/reference_data: 基准/对照数据

### 4.2 关键清单文件

- knowledge_base/corpus_manifest.json
- knowledge_base/corpus_manifest_authoritative.json
- knowledge_base/benchmark_cases.json
- knowledge_base/case_validation_manifest.json
- knowledge_base/metadata/authoritative_web_sources.json

### 4.3 构建与修复脚本

- scripts/build_research_kb.py
- scripts/run_vector_kb_ops.py
- scripts/run_kb_reliable_autopilot.py
- scripts/rebuild_octopus_tutorial16_kb.py
- scripts/build_tutorial16_capability_matrix.py
- scripts/export_web_evidence_to_kb.py

### 4.4 推荐构建顺序

1. 读取 authoritative 源清单
2. 抓取并分块
3. 写入向量库
4. 回写 ingestion 日志
5. 生成/更新能力矩阵与可追溯报告
6. 刷新同步状态文件

### 4.5 KB 质量门控

- 来源可追溯（URL + 锚点）
- 案例参数可复现（输入口径完整）
- 与参数收敛日志互相引用
- 对失败案例保留因果链，不做静默覆盖

---

## 5. Dirac 工作区架构（当前快照）

### 5.1 顶层关键目录

- scripts: 自动化、编排、收敛、清理、巡检脚本
- docs: 运维手册、流程文档、收敛报告
- docs/harness_reports: 当前保留的参数报告与收敛汇总
- knowledge_base: 语料、元数据、向量库、案例清单
- orchestration: 调度策略、执行状态机、技能契约
- state: 队列、桥接、全局同步、监控状态
- frontend/src: 前端主流程与结果面板
- backend_engine: 后端 Harness/RAG 服务实现

### 5.2 当前关键文件角色映射

- 分发与路由: scripts/dispatch_dirac_task.py
- 队列执行: scripts/dirac_exec_worker.py
- 多代理编排: scripts/run_multi_agent_orchestration.py
- 重规划执行: scripts/execute_replan_packet.py
- DFT/TDDFT 套件: scripts/run_dft_tddft_agent_suite.py
- CH4 前端复现: scripts/replay_ch4_frontend_convergence.py
- Hydrogen 三步法: scripts/validate_hydrogen_three_step.py
- 报告清理: scripts/cleanup_harness_reports.py

### 5.3 状态文件职责

- state/dirac_solver_progress_sync.json:
  - 全局阶段、last_task、workflow、next_action 真值
- state/dirac_exec_queue.json:
  - 队列任务与消费状态
- state/copilot_openclaw_bridge.json:
  - 执行总线桥接状态，供外层可视化读取

---

## 6. 已完成任务清单（归并）

### 6.1 自动化主链路方面

- 已实现 dispatcher -> queue -> worker -> reviewer -> sync 的端到端闭环。
- 已引入 replan/escalation 数据包机制。
- 已固化执行状态字段并增强对齐检查（含一致性 token 相关防误判逻辑）。

### 6.2 稳定性与可见性方面

- 已建立 5173 与 Feishu 信号监控脚本。
- 已建立 route-aware 与 fallback-aware 的运行策略（8001/8101）。
- 已形成 stale 进度与桥接错配的诊断经验并写入运行记忆。

### 6.3 参数收敛方面

- CH4: 已有 FAIL 与 PASS 证据并存，形成可追溯演化轨迹。
- Hydrogen: 已得到 PASS 参数组合并在日志留痕。
- 保持失败样本可查，支持后续自动修复与复验。

### 6.4 知识库方面

- 已形成 authoritative 来源、语料分层、抓取元数据、案例验证清单的基本闭环。
- 已具备 KB 构建、增量更新、可靠自动驾驶脚本。

### 6.5 文档与治理方面

- 操作指南、服务清单、运行模型文档已形成体系。
- 中间报告已按“保留参数收敛主报告”原则清理。

---

## 7. 操作指南（最新推荐）

### 7.1 日常启动（远端优先）

~~~bash
# 1) 远端引导（无交互）
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell

# 2) 必要时手工启动全套
ssh dirac-key "cd /data/home/zju321/.openclaw/workspace/projects/Dirac && nohup bash start_all.sh > logs/start_all_manual.log 2>&1 < /dev/null &"
~~~

### 7.2 预检

~~~bash
ssh dirac-key "(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | grep -E ':(3001|5173|8000|8001|8101)\\b'"
curl -s http://127.0.0.1:3001/api/automation/dispatch/latest
curl -s http://127.0.0.1:8001/harness/case_registry
~~~

### 7.3 自动分发执行

~~~bash
python scripts/dispatch_dirac_task.py --task "Dirac_solver 调试 run_id=<ts>" --source cli-smoke --execute --exec-timeout-seconds 240 --auto-execute-replan --sync-state state/dirac_solver_progress_sync.json
~~~

### 7.4 参数收敛复跑

~~~bash
python scripts/replay_ch4_frontend_convergence.py --api-base http://10.72.212.33:3001 --request-timeout 360
python scripts/validate_hydrogen_three_step.py --api-base http://10.72.212.33:3001 --timeout 240
~~~

### 7.5 报告治理

~~~bash
python scripts/cleanup_harness_reports.py
~~~

### 7.6 故障优先排查顺序

1. SSH/tunnel 是否抖动
2. 3001/8000/8001 是否都在正确进程上
3. 8000 是否为 Octopus MCP（非误占进程）
4. state 三件套是否一致
5. 再看参数与物理口径

---

## 8. 记忆文档归档（已融合要点）

### 8.1 Repo 记忆主轴（已吸收）

- 自动分发与重规划交接经验
- 执行门控与 preflight 诊断结论
- 前端稳定性与流式超时守卫
- 多代理关键节点与技能/插件门控
- OpenClaw 运行期可靠性、远端优先与状态一致性策略

### 8.2 长期规则归并（执行层）

- 远端优先，不把本地临时运行当生产事实
- 服务先健康、再谈参数
- 成功声明必须有状态文件与报告证据
- 收敛日志必须持续追加，不能只靠终端输出
- 大改后必须同步 state 与文档，避免 Copilot/OpenClaw 漂移

### 8.3 当前记忆驱动的关键动作

- 遇到连接抖动时优先保持执行总线而非反复重置业务参数
- 对 8001/8101 路由实行显式可达探测
- 对 Feishu 侧异常优先排除 provider/网关问题，不误判为业务失败

---

## 9. 当前未闭环项与下一步建议

### 9.1 未闭环项

- CH4 与 Hydrogen 仍存在“可成功但不稳定”的运行态（超时/偶发失败样本仍有）。
- 最新 state 仍显示历史 REPLAN 中任务，需要一次新的完整成功链路刷新真值。

### 9.2 建议下一步（按优先级）

1. 先做服务层稳定化复跑（固定 8000 正确进程 + 8001/8101 路由探测）
2. 再做 CH4/Hydrogen 各 3 轮重复验证（统计波动方差）
3. 将最终稳定参数组写入 case_validation_manifest 与文档主结论
4. 保留失败样本并标注可恢复策略，避免“假稳定”

---

## 10. 速查索引

### 10.1 首先看的文件

- docs/harness_reports/parameter_convergence_log.md
- docs/harness_reports/octopus_case_optimal_parameters_20260413.md
- state/dirac_solver_progress_sync.json
- state/dirac_exec_queue.json
- state/copilot_openclaw_bridge.json

### 10.2 首先跑的命令

~~~bash
powershell -ExecutionPolicy Bypass -File scripts/dc.ps1 -NoShell
python scripts/run_dispatch_smoke_batch.py --runs 3 --exec-timeout-seconds 240 --sync-state state/dirac_solver_progress_sync.json
~~~

---

本文件定位为 Dirac 当前阶段的总说明主文档。后续每次自动化链路、收敛参数、KB 构建策略发生实质变更，都应同步更新本文件与 state 真值文件。