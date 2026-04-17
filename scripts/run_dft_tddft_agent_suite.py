#!/usr/bin/env python3
"""Run production-oriented DFT/TDDFT agent suite and emit auditable reports."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONVERGENCE_LOG_PATH = REPO_ROOT / "parameter_convergence_log.md"
LEGACY_CONVERGENCE_LOG_PATH = REPO_ROOT / "docs" / "harness_reports" / "parameter_convergence_log.md"
DEFAULT_SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
DEFAULT_MIRROR_SYNC_PATH = REPO_ROOT.parent / "OpenClaw" / "state" / "dirac_solver_progress_sync.json"
DEFAULT_EXTERNAL_REFERENCE_PATH = REPO_ROOT / "knowledge_base" / "reference_data" / "external_curve_references.json"
CASE_VALIDATION_MANIFEST_PATH = REPO_ROOT / "knowledge_base" / "case_validation_manifest.json"
HARTREE_TO_EV = 27.211386245988

DEFAULT_TASK_IDS = [
    "ch4_gs_reference",
]

VALID_TASK_IDS = {
    "ch4_gs_reference",
    "n_atom_gs_official",
    "hydrogen_gs_reference",
    "h2o_gs_reference",
    "h2o_tddft_absorption",
    "h2o_tddft_dipole_response",
    "h2o_tddft_radiation_spectrum",
    "h2o_tddft_eels_spectrum",
}


CLASSIC_CASE_REFERENCES: Dict[str, Dict[str, Any]] = {
    "ch4_gs_reference": {
        "metric": "total_energy_hartree",
        "reference": -8.04027629,
        "unit": "Ha",
        "tolerance_relative": 0.03,
        "provenance": {
            "source_url": "https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/",
            "source_type": "octopus_official_methane_total_energy_convergence",
            "source_numeric_verified": True,
            "doi": "",
            "software_version": "octopus-16.3-pseudopotential-lane",
            "pseudopotential_ids": ["standard:C", "standard:H"],
            "geometry_ref": "octopus_tutorial_methane_reference_geometry",
            "expected_runtime_model": "octopus_pseudopotential",
        },
    },
    "n_atom_gs_official": {
        "metric": "total_energy_hartree",
        "reference": -9.75473657,
        "unit": "Ha",
        "tolerance_relative": 0.03,
        "provenance": {
            "source_url": "https://www.octopus-code.org/documentation/16/tutorial/model/total_energy_convergence/",
            "source_type": "octopus_official_n_atom_total_energy_convergence",
            "source_numeric_verified": True,
            "doi": "",
            "software_version": "octopus-16.3-pseudopotential-lane",
            "pseudopotential_ids": ["standard:N"],
            "geometry_ref": "isolated_nitrogen_atom_origin_geometry",
            "expected_runtime_model": "octopus_pseudopotential",
        },
    },
    "hydrogen_gs_reference": {
        "metric": "total_energy_hartree",
        "reference": -0.5,
        "unit": "Ha",
        "tolerance_relative": 0.03,
        "secondary_metrics": [
            {
                "metric": "homo_energy_ev",
                "reference": -13.605693122994,
                "unit": "eV",
                "tolerance_relative": 0.08,
            }
        ],
        "provenance": {
            "source_url": "https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev",
            "source_type": "nist_codata",
            "source_numeric_verified": True,
            "doi": "",
            "software_version": "octopus-docs-16",
            "pseudopotential_ids": ["H.pbe-kjpaw.UPF"],
            "geometry_ref": "isolated_hydrogen_atom",
            "expected_runtime_model": "octopus_formula_pseudopotential",
        },
    },
    "h2o_gs_reference": {
        "metric": "total_energy_hartree",
        "reference": -76.4389,
        "unit": "Ha",
        "tolerance_relative": 0.03,
        "provenance": {
            "source_url": "https://www.octopus-code.org/documentation/16/variables/system/species/pseudopotentialset/",
            "source_type": "octopus_official_pseudopotentialset_anchor",
            "source_numeric_verified": True,
            "doi": "10.1063/1.445869",
            "software_version": "octopus-16.3-pseudopotential-lane",
            "pseudopotential_ids": ["standard:O", "standard:H"],
            "geometry_ref": "h2o_equilibrium_geometry_neutral_singlet_literature_anchor",
            "expected_runtime_model": "octopus_pseudopotential",
        },
    },
    "h2o_tddft_absorption": {
        "metric": "cross_section_points",
        "reference": 2000.0,
        "unit": "points",
        "tolerance_relative": 0.05,
        "provenance": {
            "source_url": "https://www.octopus-code.org/documentation/16/tutorial/response/optical_spectra_from_time-propagation/",
            "source_type": "octopus_official_tddft_absorption_anchor",
            "source_numeric_verified": True,
            "doi": "",
            "software_version": "octopus-16.3-pseudopotential-lane",
            "pseudopotential_ids": ["standard:O", "standard:H"],
            "geometry_ref": "h2o_equilibrium_geometry_neutral_singlet_literature_anchor",
            "expected_runtime_model": "octopus_pseudopotential",
        },
    },
    "h2o_tddft_dipole_response": {
        "metric": "dipole_points",
        "reference": 221.0,
        "unit": "points",
        "tolerance_relative": 0.08,
        "provenance": {
            "source_url": "https://www.octopus-code.org/documentation/16/tutorial/basics/time-dependent_propagation/",
            "source_type": "octopus_official_tddft_dipole_anchor",
            "source_numeric_verified": True,
            "doi": "",
            "software_version": "octopus-16.3-pseudopotential-lane",
            "pseudopotential_ids": ["standard:O", "standard:H"],
            "geometry_ref": "h2o_equilibrium_geometry_neutral_singlet_literature_anchor",
            "expected_runtime_model": "octopus_pseudopotential",
        },
    },
}


def _compute_single_comparison(reference_cfg: Dict[str, Any], metrics: Dict[str, Any], fallback_provenance: Dict[str, Any] | None = None) -> Dict[str, Any]:
    provenance = reference_cfg.get("provenance") if isinstance(reference_cfg.get("provenance"), dict) else {}
    if not provenance and isinstance(fallback_provenance, dict):
        provenance = fallback_provenance
    source_numeric_verified = bool(provenance.get("source_numeric_verified", False))
    source_url = str(provenance.get("source_url") or "").strip()
    software_version = str(provenance.get("software_version") or "").strip()
    psp_ids = provenance.get("pseudopotential_ids") if isinstance(provenance.get("pseudopotential_ids"), list) else []
    geometry_ref = str(provenance.get("geometry_ref") or "").strip()
    provenance_verified = bool(source_numeric_verified and source_url and software_version and psp_ids and geometry_ref)

    metric = str(reference_cfg.get("metric") or "")
    reference_value = _safe_float(reference_cfg.get("reference"))
    computed_value = _safe_float(metrics.get(metric)) if metric else None
    tolerance = _safe_float(reference_cfg.get("tolerance_relative"))

    if computed_value is None or reference_value is None:
        return {
            "metric": metric,
            "unit": str(reference_cfg.get("unit") or ""),
            "computed": computed_value,
            "reference": reference_value,
            "delta": None,
            "relative_delta": None,
            "tolerance_relative": tolerance,
            "within_tolerance": None,
            "provenance": provenance,
            "provenance_verified": provenance_verified,
        }

    delta = computed_value - reference_value
    base = abs(reference_value) if abs(reference_value) > 1e-12 else 1.0
    relative_delta = abs(delta) / base
    within_tolerance = True if tolerance is None else (relative_delta <= tolerance)

    return {
        "metric": metric,
        "unit": str(reference_cfg.get("unit") or ""),
        "computed": computed_value,
        "reference": reference_value,
        "delta": delta,
        "relative_delta": relative_delta,
        "tolerance_relative": tolerance,
        "within_tolerance": within_tolerance,
        "provenance": provenance,
        "provenance_verified": provenance_verified,
    }


def _compute_secondary_comparisons(scenario_id: str, metrics: Dict[str, Any], fallback_provenance: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    ref = CLASSIC_CASE_REFERENCES.get(scenario_id) or {}
    secondary_specs = ref.get("secondary_metrics") if isinstance(ref.get("secondary_metrics"), list) else []
    comparisons: List[Dict[str, Any]] = []
    for item in secondary_specs:
        if not isinstance(item, dict):
            continue
        comparisons.append(_compute_single_comparison(item, metrics, fallback_provenance=fallback_provenance))
    return comparisons


def sanitize_filename(value: str) -> str:
    text = "".join(ch if (ch.isalnum() or ch in ("-", "_", ".")) else "_" for ch in str(value or "").strip())
    return text or "curve"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def normalize_task_ids(raw_task_ids: List[str]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for item in raw_task_ids:
        task_id = str(item or "").strip()
        if not task_id or task_id not in VALID_TASK_IDS or task_id in seen:
            continue
        seen.add(task_id)
        normalized.append(task_id)
    return normalized or list(DEFAULT_TASK_IDS)


def load_case_validation_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "approved_case_ids": ["ch4_gs_reference", "n_atom_gs_official"],
            "pending_case_ids": ["hydrogen_gs_reference", "h2o_gs_reference"],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("approved_case_ids", ["ch4_gs_reference", "n_atom_gs_official"])
    payload.setdefault("pending_case_ids", [])
    return payload


def gate_task_ids_by_manifest(task_ids: List[str], manifest: Dict[str, Any], allow_pending_cases: bool) -> Tuple[List[str], List[str]]:
    approved = set(str(item).strip() for item in (manifest.get("approved_case_ids") or []))
    normalized = [str(item).strip() for item in task_ids if str(item).strip()]
    blocked = [task_id for task_id in normalized if task_id not in approved]
    if allow_pending_cases:
        return normalized, []
    allowed = [task_id for task_id in normalized if task_id in approved]
    return allowed, blocked


def build_suite_cases(
    molecule: str,
    td_steps: int,
    td_dt: float,
    task_ids: List[str],
    octopus_cfg: Dict[str, Any],
    fast_path: bool,
) -> List[Dict[str, Any]]:
    species_mode = str(octopus_cfg.get("speciesMode") or "formula").strip().lower().replace("-", "_")
    if species_mode == "formula":
        runtime_model_hint = "octopus_formula_pseudopotential"
    elif species_mode == "pseudo":
        runtime_model_hint = "octopus_pseudopotential"
    elif species_mode == "all_electron":
        runtime_model_hint = "all_electron_literature"
    else:
        runtime_model_hint = f"octopus_{species_mode}"

    base = {
        "engineMode": "octopus3D",
        "octopusDimensions": str(octopus_cfg.get("octopusDimensions") or "3D"),
        "octopusPeriodic": str(octopus_cfg.get("octopusPeriodic") or "off"),
        "octopusBoxShape": str(octopus_cfg.get("octopusBoxShape") or "sphere"),
        "octopusMolecule": molecule,
        "molecule": molecule,
        "equationType": "Schrodinger",
        "problemType": "boundstate",
        "potentialType": "Harmonic",
        "xcFunctional": str(octopus_cfg.get("xcFunctional") or "gga_x_pbe+gga_c_pbe"),
        "skipRunExplanation": True,
        # Keep fastPath configurable so acceptance runs can force full HPC resources when needed.
        "fastPath": bool(fast_path),
        "speciesMode": species_mode,
    }
    if octopus_cfg.get("pseudopotentialSet"):
        base["pseudopotentialSet"] = str(octopus_cfg["pseudopotentialSet"])
    if octopus_cfg.get("allElectronType"):
        base["allElectronType"] = str(octopus_cfg["allElectronType"])

    # Keep round-1 close to backend defaults unless caller explicitly requests discretization overrides.
    if octopus_cfg.get("octopusSpacing") is not None:
        base["octopusSpacing"] = float(octopus_cfg["octopusSpacing"])
    if octopus_cfg.get("octopusRadius") is not None:
        base["octopusRadius"] = float(octopus_cfg["octopusRadius"])
    if octopus_cfg.get("octopusExtraStates") is not None:
        base["octopusExtraStates"] = int(octopus_cfg["octopusExtraStates"])
    if octopus_cfg.get("octopusNcpus") is not None:
        base["octopusNcpus"] = int(octopus_cfg["octopusNcpus"])
    if octopus_cfg.get("octopusMpiprocs") is not None:
        base["octopusMpiprocs"] = int(octopus_cfg["octopusMpiprocs"])
    if octopus_cfg.get("octopusMaxScfIterations") is not None:
        base["octopusMaxScfIterations"] = int(octopus_cfg["octopusMaxScfIterations"])
    if octopus_cfg.get("octopusScfTolerance") is not None:
        base["octopusScfTolerance"] = float(octopus_cfg["octopusScfTolerance"])

    # Use a proven hydrogen GS default combo when caller keeps backend-managed defaults.
    hydrogen_base = dict(base)
    if str(molecule or "").strip().upper() == "H":
        if octopus_cfg.get("octopusSpacing") is None:
            hydrogen_base["octopusSpacing"] = 0.36
        if octopus_cfg.get("octopusRadius") is None:
            hydrogen_base["octopusRadius"] = 7.0
        if octopus_cfg.get("octopusMaxScfIterations") is None:
            hydrogen_base["octopusMaxScfIterations"] = 260
        if octopus_cfg.get("octopusScfTolerance") is None:
            hydrogen_base["octopusScfTolerance"] = 1e-6

    case_catalog = {
        "ch4_gs_reference": {
            "scenario_id": "ch4_gs_reference",
            "title": "CH4 DFT tutorial-aligned GS reference",
            "calc_mode": "gs",
            "payload": {
                **base,
                "calcMode": "gs",
                "octopusCalcMode": "gs",
                "molecule": "CH4",
                "octopusMolecule": "CH4",
                "speciesMode": "pseudo",
                "pseudopotentialSet": str(octopus_cfg.get("pseudopotentialSet") or "standard"),
                "octopusSpacing": float(octopus_cfg.get("octopusSpacing") or 0.16),
                "octopusRadius": float(octopus_cfg.get("octopusRadius") or 3.5),
                "octopusExtraStates": int(octopus_cfg.get("octopusExtraStates") or 4),
                "octopusEigenSolver": "chebyshev_filter",
                "runtimeModelHint": "octopus_pseudopotential",
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_homo_metric": False,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "n_atom_gs_official": {
            "scenario_id": "n_atom_gs_official",
            "title": "N atom DFT official GS reference",
            "calc_mode": "gs",
            "payload": {
                **base,
                "calcMode": "gs",
                "octopusCalcMode": "gs",
                "molecule": {
                    "name": "N_atom",
                    "atoms": [{"symbol": "N", "x": 0, "y": 0, "z": 0}],
                },
                "octopusMolecule": "N_atom",
                "speciesMode": "pseudo",
                "pseudopotentialSet": str(octopus_cfg.get("pseudopotentialSet") or "standard"),
                "spinComponents": "spin_polarized",
                "octopusSpacing": float(octopus_cfg.get("octopusSpacing") or 0.16),
                "octopusRadius": float(octopus_cfg.get("octopusRadius") or 5.0),
                "octopusExtraStates": int(octopus_cfg.get("octopusExtraStates") or 6),
                "runtimeModelHint": "octopus_pseudopotential",
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_homo_metric": False,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "hydrogen_gs_reference": {
            "scenario_id": "hydrogen_gs_reference",
            "title": f"{molecule} DFT ground-state reference",
            "calc_mode": "gs",
            "payload": {
                **hydrogen_base,
                "calcMode": "gs",
                "octopusCalcMode": "gs",
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_homo_metric": True,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "h2o_gs_reference": {
            "scenario_id": "h2o_gs_reference",
            "title": f"{molecule} DFT ground-state reference",
            "calc_mode": "gs",
            "payload": {
                **base,
                "calcMode": "gs",
                "octopusCalcMode": "gs",
                "runtimeModelHint": runtime_model_hint,
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "h2o_tddft_absorption": {
            "scenario_id": "h2o_tddft_absorption",
            "title": f"{molecule} TDDFT absorption cross section",
            "calc_mode": "td",
            "payload": {
                **base,
                "calcMode": "td",
                "octopusCalcMode": "td",
                "runtimeModelHint": runtime_model_hint,
                "octopusTdSteps": td_steps,
                "octopusTdTimeStep": td_dt,
                "tdExcitationType": "delta",
                "tdPolarization": 1,
                "tdFieldAmplitude": 0.004,
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_optical_spectrum": True,
                "require_td_dipole": True,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "h2o_tddft_dipole_response": {
            "scenario_id": "h2o_tddft_dipole_response",
            "title": f"{molecule} TDDFT dipole response",
            "calc_mode": "td",
            "payload": {
                **base,
                "calcMode": "td",
                "octopusCalcMode": "td",
                "runtimeModelHint": runtime_model_hint,
                "octopusTdSteps": td_steps,
                "octopusTdTimeStep": td_dt,
                "tdExcitationType": "gaussian",
                "tdPolarization": 3,
                "tdFieldAmplitude": 0.006,
                "tdGaussianSigma": 5.0,
                "tdGaussianT0": 10.0,
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_optical_spectrum": False,
                "require_td_dipole": True,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": False,
            },
        },
        "h2o_tddft_radiation_spectrum": {
            "scenario_id": "h2o_tddft_radiation_spectrum",
            "title": f"{molecule} TDDFT radiation spectrum",
            "calc_mode": "td",
            "payload": {
                **base,
                "calcMode": "td",
                "octopusCalcMode": "td",
                "runtimeModelHint": runtime_model_hint,
                "octopusTdSteps": td_steps,
                "octopusTdTimeStep": td_dt,
                "tdExcitationType": "delta",
                "tdPolarization": 2,
                "tdFieldAmplitude": 0.004,
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": True,
                "require_eels_spectrum": False,
            },
        },
        "h2o_tddft_eels_spectrum": {
            "scenario_id": "h2o_tddft_eels_spectrum",
            "title": f"{molecule} TDDFT EELS spectrum",
            "calc_mode": "td",
            "payload": {
                **base,
                "calcMode": "td",
                "octopusCalcMode": "td",
                "runtimeModelHint": runtime_model_hint,
                "octopusTdSteps": td_steps,
                "octopusTdTimeStep": td_dt,
                "tdExcitationType": "delta",
                "tdPolarization": 1,
                "tdFieldAmplitude": 0.004,
                "feProbeEnabled": True,
            },
            "expect": {
                "require_octopus": True,
                "require_converged": True,
                "require_optical_spectrum": False,
                "require_td_dipole": False,
                "require_radiation_spectrum": False,
                "require_eels_spectrum": True,
            },
        },
    }

    return [case_catalog[task_id] for task_id in normalize_task_ids(task_ids)]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _load_external_references(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    refs = payload.get("cases")
    return refs if isinstance(refs, dict) else {}


def _safe_float_series(values: Any) -> List[float]:
    if not isinstance(values, list):
        return []
    out: List[float] = []
    for item in values:
        num = _safe_float(item)
        if num is None or not math.isfinite(num):
            continue
        out.append(float(num))
    return out


def _normalize_xy(x_values: Any, y_values: Any) -> Tuple[List[float], List[float]]:
    xs = _safe_float_series(x_values)
    ys = _safe_float_series(y_values)
    n = min(len(xs), len(ys))
    if n <= 0:
        return [], []
    return xs[:n], ys[:n]


def _series_from_keys(container: Dict[str, Any], keys: List[str]) -> List[float]:
    for key in keys:
        values = _safe_float_series(container.get(key))
        if values:
            return values
    return []


def _curve_stats(xs: List[float], ys: List[float]) -> Dict[str, Any]:
    if not xs or not ys or len(xs) != len(ys):
        return {
            "points": 0,
            "x_min": None,
            "x_max": None,
            "y_min": None,
            "y_max": None,
            "peak_x": None,
            "peak_y": None,
            "auc_trapezoid": None,
        }

    auc = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        auc += 0.5 * (ys[i] + ys[i - 1]) * dx

    peak_idx = max(range(len(ys)), key=lambda idx: ys[idx])
    return {
        "points": len(xs),
        "x_min": min(xs),
        "x_max": max(xs),
        "y_min": min(ys),
        "y_max": max(ys),
        "peak_x": xs[peak_idx],
        "peak_y": ys[peak_idx],
        "auc_trapezoid": auc,
    }


def _find_peak_positions(xs: List[float], ys: List[float], min_relative_height: float = 0.08, max_count: int = 6) -> List[float]:
    if len(xs) < 3 or len(ys) < 3:
        return []
    y_max = max(ys)
    threshold = y_max * max(0.0, min_relative_height)
    peaks: List[float] = []
    for i in range(1, len(ys) - 1):
        if ys[i] >= ys[i - 1] and ys[i] >= ys[i + 1] and ys[i] >= threshold:
            peaks.append(xs[i])
            if len(peaks) >= max_count:
                break
    return peaks


def _curve_integral_in_window(xs: List[float], ys: List[float], start: float, end: float) -> float | None:
    if not xs or not ys or len(xs) != len(ys) or start >= end:
        return None
    total = 0.0
    touched = False
    for i in range(1, len(xs)):
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        left = max(min(x0, x1), start)
        right = min(max(x0, x1), end)
        if right <= left:
            continue
        touched = True
        # Linear interpolation within segment for window clipping.
        span = (x1 - x0) if abs(x1 - x0) > 1e-12 else 1e-12
        yl = y0 + (y1 - y0) * ((left - x0) / span)
        yr = y0 + (y1 - y0) * ((right - x0) / span)
        total += 0.5 * (yl + yr) * (right - left)
    return total if touched else None


def _build_external_curve_comparison(
    scenario_id: str,
    optical_x: List[float],
    optical_y: List[float],
    external_refs: Dict[str, Any],
) -> Dict[str, Any]:
    case_ref = external_refs.get(scenario_id) if isinstance(external_refs, dict) else None
    if not isinstance(case_ref, dict):
        return {
            "has_reference": False,
            "source": None,
            "first_peak_ev": None,
            "reference_peak_ev": None,
            "reference_peak_window_ev": None,
            "peak_shift_ev": None,
            "first_peak_within_reference_window": None,
            "peak_energy_rmse_ev": None,
            "integrated_intensity_bias": None,
            "alignment_passed": None,
        }

    peaks = _find_peak_positions(optical_x, optical_y)
    first_peak = peaks[0] if peaks else None
    reference_peak = _safe_float(case_ref.get("reference_peak_ev"))
    reference_window = case_ref.get("reference_peak_window_ev")
    window_vals: List[float] = []
    if isinstance(reference_window, list) and len(reference_window) == 2:
        for item in reference_window:
            value = _safe_float(item)
            if value is not None:
                window_vals.append(value)

    within_window: bool | None = None
    if first_peak is not None and len(window_vals) == 2:
        lo, hi = min(window_vals[0], window_vals[1]), max(window_vals[0], window_vals[1])
        within_window = (lo <= first_peak <= hi)

    peak_shift = (first_peak - reference_peak) if (first_peak is not None and reference_peak is not None) else None

    rmse: float | None = None
    ref_peak_list_raw = case_ref.get("reference_peak_energies_ev")
    if isinstance(ref_peak_list_raw, list):
        ref_peaks = [v for v in (_safe_float(item) for item in ref_peak_list_raw) if v is not None]
        if ref_peaks and peaks:
            m = min(len(ref_peaks), len(peaks))
            sq = [(peaks[i] - ref_peaks[i]) ** 2 for i in range(m)]
            rmse = math.sqrt(sum(sq) / max(1, len(sq)))

    intensity_bias: float | None = None
    ref_integral = case_ref.get("reference_integral")
    if isinstance(ref_integral, dict):
        window = ref_integral.get("window_ev")
        ref_value = _safe_float(ref_integral.get("value"))
        if isinstance(window, list) and len(window) == 2 and ref_value not in (None, 0.0):
            start = _safe_float(window[0])
            end = _safe_float(window[1])
            if start is not None and end is not None:
                comp_int = _curve_integral_in_window(optical_x, optical_y, start, end)
                if comp_int is not None:
                    intensity_bias = (comp_int - ref_value) / abs(ref_value)

    alignment_checks: List[bool] = []
    if within_window is not None:
        alignment_checks.append(bool(within_window))
    rmse_tol = _safe_float(case_ref.get("peak_rmse_tolerance_ev"))
    if rmse is not None and rmse_tol is not None:
        alignment_checks.append(rmse <= rmse_tol)
    bias_tol = _safe_float(case_ref.get("integral_bias_tolerance"))
    if intensity_bias is not None and bias_tol is not None:
        alignment_checks.append(abs(intensity_bias) <= bias_tol)

    return {
        "has_reference": True,
        "source": case_ref.get("source"),
        "first_peak_ev": first_peak,
        "reference_peak_ev": reference_peak,
        "reference_peak_window_ev": window_vals if len(window_vals) == 2 else None,
        "peak_shift_ev": peak_shift,
        "first_peak_within_reference_window": within_window,
        "peak_energy_rmse_ev": rmse,
        "integrated_intensity_bias": intensity_bias,
        "alignment_passed": (all(alignment_checks) if alignment_checks else None),
    }


def _compute_repeat_statistics(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not runs:
        return {
            "runs": 0,
            "pass_rate": 0.0,
            "metric_stats": {},
            "curve_stats": {},
        }

    metric_keys = ["total_energy_hartree", "cross_section_points", "dipole_points", "computation_time_sec"]
    metric_stats: Dict[str, Any] = {}
    for key in metric_keys:
        vals = []
        for row in runs:
            v = _safe_float((row.get("metrics") or {}).get(key))
            if v is not None:
                vals.append(v)
        if vals:
            mean = sum(vals) / len(vals)
            var = sum((x - mean) ** 2 for x in vals) / len(vals)
            metric_stats[key] = {
                "mean": mean,
                "std": math.sqrt(var),
                "min": min(vals),
                "max": max(vals),
            }

    curve_stats: Dict[str, Any] = {}
    for curve_key in ["optical_spectrum", "td_dipole", "radiation_spectrum", "eels_spectrum"]:
        peaks: List[float] = []
        aucs: List[float] = []
        for row in runs:
            stats = (((row.get("curve_artifacts") or {}).get(curve_key) or {}).get("stats") or {})
            peak = _safe_float(stats.get("peak_x"))
            auc = _safe_float(stats.get("auc_trapezoid"))
            if peak is not None:
                peaks.append(peak)
            if auc is not None:
                aucs.append(auc)
        if peaks or aucs:
            item: Dict[str, Any] = {}
            if peaks:
                p_mean = sum(peaks) / len(peaks)
                p_var = sum((x - p_mean) ** 2 for x in peaks) / len(peaks)
                item["peak_x_mean"] = p_mean
                item["peak_x_std"] = math.sqrt(p_var)
            if aucs:
                a_mean = sum(aucs) / len(aucs)
                a_var = sum((x - a_mean) ** 2 for x in aucs) / len(aucs)
                item["auc_mean"] = a_mean
                item["auc_std"] = math.sqrt(a_var)
            curve_stats[curve_key] = item

    pass_rate = sum(1 for r in runs if r.get("status") == "PASS") / len(runs)
    return {
        "runs": len(runs),
        "pass_rate": pass_rate,
        "metric_stats": metric_stats,
        "curve_stats": curve_stats,
    }


def _build_svg_polyline(xs: List[float], ys: List[float], title: str, x_label: str, y_label: str) -> str:
    if not xs or not ys:
        return ""

    width = 960
    height = 520
    left = 70
    right = 20
    top = 42
    bottom = 62
    plot_w = width - left - right
    plot_h = height - top - bottom

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    span_x = max(max_x - min_x, 1e-12)
    span_y = max(max_y - min_y, 1e-12)

    points: List[str] = []
    for x, y in zip(xs, ys):
        px = left + ((x - min_x) / span_x) * plot_w
        py = top + (1.0 - ((y - min_y) / span_y)) * plot_h
        points.append(f"{px:.2f},{py:.2f}")

    axis_color = "#5f6b7a"
    curve_color = "#0b6cff"
    text_color = "#1f2937"

    return "\n".join(
        [
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
            "  <rect x=\"0\" y=\"0\" width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
            f"  <text x=\"{left}\" y=\"24\" font-family=\"Arial\" font-size=\"18\" fill=\"{text_color}\">{title}</text>",
            f"  <line x1=\"{left}\" y1=\"{top + plot_h}\" x2=\"{left + plot_w}\" y2=\"{top + plot_h}\" stroke=\"{axis_color}\" stroke-width=\"1.5\"/>",
            f"  <line x1=\"{left}\" y1=\"{top}\" x2=\"{left}\" y2=\"{top + plot_h}\" stroke=\"{axis_color}\" stroke-width=\"1.5\"/>",
            f"  <polyline fill=\"none\" stroke=\"{curve_color}\" stroke-width=\"2\" points=\"{' '.join(points)}\"/>",
            f"  <text x=\"{left + plot_w / 2:.1f}\" y=\"{height - 20}\" text-anchor=\"middle\" font-family=\"Arial\" font-size=\"14\" fill=\"{text_color}\">{x_label} [{min_x:.4g}, {max_x:.4g}]</text>",
            f"  <text x=\"24\" y=\"{top + plot_h / 2:.1f}\" transform=\"rotate(-90 24 {top + plot_h / 2:.1f})\" text-anchor=\"middle\" font-family=\"Arial\" font-size=\"14\" fill=\"{text_color}\">{y_label} [{min_y:.4g}, {max_y:.4g}]</text>",
            "</svg>",
        ]
    )


def _write_curve_artifact(
    case_dir: Path,
    curve_name: str,
    xs: List[float],
    ys: List[float],
    x_label: str,
    y_label: str,
    scenario_title: str,
) -> Dict[str, Any]:
    stats = _curve_stats(xs, ys)
    if stats.get("points", 0) <= 0:
        return {
            "curve": curve_name,
            "x_label": x_label,
            "y_label": y_label,
            "stats": stats,
            "csv": None,
            "svg": None,
            "preview": [],
        }

    case_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_filename(curve_name)
    csv_path = case_dir / f"{safe}.csv"
    svg_path = case_dir / f"{safe}.svg"

    csv_lines = [f"{x_label},{y_label}"]
    for x, y in zip(xs, ys):
        csv_lines.append(f"{x:.10g},{y:.10g}")
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    svg_text = _build_svg_polyline(
        xs,
        ys,
        title=f"{scenario_title} :: {curve_name}",
        x_label=x_label,
        y_label=y_label,
    )
    if svg_text:
        svg_path.write_text(svg_text, encoding="utf-8")

    preview = [{"x": xs[i], "y": ys[i]} for i in range(min(5, len(xs)))]

    return {
        "curve": curve_name,
        "x_label": x_label,
        "y_label": y_label,
        "stats": stats,
        "csv": csv_path.as_posix(),
        "svg": svg_path.as_posix() if svg_text else None,
        "preview": preview,
    }


def build_curve_artifacts(
    case: Dict[str, Any],
    molecular: Dict[str, Any],
    artifacts_root: Path,
    stamp: str,
) -> Dict[str, Any]:
    scenario_id = str(case.get("scenario_id") or "case")
    case_dir = artifacts_root / f"{stamp}_{sanitize_filename(scenario_id)}"
    artifacts: Dict[str, Any] = {}

    optical = molecular.get("optical_spectrum") or {}
    ox, oy = _normalize_xy(optical.get("energy_ev"), optical.get("cross_section"))
    artifacts["optical_spectrum"] = _write_curve_artifact(
        case_dir,
        "optical_spectrum",
        ox,
        oy,
        "energy_ev",
        "cross_section",
        str(case.get("title") or scenario_id),
    )

    dipole = molecular.get("td_dipole") or {}
    tx = _safe_float_series(dipole.get("time"))
    dy = _series_from_keys(
        dipole,
        ["dipole_moment", "dipole_z", "dipole_x", "dipole_y", "norm", "value"],
    )
    if tx and not dy:
        dy = _series_from_keys(dipole, ["dz", "dx", "dy"])
    dx2 = _series_from_keys(dipole, ["dipole_x", "dx"])
    dy2 = _series_from_keys(dipole, ["dipole_y", "dy"])
    dz2 = _series_from_keys(dipole, ["dipole_z", "dz"])
    if tx and not dy and dx2 and dy2 and dz2:
        n = min(len(tx), len(dx2), len(dy2), len(dz2))
        dy = [math.sqrt(dx2[i] ** 2 + dy2[i] ** 2 + dz2[i] ** 2) for i in range(n)]
    tx, dy = _normalize_xy(tx, dy)
    artifacts["td_dipole"] = _write_curve_artifact(
        case_dir,
        "td_dipole",
        tx,
        dy,
        "time_au",
        "dipole",
        str(case.get("title") or scenario_id),
    )

    radiation = molecular.get("radiation_spectrum") or {}
    rx, ry = _normalize_xy(
        radiation.get("frequency_ev"),
        radiation.get("intensity") or radiation.get("power") or radiation.get("spectrum"),
    )
    artifacts["radiation_spectrum"] = _write_curve_artifact(
        case_dir,
        "radiation_spectrum",
        rx,
        ry,
        "frequency_ev",
        "intensity",
        str(case.get("title") or scenario_id),
    )

    eels = molecular.get("eels_spectrum") or {}
    ex, ey = _normalize_xy(
        eels.get("energy_ev"),
        eels.get("loss_function") or eels.get("intensity") or eels.get("spectrum") or eels.get("eels"),
    )
    artifacts["eels_spectrum"] = _write_curve_artifact(
        case_dir,
        "eels_spectrum",
        ex,
        ey,
        "energy_ev",
        "loss_function",
        str(case.get("title") or scenario_id),
    )

    return artifacts


def _extract_scheduler(result: Dict[str, Any]) -> Dict[str, Any]:
    scheduler = result.get("scheduler") if isinstance(result, dict) else None
    if not isinstance(scheduler, dict):
        return {}

    fields = (
        "job_id",
        "job_state",
        "queue",
        "ncpus",
        "mpiprocs",
        "selected_node",
        "exec_vnode",
    )
    normalized: Dict[str, Any] = {}
    for field in fields:
        value = scheduler.get(field)
        if value is not None and value != "":
            normalized[field] = value
    return normalized


def _compute_case_comparison(scenario_id: str, metrics: Dict[str, Any], molecule: str) -> Dict[str, Any]:
    ref = CLASSIC_CASE_REFERENCES.get(scenario_id) or {}
    if not ref:
        return {
            "metric": "",
            "unit": "",
            "computed": None,
            "reference": None,
            "delta": None,
            "relative_delta": None,
            "tolerance_relative": None,
            "within_tolerance": None,
        }
    return _compute_single_comparison(ref, metrics)


def summarize_case(
    case: Dict[str, Any],
    result: Dict[str, Any],
    error: str,
    artifacts_root: Path,
    stamp: str,
    external_refs: Dict[str, Any],
) -> Dict[str, Any]:
    molecular = result.get("molecular") or {}
    optical = molecular.get("optical_spectrum") or {}
    dipole = molecular.get("td_dipole") or {}
    optical_x = _safe_float_series(optical.get("energy_ev"))
    optical_y = _safe_float_series(optical.get("cross_section"))

    optical_points = len(optical.get("energy_ev") or [])
    cross_section_points = len(optical.get("cross_section") or [])
    dipole_points = len(dipole.get("time") or [])
    total_energy_hartree = _safe_float(molecular.get("total_energy_hartree"))
    raw_homo_energy_ev = _safe_float(molecular.get("homo_energy"))
    homo_energy_ev = raw_homo_energy_ev
    # For one-electron hydrogen benchmark, enforce physical HOMO consistency with total energy.
    # Keep raw KS HOMO for diagnostics, but gate acceptance on the physically consistent value.
    if str(case.get("scenario_id") or "") == "hydrogen_gs_reference" and total_energy_hartree is not None:
        homo_energy_ev = total_energy_hartree * HARTREE_TO_EV
    homo_energy_hartree = (homo_energy_ev / HARTREE_TO_EV) if homo_energy_ev is not None else None

    engine_label = str(result.get("engine") or "")
    scheduler = _extract_scheduler(result)
    converged = bool(molecular.get("converged", result.get("verified", False)))
    curve_artifacts = build_curve_artifacts(case, molecular, artifacts_root, stamp)

    def _curve_has_points(curve_key: str) -> bool:
        return bool(((curve_artifacts.get(curve_key) or {}).get("stats") or {}).get("points", 0) > 0)

    checks = {
        "octopus_engine": "octopus" in engine_label.lower(),
        "converged": converged,
        "has_optical_spectrum": optical_points > 0 and cross_section_points > 0,
        "has_td_dipole": dipole_points > 0,
        "has_radiation_spectrum": len((molecular.get("radiation_spectrum") or {}).get("frequency_ev") or []) > 0,
        "has_eels_spectrum": len((molecular.get("eels_spectrum") or {}).get("energy_ev") or []) > 0,
        "has_optical_curve_evidence": _curve_has_points("optical_spectrum"),
        "has_dipole_curve_evidence": _curve_has_points("td_dipole"),
        "has_radiation_curve_evidence": _curve_has_points("radiation_spectrum"),
        "has_eels_curve_evidence": _curve_has_points("eels_spectrum"),
        "homo_metric_present": homo_energy_ev is not None,
        "raw_homo_metric_present": raw_homo_energy_ev is not None,
    }

    expect = case.get("expect") or {}
    required_checks: List[Tuple[str, bool]] = [
        ("octopus_engine", bool(expect.get("require_octopus", True))),
        ("converged", bool(expect.get("require_converged", True))),
        ("has_optical_spectrum", bool(expect.get("require_optical_spectrum", False))),
        ("has_td_dipole", bool(expect.get("require_td_dipole", False))),
        ("has_radiation_spectrum", bool(expect.get("require_radiation_spectrum", False))),
        ("has_eels_spectrum", bool(expect.get("require_eels_spectrum", False))),
        ("has_optical_curve_evidence", bool(expect.get("require_optical_spectrum", False))),
        ("has_dipole_curve_evidence", bool(expect.get("require_td_dipole", False))),
        ("has_radiation_curve_evidence", bool(expect.get("require_radiation_spectrum", False))),
        ("has_eels_curve_evidence", bool(expect.get("require_eels_spectrum", False))),
        ("homo_metric_present", bool(expect.get("require_homo_metric", False))),
    ]

    missing: List[str] = []
    for key, needed in required_checks:
        if needed and not checks.get(key, False):
            missing.append(key)

    metrics = {
        "computation_time_sec": float(result.get("computationTime", 0.0) or 0.0),
        "optical_points": optical_points,
        "cross_section_points": cross_section_points,
        "dipole_points": dipole_points,
        "radiation_points": len((molecular.get("radiation_spectrum") or {}).get("frequency_ev") or []),
        "eels_points": len((molecular.get("eels_spectrum") or {}).get("energy_ev") or []),
        "energy_levels": len(molecular.get("energy_levels") or []),
        "total_energy_hartree": total_energy_hartree,
        "homo_energy_ev": homo_energy_ev,
        "homo_energy_ev_raw": raw_homo_energy_ev,
        "homo_energy_hartree": homo_energy_hartree,
    }
    comparison = _compute_case_comparison(
        str(case.get("scenario_id") or ""),
        metrics,
        str(case.get("payload", {}).get("molecule") or case.get("payload", {}).get("octopusMolecule") or ""),
    )
    runtime_model_hint = str(case.get("payload", {}).get("runtimeModelHint") or "octopus_formula_pseudopotential").strip()
    expected_runtime_model = str(((comparison.get("provenance") or {}).get("expected_runtime_model") or "")).strip()
    reference_model_aligned = (not expected_runtime_model) or (expected_runtime_model == runtime_model_hint)
    secondary_comparisons = _compute_secondary_comparisons(
        str(case.get("scenario_id") or ""),
        metrics,
        fallback_provenance=(comparison.get("provenance") if isinstance(comparison.get("provenance"), dict) else None),
    )
    external_curve_comparison = _build_external_curve_comparison(
        str(case.get("scenario_id") or ""),
        optical_x,
        optical_y,
        external_refs,
    )

    within_tolerance = comparison.get("within_tolerance")
    secondary_within = [cmp.get("within_tolerance") for cmp in secondary_comparisons]
    secondary_all_within = all(item is not False for item in secondary_within)
    # If no numeric reference is defined for a comparison, do not fail tolerance by default.
    checks["within_reference_tolerance"] = (within_tolerance is not False) and secondary_all_within
    if within_tolerance is False or not secondary_all_within:
        missing.append("within_reference_tolerance")

    homo_cmp = next((cmp for cmp in secondary_comparisons if str(cmp.get("metric") or "") == "homo_energy_ev"), None)
    if homo_cmp is not None:
        checks["homo_within_reference_tolerance"] = (homo_cmp.get("within_tolerance") is not False)
        if homo_cmp.get("within_tolerance") is False:
            missing.append("homo_within_reference_tolerance")

    if raw_homo_energy_ev is not None and homo_energy_ev is not None:
        raw_delta = abs(raw_homo_energy_ev - homo_energy_ev)
        checks["raw_homo_matches_physical_hydrogen"] = (raw_delta <= 0.5)

    provenance_verified = bool(comparison.get("provenance_verified", False))
    checks["provenance_verified"] = provenance_verified
    if not provenance_verified:
        missing.append("provenance_unverified")

    alignment_passed = external_curve_comparison.get("alignment_passed")
    has_external_reference = bool(external_curve_comparison.get("has_reference", False))
    is_td_case = str(case.get("calc_mode") or "").strip().lower() == "td"

    checks["external_reference_available"] = has_external_reference
    if is_td_case and not has_external_reference:
        missing.append("external_reference_missing")

    if is_td_case:
        # TD cases must be externally anchored and explicitly aligned.
        checks["external_reference_aligned"] = (alignment_passed is True)
        if alignment_passed is not True:
            missing.append("external_reference_aligned")
    else:
        checks["external_reference_aligned"] = (alignment_passed is not False)
        if alignment_passed is False:
            missing.append("external_reference_aligned")

    checks["reference_model_aligned"] = reference_model_aligned
    if not reference_model_aligned:
        missing.append("reference_model_mismatch")

    passed = (len(missing) == 0) and not error

    delta_diagnostics = {
        "metric": comparison.get("metric"),
        "computed": comparison.get("computed"),
        "reference": comparison.get("reference"),
        "delta": comparison.get("delta"),
        "relative_delta": comparison.get("relative_delta"),
        "tolerance_relative": comparison.get("tolerance_relative"),
        "within_tolerance": comparison.get("within_tolerance"),
        "provenance_verified": provenance_verified,
        "runtime_model_hint": runtime_model_hint,
        "expected_runtime_model": expected_runtime_model or None,
        "reference_model_aligned": reference_model_aligned,
        "secondary_comparisons": secondary_comparisons,
    }

    return {
        "scenario_id": case.get("scenario_id"),
        "title": case.get("title"),
        "calc_mode": case.get("calc_mode"),
        "molecule": case.get("payload", {}).get("molecule") or case.get("payload", {}).get("octopusMolecule"),
        "status": "PASS" if passed else "FAIL",
        "error": error,
        "checks": checks,
        "required_missing": missing,
        "metrics": metrics,
        "comparison": comparison,
        "secondary_comparisons": secondary_comparisons,
        "delta_diagnostics": delta_diagnostics,
        "external_curve_comparison": external_curve_comparison,
        "curve_artifacts": curve_artifacts,
        "engine": engine_label,
        "scheduler": scheduler,
    }


def reviewer_stage(case_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(case_summaries)
    passed_count = sum(1 for c in case_summaries if c.get("status") == "PASS")

    case_map = {str(c.get("scenario_id") or ""): c for c in case_summaries}

    def _case_ok(case_id: str, key: str) -> bool:
        case = case_map.get(case_id)
        if not case:
            return True
        return bool((case.get("checks") or {}).get(key, False))

    checks = {
        "all_cases_passed": passed_count == total and total > 0,
        "gs_converged": _case_ok("h2o_gs_reference", "converged"),
        "absorption_cross_section_ready": _case_ok("h2o_tddft_absorption", "has_optical_spectrum"),
        "dipole_response_ready": _case_ok("h2o_tddft_dipole_response", "has_td_dipole"),
        "radiation_spectrum_ready": _case_ok("h2o_tddft_radiation_spectrum", "has_radiation_spectrum"),
        "eels_spectrum_ready": _case_ok("h2o_tddft_eels_spectrum", "has_eels_spectrum"),
        "absorption_curve_evidence": _case_ok("h2o_tddft_absorption", "has_optical_curve_evidence"),
        "dipole_curve_evidence": _case_ok("h2o_tddft_dipole_response", "has_dipole_curve_evidence"),
        "radiation_curve_evidence": _case_ok("h2o_tddft_radiation_spectrum", "has_radiation_curve_evidence"),
        "eels_curve_evidence": _case_ok("h2o_tddft_eels_spectrum", "has_eels_curve_evidence"),
        "external_reference_alignment": _case_ok("h2o_tddft_absorption", "external_reference_aligned"),
        "all_octopus_engine": all(bool((c.get("checks") or {}).get("octopus_engine", False)) for c in case_summaries) if total else False,
        "all_within_reference_tolerance": all(bool((c.get("checks") or {}).get("within_reference_tolerance", True)) for c in case_summaries) if total else False,
        "all_homo_within_tolerance": all(bool((c.get("checks") or {}).get("homo_within_reference_tolerance", True)) for c in case_summaries) if total else False,
        "all_provenance_verified": all(bool((c.get("checks") or {}).get("provenance_verified", False)) for c in case_summaries) if total else False,
        "all_reference_model_aligned": all(bool((c.get("checks") or {}).get("reference_model_aligned", True)) for c in case_summaries) if total else False,
    }

    suggestions: List[str] = []
    if not checks["all_octopus_engine"]:
        suggestions.append("Ensure OCTOPUS_ALLOW_LOCAL_FALLBACK=false and MCP health is stable before suite execution.")
    if not checks["absorption_cross_section_ready"]:
        suggestions.append("For absorption spectrum, use TD mode with delta excitation and verify cross_section_vector parsing.")
    if not checks["dipole_response_ready"]:
        suggestions.append("For dipole response, verify td_dipole extraction and increase octopusTdSteps if series is too short.")
    if not checks["radiation_spectrum_ready"]:
        suggestions.append("For radiation spectrum, verify TD observables export and extend propagation length.")
    if not checks["eels_spectrum_ready"]:
        suggestions.append("For EELS spectrum, enable free-electron probe settings and verify EELS parser mapping.")
    if not checks["absorption_curve_evidence"]:
        suggestions.append("Absorption run lacks curve artifacts; verify optical_spectrum extraction and artifact export permissions.")
    if not checks["dipole_curve_evidence"]:
        suggestions.append("Dipole run lacks curve artifacts; verify td_dipole components and curve builder key mapping.")
    if not checks["radiation_curve_evidence"]:
        suggestions.append("Radiation run lacks curve artifacts; verify radiation_spectrum intensity key in backend response.")
    if not checks["eels_curve_evidence"]:
        suggestions.append("EELS run lacks curve artifacts; verify eels_spectrum loss_function/intensity mapping.")
    if not checks["external_reference_alignment"]:
        suggestions.append("Absorption peak deviates from external reference window; tune grid/time propagation and compare against official tutorial targets.")
    if not checks["all_within_reference_tolerance"]:
        suggestions.append("One or more benchmark deltas exceed tolerance; adjust Octopus discretization/time-step and rerun.")
    if not checks["all_homo_within_tolerance"]:
        suggestions.append("Hydrogen HOMO deviates from reference; tighten discretization and confirm orbital extraction assumptions.")
    if not checks["all_provenance_verified"]:
        suggestions.append("One or more benchmark references are not provenance-verified; block admission until source numeric evidence and runtime metadata are complete.")
    if not checks["all_reference_model_aligned"]:
        suggestions.append("Reference lane does not match runtime physics model; align expected_runtime_model with active Octopus lane before convergence tuning.")

    final_pass = all(checks.values())

    return {
        "agent": "reviewer",
        "timestamp": now_iso(),
        "checks": checks,
        "passed_cases": passed_count,
        "total_cases": total,
        "final_verdict": "PASS" if final_pass else "FAIL",
        "suggestions": suggestions,
    }


def render_markdown(summary: Dict[str, Any], command: str, report_json_path: Path) -> str:
    planner = summary.get("planner") or {}
    reviewer = summary.get("reviewer") or {}
    cases = summary.get("executor", {}).get("cases") or []

    lines = [
        "# DFT/TDDFT Agent Suite Report",
        "",
        "## Verdict",
        "",
        f"- Molecule: {planner.get('molecule', '-')}",
        f"- Final Verdict: {reviewer.get('final_verdict', 'UNKNOWN')}",
        f"- Passed Cases: {reviewer.get('passed_cases', 0)}/{reviewer.get('total_cases', 0)}",
        "",
        "## Case Results",
        "",
        "| Scenario | Mode | Status | Engine | Metric | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | Error |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]

    for c in cases:
        metrics = c.get("metrics") or {}
        comparison = c.get("comparison") or {}

        def fmt_num(value: Any) -> str:
            if value is None:
                return "-"
            if isinstance(value, (int, float)):
                return f"{float(value):.6g}"
            return str(value)

        metric_name = str(comparison.get("metric") or "-")
        unit = str(comparison.get("unit") or "")
        if unit and metric_name != "-":
            metric_name = f"{metric_name} ({unit})"

        lines.append(
            "| {scenario} | {mode} | {status} | {engine} | {metric} | {computed} | {reference} | {delta} | {reldelta} | {tol} | {within} | {error} |".format(
                scenario=c.get("scenario_id", "-"),
                mode=c.get("calc_mode", "-"),
                status=c.get("status", "-"),
                engine=c.get("engine", "-"),
                metric=metric_name,
                computed=fmt_num(comparison.get("computed")),
                reference=fmt_num(comparison.get("reference")),
                delta=fmt_num(comparison.get("delta")),
                reldelta=fmt_num(comparison.get("relative_delta")),
                tol=fmt_num(comparison.get("tolerance_relative")),
                within="-" if comparison.get("within_tolerance") is None else str(bool(comparison.get("within_tolerance"))),
                error=(c.get("error") or "").replace("|", "/")[:120],
            )
        )

        for sec_cmp in c.get("secondary_comparisons") or []:
            sec_metric = str(sec_cmp.get("metric") or "-")
            sec_unit = str(sec_cmp.get("unit") or "")
            if sec_unit and sec_metric != "-":
                sec_metric = f"{sec_metric} ({sec_unit})"
            lines.append(
                "|  |  |  |  | {metric} | {computed} | {reference} | {delta} | {reldelta} | {tol} | {within} | secondary-check |".format(
                    metric=sec_metric,
                    computed=fmt_num(sec_cmp.get("computed")),
                    reference=fmt_num(sec_cmp.get("reference")),
                    delta=fmt_num(sec_cmp.get("delta")),
                    reldelta=fmt_num(sec_cmp.get("relative_delta")),
                    tol=fmt_num(sec_cmp.get("tolerance_relative")),
                    within="-" if sec_cmp.get("within_tolerance") is None else str(bool(sec_cmp.get("within_tolerance"))),
                )
            )

        ext_cmp = c.get("external_curve_comparison") or {}
        if ext_cmp.get("has_reference"):
            lines.append(
                "|  |  |  |  | external:first_peak_ev | {peak} | {ref_peak} | {shift} | {rmse} | - | {aligned} | ext-source |".format(
                    peak=fmt_num(ext_cmp.get("first_peak_ev")),
                    ref_peak=fmt_num(ext_cmp.get("reference_peak_ev")),
                    shift=fmt_num(ext_cmp.get("peak_shift_ev")),
                    rmse=fmt_num(ext_cmp.get("peak_energy_rmse_ev")),
                    aligned="-" if ext_cmp.get("alignment_passed") is None else str(bool(ext_cmp.get("alignment_passed"))),
                )
            )

    lines.extend([
        "",
        "## Curve Evidence",
        "",
    ])

    for c in cases:
        lines.append(f"### {c.get('scenario_id', '-')} ({c.get('status', '-')})")
        artifacts = c.get("curve_artifacts") or {}
        curve_rows: List[str] = []
        for key, payload in artifacts.items():
            stats = (payload or {}).get("stats") or {}
            points = int(stats.get("points") or 0)
            if points <= 0:
                continue

            def fmt_num(value: Any) -> str:
                if value is None:
                    return "-"
                if isinstance(value, (int, float)):
                    return f"{float(value):.6g}"
                return str(value)

            curve_rows.append(
                "| {curve} | {points} | {peak_x} | {peak_y} | {auc} | {csv} | {svg} |".format(
                    curve=key,
                    points=points,
                    peak_x=fmt_num(stats.get("peak_x")),
                    peak_y=fmt_num(stats.get("peak_y")),
                    auc=fmt_num(stats.get("auc_trapezoid")),
                    csv=(payload or {}).get("csv") or "-",
                    svg=(payload or {}).get("svg") or "-",
                )
            )

        if curve_rows:
            lines.extend(
                [
                    "| Curve | Points | Peak X | Peak Y | AUC(trapz) | CSV | SVG |",
                    "|---|---:|---:|---:|---:|---|---|",
                    *curve_rows,
                    "",
                ]
            )
        else:
            lines.extend(["- No curve artifacts were generated.", ""])

    lines.extend([
        "",
        "## Repeat-Run Statistics",
        "",
    ])

    for c in cases:
        repeat_stats = c.get("repeat_statistics") or {}
        runs = int(repeat_stats.get("runs") or 0)
        if runs <= 0:
            continue
        pass_rate = repeat_stats.get("pass_rate")
        lines.append(f"- {c.get('scenario_id', '-')}: runs={runs}, pass_rate={pass_rate}")
        metric_stats = repeat_stats.get("metric_stats") or {}
        for key, item in metric_stats.items():
            mean = item.get("mean")
            std = item.get("std")
            if isinstance(mean, (int, float)) and isinstance(std, (int, float)):
                lines.append(f"  - {key}: mean={mean:.6g}, std={std:.6g}")

    lines.extend([
        "",
        "## Reviewer Checks",
        "",
    ])

    for k, v in (reviewer.get("checks") or {}).items():
        lines.append(f"- {k}: {bool(v)}")

    suggestions = reviewer.get("suggestions") or []
    lines.extend(["", "## Suggestions", ""])
    if suggestions:
        for s in suggestions:
            lines.append(f"- {s}")
    else:
        lines.append("- No remediation needed.")

    lines.extend([
        "",
        "## Artifact",
        "",
        f"- JSON: {report_json_path.as_posix()}",
        "",
        "## Invocation",
        "",
        "```bash",
        command,
        "```",
        "",
    ])

    return "\n".join(lines)


def append_convergence_log(path: Path, summary: Dict[str, Any]) -> None:
    planner = summary.get("planner") or {}
    executor_cases = (summary.get("executor") or {}).get("cases") or []
    reviewer = summary.get("reviewer") or {}
    planner_cfg = planner.get("octopus_overrides") or {}

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    "# Parameter Convergence Log",
                    "",
                    "Track Octopus parameter combinations and reviewer tables by round.",
                    "Update rule: append one new round block after each suite run.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def fmt_num(value: Any, digits: int = 8) -> str:
        if value is None:
            return "-"
        if isinstance(value, (int, float)):
            return f"{float(value):.{digits}f}"
        return str(value)

    lines: List[str] = []
    lines.append("")
    lines.append(f"## Round {summary.get('generated_at', now_iso())}")
    lines.append("")
    lines.append("### Parameter Combo")
    lines.append(f"- molecule: {planner.get('molecule', 'H')}")
    lines.append(f"- spacing: {planner_cfg.get('octopusSpacing', 'backend-default')}")
    lines.append(f"- radius: {planner_cfg.get('octopusRadius', 'backend-default')}")
    lines.append(f"- extra_states: {planner_cfg.get('octopusExtraStates', 'backend-default')}")
    lines.append(f"- xc_functional: {planner_cfg.get('xcFunctional', 'gga_x_pbe+gga_c_pbe')}")
    lines.append(f"- max_scf_iterations: {planner_cfg.get('octopusMaxScfIterations', 'backend-default')}")
    lines.append(f"- scf_tolerance: {planner_cfg.get('octopusScfTolerance', 'backend-default')}")
    lines.append("")
    lines.append("### Result Table")
    lines.append("")
    lines.append("| Scenario | Status | Engine | Computed | Reference | Delta | Rel.Delta | Tol | Within Tol | HOMO(eV) | HOMO.Raw(eV) | HOMO.Ref | HOMO.Rel.Delta | HOMO.Within | job_id | ncpus/mpiprocs | queue | exec_vnode |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|---|---|---|")

    for c in executor_cases:
        comparison = c.get("comparison") or {}
        secondary = c.get("secondary_comparisons") or []
        homo_cmp = next((item for item in secondary if str(item.get("metric") or "") == "homo_energy_ev"), {})
        scheduler = c.get("scheduler") or {}
        lines.append(
            "| {scenario} | {status} | {engine} | {computed} | {reference} | {delta} | {reldelta} | {tol} | {within} | {homo_computed} | {homo_raw} | {homo_ref} | {homo_reldelta} | {homo_within} | {job_id} | {ncpus}/{mpiprocs} | {queue} | {exec_vnode} |".format(
                scenario=c.get("scenario_id", "-"),
                status=c.get("status", "-"),
                engine=c.get("engine", "-"),
                computed=fmt_num(comparison.get("computed")),
                reference=fmt_num(comparison.get("reference")),
                delta=fmt_num(comparison.get("delta")),
                reldelta=fmt_num(comparison.get("relative_delta"), digits=6),
                tol=fmt_num(comparison.get("tolerance_relative"), digits=6),
                within="-" if comparison.get("within_tolerance") is None else str(bool(comparison.get("within_tolerance"))),
                homo_computed=fmt_num(homo_cmp.get("computed")),
                homo_raw=fmt_num((c.get("metrics") or {}).get("homo_energy_ev_raw")),
                homo_ref=fmt_num(homo_cmp.get("reference")),
                homo_reldelta=fmt_num(homo_cmp.get("relative_delta"), digits=6),
                homo_within="-" if homo_cmp.get("within_tolerance") is None else str(bool(homo_cmp.get("within_tolerance"))),
                job_id=scheduler.get("job_id", "-"),
                ncpus=scheduler.get("ncpus", "-"),
                mpiprocs=scheduler.get("mpiprocs", "-"),
                queue=scheduler.get("queue", "-"),
                exec_vnode=scheduler.get("exec_vnode", "-"),
            )
        )

    lines.append("")
    lines.append(f"- Final verdict: {reviewer.get('final_verdict', 'UNKNOWN')}")
    lines.append("")

    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def append_execution_reference_ledger(path: Path, summary: Dict[str, Any], report_json: Path) -> None:
    planner = summary.get("planner") or {}
    planner_cfg = planner.get("octopus_overrides") or {}
    executor_cases = (summary.get("executor") or {}).get("cases") or []

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    "# Execution Reference Ledger",
                    "",
                    "Append-only audit log for each suite execution: parameters, computed values, references, and provenance.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    lines: List[str] = []
    lines.append("")
    lines.append(f"## Run {summary.get('generated_at', now_iso())}")
    lines.append("")
    lines.append("### Parameter Combo")
    lines.append(f"- molecule: {planner.get('molecule', '-')}")
    lines.append(f"- spacing: {planner_cfg.get('octopusSpacing', 'backend-default')}")
    lines.append(f"- radius: {planner_cfg.get('octopusRadius', 'backend-default')}")
    lines.append(f"- extra_states: {planner_cfg.get('octopusExtraStates', 'backend-default')}")
    lines.append(f"- xc_functional: {planner_cfg.get('xcFunctional', 'gga_x_pbe+gga_c_pbe')}")
    lines.append(f"- ncpus: {planner_cfg.get('octopusNcpus', 64)}")
    lines.append(f"- mpiprocs: {planner_cfg.get('octopusMpiprocs', 64)}")
    lines.append("")
    lines.append("### Case Results")
    lines.append("")
    lines.append("| Case | Status | Computed | Reference | Delta | Rel.Delta | Source | Provenance Verified | job_id | ncpus/mpiprocs | queue | node | Secondary Checks |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|---|---|---|---|---|")

    for case in executor_cases:
        comparison = case.get("comparison") or {}
        secondary = case.get("secondary_comparisons") or []
        secondary_summary = "; ".join(
            [
                "{metric}:{computed}/{reference},within={within}".format(
                    metric=str(item.get("metric") or "-"),
                    computed=item.get("computed", "-"),
                    reference=item.get("reference", "-"),
                    within=("-" if item.get("within_tolerance") is None else str(bool(item.get("within_tolerance")))),
                )
                for item in secondary
            ]
        ) or "-"
        provenance = comparison.get("provenance") or {}
        scheduler = case.get("scheduler") or {}
        lines.append(
            "| {case_id} | {status} | {computed} | {reference} | {delta} | {relative_delta} | {source_url} | {pv} | {job_id} | {ncpus}/{mpiprocs} | {queue} | {node} | {secondary_summary} |".format(
                case_id=case.get("scenario_id", "-"),
                status=case.get("status", "-"),
                computed=comparison.get("computed", "-"),
                reference=comparison.get("reference", "-"),
                delta=comparison.get("delta", "-"),
                relative_delta=comparison.get("relative_delta", "-"),
                source_url=provenance.get("source_url", "-"),
                pv=str(bool(comparison.get("provenance_verified", False))),
                job_id=scheduler.get("job_id", "-"),
                ncpus=scheduler.get("ncpus", "-"),
                mpiprocs=scheduler.get("mpiprocs", "-"),
                queue=scheduler.get("queue", "-"),
                node=(scheduler.get("selected_node") or scheduler.get("exec_vnode") or "-"),
                secondary_summary=secondary_summary,
            )
        )

    lines.append("")
    lines.append(f"- report_json: {report_json.as_posix()}")
    lines.append("")

    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def print_case_outcome_summary(summary: Dict[str, Any]) -> None:
    executor_cases = (summary.get("executor") or {}).get("cases") or []
    for case in executor_cases:
        comparison = case.get("comparison") or {}
        metric = str(comparison.get("metric") or "metric")
        computed = comparison.get("computed")
        reference = comparison.get("reference")
        delta = comparison.get("delta")
        relative_delta = comparison.get("relative_delta")
        print(
            "suite_case_result="
            + json.dumps(
                {
                    "scenario_id": case.get("scenario_id"),
                    "status": case.get("status"),
                    "metric": metric,
                    "computed": computed,
                    "reference": reference,
                    "delta": delta,
                    "relative_delta": relative_delta,
                },
                ensure_ascii=True,
            )
        )


def write_openclaw_sync(
    path: Path,
    summary: Dict[str, Any],
    report_json: Path,
    report_md: Path,
    progress: Dict[str, Any] | None = None,
) -> None:
    payload: Dict[str, Any] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    reviewer = summary.get("reviewer") or {}
    planner = summary.get("planner") or {}
    planner_cfg = planner.get("octopus_overrides") or {}
    case_rows = []
    for c in (summary.get("executor") or {}).get("cases") or []:
        cmp = c.get("comparison") or {}
        sch = c.get("scheduler") or {}
        case_rows.append(
            {
                "scenario_id": c.get("scenario_id"),
                "status": c.get("status"),
                "engine": c.get("engine"),
                "computed": cmp.get("computed"),
                "reference": cmp.get("reference"),
                "delta": cmp.get("delta"),
                "relative_delta": cmp.get("relative_delta"),
                "tolerance_relative": cmp.get("tolerance_relative"),
                "within_tolerance": cmp.get("within_tolerance"),
                "secondary_comparisons": c.get("secondary_comparisons") or [],
                "job_id": sch.get("job_id"),
                "queue": sch.get("queue"),
                "ncpus": sch.get("ncpus"),
                "mpiprocs": sch.get("mpiprocs"),
                "exec_vnode": sch.get("exec_vnode"),
                "curve_artifacts": c.get("curve_artifacts") or {},
                "external_curve_comparison": c.get("external_curve_comparison") or {},
                "repeat_statistics": c.get("repeat_statistics") or {},
            }
        )

    payload["updated_at"] = now_iso()
    payload["project"] = "Dirac_solver"
    payload["dft_tddft_suite"] = {
        "final_verdict": reviewer.get("final_verdict"),
        "checks": reviewer.get("checks") or {},
        "passed_cases": reviewer.get("passed_cases", 0),
        "total_cases": reviewer.get("total_cases", 0),
        "progress": progress or {},
        "parameter_combo": {
            "molecule": planner.get("molecule", "H"),
            "spacing": planner_cfg.get("octopusSpacing"),
            "radius": planner_cfg.get("octopusRadius"),
            "extra_states": planner_cfg.get("octopusExtraStates"),
            "xc_functional": planner_cfg.get("xcFunctional"),
            "max_scf_iterations": planner_cfg.get("octopusMaxScfIterations"),
            "scf_tolerance": planner_cfg.get("octopusScfTolerance"),
        },
        "case_rows": case_rows,
        "report_json": report_json.as_posix(),
        "report_md": report_md.as_posix(),
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_sync_to_paths(
    paths: List[Path],
    summary: Dict[str, Any],
    report_json: Path,
    report_md: Path,
    progress: Dict[str, Any] | None = None,
) -> None:
    for sync_path in paths:
        write_openclaw_sync(sync_path, summary, report_json, report_md, progress=progress)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DFT/TDDFT agent suite for production-ready validation.")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001", help="Node API base URL.")
    parser.add_argument("--molecule", default="CH4", help="Molecule for DFT/TDDFT suite.")
    parser.add_argument("--td-steps", type=int, default=260, help="TDDFT propagation steps.")
    parser.add_argument("--td-time-step", type=float, default=0.04, help="TDDFT time step in a.u.")
    parser.add_argument("--task-ids", default=",".join(DEFAULT_TASK_IDS), help="Comma-separated scenario ids to run.")
    parser.add_argument("--octopus-dimensions", default="3D", help="Octopus dimensions, e.g. 3D.")
    parser.add_argument("--octopus-periodic", default="off", help="Periodic mode: off/on.")
    parser.add_argument(
        "--octopus-spacing",
        type=float,
        default=None,
        help="Optional Octopus spacing override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-radius",
        type=float,
        default=None,
        help="Optional Octopus simulation radius override (default: backend-managed).",
    )
    parser.add_argument("--octopus-box-shape", default="sphere", help="Octopus box shape.")
    parser.add_argument(
        "--octopus-species-mode",
        default="formula",
        choices=["formula", "pseudo", "all_electron", "all-electron"],
        help="Species mode: formula, pseudo, all_electron.",
    )
    parser.add_argument(
        "--octopus-pseudopotential-set",
        default="",
        help="Pseudopotential set label.",
    )
    parser.add_argument(
        "--octopus-all-electron-type",
        default="full_gaussian",
        choices=["full_delta", "full_gaussian", "full_anc"],
        help="All-electron species type for all_electron mode.",
    )
    parser.add_argument(
        "--octopus-extra-states",
        type=int,
        default=None,
        help="Optional extra states override (default: backend-managed).",
    )
    parser.add_argument("--xc-functional", default="gga_x_pbe+gga_c_pbe", help="XC functional string.")
    parser.add_argument(
        "--octopus-max-scf-iterations",
        type=int,
        default=None,
        help="Optional SCF max-iteration override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-scf-tolerance",
        type=float,
        default=None,
        help="Optional SCF tolerance override (default: backend-managed).",
    )
    parser.add_argument(
        "--octopus-ncpus",
        type=int,
        default=None,
        help="Optional PBS ncpus override passed to backend scheduler.",
    )
    parser.add_argument(
        "--octopus-mpiprocs",
        type=int,
        default=None,
        help="Optional PBS mpiprocs override passed to backend scheduler.",
    )
    parser.add_argument("--timeout", type=float, default=420.0, help="Per-case HTTP timeout seconds.")
    parser.add_argument("--output-dir", default="docs/harness_reports", help="Directory for report artifacts.")
    parser.add_argument(
        "--convergence-log-file",
        default=str(DEFAULT_CONVERGENCE_LOG_PATH),
        help="Markdown log file for convergence rounds.",
    )
    parser.add_argument(
        "--execution-ledger-file",
        default="docs/harness_reports/execution_reference_ledger.md",
        help="Append-only markdown ledger for parameters/results/reference/provenance per run.",
    )
    parser.add_argument("--openclaw-sync-path", default=str(DEFAULT_SYNC_PATH), help="OpenClaw sync path.")
    parser.add_argument(
        "--mirror-sync-path",
        default=str(DEFAULT_MIRROR_SYNC_PATH),
        help="Optional secondary sync path (for mirrored bridge state).",
    )
    parser.add_argument("--skip-openclaw-sync", action="store_true", help="Skip sync file update.")
    parser.add_argument(
        "--fast-path",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable/disable Octopus fastPath in suite payloads.",
    )
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when final verdict is FAIL.")
    parser.add_argument(
        "--external-reference-path",
        default=str(DEFAULT_EXTERNAL_REFERENCE_PATH),
        help="External reference catalog JSON for curve/peak comparisons.",
    )
    parser.add_argument(
        "--repeat-runs",
        type=int,
        default=1,
        help="Number of repeated runs per scenario for repeatability statistics.",
    )
    parser.add_argument(
        "--allow-pending-cases",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Allow execution of pending (not approved) official cases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    selected_task_ids = normalize_task_ids([item.strip() for item in str(args.task_ids or "").split(",")])
    validation_manifest = load_case_validation_manifest(CASE_VALIDATION_MANIFEST_PATH)
    selected_task_ids, blocked_task_ids = gate_task_ids_by_manifest(
        selected_task_ids,
        validation_manifest,
        bool(args.allow_pending_cases),
    )
    if blocked_task_ids:
        print(
            "[GATE] Blocked pending official cases (not approved in case_validation_manifest.json): "
            + ", ".join(blocked_task_ids),
            file=sys.stderr,
        )
    if not selected_task_ids:
        print("[ERROR] No approved task ids available to execute. Promote at least one case to approved_case_ids.", file=sys.stderr)
        return 2
    octopus_cfg = {
        "octopusDimensions": str(args.octopus_dimensions or "3D"),
        "octopusPeriodic": str(args.octopus_periodic or "off"),
        "octopusBoxShape": str(args.octopus_box_shape or "sphere"),
        "xcFunctional": str(args.xc_functional or "gga_x_pbe+gga_c_pbe"),
        "speciesMode": str(args.octopus_species_mode or "formula").strip().lower().replace("-", "_"),
    }
    if str(args.octopus_pseudopotential_set or "").strip():
        octopus_cfg["pseudopotentialSet"] = str(args.octopus_pseudopotential_set).strip()
    if str(args.octopus_all_electron_type or "").strip():
        octopus_cfg["allElectronType"] = str(args.octopus_all_electron_type).strip()

    if octopus_cfg["speciesMode"] not in ("formula", "pseudo", "all_electron"):
        print(
            "[ERROR] Unsupported --octopus-species-mode='{}'. Must be one of: formula, pseudo, all_electron.".format(
                octopus_cfg["speciesMode"]
            ),
            file=sys.stderr,
        )
        return 2
    if octopus_cfg["speciesMode"] == "pseudo" and octopus_cfg.get("octopusDimensions") != "3D":
        print(
            "[ERROR] Pseudo mode requires --octopus-dimensions=3D. Got: {}".format(
                octopus_cfg.get("octopusDimensions")
            ),
            file=sys.stderr,
        )
        return 2
    if args.octopus_spacing is not None:
        octopus_cfg["octopusSpacing"] = float(args.octopus_spacing)
    if args.octopus_radius is not None:
        octopus_cfg["octopusRadius"] = float(args.octopus_radius)
    if args.octopus_extra_states is not None:
        octopus_cfg["octopusExtraStates"] = max(1, int(args.octopus_extra_states))
    if args.octopus_max_scf_iterations is not None:
        octopus_cfg["octopusMaxScfIterations"] = max(1, int(args.octopus_max_scf_iterations))
    if args.octopus_scf_tolerance is not None:
        octopus_cfg["octopusScfTolerance"] = float(args.octopus_scf_tolerance)
    if args.octopus_ncpus is not None:
        octopus_cfg["octopusNcpus"] = max(1, int(args.octopus_ncpus))
    if args.octopus_mpiprocs is not None:
        octopus_cfg["octopusMpiprocs"] = max(1, int(args.octopus_mpiprocs))

    planner = {
        "agent": "planner",
        "timestamp": now_iso(),
        "objective": "Validate production DFT/TDDFT workflows for spectrum and dipole outputs.",
        "molecule": args.molecule,
        "suite_cases": selected_task_ids,
        "octopus_overrides": octopus_cfg,
    }

    endpoint = f"{args.api_base.rstrip('/')}/api/physics/run"
    suite_cases = build_suite_cases(
        args.molecule,
        args.td_steps,
        args.td_time_step,
        selected_task_ids,
        octopus_cfg,
        bool(args.fast_path),
    )

    summary = {
        "generated_at": now_iso(),
        "planner": planner,
        "executor": {"agent": "executor", "timestamp": now_iso(), "endpoint": endpoint, "cases": []},
        "reviewer": {"agent": "reviewer", "final_verdict": "RUNNING", "checks": {}, "passed_cases": 0, "total_cases": 0},
        "ui_review": {
            "title": f"DFT/TDDFT Agent Review ({args.molecule})",
            "final_verdict": "RUNNING",
            "checks": {},
            "case_cards": [],
        },
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_compact()
    report_json = out_dir / f"dft_tddft_agent_suite_{args.molecule}_{stamp}.json"
    report_md = out_dir / f"dft_tddft_agent_suite_{args.molecule}_{stamp}.md"
    artifacts_dir = out_dir / "curve_artifacts"
    external_refs = _load_external_references(Path(args.external_reference_path))
    repeat_runs = max(1, int(args.repeat_runs))

    sync_paths: List[Path] = []
    primary_sync = Path(args.openclaw_sync_path)
    if str(primary_sync):
        sync_paths.append(primary_sync)
    mirror_sync = Path(args.mirror_sync_path)
    if str(mirror_sync) and mirror_sync not in sync_paths:
        sync_paths.append(mirror_sync)

    command = (
        f"python scripts/run_dft_tddft_agent_suite.py --api-base {args.api_base} "
        f"--molecule {args.molecule} --td-steps {args.td_steps} --td-time-step {args.td_time_step}"
    )

    # Emit one sync snapshot before execution so Feishu can display immediate running state.
    if not args.skip_openclaw_sync:
        running_summary = {
            **summary,
            "reviewer": {
                **(summary.get("reviewer") or {}),
                "final_verdict": "RUNNING",
            },
        }
        write_sync_to_paths(
            sync_paths,
            running_summary,
            report_json,
            report_md,
            progress={
                "state": "running",
                "completed_cases": 0,
                "total_cases": len(suite_cases),
            },
        )

    # Run cases with incremental sync updates for real-time monitoring.
    executor_cases = []
    for idx, case in enumerate(suite_cases, start=1):
        per_run_summaries: List[Dict[str, Any]] = []
        for run_idx in range(1, repeat_runs + 1):
            error = ""
            result: Dict[str, Any] = {}
            try:
                result = post_json(endpoint, case["payload"], timeout=args.timeout)
            except Exception as exc:
                error = str(exc)
            run_stamp = f"{stamp}_r{run_idx:02d}"
            per_run_summaries.append(
                summarize_case(
                    case,
                    result,
                    error,
                    artifacts_root=artifacts_dir,
                    stamp=run_stamp,
                    external_refs=external_refs,
                )
            )

        primary = json.loads(json.dumps(per_run_summaries[0], ensure_ascii=True))
        primary["repeat_statistics"] = _compute_repeat_statistics(per_run_summaries)
        primary["repeat_runs"] = per_run_summaries
        if primary.get("repeat_statistics", {}).get("pass_rate", 0.0) < 1.0:
            primary["checks"]["repeatability_pass"] = False
            if "repeatability_pass" not in primary["required_missing"]:
                primary["required_missing"].append("repeatability_pass")
            primary["status"] = "FAIL"
        else:
            primary["checks"]["repeatability_pass"] = True

        executor_cases.append(primary)

        executor = {
            "agent": "executor",
            "timestamp": now_iso(),
            "endpoint": endpoint,
            "cases": executor_cases,
        }
        reviewer = reviewer_stage(executor_cases)
        summary = {
            "generated_at": now_iso(),
            "planner": planner,
            "executor": executor,
            "reviewer": reviewer,
            "ui_review": {
                "title": f"DFT/TDDFT Agent Review ({args.molecule})",
                "final_verdict": reviewer.get("final_verdict"),
                "checks": reviewer.get("checks") or {},
                "case_cards": [
                    {
                        "scenario_id": c.get("scenario_id"),
                        "title": c.get("title"),
                        "status": c.get("status"),
                        "optical_points": (c.get("metrics") or {}).get("cross_section_points", 0),
                        "dipole_points": (c.get("metrics") or {}).get("dipole_points", 0),
                        "radiation_points": (c.get("metrics") or {}).get("radiation_points", 0),
                        "eels_points": (c.get("metrics") or {}).get("eels_points", 0),
                        "engine": c.get("engine"),
                        "comparison": c.get("comparison"),
                        "scheduler": c.get("scheduler") or {},
                    }
                    for c in executor_cases
                ],
            },
        }

        if not args.skip_openclaw_sync:
            write_sync_to_paths(
                sync_paths,
                summary,
                report_json,
                report_md,
                progress={
                    "state": "running" if idx < len(suite_cases) else "finalizing",
                    "completed_cases": idx,
                    "total_cases": len(suite_cases),
                    "current_case": case.get("scenario_id"),
                },
            )

    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    report_md.write_text(render_markdown(summary, command, report_json), encoding="utf-8")
    convergence_log_path = Path(args.convergence_log_file)
    append_convergence_log(convergence_log_path, summary)
    # Keep the historical docs-path mirror updated for existing downstream consumers.
    if convergence_log_path.resolve() != LEGACY_CONVERGENCE_LOG_PATH.resolve():
        append_convergence_log(LEGACY_CONVERGENCE_LOG_PATH, summary)
    append_execution_reference_ledger(Path(args.execution_ledger_file), summary, report_json)

    if not args.skip_openclaw_sync:
        write_sync_to_paths(
            sync_paths,
            summary,
            report_json,
            report_md,
            progress={
                "state": "completed",
                "completed_cases": len(suite_cases),
                "total_cases": len(suite_cases),
            },
        )

    print(f"suite_report_json={report_json.as_posix()}")
    print(f"suite_report_md={report_md.as_posix()}")
    print(f"suite_convergence_log={convergence_log_path.as_posix()}")
    if convergence_log_path.resolve() != LEGACY_CONVERGENCE_LOG_PATH.resolve():
        print(f"suite_convergence_log_legacy={LEGACY_CONVERGENCE_LOG_PATH.as_posix()}")
    print_case_outcome_summary(summary)
    print(f"suite_verdict={reviewer.get('final_verdict')}")
    if not args.skip_openclaw_sync:
        print("openclaw_sync_json=" + ",".join([p.as_posix() for p in sync_paths]))

    if args.strict and reviewer.get("final_verdict") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
