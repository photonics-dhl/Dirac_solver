#!/usr/bin/env python3
"""Run a harness benchmark case and persist a machine + human readable report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def post_json_with_fallback(urls: list[str], payload: Dict[str, Any], timeout: float) -> tuple[Dict[str, Any], str]:
    errors: list[str] = []
    seen: set[str] = set()
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


def render_markdown(result: Dict[str, Any], command: str, json_path: Path) -> str:
    case_id = result.get("case_id", "unknown")
    cfg_hash = result.get("config_hash", "")
    rel_err = result.get("relative_error")
    threshold = result.get("threshold")
    passed = bool(result.get("passed", False))
    escalation = result.get("escalation") or {}
    constraints = result.get("harness_constraints") or {}
    log_refs = result.get("log_refs") or {}
    summary = result.get("solver_summary") or {}

    rel_err_pct = f"{(float(rel_err) * 100):.6f}%" if isinstance(rel_err, (int, float)) else "N/A"
    threshold_pct = f"{(float(threshold) * 100):.2f}%" if isinstance(threshold, (int, float)) else "N/A"

    lines = [
        "# Harness Acceptance Report",
        "",
        "## Verdict",
        "",
        f"- Case: {case_id}",
        f"- Passed: {'YES' if passed else 'NO'}",
        f"- Relative Error: {rel_err_pct}",
        f"- Threshold: {threshold_pct}",
        f"- Escalation Required: {'YES' if escalation.get('required') else 'NO'}",
        f"- Escalation Reason: {escalation.get('reason') or '-'}",
        "",
        "## Run Metadata",
        "",
        f"- Config Hash: {cfg_hash}",
        f"- Attempts Used: {constraints.get('attempts_used', '-')}",
        f"- Max Retries: {constraints.get('max_retries', '-')}",
        f"- Timeout Seconds: {constraints.get('timeout_seconds', '-')}",
        f"- Solver Elapsed Seconds: {summary.get('elapsed_seconds', '-')}",
        "",
        "## Artifacts",
        "",
        f"- Harness Event Log: {log_refs.get('event_log', '-')}",
        f"- Harness Result JSON: {log_refs.get('result_json', '-')}",
        f"- Local Raw Result JSON: {json_path.as_posix()}",
        "",
        "## Invocation",
        "",
        "```bash",
        command,
        "```",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run harness benchmark and write acceptance report files.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Harness/API base URL.")
    parser.add_argument("--case-id", default="infinite_well_v1", help="Benchmark case id.")
    parser.add_argument(
        "--overrides-json",
        default="",
        help="JSON string for request overrides, e.g. '{\"gridPoints\":401}'.",
    )
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--output-dir",
        default="docs/harness_reports",
        help="Directory for generated report files.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code if harness verdict is failed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    overrides: Dict[str, Any] | None = None
    if args.overrides_json.strip():
        parsed = json.loads(args.overrides_json)
        if not isinstance(parsed, dict):
            raise ValueError("--overrides-json must decode to a JSON object")
        overrides = parsed

    payload: Dict[str, Any] = {"case_id": args.case_id}
    if overrides:
        payload["overrides"] = overrides

    base = args.base_url.rstrip("/")
    endpoint_candidates = [
        f"{base}/harness/run_case",
        f"{base}/harness/run-case",
        f"{base}/api/harness/run_case",
        f"{base}/api/harness/run-case",
        "http://127.0.0.1:8101/harness/run_case",
        "http://127.0.0.1:8101/harness/run-case",
        "http://127.0.0.1:8101/api/harness/run_case",
        "http://127.0.0.1:8101/api/harness/run-case",
        "http://127.0.0.1:3001/api/harness/run-case",
    ]
    command_text = (
        f"python scripts/run_harness_acceptance.py --base-url {args.base_url} "
        f"--case-id {args.case_id}"
        + (f" --overrides-json '{json.dumps(overrides)}'" if overrides else "")
    )

    result, used_endpoint = post_json_with_fallback(endpoint_candidates, payload, timeout=args.timeout)
    stamp = utc_now_compact()
    json_path = output_dir / f"harness_acceptance_{args.case_id}_{stamp}.json"
    md_path = output_dir / f"harness_acceptance_{args.case_id}_{stamp}.md"

    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(render_markdown(result, command_text, json_path), encoding="utf-8")

    passed = bool(result.get("passed", False))
    print(f"report_json={json_path.as_posix()}")
    print(f"report_md={md_path.as_posix()}")
    print(f"case_id={result.get('case_id', args.case_id)}")
    print(f"used_endpoint={used_endpoint}")
    print(f"passed={passed}")

    if args.strict and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
