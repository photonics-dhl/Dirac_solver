#!/usr/bin/env python3
"""Lightweight execution bus worker for Dirac automation.

Consumes queued tasks from state/dirac_exec_queue.json, executes dispatcher,
and writes deterministic ACK status back to queue + bridge state.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE = REPO_ROOT / "state" / "dirac_exec_queue.json"
DEFAULT_BRIDGE = REPO_ROOT / "state" / "copilot_openclaw_bridge.json"
DEFAULT_DISPATCH = REPO_ROOT / "scripts" / "dispatch_dirac_task.py"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return dict(fallback)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def parse_timestamp(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


@contextmanager
def file_lock(lock_path: Path, timeout_seconds: float = 8.0):
    start = time.time()
    acquired_fd: Optional[int] = None
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


def ensure_queue(payload: Dict[str, Any]) -> Dict[str, Any]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    payload["tasks"] = tasks
    payload["updated_at"] = str(payload.get("updated_at") or now_iso())
    return payload


def parse_kv_lines(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for line in (text or "").splitlines():
        idx = line.find("=")
        if idx <= 0:
            continue
        key = line[:idx].strip()
        value = line[idx + 1 :].strip()
        if key:
            result[key] = value
    return result


def parse_phase_stream(kv: Dict[str, str]) -> List[Dict[str, Any]]:
    raw_json = str(kv.get("phase_stream_json") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except Exception:
            pass

    report_path = str(kv.get("dispatch_report") or "").strip()
    if report_path:
        report = read_json(Path(report_path), {})
        phase_stream = report.get("phase_stream")
        if isinstance(phase_stream, list):
            return [item for item in phase_stream if isinstance(item, dict)]

    return []


def queue_depth(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    depth = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for item in tasks:
        status = str(item.get("status") or "queued")
        if status not in depth:
            continue
        depth[status] += 1
    return depth


def try_claim_task(queue_path: Path, stale_running_seconds: int) -> Optional[Dict[str, Any]]:
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    with file_lock(lock_path):
        queue_payload = ensure_queue(read_json(queue_path, {"tasks": []}))
        tasks = queue_payload.get("tasks") or []
        now_ts = time.time()

        for item in tasks:
            # Backward-compatibility normalization: reviewer-gated failures are
            # retried until max attempts, never treated as done.
            if str(item.get("status") or "") == "failed":
                ack = item.get("ack") if isinstance(item.get("ack"), dict) else {}
                if str(ack.get("dispatch_status") or "") == "blocked_reviewer_gate":
                    attempts = int(item.get("attempts") or 0)
                    max_attempts = int(item.get("max_attempts") or 3)
                    if attempts < max_attempts:
                        item["status"] = "queued"
                        item["available_at"] = now_iso()
                        item["last_error"] = "blocked_reviewer_gate_auto_retry"
                    item["updated_at"] = now_iso()

        for item in tasks:
            status = str(item.get("status") or "")
            if status != "running":
                continue
            started_ts = parse_timestamp(str(item.get("started_at") or ""))
            max_attempts = int(item.get("max_attempts") or 3)
            attempts = int(item.get("attempts") or 0)
            if started_ts > 0 and (now_ts - started_ts) > stale_running_seconds and attempts < max_attempts:
                item["status"] = "queued"
                item["available_at"] = now_iso()
                item["last_error"] = f"worker_stale_timeout_after_{stale_running_seconds}s"
                item["updated_at"] = now_iso()

        claimed: Optional[Dict[str, Any]] = None
        for item in tasks:
            status = str(item.get("status") or "queued")
            if status != "queued":
                continue
            available_at = str(item.get("available_at") or "")
            available_ts = parse_timestamp(available_at)
            if available_ts > 0 and available_ts > now_ts:
                continue

            attempts = int(item.get("attempts") or 0)
            item["attempts"] = attempts + 1
            item["status"] = "running"
            item["started_at"] = now_iso()
            item["updated_at"] = now_iso()
            item["worker"] = {
                "pid": os.getpid(),
                "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
            }
            claimed = dict(item)
            break

        queue_payload["updated_at"] = now_iso()
        write_json(queue_path, queue_payload)
        return claimed


def complete_task(
    queue_path: Path,
    task_id: str,
    status: str,
    ack: Dict[str, Any],
    retry_after_seconds: int,
    max_attempts: int,
) -> Dict[str, Any]:
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    with file_lock(lock_path):
        queue_payload = ensure_queue(read_json(queue_path, {"tasks": []}))
        tasks = queue_payload.get("tasks") or []
        updated_task: Dict[str, Any] = {}
        for item in tasks:
            if str(item.get("task_id") or "") != task_id:
                continue
            attempts = int(item.get("attempts") or 0)
            retryable = bool(ack.get("retryable", False)) and attempts < max_attempts
            if retryable:
                item["status"] = "queued"
                item["available_at"] = datetime.fromtimestamp(time.time() + max(1, retry_after_seconds), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                item["last_error"] = str(ack.get("failure_reason") or ack.get("dispatch_status") or "retryable_failure")
            else:
                dispatch_status = str(ack.get("dispatch_status") or "").strip().lower()
                if status == "failed" and dispatch_status in {"auto_repairing", "blocked_reviewer_gate", "input_contract_invalid", "execution_failed", "blocked_permissions"}:
                    item["status"] = "done"
                    item["last_error"] = "auto_repair_pending_followup"
                else:
                    item["status"] = status
            item["completed_at"] = now_iso()
            item["updated_at"] = now_iso()
            item["ack"] = ack
            updated_task = dict(item)
            break

        queue_payload["updated_at"] = now_iso()
        write_json(queue_path, queue_payload)
        return {
            "task": updated_task,
            "depth": queue_depth(tasks),
        }


def update_bridge(bridge_path: Path, ack_payload: Dict[str, Any]) -> None:
    bridge = read_json(bridge_path, {})
    bridge["updated_at"] = now_iso()
    bridge["handshake_status"] = "synced_with_copilot"
    bus = bridge.get("execution_bus")
    if not isinstance(bus, dict):
        bus = {}
        bridge["execution_bus"] = bus
    bus["last_worker_seen_at"] = now_iso()
    bus["last_task"] = ack_payload
    write_json(bridge_path, bridge)


def run_dispatch(task: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    task_text = str(task.get("task") or "Dirac_solver 调试")
    source = str(task.get("source") or "queue-worker")
    cmd = [
        sys.executable,
        args.dispatch_script,
        "--task",
        task_text,
        "--source",
        source,
        "--execute",
        "--auto-execute-replan",
        "--api-base",
        args.api_base,
        "--harness-base",
        args.harness_base,
        "--sync-state",
        args.sync_state,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=max(30, int(args.dispatch_timeout_seconds)),
        )
        kv = parse_kv_lines(proc.stdout)
        dispatch_status = str(kv.get("dispatch_status") or "unknown")
        failure_reason = str(kv.get("failure_reason") or "")
        human_status = str(kv.get("human_status") or "")
        phase_stream = parse_phase_stream(kv)
        phase_stream_compact = str(kv.get("phase_stream") or "")
        workflow_state = str(kv.get("workflow_state") or "UNKNOWN").upper()
        # blocked_reviewer_gate means orchestration ran and hit strict reviewer gate;
        # this is an execution outcome, not a worker startup failure.
        program_started = dispatch_status in {
            "success",
            "blocked_reviewer_gate",
            "execution_failed",
            "blocked_permissions",
            "input_contract_invalid",
            "ok",
            "executed",
        }
        retryable = dispatch_status in {"execution_failed", "blocked_permissions", "unknown", "input_contract_invalid", "auto_repairing"}
        if dispatch_status == "blocked_reviewer_gate" or workflow_state in {"REPLAN", "RETRY_WAIT", "ESCALATING"}:
            retryable = True
        return {
            "ok": proc.returncode == 0,
            "program_started": program_started,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "dispatch_status": dispatch_status,
            "failure_reason": failure_reason,
            "human_status": human_status,
            "phase_stream": phase_stream,
            "phase_stream_compact": phase_stream_compact,
            "dispatch_report": str(kv.get("dispatch_report") or ""),
            "assignee": str(kv.get("assignee") or ""),
            "action": str(kv.get("action") or ""),
            "preflight_ready": str(kv.get("preflight_ready") or ""),
            "execution_exit_code": str(kv.get("execution_exit_code") or ""),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "workflow_state": workflow_state,
            "retryable": retryable and proc.returncode != 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "program_started": False,
            "command": " ".join(cmd),
            "exit_code": 124,
            "dispatch_status": "execution_failed",
            "failure_reason": f"worker_dispatch_timeout_after_{int(args.dispatch_timeout_seconds)}s",
            "human_status": "AUTO_REPAIRING_EXECUTION",
            "phase_stream": [],
            "phase_stream_compact": "",
            "dispatch_report": "",
            "assignee": "",
            "action": "",
            "preflight_ready": "",
            "execution_exit_code": "",
            "stdout": "",
            "stderr": "",
            "retryable": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dirac execution queue worker")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE), help="Queue state file path")
    parser.add_argument("--bridge", default=str(DEFAULT_BRIDGE), help="Bridge state file path")
    parser.add_argument("--dispatch-script", default=str(DEFAULT_DISPATCH), help="Dispatch script path")
    parser.add_argument("--sync-state", default=str(REPO_ROOT / "state" / "dirac_solver_progress_sync.json"))
    parser.add_argument("--api-base", default="http://127.0.0.1:3001")
    parser.add_argument("--harness-base", default="http://127.0.0.1:8001")
    parser.add_argument("--max-jobs", type=int, default=6)
    parser.add_argument("--stale-running-seconds", type=int, default=240)
    parser.add_argument("--retry-backoff-seconds", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--dispatch-timeout-seconds", type=int, default=1200)
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit")
    args = parser.parse_args()

    queue_path = Path(args.queue)
    bridge_path = Path(args.bridge)
    processed = 0

    max_jobs = 1 if args.once else max(1, int(args.max_jobs))
    while processed < max_jobs:
        task = try_claim_task(queue_path, stale_running_seconds=max(30, int(args.stale_running_seconds)))
        if not task:
            break

        task_id = str(task.get("task_id") or "")
        if not task_id:
            processed += 1
            continue

        ack = run_dispatch(task, args)
        dispatch_status = str(ack.get("dispatch_status") or "unknown")
        started = bool(ack.get("program_started", False))
        workflow_state = str(ack.get("workflow_state") or "UNKNOWN").upper()
        final_status = "done" if (dispatch_status in {"success", "ok", "executed", "auto_repairing"} and workflow_state in {"DONE", "REPLAN", "RETRY_WAIT", "ESCALATING", "FAILED", "UNKNOWN"}) else "failed"
        completion = complete_task(
            queue_path,
            task_id=task_id,
            status=final_status,
            ack=ack,
            retry_after_seconds=max(5, int(args.retry_backoff_seconds)) * max(1, int(task.get("attempts") or 1)),
            max_attempts=max(1, int(args.max_attempts)),
        )

        update_bridge(
            bridge_path,
            {
                "task_id": task_id,
                "status": str(completion.get("task", {}).get("status") or final_status),
                "attempts": int(completion.get("task", {}).get("attempts") or 0),
                "dispatch_status": str(ack.get("dispatch_status") or "unknown"),
                "failure_reason": str(ack.get("failure_reason") or ""),
                "human_status": str(ack.get("human_status") or ""),
                "phase_stream": ack.get("phase_stream") if isinstance(ack.get("phase_stream"), list) else [],
                "phase_stream_compact": str(ack.get("phase_stream_compact") or ""),
                "dispatch_report": str(ack.get("dispatch_report") or ""),
                "queued_depth": completion.get("depth") or {},
                "completed_at": now_iso(),
            },
        )
        processed += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


