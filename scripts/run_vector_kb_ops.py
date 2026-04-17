#!/usr/bin/env python3
"""Utility tool for vector KB ingestion, query probe, and sync snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYNC = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_MANIFEST = REPO_ROOT / "knowledge_base" / "corpus_manifest.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def run_cmd(cmd: List[str], cwd: Path, timeout: int) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"timeout_after_{timeout}s",
            "kv": {},
        }

    kv: Dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        idx = line.find("=")
        if idx > 0:
            key = line[:idx].strip()
            value = line[idx + 1 :].strip()
            if key:
                kv[key] = value

    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "kv": kv,
    }


def post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urlopen(req, timeout=max(5, int(timeout))) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error {url}: {exc}") from exc


def post_with_fallback(urls: List[str], payload: Dict[str, Any], timeout: int) -> Tuple[Dict[str, Any], str]:
    errors: List[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = raw.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            return post_json(url, payload, timeout), url
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) if errors else "No valid endpoint candidates")


def run_ingest(base_url: str, include_web: bool, force_reingest: bool, timeout: int, manifest: str) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "scripts/run_kb_reliable_autopilot.py",
        "--base-url",
        base_url,
        "--manifest",
        manifest,
        "--timeout",
        str(timeout),
        "--max-attempts",
        "5",
        "--output-dir",
        "docs/harness_reports",
    ]
    if include_web:
        cmd.append("--include-web")
    if force_reingest:
        cmd.append("--force-reingest")
    return run_cmd(cmd, cwd=REPO_ROOT, timeout=max(60, timeout * 4))


def run_query(base_url: str, query: str, top_k: int, timeout: int) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    endpoints = [
        f"{base}/kb/query",
        f"{base}/api/kb/query",
        "http://127.0.0.1:3001/api/kb/query",
        "http://127.0.0.1:8011/kb/query",
        "http://127.0.0.1:8001/kb/query",
        "http://127.0.0.1:8101/kb/query",
    ]
    payload = {"query": query, "top_k": max(1, min(int(top_k), 20))}
    result, endpoint = post_with_fallback(endpoints, payload, timeout)
    hits = result.get("hits") if isinstance(result, dict) else []
    return {
        "endpoint": endpoint,
        "top_k": payload["top_k"],
        "hits_count": len(hits) if isinstance(hits, list) else 0,
        "result": result,
    }


def sync_snapshot(sync_path: Path) -> Dict[str, Any]:
    state = read_json(sync_path, {})
    kb = state.get("kb_sync") if isinstance(state, dict) else {}
    return {
        "sync_path": sync_path.as_posix(),
        "updated_at": state.get("updated_at") if isinstance(state, dict) else None,
        "kb_sync": {
            "mode": kb.get("mode") if isinstance(kb, dict) else None,
            "manifest": kb.get("manifest") if isinstance(kb, dict) else None,
            "total_sources": kb.get("total_sources") if isinstance(kb, dict) else None,
            "ingested_sources": kb.get("ingested_sources") if isinstance(kb, dict) else None,
            "unchanged_sources": kb.get("unchanged_sources") if isinstance(kb, dict) else None,
            "skipped_sources": kb.get("skipped_sources") if isinstance(kb, dict) else None,
            "failed_sources": kb.get("failed_sources") if isinstance(kb, dict) else None,
            "total_chunks_added": kb.get("total_chunks_added") if isinstance(kb, dict) else None,
            "report_json": kb.get("report_json") if isinstance(kb, dict) else None,
            "report_md": kb.get("report_md") if isinstance(kb, dict) else None,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dirac vector KB operations tool")
    parser.add_argument("--mode", choices=["ingest", "query", "status", "full"], default="full")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--query", default="Octopus TDDFT convergence and cross_section_vector")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--include-web", action="store_true")
    parser.add_argument("--force-reingest", action="store_true")
    parser.add_argument("--sync-path", default=str(DEFAULT_SYNC))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sync_path = Path(args.sync_path)

    output: Dict[str, Any] = {
        "tool": "run_vector_kb_ops",
        "mode": args.mode,
        "generated_at": now_iso(),
        "ok": True,
        "steps": {},
    }

    try:
        if args.mode in {"ingest", "full"}:
            output["steps"]["ingest"] = run_ingest(
                base_url=args.base_url,
                include_web=bool(args.include_web),
                force_reingest=bool(args.force_reingest),
                timeout=int(args.timeout),
                manifest=args.manifest,
            )
            if int(output["steps"]["ingest"].get("exit_code", 1)) != 0:
                output["ok"] = False

        if args.mode in {"query", "full"}:
            output["steps"]["query"] = run_query(
                base_url=args.base_url,
                query=args.query,
                top_k=int(args.top_k),
                timeout=int(args.timeout),
            )

        if args.mode in {"status", "full", "ingest"}:
            output["steps"]["status"] = sync_snapshot(sync_path)

    except Exception as exc:
        output["ok"] = False
        output["error"] = str(exc)

    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0 if output.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
