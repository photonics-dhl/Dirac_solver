# Dirac + Octopus HPC 全链路运行说明（中文）

## 1) 你这次报错是什么意思

你截图里执行的是：

- `qsub -I workq -l select=1:ncpus=64:mpiprecs=64`

报错原因有两个：

1. `workq` 前面少了 `-q`，应写成 `-q workq`。
2. `mpiprocs` 拼写写成了 `mpiprecs`。

所以 `qsub` 只打印了帮助信息，没有真正分配计算节点。

正确命令：

- 交互作业：
  - `qsub -I -q workq -l select=1:ncpus=64:mpiprocs=64`
- 批处理作业：
  - `qsub -q workq -l select=1:ncpus=64:mpiprocs=64 your_job.pbs`

---

## 2) 从连接到回传前端的全链路（命令 + 解释）

## 阶段 A：连接服务器

1. 连接：
   - `ssh dirac-key`
2. 确认你当前在哪台机器：
   - `hostname`

说明：
- 登录后通常在登录节点（如 `mu02`），不是计算节点。

---

## 阶段 B：申请/进入计算资源

有两种方式：

### 方式 1：交互调试（推荐用于排障）

1. 申请交互节点：
   - `qsub -I -q workq -l select=1:ncpus=64:mpiprocs=64`
2. 验证是否进入作业环境：
   - `echo $PBS_JOBID`
   - `hostname`
   - `cat $PBS_NODEFILE | sort -u`

说明：
- `PBS_JOBID` 非空，且 `hostname` 不再是登录节点时，说明你已在计算作业环境中。

### 方式 2：直接批处理（生产推荐）

1. 准备 `job.pbs`。
2. 提交：
   - `qsub -q workq -l select=1:ncpus=64:mpiprocs=64 job.pbs`
3. 查看状态：
   - `qstat -an`

---

## 阶段 C：启动后端服务（Dirac）

在项目目录：

1. 切目录：
   - `cd /data/home/zju321/.openclaw/workspace/projects/Dirac`
2. 启动服务：
   - `./start_all.sh`
3. 检查端口：
   - `ss -ltnp | grep -E ':3001|:5173|:8000'`

说明：
- `3001`：Node API
- `5173`：前端
- `8000`：Octopus MCP

---

## 阶段 D：前端发起计算（自动链路）

前端点击计算后，链路是：

1. 前端调用 `POST/GET` 流接口：
   - `GET /api/physics/stream`（SSE）
2. Node 后端进入物理流程：
   - 文件：`src/physics_engine.ts`
3. 生成 Octopus 输入文件：
   - 脚本：`@Octopus_docs/octopus_input_generator.py`
   - 产物：`@Octopus_docs/generated_inputs/inp`
4. 调 MCP 执行计算：
   - MCP：`docker/workspace/server.py`
5. MCP 生成并提交 PBS 作业：
   - 产物目录：`@Octopus_docs/output/runs/octopus_xxxxxxxx/`
   - 关键文件：
     - `octopus_job.pbs`
     - `octopus.stdout`
     - `octopus.stderr`
     - `octopus.exitcode`
6. 计算完成后解析结果并回传 Node API。
7. Node API 通过 SSE 把结果推回前端。

---

## 阶段 E：结果可视化回传前端（VisIt 或 Matplotlib）

接口：

- `POST /api/physics/visualize`

逻辑：

1. 3D 密度优先用 VisIt。
2. VisIt 失败则自动回退 Matplotlib。
3. 返回 `pngBase64` 给前端显示。

实现位置：

- 路由：`src/server.ts`
- VisIt 支持：`src/visit_renderer.ts`
- Matplotlib 脚本：`src/render_mpl.py`

---

## 3) conda 需不需要每次都做？

结论：

- **不需要每次请求都 `conda activate`。**
- 只需要在“启动 Python 服务进程时”确保用正确 Python 环境。

推荐做法（二选一）：

