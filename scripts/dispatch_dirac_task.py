#!/usr/bin/env python3
"""Dispatch Dirac tasks between Copilot/OpenClaw roles and trigger orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]

# feishu_notify for centralized Feishu status notifications
try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from feishu_notify import notify_received
    from run_multi_agent_orchestration import update_status_dashboard
except ImportError:
    notify_received = None  # type: ignore
    update_status_dashboard = None
DEFAULT_RULES = REPO_ROOT / "orchestration" / "task_dispatch_rules.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"
DEFAULT_POLICY = REPO_ROOT / "orchestration" / "openclaw_exec_policy.json"
# IMPORTANT: OpenClaw is deployed on the remote HPC server (CentOS 7).
# On Windows, access via RaiDrive CIFS mount: Z:\.openclaw = \\RaiDrive-Mac\SFTP\.openclaw
# DO NOT use local Windows path C:\Users\Mac\.openclaw (that doesn't exist on server).
DEFAULT_OPENCLAW_ROOT = r"\\RaiDrive-Mac\SFTP\.openclaw"
DEFAULT_SYNC_STATE = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_WORKFLOW_SPEC = REPO_ROOT / "orchestration" / "execution_wake_state_machine.json"
DEFAULT_CODING_GATEWAY_CONFIG = REPO_ROOT / "orchestration" / "coding_gateway_config.json"
DEFAULT_MANIFEST = REPO_ROOT / "knowledge_base" / "corpus_manifest.json"
DEFAULT_WORKFLOW_ROUTE = "L0"
DEFAULT_HARNESS_FALLBACK_BASE = "http://10.72.212.33:8101"
DEFAULT_API_BASE = str(os.environ.get("DIRAC_API_BASE") or "http://10.72.212.33:3004").strip()
DEFAULT_HARNESS_BASE = str(os.environ.get("DIRAC_HARNESS_BASE") or "http://10.72.212.33:8101").strip()
DEFAULT_EXEC_TIMEOUT_SECONDS = max(60, int(os.environ.get("DIRAC_EXEC_TIMEOUT_SECONDS") or "900"))


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


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def parse_inline_kv(text: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)", text or ""):
        key = str(match.group(1) or "").strip().lower()
        value = str(match.group(2) or "").strip()
        if key and value:
            pairs[key] = value
    return pairs


def infer_octopus_defaults_for_case(case_id: str) -> Tuple[str, str]:
    """Map case_id → (molecule, calc_mode) using atom/mode extraction."""
    case_key = str(case_id or "").strip().lower()
    molecule = "H2"
    calc_mode = "gs"

    # Atom extraction (handles any future atom symbol)
    ATOM_MOLECULE = {
        "h": "H", "he": "He", "he_pp": "He",
        "n": "N", "na": "Na", "k": "K", "cl": "Cl",
        "o": "O", "c": "C", "f": "F", "s": "S",
    }
    for atom_key, mol in ATOM_MOLECULE.items():
        if case_key.startswith(atom_key + "_") or case_key == atom_key:
            molecule = mol
            break

    # Calculation mode: TD if any td-related token present
    TD_TOKENS = {"td", "tddft", "td-dft", "casida", "absorption", "radiation", "eels", "rt"}
    calc_tokens = {tok for tok in case_key.replace("-", "_").split("_") if tok}
    if calc_tokens & TD_TOKENS or "td" in case_key:
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


def normalize_task_contract(task: str, source: str) -> Dict[str, Any]:
    raw = str(task or "").strip()
    compact = re.sub(r"\s+", " ", raw)
    compact_lower = compact.lower()
    if compact_lower in {"/auto", "auto", "自动", "自动调试", "自动执行"}:
        compact = f"Dirac_solver 调试 /auto {compact}".strip()
        compact_lower = compact.lower()

    compact = re.sub(
        r"(?i)^dirac_solver\s+调试\s+dirac_solver\s+调试\s+",
        "Dirac_solver 调试 ",
        compact,
    )
    if compact.lower().startswith("dirac_solver 调试"):
        compact = "Dirac_solver 调试" + compact[len("dirac_solver 调试"):]

    kv = parse_inline_kv(compact)
    is_auto = "/auto" in compact_lower or " auto" in compact_lower or str(source or "").lower().startswith("feishu")
    if is_auto:
        auto_defaults = {
            "workflow": "fullchain",
            "mode": "autonomous",
            "case": "hydrogen_gs_reference",
            "octopus": "required",
            "ncpus": "64",
            "mpiprocs": "64",
        }
        for key, value in auto_defaults.items():
            if not str(kv.get(key) or "").strip():
                kv[key] = value
                compact = f"{compact} {key}={value}".strip()
        compact_lower = compact.lower()
    run_id = str(kv.get("run_id") or kv.get("token") or "").strip()
    warnings: List[str] = []

    if not run_id:
        run_id = f"RSH-{utc_stamp()}"
        compact = f"{compact} run_id={run_id}".strip()
        warnings.append("run_id_missing_autofilled")

    workflow = str(kv.get("workflow") or "").strip().lower()
    if workflow and workflow not in {"fullchain", "orchestration", "kb", "replan", "status"}:
        warnings.append("workflow_unknown_value")

    # Auto-detect case ID from task text when not explicitly given
    # Uses a pattern-first approach for extensibility: atom + calcMode + postfix
    # New cases can be added by extending the pattern lists without code changes
    detected_case = str(kv.get("case") or "").strip()
    if not detected_case and not is_auto:
        import re as re_module

        # ── Pattern tables (extend here to add new cases) ──────────────────
        ATOM_MAP = {
            r"\bh\b": "H",
            r"\bhe\b": "He",
            r"\bn\b": "N",
            r"\bna\b": "Na",
            r"\bk\b": "K",
            r"\bcl\b": "Cl",
            r"\bo\b": "O",
            r"\bc\b": "C",
            r"\bf\b": "F",
            r"\bs\b": "S",
        }
        CALC_MAP = {
            r"_gs\b": "gs",
            r"_td\b": "td",
            r"_pp\b": "pp",
            r"\bgs\b": "gs",
            r"\btd\b": "td",
            r"\btddft\b": "td",
            r"\btd-dft\b": "td",
        }
        POSTFIX_MAP = {
            r"_reference\b": "reference",
            r"_official\b": "official",
            r"_nist\b": "nist",
            r"_pbe\b": "pbe",
            r"_lda\b": "lda",
        }

        def _best_match(text, table):
            matches = []
            for pat, val in table.items():
                if re_module.search(pat, text):
                    matches.append(val)
            return max(matches, key=len) if matches else ""

        atom = _best_match(compact_lower, ATOM_MAP)
        calc = _best_match(compact_lower, CALC_MAP)
        postfix = _best_match(compact_lower, POSTFIX_MAP)

        if atom:
            parts = [atom]
            if calc:
                parts.append(calc)
            if postfix:
                parts.append(postfix)
            detected_case = "_".join(parts)

        if not detected_case:
            # Fallback: scan for any known multi-token case name
            KNOWN_CASES = [
                "h_gs", "h_td", "h_pp",
                "he_gs", "he_td", "he_pp",
                "n_gs", "n_td", "n_pp",
                "h2_gs", "h2_td",
                "h2o_gs", "h2o_td", "h2o_pp",
                "ch4_gs", "ch4_td", "ch4_pp",
            ]
            for case in sorted(KNOWN_CASES, key=len, reverse=True):
                if re_module.search(r'\b' + re_module.escape(case) + r'\b', compact_lower):
                    detected_case = case
                    break

    return {
        "original": raw,
        "normalized": compact,
        "metadata": {
            "run_id": run_id,
            "workflow": workflow or "",
            "mode": str(kv.get("mode") or "").strip(),
            "case": detected_case,
            "octopus": str(kv.get("octopus") or "").strip(),
            "ncpus": str(kv.get("ncpus") or "").strip(),
            "mpiprocs": str(kv.get("mpiprocs") or "").strip(),
        },
        "warnings": warnings,
        "is_auto": is_auto,
    }


def to_human_status(status: str, executed: bool, failure_reason: str, auto_mode: bool = False) -> str:
    state = str(status or "").strip().lower()
    reason = str(failure_reason or "").strip().lower()
    if auto_mode and state in {"input_contract_invalid", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"}:
        if state == "input_contract_invalid":
            return "AUTO_REPAIRING_INPUT_CONTRACT"
        if state == "blocked_reviewer_gate":
            return "AUTO_REPAIRING_REVIEW"
        if state == "blocked_convergence_gate":
            return "AUTO_REPAIRING_CONVERGENCE"
        if state == "blocked_physics_result_missing":
            return "AUTO_REPAIRING_PHYSICS_RESULT"
        if state == "blocked_physics_mismatch":
            return "AUTO_REPAIRING_PHYSICS_MISMATCH"
        if state == "blocked_provenance_unverified":
            return "AUTO_REPAIRING_PROVENANCE"
        return "AUTO_REPAIRING_EXECUTION"
    if state == "input_contract_invalid":
        return "INPUT_CONTRACT_INCOMPLETE"
    if state == "blocked_plugin_gate":
        return "PLUGIN_GATE_BLOCKED"
    if state == "success":
        return "EXECUTED_SUCCESS"
    if state == "blocked_reviewer_gate":
        return "EXECUTED_AND_BLOCKED_BY_REVIEW"
    if state == "blocked_convergence_gate":
        return "EXECUTED_AND_BLOCKED_BY_CONVERGENCE"
    if state == "blocked_physics_result_missing":
        return "EXECUTED_AND_BLOCKED_BY_PHYSICS_RESULT"
    if state == "blocked_physics_mismatch":
        return "EXECUTED_AND_BLOCKED_BY_PHYSICS_MISMATCH"
    if state == "blocked_provenance_unverified":
        return "EXECUTED_AND_BLOCKED_BY_PROVENANCE"
    if state in {"execution_failed", "blocked_permissions"}:
        return "EXECUTED_AND_WAITING_REPLAN"
    if state in {"routed_only", "unknown"} and not executed:
        return "ROUTED_NOT_EXECUTED"
    if reason:
        return "EXECUTION_STATE_NEEDS_ATTENTION"
    return "DISPATCH_STATE_UNKNOWN"


def to_public_dispatch_status(status: str, auto_mode: bool) -> str:
    state = str(status or "").strip().lower()
    if auto_mode and state in {"input_contract_invalid", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"}:
        return "auto_repairing"
    return str(status or "unknown")


def to_public_failure_reason(status: str, failure_reason: str, auto_mode: bool) -> str:
    state = str(status or "").strip().lower()
    reason = str(failure_reason or "").strip()
    if auto_mode and state in {"input_contract_invalid", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"}:
        if state == "input_contract_invalid":
            return "auto_repair_input_contract"
        if state == "blocked_reviewer_gate":
            return "auto_repair_reviewer_gate"
        if state == "blocked_convergence_gate":
            return "auto_repair_convergence_gate"
        if state == "blocked_physics_result_missing":
            return "auto_repair_physics_result"
        if state == "blocked_physics_mismatch":
            return "auto_repair_physics_mismatch"
        if state == "blocked_provenance_unverified":
            return "auto_repair_provenance"
        if reason:
            return f"auto_repair_execution:{reason}"
        return "auto_repair_execution"
    return reason


def build_phase_stream(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = now_iso()
    status = str(report.get("status") or "unknown")
    executed = bool(report.get("executed"))
    human_status = str(report.get("human_status") or "")
    reason = str(report.get("public_failure_reason") or report.get("failure_reason") or "")
    auto_mode = bool(report.get("auto_policy_applied"))

    executing_state = "completed" if executed else "skipped"
    if status in {"execution_failed", "blocked_permissions"}:
        executing_state = "failed"
    if auto_mode and status in {"execution_failed", "blocked_permissions", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "input_contract_invalid"}:
        executing_state = "repairing"

    if status in {"blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
        reviewing_state = "repairing" if auto_mode else "failed"
    elif executed and status == "success":
        reviewing_state = "completed"
    elif executed:
        reviewing_state = "completed"
    else:
        reviewing_state = "skipped"

    queue_state = "queued"
    if status == "input_contract_invalid":
        queue_state = "blocked"
    elif status in {"success", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"}:
        queue_state = "dispatched"
    if auto_mode and status in {"input_contract_invalid", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"}:
        queue_state = "repairing"

    return [
        {
            "phase": "Trigger",
            "state": "completed",
            "at": str(report.get("timestamp") or now),
            "detail": f"source={str(report.get('source') or '-')}",
        },
        {
            "phase": "Queue",
            "state": queue_state,
            "at": now,
            "detail": f"assignee={str(report.get('assignee') or '-')}; action={str(report.get('action') or '-')}",
        },
        {
            "phase": "Executing",
            "state": executing_state,
            "at": now,
            "detail": "subprocess_executed" if executed else "execution_skipped",
        },
        {
            "phase": "Reviewing",
            "state": reviewing_state,
            "at": now,
            "detail": "reviewer_pass" if status == "success" else (
                "auto_repair_in_progress"
                if auto_mode
                else (
                    "reviewer_fail"
                    if status == "blocked_reviewer_gate"
                    else (
                        "physics_result_missing"
                        if status == "blocked_physics_result_missing"
                        else ("convergence_gate_failed" if status == "blocked_convergence_gate" else "review_not_required_or_skipped")
                    )
                )
            ),
        },
        {
            "phase": "Result",
            "state": "completed",
            "at": now,
            "detail": f"status={str(report.get('public_status') or status)}; human_status={human_status}; reason={reason or '-'}",
        },
    ]


def phase_stream_compact(phases: List[Dict[str, Any]]) -> str:
    return " | ".join(f"{str(item.get('phase') or '')}:{str(item.get('state') or '')}" for item in phases)


def route_task(text: str, rules: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str]:
    normalized = normalize(text)
    routing = rules.get("routing") or []
    for item in routing:
        keywords = [normalize(k) for k in (item.get("keywords") or [])]
        if any(k and k in normalized for k in keywords):
            return item, item.get("assignee", "openclaw-planner"), item.get("action", "prepare")

    fallback = {
        "name": "default",
        "assignee": rules.get("default_assignee", "openclaw-planner"),
        "action": "prepare",
    }
    return fallback, fallback["assignee"], fallback["action"]


def validate_command_contract(contract: Dict[str, Any], matched_rule: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(contract.get("metadata") or {})
    is_auto = bool(contract.get("is_auto"))
    rule_name = str(matched_rule.get("name") or "").strip().lower()

    required: List[str] = [] if rule_name == "resume_debug_session" else ["run_id"]
    if is_auto and rule_name == "dirac_full_debug":
        required.extend(["workflow", "mode", "case", "octopus", "ncpus", "mpiprocs"])

    missing = [key for key in required if not str(metadata.get(key) or "").strip()]
    return {
        "is_valid": len(missing) == 0,
        "required_fields": required,
        "missing_required_fields": missing,
        "blocking_reason": "missing_required_fields" if missing else "",
    }


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
        # Use direct write for network paths (Windows os.replace can't atomically
        # replace across network shares from a local temp file). On local paths,
        # os.replace is used for atomic semantics.
        try:
            os.replace(temp_path, path)
        except OSError:
            # Network share or cross-filesystem: write directly
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _merge_task_summary_into_root_sync(existing: Dict[str, Any], task_state: Dict[str, Any]) -> Dict[str, Any]:
    for key in [
        "task_id",
        "session_id",
        "user_instruction",
        "intent_type",
        "owner_role",
        "phase",
        "iteration",
        "routing",
        "last_action",
        "last_result",
        "blocked",
        "next_action",
        "source",
        "workflow",
        "conversation_handoff",
    ]:
        if key in task_state:
            existing[key] = task_state.get(key)
    return existing


def post_json(url: str, payload: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=max(3, int(timeout_seconds))) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def load_workflow_policy(path: Path) -> Dict[str, Any]:
    payload = read_json(path)
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict):
        policy = {}
    return {
        "max_attempts_l0": max(1, int(policy.get("max_attempts_l0") or 2)),
        "max_attempts_l1": max(1, int(policy.get("max_attempts_l1") or 2)),
        "retry_backoff_seconds": max(1, int(policy.get("retry_backoff_seconds") or 30)),
        "orchestration_timeout_seconds": max(30, int(policy.get("orchestration_timeout_seconds") or 900)),
        "kb_stage_timeout_seconds": max(120, int(policy.get("kb_stage_timeout_seconds") or 3600)),
        "kb_http_timeout_seconds": max(30, int(policy.get("kb_http_timeout_seconds") or 120)),
        "suite_stage_timeout_seconds": max(120, int(policy.get("suite_stage_timeout_seconds") or 1800)),
        "web_export_timeout_seconds": max(30, int(policy.get("web_export_timeout_seconds") or 600)),
        "auto_timeout_escalation_factor": max(1.1, float(policy.get("auto_timeout_escalation_factor") or 1.5)),
        "auto_timeout_increment_seconds": max(1, int(policy.get("auto_timeout_increment_seconds") or 30)),
        "auto_timeout_cap_seconds": max(60, int(policy.get("auto_timeout_cap_seconds") or 1800)),
        "escalate_l0_to_l1_if": [str(x) for x in (policy.get("escalate_l0_to_l1_if") or [])],
        "auto_loop_max_iterations": max(1, int(policy.get("auto_loop_max_iterations") or 3)),
        "auto_loop_retryable_statuses": [
            str(x).strip()
            for x in (policy.get("auto_loop_retryable_statuses") or ["blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"])
            if str(x).strip()
        ],
        "openclaw_autonomy_enabled": bool(policy.get("openclaw_autonomy_enabled", True)),
        "openclaw_action_switch_enabled": bool(policy.get("openclaw_action_switch_enabled", True)),
        "plugin_gate_required": bool(policy.get("plugin_gate_required", False)),
        "required_plugins": [str(x).strip() for x in (policy.get("required_plugins") or []) if str(x).strip()],
        "task_policy_overrides": dict(policy.get("task_policy_overrides") or {}),
        "source": path.as_posix(),
    }


def load_coding_gateway_config(path: Path) -> Dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        payload = {}
    return {
        "enabled": bool(payload.get("enabled", False)),
        "gateway_base_url": str(payload.get("gateway_base_url") or "http://127.0.0.1:8111").rstrip("/"),
        "submit_endpoint": str(payload.get("submit_endpoint") or "/coding/submit"),
        "submit_timeout_seconds": max(3, int(payload.get("submit_timeout_seconds") or 15)),
        "source": path.as_posix(),
    }


def submit_coding_task(
    gateway_cfg: Dict[str, Any],
    sync_state: Dict[str, Any],
    report: Dict[str, Any],
    report_path: Path,
) -> Dict[str, Any]:
    base = str(gateway_cfg.get("gateway_base_url") or "").rstrip("/")
    endpoint = str(gateway_cfg.get("submit_endpoint") or "/coding/submit")
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    submit_url = f"{base}{endpoint}"

    payload = {
        "source": "dispatch_dirac_task",
        "task_id": sync_state.get("task_id"),
        "intent_type": sync_state.get("intent_type"),
        "routing": sync_state.get("routing") or {},
        "user_instruction": sync_state.get("user_instruction"),
        "dispatch_report": report_path.as_posix(),
        "workflow": report.get("workflow") or {},
        "acceptance": {
            "status": report.get("status"),
            "failure_reason": report.get("failure_reason"),
        },
        "created_at": now_iso(),
    }
    response = post_json(
        submit_url,
        payload,
        timeout_seconds=int(gateway_cfg.get("submit_timeout_seconds") or 15),
    )
    return {
        "submitted": bool(response.get("ok", False)),
        "task_id": str(response.get("task_id") or ""),
        "state": str(response.get("state") or "unknown"),
        "submit_url": submit_url,
        "config_source": str(gateway_cfg.get("source") or ""),
    }


def resolve_workflow_policy(base_policy: Dict[str, Any], intent_name: str) -> Dict[str, Any]:
    """Merge base workflow policy with optional intent-specific overrides."""
    resolved = {
        "max_attempts_l0": max(1, int(base_policy.get("max_attempts_l0") or 2)),
        "max_attempts_l1": max(1, int(base_policy.get("max_attempts_l1") or 2)),
        "retry_backoff_seconds": max(1, int(base_policy.get("retry_backoff_seconds") or 30)),
        "orchestration_timeout_seconds": max(30, int(base_policy.get("orchestration_timeout_seconds") or 900)),
        "kb_stage_timeout_seconds": max(120, int(base_policy.get("kb_stage_timeout_seconds") or 3600)),
        "kb_http_timeout_seconds": max(30, int(base_policy.get("kb_http_timeout_seconds") or 120)),
        "suite_stage_timeout_seconds": max(120, int(base_policy.get("suite_stage_timeout_seconds") or 1800)),
        "web_export_timeout_seconds": max(30, int(base_policy.get("web_export_timeout_seconds") or 600)),
        "auto_timeout_escalation_factor": max(1.1, float(base_policy.get("auto_timeout_escalation_factor") or 1.5)),
        "auto_timeout_increment_seconds": max(1, int(base_policy.get("auto_timeout_increment_seconds") or 30)),
        "auto_timeout_cap_seconds": max(60, int(base_policy.get("auto_timeout_cap_seconds") or 1800)),
        "escalate_l0_to_l1_if": [str(x) for x in (base_policy.get("escalate_l0_to_l1_if") or [])],
        "auto_loop_max_iterations": max(1, int(base_policy.get("auto_loop_max_iterations") or 3)),
        "auto_loop_retryable_statuses": [
            str(x).strip()
            for x in (base_policy.get("auto_loop_retryable_statuses") or ["blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "blocked_permissions"])
            if str(x).strip()
        ],
        "openclaw_autonomy_enabled": bool(base_policy.get("openclaw_autonomy_enabled", True)),
        "openclaw_action_switch_enabled": bool(base_policy.get("openclaw_action_switch_enabled", True)),
        "plugin_gate_required": bool(base_policy.get("plugin_gate_required", False)),
        "required_plugins": [str(x).strip() for x in (base_policy.get("required_plugins") or []) if str(x).strip()],
        "source": str(base_policy.get("source") or DEFAULT_WORKFLOW_SPEC.as_posix()),
        "policy_override_for": None,
    }

    override_map = base_policy.get("task_policy_overrides")
    if isinstance(override_map, dict):
        override = override_map.get(str(intent_name or ""))
        if isinstance(override, dict):
            if override.get("max_attempts_l0") is not None:
                resolved["max_attempts_l0"] = max(1, int(override.get("max_attempts_l0")))
            if override.get("max_attempts_l1") is not None:
                resolved["max_attempts_l1"] = max(1, int(override.get("max_attempts_l1")))
            if override.get("retry_backoff_seconds") is not None:
                resolved["retry_backoff_seconds"] = max(1, int(override.get("retry_backoff_seconds")))
            if override.get("orchestration_timeout_seconds") is not None:
                resolved["orchestration_timeout_seconds"] = max(30, int(override.get("orchestration_timeout_seconds")))
            if override.get("kb_stage_timeout_seconds") is not None:
                resolved["kb_stage_timeout_seconds"] = max(120, int(override.get("kb_stage_timeout_seconds")))
            if override.get("kb_http_timeout_seconds") is not None:
                resolved["kb_http_timeout_seconds"] = max(30, int(override.get("kb_http_timeout_seconds")))
            if override.get("suite_stage_timeout_seconds") is not None:
                resolved["suite_stage_timeout_seconds"] = max(120, int(override.get("suite_stage_timeout_seconds")))
            if override.get("web_export_timeout_seconds") is not None:
                resolved["web_export_timeout_seconds"] = max(30, int(override.get("web_export_timeout_seconds")))
            if override.get("auto_timeout_escalation_factor") is not None:
                resolved["auto_timeout_escalation_factor"] = max(1.1, float(override.get("auto_timeout_escalation_factor")))
            if override.get("auto_timeout_increment_seconds") is not None:
                resolved["auto_timeout_increment_seconds"] = max(1, int(override.get("auto_timeout_increment_seconds")))
            if override.get("auto_timeout_cap_seconds") is not None:
                resolved["auto_timeout_cap_seconds"] = max(60, int(override.get("auto_timeout_cap_seconds")))
            if override.get("escalate_l0_to_l1_if") is not None:
                resolved["escalate_l0_to_l1_if"] = [str(x) for x in (override.get("escalate_l0_to_l1_if") or [])]
            if override.get("auto_loop_max_iterations") is not None:
                resolved["auto_loop_max_iterations"] = max(1, int(override.get("auto_loop_max_iterations")))
            if override.get("auto_loop_retryable_statuses") is not None:
                resolved["auto_loop_retryable_statuses"] = [
                    str(x).strip()
                    for x in (override.get("auto_loop_retryable_statuses") or [])
                    if str(x).strip()
                ]
            if override.get("openclaw_autonomy_enabled") is not None:
                resolved["openclaw_autonomy_enabled"] = bool(override.get("openclaw_autonomy_enabled"))
            if override.get("openclaw_action_switch_enabled") is not None:
                resolved["openclaw_action_switch_enabled"] = bool(override.get("openclaw_action_switch_enabled"))
            if override.get("plugin_gate_required") is not None:
                resolved["plugin_gate_required"] = bool(override.get("plugin_gate_required"))
            if override.get("required_plugins") is not None:
                resolved["required_plugins"] = [str(x).strip() for x in (override.get("required_plugins") or []) if str(x).strip()]
            resolved["policy_override_for"] = str(intent_name)

    return resolved


def route_tier(action: str) -> str:
    # Current runtime uses deterministic script-driven execution as default.
    if action in {"run_orchestration", "run_kb_collaboration"}:
        return "L0"
    return DEFAULT_WORKFLOW_ROUTE


def init_workflow_snapshot(action: str, workflow_policy: Dict[str, Any]) -> Dict[str, Any]:
    now = now_iso()
    tier = route_tier(action)
    return {
        "version": "v2",
        "current": "ROUTED",
        "route": tier,
        "attempts": {
            "l0": 0,
            "l1": 0,
        },
        "policy": {
            "max_attempts_l0": int(workflow_policy.get("max_attempts_l0") or 2),
            "max_attempts_l1": int(workflow_policy.get("max_attempts_l1") or 2),
            "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
            "escalate_l0_to_l1_if": list(workflow_policy.get("escalate_l0_to_l1_if") or []),
            "policy_override_for": workflow_policy.get("policy_override_for"),
            "source": str(workflow_policy.get("source") or DEFAULT_WORKFLOW_SPEC.as_posix()),
        },
        "history": [
            {
                "event": "TASK_SUBMITTED",
                "from": "NEW",
                "to": "VALIDATING",
                "at": now,
            },
            {
                "event": "TASK_VALID",
                "from": "VALIDATING",
                "to": "ROUTED",
                "at": now,
            },
        ],
        "last_event": "TASK_VALID",
        "updated_at": now,
    }


def append_workflow_event(workflow: Dict[str, Any], event: str, to_state: str) -> None:
    history = workflow.get("history")
    if not isinstance(history, list):
        history = []
        workflow["history"] = history
    current = str(workflow.get("current") or "UNKNOWN")
    payload = {
        "event": event,
        "from": current,
        "to": to_state,
        "at": now_iso(),
    }
    history.append(payload)
    workflow["current"] = to_state
    workflow["last_event"] = event
    workflow["updated_at"] = payload["at"]


def apply_execution_attempt(workflow: Dict[str, Any]) -> None:
    attempts = workflow.get("attempts")
    if not isinstance(attempts, dict):
        attempts = {"l0": 0, "l1": 0}
        workflow["attempts"] = attempts
    tier = str(workflow.get("route") or "L0").upper()
    if tier == "L1":
        attempts["l1"] = int(attempts.get("l1") or 0) + 1
    else:
        attempts["l0"] = int(attempts.get("l0") or 0) + 1


def should_escalate_to_l1(workflow: Dict[str, Any], final_status: str) -> bool:
    route = str(workflow.get("route") or "L0").upper()
    if route != "L0":
        return False

    policy = workflow.get("policy") if isinstance(workflow.get("policy"), dict) else {}
    attempts = workflow.get("attempts") if isinstance(workflow.get("attempts"), dict) else {}
    l0_attempts = int(attempts.get("l0") or 0)
    max_l0 = int(policy.get("max_attempts_l0") or 2)
    conditions = [str(x) for x in (policy.get("escalate_l0_to_l1_if") or [])]

    reason = None
    if final_status in {"blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"} and "reviewer_gate_failed" in conditions:
        reason = "reviewer_gate_failed"
    elif final_status == "blocked_convergence_gate" and (
        "convergence_gate_failed" in conditions or "reviewer_gate_failed" in conditions
    ):
        reason = "convergence_gate_failed"
    elif final_status in {"execution_failed", "blocked_permissions"} and "deterministic_pipeline_failed" in conditions:
        reason = "deterministic_pipeline_failed"

    if reason and l0_attempts >= max_l0:
        workflow["escalation_reason"] = reason
        return True
    return False


def init_sync_state(sync_path: Path, task: str, source: str, matched_rule: Dict[str, Any], assignee: str, action: str, workflow_policy: Dict[str, Any]) -> Dict[str, Any]:
    lock_path = sync_path.with_suffix(sync_path.suffix + ".lock")
    with file_lock(lock_path):
        existing = read_json(sync_path)
        task_id = f"T-{utc_stamp()}"
        max_iterations = int(matched_rule.get("max_iterations") or 4)
        state: Dict[str, Any] = {
            "task_id": task_id,
            "session_id": f"dispatch-{utc_stamp()}",
            "user_instruction": task,
            "intent_type": str(matched_rule.get("name") or "default"),
            "owner_role": "supervisor",
            "phase": "RECEIVED",
            "iteration": {
                "current": 0,
                "max": max_iterations,
                "budget_seconds": 1800,
            },
            "routing": {
                "matched_rule": str(matched_rule.get("name") or "default"),
                "assignee": assignee,
                "action": action,
                "intent_confidence": matched_rule.get("intent_confidence"),
                "requires_reviewer": bool(matched_rule.get("requires_reviewer", True)),
                "auto_escalation_policy": str(matched_rule.get("auto_escalation_policy") or "soft"),
                "stop_conditions": list(matched_rule.get("stop_conditions") or []),
            },
            "last_action": {
                "by": "supervisor",
                "at": now_iso(),
                "summary": "task received and routed",
            },
            "last_result": {
                "status": "pending",
                "evidence": [],
            },
            "blocked": {
                "is_blocked": False,
                "reason_code": "none",
                "reason_detail": "",
            },
            "next_action": {
                "by": assignee,
                "todo": action,
            },
            "updated_at": now_iso(),
            "source": source,
            "workflow": init_workflow_snapshot(action, workflow_policy),
        }

        if existing:
            previous_task = existing.get("last_task") if isinstance(existing.get("last_task"), dict) else None
            if isinstance(previous_task, dict):
                state["previous_task"] = previous_task
            existing["last_task"] = state
            existing = _merge_task_summary_into_root_sync(existing, state)
            existing["updated_at"] = now_iso()
            write_json(sync_path, existing)
            return state

        write_json(sync_path, state)
        return state


def finalize_sync_state(sync_path: Path, state: Dict[str, Any], report: Dict[str, Any], report_path: Path) -> None:
    final_state = dict(state)
    final_status = str(report.get("status") or "unknown")
    public_status = str(report.get("public_status") or final_status)
    public_failure_reason = str(report.get("public_failure_reason") or report.get("failure_reason") or "")
    auto_mode = bool(report.get("auto_policy_applied"))
    phase = "DONE"
    blocked = {
        "is_blocked": False,
        "reason_code": "none",
        "reason_detail": "",
    }

    escalation_packet = str(report.get("escalation_packet") or "").strip()
    replan_packet = str(report.get("replan_packet") or "").strip()
    default_policy = resolve_workflow_policy(
        load_workflow_policy(DEFAULT_WORKFLOW_SPEC),
        str(final_state.get("intent_type") or "default"),
    )
    workflow = dict(final_state.get("workflow") or init_workflow_snapshot(str((final_state.get("routing") or {}).get("action") or "prepare"), default_policy))

    if report.get("executed"):
        append_workflow_event(workflow, "RETRY_DUE", f"EXEC_{str(workflow.get('route') or 'L0').upper()}")
        apply_execution_attempt(workflow)

    if final_status in {"blocked_permissions", "blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified", "execution_failed", "input_contract_invalid"}:
        phase = "BLOCKED"
        blocked = {
            "is_blocked": True,
            "reason_code": final_status,
            "reason_detail": str(report.get("failure_reason") or ""),
        }
        if auto_mode:
            phase = "REPAIRING"
            blocked = {
                "is_blocked": True,
                "reason_code": (
                    "auto_repair_reviewer_gate"
                    if final_status == "blocked_reviewer_gate"
                    else "auto_repair_convergence_gate"
                    if final_status == "blocked_convergence_gate"
                    else "auto_repair_physics_result"
                    if final_status == "blocked_physics_result_missing"
                    else "auto_repair_physics_mismatch"
                    if final_status == "blocked_physics_mismatch"
                    else "auto_repair_provenance"
                    if final_status == "blocked_provenance_unverified"
                    else "auto_repair_permissions"
                    if final_status == "blocked_permissions"
                    else "auto_repair_execution"
                    if final_status == "execution_failed"
                    else "auto_repair_input_contract"
                    if final_status == "input_contract_invalid"
                    else "auto_repair_in_progress"
                ),
                "reason_detail": public_failure_reason,
            }
            append_workflow_event(workflow, "AUTO_REPAIR", "REPLAN")
        if escalation_packet:
            phase = "ESCALATING"
            append_workflow_event(workflow, "EXEC_FAIL", "RETRY_WAIT")
            append_workflow_event(workflow, "REPLAN_READY", "ESCALATING")
        if replan_packet:
            phase = "REPLAN"
            append_workflow_event(workflow, "REVIEW_FAIL", "REPLAN")
        if should_escalate_to_l1(workflow, final_status):
            workflow["route"] = "L1"
            append_workflow_event(workflow, "ROUTE_TO_L1", "QUEUED")
            workflow["next_route"] = "L1"
    elif final_status in {"routed_only", "unknown"}:
        phase = "PLANNED"
        append_workflow_event(workflow, "ROUTE_TO_L0", "QUEUED")
    elif final_status == "success":
        append_workflow_event(workflow, "EXEC_SUCCESS", "REVIEWING")
        append_workflow_event(workflow, "REVIEW_PASS", "DONE")

    final_state["phase"] = phase
    final_state["blocked"] = blocked
    final_state["iteration"] = {
        **dict(final_state.get("iteration") or {}),
        "current": 1 if report.get("executed") else 0,
    }
    final_state["last_action"] = {
        "by": "supervisor",
        "at": now_iso(),
        "summary": f"dispatch finished: {public_status}",
    }
    final_state["last_result"] = {
        "status": public_status,
        "internal_status": final_status,
        "human_status": str(report.get("human_status") or ""),
        "failure_reason": public_failure_reason,
        "failure_reason_taxonomy": str(report.get("failure_reason_taxonomy") or ""),
        "evidence": [report_path.as_posix()],
    }
    if isinstance(report.get("physics_result"), dict):
        final_state["last_result"]["physics_result"] = dict(report.get("physics_result") or {})
        benchmark_delta = (report.get("physics_result") or {}).get("benchmark_delta")
        if isinstance(benchmark_delta, dict):
            final_state["last_result"]["delta_diagnostics"] = dict(benchmark_delta)
    convergence_gate = report.get("convergence_gate") if isinstance(report.get("convergence_gate"), dict) else {}
    final_state["last_result"]["convergence_gate_applied"] = bool(convergence_gate.get("applied", False))
    final_state["last_result"]["convergence_gate_passed"] = bool(convergence_gate.get("passed", False))
    final_state["last_result"]["convergence_gate_unmet"] = [
        str(x) for x in (convergence_gate.get("unmet_conditions") or []) if str(x)
    ]
    if isinstance(report.get("autonomous_assessment"), dict):
        final_state["last_result"]["autonomous_assessment"] = dict(report.get("autonomous_assessment") or {})
    if escalation_packet:
        final_state["last_result"]["escalation_packet"] = escalation_packet
    if replan_packet:
        final_state["last_result"]["replan_packet"] = replan_packet
    coding_submission = report.get("coding_submission")
    if isinstance(coding_submission, dict):
        final_state["last_result"]["coding_submission"] = coding_submission
    final_state["next_action"] = {
        "by": "supervisor" if (escalation_packet or replan_packet) else ("reviewer" if report.get("executed") else str((final_state.get("routing") or {}).get("assignee") or "supervisor")),
        "todo": "execute replan packet actions" if replan_packet else ("run external assist from escalation packet" if escalation_packet else ("review execution artifacts" if report.get("executed") else "wait for execution")),
    }
    if str(workflow.get("next_route") or "") == "L1":
        final_state["next_action"] = {
            "by": "codex-executor",
            "todo": "escalate to L1 backend coding executor",
        }
    final_state["conversation_handoff"] = {
        "summary": f"status={public_status}; phase={phase}; reviewer_verdict={public_failure_reason or 'pass_or_pending'}",
        "carry_over_required": True,
        "next_packet": replan_packet or escalation_packet or report_path.as_posix(),
        "generated_at": now_iso(),
    }
    final_state["updated_at"] = now_iso()
    final_state["workflow"] = workflow

    lock_path = sync_path.with_suffix(sync_path.suffix + ".lock")
    with file_lock(lock_path):
        existing = read_json(sync_path)
        if existing and "last_task" in existing:
            existing["last_task"] = final_state
            existing = _merge_task_summary_into_root_sync(existing, final_state)
            existing["updated_at"] = now_iso()
            write_json(sync_path, existing)
            return

        write_json(sync_path, final_state)


def maybe_write_escalation_packet(
    report: Dict[str, Any],
    matched_rule: Dict[str, Any],
    sync_state: Dict[str, Any],
    report_path: Path,
    report_dir: Path,
) -> Optional[Path]:
    policy = str(matched_rule.get("auto_escalation_policy") or "").strip().lower()
    status = str(report.get("status") or "").strip()
    if policy != "strict":
        return None
    if status not in {"blocked_reviewer_gate", "blocked_convergence_gate", "blocked_permissions", "execution_failed"}:
        return None

    packet = {
        "escalation_id": f"E-{utc_stamp()}",
        "task_id": sync_state.get("task_id"),
        "from_role": "supervisor",
        "to_role": "openclaw-external-assist",
        "blocker_type": (
            "review"
            if status == "blocked_reviewer_gate"
            else ("convergence" if status == "blocked_convergence_gate" else ("permission" if status == "blocked_permissions" else "execution"))
        ),
        "severity": "high",
        "attempted": [
            {
                "step": "dispatch_dirac_task --execute",
                "result": status,
            }
        ],
        "needs_external": {
            "provider": "openclaw_claude",
            "ask": "Return minimal patch + verification plan to clear the current blocker",
        },
        "expected_return": [
            "root_cause",
            "minimal_patch",
            "verification_plan",
        ],
        "evidence": [
            report_path.as_posix(),
        ],
        "created_at": now_iso(),
    }

    packet_path = report_dir / f"escalation_packet_{utc_stamp()}.json"
    write_json(packet_path, packet)
    return packet_path


def maybe_write_replan_packet(report: Dict[str, Any], report_dir: Path) -> Optional[Path]:
    status = str(report.get("status") or "").strip()
    if status not in {"blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
        return None

    execution = report.get("execution") or {}
    exec_kv = parse_kv_lines(str(execution.get("stdout") or ""))
    multi_agent_report_json = str(exec_kv.get("multi_agent_report_json") or "").strip()
    suggestions: List[str] = []
    checks: Dict[str, Any] = {}
    next_action_packet: List[Dict[str, Any]] = []
    failure_type = ""
    anti_repeat_triggered = False
    if multi_agent_report_json:
        payload = read_json((REPO_ROOT / multi_agent_report_json).resolve() if not Path(multi_agent_report_json).is_absolute() else Path(multi_agent_report_json))
        reviewer = payload.get("reviewer") if isinstance(payload, dict) else {}
        if isinstance(reviewer, dict):
            suggestions = [str(x) for x in (reviewer.get("suggestions") or [])]
            checks = dict(reviewer.get("checks") or {})
            packet_raw = reviewer.get("next_action_packet") or []
            if isinstance(packet_raw, list):
                next_action_packet = [dict(x) for x in packet_raw if isinstance(x, dict)]
            failure_type = str(reviewer.get("failure_type") or "")
            anti_repeat_triggered = bool(reviewer.get("anti_repeat_triggered", False))

    convergence_gate = report.get("convergence_gate") if isinstance(report.get("convergence_gate"), dict) else {}
    convergence_unmet = [str(x) for x in (convergence_gate.get("unmet_conditions") or []) if str(x)]

    if status == "blocked_convergence_gate" and convergence_unmet:
        suggestions = [
            f"Address convergence condition: {item}" for item in convergence_unmet
        ] + suggestions
    if status == "blocked_physics_mismatch":
        suggestions = [
            "Physics mismatch detected: tune numerics/geometry/XC and rerun until benchmark delta is within tolerance.",
            "Keep failed run evidence and report relative delta/root-cause hypothesis for each retry.",
        ] + suggestions
    if status == "blocked_provenance_unverified":
        suggestions = [
            "Benchmark provenance is incomplete: add authoritative source URL/DOI and runtime metadata (version/PSP/geometry/discretization).",
            "Do not promote this benchmark to reviewer baseline until provenance_verified=true.",
        ] + suggestions

    if not suggestions:
        suggestions = [
            "Rerun harness acceptance with strict mode and inspect relative_error drift",
            "Rebuild or enrich KB corpus and re-evaluate retrieval richness",
            "Verify Octopus execution path and remote service readiness",
        ]

    actions: List[Dict[str, Any]] = []
    if next_action_packet:
        for idx, item in enumerate(next_action_packet):
            actions.append(
                {
                    "step": idx + 1,
                    "owner": str(item.get("owner") or "planner"),
                    "action": str(item.get("action") or ""),
                    "why": str(item.get("why") or ""),
                    "source": "reviewer.next_action_packet",
                    "status": "pending",
                }
            )
    else:
        actions = [
            {"step": idx + 1, "action": item, "source": "reviewer.suggestions", "status": "pending"}
            for idx, item in enumerate(suggestions)
        ]

    packet = {
        "replan_id": f"RPL-{utc_stamp()}",
        "task_id": report.get("task_id"),
        "trigger": status,
        "convergence_unmet": convergence_unmet,
        "reviewer_checks": checks,
        "failure_type": failure_type,
        "anti_repeat_triggered": anti_repeat_triggered,
        "delta_diagnostics": dict((report.get("physics_result") or {}).get("benchmark_delta") or {}),
        "failure_reason_taxonomy": str(report.get("failure_reason_taxonomy") or ""),
        "actions": actions,
        "source_report": report.get("execution", {}).get("command"),
        "created_at": now_iso(),
    }

    packet_path = report_dir / f"replan_packet_{utc_stamp()}.json"
    write_json(packet_path, packet)
    return packet_path


def run_orchestration(args: argparse.Namespace) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "scripts/run_multi_agent_orchestration.py",
        "--api-base",
        args.api_base,
        "--harness-base",
        args.harness_base,
        "--case-id",
        args.case_id,
        "--max-iterations",
        str(args.max_iterations),
        "--octopus-molecule",
        args.octopus_molecule,
        "--octopus-calc-mode",
        args.octopus_calc_mode,
        "--skills-manifest",
        args.skills_manifest,
        "--planner-model-priority",
        str(args.planner_model_priority),
        "--reviewer-model-priority",
        str(args.reviewer_model_priority),
        "--planner-thinking-budget",
        str(int(args.planner_thinking_budget)),
        "--reviewer-thinking-budget",
        str(int(args.reviewer_thinking_budget)),
    ]
    strict_mode = bool(args.reviewer_strict) or str(os.environ.get("DIRAC_REVIEWER_STRICT", "0")).strip() == "1"
    if strict_mode:
        cmd.append("--strict")
    run_id = str(getattr(args, "run_id", "") or "").strip()
    if run_id:
        cmd.extend(["--run-id", run_id])

    timeout_seconds = max(30, int(getattr(args, "orchestration_timeout_seconds", 0) or args.exec_timeout_seconds))
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"orchestration_timeout_after_{timeout_seconds}s",
        }
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_kb_collaboration(args: argparse.Namespace) -> Dict[str, Any]:
    kb_http_timeout_seconds = max(30, int(getattr(args, "kb_http_timeout_seconds", 0) or 120))
    kb_cmd = [
        sys.executable,
        "scripts/run_kb_reliable_autopilot.py",
        "--base-url",
        args.harness_base,
        "--manifest",
        str(DEFAULT_MANIFEST),
        "--timeout",
        str(kb_http_timeout_seconds),
        "--max-attempts",
        "5",
        "--output-dir",
        args.report_dir,
    ]
    if args.include_web:
        kb_cmd.append("--include-web")

    timeout_seconds = max(120, int(getattr(args, "kb_stage_timeout_seconds", 0) or 3600))
    orchestration_stage_timeout = max(30, int(getattr(args, "orchestration_timeout_seconds", 0) or args.exec_timeout_seconds))
    suite_stage_timeout = max(120, int(getattr(args, "suite_stage_timeout_seconds", 0) or timeout_seconds))
    web_export_timeout = max(30, int(getattr(args, "web_export_timeout_seconds", 0) or 600))
    try:
        kb_proc = subprocess.run(
            kb_cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(kb_cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"kb_build_timeout_after_{timeout_seconds}s",
            "stages": {
                "kb_build": {
                    "command": " ".join(kb_cmd),
                    "exit_code": 124,
                },
                "orchestration": {
                    "exit_code": 0,
                },
            },
        }

    original_orchestration_timeout = int(getattr(args, "orchestration_timeout_seconds", 0) or args.exec_timeout_seconds)
    args.orchestration_timeout_seconds = orchestration_stage_timeout
    orchestrate = run_orchestration(args)
    args.orchestration_timeout_seconds = original_orchestration_timeout
    orchestrate_kv = parse_kv_lines(str(orchestrate.get("stdout") or ""))
    orchestration_report_json = str(orchestrate_kv.get("multi_agent_report_json") or "").strip()

    suite_molecule, _ = infer_octopus_defaults_for_case(args.case_id)
    suite_task_ids = "hydrogen_gs_reference"
    if suite_molecule == "H2O":
        suite_task_ids = "h2o_gs_reference,h2o_tddft_absorption,h2o_tddft_dipole_response,h2o_tddft_radiation_spectrum,h2o_tddft_eels_spectrum"

    suite_cmd = [
        sys.executable,
        "scripts/run_dft_tddft_agent_suite.py",
        "--api-base",
        args.api_base,
        "--molecule",
        suite_molecule,
        "--task-ids",
        suite_task_ids,
        "--output-dir",
        args.report_dir,
        "--external-reference-path",
        "knowledge_base/reference_data/external_curve_references.json",
    ]
    if bool(args.reviewer_strict):
        suite_cmd.append("--strict")
    try:
        suite_proc = subprocess.run(
            suite_cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=suite_stage_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        suite_proc = subprocess.CompletedProcess(
            args=suite_cmd,
            returncode=124,
            stdout=str(exc.stdout or ""),
            stderr=f"dft_tddft_suite_timeout_after_{timeout_seconds}s",
        )

    suite_kv = parse_kv_lines(str(suite_proc.stdout or ""))
    suite_report_json = str(suite_kv.get("suite_report_json") or "").strip()
    suite_report_md = str(suite_kv.get("suite_report_md") or "").strip()
    suite_case_summary: Dict[str, Any] = {
        "total_cases": 0,
        "passed_cases": 0,
        "cases": [],
    }
    if suite_report_json:
        suite_report_path = Path(suite_report_json)
        if not suite_report_path.is_absolute():
            suite_report_path = REPO_ROOT / suite_report_path
        suite_payload = read_json(suite_report_path)
        suite_cases = list(((suite_payload.get("executor") or {}).get("cases") or []))
        suite_rows: List[Dict[str, Any]] = []
        passed_count = 0
        for row in suite_cases:
            status = str(row.get("status") or "")
            if status == "PASS":
                passed_count += 1
            comparison = row.get("comparison") or {}
            external = row.get("external_curve_comparison") or {}
            artifacts = row.get("curve_artifacts") or {}
            curve_files: List[str] = []
            for payload in artifacts.values():
                if not isinstance(payload, dict):
                    continue
                csv_path = str(payload.get("csv") or "").strip()
                svg_path = str(payload.get("svg") or "").strip()
                if csv_path:
                    curve_files.append(csv_path)
                if svg_path:
                    curve_files.append(svg_path)
            suite_rows.append(
                {
                    "scenario_id": str(row.get("scenario_id") or ""),
                    "status": status,
                    "metric": str(comparison.get("metric") or ""),
                    "computed": comparison.get("computed"),
                    "reference": comparison.get("reference"),
                    "relative_delta": comparison.get("relative_delta"),
                    "within_tolerance": comparison.get("within_tolerance"),
                    "provenance_verified": comparison.get("provenance_verified"),
                    "delta_diagnostics": {
                        "delta": comparison.get("delta"),
                        "relative_delta": comparison.get("relative_delta"),
                        "tolerance_relative": comparison.get("tolerance_relative"),
                        "within_tolerance": comparison.get("within_tolerance"),
                    },
                    "external_source": str(external.get("source") or ""),
                    "curve_files": curve_files,
                }
            )
        suite_case_summary = {
            "total_cases": len(suite_cases),
            "passed_cases": passed_count,
            "cases": suite_rows,
        }

    month_tag = datetime.now(timezone.utc).strftime("%Y_%m")
    web_evidence_output = f"knowledge_base/corpus/web_evidence_traceable_cases_{month_tag}.md"
    export_cmd: List[str] = []
    export_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    if orchestration_report_json:
        export_cmd = [
            sys.executable,
            "scripts/export_web_evidence_to_kb.py",
            "--report",
            orchestration_report_json,
            "--output",
            web_evidence_output,
        ]
        try:
            export_proc = subprocess.run(
                export_cmd,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=web_export_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            export_proc = subprocess.CompletedProcess(
                args=export_cmd,
                returncode=124,
                stdout=str(exc.stdout or ""),
                stderr="web_evidence_export_timeout",
            )

    combined_stdout = "\n".join([
        "[KB_BUILD]",
        kb_proc.stdout,
        "[ORCHESTRATION]",
        orchestrate.get("stdout", ""),
        "[DFT_TDDFT_SUITE]",
        str(suite_proc.stdout or ""),
        "[WEB_EVIDENCE_EXPORT]",
        str(export_proc.stdout or ""),
    ])
    combined_stderr = "\n".join([
        kb_proc.stderr,
        "[ORCHESTRATION]",
        orchestrate.get("stderr", ""),
        "[DFT_TDDFT_SUITE]",
        str(suite_proc.stderr or ""),
        "[WEB_EVIDENCE_EXPORT]",
        str(export_proc.stderr or ""),
    ])

    combined_exit = 0
    if kb_proc.returncode != 0 or int(orchestrate.get("exit_code", 1)) != 0 or int(suite_proc.returncode or 0) != 0:
        combined_exit = 2
    if export_cmd and int(export_proc.returncode or 0) != 0:
        combined_exit = 2

    return {
        "command": " && ".join([
            " ".join(kb_cmd),
            str(orchestrate.get("command", "")).strip(),
            " ".join(suite_cmd),
            " ".join(export_cmd) if export_cmd else "",
        ]).strip(" &"),
        "exit_code": combined_exit,
        "stdout": combined_stdout,
        "stderr": combined_stderr,
        "artifacts": {
            "orchestration_report_json": orchestration_report_json,
            "suite_report_json": suite_report_json,
            "suite_report_md": suite_report_md,
            "suite_case_summary": suite_case_summary,
            "web_evidence_kb_output": web_evidence_output if export_cmd else "",
        },
        "stages": {
            "kb_build": {
                "command": " ".join(kb_cmd),
                "exit_code": kb_proc.returncode,
                "autopilot": True,
            },
            "orchestration": {
                "command": str(orchestrate.get("command", "")),
                "exit_code": int(orchestrate.get("exit_code", 1)),
            },
            "dft_tddft_suite": {
                "command": " ".join(suite_cmd),
                "exit_code": int(suite_proc.returncode or 0),
            },
            "web_evidence_export": {
                "command": " ".join(export_cmd),
                "exit_code": int(export_proc.returncode or 0),
            },
        },
    }


def run_octopus_campaign(args: argparse.Namespace) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "scripts/run_multi_agent_octopus_campaign.py",
        "--api-base",
        args.api_base,
        "--harness-base",
        args.harness_base,
        "--skills-manifest",
        args.skills_manifest,
        "--report-dir",
        args.report_dir,
        "--timeout",
        str(args.exec_timeout_seconds),
        "--profile",
        "octopus-max",
        "--planner-model-priority",
        str(args.planner_model_priority),
        "--reviewer-model-priority",
        str(args.reviewer_model_priority),
        "--planner-thinking-budget",
        str(int(args.planner_thinking_budget)),
        "--reviewer-thinking-budget",
        str(int(args.reviewer_thinking_budget)),
    ]
    feishu_target = str(args.feishu_target or "").strip()
    if bool(args.feishu_log) or bool(feishu_target):
        cmd.append("--feishu-log")
        if feishu_target:
            cmd.extend(["--feishu-target", feishu_target])
        cmd.extend(["--feishu-message-mode", str(args.feishu_message_mode)])
        cmd.extend(["--feishu-explain-model", str(args.feishu_explain_model)])
        cmd.extend(["--feishu-explain-timeout", str(int(args.feishu_explain_timeout))])
        cmd.extend(["--feishu-progress-interval", str(int(args.feishu_progress_interval))])
    timeout_seconds = max(60, int(args.exec_timeout_seconds) + 600)
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"octopus_campaign_timeout_after_{timeout_seconds}s",
        }
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def run_resume_debug_session(args: argparse.Namespace, current_sync_state: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    latest = current_sync_state if isinstance(current_sync_state, dict) else {}
    last_task = latest.get("last_task") if isinstance(latest.get("last_task"), dict) else latest
    if not isinstance(last_task, dict):
        last_task = {}

    previous_task = last_task.get("previous_task") if isinstance(last_task.get("previous_task"), dict) else {}
    resume_source_task = previous_task if previous_task else last_task
    for _ in range(8):
        if str(resume_source_task.get("intent_type") or "") != "resume_debug_session":
            break
        nested_prev = resume_source_task.get("previous_task") if isinstance(resume_source_task.get("previous_task"), dict) else None
        if not isinstance(nested_prev, dict):
            break
        resume_source_task = nested_prev
    if str(resume_source_task.get("intent_type") or "") == "resume_debug_session":
        if str(latest.get("intent_type") or "") and str(latest.get("intent_type") or "") != "resume_debug_session":
            resume_source_task = latest

    handoff = resume_source_task.get("conversation_handoff") if isinstance(resume_source_task.get("conversation_handoff"), dict) else {}
    workflow = resume_source_task.get("workflow") if isinstance(resume_source_task.get("workflow"), dict) else {}
    routing = resume_source_task.get("routing") if isinstance(resume_source_task.get("routing"), dict) else {}
    blocked = resume_source_task.get("blocked") if isinstance(resume_source_task.get("blocked"), dict) else {}
    last_result = resume_source_task.get("last_result") if isinstance(resume_source_task.get("last_result"), dict) else {}

    resume_payload = {
        "generated_at": now_iso(),
        "resume_command": "Dirac_solver 调试 /auto",
        "source_state": Path(args.sync_state).as_posix(),
        "last_task": {
            "task_id": str(resume_source_task.get("task_id") or ""),
            "phase": str(resume_source_task.get("phase") or ""),
            "intent_type": str(resume_source_task.get("intent_type") or ""),
            "updated_at": str(resume_source_task.get("updated_at") or ""),
        },
        "handoff": {
            "summary": str(handoff.get("summary") or ""),
            "next_packet": str(handoff.get("next_packet") or ""),
            "carry_over_required": bool(handoff.get("carry_over_required", True)),
        },
        "next_action": dict(resume_source_task.get("next_action") or {}),
        "blocked": {
            "is_blocked": bool(blocked.get("is_blocked", False)),
            "reason_code": str(blocked.get("reason_code") or "none"),
            "reason_detail": str(blocked.get("reason_detail") or ""),
        },
        "routing": {
            "matched_rule": str(routing.get("matched_rule") or ""),
            "action": str(routing.get("action") or ""),
            "assignee": str(routing.get("assignee") or ""),
        },
        "workflow": {
            "route": str(workflow.get("route") or ""),
            "current": str(workflow.get("current") or ""),
            "last_event": str(workflow.get("last_event") or ""),
            "next_route": str(workflow.get("next_route") or ""),
        },
        "evidence": {
            "dispatch_report": str((last_result.get("evidence") or [""])[0] or ""),
            "replan_packet": str(last_result.get("replan_packet") or ""),
            "escalation_packet": str(last_result.get("escalation_packet") or ""),
            "replan_execution_report": str(last_result.get("replan_execution_report") or ""),
        },
        "service_readiness_checklist": [
            "python scripts/dc.ps1 -NoShell",
            "确认 3001(API) 与 8001(Harness) 可访问，必要时启用 8101 兜底",
            "python scripts/dispatch_dirac_task.py --task \"Dirac_solver 调试 /auto\" --source cli --execute --auto-execute-replan --reviewer-strict",
        ],
    }

    bootstrap_cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "scripts/dc.ps1",
        "-SkipComputeSubmitCheck",
        "-NoShell",
    ]
    bootstrap_timeout = max(45, int(args.resume_bootstrap_timeout_seconds))
    preflight_before_bootstrap = run_preflight(args)
    service_gate_before = preflight_before_bootstrap.get("service_gate") if isinstance(preflight_before_bootstrap.get("service_gate"), dict) else {}
    api_ready_before = bool((service_gate_before.get("api") or {}).get("reachable", False))
    harness_ready_before = bool((service_gate_before.get("harness") or {}).get("reachable", False))
    policy_skip_bootstrap = bool(args.resume_skip_bootstrap)
    if not policy_skip_bootstrap:
        env_skip = str(os.environ.get("DIRAC_RESUME_SKIP_BOOTSTRAP") or "").strip().lower()
        policy_skip_bootstrap = env_skip in {"1", "true", "yes", "on"}
    should_skip_bootstrap = (api_ready_before and harness_ready_before) or policy_skip_bootstrap
    should_skip_bootstrap = should_skip_bootstrap and not bool(args.resume_force_bootstrap)

    if should_skip_bootstrap:
        bootstrap_proc = None
        bootstrap_exit_code = 0
        bootstrap_stdout = ""
        if policy_skip_bootstrap:
            bootstrap_stderr = "resume_bootstrap_skipped_by_policy"
        else:
            bootstrap_stderr = "resume_bootstrap_skipped_services_already_ready"
        preflight = run_preflight(args)
    else:
        try:
            bootstrap_proc = subprocess.run(
                bootstrap_cmd,
                cwd=REPO_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=bootstrap_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            bootstrap_proc = None
            bootstrap_exit_code = 124
            bootstrap_stdout = str(exc.stdout or "")
            bootstrap_stderr = f"resume_service_bootstrap_timeout_after_{bootstrap_timeout}s"
        else:
            bootstrap_exit_code = int(bootstrap_proc.returncode)
            bootstrap_stdout = ""
            bootstrap_stderr = ""

        preflight = run_preflight(args)
    preflight_ready = bool(preflight.get("ready", False))
    harness_selected_base = str((((preflight.get("service_gate") or {}).get("harness") or {}).get("selected_base") or "")).strip()
    harness_base_for_acceptance = harness_selected_base or str(args.harness_base)

    acceptance_cmd = [
        sys.executable,
        "scripts/run_harness_acceptance.py",
        "--base-url",
        harness_base_for_acceptance,
        "--case-id",
        str(args.case_id),
        "--timeout",
        str(max(30, min(180, int(args.exec_timeout_seconds)))),
        "--output-dir",
        str(args.report_dir),
    ]
    acceptance_exit_code = -1
    acceptance_stdout = ""
    acceptance_stderr = ""
    acceptance_kv: Dict[str, str] = {}
    if bootstrap_exit_code == 0 and preflight_ready:
        acceptance_timeout = max(120, int(args.exec_timeout_seconds) + 60)
        try:
            acceptance_proc = subprocess.run(
                acceptance_cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=acceptance_timeout,
                check=False,
            )
            acceptance_exit_code = int(acceptance_proc.returncode)
            acceptance_stdout = str(acceptance_proc.stdout or "")
            acceptance_stderr = str(acceptance_proc.stderr or "")
            acceptance_kv = parse_kv_lines(acceptance_stdout)
        except subprocess.TimeoutExpired as exc:
            acceptance_exit_code = 124
            acceptance_stdout = str(exc.stdout or "")
            acceptance_stderr = f"resume_acceptance_timeout_after_{acceptance_timeout}s"

    packet_path = report_dir / f"resume_debug_packet_{utc_stamp()}.json"
    resume_payload["service_bootstrap"] = {
        "command": " ".join(bootstrap_cmd),
        "exit_code": bootstrap_exit_code,
        "timeout_seconds": bootstrap_timeout,
        "skipped": bool(should_skip_bootstrap),
    }
    resume_payload["service_preflight"] = {
        "ready": preflight_ready,
        "reason_code": str(preflight.get("reason_code") or ""),
        "service_gate": dict(preflight.get("service_gate") or {}),
    }
    resume_payload["acceptance"] = {
        "attempted": bootstrap_exit_code == 0 and preflight_ready,
        "command": " ".join(acceptance_cmd),
        "exit_code": acceptance_exit_code,
        "report_json": str(acceptance_kv.get("report_json") or ""),
        "passed": str(acceptance_kv.get("passed") or ""),
        "used_endpoint": str(acceptance_kv.get("used_endpoint") or ""),
    }
    write_json(packet_path, resume_payload)

    failure_reason = ""
    if bootstrap_exit_code != 0:
        failure_reason = "resume_service_bootstrap_failed"
    elif not preflight_ready:
        failure_reason = str(preflight.get("reason_code") or "resume_service_preflight_failed")
    elif acceptance_exit_code not in {0, -1}:
        failure_reason = "resume_acceptance_failed"

    stdout_lines = [
        f"resume_packet={packet_path.as_posix()}",
        f"last_task_id={resume_payload['last_task']['task_id'] or '-'}",
        f"last_phase={resume_payload['last_task']['phase'] or '-'}",
        f"resume_next_packet={resume_payload['handoff']['next_packet'] or '-'}",
        f"resume_blocked={str(resume_payload['blocked']['is_blocked'])}",
        f"resume_bootstrap_exit_code={bootstrap_exit_code}",
        f"resume_preflight_ready={str(preflight_ready)}",
        f"resume_acceptance_exit_code={acceptance_exit_code}",
    ]
    if acceptance_kv.get("report_json"):
        stdout_lines.append(f"resume_acceptance_report_json={acceptance_kv.get('report_json')}")
    if acceptance_kv.get("report_md"):
        stdout_lines.append(f"resume_acceptance_report_md={acceptance_kv.get('report_md')}")
    if acceptance_kv.get("used_endpoint"):
        stdout_lines.append(f"resume_acceptance_used_endpoint={acceptance_kv.get('used_endpoint')}")
    if acceptance_kv.get("passed"):
        stdout_lines.append(f"resume_acceptance_passed={acceptance_kv.get('passed')}")
    if failure_reason:
        stdout_lines.append(f"resume_failure_reason={failure_reason}")

    return {
        "command": "resume_debug_session",
        "exit_code": 0 if not failure_reason else 2,
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join([
            bootstrap_stderr[:4000],
            acceptance_stderr[:2000],
        ]).strip(),
    }


def run_replan_executor(args: argparse.Namespace, packet_path: Path) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "scripts/execute_replan_packet.py",
        "--packet",
        packet_path.as_posix(),
        "--state",
        args.sync_state,
        "--api-base",
        args.api_base,
        "--harness-base",
        args.harness_base,
        "--case-id",
        args.case_id,
        "--octopus-molecule",
        args.octopus_molecule,
        "--octopus-calc-mode",
        args.octopus_calc_mode,
        "--report-dir",
        args.report_dir,
    ]
    timeout_seconds = max(30, int(args.exec_timeout_seconds))
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"replan_timeout_after_{timeout_seconds}s",
        }
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def parse_kv_lines(text: str) -> Dict[str, str]:
    kv: Dict[str, str] = {}
    for line in (text or "").splitlines():
        idx = line.find("=")
        if idx <= 0:
            continue
        key = line[:idx].strip()
        value = line[idx + 1 :].strip()
        if key:
            kv[key] = value
    return kv


def _load_orchestration_report_payload(execution: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(execution, dict):
        return {}
    kv = parse_kv_lines(str(execution.get("stdout") or ""))
    report_json = str(kv.get("multi_agent_report_json") or "").strip()
    if not report_json:
        artifacts = execution.get("artifacts") if isinstance(execution.get("artifacts"), dict) else {}
        report_json = str(artifacts.get("orchestration_report_json") or "").strip()
    if not report_json:
        return {}
    report_path = Path(report_json)
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    return read_json(report_path)


def extract_physics_result_snapshot(execution: Dict[str, Any]) -> Dict[str, Any]:
    payload = _load_orchestration_report_payload(execution)
    executor = payload.get("executor") if isinstance(payload.get("executor"), dict) else {}
    benchmark_review = executor.get("benchmark_review") if isinstance(executor.get("benchmark_review"), dict) else {}
    physics_result = executor.get("physics_result") if isinstance(executor.get("physics_result"), dict) else {}

    if physics_result:
        snapshot = dict(physics_result)
    else:
        octopus = executor.get("octopus") if isinstance(executor.get("octopus"), dict) else {}
        oct_result = octopus.get("result") if isinstance(octopus.get("result"), dict) else {}
        molecular = oct_result.get("molecular") if isinstance(oct_result.get("molecular"), dict) else {}
        optical = molecular.get("optical_spectrum") if isinstance(molecular.get("optical_spectrum"), dict) else {}
        energy_ev = optical.get("energy_ev") if isinstance(optical.get("energy_ev"), list) else []
        cross_section = optical.get("cross_section") if isinstance(optical.get("cross_section"), list) else []
        benchmark = (executor.get("benchmark_review") or {}).get("delta") if isinstance(executor.get("benchmark_review"), dict) else {}
        benchmark = benchmark if isinstance(benchmark, dict) else {}
        ground_state = molecular.get("total_energy_hartree")
        spectrum_points = min(len(energy_ev), len(cross_section))
        snapshot = {
            "calc_mode": str(molecular.get("calcMode") or ""),
            "molecule_name": str(molecular.get("moleculeName") or ""),
            "ground_state_energy_hartree": float(ground_state) if isinstance(ground_state, (int, float)) else None,
            "homo_energy": float(molecular.get("homo_energy")) if isinstance(molecular.get("homo_energy"), (int, float)) else None,
            "lumo_energy": float(molecular.get("lumo_energy")) if isinstance(molecular.get("lumo_energy"), (int, float)) else None,
            "absorption_spectrum_points": int(spectrum_points),
            "absorption_spectrum": {
                "energy_ev": energy_ev,
                "cross_section": cross_section,
            },
            "benchmark_delta": {
                "relative_error": float(benchmark.get("relative_error")) if isinstance(benchmark.get("relative_error"), (int, float)) else None,
                "threshold": float(benchmark.get("threshold")) if isinstance(benchmark.get("threshold"), (int, float)) else None,
                "within_tolerance": bool(benchmark.get("within_tolerance", False)),
            },
        }

    missing_fields = [str(x) for x in (snapshot.get("missing_fields") or []) if str(x)]
    calc_mode = str(snapshot.get("calc_mode") or "").strip().lower()
    requires_absorption_spectrum = bool(snapshot.get("requires_absorption_spectrum"))
    if not requires_absorption_spectrum:
        requires_absorption_spectrum = calc_mode in {"td", "tddft", "rt", "spectrum", "casida"}
    snapshot["requires_absorption_spectrum"] = requires_absorption_spectrum
    if not missing_fields:
        if not isinstance(snapshot.get("ground_state_energy_hartree"), (int, float)):
            missing_fields.append("ground_state_energy_hartree")
        if requires_absorption_spectrum and int(snapshot.get("absorption_spectrum_points") or 0) <= 0:
            missing_fields.append("absorption_spectrum")
        benchmark_delta = snapshot.get("benchmark_delta") if isinstance(snapshot.get("benchmark_delta"), dict) else {}
        if not isinstance(benchmark_delta.get("relative_error"), (int, float)):
            missing_fields.append("benchmark_delta.relative_error")

    snapshot["missing_fields"] = missing_fields
    snapshot["has_required_fields"] = len(missing_fields) == 0
    if "provenance_verified" not in snapshot:
        snapshot["provenance_verified"] = bool(benchmark_review.get("provenance_verified", False))
    snapshot["available"] = bool(payload)
    return snapshot


def _to_bool_token(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "pass", "passed", "ok"}


def _to_int_token(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def evaluate_convergence_gate(report: Dict[str, Any], matched_rule: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce evidence-based convergence for autonomous/strict workflows.

    A task is considered truly converged only when execution signals and artifacts
    satisfy task-specific evidence checks.
    """
    status = str(report.get("status") or "").strip().lower()
    if status != "success":
        return {
            "applied": False,
            "passed": True,
            "reason": "status_not_success",
            "unmet_conditions": [],
            "evidence": {},
        }

    auto_mode = bool(report.get("auto_policy_applied"))
    requires_reviewer = bool(report.get("requires_reviewer", True))
    action = str(report.get("action") or "").strip()
    rule_name = str((matched_rule or {}).get("name") or "").strip().lower()
    strict_rule = rule_name in {
        "auto_default_orchestration",
        "dirac_full_debug",
        "auto_kb_openclaw_planner_first",
        "knowledge_base_collaboration",
    }

    if not (auto_mode or (requires_reviewer and strict_rule)):
        return {
            "applied": False,
            "passed": True,
            "reason": "not_required_for_current_task",
            "unmet_conditions": [],
            "evidence": {},
        }

    execution = report.get("execution") if isinstance(report.get("execution"), dict) else {}
    exec_kv = parse_kv_lines(str(execution.get("stdout") or ""))
    artifacts = execution.get("artifacts") if isinstance(execution.get("artifacts"), dict) else {}
    unmet: List[str] = []
    evidence: Dict[str, Any] = {
        "action": action,
        "rule_name": rule_name,
        "reviewer_verdict": str(exec_kv.get("reviewer_verdict") or ""),
        "suite_verdict": str(exec_kv.get("suite_verdict") or ""),
        "openclaw_planner_ok": str(exec_kv.get("openclaw_planner_ok") or ""),
        "sources_verified": _to_int_token(exec_kv.get("sources_verified"), default=0),
        "multimodal_evidence_count": _to_int_token(exec_kv.get("multimodal_evidence_count"), default=0),
    }

    reviewer_strict = bool(report.get("reviewer_strict"))
    reviewer_verdict = str(exec_kv.get("reviewer_verdict") or "").strip().upper()
    if reviewer_strict:
        if reviewer_verdict and reviewer_verdict != "PASS":
            unmet.append("reviewer_verdict_not_pass")
        if not reviewer_verdict:
            unmet.append("reviewer_verdict_missing")

    if action in {"run_orchestration", "run_kb_collaboration"}:
        planner_token = str(exec_kv.get("openclaw_planner_ok") or "").strip()
        if not planner_token:
            unmet.append("openclaw_planner_ok_missing")
        elif not _to_bool_token(planner_token):
            unmet.append("openclaw_planner_not_ok")

    if action == "run_orchestration":
        suite_verdict = str(exec_kv.get("suite_verdict") or "").strip().upper()
        if suite_verdict and suite_verdict != "PASS":
            unmet.append("suite_verdict_not_pass")

    if action == "run_kb_collaboration":
        suite_summary = artifacts.get("suite_case_summary") if isinstance(artifacts.get("suite_case_summary"), dict) else {}
        total_cases = _to_int_token(suite_summary.get("total_cases"), default=0)
        passed_cases = _to_int_token(suite_summary.get("passed_cases"), default=0)
        evidence["suite_total_cases"] = total_cases
        evidence["suite_passed_cases"] = passed_cases
        if total_cases <= 0:
            unmet.append("suite_case_summary_missing")
        elif passed_cases < total_cases:
            unmet.append(f"suite_not_fully_passed:{passed_cases}/{total_cases}")

        web_output = str(artifacts.get("web_evidence_kb_output") or "").strip()
        evidence["web_evidence_kb_output"] = web_output
        if not web_output:
            unmet.append("web_evidence_kb_output_missing")
        else:
            web_path = Path(web_output)
            if not web_path.is_absolute():
                web_path = (REPO_ROOT / web_path).resolve()
            if not web_path.exists():
                unmet.append("web_evidence_kb_output_not_found")
            else:
                try:
                    if web_path.stat().st_size < 80:
                        unmet.append("web_evidence_kb_output_too_small")
                except Exception:
                    unmet.append("web_evidence_kb_output_unreadable")

    if action == "resume_debug_session":
        if not _to_bool_token(exec_kv.get("resume_preflight_ready")):
            unmet.append("resume_preflight_not_ready")
        if not _to_bool_token(exec_kv.get("resume_acceptance_passed")):
            unmet.append("resume_acceptance_not_passed")

    return {
        "applied": True,
        "passed": len(unmet) == 0,
        "reason": "ok" if len(unmet) == 0 else "evidence_gate_failed",
        "unmet_conditions": unmet,
        "evidence": evidence,
    }


