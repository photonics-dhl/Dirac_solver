#!/usr/bin/env python3
"""
sync_case_result.py — Auto-sync orchestrator results to documentation and KB.

Triggered after REVIEW_PASS to update:
  1. docs/octopus_case_convergence.md     — convergence parameters + verified results
  2. docs/octopus_user_guide.md           — executor capability table
  3. knowledge_base/corpus_new/           — per-case KB files
  4. knowledge_base/corpus_manifest.json   — KB index

Can run standalone:
  python scripts/sync_case_result.py --report <path-to-orchestrator-report.json>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERGENCE_DOC = REPO_ROOT / "docs" / "octopus_case_convergence.md"
USER_GUIDE_DOC = REPO_ROOT / "docs" / "octopus_user_guide.md"
CORPUS_DIR = REPO_ROOT / "knowledge_base" / "corpus_new"
MANIFEST_PATH = REPO_ROOT / "knowledge_base" / "corpus_manifest.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    path.write_text(serialized, encoding="utf-8")
    tmp.unlink(missing_ok=True)


# ─── 1. Convergence document sync ────────────────────────────────────────────

def extract_physics_result(report: Dict[str, Any]) -> Dict[str, Any]:
    """Extract physics result from orchestrator report."""
    executor = report.get("executor", {})
    physics = executor.get("physics_result", {}) or {}

    tuning = executor.get("tuning_profile", {}) or {}
    numerical = tuning.get("numerical_axis", {}) or {}
    model = tuning.get("model_axis", {}) or {}

    delta = physics.get("benchmark_delta", {}) or {}

    return {
        "case_id": report.get("planner", {}).get("selected_case") or report.get("case_id", "") or "",
        "molecule": physics.get("molecule_name", ""),
        "calc_mode": physics.get("calc_mode", "gs"),
        "total_energy": physics.get("ground_state_energy_hartree"),
        "homo_energy": physics.get("homo_energy"),
        "lumo_energy": physics.get("lumo_energy"),
        "reference_energy": delta.get("reference_energy"),
        "relative_error": delta.get("relative_error"),
        "threshold": delta.get("threshold"),
        "spacing": numerical.get("spacing"),
        "radius": numerical.get("radius"),
        "xc": model.get("xc", ""),
        "pseudopotential": model.get("pseudopotential_set", ""),
        "extra_states": model.get("extra_states"),
        "scf_tolerance": numerical.get("scf_tolerance"),
        "max_scf_iterations": numerical.get("max_scf_iterations"),
        "verdict": report.get("reviewer", {}).get("primary_acceptance", {}).get("primary_verdict", "?"),
        "timestamp": report.get("generated_at", utc_now_iso()),
    }


def build_convergence_row(r: Dict[str, Any]) -> str:
    """Build a markdown table row for octopus_case_convergence.md."""
    te = f"{r['total_energy']:.6f}" if r.get('total_energy') is not None else "—"
    ref = f"{r['reference_energy']:.6f}" if r.get('reference_energy') is not None else "—"
    rel_err = f"{r['relative_error']*100:.2f}%" if r.get('relative_error') is not None else "—"
    spacing = f"{r['spacing']}" if r.get('spacing') is not None else "?"
    radius = f"{r['radius']}" if r.get('radius') is not None else "?"
    xc = r.get('xc', '?')
    homo = f"{r['homo_energy']:.6f}" if r.get('homo_energy') is not None else "—"
    verdict = "✅ PASS" if r.get('verdict') == 'PASS' else f"❌ {r.get('verdict', 'FAIL')}"
    date = r.get('timestamp', '')[:10]

    return f"| {r.get('molecule', '?')} | {r.get('calc_mode', 'gs').upper()} | {verdict} | {date} | {te} Ha | {ref} Ha | {rel_err} | sp={spacing}Å R={radius}Å {xc} |"


def update_convergence_doc(result: Dict[str, Any]) -> None:
    """Append verified result to octopus_case_convergence.md."""
    if not CONVERGENCE_DOC.exists():
        print(f"[sync] WARN: {CONVERGENCE_DOC} not found, skipping convergence doc update")
        return

    content = CONVERGENCE_DOC.read_text(encoding="utf-8")
    row = build_convergence_row(result)
    molecule = result.get('molecule', '?')
    case_id = result.get('case_id', '')
    date = result.get('timestamp', '')[:10]
    mode = result.get('calc_mode', 'gs')
    species = result.get('pseudopotential', 'formula')

    # Strictly match section header (## at line start, not inside tables)
    molecule_esc = re.escape(molecule)
    case_id_esc = re.escape(case_id)

    # Find section by looking for ## at start of line containing molecule name or case_id
    section_start = None
    section_end = None
    lines = content.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match section header lines only (## at column 0 or after optional #)
        if stripped.startswith('## '):
            header_text = stripped[3:].lower()
            if molecule_esc.lower() in header_text or case_id_esc.lower() in header_text:
                section_start = i
            elif section_start is not None:
                # Found next section, close previous
                section_end = i
                break

    if section_start is not None:
        if section_end is None:
            section_end = len(lines)
        section = '\n'.join(lines[section_start:section_end])

        # Check for duplicate (same energy + date)
        te = f"{result.get('total_energy', 0):.4f}"
        if te in section and date in section:
            print(f"[sync] Result already exists for {molecule}/{case_id} on {date}, skipping")
        else:
            # Append new row at end of section (before next ## or EOF)
            new_content = '\n'.join(lines[:section_end])
            new_content += f"\n\n**Orchestrator 实测（{date}）：**\n\n| Molecule | Mode | Verdict | Date | Etot (Ha) | Ref (Ha) | Error | Parameters |\n"
            new_content += f"|----------|------|---------|------|-----------|----------|-------|------------|\n"
            new_content += f"| {row} |\n"
            if section_end < len(lines):
                new_content += '\n'.join(lines[section_end:])
            content = new_content
            print(f"[sync] Updated existing section for {molecule}/{case_id}")
    else:
        # No existing section — append new section
        # Determine PP vs formula
        pp_type = "Formula Mode" if species == "formula" else "PP Mode"
        new_section = f"""

