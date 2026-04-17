#!/usr/bin/env python3
"""Check consistency for H2O GS provenance anchors across code and KB artifacts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_suite_reference_constant(path: Path) -> float | None:
    text = _read_text(path)
    block = re.search(
        r'"h2o_gs_reference"\s*:\s*\{[^\}]*?"reference"\s*:\s*([-+]?\d+(?:\.\d+)?)',
        text,
        flags=re.S,
    )
    if not block:
        return None
    try:
        return float(block.group(1))
    except ValueError:
        return None


def _extract_provenance_reference(path: Path) -> float | None:
    text = _read_text(path)
    m = re.search(r"(?:Current|Active) reference value(?: in code)?:\s*`\s*([-+]?\d+(?:\.\d+)?)\s*Ha\s*`", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _find_case_bank_row(path: Path, case_id: str = "A03_h2o_gs_energy") -> str | None:
    text = _read_text(path)
    for line in text.splitlines():
        if line.strip().startswith(f"| {case_id} "):
            return line
    return None


def _extract_latest_h2o_suite_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(_read_text(path))
    cases = ((payload.get("executor") or {}).get("cases") or [])
    target = None
    for case in cases:
        if str(case.get("scenario_id") or "").strip() == "h2o_gs_reference":
            target = case
            break
    return {
        "report": str(path.as_posix()),
        "generated_at": payload.get("generated_at"),
        "final_verdict": (payload.get("reviewer") or {}).get("final_verdict"),
        "scenario_found": target is not None,
        "computed_total_energy_hartree": ((target or {}).get("metrics") or {}).get("total_energy_hartree"),
        "reference_total_energy_hartree": ((target or {}).get("comparison") or {}).get("reference"),
        "relative_delta": ((target or {}).get("comparison") or {}).get("relative_delta"),
        "within_tolerance": ((target or {}).get("comparison") or {}).get("within_tolerance"),
        "engine": (target or {}).get("engine"),
        "scheduler": (target or {}).get("scheduler") or {},
    }


def _latest_suite_report(reports_dir: Path) -> Path | None:
    files = sorted(
        reports_dir.glob("dft_tddft_agent_suite_H2O_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check H2O GS provenance consistency.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    suite_py = repo / "scripts" / "run_dft_tddft_agent_suite.py"
    provenance_md = repo / "knowledge_base" / "corpus" / "h2o_gs_reference_provenance.md"
    case_bank_md = repo / "knowledge_base" / "corpus" / "dft_tddft_authoritative_case_bank_60plus_2026_04.md"
    reports_dir = repo / "docs" / "harness_reports"

    checks: list[CheckResult] = []

    suite_ref = _extract_suite_reference_constant(suite_py)
    checks.append(
        CheckResult(
            name="suite_reference_constant_present",
            passed=suite_ref is not None,
            detail=f"suite_reference={suite_ref}",
        )
    )

    provenance_ref = _extract_provenance_reference(provenance_md)
    checks.append(
        CheckResult(
            name="provenance_reference_present",
            passed=provenance_ref is not None,
            detail=f"provenance_reference={provenance_ref}",
        )
    )

    if suite_ref is not None and provenance_ref is not None:
        checks.append(
            CheckResult(
                name="reference_value_consistent",
                passed=abs(suite_ref - provenance_ref) <= 1e-12,
                detail=f"delta={suite_ref - provenance_ref}",
            )
        )

    case_row = _find_case_bank_row(case_bank_md)
    checks.append(
        CheckResult(
            name="case_bank_row_present",
            passed=case_row is not None,
            detail=(case_row or "row_not_found"),
        )
    )

    if case_row is not None:
        has_target = "knowledge_base/corpus/h2o_gs_reference_provenance.md" in case_row
        checks.append(
            CheckResult(
                name="case_bank_points_to_provenance_doc",
                passed=has_target,
                detail="local_evidence_target contains provenance doc path" if has_target else case_row,
            )
        )

    latest_report = _latest_suite_report(reports_dir)
    suite_summary: dict[str, Any] = {}
    if latest_report is not None:
        suite_summary = _extract_latest_h2o_suite_summary(latest_report)
        checks.append(
            CheckResult(
                name="latest_suite_report_has_h2o_case",
                passed=bool(suite_summary.get("scenario_found")),
                detail=f"report={latest_report.as_posix()}",
            )
        )
        latest_ref = suite_summary.get("reference_total_energy_hartree")
        if isinstance(latest_ref, (int, float)) and suite_ref is not None:
            checks.append(
                CheckResult(
                    name="latest_report_reference_matches_suite_constant",
                    passed=abs(float(latest_ref) - float(suite_ref)) <= 1e-12,
                    detail=f"latest_ref={latest_ref}, suite_ref={suite_ref}",
                )
            )
    else:
        checks.append(CheckResult(name="latest_suite_report_exists", passed=False, detail="no suite report found"))

    overall = all(c.passed for c in checks)
    output = {
        "overall_passed": overall,
        "checks": [c.__dict__ for c in checks],
        "anchors": {
            "suite_reference": suite_ref,
            "provenance_reference": provenance_ref,
            "latest_suite_summary": suite_summary,
        },
    }
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
