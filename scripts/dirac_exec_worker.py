#!/usr/bin/env python3
"""Lightweight execution bus worker for Dirac automation.

Consumes queued tasks from state/dirac_exec_queue.json, executes dispatcher,
and writes deterministic ACK status back to queue + bridge state.
"""

from __future__ import annotations

import argparse
import hashlib
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
DEFAULT_WORKFLOW_SPEC = REPO_ROOT / "orchestration" / "execution_wake_state_machine.json"
DEFAULT_API_BASE = str(os.environ.get("DIRAC_API_BASE") or "http://127.0.0.1:3001").strip()
DEFAULT_HARNESS_BASE = str(os.environ.get("DIRAC_HARNESS_BASE") or "http://127.0.0.1:8001").strip()
DEFAULT_DISPATCH_TIMEOUT_SECONDS = max(60, int(os.environ.get("DIRAC_DISPATCH_TIMEOUT_SECONDS") or "1800"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        backup_path = path.with_suffix(path.suffix + ".bak")
        try:
            raw = backup_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return dict(fallback)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
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


def load_workflow_policy(path: Path) -> Dict[str, Any]:
    payload = read_json(path, {})
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict):
        policy = {}
    max_l0 = max(1, int(policy.get("max_attempts_l0") or 2))
    max_l1 = max(1, int(policy.get("max_attempts_l1") or 2))
    return {
        "max_attempts_l0": max_l0,
        "max_attempts_l1": max_l1,
        "max_attempts_worker": max(max_l0, max_l1),
        "retry_backoff_seconds": max(1, int(policy.get("retry_backoff_seconds") or 30)),
        "source": path.as_posix(),
    }


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


def compute_consistency_token(task_id: str, dispatch_status: str, reviewer_verdict: str) -> str:
    raw = f"{str(task_id or '').strip()}|{str(dispatch_status or '').strip()}|{str(reviewer_verdict or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _parse_unmet_conditions(value: Any) -> List[str]:
    return [
        part.strip()
        for part in str(value or "").split(",")
        if part.strip() and part.strip() != "-"
    ]


def _derive_sync_phase(ack_payload: Dict[str, Any]) -> str:
    dispatch_status = str(ack_payload.get("dispatch_status") or "unknown").strip().lower()
    workflow = ack_payload.get("workflow") if isinstance(ack_payload.get("workflow"), dict) else {}
    workflow_state = str(workflow.get("state") or "").strip().upper()

    if workflow_state == "DONE" or dispatch_status in {"success", "ok", "executed"}:
        return "DONE"
    if dispatch_status in {"blocked_reviewer_gate", "blocked_convergence_gate", "execution_failed", "blocked_permissions", "input_contract_invalid", "auto_repairing"}:
        return "REPAIRING"
    if workflow_state in {"REPLAN", "RETRY_WAIT", "ESCALATING"}:
        return "REPAIRING"
    return "IN_PROGRESS"


def enforce_consistency_contract(task_id: str, ack: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_status = str(ack.get("dispatch_status") or "unknown")
    reviewer_verdict = str(ack.get("reviewer_verdict") or "")
    token_task_id = str(ack.get("dispatch_task_id") or task_id)
    expected_token = compute_consistency_token(token_task_id, dispatch_status, reviewer_verdict)
    received_token = str(ack.get("consistency_token") or "").strip()
    if not received_token:
        ack["consistency_check"] = "legacy"
        ack["expected_consistency_token"] = expected_token
        return ack
    if received_token == expected_token:
        ack["consistency_check"] = "passed"
        return ack
    ack["consistency_check"] = "failed"
    ack["expected_consistency_token"] = expected_token
    ack["mismatch_reason"] = "consistency_token_mismatch"
    # Token mismatch means ACK may not belong to the expected task/result contract.
    ack["retryable"] = False
    return ack


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
            # Backward-compatibility normalization: historical workers marked
            # strict gate outcomes as failed even though execution had started.
            if str(item.get("status") or "") == "failed":
                ack = item.get("ack") if isinstance(item.get("ack"), dict) else {}
                if str(ack.get("dispatch_status") or "") in {"blocked_reviewer_gate", "blocked_convergence_gate"}:
                    attempts = int(item.get("attempts") or 0)
                    max_attempts = int(item.get("max_attempts") or 3)
                    if attempts < max_attempts:
                        item["status"] = "queued"
                        item["available_at"] = now_iso()
                        item["last_error"] = "strict_gate_auto_retry"
                    else:
                        item["status"] = "failed"
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
    lock_path = bridge_path.with_suffix(bridge_path.suffix + ".lock")
    with file_lock(lock_path):
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


def update_sync_state(sync_path: Path, ack_payload: Dict[str, Any]) -> None:
    lock_path = sync_path.with_suffix(sync_path.suffix + ".lock")
    with file_lock(lock_path):
        sync = read_json(sync_path, {})
        sync["updated_at"] = now_iso()

        bus = sync.get("execution_bus")
        if not isinstance(bus, dict):
            bus = {}
            sync["execution_bus"] = bus
        bus["last_worker_seen_at"] = now_iso()
        bus["last_task"] = {
            "task_id": str(ack_payload.get("task_id") or ""),
            "dispatch_status": str(ack_payload.get("dispatch_status") or "unknown"),
            "reviewer_verdict": str(ack_payload.get("reviewer_verdict") or ""),
            "retryable": bool(ack_payload.get("retryable", False)),
            "consistency_token": str(ack_payload.get("consistency_token") or ""),
            "consistency_check": str(ack_payload.get("consistency_check") or "legacy"),
            "mismatch_reason": str(ack_payload.get("mismatch_reason") or ""),
            "expected_consistency_token": str(ack_payload.get("expected_consistency_token") or ""),
            "convergence_gate": {
                "applied": to_bool(ack_payload.get("convergence_gate_applied")),
                "passed": to_bool(ack_payload.get("convergence_gate_passed")),
                "unmet": _parse_unmet_conditions(ack_payload.get("convergence_gate_unmet")),
            },
            "workflow": dict(ack_payload.get("workflow") or {}),
            "completed_at": str(ack_payload.get("completed_at") or now_iso()),
        }

        last_task = sync.get("last_task")
        if isinstance(last_task, dict):
            result = last_task.get("last_result")
            if not isinstance(result, dict):
                result = {}
                last_task["last_result"] = result
            result["status"] = str(ack_payload.get("dispatch_status") or result.get("status") or "unknown")
            result["human_status"] = str(ack_payload.get("human_status") or result.get("human_status") or "")
            result["failure_reason"] = str(ack_payload.get("failure_reason") or result.get("failure_reason") or "")
            result["reviewer_verdict"] = str(ack_payload.get("reviewer_verdict") or result.get("reviewer_verdict") or "")
            result["retryable"] = bool(ack_payload.get("retryable", result.get("retryable", False)))
            result["consistency_token"] = str(ack_payload.get("consistency_token") or result.get("consistency_token") or "")
            result["consistency_check"] = str(ack_payload.get("consistency_check") or result.get("consistency_check") or "legacy")
            result["mismatch_reason"] = str(ack_payload.get("mismatch_reason") or result.get("mismatch_reason") or "")
            result["expected_consistency_token"] = str(ack_payload.get("expected_consistency_token") or result.get("expected_consistency_token") or "")
            result["convergence_gate_applied"] = to_bool(ack_payload.get("convergence_gate_applied"))
            result["convergence_gate_passed"] = to_bool(ack_payload.get("convergence_gate_passed"))
            result["convergence_gate_unmet"] = _parse_unmet_conditions(ack_payload.get("convergence_gate_unmet"))

            multi_agent = last_task.get("multi_agent")
            if not isinstance(multi_agent, dict):
                multi_agent = {}
                last_task["multi_agent"] = multi_agent
            reviewer = multi_agent.get("reviewer")
            if not isinstance(reviewer, dict):
                reviewer = {}
                multi_agent["reviewer"] = reviewer
            reviewer["verdict"] = str(ack_payload.get("reviewer_verdict") or reviewer.get("verdict") or "")
            reviewer["dispatch_status_at_time_of_verdict"] = str(ack_payload.get("dispatch_status") or reviewer.get("dispatch_status_at_time_of_verdict") or "unknown")
            reviewer["consistency_checkpoint"] = str(ack_payload.get("consistency_token") or reviewer.get("consistency_checkpoint") or "")

        dispatch_status = str(ack_payload.get("dispatch_status") or "unknown")
        failure_reason = str(ack_payload.get("failure_reason") or "")
        retryable = bool(ack_payload.get("retryable", False))
        sync_phase = _derive_sync_phase(ack_payload)
        sync["phase"] = sync_phase
        sync["workflow"] = dict(ack_payload.get("workflow") or {})
        sync["last_action"] = {
            "by": "dirac_exec_worker",
            "at": now_iso(),
            "summary": f"worker ack: {dispatch_status}",
        }
        sync["last_result"] = {
            "status": dispatch_status,
            "human_status": str(ack_payload.get("human_status") or ""),
            "failure_reason": failure_reason,
            "reviewer_verdict": str(ack_payload.get("reviewer_verdict") or ""),
            "retryable": retryable,
            "consistency_token": str(ack_payload.get("consistency_token") or ""),
            "consistency_check": str(ack_payload.get("consistency_check") or "legacy"),
            "mismatch_reason": str(ack_payload.get("mismatch_reason") or ""),
            "expected_consistency_token": str(ack_payload.get("expected_consistency_token") or ""),
            "convergence_gate_applied": to_bool(ack_payload.get("convergence_gate_applied")),
            "convergence_gate_passed": to_bool(ack_payload.get("convergence_gate_passed")),
            "convergence_gate_unmet": _parse_unmet_conditions(ack_payload.get("convergence_gate_unmet")),
        }
        is_blocked = dispatch_status in {
            "blocked_reviewer_gate",
            "blocked_convergence_gate",
            "execution_failed",
            "blocked_permissions",
            "input_contract_invalid",
        }
        sync["blocked"] = {
            "is_blocked": is_blocked,
            "reason_code": dispatch_status if is_blocked else "none",
            "reason_detail": failure_reason if is_blocked else "",
        }
        if retryable:
            sync["next_action"] = {"by": "openclaw-supervisor", "todo": "retry_or_replan"}
        elif dispatch_status in {"success", "ok", "executed"}:
            sync["next_action"] = {"by": "supervisor", "todo": "wait_for_next_task"}
        elif dispatch_status == "blocked_convergence_gate":
            sync["next_action"] = {"by": "planner", "todo": "repair_convergence_unmet_conditions"}
        else:
            sync["next_action"] = {"by": "supervisor", "todo": "inspect_failure"}

        write_json(sync_path, sync)


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
        "--workflow-spec",
        args.workflow_spec,
    ]
    if args.auto_submit_coding:
        cmd.append("--auto-submit-coding")
    if str(args.coding_gateway_config).strip():
        cmd.extend(["--coding-gateway-config", str(args.coding_gateway_config)])
    if str(args.coding_gateway_url).strip():
        cmd.extend(["--coding-gateway-url", str(args.coding_gateway_url)])
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
        workflow_state = str(kv.get("workflow_state") or "UNKNOWN").upper()
        # blocked_reviewer_gate means orchestration ran and hit strict reviewer gate;
        # this is an execution outcome, not a worker startup failure.
        program_started = dispatch_status in {"blocked_reviewer_gate", "blocked_convergence_gate", "execution_failed", "blocked_permissions", "ok", "executed"}
        retryable = dispatch_status in {"execution_failed", "blocked_permissions", "unknown", "blocked_reviewer_gate", "blocked_convergence_gate"}
        retryable_from_dispatch = kv.get("retryable")
        if retryable_from_dispatch is not None:
            retryable = to_bool(retryable_from_dispatch)
        if workflow_state in {"REPLAN", "RETRY_WAIT", "ESCALATING"}:
            retryable = True
        return {
            "ok": proc.returncode == 0,
            "program_started": program_started,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "dispatch_status": dispatch_status,
            "dispatch_task_id": str(kv.get("dispatch_task_id") or ""),
            "human_status": str(kv.get("human_status") or ""),
            "failure_reason": failure_reason,
            "dispatch_report": str(kv.get("dispatch_report") or ""),
            "dispatch_receipt_json": str(kv.get("dispatch_receipt_json") or ""),
            "phase_stream_json": str(kv.get("phase_stream_json") or "[]"),
            "assignee": str(kv.get("assignee") or ""),
            "action": str(kv.get("action") or ""),
            "preflight_ready": str(kv.get("preflight_ready") or ""),
            "execution_exit_code": str(kv.get("execution_exit_code") or ""),
            "suite_verdict": str(kv.get("suite_verdict") or ""),
            "reviewer_verdict": str(kv.get("reviewer_verdict") or ""),
            "reviewer_issues_count": str(kv.get("reviewer_issues_count") or ""),
            "sources_verified": str(kv.get("sources_verified") or ""),
            "multimodal_evidence_count": str(kv.get("multimodal_evidence_count") or ""),
            "workflow_route": str(kv.get("workflow_route") or "L0"),
            "workflow_state": workflow_state,
            "workflow_event": str(kv.get("workflow_event") or ""),
            "workflow_next_route": str(kv.get("workflow_next_route") or kv.get("workflow_route") or "L0"),
            "plugin_gate_passed": str(kv.get("plugin_gate_passed") or ""),
            "skills_snapshot_json": str(kv.get("skills_snapshot_json") or ""),
            "loop_iteration_count": str(kv.get("loop_iteration_count") or ""),
            "loop_max_attempts": str(kv.get("loop_max_attempts") or ""),
            "retry_backoff_seconds": str(kv.get("retry_backoff_seconds") or ""),
            "consistency_token": str(kv.get("consistency_token") or ""),
            "mismatch_reason": str(kv.get("mismatch_reason") or ""),
            "expected_consistency_token": str(kv.get("expected_consistency_token") or ""),
            "convergence_gate_applied": str(kv.get("convergence_gate_applied") or "False"),
            "convergence_gate_passed": str(kv.get("convergence_gate_passed") or "False"),
            "convergence_gate_unmet": str(kv.get("convergence_gate_unmet") or "-"),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "retryable": retryable,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "program_started": False,
            "command": " ".join(cmd),
            "exit_code": 124,
            "dispatch_status": "execution_failed",
            "failure_reason": f"worker_dispatch_timeout_after_{int(args.dispatch_timeout_seconds)}s",
            "dispatch_report": "",
            "assignee": "",
            "action": "",
            "preflight_ready": "",
            "execution_exit_code": "",
            "workflow_route": "L0",
            "workflow_state": "RETRY_WAIT",
            "workflow_event": "TIMEOUT",
            "workflow_next_route": "L0",
            "convergence_gate_applied": "False",
            "convergence_gate_passed": "False",
            "convergence_gate_unmet": "-",
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
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--harness-base", default=DEFAULT_HARNESS_BASE)
    parser.add_argument("--max-jobs", type=int, default=6)
    parser.add_argument("--stale-running-seconds", type=int, default=240)
    parser.add_argument("--retry-backoff-seconds", type=int)
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--dispatch-timeout-seconds", type=int, default=DEFAULT_DISPATCH_TIMEOUT_SECONDS)
    parser.add_argument("--workflow-spec", default=str(DEFAULT_WORKFLOW_SPEC), help="Workflow state machine spec path")
    parser.add_argument("--auto-submit-coding", action="store_true", help="Forward L1 tasks to coding gateway through dispatcher")
    parser.add_argument("--coding-gateway-config", default=str(REPO_ROOT / "orchestration" / "coding_gateway_config.json"), help="Coding gateway config json path")
    parser.add_argument("--coding-gateway-url", default="", help="Optional coding gateway base url override")
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit")
    args = parser.parse_args()

    workflow_policy = load_workflow_policy(Path(args.workflow_spec))
    effective_retry_backoff = max(1, int(args.retry_backoff_seconds)) if args.retry_backoff_seconds is not None else int(workflow_policy.get("retry_backoff_seconds") or 30)
    effective_max_attempts = max(1, int(args.max_attempts)) if args.max_attempts is not None else int(workflow_policy.get("max_attempts_worker") or 2)

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

        update_bridge(
            bridge_path,
            {
                "task_id": task_id,
                "updated_at": now_iso(),
                "status": "running",
                "attempts": int(task.get("attempts") or 0),
                "dispatch_status": "running",
                "failure_reason": "",
                "dispatch_report": "",
                "workflow": {
                    "route": str(task.get("route") or "L0"),
                    "state": "EXEC_L0",
                    "event": "RETRY_DUE",
                    "next_route": str(task.get("route") or "L0"),
                    "policy_source": str(workflow_policy.get("source") or ""),
                },
                "queued_depth": {},
                "completed_at": "",
            },
        )

        ack = run_dispatch(task, args)
        ack = enforce_consistency_contract(task_id, ack)
        if str(ack.get("consistency_check") or "").strip().lower() == "failed":
            ack["dispatch_status"] = "execution_failed"
            if not str(ack.get("failure_reason") or "").strip():
                ack["failure_reason"] = str(ack.get("mismatch_reason") or "consistency_token_mismatch")
            ack["human_status"] = "CONSISTENCY_CHECK_FAILED"
            ack["workflow_state"] = "RETRY_WAIT"
            ack["workflow_event"] = "CONSISTENCY_FAIL"
            ack["retryable"] = False
        dispatch_status = str(ack.get("dispatch_status") or "unknown")
        workflow_state = str(ack.get("workflow_state") or "UNKNOWN").upper()
        final_status = "done" if (dispatch_status in {"success", "ok", "executed"} and workflow_state == "DONE") else "failed"
        completion = complete_task(
            queue_path,
            task_id=task_id,
            status=final_status,
            ack=ack,
            retry_after_seconds=max(5, effective_retry_backoff) * max(1, int(task.get("attempts") or 1)),
            max_attempts=effective_max_attempts,
        )

        sync_payload = {
            "task_id": task_id,
            "dispatch_status": str(ack.get("dispatch_status") or "unknown"),
            "human_status": str(ack.get("human_status") or ""),
            "failure_reason": str(ack.get("failure_reason") or ""),
            "reviewer_verdict": str(ack.get("reviewer_verdict") or ""),
            "retryable": bool(ack.get("retryable", False)),
            "consistency_token": str(ack.get("consistency_token") or ""),
            "consistency_check": str(ack.get("consistency_check") or "legacy"),
            "convergence_gate_applied": str(ack.get("convergence_gate_applied") or "False"),
            "convergence_gate_passed": str(ack.get("convergence_gate_passed") or "False"),
            "convergence_gate_unmet": str(ack.get("convergence_gate_unmet") or "-"),
            "workflow": {
                "route": str(ack.get("workflow_route") or "L0"),
                "state": str(ack.get("workflow_state") or "UNKNOWN"),
                "event": str(ack.get("workflow_event") or ""),
                "next_route": str(ack.get("workflow_next_route") or ack.get("workflow_route") or "L0"),
                "policy_source": str(workflow_policy.get("source") or ""),
            },
            "completed_at": now_iso(),
        }
        update_sync_state(Path(args.sync_state), sync_payload)

        update_bridge(
            bridge_path,
            {
                "task_id": task_id,
                "updated_at": now_iso(),
                "status": str(completion.get("task", {}).get("status") or final_status),
                "attempts": int(completion.get("task", {}).get("attempts") or 0),
                "dispatch_status": str(ack.get("dispatch_status") or "unknown"),
                "human_status": str(ack.get("human_status") or ""),
                "failure_reason": str(ack.get("failure_reason") or ""),
                "dispatch_report": str(ack.get("dispatch_report") or ""),
                "dispatch_receipt_json": str(ack.get("dispatch_receipt_json") or ""),
                "phase_stream_json": str(ack.get("phase_stream_json") or "[]"),
                "suite_verdict": str(ack.get("suite_verdict") or ""),
                "reviewer_verdict": str(ack.get("reviewer_verdict") or ""),
                "reviewer_issues_count": str(ack.get("reviewer_issues_count") or ""),
                "sources_verified": str(ack.get("sources_verified") or ""),
                "multimodal_evidence_count": str(ack.get("multimodal_evidence_count") or ""),
                "plugin_gate_passed": str(ack.get("plugin_gate_passed") or ""),
                "skills_snapshot_json": str(ack.get("skills_snapshot_json") or ""),
                "loop_iteration_count": str(ack.get("loop_iteration_count") or ""),
                "loop_max_attempts": str(ack.get("loop_max_attempts") or ""),
                "retry_backoff_seconds": str(ack.get("retry_backoff_seconds") or ""),
                "consistency_token": str(ack.get("consistency_token") or ""),
                "consistency_check": str(ack.get("consistency_check") or "legacy"),
                "expected_consistency_token": str(ack.get("expected_consistency_token") or ""),
                "mismatch_reason": str(ack.get("mismatch_reason") or ""),
                "convergence_gate_applied": str(ack.get("convergence_gate_applied") or "False"),
                "convergence_gate_passed": str(ack.get("convergence_gate_passed") or "False"),
                "convergence_gate_unmet": str(ack.get("convergence_gate_unmet") or "-"),
                "workflow": {
                    "route": str(ack.get("workflow_route") or "L0"),
                    "state": str(ack.get("workflow_state") or "UNKNOWN"),
                    "event": str(ack.get("workflow_event") or ""),
                    "next_route": str(ack.get("workflow_next_route") or ack.get("workflow_route") or "L0"),
                    "policy_source": str(workflow_policy.get("source") or ""),
                },
                "queued_depth": completion.get("depth") or {},
                "completed_at": now_iso(),
            },
        )
        processed += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


