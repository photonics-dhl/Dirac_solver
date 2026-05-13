#!/usr/bin/env python3
"""
Multi-parameter Octopus sweep for Dirac_solver.

Performs a grid sweep over Octopus parameters (XC functional, eigensolver,
grid spacing, SCF tolerance, soft-core alpha, etc.) and reports which
combinations converge and their ground-state energies.

Usage:
    python scripts/run_multi_parameter_octopus_sweep.py \\
        --case hydrogen_gs_reference \\
        --api-base http://10.72.212.33:3001 \\
        --output-dir docs/harness_reports/sweeps/

    # Sweep only XC functional for H
    python scripts/run_multi_parameter_octopus_sweep.py \\
        --case hydrogen_gs_reference --sweep-mode xc \\
        --xc-functionals lda_x+lda_c_pz gga_x_pbe+gga_c_pbe gga_x_b88+gga_c_lyp

    # Full grid sweep (all parameter combos)
    python scripts/run_multi_parameter_octopus_sweep.py \\
        --case hydrogen_gs_reference --sweep-mode full \\
        --max-combinations 100
"""

import argparse
import itertools
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Local imports ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

try:
    import requests

    def _post_json(url: str, payload: dict, timeout: int = 120) -> dict:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
except ImportError:
    import urllib.request

    def _post_json(url: str, payload: dict, timeout: int = 120) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


# ── Reference energies ─────────────────────────────────────────────────────────
CASE_REFERENCES: Dict[str, Dict[str, Any]] = {
    "hydrogen_gs_reference": {
        "molecule": "H",
        "reference_energy_hartree": -0.5,
        "reference_source": "NIST/CODATA exact (Rydberg constant)",
        "reference_url": "https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev",
        "xc_authoritative": "lda_x+lda_c_pz",
    },
    "ch4_gs_reference": {
        "molecule": "CH4",
        "reference_energy_hartree": -8.04,
        "reference_source": "Octopus Tutorial (formula pseudo-potential)",
        "reference_url": "https://www.octopus-code.org/documentation/16/",
        "xc_authoritative": "lda_x+lda_c_pz",
    },
    "n_atom_gs_official": {
        "molecule": "N",
        "reference_energy_hartree": -9.75473657,
        "reference_source": "Octopus Tutorial 16 (spacing=0.18Å, eV→Ha conversion)",
        "reference_url": "https://www.octopus-code.org/documentation/16/",
        "xc_authoritative": "lda_x+lda_c_pz",
    },
}

# ── Sweep parameter grids ─────────────────────────────────────────────────────
# Each axis is a list of values; None means "use default from executor".
# Values are passed directly to the MCP REST endpoint.