1. 用绝对路径启动 Python（最稳）：
   - `/data/home/zju321/miniconda3/envs/ai_agent/bin/python server.py`
2. 或先激活再启动：
   - `source ~/miniconda3/etc/profile.d/conda.sh`
   - `conda activate ai_agent`
   - `python server.py`

说明：
- 进程启动后，后续请求复用该进程，不需要每次再激活 conda。

---

## 4) 你目标流程与当前系统的对应关系

你的目标是：

- 前端传入参数
- 后端组装 Octopus 输入
- 生成并提交 job 到计算节点
- 计算完成后回传输出文件到服务器
- 再返回前端展示（VisIt/Matplotlib 可选）

当前系统已经基本按此流程实现：

1. 前端 -> `/api/physics/stream`
2. 后端生成输入 -> `@Octopus_docs/generated_inputs/inp`
3. MCP 生成 PBS 作业并提交 -> `@Octopus_docs/output/runs/octopus_*/octopus_job.pbs`
4. 结果落盘并解析 -> `@Octopus_docs/output/...`
5. 前端可视化调用 -> `/api/physics/visualize`
6. 3D 优先 VisIt，失败回退 Matplotlib。

---

## 5) 常用排障命令（建议收藏）

1. 查看作业：
   - `qstat -an`
2. 查看最新运行目录：
   - `ls -1dt @Octopus_docs/output/runs/octopus_* | head -n 1`
3. 看 PBS 脚本是否 64 核：
   - `sed -n '1,30p' @Octopus_docs/output/runs/<run_id>/octopus_job.pbs`
4. 看并行是否生效：
   - `grep -n 'Parallelization\|Number of processes\|serial\|parallel' @Octopus_docs/output/runs/<run_id>/octopus.stdout`
5. 看 API 日志：
   - `tail -n 200 logs/node_api.log`

---

## 6) 为什么 `pestat` 会报错 `command not found`

这是因为你所在环境没有安装 `pestat`（或不在 PATH），不是你命令写错。

可以直接用 PBS 自带命令替代：

- 查看节点整体：
   - `pbsnodes -a`
- 查看某个节点：
   - `pbsnodes cn01`
- 查看队列作业：
   - `qstat -an`

说明：
- 不同集群教程里会出现 `pestat`，但它通常是集群管理员额外安装的小工具，不是 PBS 标配。

---

## 7) 已支持“提交前查空闲节点”

后端已加入预检逻辑：提交 `qsub` 前先查空闲节点，如果当前没有满足核数的空闲节点，则快速返回，不盲等排队。

相关环境变量：

- `OCTOPUS_PBS_PRECHECK_FREE=true`
   - 启用空闲节点预检（默认开启）
- `OCTOPUS_PBS_BIND_FREE_NODE=true`
   - 是否把任务绑定到检测到的某个空闲节点（建议开启）
- `OCTOPUS_FP_HTTP_TIMEOUT_SECONDS=180`
   - 调试阶段 Octopus 首性原理流程的 HTTP 超时（秒）。默认 180 秒，避免单次调试等待过久。
- `OCTOPUS_FAST_SOLVE_TIMEOUT_MS=120000`
   - fastPath 模式下 `/api/physics/run` 到 Octopus MCP 的超时（毫秒），默认 120 秒，让后端先于外层脚本超时返回结构化结果。
- `OCTOPUS_FAST_MAX_SCF_ITERATIONS=80`
   - fastPath 模式下 SCF 最大迭代数上限，默认 80，避免调试阶段长时间 SCF 死磕。
- `OCTOPUS_FAST_HPC_TIMEOUT_SECONDS=150`
   - fastPath 下 HPC 求解总超时（秒），默认 150 秒，避免长时间卡住。
- `OCTOPUS_FAST_PBS_NCPUS=8`
- `OCTOPUS_FAST_PBS_MPIPROCS=8`
   - fastPath 下默认使用较小并行规模，降低排队概率。
