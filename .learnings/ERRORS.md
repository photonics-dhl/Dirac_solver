# Errors

Command failures and integration errors.

---

## [ERR-20260404-001] run_in_terminal_payload

**Logged**: 2026-04-04T11:24:30Z
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
Tool call failed because required `isBackground` field was omitted.

### Error
```
ERROR: Your input to the tool was invalid (must have required property 'isBackground')
```

### Context
- Operation: batch strict regression command execution.
- Cause: `run_in_terminal` payload missing required parameter.

### Suggested Fix
Always include `isBackground` and `timeout` fields for terminal tool invocations.

### Metadata
- Reproducible: yes
- Related Files: N/A

---

## [ERR-20260413-001] official_gs_route_unreachable

**Logged**: 2026-04-13T13:20:00Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Direct route validation for `/api/agents/run-official-gs-convergence` failed because active backend endpoint was unavailable.

### Error
```
Cannot POST /api/agents/run-official-gs-convergence
由于目标计算机积极拒绝，无法连接。
```

### Context
- Operation: validating UI-equivalent POST request after adding case-specific GS settings.
- Attempted endpoints: `http://127.0.0.1:3001` (route missing), `http://127.0.0.1:3011` (connection refused).

### Suggested Fix
Ensure the updated backend server is running and reachable on the same API base used by frontend (`VITE_API_BASE`) before end-to-end UI verification.

### Metadata
- Reproducible: yes
- Related Files: src/server.ts, frontend/src/App.tsx

---

## [ERR-20260404-002] soak_summary_key_mismatch

**Logged**: 2026-04-04T11:32:00Z
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
Soak summary parser looked for `status=` while dispatcher emits `dispatch_status=`.

### Error
```
strict_pass=0 despite all runs reporting DONE/REVIEW_PASS and exit_code=0
```

### Context
- Operation: 20-run strict soak aggregation.
- Cause: key mismatch in ad-hoc parser logic.

### Suggested Fix
Prefer parsing `dispatch_status` from dispatcher output and treat workflow tuple (`DONE`, `REVIEW_PASS`) + exit_code as canonical pass criteria.

### Metadata
- Reproducible: yes
- Related Files: docs/harness_reports/soak_batch_20_strict_latest.json

---

## [ERR-20260405-001] search_subagent_context_overflow

**Logged**: 2026-04-05T00:00:00Z
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
`search_subagent` failed because the details payload exceeded model context limits.

### Error
```
failed: Request Failed: 400 {"error":{"message":"Your input exceeds the context window of this model. Please adjust your input and try again.","code":"invalid_request_body"}}
```

### Context
- Operation: single-shot code path mapping for frontend/backend/reviewer files.
- Cause: query+details text too verbose for the subagent model budget.

---

## [ERR-20260407-001] dispatch_indentation_after_contract_patch

**Logged**: 2026-04-07T09:17:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Dispatcher contract patch introduced an indentation error in the receipt/print block.

### Error
```
IndentationError: unexpected indent (scripts/dispatch_dirac_task.py)
```

### Context
- Operation: adding plugin gate, skills snapshot, and loop consistency fields.
- Cause: new `receipt` keys and `loop_contract` print block were over-indented.

### Suggested Fix
Align inserted dictionary keys and trailing print block with the existing function indentation before re-running syntax validation.

### Metadata
- Reproducible: yes
- Related Files: scripts/dispatch_dirac_task.py

### Resolution
- **Resolved**: 2026-04-07T09:18:00Z
- **Commit/PR**: local-working-tree
- **Notes**: Fixed indentation and validated with py_compile + editor diagnostics.

### Suggested Fix
Use concise subagent prompts (short query + one-sentence objective), or switch to direct local search when the workspace is known.

### Metadata
- Reproducible: yes
- Related Files: N/A

---

## [ERR-20260405-002] frontend_white_screen_missing_symbol

**Logged**: 2026-04-05T04:51:00Z
**Priority**: high
**Status**: resolved
**Area**: frontend

### Summary
UI rendered a white screen because a JSX icon symbol remained in render after its import was removed.

### Error
```
Blank page in browser; runtime render path referenced `FlaskConical` without import after setup-panel refactor.
```

### Context
- Operation: remove duplicated setup controls and harness entry points.
- Trigger: refactor removed `FlaskConical` from import list but left two JSX usages.
- Evidence: strict TS check reported `Cannot find name 'FlaskConical'`; browser snapshot showed full-page white screen.

