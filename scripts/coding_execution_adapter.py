#!/usr/bin/env python3
"""Production adapter for coding gateway tasks.

This adapter executes real repository scripts based on coding task payloads
from the gateway and returns structured execution results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"
DEFAULT_SYNC_STATE = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def append_unique(values: List[str], item: str) -> List[str]:
    text = str(item or "").strip()
    if not text:
        return list(values)
    out = list(values)
    if text not in out:
        out.append(text)
    return out


def parse_kv(stdout: str) -> Dict[str, str]:
    kv: Dict[str, str] = {}
    for line in (stdout or "").splitlines():
        idx = line.find("=")
        if idx <= 0:
            continue
        key = line[:idx].strip()
        value = line[idx + 1 :].strip()
        if key:
            kv[key] = value
    return kv


def resolve_report_path(raw: str) -> Optional[Path]:
    text = str(raw or "").strip()
    if not text:
        return None

    direct = Path(text)
    if direct.exists():
        return direct

    marker = "/.openclaw/workspace/projects/Dirac/"
    if marker in text:
        suffix = text.split(marker, 1)[1]
        candidate = REPO_ROOT / Path(suffix)
        if candidate.exists():
            return candidate

    rel = REPO_ROOT / text
    if rel.exists():
        return rel

    if "/docs/harness_reports/" in text:
        name = text.rsplit("/", 1)[-1]
        report_candidate = DEFAULT_REPORT_DIR / name
        if report_candidate.exists():
            return report_candidate

    return None


def parse_flag_from_command(command_text: str, flag: str) -> Optional[str]:
    tokens: List[str] = []
    try:
        tokens = shlex.split(command_text, posix=True)
    except Exception:
        tokens = command_text.split()

    needle = f"--{flag}"
    for idx, token in enumerate(tokens):
        if token != needle:
            continue
        if idx + 1 < len(tokens):
            return tokens[idx + 1]
    return None


def infer_octopus_defaults_for_case(case_id: str) -> Tuple[str, str]:
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


def build_context(dispatch_report: Dict[str, Any]) -> Dict[str, str]:
    ctx: Dict[str, str] = {
        "api_base": os.environ.get("DIRAC_API_BASE", "http://127.0.0.1:3001"),
        "harness_base": os.environ.get("DIRAC_HARNESS_BASE", "http://127.0.0.1:8001"),
        "case_id": "hydrogen_gs_reference",
        "octopus_molecule": "H",
        "octopus_calc_mode": "gs",
        "max_iterations": "6",
    }

    stage_orch = (((dispatch_report.get("execution") or {}).get("stages") or {}).get("orchestration") or {})
    cmd = str(stage_orch.get("command") or "")
    if not cmd:
        cmd = str((dispatch_report.get("execution") or {}).get("command") or "")

    case_flag = parse_flag_from_command(cmd, "case-id")
    if case_flag:
        ctx["case_id"] = case_flag

    for flag_name, key in [
        ("api-base", "api_base"),
        ("harness-base", "harness_base"),
        ("max-iterations", "max_iterations"),
    ]:
        value = parse_flag_from_command(cmd, flag_name)
        if value:
            ctx[key] = value

    molecule_flag = parse_flag_from_command(cmd, "octopus-molecule")
    calc_mode_flag = parse_flag_from_command(cmd, "octopus-calc-mode")
    inferred_molecule, inferred_calc_mode = infer_octopus_defaults_for_case(ctx["case_id"])
    ctx["octopus_molecule"] = molecule_flag or inferred_molecule
    ctx["octopus_calc_mode"] = calc_mode_flag or inferred_calc_mode

    return ctx


def cmd(step: str, argv: List[str]) -> Dict[str, Any]:
    return {"step": step, "argv": argv}


def build_plan(task: Dict[str, Any], dispatch_report: Dict[str, Any], user_instruction: str, intent_type: str) -> List[Dict[str, Any]]:
    context = build_context(dispatch_report)
    reviewer_strict = str(os.environ.get("DIRAC_REVIEWER_STRICT", "0")).strip() == "1"

    packet_path = resolve_report_path(str(dispatch_report.get("replan_packet") or ""))
    if packet_path and packet_path.exists():
        return [
            cmd(
                "execute_replan_packet",
                [
                    sys.executable,
                    "scripts/execute_replan_packet.py",
                    "--packet",
                    packet_path.as_posix(),
                    "--state",
                    DEFAULT_SYNC_STATE.as_posix(),
                    "--api-base",
                    context["api_base"],
                    "--harness-base",
                    context["harness_base"],
                    "--case-id",
                    context["case_id"],
                    "--octopus-molecule",
                    context["octopus_molecule"],
                    "--octopus-calc-mode",
                    context["octopus_calc_mode"],
                    "--report-dir",
                    DEFAULT_REPORT_DIR.as_posix(),
                ],
            )
        ]

    action = str(dispatch_report.get("action") or "").strip()
    if action == "run_kb_collaboration" or intent_type == "knowledge_base_collaboration":
        orchestration_cmd = [
            sys.executable,
            "scripts/run_multi_agent_orchestration.py",
            "--api-base",
            context["api_base"],
            "--harness-base",
            context["harness_base"],
            "--case-id",
            context["case_id"],
            "--max-iterations",
            context["max_iterations"],
            "--octopus-molecule",
            context["octopus_molecule"],
            "--octopus-calc-mode",
            context["octopus_calc_mode"],
            "--skills-manifest",
            "orchestration/agent_skills_manifest.json",
        ]
        if reviewer_strict:
            orchestration_cmd.append("--strict")

        return [
            cmd(
                "build_research_kb",
                [
                    sys.executable,
                    "scripts/build_research_kb.py",
                    "--base-url",
                    context["harness_base"],
                    "--manifest",
                    "knowledge_base/corpus_manifest.json",
                ],
            ),
            cmd(
                "run_multi_agent_orchestration",
                orchestration_cmd,
            ),
        ]

    if action == "run_orchestration":
        orchestration_cmd = [
            sys.executable,
            "scripts/run_multi_agent_orchestration.py",
            "--api-base",
            context["api_base"],
            "--harness-base",
            context["harness_base"],
            "--case-id",
            context["case_id"],
            "--max-iterations",
            context["max_iterations"],
            "--octopus-molecule",
            context["octopus_molecule"],
            "--octopus-calc-mode",
            context["octopus_calc_mode"],
            "--skills-manifest",
            "orchestration/agent_skills_manifest.json",
        ]
        if reviewer_strict:
            orchestration_cmd.append("--strict")

        return [
            cmd(
                "run_multi_agent_orchestration",
                orchestration_cmd,
            )
        ]

    if intent_type == "dirac_full_debug":
        debug_cmd = [
            sys.executable,
            "scripts/run_dirac_debug_ops.py",
            "--mode",
            "full",
            "--task",
            user_instruction or "Dirac_solver 调试",
            "--source",
            "coding-gateway-adapter",
            "--timeout",
            "1200",
        ]
        # Keep default behavior stable; opt-in to heavy execute/replan mode.
        if str(os.environ.get("DIRAC_CODING_DEBUG_EXECUTE", "0")).strip() == "1":
            debug_cmd.extend(["--execute", "--auto-replan"])
        return [cmd("run_dirac_debug_ops", debug_cmd)]

    # Fallback path keeps this adapter useful for unknown intents.
    return [
        cmd(
            "dispatch_dirac_task",
            [
                sys.executable,
                "scripts/dispatch_dirac_task.py",
                "--task",
                user_instruction or str((task.get("request") or {}).get("task_id") or "Dirac_solver 调试"),
                "--source",
                "coding-gateway-adapter",
                "--execute",
                "--auto-execute-replan",
            ],
        )
    ]


def run_step(step: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    argv = list(step.get("argv") or [])
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=max(30, int(timeout_seconds)),
        check=False,
    )
    return {
        "step": str(step.get("step") or "unknown"),
        "command": " ".join(argv),
        "exit_code": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "kv": parse_kv(proc.stdout),
    }


def collect_artifacts(step_results: List[Dict[str, Any]]) -> List[str]:
    artifacts: List[str] = []
    for result in step_results:
        kv = result.get("kv") or {}
        if not isinstance(kv, dict):
            continue
        for key, value in kv.items():
            if not isinstance(value, str):
                continue
            if key.endswith("_json") or key.endswith("_md") or key.endswith("_report") or key.endswith("_packet"):
                artifacts.append(value)
    # Keep order and remove duplicates.
    seen: set[str] = set()
    output: List[str] = []
    for item in artifacts:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def update_sync_state_after_coding(
    sync_path: Path,
    task_id: str,
    ok: bool,
    adapter_result_path: Path,
    dispatch_report_path: Optional[Path],
    warnings: List[str],
) -> None:
    payload = read_json(sync_path)
    if not payload:
        return

    now = now_iso()
    last_task = payload.get("last_task") if isinstance(payload.get("last_task"), dict) else {}
    if not last_task:
        return

    last_result = last_task.get("last_result") if isinstance(last_task.get("last_result"), dict) else {}
    evidence = list(last_result.get("evidence") or []) if isinstance(last_result.get("evidence"), list) else []
    evidence = append_unique(evidence, adapter_result_path.as_posix())
    if dispatch_report_path:
        evidence = append_unique(evidence, dispatch_report_path.as_posix())

    last_result["evidence"] = evidence
    last_result["coding_gateway_result"] = {
        "task_id": task_id,
        "status": "succeeded" if ok else "repairing",
        "adapter_result_json": adapter_result_path.as_posix(),
        "warnings": list(warnings),
        "finished_at": now,
    }

    if ok:
        last_result["status"] = "success"
        last_task["phase"] = "DONE"
        last_task["blocked"] = {
            "is_blocked": False,
            "reason_code": "none",
            "reason_detail": "",
        }
        workflow = last_task.get("workflow") if isinstance(last_task.get("workflow"), dict) else {}
        if workflow:
            workflow["current"] = "DONE"
            workflow["last_event"] = "EXEC_SUCCESS"
            workflow["updated_at"] = now
            workflow["next_route"] = "L0"
            last_task["workflow"] = workflow
        payload["reviewer_verdict"] = "PASS_OR_PENDING"
        payload["contracts_passed"] = True
        payload["sync_state"] = "healthy"
        last_task["next_action"] = {
            "by": "supervisor",
            "todo": "wait for next Feishu instruction",
        }
    else:
        last_result["status"] = "auto_repairing"
        last_task["phase"] = "REPAIRING"
        last_task["blocked"] = {
            "is_blocked": True,
            "reason_code": "auto_repair_in_progress",
            "reason_detail": "adapter_nonzero_exit",
        }

    last_task["last_result"] = last_result
    last_task["last_action"] = {
        "by": "codex-executor",
        "at": now,
        "summary": f"coding gateway execution finished: {'success' if ok else 'repairing'}",
    }
    last_task["conversation_handoff"] = {
        "summary": f"status={last_result.get('status')}; phase={last_task.get('phase')}",
        "carry_over_required": not ok,
        "next_packet": adapter_result_path.as_posix(),
        "generated_at": now,
    }
    last_task["updated_at"] = now
    payload["last_task"] = last_task
    payload["updated_at"] = now
    write_json(sync_path, payload)


def is_strict_mode() -> bool:
    return str(os.environ.get("DIRAC_CODING_ADAPTER_STRICT", "0")).strip() == "1"


def is_soft_failure(step_name: str, result: Dict[str, Any]) -> Tuple[bool, str]:
    # Replan execution can fail due reviewer-gate business conditions while
    # the coding channel itself is healthy. Treat this as soft-failure by default.
    if step_name == "execute_replan_packet":
        kv = result.get("kv") if isinstance(result.get("kv"), dict) else {}
        if str(kv.get("replan_all_passed") or "").lower() == "false":
            return True, "replan_business_gate_failed"
    return False, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real coding execution adapter")
    parser.add_argument("--task-file", required=True, help="Gateway task payload file path")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="Timeout per step")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_path = Path(args.task_file)
    task_payload = read_json(task_path)

    task_id = str(task_payload.get("task_id") or "unknown")
    request = task_payload.get("request") if isinstance(task_payload.get("request"), dict) else {}
    intent_type = str(request.get("intent_type") or "unknown")
    user_instruction = str(request.get("user_instruction") or "").strip()

    dispatch_report_path = resolve_report_path(str(request.get("dispatch_report") or ""))
    dispatch_report = read_json(dispatch_report_path) if dispatch_report_path else {}

    plan = build_plan(task_payload, dispatch_report, user_instruction, intent_type)
    step_results: List[Dict[str, Any]] = []
    all_ok = True
    warnings: List[str] = []

    for step in plan:
        try:
            result = run_step(step, int(args.timeout_seconds))
        except subprocess.TimeoutExpired:
            result = {
                "step": str(step.get("step") or "unknown"),
                "command": " ".join(list(step.get("argv") or [])),
                "exit_code": 124,
                "stdout": "",
                "stderr": f"timeout_after_{int(args.timeout_seconds)}s",
                "kv": {},
            }
        step_results.append(result)
        if int(result.get("exit_code", 1)) != 0:
            soft, reason = is_soft_failure(str(result.get("step") or ""), result)
            if soft and not is_strict_mode():
                result["soft_failed"] = True
                result["soft_failure_reason"] = reason
                warnings.append(f"{str(result.get('step') or 'unknown')}: {reason}")
                continue
            all_ok = False
            break

    run_dir = REPO_ROOT / "state" / "coding_gateway_runs" / task_id
    run_dir.mkdir(parents=True, exist_ok=True)
    adapter_result = {
        "adapter": "coding_execution_adapter",
        "task_id": task_id,
        "intent_type": intent_type,
        "user_instruction": user_instruction,
        "task_file": task_path.as_posix(),
        "dispatch_report": dispatch_report_path.as_posix() if dispatch_report_path else "",
        "generated_at": now_iso(),
        "ok": all_ok,
        "plan": [{"step": s.get("step"), "command": " ".join(list(s.get("argv") or []))} for s in plan],
        "steps": step_results,
        "artifacts": collect_artifacts(step_results),
        "warnings": warnings,
        "run_dir": run_dir.as_posix(),
    }
    adapter_result_path = run_dir / "adapter_result.json"
    write_json(adapter_result_path, adapter_result)
    update_sync_state_after_coding(
        DEFAULT_SYNC_STATE,
        task_id=task_id,
        ok=all_ok,
        adapter_result_path=adapter_result_path,
        dispatch_report_path=dispatch_report_path,
        warnings=warnings,
    )

    print("adapter=real")
    print(f"task_id={task_id}")
    print(f"intent_type={intent_type}")
    print(f"dispatch_report={adapter_result['dispatch_report'] or '-'}")
    print(f"run_dir={adapter_result['run_dir']}")
    print(f"steps_executed={len(step_results)}")
    print(f"artifacts_count={len(adapter_result['artifacts'])}")
    print(f"adapter_result_json={adapter_result_path.as_posix()}")
    print(f"finished_at={now_iso()}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
