#!/usr/bin/env python3
"""Run a strict multi-agent Octopus campaign across many molecules/modes."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]

# Use centralized feishu_notify instead of local send_feishu_log
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from feishu_notify import notify as _feishu_notify, FEISHU_BINDINGS
except ImportError:
    _feishu_notify = None  # type: ignore
    FEISHU_BINDINGS = {}

DEFAULT_EXPLAIN_MODEL = "gpt-5-thinking"
DEFAULT_EXPLAIN_TIMEOUT_SECONDS = 60


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def parse_csv_list(raw: str, fallback: List[str]) -> List[str]:
    items = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    if not items:
        return list(fallback)
    dedup: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup


def sanitize_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()) or "unknown"


def run_cmd(cmd: List[str], timeout_seconds: int) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=max(30, int(timeout_seconds)),
            check=False,
        )
        return {
            "command": " ".join(cmd),
            "exit_code": int(proc.returncode),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "kv": parse_kv_lines(proc.stdout),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"timeout_after_{timeout_seconds}s",
            "kv": {},
        }


def load_json_if_exists(path_str: str) -> Dict[str, Any]:
    if not path_str:
        return {}
    p = Path(path_str)
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def send_feishu_log(feishu_target: str, message: str) -> None:
    """Send a Feishu log message via centralized feishu_notify (backward-compatible wrapper)."""
    if _feishu_notify is None:
        # Fallback: direct CLI invocation
        target = str(feishu_target or "").strip()
        if not target:
            return
        cli = str(os.environ.get("DIRAC_REMOTE_OPENCLAW_BIN") or "/data/home/zju321/.local/bin/openclaw").strip()
        cmd = [
            cli, "message", "send",
            "--channel", "feishu",
            "--target", target,
            "--message", str(message or "")[:3500],
        ]
        try:
            subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, timeout=25, text=True, capture_output=True)
        except Exception:
            pass
        return
    # Find which agent this target belongs to and use centralized notify
    for agent_name, binding in FEISHU_BINDINGS.items():
        if binding == feishu_target:
            _feishu_notify(agent=agent_name, event="CAMPAIGN", progress_pct=50,
                           detail=message[:200], directive="")
            return
    # Unknown target: send directly to the specified target
    _feishu_notify(agent="bot_dm", event="CAMPAIGN", progress_pct=50,
                   detail=message[:200], directive="", target_override=feishu_target)


def _safe_text(value: Any, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max(0, int(limit)):
        return text
    return text[: max(0, int(limit) - 3)] + "..."


def _failed_check_names(evaluation: Dict[str, Any]) -> List[str]:
    checks = evaluation.get("reviewer_checks") if isinstance(evaluation, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    failed: List[str] = []
    for key, value in checks.items():
        if not bool(value):
            failed.append(str(key))
    return failed[:5]


def _fallback_explained_message(
    *,
    event: str,
    profile: str,
    strict: bool,
    idx: int,
    total: int,
    step_name: str,
    status: str,
    verdict: str,
    evaluation: Dict[str, Any],
    campaign_verdict: str,
    passed_steps: int,
    report_path: str,
) -> str:
    failed_checks = _failed_check_names(evaluation)
    if event == "start":
        return (
            "Campaign interpretation: OpenClaw has started a strict Octopus campaign. "
            f"Profile={_safe_text(profile, 48)}, strict={strict}, total_steps={total}. "
            "Next action is planner->executor->reviewer orchestration for each case with interpreted progress updates."
        )
    if event == "progress":
        note = "Step appears stable."
        if status != "PASS":
            note = "OpenClaw completed this step but reviewer marked it as failed; replan or parameter refinement is required."
            if failed_checks:
                note += f" Failed checks: {', '.join(failed_checks)}."
        return (
            "Campaign interpretation update: "
            f"step {idx}/{total} ({_safe_text(step_name, 72)}) is {status}. "
            f"Reviewer verdict is {_safe_text(verdict, 24)}. {note} "
            "Next action is to continue remaining queued steps unless a hard blocker persists."
        )
    report_hint = _safe_text(report_path, 200)
    return (
        "Campaign interpretation complete: "
        f"overall verdict is {_safe_text(campaign_verdict, 24)} with {passed_steps}/{total} steps passing. "
        f"Full report artifact: {report_hint}"
    )


def _build_explainer_prompt(
    *,
    event: str,
    profile: str,
    strict: bool,
    idx: int,
    total: int,
    step_name: str,
    step_type: str,
    status: str,
    verdict: str,
    evaluation: Dict[str, Any],
    campaign_verdict: str,
    passed_steps: int,
    report_path: str,
) -> str:
    payload = {
        "event": event,
        "profile": profile,
        "strict": bool(strict),
        "index": int(idx),
        "total": int(total),
        "step_name": step_name,
        "step_type": step_type,
        "status": status,
        "verdict": verdict,
        "evaluation": evaluation,
        "campaign_verdict": campaign_verdict,
        "passed_steps": int(passed_steps),
        "report_path": report_path,
    }
    instructions = (
        "You are writing an interpreted status message for Feishu. "
        "Output plain English only, 3-5 short sentences, no markdown list. "
        "Do not expose raw logs, kv lines, shell commands, or stack traces. "
        "Explain what happened, whether it passed, and what action is next. "
        "If there is a failure, mention up to three failed checks by name. "
        "Always include the report path when event=end."
    )
    return instructions + "\n\nSTATUS_JSON:\n" + json.dumps(payload, ensure_ascii=True)


def _generate_explained_message(
    *,
    cli: str,
    model: str,
    timeout_seconds: int,
    event: str,
    profile: str,
    strict: bool,
    idx: int,
    total: int,
    step_name: str,
    step_type: str,
    status: str,
    verdict: str,
    evaluation: Dict[str, Any],
    campaign_verdict: str,
    passed_steps: int,
    report_path: str,
) -> str:
    fallback = _fallback_explained_message(
        event=event,
        profile=profile,
        strict=strict,
        idx=idx,
        total=total,
        step_name=step_name,
        status=status,
        verdict=verdict,
        evaluation=evaluation,
        campaign_verdict=campaign_verdict,
        passed_steps=passed_steps,
        report_path=report_path,
    )

    prompt = _build_explainer_prompt(
        event=event,
        profile=profile,
        strict=strict,
        idx=idx,
        total=total,
        step_name=step_name,
        step_type=step_type,
        status=status,
        verdict=verdict,
        evaluation=evaluation,
        campaign_verdict=campaign_verdict,
        passed_steps=passed_steps,
        report_path=report_path,
    )

    tried: List[str] = []
    model_candidates: List[str] = []
    preferred = str(model or "").strip()
    if preferred:
        model_candidates.append(preferred)
    for candidate in ["gpt-5-thinking", "deepseek-r1", ""]:
        if candidate in model_candidates:
            continue
        model_candidates.append(candidate)

    for candidate_model in model_candidates:
        cmd = [
            str(cli or "").strip(),
            "agent",
            "--agent",
            "main",
        ]
        if str(candidate_model).strip():
            cmd.extend(["--model", str(candidate_model).strip()])
        cmd.extend(
            [
                "--message",
                prompt,
                "--timeout",
                str(max(20, int(timeout_seconds))),
            ]
        )
        tried.append(candidate_model or "default")
        try:
            proc = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                check=False,
                timeout=max(25, int(timeout_seconds) + 10),
                text=True,
                capture_output=True,
            )
        except Exception:
            continue

        if int(proc.returncode) != 0:
            continue

        output = str(proc.stdout or "").strip()
        if not output:
            continue

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        interpreted = lines[-1] if lines else output
        interpreted = _safe_text(interpreted, 3000)
        if interpreted:
            return interpreted

    fallback_with_trace = fallback + f" (explain_models_tried={','.join(tried)})"
    return _safe_text(fallback_with_trace, 3400)


def build_orchestration_step(
    *,
    api_base: str,
    harness_base: str,
    skills_manifest: str,
    molecule: str,
    calc_mode: str,
    strict: bool,
    planner_model_priority: str,
    reviewer_model_priority: str,
    planner_thinking_budget: int,
    reviewer_thinking_budget: int,
) -> Dict[str, Any]:
    name = f"orchestration_{sanitize_name(molecule)}_{sanitize_name(calc_mode)}"
    cmd = [
        sys.executable,
        "scripts/run_multi_agent_orchestration.py",
        "--api-base",
        api_base,
        "--harness-base",
        harness_base,
        "--case-id",
        "infinite_well_v1",
        "--max-iterations",
        "3",
        "--octopus-molecule",
        molecule,
        "--octopus-calc-mode",
        calc_mode,
        "--skills-manifest",
        skills_manifest,
        "--planner-model-priority",
        planner_model_priority,
        "--reviewer-model-priority",
        reviewer_model_priority,
        "--planner-thinking-budget",
        str(int(planner_thinking_budget)),
        "--reviewer-thinking-budget",
        str(int(reviewer_thinking_budget)),
    ]
    if strict:
        cmd.append("--strict")
    return {
        "name": name,
        "type": "orchestration",
        "cmd": cmd,
        "artifact_key": "multi_agent_report_json",
    }


def build_plan(args: argparse.Namespace) -> List[Dict[str, Any]]:
    molecules = parse_csv_list(
        args.molecules,
        ["H2", "N2", "CO", "H2O", "NH3", "CH4", "C2H4", "Benzene", "Si", "Al2O3"],
    )
    calc_modes = parse_csv_list(args.calc_modes, ["gs", "td"])
    max_cases = max(1, int(args.max_cases))

    plan: List[Dict[str, Any]] = []
    for molecule in molecules:
        for calc_mode in calc_modes:
            if len(plan) >= max_cases:
                break
            plan.append(
                build_orchestration_step(
                    api_base=args.api_base,
                    harness_base=args.harness_base,
                    skills_manifest=args.skills_manifest,
                    molecule=molecule,
                    calc_mode=calc_mode,
                    strict=bool(args.strict),
                    planner_model_priority=str(args.planner_model_priority),
                    reviewer_model_priority=str(args.reviewer_model_priority),
                    planner_thinking_budget=int(args.planner_thinking_budget),
                    reviewer_thinking_budget=int(args.reviewer_thinking_budget),
                )
            )
        if len(plan) >= max_cases:
            break

    if not args.skip_suite:
        suite_cmd = [
            sys.executable,
            "scripts/run_dft_tddft_agent_suite.py",
            "--api-base",
            args.api_base,
            "--molecule",
            args.suite_molecule,
            "--external-reference-path",
            args.external_reference_path,
        ]
        if args.strict:
            suite_cmd.append("--strict")
        plan.append(
            {
                "name": f"suite_{sanitize_name(args.suite_molecule)}_dft_tddft",
                "type": "suite",
                "cmd": suite_cmd,
                "artifact_key": "suite_report_json",
                "verdict_kv": "suite_verdict",
            }
        )

    return plan


def _is_step_pass(
    *,
    step_type: str,
    run: Dict[str, Any],
    verdict: str,
    artifact_path: str,
    profile: str,
) -> tuple[bool, Dict[str, Any]]:
    exit_ok = int(run.get("exit_code", 1)) == 0
    details: Dict[str, Any] = {
        "exit_ok": exit_ok,
        "raw_verdict": verdict,
        "profile": profile,
    }
    if not exit_ok:
        return False, details

    if step_type != "suite":
        return verdict == "PASS", details

    payload = load_json_if_exists(artifact_path)
    reviewer = payload.get("reviewer") if isinstance(payload, dict) else {}
    checks = (reviewer or {}).get("checks") if isinstance(reviewer, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    details["reviewer_checks"] = checks

    if str(profile or "").strip().lower() == "octopus-max":
        operational_checks = [
            "all_cases_passed",
            "gs_converged",
            "absorption_cross_section_ready",
            "dipole_response_ready",
            "radiation_spectrum_ready",
            "eels_spectrum_ready",
            "all_octopus_engine",
        ]
        hard_ready = all(bool(checks.get(k, False)) for k in operational_checks)
        details["operational_checks"] = operational_checks
        details["operational_ready"] = hard_ready
        details["tolerance_advisory"] = bool(checks.get("all_within_reference_tolerance", False))
        details["evaluation_mode"] = "operational_hard_gates_with_advisory_tolerance"
        return hard_ready, details

    return verdict == "PASS", details


def build_md(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Multi-Agent Octopus Campaign Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Generated At: {report.get('generated_at')}")
    lines.append(f"- Profile: {report.get('profile')}")
    lines.append(f"- Total Steps: {report.get('total_steps')}")
    lines.append(f"- Passed Steps: {report.get('passed_steps')}")
    lines.append(f"- Campaign Verdict: {report.get('campaign_verdict')}")
    lines.append("")
    lines.append("## Step Results")
    lines.append("")
    lines.append("| Step | Type | Status | Exit | Verdict | Artifact |")
    lines.append("|---|---|---|---:|---|---|")
    for item in report.get("steps", []):
        lines.append(
            "| {name} | {type} | {status} | {exit_code} | {verdict} | {artifact} |".format(
                name=item.get("name", "-"),
                type=item.get("type", "-"),
                status=item.get("status", "-"),
                exit_code=item.get("exit_code", "-"),
                verdict=item.get("verdict", "-"),
                artifact=item.get("artifact", "-"),
            )
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- All steps are executed through planner/executor/reviewer runner paths.")
    lines.append("- Campaign scales by molecules x calc_modes with strict gating support.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-agent Octopus campaign")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001")
    parser.add_argument("--harness-base", default="http://127.0.0.1:8001")
    parser.add_argument("--skills-manifest", default="orchestration/agent_skills_manifest.json")
    parser.add_argument("--report-dir", default="docs/harness_reports")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--profile", default="octopus-max")
    parser.add_argument("--molecules", default="H2,N2,CO,H2O,NH3,CH4,C2H4,Benzene,Si,Al2O3")
    parser.add_argument("--calc-modes", default="gs,td")
    parser.add_argument("--max-cases", type=int, default=24)
    parser.add_argument("--skip-suite", action="store_true")
    parser.add_argument("--suite-molecule", default="H2O")
    parser.add_argument("--external-reference-path", default="knowledge_base/reference_data/external_curve_references.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--planner-model-priority", default="gpt-5-thinking,deepseek-r1")
    parser.add_argument("--reviewer-model-priority", default="gpt-5-thinking,deepseek-r1")
    parser.add_argument("--planner-thinking-budget", type=int, default=8000)
    parser.add_argument("--reviewer-thinking-budget", type=int, default=8000)
    parser.add_argument("--feishu-target", default="")
    parser.add_argument("--feishu-log", action="store_true")
    parser.add_argument("--feishu-message-mode", choices=["explained", "raw"], default="explained")
    parser.add_argument("--feishu-explain-model", default=DEFAULT_EXPLAIN_MODEL)
    parser.add_argument("--feishu-explain-timeout", type=int, default=DEFAULT_EXPLAIN_TIMEOUT_SECONDS)
    parser.add_argument("--feishu-progress-interval", type=int, default=1)
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = REPO_ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(args)
    feishu_target = str(args.feishu_target or os.environ.get("DIRAC_FEISHU_TARGET") or "").strip()
    feishu_enabled = bool(args.feishu_log and feishu_target)
    feishu_cli = str(os.environ.get("DIRAC_REMOTE_OPENCLAW_BIN") or "/data/home/zju321/.local/bin/openclaw").strip()
    progress_interval = max(1, int(args.feishu_progress_interval))
    if feishu_enabled:
        raw_start = f"[Campaign Start] profile={args.profile} strict={args.strict} steps={len(plan)} molecules={args.molecules} modes={args.calc_modes}"
        if str(args.feishu_message_mode).strip().lower() == "raw":
            send_feishu_log(feishu_target, raw_start)
        else:
            explained = _generate_explained_message(
                cli=feishu_cli,
                model=str(args.feishu_explain_model or DEFAULT_EXPLAIN_MODEL),
                timeout_seconds=int(args.feishu_explain_timeout),
                event="start",
                profile=str(args.profile or ""),
                strict=bool(args.strict),
                idx=0,
                total=len(plan),
                step_name="campaign_start",
                step_type="campaign",
                status="RUNNING",
                verdict="N/A",
                evaluation={},
                campaign_verdict="RUNNING",
                passed_steps=0,
                report_path="",
            )
            send_feishu_log(feishu_target, explained)

    steps: List[Dict[str, Any]] = []
    passed = 0
    for idx, item in enumerate(plan, start=1):
        run = run_cmd(item["cmd"], timeout_seconds=args.timeout)
        artifact = str(run.get("kv", {}).get(item.get("artifact_key", ""), ""))
        verdict = "UNKNOWN"
        if item.get("type") == "suite":
            verdict = str(run.get("kv", {}).get(item.get("verdict_kv", ""), "UNKNOWN")).upper()
        else:
            payload = load_json_if_exists(artifact)
            reviewer = payload.get("reviewer") if isinstance(payload, dict) else {}
            verdict = str((reviewer or {}).get("final_verdict") or "UNKNOWN").upper()

        is_pass, eval_details = _is_step_pass(
            step_type=str(item.get("type") or ""),
            run=run,
            verdict=verdict,
            artifact_path=artifact,
            profile=str(args.profile or ""),
        )
        status = "PASS" if is_pass else "FAIL"
        if status == "PASS":
            passed += 1

        steps.append(
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "status": status,
                "exit_code": int(run.get("exit_code", 1)),
                "verdict": verdict,
                "artifact": artifact,
                "command": run.get("command"),
                "evaluation": eval_details,
            }
        )

        if feishu_enabled and (idx % progress_interval == 0 or status != "PASS" or idx == len(plan)):
            raw_progress = (
                f"[Campaign Progress] {idx}/{len(plan)} {item.get('name')} "
                f"status={status} verdict={verdict} exit={int(run.get('exit_code', 1))}"
            )
            if str(args.feishu_message_mode).strip().lower() == "raw":
                send_feishu_log(feishu_target, raw_progress)
            else:
                explained = _generate_explained_message(
                    cli=feishu_cli,
                    model=str(args.feishu_explain_model or DEFAULT_EXPLAIN_MODEL),
                    timeout_seconds=int(args.feishu_explain_timeout),
                    event="progress",
                    profile=str(args.profile or ""),
                    strict=bool(args.strict),
                    idx=idx,
                    total=len(plan),
                    step_name=str(item.get("name") or ""),
                    step_type=str(item.get("type") or ""),
                    status=status,
                    verdict=str(verdict or "UNKNOWN"),
                    evaluation=eval_details,
                    campaign_verdict="RUNNING",
                    passed_steps=passed,
                    report_path=str(artifact or ""),
                )
                send_feishu_log(feishu_target, explained)

    campaign_verdict = "PASS" if passed == len(steps) else "FAIL"
    report = {
        "generated_at": now_iso(),
        "profile": args.profile,
        "total_steps": len(steps),
        "passed_steps": passed,
        "campaign_verdict": campaign_verdict,
        "steps": steps,
    }

    stamp = utc_stamp()
    json_path = report_dir / f"multi_agent_octopus_campaign_{stamp}.json"
    md_path = report_dir / f"multi_agent_octopus_campaign_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    md_path.write_text(build_md(report), encoding="utf-8")

    if feishu_enabled:
        raw_end = f"[Campaign End] verdict={campaign_verdict} passed={passed}/{len(steps)} report={json_path.as_posix()}"
        if str(args.feishu_message_mode).strip().lower() == "raw":
            send_feishu_log(feishu_target, raw_end)
        else:
            explained = _generate_explained_message(
                cli=feishu_cli,
                model=str(args.feishu_explain_model or DEFAULT_EXPLAIN_MODEL),
                timeout_seconds=int(args.feishu_explain_timeout),
                event="end",
                profile=str(args.profile or ""),
                strict=bool(args.strict),
                idx=len(steps),
                total=len(steps),
                step_name="campaign_end",
                step_type="campaign",
                status=campaign_verdict,
                verdict=campaign_verdict,
                evaluation={},
                campaign_verdict=campaign_verdict,
                passed_steps=passed,
                report_path=json_path.as_posix(),
            )
            send_feishu_log(feishu_target, explained)

    print(f"campaign_report_json={json_path.as_posix()}")
    print(f"campaign_report_md={md_path.as_posix()}")
    print(f"campaign_verdict={campaign_verdict}")
    return 0 if campaign_verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