- `OCTOPUS_PBS_CMD_TIMEOUT_SECONDS=20`
   - 对 `qsub/qstat` 子命令通信增加超时保护，防止调度命令卡死导致 API 永久挂起。
- `OCTOPUS_FAST_DIRECT_TIMEOUT_SECONDS=180`
   - fastPath 下若 HPC 调度失败，自动回退 direct 执行的超时上限（秒），用于保障手动调试链路可返回结果。

建议：

- 推荐保持 `PRECHECK_FREE=true`、`BIND_FREE_NODE=true`。
- 若集群策略不允许 vnode 绑定，再改回 `BIND_FREE_NODE=false`。
- 若仅做调试排障，建议 `OCTOPUS_FP_HTTP_TIMEOUT_SECONDS=180~300`；生产长任务可再调大。
- 若仍超时，可先降 `OCTOPUS_FAST_MAX_SCF_ITERATIONS=40~60` 做“是否可收敛”快速判定，再逐步放宽。
- 若出现“求解进程已完成但调用仍超时”，优先检查是否命中 `qstat` 卡死；当前版本已加 `OCTOPUS_PBS_CMD_TIMEOUT_SECONDS` 保护并在 fastPath 返回轻量结果。

---

## 8) 本次你遇到问题的一句话结论

你并不是“进不了计算节点”，而是 `qsub` 命令参数写错导致任务没提交成功；修正命令后即可正常申请计算资源并使用 64 核。

---

## 9) 中间运行文件清理策略（已支持）

后端已加入 runs 目录自动清理（仅清理旧目录，不清理当前正在运行目录）。

默认策略：

- 保留最近 `20` 次运行目录。
- 同时删除超过 `168` 小时（7天）的旧目录。
- 默认保留失败任务目录（`octopus.exitcode != 0`）用于排障。

可用环境变量：

- `OCTOPUS_RUN_CLEANUP_ENABLED=true|false`
- `OCTOPUS_RUN_RETENTION_COUNT=20`
- `OCTOPUS_RUN_MAX_AGE_HOURS=168`
- `OCTOPUS_RUN_KEEP_FAILED=true|false`

建议：

- 生产环境：`RETENTION_COUNT=20~50`，`MAX_AGE_HOURS=72~168`。
- 如果磁盘非常紧张，可先把 `MAX_AGE_HOURS` 调到 `48`。

---

## 10) 为什么 pbs.out 为空但 octopus.stdout 有内容

这是正常现象（在当前 job 脚本里）。

因为脚本把程序输出重定向到了：

- 标准输出：`octopus.stdout`
- 标准错误：`octopus.stderr`

PBS 的 `-o pbs.out` / `-e pbs.err` 主要记录脚本层输出；如果脚本本身没有额外 `echo`，`pbs.out` 可能为空。

---

## 11) 本次卡点定位与已实施修复（2026-04-01）

### 现象

- 多 agent 合同检查通过，但 reviewer 长期卡在 `octopus_ok=false`。
- 失败信息先后出现：
   - `Request timeout after 600000ms`
   - 以及修复后调试回归中的 `failure_reason=timed out`（更快返回）。

### 根因结论

- 主要不是权限或路由问题，而是 **Octopus 首性原理路径耗时过长**。
- 运行日志显示请求已进入 MCP `solve_handler` 并开始真实求解；并非前置接口直接失败。
- 集群存在较多运行中任务时，排队/运行时延更容易触发上层超时。

---

## 12) 经典 DFT RAG 知识库构建（已接入当前框架）

### 已新增语料（面向自动开发）

- `knowledge_base/corpus/dft_classic_cases_octopus.md`
   - 经典 DFT/TDDFT 案例族、验收标准、失败特征和修复动作。
- `knowledge_base/corpus/octopus_capability_maximization.md`
   - Octopus 能力覆盖矩阵、模式压榨策略（`gs/td/unocc/opt/em/vib`）、自动化检索提示。

Manifest 已升级为 `2026-04-02` 并纳入上述新语料。

### 构建命令

建议在远端项目根目录执行：

