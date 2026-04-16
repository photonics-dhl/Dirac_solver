#!/usr/bin/env python3
"""Worker for coding gateway tasks.

This worker claims queued tasks from state storage and invokes an external
adapter command to run coding execution in an isolated process.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def load_state(path: Path) -> Dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("tasks"), dict):
        payload["tasks"] = {}
    return payload


def save_state(path: Path, payload: Dict[str, Any]) -> None:
    payload["updated_at"] = now_iso()
    write_json(path, payload)


def claim_task(state_path: Path) -> Optional[Dict[str, Any]]:
    state = load_state(state_path)
    tasks = state.get("tasks", {})
    for task_id, task in tasks.items():
        if not isinstance(task, dict):
            continue
        if str(task.get("state") or "") != "queued":
            continue
        task["state"] = "running"
        task["started_at"] = now_iso()
        task["updated_at"] = now_iso()
        save_state(state_path, state)
        return dict(task)
    return None


def persist_result(state_path: Path, task_id: str, ok: bool, result: Dict[str, Any]) -> None:
    state = load_state(state_path)
    tasks = state.get("tasks", {})
    task = tasks.get(task_id)
    if not isinstance(task, dict):
        return
    task["state"] = "succeeded" if ok else "failed"
    task["result"] = result
    task["finished_at"] = now_iso()
    task["updated_at"] = now_iso()
    save_state(state_path, state)


def run_adapter(adapter_cmd: str, task_payload_path: Path, timeout_seconds: int) -> Dict[str, Any]:
    cmd_text = adapter_cmd.replace("{task_file}", task_payload_path.as_posix())
    proc = subprocess.run(
        cmd_text,
        shell=True,
        capture_output=True,
        text=True,
        timeout=max(30, int(timeout_seconds)),
    )
    return {
        "command": cmd_text,
        "exit_code": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coding gateway worker")
    parser.add_argument("--state", default="state/coding_gateway_tasks.json")
    parser.add_argument(
        "--adapter-cmd",
        default="",
        help="Adapter shell command template. Use {task_file} placeholder for task payload json path.",
    )
    parser.add_argument("--work-dir", default="state/coding_gateway_work")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--poll-interval-seconds", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state)
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    max_jobs = 1 if args.once else max(1, int(args.max_jobs))
    poll_interval_seconds = max(1, int(args.poll_interval_seconds))

    while processed < max_jobs:
        task = claim_task(state_path)
        if not task:
            if args.once:
                break
            time.sleep(poll_interval_seconds)
            continue

        task_id = str(task.get("task_id") or "")
        if not task_id:
            processed += 1
            continue

        payload_file = work_dir / f"{task_id}.json"
        write_json(payload_file, task)

        if not str(args.adapter_cmd).strip():
            persist_result(
                state_path,
                task_id,
                ok=False,
                result={
                    "error": "adapter_not_configured",
                    "message": "Set --adapter-cmd with {task_file} placeholder.",
                },
            )
            processed += 1
            continue

        try:
            adapter_result = run_adapter(str(args.adapter_cmd), payload_file, int(args.timeout_seconds))
            ok = int(adapter_result.get("exit_code", 1)) == 0
            persist_result(state_path, task_id, ok=ok, result=adapter_result)
        except subprocess.TimeoutExpired:
            persist_result(
                state_path,
                task_id,
                ok=False,
                result={
                    "error": "adapter_timeout",
                    "timeout_seconds": int(args.timeout_seconds),
                },
            )

        processed += 1

    print(f"coding_worker_processed={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
