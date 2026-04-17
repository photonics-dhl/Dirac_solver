#!/usr/bin/env python3
"""Build vector knowledge base from curated manifest sources and sync OpenClaw status."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "knowledge_base" / "corpus_manifest.json"
DEFAULT_OPENCLAW_SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_CHUNKS_DIR = REPO_ROOT / "knowledge_base" / "chunks"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@contextmanager
def file_lock(lock_path: Path, timeout_seconds: float = 8.0):
    start = time.time()
    acquired_fd = None
    while True:
        try:
            acquired_fd = os.open(lock_path.as_posix(), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if (time.time() - start) >= timeout_seconds:
                raise TimeoutError(f"lock timeout: {lock_path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        if acquired_fd is not None:
            try:
                os.close(acquired_fd)
            except Exception:
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            try:
                backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")

    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def post_json_with_fallback(urls: List[str], payload: Dict[str, Any], timeout: float) -> Tuple[Dict[str, Any], str]:
    errors: List[str] = []
    seen = set()
    for url in urls:
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return post_json(normalized, payload, timeout=timeout), normalized
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors) if errors else "No endpoint candidates provided")


def fetch_text(url: str, timeout: float) -> str:
    request = Request(url, method="GET")
    request.add_header("User-Agent", "DiracKBBuilder/1.0")
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def resolve_local_path(rel_path: str) -> Path:
    p = Path(rel_path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def sanitize_source_id(source_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", source_id.strip())
    return normalized[:80] or "unknown_source"


def chunk_text_sliding_window(text: str, chunk_size: int, overlap: int) -> List[str]:
    clean = text.replace("\r\n", "\n").strip()
    if not clean:
        return []
    if chunk_size <= 0:
        return [clean]
    safe_overlap = max(0, min(overlap, max(chunk_size - 1, 0)))
    step = max(1, chunk_size - safe_overlap)
    chunks: List[str] = []
    for start in range(0, len(clean), step):
        piece = clean[start : start + chunk_size]
        if piece.strip():
            chunks.append(piece)
        if start + chunk_size >= len(clean):
            break
    return chunks


def export_local_chunks(
    chunks_dir: Path,
    source_id: str,
    title: str,
    tags: List[str],
    content_hash: str,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> Tuple[int, str]:
    chunks = chunk_text_sliding_window(text, chunk_size=chunk_size, overlap=chunk_overlap)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    short_hash = content_hash[:12]
    filename = f"{sanitize_source_id(source_id)}__{short_hash}.jsonl"
    out_path = chunks_dir / filename
    lines: List[str] = []
    for idx, chunk in enumerate(chunks):
        row = {
            "source_id": source_id,
            "title": title,
            "content_hash": content_hash,
            "chunk_index": idx,
            "chunk_total": len(chunks),
            "chunk_size": len(chunk),
            "chunking": {
                "method": "char_sliding_window",
                "window": chunk_size,
                "overlap": chunk_overlap,
            },
            "topic_tags": tags,
            "text": chunk,
        }
        lines.append(json.dumps(row, ensure_ascii=True))
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(chunks), out_path.as_posix()


def load_previous_source_index(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    kb_sync = payload.get("kb_sync") if isinstance(payload, dict) else None
    if not isinstance(kb_sync, dict):
        return {}
    source_index = kb_sync.get("source_index")
    if not isinstance(source_index, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in source_index.items():
        if isinstance(value, dict):
            normalized[str(key)] = value
    return normalized


def write_openclaw_sync(path: Path, kb_summary: Dict[str, Any], report_json: Path, report_md: Path, source_index: Dict[str, Dict[str, Any]]) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path):
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                backup_path = path.with_suffix(path.suffix + ".bak")
                try:
                    existing = json.loads(backup_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}

        existing["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing["project"] = "Dirac_solver"
        if not isinstance(existing.get("last_task"), dict):
            existing["phase"] = "phaseA_plus"
            existing["status"] = "in_progress"
        existing["kb_sync"] = {
            "mode": kb_summary.get("mode", "incremental"),
            "manifest": kb_summary.get("manifest"),
            "total_sources": kb_summary.get("total_sources", 0),
            "ingested_sources": kb_summary.get("ingested_sources", 0),
            "unchanged_sources": kb_summary.get("unchanged_sources", 0),
            "skipped_sources": kb_summary.get("skipped_sources", 0),
            "failed_sources": kb_summary.get("failed_sources", 0),
            "total_chunks_added": kb_summary.get("total_chunks_added", 0),
            "local_chunk_evidence_count": kb_summary.get("local_chunk_evidence_count", 0),
            "local_chunks_dir": kb_summary.get("local_chunks_dir"),
            "report_json": report_json.as_posix(),
            "report_md": report_md.as_posix(),
            "source_index": source_index,
        }

        write_json_atomic(path, existing)


def render_markdown(summary: Dict[str, Any], command: str, report_json: Path) -> str:
    lines: List[str] = [
        "# Research KB Build Report",
        "",
        "## Summary",
        "",
        f"- Generated At: {summary.get('generated_at')}",
        f"- Manifest: {summary.get('manifest')}",
        f"- Total Sources: {summary.get('total_sources')}",
        f"- Ingested Sources: {summary.get('ingested_sources')}",
        f"- Skipped Sources: {summary.get('skipped_sources')}",
        f"- Failed Sources: {summary.get('failed_sources')}",
        f"- Total Chunks Added: {summary.get('total_chunks_added')}",
        f"- Local Chunk Evidence Count: {summary.get('local_chunk_evidence_count')}",
        f"- Local Chunks Dir: {summary.get('local_chunks_dir')}",
        "",
        "## Details",
        "",
        "| Source ID | Type | Status | Chunks Added | Local Chunks | Local Chunk File | Note |",
        "|---|---|---|---|---|---|---|",
    ]

    for row in summary.get("rows", []):
        lines.append(
            "| {source_id} | {stype} | {status} | {chunks} | {local_chunks} | {chunk_file} | {note} |".format(
                source_id=row.get("source_id", "-"),
                stype=row.get("type", "-"),
                status=row.get("status", "-"),
                chunks=row.get("chunks_added", 0),
                local_chunks=row.get("local_chunks", 0),
                chunk_file=str(row.get("local_chunk_file", "-")).replace("|", "/"),
                note=str(row.get("note", "-")).replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Artifact",
            "",
            f"- JSON: {report_json.as_posix()}",
            "",
            "## Invocation",
            "",
            "```bash",
            command,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build DFT/TDDFT/QM vector KB from manifest sources.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Backend/API base URL.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to corpus manifest JSON.")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout seconds.")
    parser.add_argument("--include-web", action="store_true", help="Fetch and ingest web_reference URLs in manifest.")
    parser.add_argument("--output-dir", default="docs/harness_reports", help="Report output directory.")
    parser.add_argument("--openclaw-sync-path", default=str(DEFAULT_OPENCLAW_SYNC_PATH), help="OpenClaw sync JSON path.")
    parser.add_argument("--skip-openclaw-sync", action="store_true", help="Skip OpenClaw sync JSON write.")
    parser.add_argument("--force-reingest", action="store_true", help="Force re-ingestion even when source content hash is unchanged.")
    parser.add_argument("--chunks-dir", default=str(DEFAULT_CHUNKS_DIR), help="Local chunk evidence output directory.")
    parser.add_argument("--chunk-size", type=int, default=1400, help="Chunk size for local chunk evidence.")
    parser.add_argument("--chunk-overlap", type=int, default=180, help="Chunk overlap for local chunk evidence.")
    parser.add_argument("--skip-local-chunk-export", action="store_true", help="Skip writing local chunk evidence files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    payload = load_manifest(manifest_path)
    sources = payload.get("sources") or []
    base = args.base_url.rstrip("/")
    endpoint_candidates = [
        f"{base}/kb/ingest_markdown",
        f"{base}/kb/ingest-markdown",
        f"{base}/api/kb/ingest-markdown",
        f"{base}/api/kb/ingest_markdown",
        "http://127.0.0.1:3001/api/kb/ingest-markdown",
        "http://127.0.0.1:8011/kb/ingest_markdown",
        "http://127.0.0.1:8011/kb/ingest-markdown",
        "http://127.0.0.1:8001/kb/ingest_markdown",
        "http://127.0.0.1:8101/kb/ingest_markdown",
    ]

    rows: List[Dict[str, Any]] = []
    total_chunks = 0
    local_chunk_evidence_count = 0
    sync_path = Path(args.openclaw_sync_path)
    chunks_dir = Path(args.chunks_dir)
    previous_index = load_previous_source_index(sync_path)
    next_index: Dict[str, Dict[str, Any]] = dict(previous_index)

    for src in sources:
        source_id = str(src.get("source_id", "")).strip() or "unknown"
        source_type = str(src.get("type", "local_markdown")).strip()
        tags = src.get("topic_tags") or []
        title = str(src.get("title", source_id))

        try:
            text = ""
            note = ""
            if source_type == "local_markdown":
                local_path_raw = str(src.get("local_markdown", "")).strip()
                if not local_path_raw:
                    rows.append({
                        "source_id": source_id,
                        "type": source_type,
                        "status": "skipped",
                        "chunks_added": 0,
                        "note": "missing local_markdown",
                    })
                    continue
                local_path = resolve_local_path(local_path_raw)
                if not local_path.exists():
                    rows.append({
                        "source_id": source_id,
                        "type": source_type,
                        "status": "skipped",
                        "chunks_added": 0,
                        "note": f"missing file: {local_path.as_posix()}",
                    })
                    continue
                text = local_path.read_text(encoding="utf-8")
                note = local_path.as_posix()
            elif source_type == "web_reference":
                if not args.include_web:
                    rows.append({
                        "source_id": source_id,
                        "type": source_type,
                        "status": "skipped",
                        "chunks_added": 0,
                        "note": "web ingestion disabled; pass --include-web",
                    })
                    continue
                url = str(src.get("url", "")).strip()
                if not url:
                    rows.append({
                        "source_id": source_id,
                        "type": source_type,
                        "status": "skipped",
                        "chunks_added": 0,
                        "note": "missing url",
                    })
                    continue
                text = fetch_text(url, timeout=args.timeout)
                note = url
            else:
                rows.append({
                    "source_id": source_id,
                    "type": source_type,
                    "status": "skipped",
                    "chunks_added": 0,
                    "note": "unsupported source type",
                })
                continue

            ingest_payload = {
                "source": f"{source_id}:{title}",
                "text": text,
                "topic_tags": tags,
            }
            content_hash = text_sha256(text)
            local_chunks = 0
            local_chunk_file = ""
            if not args.skip_local_chunk_export:
                local_chunks, local_chunk_file = export_local_chunks(
                    chunks_dir=chunks_dir,
                    source_id=source_id,
                    title=title,
                    tags=tags,
                    content_hash=content_hash,
                    text=text,
                    chunk_size=max(200, int(args.chunk_size)),
                    chunk_overlap=max(0, int(args.chunk_overlap)),
                )
                local_chunk_evidence_count += local_chunks
            prev = previous_index.get(source_id) or {}
            prev_hash = str(prev.get("content_hash", "")).strip()
            if not args.force_reingest and prev_hash and prev_hash == content_hash:
                rows.append(
                    {
                        "source_id": source_id,
                        "type": source_type,
                        "status": "unchanged",
                        "chunks_added": 0,
                        "local_chunks": local_chunks,
                        "local_chunk_file": local_chunk_file,
                        "note": f"unchanged hash; skipped ({note})",
                    }
                )
                continue

            result, used_endpoint = post_json_with_fallback(endpoint_candidates, ingest_payload, timeout=args.timeout)
            chunks = int(result.get("chunks", 0))
            total_chunks += chunks
            next_index[source_id] = {
                "content_hash": content_hash,
                "source_type": source_type,
                "title": title,
                "last_ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            rows.append(
                {
                    "source_id": source_id,
                    "type": source_type,
                    "status": "ingested",
                    "chunks_added": chunks,
                    "local_chunks": local_chunks,
                    "local_chunk_file": local_chunk_file,
                    "note": f"{note} via {used_endpoint}",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "source_id": source_id,
                    "type": source_type,
                    "status": "failed",
                    "chunks_added": 0,
                    "local_chunks": 0,
                    "local_chunk_file": "",
                    "note": str(exc),
                }
            )

    ingested = sum(1 for r in rows if r["status"] == "ingested")
    unchanged = sum(1 for r in rows if r["status"] == "unchanged")
    skipped = sum(1 for r in rows if r["status"] == "skipped")
    failed = sum(1 for r in rows if r["status"] == "failed")

    summary: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest": manifest_path.as_posix(),
        "mode": "force_reingest" if args.force_reingest else "incremental",
        "total_sources": len(sources),
        "ingested_sources": ingested,
        "unchanged_sources": unchanged,
        "skipped_sources": skipped,
        "failed_sources": failed,
        "total_chunks_added": total_chunks,
        "local_chunk_evidence_count": local_chunk_evidence_count,
        "local_chunks_dir": chunks_dir.as_posix(),
        "rows": rows,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_compact()
    report_json = output_dir / f"kb_ingestion_report_{stamp}.json"
    report_md = output_dir / f"kb_ingestion_report_{stamp}.md"

    command_text = (
        f"python scripts/build_research_kb.py --base-url {args.base_url} --manifest {manifest_path.as_posix()}"
        + (" --include-web" if args.include_web else "")
    )

    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    report_md.write_text(render_markdown(summary, command_text, report_json), encoding="utf-8")

    if not args.skip_openclaw_sync:
        write_openclaw_sync(sync_path, summary, report_json, report_md, next_index)

    print(f"kb_report_json={report_json.as_posix()}")
    print(f"kb_report_md={report_md.as_posix()}")
    print(f"ingested_sources={ingested}")
    print(f"unchanged_sources={unchanged}")
    print(f"skipped_sources={skipped}")
    print(f"failed_sources={failed}")
    print(f"total_chunks_added={total_chunks}")
    print(f"local_chunk_evidence_count={local_chunk_evidence_count}")
    print(f"local_chunks_dir={chunks_dir.as_posix()}")
    if not args.skip_openclaw_sync:
        print(f"openclaw_sync_json={Path(args.openclaw_sync_path).as_posix()}")

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