- `python3 scripts/build_research_kb.py --base-url http://127.0.0.1:8011 --manifest knowledge_base/corpus_manifest.json`

说明：

- 脚本端点回退已补齐，包含 `8011/8001/8101` 与 `ingest_markdown` 的连字符/下划线变体，提升异构环境成功率。

### 验证命令

- `python3 -c "import json,urllib.request;req=urllib.request.Request('http://127.0.0.1:8101/kb/query',data=json.dumps({'query':'Recommend classic DFT/TDDFT benchmark sequence for Octopus capability coverage','top_k':5}).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json'});print(json.loads(urllib.request.urlopen(req,timeout=20).read().decode()).get('hits',[])[0]['source'])"`

### 本次构建结果（可复核）

- 报告：`docs/harness_reports/kb_ingestion_report_20260401T163124Z.json`
- 指标：
   - `total_sources=12`
   - `ingested_sources=9`
   - `failed_sources=0`
   - `total_chunks_added=44`

### 已修复项（代码默认行为）

1. 启用“空闲节点预检 + 绑定”默认策略，降低挑到 busy 节点概率。
    - `OCTOPUS_PBS_PRECHECK_FREE=true`
    - `OCTOPUS_PBS_BIND_FREE_NODE=true`
2. fastPath 调试请求默认跳过 run explanation，减少非必要等待。
3. 首性原理调试脚本超时改为可配置，并默认较短：
    - `OCTOPUS_FP_HTTP_TIMEOUT_SECONDS=300`

### 调试建议（快失败）

- 调试阶段：`OCTOPUS_FP_HTTP_TIMEOUT_SECONDS=180~300`。
- 生产阶段：按任务规模再放宽（例如 600~1200）。
- 若频繁超时，优先排查：
   - 队列负载（`qstat -x`）
   - 实际绑定节点是否空闲（`pbsnodes -a`）
   - 本次 run 的 `octopus.stdout/stderr` 是否显示 SCF 长时间未收敛。

---

## 13) RAG 第二轮增强：官网能力边界 + reviewer UI 审查知识（2026-04-01）

### 新增语料

- `knowledge_base/corpus/octopus_official_capability_matrix_v16.md`
   - 基于 Octopus 16 Manual/Variables 的能力矩阵。
   - 包含能力域到可执行 case 路径映射，以及 reviewer 反幻觉约束。
- `knowledge_base/corpus/reviewer_ui_design_gate_knowledge.md`
   - reviewer 的 UI 质量门禁知识（信息架构、可访问性、响应式、审美一致性、证据合同）。

Manifest 已升级为 `2026-04-03`，总源数从 12 扩展到 14。

### 构建结果（可复核）

- 报告：`docs/harness_reports/kb_ingestion_report_20260401T170512Z.json`
- 指标：
   - `total_sources=14`
   - `ingested_sources=11`
   - `failed_sources=0`
   - `total_chunks_added=0`（增量构建去重场景下为正常现象）

### 检索冒烟（建议）

- 能力边界验证：
   - `python3 -c "import json,urllib.request;u='http://127.0.0.1:8101/kb/query';q='scope_alignment_ok mode_mapping_ok evidence_type_ok';req=urllib.request.Request(u,data=json.dumps({'query':q,'top_k':5}).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json'});print([h.get('source') for h in json.loads(urllib.request.urlopen(req,timeout=20).read().decode()).get('hits',[])])"`
- UI reviewer 验证：
   - `python3 -c "import json,urllib.request;u='http://127.0.0.1:8101/kb/query';q='ui_visual_quality_ok ui_accessibility_ok ui_responsive_ok';req=urllib.request.Request(u,data=json.dumps({'query':q,'top_k':5}).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json'});print([h.get('source') for h in json.loads(urllib.request.urlopen(req,timeout=20).read().decode()).get('hits',[])])"`

预期：hits 内应包含 `octopus_official_capability_matrix_v16` 或 `reviewer_ui_design_gate_knowledge`。