### Suggested Fix
Restore required imports (or remove stale JSX usages) and enforce post-refactor remote `tsc --noEmit` + page reload check.

### Metadata
- Reproducible: yes
- Related Files: frontend/src/App.tsx, logs/vite.log

### Resolution
- **Resolved**: 2026-04-05T04:52:00Z
- **Commit/PR**: workspace-uncommitted
- **Notes**: Restored icon import and cleaned unused harness scaffolding left after UI simplification.

---

## [ERR-20260405-001] wrong_working_directory_python_run

**Logged**: 2026-04-05T17:54:24
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Python suite command failed because terminal CWD drifted to Z:\ root.

### Error
`	ext
D:/Softwares_new/Python/python.exe: can't open file 'Z:\\scripts\\run_dft_tddft_agent_suite.py': [Errno 2] No such file or directory
` 

### Context
- Command attempted from wrong CWD after long-running searches
- Expected CWD: Z:\.openclaw\workspace\projects\Dirac

### Suggested Fix
Always run Set-Location to project root before Python suite invocation.

### Metadata
- Reproducible: yes
- Related Files: scripts/run_dft_tddft_agent_suite.py

---

## [ERR-20260406-001] aps_pdf_download_timeout

**Logged**: 2026-04-06T00:00:00Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Primary APS PDF links for classic DFT/TDDFT papers timed out while arXiv PDFs succeeded in the same run.

### Error
```
connection attempt failed: journals.aps.org:443 timeout/no response
```

### Context
- Operation: primary literature PDF acquisition for KB expansion.
- Successful controls in same batch: arXiv PDF downloads.
- Failed targets: APS PhysRev and PhysRevLett PDF endpoints.

### Suggested Fix
Keep DOI/URL metadata in KB, use arXiv/open mirrors when available, and retry APS with proxy/network path verification.

### Metadata
- Reproducible: unknown
- Related Files: knowledge_base/metadata/pdf_download_status.json, scripts/download_kb_primary_pdfs.ps1

---

## [ERR-20260411-001] queue_state_json_truncated

**Logged**: 2026-04-11T15:05:00Z
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
`state/dirac_exec_queue.json` (and `.bak`) became non-parseable during active execution, breaking JSON-based status extraction.

### Error
```
ConvertFrom-Json: Unexpected end when deserializing object
```

### Context
- Operation: correlate Feishu token with latest queue task.
- Symptom: file tail ends mid-object while worker is active.
- Impact: queue-based parsing unreliable for real-time status checks.

### Suggested Fix
Adopt atomic write for queue snapshots (write temp + rename), and during runtime use `/api/automation/dispatch/latest` plus task_dispatch reports as primary truth.

### Metadata
- Reproducible: intermittent
- Related Files: state/dirac_exec_queue.json, state/dirac_exec_queue.json.bak, scripts/dirac_exec_worker.py

---

## [ERR-20260412-001] missing-rg-on-pwsh

**Logged**: 2026-04-12T00:00:00Z
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
Attempted to use rg in pwsh but ripgrep is not installed in this shell environment.

### Error

g: The term 'rg' is not recognized as a name of a cmdlet, function, script file, or executable program.

### Context
- Command attempted: rg pattern search across implementation files
- Environment: PowerShell in mounted remote workspace

### Suggested Fix
Use workspace grep_search tool or PowerShell Select-String fallback when rg is unavailable.

### Metadata
- Reproducible: yes
- Related Files: frontend/src/App.tsx, src/server.ts, docker/workspace/server.py, scripts/run_dft_tddft_agent_suite.py

---

## [ERR-20260413-001] run_in_terminal_parallel_session_closed

**Logged**: 2026-04-13T00:00:00Z
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
Parallel `run_in_terminal` calls failed with "The terminal was closed" while attempting concurrent endpoint checks.

### Error
```
ERROR while calling tool: The terminal was closed
```

### Context
- Operation: parallel black-box API validation on harness endpoints.
- Commands: three concurrent `Invoke-RestMethod` calls.
- Outcome: all three calls aborted before execution due to terminal session closure.

### Suggested Fix
Use sequential `run_in_terminal` calls for terminal-backed validation steps, or use non-terminal tools where possible.

### Metadata
- Reproducible: unknown
- Related Files: N/A

---

