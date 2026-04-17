#!/usr/bin/env python3
"""Export web evidence rows from orchestration report into reusable KB corpus markdown."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "harness_reports"
DEFAULT_OUTPUT = REPO_ROOT / "knowledge_base" / "corpus" / "web_evidence_traceable_cases_2026_04.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_orchestration_report(report_dir: Path) -> Path:
    matches = sorted(report_dir.glob("multi_agent_orchestration_*_*.json"))
    if not matches:
        raise FileNotFoundError("No orchestration report found")
    return matches[-1]


def _escape_cell(value: Any) -> str:
    text = str(value if value is not None else "").replace("|", "/")
    return text.strip()


def render_markdown(report_path: Path, payload: Dict[str, Any]) -> str:
    reviewer = payload.get("reviewer") if isinstance(payload, dict) else {}
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    web = reviewer.get("web_evidence") if isinstance(reviewer.get("web_evidence"), dict) else {}
    rows = web.get("rows") if isinstance(web.get("rows"), list) else []

    lines: List[str] = []
    lines.append("# Traceable Web Evidence Cases (2026-04)")
    lines.append("")
    lines.append("Generated from multi-agent orchestration real-web evidence stage.")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- source_report: {report_path.as_posix()}")
    lines.append(f"- sources_total: {web.get('sources_total', 0)}")
    lines.append(f"- sources_verified: {web.get('sources_verified', 0)}")
    lines.append(f"- multimodal_evidence_count: {web.get('multimodal_evidence_count', 0)}")
    lines.append("")
    lines.append("## Evidence Table")
    lines.append("")
    lines.append("| source_id | url | retrieved_at | title | verified | content_hash_sha256 | screenshot_path | openclaw_command | html_error | automation_error | screenshot_error |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for item in rows:
        if not isinstance(item, dict):
            continue
        shot = (item.get("playwright_screenshot") or {}) if isinstance(item.get("playwright_screenshot"), dict) else {}
        openclaw = (item.get("openclaw_automation") or {}) if isinstance(item.get("openclaw_automation"), dict) else {}
        lines.append(
            "| {source_id} | {url} | {retrieved_at} | {title} | {verified} | {hashv} | {screenshot} | {cmd} | {html_error} | {automation_error} | {screenshot_error} |".format(
                source_id=_escape_cell(item.get("source_id")),
                url=_escape_cell(item.get("url")),
                retrieved_at=_escape_cell(item.get("retrieved_at")),
                title=_escape_cell(item.get("title")),
                verified=_escape_cell(item.get("verified")),
                hashv=_escape_cell(item.get("content_hash_sha256")),
                screenshot=_escape_cell(shot.get("screenshot")),
                cmd=_escape_cell(openclaw.get("command")),
                html_error=_escape_cell(item.get("html_error")),
                automation_error=_escape_cell(openclaw.get("stderr")),
                screenshot_error=_escape_cell(shot.get("stderr")),
            )
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This corpus stores auditable provenance fields for reusable KB ingestion.")
    lines.append("- Prefer verified=true rows with screenshot and non-empty content hash for A-ready case linkage.")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export web evidence rows into KB markdown")
    parser.add_argument("--report", default="", help="Specific orchestration report json path")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Directory of orchestration reports")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output markdown path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir)
    report_path = Path(args.report) if str(args.report).strip() else latest_orchestration_report(report_dir)
    if not report_path.is_absolute():
        report_path = (REPO_ROOT / report_path).resolve()
    payload = read_json(report_path)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (REPO_ROOT / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(report_path, payload), encoding="utf-8")

    print(f"web_evidence_kb_output={output_path.as_posix()}")
    print(f"web_evidence_source_report={report_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