SWEEP_AXES: Dict[str, List[Any]] = {
    # XC functional: passed as xcFunctional (maps to Octopus XCFunctional block)
    "xc": [
        "lda_x+lda_c_pz",  # LDA Perdew-Zunger (default)
        # "lda_x+lda_c_ca",  # BROKEN: 'lda_c_ca' is not a valid Octopus functional
        # Valid LDA correlation in Octopus: lda_c_pz (Perdew-Zunger), lda_c_vWN (Vosko-Wilk-Nusair), lda_c_pw (Perdew-Wang)
        "gga_x_pbe+gga_c_pbe",  # GGA PBE
        "gga_x_b88+gga_c_lyp",  # GGA BLYP
        # "hartree_fock",  # BROKEN in formula mode: Octopus gives Exchange=0 with species_user_defined
        # HF only works with species_pseudo (standard PP), not formula mode
    ],
    # SCF tolerance
    "scf_tolerance": [1e-4, 1e-5, 1e-6, 1e-7],
    # Grid spacing (Bohr)
    "spacing": [0.05, 0.10, 0.15, 0.20],
    # Radius (Bohr)
    "radius": [5.0, 7.5, 10.0],
    # Eigensolver
    "eigensolver": [
        "rmdiis",  # default — RMM-DIIS
        "davidson",  # Davidson diagonalization
        "cg",  # conjugate gradient
        "lobpcg",  # Locally Optimal Block PCG
    ],
    # Mixing scheme
    "mixing_scheme": [
        "broyden",  # default
        "linear",
        "anderson",
        "pulay",
    ],
    # Soft-core alpha (only for formula mode)
    "soft_core_alpha": [0.01, 0.05, 0.1, 0.2, 0.5],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_hash(config: dict) -> str:
    """Stable hash of a config dict for identification."""
    s = json.dumps(config, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def build_base_payload(case_id: str, case_info: Dict[str, Any]) -> dict:
    """Build the base REST payload for a given case."""
    molecule = case_info["molecule"]
    return {
        "engineMode": "octopus3D",
        "calcMode": "gs",
        "octopusCalcMode": "gs",
        "octopusDimensions": "3D",
        "octopusPeriodic": "off",
        "octopusBoxShape": "sphere",
        "octopusMolecule": molecule,
        "molecule": molecule,
        "dimensionality": "3D",
        "equationType": "Schrodinger",
        "problemType": "boundstate",
        "potentialType": "Coulomb",
        "fastPath": False,  # always full accuracy
        "octopusSpacing": 0.05,
        "octopusRadius": 10.0,
        "octopusLengthUnit": "bohr",
        "octopusExtraStates": 4,
        "octopusMaxScfIterations": 200,
        "octopusScfTolerance": 1e-6,
        # Default XC
        "xcFunctional": "lda_x+lda_c_pz",
        "mixingScheme": "broyden",
        # Default species mode (formula)
        "speciesMode": "formula",
        # Default soft-core alpha
        "softCoreAlpha": {"_default": 0.1},
    }


def resolve_reference(source: str) -> Tuple[float, float]:
    """Resolve reference energy and return (value, error) in Ha.

    For multi-parameter sweeps we compare computed energy vs reference
    at the authoritative XC (LDA). For non-LDA functionals we record
    the delta from LDA reference as "expected deviation".
    """
    # Return NaN to signal "no comparison available"
    return float("nan"), float("nan")


def compute_delta(computed: float, reference: float) -> Tuple[float, float]:
    """Compute absolute and relative delta from reference."""
    if reference == 0 or abs(reference) < 1e-12:
        return float("nan"), float("nan")
    abs_delta = abs(computed - reference)
    rel_delta = abs_delta / abs(reference)
    return abs_delta, rel_delta


def apply_param_overrides(payload: dict, overrides: dict) -> dict:
    """Apply parameter overrides to base payload."""
    p = dict(payload)
    for key, value in overrides.items():
        if key == "xc" or key == "xcFunctional":
            p["xcFunctional"] = value
        elif key == "scf_tolerance":
            p["octopusScfTolerance"] = value
        elif key == "spacing":
            p["octopusSpacing"] = value
        elif key == "radius":
            p["octopusRadius"] = value
        elif key == "eigensolver":
            p["octopusEigenSolver"] = value
        elif key == "mixing_scheme":
            p["mixingScheme"] = value
        elif key == "soft_core_alpha":
            p["softCoreAlpha"] = {"_default": float(value)}
        elif key in payload:
            p[key] = value
    return p


def run_single(
    api_base: str,
    payload: dict,
    timeout: int = 180,
) -> Tuple[dict, bool, str]:
    """Run a single Octopus calculation via REST API.

    Returns:
        (result_dict, converged, error_message)
    """
    url = f"{api_base.rstrip('/')}/api/physics/run"
    try:
        result = _post_json(url, payload, timeout=timeout)
        converged = bool(result.get("converged", False))
        error_msg = str(result.get("error") or result.get("message") or "")
        return result, converged, error_msg
    except Exception as exc:
        return {}, False, str(exc)


def grid_product(axes: Dict[str, List], max_combos: int = 200) -> List[dict]:
    """Generate parameter combination list, capped at max_combos.

    Uses round-robin interleaving to spread coverage evenly when
    max_combos < full grid size.
    """
    keys = list(axes.keys())
    values = list(axes.values())
    n_combos = 1
    for v in values:
        n_combos *= len(v)

    if n_combos <= max_combos:
        # Full grid
        combos = []
        for combo in itertools.product(*values):
            combos.append(dict(zip(keys, combo)))
        return combos

    # Sparse coverage: round-robin sample
    picks_per_axis = max(1, int(round((max_combos / n_combos) ** (1 / len(keys)))))
    sampled = [v[:picks_per_axis] for v in values]
    combos = []
    for combo in itertools.product(*sampled):
        combos.append(dict(zip(keys, combo)))
    return combos


# ── Main sweep logic ───────────────────────────────────────────────────────────

def run_sweep(
    case_id: str,
    api_base: str,
    sweep_axes: Dict[str, List],
    output_dir: Path,
    max_combinations: int = 200,
    timeout_per_run: int = 180,
    dry_run: bool = False,
) -> dict:
    """Run the full parameter sweep and return a summary report."""

    if case_id not in CASE_REFERENCES:
        raise ValueError(
            f"Unknown case_id: {case_id!r}. "
            f"Available: {list(CASE_REFERENCES.keys())}"
        )

    case_info = CASE_REFERENCES[case_id]
    base_payload = build_base_payload(case_id, case_info)
    ref_energy = case_info["reference_energy_hartree"]
    ref_source = case_info["reference_source"]
    ref_url = case_info["reference_url"]

    # Generate parameter combinations
    combos = grid_product(sweep_axes, max_combinations)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{case_id}_sweep_{timestamp}"

    results: List[dict] = []
    converged_count = 0
    errors: List[str] = []

    for i, combo in enumerate(combos):
        payload = apply_param_overrides(base_payload, combo)
        label = " × ".join(f"{k}={v}" for k, v in combo.items())

        print(f"[{i+1}/{len(combos)}] {label}")

        if dry_run:
            results.append({
                "combo": combo,
                "label": label,
                "status": "dry_run",
                "converged": None,
                "total_energy_hartree": None,
                "scf_iterations": None,
                "error": None,
            })
            continue

        result_data, converged, error_msg = run_single(api_base, payload, timeout=timeout_per_run)
        oct_result = result_data.get("result", {}) if isinstance(result_data, dict) else {}
        molecular = oct_result.get("molecular", {}) if isinstance(oct_result, dict) else {}
        total_energy = molecular.get("total_energy_hartree")

        # Compute delta from reference (LDA baseline)
        abs_delta = None
        rel_delta = None
        if isinstance(total_energy, (int, float)):
            abs_delta, rel_delta = compute_delta(float(total_energy), ref_energy)
            if converged:
                converged_count += 1

        # Determine XC label for display
        xc_label = combo.get("xc", "lda_x+lda_c_pz")

        row = {
            "combo_index": i + 1,
            "combo": combo,
            "label": label,
            "status": "ok" if converged else "failed",
            "converged": converged,
            "total_energy_hartree": total_energy,
            "scf_iterations": oct_result.get("scf_iterations") if isinstance(oct_result, dict) else None,
            "eigenvalues": molecular.get("energy_levels", [])[:5] if isinstance(molecular, dict) else [],
            "abs_delta_from_reference": abs_delta,
            "rel_delta_from_reference": rel_delta,
            "error": error_msg if error_msg else None,
            "config_hash": config_hash(payload),
            "xc_functional": xc_label,
        }
        results.append(row)

        if error_msg:
            errors.append(f"[{label}] {error_msg}")

    # ── Build summary ─────────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r.get("converged"))
    failed = total - passed

    # Group by XC functional
    by_xc: Dict[str, List[dict]] = {}
    for r in results:
        xc = r.get("xc_functional", "unknown")
        by_xc.setdefault(xc, []).append(r)

    xc_summary = {}
    for xc, xc_results in by_xc.items():
        energies = [r["total_energy_hartree"] for r in xc_results if isinstance(r["total_energy_hartree"], (int, float))]
        best_energy = min(energies) if energies else None
        xc_passed = sum(1 for r in xc_results if r.get("converged"))
        xc_summary[xc] = {
            "total_runs": len(xc_results),
            "converged": xc_passed,
            "convergence_rate": round(xc_passed / len(xc_results) * 100, 1) if xc_results else 0,
            "energies": sorted(set(round(e, 6) for e in energies)),
            "best_energy_hartree": best_energy,
        }

    # Best overall (lowest energy among converged)
    converged_energies = [
        (r["total_energy_hartree"], r["label"], r["combo"])
        for r in results
        if r.get("converged") and isinstance(r["total_energy_hartree"], (int, float))
    ]
    best_row = min(converged_energies, key=lambda x: x[0]) if converged_energies else (None, None, None)

    report = {
        "generated_at": now_iso(),
        "run_id": run_id,
        "case_id": case_id,
        "molecule": case_info["molecule"],
        "reference_energy_hartree": ref_energy,
        "reference_source": ref_source,
        "reference_url": ref_url,
        "sweep_axes": {k: list(v) for k, v in sweep_axes.items()},
        "total_combinations": total,
        "max_combinations": max_combinations,
        "converged_count": converged_count,
        "failed_count": failed,
        "convergence_rate_pct": round(converged_count / total * 100, 1) if total else 0,
        "best_converged": {
            "total_energy_hartree": best_row[0],
            "label": best_row[1],
            "combo": best_row[2],
        } if best_row[0] is not None else None,
        "xc_summary": xc_summary,
        "all_results": results,
        "errors": errors,
    }

    # ── Write outputs ─────────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    md_lines = build_markdown_report(report, case_info)
    md_path = output_dir / f"{run_id}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_lines)

    print(f"\nSweep complete: {converged_count}/{total} converged")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")

    return report


def build_markdown_report(report: dict, case_info: Dict[str, Any]) -> str:
    """Build a readable markdown report from the sweep results."""

    lines = [
        f"# Octopus Multi-Parameter Sweep Report",
        "",
        f"**Run ID**: `{report['run_id']}`",
        f"**Case**: `{report['case_id']}` ({report['molecule']})",
        f"**Generated**: {report['generated_at']}",
        f"**Sweep axes**: {', '.join(report['sweep_axes'].keys())}",
        f"**Total combinations**: {report['total_combinations']}",
        f"**Converged**: {report['converged_count']}/{report['total_combinations']} ({report['convergence_rate_pct']}%)",
        "",
        "## Reference",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Reference energy (Ha) | {report['reference_energy_hartree']} |",
        f"| Source | {report['reference_source']} |",
        f"| URL | {report['reference_url']} |",
        "",
    ]

    # XC summary table
    lines += [
        "## XC Functional Summary",
        "",
        f"| XC Functional | Runs | Converged | Rate | Best E (Ha) |",
        f"|---------------|------|-----------|------|-------------|",
    ]
    for xc, xs in sorted(report["xc_summary"].items()):
        best = f"{xs['best_energy_hartree']:.6f}" if xs["best_energy_hartree"] else "—"
        lines.append(
            f"| `{xc}` | {xs['total_runs']} | {xs['converged']} | "
            f"{xs['convergence_rate']}% | {best} |"
        )

    # Convergence heat-map by XC × spacing
    lines += ["", "## Convergence Map (XC × Spacing)", ""]
    lines.append("| XC \\ Spacing | " + " | ".join(str(s) for s in SWEEP_AXES.get("spacing", [])) + " |")
    lines.append("|" + "|".join(["---"] * (len(SWEEP_AXES.get("spacing", [])) + 1)) + "|")
    xc_spacing: Dict[str, Dict[float, int]] = {}
    for r in report["all_results"]:
        xc = r.get("xc_functional", "unknown")
        sp = r.get("combo", {}).get("spacing")
        converged = int(r.get("converged") or False)
        xc_spacing.setdefault(xc, {})
        xc_spacing[xc][sp] = xc_spacing[xc].get(sp, 0) + converged
    for xc in sorted(xc_spacing.keys()):
        row = [f"`{xc}`"]
        for sp in SWEEP_AXES.get("spacing", []):
            cnt = xc_spacing[xc].get(sp, 0)
            row.append(str(cnt) if cnt > 0 else "—")
        lines.append("| " + " | ".join(row) + " |")

    # Energy table for best converged per XC
    lines += [
        "",
        "## Best Converged Energy by XC Functional",
        "",
        "| XC Functional | Best E (Ha) | Rel. Δ from Ref | Combo |",
        "|----------------|-------------|-----------------|-------|",
    ]
    for xc, xs in sorted(report["xc_summary"].items()):
        if xs["best_energy_hartree"] is None:
            continue
        ref = report["reference_energy_hartree"]
        best_e = xs["best_energy_hartree"]
        rel = abs(best_e - ref) / abs(ref) if ref != 0 else float("nan")
        # Find the combo label for best energy
        best_label = ""
        for r in report["all_results"]:
            if r.get("xc_functional") == xc and r.get("total_energy_hartree") == best_e:
                best_label = r.get("label", "")[:60]
                break
        lines.append(f"| `{xc}` | {best_e:.6f} | {rel*100:.1f}% | {best_label} |")

    # Best overall
    best = report["best_converged"]
    if best and best["total_energy_hartree"] is not None:
        ref = report["reference_energy_hartree"]
        rel = abs(best["total_energy_hartree"] - ref) / abs(ref) if ref != 0 else float("nan")
        lines += [
            "",
            "## Best Overall (Lowest Energy Converged)",
            "",
            f"- **Energy**: {best['total_energy_hartree']:.6f} Ha",
            f"- **Rel. Δ from ref. ({ref} Ha)**: {rel*100:.2f}%",
            f"- **Combo**: {best['label']}",
        ]

    # Provenance links
    lines += [
        "",
        "## Provenance & References",
        "",
        f"- Reference energy: {report['reference_source']} — {report['reference_url']}",
        f"- Case: `{report['case_id']}`",
        f"- Octopus version: via MCP server (port 8000)",
        "",
        "## Sweep Parameters",
        "",
    ]
    for axis, values in report["sweep_axes"].items():
        lines.append(f"- **{axis}**: {values}")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-parameter Octopus sweep")
    p.add_argument("--case", required=True,
                   choices=list(CASE_REFERENCES.keys()),
                   help="Case ID to sweep")
    p.add_argument("--api-base", default="http://127.0.0.1:3004",
                   help="Base URL for the harness REST API (port 3004 = Node API, 8101 = uvicorn fallback)")
    p.add_argument("--output-dir", default="docs/harness_reports/sweeps",
                   help="Directory for sweep output files")
    p.add_argument("--sweep-mode", default="xc", choices=["xc", "grid", "full"],
                   help="Sweep mode: xc=XC only, grid=XC+spacing, full=all axes")
    p.add_argument("--xc-functionals", nargs="+",
                   help="Override XC functionals to sweep")
    p.add_argument("--max-combinations", type=int, default=200,
                   help="Max parameter combinations to run")
    p.add_argument("--timeout", type=int, default=180,
                   help="Timeout per Octopus run (seconds)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print combos without running Octopus")
    return p.parse_args()


def main():
    args = parse_args()

    # Determine sweep axes based on mode
    if args.sweep_mode == "xc":
        axes = {"xc": args.xc_functionals or SWEEP_AXES["xc"]}
    elif args.sweep_mode == "grid":
        axes = {
            "xc": SWEEP_AXES["xc"],
            "spacing": SWEEP_AXES["spacing"],
        }
    else:  # full
        axes = {k: v for k, v in SWEEP_AXES.items()}

    output_dir = Path(args.output_dir)

    report = run_sweep(
        case_id=args.case,
        api_base=args.api_base,
        sweep_axes=axes,
        output_dir=output_dir,
        max_combinations=args.max_combinations,
        timeout_per_run=args.timeout,
        dry_run=args.dry_run,
    )

    json_path = output_dir / f"{report['run_id']}.json"
    md_path = output_dir / f"{report['run_id']}.md"
    print(f"\nOutputs:")
    print(f"  {json_path}")
    print(f"  {md_path}")


if __name__ == "__main__":
    main()
