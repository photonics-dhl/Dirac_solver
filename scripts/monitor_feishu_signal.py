#!/usr/bin/env python3
"""Persistent monitor for Feishu-originated queue/sync signals."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = REPO_ROOT / "state" / "dirac_exec_queue.json"
SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
STATE_PATH = REPO_ROOT / "state" / "monitor_feishu_signal_state.json"
LOG_PATH = REPO_ROOT / "logs" / "monitor_feishu_signal.log"
INTERVAL_SECONDS = max(3, int(os.getenv("DIRAC_FEISHU_MONITOR_INTERVAL_SECONDS", "8")))
HISTORY_LIMIT = max(10, int(os.getenv("DIRAC_FEISHU_MONITOR_HISTORY_LIMIT", "200")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def append_log(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def latest_feishu_task(queue_data: dict) -> dict:
    tasks = queue_data.get("tasks") if isinstance(queue_data.get("tasks"), list) else []
    feishu_tasks = [t for t in tasks if isinstance(t, dict) and str(t.get("source", "")).startswith("feishu")]
    if not feishu_tasks:
        return {}
    feishu_tasks.sort(key=lambda t: str(t.get("updated_at") or t.get("created_at") or ""), reverse=True)
    return feishu_tasks[0]


def main() -> int:
    while True:
        ts = now_iso()
        queue_data = read_json(QUEUE_PATH)
        sync_data = read_json(SYNC_PATH)
        task = latest_feishu_task(queue_data)

        root_source = str(sync_data.get("source", ""))
        last_task = sync_data.get("last_task") if isinstance(sync_data.get("last_task"), dict) else {}
        last_task_source = str(last_task.get("source", ""))

        state = read_json(STATE_PATH)
        history = state.get("history") if isinstance(state.get("history"), list) else []
        snapshot = {
            "ts": ts,
            "latest_feishu_task_id": str(task.get("task_id", "")),
            "latest_feishu_status": str(task.get("status", "")),
            "latest_feishu_updated_at": str(task.get("updated_at", "")),
            "sync_root_source": root_source,
            "sync_last_task_source": last_task_source,
        }
        history.append(snapshot)
        history = history[-HISTORY_LIMIT:]

        state.update(
            {
                "updated_at": ts,
                "interval_seconds": INTERVAL_SECONDS,
                "last": snapshot,
                "history": history,
            }
        )
        write_json(STATE_PATH, state)

        append_log(
            f"{ts} feishu_signal task_id={snapshot['latest_feishu_task_id']} status={snapshot['latest_feishu_status']} "
            f"sync_root_source={root_source} sync_last_task_source={last_task_source}"
        )
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
