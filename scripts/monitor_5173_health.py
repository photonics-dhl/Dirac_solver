#!/usr/bin/env python3
"""Persistent health monitor for 10.72.212.33:5173."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "state" / "monitor_5173_state.json"
LOG_PATH = REPO_ROOT / "logs" / "monitor_5173_health.log"
TARGET_URL = os.getenv("DIRAC_5173_MONITOR_URL", "http://10.72.212.33:5173")
INTERVAL_SECONDS = max(5, int(os.getenv("DIRAC_5173_MONITOR_INTERVAL_SECONDS", "15")))
TIMEOUT_SECONDS = max(2, int(os.getenv("DIRAC_5173_MONITOR_TIMEOUT_SECONDS", "5")))
HISTORY_LIMIT = max(10, int(os.getenv("DIRAC_5173_MONITOR_HISTORY_LIMIT", "200")))


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


def check_once() -> tuple[bool, int, int, str]:
    req = Request(TARGET_URL, method="GET")
    start = time.time()
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            latency = int((time.time() - start) * 1000)
            code = int(getattr(resp, "status", 0) or 0)
            ok = 200 <= code < 500
            return ok, code, latency, ""
    except HTTPError as exc:
        latency = int((time.time() - start) * 1000)
        code = int(getattr(exc, "code", 0) or 0)
        ok = 200 <= code < 500
        return ok, code, latency, str(exc)
    except URLError as exc:
        latency = int((time.time() - start) * 1000)
        return False, 0, latency, str(exc)
    except Exception as exc:
        latency = int((time.time() - start) * 1000)
        return False, 0, latency, str(exc)


def main() -> int:
    while True:
        ts = now_iso()
        ok, code, latency_ms, error = check_once()

        state = read_json(STATE_PATH)
        history = state.get("history") if isinstance(state.get("history"), list) else []
        history.append(
            {
                "ts": ts,
                "ok": bool(ok),
                "status_code": code,
                "latency_ms": latency_ms,
                "error": error,
            }
        )
        history = history[-HISTORY_LIMIT:]

        state.update(
            {
                "updated_at": ts,
                "target_url": TARGET_URL,
                "interval_seconds": INTERVAL_SECONDS,
                "timeout_seconds": TIMEOUT_SECONDS,
                "last": history[-1],
                "history": history,
            }
        )
        write_json(STATE_PATH, state)

        status_text = "UP" if ok else "DOWN"
        append_log(f"{ts} monitor_5173 status={status_text} code={code} latency_ms={latency_ms} err={error}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