def summarize_result(report: Dict[str, Any]) -> Dict[str, Any]:
    validation = report.get("contract_validation") if isinstance(report.get("contract_validation"), dict) else {}
    if validation and not bool(validation.get("is_valid", True)):
        missing = [str(x) for x in (validation.get("missing_required_fields") or [])]
        return {
            "status": "input_contract_invalid",
            "failure_reason": f"missing_required_fields:{','.join(missing)}",
        }

    preflight = report.get("preflight") or {}
    execution = report.get("execution") or {}
    plugin_gate = preflight.get("plugin_gate") if isinstance(preflight, dict) else {}
    if isinstance(plugin_gate, dict) and plugin_gate.get("checked") and not bool(plugin_gate.get("plugin_gate_passed", True)):
        return {
            "status": "blocked_plugin_gate",
            "failure_reason": str(plugin_gate.get("reason") or "missing_required_plugins"),
        }

    if preflight and not preflight.get("ready", False):
        return {
            "status": "blocked_permissions",
            "failure_reason": str(preflight.get("reason_code") or preflight.get("reason") or "openclaw_execution_not_ready"),
        }

    if execution:
        exit_code = int(execution.get("exit_code", 0) or 0)
        exec_kv = parse_kv_lines(str(execution.get("stdout") or ""))
        exec_stderr = str(execution.get("stderr") or "")
        action = str(report.get("action") or "").strip().lower()
        physics_result = extract_physics_result_snapshot(execution)
        if physics_result:
            report["physics_result"] = physics_result
        if action == "run_orchestration" and exit_code in {0, 2}:
            if not bool((physics_result or {}).get("has_required_fields", False)):
                missing_fields = [str(x) for x in ((physics_result or {}).get("missing_fields") or []) if str(x)]
                missing_text = ",".join(missing_fields) if missing_fields else "unknown"
                return {
                    "status": "blocked_physics_result_missing",
                    "failure_reason": f"missing_physics_result_fields:{missing_text}",
                    "failure_reason_taxonomy": "missing_required_physics_fields",
                }
            benchmark_delta = (physics_result or {}).get("benchmark_delta") if isinstance((physics_result or {}).get("benchmark_delta"), dict) else {}
            provenance_verified = (physics_result or {}).get("provenance_verified")
            if provenance_verified is False:
                return {
                    "status": "blocked_provenance_unverified",
                    "failure_reason": "benchmark_provenance_unverified",
                    "failure_reason_taxonomy": "provenance_unverified",
                }
            within_tolerance = benchmark_delta.get("within_tolerance")
            relative_error = benchmark_delta.get("relative_error")
            threshold = benchmark_delta.get("threshold")
            if within_tolerance is False:
                return {
                    "status": "blocked_physics_mismatch",
                    "failure_reason": f"physics_delta_exceeds_tolerance:relative_error={relative_error};threshold={threshold}",
                    "failure_reason_taxonomy": "physics_mismatch",
                }

        if action == "run_kb_collaboration" and exit_code in {0, 2}:
            artifacts = execution.get("artifacts") if isinstance(execution.get("artifacts"), dict) else {}
            suite_summary = artifacts.get("suite_case_summary") if isinstance(artifacts.get("suite_case_summary"), dict) else {}
            suite_cases = suite_summary.get("cases") if isinstance(suite_summary.get("cases"), list) else []
            for row in suite_cases:
                if not isinstance(row, dict):
                    continue
                if row.get("within_tolerance") is False:
                    return {
                        "status": "blocked_physics_mismatch",
                        "failure_reason": f"suite_physics_mismatch:{str(row.get('scenario_id') or '')}",
                        "failure_reason_taxonomy": "physics_mismatch",
                    }
                if row.get("provenance_verified") is False:
                    return {
                        "status": "blocked_provenance_unverified",
                        "failure_reason": f"suite_provenance_unverified:{str(row.get('scenario_id') or '')}",
                        "failure_reason_taxonomy": "provenance_unverified",
                    }
        reviewer_verdict = exec_kv.get("reviewer_verdict", "")
        if reviewer_verdict.upper() == "FAIL":
            reviewer_strict = bool(report.get("reviewer_strict"))
            if not reviewer_strict and exit_code in {0, 2}:
                return {
                    "status": "success",
                    "failure_reason": "reviewer_verdict_fail_softgate",
                    "failure_reason_taxonomy": "softgate_override",
                }
            return {
                "status": "blocked_reviewer_gate",
                "failure_reason": "reviewer_verdict_fail",
                "failure_reason_taxonomy": "reviewer_gate_failed",
            }
        if exit_code == 0:
            return {
                "status": "success",
                "failure_reason": None,
                "failure_reason_taxonomy": "none",
            }
        timeout_marker = ""
        marker_match = re.search(r"([a-z_]*timeout_after_\d+s)", exec_stderr)
        if marker_match:
            timeout_marker = str(marker_match.group(1) or "").strip()
        if timeout_marker:
            return {
                "status": "execution_failed",
                "failure_reason": timeout_marker,
                "failure_reason_taxonomy": "execution_timeout",
            }
        custom_failure_reason = str(exec_kv.get("failure_reason") or exec_kv.get("resume_failure_reason") or "").strip()
        if custom_failure_reason:
            return {
                "status": "execution_failed",
                "failure_reason": custom_failure_reason,
                "failure_reason_taxonomy": "execution_error",
            }
        return {
            "status": "execution_failed",
            "failure_reason": f"orchestration_nonzero_exit:{exit_code}",
            "failure_reason_taxonomy": "execution_nonzero_exit",
        }

    return {
        "status": "routed_only",
        "failure_reason": None,
        "failure_reason_taxonomy": "not_executed",
    }


