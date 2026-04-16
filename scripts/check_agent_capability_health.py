#!/usr/bin/env python3
"""Health checks for agent skill contracts, MCP signals, and web-search skills."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"
MANIFEST_PATH = REPO_ROOT / "orchestration" / "agent_skills_manifest.json"

SEARCH_SKILLS = {
    "tavily": Path("z:/.claude/skills/openclaw-tavily/scripts/tavily_search.py"),
    "baidu": Path("z:/.claude/skills/openclaw-baidu-search/scripts/search.py"),
    "duckduckgo": Path("z:/.claude/skills/openclaw-ddg-search-privacy/scripts/duckduckgo_search.py"),
}
MCP_SKILL_EVAL = Path("z:/.openclaw/workspace/skills/mcp-builder/scripts/evaluation.py")
SEARCH_SKILL_KEY_REQUIREMENTS = {
    "tavily": "TAVILY_API_KEY",
    "baidu": "BAIDU_API_KEY",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def compile_check(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "compile_ok": False, "error": "missing"}
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "exists": True,
        "compile_ok": proc.returncode == 0,
        "error": proc.stderr.strip() if proc.returncode != 0 else "",
    }


def latest_orchestration_report(report_dir: Path) -> Path | None:
    matches = sorted(report_dir.glob("multi_agent_orchestration_*_*.json"))
    return matches[-1] if matches else None


def check_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "ok": False, "error": "manifest_missing", "roles": {}}

    payload = read_json(path)
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    status: Dict[str, Any] = {}
    all_ok = True

    for role in ["planner", "executor", "reviewer"]:
        spec = (roles or {}).get(role, {})
        role_ok = bool(spec.get("skill_id")) and isinstance(spec.get("required_outputs"), list) and bool(spec.get("required_outputs"))
        status[role] = {
            "skill_id": spec.get("skill_id"),
            "required_outputs_count": len(spec.get("required_outputs") or []),
            "ok": role_ok,
        }
        if not role_ok:
            all_ok = False

    return {"exists": True, "ok": all_ok, "roles": status}


def check_latest_report(report_dir: Path) -> Dict[str, Any]:
    report = latest_orchestration_report(report_dir)
    if report is None:
        return {"exists": False, "ok": False, "error": "no_orchestration_report"}

    payload = read_json(report)
    reviewer = payload.get("reviewer") or {}
    checks = reviewer.get("checks") or {}

    keys = [
        "retrieval_skill_ok",
        "web_evidence_ok",
        "mcp_attempted_ok",
        "skills_contracts_ok",
    ]
    key_state = {k: bool(checks.get(k, False)) for k in keys}
    ok = all(key_state.values())

    return {
        "exists": True,
        "ok": ok,
        "report": report.as_posix(),
        "checks": key_state,
        "final_verdict": reviewer.get("final_verdict"),
    }


def render_markdown(summary: Dict[str, Any], report_json: Path) -> str:
    lines = [
        "# Agent Capability Health Check",
        "",
        "## Summary",
        "",
        f"- Generated At: {summary.get('generated_at')}",
        f"- Verdict: {summary.get('verdict')}",
        "",
        "## Core Checks",
        "",
        f"- Manifest Contracts OK: {summary.get('manifest', {}).get('ok')}",
        f"- Latest Orchestration Signal OK: {summary.get('latest_orchestration', {}).get('ok')}",
        f"- MCP Skill Eval Script Compile OK: {summary.get('mcp_skill_compile', {}).get('compile_ok')}",
        "",
        "## Web Search Skills",
        "",
        "| Skill | Exists | Compile OK | Notes |",
        "|---|---:|---:|---|",
    ]

    for name, item in (summary.get("web_search_skills") or {}).items():
        note = item.get("error") or "-"
        lines.append(f"| {name} | {item.get('exists')} | {item.get('compile_ok')} | {note} |")

    env = summary.get("env") or {}
    notes = summary.get("notes") or []
    lines.extend(
        [
            "",
            "## Environment Signals",
            "",
            f"- TAVILY_API_KEY present: {env.get('TAVILY_API_KEY_present')}",
            f"- BAIDU_API_KEY present: {env.get('BAIDU_API_KEY_present')}",
            "",
            "## Notes",
            "",
        ]
    )

    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- No additional notes.")

    lines.extend(
        [
            "",
            "## Artifact",
            "",
            f"- JSON: {report_json.as_posix()}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check agent capability health")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    manifest = check_manifest(MANIFEST_PATH)
    latest = check_latest_report(report_dir)

    web = {name: compile_check(path) for name, path in SEARCH_SKILLS.items()}
    mcp_compile = compile_check(MCP_SKILL_EVAL)

    env = {
        "TAVILY_API_KEY_present": bool(os.getenv("TAVILY_API_KEY")),
        "BAIDU_API_KEY_present": bool(os.getenv("BAIDU_API_KEY")),
    }

    notes: List[str] = []
    missing_provider_keys: List[str] = []
    for skill_name, env_key in SEARCH_SKILL_KEY_REQUIREMENTS.items():
        if not bool(os.getenv(env_key)):
            missing_provider_keys.append(f"{skill_name}:{env_key}")

    if missing_provider_keys:
        notes.append(
            "API-key-backed web search providers are installed and compilable but not fully runnable without env keys: "
            + ", ".join(missing_provider_keys)
        )
        notes.append("This is an environment configuration gap, not a code patch requirement.")

    hard_fail = not manifest.get("ok", False) or not mcp_compile.get("compile_ok", False)
    soft_warn = (
        not latest.get("ok", False)
        or any(not item.get("compile_ok", False) for item in web.values())
        or bool(missing_provider_keys)
    )

    verdict = "FAIL" if hard_fail else ("WARN" if soft_warn else "PASS")

    summary = {
        "generated_at": now_iso(),
        "manifest": manifest,
        "latest_orchestration": latest,
        "web_search_skills": web,
        "mcp_skill_compile": mcp_compile,
        "env": env,
        "notes": notes,
        "verdict": verdict,
    }

    stamp = utc_stamp()
    report_json = report_dir / f"agent_capability_health_{stamp}.json"
    report_md = report_dir / f"agent_capability_health_{stamp}.md"
    write_json(report_json, summary)
    report_md.write_text(render_markdown(summary, report_json), encoding="utf-8")

    print(f"agent_capability_health_json={report_json.as_posix()}")
    print(f"agent_capability_health_md={report_md.as_posix()}")
    print(f"agent_capability_health_verdict={verdict}")
    return 0 if verdict in {"PASS", "WARN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
