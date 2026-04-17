# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260404-001] best_practice

**Logged**: 2026-04-04T11:25:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
Strict reviewer stability must be validated with repeated dispatcher runs, not a single PASS.

### Details
A one-shot PASS can hide transient orchestration or endpoint issues. Running consecutive strict dispatch cycles produced stronger evidence of framework health and revealed whether DONE/REVIEW_PASS is consistently reached.

### Suggested Action
Adopt repeated strict runs (>=5) as stabilization baseline before declaring framework healthy.

### Metadata
- Source: conversation
- Related Files: scripts/dispatch_dirac_task.py
- Tags: strict-gate, stabilization, regression

---

## [LRN-20260404-002] best_practice

**Logged**: 2026-04-04T11:25:20Z
**Priority**: medium
**Status**: pending
**Area**: docs

### Summary
Always run aggregate + cleanup after batch verification to keep handoff artifacts truthful and lightweight.

### Details
Large report directories accumulate stale evidence and can mislead future sessions. Aggregating and cleaning with retention keeps only current signals while preserving milestone outputs.

### Suggested Action
After major regression batches, run aggregate report generation and cleanup with explicit retention policy.

### Metadata
- Source: conversation
- Related Files: scripts/aggregate_harness_reports.py, scripts/cleanup_harness_reports.py
- Tags: artifact-hygiene, handoff

---

## [LRN-20260404-003] best_practice

**Logged**: 2026-04-04T11:35:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
Full stabilization acceptance should include both strict soak and queue-worker burst checks.

### Details
Strict dispatcher soak validates planner/executor/reviewer contract stability, while queue burst validates execution bus claim/ACK behavior. Running only one of the two leaves orchestration blind spots.

### Suggested Action
Use a two-part gate: (1) >=20 strict runs with DONE/REVIEW_PASS, (2) burst queue consumption (>=5) with all tasks done and success ACK.

### Metadata
- Source: conversation
- Related Files: scripts/dispatch_dirac_task.py, scripts/dirac_exec_worker.py
- Tags: soak, queue-worker, stabilization-gate

---

## [LRN-20260405-004] best_practice

**Logged**: 2026-04-05T04:50:00Z
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
When simplifying UI flows, remove or explicitly retain dependent symbols; missing render imports can cause full-page white screen.

### Details
After removing duplicated setup controls, `FlaskConical` was deleted from imports but still used in render. The page crashed at runtime with a blank screen even though local static checks initially looked clean.

### Suggested Action
After each frontend refactor, run strict TypeScript check in the actual runtime environment and reload the live page once before declaring completion.

### Metadata
- Source: conversation
- Related Files: frontend/src/App.tsx, logs/vite.log
- Tags: white-screen, runtime-crash, refactor-safety

### Resolution
- **Resolved**: 2026-04-05T04:52:00Z
- **Commit/PR**: workspace-uncommitted
- **Notes**: Restored `FlaskConical` import and removed stale harness-only UI state/effects to keep strict compile and runtime aligned.

---

## [LRN-20260405-005] insight

**Logged**: 2026-04-05T04:53:00Z
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
H2O run latency was amplified by duplicated task selectors that silently triggered multi-task TD workloads.

### Details
`Calculation Mode` and a separate task checklist existed in parallel. Default checklist selection included multiple TD cases, so users expecting a single GS run could unintentionally execute a heavier suite path.

### Suggested Action
Use one source of truth for run intent (`Calculation Mode`) and derive reviewer task IDs from it automatically.

### Metadata
- Source: conversation
- Related Files: frontend/src/App.tsx
- Tags: ux-contract, runtime-cost, reviewer

### Resolution
- **Resolved**: 2026-04-05T04:53:30Z
- **Commit/PR**: workspace-uncommitted
- **Notes**: Replaced manual task checklist with mode-aligned automatic mapping and renamed setup action accordingly.

---

## [LRN-20260405-002] correction

**Logged**: 2026-04-05T19:30:44
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
User-corrected requirement: Feishu-side dynamic status + table sync and persistent convergence log rule must be treated as long-term memory, not session-only.

### Details
Previously remembered execution/sync behavior but did not persist this exact display requirement as explicit hard rule, causing repeated reminders.

### Suggested Action
Always update persistent memory with user-stated workflow locks immediately after confirmation and mirror them in repo runtime notes when implementation changes.

### Metadata
- Source: user_feedback
- Related Files: /memories/connection_notes.md, /memories/repo/openclaw-runtime-notes.md
- Tags: feishu, long-term-memory, convergence-log

---

## [LRN-20260411-001] best_practice

**Logged**: 2026-04-11T15:06:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
When queue state JSON is unstable, prioritize dispatch API + task_dispatch artifacts + Feishu in-page evidence over direct queue parsing.

### Details
Runtime queue file can be temporarily truncated under active writes, causing parse failures and false negatives. In this state, the reliable triad is:
- `/api/automation/dispatch/latest` for live status,
- newest `docs/harness_reports/task_dispatch_*.json` for execution evidence,
- Feishu visible message/thread confirmation for user-facing delivery proof.

### Suggested Action
Standardize incident mode: if queue parse fails, switch status collection pipeline to the triad above and mark queue file as degraded source until restored.

### Metadata
- Source: conversation
- Related Files: state/dirac_exec_queue.json, src/server.ts, docs/harness_reports/task_dispatch_*.json
- Tags: runtime-integrity, evidence-priority, feishu-verification

---

## [LRN-20260413-001] correction

**Logged**: 2026-04-13T12:45:00Z
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
Official total-energy复现中，不应混入S/P轨道误差口径，图表必须只反映总能量。

### Details
用户明确指出官方教程语境是 total energy convergence。此前报告中混入了 s/p 误差列，造成“复现实验指标”与“输出展示口径”不一致。该问题会误导判据解释和图表阅读。

### Suggested Action
将复现脚本、CSV、Markdown、PNG 全部统一为 total-energy-only；后续若需轨道信息，单列到独立分析报告，不混入官方复现主报告。

### Metadata
- Source: user_feedback
- Related Files: scripts/run_octopus_nitrogen_total_energy_convergence.py, docs/harness_reports/octopus_case_optimal_parameters_20260413.md
- Tags: correction, official-reproduction, reporting-consistency

---

## [LRN-20260413-002] correction

**Logged**: 2026-04-13T13:10:00Z
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
官方复现必须按案例区分判据口径，不能把 N atom 和 CH4 统一成同一展示标准。

### Details
用户指出 N atom 官方教程主图是误差曲线（含 total/s/p 误差），而 CH4 官方案例是总能量随 spacing 变化并结合尾段波动判据。将二者一刀切会导致“复现结论与教程语义不一致”。

### Suggested Action
在脚本和前端中显式引入 case-specific report style（N atom error vs CH4 total-energy），并在 UI 暴露可手动复现参数，确保前后端结果可对齐复算。

### Metadata
- Source: user_feedback
- Related Files: scripts/run_octopus_nitrogen_total_energy_convergence.py, frontend/src/App.tsx
- Tags: official-reproduction, case-specific-metrics, ui-parity

---

