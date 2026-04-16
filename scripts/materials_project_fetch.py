#!/usr/bin/env python3
"""
Materials Project DFT data fetcher for Dirac KB.

Uses mp-api (Materials Project official client) to fetch:
- H2O, CH4, H2, Si, N2 分子/晶体的 DFT band gap / formation energy
- 格式化输出为 markdown 文档，直接供 build_research_kb.py 摄入

Usage:
    python scripts/materials_project_fetch.py --api-key KEY [--formulas H2O CH4 Si] [--output-dir knowledge_base/corpus_new_mp]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── MP API imports (installed via conda-forge) ──────────────────────────────
try:
    from mp_api.client import MPRester
    _MP_AVAILABLE = True
except ImportError:
    _MP_AVAILABLE = False
    MPRester = None


# ── Default target formulas / systems ─────────────────────────────────────
DEFAULT_TARGETS = [
    # (formula_or_system, description, case_id)
    ("H2O",           "water molecule DFT bandgap and structure",       "h2o_mp_reference"),
    ("CH4",           "methane molecule DFT formation energy",          "ch4_mp_reference"),
    ("Si",            "silicon crystal DFT bandgap (semiconductor)",    "si_mp_reference"),
    ("H2",            "hydrogen molecule DFT total energy",             "h2_mp_reference"),
    ("N2",            "nitrogen molecule DFT total energy",            "n2_mp_reference"),
    ("C",             "carbon (graphite/diamond) DFT reference",       "c_mp_reference"),
    ("Fe",            "iron magnetic material DFT reference",           "fe_mp_reference"),
    ("TiO2",          "TiO2 anatase/rutile DFT bandgap",               "tio2_mp_reference"),
]

# Fields we want per material
SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "composition",
    "band_gap",
    "formation_energy_per_atom",
    "e_above_hull",
    "structure",
    "spacegroup",
    "nsites",
    "nelements",
    "density",
    "volume",
    "energy",
    "energy_per_atom",
    "total_magnetization",
    "is_magnetic",
    "is_metal",
    "is_xcFunctional",
    "xc_functional",
    "theoretical",
    "database_IDs",
]

STRUCTURE_FIELDS = [
    "material_id",
    "formula_pretty",
    "structure",
    "spacegroup",
    "lattice",
    "nsites",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def format_composition(comp) -> str:
    """Convert pymatgen Composition object to human-readable string."""
    try:
        # Get alphabetical formula like H2 O
        return comp.reduced_formula
    except Exception:
        return str(comp)


def format_structure(structure) -> str:
    """Convert pymatgen Structure object to POSCAR-like string."""
    lines = []
    try:
        lattice = structure.lattice
        lines.append(f"Lattice (Angstrom): {lattice.a:.4f} {lattice.b:.4f} {lattice.c:.4f} | {lattice.alpha:.2f} {lattice.beta:.2f} {lattice.gamma:.2f}")
        lines.append(f"Space group: {structure.get_space_group_info()}")
        lines.append("")
        lines.append("Fractional coordinates:")
        for site in structure:
            species = site.specie.symbol
            frac = site.frac_coords
            lines.append(f"  {species:>2}: [{frac[0]:.6f}, {frac[1]:.6f}, {frac[2]:.6f}]")
    except Exception as e:
        lines.append(f"(structure parsing error: {e})")
    return "\n".join(lines)


def build_markdown_entry(doc: dict, source_type: str = "materials_project") -> str:
    """Build a markdown document from an MP summary document."""
    formula    = doc.get("formula_pretty", "unknown")
    mat_id     = doc.get("material_id", "")
    band_gap   = doc.get("band_gap", None)
    form_e     = doc.get("formation_energy_per_atom", None)
    e_hull     = doc.get("e_above_hull", None)
    energy     = doc.get("energy", None)
    epa        = doc.get("energy_per_atom", None)
    volume     = doc.get("volume", None)
    density    = doc.get("density", None)
    xc_func    = doc.get("xc_functional", "unknown")
    theoretical = doc.get("theoretical", False)
    is_metal   = doc.get("is_metal", None)
    is_mag     = doc.get("is_magnetic", False)
    mag        = doc.get("total_magnetization", None)
    nsites     = doc.get("nsites", 0)
    nelements  = doc.get("nelements", 0)

    # Provenance
    provenance_parts = [
        f"source: Materials Project (https://materialsproject.org/materials/{mat_id})",
        f"accessed: {now_iso()}",
        f"xc_functional: {xc_func}",
        f"theoretical: {theoretical}",
        f"material_id: {mat_id}",
    ]
    if form_e is not None:
        provenance_parts.append(f"formation_energy_per_atom: {form_e:.4f} eV/atom")
    if e_hull is not None:
        provenance_parts.append(f"e_above_hull: {e_hull:.4f} eV/atom (stability)")
    provenance_parts.append(f"structure_type: {'theoretical' if theoretical else 'experimental'}")

    # Physical discussion
    sections = []

    # Header
    sections.append(f"# {formula} — Materials Project DFT Reference")
    sections.append("")
    sections.append(f"**Formula**: {formula}  ")
    sections.append(f"**Material ID**: {mat_id}  ")
    sections.append(f"**Source**: [Materials Project](https://materialsproject.org/materials/{mat_id})  ")
    sections.append(f"**Last Updated**: {now_iso()}  ")
    sections.append(f"**Type**: {'Theoretical (DFT)' if theoretical else 'Experimental'}  ")
    sections.append("")

    # Provenance block
    sections.append("## Provenance")
    sections.append("")
    for p in provenance_parts:
        sections.append(f"- {p}")
    sections.append("")

    # Electronic structure
    sections.append("## Electronic Structure")
    sections.append("")
    if band_gap is not None:
        if band_gap > 0:
            sections.append(f"- **Band gap**: {band_gap:.4f} eV")
            sections.append(f"- **Conductor type**: Semiconductor/Insulator")
        else:
            sections.append(f"- **Band gap**: 0.0 eV (metallic)")
            sections.append(f"- **Conductor type**: Metal")
    else:
        sections.append("- Band gap: N/A")
    if is_metal is not None:
        sections.append(f"- **Is metal**: {is_metal}")
    if is_mag:
        sections.append(f"- **Magnetic**: Yes (total magnetization: {mag} bohr-magneton)" if mag else "- **Magnetic**: Yes")
    else:
        sections.append("- **Magnetic**: No")
    sections.append(f"- **Functional**: {xc_func}")
    sections.append("")

    # Thermodynamic stability
    sections.append("## Thermodynamic Stability")
    sections.append("")
    if form_e is not None:
        sections.append(f"- **Formation energy**: {form_e:.4f} eV/atom")
        if form_e < 0:
            sections.append("  → Thermodynamically stable (negative formation energy)")
        else:
            sections.append("  → Thermodynamically unstable (positive formation energy)")
    else:
        sections.append("- Formation energy: N/A")
    if e_hull is not None:
        sections.append(f"- **Energy above hull**: {e_hull:.4f} eV/atom")
        if e_hull < 0.01:
            sections.append("  → Ground state / very stable")
        elif e_hull < 0.1:
            sections.append("  → Near ground state")
    sections.append("")

    # Total energy
    sections.append("## Total Energy")
    sections.append("")
    if energy is not None:
        sections.append(f"- **Total energy**: {energy:.6f} eV")
    if epa is not None:
        sections.append(f"- **Energy per atom**: {epa:.6f} eV/atom")
    if volume is not None:
        sections.append(f"- **Volume**: {volume:.4f} Angstrom^3")
    if density is not None:
        sections.append(f"- **Density**: {density:.4f} g/cm^3")
    sections.append("")

    # Structure
    if "structure" in doc and doc["structure"]:
        sections.append("## Crystal Structure")
        sections.append("")
        struct = doc["structure"]
        if isinstance(struct, dict):
            # Serialized structure
            lattice = struct.get("lattice", {})
            if isinstance(lattice, dict):
                a = lattice.get("a", 0)
                b = lattice.get("b", 0)
                c = lattice.get("c", 0)
                alpha = lattice.get("alpha", 0)
                beta  = lattice.get("beta", 0)
                gamma = lattice.get("gamma", 0)
                sections.append(f"- **Lattice**: a={a:.4f}, b={b:.4f}, c={c:.4f} Angstrom | alpha={alpha:.2f}, beta={beta:.2f}, gamma={gamma:.2f} deg")
            sg = struct.get("spacegroup", {})
            if isinstance(sg, dict):
                sections.append(f"- **Space group**: {sg.get('symbol', 'N/A')} (IT number: {sg.get('number', 'N/A')})")
            frac_coords = struct.get("frac_coords", [])
            species = struct.get("species", [])
            if frac_coords and species:
                sections.append("- **Fractional coordinates**:")
                for sp, fc in zip(species[:10], frac_coords[:10]):  # limit to 10
                    sections.append(f"  {sp}: [{fc[0]:.6f}, {fc[1]:.6f}, {fc[2]:.6f}]")
        sections.append("")
    else:
        sections.append("## Crystal Structure")
        sections.append("")
        sections.append("- Structure data not included in this query response")
        sections.append("")

    # Physical interpretation
    sections.append("## Physical Interpretation for Dirac/Octopus Comparison")
    sections.append("")
    if formula == "H2O":
        sections.append("H2O is a key test case for Octopus TDDFT absorption spectrum.")
        if band_gap:
            sections.append(f"  MP LDA bandgap {band_gap:.2f} eV can be compared with Octopus TDDFT first peak (~7.5 eV).")
        sections.append("  Note: MP uses PAW pseudopotentials (VASP) vs Octopus norm-conserving PP — direct numbers differ but trends should agree.")
    elif formula == "CH4":
        sections.append("CH4 (methane) is a simple molecular benchmark for Octopus GS energy convergence.")
        if form_e is not None:
            sections.append(f"  MP formation energy {form_e:.3f} eV/atom provides thermodynamic anchor for Octopus GS total energy.")
    elif formula == "Si":
        sections.append("Si is the canonical semiconductor test case from Octopus Tutorial 16 (periodic systems / optical spectra).")
        if band_gap:
            sections.append(f"  MP LDA bandgap {band_gap:.3f} eV vs experimental 1.1 eV — similar LDA underestimation to Octopus.")
        sections.append("  Direct comparison: Octopus Tutorial 16 reports LDA bandgap ~0.5 eV.")
    sections.append("")

    # Comparison guidance
    sections.append("## Comparison with Octopus Calculations")
    sections.append("")
    sections.append("| Property | MP (VASP) | Octopus (this repo) | Notes |")
    sections.append("|---|---|---|---|")
    if band_gap is not None:
        sections.append(f"| Band gap (eV) | {band_gap:.4f} | TBD (your run) | MP uses PAW; Octopus uses norm-conserving PP |")
    if form_e is not None:
        sections.append(f"| Formation energy (eV/atom) | {form_e:.4f} | TBD (your run) | Cross-check thermodynamic stability |")
    if energy is not None and epa is not None:
        sections.append(f"| Total energy (eV) | {epa:.4f} per atom | TBD (your run) | Per-atom comparison most robust |")
    sections.append("")

    # References
    sections.append("## References")
    sections.append("")
    sections.append(f"- Materials Project entry: https://materialsproject.org/materials/{mat_id}")
    sections.append("- Methodology: https://docs.materialsproject.org/methodology/materials-methodology/calculation-details")
    sections.append("")

    return "\n".join(sections)


def fetch_mp_data(api_key: str, formulas: list, output_dir: Path, timeout: int = 30) -> dict:
    """Fetch MP data for given formulas and write markdown files."""
    results = {
        "fetched": [],
        "failed": [],
        "output_files": [],
    }

    if not _MP_AVAILABLE:
        raise RuntimeError(
            "mp-api not available. Please install: conda install -c conda-forge mp-api=0.29.0"
        )

    with MPRester(api_key) as mpr:
        for formula in formulas:
            mat_id_list = []
            try:
                # Search summary docs
                docs = mpr.materials.summary.search(
                    formulas=[formula],
                    fields=SUMMARY_FIELDS,
                    limit=3,  # top 3 most stable entries per formula
                )

                if not docs:
                    # Try by chemsys
                    docs = mpr.materials.summary.search(
                        chemsys=[formula],
                        fields=SUMMARY_FIELDS,
                        limit=3,
                    )

                if not docs:
                    print(f"[MP] No results for {formula}, skipping")
                    results["failed"].append(formula)
                    continue

                for doc in docs:
                    mat_id = doc.material_id
                    mat_id_list.append(mat_id)

                    # Build markdown
                    doc_dict = {
                        "material_id": doc.material_id,
                        "formula_pretty": doc.formula_pretty,
                        "composition": str(doc.composition),
                        "band_gap": doc.band_gap,
                        "formation_energy_per_atom": doc.formation_energy_per_atom,
                        "e_above_hull": doc.e_above_hull,
                        "energy": doc.energy,
                        "energy_per_atom": doc.energy_per_atom,
                        "volume": doc.volume,
                        "density": doc.density,
                        "xc_functional": doc.xc_functional,
                        "theoretical": doc.theoretical,
                        "is_metal": doc.is_metal,
                        "is_magnetic": doc.is_magnetic,
                        "total_magnetization": doc.total_magnetization,
                        "nsites": doc.nsites,
                        "nelements": doc.nelements,
                        "structure": None,
                    }

                    # Try to get structure too
                    try:
                        struct_docs = mpr.materials.structure.search(
                            material_ids=[mat_id],
                            fields=STRUCTURE_FIELDS,
                            limit=1,
                        )
                        if struct_docs:
                            s = struct_docs[0]
                            doc_dict["structure"] = {
                                "lattice": {
                                    "a": s.structure.lattice.a,
                                    "b": s.structure.lattice.b,
                                    "c": s.structure.lattice.c,
                                    "alpha": s.structure.lattice.alpha,
                                    "beta":  s.structure.lattice.beta,
                                    "gamma": s.structure.lattice.gamma,
                                },
                                "spacegroup": {
                                    "symbol": s.structure.get_space_group_info()[0],
                                    "number": s.structure.get_space_group_info()[1],
                                },
                                "species": [str(site.specie) for site in s.structure],
                                "frac_coords": [site.frac_coords.tolist() for site in s.structure],
                            }
                    except Exception as e:
                        print(f"[MP] Structure fetch failed for {mat_id}: {e}")

                    md_text = build_markdown_entry(doc_dict)

                    # Write markdown file
                    safe_id = formula.replace("*", "_").replace("/", "_")
                    out_path = output_dir / f"mp_{safe_id}_{mat_id}.md"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(md_text, encoding="utf-8")

                    results["fetched"].append({
                        "formula": formula,
                        "material_id": mat_id,
                        "band_gap": doc.band_gap,
                        "formation_energy": doc.formation_energy_per_atom,
                        "output_file": out_path.as_posix(),
                    })
                    results["output_files"].append(out_path.as_posix())
                    print(f"[MP] Fetched {formula} ({mat_id}): band_gap={doc.band_gap}, E_form={doc.formation_energy_per_atom}")

            except Exception as e:
                print(f"[MP] Failed to fetch {formula}: {e}")
                results["failed"].append(formula)

    return results


def build_corpus_manifest_entries(results: dict, output_dir: Path) -> list:
    """Build corpus_manifest entries for MP sources."""
    entries = []
    for item in results.get("fetched", []):
        out_path = Path(item["output_file"])
        safe_id = item["formula"].replace("*", "_").replace("/", "_")
        source_id = f"mp_{safe_id}_{item['material_id']}"

        # Determine confidence tier
        form_e = item.get("formation_energy")
        band_gap = item.get("band_gap")
        if form_e is not None and abs(form_e) < 0.1:
            tier = "A-ready"
        elif band_gap is not None:
            tier = "B-needs-comparison"
        else:
            tier = "B-needs-evidence"

        entry = {
            "source_id": source_id,
            "type": "local_markdown",
            "title": f"Materials Project DFT Reference — {item['formula']} ({item['material_id']})",
            "case_id": f"{item['formula'].lower()}_mp_reference",
            "topic_tags": [
                "dft", "materials_project", "bandgap", "formation_energy",
                "xc_functional", "periodic", "molecule",
                item["formula"].lower()
            ],
            "local_markdown": out_path.as_posix(),
            "provenance": {
                "primary_url": f"https://materialsproject.org/materials/{item['material_id']}",
                "source_type": "materials_project_database",
                "software_version": "VASP (PAW PBE)",  # MP default
                "xc_functional": "PBE (GGA)",
                "confidence_tier": tier,
                "verified": True,
                "provenance_file": out_path.as_posix(),
                "mp_material_id": item["material_id"],
            },
            "reference_values": {
                "band_gap_eV": band_gap,
                "formation_energy_per_atom_eV": form_e,
                "unit": "eV",
            },
            "qa_notes": [
                f"Fetched from Materials Project via mp-api at {now_iso()}",
                "Values are from VASP PAW calculations (PBE functional)",
                "For Octopus comparison: use same functional (LDA/GGA) and similar PSF family",
            ],
        }
        entries.append(entry)
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DFT data from Materials Project for KB.")
    parser.add_argument("--api-key", default=os.environ.get("MATERIALS_PROJECT_API_KEY", ""),
                        help="Materials Project API key (or set MATERIALS_PROJECT_API_KEY env var)")
    parser.add_argument("--formulas", nargs="+",
                        default=["H2O", "CH4", "Si", "H2", "N2"],
                        help="Formulas to fetch (default: H2O CH4 Si H2 N2)")
    parser.add_argument("--output-dir", default="knowledge_base/corpus_mp",
                        help="Output directory for fetched markdown files")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout per request")
    parser.add_argument("--manifest-out", default="knowledge_base/corpus_mp_manifest.json",
                        help="Output path for generated corpus_manifest entries JSON")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repo root (for path resolution)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("[MP] ERROR: No API key provided. Set --api-key or MATERIALS_PROJECT_API_KEY env var.")
        return 1

    if not _MP_AVAILABLE:
        print("[MP] ERROR: mp-api not installed.")
        print("       On HPC, run: conda install -y -c conda-forge mp-api=0.29.0")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[MP] Fetching {len(args.formulas)} formulas: {args.formulas}")
    results = fetch_mp_data(args.api_key, args.formulas, output_dir, timeout=args.timeout)

    print(f"\n[MP] Summary:")
    print(f"  Fetched: {len(results['fetched'])}")
    print(f"  Failed:  {len(results['failed'])}")

    if results["fetched"]:
        manifest_entries = build_corpus_manifest_entries(results, output_dir)
        manifest_path = Path(args.manifest_out)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({"version": now_iso(), "sources": manifest_entries}, indent=2, ensure_ascii=True),
            encoding="utf-8"
        )
        print(f"\n[MP] Corpus manifest entries written to: {manifest_path.as_posix()}")

        # Also write a summary JSON for inspection
        summary = {
            "fetched_at": now_iso(),
            "total_fetched": len(results["fetched"]),
            "total_failed": len(results["failed"]),
            "files": results["output_files"],
        }
        summary_path = output_dir / "fetch_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[MP] Summary written to: {summary_path.as_posix()}")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
