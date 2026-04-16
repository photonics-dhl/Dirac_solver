#!/usr/bin/env python3
"""Minimal coding adapter stub for coding gateway bring-up.

This adapter proves the gateway->worker->adapter path is healthy.
Replace with a real coding executor adapter for production usage.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Coding adapter stub")
    parser.add_argument("--task-file", required=True, help="Gateway task payload file path")
    args = parser.parse_args()

    task_path = Path(args.task_file)
    payload = read_json(task_path)
    task_id = str(payload.get("task_id") or "unknown")
    intent = str((payload.get("request") or {}).get("intent_type") or "unknown")

    print(f"adapter=stub")
    print(f"task_id={task_id}")
    print(f"intent_type={intent}")
    print(f"finished_at={now_iso()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