## {molecule} | {pp_type} | ✅ PASS ({date})

> Auto-synced from orchestrator result

| 量 | 值 |
|----|----|
| Case ID | `{case_id}` |
| Total Energy | {result.get('total_energy', '—'):.6f} Ha |
| Reference | {result.get('reference_energy', '—'):.6f} Ha |
| Relative Error | {result.get('relative_error', 0)*100:.2f}% |
| Spacing | {result.get('spacing', '?')} Å |
| Radius | {result.get('radius', '?')} Å |
| XC | {result.get('xc', '?')} |

**本次结果：**

| Molecule | Mode | Verdict | Date | Etot (Ha) | Ref (Ha) | Error | Parameters |
|----------|------|---------|------|-----------|----------|-------|------------|
{row}

"""
        content += new_section
        print(f"[sync] Created new section for {molecule}/{case_id}")

    CONVERGENCE_DOC.write_text(content, encoding="utf-8")
    print(f"[sync] Wrote {CONVERGENCE_DOC}")


# ─── 2. User guide sync ──────────────────────────────────────────────────────

CAPABILITY_TABLE_HEADER = """
## Executor Capability Summary

| Case | Mode | PP/Pseudopotential | XC | Spacing | Radius | Status |
|------|------|--------------------|----|---------|--------|--------|
"""

def update_user_guide(result: Dict[str, Any]) -> None:
    """Update executor capability table in octopus_user_guide.md."""
    if not USER_GUIDE_DOC.exists():
        print(f"[sync] WARN: {USER_GUIDE_DOC} not found, skipping user guide update")
        return

    content = USER_GUIDE_DOC.read_text(encoding="utf-8")
    molecule = result.get('molecule', '?')
    case_id = result.get('case_id', '')
    xc = result.get('xc', '?')
    spacing = result.get('spacing', '?')
    radius = result.get('radius', '?')
    species = result.get('pseudopotential', '?')
    verdict = "✅ PASS" if result.get('verdict') == 'PASS' else "❌ FAIL"

    # Build new row
    new_row = f"| `{case_id}` | {result.get('calc_mode', 'gs').upper()} | {species} | {xc} | {spacing} Å | {radius} Å | {verdict} |"

    # Try to find and update existing row for this case_id
    case_id_esc = re.escape(case_id)
    pattern = r"\| `\{" + case_id_esc + r"\}` \|.*?\|.*?\|.*?\|.*?\|.*?\|.*?\|"
    if re.search(pattern, content):
        content = re.sub(pattern, new_row, content)
        print(f"[sync] Updated capability table row for {case_id}")
    else:
        # Append to capability table
        if CAPABILITY_TABLE_HEADER.strip() in content:
            content = content.replace(CAPABILITY_TABLE_HEADER,
                                      CAPABILITY_TABLE_HEADER + "\n" + new_row)
            print(f"[sync] Appended capability table row for {case_id}")
        else:
            print(f"[sync] WARN: Capability table header not found in user guide")

    USER_GUIDE_DOC.write_text(content, encoding="utf-8")
    print(f"[sync] Wrote {USER_GUIDE_DOC}")


# ─── 3. KB corpus file sync ──────────────────────────────────────────────────

def update_corpus_file(result: Dict[str, Any]) -> None:
    """Update or create KB corpus .md file for this case."""
    case_id = result.get('case_id', '')
    if not case_id:
        return

    # Find existing corpus file
    existing = None
    for f in CORPUS_DIR.glob(f"{case_id}*.md"):
        existing = f
        break

    molecule = result.get('molecule', '')
    xc = result.get('xc', 'unknown')
    spacing = result.get('spacing', 0.18)
    radius = result.get('radius', 10.0)
    total_energy = result.get('total_energy')
    reference_energy = result.get('reference_energy')
    relative_error = result.get('relative_error')
    verdict = result.get('verdict', 'PASS')
    date = result.get('timestamp', '')[:10]

    if verdict != 'PASS' and relative_error is not None:
        # For FAIL cases, just log and don't create/update corpus
        print(f"[sync] Case {case_id} verdict={verdict}, not writing to KB corpus")
        return

    # Format new measurement row (used for both update and create)
    te_str = f"{total_energy:.6f}" if total_energy is not None else "—"
    ref_str = f"{reference_energy:.6f}" if reference_energy is not None else "—"
    err_str = f"{relative_error*100:.2f}%" if relative_error is not None else "—"
    new_measurement = f"| {date} | {te_str} Ha | {ref_str} Ha | {err_str} | sp={spacing}Å R={radius}Å {xc} |"

    if existing:
        # Update existing file — append measurement result
        content = existing.read_text(encoding="utf-8")

        # Try to update or append to实测结果 table
        meas_pattern = r"(\*\*实测结果：\*\*.*?\n\n\| Date \|)"
        meas_match = re.search(meas_pattern, content, re.DOTALL)

        if meas_match:
            insert_pos = meas_match.end()
            # Find end of table
            table_end = content.find('\n\n', insert_pos)
            if table_end == -1:
                table_end = len(content)
            # Check if row already exists
            if f"{total_energy:.4f}" not in content[insert_pos:table_end]:
                content = content[:table_end] + f"\n{new_measurement}" + content[table_end:]
                print(f"[sync] Updated existing KB file {existing.name}")
            else:
                print(f"[sync] Measurement already in KB file {existing.name}")
        else:
            # Append new measurement section
            content += f"""