def should_apply_auto_policy(task: str, matched_rule: Dict[str, Any], source: str = "") -> bool:
    text = str(task or "").lower()
    rule_name = str(matched_rule.get("name") or "").lower()
    source_text = str(source or "").lower()
    return (
        "auto" in text
        or "/auto" in text
        or "自动执行" in text
        or "自动调试" in text
        or "自动" in text
        or "auto" in rule_name
        or source_text.startswith("feishu")
    )


def execute_action_once(action: str, args: argparse.Namespace) -> Dict[str, Any]:
    if action == "run_kb_collaboration":
        return run_kb_collaboration(args)
    if action == "run_octopus_campaign":
        return run_octopus_campaign(args)
    if action == "resume_debug_session":
        return run_resume_debug_session(args, read_json(Path(args.sync_state)), report_dir=Path(args.report_dir))
    return run_orchestration(args)


def _load_reviewer_packet_from_execution(execution: Dict[str, Any]) -> Dict[str, Any]:
    kv = parse_kv_lines(str(execution.get("stdout") or ""))
    report_json = str(kv.get("multi_agent_report_json") or "").strip()
    if not report_json:
        artifacts = execution.get("artifacts") if isinstance(execution.get("artifacts"), dict) else {}
        report_json = str(artifacts.get("orchestration_report_json") or "").strip()
    if not report_json:
        return {}

    report_path = Path(report_json)
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    payload = read_json(report_path)
    reviewer = payload.get("reviewer") if isinstance(payload, dict) else {}
    if not isinstance(reviewer, dict):
        return {}

    next_action_packet = reviewer.get("next_action_packet")
    if not isinstance(next_action_packet, list):
        next_action_packet = []
    actions = [dict(item) for item in next_action_packet if isinstance(item, dict)]

    return {
        "report_json": report_path.as_posix(),
        "final_verdict": str(reviewer.get("final_verdict") or ""),
        "failure_type": str(reviewer.get("failure_type") or ""),
        "repair_type": str(reviewer.get("repair_type") or ""),
        "anti_repeat_triggered": bool(reviewer.get("anti_repeat_triggered", False)),
        "next_action_packet": actions,
    }


