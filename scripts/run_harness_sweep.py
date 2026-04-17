#!/usr/bin/env python3
"""Run a parameter sweep for harness acceptance and generate aggregate reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
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


def sweep_presets() -> Dict[str, List[Dict[str, Any]]]:
    # Keep default config physically equivalent while probing discretization sensitivity.
    return {
        "quick": [
            {"gridPoints": 151, "gridSpacing": 0.03},
            {"gridPoints": 201, "gridSpacing": 0.02},
            {"gridPoints": 401, "gridSpacing": 0.01},
        ],
        "full": [
            {"gridPoints": 101, "gridSpacing": 0.04},
            {"gridPoints": 151, "gridSpacing": 0.03},
            {"gridPoints": 201, "gridSpacing": 0.02},
            {"gridPoints": 301, "gridSpacing": 0.015},
            {"gridPoints": 401, "gridSpacing": 0.01},
            {"gridPoints": 601, "gridSpacing": 0.007},
        ],
    }


def to_pct(value: Any, digits: int = 4) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value) * 100:.{digits}f}%"
    return "N/A"


def build_recommendations(run_rows: List[Dict[str, Any]], threshold: Any) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    numeric_threshold = float(threshold) if isinstance(threshold, (int, float)) else None

    for row in run_rows:
        if row.get("passed"):
            continue

        overrides = row.get("overrides") or {}
        grid_points = overrides.get("gridPoints")
        grid_spacing = overrides.get("gridSpacing")
        rel_err = row.get("relative_error")

        actions: List[str] = []
        if isinstance(grid_points, int) and grid_points < 201:
            actions.append("Increase gridPoints to >= 201 for baseline stability.")
        if isinstance(grid_spacing, (int, float)) and float(grid_spacing) > 0.02:
            actions.append("Decrease gridSpacing to <= 0.02 to reduce discretization error.")
        if not actions:
            actions.append("Use the known stable baseline (gridPoints=201, gridSpacing=0.02) and retest.")

        suggested_overrides = {
            "gridPoints": max(int(grid_points), 201) if isinstance(grid_points, int) else 201,
            "gridSpacing": min(float(grid_spacing), 0.02) if isinstance(grid_spacing, (int, float)) else 0.02,
        }
        suggested_command = (
            "python scripts/run_harness_acceptance.py "
            "--base-url http://127.0.0.1:8001 "
            "--case-id infinite_well_v1 "
            f"--overrides-json '{json.dumps(suggested_overrides, ensure_ascii=True)}' --strict"
        )

        severity = "medium"
        if isinstance(rel_err, (int, float)) and numeric_threshold is not None and float(rel_err) > numeric_threshold * 2:
            severity = "high"

        recommendations.append(
            {
                "run_id": row.get("run_id"),
                "config_hash": row.get("config_hash"),
                "relative_error": rel_err,
                "threshold": numeric_threshold,
                "severity": severity,
                "root_cause_hint": "discretization_too_coarse",
                "actions": actions,
                "suggested_overrides": suggested_overrides,
                "suggested_command": suggested_command,
            }
        )

    return recommendations


def render_markdown(summary: Dict[str, Any], command: str, json_path: Path) -> str:
    total = int(summary.get("total", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    pass_rate = (passed / total) * 100 if total > 0 else 0.0
    max_error = summary.get("max_relative_error")
    threshold = summary.get("threshold")

    lines = [
        "# Harness Sweep Report",
        "",
        "## Summary",
        "",
        f"- Case: {summary.get('case_id', 'unknown')}",
        f"- Preset: {summary.get('preset', '-')}",
        f"- Total Runs: {total}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Pass Rate: {pass_rate:.2f}%",
        f"- Max Relative Error: {to_pct(max_error, 6)}",
        f"- Threshold: {to_pct(threshold, 2)}",
        "",
        "## Runs",
        "",
        "| Run | Passed | Relative Error | Threshold | Config Hash | Overrides |",
        "|---|---|---|---|---|---|",
    ]

    for item in summary.get("runs", []):
        run_id = item.get("run_id", "-")
        verdict = "YES" if item.get("passed") else "NO"
        rel_err = to_pct(item.get("relative_error"), 6)
        thr = to_pct(item.get("threshold"), 2)
        cfg_hash = item.get("config_hash", "-")
        overrides = json.dumps(item.get("overrides", {}), ensure_ascii=True)
        lines.append(f"| {run_id} | {verdict} | {rel_err} | {thr} | {cfg_hash} | {overrides} |")

    recommendations = summary.get("recommendations", [])
    lines.extend([
        "",
        "## Recommendations",
        "",
    ])
    if recommendations:
        for rec in recommendations:
            lines.append(
                "- Run {run_id}: relative_error={rel} vs threshold={thr} | severity={sev} | hint={hint}".format(
                    run_id=rec.get("run_id", "-"),
                    rel=to_pct(rec.get("relative_error"), 6),
                    thr=to_pct(rec.get("threshold"), 2),
                    sev=rec.get("severity", "-"),
                    hint=rec.get("root_cause_hint", "-"),
                )
            )
            for action in rec.get("actions", []):
                lines.append(f"  - {action}")
            if rec.get("suggested_command"):
                lines.append(f"  - Suggested retest: {rec.get('suggested_command')}")
    else:
        lines.append("- No remediation suggestions required. All runs passed threshold.")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Local Aggregate JSON: {json_path.as_posix()}",
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
    parser = argparse.ArgumentParser(description="Run harness sweep and generate aggregate reports.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Harness API base URL.")
    parser.add_argument("--case-id", default="infinite_well_v1", help="Benchmark case id.")
    parser.add_argument("--preset", choices=["quick", "full"], default="quick", help="Sweep preset name.")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds.")
    parser.add_argument("--output-dir", default="docs/harness_reports", help="Output directory.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any run fails threshold.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    presets = sweep_presets()
    runs = presets[args.preset]
    endpoint = f"{args.base_url.rstrip('/')}/harness/run_case"

    run_rows: List[Dict[str, Any]] = []
    max_relative_error = -1.0
    threshold_value: Any = None

    for idx, overrides in enumerate(runs, start=1):
        payload: Dict[str, Any] = {
            "case_id": args.case_id,
            "overrides": overrides,
        }
        result = post_json(endpoint, payload, timeout=args.timeout)

        relative_error = result.get("relative_error")
        threshold = result.get("threshold")
        if isinstance(relative_error, (int, float)):
            max_relative_error = max(max_relative_error, float(relative_error))
        if threshold_value is None:
            threshold_value = threshold

        run_rows.append(
            {
                "run_id": idx,
                "overrides": overrides,
                "passed": bool(result.get("passed", False)),
                "relative_error": relative_error,
                "threshold": threshold,
                "config_hash": result.get("config_hash", ""),
                "escalation": result.get("escalation") or {},
                "log_refs": result.get("log_refs") or {},
                "raw": result,
            }
        )

    passed_count = sum(1 for row in run_rows if row["passed"])
    failed_count = len(run_rows) - passed_count
    recommendations = build_recommendations(run_rows, threshold_value)

    summary: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "case_id": args.case_id,
        "preset": args.preset,
        "total": len(run_rows),
        "passed": passed_count,
        "failed": failed_count,
        "threshold": threshold_value,
        "max_relative_error": None if max_relative_error < 0 else max_relative_error,
        "recommendations": recommendations,
        "runs": [
            {
                "run_id": row["run_id"],
                "overrides": row["overrides"],
                "passed": row["passed"],
                "relative_error": row["relative_error"],
                "threshold": row["threshold"],
                "config_hash": row["config_hash"],
                "escalation": row["escalation"],
                "log_refs": row["log_refs"],
            }
            for row in run_rows
        ],
    }

    stamp = utc_now_compact()
    json_path = output_dir / f"harness_sweep_{args.case_id}_{args.preset}_{stamp}.json"
    md_path = output_dir / f"harness_sweep_{args.case_id}_{args.preset}_{stamp}.md"

    command_text = (
        f"python scripts/run_harness_sweep.py --base-url {args.base_url} "
        f"--case-id {args.case_id} --preset {args.preset}" + (" --strict" if args.strict else "")
    )

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(render_markdown(summary, command_text, json_path), encoding="utf-8")

    print(f"sweep_report_json={json_path.as_posix()}")
    print(f"sweep_report_md={md_path.as_posix()}")
    print(f"total={summary['total']}")
    print(f"passed={summary['passed']}")
    print(f"failed={summary['failed']}")

    if args.strict and failed_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
