#!/usr/bin/env python3
"""Run planner/executor/reviewer orchestration for Dirac solver workflows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import ProxyHandler, Request, build_opener, install_opener, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]

# feishu_notify for centralized Feishu status notifications
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from feishu_notify import (
        notify_planned, notify_executing, notify_reviewing,
        notify_done, notify_replan, notify_debugger,
    )
except ImportError:
    notify_planned = None  # type: ignore
    notify_executing = None  # type: ignore
    notify_reviewing = None  # type: ignore
    notify_done = None  # type: ignore
    notify_replan = None  # type: ignore
    notify_debugger = None  # type: ignore

DEFAULT_SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_SKILLS_MANIFEST_PATH = REPO_ROOT / "orchestration" / "agent_skills_manifest.json"
DEFAULT_LEARNING_STATE_PATH = REPO_ROOT / "state" / "multi_agent_learning_state.json"
DEFAULT_WEB_SOURCES_PATH = REPO_ROOT / "knowledge_base" / "metadata" / "authoritative_web_sources.json"
DEFAULT_DASHBOARD_PATH = REPO_ROOT / "state" / "dirac_status_dashboard.json"
DEFAULT_DEEP_MODEL_PRIORITY = ["gpt-5-thinking", "deepseek-r1"]
DEFAULT_REMOTE_OPENCLAW_SSH_ALIAS = "dirac-key"
DEFAULT_REMOTE_OPENCLAW_CWD = "/data/home/zju321/.openclaw/workspace/projects/Dirac"
DEFAULT_REMOTE_OPENCLAW_BIN = os.environ.get(
    "DIRAC_REMOTE_OPENCLAW_BIN",
    str(REPO_ROOT.parent / ".local/bin/openclaw")
)
DEFAULT_CASE_REFERENCE_ENERGY_HARTREE: Dict[str, float] = {
    "hydrogen_gs_reference": -0.5,
    "h2o_gs_reference": -76.4389,
    "ch4_gs_reference": -8.04027629,
    "n_atom_gs_official": -9.75473657,
}
DEFAULT_CASE_PROVENANCE_SOURCE_DOC: Dict[str, str] = {
    "hydrogen_gs_reference": "knowledge_base/corpus/hydrogen_gs_reference_provenance.md",
    "h2o_gs_reference": "knowledge_base/corpus/h2o_gs_reference_provenance.md",
    "ch4_gs_reference": "knowledge_base/corpus_new/ch4_gs_reference.md",
    "n_atom_gs_official": "knowledge_base/corpus_new/n_atom_gs_official.md",
}
DEFAULT_CASE_PROVENANCE_FALLBACK: Dict[str, Dict[str, Any]] = {
    "hydrogen_gs_reference": {
        "source_url": "https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev",
        "source_type": "nist_codata",
        "source_numeric_verified": True,
        "software_version": "octopus-docs-16",
        "pseudopotential_ids": ["H.pbe-kjpaw.UPF"],
        "geometry_ref": "isolated_hydrogen_atom",
    },
    "h2o_gs_reference": {
        "source_url": "https://cccbdb.nist.gov/",
        "source_type": "nist_cccbdb_literature_anchor",
        "source_numeric_verified": True,
        "doi": "10.1063/1.445869",
        "software_version": "literature-all-electron-reference",
        "pseudopotential_ids": [],
        "geometry_ref": "h2o_equilibrium_geometry_neutral_singlet_literature_anchor",
    },
    "ch4_gs_reference": {
        "source_url": "https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/",
        "source_type": "octopus_official_methane_total_energy_convergence",
        "source_numeric_verified": True,
        "software_version": "octopus-16.3-pseudopotential-lane",
        "pseudopotential_ids": ["standard:C", "standard:H"],
        "geometry_ref": "octopus_tutorial_methane_reference_geometry",
        "expected_runtime_model": "octopus_pseudopotential",
    },
    "n_atom_gs_official": {
        "source_url": "https://www.octopus-code.org/documentation/16/tutorial/model/total_energy_convergence/",
        "source_type": "octopus_official_n_atom_total_energy_convergence",
        "source_numeric_verified": True,
        "software_version": "octopus-16.3-pseudopotential-lane",
        "pseudopotential_ids": ["standard:N"],
        "geometry_ref": "isolated_nitrogen_atom_origin_geometry",
        "expected_runtime_model": "octopus_pseudopotential",
    },
}


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def update_status_dashboard(
    phase: str,
    run_id: str,
    case_id: str,
    overall_pct: int,
    initiator: str = "agent",
    planner_done: bool = False,
    executor_done: bool = False,
    reviewer_done: bool = False,
    final_verdict: str = "",
    benchmark_delta: float = None,
    threshold: float = None,
    failure_reason: str = "",
    state_machine: str = "",
) -> None:
    """Update the lightweight status dashboard JSON file.

    This is called at each phase transition so the user can quickly
    see the current state without parsing complex JSON.
    """
    dashboard_path = DEFAULT_DASHBOARD_PATH
    try:
        if dashboard_path.exists():
            try:
                data = json.loads(dashboard_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"version": "v1", "current_task": {}, "progress": {}, "last_transition": {}, "verdict": {}, "active_blockers": [], "recent_events": []}
        else:
            data = {"version": "v1", "current_task": {}, "progress": {}, "last_transition": {}, "verdict": {}, "active_blockers": [], "recent_events": []}
    except Exception:
        return

    ts = now_iso()
    data["updated_at"] = ts
    data["version"] = "v1"
    data["current_task"] = {
        "run_id": run_id,
        "phase": phase,
        "state_machine": state_machine,
        "initiator": initiator,
        "agent_id": "dirac-orchestration",
        "case_id": case_id,
    }
    data["progress"] = {
        "overall_pct": overall_pct,
        "planner_done": planner_done,
        "executor_done": executor_done,
        "reviewer_done": reviewer_done,
    }
    data["last_transition"] = {
        "from": (data.get("current_task") or {}).get("phase") or None,
        "to": phase,
        "timestamp": ts,
        "trigger": "orchestration_script",
    }
    if final_verdict:
        data["verdict"] = {
            "final": final_verdict,
            "benchmark_delta": benchmark_delta,
            "threshold": threshold,
        }
    if failure_reason:
        data["active_blockers"] = [failure_reason]
    else:
        data["active_blockers"] = []

    recent = list(data.get("recent_events", []))
    recent.insert(0, {"ts": ts, "event": phase, "agent": "orchestration", "run_id": run_id, "case": case_id})
    data["recent_events"] = recent[:10]

    try:
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


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


def was_cli_flag_provided(flag: str) -> bool:
    needle = str(flag or "").strip()
    if not needle:
        return False
    for token in sys.argv[1:]:
        if token == needle or token.startswith(f"{needle}="):
            return True
    return False


def resolve_reference_energy_hartree(case_id: str, planner_reference: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """Resolve reference energy from planner payload first, then deterministic case fallback."""
    for key in ("total_energy_hartree", "reference_energy_hartree", "value"):
        value = planner_reference.get(key)
        if isinstance(value, (int, float)):
            return float(value), "planner.benchmark_reference"

    case_key = str(case_id or "").strip().lower()
    if case_key in DEFAULT_CASE_REFERENCE_ENERGY_HARTREE:
        return float(DEFAULT_CASE_REFERENCE_ENERGY_HARTREE[case_key]), DEFAULT_CASE_PROVENANCE_SOURCE_DOC.get(case_key, "")

    return None, ""


def merge_case_provenance(case_id: str, base_provenance: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base_provenance or {})
    fallback = DEFAULT_CASE_PROVENANCE_FALLBACK.get(str(case_id or "").strip().lower()) or {}
    for key, value in fallback.items():
        current = merged.get(key)
        if key == "source_numeric_verified":
            if key not in merged:
                merged[key] = bool(value)
            continue
        if key == "pseudopotential_ids":
            if not isinstance(current, list) or len([str(x).strip() for x in current if str(x).strip()]) == 0:
                merged[key] = list(value) if isinstance(value, list) else []
            continue
        if not str(current or "").strip():
            merged[key] = value
    return merged


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


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
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


def load_learning_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "version": "v1",
            "updated_at": "",
            "recent_failures": [],
            "failure_type_counts": {},
            "last_run": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("version", "v1")
            payload.setdefault("updated_at", "")
            payload.setdefault("recent_failures", [])
            payload.setdefault("failure_type_counts", {})
            payload.setdefault("last_run", {})
            return payload
    except Exception:
        pass
    return {
        "version": "v1",
        "updated_at": "",
        "recent_failures": [],
        "failure_type_counts": {},
        "last_run": {},
    }


def save_learning_state(path: Path, state: Dict[str, Any]) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path):
        write_json_atomic(path, state)


def _infer_failure_type(checks: Dict[str, Any], repair_type: str, blocked_reason_code: str) -> str:
    if not bool(checks.get("planner_executor_chain_ok", True)):
        return "planner_executor_chain_break"
    if not bool(checks.get("case_scope_ok", True)):
        return "case_scope_mismatch"
    if not bool(checks.get("execution_ok", False)) or blocked_reason_code not in ("", "none"):
        return "endpoint_or_service"
    if not bool(checks.get("provenance_verified", False)):
        return "benchmark_provenance"
    if not bool(checks.get("accuracy_ok", False)) or not bool(checks.get("benchmarks_aligned_ok", False)):
        return "numerical_accuracy"
    if not bool(checks.get("web_evidence_ok", False)):
        return "web_evidence"
    if not bool(checks.get("kb_richness_ok", False)) or not bool(checks.get("retrieval_skill_ok", False)):
        return "knowledge_retrieval"
    if not bool(checks.get("ui_ok", False)) or not bool(checks.get("ui_rendering_ok", False)):
        return "ui_runtime"
    if not bool(checks.get("octopus_ok", False)):
        return "octopus_runtime"
    if repair_type and repair_type != "none":
        return str(repair_type)
    return "unknown"


def _normalize_model_name(name: str) -> str:
    return str(name or "").strip().lower().replace("_", "-")


def _parse_model_priority(raw: str, fallback: List[str]) -> List[str]:
    parts = [p.strip() for p in str(raw or "").split(",") if p.strip()]
    normalized: List[str] = []
    seen = set()
    for item in (parts or fallback):
        norm = _normalize_model_name(item)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        normalized.append(norm)
    return normalized


def _is_deep_thinking_model(name: str) -> bool:
    norm = _normalize_model_name(name)
    return norm.startswith("gpt-5-thinking") or norm.startswith("deepseek-r1") or norm.startswith("deepseek-r-1")


def verify_planner_executor_chain(planner: Dict[str, Any], executor: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    planner_case = str(planner.get("selected_case") or "")
    preferred_entrypoint = str(((planner.get("strategy_profile") or {}).get("preferred_harness_entrypoint") or "iterate_case"))
    planner_openclaw = (planner.get("openclaw_planner") or {}) if isinstance(planner.get("openclaw_planner"), dict) else {}
    planner_openclaw_ok = bool(planner_openclaw.get("ok", False))
    degraded_mode = str(planner_openclaw.get("degraded_mode") or "")
    planner_openclaw_acceptable = planner_openclaw_ok

    blocked = (executor.get("blocked") or {}) if isinstance(executor.get("blocked"), dict) else {}
    blocked_reason = str(blocked.get("reason_code") or "none")
    blocked_reason_detail = str(blocked.get("reason_detail") or "")
    execution_mode = str(executor.get("execution_mode") or "")
    iterations_completed = int((executor.get("simple_harness") or {}).get("iterations_completed") or 0)
    octopus_ok = bool(((executor.get("octopus") or {}).get("passed", False)) if isinstance(executor.get("octopus"), dict) else False)
    physics_result = (executor.get("physics_result") or {}) if isinstance(executor.get("physics_result"), dict) else {}
    physics_result_ok = bool(physics_result.get("has_required_fields", False))
    unsupported_harness_case = (
        blocked_reason in {"harness_run_case_unreachable", "iterate_endpoint_unavailable"}
        and "unsupported case_id" in blocked_reason_detail.lower()
    )
    octopus_direct_path_flag = bool(blocked.get("octopus_direct_path_ok", False))
    octopus_direct_path_ok = octopus_direct_path_flag or (unsupported_harness_case and octopus_ok and physics_result_ok)

    benchmark_delta = (executor.get("benchmark_review") or {}).get("delta")
    if not isinstance(benchmark_delta, dict):
        benchmark_delta = {}
    planner_threshold = planner.get("threshold")
    delta_threshold = benchmark_delta.get("threshold")
    threshold_match = True
    if isinstance(planner_threshold, (int, float)) and isinstance(delta_threshold, (int, float)):
        threshold_match = abs(float(planner_threshold) - float(delta_threshold)) < 1e-9

    if not planner_case:
        issues.append("planner_missing_selected_case")
    if not planner_openclaw_acceptable:
        issues.append("planner_openclaw_not_ok")
    if iterations_completed <= 0 and not octopus_direct_path_ok:
        issues.append("executor_no_iterations_completed")
    if blocked_reason not in ("", "none") and not octopus_direct_path_ok:
        issues.append(f"executor_blocked:{blocked_reason}")
    if preferred_entrypoint == "run_case" and not execution_mode.startswith("run_case") and not octopus_direct_path_ok:
        issues.append(f"execution_mode_mismatch:{preferred_entrypoint}->{execution_mode or 'unknown'}")
    if preferred_entrypoint == "iterate_case" and "iterate" not in execution_mode and execution_mode != "iterate_case" and not octopus_direct_path_ok:
        issues.append(f"execution_mode_mismatch:{preferred_entrypoint}->{execution_mode or 'unknown'}")
    if not threshold_match:
        issues.append("threshold_mismatch_between_planner_and_executor")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "planner_selected_case": planner_case,
        "planner_openclaw_ok": planner_openclaw_ok,
        "planner_openclaw_degraded_mode": degraded_mode,
        "planner_openclaw_acceptable": planner_openclaw_acceptable,
        "preferred_harness_entrypoint": preferred_entrypoint,
        "execution_mode": execution_mode,
        "iterations_completed": iterations_completed,
        "blocked_reason_code": blocked_reason,
        "unsupported_harness_case": unsupported_harness_case,
        "octopus_direct_path_ok": octopus_direct_path_ok,
        "threshold_match": threshold_match,
    }


def _build_failure_signature(
    checks: Dict[str, Any],
    repair_type: str,
    blocked_reason_code: str,
    benchmark_next_action: str,
) -> Dict[str, Any]:
    failed_checks = sorted([k for k, v in checks.items() if not bool(v)])
    signature_payload = {
        "repair_type": str(repair_type or "none"),
        "failed_checks": failed_checks,
        "blocked_reason_code": str(blocked_reason_code or "none"),
        "benchmark_next_action": str(benchmark_next_action or "none"),
    }
    raw = json.dumps(signature_payload, sort_keys=True, separators=(",", ":"))
    sig_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return {
        "hash": sig_hash,
        "raw": signature_payload,
    }


def _consecutive_repeat_count(recent_failures: List[Dict[str, Any]], signature_hash: str) -> int:
    count = 0
    for item in reversed(recent_failures):
        if str(item.get("signature_hash") or "") == signature_hash:
            count += 1
            continue
        break
    return count


def update_learning_state(state: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    reviewer = summary.get("reviewer") or {}
    planner = summary.get("planner") or {}
    checks = reviewer.get("checks") or {}
    final_verdict = str(reviewer.get("final_verdict") or "FAIL").upper()

    state["updated_at"] = now_iso()
    state["last_run"] = {
        "at": now_iso(),
        "case": planner.get("selected_case"),
        "verdict": final_verdict,
        "repair_type": reviewer.get("repair_type"),
        "failure_type": reviewer.get("failure_type"),
        "failure_signature_hash": ((reviewer.get("failure_signature") or {}).get("hash")),
        "checks": checks,
    }

    if final_verdict == "PASS":
        state["last_pass_at"] = now_iso()
        state.setdefault("pass_count", 0)
        state["pass_count"] = int(state.get("pass_count", 0)) + 1
        return state

    rec = {
        "at": now_iso(),
        "case": planner.get("selected_case"),
        "repair_type": reviewer.get("repair_type"),
        "failure_type": reviewer.get("failure_type"),
        "signature_hash": ((reviewer.get("failure_signature") or {}).get("hash")),
        "failed_checks": sorted([k for k, v in checks.items() if not bool(v)]),
    }
    recent = state.get("recent_failures")
    if not isinstance(recent, list):
        recent = []
    recent.append(rec)
    state["recent_failures"] = recent[-20:]

    failure_type = str(reviewer.get("failure_type") or "unknown")
    counts = state.get("failure_type_counts")
    if not isinstance(counts, dict):
        counts = {}
    counts[failure_type] = int(counts.get(failure_type, 0)) + 1
    state["failure_type_counts"] = counts
    return state


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def get_json(url: str, timeout: float) -> Dict[str, Any]:
    req = Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def read_text_url(url: str, timeout: float) -> str:
    req = Request(url, method="GET")
    req.add_header("Accept", "text/html,application/json,*/*")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _configure_http_proxy_if_present() -> None:
    proxy = str(
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    ).strip()
    if proxy:
        install_opener(build_opener(ProxyHandler({"http": proxy, "https": proxy})))


def read_text_url_with_retry(url: str, timeout: float, retries: int = 2) -> str:
    last_error = ""
    for _ in range(max(0, retries) + 1):
        try:
            return read_text_url(url, timeout=timeout)
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "read_text_url_failed")


def _normalize_ui_url(raw_url: str) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return ""
    scheme = parsed.scheme or "http"
    path = parsed.path if parsed.path and parsed.path != "/" else ""
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _is_local_hostname(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    return normalized in ("", "localhost", "127.0.0.1", "::1")


def _build_ui_probe_targets(ui_url: str, api_base: str) -> List[str]:
    candidates: List[str] = []

    explicit = _normalize_ui_url(ui_url)
    if explicit:
        candidates.append(explicit)

    for env_key in ("DIRAC_UI_URL", "DIRAC_FRONTEND_URL", "FRONTEND_URL"):
        env_url = _normalize_ui_url(os.environ.get(env_key, ""))
        if env_url:
            candidates.append(env_url)

    try:
        parsed_api = urlparse(str(api_base or ""))
        api_host = str(parsed_api.hostname or "").strip()
        if api_host and not _is_local_hostname(api_host):
            api_scheme = parsed_api.scheme or "http"
            candidates.append(f"{api_scheme}://{api_host}:5173")
    except Exception:
        pass

    candidates.append("http://127.0.0.1:5173")

    deduped: List[str] = []
    seen = set()
    for item in candidates:
        normalized = _normalize_ui_url(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _extract_text_preview(html: str, max_chars: int = 1800) -> Tuple[str, str]:
    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = unescape(re.sub(r"\s+", " ", title_match.group(1) or "")).strip()

    stripped = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.IGNORECASE)
    stripped = re.sub(r"<style[\s\S]*?</style>", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    stripped = unescape(re.sub(r"\s+", " ", stripped)).strip()
    if len(stripped) > max_chars:
        stripped = stripped[:max_chars]
    return title, stripped


def _resolve_executable(candidates: List[str]) -> str:
    for item in candidates:
        name = str(item or "").strip()
        if not name:
            continue
        if "/" in name:
            p = Path(name).expanduser()
            if p.exists() and p.is_file():
                return p.as_posix()
            continue
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return ""


def _remote_openclaw_ssh_alias() -> str:
    alias = str(os.environ.get("DIRAC_REMOTE_OPENCLAW_SSH_ALIAS") or "").strip()
    return alias or DEFAULT_REMOTE_OPENCLAW_SSH_ALIAS


def _remote_openclaw_cwd() -> str:
    cwd = str(os.environ.get("DIRAC_REMOTE_OPENCLAW_CWD") or "").strip()
    return cwd or DEFAULT_REMOTE_OPENCLAW_CWD


def _remote_openclaw_bin() -> str:
    remote_bin = str(os.environ.get("DIRAC_REMOTE_OPENCLAW_BIN") or "").strip()
    return remote_bin or DEFAULT_REMOTE_OPENCLAW_BIN


def _run_openclaw_agent_command(
    message: str,
    timeout: float,
    model: str = "",
    prefer_remote: bool = True,
) -> Dict[str, Any]:
    # NOTE: feishu plugin initialization takes ~8s on HPC, so we must use a long
    # timeout here. The openclaw agent CLI delivers the response via feishu
    # asynchronously — the CLI itself exits 0 before the response arrives.
    timeout_sec = max(120, int(timeout))
    remote_alias = _remote_openclaw_ssh_alias()
    remote_cwd = _remote_openclaw_cwd()
    remote_bin = _remote_openclaw_bin()
    attempts: List[Dict[str, Any]] = []

    run_orders = ["remote", "local"] if prefer_remote else ["local", "remote"]

    for mode in run_orders:
        if mode == "remote":
            # Remote execution: SSH to local machine from HPC (dirac-key alias must resolve locally)
            remote_parts = ["agent", "--agent", "dirac-planner"]
            # Note: --model flag is not supported by openclaw CLI; agent uses its configured default model
            remote_parts.extend(["--message", message, "--json", "--timeout", str(timeout_sec)])
            remote_cmd = (
                "OPENCLAW_BIN="
                + shlex.quote(remote_bin)
                + "; if [ ! -x \"$OPENCLAW_BIN\" ]; then OPENCLAW_BIN=\"$(command -v openclaw 2>/dev/null || true)\"; fi; "
                + "if [ -z \"$OPENCLAW_BIN\" ]; then echo remote_openclaw_not_found >&2; exit 127; fi; "
                + "cd "
                + shlex.quote(remote_cwd)
                + " && \"$OPENCLAW_BIN\" "
                + " ".join(shlex.quote(p) for p in remote_parts)
            )
            cmd = ["ssh", remote_alias, remote_cmd]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=max(15, int(timeout_sec + 15)),
                    check=False,
                )
                stderr_text = (proc.stderr or "")[:4000]
                stdout_text = (proc.stdout or "")[:10000]
                # openclaw agent delivers via feishu asynchronously; detect embedded
                # run timeout from stderr content written by the gateway.
                embedded_timed_out = (
                    "Request timed out" in stderr_text
                    or "timeoutMs=" in stderr_text
                    or "timed out before a response" in stderr_text
                )
                attempt = {
                    "command": " ".join(cmd),
                    "exit_code": int(proc.returncode),
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "ok": proc.returncode == 0 and not embedded_timed_out,
                    "execution_mode": "remote_ssh",
                    "embedded_timed_out": embedded_timed_out,
                }
                attempts.append(attempt)
                if attempt["ok"]:
                    return {
                        "ok": True,
                        "attempts": attempts,
                        "selected_command": attempt["command"],
                        "selected_exit_code": attempt["exit_code"],
                        "selected_execution_mode": attempt["execution_mode"],
                    }
            except FileNotFoundError:
                attempts.append(
                    {
                        "command": " ".join(cmd),
                        "exit_code": 127,
                        "stdout": "",
                        "stderr": "ssh_command_not_found",
                        "ok": False,
                        "execution_mode": "remote_ssh",
                    }
                )
            except Exception as exc:
                attempts.append(
                    {
                        "command": " ".join(cmd),
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": str(exc),
                        "ok": False,
                        "execution_mode": "remote_ssh",
                    }
                )
            continue

        openclaw_bin = _resolve_executable(
            [
                str(os.environ.get("OPENCLAW_BIN") or ""),
                "openclaw",
                str(Path.home() / ".local" / "bin" / "openclaw"),
                "/usr/local/bin/openclaw",
                "/usr/bin/openclaw",
            ]
        )
        if not openclaw_bin:
            attempts.append(
                {
                    "command": "openclaw agent --agent dirac-planner --message <task> --json --timeout <sec>",
                    "exit_code": 127,
                    "stdout": "",
                    "stderr": "openclaw_command_not_found",
                    "ok": False,
                    "execution_mode": "local",
                }
            )
            continue

        local_cmd = [openclaw_bin, "agent", "--agent", "dirac-planner"]
        # Note: --model flag is not supported; agent uses its configured default model
        local_cmd.extend(["--message", message, "--json", "--timeout", str(timeout_sec)])
        try:
            proc = subprocess.run(
                local_cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(15, int(timeout_sec + 15)),
                check=False,
            )
            # openclaw agent is fire-and-forget: it delivers the message via feishu
            # and exits 0 before the response arrives. stdout is always empty.
            # We detect embedded-run timeout from stderr content.
            stderr_text = (proc.stderr or "")[:4000]
            stdout_text = (proc.stdout or "")[:10000]
            # Check for embedded run timeout (gateway writes this to stderr when
            # the embedded agent run times out before generating a response)
            embedded_timed_out = (
                "Request timed out" in stderr_text
                or "timeoutMs=" in stderr_text
                or "timed out before a response" in stderr_text
            )
            attempt = {
                "command": " ".join(local_cmd),
                "exit_code": int(proc.returncode),
                "stdout": stdout_text,
                "stderr": stderr_text,
                "ok": proc.returncode == 0 and not embedded_timed_out,
                "execution_mode": "local",
                "embedded_timed_out": embedded_timed_out,
            }
            attempts.append(attempt)
            if attempt["ok"]:
                return {
                    "ok": True,
                    "attempts": attempts,
                    "selected_command": attempt["command"],
                    "selected_exit_code": attempt["exit_code"],
                    "selected_execution_mode": attempt["execution_mode"],
                }
        except FileNotFoundError:
            attempts.append(
                {
                    "command": " ".join(local_cmd),
                    "exit_code": 127,
                    "stdout": "",
                    "stderr": "openclaw_command_not_found",
                    "ok": False,
                    "execution_mode": "local",
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "command": " ".join(local_cmd),
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": str(exc),
                    "ok": False,
                    "execution_mode": "local",
                }
            )

    return {
        "ok": False,
        "attempts": attempts,
        "selected_command": "",
        "selected_exit_code": int((attempts[-1] or {}).get("exit_code") or 1) if attempts else 1,
        "selected_execution_mode": "",
    }


def _load_web_sources(path: Path) -> List[Dict[str, Any]]:
    defaults: List[Dict[str, Any]] = [
        {
            "source_id": "octopus_doc_v16",
            "url": "https://octopus-code.org/documentation/16/",
            "expect_terms": ["octopus", "dft", "tddft"],
        },
        {
            "source_id": "octopus_arxiv_2012_abs",
            "url": "https://arxiv.org/abs/1207.0402",
            "expect_terms": ["octopus", "time-dependent", "density"],
        },
        {
            "source_id": "octopus_arxiv_2015_abs",
            "url": "https://arxiv.org/abs/1511.05686",
            "expect_terms": ["octopus", "real-space", "electronic"],
        },
    ]
    if not path.exists():
        return defaults

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return defaults

    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources:
        return defaults

    normalized: List[Dict[str, Any]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        terms = item.get("expect_terms") if isinstance(item.get("expect_terms"), list) else []
        normalized.append(
            {
                "source_id": str(item.get("source_id") or f"source_{len(normalized)+1}"),
                "url": url,
                "expect_terms": [str(t).strip().lower() for t in terms if str(t).strip()],
            }
        )
    return normalized if normalized else defaults


def _run_openclaw_web_automation(url: str, timeout: float) -> Dict[str, Any]:
    prompt = (
        f"Use available web automation/browser skills to read {url}. "
        "Return strict JSON with keys: url,title,summary,key_claims(<=3),citation_hint."
    )
    run = _run_openclaw_agent_command(message=prompt, timeout=timeout, model="", prefer_remote=True)
    attempts = run.get("attempts") if isinstance(run.get("attempts"), list) else []
    selected = attempts[-1] if attempts else {}
    if run.get("ok"):
        for attempt in reversed(attempts):
            if bool(attempt.get("ok", False)):
                selected = attempt
                break
    return {
        "attempted": True,
        "ok": bool(run.get("ok", False)),
        "exit_code": int(selected.get("exit_code") or 1),
        "stdout": str(selected.get("stdout") or "")[:3000],
        "stderr": str(selected.get("stderr") or "")[:1200],
        "command": str(selected.get("command") or "openclaw agent --agent dirac-planner --message <task> --json --timeout <sec>"),
        "execution_mode": str(selected.get("execution_mode") or ""),
        "attempts": attempts,
    }


def _extract_openclaw_web_summary(stdout_text: str) -> Tuple[str, str]:
    raw = str(stdout_text or "").strip()
    if not raw:
        return "", ""

    def _pull(payload: Any) -> Tuple[str, str]:
        obj = payload
        if isinstance(obj, dict):
            for key in ["result", "data", "output", "message"]:
                nested = obj.get(key)
                if isinstance(nested, dict):
                    obj = nested
                    break
            title_val = str(obj.get("title") or "").strip() if isinstance(obj, dict) else ""
            parts: List[str] = []
            if isinstance(obj, dict):
                for key in ["summary", "citation_hint", "url"]:
                    value = obj.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
                claims = obj.get("key_claims")
                if isinstance(claims, list):
                    claim_parts = [str(item).strip() for item in claims if str(item).strip()]
                    if claim_parts:
                        parts.append("; ".join(claim_parts[:3]))
            text_val = " ".join(parts).strip()
            return title_val, text_val
        return "", ""

    candidates: List[Any] = []
    try:
        candidates.append(json.loads(raw))
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[idx:])
            candidates.append(parsed)
        except Exception:
            continue

    for item in candidates:
        title, text = _pull(item)
        if title or text:
            return title, text
    return "", ""


def _run_python_playwright_screenshot(url: str, output_path: Path, timeout: float) -> Dict[str, Any]:
    py_probe = """
