# OpenClaw Orchestration Flow

## Pipeline

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

## Keyword Routing

| Trigger | Route | Role |
|---------|-------|------|
| `n_atom_gs_official`, `ch4_gs` | `dirac_standard_case_orchestration` | supervisor |
| `/auto`, `自动调试` | `auto_default_orchestration` | — |
| `refactor`, `fix bug` | `code_implementation` | copilot-executor |
| `review`, `质量门禁` | `quality_review` | reviewer |

## Knowledge Base

```
knowledge_base/
├── corpus_new/          # 参考值文档（人工编写，核心真值）
├── corpus_mp/           # Materials Project 自动抓取（H2O/Si/CH4/H2）
├── vector_store/        # ChromaDB 持久化（5 collection UUID）+ chroma.sqlite3
├── metadata/            # PDF 源索引 + 摄入日志
└── corpus_manifest.json
```

**KB RAG** (`backend_engine/kb_rag.py`): ChromaDB 默认嵌入，`/kb/query` 支持 top_k + topic_tag 过滤。
