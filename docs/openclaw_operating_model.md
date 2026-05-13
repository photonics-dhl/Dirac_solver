# OpenClaw 操作系统手册

> Dirac 自动化框架的角色边界、触发协议、故障排查和状态真值定义。

---

## 1. 角色与职责边界

| 角色 | 职责 | 产出 |
|------|------|------|
| **openclaw-planner** | 规划、分解、任务策略 | 任务计划、约束、验收标准、迭代预算 |
| **openclaw-executor** | 重复执行循环：服务引导、编排运行、制品生成、状态同步 | 执行日志、状态同步 |
| **openclaw-reviewer** | 阻塞式审查门禁，判定通过/失败 | 审查报告 |
| **copilot-executor** | 自身实现和验证执行循环 | 可审计的代码变更、测试证据 |

> 重要：reviewer 是阻塞门禁——所有检查项通过才能发布。

---

## 2. 触发源与执行总线

### 2.1 触发方式

| 触发源 | 命令 | 说明 |
|--------|------|------|
| CLI | `python scripts/dispatch_dirac_task.py --task "任务" --source cli --execute` | 本地命令行 |
| Feishu 文本 | 同上，source=`feishu` | 飞书消息入口 |
| Feishu `/auto` | `/auto <自然语言任务>` | 强制路由到 Dirac 执行 |

### 2.2 执行总线（Execution Bus）

飞书触发先进入队列（`state/dirac_exec_queue.json`），而不是一次性的 HTTP 分发：

```
Feishu → queue → dirac_exec_worker.py → dispatch_dirac_task.py --execute --auto-execute-replan
```

队列持久化 worker（`scripts/run_dirac_exec_worker.sh`）由 `start_all.sh` 启动，日志写入 `logs/dirac_exec_worker.log`。

### 2.3 Bot 响应契约（防止错误拒绝）

OpenClaw bot 收到请求后必须按顺序检查，不能直接返回"无权限"：

```
1. POST /api/automation/exec-readiness
2. POST /api/automation/ensure-exec（当 readiness=false 时）
3. POST /api/automation/dispatch
```

---

## 3. 状态真值

成功判定（必须同时满足）：

| 条件 | 文件位置 |
|------|---------|
| `workflow_state = DONE` | `state/dirac_solver_progress_sync.json` |
| `workflow_event = REVIEW_PASS` | 同上 |
| 报告文件存在 | `docs/harness_reports/` |

---

## 4. 故障排查

### 4.1 端口冲突（最常见问题）

端口冲突是连接失败的首要原因。用 PowerShell 管理员清理：

```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 3004).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8001).OwningProcess -Force -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 5173).OwningProcess -ErrorAction SilentlyContinue
```

### 4.2 服务启动顺序

若 `start_all.bat` 失败，按以下顺序在独立终端中手动启动：

```
1. Docker (Octopus Engine):
   docker-compose up -d

2. Local Engine (port 8001):
   python backend_engine/main.py

3. Vite Frontend (port 5173):
   cd frontend && npm run dev

4. Node API Server (port 3004):
   npx ts-node src/server.ts
```

### 4.3 Docker "server.py not found" (Errno 2)

镜像或卷不同步。修复方式：

```bash
# 方式 A：强制重建（推荐）
cd docker
docker-compose build --no-cache
docker-compose up -d

# 方式 B：检查目录结构
# 确保在根目录或 docker/ 子目录下运行
```

---

## 5. 已完成阶段记录

### Phase 1-4：初始实现（2026-04 初）

- [x] Phase 1: 发现现有配置和运行时差距
- [x] Phase 2: 实现审批治理制品和审计脚本
- [x] Phase 3: 实现统一任务分发器/自动流包装
- [x] Phase 4: 更新文档并验证执行路径

### 稳定性验证（2026-04-04）

- [x] 5 次连续 strict dispatcher 回归（5/5 PASS）
- [x] 队列-worker 突发消费验证（5/5 完成）

### 长期稳定性验证（2026-04-04 Extended）

- [x] 20 次 strict soak 批次（20/20 PASS，100%）
- [x] 队列-worker 压力测试通过
- [x] 报告保留清理（保留最近 2 次运行 + 呼吸式触发）

**当前状态：部分功能中断（2026-04-22）**

| 模块 | 状态 | 说明 |
|------|------|------|
| Octopus PP Mode | ✅ 正常 | He 原子语法已修复（H 已验证，He 2026-04-22 实测通过）|
| Worker 队列 | ✅ 运行中 | daemon 在跑（PID 27193），但队列无新任务 |
| Node API | ✅ 运行中 | port 3004 |
| Feishu 通知 | ❌ 残缺 | 仅入口 `notify_received` 触发，中间/结束通知未接入 |
| Dispatcher 编排 | ⚠️ 停滞 | 4月17日后停滞在 `routed_only`，未进入 executing |

---

## 6. 已知问题

| 问题 | 频率 | 处理方式 |
|------|------|---------|
| 8000/8001/8101 端口互占 | 高 | 先查 `ss -lntp` 确认端口进程 |
| Node API 端口漂移 | 中 | 实际端口 3004（3001 已废弃），始终用 `ss -lntp` 确认 |
| Hydrogen 三步法偶尔不一致 | 中 | backend/frontend 参数对齐不足，保留失败样本 |
| Feishu 通知从未成功发送（除 RECEIVED 外）| 中 | `feishu_notify.py` 仅入口调用了 `notify_received`，中间/结束状态未接入 |
| Dispatcher 停滞在 routed_only | 中 | `--execute` 参数链路疑似断裂，4月17日后无完整执行记录 |
| Knowledge Base 未构建完成 | 低 | corpus 无 chunks/vector_store，需重建 |
| He 原子 PP Mode 计算失败 | 低 | `species_pseudo | set` 应改为 `species_pseudo | file`，路径加单引号，扩展名自动检测 |

---

## 7. 相关文档索引

| 文档 | 用途 |
|------|------|
| [octopus_user_guide.md](octopus_user_guide.md) | Octopus 完整使用指南（含并行化）|
| [octopus_knowledge_reference.md](octopus_knowledge_reference.md) | Octopus 语法/解析速查 |
| [development_lessons_20260418.md](development_lessons_20260418.md) | 开发问题记录 |
| [harness_reports/](harness_reports/) | 自动化测试报告目录 |
| `state/dirac_solver_progress_sync.json` | 工作流状态真值 |
| `state/dirac_exec_queue.json` | 执行队列 |
| `state/multi_agent_learning_state.json` | 失败知识库 |