## Measured Results

> Auto-synced from orchestrator {date}

| Date | Etot (Ha) | Ref (Ha) | Error | Parameters |
|------|-----------|----------|-------|------------|
| {new_measurement}

"""
            print(f"[sync] Appended measurement to KB file {existing.name}")

        existing.write_text(content, encoding="utf-8")
    else:
        # Create new KB file
        new_file = CORPUS_DIR / f"{case_id}.md"
        if new_file.exists():
            print(f"[sync] KB file {new_file.name} already exists")
            return

        doc = f"""# {case_id} — Auto-Synced KB Entry

> **Auto-generated**: {utc_date()}
> **Source**: Orchestrator execution result

## Provenance

| Field | Value |
|-------|-------|
| **Case ID** | `{case_id}` |
| **Molecule** | {molecule} |
| **Category** | DFT ground-state |
| **Confidence Tier** | **A-ready** |
| **Auto-Synced** | {date} |

## System Definition

- **Formula**: {molecule}
- **Calculation Mode**: {result.get('calc_mode', 'gs')}
- **XC Functional**: {xc}
- **Pseudopotential**: {result.get('pseudopotential', 'N/A')}
- **Spacing**: {spacing} Å
- **Radius**: {radius} Å

## Reference Values

| Quantity | Value | Unit | Source |
|----------|------:|------|--------|
| Total Energy | {ref_str} | Ha | orchestrator reference |
| Computed Energy | {te_str} | Ha | MCP result |

## Measured Results

> Auto-synced from orchestrator {date}

| Date | Etot (Ha) | Ref (Ha) | Error | Parameters |
|------|-----------|----------|-------|------------|
| {date} | {te_str} | {ref_str} | {err_str} | sp={spacing}Å R={radius}Å {xc} |

