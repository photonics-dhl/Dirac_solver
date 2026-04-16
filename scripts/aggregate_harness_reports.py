#!/usr/bin/env python3
"""Aggregate harness acceptance/sweep outputs into a master report."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENCLAW_SYNC_PATH = REPO_ROOT.parent / "OpenClaw" / "state" / "dirac_solver_progress_sync.json"


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate harness report artifacts into one master report.")
    parser.add_argument(
        "--reports-dir",
        default="docs/harness_reports",
        help="Directory containing harness_acceptance_*.json and harness_sweep_*.json outputs.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/harness_reports",
        help="Directory for generated master aggregate report files.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=50,
        help="Maximum number of newest report files to include.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow generation even when no source report files are found.",
    )
    parser.add_argument(
        "--openclaw-sync-path",
        default=str(DEFAULT_OPENCLAW_SYNC_PATH),
        help="Where to write OpenClaw-readable progress sync JSON.",
    )
    parser.add_argument(
        "--skip-openclaw-sync",
        action="store_true",
        help="Skip writing OpenClaw sync status file.",
    )
    return parser.parse_args()


def write_openclaw_sync(path: Path, summary: Dict[str, Any], json_path: Path, md_path: Path) -> None:
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

        top_recommendation = None
        recs = summary.get("recommendations") or []
        if recs:
            first = recs[0]
            top_recommendation = {
                "severity": first.get("severity"),
                "relative_error": first.get("relative_error"),
                "threshold": first.get("threshold"),
                "actions": first.get("actions") or [],
                "suggested_command": first.get("suggested_command"),
                "source": first.get("source"),
            }

        sync_payload = dict(existing)
        sync_payload["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        sync_payload["project"] = "Dirac_solver"
        if not isinstance(sync_payload.get("last_task"), dict):
            sync_payload["phase"] = "phaseA_plus"
            sync_payload["status"] = "in_progress"
        sync_payload["summary"] = {
            "acceptance_count": summary.get("acceptance_count", 0),
            "sweep_count": summary.get("sweep_count", 0),
            "acceptance_pass_rate": summary.get("acceptance_pass_rate", 0.0),
            "recommendations_count": len(recs),
        }
        sync_payload["artifacts"] = {
            "master_json": json_path.as_posix(),
            "master_md": md_path.as_posix(),
        }
        sync_payload["top_recommendation"] = top_recommendation

        write_json_atomic(path, sync_payload)


def load_json(path: Path) -> Dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def classify_report(path: Path, payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    name = path.name
    if name.startswith("harness_acceptance_"):
        return (
            "acceptance",
            {
                "file": path.as_posix(),
                "case_id": payload.get("case_id"),
                "passed": bool(payload.get("passed", False)),
                "relative_error": payload.get("relative_error"),
                "threshold": payload.get("threshold"),
                "config_hash": payload.get("config_hash"),
                "generated_at": payload.get("event_chain", [{}])[0].get("timestamp") if isinstance(payload.get("event_chain"), list) and payload.get("event_chain") else None,
            },
        )

    if name.startswith("harness_sweep_"):
        return (
            "sweep",
            {
                "file": path.as_posix(),
                "case_id": payload.get("case_id"),
                "preset": payload.get("preset"),
                "total": payload.get("total"),
                "passed": payload.get("passed"),
                "failed": payload.get("failed"),
                "max_relative_error": payload.get("max_relative_error"),
                "threshold": payload.get("threshold"),
                "recommendations": payload.get("recommendations") or [],
                "generated_at": payload.get("generated_at"),
            },
        )

    return ("unknown", {"file": path.as_posix()})


def to_pct(value: Any, digits: int = 4) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value) * 100:.{digits}f}%"
    return "N/A"


def severity_rank(level: Any) -> int:
    if str(level).lower() == "high":
        return 3
    if str(level).lower() == "medium":
        return 2
    if str(level).lower() == "low":
        return 1
    return 0


def dedupe_and_sort_recommendations(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for rec in items:
        actions = rec.get("actions") or []
        key = "||".join(actions) or f"run:{rec.get('run_id')}"
        previous = merged.get(key)
        if previous is None:
            merged[key] = rec
            continue

        prev_err = float(previous.get("relative_error")) if isinstance(previous.get("relative_error"), (int, float)) else -1.0
        cur_err = float(rec.get("relative_error")) if isinstance(rec.get("relative_error"), (int, float)) else -1.0
        prev_sev = severity_rank(previous.get("severity"))
        cur_sev = severity_rank(rec.get("severity"))

        if cur_sev > prev_sev or (cur_sev == prev_sev and cur_err > prev_err):
            merged[key] = rec

    deduped = list(merged.values())
    deduped.sort(
        key=lambda r: (
            severity_rank(r.get("severity")),
            float(r.get("relative_error")) if isinstance(r.get("relative_error"), (int, float)) else -1.0,
        ),
        reverse=True,
    )
    return deduped


def render_markdown(summary: Dict[str, Any], command: str, json_path: Path) -> str:
    lines: List[str] = [
        "# Harness Master Aggregate Report",
        "",
        "## Summary",
        "",
        f"- Generated At: {summary.get('generated_at')}",
        f"- Source Directory: {summary.get('reports_dir')}",
        f"- Included Files: {summary.get('source_files_count', 0)}",
        f"- Acceptance Reports: {summary.get('acceptance_count', 0)}",
        f"- Sweep Reports: {summary.get('sweep_count', 0)}",
        f"- Acceptance Pass Rate: {summary.get('acceptance_pass_rate', 0.0):.2f}%",
        "",
        "## Acceptance Runs",
        "",
        "| File | Case | Passed | Relative Error | Threshold | Config Hash |",
        "|---|---|---|---|---|---|",
    ]

    for row in summary.get("acceptance_reports", []):
        lines.append(
            "| {file} | {case} | {passed} | {rel} | {thr} | {hashv} |".format(
                file=row.get("file", "-"),
                case=row.get("case_id", "-"),
                passed="YES" if row.get("passed") else "NO",
                rel=to_pct(row.get("relative_error"), 6),
                thr=to_pct(row.get("threshold"), 2),
                hashv=row.get("config_hash", "-"),
            )
        )

    lines.extend(
        [
            "",
            "## Sweep Runs",
            "",
            "| File | Case | Preset | Total | Passed | Failed | Max Relative Error | Threshold |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )

    for row in summary.get("sweep_reports", []):
        lines.append(
            "| {file} | {case} | {preset} | {total} | {passed} | {failed} | {maxe} | {thr} |".format(
                file=row.get("file", "-"),
                case=row.get("case_id", "-"),
                preset=row.get("preset", "-"),
                total=row.get("total", "-"),
                passed=row.get("passed", "-"),
                failed=row.get("failed", "-"),
                maxe=to_pct(row.get("max_relative_error"), 6),
                thr=to_pct(row.get("threshold"), 2),
            )
        )

    lines.extend(
        [
            "",
            "## Consolidated Recommendations",
            "",
        ]
    )

    recommendations = summary.get("recommendations", [])
    if recommendations:
        for rec in recommendations:
            lines.append(
                "- Source: {source} run={run_id} | severity={sev} | relative_error={rel} vs threshold={thr}".format(
                    source=rec.get("source", "-"),
                    run_id=rec.get("run_id", "-"),
                    sev=rec.get("severity", "-"),
                    rel=to_pct(rec.get("relative_error"), 6),
                    thr=to_pct(rec.get("threshold"), 2),
                )
            )
            for action in rec.get("actions", []):
                lines.append(f"  - {action}")
            if rec.get("suggested_command"):
                lines.append(f"  - Suggested retest: {rec.get('suggested_command')}")
    else:
        lines.append("- No remediation suggestions were emitted by included sweep reports.")

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


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not reports_dir.exists():
        if args.allow_empty:
            candidates: List[Path] = []
        else:
            raise FileNotFoundError(f"Reports directory does not exist: {reports_dir.as_posix()}")
    else:
        candidates = sorted(
            [p for p in reports_dir.glob("*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: max(1, args.max_items)]

    acceptance_reports: List[Dict[str, Any]] = []
    sweep_reports: List[Dict[str, Any]] = []

    for path in candidates:
        payload = load_json(path)
        if not payload:
            continue
        kind, row = classify_report(path, payload)
        if kind == "acceptance":
            acceptance_reports.append(row)
        elif kind == "sweep":
            sweep_reports.append(row)

    total_acceptance = len(acceptance_reports)
    pass_acceptance = sum(1 for x in acceptance_reports if x.get("passed"))
    pass_rate = (pass_acceptance / total_acceptance * 100.0) if total_acceptance > 0 else 0.0

    recommendations: List[Dict[str, Any]] = []
    for sweep in sweep_reports:
        source_file = sweep.get("file", "-")
        for rec in sweep.get("recommendations", []):
            recommendations.append(
                {
                    "source": source_file,
                    "run_id": rec.get("run_id"),
                    "relative_error": rec.get("relative_error"),
                    "threshold": rec.get("threshold"),
                    "severity": rec.get("severity"),
                    "actions": rec.get("actions") or [],
                    "suggested_command": rec.get("suggested_command"),
                }
            )

    recommendations = dedupe_and_sort_recommendations(recommendations)

    summary: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reports_dir": reports_dir.as_posix(),
        "source_files_count": len(candidates),
        "acceptance_count": len(acceptance_reports),
        "sweep_count": len(sweep_reports),
        "acceptance_pass_rate": pass_rate,
        "acceptance_reports": acceptance_reports,
        "sweep_reports": sweep_reports,
        "recommendations": recommendations,
    }

    if not args.allow_empty and len(candidates) == 0:
        raise RuntimeError("No JSON reports found; run acceptance/sweep first or pass --allow-empty")

    stamp = utc_now_compact()
    json_path = output_dir / f"harness_master_aggregate_{stamp}.json"
    md_path = output_dir / f"harness_master_aggregate_{stamp}.md"

    command_text = (
        f"python scripts/aggregate_harness_reports.py --reports-dir {args.reports_dir} "
        f"--output-dir {args.output_dir} --max-items {args.max_items}"
        + (" --allow-empty" if args.allow_empty else "")
    )

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(render_markdown(summary, command_text, json_path), encoding="utf-8")

    sync_path = Path(args.openclaw_sync_path)
    if not args.skip_openclaw_sync:
        write_openclaw_sync(sync_path, summary, json_path, md_path)

    print(f"master_report_json={json_path.as_posix()}")
    print(f"master_report_md={md_path.as_posix()}")
    print(f"source_files_count={summary['source_files_count']}")
    print(f"acceptance_count={summary['acceptance_count']}")
    print(f"sweep_count={summary['sweep_count']}")
    if not args.skip_openclaw_sync:
        print(f"openclaw_sync_json={sync_path.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