def _infer_action_from_openclaw_packet(reviewer_packet: Dict[str, Any], current_action: str) -> str:
    failure_type = str(reviewer_packet.get("failure_type") or "").strip().lower()
    if failure_type in {"knowledge_retrieval", "web_evidence"}:
        return "run_kb_collaboration"
    if failure_type in {
        "endpoint_or_service",
        "numerical_accuracy",
        "planner_executor_chain_break",
        "openclaw_runtime_or_permission",
        "ui_runtime",
        "octopus_runtime",
    }:
        return "run_orchestration"

    packet_items = reviewer_packet.get("next_action_packet")
    if not isinstance(packet_items, list):
        return current_action

    packet_text = " ".join(
        (
            f"{str(item.get('owner') or '')} "
            f"{str(item.get('action') or '')} "
            f"{str(item.get('why') or '')}"
        ).strip().lower()
        for item in packet_items
        if isinstance(item, dict)
    )
    if any(token in packet_text for token in ["kb_query", "source_diversity", "web_automation", "retrieval"]):
        return "run_kb_collaboration"
    if any(token in packet_text for token in ["iterate", "run_case", "endpoint", "remote_openclaw", "harness"]):
        return "run_orchestration"
    return current_action


def decide_auto_loop_with_openclaw(
    *,
    auto_mode: bool,
    iteration: int,
    max_iterations: int,
    status: str,
    retryable_statuses: List[str],
    current_action: str,
    execution: Dict[str, Any],
    openclaw_autonomy_enabled: bool,
    openclaw_action_switch_enabled: bool,
) -> Dict[str, Any]:
    normalized = str(status or "").strip().lower()
    decision: Dict[str, Any] = {
        "continue": False,
        "next_action": current_action,
        "decision_source": "policy_retryable",
        "reason": "terminal_status",
        "status": normalized,
    }
    if not auto_mode:
        decision["reason"] = "auto_mode_disabled"
        return decision
    if iteration >= max_iterations:
        decision["reason"] = "max_iterations_reached"
        return decision
    if normalized in {"success", "input_contract_invalid", "blocked_plugin_gate", "routed_only", "unknown"}:
        decision["reason"] = "status_terminal"
        return decision

    retryable = normalized in {str(x).strip().lower() for x in retryable_statuses if str(x).strip()}
    decision["continue"] = retryable
    decision["reason"] = "retryable_status" if retryable else "non_retryable_status"

    if not openclaw_autonomy_enabled:
        return decision

    reviewer_packet = _load_reviewer_packet_from_execution(execution)
    if reviewer_packet:
        decision["reviewer_packet"] = reviewer_packet
        decision["decision_source"] = "openclaw_reviewer_packet"
        decision["failure_type"] = str(reviewer_packet.get("failure_type") or "")
        decision["repair_type"] = str(reviewer_packet.get("repair_type") or "")
        decision["anti_repeat_triggered"] = bool(reviewer_packet.get("anti_repeat_triggered", False))
        if openclaw_action_switch_enabled:
            decision["next_action"] = _infer_action_from_openclaw_packet(reviewer_packet, current_action)
            decision["action_switched"] = decision["next_action"] != current_action

    return decision


