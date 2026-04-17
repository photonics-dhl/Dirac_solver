#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

HARTREE_TO_EV = 27.211386245988
SPACINGS = [0.22, 0.20, 0.18, 0.16, 0.14, 0.12, 0.10]
REF_SPACING = 0.16
DEFAULT_API_BASE = "http://127.0.0.1:3001"
REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "harness_reports" / "octopus_case_optimal_parameters_20260413.md"


def post_json(url: str, payload: dict, timeout: int = 900) -> dict:
    req = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text) if text else {}


def health_check(api_base: str) -> None:
    req = Request(f"{api_base}/api/mcp/health", method="GET")
    with urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Health check failed: HTTP {resp.status}")


def build_payload(spacing: float) -> dict:
    return {
        "engineMode": "octopus3D",
        "calcMode": "gs",
        "octopusCalcMode": "gs",
        "caseType": "dft_gs_3d",
        "octopusDimensions": "3D",
        "speciesMode": "pseudo",
        "pseudopotentialSet": "standard",
        "octopusLengthUnit": "angstrom",
        "octopusUnitsOutput": "eV_Angstrom",
        "octopusSpacing": spacing,
        "octopusRadius": 3.5,
        "octopusBoxShape": "sphere",
        "octopusExtraStates": 4,
        "xcFunctional": "gga_x_pbe+gga_c_pbe",
        "spinComponents": "unpolarized",
        "fastPath": False,
        "octopusNcpus": 32,
        "octopusMpiprocs": 32,
        "octopusEigenSolver": "chebyshev_filter",
        "molecule": "CH4",
        "octopusMolecule": "CH4",
    }


def run_sweep(api_base: str, request_timeout: int) -> list[dict]:
    points = []
    for spacing in SPACINGS:
        print(f"[run] spacing={spacing:.2f}A", flush=True)
        payload = build_payload(spacing)
        try:
            result = post_json(f"{api_base}/api/physics/run", payload, timeout=request_timeout)
            molecular = result.get("molecular") or {}
            scheduler = result.get("scheduler") or {}
            total_ha = result.get("total_energy")
            if total_ha is None:
                total_ha = molecular.get("total_energy_hartree")
            total_ha = float(total_ha) if total_ha is not None else None
            points.append(
                {
                    "spacing": spacing,
                    "total_energy_hartree": total_ha,
                    "total_energy_ev": (total_ha * HARTREE_TO_EV) if total_ha is not None else None,
                    "converged": bool(result.get("converged", molecular.get("converged", False))),
                    "scf_iterations": result.get("scf_iterations", molecular.get("scf_iterations")),
                    "job_id": scheduler.get("job_id") or "-",
                    "error": None,
                }
            )
            print(f"[ok] spacing={spacing:.2f}A", flush=True)
        except Exception as exc:
            points.append(
                {
                    "spacing": spacing,
                    "total_energy_hartree": None,
                    "total_energy_ev": None,
                    "converged": False,
                    "scf_iterations": None,
                    "job_id": "-",
                    "error": str(exc),
                }
            )
            print(f"[fail] spacing={spacing:.2f}A error={exc}", flush=True)
    return points


def compute_metrics(points: list[dict]) -> dict:
    ref = next((p for p in points if abs(p["spacing"] - REF_SPACING) < 1e-12), None)
    ref_ha = ref.get("total_energy_hartree") if ref else None
    for p in points:
        if p.get("total_energy_hartree") is None or ref_ha is None:
            p["error_total_energy_ev"] = None
        else:
            p["error_total_energy_ev"] = (p["total_energy_hartree"] - ref_ha) * HARTREE_TO_EV

    def tail_band(from_spacing: float) -> float | None:
        vals = [p["total_energy_hartree"] for p in points if p["total_energy_hartree"] is not None and p["spacing"] <= from_spacing]
        if not vals:
            return None
        return (max(vals) - min(vals)) * HARTREE_TO_EV

    tail_018 = tail_band(0.18)
    tail_016 = tail_band(0.16)
    succeeded = sum(1 for p in points if p.get("total_energy_hartree") is not None)
    return {
        "tail_018_ev": tail_018,
        "tail_016_ev": tail_016,
        "official_aligned": (tail_016 is not None and tail_016 <= 0.1),
        "succeeded_points": succeeded,
        "total_points": len(points),
        "has_reference_016": ref_ha is not None,
    }


def append_doc(points: list[dict], metrics: dict, api_base: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = []
    lines.append(f"## 8) CH4 前端发起复现记录 ({now})")
    lines.append("")
    lines.append("- 触发路径: frontend-equivalent `/api/physics/run` (Octopus GS)")
    lines.append(f"- API base: `{api_base}`")
    lines.append("- 参数口径: pseudo + angstrom + `fastPath=false` + `radius=3.5` + `extra_states=4` + `chebyshev_filter`")
    lines.append("- 参考 spacing: 0.16 A")
    lines.append("")
    lines.append("| spacing (A) | total_energy (Ha) | total_energy (eV) | error vs 0.16A (eV) | converged | scf_iterations | job_id |")
    lines.append("|---:|---:|---:|---:|:---:|---:|---|")
    for p in points:
        if p.get("error"):
            lines.append(f"| {p['spacing']:.2f} | N/A | N/A | N/A | N | - | timeout/error |")
            continue
        ha = "N/A" if p["total_energy_hartree"] is None else f"{p['total_energy_hartree']:.8f}"
        ev = "N/A" if p["total_energy_ev"] is None else f"{p['total_energy_ev']:.6f}"
        err = "N/A" if p.get("error_total_energy_ev") is None else f"{p['error_total_energy_ev']:.6f}"
        lines.append(
            f"| {p['spacing']:.2f} | {ha} | {ev} | {err} | {'Y' if p['converged'] else 'N'} | {p['scf_iterations'] if p['scf_iterations'] is not None else '-'} | {p['job_id']} |"
        )
    lines.append("")
    lines.append(f"- Completed points: {metrics['succeeded_points']}/{metrics['total_points']}")
    lines.append(f"- Reference point 0.16A available: {'Y' if metrics['has_reference_016'] else 'N'}")
    lines.append(f"- Tail band (from 0.18A): {metrics['tail_018_ev']:.6f} eV" if metrics["tail_018_ev"] is not None else "- Tail band (from 0.18A): N/A")
    lines.append(f"- Tail band (from 0.16A): {metrics['tail_016_ev']:.6f} eV" if metrics["tail_016_ev"] is not None else "- Tail band (from 0.16A): N/A")
    lines.append(f"- Official criterion (<=0.1 eV from 0.16A): {'PASS' if metrics['official_aligned'] else 'FAIL'}")
    lines.append("")

    existing = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    DOC_PATH.write_text(existing.rstrip() + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay CH4 convergence via frontend-equivalent API.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL, e.g. http://127.0.0.1:3001")
    parser.add_argument("--request-timeout", type=int, default=300, help="Per-spacing request timeout seconds")
    args = parser.parse_args()
    api_base = str(args.api_base or DEFAULT_API_BASE).rstrip("/")

    try:
        health_check(api_base)
        print(f"[health] api_base={api_base} ok", flush=True)
        points = run_sweep(api_base, request_timeout=max(30, int(args.request_timeout)))
        metrics = compute_metrics(points)
        append_doc(points, metrics, api_base)
        print(json.dumps({"ok": True, "points": points, "metrics": metrics}, ensure_ascii=False))
        return 0
    except (HTTPError, URLError, RuntimeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
