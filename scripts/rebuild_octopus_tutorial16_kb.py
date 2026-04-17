#!/usr/bin/env python3
"""Build normalized Octopus tutorial16 KB artifacts from Playwright crawl output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "knowledge_base" / "metadata" / "octopus_tutorial16_index.json"
OUT_JSON = REPO_ROOT / "knowledge_base" / "metadata" / "octopus_tutorial16_cases_table.json"
OUT_MD = REPO_ROOT / "knowledge_base" / "corpus" / "octopus_tutorial16_official_catalog_2026_04.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_code_blocks(blocks: list[str], max_items: int = 2, max_len: int = 600) -> list[str]:
    out: list[str] = []
    for b in blocks[:max_items]:
        text = (b or "").strip()
        if not text:
            continue
        out.append(text[:max_len])
    return out


def derive_artifact_types(row: dict) -> list[str]:
    types: list[str] = []
    if int(row.get("tableCount") or 0) > 0:
        types.append("table")
    if int(row.get("imageCount") or 0) > 0:
        types.append("image")
    if int(row.get("videoCount") or 0) > 0:
        types.append("video")
    if int(row.get("dataLinkCount") or 0) > 0:
        types.append("data_file")
    if int(row.get("codeBlockCount") or 0) > 0:
        types.append("code_block")
    if not types:
        types.append("text_only")
    return types


def infer_tags(url: str) -> list[str]:
    u = (url or "").lower()
    tags: list[str] = ["octopus", "official_tutorial", "v16"]
    for key, tag in [
        ("/tutorial/response/", "optical_response"),
        ("/tutorial/periodic_systems/", "periodic_systems"),
        ("/tutorial/model/", "model_systems"),
        ("/tutorial/hpc/", "hpc"),
        ("/tutorial/maxwell/", "maxwell"),
        ("/tutorial/basics/", "basics"),
        ("/tutorial/cecam_2024/", "cecam_2024"),
    ]:
        if key in u:
            tags.append(tag)
    return sorted(set(tags))


def build_rows(index_payload: dict) -> list[dict]:
    rows: list[dict] = []
    for item in index_payload.get("index") or []:
        url = str(item.get("url") or "").strip()
        if "/documentation/16/tutorial/" not in url:
            continue
        rows.append(
            {
                "url": url,
                "title": item.get("h1") or item.get("title") or "",
                "headings": item.get("h2") or [],
                "artifact_types": derive_artifact_types(item),
                "table_count": int(item.get("tableCount") or 0),
                "image_count": int(item.get("imageCount") or 0),
                "video_count": int(item.get("videoCount") or 0),
                "data_link_count": int(item.get("dataLinkCount") or 0),
                "image_links": (item.get("imageLinks") or [])[:40],
                "video_links": (item.get("videoLinks") or [])[:40],
                "data_links": (item.get("dataLinks") or [])[:120],
                "example_parameters": compact_code_blocks(item.get("firstCodeBlocks") or []),
                "tags": infer_tags(url),
                "crawl_error": item.get("error"),
            }
        )
    rows.sort(key=lambda x: x["url"])
    return rows


def write_markdown(rows: list[dict], output: Path) -> None:
    lines: list[str] = []
    lines.append("# Octopus Official Tutorial Catalog (Documentation 16)")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- tutorial_count: {len(rows)}")
    lines.append("- source: https://www.octopus-code.org/documentation/16/tutorial/")
    lines.append("- evidence_policy: playwright_full_click_and_extract")
    lines.append("")
    lines.append("## Coverage Table")
    lines.append("")
    lines.append("| Title | URL | Artifacts | Tables | Images | Videos | Data Files |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for r in rows:
        title = (r.get("title") or "").replace("|", "/")
        url = r.get("url") or ""
        artifacts = ", ".join(r.get("artifact_types") or [])
        lines.append(
            "| {title} | {url} | {artifacts} | {tables} | {images} | {videos} | {data} |".format(
                title=title,
                url=url,
                artifacts=artifacts,
                tables=r.get("table_count", 0),
                images=r.get("image_count", 0),
                videos=r.get("video_count", 0),
                data=r.get("data_link_count", 0),
            )
        )

    lines.append("")
    lines.append("## Tutorial Records")
    lines.append("")
    for i, r in enumerate(rows, start=1):
        lines.append(f"### T{i:03d} - {r.get('title')}")
        lines.append("")
        lines.append(f"- url: {r.get('url')}")
        lines.append(f"- tags: {', '.join(r.get('tags') or [])}")
        lines.append(f"- artifact_types: {', '.join(r.get('artifact_types') or [])}")
        lines.append(f"- tables: {r.get('table_count', 0)}")
        lines.append(f"- images: {r.get('image_count', 0)}")
        lines.append(f"- videos: {r.get('video_count', 0)}")
        lines.append(f"- data_files: {r.get('data_link_count', 0)}")
        if r.get("headings"):
            lines.append("- headings:")
            for h in r.get("headings")[:12]:
                lines.append(f"  - {h}")
        if r.get("example_parameters"):
            lines.append("- example_parameters:")
            for block in r.get("example_parameters"):
                lines.append("```text")
                lines.append(block)
                lines.append("```")
        if r.get("image_links"):
            lines.append("- image_links:")
            for u in r.get("image_links")[:15]:
                lines.append(f"  - {u}")
        if r.get("video_links"):
            lines.append("- video_links:")
            for u in r.get("video_links")[:15]:
                lines.append(f"  - {u}")
        if r.get("data_links"):
            lines.append("- data_links:")
            for u in r.get("data_links")[:20]:
                lines.append(f"  - {u}")
        if r.get("crawl_error"):
            lines.append(f"- crawl_error: {r.get('crawl_error')}")
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"Missing index input: {INDEX_PATH.as_posix()}")

    payload = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    rows = build_rows(payload)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "source": "octopus_tutorial16_playwright_index",
                "landing": payload.get("landing"),
                "tutorial_count": len(rows),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    write_markdown(rows, OUT_MD)

    print(f"tutorial_rows={len(rows)}")
    print(f"catalog_json={OUT_JSON.as_posix()}")
    print(f"catalog_md={OUT_MD.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