## Reproducibility Metadata

- `xc`: {xc}
- `spacing`: {spacing} Å
- `radius`: {radius} Å
- `species`: {result.get('pseudopotential', 'formula')}
- `scf_tolerance`: {result.get('scf_tolerance', '1e-6')}
- `max_scf_iterations`: {result.get('max_scf_iterations', '?')}
- `extra_states`: {result.get('extra_states', '?')}

## Changelog

- {date}: Auto-synced from orchestrator result (verdict={verdict}, error={err_str})
"""
        new_file.write_text(doc, encoding="utf-8")
        print(f"[sync] Created new KB file {new_file.name}")


# ─── 4. Corpus manifest sync ──────────────────────────────────────────────────

def rebuild_corpus_manifest() -> None:
    """Rebuild corpus_manifest.json from all .md files in corpus_new/."""
    entries = []
    for md_file in sorted(CORPUS_DIR.glob("*.md")):
        if md_file.name in ("README.md", "executor_guide.md", "tddft_metrics_supplemental.md", "octopus_tutorial16_capability_matrix.md"):
            continue
        content = md_file.read_text(encoding="utf-8")

        # Extract case_id from first header
        case_id = re.search(r"^#\s+(\S+)", content, re.MULTILINE)
        case_id = case_id.group(1).rstrip("—") if case_id else md_file.stem

        # Extract confidence tier
        tier_match = re.search(r"Confidence Tier.*?\*\*([A-Za-z\-]+)\*\*", content, re.DOTALL)
        tier = tier_match.group(1) if tier_match else "C-draft"

        # Extract reference energy if present
        ref_match = re.search(r"Reference.*?\|\s*([-+]?[0-9.]+)\s*\| Ha", content)
        ref_energy = float(ref_match.group(1)) if ref_match else None

        # Extract primary source URL
        src_match = re.search(r"Primary Source.*?\[([^\]]+)\]\(([^\)]+)\)", content)
        src_url = src_match.group(2) if src_match else ""

        entries.append({
            "case_id": case_id,
            "file": f"corpus_new/{md_file.name}",
            "confidence_tier": tier,
            "reference_energy_hartree": ref_energy,
            "primary_source_url": src_url,
            "last_updated": utc_date(),
        })

    manifest = {
        "generated_at": utc_now_iso(),
        "generated_by": "sync_case_result.py",
        "total_entries": len(entries),
        "entries": entries,
    }

    save_json(MANIFEST_PATH, manifest)
    print(f"[sync] Rebuilt corpus_manifest.json with {len(entries)} entries")


# ─── Main ─────────────────────────────────────────────────────────────────────

def sync_from_report(report_path: Path) -> None:
    """Main entry point: sync results from an orchestrator report JSON."""
    print(f"[sync] Loading report: {report_path}")
    report = load_json(report_path)

    # Extract verdict
    reviewer = report.get("reviewer", {}) or {}
    primary = reviewer.get("primary_acceptance", {}) or {}
    verdict = primary.get("primary_verdict", "?")

    if verdict != "PASS":
        print(f"[sync] Verdict={verdict}, auto-sync only syncs PASS cases")
        # Still update manifest to reflect latest runs
        rebuild_corpus_manifest()
        return

    # Extract physics result
    result = extract_physics_result(report)
    case_id = result.get('case_id', '')
    print(f"[sync] Syncing PASS case: {case_id}")
    print(f"[sync]   Etot={result.get('total_energy')} Ha | error={result.get('relative_error')} | xc={result.get('xc')}")

    # Run all sync operations
    try:
        update_convergence_doc(result)
    except Exception as e:
        print(f"[sync] ERROR updating convergence doc: {e}")

    try:
        update_user_guide(result)
    except Exception as e:
        print(f"[sync] ERROR updating user guide: {e}")

    try:
        update_corpus_file(result)
    except Exception as e:
        import traceback
        print(f"[sync] ERROR updating corpus file: {e}")
        traceback.print_exc()

    try:
        rebuild_corpus_manifest()
    except Exception as e:
        print(f"[sync] ERROR rebuilding manifest: {e}")

    print(f"[sync] Done.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync orchestrator results to docs and KB")
    parser.add_argument("--report", type=Path, required=True, help="Path to orchestrator report JSON")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"[sync] ERROR: report not found: {args.report}")
        return 1

    sync_from_report(args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
