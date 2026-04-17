#!/usr/bin/env python3
"""Execute replan packet actions and persist handoff-ready artifacts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]


# feishu_notify for centralized Feishu status notifications
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from feishu_notify import notify_escalating
    from run_multi_agent_orchestration import update_status_dashboard
except ImportError:
    notify_escalating = None  # type: ignore
    update_status_dashboard = None


def _fire_and_forget_notify(func, timeout_seconds: float = 8.0, **kwargs):
    """Run a notification function in a background thread with timeout.
    Never blocks the caller. If it fails, we log but continue.
    """
    import threading

    def _run():
        try:
            func(**kwargs)
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)
DEFAULT_STATE_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        backup_path = path.with_suffix(path.suffix + ".bak")
        try:
            return json.loads(backup_path.read_text(encoding="utf-8"))
        except Exception:
            return {}


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


def resolve_packet_path(state_path: Path, packet_arg: str) -> Path:
    if packet_arg.strip():
        return Path(packet_arg)
    state = read_json(state_path)
    packet = (
        ((state.get("last_task") or {}).get("last_result") or {}).get("replan_packet")
        if isinstance(state, dict)
        else ""
    )
    packet_text = str(packet or "").strip()
    if not packet_text:
        raise FileNotFoundError("No replan packet found in state and --packet not provided")
    return Path(packet_text)


def map_action_to_command(action_text: str, args: argparse.Namespace) -> List[str]:
    text = action_text.lower()
    if "switch_harness_entrypoint_to_run_case" in text:
        return [
            sys.executable,
            "scripts/run_multi_agent_orchestration.py",
            "--api-base",
            args.api_base,
            "--harness-base",
            args.harness_base,
            "--case-id",
            args.case_id,
            "--max-iterations",
            "1",
            "--octopus-molecule",
            args.octopus_molecule,
            "--octopus-calc-mode",
            args.octopus_calc_mode,
            "--strict",
        ]
    if "validate_8001_8101_and_3001_before_iteration" in text:
        return [
            sys.executable,
            "scripts/check_agent_capability_health.py",
            "--report-dir",
            args.report_dir,
        ]
    if "increase_iteration_budget_and_refine_discretization" in text or "run_iterate_case_with_finer_grid_variant" in text:
        return [
            sys.executable,
            "scripts/run_harness_acceptance.py",
            "--base-url",
            args.harness_base,
            "--case-id",
            args.case_id,
            "--strict",
        ]
    if "run_kb_query_skill_with_alternate_query_and_top_k" in text or "require_minimum_source_diversity_before_pass" in text:
        return [
            sys.executable,
            "scripts/build_research_kb.py",
            "--base-url",
            args.harness_base,
            "--manifest",
            "knowledge_base/corpus_manifest.json",
        ]
    if "collect_browser_screenshot_and_http_probe_together" in text or "block_release_when_rendering_evidence_is_missing" in text:
        return [
            sys.executable,
            "scripts/run_multi_agent_orchestration.py",
            "--api-base",
            args.api_base,
            "--harness-base",
            args.harness_base,
            "--case-id",
            args.case_id,
            "--max-iterations",
            "1",
            "--octopus-molecule",
            args.octopus_molecule,
            "--octopus-calc-mode",
            args.octopus_calc_mode,
        ]
    if "request_manual_triage_and_new_strategy" in text:
        return [
            sys.executable,
            "scripts/run_multi_agent_orchestration.py",
            "--api-base",
            args.api_base,
            "--harness-base",
            args.harness_base,
            "--case-id",
            args.case_id,
            "--max-iterations",
            "1",
            "--octopus-molecule",
            args.octopus_molecule,
            "--octopus-calc-mode",
            args.octopus_calc_mode,
            "--strict",
        ]
    if "accuracy gate failed" in text or "harness" in text:
        return [
            sys.executable,
            "scripts/run_harness_acceptance.py",
            "--base-url",
            args.harness_base,
            "--case-id",
            args.case_id,
            "--strict",
        ]
    if "kb richness" in text or "ingest" in text or "retrieval" in text:
        return [
            sys.executable,
            "scripts/build_research_kb.py",
            "--base-url",
            args.harness_base,
            "--manifest",
            "knowledge_base/corpus_manifest.json",
        ]
    if "octopus" in text:
        return [
            sys.executable,
            "scripts/run_octopus_first_principles_case.py",
            "--api-base",
            args.api_base,
            "--harness-base",
            args.harness_base,
            "--simple-case",
            args.case_id,
            "--molecule",
            args.octopus_molecule,
            "--calc-mode",
            args.octopus_calc_mode,
            "--strict",
        ]
    return []


def infer_octopus_defaults_for_case(case_id: str) -> tuple[str, str]:
    case_key = str(case_id or "").strip().lower()
    molecule = "H2"
    calc_mode = "gs"
    if case_key.startswith("h2o"):
        molecule = "H2O"
    elif case_key.startswith("hydrogen") or case_key.startswith("h_"):
        molecule = "H"
    elif case_key.startswith("h2"):
        molecule = "H2"
    if any(token in case_key for token in ("tddft", "absorption", "dipole", "radiation", "eels", "casida", "rt")):
        calc_mode = "td"
    return molecule, calc_mode


def was_cli_flag_provided(flag: str) -> bool:
    needle = str(flag or "").strip()
    if not needle:
        return False
    for token in sys.argv[1:]:
        if token == needle or token.startswith(f"{needle}="):
            return True
    return False


def execute_actions(packet: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    actions = packet.get("actions") or []
    updated_actions: List[Dict[str, Any]] = []
    runs: List[Dict[str, Any]] = []
    all_passed = True
    unmapped_count = 0
    executed_count = 0

    if not actions:
        all_passed = False

    for item in actions:
        action = dict(item) if isinstance(item, dict) else {"action": str(item)}
        action_text = str(action.get("action") or "")
        command = map_action_to_command(action_text, args)
        if not command:
            action["status"] = "skipped"
            action["note"] = "no command mapping"
            updated_actions.append(action)
            unmapped_count += 1
            all_passed = False
            continue

        try:
            proc = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout per action to prevent indefinite blocking
                check=False,
            )
        except subprocess.TimeoutExpired:
            action["status"] = "timeout"
            action["exit_code"] = 124
            updated_actions.append(action)
            executed_count += 1
            runs.append({
                "action": action_text,
                "command": " ".join(command),
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Action timed out after 300s",
            })
            all_passed = False
            continue
        ok = proc.returncode == 0
        action["status"] = "done" if ok else "failed"
        action["exit_code"] = proc.returncode
        updated_actions.append(action)
        executed_count += 1
        runs.append(
            {
                "action": action_text,
                "command": " ".join(command),
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        )
        if not ok:
            all_passed = False

    return {
        "updated_actions": updated_actions,
        "runs": runs,
        "all_passed": all_passed,
        "stats": {
            "total_actions": len(actions),
            "executed_actions": executed_count,
            "unmapped_actions": unmapped_count,
        },
    }


def update_state(state_path: Path, packet_path: Path, report_path: Path, all_passed: bool) -> None:
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with file_lock(lock_path):
        state = read_json(state_path)
        last_task = state.get("last_task") if isinstance(state, dict) else None
        if not isinstance(last_task, dict):
            return
        last_task["phase"] = "REVIEWING" if all_passed else "ESCALATING"
        last_task["next_action"] = {
            "by": "supervisor",
            "todo": "rerun dispatch verification" if all_passed else "run external assist from escalation packet",
        }
        last_result = last_task.get("last_result") if isinstance(last_task.get("last_result"), dict) else {}
        last_result["replan_execution_report"] = report_path.as_posix()
        last_result["replan_packet"] = packet_path.as_posix()
        last_task["last_result"] = last_result
        last_task["conversation_handoff"] = {
            "summary": f"replan_executed={'true' if all_passed else 'false'}",
            "carry_over_required": True,
            "next_packet": report_path.as_posix(),
            "generated_at": now_iso(),
        }
        last_task["updated_at"] = now_iso()
        state["last_task"] = last_task
        state["updated_at"] = now_iso()
        write_json(state_path, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute actions from a replan packet.")
    parser.add_argument("--packet", default="", help="Path to replan packet json. If empty, read from state.")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="Progress sync state path.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Output directory for replan execution report.")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001")
    parser.add_argument("--harness-base", default="http://127.0.0.1:8001")
    parser.add_argument("--case-id", default="hydrogen_gs_reference")
    parser.add_argument("--octopus-molecule", default="H2")
    parser.add_argument("--octopus-calc-mode", default="gs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inferred_molecule, inferred_calc_mode = infer_octopus_defaults_for_case(args.case_id)
    if not was_cli_flag_provided("--octopus-molecule"):
        args.octopus_molecule = inferred_molecule
    if not was_cli_flag_provided("--octopus-calc-mode"):
        args.octopus_calc_mode = inferred_calc_mode

    state_path = Path(args.state)
    packet_path = resolve_packet_path(state_path, args.packet)
    packet = read_json(packet_path)
    if not packet:
        raise RuntimeError(f"Invalid or empty packet: {packet_path.as_posix()}")

    # Feishu: ESCALATING notification — replan packet execution started
    # Use fire-and-forget to avoid blocking on slow Feishu API
    if notify_escalating is not None:
        task_id = str(packet.get("task_id") or args.case_id or "")
        failure_type = str(packet.get("failure_type") or "")
        blocker = str(packet.get("blocker") or "")
        _fire_and_forget_notify(
            notify_escalating,
            run_id=task_id,
            severity="high",
            blocker=(blocker or failure_type or "replan_triggered"),
        )
        if update_status_dashboard is not None:
            def _update_dashboard():
                try:
                    update_status_dashboard(
                        phase="REPLAN", run_id=task_id, case_id=str(args.case_id or "unknown"),
                        overall_pct=90, planner_done=True, executor_done=False, reviewer_done=False,
                        failure_reason=(blocker or failure_type or "replan_triggered"),
                        state_machine="L1",
                    )
                except Exception:
                    pass
            threading.Thread(target=_update_dashboard, daemon=True).start()

    exec_result = execute_actions(packet, args)
    packet["actions"] = exec_result["updated_actions"]
    packet["executed_at"] = now_iso()
    packet["all_passed"] = exec_result["all_passed"]
    packet["execution_stats"] = exec_result.get("stats") or {}
    write_json(packet_path, packet)

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"replan_execution_{utc_stamp()}.json"
    report_payload = {
        "timestamp": now_iso(),
        "packet": packet_path.as_posix(),
        "task_id": packet.get("task_id"),
        "all_passed": exec_result["all_passed"],
        "stats": exec_result.get("stats") or {},
        "runs": exec_result["runs"],
    }
    write_json(report_path, report_payload)

    update_state(state_path, packet_path, report_path, exec_result["all_passed"])

    print(f"replan_packet={packet_path.as_posix()}")
    print(f"replan_execution_report={report_path.as_posix()}")
    print(f"replan_all_passed={exec_result['all_passed']}")
    return 0 if exec_result["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
