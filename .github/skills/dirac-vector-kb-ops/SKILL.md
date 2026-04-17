---
name: dirac-vector-kb-ops
description: Use when the user asks to build, refresh, validate, or inspect the Dirac DFT/TDDFT vector knowledge base, including ingestion status and retrieval quality.
---

# Dirac Vector KB Ops Skill

## Use When
- User asks to "supplement vector KB", "refresh KB", or "check KB sync".
- Need deterministic proof that KB ingestion happened and sync state was updated.
- Need a quick retrieval probe after ingestion.

## Primary Tool
- `scripts/run_vector_kb_ops.py`

## Typical Commands
```bash
# Full workflow: ingest + query probe + sync snapshot
python scripts/run_vector_kb_ops.py --mode full --base-url http://127.0.0.1:8001

# Force reingest and include web references from manifest
python scripts/run_vector_kb_ops.py --mode ingest --force-reingest --include-web

# Query-only probe
python scripts/run_vector_kb_ops.py --mode query --query "Octopus TDDFT convergence" --top-k 5

# Status-only snapshot from sync file
python scripts/run_vector_kb_ops.py --mode status
```

## Required Outputs
- Ingestion command exit code.
- Ingestion report path from `kb_sync.report_json` / `kb_sync.report_md`.
- Query endpoint used and `hits_count`.
- Sync snapshot fields: `total_sources`, `ingested_sources`, `total_chunks_added`.

## Rules
1. Always return structured evidence from tool output before narrative summary.
2. If ingestion fails, report stderr and stop claiming KB is updated.
3. For incremental no-change runs, explicitly report `unchanged_sources`.
4. If retrieval hits are empty, suggest concrete source/topic gaps.