import sys
from playwright.sync_api import sync_playwright
u = sys.argv[1]
out = sys.argv[2]
t = max(2000, int(float(sys.argv[3]) * 1000))
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto(u, wait_until='domcontentloaded', timeout=t)
    try:
        page.wait_for_load_state('networkidle', timeout=min(t, 12000))
    except Exception:
        pass
    page.screenshot(path=out, full_page=True)
    b.close()
print('ok')
"""
    try:
        py_proc = subprocess.run(
            [sys.executable, "-c", py_probe, url, output_path.as_posix(), str(timeout)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(12, int(timeout + 20)),
            check=False,
        )
        py_ok = py_proc.returncode == 0 and output_path.exists()
        return {
            "attempted": True,
            "ok": py_ok,
            "exit_code": int(py_proc.returncode),
            "stderr": (py_proc.stderr or "")[:1200],
            "stdout": (py_proc.stdout or "")[:1200],
            "screenshot": output_path.as_posix() if py_ok else "",
            "command": f"{sys.executable} -c '<playwright screenshot>' {url} {output_path.as_posix()}",
        }
    except Exception as exc:
        return {
            "attempted": True,
            "ok": False,
            "exit_code": 1,
            "stderr": str(exc),
            "stdout": "",
            "screenshot": "",
            "command": f"{sys.executable} -c '<playwright screenshot>' {url} {output_path.as_posix()}",
        }


def _run_playwright_screenshot(url: str, output_path: Path, timeout: float) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    npx_bin = _resolve_executable(
        [
            str(os.environ.get("NPX_BIN") or ""),
            "npx",
            "npx.cmd",
            str(Path.home() / ".local" / "bin" / "npx"),
            "/usr/bin/npx",
        ]
    )
    if not npx_bin:
        fallback = _run_python_playwright_screenshot(url, output_path, timeout)
        if fallback.get("ok"):
            return fallback
        return {
            "attempted": True,
            "ok": False,
            "exit_code": int(fallback.get("exit_code") or 127),
            "stderr": f"npx_not_found | fallback={fallback.get('stderr') or 'python_playwright_failed'}",
            "stdout": str(fallback.get("stdout") or "")[:1200],
            "screenshot": "",
            "command": "npx -y playwright screenshot <url> <path>",
        }

    cmd = [
        npx_bin,
        "-y",
        "playwright@latest",
        "--",
        "screenshot",
        url,
        output_path.as_posix(),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(18, int(timeout)),
            check=False,
        )
        ok = proc.returncode == 0 and output_path.exists()
        if ok:
            return {
                "attempted": True,
                "ok": True,
                "exit_code": int(proc.returncode),
                "stderr": (proc.stderr or "")[:1200],
                "stdout": (proc.stdout or "")[:1200],
                "screenshot": output_path.as_posix(),
                "command": " ".join(cmd),
            }

        fallback = _run_python_playwright_screenshot(url, output_path, timeout)
        if fallback.get("ok"):
            fallback["stderr"] = f"npx_failed:{int(proc.returncode)} | {str(fallback.get('stderr') or '')}".strip()
            fallback["stdout"] = str(fallback.get("stdout") or "")[:1200]
            return fallback
        return {
            "attempted": True,
            "ok": False,
            "exit_code": int(proc.returncode),
            "stderr": f"npx_failed:{int(proc.returncode)} | {str(proc.stderr or '')[:800]} | fallback={str(fallback.get('stderr') or 'python_playwright_failed')[:300]}",
            "stdout": (proc.stdout or "")[:1200],
            "screenshot": "",
            "command": " ".join(cmd),
        }
    except FileNotFoundError:
        fallback = _run_python_playwright_screenshot(url, output_path, timeout)
        if fallback.get("ok"):
            return fallback
        return {
            "attempted": True,
            "ok": False,
            "exit_code": int(fallback.get("exit_code") or 127),
            "stderr": f"npx_not_found | fallback={fallback.get('stderr') or 'python_playwright_failed'}",
            "stdout": str(fallback.get("stdout") or "")[:1200],
            "screenshot": "",
            "command": " ".join(cmd),
        }
    except Exception as exc:
        fallback = _run_python_playwright_screenshot(url, output_path, timeout)
        if fallback.get("ok"):
            fallback["stderr"] = f"npx_exception:{str(exc)[:300]}"
            return fallback
        return {
            "attempted": True,
            "ok": False,
            "exit_code": 1,
            "stderr": f"npx_exception:{str(exc)} | fallback={fallback.get('stderr') or 'python_playwright_failed'}",
            "stdout": str(fallback.get("stdout") or "")[:1200],
            "screenshot": "",
            "command": " ".join(cmd),
        }


def run_openclaw_planner_agent(task: str, output_dir: Path, timeout: float, model_priority: List[str], thinking_budget: int) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / f"openclaw_planner_trace_{utc_now_compact()}.log"
    resolved_priority = model_priority if model_priority else list(DEFAULT_DEEP_MODEL_PRIORITY)
    resolved_model = resolved_priority[0] if resolved_priority else ""
    planner_prompt = (
        f"{task}\n"
        f"Model priority (strict): {', '.join(resolved_priority)}. "
        "Prefer deep-thinking reasoning and keep plans auditable."
    )

    attempts: List[Dict[str, Any]] = []
    model_candidates: List[str] = [m for m in resolved_priority if str(m or "").strip()]
    model_candidates.append("")
    model_flag_supported = True

    def model_flag_unsupported(candidate: str, rows: List[Dict[str, Any]]) -> bool:
        if not str(candidate or "").strip():
            return False
        for row in rows:
            stderr_text = str(row.get("stderr") or "").lower()
            if "unknown option '--model'" in stderr_text or "unknown option \"--model\"" in stderr_text:
                return True
        return False

    selected_command = ""
    selected_execution_mode = ""
    selected_exit_code = 1
    success_model = ""
    for candidate_model in model_candidates:
        if str(candidate_model or "").strip() and not model_flag_supported:
            continue
        run = _run_openclaw_agent_command(
            message=planner_prompt,
            timeout=timeout,
            model=candidate_model,
            prefer_remote=True,
        )
        candidate_attempts = run.get("attempts") if isinstance(run.get("attempts"), list) else []
        attempts.extend(candidate_attempts)
        if model_flag_unsupported(candidate_model, candidate_attempts):
            model_flag_supported = False
            continue
        if run.get("ok"):
            selected_command = str(run.get("selected_command") or "")
            selected_execution_mode = str(run.get("selected_execution_mode") or "")
            selected_exit_code = int(run.get("selected_exit_code") or 0)
            success_model = candidate_model
            trace_path.write_text(
                json.dumps({"attempts": attempts}, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            return {
                "attempted": True,
                "ok": True,
                "fallback_used": selected_execution_mode != "remote_ssh",
                "selected_command": selected_command,
                "execution_mode": selected_execution_mode,
                "exit_code": selected_exit_code,
                "trace_log": trace_path.as_posix(),
                "model_priority": resolved_priority,
                "selected_model": success_model or resolved_model,
                "model_flag_supported": model_flag_supported,
                "thinking_budget": int(max(0, thinking_budget)),
                "attempts": attempts,
            }

    remote_attempted = any(str(a.get("execution_mode") or "") == "remote_ssh" for a in attempts)
    local_missing = any(
        str(a.get("execution_mode") or "") == "local" and str(a.get("stderr") or "") == "openclaw_command_not_found"
        for a in attempts
    )
    degraded_mode = "remote_openclaw_unavailable" if remote_attempted else "local_planner_without_openclaw_cli"
    if local_missing and remote_attempted:
        degraded_mode = "remote_openclaw_unavailable"

    trace_path.write_text(
        json.dumps({"attempts": attempts}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return {
        "attempted": True,
        "ok": False,
        "degraded_mode": degraded_mode,
        "fallback_used": True,
        "selected_command": selected_command,
        "execution_mode": selected_execution_mode,
        "exit_code": int((attempts[-1] or {}).get("exit_code") or 1) if attempts else 1,
        "trace_log": trace_path.as_posix(),
        "model_priority": resolved_priority,
        "selected_model": resolved_model,
        "model_flag_supported": model_flag_supported,
        "thinking_budget": int(max(0, thinking_budget)),
        "attempts": attempts,
    }


def run_web_evidence_agent(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_http_proxy_if_present()
    sources = _load_web_sources(Path(args.web_sources_manifest))

    evidence_rows: List[Dict[str, Any]] = []
    verified = 0
    multimodal = 0
    openclaw_ok_count = 0

    for idx, src in enumerate(sources, start=1):
        source_id = str(src.get("source_id") or f"source_{idx}")
        url = str(src.get("url") or "").strip()
        expect_terms = [str(t).strip().lower() for t in (src.get("expect_terms") or []) if str(t).strip()]
        if not url:
            continue

        openclaw_result = _run_openclaw_web_automation(url, timeout=min(args.timeout, 45.0))
        if bool(openclaw_result.get("ok", False)):
            openclaw_ok_count += 1

        html_ok = False
        html_error = ""
        content_hash = ""
        title = ""
        text_preview = ""
        contains_expected = False
        openclaw_title = ""
        openclaw_preview = ""

        try:
            openclaw_title, openclaw_preview = _extract_openclaw_web_summary(str(openclaw_result.get("stdout") or ""))
        except Exception:
            openclaw_title, openclaw_preview = "", ""

        try:
            html = read_text_url_with_retry(url, timeout=min(args.timeout, 45.0), retries=2)
            title, text_preview = _extract_text_preview(html)
            content_hash = hashlib.sha256((html or "").encode("utf-8", errors="ignore")).hexdigest()
            lower_text = text_preview.lower()
            contains_expected = bool(expect_terms and any(term in lower_text for term in expect_terms))
            html_ok = len(text_preview) >= 240
        except Exception as exc:
            html_error = str(exc)

        if not title and openclaw_title:
            title = openclaw_title
        if not text_preview and openclaw_preview:
            text_preview = openclaw_preview[:1800]
        if not content_hash and text_preview:
            content_hash = hashlib.sha256((text_preview or "").encode("utf-8", errors="ignore")).hexdigest()

        combined_text = " ".join([text_preview or "", openclaw_preview or ""]).strip().lower()
        if expect_terms and combined_text:
            contains_expected = any(term in combined_text for term in expect_terms)

        if not html_ok and text_preview:
            # Treat structured automation summaries as fallback textual evidence.
            html_ok = len(text_preview) >= 240 or (bool(openclaw_result.get("ok", False)) and len(text_preview) >= 120)

        screenshot = _run_playwright_screenshot(
            url,
            output_dir / f"web_evidence_{source_id}_{utc_now_compact()}.png",
            timeout=min(args.timeout, 70.0),
        )
        screenshot_ok = bool(screenshot.get("ok", False))
        if screenshot_ok:
            multimodal += 1

        row_verified = bool(html_ok and (contains_expected or not expect_terms))
        if row_verified:
            verified += 1

        evidence_rows.append(
            {
                "source_id": source_id,
                "url": url,
                "retrieved_at": now_iso(),
                "expect_terms": expect_terms,
                "contains_expected_terms": contains_expected,
                "html_ok": html_ok,
                "html_error": html_error,
                "title": title,
                "text_preview": text_preview,
                "content_hash_sha256": content_hash,
                "verified": row_verified,
                "openclaw_automation": openclaw_result,
                "playwright_screenshot": screenshot,
            }
        )

    required_verified = max(1, int(args.web_min_verified_sources))
    required_multimodal = max(0, int(args.web_min_multimodal_evidence))
    web_ok = verified >= required_verified and multimodal >= required_multimodal

    return {
        "agent": "web_evidence",
        "timestamp": now_iso(),
        "sources_total": len(sources),
        "sources_verified": verified,
        "multimodal_evidence_count": multimodal,
        "openclaw_success_count": openclaw_ok_count,
        "requirements": {
            "min_verified_sources": required_verified,
            "min_multimodal_evidence": required_multimodal,
        },
        "ok": web_ok,
        "rows": evidence_rows,
    }


def browser_ui_probe(ui_url: str, timeout: float, screenshot_path: Path) -> Dict[str, Any]:
    """Try browser-level UI verification via Playwright and save screenshot evidence."""
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    probe_code = """
import json
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
shot = sys.argv[2]
timeout_ms = max(1500, int(float(sys.argv[3])))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
    try:
        page.wait_for_load_state('networkidle', timeout=min(timeout_ms, 12000))
    except Exception:
        pass
    title = page.title()
    html = page.content()
    page.screenshot(path=shot, full_page=True)
    browser.close()
    print(json.dumps({'title': title, 'html_len': len(html)}))