def should_continue_auto_loop(
    *,
    auto_mode: bool,
    iteration: int,
    max_iterations: int,
    status: str,
    retryable_statuses: List[str],
) -> bool:
    if not auto_mode:
        return False
    if iteration >= max_iterations:
        return False
    normalized = str(status or "").strip().lower()
    if normalized in {"success", "input_contract_invalid", "blocked_plugin_gate", "routed_only", "unknown"}:
        return False
    return normalized in {str(x).strip().lower() for x in retryable_statuses if str(x).strip()}


def probe_service_base(base_url: str, timeout_seconds: float) -> Dict[str, Any]:
    target = str(base_url or "").strip()
    if not target:
        return {
            "base_url": target,
            "ok": False,
            "error": "empty_base_url",
        }
    try:
        parsed = urlparse(target)
        host = str(parsed.hostname or "").strip()
        if not host:
            return {
                "base_url": target,
                "ok": False,
                "error": "invalid_base_url",
            }
        if parsed.port:
            port = int(parsed.port)
        else:
            port = 443 if str(parsed.scheme or "").lower() == "https" else 80
        with socket.create_connection((host, port), timeout=max(0.5, float(timeout_seconds))):
            pass
        return {
            "base_url": target,
            "ok": True,
            "host": host,
            "port": port,
        }
    except Exception as exc:
        return {
            "base_url": target,
            "ok": False,
            "error": str(exc),
        }


