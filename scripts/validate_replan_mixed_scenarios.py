#!/usr/bin/env python3
"""Validate mixed replan semantics without external service dependencies."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import execute_replan_packet as erp

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"


@dataclass
class FakeProc:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def render_markdown(summary: Dict[str, Any], report_json: Path) -> str:
    lines = [
        "# Replan Mixed Scenario Validation",
        "",
        "## Summary",
        "",
        f"- Generated At: {summary.get('generated_at')}",
        f"- Total Scenarios: {summary.get('total')}",
        f"- Passed: {summary.get('passed')}",
        f"- Failed: {summary.get('failed')}",
        f"- Verdict: {summary.get('verdict')}",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Expected all_passed | Actual all_passed | Expected stats | Actual stats | Result |",
        "|---|---:|---:|---|---|---|",
    ]

    for item in summary.get("results", []):
        lines.append(
            "| {name} | {exp_pass} | {act_pass} | {exp_stats} | {act_stats} | {status} |".format(
                name=item.get("name"),
                exp_pass=str(item.get("expected_all_passed")),
                act_pass=str(item.get("actual_all_passed")),
                exp_stats=json.dumps(item.get("expected_stats"), ensure_ascii=True),
                act_stats=json.dumps(item.get("actual_stats"), ensure_ascii=True),
                status="PASS" if item.get("ok") else "FAIL",
            )
        )

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


def run_scenario(name: str, packet: Dict[str, Any], command_map: Dict[str, List[str]], rc_map: Dict[Tuple[str, ...], int], args: argparse.Namespace) -> Dict[str, Any]:
    original_mapper = erp.map_action_to_command
    original_run = erp.subprocess.run

    def fake_mapper(action_text: str, _args: argparse.Namespace) -> List[str]:
        return command_map.get(action_text, [])

    def fake_run(command: List[str], **_kwargs: Any) -> FakeProc:
        key = tuple(command)
        rc = rc_map.get(key, 0)
        return FakeProc(returncode=rc, stdout=f"simulated:{' '.join(command)}", stderr="")

    try:
        erp.map_action_to_command = fake_mapper  # type: ignore[assignment]
        erp.subprocess.run = fake_run  # type: ignore[assignment]
        result = erp.execute_actions(packet, args)
        return {
            "name": name,
            "actual_all_passed": bool(result.get("all_passed", False)),
            "actual_stats": result.get("stats") or {},
        }
    finally:
        erp.map_action_to_command = original_mapper  # type: ignore[assignment]
        erp.subprocess.run = original_run  # type: ignore[assignment]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate replan mixed scenarios.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    args = parser.parse_args()

    exec_args = SimpleNamespace(
        api_base="http://127.0.0.1:3001",
        harness_base="http://127.0.0.1:8001",
        case_id="infinite_well_v1",
        octopus_molecule="H2",
        octopus_calc_mode="gs",
    )

    scenarios = [
        {
            "name": "empty_actions",
            "packet": {"actions": []},
            "command_map": {},
            "rc_map": {},
            "expected_all_passed": False,
            "expected_stats": {"total_actions": 0, "executed_actions": 0, "unmapped_actions": 0},
        },
        {
            "name": "all_unmapped",
            "packet": {"actions": [{"action": "unknown-a"}, {"action": "unknown-b"}]},
            "command_map": {},
            "rc_map": {},
            "expected_all_passed": False,
            "expected_stats": {"total_actions": 2, "executed_actions": 0, "unmapped_actions": 2},
        },
        {
            "name": "mixed_success_and_unmapped",
            "packet": {"actions": [{"action": "mapped-ok"}, {"action": "unknown"}]},
            "command_map": {"mapped-ok": ["cmd", "ok"]},
            "rc_map": {("cmd", "ok"): 0},
            "expected_all_passed": False,
            "expected_stats": {"total_actions": 2, "executed_actions": 1, "unmapped_actions": 1},
        },
        {
            "name": "mixed_success_and_failure",
            "packet": {"actions": [{"action": "mapped-ok"}, {"action": "mapped-fail"}]},
            "command_map": {"mapped-ok": ["cmd", "ok"], "mapped-fail": ["cmd", "fail"]},
            "rc_map": {("cmd", "ok"): 0, ("cmd", "fail"): 3},
            "expected_all_passed": False,
            "expected_stats": {"total_actions": 2, "executed_actions": 2, "unmapped_actions": 0},
        },
        {
            "name": "all_mapped_success",
            "packet": {"actions": [{"action": "mapped-a"}, {"action": "mapped-b"}]},
            "command_map": {"mapped-a": ["cmd", "a"], "mapped-b": ["cmd", "b"]},
            "rc_map": {("cmd", "a"): 0, ("cmd", "b"): 0},
            "expected_all_passed": True,
            "expected_stats": {"total_actions": 2, "executed_actions": 2, "unmapped_actions": 0},
        },
    ]

    results: List[Dict[str, Any]] = []
    passed = 0
    for s in scenarios:
        actual = run_scenario(
            name=s["name"],
            packet=s["packet"],
            command_map=s["command_map"],
            rc_map=s["rc_map"],
            args=exec_args,
        )
        ok = (
            actual["actual_all_passed"] == s["expected_all_passed"]
            and actual["actual_stats"] == s["expected_stats"]
        )
        if ok:
            passed += 1
        results.append(
            {
                "name": s["name"],
                "expected_all_passed": s["expected_all_passed"],
                "actual_all_passed": actual["actual_all_passed"],
                "expected_stats": s["expected_stats"],
                "actual_stats": actual["actual_stats"],
                "ok": ok,
            }
        )

    summary = {
        "generated_at": now_iso(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "verdict": "PASS" if passed == len(results) else "FAIL",
        "results": results,
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    report_json = report_dir / f"replan_mixed_validation_{stamp}.json"
    report_md = report_dir / f"replan_mixed_validation_{stamp}.md"

    write_json(report_json, summary)
    report_md.write_text(render_markdown(summary, report_json), encoding="utf-8")

    print(f"replan_mixed_validation_json={report_json.as_posix()}")
    print(f"replan_mixed_validation_md={report_md.as_posix()}")
    print(f"replan_mixed_validation_verdict={summary['verdict']}")
    return 0 if summary["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
