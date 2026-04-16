#!/usr/bin/env python3
"""Run Octopus official-like GS total-energy convergence sweep.

Reference tutorial:
https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from urllib import request

HARTREE_TO_EV = 27.211386245988
DEFAULT_SPACINGS = [0.26, 0.24, 0.22, 0.20, 0.18, 0.16, 0.14]


def resolve_report_style(molecule: str, tutorial_profile: str, report_style: str) -> str:
    requested = (report_style or "auto").strip().lower()
    if requested in {"n_atom_error", "total_energy_only"}:
        return requested
    mol = (molecule or "").strip().lower()
    prof = (tutorial_profile or "").strip().lower()
    if mol == "n_atom" and not prof:
        return "n_atom_error"
    return "total_energy_only"


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310: controlled internal endpoint
        return json.loads(resp.read().decode("utf-8"))


def verify_web_provenance(reference_url: str, molecule: str, timeout: int) -> dict[str, Any]:
    req = request.Request(reference_url, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310: user-requested public docs provenance check
        html = resp.read().decode("utf-8", errors="replace")

    title_match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

    anchors: list[str] = []
    html_lower = html.lower()
    mol = (molecule or "").strip().lower()
    if mol == "ch4":
        anchors = [
            "methane molecule",
            "the total energy is converged to within 0.1 ev for a spacing of 0.18",
            "#sp    energy",
        ]
    elif mol == "n_atom":
        anchors = [
            "nitrogen atom: finding a good spacing",
            "a rather good spacing for this nitrogen pseudopotential seems to be 0.18",
        ]

    missing = [a for a in anchors if a not in html_lower]
    if missing:
        raise RuntimeError(f"Provenance anchor check failed for {molecule}: missing {missing}")

    return {
        "reference_url": reference_url,
        "reference_title": title,
        "reference_checked_at": datetime.now(timezone.utc).isoformat(),
        "reference_anchor_count": len(anchors),
        "reference_anchor_missing": missing,
    }


def build_payload(spacing_angstrom: float, radius_angstrom: float, ncpus: int, mpiprocs: int, xc: str, spin_components: str, molecule: str, extra_states: int, eigensolver: str) -> dict[str, Any]:
    molecule = (molecule or "N_atom").strip()
    if molecule == "N_atom":
        molecule_payload: Any = {
            "name": "N_atom",
            "atoms": [{"symbol": "N", "x": 0.0, "y": 0.0, "z": 0.0}],
        }
        octopus_molecule = "N_atom"
    else:
        molecule_payload = molecule
        octopus_molecule = molecule

    payload = {
        "engineMode": "octopus3D",
        "calcMode": "gs",
        "octopusCalcMode": "gs",
        "caseType": "dft_gs_3d",
        "octopusDimensions": "3D",
        "speciesMode": "pseudo",
        "pseudopotentialSet": "standard",
        "octopusLengthUnit": "angstrom",
        "octopusSpacing": float(spacing_angstrom),
        "octopusRadius": float(radius_angstrom),
        "octopusBoxShape": "sphere",
        "octopusExtraStates": int(extra_states),
        "xcFunctional": xc,
        "spinComponents": spin_components,
        "fastPath": False,
        "octopusNcpus": ncpus,
        "octopusMpiprocs": mpiprocs,
        "molecule": molecule_payload,
        "octopusMolecule": octopus_molecule,
    }
    if eigensolver:
        payload["octopusEigenSolver"] = eigensolver
    return payload


def extract_point(spacing: float, raw: dict[str, Any], include_orbital_error: bool) -> dict[str, Any]:
    s_ha = None
    p_ha = None
    if include_orbital_error:
        eigenvalues = raw.get("eigenvalues") or []
        s_ha = float(eigenvalues[0]) if len(eigenvalues) >= 1 else None
        if len(eigenvalues) >= 4:
            p_ha = mean(float(v) for v in eigenvalues[1:4])
        elif len(eigenvalues) >= 2:
            p_ha = float(eigenvalues[1])

    total_energy_ha = raw.get("total_energy")
    molecular = raw.get("molecular") or {}
    if total_energy_ha is None:
        total_energy_ha = molecular.get("total_energy_hartree")

    converged = raw.get("converged")
    if converged is None:
        converged = molecular.get("converged")

    scf_iterations = raw.get("scf_iterations")
    if scf_iterations is None:
        scf_iterations = molecular.get("scf_iterations")

    scheduler = raw.get("scheduler") or {}
    point = {
        "spacing_angstrom": spacing,
        "total_energy_hartree": float(total_energy_ha) if total_energy_ha is not None else None,
        "converged": bool(converged),
        "scf_iterations": scf_iterations,
        "job_id": scheduler.get("job_id"),
        "queue": scheduler.get("queue"),
        "run_dir": scheduler.get("run_dir"),
        "error": None,
    }
    if include_orbital_error:
        point["s_eigen_hartree"] = s_ha
        point["p_eigen_hartree"] = p_ha
    return point


def compute_errors_vs_reference(points: list[dict[str, Any]], ref_spacing: float, include_orbital_error: bool) -> None:
    ref = next((p for p in points if math.isclose(p["spacing_angstrom"], ref_spacing, abs_tol=1e-12)), None)
    if ref is None:
        raise RuntimeError(f"Reference spacing {ref_spacing} not found in run points")

    ref_total = ref.get("total_energy_hartree")
    ref_s = ref.get("s_eigen_hartree") if include_orbital_error else None
    ref_p = ref.get("p_eigen_hartree") if include_orbital_error else None

    for p in points:
        total = p.get("total_energy_hartree")
        p["error_total_energy_ev"] = (total - ref_total) * HARTREE_TO_EV if total is not None and ref_total is not None else None
        if include_orbital_error:
            s_eigen = p.get("s_eigen_hartree")
            p_eigen = p.get("p_eigen_hartree")
            p["error_s_eigen_ev"] = (s_eigen - ref_s) * HARTREE_TO_EV if s_eigen is not None and ref_s is not None else None
            p["error_p_eigen_ev"] = (p_eigen - ref_p) * HARTREE_TO_EV if p_eigen is not None and ref_p is not None else None


def find_spacing_by_tail_fluctuation(points: list[dict[str, Any]], tolerance_ev: float) -> dict[str, Any]:
    valid = [p for p in points if p.get("total_energy_hartree") is not None]
    if not valid:
        return {
            "tolerance_ev": tolerance_ev,
            "first_spacing_within_band_angstrom": None,
            "tail_band_ev": None,
            "status": "no_data",
        }

    for i, p in enumerate(valid):
        tail = valid[i:]
        vals = [float(t["total_energy_hartree"]) for t in tail]
        band_ev = (max(vals) - min(vals)) * HARTREE_TO_EV
        if band_ev <= tolerance_ev:
            return {
                "tolerance_ev": tolerance_ev,
                "first_spacing_within_band_angstrom": float(p["spacing_angstrom"]),
                "tail_band_ev": band_ev,
                "status": "ok",
            }

    vals_all = [float(t["total_energy_hartree"]) for t in valid]
    return {
        "tolerance_ev": tolerance_ev,
        "first_spacing_within_band_angstrom": None,
        "tail_band_ev": (max(vals_all) - min(vals_all)) * HARTREE_TO_EV,
        "status": "not_reached",
    }


def write_outputs(out_dir: Path, tag: str, payload: dict[str, Any], points: list[dict[str, Any]], ref_spacing: float, plot_png: bool, molecule: str, provenance: dict[str, Any], convergence_band: dict[str, Any], report_style: str, include_orbital_error: bool) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = (molecule or "case").strip().lower().replace(" ", "_")
    json_path = out_dir / f"octopus_{slug}_total_energy_convergence_{tag}.json"
    csv_path = out_dir / f"octopus_{slug}_total_energy_convergence_{tag}.csv"
    md_path = out_dir / f"octopus_{slug}_total_energy_convergence_{tag}.md"
    png_path = out_dir / f"octopus_{slug}_total_energy_convergence_{tag}.png"

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_tutorial": "https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/",
        "reference_spacing_angstrom": ref_spacing,
        "molecule": molecule,
        "provenance": provenance,
        "convergence_band": convergence_band,
        "report_style": report_style,
        "payload_template": payload,
        "points": points,
    }
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if include_orbital_error:
        csv_lines = [
            "spacing_angstrom,total_energy_hartree,total_energy_ev,error_total_energy_ev,error_s_eigen_ev,error_p_eigen_ev,converged,scf_iterations,job_id"
        ]
    else:
        csv_lines = [
            "spacing_angstrom,total_energy_hartree,total_energy_ev,error_total_energy_ev,converged,scf_iterations,job_id"
        ]
    for p in points:
        total_h = p.get("total_energy_hartree")
        total_ev = (float(total_h) * HARTREE_TO_EV) if total_h is not None else ""
        common = [
            str(p.get("spacing_angstrom", "")),
            str(total_h if total_h is not None else ""),
            str(total_ev),
            str(p.get("error_total_energy_ev", "")),
        ]
        if include_orbital_error:
            common.extend([
                str(p.get("error_s_eigen_ev", "")),
                str(p.get("error_p_eigen_ev", "")),
            ])
        common.extend([
            str(p.get("converged", "")),
            str(p.get("scf_iterations", "")),
            str(p.get("job_id", "")),
        ])
        csv_lines.append(
            ",".join(common)
        )
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    md_lines = [
        f"# {molecule} Total Energy Convergence (Official-style)",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- reference: {report['reference_tutorial']}",
        f"- reference_spacing: {ref_spacing} Angstrom",
        f"- convergence_band_tolerance: {convergence_band.get('tolerance_ev')} eV",
        f"- first_spacing_within_band: {convergence_band.get('first_spacing_within_band_angstrom')}",
        f"- tail_band_ev: {convergence_band.get('tail_band_ev')}",
        "",
    ]
    if include_orbital_error:
        md_lines.extend([
            "| Spacing (A) | Total error (eV) | s-eigen error (eV) | p-eigen error (eV) | Converged | SCF iters | Job ID |",
            "|---:|---:|---:|---:|:---:|---:|---|",
        ])
    else:
        md_lines.extend([
            "| Spacing (A) | Total Energy (Ha) | Total Energy (eV) | Total error (eV) | Converged | SCF iters | Job ID |",
            "|---:|---:|---:|---:|:---:|---:|---|",
        ])
    for p in points:
        total_h = p.get("total_energy_hartree")
        total_ev = (float(total_h) * HARTREE_TO_EV) if total_h is not None else None
        if include_orbital_error:
            md_lines.append(
                "| {spacing:.2f} | {te} | {se} | {pe} | {conv} | {iters} | {job} |".format(
                    spacing=float(p["spacing_angstrom"]),
                    te=("{:.6f}".format(p["error_total_energy_ev"]) if p.get("error_total_energy_ev") is not None else "N/A"),
                    se=("{:.6f}".format(p["error_s_eigen_ev"]) if p.get("error_s_eigen_ev") is not None else "N/A"),
                    pe=("{:.6f}".format(p["error_p_eigen_ev"]) if p.get("error_p_eigen_ev") is not None else "N/A"),
                    conv="Y" if p.get("converged") else "N",
                    iters=p.get("scf_iterations", ""),
                    job=p.get("job_id", ""),
                )
            )
        else:
            md_lines.append(
                "| {spacing:.2f} | {th} | {tev} | {te} | {conv} | {iters} | {job} |".format(
                    spacing=float(p["spacing_angstrom"]),
                    th=("{:.8f}".format(total_h) if total_h is not None else "N/A"),
                    tev=("{:.6f}".format(total_ev) if total_ev is not None else "N/A"),
                    te=("{:.6f}".format(p["error_total_energy_ev"]) if p.get("error_total_energy_ev") is not None else "N/A"),
                    conv="Y" if p.get("converged") else "N",
                    iters=p.get("scf_iterations", ""),
                    job=p.get("job_id", ""),
                )
            )
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    wrote_plot = False
    if plot_png:
        try:
            import matplotlib.pyplot as plt

            xs = [p["spacing_angstrom"] for p in points]
            if include_orbital_error:
                y_total = [p.get("error_total_energy_ev") for p in points]
                y_s = [p.get("error_s_eigen_ev") for p in points]
                y_p = [p.get("error_p_eigen_ev") for p in points]
            else:
                y_total = [((float(p["total_energy_hartree"]) * HARTREE_TO_EV) if p.get("total_energy_hartree") is not None else None) for p in points]

            plt.figure(figsize=(8, 5))
            plt.plot(xs, y_total, marker="o", color="#8A2BE2", label="total_energy")
            if include_orbital_error:
                plt.plot(xs, y_s, marker="o", color="#0D9488", label="s-eigen")
                plt.plot(xs, y_p, marker="o", color="#38BDF8", label="p-eigen")
            plt.xlabel("Spacing (Angstrom)")
            plt.ylabel("Error (eV)" if include_orbital_error else "Total Energy (eV)")
            plt.title(
                f"Convergence with spacing of {molecule}" if include_orbital_error
                else f"Total Energy vs Spacing ({molecule})"
            )
            plt.grid(True, alpha=0.25)
            plt.legend()
            plt.tight_layout()
            plt.savefig(png_path, dpi=150)
            plt.close()
            wrote_plot = True
        except Exception:
            wrote_plot = False

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "md": str(md_path),
        "png": str(png_path) if wrote_plot else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run official-like GS total-energy convergence sweep using Octopus API")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001", help="API base URL")
    parser.add_argument("--timeout-seconds", type=int, default=1800, help="Per-run request timeout")
    parser.add_argument("--radius", type=float, default=5.0, help="Simulation radius")
    parser.add_argument("--ncpus", type=int, default=64)
    parser.add_argument("--mpiprocs", type=int, default=64)
    parser.add_argument("--xc-functional", default="lda_x+lda_c_pz")
    parser.add_argument("--reference-spacing", type=float, default=0.14)
    parser.add_argument("--spin-components", default="spin_polarized")
    parser.add_argument("--molecule", default="N_atom", help="Molecule id: N_atom, N2, CH4, H2O, etc.")
    parser.add_argument("--spacings", default=",".join(str(v) for v in DEFAULT_SPACINGS), help="Comma-separated spacings")
    parser.add_argument("--extra-states", type=int, default=1)
    parser.add_argument("--reference-url", default="https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/")
    parser.add_argument("--tutorial-profile", default="", help="Use built-in official profile, e.g. methane_spacing")
    parser.add_argument("--eigensolver", default="")
    parser.add_argument("--report-style", default="auto", help="auto | n_atom_error | total_energy_only")
    parser.add_argument("--convergence-tolerance-ev", type=float, default=0.1)
    parser.add_argument("--output-dir", default="docs/harness_reports")
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    if args.tutorial_profile == "methane_spacing":
        args.molecule = "CH4"
        args.radius = 3.5
        args.spacings = "0.22,0.20,0.18,0.16,0.14,0.12,0.10"
        args.reference_spacing = 0.10
        args.extra_states = 4
        args.eigensolver = "chebyshev_filter"

    provenance = verify_web_provenance(args.reference_url, args.molecule, timeout=max(20, args.timeout_seconds))
    report_style = resolve_report_style(args.molecule, args.tutorial_profile, args.report_style)
    include_orbital_error = report_style == "n_atom_error"

    spacings = [float(x.strip()) for x in str(args.spacings).split(",") if x.strip()]
    points: list[dict[str, Any]] = []

    for spacing in spacings:
        try:
            payload = build_payload(spacing, args.radius, args.ncpus, args.mpiprocs, args.xc_functional, args.spin_components, args.molecule, args.extra_states, args.eigensolver)
            raw = post_json(f"{args.api_base.rstrip('/')}/api/physics/run", payload, args.timeout_seconds)
            point = extract_point(spacing, raw, include_orbital_error=include_orbital_error)
        except Exception as exc:
            point = {
                "spacing_angstrom": spacing,
                "total_energy_hartree": None,
                "converged": False,
                "scf_iterations": None,
                "job_id": None,
                "queue": None,
                "run_dir": None,
                "error": str(exc),
            }
            if include_orbital_error:
                point["s_eigen_hartree"] = None
                point["p_eigen_hartree"] = None
        points.append(point)
        print(f"[run] spacing={spacing:.2f}A converged={point.get('converged')} total={point.get('total_energy_hartree')} error={point.get('error')}", flush=True)

    successful_points = [p for p in points if p.get("total_energy_hartree") is not None]
    if not successful_points:
        raise RuntimeError("All convergence points failed; no usable data generated")

    compute_errors_vs_reference(points, args.reference_spacing, include_orbital_error=include_orbital_error)
    convergence_band = find_spacing_by_tail_fluctuation(points, args.convergence_tolerance_ev)
    tag = _now_tag()
    template_payload = build_payload(args.reference_spacing, args.radius, args.ncpus, args.mpiprocs, args.xc_functional, args.spin_components, args.molecule, args.extra_states, args.eigensolver)
    outputs = write_outputs(
        Path(args.output_dir),
        tag,
        template_payload,
        points,
        args.reference_spacing,
        plot_png=not args.no_plot,
        molecule=args.molecule,
        provenance=provenance,
        convergence_band=convergence_band,
        report_style=report_style,
        include_orbital_error=include_orbital_error,
    )

    print("[done] outputs:")
    for key, value in outputs.items():
        if value:
            print(f"  - {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