def probe_service_group(name: str, base_urls: List[str], timeout_seconds: float) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in base_urls:
        base = str(raw or "").strip()
        if not base:
            continue
        if base in seen:
            continue
        seen.add(base)
        item = probe_service_base(base, timeout_seconds=timeout_seconds)
        checks.append(item)
        if bool(item.get("ok", False)):
            return {
                "name": name,
                "reachable": True,
                "selected_base": base,
                "checks": checks,
            }
    return {
        "name": name,
        "reachable": False,
        "selected_base": "",
        "checks": checks,
    }


def _http_status(url: str, timeout_seconds: float, method: str = "GET") -> int:
    request = Request(url=url, method=method)
    try:
        with urlopen(request, timeout=max(0.5, float(timeout_seconds))) as response:
            return int(getattr(response, "status", 0) or 0)
    except HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0)
    except Exception:
        return 0


def probe_harness_group(base_urls: List[str], timeout_seconds: float) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in base_urls:
        base = str(raw or "").strip().rstrip("/")
        if not base or base in seen:
            continue
        seen.add(base)

        tcp_item = probe_service_base(base, timeout_seconds=timeout_seconds)
        route_checks: List[Dict[str, Any]] = []
        route_ready = False
        if bool(tcp_item.get("ok", False)):
            # Any non-404 status indicates the route exists (e.g. 200/401/405), which is enough for readiness.
            route_candidates = [
                ("GET", f"{base}/harness/cases"),
                ("GET", f"{base}/harness/case_registry"),
                ("OPTIONS", f"{base}/harness/run_case"),
                ("OPTIONS", f"{base}/api/harness/run_case"),
            ]
            for method, url in route_candidates:
                status = _http_status(url, timeout_seconds=timeout_seconds, method=method)
                route_checks.append({"method": method, "url": url, "status": status})
                if status and status != 404:
                    route_ready = True

        checks.append(
            {
                "base_url": base,
                "tcp_ok": bool(tcp_item.get("ok", False)),
                "tcp_error": str(tcp_item.get("error") or ""),
                "route_ready": route_ready,
                "route_checks": route_checks,
            }
        )

        if route_ready:
            return {
                "name": "harness",
                "reachable": True,
                "selected_base": base,
                "checks": checks,
            }

    return {
        "name": "harness",
        "reachable": False,
        "selected_base": "",
        "checks": checks,
    }


def run_preflight(args: argparse.Namespace) -> Dict[str, Any]:
    ensure_cmd = [
        sys.executable,
        "scripts/ensure_openclaw_exec.py",
        "--openclaw-root",
        args.openclaw_root,
        "--timeout-ms",
        str(args.exec_timeout_ms),
        "--json",
    ]
    ensure_proc = subprocess.run(ensure_cmd, cwd=REPO_ROOT, capture_output=True, text=True)

    audit_cmd = [
        sys.executable,
        "scripts/audit_openclaw_permissions.py",
        "--openclaw-root",
        args.openclaw_root,
        "--policy",
        args.exec_policy,
        "--json",
    ]
    audit_proc = subprocess.run(audit_cmd, cwd=REPO_ROOT, capture_output=True, text=True)

    ensure_json: Dict[str, Any] = {}
    audit_json: Dict[str, Any] = {}
    try:
        ensure_json = json.loads(ensure_proc.stdout) if ensure_proc.stdout.strip() else {}
    except Exception:
        ensure_json = {}
    try:
        audit_json = json.loads(audit_proc.stdout) if audit_proc.stdout.strip() else {}
    except Exception:
        audit_json = {}

    service_timeout_seconds = max(1.0, min(8.0, float(max(1000, int(args.exec_timeout_ms))) / 1000.0))
    harness_fallback_base = str(os.environ.get("DIRAC_HARNESS_FALLBACK_BASE") or DEFAULT_HARNESS_FALLBACK_BASE).strip()
    api_probe = probe_service_group("api", [str(args.api_base or "")], timeout_seconds=service_timeout_seconds)
    harness_probe = probe_harness_group(
        [str(args.harness_base or ""), harness_fallback_base],
        timeout_seconds=service_timeout_seconds,
    )

    reason_codes: List[str] = []
    audit_ready = bool(audit_json.get("execution_ready", False))
    if not audit_ready:
        reason_codes.append("openclaw_execution_not_ready")
    if not bool(api_probe.get("reachable", False)):
        reason_codes.append("api_service_unreachable")
    if not bool(harness_probe.get("reachable", False)):
        reason_codes.append("harness_service_unreachable")

    ready = audit_ready and bool(api_probe.get("reachable", False)) and bool(harness_probe.get("reachable", False))
    return {
        "ready": ready,
        "reason_code": "|".join(reason_codes) if reason_codes else "",
        "service_gate": {
            "timeout_seconds": service_timeout_seconds,
            "api": api_probe,
            "harness": harness_probe,
        },
        "ensure": {
            "command": " ".join(ensure_cmd),
            "exit_code": ensure_proc.returncode,
            "stdout": ensure_proc.stdout,
            "stderr": ensure_proc.stderr,
            "json": ensure_json,
        },
        "audit": {
            "command": " ".join(audit_cmd),
            "exit_code": audit_proc.returncode,
            "stdout": audit_proc.stdout,
            "stderr": audit_proc.stderr,
            "json": audit_json,
        },
    }


def plugin_prefix_match(required_prefix: str, candidate: str) -> bool:
    prefix = str(required_prefix or "").strip()
    value = str(candidate or "").strip()
    if not prefix or not value:
        return False
    if prefix.endswith(".*"):
        return value.startswith(prefix[:-1])
    return value == prefix or value.startswith(prefix)


def gather_plugin_inventory(openclaw_root: Path) -> List[Dict[str, str]]:
    roots = [
        REPO_ROOT / "external" / "openclaw_selected" / "extensions",
        openclaw_root / ".openclaw" / "plugins",
    ]
    records: List[Dict[str, str]] = []
    seen_paths: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for plugin_file in root.rglob("openclaw.plugin.json"):
            payload = read_json(plugin_file)
            plugin_id = str(payload.get("id") or "").strip()
            path_str = plugin_file.as_posix()
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)
            records.append({"id": plugin_id, "path": path_str})
    return records


def build_skills_visibility_snapshot(manifest_path: Path, openclaw_root: Path) -> Dict[str, Any]:
    manifest = read_json(manifest_path)
    roles = dict(manifest.get("roles") or {}) if isinstance(manifest, dict) else {}
    required_skill_ids: List[str] = []
    for role_name in ["planner", "executor", "reviewer"]:
        role = roles.get(role_name)
        if isinstance(role, dict):
            skill_id = str(role.get("skill_id") or "").strip()
            if skill_id:
                required_skill_ids.append(skill_id)

    skill_roots = [REPO_ROOT / ".claude" / "skills", openclaw_root / "skills"]
    roots_status = [{"path": root.as_posix(), "exists": root.exists()} for root in skill_roots]

    role_snapshot: Dict[str, Dict[str, Any]] = {}
    for role_name in ["planner", "executor", "reviewer"]:
        role = roles.get(role_name)
        skill_id = str((role or {}).get("skill_id") or "").strip() if isinstance(role, dict) else ""
        role_snapshot[role_name] = {
            "skill_id": skill_id,
            "required_outputs": list((role or {}).get("required_outputs") or []) if isinstance(role, dict) else [],
            "visible": bool(skill_id),
            "source": "agent_skills_manifest" if skill_id else "",
        }

    return {
        "timestamp": now_iso(),
        "manifest_source": manifest_path.as_posix(),
        "skill_roots": roots_status,
        "required_skill_ids": required_skill_ids,
        "roles": role_snapshot,
        "missing_roles": [name for name, info in role_snapshot.items() if not bool(info.get("visible"))],
    }


def evaluate_plugin_presence_gate(
    *,
    workflow_policy: Dict[str, Any],
    skills_snapshot: Dict[str, Any],
    openclaw_root: Path,
) -> Dict[str, Any]:
    required_plugins = [str(x).strip() for x in (workflow_policy.get("required_plugins") or []) if str(x).strip()]
    inventory = gather_plugin_inventory(openclaw_root)
    plugin_ids = [str(item.get("id") or "").strip() for item in inventory if str(item.get("id") or "").strip()]
    role_skill_ids = [
        str(role_info.get("skill_id") or "").strip()
        for role_info in (skills_snapshot.get("roles") or {}).values()
        if isinstance(role_info, dict)
    ]
    candidates = plugin_ids + role_skill_ids

    matched: Dict[str, str] = {}
    missing: List[str] = []
    for required in required_plugins:
        hit = next((candidate for candidate in candidates if plugin_prefix_match(required, candidate)), "")
        if hit:
            matched[required] = hit
        else:
            missing.append(required)

    gate_required = bool(workflow_policy.get("plugin_gate_required", False))
    gate_passed = (not gate_required) or (len(missing) == 0)
    reason = "ok" if gate_passed else f"missing_required_plugins:{','.join(missing)}"

    return {
        "checked": True,
        "plugin_gate_required": gate_required,
        "required_plugins": required_plugins,
        "matched": matched,
        "missing_plugins": missing,
        "found_plugin_ids": plugin_ids,
        "found_skill_ids": role_skill_ids,
        "plugin_inventory": inventory,
        "plugin_gate_passed": gate_passed,
        "reason": reason,
    }


