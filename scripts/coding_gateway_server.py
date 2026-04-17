#!/usr/bin/env python3
"""Lightweight coding gateway service for asynchronous coding task submission."""

from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


class TaskStore:
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self._lock = threading.Lock()

    def _load(self) -> Dict[str, Any]:
        payload = read_json(self.state_path)
        if not isinstance(payload, dict):
            payload = {}
        if not isinstance(payload.get("tasks"), dict):
            payload["tasks"] = {}
        return payload

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = now_iso()
        write_json(self.state_path, payload)

    def create_task(self, request: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            payload = self._load()
            task_id = f"CG-{utc_stamp()}"
            task = {
                "task_id": task_id,
                "state": "queued",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "request": request,
                "result": {},
            }
            payload["tasks"][task_id] = task
            self._save(payload)
            return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            payload = self._load()
            task = payload.get("tasks", {}).get(task_id)
            return dict(task) if isinstance(task, dict) else None


def make_handler(store: TaskStore):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, body: Dict[str, Any]) -> None:
            encoded = json.dumps(body, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._json(HTTPStatus.OK, {"ok": True, "time": now_iso()})
                return

            if parsed.path in {"/coding/status", "/coding/result"}:
                task_id = (parse_qs(parsed.query).get("task_id") or [""])[0].strip()
                if not task_id:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "task_id_required"})
                    return
                task = store.get_task(task_id)
                if not task:
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "task_not_found", "task_id": task_id})
                    return
                if parsed.path == "/coding/status":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "task_id": task_id,
                            "state": str(task.get("state") or "unknown"),
                            "updated_at": task.get("updated_at"),
                        },
                    )
                else:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "task_id": task_id,
                            "state": str(task.get("state") or "unknown"),
                            "result": task.get("result") or {},
                            "updated_at": task.get("updated_at"),
                        },
                    )
                return

            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "route_not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/coding/submit":
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "route_not_found"})
                return

            req = self._read_json()
            if not req:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json_payload"})
                return

            task = store.create_task(req)
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "task_id": task.get("task_id"),
                    "state": task.get("state"),
                    "created_at": task.get("created_at"),
                },
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run coding gateway HTTP service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8111)
    parser.add_argument(
        "--state",
        default="state/coding_gateway_tasks.json",
        help="Task state file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state)
    store = TaskStore(state_path)
    server = ThreadingHTTPServer((args.host, int(args.port)), make_handler(store))
    print(f"coding_gateway_listen=http://{args.host}:{int(args.port)}")
    print(f"coding_gateway_state={state_path.as_posix()}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
