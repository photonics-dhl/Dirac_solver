# Research KB Build Report

## Summary

- Generated At: 2026-04-15T16:25:33.127667Z
- Manifest: knowledge_base/corpus_manifest.json
- Total Sources: 4
- Ingested Sources: 4
- Skipped Sources: 0
- Failed Sources: 0
- Total Chunks Added: 160
- Local Chunk Evidence Count: 111
- Local Chunks Dir: /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/chunks

## Details

| Source ID | Type | Status | Chunks Added | Local Chunks | Local Chunk File | Note |
|---|---|---|---|---|---|---|
| h2o_gs_reference_provenance | local_markdown | ingested | 2 | 2 | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/chunks/h2o_gs_reference_provenance__f9573d8a0f06.jsonl | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/corpus/h2o_gs_reference_provenance.md via http://127.0.0.1:8101/kb/ingest_markdown |
| dft_tddft_authoritative_reference_cases_2026_04 | local_markdown | ingested | 7 | 3 | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/chunks/dft_tddft_authoritative_reference_cases_2026_04__e2b6c2563d13.jsonl | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/corpus/dft_tddft_authoritative_reference_cases_2026_04.md via http://127.0.0.1:8101/kb/ingest_markdown |
| octopus_tutorial16_capability_matrix_2026_04 | local_markdown | ingested | 13 | 4 | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/chunks/octopus_tutorial16_capability_matrix_2026_04__60533613b500.jsonl | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/corpus/octopus_tutorial16_capability_matrix_2026_04.md via http://127.0.0.1:8101/kb/ingest_markdown |
| octopus_tutorial16_official_catalog_2026_04 | local_markdown | ingested | 138 | 102 | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/chunks/octopus_tutorial16_official_catalog_2026_04__6b2f37ba64ad.jsonl | /data/home/zju321/.openclaw/workspace/projects/Dirac/knowledge_base/corpus/octopus_tutorial16_official_catalog_2026_04.md via http://127.0.0.1:8101/kb/ingest_markdown |

## Artifact

- JSON: docs/harness_reports/kb_ingestion_report_20260415T162533Z.json

## Invocation

```bash
python scripts/build_research_kb.py --base-url http://127.0.0.1:8101 --manifest knowledge_base/corpus_manifest.json
```
