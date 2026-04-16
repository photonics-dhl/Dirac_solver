#!/usr/bin/env python3
"""Build capability matrix and canonical cases from Octopus tutorial16 catalog."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_JSON = REPO_ROOT / "knowledge_base" / "metadata" / "octopus_tutorial16_cases_table.json"
OUT_MATRIX_JSON = REPO_ROOT / "knowledge_base" / "metadata" / "octopus_tutorial16_capability_matrix.json"
OUT_MATRIX_MD = REPO_ROOT / "knowledge_base" / "corpus" / "octopus_tutorial16_capability_matrix_2026_04.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_category(url: str) -> str:
    marker = "/documentation/16/tutorial/"
    if marker not in url:
        return "other"
    suffix = url.split(marker, 1)[1].strip("/")
    if not suffix:
        return "landing"
    return suffix.split("/", 1)[0]


def is_index_page(url: str) -> bool:
    marker = "/documentation/16/tutorial/"
    if marker not in url:
        return False
    suffix = url.split(marker, 1)[1].strip("/")
    if not suffix:
        return True
    return "/" not in suffix


def category_support_status(category: str) -> str:
    status_map = {
        "response": "partial",
        "periodic_systems": "partial",
        "hpc": "partial",
        "maxwell": "missing",
        "model": "partial",
        "unsorted": "partial",
        "basics": "partial",
        "multisystem": "missing",
        "courses": "missing",
        "cecam_2024": "missing",
    }
    return status_map.get(category, "unknown")


def category_priority(category: str) -> str:
    if category in {"response", "periodic_systems", "basics"}:
        return "P0"
    if category in {"hpc", "model", "unsorted"}:
        return "P1"
    return "P2"


def tutorial_score(row: Dict) -> int:
    score = 0
    score += int(row.get("data_link_count") or 0) * 3
    score += int(row.get("table_count") or 0) * 2
    score += int(row.get("video_count") or 0) * 2
    score += 2 if "code_block" in (row.get("artifact_types") or []) else 0
    score += 1 if (row.get("example_parameters") or []) else 0
    return score


def build_matrix(rows: List[Dict]) -> Dict:
    categories: Dict[str, Dict] = {}
    for row in rows:
        url = str(row.get("url") or "")
        category = parse_category(url)
        if category not in categories:
            categories[category] = {
                "category": category,
                "tutorial_count": 0,
                "index_pages": 0,
                "case_pages": 0,
                "with_code_blocks": 0,
                "with_tables": 0,
                "with_videos": 0,
                "with_data_files": 0,
                "support_status": category_support_status(category),
                "implementation_priority": category_priority(category),
                "canonical_candidates": [],
            }

        entry = categories[category]
        entry["tutorial_count"] += 1
        if is_index_page(url):
            entry["index_pages"] += 1
        else:
            entry["case_pages"] += 1
        if "code_block" in (row.get("artifact_types") or []):
            entry["with_code_blocks"] += 1
        if int(row.get("table_count") or 0) > 0:
            entry["with_tables"] += 1
        if int(row.get("video_count") or 0) > 0:
            entry["with_videos"] += 1
        if int(row.get("data_link_count") or 0) > 0:
            entry["with_data_files"] += 1

        if not is_index_page(url):
            candidate = {
                "title": row.get("title") or "",
                "url": url,
                "score": tutorial_score(row),
                "artifact_types": row.get("artifact_types") or [],
                "table_count": int(row.get("table_count") or 0),
                "video_count": int(row.get("video_count") or 0),
                "data_link_count": int(row.get("data_link_count") or 0),
            }
            entry["canonical_candidates"].append(candidate)

    # keep top 3 canonical cases per category
    for entry in categories.values():
        candidates = sorted(
            entry["canonical_candidates"],
            key=lambda c: (c["score"], c["data_link_count"], c["table_count"], c["video_count"], c["title"]),
            reverse=True,
        )
        entry["canonical_cases"] = candidates[:3]
        entry.pop("canonical_candidates", None)

    matrix_rows = sorted(categories.values(), key=lambda x: (x["implementation_priority"], x["category"]))
    return {
        "generated_at": now_iso(),
        "source": CATALOG_JSON.as_posix(),
        "tutorial_count": len(rows),
        "category_count": len(matrix_rows),
        "rows": matrix_rows,
    }


def render_markdown(matrix: Dict) -> str:
    lines: List[str] = []
    lines.append("# Octopus Tutorial16 Capability Matrix")
    lines.append("")
    lines.append(f"- generated_at: {matrix.get('generated_at')}")
    lines.append(f"- tutorial_count: {matrix.get('tutorial_count')}")
    lines.append(f"- category_count: {matrix.get('category_count')}")
    lines.append("")
    lines.append("## Coverage Matrix")
    lines.append("")
    lines.append("| Category | Tutorials | Case Pages | Code | Tables | Videos | Data Files | Support | Priority |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
    for row in matrix.get("rows") or []:
        lines.append(
            "| {category} | {tutorial_count} | {case_pages} | {with_code_blocks} | {with_tables} | {with_videos} | {with_data_files} | {support_status} | {implementation_priority} |".format(
                **row
            )
        )

    lines.append("")
    lines.append("## Canonical Cases")
    lines.append("")
    for row in matrix.get("rows") or []:
        lines.append(f"### {row.get('category')}")
        lines.append("")
        canonical_cases = row.get("canonical_cases") or []
        if not canonical_cases:
            lines.append("- No canonical case selected.")
            lines.append("")
            continue
        for case in canonical_cases:
            title = str(case.get("title") or "").replace("|", "/")
            lines.append(
                f"- {title} | {case.get('url')} | score={case.get('score')} | artifacts={','.join(case.get('artifact_types') or [])}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if not CATALOG_JSON.exists():
        raise FileNotFoundError(f"Missing catalog json: {CATALOG_JSON.as_posix()}")
    payload = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []

    matrix = build_matrix(rows)

    OUT_MATRIX_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MATRIX_JSON.write_text(json.dumps(matrix, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    OUT_MATRIX_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MATRIX_MD.write_text(render_markdown(matrix), encoding="utf-8")

    print(f"tutorial_count={matrix.get('tutorial_count')}")
    print(f"category_count={matrix.get('category_count')}")
    print(f"matrix_json={OUT_MATRIX_JSON.as_posix()}")
    print(f"matrix_md={OUT_MATRIX_MD.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
