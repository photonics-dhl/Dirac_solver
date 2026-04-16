#!/usr/bin/env python3
"""Cleanup intermediate harness reports while keeping key artifacts and sync references."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = REPO_ROOT / "docs" / "harness_reports"
DEFAULT_SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"


@dataclass
class RunGroup:
    key: str
    files: List[Path]
    mtime: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean old harness report artifacts with retention policy.")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR), help="Report directory.")
    parser.add_argument("--openclaw-sync-path", default=str(DEFAULT_SYNC_PATH), help="OpenClaw sync JSON path.")
    parser.add_argument("--keep-per-case", type=int, default=1, help="How many newest runs to keep for each case.")
    parser.add_argument("--keep-global", type=int, default=3, help="How many newest runs to keep for global categories (master/kb/task_dispatch/replan).")
    parser.add_argument("--breathing-file-threshold", type=int, default=1200, help="Threshold used by breathing auto-cleanup trigger (for summary/telemetry).")
    parser.add_argument("--trigger-reason", default="manual", help="Cleanup trigger reason, e.g. manual/breathing_threshold.")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be deleted.")
    return parser.parse_args()


def category_of(name: str) -> str:
    if name.startswith("harness_acceptance_"):
        return "acceptance"
    if name.startswith("harness_sweep_"):
        return "sweep"
    if name.startswith("harness_master_aggregate_"):
        return "master"
    if name.startswith("kb_ingestion_report_"):
        return "kb"
    if name.startswith("octopus_first_principles_"):
        return "octopus"
    if name.startswith("multi_agent_orchestration_"):
        return "multi_agent"
    if name.startswith("task_dispatch_"):
        return "task_dispatch"
    if name.startswith("replan_packet_"):
        return "replan_packet"
    if name.startswith("replan_execution_"):
        return "replan_execution"
    if name.startswith("escalation_packet_"):
        return "escalation_packet"
    return "other"


def load_sync(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_pinned_files(sync: Dict[str, object]) -> Set[str]:
    pinned: Set[str] = set()

    artifacts = sync.get("artifacts") or {}
    for key in ("master_json", "master_md"):
        value = artifacts.get(key) if isinstance(artifacts, dict) else None
        if isinstance(value, str) and value:
            pinned.add(value.replace("\\", "/"))

    kb_sync = sync.get("kb_sync") or {}
    for key in ("report_json", "report_md"):
        value = kb_sync.get(key) if isinstance(kb_sync, dict) else None
        if isinstance(value, str) and value:
            pinned.add(value.replace("\\", "/"))

    octo = sync.get("octopus_first_principles") or {}
    for key in ("report_json", "report_md"):
        value = octo.get(key) if isinstance(octo, dict) else None
        if isinstance(value, str) and value:
            pinned.add(value.replace("\\", "/"))

    top = sync.get("top_recommendation") or {}
    source = top.get("source") if isinstance(top, dict) else None
    if isinstance(source, str) and source:
        pinned.add(source.replace("\\", "/"))

    return pinned


def build_groups(files: List[Path]) -> Dict[str, Dict[str, RunGroup]]:
    grouped: Dict[str, Dict[str, RunGroup]] = {}
    for file in files:
        cat = category_of(file.name)
        if cat == "other":
            continue
        run_key = file.stem
        if cat not in grouped:
            grouped[cat] = {}
        entry = grouped[cat].get(run_key)
        mtime = file.stat().st_mtime
        if entry is None:
            grouped[cat][run_key] = RunGroup(key=run_key, files=[file], mtime=mtime)
        else:
            entry.files.append(file)
            if mtime > entry.mtime:
                entry.mtime = mtime
    return grouped


def select_keep_keys(groups: Dict[str, RunGroup], keep_count: int) -> Set[str]:
    ordered = sorted(groups.values(), key=lambda g: g.mtime, reverse=True)
    return {g.key for g in ordered[: max(0, keep_count)]}


def _trim_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def case_key_from_run_key(category: str, run_key: str) -> str:
    # run_key is stem without extension and includes timestamp suffix.
    token = run_key.rsplit("_", 1)[0] if "_" in run_key else run_key

    if category == "acceptance":
        return _trim_prefix(token, "harness_acceptance_")

    if category == "sweep":
        body = _trim_prefix(token, "harness_sweep_")
        if body.endswith("_quick"):
            return body[: -len("_quick")]
        if body.endswith("_full"):
            return body[: -len("_full")]
        return body

    if category == "octopus":
        return _trim_prefix(token, "octopus_first_principles_")

    if category == "multi_agent":
        return _trim_prefix(token, "multi_agent_orchestration_")

    if category == "task_dispatch":
        return "task_dispatch"
    if category == "replan_packet":
        return "replan_packet"
    if category == "replan_execution":
        return "replan_execution"
    if category == "escalation_packet":
        return "escalation_packet"

    # master/kb are not case-specific.
    return "__global__"


def select_keep_keys_per_case(category: str, groups: Dict[str, RunGroup], keep_per_case: int) -> Set[str]:
    by_case: Dict[str, List[RunGroup]] = {}
    for group in groups.values():
        case_key = case_key_from_run_key(category, group.key)
        by_case.setdefault(case_key, []).append(group)

    keep_keys: Set[str] = set()
    for case_groups in by_case.values():
        ordered = sorted(case_groups, key=lambda g: g.mtime, reverse=True)
        keep_keys.update(g.key for g in ordered[: max(0, keep_per_case)])
    return keep_keys


def relative_posix(path: Path, base: Path) -> str:
    # Windows mapped drives (e.g. Z:) and UNC roots can point to the same file tree
    # but fail direct pathlib.relative_to checks. Normalize first and fall back safely.
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        try:
            rel = os.path.relpath(str(path.resolve()), str(base.resolve()))
            return Path(rel).as_posix()
        except Exception:
            return path.resolve().as_posix()


def update_sync_cleanup(sync_path: Path, sync: Dict[str, object], summary: Dict[str, object]) -> None:
    sync["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sync["cleanup"] = summary
    sync_path.parent.mkdir(parents=True, exist_ok=True)
    sync_path.write_text(json.dumps(sync, indent=2, ensure_ascii=True), encoding="utf-8")


def main() -> int:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    sync_path = Path(args.openclaw_sync_path)

    if not reports_dir.exists():
        raise FileNotFoundError(f"Reports directory not found: {reports_dir.as_posix()}")

    all_files = [p for p in reports_dir.glob("*.*") if p.is_file() and p.suffix in {".json", ".md"}]

    sync = load_sync(sync_path)
    pinned_rel = extract_pinned_files(sync)

    groups_by_cat = build_groups(all_files)
    keep_policy = {
        "keep_per_case": args.keep_per_case,
        "keep_global": args.keep_global,
    }

    keep_run_keys: Dict[str, Set[str]] = {}
    for cat, groups in groups_by_cat.items():
        if cat in {"master", "kb", "task_dispatch", "replan_packet", "replan_execution", "escalation_packet"}:
            keep_run_keys[cat] = select_keep_keys(groups, args.keep_global)
        else:
            keep_run_keys[cat] = select_keep_keys_per_case(cat, groups, args.keep_per_case)

    to_delete: List[Path] = []
    kept_count = 0

    for file in all_files:
        cat = category_of(file.name)
        rel = relative_posix(file, REPO_ROOT)
        if rel in pinned_rel:
            kept_count += 1
            continue
        if cat == "other":
            kept_count += 1
            continue

        run_key = file.stem
        if run_key in keep_run_keys.get(cat, set()):
            kept_count += 1
            continue

        to_delete.append(file)

    deleted = 0
    for file in to_delete:
        if args.dry_run:
            print(f"would_delete={file.as_posix()}")
            continue
        try:
            file.unlink()
            deleted += 1
        except Exception as exc:
            print(f"warn=failed_delete path={file.as_posix()} err={exc}")

    summary = {
        "last_cleanup_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reports_dir": reports_dir.as_posix(),
        "dry_run": bool(args.dry_run),
        "trigger_reason": str(args.trigger_reason or "manual"),
        "policy": keep_policy,
        "breathing": {
            "file_threshold": int(args.breathing_file_threshold),
            "triggered": str(args.trigger_reason or "manual") != "manual",
        },
        "total_files_scanned": len(all_files),
        "pinned_files": len(pinned_rel),
        "kept_files": kept_count,
        "deleted_files": deleted,
    }

    update_sync_cleanup(sync_path, sync, summary)

    print(f"total_files_scanned={len(all_files)}")
    print(f"kept_files={kept_count}")
    print(f"deleted_files={deleted}")
    print(f"openclaw_sync_json={sync_path.as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