def compute_consistency_token(task_id: str, dispatch_status: str, reviewer_verdict: str) -> str:
    raw = f"{str(task_id or '').strip()}|{str(dispatch_status or '').strip()}|{str(reviewer_verdict or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def assess_autonomous_workflow(
    report: Dict[str, Any],
    reviewer_verdict: str,
    loop_retryable: bool,
) -> Dict[str, Any]:
    auto_mode = bool(report.get("auto_policy_applied"))
    status = str(report.get("status") or "unknown").strip().lower()
    public_status = str(report.get("public_status") or status).strip().lower()
    public_failure_reason = str(report.get("public_failure_reason") or report.get("failure_reason") or "").strip()
    workflow = report.get("workflow") if isinstance(report.get("workflow"), dict) else {}
    workflow_state = str(workflow.get("state") or "UNKNOWN")
    workflow_next_route = str(workflow.get("next_route") or "")
    loop_info = report.get("loop_iterations") if isinstance(report.get("loop_iterations"), dict) else {}
    loop_stopped_due_to = str(loop_info.get("stopped_due_to") or "")
    plugin_gate = report.get("plugin_presence_gate") if isinstance(report.get("plugin_presence_gate"), dict) else {}
    plugin_gate_passed = bool(plugin_gate.get("plugin_gate_passed", False))
    preflight = report.get("preflight") if isinstance(report.get("preflight"), dict) else {}
    preflight_ready = bool(preflight.get("ready", False)) if preflight else False
    convergence_gate = report.get("convergence_gate") if isinstance(report.get("convergence_gate"), dict) else {}
    convergence_gate_applied = bool(convergence_gate.get("applied", False))
    convergence_gate_passed = bool(convergence_gate.get("passed", True))

    completion_state = "not_applicable"
    health_state = "unknown"
    ready_for_next_auto_task = False
    blockers: List[str] = []

    if not auto_mode:
        return {
            "enabled": False,
            "completion_state": completion_state,
            "health_state": health_state,
            "ready_for_next_auto_task": ready_for_next_auto_task,
            "blockers": blockers,
            "workflow_state": workflow_state,
            "workflow_next_route": workflow_next_route,
            "status": status,
        }

    completion_state = "in_progress"
    if status == "success":
        completion_state = "completed"
    elif public_status == "auto_repairing":
        completion_state = "repairing"
        if workflow_next_route.upper() == "L1" and loop_stopped_due_to == "max_iterations_reached":
            completion_state = "escalated"
    elif status in {"execution_failed", "blocked_permissions", "blocked_plugin_gate", "input_contract_invalid", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
        completion_state = "blocked"
    elif public_status == "routed_only" or status == "routed_only":
        completion_state = "queued"

    if status == "success":
        health_state = "healthy" if plugin_gate_passed else "degraded"
    elif public_status == "auto_repairing":
        health_state = "degraded"
    elif status in {"blocked_reviewer_gate", "blocked_convergence_gate", "routed_only"}:
        health_state = "degraded"
    elif status in {"execution_failed", "blocked_permissions", "blocked_plugin_gate", "input_contract_invalid", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
        health_state = "unhealthy"

    if not plugin_gate_passed:
        blockers.append("plugin_gate_failed")
    if convergence_gate_applied and not convergence_gate_passed:
        blockers.append("convergence_gate_failed")
        blockers.extend([str(x) for x in (convergence_gate.get("unmet_conditions") or []) if str(x)])
    if report.get("executed") and preflight and not preflight_ready:
        blockers.append("preflight_not_ready")
    if status in {"blocked_reviewer_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"} or reviewer_verdict.upper() == "FAIL":
        blockers.append("reviewer_gate_failed")
    if public_failure_reason:
        blockers.append(public_failure_reason)
    elif status == "execution_failed":
        blockers.append(str(report.get("failure_reason") or "execution_failed"))
    if status == "blocked_permissions" and not public_failure_reason:
        blockers.append("openclaw_execution_not_ready")
    if loop_retryable and loop_stopped_due_to != "max_iterations_reached":
        blockers.append("retry_loop_in_progress")
    if workflow_next_route.upper() == "L1":
        blockers.append("escalated_to_l1")

    if completion_state == "completed" and health_state == "healthy" and len(blockers) == 0:
        ready_for_next_auto_task = True

    return {
        "enabled": True,
        "completion_state": completion_state,
        "health_state": health_state,
        "ready_for_next_auto_task": ready_for_next_auto_task,
        "blockers": blockers,
        "workflow_state": workflow_state,
        "workflow_next_route": workflow_next_route,
        "status": status,
        "public_status": public_status,
    }


def _resolve_repo_path(value: str) -> str:
    p = Path(str(value or "").strip())
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    return p.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch and execute Dirac tasks.")
    parser.add_argument("--task", required=True, help="Task text from CLI or Feishu.")
    parser.add_argument("--source", default="cli", help="Task source label (e.g. cli/feishu/worker).")
    parser.add_argument("--rules", default=str(DEFAULT_RULES), help="Dispatch rules json path.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Dispatch report output dir.")
    parser.add_argument("--execute", action="store_true", help="Execute routed action.")
    parser.add_argument(
        "--openclaw-root",
        default=str(DEFAULT_OPENCLAW_ROOT),
        help="OpenClaw root path for execution checks.",
    )
    parser.add_argument("--exec-policy", default=str(DEFAULT_POLICY), help="Execution policy path.")
    parser.add_argument("--exec-timeout-ms", type=int, default=60000, help="Minimum shellEnv timeout for auto-fix.")
    parser.add_argument("--exec-timeout-seconds", type=int, default=DEFAULT_EXEC_TIMEOUT_SECONDS, help="Timeout for orchestration/KB/replan subprocess execution.")
    parser.add_argument("--resume-bootstrap-timeout-seconds", type=int, default=240, help="Timeout for resume service bootstrap via scripts/dc.ps1 -NoShell.")
    parser.add_argument("--resume-skip-bootstrap", action="store_true", help="Skip resume service bootstrap and rely on existing tunnel/service state.")
    parser.add_argument("--resume-force-bootstrap", action="store_true", help="Force service bootstrap even when preflight already reports ready.")
    parser.add_argument("--sync-state", default=str(DEFAULT_SYNC_STATE), help="Progress sync state file path.")
    parser.add_argument("--workflow-spec", default=str(DEFAULT_WORKFLOW_SPEC), help="Workflow state machine spec path.")
    parser.add_argument("--coding-gateway-config", default=str(DEFAULT_CODING_GATEWAY_CONFIG), help="Coding gateway config json path.")
    parser.add_argument("--coding-gateway-url", default="", help="Optional coding gateway base url override.")
    parser.add_argument("--auto-submit-coding", action="store_true", help="Automatically submit task to coding gateway when workflow_next_route=L1.")

    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--harness-base", default=DEFAULT_HARNESS_BASE)
    parser.add_argument("--case-id", default="hydrogen_gs_reference")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--octopus-molecule", default="H2")
    parser.add_argument("--octopus-calc-mode", default="gs", choices=["gs", "td", "unocc", "opt", "em", "vib"])
    parser.add_argument(
        "--skills-manifest",
        default=str((REPO_ROOT / "orchestration" / "agent_skills_manifest.json").as_posix()),
    )
    parser.add_argument("--auto-execute-replan", action="store_true", help="Automatically run replan packet actions when generated.")
    parser.add_argument("--include-web", action="store_true", help="Include web references during KB build stage.")
    parser.add_argument("--reviewer-strict", action="store_true", help="Treat reviewer FAIL as hard gate (default soft gate unless env DIRAC_REVIEWER_STRICT=1).")
    parser.add_argument("--planner-model-priority", default="gpt-5-thinking,deepseek-r1", help="Comma-separated model priority for planner stage.")
    parser.add_argument("--reviewer-model-priority", default="gpt-5-thinking,deepseek-r1", help="Comma-separated model priority for reviewer stage.")
    parser.add_argument("--planner-thinking-budget", type=int, default=8000, help="Reasoning budget hint for planner stage.")
    parser.add_argument("--reviewer-thinking-budget", type=int, default=8000, help="Reasoning budget hint for reviewer stage.")
    parser.add_argument("--feishu-log", action="store_true", help="Enable Feishu campaign notifications for campaign action.")
    parser.add_argument("--feishu-target", default="", help="Feishu target id; defaults to DIRAC_FEISHU_TARGET when empty.")
    parser.add_argument("--feishu-message-mode", choices=["explained", "raw"], default="explained", help="Campaign Feishu message mode.")
    parser.add_argument("--feishu-explain-model", default="gpt-5-thinking", help="Model used for explanation text in Feishu updates.")
    parser.add_argument("--feishu-explain-timeout", type=int, default=60, help="Timeout seconds for Feishu explanation generation.")
    parser.add_argument("--feishu-progress-interval", type=int, default=2, help="Send interpreted campaign progress every N steps.")

    args = parser.parse_args()
    args.skills_manifest = _resolve_repo_path(str(args.skills_manifest or ""))
    if not str(args.feishu_target or "").strip():
        args.feishu_target = str(os.environ.get("DIRAC_FEISHU_TARGET") or "").strip()

    contract = normalize_task_contract(args.task, args.source)
    metadata = contract.get("metadata") if isinstance(contract.get("metadata"), dict) else {}
    contract_case = str(metadata.get("case") or "").strip()

    # Feishu RECEIVED notification — tell users the task was received
    if notify_received is not None:
        run_id = str(metadata.get("run_id") or "").strip()
        initiator = "agent" if str(args.source or "").strip() not in {"cli", ""} else "human"
        notify_received(run_id=run_id, initiator=initiator, run_id_short=(run_id.split("-")[-1] if run_id else ""))
        if update_status_dashboard is not None:
            case_id = str(args.case_id or "hydrogen_gs_reference")
            update_status_dashboard(
                phase="RECEIVED", run_id=run_id, case_id=case_id,
                overall_pct=5, initiator=initiator,
                planner_done=False, executor_done=False, reviewer_done=False,
                state_machine="L0",
            )
        args.case_id = contract_case
    inferred_molecule, inferred_calc_mode = infer_octopus_defaults_for_case(args.case_id)
    if not was_cli_flag_provided("--octopus-molecule"):
        args.octopus_molecule = inferred_molecule
    if not was_cli_flag_provided("--octopus-calc-mode"):
        args.octopus_calc_mode = inferred_calc_mode

    normalized_task = str(contract.get("normalized") or args.task)
    rules = read_json(Path(args.rules))
    base_workflow_policy = load_workflow_policy(Path(args.workflow_spec))
    matched_rule, assignee, action = route_task(normalized_task, rules)
    auto_policy_applied = False
    if should_apply_auto_policy(normalized_task, matched_rule, args.source):
        # Auto tasks must run with truthful closed-loop behavior by default.
        args.auto_execute_replan = True
        auto_reviewer_strict = str(os.environ.get("DIRAC_AUTO_REVIEWER_STRICT", "0")).strip() == "1"
        args.reviewer_strict = bool(args.reviewer_strict) or auto_reviewer_strict
        args.auto_submit_coding = True
        auto_policy_applied = True

    workflow_policy = resolve_workflow_policy(base_workflow_policy, str(matched_rule.get("name") or "default"))
    args.orchestration_timeout_seconds = int(workflow_policy.get("orchestration_timeout_seconds") or args.exec_timeout_seconds)
    args.kb_stage_timeout_seconds = int(workflow_policy.get("kb_stage_timeout_seconds") or 3600)
    args.kb_http_timeout_seconds = int(workflow_policy.get("kb_http_timeout_seconds") or 120)
    args.suite_stage_timeout_seconds = int(workflow_policy.get("suite_stage_timeout_seconds") or args.kb_stage_timeout_seconds)
    args.web_export_timeout_seconds = int(workflow_policy.get("web_export_timeout_seconds") or 600)
    sync_path = Path(args.sync_state)
    sync_state = init_sync_state(sync_path, normalized_task, args.source, matched_rule, assignee, action, workflow_policy)

    rule_max_iterations = int(matched_rule.get("max_iterations") or args.max_iterations)
    args.max_iterations = max(1, min(rule_max_iterations, 12))

    report: Dict[str, Any] = {
        "timestamp": now_iso(),
        "task_id": sync_state.get("task_id"),
        "source": args.source,
        "task": normalized_task,
        "task_original": str(contract.get("original") or args.task),
        "run_id": str((contract.get("metadata") or {}).get("run_id") or ""),
        "command_contract": {
            "normalized": True,
            "warnings": list(contract.get("warnings") or []),
            "metadata": dict(contract.get("metadata") or {}),
        },
        "contract_validation": {},
        "matched_rule": matched_rule.get("name", "default"),
        "assignee": assignee,
        "action": action,
        "intent_confidence": matched_rule.get("intent_confidence"),
        "requires_reviewer": bool(matched_rule.get("requires_reviewer", True)),
        "max_iterations": args.max_iterations,
        "auto_escalation_policy": matched_rule.get("auto_escalation_policy", "soft"),
        "stop_conditions": list(matched_rule.get("stop_conditions") or []),
        "auto_policy_applied": auto_policy_applied,
        "reviewer_strict": bool(args.reviewer_strict),
        "auto_execute_replan": bool(args.auto_execute_replan),
        "executed": False,
        "execution": None,
        "preflight": None,
        "workflow": {
            "route": route_tier(action),
            "state": "ROUTED",
            "last_event": "TASK_VALID",
            "next_route": route_tier(action),
            "policy": {
                "max_attempts_l0": int(workflow_policy.get("max_attempts_l0") or 2),
                "max_attempts_l1": int(workflow_policy.get("max_attempts_l1") or 2),
                "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
                "policy_override_for": workflow_policy.get("policy_override_for"),
            },
        },
    }

    validation = validate_command_contract(contract, matched_rule)
    report["contract_validation"] = validation
    skills_snapshot = build_skills_visibility_snapshot(Path(args.skills_manifest), Path(args.openclaw_root))
    plugin_gate = evaluate_plugin_presence_gate(
        workflow_policy=workflow_policy,
        skills_snapshot=skills_snapshot,
        openclaw_root=Path(args.openclaw_root),
    )
    report["skills_visibility_snapshot"] = skills_snapshot
    report["plugin_presence_gate"] = plugin_gate

    executable_actions = {"run_orchestration", "run_kb_collaboration", "run_octopus_campaign", "resume_debug_session"}

    if args.execute and action in executable_actions and bool(validation.get("is_valid", True)):
        report["workflow"] = {
            "route": route_tier(action),
            "state": f"EXEC_{route_tier(action).upper()}",
            "last_event": "RETRY_DUE",
            "policy": {
                "max_attempts_l0": int(workflow_policy.get("max_attempts_l0") or 2),
                "max_attempts_l1": int(workflow_policy.get("max_attempts_l1") or 2),
                "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
                "policy_override_for": workflow_policy.get("policy_override_for"),
            },
        }
        requires_preflight = action in {"run_orchestration", "run_kb_collaboration", "run_octopus_campaign"}
        preflight = run_preflight(args) if requires_preflight else {}
        if requires_preflight:
            preflight["plugin_gate"] = plugin_gate
            if not bool(plugin_gate.get("plugin_gate_passed", True)):
                preflight["ready"] = False
                reason_code = str(preflight.get("reason_code") or "").strip()
                if reason_code:
                    preflight["reason_code"] = f"{reason_code}|plugin_gate_failed"
                else:
                    preflight["reason_code"] = "plugin_gate_failed"
        report["preflight"] = preflight if requires_preflight else {
            "ready": bool(plugin_gate.get("plugin_gate_passed", True)),
            "skipped": True,
            "reason": "resume_action_no_exec_required",
            "plugin_gate": plugin_gate,
        }
        if (not report["preflight"].get("ready", False)):
            report["executed"] = False
            report["workflow"] = {
                "route": route_tier(action),
                "state": "FAILED",
                "last_event": "TASK_INVALID",
            }
        else:
            report_dir = Path(args.report_dir)
            report_dir.mkdir(parents=True, exist_ok=True)
            auto_mode_loop = bool(report.get("auto_policy_applied"))
            max_loop = min(int(report.get("max_iterations") or 1), int(workflow_policy.get("auto_loop_max_iterations") or 1))
            max_loop = max(1, max_loop)
            retryable_statuses = list(workflow_policy.get("auto_loop_retryable_statuses") or [])
            loop_history: List[Dict[str, Any]] = []
            iteration = 0
            current_action = action
            base_exec_timeout = max(30, int(args.exec_timeout_seconds))
            adaptive_exec_timeout = base_exec_timeout
            adaptive_factor = max(1.1, float(workflow_policy.get("auto_timeout_escalation_factor") or 1.5))
            adaptive_increment_seconds = max(1, int(workflow_policy.get("auto_timeout_increment_seconds") or 30))
            adaptive_exec_timeout_max = max(base_exec_timeout, int(workflow_policy.get("auto_timeout_cap_seconds") or 1800))
            openclaw_autonomy_enabled = bool(workflow_policy.get("openclaw_autonomy_enabled", True))
            openclaw_action_switch_enabled = bool(workflow_policy.get("openclaw_action_switch_enabled", True))

            while True:
                iteration += 1
                report["executed"] = True
                args.exec_timeout_seconds = adaptive_exec_timeout
                # Forward run_id so orchestration can use it for Feishu notifications
                args.run_id = str(report.get("run_id") or "")
                report["execution"] = execute_action_once(current_action, args)

                loop_summary = summarize_result(report)
                status_now = str(loop_summary.get("status") or "unknown")
                failure_now = str(loop_summary.get("failure_reason") or "")
                iter_entry: Dict[str, Any] = {
                    "iteration": iteration,
                    "action": current_action,
                    "status": status_now,
                    "failure_reason": failure_now,
                    "execution_exit_code": int((report.get("execution") or {}).get("exit_code") or 0),
                    "exec_timeout_seconds": int(args.exec_timeout_seconds),
                    "at": now_iso(),
                }

                if status_now == "execution_failed" and re.search(r"timeout_after_\d+s", failure_now):
                    next_timeout = min(adaptive_exec_timeout_max, max(adaptive_exec_timeout + adaptive_increment_seconds, int(adaptive_exec_timeout * adaptive_factor)))
                    if next_timeout > adaptive_exec_timeout:
                        adaptive_exec_timeout = next_timeout
                        iter_entry["next_exec_timeout_seconds"] = adaptive_exec_timeout
                        iter_entry["timeout_adaptive_increase"] = True

                if status_now in {"blocked_reviewer_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
                    loop_replan_path = maybe_write_replan_packet(report, report_dir)
                    if loop_replan_path:
                        report["replan_packet"] = loop_replan_path.as_posix()
                        iter_entry["replan_packet"] = loop_replan_path.as_posix()
                        if args.auto_execute_replan:
                            replan_exec = run_replan_executor(args, loop_replan_path)
                            report["replan_execution"] = replan_exec
                            iter_entry["replan_execution_exit_code"] = int(replan_exec.get("exit_code") or 0)

                loop_decision = decide_auto_loop_with_openclaw(
                    auto_mode=auto_mode_loop,
                    iteration=iteration,
                    max_iterations=max_loop,
                    status=status_now,
                    retryable_statuses=retryable_statuses,
                    current_action=current_action,
                    execution=dict(report.get("execution") or {}),
                    openclaw_autonomy_enabled=openclaw_autonomy_enabled,
                    openclaw_action_switch_enabled=openclaw_action_switch_enabled,
                )
                iter_entry["openclaw_loop_decision"] = loop_decision
                next_action = str(loop_decision.get("next_action") or current_action)
                if next_action != current_action:
                    iter_entry["next_action"] = next_action
                    current_action = next_action

                loop_history.append(iter_entry)

                if not bool(loop_decision.get("continue", False)):
                    break

            report["loop_iterations"] = {
                "count": iteration,
                "max": max_loop,
                "retryable_statuses": retryable_statuses,
                "openclaw_autonomy": {
                    "enabled": openclaw_autonomy_enabled,
                    "action_switch_enabled": openclaw_action_switch_enabled,
                    "final_action": current_action,
                },
                "adaptive_timeout": {
                    "enabled": True,
                    "escalation_factor": adaptive_factor,
                    "increment_seconds": adaptive_increment_seconds,
                    "base_exec_timeout_seconds": base_exec_timeout,
                    "max_exec_timeout_seconds": adaptive_exec_timeout_max,
                    "final_exec_timeout_seconds": adaptive_exec_timeout,
                },
                "history": loop_history,
                "stopped_due_to": (
                    "max_iterations_reached" if iteration >= max_loop and str((loop_history[-1] if loop_history else {}).get("status") or "") != "success" else "status_terminal"
                ),
            }
            args.exec_timeout_seconds = base_exec_timeout
    elif args.execute and action in executable_actions:
        report["executed"] = False
        report["workflow"] = {
            "route": route_tier(action),
            "state": "FAILED",
            "last_event": "TASK_INVALID",
            "next_route": route_tier(action),
            "policy": {
                "max_attempts_l0": int(workflow_policy.get("max_attempts_l0") or 2),
                "max_attempts_l1": int(workflow_policy.get("max_attempts_l1") or 2),
                "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
                "policy_override_for": workflow_policy.get("policy_override_for"),
            },
        }

    summary = summarize_result(report)
    report["status"] = summary["status"]
    report["failure_reason"] = summary["failure_reason"]
    report["failure_reason_taxonomy"] = str(summary.get("failure_reason_taxonomy") or "")

    convergence_gate = evaluate_convergence_gate(report, matched_rule)
    report["convergence_gate"] = convergence_gate
    if bool(convergence_gate.get("applied", False)) and not bool(convergence_gate.get("passed", True)):
        report["status"] = "blocked_convergence_gate"
        unmet_conditions = [str(x) for x in (convergence_gate.get("unmet_conditions") or []) if str(x)]
        report["failure_reason"] = "convergence_gate_failed" + (
            f":{','.join(unmet_conditions)}" if unmet_conditions else ""
        )

    auto_mode = bool(report.get("auto_policy_applied"))
    report["public_status"] = to_public_dispatch_status(str(report.get("status") or "unknown"), auto_mode)
    report["public_failure_reason"] = to_public_failure_reason(
        str(report.get("status") or "unknown"),
        str(report.get("failure_reason") or ""),
        auto_mode,
    )
    report["human_status"] = to_human_status(
        str(report.get("status") or ""),
        bool(report.get("executed")),
        str(report.get("failure_reason") or ""),
        auto_mode=auto_mode,
    )
    report["phase_stream"] = build_phase_stream(report)
    execution_kv_for_contract = parse_kv_lines(str((report.get("execution") or {}).get("stdout") or ""))
    reviewer_verdict_for_contract = str(execution_kv_for_contract.get("reviewer_verdict") or "")
    loop_count = int(((report.get("loop_iterations") or {}).get("count") or (1 if report.get("executed") else 0)))
    loop_max_attempts = int(((report.get("loop_iterations") or {}).get("max") or report.get("max_iterations") or 1))
    retryable_statuses = {str(x).strip().lower() for x in (workflow_policy.get("auto_loop_retryable_statuses") or []) if str(x).strip()}
    loop_retryable = str(report.get("status") or "").strip().lower() in retryable_statuses
    consistency_token = compute_consistency_token(
        str(report.get("task_id") or ""),
        str(report.get("public_status") or report.get("status") or "unknown"),
        reviewer_verdict_for_contract,
    )
    report["loop_verdict_contract"] = {
        "dispatch_status": str(report.get("public_status") or report.get("status") or "unknown"),
        "reviewer_verdict": reviewer_verdict_for_contract,
        "retryable": loop_retryable,
        "loop_iteration_count": loop_count,
        "loop_max_attempts": loop_max_attempts,
        "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
        "consistency_token": consistency_token,
    }
    report["consistency_token"] = consistency_token
    workflow_policy_view = {
        "max_attempts_l0": int(workflow_policy.get("max_attempts_l0") or 2),
        "max_attempts_l1": int(workflow_policy.get("max_attempts_l1") or 2),
        "retry_backoff_seconds": int(workflow_policy.get("retry_backoff_seconds") or 30),
        "policy_override_for": workflow_policy.get("policy_override_for"),
    }
    if report["status"] == "success":
        report["workflow"] = {
            "route": route_tier(action),
            "state": "DONE",
            "last_event": "REVIEW_PASS",
            "policy": workflow_policy_view,
        }
    elif report["status"] in {"blocked_reviewer_gate", "blocked_convergence_gate", "blocked_physics_result_missing", "blocked_physics_mismatch", "blocked_provenance_unverified"}:
        report["workflow"] = {
            "route": route_tier(action),
            "state": "REPLAN",
            "last_event": "REVIEW_REPAIR" if auto_mode else ("CONVERGENCE_FAIL" if report["status"] == "blocked_convergence_gate" else "REVIEW_FAIL"),
            "policy": workflow_policy_view,
        }
    elif report["status"] in {"execution_failed", "blocked_permissions"}:
        report["workflow"] = {
            "route": route_tier(action),
            "state": "RETRY_WAIT",
            "last_event": "EXEC_REPAIR" if auto_mode else "EXEC_FAIL",
            "policy": workflow_policy_view,
        }
    elif report["status"] == "input_contract_invalid":
        report["workflow"] = {
            "route": route_tier(action),
            "state": "REPLAN" if auto_mode else "FAILED",
            "last_event": "TASK_REPAIR" if auto_mode else "TASK_INVALID",
            "policy": workflow_policy_view,
        }
    elif report["status"] == "blocked_plugin_gate":
        report["workflow"] = {
            "route": route_tier(action),
            "state": "FAILED",
            "last_event": "TASK_INVALID",
            "policy": workflow_policy_view,
        }

    workflow_preview = dict(sync_state.get("workflow") or {})
    if report.get("executed"):
        apply_execution_attempt(workflow_preview)
    if should_escalate_to_l1(workflow_preview, str(report.get("status") or "")):
        report["workflow"]["next_route"] = "L1"
    else:
        report["workflow"]["next_route"] = str(report["workflow"].get("route") or route_tier(action))

    report["autonomous_assessment"] = assess_autonomous_workflow(
        report,
        reviewer_verdict=reviewer_verdict_for_contract,
        loop_retryable=loop_retryable,
    )

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"task_dispatch_{utc_stamp()}.json"
    escalation_packet_path = maybe_write_escalation_packet(report, matched_rule, sync_state, report_path, report_dir)
    if escalation_packet_path:
        report["escalation_packet"] = escalation_packet_path.as_posix()
    replan_packet_path = maybe_write_replan_packet(report, report_dir)
    if replan_packet_path:
        report["replan_packet"] = replan_packet_path.as_posix()
        if args.auto_execute_replan:
            report["replan_execution"] = run_replan_executor(args, replan_packet_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    effective_coding_cfg = load_coding_gateway_config(Path(args.coding_gateway_config))
    if str(args.coding_gateway_url).strip():
        effective_coding_cfg["gateway_base_url"] = str(args.coding_gateway_url).strip().rstrip("/")

    if report.get("workflow", {}).get("next_route") == "L1" and args.auto_submit_coding and bool(effective_coding_cfg.get("enabled", False)):
        try:
            report["coding_submission"] = submit_coding_task(effective_coding_cfg, sync_state, report, report_path)
        except Exception as exc:
            report["coding_submission"] = {
                "submitted": False,
                "error": str(exc),
                "config_source": str(effective_coding_cfg.get("source") or ""),
            }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    finalize_sync_state(sync_path, sync_state, report, report_path)

    print(f"dispatch_report={report_path.as_posix()}")
    print(f"dispatch_task_id={str(report.get('task_id') or '')}")
    print(f"assignee={assignee}")
    print(f"action={action}")
    print(f"dispatch_status={report['status']}")
    print(f"human_status={report.get('human_status')}")
    print(f"failure_reason={report.get('public_failure_reason') or report['failure_reason'] or '-'}")
    print(f"workflow_route={str((report.get('workflow') or {}).get('route') or route_tier(action))}")
    print(f"workflow_state={str((report.get('workflow') or {}).get('state') or 'UNKNOWN')}")
    print(f"workflow_event={str((report.get('workflow') or {}).get('last_event') or '-')}")
    print(f"workflow_next_route={str((report.get('workflow') or {}).get('next_route') or route_tier(action))}")
    print(f"workflow_policy_override_for={str(((report.get('workflow') or {}).get('policy') or {}).get('policy_override_for') or '-')}")
    print(f"plugin_gate_passed={str((report.get('plugin_presence_gate') or {}).get('plugin_gate_passed') or False)}")
    print(
        "skills_snapshot_json="
        + json.dumps(
            {
                "manifest_source": str((report.get("skills_visibility_snapshot") or {}).get("manifest_source") or ""),
                "missing_roles": list((report.get("skills_visibility_snapshot") or {}).get("missing_roles") or []),
                "required_skill_ids": list((report.get("skills_visibility_snapshot") or {}).get("required_skill_ids") or []),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    print(f"phase_stream_json={json.dumps(list(report.get('phase_stream') or []), ensure_ascii=True, separators=(',', ':'))}")
    print(f"phase_stream={phase_stream_compact(list(report.get('phase_stream') or []))}")
    coding_submission = report.get("coding_submission")
    if isinstance(coding_submission, dict):
        print(f"coding_submitted={str(coding_submission.get('submitted') or False)}")
        print(f"coding_task_id={str(coding_submission.get('task_id') or '-')}")

    if report.get("execution"):
        print(f"execution_exit_code={report['execution']['exit_code']}")
        execution_kv = execution_kv_for_contract
        for key in [
            "openclaw_planner_ok",
            "web_evidence_ok",
            "openclaw_flow_ok",
            "openclaw_planner_trace_log",
            "suite_verdict",
            "reviewer_verdict",
            "reviewer_issues_count",
            "sources_verified",
            "multimodal_evidence_count",
        ]:
            if key in execution_kv:
                print(f"{key}={execution_kv.get(key)}")

        receipt = {
            "dispatch_status": str(report.get("public_status") or report.get("status") or "unknown"),
            "human_status": str(report.get("human_status") or ""),
            "workflow_state": str((report.get("workflow") or {}).get("state") or "UNKNOWN"),
            "workflow_route": str((report.get("workflow") or {}).get("route") or route_tier(action)),
            "workflow_next_route": str((report.get("workflow") or {}).get("next_route") or route_tier(action)),
            "suite_verdict": str(execution_kv.get("suite_verdict") or ""),
            "reviewer_verdict": str(execution_kv.get("reviewer_verdict") or ""),
            "reviewer_issues_count": str(execution_kv.get("reviewer_issues_count") or ""),
            "sources_verified": str(execution_kv.get("sources_verified") or ""),
            "multimodal_evidence_count": str(execution_kv.get("multimodal_evidence_count") or ""),
            "retryable": str((report.get("loop_verdict_contract") or {}).get("retryable") or False).lower(),
            "loop_iteration_count": str((report.get("loop_verdict_contract") or {}).get("loop_iteration_count") or 0),
            "loop_max_attempts": str((report.get("loop_verdict_contract") or {}).get("loop_max_attempts") or 1),
            "consistency_token": str(report.get("consistency_token") or ""),
        }
        print(f"dispatch_receipt_json={json.dumps(receipt, ensure_ascii=True, separators=(',', ':'))}")

    loop_contract = report.get("loop_verdict_contract") if isinstance(report.get("loop_verdict_contract"), dict) else {}
    print(f"loop_iteration_count={str(loop_contract.get('loop_iteration_count') or 0)}")
    print(f"loop_max_attempts={str(loop_contract.get('loop_max_attempts') or 1)}")
    print(f"retry_backoff_seconds={str(loop_contract.get('retry_backoff_seconds') or 30)}")
    print(f"retryable={str(loop_contract.get('retryable') or False)}")
    print(f"consistency_token={str(report.get('consistency_token') or '')}")
    autonomous_assessment = report.get("autonomous_assessment") if isinstance(report.get("autonomous_assessment"), dict) else {}
    print(f"autonomous_completion={str(autonomous_assessment.get('completion_state') or 'unknown')}")
    print(f"autonomous_health={str(autonomous_assessment.get('health_state') or 'unknown')}")
    print(f"autonomous_ready={str(autonomous_assessment.get('ready_for_next_auto_task') or False)}")
    blockers_text = ",".join([str(x) for x in (autonomous_assessment.get("blockers") or [])])
    print(f"autonomous_blockers={blockers_text or '-'}")
    convergence_gate = report.get("convergence_gate") if isinstance(report.get("convergence_gate"), dict) else {}
    print(f"convergence_gate_applied={str(convergence_gate.get('applied') or False)}")
    print(f"convergence_gate_passed={str(convergence_gate.get('passed') or False)}")
    unmet_gate_conditions = ",".join([str(x) for x in (convergence_gate.get("unmet_conditions") or []) if str(x)])
    print(f"convergence_gate_unmet={unmet_gate_conditions or '-'}")

    if report.get("preflight"):
        print(f"preflight_ready={report['preflight']['ready']}")
    if report.get("escalation_packet"):
        print(f"escalation_packet={report['escalation_packet']}")
    if report.get("replan_packet"):
        print(f"replan_packet={report['replan_packet']}")

    if report.get("public_status") == "auto_repairing":
        return 0
    if report.get("preflight") and not report["preflight"].get("ready", False):
        return 3
    if report.get("execution") and report["execution"]["exit_code"] != 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