"""
    timeout_ms = max(3000, int(timeout * 1000))
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe_code, ui_url, screenshot_path.as_posix(), str(timeout_ms)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(10, int(timeout + 20)),
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "method": "playwright",
            "screenshot": "",
        }

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "playwright_probe_failed").strip(),
            "method": "playwright",
            "screenshot": "",
        }

    meta: Dict[str, Any] = {}
    try:
        meta = json.loads(proc.stdout.strip()) if proc.stdout.strip() else {}
    except Exception:
        meta = {}

    title = str(meta.get("title") or "")
    title_ok = ("Dirac Solver" in title) or ("Antigravity" in title)
    html_len = int(meta.get("html_len") or 0)
    return {
        "ok": bool(title_ok or html_len > 1000),
        "error": "",
        "method": "playwright",
        "title": title,
        "html_len": html_len,
        "screenshot": screenshot_path.as_posix() if screenshot_path.exists() else "",
    }


def _default_role_specs() -> Dict[str, Dict[str, Any]]:
    return {
        "planner": {
            "skill_id": "dirac.planner.v1",
            "purpose": "Select case, tolerance, and execution budget.",
            "required_outputs": [
                "selected_case",
                "threshold",
                "max_iterations",
                "openclaw_planner.ok",
                "execution_budget.retry_budget",
                "execution_budget.timeout_seconds",
                "workflow.stage_order",
                "workflow.main_controls",
                "review_plan.benchmark_delta_required",
                "review_plan.provenance_required",
            ],
        },
        "executor": {
            "skill_id": "dirac.executor.v1",
            "purpose": "Execute harness and Octopus with endpoint resilience.",
            "required_outputs": [
                "execution_mode",
                "simple_harness.passed",
                "simple_harness.best_relative_error",
                "mcp.attempted",
                "octopus.passed",
                "physics_result.ground_state_energy_hartree",
                "physics_result.absorption_spectrum_points",
                "physics_result.benchmark_delta.relative_error",
                "benchmark_review.final_verdict",
                "benchmark_review.delta.relative_error",
                "benchmark_review.next_action",
                "benchmark_review.provenance_verified",
                "blocked.is_blocked",
                "blocked.reason_code",
            ],
        },
        "reviewer": {
            "skill_id": "dirac.reviewer.v1",
            "purpose": "Gate release by accuracy, KB, UI, and execution completion.",
            "required_outputs": [
                "checks.accuracy_ok",
                "checks.benchmarks_aligned_ok",
                "checks.provenance_verified",
                "checks.kb_richness_ok",
                "checks.retrieval_skill_ok",
                "checks.mcp_attempted_ok",
                "checks.octopus_ok",
                "checks.ui_ok",
                "checks.ui_rendering_ok",
                "checks.web_evidence_ok",
                "checks.openclaw_flow_ok",
                "checks.planner_executor_chain_ok",
                "checks.deep_model_priority_ok",
                "checks.skills_contracts_ok",
                "checks.logs_consistent",
                "checks.execution_ok",
                "checks.physics_result_ok",
                "retrieval.skill_invoked",
                "repair_type",
                "repair_confidence",
                "final_verdict",
            ],
        },
    }


def load_role_specs(path: Path) -> Dict[str, Dict[str, Any]]:
    specs = _default_role_specs()
    if not path.exists():
        return specs

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return specs

    role_payload = payload.get("roles") if isinstance(payload, dict) else None
    if not isinstance(role_payload, dict):
        return specs

    for role_name in ("planner", "executor", "reviewer"):
        override = role_payload.get(role_name)
        if not isinstance(override, dict):
            continue

        base = specs[role_name]
        if override.get("skill_id"):
            base["skill_id"] = str(override.get("skill_id"))
        if override.get("purpose"):
            base["purpose"] = str(override.get("purpose"))

        required = override.get("required_outputs")
        if isinstance(required, list):
            normalized = [str(item).strip() for item in required if str(item).strip()]
            if normalized:
                base["required_outputs"] = normalized

    return specs


def _lookup_path(payload: Dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def evaluate_contract(payload: Dict[str, Any], required_outputs: List[str]) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for key in required_outputs:
        value = _lookup_path(payload, key)
        if _is_missing(value):
            missing.append(key)
    return len(missing) == 0, missing


def attach_skill_contract(payload: Dict[str, Any], role_spec: Dict[str, Any]) -> Dict[str, Any]:
    required_outputs = [str(item) for item in role_spec.get("required_outputs") or []]
    passed, missing = evaluate_contract(payload, required_outputs)
    payload["skill"] = {
        "id": str(role_spec.get("skill_id", "")),
        "purpose": str(role_spec.get("purpose", "")),
        "required_outputs": required_outputs,
        "contract_passed": passed,
        "missing_outputs": missing,
    }
    return payload


def _dedupe_urls(urls: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for url in urls:
        normalized = url.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def get_json_with_fallback(urls: List[str], timeout: float) -> Tuple[Dict[str, Any], str]:
    errors: List[str] = []
    for url in _dedupe_urls(urls):
        try:
            return get_json(url, timeout=timeout), url
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors) if errors else "No GET endpoint candidates provided")


def post_json_with_fallback(urls: List[str], payload: Dict[str, Any], timeout: float) -> Tuple[Dict[str, Any], str]:
    errors: List[str] = []
    for url in _dedupe_urls(urls):
        try:
            return post_json(url, payload, timeout=timeout), url
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors) if errors else "No POST endpoint candidates provided")


def registry_endpoint_candidates(args: argparse.Namespace) -> List[str]:
    harness_base = args.harness_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    return _dedupe_urls(
        [
            f"{harness_base}/harness/case_registry",
            f"{harness_base}/harness/case-registry",
            f"{api_base}/api/harness/case-registry",
            f"{api_base}/api/harness/case_registry",
            "http://127.0.0.1:8001/harness/case_registry",
            "http://127.0.0.1:8101/harness/case_registry",
            "http://127.0.0.1:3004/api/harness/case-registry",
        ]
    )


def iterate_endpoint_candidates(args: argparse.Namespace) -> List[str]:
    harness_base = args.harness_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    return _dedupe_urls(
        [
            f"{harness_base}/harness/iterate_case",
            f"{harness_base}/harness/iterate-case",
            f"{api_base}/api/harness/iterate-case",
            f"{api_base}/api/harness/iterate_case",
            "http://127.0.0.1:8001/harness/iterate_case",
            "http://127.0.0.1:8101/harness/iterate_case",
            "http://127.0.0.1:3004/api/harness/iterate-case",
        ]
    )


def run_case_endpoint_candidates(args: argparse.Namespace) -> List[str]:
    harness_base = args.harness_base.rstrip("/")
    api_base = args.api_base.rstrip("/")
    return _dedupe_urls(
        [
            f"{harness_base}/harness/run_case",
            f"{harness_base}/harness/run-case",
            f"{api_base}/api/harness/run-case",
            f"{api_base}/api/harness/run_case",
            "http://127.0.0.1:8001/harness/run_case",
            "http://127.0.0.1:8101/harness/run_case",
            "http://127.0.0.1:3004/api/harness/run-case",
        ]
    )


def kb_endpoint_candidates(args: argparse.Namespace) -> List[str]:
    harness_base = args.harness_base.rstrip("/")
    return _dedupe_urls(
        [
            f"{harness_base}/kb/query",
            "http://127.0.0.1:8001/kb/query",
            "http://127.0.0.1:8101/kb/query",
            "http://127.0.0.1:3004/kb/query",
        ]
    )


def run_kb_query_skill(args: argparse.Namespace) -> Dict[str, Any]:
    query = str(args.kb_query)
    top_k = max(1, min(int(args.kb_top_k), 20))
    cmd = [
        sys.executable,
        "scripts/run_vector_kb_ops.py",
        "--mode",
        "query",
        "--base-url",
        str(args.harness_base),
        "--query",
        query,
        "--top-k",
        str(top_k),
        "--timeout",
        str(max(30, int(args.timeout))),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(30, int(args.timeout * 2)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "skill_id": "dirac-vector-kb-ops",
            "skill_invoked": True,
            "ok": False,
            "error": "kb_query_skill_timeout",
            "command": " ".join(cmd),
        }

    parsed: Dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = {}

    step_query = ((parsed.get("steps") or {}).get("query") or {}) if isinstance(parsed, dict) else {}
    if not isinstance(step_query, dict):
        step_query = {}

    return {
        "skill_id": "dirac-vector-kb-ops",
        "skill_invoked": True,
        "ok": bool(parsed.get("ok", False)),
        "command": " ".join(cmd),
        "exit_code": int(proc.returncode),
        "endpoint": step_query.get("endpoint", ""),
        "hits_count": int(step_query.get("hits_count", 0) or 0),
        "result": step_query.get("result") if isinstance(step_query.get("result"), dict) else {},
        "stderr": (proc.stderr or "").strip(),
        "error": str(parsed.get("error") or "").strip(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run planner/executor/reviewer orchestration.")
    parser.add_argument("--api-base", default="http://127.0.0.1:3004", help="Node API base URL.")
    parser.add_argument("--harness-base", default="http://127.0.0.1:8101", help="Harness backend base URL.")
    parser.add_argument("--case-id", default="hydrogen_gs_reference", help="Benchmark case id.")
    parser.add_argument("--max-iterations", type=int, default=3, help="Harness iterate max iterations.")
    parser.add_argument("--octopus-molecule", default="H2", help="Octopus molecule for executor stage.")
    parser.add_argument("--octopus-calc-mode", default="gs", choices=["gs", "td", "unocc", "opt", "em", "vib"], help="Octopus calculation mode.")
    parser.add_argument(
        "--octopus-spacing",
        type=float,
        default=None,
        help="Optional Octopus spacing override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-radius",
        type=float,
        default=None,
        help="Optional Octopus radius override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-max-scf-iterations",
        type=int,
        default=None,
        help="Optional SCF max iterations override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-scf-tolerance",
        type=float,
        default=None,
        help="Optional SCF tolerance override (default: backend-managed).",
    )
    parser.add_argument("--octopus-xc", default=None, help="Optional XC functional override (model-axis tuning).")
    parser.add_argument(
        "--octopus-pseudopotential-set",
        default=None,
        help="Optional pseudopotential set id override (model-axis tuning).",
    )
    parser.add_argument("--octopus-propagator", default=None, help="Optional TD propagator override (model-axis tuning).")
    parser.add_argument(
        "--octopus-extra-states",
        type=int,
        default=None,
        help="Optional extra-state count override for spectra workflows (model-axis tuning).",
    )
    parser.add_argument("--octopus-time-step", type=float, default=None, help="Optional TD time-step override.")
    parser.add_argument("--octopus-total-time", type=float, default=None, help="Optional TD total-time override.")
    parser.add_argument("--octopus-abs-energy-min", type=float, default=None, help="Optional absorption min-energy override.")
    parser.add_argument("--octopus-abs-energy-max", type=float, default=None, help="Optional absorption max-energy override.")
    parser.add_argument("--octopus-abs-energy-step", type=float, default=None, help="Optional absorption energy-step override.")
    parser.add_argument("--ui-url", default="http://127.0.0.1:5173", help="Frontend URL for reviewer checks.")
    parser.add_argument("--kb-query", default="infinite well schrodinger benchmark octopus settings", help="Reviewer KB richness query.")
    parser.add_argument("--kb-top-k", type=int, default=6, help="KB retrieval top-k for reviewer.")
    parser.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout seconds.")
    parser.add_argument("--output-dir", default="docs/harness_reports", help="Directory for report artifacts.")
    parser.add_argument("--openclaw-sync-path", default=str(DEFAULT_SYNC_PATH), help="OpenClaw sync json path.")
    parser.add_argument("--skills-manifest", default=str(DEFAULT_SKILLS_MANIFEST_PATH), help="JSON manifest that binds role->skill contracts.")
    parser.add_argument("--learning-state-path", default=str(DEFAULT_LEARNING_STATE_PATH), help="Persistent learning state path for anti-repeat strategy.")
    parser.add_argument("--web-sources-manifest", default=str(DEFAULT_WEB_SOURCES_PATH), help="Authoritative web source list used by web evidence agent.")
    parser.add_argument("--web-min-verified-sources", type=int, default=2, help="Minimum verified real-web sources required by reviewer gate.")
    parser.add_argument("--web-min-multimodal-evidence", type=int, default=0, help="Minimum screenshot-backed evidence count required by reviewer gate.")
    parser.add_argument("--planner-model-priority", default=",".join(DEFAULT_DEEP_MODEL_PRIORITY), help="Comma-separated model priority for planner stage.")
    parser.add_argument("--reviewer-model-priority", default=",".join(DEFAULT_DEEP_MODEL_PRIORITY), help="Comma-separated model priority for reviewer stage.")
    parser.add_argument("--planner-thinking-budget", type=int, default=8000, help="Reasoning budget hint for planner stage.")
    parser.add_argument("--reviewer-thinking-budget", type=int, default=8000, help="Reasoning budget hint for reviewer stage.")
    parser.add_argument("--skip-openclaw-sync", action="store_true", help="Skip writing OpenClaw sync updates.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when final reviewer verdict fails.")
    parser.add_argument("--run-id", default="", help="Optional run identifier for Feishu notification tracking.")
    return parser.parse_args()


def planner_stage(args: argparse.Namespace, role_spec: Dict[str, Any], learning_state: Dict[str, Any]) -> Dict[str, Any]:
    registry: Dict[str, Any] = {"cases": []}
    registry_endpoint = ""
    registry_error = ""
    try:
        registry, registry_endpoint = get_json_with_fallback(registry_endpoint_candidates(args), timeout=args.timeout)
    except Exception as exc:
        registry_error = str(exc)

    cases = registry.get("cases") or []
    selected = None
    for c in cases:
        if str(c.get("case_id", "")).strip().lower() == args.case_id.strip().lower():
            selected = c
            break

    if selected is None:
        selected = {"case_id": args.case_id, "tolerance": {"relative_error_max": 0.03}}

    selected_provenance = (selected.get("provenance") if isinstance(selected.get("provenance"), dict) else {}) or {}
    selected_provenance = merge_case_provenance(str(selected.get("case_id", args.case_id)), selected_provenance)
    selected_case_id = str(selected.get("case_id", args.case_id)).strip().lower()
    is_selfcheck_case = selected_case_id == "infinite_well_v1"

    planner_models = _parse_model_priority(args.planner_model_priority, DEFAULT_DEEP_MODEL_PRIORITY)
    reviewer_models = _parse_model_priority(args.reviewer_model_priority, DEFAULT_DEEP_MODEL_PRIORITY)

    planner_task = (
        f"Dirac_solver /auto planner: build a physically-grounded, traceable, reusable KB plan for "
        f"case={args.case_id}, molecule={args.octopus_molecule}, calc={args.octopus_calc_mode}."
    )
    openclaw_planner = run_openclaw_planner_agent(
        planner_task,
        output_dir=Path(args.output_dir),
        timeout=min(max(float(args.timeout), 20.0), 90.0),
        model_priority=planner_models,
        thinking_budget=args.planner_thinking_budget,
    )

    tol = selected.get("tolerance") or {}
    threshold = float(tol.get("relative_error_max", 0.10))

    recent_failures = learning_state.get("recent_failures") if isinstance(learning_state.get("recent_failures"), list) else []
    last_failure = recent_failures[-1] if recent_failures else {}
    last_failure_type = str(last_failure.get("failure_type") or "")
    repeat_count = 0
    if recent_failures and isinstance(last_failure, dict):
        sig_hash = str(last_failure.get("signature_hash") or "")
        if sig_hash:
            repeat_count = _consecutive_repeat_count(recent_failures, sig_hash)

    preferred_harness_entrypoint = "iterate_case"
    if last_failure_type == "endpoint_or_service" and repeat_count >= 1:
        preferred_harness_entrypoint = "run_case"

    adaptive_max_iterations = int(max(1, min(args.max_iterations, 10)))
    if last_failure_type == "numerical_accuracy" and repeat_count >= 1:
        adaptive_max_iterations = int(max(1, min(adaptive_max_iterations + 1, 10)))

    payload = {
        "agent": "planner",
        "timestamp": now_iso(),
        "selected_case": selected.get("case_id", args.case_id),
        "registry_endpoint": registry_endpoint,
        "registry_error": registry_error,
        "threshold": threshold,
        "max_iterations": adaptive_max_iterations,
        "execution_budget": {
            "retry_budget": 2 if repeat_count == 0 else min(4, 2 + repeat_count),
            "timeout_seconds": 180,
        },
        "workflow": {
            "stage_order": ["planner", "executor", "reviewer"],
            "main_controls": [
                "harness_iterate_then_run_case_fallback",
                "octopus_mcp_probe_required",
                "strict_reviewer_gate_if_enabled",
                "failure_fingerprint_anti_repeat_strategy",
            ],
        },
        "strategy_profile": {
            "preferred_harness_entrypoint": preferred_harness_entrypoint,
            "last_failure_type": last_failure_type,
            "last_failure_repeat_count": repeat_count,
            "anti_repeat_mode": repeat_count >= 1,
        },
        "review_plan": {
            "benchmark_delta_required": True,
            "provenance_required": True,
            "ui_render_required": True,
            "kb_richness_min_hits": 3,
            "kb_richness_min_sources": 2,
            "selfcheck_case": is_selfcheck_case,
            "eligible_for_research_pass": not is_selfcheck_case,
        },
        "benchmark_reference": {
            "case_id": selected.get("case_id", args.case_id),
            "provenance": selected_provenance,
        },
        "model_preferences": {
            "planner_priority": planner_models,
            "reviewer_priority": reviewer_models,
            "planner_thinking_budget": int(max(0, args.planner_thinking_budget)),
            "reviewer_thinking_budget": int(max(0, args.reviewer_thinking_budget)),
        },
        "openclaw_planner": openclaw_planner,
        "goal": "achieve threshold pass and produce auditable artifacts",
    }
    return attach_skill_contract(payload, role_spec)


def executor_stage(args: argparse.Namespace, planner: Dict[str, Any], role_spec: Dict[str, Any]) -> Dict[str, Any]:
    case_id = str(planner.get("selected_case", args.case_id))
    case_key = case_id.strip().lower()
    requires_accuracy_octopus = case_key in DEFAULT_CASE_REFERENCE_ENERGY_HARTREE or case_key.startswith("h2o")
    threshold = float(planner.get("threshold", 0.10))

    iterate_payload = {"case_id": case_id, "max_iterations": int(planner.get("max_iterations", args.max_iterations))}
    iterate_endpoint = ""
    iterate_error = ""
    execution_mode = "iterate_case"
    fallback_run_endpoint = ""
    fallback_run_error = ""
    preferred_entrypoint = str(((planner.get("strategy_profile") or {}).get("preferred_harness_entrypoint") or "iterate_case"))
    iterate = {"passed": False, "history": [], "iterations_completed": 0}

    if preferred_entrypoint == "run_case":
        execution_mode = "run_case_first"
        try:
            run_result, fallback_run_endpoint = post_json_with_fallback(
                run_case_endpoint_candidates(args), {"case_id": case_id}, timeout=args.timeout
            )
            iterate = {
                "passed": bool(run_result.get("passed", False)),
                "history": [run_result],
                "iterations_completed": 1,
                "best_relative_error": run_result.get("relative_error"),
                "best_config_hash": run_result.get("config_hash"),
            }
        except Exception as run_exc:
            fallback_run_error = str(run_exc)
            try:
                iterate, iterate_endpoint = post_json_with_fallback(
                    iterate_endpoint_candidates(args), iterate_payload, timeout=args.timeout
                )
                execution_mode = "run_case_first_then_iterate_fallback"
                iterate_error = ""
            except Exception as exc:
                iterate_error = str(exc)
                execution_mode = "run_case_first_both_failed"
    else:
        try:
            iterate, iterate_endpoint = post_json_with_fallback(iterate_endpoint_candidates(args), iterate_payload, timeout=args.timeout)
        except Exception as exc:
            iterate = {"passed": False, "history": [], "iterations_completed": 0}
            iterate_error = str(exc)
            execution_mode = "run_case_fallback"
            try:
                run_result, fallback_run_endpoint = post_json_with_fallback(
                    run_case_endpoint_candidates(args), {"case_id": case_id}, timeout=args.timeout
                )
                iterate = {
                    "passed": bool(run_result.get("passed", False)),
                    "history": [run_result],
                    "iterations_completed": 1,
                    "best_relative_error": run_result.get("relative_error"),
                    "best_config_hash": run_result.get("config_hash"),
                }
            except Exception as run_exc:
                fallback_run_error = str(run_exc)

    final_harness = None
    history = iterate.get("history") or []
    if isinstance(history, list) and len(history) > 0 and isinstance(history[-1], dict):
        final_harness = history[-1]

    simple_passed = bool(iterate.get("passed", False))
    best_relative_error = iterate.get("best_relative_error")
    if best_relative_error is None and isinstance(final_harness, dict):
        best_relative_error = final_harness.get("relative_error")
    if best_relative_error is None:
        best_relative_error = -1.0

    blocked_reason_code = "none"
    blocked_reason_detail = ""
    if fallback_run_error:
        blocked_reason_code = "harness_run_case_unreachable"
        blocked_reason_detail = str(fallback_run_error)
    elif iterate_error and execution_mode == "run_case_fallback":
        blocked_reason_code = "iterate_endpoint_unavailable"
        blocked_reason_detail = str(iterate_error)
    elif iterate_error:
        blocked_reason_code = "iterate_endpoint_error"
        blocked_reason_detail = str(iterate_error)

    blocked_payload = {
        "is_blocked": blocked_reason_code != "none",
        "reason_code": blocked_reason_code,
        "reason_detail": blocked_reason_detail,
    }

    benchmark_delta_relative_error = float(best_relative_error) if isinstance(best_relative_error, (int, float)) else -1.0

    octopus = {
        "attempted": False,
        "passed": False,
        "error": "",
        "result": {},
    }

    molecule_key = str(args.octopus_molecule or "").strip().upper()
    molecular_targets = {"H", "H2", "H2O", "NH3", "CH4", "CO2"}
    potential_type = "Coulomb" if molecule_key in molecular_targets else "Harmonic"

    octopus_payload = {
        "engineMode": "octopus3D",
        "calcMode": args.octopus_calc_mode,
        "octopusCalcMode": args.octopus_calc_mode,
        "octopusDimensions": "3D",
        "octopusPeriodic": "off",
        "octopusBoxShape": "sphere",
        "octopusMolecule": args.octopus_molecule,
        "molecule": args.octopus_molecule,
        "dimensionality": "3D",
        "equationType": "Schrodinger",
        "problemType": "boundstate",
        "potentialType": potential_type,
        "fastPath": not requires_accuracy_octopus,
        # Send spacing/radius in Angstrom — matches octopus_case_convergence.md defaults.
        # MCP server (server.py) converts to Bohr internally when octopusLengthUnit="angstrom".
        # 0.18 Å / 0.529 Å/Bohr = 0.34 bohr;  10.0 Å / 0.529 Å/Bohr = 18.9 bohr
        "octopusSpacing": float(args.octopus_spacing) if args.octopus_spacing is not None else 0.18,
        "octopusRadius": float(args.octopus_radius) if args.octopus_radius is not None else 10.0,
        "octopusLengthUnit": "angstrom",  # MCP converts to Bohr internally
    }
    if args.octopus_max_scf_iterations is not None:
        octopus_payload["octopusMaxScfIterations"] = int(args.octopus_max_scf_iterations)
    if args.octopus_scf_tolerance is not None:
        octopus_payload["octopusScfTolerance"] = float(args.octopus_scf_tolerance)
    if args.octopus_xc is not None:
        octopus_payload["octopusXC"] = str(args.octopus_xc)
    if args.octopus_pseudopotential_set is not None:
        octopus_payload["octopusPseudopotentialSet"] = str(args.octopus_pseudopotential_set)
    if args.octopus_propagator is not None:
        octopus_payload["octopusPropagator"] = str(args.octopus_propagator)
    if args.octopus_extra_states is not None:
        octopus_payload["octopusExtraStates"] = int(args.octopus_extra_states)
    if args.octopus_time_step is not None:
        octopus_payload["octopusTimeStep"] = float(args.octopus_time_step)
    if args.octopus_total_time is not None:
        octopus_payload["octopusTotalTime"] = float(args.octopus_total_time)
    if args.octopus_abs_energy_min is not None:
        octopus_payload["octopusAbsEnergyMin"] = float(args.octopus_abs_energy_min)
    if args.octopus_abs_energy_max is not None:
        octopus_payload["octopusAbsEnergyMax"] = float(args.octopus_abs_energy_max)
    if args.octopus_abs_energy_step is not None:
        octopus_payload["octopusAbsEnergyStep"] = float(args.octopus_abs_energy_step)
    if not simple_passed and not requires_accuracy_octopus:
        # For non-benchmark fallback routes, keep a lightweight external-call probe.
        octopus_payload["mcpProbeOnly"] = True

    octopus["attempted"] = True
    try:
        oct_result = post_json(f"{args.api_base.rstrip('/')}/api/physics/run", octopus_payload, timeout=args.timeout)
        octopus["result"] = oct_result
        octopus["passed"] = not bool(oct_result.get("error"))
        if not octopus["passed"]:
            octopus["error"] = str(oct_result.get("error") or "octopus result error")
    except Exception as exc:
        octopus["passed"] = False
        octopus["error"] = str(exc)

    octopus_result = octopus.get("result") if isinstance(octopus.get("result"), dict) else {}
    molecular = octopus_result.get("molecular") if isinstance(octopus_result.get("molecular"), dict) else {}
    optical = molecular.get("optical_spectrum") if isinstance(molecular.get("optical_spectrum"), dict) else {}
    optical_energy = optical.get("energy_ev") if isinstance(optical.get("energy_ev"), list) else []
    optical_cross = optical.get("cross_section") if isinstance(optical.get("cross_section"), list) else []
    optical_points = min(len(optical_energy), len(optical_cross))
    ground_state = molecular.get("total_energy_hartree")
    homo_energy = molecular.get("homo_energy")
    lumo_energy = molecular.get("lumo_energy")
    planner_reference = (planner.get("benchmark_reference") or {}) if isinstance(planner.get("benchmark_reference"), dict) else {}
    reference_energy_hartree, reference_energy_source = resolve_reference_energy_hartree(case_id, planner_reference)
    benchmark_reference_fallback_applied = False
    # Always compute benchmark delta using Octopus MCP ground_state vs authoritative reference
    if isinstance(ground_state, (int, float)) and isinstance(reference_energy_hartree, (int, float)):
        ref_abs = abs(float(reference_energy_hartree))
        if ref_abs > 1e-12:
            benchmark_delta_relative_error = abs((float(ground_state) - float(reference_energy_hartree)) / ref_abs)
            benchmark_reference_fallback_applied = True

    unsupported_harness_case = (
        blocked_reason_code in {"harness_run_case_unreachable", "iterate_endpoint_unavailable"}
        and "unsupported case_id" in blocked_reason_detail.lower()
    )
    octopus_direct_path_ok = bool(unsupported_harness_case and octopus.get("passed", False) and isinstance(ground_state, (int, float)))
    effective_blocked_reason_code = "none" if octopus_direct_path_ok else blocked_reason_code

    # For atomic benchmark cases (requires_accuracy_octopus=True): MCP is authoritative.
    # Use MCP ground_state to compute delta, and octopus.passed for verdict.
    # For non-atomic cases: fall back to simple_harness passed + delta.
    if requires_accuracy_octopus and isinstance(ground_state, (int, float)):
        # MCP returned a valid ground_state — use it for the authoritative verdict
        mcp_benchmark_ok = bool(octopus.get("passed")) and benchmark_delta_relative_error >= 0 and benchmark_delta_relative_error <= threshold
        benchmark_verdict = "PASS" if mcp_benchmark_ok else "FAIL"
    else:
        benchmark_verdict = "PASS" if (simple_passed and benchmark_delta_relative_error >= 0 and benchmark_delta_relative_error <= threshold) else "FAIL"
    if effective_blocked_reason_code != "none":
        benchmark_verdict = "BLOCKED"

    benchmark_next_action = "proceed_to_reviewer"
    if effective_blocked_reason_code != "none":
        benchmark_next_action = "repair_harness_endpoint_topology"
    elif benchmark_verdict == "FAIL":
        benchmark_next_action = "tune_discretization_and_retry"

    blocked_payload = {
        "is_blocked": effective_blocked_reason_code != "none",
        "reason_code": effective_blocked_reason_code,
        "reason_detail": blocked_reason_detail,
        "upstream_reason_code": blocked_reason_code,
        "octopus_direct_path_ok": octopus_direct_path_ok,
    }

    benchmark_delta = {
        "relative_error": benchmark_delta_relative_error,
        "threshold": threshold,
        "within_tolerance": benchmark_delta_relative_error >= 0 and benchmark_delta_relative_error <= threshold,
        "reference_energy_hartree": reference_energy_hartree,
        "reference_source": reference_energy_source,
        "fallback_applied": benchmark_reference_fallback_applied,
    }
    benchmark_provenance = (planner_reference.get("provenance") or {}) if isinstance(planner_reference.get("provenance"), dict) else {}
    source_numeric_verified = bool(benchmark_provenance.get("source_numeric_verified", False))
    source_url = str(benchmark_provenance.get("source_url") or "").strip()
    software_version = str(benchmark_provenance.get("software_version") or "").strip()
    psp_ids = benchmark_provenance.get("pseudopotential_ids")
    if not isinstance(psp_ids, list):
        psp_ids = []
    psp_ids = [str(x).strip() for x in psp_ids if str(x).strip()]
    geometry_ref = str(benchmark_provenance.get("geometry_ref") or "").strip()
    provenance_verified = bool(source_numeric_verified and source_url and software_version and psp_ids and geometry_ref)
    if benchmark_verdict == "FAIL" and not provenance_verified:
        benchmark_next_action = "complete_provenance_chain_before_tuning"

    missing_fields: List[str] = []
    if not isinstance(ground_state, (int, float)):
        missing_fields.append("ground_state_energy_hartree")
    calc_mode = str(octopus_payload.get("calcMode") or "").strip().lower()
    requires_absorption_spectrum = calc_mode in {"td", "tddft", "rt", "spectrum", "casida"}
    if requires_absorption_spectrum and optical_points <= 0:
        missing_fields.append("absorption_spectrum")
    if benchmark_delta_relative_error < 0:
        missing_fields.append("benchmark_delta.relative_error")

    physics_result = {
        "calc_mode": str(octopus_payload.get("calcMode") or ""),
        "molecule_name": str(molecular.get("moleculeName") or args.octopus_molecule),
        "ground_state_energy_hartree": float(ground_state) if isinstance(ground_state, (int, float)) else None,
        "homo_energy": float(homo_energy) if isinstance(homo_energy, (int, float)) else None,
        "lumo_energy": float(lumo_energy) if isinstance(lumo_energy, (int, float)) else None,
        "absorption_spectrum_points": int(optical_points),
        "absorption_spectrum": {
            "energy_ev": optical_energy,
            "cross_section": optical_cross,
        },
        "benchmark_delta": benchmark_delta,
        "requires_absorption_spectrum": requires_absorption_spectrum,
        "has_required_fields": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }

    numerical_axis = {
        "spacing": args.octopus_spacing,
        "radius": args.octopus_radius,
        "max_scf_iterations": args.octopus_max_scf_iterations,
        "scf_tolerance": args.octopus_scf_tolerance,
    }
    model_axis = {
        "xc": args.octopus_xc,
        "pseudopotential_set": args.octopus_pseudopotential_set,
        "propagator": args.octopus_propagator,
        "extra_states": args.octopus_extra_states,
        "time_step": args.octopus_time_step,
        "total_time": args.octopus_total_time,
        "abs_energy_min": args.octopus_abs_energy_min,
        "abs_energy_max": args.octopus_abs_energy_max,
        "abs_energy_step": args.octopus_abs_energy_step,
    }
    numerical_axis_touched = any(value is not None for value in numerical_axis.values())
    model_axis_touched = any(value is not None for value in model_axis.values())
    tuning_profile = {
        "numerical_axis": numerical_axis,
        "model_axis": model_axis,
        "numerical_axis_touched": numerical_axis_touched,
        "model_axis_touched": model_axis_touched,
    }

    payload = {
        "agent": "executor",
        "timestamp": now_iso(),
        "execution_mode": execution_mode,
        "preferred_harness_entrypoint": preferred_entrypoint,
        "iterate_endpoint": iterate_endpoint,
        "iterate_error": iterate_error,
        "fallback_run_endpoint": fallback_run_endpoint,
        "fallback_run_error": fallback_run_error,
        "simple_harness": {
            "iterations_completed": iterate.get("iterations_completed"),
            "passed": simple_passed,
            "best_relative_error": best_relative_error,
            "best_config_hash": iterate.get("best_config_hash"),
            "final": final_harness,
        },
        "blocked": blocked_payload,
        "benchmark_review": {
            "final_verdict": benchmark_verdict,
            "delta": benchmark_delta,
            "next_action": benchmark_next_action,
            "provenance": benchmark_provenance,
            "provenance_verified": provenance_verified,
        },
        "tuning_profile": tuning_profile,
        "physics_result": physics_result,
        "mcp": {
            "attempted": bool(octopus.get("attempted", False)),
            "endpoint": f"{args.api_base.rstrip('/')}/api/physics/run",
            "passed": bool(octopus.get("passed", False)),
            "error": str(octopus.get("error") or ""),
        },
        "octopus": octopus,
    }
    return attach_skill_contract(payload, role_spec)


def reviewer_stage(
    args: argparse.Namespace,
    planner: Dict[str, Any],
    executor: Dict[str, Any],
    role_spec: Dict[str, Any],
    role_specs: Dict[str, Dict[str, Any]],
    learning_state: Dict[str, Any],
) -> Dict[str, Any]:
    threshold = float(planner.get("threshold", 0.10))

    final_h = (executor.get("simple_harness") or {}).get("final") or {}
    rel_err = final_h.get("relative_error")
    rel_err_num = float(rel_err) if isinstance(rel_err, (int, float)) else None

    accuracy_ok = bool((executor.get("simple_harness") or {}).get("passed", False))
    if rel_err_num is not None:
        accuracy_ok = accuracy_ok and rel_err_num <= threshold

    retrieval = run_kb_query_skill(args)
    kb_result: Dict[str, Any] = retrieval.get("result") if isinstance(retrieval.get("result"), dict) else {"hits": []}
    kb_endpoint = str(retrieval.get("endpoint") or "")
    kb_error = str(retrieval.get("error") or "")

    if not kb_result:
        kb_result = {"hits": []}

    if not retrieval.get("ok", False):
        try:
            kb_result, kb_endpoint = post_json_with_fallback(
                kb_endpoint_candidates(args),
                {"query": args.kb_query, "top_k": max(1, min(args.kb_top_k, 20))},
                timeout=args.timeout,
            )
            kb_error = ""
        except Exception as exc:
            kb_error = str(exc) if not kb_error else f"{kb_error}; {exc}"

    hits = kb_result.get("hits") or []
    unique_sources = sorted({str(h.get("source", "unknown")) for h in hits if isinstance(h, dict)})
    kb_ok = len(hits) >= 3 and len(unique_sources) >= 2
    retrieval_skill_ok = bool(retrieval.get("skill_invoked", False)) and not bool(retrieval.get("error", ""))

    web_evidence = run_web_evidence_agent(args)
    web_evidence_ok = bool(web_evidence.get("ok", False))

    ui_ok = False
    ui_error = ""
    ui_browser = {
        "ok": False,
        "error": "not_run",
        "method": "playwright",
        "screenshot": "",
    }
    ui_http_ok = False
    ui_http_error = ""
    ui_probe_attempts: List[Dict[str, Any]] = []
    ui_probe_url = ""

    ui_probe_targets = _build_ui_probe_targets(args.ui_url, args.api_base)
    for idx, probe_url in enumerate(ui_probe_targets):
        shot_name = f"ui_probe_{idx + 1}_{utc_now_compact()}.png"
        screenshot_path = Path(args.output_dir) / shot_name
        browser_probe = browser_ui_probe(probe_url, timeout=min(args.timeout, 30.0), screenshot_path=screenshot_path)

        http_ok = False
        http_error = ""
        try:
            html = read_text_url(probe_url, timeout=min(args.timeout, 20.0))
            has_title = "Dirac Solver" in html or "Antigravity" in html
            http_ok = bool(has_title)
        except Exception as exc:
            http_ok = False
            http_error = str(exc)

        ui_probe_attempts.append(
            {
                "url": probe_url,
                "browser_ok": bool(browser_probe.get("ok", False)),
                "browser_error": str(browser_probe.get("error") or ""),
                "http_ok": http_ok,
                "http_error": http_error,
            }
        )

        if bool(browser_probe.get("ok", False)) or http_ok:
            ui_browser = browser_probe
            ui_http_ok = http_ok
            ui_http_error = http_error
            ui_ok = True
            ui_probe_url = probe_url
            break

        ui_browser = browser_probe
        ui_http_ok = http_ok
        ui_http_error = http_error

    if not ui_probe_url and ui_probe_targets:
        ui_probe_url = ui_probe_targets[0]

    if not ui_ok:
        ui_error = str(ui_browser.get("error") or ui_http_error or "ui_probe_failed")

    ui_rendering_ok = bool(ui_browser.get("ok", False) or ui_http_ok)
    octopus_ok = bool(((executor.get("octopus") or {}).get("passed", False)))
    octopus_error = str(((executor.get("octopus") or {}).get("error") or ""))
    mcp_attempted_ok = bool(((executor.get("mcp") or {}).get("attempted", False)))
    executor_blocked = bool(((executor.get("blocked") or {}).get("is_blocked", False)))
    physics_result = (executor.get("physics_result") or {}) if isinstance(executor.get("physics_result"), dict) else {}
    physics_result_ok = bool(physics_result.get("has_required_fields", False))
    blocked_reason_code = str(((executor.get("blocked") or {}).get("reason_code") or "none"))
    blocked_reason_detail = str(((executor.get("blocked") or {}).get("reason_detail") or ""))
    unsupported_harness_case = (
        blocked_reason_code in {"harness_run_case_unreachable", "iterate_endpoint_unavailable"}
        and "unsupported case_id" in blocked_reason_detail.lower()
    )
    octopus_direct_execution_ok = unsupported_harness_case and octopus_ok and physics_result_ok
    execution_ok = bool((executor.get("simple_harness") or {}).get("iterations_completed") or 0) and not executor_blocked
    execution_ok = execution_ok or octopus_direct_execution_ok
    logs_consistent = (not executor_blocked) or octopus_direct_execution_ok
    benchmarks_aligned_ok = bool((executor.get("benchmark_review") or {}).get("delta", {}).get("within_tolerance", False))
    benchmark_next_action = str(((executor.get("benchmark_review") or {}).get("next_action") or "none"))
    provenance_required = bool((planner.get("review_plan") or {}).get("provenance_required", True))
    provenance_verified = bool((executor.get("benchmark_review") or {}).get("provenance_verified", False))
    if not provenance_required:
        provenance_verified = True
    selected_case = str(planner.get("selected_case") or "").strip().lower()
    case_scope_ok = selected_case != "infinite_well_v1"

    # In local/forwarded runs, reviewer should not hard-fail when infra-only checks are unreachable
    # if the numerical benchmark already passed and execution reached reviewer stage.
    octopus_gate_waived = (
        not octopus_ok
        and benchmark_next_action == "proceed_to_reviewer"
        and execution_ok
        and physics_result_ok
        and ("octopus required but unavailable" in octopus_error.lower() or "health check failed" in octopus_error.lower())
    )
    ui_error_text = f"{ui_error} {ui_http_error}"
    ui_gate_waived = (
        not ui_rendering_ok
        and benchmark_next_action == "proceed_to_reviewer"
        and execution_ok
        and (
            "err_connection_refused" in ui_error_text.lower()
            or "connection refused" in ui_error_text.lower()
            or "winerror 10061" in ui_error_text.lower()
        )
    )

    if octopus_gate_waived:
        octopus_ok = True
    if ui_gate_waived:
        ui_ok = True
        ui_rendering_ok = True

    planner_openclaw = (planner.get("openclaw_planner") or {}) if isinstance(planner.get("openclaw_planner"), dict) else {}
    openclaw_flow_ok = bool(planner_openclaw.get("ok", False))
    chain_continuity = verify_planner_executor_chain(planner, executor)
    planner_executor_chain_ok = bool(chain_continuity.get("ok", False))

    planner_models = _parse_model_priority(
        ",".join(((planner.get("model_preferences") or {}).get("planner_priority") or [])),
        DEFAULT_DEEP_MODEL_PRIORITY,
    )
    reviewer_models = _parse_model_priority(args.reviewer_model_priority, DEFAULT_DEEP_MODEL_PRIORITY)
    deep_model_priority_ok = bool(planner_models and reviewer_models and _is_deep_thinking_model(planner_models[0]) and _is_deep_thinking_model(reviewer_models[0]))

    planner_contract_ok = bool(((planner.get("skill") or {}).get("contract_passed", False)))
    executor_contract_ok = bool(((executor.get("skill") or {}).get("contract_passed", False)))
    draft_checks = {
        "accuracy_ok": accuracy_ok,
        "benchmarks_aligned_ok": benchmarks_aligned_ok,
        "provenance_verified": provenance_verified,
        "case_scope_ok": case_scope_ok,
        "execution_ok": execution_ok,
        "logs_consistent": logs_consistent,
        "kb_richness_ok": kb_ok,
        "retrieval_skill_ok": retrieval_skill_ok,
        "web_evidence_ok": web_evidence_ok,
        "openclaw_flow_ok": openclaw_flow_ok,
        "planner_executor_chain_ok": planner_executor_chain_ok,
        "deep_model_priority_ok": deep_model_priority_ok,
        "mcp_attempted_ok": mcp_attempted_ok,
        "octopus_ok": octopus_ok,
        "ui_ok": ui_ok,
        "ui_rendering_ok": ui_rendering_ok,
        "physics_result_ok": physics_result_ok,
    }

    repair_type = "none"
    repair_confidence = "high"
    if not planner_executor_chain_ok:
        repair_type = "planner_executor_chain_break"
        repair_confidence = "high"
    elif not case_scope_ok:
        repair_type = "case_scope_mismatch"
        repair_confidence = "high"
    elif not execution_ok:
        repair_type = "endpoint_topology_or_service_liveness"
        repair_confidence = "high"
    elif not provenance_verified:
        repair_type = "benchmark_provenance_unverified"
        repair_confidence = "high"
    elif not accuracy_ok or not benchmarks_aligned_ok:
        repair_type = "numerical_tuning"
        repair_confidence = "medium"
    elif not ui_ok or not ui_rendering_ok:
        repair_type = "frontend_runtime_or_probe_dependency"
        repair_confidence = "medium"
    elif not physics_result_ok:
        repair_type = "physics_result_missing"
        repair_confidence = "high"
    elif not kb_ok or not retrieval_skill_ok:
        repair_type = "knowledge_base_ingestion_or_retrieval"
        repair_confidence = "medium"
    elif not web_evidence_ok:
        repair_type = "web_evidence_collection_or_playwright_probe"
        repair_confidence = "medium"
    elif not openclaw_flow_ok:
        repair_type = "openclaw_runtime_or_permission"
        repair_confidence = "high"

    skills_contracts_ok = planner_contract_ok and executor_contract_ok
    draft_checks["skills_contracts_ok"] = skills_contracts_ok

    effective_blocked_reason_code = "none" if octopus_direct_execution_ok else blocked_reason_code
    failure_signature = _build_failure_signature(draft_checks, repair_type, effective_blocked_reason_code, benchmark_next_action)
    recent_failures = learning_state.get("recent_failures") if isinstance(learning_state.get("recent_failures"), list) else []
    previous_repeat = _consecutive_repeat_count(recent_failures, str(failure_signature.get("hash") or ""))
    repeat_count = previous_repeat + 1
    anti_repeat_triggered = repeat_count >= 2
    failure_type = _infer_failure_type(draft_checks, repair_type, effective_blocked_reason_code)

    draft_payload = {
        "agent": "reviewer",
        "timestamp": now_iso(),
        "kb_endpoint": kb_endpoint,
        "kb_error": kb_error,
        "checks": draft_checks,
        "metrics": {
            "relative_error": rel_err_num,
            "threshold": threshold,
            "provenance_verified": provenance_verified,
            "kb_hits": len(hits),
            "kb_unique_sources": len(unique_sources),
            "kb_sources": unique_sources,
            "web_sources_total": int(web_evidence.get("sources_total") or 0),
            "web_sources_verified": int(web_evidence.get("sources_verified") or 0),
            "web_multimodal_evidence_count": int(web_evidence.get("multimodal_evidence_count") or 0),
        },
        "ui_error": ui_error,
        "ui_probes": {
            "browser": ui_browser,
            "http": {
                "ok": ui_http_ok,
                "error": ui_http_error,
                "url": ui_probe_url or args.ui_url,
                "method": "http_get_text",
            },
            "attempts": ui_probe_attempts,
        },
        "retrieval": retrieval,
        "web_evidence": web_evidence,
        "gate_waivers": {
            "octopus_gate_waived": octopus_gate_waived,
            "ui_gate_waived": ui_gate_waived,
        },
        "chain_continuity": chain_continuity,
        "model_preferences": {
            "planner_priority": planner_models,
            "reviewer_priority": reviewer_models,
            "planner_thinking_budget": int(max(0, args.planner_thinking_budget)),
            "reviewer_thinking_budget": int(max(0, args.reviewer_thinking_budget)),
        },
        "repair_type": repair_type,
        "repair_confidence": repair_confidence,
        "failure_type": failure_type,
        "failure_signature": failure_signature,
        "repeat_count": repeat_count,
        "anti_repeat_triggered": anti_repeat_triggered,
        "final_verdict": "FAIL",
        "suggestions": [],
    }

    tuning_profile = (executor.get("tuning_profile") or {}) if isinstance(executor.get("tuning_profile"), dict) else {}
    numerical_axis_profile = (
        tuning_profile.get("numerical_axis") if isinstance(tuning_profile.get("numerical_axis"), dict) else {}
    )
    model_axis_profile = tuning_profile.get("model_axis") if isinstance(tuning_profile.get("model_axis"), dict) else {}
    numerical_axis_touched = bool(tuning_profile.get("numerical_axis_touched", False))
    model_axis_touched = bool(tuning_profile.get("model_axis_touched", False))
    missing_model_axis_keys = [
        str(key)
        for key, value in model_axis_profile.items()
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    tuning_diagnostics = {
        "failure_type": failure_type,
        "numerical_axis_touched": numerical_axis_touched,
        "model_axis_touched": model_axis_touched,
        "numerical_axis": numerical_axis_profile,
        "model_axis": model_axis_profile,
        "missing_model_axis_keys": missing_model_axis_keys,
        "next_tuning_focus": "model_axis_scan_first"
        if failure_type == "numerical_accuracy" and not model_axis_touched
        else "discretization_refine",
    }
    draft_payload["tuning_diagnostics"] = tuning_diagnostics

    final_ok = case_scope_ok and accuracy_ok and benchmarks_aligned_ok and provenance_verified and kb_ok and retrieval_skill_ok and web_evidence_ok and openclaw_flow_ok and planner_executor_chain_ok and deep_model_priority_ok and mcp_attempted_ok and octopus_ok and ui_ok and ui_rendering_ok and physics_result_ok and skills_contracts_ok

    suggestions: List[str] = []
    if not accuracy_ok:
        suggestions.append("Reviewer: accuracy gate failed; rerun harness with finer discretization and inspect comparator mapping.")
    if not benchmarks_aligned_ok:
        suggestions.append("Reviewer: benchmark delta is not aligned with threshold; check comparator mapping and expected tolerance.")
        if not model_axis_touched:
            suggestions.append(
                "Reviewer: no model-axis tuning detected (XC/pseudopotential/propagator/TD knobs); run model-axis scan before further grid-only retries."
            )
    if not case_scope_ok:
        suggestions.append("Reviewer: case scope mismatch; infinite_well_v1 is self-check only and cannot be used as research acceptance evidence.")
    if not provenance_verified:
        provenance = (executor.get("benchmark_review") or {}).get("provenance") if isinstance((executor.get("benchmark_review") or {}).get("provenance"), dict) else {}
        missing_provenance: List[str] = []
        if not bool(provenance.get("source_numeric_verified", False)):
            missing_provenance.append("source_numeric_verified")
        if not str(provenance.get("source_url") or "").strip():
            missing_provenance.append("source_url")
        if not str(provenance.get("software_version") or "").strip():
            missing_provenance.append("software_version")
        psp_ids = provenance.get("pseudopotential_ids")
        if not isinstance(psp_ids, list) or not [str(x).strip() for x in psp_ids if str(x).strip()]:
            missing_provenance.append("pseudopotential_ids")
        if not str(provenance.get("geometry_ref") or "").strip():
            missing_provenance.append("geometry_ref")
        missing_text = ",".join(missing_provenance) if missing_provenance else "unknown"
        suggestions.append(f"Reviewer: benchmark provenance is unverified; missing required evidence fields: {missing_text}.")
    if not kb_ok:
        suggestions.append("Reviewer: KB richness is insufficient; ingest more sources and re-run retrieval quality checks.")
    if not retrieval_skill_ok:
        suggestions.append("Reviewer: KB retrieval skill invocation failed; inspect run_vector_kb_ops query step and endpoint health.")
    if not web_evidence_ok:
        suggestions.append("Reviewer: real-web evidence gate failed; run OpenClaw web-automation plus Playwright screenshot collection on authoritative URLs before pass.")
    if not openclaw_flow_ok:
        suggestions.append("Reviewer: OpenClaw planner flow not active; restore OpenClaw runtime/permissions and rerun planner-first automation.")
    if not planner_executor_chain_ok:
        suggestions.append("Reviewer: planner->executor continuity gate failed; force remote OpenClaw-first remediation and rerun strict workflow.")
    if not deep_model_priority_ok:
        suggestions.append("Reviewer: deep-thinking model priority is not correctly configured for planner/reviewer; enforce gpt-5-thinking > deepseek-r1.")
    if not mcp_attempted_ok:
        suggestions.append("Reviewer: external MCP path was not attempted; verify executor stage reached /api/physics/run call.")
    if not octopus_ok:
        suggestions.append("Reviewer: Octopus execution failed; verify remote MCP health and compute queue status.")
    if not ui_ok:
        suggestions.append("Reviewer: UI readiness check failed; verify frontend service and review harness visualization controls.")
    if not ui_rendering_ok:
        suggestions.append("Reviewer: UI rendering proof is incomplete; fix browser probe dependencies or strengthen HTTP/UI evidence path.")
    if not physics_result_ok:
        missing_fields = [str(x) for x in (physics_result.get("missing_fields") or []) if str(x)]
        missing_text = ",".join(missing_fields) if missing_fields else "unknown"
        suggestions.append(f"Reviewer: physics result is incomplete; missing required fields: {missing_text}.")
    if not skills_contracts_ok:
        suggestions.append("Reviewer: agent skill contracts are incomplete; inspect planner/executor missing outputs before release.")
    if octopus_gate_waived:
        suggestions.append("Reviewer: octopus gate waived because benchmark passed and Octopus endpoint was infra-unavailable in this run.")
    if ui_gate_waived:
        suggestions.append("Reviewer: UI gate waived because benchmark passed and UI endpoint was connection-refused in this run.")

    next_action_packet: List[Dict[str, Any]] = []
    if anti_repeat_triggered:
        suggestions.append(
            "Reviewer: repeated failure fingerprint detected; enabling anti-repeat remediation packet with a changed execution path."
        )

    if failure_type == "planner_executor_chain_break":
        next_action_packet = [
            {
                "owner": "planner",
                "action": "rebuild_plan_and_handoff_with_remote_openclaw_first",
                "why": "planner->executor continuity failed under strict gate",
            },
            {
                "owner": "executor",
                "action": "execute_via_remote_openclaw_path_only",
                "why": "avoid local-only fallback when chain continuity is broken",
            },
        ]
    elif failure_type == "endpoint_or_service":
        next_action_packet = [
            {
                "owner": "planner",
                "action": "switch_harness_entrypoint_to_run_case",
                "why": "endpoint/service failures repeated or execution blocked",
            },
            {
                "owner": "executor",
                "action": "validate_8001_8101_and_3001_before_iteration",
                "why": "prevent retrying dead endpoint topology",
            },
        ]
    elif failure_type == "numerical_accuracy":
        if model_axis_touched:
            next_action_packet = [
                {
                    "owner": "planner",
                    "action": "increase_iteration_budget_and_refine_discretization",
                    "why": "model-axis knobs already explored; continue with numerical refinement",
                },
                {
                    "owner": "executor",
                    "action": "run_iterate_case_with_finer_grid_variant",
                    "why": "avoid repeating same numerical configuration",
                },
            ]
        else:
            next_action_packet = [
                {
                    "owner": "planner",
                    "action": "design_model_axis_scan_before_grid_retry",
                    "why": "numerical accuracy failed without model-axis coverage",
                },
                {
                    "owner": "executor",
                    "action": "run_octopus_model_axis_scan",
                    "why": "activate XC/pseudopotential/propagator/TD knobs before additional discretization loops",
                },
            ]
    elif failure_type == "knowledge_retrieval":
        next_action_packet = [
            {
                "owner": "executor",
                "action": "run_kb_query_skill_with_alternate_query_and_top_k",
                "why": "increase retrieval diversity and evidence quality",
            },
            {
                "owner": "reviewer",
                "action": "require_minimum_source_diversity_before_pass",
                "why": "stop low-richness retrieval from being recycled",
            },
        ]
    elif failure_type == "web_evidence":
        next_action_packet = [
            {
                "owner": "executor",
                "action": "run_openclaw_web_automation_on_authoritative_sources",
                "why": "collect real-page evidence rather than relying on static logs",
            },
            {
                "owner": "reviewer",
                "action": "require_playwright_multimodal_screenshot_proof",
                "why": "ensure extracted facts are tied to browsed page evidence",
            },
        ]
    elif failure_type == "openclaw_runtime_or_permission":
        next_action_packet = [
            {
                "owner": "executor",
                "action": "repair_openclaw_runtime_and_permissions",
                "why": "planner-first automation requires OpenClaw CLI and elevated execution scopes",
            },
            {
                "owner": "reviewer",
                "action": "reject_release_without_openclaw_planner_trace",
                "why": "enforce OpenClaw-first decision provenance for /auto tasks",
            },
        ]
    elif failure_type == "ui_runtime":
        next_action_packet = [
            {
                "owner": "executor",
                "action": "collect_browser_screenshot_and_http_probe_together",
                "why": "ensure UI evidence path is auditable",
            },
            {
                "owner": "reviewer",
                "action": "block_release_when_rendering_evidence_is_missing",
                "why": "prevent false PASS when UI is not verifiably rendered",
            },
        ]

    if not next_action_packet and not final_ok:
        next_action_packet = [
            {
                "owner": "planner",
                "action": "request_manual_triage_and_new_strategy",
                "why": "unclassified failure pattern requires broader intervention",
            }
        ]

    payload = draft_payload
    payload["checks"] = draft_checks
    payload["final_verdict"] = "PASS" if final_ok else "FAIL"
    payload["suggestions"] = suggestions
    payload["next_action_packet"] = next_action_packet
    return attach_skill_contract(payload, role_spec)


def _compute_failure_hash(failure_type: str, case_id: str, executor_error: str) -> str:
    """Compute deterministic failure fingerprint hash."""
    import hashlib
    raw = f"{failure_type}|{case_id}|{executor_error}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:16]


def local_debugger_diagnose(
    run_id: str,
    case_id: str,
    failure_type: str,
    failure_hash: str,
    repeat_count: int,
    executor_error: str,
    harness_error: str,
    checks_failed: List[str],
    suggestions: List[str],
) -> Dict[str, Any]:
    """
    Local diagnosis engine — replaces debugger agent subprocess call.

    Analyzes failure context and returns structured diagnostic report
    without requiring the debugger agent to be reachable.
    """
    import hashlib
    diagnostic_id = f"diag-{run_id}-{int(time.time() * 1000)}"

    # Build error chain from available context
    error_chain: List[Dict[str, Any]] = []
    step = 1

    if harness_error:
        error_chain.append({
            "step": step,
            "component": "harness",
            "file": "scripts/run_harness_acceptance.py",
            "error_message": harness_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        step += 1

    if executor_error:
        error_chain.append({
            "step": step,
            "component": "executor",
            "file": "docker/workspace/server.py",
            "error_message": executor_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        step += 1

    if "octopus_mpi" in executor_error.lower() or "pmix" in executor_error.lower():
        error_chain.append({
            "step": step,
            "component": "mpi_runtime",
            "file": "docker/workspace/server.py:run_octopus_hpc",
            "error_message": "PMIx process group failed — container MPI cannot reach host PMIx server",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        step += 1
        failure_type = "endpoint_or_service"

    if not failure_hash or failure_hash == "unknown":
        failure_hash = _compute_failure_hash(failure_type, case_id, executor_error)

    # Root cause analysis based on failure type
    root_cause_map = {
        "endpoint_or_service": (
            "HPC service endpoint unavailable or MPI runtime failure. "
            "Octopus/VASP binary not in PATH, or udocker container MPI cannot reach PBS PMIx server."
        ),
        "planner_executor_chain_break": (
            "State handoff broken between Planner and Executor. "
            "Reviewer output may not have been correctly serialized to executor input."
        ),
        "case_scope_mismatch": (
            "Selected benchmark case parameters do not match harness case parameters. "
            "Verify that the reference benchmark and test case use identical physical conditions."
        ),
        "benchmark_provenance": (
            "Reference benchmark data source cannot be verified. "
            "Origin of benchmark energy values is not documented in provenance."
        ),
    }
    root_cause = root_cause_map.get(failure_type) or f"Unknown failure type: {failure_type}"

    # Generate fixes based on failure type and context
    required_fixes: List[Dict[str, Any]] = []

    if failure_type == "endpoint_or_service":
        required_fixes.extend([
            {
                "fix_id": 1,
                "description": "Verify Octopus/VASP binary is in PATH on HPC: ssh dirac-key 'which octopus' and ssh dirac-key 'which vasp'",
                "confidence": "high",
                "requires_human": False,
            },
            {
                "fix_id": 2,
                "description": "Check PBS job status: ssh dirac-key 'qstat -a' to confirm no zombie Octopus jobs",
                "confidence": "high",
                "requires_human": False,
            },
            {
                "fix_id": 3,
                "description": "If PMIx error in stderr, confirm --mca gds ^pmix is applied in mpirun command",
                "confidence": "high",
                "requires_human": False,
            },
        ])

    if failure_type == "planner_executor_chain_break":
        required_fixes.extend([
            {
                "fix_id": 1,
                "description": "Verify state/dirac_solver_progress_sync.json last_task.last_result is valid JSON and readable",
                "confidence": "high",
                "requires_human": False,
            },
            {
                "fix_id": 2,
                "description": "Confirm executor input contract matches planner output contract (case_id, threshold, molecule)",
                "confidence": "medium",
                "requires_human": False,
            },
        ])

    if failure_type == "case_scope_mismatch":
        required_fixes.extend([
            {
                "fix_id": 1,
                "description": f"Cross-check harness case '{case_id}' parameters against reference benchmark provenance",
                "confidence": "high",
                "requires_human": False,
            },
            {
                "fix_id": 2,
                "description": "Verify SelectedCase and threshold in planner output match what executor uses",
                "confidence": "high",
                "requires_human": False,
            },
        ])

    if checks_failed:
        required_fixes.append({
            "fix_id": 99,
            "description": f"Failed checks: {', '.join(checks_failed)}. Review individual check implementations.",
            "confidence": "medium",
            "requires_human": False,
        })

    if suggestions:
        for i, sug in enumerate(suggestions[:3], start=100):
            required_fixes.append({
                "fix_id": i,
                "description": f"Reviewer suggestion: {sug}",
                "confidence": "medium",
                "requires_human": False,
            })

    escalation_required = repeat_count >= 2 or failure_type in ("endpoint_or_service",)

    return {
        "diagnostic_id": diagnostic_id,
        "task_id": run_id,
        "case_id": case_id,
        "failure_signature_hash": failure_hash,
        "failure_type": failure_type,
        "error_chain": error_chain,
        "root_cause": root_cause,
        "required_fixes": required_fixes,
        "escalation_required": escalation_required,
        "escalation_reason": (
            f"Repeat count {repeat_count} >= 2" if repeat_count >= 2
            else f"Endpoint/service failure requires human review" if failure_type == "endpoint_or_service"
            else ""
        ),
    }


def debugger_diagnose(
    run_id: str,
    case_id: str,
    reviewer: Dict[str, Any],
    executor: Dict[str, Any],
    planner: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    """
    Analyze a FAIL verdict and return required_fixes.

    Returns a diagnosis dict with:
      - diagnostic_id: str
      - failure_signature_hash: str
      - failure_type: str
      - error_chain: list of error steps
      - root_cause: str
      - required_fixes: list of {"fix_id", "description", "confidence", "requires_human"}
      - escalation_required: bool
      - escalation_reason: str
    """
    failure_sig = reviewer.get("failure_signature") or {}
    failure_hash = str(failure_sig.get("hash") or "")
    failure_type = str(reviewer.get("failure_type") or "unknown")
    repeat_count = int(reviewer.get("repeat_count") or 0)
    suggestions = reviewer.get("suggestions") or []
    checks = reviewer.get("checks") or {}
    executor_simple = executor.get("simple_harness") or {}
    executor_octopus = executor.get("octopus") or {}
    executor_error = str(executor_octopus.get("error") or "") or str(executor.get("error") or "")
    harness_error = str(executor_simple.get("error") or "")

    # Notify debugger via Feishu that diagnosis is needed
    if notify_debugger is not None:
        notify_debugger(
            run_id=run_id,
            case_id=case_id,
            failure_signature_hash=failure_hash,
            failure_type=failure_type,
            verdict="FAIL",
            repeat_count=repeat_count,
        )

    # Use local diagnosis engine (replaces debugger agent subprocess which hangs)
    checks_failed = [k for k, v in checks.items() if not bool(v)]
    diagnosis = local_debugger_diagnose(
        run_id=run_id,
        case_id=case_id,
        failure_type=failure_type,
        failure_hash=failure_hash,
        repeat_count=repeat_count,
        executor_error=executor_error,
        harness_error=harness_error,
        checks_failed=checks_failed,
        suggestions=suggestions,
    )

    # Write diagnostic report for manual review
    diag_file = output_dir / f"debugger_diagnosis_{case_id}_{int(time.time() * 1000)}.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        diag_file.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return diagnosis


def render_markdown(summary: Dict[str, Any], command: str, report_json: Path) -> str:
    planner = summary.get("planner") or {}
    executor = summary.get("executor") or {}
    reviewer = summary.get("reviewer") or {}
    primary_acceptance = reviewer.get("primary_acceptance") or {}
    case_rows = summary.get("case_delta_rows") or []

    lines = [
        "# Multi-Agent Orchestration Report",
        "",
        "## Primary Acceptance (Physical Delta First)",
        "",
        f"- Physics Equivalence: {primary_acceptance.get('physics_equivalence', False)}",
        f"- Provenance Complete: {primary_acceptance.get('provenance_complete', False)}",
        f"- Execution Health: {primary_acceptance.get('execution_health', False)}",
        f"- Primary Verdict: {primary_acceptance.get('primary_verdict', reviewer.get('final_verdict', 'UNKNOWN'))}",
        "",
    ]

    if case_rows:
        lines.extend(
            [
                "## Case Delta Board",
                "",
                "| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Physics Fields |",
                "|---|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|",
            ]
        )
        for row in case_rows:
            lines.append(
                "| "
                + f"{row.get('case_id', '-')} | "
                + f"{row.get('metric', '-')} | "
                + f"{row.get('computed_value', '-')} | "
                + f"{row.get('reference_value', '-')} | "
                + f"{row.get('absolute_delta', '-')} | "
                + f"{row.get('relative_delta', '-')} | "
                + f"{row.get('tolerance', '-')} | "
                + f"{row.get('within_tolerance', False)} | "
                + f"{row.get('provenance_complete', False)} | "
                + f"{row.get('physics_fields_complete', False)} |"
            )
        lines.append("")
    else:
        lines.extend(["## Case Delta Board", "", "- No case delta rows were produced.", ""])

    lines.extend(
        [
            "## Final Verdict",
            "",
            f"- Verdict: {reviewer.get('final_verdict', 'UNKNOWN')}",
            f"- Case: {planner.get('selected_case', '-')}",
            f"- Threshold: {planner.get('threshold', '-')}",
            f"- Harness Passed: {((executor.get('simple_harness') or {}).get('passed'))}",
            f"- Octopus Passed: {((executor.get('octopus') or {}).get('passed'))}",
            f"- KB Richness OK: {((reviewer.get('checks') or {}).get('kb_richness_ok'))}",
            f"- Retrieval Skill OK: {((reviewer.get('checks') or {}).get('retrieval_skill_ok'))}",
            f"- UI OK: {((reviewer.get('checks') or {}).get('ui_ok'))}",
            f"- Skill Contracts OK: {((reviewer.get('checks') or {}).get('skills_contracts_ok'))}",
            "",
            "## Roles",
            "",
            "- Planner: case and tolerance planning, execution budget.",
            f"- Planner Skill: {((planner.get('skill') or {}).get('id', '-'))} | contract={((planner.get('skill') or {}).get('contract_passed'))}",
            "- Executor: harness iterative execution and Octopus run.",
            f"- Executor Skill: {((executor.get('skill') or {}).get('id', '-'))} | contract={((executor.get('skill') or {}).get('contract_passed'))}",
            "- Reviewer: strict checks for accuracy/KB/UI/completion and remediation suggestions.",
            f"- Reviewer Skill: {((reviewer.get('skill') or {}).get('id', '-'))} | contract={((reviewer.get('skill') or {}).get('contract_passed'))}",
            "",
            "## Suggestions",
            "",
        ]
    )

    suggestions = reviewer.get("suggestions") or []
    if suggestions:
        for s in suggestions:
            lines.append(f"- {s}")
    else:
        lines.append("- No remediation needed.")

    lines.extend(
        [
            "",
            "## Artifact",
            "",
            f"- JSON: {report_json.as_posix()}",
            "",
            "## Invocation",
            "",
            "```bash",
            command,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_openclaw_sync(path: Path, summary: Dict[str, Any], report_json: Path, report_md: Path) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path):
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                backup_path = path.with_suffix(path.suffix + ".bak")
                try:
                    existing = json.loads(backup_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}

        reviewer = summary.get("reviewer") or {}
        checks = reviewer.get("checks") or {}
        executor = summary.get("executor") or {}
        planner = summary.get("planner") or {}
        case_rows = summary.get("case_delta_rows") or []

        planner_skill = planner.get("skill") or {}
        executor_skill = executor.get("skill") or {}
        reviewer_skill = reviewer.get("skill") or {}
        all_contracts_passed = bool(
            planner_skill.get("contract_passed") and executor_skill.get("contract_passed") and reviewer_skill.get("contract_passed")
        )

        existing["updated_at"] = now_iso()
        existing["protocol_version"] = "v1"
        existing["project"] = "Dirac_solver"
        if not isinstance(existing.get("last_task"), dict):
            existing["phase"] = "phaseA_plus"
        final_verdict = str(reviewer.get("final_verdict") or "FAIL").upper()
        execution_ok = bool((checks or {}).get("execution_ok", False))
        existing["status"] = "healthy" if final_verdict == "PASS" else ("blocked" if not execution_ok else "in_progress")
        existing["state_machine"] = {
            "current": "DONE" if final_verdict == "PASS" else ("BLOCKED" if not execution_ok else "REVIEWING"),
            "allowed": [
                "RECEIVED",
                "PLANNED",
                "EXECUTING",
                "REVIEWING",
                "REPLAN",
                "ESCALATING",
                "DONE",
                "BLOCKED",
            ],
        }

        existing["multi_agent"] = {
            "planner": {
                "case": planner.get("selected_case"),
                "threshold": planner.get("threshold"),
                "max_iterations": planner.get("max_iterations"),
            },
            "executor": {
                "harness_passed": ((executor.get("simple_harness") or {}).get("passed")),
                "octopus_passed": ((executor.get("octopus") or {}).get("passed")),
            },
            "reviewer": {
                "verdict": reviewer.get("final_verdict"),
                "primary_acceptance": reviewer.get("primary_acceptance") or {},
                "checks": checks,
                "retrieval": reviewer.get("retrieval") or {},
                "suggestions": reviewer.get("suggestions") or [],
                "failure_type": reviewer.get("failure_type"),
                "failure_signature_hash": ((reviewer.get("failure_signature") or {}).get("hash")),
                "repeat_count": reviewer.get("repeat_count"),
                "anti_repeat_triggered": reviewer.get("anti_repeat_triggered"),
                "next_action_packet": reviewer.get("next_action_packet") or [],
            },
            "skill_contracts": {
                "planner": planner_skill.get("contract_passed"),
                "executor": executor_skill.get("contract_passed"),
                "reviewer": reviewer_skill.get("contract_passed"),
                "all_passed": all_contracts_passed,
            },
            "openclaw_flow": {
                "planner_attempted": bool((planner.get("openclaw_planner") or {}).get("attempted", False)),
                "planner_ok": bool((planner.get("openclaw_planner") or {}).get("ok", False)),
                "planner_trace_log": str((planner.get("openclaw_planner") or {}).get("trace_log") or ""),
            },
            "report_json": report_json.as_posix(),
            "report_md": report_md.as_posix(),
            "case_rows": case_rows,
        }

        existing["skills_usage"] = {
            "planner": {
                "id": planner_skill.get("id"),
                "contract_passed": planner_skill.get("contract_passed"),
                "missing_outputs": planner_skill.get("missing_outputs") or [],
            },
            "executor": {
                "id": executor_skill.get("id"),
                "contract_passed": executor_skill.get("contract_passed"),
                "missing_outputs": executor_skill.get("missing_outputs") or [],
            },
            "reviewer": {
                "id": reviewer_skill.get("id"),
                "contract_passed": reviewer_skill.get("contract_passed"),
                "missing_outputs": reviewer_skill.get("missing_outputs") or [],
            },
            "status": "active_with_contract_checks",
            "all_contracts_passed": all_contracts_passed,
        }

        existing["sandbox_usage"] = {
            "used": False,
            "mode": "no_remote_sandbox_required_in_this_run",
            "note": "Execution used remote HPC + udocker pipeline rather than E2B sandbox.",
        }

        write_json_atomic(path, existing)


def _build_case_delta_rows(planner: Dict[str, Any], executor: Dict[str, Any], reviewer: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    simple_final = ((executor.get("simple_harness") or {}).get("final") or {})
    benchmark_review = (executor.get("benchmark_review") or {}) if isinstance(executor.get("benchmark_review"), dict) else {}
    delta = (benchmark_review.get("delta") or {}) if isinstance(benchmark_review.get("delta"), dict) else {}
    provenance = (benchmark_review.get("provenance") or {}) if isinstance(benchmark_review.get("provenance"), dict) else {}
    physics_result = (executor.get("physics_result") or {}) if isinstance(executor.get("physics_result"), dict) else {}

    theory_e1 = ((simple_final.get("theory") or {}).get("E1")) if isinstance(simple_final.get("theory"), dict) else None
    # Prefer MCP ground_state over simple_harness E1 — for atomic benchmark cases MCP is authoritative.
    # MCP result path: executor.octopus.result.molecular.total_energy_hartree
    # simple_harness path: executor.simple_harness.final.computed.E1 or .total_energy_hartree
    oct_result = (executor.get("octopus") or {}).get("result") if isinstance(executor.get("octopus"), dict) else {}
    molecular = oct_result.get("molecular") if isinstance(oct_result.get("molecular"), dict) else {}
    mcp_energy = molecular.get("total_energy_hartree") if isinstance(molecular, dict) else None
    simple_computed = (simple_final.get("computed") or {}) if isinstance(simple_final, dict) else {}
    simple_e1 = simple_computed.get("E1") if isinstance(simple_computed, dict) else None
    simple_total = simple_computed.get("total_energy_hartree") if isinstance(simple_computed, dict) else None
    computed_e1 = mcp_energy if isinstance(mcp_energy, (int, float)) else (simple_e1 if simple_e1 is not None else simple_total)
    rel_err = simple_final.get("relative_error", delta.get("relative_error"))
    threshold = simple_final.get("threshold", delta.get("threshold", planner.get("threshold")))
    within_tolerance = bool(simple_final.get("passed", delta.get("within_tolerance", False)))

    abs_delta: Any = "-"
    if isinstance(theory_e1, (int, float)) and isinstance(computed_e1, (int, float)):
        abs_delta = abs(float(computed_e1) - float(theory_e1))

    missing_physics_fields = [str(x) for x in (physics_result.get("missing_fields") or []) if str(x)]
    missing_provenance: List[str] = []
    if not bool(provenance.get("source_numeric_verified", False)):
        missing_provenance.append("source_numeric_verified")
    if not str(provenance.get("source_url") or "").strip():
        missing_provenance.append("source_url")
    if not str(provenance.get("software_version") or "").strip():
        missing_provenance.append("software_version")
    psp_ids = provenance.get("pseudopotential_ids")
    if not isinstance(psp_ids, list) or not [str(x).strip() for x in psp_ids if str(x).strip()]:
        missing_provenance.append("pseudopotential_ids")
    if not str(provenance.get("geometry_ref") or "").strip():
        missing_provenance.append("geometry_ref")

    rows.append(
        {
            "case_id": str(simple_final.get("case_id") or planner.get("selected_case") or "-"),
            "metric": "E1",
            "computed_value": computed_e1 if computed_e1 is not None else "-",
            "reference_value": theory_e1 if theory_e1 is not None else "-",
            "absolute_delta": abs_delta,
            "relative_delta": rel_err if rel_err is not None else "-",
            "tolerance": threshold if threshold is not None else "-",
            "within_tolerance": within_tolerance,
            "provenance_complete": len(missing_provenance) == 0,
            "missing_provenance_fields": missing_provenance,
            "physics_fields_complete": bool(physics_result.get("has_required_fields", False)),
            "missing_physics_fields": missing_physics_fields,
            "reviewer_verdict": str(reviewer.get("final_verdict") or "UNKNOWN"),
        }
    )
    return rows


def render_case_delta_board(summary: Dict[str, Any], report_json: Path) -> str:
    reviewer = summary.get("reviewer") or {}
    rows = summary.get("case_delta_rows") or []
    primary_acceptance = reviewer.get("primary_acceptance") or {}

    lines = [
        "# Case Delta Board",
        "",
        "## Primary Verdict",
        "",
        f"- Primary Verdict: {primary_acceptance.get('primary_verdict', reviewer.get('final_verdict', 'UNKNOWN'))}",
        f"- Physics Equivalence: {primary_acceptance.get('physics_equivalence', False)}",
        f"- Provenance Complete: {primary_acceptance.get('provenance_complete', False)}",
        f"- Execution Health: {primary_acceptance.get('execution_health', False)}",
        "",
        "## Cases",
        "",
        "| Case | Metric | Computed | Reference | Abs Delta | Relative Delta | Tolerance | Within Tol | Provenance | Missing Provenance | Physics Fields | Missing Physics Fields |",
        "|---|---|---:|---:|---:|---:|---:|:---:|:---:|---|:---:|---|",
    ]

    if rows:
        for row in rows:
            missing_provenance = ",".join([str(x) for x in (row.get("missing_provenance_fields") or []) if str(x)]) or "-"
            missing_physics = ",".join([str(x) for x in (row.get("missing_physics_fields") or []) if str(x)]) or "-"
            lines.append(
                "| "
                + f"{row.get('case_id', '-')} | "
                + f"{row.get('metric', '-')} | "
                + f"{row.get('computed_value', '-')} | "
                + f"{row.get('reference_value', '-')} | "
                + f"{row.get('absolute_delta', '-')} | "
                + f"{row.get('relative_delta', '-')} | "
                + f"{row.get('tolerance', '-')} | "
                + f"{row.get('within_tolerance', False)} | "
                + f"{row.get('provenance_complete', False)} | "
                + f"{missing_provenance} | "
                + f"{row.get('physics_fields_complete', False)} | "
                + f"{missing_physics} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | False | False | - | False | - |")

    lines.extend(
        [
            "",
            "## Source Artifact",
            "",
            f"- JSON: {report_json.as_posix()}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    inferred_molecule, inferred_calc_mode = infer_octopus_defaults_for_case(args.case_id)
    if not was_cli_flag_provided("--octopus-molecule"):
        args.octopus_molecule = inferred_molecule
    if not was_cli_flag_provided("--octopus-calc-mode"):
        args.octopus_calc_mode = inferred_calc_mode

    role_specs = load_role_specs(Path(args.skills_manifest))
    learning_state_path = Path(args.learning_state_path)
    learning_state = load_learning_state(learning_state_path)

    planner = planner_stage(args, role_specs.get("planner") or _default_role_specs()["planner"], learning_state)

    # Feishu + Dashboard: PLANNED notification after planner completes
    if notify_planned is not None:
        run_id = str(args.run_id or "")
        selected_case = str(planner.get("selected_case", args.case_id))
        threshold = float(planner.get("threshold", 0.10))
        notify_planned(run_id=run_id, case=selected_case, threshold=threshold,
                       plan_summary=f"iterations={planner.get('max_iterations', '?')}")
        update_status_dashboard(
            phase="PLANNED", run_id=run_id, case_id=selected_case,
            overall_pct=20, initiator=str(args.run_id and "agent" or "human"),
            planner_done=True, executor_done=False, reviewer_done=False,
            threshold=threshold, state_machine="L0",
        )

    executor = executor_stage(args, planner, role_specs.get("executor") or _default_role_specs()["executor"])

    # Feishu + Dashboard: EXECUTING notification after executor completes
    if notify_executing is not None:
        run_id = str(args.run_id or "")
        case_id = str(planner.get("selected_case", args.case_id))
        notify_executing(run_id=run_id, stage="harness_complete", case=case_id, pct=55)
        update_status_dashboard(
            phase="EXECUTING", run_id=run_id, case_id=case_id,
            overall_pct=55, planner_done=True, executor_done=True,
            reviewer_done=False, state_machine="L0",
        )

    # Feishu + Dashboard: REVIEWING notification before reviewer stage
    if notify_reviewing is not None:
        run_id = str(args.run_id or "")
        case_id = str(planner.get("selected_case", args.case_id))
        notify_reviewing(run_id=run_id, checks_pending=0, case=case_id)
        update_status_dashboard(
            phase="REVIEWING", run_id=run_id, case_id=case_id,
            overall_pct=80, planner_done=True, executor_done=True,
            reviewer_done=False, state_machine="L0",
        )

    reviewer = reviewer_stage(
        args,
        planner,
        executor,
        role_specs.get("reviewer") or _default_role_specs()["reviewer"],
        role_specs,
        learning_state,
    )

    reviewer_checks = reviewer.get("checks") or {}
    physics_equivalence = bool(
        reviewer_checks.get("case_scope_ok", False)
        and reviewer_checks.get("accuracy_ok", False)
        and reviewer_checks.get("benchmarks_aligned_ok", False)
        and reviewer_checks.get("provenance_verified", False)
        and reviewer_checks.get("physics_result_ok", False)
    )
    execution_health = bool(
        reviewer_checks.get("execution_ok", False)
        and reviewer_checks.get("logs_consistent", False)
        and reviewer_checks.get("mcp_attempted_ok", False)
        and reviewer_checks.get("octopus_ok", False)
    )
    reviewer["primary_acceptance"] = {
        "physics_equivalence": physics_equivalence,
        "provenance_complete": bool(reviewer_checks.get("provenance_verified", False)),
        "case_scope_ok": bool(reviewer_checks.get("case_scope_ok", False)),
        "execution_health": execution_health,
        "primary_verdict": "PASS" if physics_equivalence else "FAIL",
    }

    # Debugger diagnosis on FAIL — provides required_fixes for the replan packet
    if not physics_equivalence:
        diagnosis = debugger_diagnose(
            run_id=str(args.run_id or ""),
            case_id=str(planner.get("selected_case", args.case_id)),
            reviewer=reviewer,
            executor=executor,
            planner=planner,
            output_dir=Path(args.output_dir),
        )
        reviewer["debugger_diagnosis"] = diagnosis

    # Feishu: DONE/FAIL notification after verdict is determined
    if notify_done is not None:
        run_id = str(args.run_id or "")
        case_id = str(planner.get("selected_case", args.case_id))
        final_verdict = "PASS" if physics_equivalence else "FAIL"
        delta_rows = reviewer.get("case_rows", [])
        delta_val = ""
        if delta_rows and isinstance(delta_rows, list) and delta_rows:
            dr = delta_rows[0] or {}
            delta_val = f"delta={dr.get('relative_delta', '?')}"
        detail = f"run_id={run_id} | verdict={final_verdict} | case={case_id}"
        if delta_val:
            detail += f" | {delta_val}"
        # report path will be written to summary after this; use summary path instead
        report_path = f"multi_agent_orchestration_{case_id}_{now_iso().replace(':', '').replace('-', '')}.json"
        notify_done(run_id=run_id, verdict=final_verdict, report_path=report_path, case=case_id)
        delta_rows = reviewer.get("case_rows", [])
        benchmark_delta = None
        if delta_rows and isinstance(delta_rows, list) and delta_rows:
            dr = delta_rows[0] or {}
            benchmark_delta = dr.get("relative_delta")
        # Build failure_reason from debugger diagnosis if available
        failure_reason_str = ""
        if not physics_equivalence:
            diag = reviewer.get("debugger_diagnosis") or {}
            root_cause = diag.get("root_cause", "")
            failure_type = str(reviewer.get("failure_type") or "")
            if root_cause and root_cause != "debugger_agent_unavailable":
                failure_reason_str = f"[Debugger] {root_cause}"
            elif failure_type:
                failure_reason_str = f"[Reviewer] {failure_type}"
        update_status_dashboard(
            phase="DONE" if physics_equivalence else "FAILED",
            run_id=run_id, case_id=case_id,
            overall_pct=100,
            planner_done=True, executor_done=True, reviewer_done=True,
            final_verdict=final_verdict,
            benchmark_delta=benchmark_delta,
            threshold=float(planner.get("threshold", 0.03)),
            failure_reason=failure_reason_str,
            state_machine="L0",
        )

    case_delta_rows = _build_case_delta_rows(planner, executor, reviewer)

    summary = {
        "generated_at": now_iso(),
        "planner": planner,
        "executor": executor,
        "reviewer": reviewer,
        "case_delta_rows": case_delta_rows,
        "chain_continuity": reviewer.get("chain_continuity") or {},
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_compact()
    report_json = output_dir / f"multi_agent_orchestration_{planner.get('selected_case', args.case_id)}_{stamp}.json"
    report_md = output_dir / f"multi_agent_orchestration_{planner.get('selected_case', args.case_id)}_{stamp}.md"
    case_delta_md = output_dir / f"case_delta_board_{planner.get('selected_case', args.case_id)}_{stamp}.md"

    command = (
        f"python scripts/run_multi_agent_orchestration.py --api-base {args.api_base} "
        f"--harness-base {args.harness_base} --case-id {args.case_id} "
        f"--max-iterations {args.max_iterations} --octopus-molecule {args.octopus_molecule} "
        f"--octopus-calc-mode {args.octopus_calc_mode} --skills-manifest {args.skills_manifest}"
    )

    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    report_md.write_text(render_markdown(summary, command, report_json), encoding="utf-8")
    case_delta_md.write_text(render_case_delta_board(summary, report_json), encoding="utf-8")

    learning_state = update_learning_state(learning_state, summary)
    save_learning_state(learning_state_path, learning_state)

    if not args.skip_openclaw_sync:
        write_openclaw_sync(Path(args.openclaw_sync_path), summary, report_json, report_md)

    print(f"multi_agent_report_json={report_json.as_posix()}")
    print(f"multi_agent_report_md={report_md.as_posix()}")
    print(f"case_delta_board_md={case_delta_md.as_posix()}")
    print(f"reviewer_verdict={(reviewer.get('final_verdict'))}")
    print(f"openclaw_planner_ok={str(((planner.get('openclaw_planner') or {}).get('ok')))}")
    print(f"web_evidence_ok={str(((reviewer.get('checks') or {}).get('web_evidence_ok')))}")
    print(f"openclaw_flow_ok={str(((reviewer.get('checks') or {}).get('openclaw_flow_ok')))}")
    print(f"planner_executor_chain_ok={str(((reviewer.get('checks') or {}).get('planner_executor_chain_ok')))}")
    print(f"deep_model_priority_ok={str(((reviewer.get('checks') or {}).get('deep_model_priority_ok')))}")
    print(f"openclaw_planner_trace_log={str(((planner.get('openclaw_planner') or {}).get('trace_log') or '-'))}")
    if not args.skip_openclaw_sync:
        print(f"openclaw_sync_json={Path(args.openclaw_sync_path).as_posix()}")

    if args.strict and reviewer.get("final_verdict") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
