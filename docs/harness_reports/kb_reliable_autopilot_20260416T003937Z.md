# KB Reliable Autopilot Report

## Summary

- Generated At: 2026-04-16T00:39:37.013893Z
- Final Status: repairing
- Human Status: AUTO_REPAIRING_ACTIVE
- Attempts: 5
- Success: False
- Manifest: /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/corpus_manifest.json

## Attempt Log

| # | base_url | include_web | force_reingest | repair_action | ok | failed_sources | exit_code | note |
|---|---|---|---|---|---|---|---|---|
| 1 | http://127.0.0.1:8001 | False | False | initial_attempt | False | 10 | 2 | auto_repair_next_attempt |
| 2 | http://127.0.0.1:8001 | False | False | disable_web_ingestion | False | 10 | 2 | auto_repair_next_attempt |
| 3 | http://127.0.0.1:8101 | False | False | switch_harness_endpoint | False | 10 | 2 | auto_repair_next_attempt |
| 4 | http://127.0.0.1:8101 | False | True | force_reingest_on_fallback | False | 10 | 2 | auto_repair_next_attempt |
| 5 | http://127.0.0.1:8001 | False | True | force_reingest_on_primary | False | 10 | 2 | auto_repair_next_attempt |

## Artifact

- JSON: /data/home/zju321/.openclaw/workspace/projects/Dirac/docs/harness_reports/kb_reliable_autopilot_20260416T003937Z.json
