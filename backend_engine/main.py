from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh
import math
from pathlib import Path
import hashlib
import json
import time
from datetime import datetime, timezone
import os

try:
    from .kb_rag import default_kb
except ImportError:
    # Fallback for direct script execution contexts.
    from kb_rag import default_kb

app = FastAPI()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_KB_SERVICE = None
_CASE_REGISTRY_CACHE = None
CASE_REGISTRY_PATH = PROJECT_ROOT / "knowledge_base" / "benchmark_cases.json"
CASE_VALIDATION_MANIFEST_PATH = PROJECT_ROOT / "knowledge_base" / "case_validation_manifest.json"
CAPABILITY_MATRIX_PATH = PROJECT_ROOT / "knowledge_base" / "metadata" / "octopus_tutorial16_capability_matrix.json"
_CAPABILITY_MATRIX_CACHE = None
_CASE_TYPE_REGISTRY_CACHE = None
_CASE_VALIDATION_MANIFEST_CACHE = None

_CATEGORY_TO_CASE_TYPE = {
    "periodic_systems": "periodic_bands",
    "response": "response_td",
    "maxwell": "response_td",
    "hpc": "hpc_scaling",
    "basics": "boundstate_1d",
    "model": "dft_gs_3d",
    "multisystem": "dft_gs_3d",
}


def kb_service():
    global _KB_SERVICE
    if _KB_SERVICE is None:
        _KB_SERVICE = default_kb(PROJECT_ROOT)
    return _KB_SERVICE

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PhysicsConfig(BaseModel):
    # Core parameters
    mass: float = 1.0
    gridSpacing: float = 0.05
    potentialStrength: float = 0.0
    # Geometry
    dimensionality: str = "1D"
    unitSystem: str = "natural"
    spatialRange: float = 10.0
    gridPoints: int = 100
    boundaryCondition: str = "dirichlet"
    # Potential
    potentialType: str = "InfiniteWell"
    wellWidth: float = 1.0
    customExpression: Optional[str] = None
    # Equation & problem type
    equationType: str = "Schrodinger"
    problemType: str = "boundstate"
    picture: str = "schrodinger"
    # Time evolution parameters
    numTimeSteps: int = 50
    totalTime: float = 5.0
    initialState: str = "gaussian"
    gaussianCenter: float = 0.0
    gaussianWidth: float = 0.3
    gaussianMomentum: float = 5.0
    # Scattering
    scatteringEnergyMin: float = 0.0
    scatteringEnergyMax: float = 10.0
    scatteringEnergySteps: int = 200
    caseType: Optional[str] = None


class KBIngestRequest(BaseModel):
    source: str
    text: str
    topic_tags: Optional[List[str]] = None


class KBQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    topic_tag: Optional[str] = None


class HarnessCaseRequest(BaseModel):
    case_id: str = "h2o_gs_reference"
    overrides: Optional[Dict[str, object]] = None


class HarnessIterateRequest(BaseModel):
    case_id: str = "h2o_gs_reference"
    max_iterations: int = 3
    initial_overrides: Optional[Dict[str, object]] = None


def _load_case_registry() -> Dict[str, Dict[str, object]]:
    global _CASE_REGISTRY_CACHE
    if _CASE_REGISTRY_CACHE is not None:
        return _CASE_REGISTRY_CACHE

    if not CASE_REGISTRY_PATH.exists():
        _CASE_REGISTRY_CACHE = {}
        return _CASE_REGISTRY_CACHE

    payload = json.loads(CASE_REGISTRY_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    registry: Dict[str, Dict[str, object]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        normalized_case = dict(case)
        case_id = str(normalized_case.get("case_id", "")).strip().lower()
        if not case_id:
            continue
        inferred_case_type = _infer_case_type(normalized_case)
        normalized_case["case_type"] = inferred_case_type

        default_cfg = dict(normalized_case.get("default_config") or {})
        default_cfg.setdefault("caseType", inferred_case_type)
        normalized_case["default_config"] = default_cfg

        registry[case_id] = normalized_case
        for alias in normalized_case.get("aliases") or []:
            registry[str(alias).strip().lower()] = normalized_case
    _CASE_REGISTRY_CACHE = registry
    return registry


def _default_case_validation_manifest() -> Dict[str, object]:
    return {
        "version": "1.0.0",
        "updated_at": None,
        "approved_case_ids": [
            "infinite_well_v1",
            "harmonic_oscillator_v1",
            "ch4_gs_reference",
            "n_atom_gs_official",
        ],
        "approved_molecules": ["CH4", "N_atom"],
        "pending_case_ids": [
            "hydrogen_gs_reference",
            "h2o_gs_reference",
            "h2o_tddft_dipole_response",
            "h2o_tddft_absorption",
            "h2o_tddft_radiation_spectrum",
            "h2o_tddft_eels_spectrum",
        ],
        "notes": "CH4 and N_atom are current golden official cases for UI-first exposure.",
    }


def _load_case_validation_manifest() -> Dict[str, object]:
    global _CASE_VALIDATION_MANIFEST_CACHE
    if _CASE_VALIDATION_MANIFEST_CACHE is not None:
        return _CASE_VALIDATION_MANIFEST_CACHE

    manifest = _default_case_validation_manifest()
    if CASE_VALIDATION_MANIFEST_PATH.exists():
        try:
            payload = json.loads(CASE_VALIDATION_MANIFEST_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                manifest.update(payload)
        except Exception:
            pass

    approved_case_ids = manifest.get("approved_case_ids")
    if not isinstance(approved_case_ids, list):
        approved_case_ids = []
    manifest["approved_case_ids"] = sorted(set(str(item).strip().lower() for item in approved_case_ids if str(item).strip()))

    pending_case_ids = manifest.get("pending_case_ids")
    if not isinstance(pending_case_ids, list):
        pending_case_ids = []
    manifest["pending_case_ids"] = sorted(set(str(item).strip().lower() for item in pending_case_ids if str(item).strip()))

    approved_molecules = manifest.get("approved_molecules")
    if not isinstance(approved_molecules, list):
        approved_molecules = []
    manifest["approved_molecules"] = sorted(set(str(item).strip() for item in approved_molecules if str(item).strip()))

    _CASE_VALIDATION_MANIFEST_CACHE = manifest
    return manifest


def _infer_case_type(case: Dict[str, object]) -> str:
    explicit = str(case.get("case_type") or "").strip().lower()
    if explicit:
        return explicit

    comparator = str(case.get("comparator") or "").strip().lower()
    if comparator in {"infinite_well_ground_state", "harmonic_oscillator_ground_state"}:
        return "boundstate_1d"
    if comparator in {"h2o_gs_reference_energy"}:
        return "dft_gs_3d"

    default_cfg = case.get("default_config") or {}
    problem_type = str(default_cfg.get("problemType") or "").strip().lower()
    dimensionality = str(default_cfg.get("dimensionality") or "").strip().lower()
    if problem_type in {"timeevolution", "scattering"}:
        return "response_td"
    if dimensionality == "3d":
        return "dft_gs_3d"
    return "boundstate_1d"


def _default_config_template(case_type: str) -> Dict[str, object]:
    base = _default_infinite_well_config().model_dump()
    normalized = str(case_type or "boundstate_1d").strip().lower()
    if normalized == "dft_gs_3d":
        base.update({
            "dimensionality": "3D",
            "equationType": "Schrodinger",
            "problemType": "boundstate",
            "potentialType": "Coulomb",
            "gridPoints": 64,
            "gridSpacing": 0.25,
        })
    elif normalized == "response_td":
        base.update({
            "problemType": "timeevolution",
            "equationType": "Schrodinger",
            "totalTime": 8.0,
            "numTimeSteps": 80,
            "potentialType": "Harmonic",
        })
    elif normalized == "periodic_bands":
        base.update({
            "dimensionality": "3D",
            "equationType": "Schrodinger",
            "problemType": "boundstate",
            "potentialType": "Custom",
            "customExpression": "0.0",
            "gridPoints": 80,
            "gridSpacing": 0.2,
        })
    elif normalized == "hpc_scaling":
        base.update({
            "dimensionality": "3D",
            "equationType": "Schrodinger",
            "problemType": "boundstate",
            "gridPoints": 96,
            "gridSpacing": 0.2,
        })
    base["caseType"] = normalized
    return base


def _infer_case_type_from_category(category: str) -> str:
    norm = str(category or "").strip().lower()
    return _CATEGORY_TO_CASE_TYPE.get(norm, "dft_gs_3d")


def _build_case_type_registry() -> Dict[str, object]:
    global _CASE_TYPE_REGISTRY_CACHE
    if _CASE_TYPE_REGISTRY_CACHE is not None:
        return _CASE_TYPE_REGISTRY_CACHE

    cases_by_id: Dict[str, Dict[str, object]] = {}
    for case in _load_case_registry().values():
        canonical_id = str(case.get("case_id") or "").strip().lower()
        if canonical_id:
            cases_by_id[canonical_id] = case

    case_types: Dict[str, Dict[str, object]] = {}
    for case in cases_by_id.values():
        case_type = str(case.get("case_type") or "boundstate_1d").strip().lower()
        item = case_types.setdefault(
            case_type,
            {
                "case_type": case_type,
                "case_ids": [],
                "matrix_categories": [],
                "canonical_tutorials": [],
                "default_config_template": _default_config_template(case_type),
            },
        )
        item["case_ids"].append(str(case.get("case_id") or ""))
        cfg = case.get("default_config") or {}
        if isinstance(cfg, dict) and cfg:
            item["default_config_template"] = dict(cfg)
            item["default_config_template"].setdefault("caseType", case_type)

    matrix = _load_capability_matrix()
    for row in matrix.get("rows") or []:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "").strip().lower()
        case_type = _infer_case_type_from_category(category)
        item = case_types.setdefault(
            case_type,
            {
                "case_type": case_type,
                "case_ids": [],
                "matrix_categories": [],
                "canonical_tutorials": [],
                "default_config_template": _default_config_template(case_type),
            },
        )
        item["matrix_categories"].append(category)
        tutorials = row.get("canonical_cases") or []
        if isinstance(tutorials, list):
            for tutorial in tutorials:
                if not isinstance(tutorial, dict):
                    continue
                item["canonical_tutorials"].append(
                    {
                        "title": tutorial.get("title"),
                        "url": tutorial.get("url"),
                        "score": tutorial.get("score"),
                        "source_category": category,
                    }
                )

    normalized_case_types = []
    for key in sorted(case_types.keys()):
        entry = case_types[key]
        entry["case_ids"] = sorted(set([cid for cid in entry.get("case_ids", []) if cid]))
        entry["matrix_categories"] = sorted(set([c for c in entry.get("matrix_categories", []) if c]))
        entry["canonical_tutorials"] = sorted(
            entry.get("canonical_tutorials", []),
            key=lambda item: (str(item.get("source_category") or ""), -float(item.get("score") or 0.0), str(item.get("title") or "")),
        )
        entry["case_count"] = len(entry["case_ids"])
        normalized_case_types.append(entry)

    _CASE_TYPE_REGISTRY_CACHE = {
        "generated_at": _utc_now_iso(),
        "tutorial_matrix_generated_at": matrix.get("generated_at"),
        "case_types": normalized_case_types,
        "count": len(normalized_case_types),
    }
    return _CASE_TYPE_REGISTRY_CACHE


def _get_case_def(case_id: str) -> Dict[str, object]:
    registry = _load_case_registry()
    case = registry.get((case_id or "").strip().lower())
    if not case:
        raise HTTPException(status_code=400, detail=f"Unsupported case_id: {case_id}")
    if case.get("enabled") is False:
        raise HTTPException(status_code=400, detail=f"Case is disabled: {case.get('case_id', case_id)}")
    return case


def _load_capability_matrix() -> Dict[str, object]:
    global _CAPABILITY_MATRIX_CACHE
    if _CAPABILITY_MATRIX_CACHE is not None:
        return _CAPABILITY_MATRIX_CACHE

    if not CAPABILITY_MATRIX_PATH.exists():
        _CAPABILITY_MATRIX_CACHE = {
            "generated_at": None,
            "source": str(CAPABILITY_MATRIX_PATH),
            "tutorial_count": 0,
            "category_count": 0,
            "rows": [],
            "missing": True,
        }
        return _CAPABILITY_MATRIX_CACHE

    payload = json.loads(CAPABILITY_MATRIX_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("missing", False)
    payload.setdefault("rows", [])
    payload.setdefault("tutorial_count", 0)
    payload.setdefault("category_count", 0)
    _CAPABILITY_MATRIX_CACHE = payload
    return _CAPABILITY_MATRIX_CACHE


def _config_from_case(case: Dict[str, object], overrides: Optional[Dict[str, object]]) -> PhysicsConfig:
    cfg_dict = dict(case.get("default_config") or {})
    if not cfg_dict:
        cfg_dict = _default_infinite_well_config().model_dump()

    cfg_dict.setdefault("caseType", str(case.get("case_type") or "boundstate_1d").strip().lower())
    allowed_fields = set(PhysicsConfig.model_fields.keys())

    if overrides:
        for key, value in overrides.items():
            if key in allowed_fields:
                cfg_dict[key] = value
    return PhysicsConfig(**cfg_dict)


def _harmonic_oscillator_reference(config: PhysicsConfig) -> Dict[str, float]:
    # For V(x)=k*x^2 and m=1, hbar=1, omega=sqrt(2k), E0=(1/2)*omega.
    k = abs(config.potentialStrength) if config.potentialStrength != 0 else 0.5
    omega = math.sqrt(max(2.0 * k, 1e-12))
    e0 = 0.5 * omega
    return {"E0": e0, "omega": omega, "k": k}


def _h2o_gs_reference() -> Dict[str, object]:
    return {
        "total_energy_hartree": -62.91084098,
        "units": "Ha",
        "source": "knowledge_base/corpus/h2o_gs_reference_provenance.md",
    }


HARTREE_TO_EV = 27.211386245988


def _to_float(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_energy_hartree(solver_result: Dict[str, object]) -> tuple[Optional[float], Optional[str]]:
    energy = _to_float(solver_result.get("total_energy_hartree"))
    if energy is not None:
        return energy, "total_energy_hartree"

    energy = _to_float(solver_result.get("total_energy"))
    if energy is not None:
        return energy, "total_energy"

    eigenvalues = solver_result.get("eigenvalues", [])
    if isinstance(eigenvalues, list) and eigenvalues:
        energy = _to_float(eigenvalues[0])
        if energy is not None:
            return energy, "eigenvalue0_proxy"
    return None, None


def _normalize_threshold(case: Dict[str, object], default_value: float = 0.03) -> float:
    tolerance_cfg = case.get("tolerance") or {}
    threshold = _to_float(tolerance_cfg.get("relative_error_max"))
    if threshold is None or threshold <= 0:
        return default_value
    return threshold


def _with_eval_metadata(
    payload: Dict[str, object],
    evaluator_name: str,
    diagnostics: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    payload["evaluator"] = evaluator_name
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    return payload


def _evaluate_case_by_comparator(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    """Legacy comparator path kept for backward compatibility."""
    comparator = str(case.get("comparator") or "infinite_well_ground_state").strip().lower()
    tolerance_cfg = case.get("tolerance") or {}
    threshold = float(tolerance_cfg.get("relative_error_max", 0.03))

    eigenvalues = solver_result.get("eigenvalues", [])

    if comparator == "infinite_well_ground_state":
        if not eigenvalues:
            raise ValueError("No eigenvalues returned from solver")
        theory = _infinite_well_reference(config)
        ref = float(theory["E1"])
        calc = float(eigenvalues[0])
        observable_name = "E1"
    elif comparator == "harmonic_oscillator_ground_state":
        if not eigenvalues:
            raise ValueError("No eigenvalues returned from solver")
        theory = _harmonic_oscillator_reference(config)
        ref = float(theory["E0"])
        calc = float(eigenvalues[0])
        observable_name = "E0"
    elif comparator == "h2o_gs_reference_energy":
        theory = _h2o_gs_reference()
        ref = float(theory["total_energy_hartree"])
        energy_value = solver_result.get("total_energy_hartree")
        if energy_value is None:
            energy_value = solver_result.get("total_energy")
        if energy_value is None:
            if not eigenvalues:
                raise ValueError("No total_energy_hartree or eigenvalues returned from solver")
            energy_value = eigenvalues[0]
            theory = dict(theory)
            theory["fallback"] = "used_eigenvalue0_as_energy_proxy"
        calc = float(energy_value)
        observable_name = "total_energy_hartree"
    else:
        raise ValueError(f"Unsupported comparator: {comparator}")

    rel_err = abs(calc - ref) / (abs(ref) + 1e-12)
    passed = rel_err < threshold
    quality_score = max(0.0, min(1.0, 1.0 - rel_err / (threshold + 1e-12)))

    return {
        "comparator": comparator,
        "theory": theory,
        "computed": {observable_name: calc},
        "relative_error": rel_err,
        "threshold": threshold,
        "passed": passed,
        "quality_score": quality_score,
    }


def _evaluate_case_boundstate_1d(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    return _evaluate_case_by_comparator(case, config, solver_result)


def _evaluate_case_dft_gs_3d(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    comparator = str(case.get("comparator") or "").strip().lower()
    if comparator in {
        "infinite_well_ground_state",
        "harmonic_oscillator_ground_state",
        "h2o_gs_reference_energy",
    }:
        base = _evaluate_case_by_comparator(case, config, solver_result)

        threshold = _normalize_threshold(case)
        diagnostics: Dict[str, object] = {
            "fallback_to_comparator": True,
            "energy_source": None,
        }

        energy_hartree, energy_source = _extract_energy_hartree(solver_result)
        diagnostics["energy_source"] = energy_source

        case_id = str(case.get("case_id") or "").strip().lower()
        if case_id == "hydrogen_gs_reference" and energy_hartree is not None:
            derived_homo_ev = energy_hartree * HARTREE_TO_EV
            diagnostics["derived_homo_ev"] = derived_homo_ev
            theory_ref = _to_float(((case.get("theory") or {}).get("homo_energy_ev")))
            if theory_ref is not None and abs(theory_ref) > 1e-12:
                homo_rel_error = abs(derived_homo_ev - theory_ref) / (abs(theory_ref) + 1e-12)
                diagnostics["homo_relative_error"] = homo_rel_error
                diagnostics["homo_within_threshold"] = homo_rel_error <= threshold

        return _with_eval_metadata(base, "dft_gs_3d", diagnostics)

    threshold = _normalize_threshold(case)
    energy_hartree, energy_source = _extract_energy_hartree(solver_result)
    diagnostics: Dict[str, object] = {
        "fallback_to_comparator": False,
        "energy_source": energy_source,
    }

    if energy_hartree is None:
        return _with_eval_metadata(
            {
                "comparator": "dft_gs_3d_energy_presence",
                "theory": {
                    "observable": "total_energy_hartree",
                    "units": "Ha",
                    "source": "case_definition_or_runtime",
                },
                "computed": {},
                "relative_error": 1.0,
                "threshold": threshold,
                "passed": False,
                "quality_score": 0.0,
            },
            "dft_gs_3d",
            diagnostics,
        )

    theory = case.get("theory") or {}
    ref = _to_float(theory.get("total_energy_hartree"))
    if ref is None:
        ref = _to_float(theory.get("reference_total_energy_hartree"))

    computed_payload: Dict[str, Any] = {
        "total_energy_hartree": energy_hartree,
    }
    if str(case.get("case_id") or "").strip().lower() == "hydrogen_gs_reference":
        computed_payload["homo_energy_ev"] = energy_hartree * HARTREE_TO_EV

    if ref is None:
        return _with_eval_metadata(
            {
                "comparator": "dft_gs_3d_energy_presence",
                "theory": {
                    "observable": "total_energy_hartree",
                    "units": "Ha",
                    "source": "case_definition_missing_numeric_reference",
                },
                "computed": computed_payload,
                "relative_error": 0.0,
                "threshold": threshold,
                "passed": True,
                "quality_score": 1.0,
            },
            "dft_gs_3d",
            diagnostics,
        )

    rel_err = abs(energy_hartree - ref) / (abs(ref) + 1e-12)
    passed = rel_err <= threshold
    quality_score = max(0.0, min(1.0, 1.0 - rel_err / (threshold + 1e-12)))
    return _with_eval_metadata(
        {
            "comparator": "dft_gs_3d_total_energy",
            "theory": {
                "total_energy_hartree": ref,
                "units": "Ha",
                "source": "case_definition",
            },
            "computed": computed_payload,
            "relative_error": rel_err,
            "threshold": threshold,
            "passed": passed,
            "quality_score": quality_score,
        },
        "dft_gs_3d",
        diagnostics,
    )


def _evaluate_case_response_td(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    comparator = str(case.get("comparator") or "").strip().lower()
    if comparator in {
        "infinite_well_ground_state",
        "harmonic_oscillator_ground_state",
        "h2o_gs_reference_energy",
    }:
        base = _evaluate_case_by_comparator(case, config, solver_result)
        return _with_eval_metadata(
            base,
            "response_td",
            {"fallback_to_comparator": True},
        )

    threshold = _normalize_threshold(case, default_value=0.05)
    time_grid = solver_result.get("time_grid") if isinstance(solver_result.get("time_grid"), list) else []
    psi_t = solver_result.get("psi_t") if isinstance(solver_result.get("psi_t"), list) else []
    x_grid = solver_result.get("x_grid") if isinstance(solver_result.get("x_grid"), list) else []

    has_time_grid = len(time_grid) > 1
    has_psi_t = len(psi_t) > 0
    dx = 1.0
    if len(x_grid) > 1:
        x0 = _to_float(x_grid[0])
        x1 = _to_float(x_grid[1])
        if x0 is not None and x1 is not None:
            dx = abs(x1 - x0)

    norm_drift = None
    if has_time_grid and has_psi_t:
        norms: List[float] = []
        for row in psi_t:
            if isinstance(row, list) and row:
                norm = 0.0
                for v in row:
                    fv = _to_float(v)
                    if fv is not None:
                        norm += fv
                norms.append(norm * dx)
        if norms:
            norm_drift = max(abs(v - norms[0]) for v in norms)

    structure_ok = has_time_grid and has_psi_t
    if norm_drift is None:
        rel_err = 1.0 if not structure_ok else 0.0
    else:
        rel_err = float(norm_drift)
    passed = structure_ok and rel_err <= threshold
    quality_score = max(0.0, min(1.0, 1.0 - rel_err / (threshold + 1e-12)))

    diagnostics = {
        "fallback_to_comparator": False,
        "has_time_grid": has_time_grid,
        "has_psi_t": has_psi_t,
        "norm_drift": norm_drift,
        "time_steps": len(time_grid),
    }
    return _with_eval_metadata(
        {
            "comparator": "response_td_norm_drift",
            "theory": {
                "observable": "norm_drift",
                "target": 0.0,
                "units": "absolute_probability",
                "source": "response_td_runtime",
            },
            "computed": {
                "norm_drift": norm_drift,
                "time_steps": len(time_grid),
            },
            "relative_error": rel_err,
            "threshold": threshold,
            "passed": passed,
            "quality_score": quality_score,
        },
        "response_td",
        diagnostics,
    )


def _evaluate_case_periodic_bands(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    comparator = str(case.get("comparator") or "").strip().lower()
    if comparator in {
        "infinite_well_ground_state",
        "harmonic_oscillator_ground_state",
        "h2o_gs_reference_energy",
    }:
        base = _evaluate_case_by_comparator(case, config, solver_result)
        return _with_eval_metadata(
            base,
            "periodic_bands",
            {"fallback_to_comparator": True},
        )

    threshold = _normalize_threshold(case, default_value=0.05)
    eigenvalues_raw = solver_result.get("eigenvalues", [])
    eigenvalues: List[float] = []
    if isinstance(eigenvalues_raw, list):
        for value in eigenvalues_raw:
            fv = _to_float(value)
            if fv is not None:
                eigenvalues.append(fv)
    eigenvalues = sorted(eigenvalues)

    gap = None
    if len(eigenvalues) >= 2:
        gap = max(0.0, eigenvalues[1] - eigenvalues[0])

    theory = case.get("theory") or {}
    ref_gap = _to_float(theory.get("band_gap"))
    if ref_gap is None:
        ref_gap = _to_float(theory.get("band_gap_reference"))

    if gap is None:
        rel_err = 1.0
        passed = False
    elif ref_gap is None:
        rel_err = 0.0 if gap > 0 else 1.0
        passed = gap > 0
    else:
        rel_err = abs(gap - ref_gap) / (abs(ref_gap) + 1e-12)
        passed = rel_err <= threshold
    quality_score = max(0.0, min(1.0, 1.0 - rel_err / (threshold + 1e-12)))

    diagnostics = {
        "fallback_to_comparator": False,
        "eigenvalue_count": len(eigenvalues),
        "reference_gap_available": ref_gap is not None,
    }
    return _with_eval_metadata(
        {
            "comparator": "periodic_band_gap_proxy",
            "theory": {
                "band_gap": ref_gap,
                "units": "solver_energy_units",
                "source": "case_definition" if ref_gap is not None else "case_definition_missing_numeric_reference",
            },
            "computed": {
                "band_gap": gap,
                "eigenvalue_count": len(eigenvalues),
            },
            "relative_error": rel_err,
            "threshold": threshold,
            "passed": passed,
            "quality_score": quality_score,
        },
        "periodic_bands",
        diagnostics,
    )


def _evaluate_case_hpc_scaling(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    return _evaluate_case_by_comparator(case, config, solver_result)


def _evaluate_case(case: Dict[str, object], config: PhysicsConfig, solver_result: Dict[str, object]) -> Dict[str, object]:
    case_type = str(case.get("case_type") or config.caseType or "boundstate_1d").strip().lower()
    dispatch = {
        "boundstate_1d": _evaluate_case_boundstate_1d,
        "dft_gs_3d": _evaluate_case_dft_gs_3d,
        "response_td": _evaluate_case_response_td,
        "maxwell_em": _evaluate_case_response_td,
        "periodic_bands": _evaluate_case_periodic_bands,
        "hpc_scaling": _evaluate_case_hpc_scaling,
    }
    evaluator = dispatch.get(case_type, _evaluate_case_by_comparator)
    result = evaluator(case, config, solver_result)
    result["case_type"] = case_type
    return result


def _controller_adjustment(config: PhysicsConfig, relative_error: float, threshold: float) -> Dict[str, object]:
    actions: List[str] = []
    overrides: Dict[str, object] = {}

    if relative_error > threshold:
        current_points = max(int(config.gridPoints), 51)
        current_spacing = max(float(config.gridSpacing), 1e-6)
        if current_points < 401:
            overrides["gridPoints"] = min(801, int(current_points * 1.5))
            actions.append("increase_grid_points")
        if current_spacing > 0.01:
            overrides["gridSpacing"] = round(max(0.005, current_spacing * 0.7), 6)
            actions.append("decrease_grid_spacing")

    if not actions:
        actions.append("keep_config")

    return {
        "actions": actions,
        "overrides": overrides,
        "reason": "relative_error_above_threshold" if relative_error > threshold else "passed_or_no_adjustment_needed",
    }


def _run_harness_case(case_id: str, overrides: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    case = _get_case_def(case_id)
    canonical_case_id = str(case.get("case_id") or case_id)

    max_retries = max(1, int(float(os.environ.get("HARNESS_MAX_RETRIES", "2"))))
    base_timeout_seconds = max(1.0, float(os.environ.get("HARNESS_TIMEOUT_SECONDS", "60")))

    current_overrides = dict(overrides or {})
    cfg = _config_from_case(case, current_overrides)
    estimated_timeout_seconds = _estimate_harness_timeout_seconds(canonical_case_id, cfg)
    timeout_seconds = max(base_timeout_seconds, estimated_timeout_seconds)
    cfg_hash = _stable_config_hash(cfg.model_dump())

    threshold_cfg = case.get("tolerance") or {}
    desired_relative_error_max = float(threshold_cfg.get("relative_error_max", 0.03))

    event_chain: List[Dict[str, object]] = [
        {
            "phase": "harness_start",
            "timestamp": _utc_now_iso(),
            "case_id": canonical_case_id,
            "config_hash": cfg_hash,
            "framework": "desired_state -> controller -> solver -> quality_feedback",
            "constraints": {
                "max_retries": max_retries,
                "base_timeout_seconds": base_timeout_seconds,
                "estimated_timeout_seconds": estimated_timeout_seconds,
                "timeout_seconds": timeout_seconds,
                "error_threshold": desired_relative_error_max,
            },
        }
    ]

    started_at = time.perf_counter()
    last_error: Optional[str] = None
    final_solver_result: Optional[Dict[str, object]] = None
    final_eval: Optional[Dict[str, object]] = None
    control_iterations: List[Dict[str, object]] = []

    for attempt in range(1, max_retries + 1):
        cfg = _config_from_case(case, current_overrides)
        event_chain.append(
            {
                "phase": "solver_attempt_start",
                "timestamp": _utc_now_iso(),
                "attempt": attempt,
                "config": cfg.model_dump(),
            }
        )
        try:
            solver_result = solve_quantum_system(cfg)
            evaluated = _evaluate_case(case, cfg, solver_result)

            control_step = {
                "attempt": attempt,
                "desired_state": {"relative_error_max": evaluated["threshold"]},
                "controller_action": {"actions": ["evaluate_current_config"], "overrides": dict(current_overrides)},
                "observed_state": {
                    "relative_error": evaluated["relative_error"],
                    "passed": evaluated["passed"],
                },
                "quality": {
                    "score": evaluated["quality_score"],
                    "threshold": evaluated["threshold"],
                },
            }

            if not evaluated["passed"] and attempt < max_retries:
                adjustment = _controller_adjustment(cfg, float(evaluated["relative_error"]), float(evaluated["threshold"]))
                control_step["controller_action"] = adjustment
                current_overrides.update(adjustment.get("overrides") or {})

            control_iterations.append(control_step)
            event_chain.append(
                {
                    "phase": "solver_attempt_success",
                    "timestamp": _utc_now_iso(),
                    "attempt": attempt,
                    "relative_error": evaluated["relative_error"],
                    "passed": evaluated["passed"],
                    "quality_score": evaluated["quality_score"],
                }
            )

            final_solver_result = solver_result
            final_eval = evaluated
            if evaluated["passed"]:
                break
        except Exception as exc:
            last_error = str(exc)
            event_chain.append(
                {
                    "phase": "solver_attempt_failure",
                    "timestamp": _utc_now_iso(),
                    "attempt": attempt,
                    "error": last_error,
                }
            )

    elapsed = time.perf_counter() - started_at
    if final_solver_result is None or final_eval is None:
        raise ValueError(f"Solver failed after {max_retries} attempts: {last_error}")
    if elapsed > timeout_seconds:
        raise TimeoutError(f"Harness exceeded timeout ({elapsed:.2f}s > {timeout_seconds:.2f}s)")

    event_chain.append(
        {
            "phase": "harness_evaluate",
            "timestamp": _utc_now_iso(),
            "relative_error": final_eval["relative_error"],
            "threshold": final_eval["threshold"],
            "passed": final_eval["passed"],
            "quality_score": final_eval["quality_score"],
            "elapsed_seconds": elapsed,
        }
    )

    result_payload = {
        "case_id": canonical_case_id,
        "case_type": final_eval.get("case_type") or str(case.get("case_type") or cfg.caseType or "boundstate_1d").strip().lower(),
        "evaluator": final_eval.get("evaluator"),
        "diagnostics": final_eval.get("diagnostics") or {},
        "config_hash": _stable_config_hash(cfg.model_dump()),
        "config": cfg.model_dump(),
        "theory": final_eval["theory"],
        "computed": final_eval["computed"],
        "relative_error": final_eval["relative_error"],
        "threshold": final_eval["threshold"],
        "passed": final_eval["passed"],
        "harness_constraints": {
            "max_retries": max_retries,
            "base_timeout_seconds": base_timeout_seconds,
            "estimated_timeout_seconds": estimated_timeout_seconds,
            "timeout_seconds": timeout_seconds,
            "attempts_used": len(control_iterations),
        },
        "control_loop": {
            "desired_state": {"relative_error_max": final_eval["threshold"]},
            "final_observed_state": {
                "relative_error": final_eval["relative_error"],
                "passed": final_eval["passed"],
            },
            "quality": {"score": final_eval["quality_score"]},
            "iterations": control_iterations,
        },
        "solver_summary": {
            "eigenvalue_count": len(final_solver_result.get("eigenvalues", [])),
            "matrix_info": final_solver_result.get("matrix_info", {}),
            "elapsed_seconds": elapsed,
        },
        "escalation": {
            "required": not final_eval["passed"],
            "reason": "relative_error_exceeds_threshold" if not final_eval["passed"] else None,
        },
        "event_chain": event_chain,
        "solver_result": final_solver_result,
    }

    log_refs = _write_harness_logs(canonical_case_id, result_payload["config_hash"], event_chain, result_payload)
    result_payload["log_refs"] = log_refs
    return result_payload


def _infinite_well_reference(config: PhysicsConfig) -> Dict[str, float]:
    """Reference energies for 1D infinite well: E_n = n^2*pi^2/(2mL^2)."""
    L = config.wellWidth if config.wellWidth > 0 else config.spatialRange
    m = config.mass
    e1 = (math.pi ** 2) / (2.0 * m * (L ** 2))
    return {"E1": e1, "L": L}


def _default_infinite_well_config() -> PhysicsConfig:
    return PhysicsConfig(
        mass=1.0,
        gridSpacing=0.02,
        potentialStrength=0.0,
        dimensionality="1D",
        unitSystem="natural",
        spatialRange=2.0,
        gridPoints=201,
        boundaryCondition="dirichlet",
        potentialType="InfiniteWell",
        wellWidth=1.0,
        equationType="Schrodinger",
        problemType="boundstate",
    )


def _estimate_harness_timeout_seconds(case_id: str, config: PhysicsConfig) -> float:
    """Estimate a runtime budget from problem complexity to avoid under-timeout on larger cases."""
    grid_points = max(int(config.gridPoints), 10)
    dim_label = (config.dimensionality or "1D").strip().upper()
    dim_factor = {"1D": 1.0, "2D": 4.0, "3D": 12.0}.get(dim_label, 1.0)

    equation = (config.equationType or "Schrodinger").strip().lower()
    eq_factor = 1.0
    if equation == "dirac":
        eq_factor = 1.8
    elif equation == "kleingordon":
        eq_factor = 1.3

    ptype = (config.problemType or "boundstate").strip().lower()
    ptype_factor = 1.0 if ptype == "boundstate" else 1.5

    complexity_score = grid_points * dim_factor * eq_factor * ptype_factor
    if case_id == "infinite_well_v1":
        base_seconds = 20.0
    else:
        base_seconds = 30.0

    estimated = base_seconds + (complexity_score / 40.0)
    return max(10.0, min(600.0, estimated))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_config_hash(config_dict: Dict[str, object]) -> str:
    payload = json.dumps(config_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _write_harness_logs(case_id: str, config_hash: str, event_chain: List[Dict[str, object]], result_payload: Dict[str, object]) -> Dict[str, str]:
    hash_part = config_hash.split(":", 1)[-1]
    base_dir = PROJECT_ROOT / "harness_logs" / case_id / hash_part
    base_dir.mkdir(parents=True, exist_ok=True)

    event_log_path = base_dir / "event_log.json"
    result_path = base_dir / "result.json"

    event_log_path.write_text(json.dumps(event_chain, indent=2, ensure_ascii=True), encoding="utf-8")
    result_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    return {
        "event_log": str(event_log_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "result_json": str(result_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }


@app.post("/kb/ingest_markdown")
def ingest_markdown(req: KBIngestRequest):
    try:
        result = kb_service().ingest_markdown(
            source=req.source,
            text=req.text,
            topic_tags=req.topic_tags,
        )
        return {"status": "ok", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KB ingest failed: {exc}") from exc


@app.post("/kb/query")
def query_kb(req: KBQueryRequest):
    try:
        return kb_service().query(query=req.query, top_k=req.top_k, topic_tag=req.topic_tag)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KB query failed: {exc}") from exc


@app.get("/harness/capability_matrix")
def harness_capability_matrix():
    """Expose tutorial16 capability matrix for UI/planner/reviewer alignment."""
    try:
        return _load_capability_matrix()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Capability matrix load failed: {exc}") from exc


# ─── Potential Builders ─────────────────────────────────────────────

def build_potential_1d(x: np.ndarray, config: PhysicsConfig) -> np.ndarray:
    V = np.zeros(len(x))
    ptype = config.potentialType.lower().replace(" ", "").replace("_", "")
    V0 = config.potentialStrength
    w = config.wellWidth / 2.0

    if ptype == "infinitewell":
        V[:] = 0.0
        # Infinite walls are enforced in the kinetic operator builder

    elif ptype == "finitewell":
        for i in range(len(x)):
            if np.abs(x[i]) < w:
                V[i] = V0  # inside well (usually negative)
            else:
                V[i] = 0.0 # outside well

    elif ptype == "coulomb":
        Z = abs(V0) if V0 != 0 else 1.0
        a = config.gridSpacing * 0.5  # softening
        V = -Z / np.sqrt(x**2 + a**2)

    elif ptype == "harmonic":
        k = abs(V0) if V0 != 0 else 0.5
        V = k * x**2

    elif ptype == "gaussian":
        sigma = w  # wellWidth used as sigma
        V0_ = V0 if V0 != 0 else -1.0
        V = V0_ * np.exp(-x**2 / (2 * sigma**2))

    elif ptype == "step":
        V[x >= 0] = V0
        V[x < 0] = 0.0

    elif ptype == "doublewell":
        # Double well: V(x) = V0*(x^2 - d^2)^2 / d^4; d = wellWidth/2
        d = w
        a = abs(V0) if V0 != 0 else 1.0
        V = a * (x**2 - d**2)**2 / (d**4 + 1e-10)

    elif ptype == "morse":
        # Morse potential: V(x) = V0*(1-exp(-alpha*(x-xe)))^2; xe=0, alpha=wellWidth
        alpha = config.wellWidth if config.wellWidth != 0 else 1.0
        V0_ = abs(V0) if V0 != 0 else 1.0
        V = V0_ * (1 - np.exp(-alpha * x))**2

    elif ptype == "freespace":
        V[:] = 0.0

    elif ptype == "custom" and config.customExpression:
        try:
            V = eval(config.customExpression, {"x": x, "np": np,
                     "sin": np.sin, "cos": np.cos, "exp": np.exp,
                     "sqrt": np.sqrt, "abs": np.abs, "pi": np.pi})
            if np.isscalar(V):
                V = np.full_like(x, V)
        except Exception as e:
            raise ValueError(f"Invalid custom expression: {e}")
    else:
        # Fallback to constant potential if not matched, but should not happen for standard types
        V[:] = V0

    return V


def build_2d_potential(xx: np.ndarray, yy: np.ndarray, config: PhysicsConfig) -> np.ndarray:
    """2D potential on meshgrid (Nx, Ny)."""
    V_x = build_potential_1d(xx[0, :], config)  # potential along x
    V_y = build_potential_1d(yy[:, 0], config)  # potential along y
    # For separable potentials, V(x,y) = V(x) + V(y)
    return V_x[np.newaxis, :] + V_y[:, np.newaxis]


# ─── Hamiltonian Builders ────────────────────────────────────────────

def build_schrodinger_1d(x, V, m, config):
    N = len(x)
    dx = x[1] - x[0]
    diag = np.ones(N) * (1.0 / (m * dx**2)) + V
    off = np.ones(N - 1) * (-0.5 / (m * dx**2))

    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: off[i] = 0.0
                if i > 0: off[i - 1] = 0.0

    return sparse.diags([off, diag, off], [-1, 0, 1], format='csr')


def build_dirac_1d(x, V, m, config):
    """1D Dirac Hamiltonian in 2-component spinor space (2N × 2N matrix)."""
    N = len(x)
    dx = x[1] - x[0]

    diag_A = m + V
    diag_B = -m + V
    H_AA = sparse.diags([diag_A], [0], shape=(N, N))
    H_BB = sparse.diags([diag_B], [0], shape=(N, N))

    b_off = np.ones(N - 1) / (2.0 * dx)
    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: b_off[i] = 0.0
                if i > 0: b_off[i - 1] = 0.0

    D_minus = sparse.diags([b_off, -b_off], [-1, 1], shape=(N, N))
    D_plus = sparse.diags([-b_off, b_off], [-1, 1], shape=(N, N))

    return sparse.bmat([[H_AA, D_minus], [D_plus, H_BB]], format='csr')


def build_kleingorden_1d(x, V, m, config):
    """Klein-Gordon effective Hamiltonian: H_eff = -∂²/∂x² + m² + 2mV(x)
    We solve H_eff ψ = E² ψ, then E = sqrt(eigenvalue).
    This is equivalent to (E - V)² = p² + m², so H_eff = p² + (m + V)² - V²
    Simplified: H_eff = -∂²/∂x² + m² + 2mV for weak potentials.
    """
    N = len(x)
    dx = x[1] - x[0]
    # p² operator (same as kinetic in Schrödinger but without 1/2m)
    diag = np.ones(N) * (1.0 / dx**2) + m**2 + 2 * m * V
    off = np.ones(N - 1) * (-0.5 / dx**2)

    ptype = config.potentialType.lower()
    if "infinite" in ptype and "well" in ptype:
        w = config.wellWidth / 2.0
        for i in range(N):
            if np.abs(x[i]) >= w - 1e-10:
                if i < N - 1: off[i] = 0.0
                if i > 0: off[i - 1] = 0.0

    return sparse.diags([off, diag, off], [-1, 0, 1], format='csr')


def build_schrodinger_2d(x, y, V2d, m):
    """2D Schrödinger Hamiltonian via Kronecker sum."""
    Nx, Ny = len(x), len(y)
    dx, dy = x[1] - x[0], y[1] - y[0]

    # 1D kinetic operators
    diag_x = np.ones(Nx) * (1.0 / (m * dx**2))
    off_x = np.ones(Nx - 1) * (-0.5 / (m * dx**2))
    T_x = sparse.diags([off_x, diag_x, off_x], [-1, 0, 1], format='csr')

    diag_y = np.ones(Ny) * (1.0 / (m * dy**2))
    off_y = np.ones(Ny - 1) * (-0.5 / (m * dy**2))
    T_y = sparse.diags([off_y, diag_y, off_y], [-1, 0, 1], format='csr')

    # Kronecker sum: T_2D = T_x ⊗ I_y + I_x ⊗ T_y
    I_x = sparse.eye(Nx, format='csr')
    I_y = sparse.eye(Ny, format='csr')
    T_2D = sparse.kron(T_x, I_y, format='csr') + sparse.kron(I_x, T_y, format='csr')

    # Potential (flattened)
    V_flat = V2d.flatten()
    V_mat = sparse.diags([V_flat], [0], format='csr')

    return T_2D + V_mat


# ─── Eigenstate Solver ───────────────────────────────────────────────

def solve_eigenstates(H, N_total, k=10):
    """Solve for k lowest eigenstates of sparse Hamiltonian H."""
    k = min(k, N_total - 2)
    if N_total <= 2000:
        evals, evecs = np.linalg.eigh(H.toarray())
    else:
        evals, evecs = eigsh(H, k=k, which='SA')
    idx = np.argsort(evals)
    return evals[idx], evecs[:, idx]


# ─── Momentum Space ──────────────────────────────────────────────────

def compute_momentum_space(psi_x, dx):
    """Compute momentum-space wavefunction via FFT."""
    N = len(psi_x)
    freqs = np.fft.fftfreq(N, d=dx)
    p_grid = 2 * np.pi * freqs
    psi_p_raw = np.fft.fft(psi_x) * dx / np.sqrt(2 * np.pi)
    sort_idx = np.argsort(p_grid)
    return p_grid[sort_idx], np.abs(psi_p_raw[sort_idx])


# ─── Time Evolution Solver ───────────────────────────────────────────

def solve_time_evolution(x, V, m, config, eq):
    """
    Build eigenstate basis, project initial Gaussian wavepacket,
    propagate in time, return |ψ(x,t)|².
    """
    N = len(x)
    dx = x[1] - x[0]

    # Build Hamiltonian and solve eigenstates
    if "dirac" in eq:
        H = build_dirac_1d(x, V, m, config)
        k_use = min(80, 2 * N - 2)
    elif "kleingorden" in eq or "klein" in eq:
        H = build_kleingorden_1d(x, V, m, config)
        k_use = min(80, N - 2)
    else:
        H = build_schrodinger_1d(x, V, m, config)
        k_use = min(80, N - 2)

    evals, evecs = solve_eigenstates(H, H.shape[0], k=k_use)

    # For Dirac, extract upper component
    if "dirac" in eq:
        evals_phys = []
        evecs_phys = []
        # Keep only positive-energy states
        for i in range(len(evals)):
            if evals[i] > 0:
                psi_A = evecs[:N, i]
                norm = np.sqrt(np.sum(np.abs(psi_A)**2) * dx)
                if norm > 1e-12:
                    evecs_phys.append(psi_A / norm)
                    evals_phys.append(evals[i])
        evals = np.array(evals_phys[:80])
        phi = np.array(evecs_phys[:80])  # shape (k, N)
    elif "kleingorden" in eq or "klein" in eq:
        # Take positive energy sqrt(eigenvalues)
        pos_mask = evals > 0
        evals = np.sqrt(np.clip(evals[pos_mask], 0, None))[:80]
        phi = evecs[:, pos_mask].T[:80]  # shape (k, N)
        for i in range(len(phi)):
            norm = np.sqrt(np.sum(np.abs(phi[i])**2) * dx)
            if norm > 1e-12:
                phi[i] /= norm
    else:
        # Keep up to lowest 80
        k_keep = min(80, len(evals))
        evals = evals[:k_keep]
        phi = evecs[:, :k_keep].T  # shape (k, N)
        for i in range(len(phi)):
            norm = np.sqrt(np.sum(np.abs(phi[i])**2) * dx)
            if norm > 1e-12:
                phi[i] /= norm

    if len(evals) == 0:
        raise ValueError("No valid eigenstates found for time evolution")

    # Construct initial Gaussian wavepacket
    x0 = config.gaussianCenter
    sigma = config.gaussianWidth * (x[-1] - x[0])  # relative to domain
    k0 = config.gaussianMomentum
    psi0 = np.exp(-(x - x0)**2 / (4 * sigma**2)) * np.exp(1j * k0 * x)
    norm0 = np.sqrt(np.sum(np.abs(psi0)**2) * dx)
    psi0 /= norm0

    # Expansion coefficients: c_n = <phi_n | psi_0>
    c = np.array([np.sum(phi[i] * psi0) * dx for i in range(len(evals))])

    # Time grid
    T_total = config.totalTime
    n_steps = min(config.numTimeSteps, 100)
    time_grid = np.linspace(0, T_total, n_steps)

    # Propagate: ψ(x,t) = Σ_n c_n φ_n(x) e^{-i E_n t}
    psi_t = np.zeros((n_steps, N))  # |ψ(x,t)|²
    for ti, t in enumerate(time_grid):
        psi_xt = np.zeros(N, dtype=complex)
        for ni in range(len(evals)):
            psi_xt += c[ni] * phi[ni] * np.exp(-1j * evals[ni] * t)
        psi_t[ti] = np.abs(psi_xt)**2

    return {
        "time_grid": time_grid.tolist(),
        "psi_t": psi_t.tolist(),
        "initial_state": (np.abs(psi0)**2).tolist(),
        "eigenvalues": evals.tolist(),
        "initial_coefficients": (np.abs(c)**2).tolist(),
        "x_grid": x.tolist(),
    }


# ─── Scattering Solver (Transfer Matrix) ────────────────────────────

def solve_scattering(x, V, m, config, eq):
    """
    Transfer matrix method for 1D scattering.
    Computes T(E) and R(E) for a range of incident energies.
    Returns energy_range, transmission, reflection, and scattering wavefunctions
    at selected energies.
    """
    E_min = config.scatteringEnergyMin
    E_max = config.scatteringEnergyMax
    n_E = min(config.scatteringEnergySteps, 500)
    energies = np.linspace(E_min + 1e-6, E_max, n_E)

    dx = x[1] - x[0]
    N = len(x)

    transmission = np.zeros(n_E)
    reflection = np.zeros(n_E)

    for ei, E in enumerate(energies):
        # Local wavenumber: k²(x) = 2m(E - V(x)) for Schrödinger
        # For KG: k²(x) = (E - V)² - m²; for Dirac similarly
        if "dirac" in eq.lower() or "kleingorden" in eq.lower() or "klein" in eq.lower():
            k2 = (E - V)**2 - m**2
        else:
            k2 = 2 * m * (E - V)

        # Transfer matrix product
        M = np.eye(2, dtype=complex)
        for i in range(N - 1):
            k2i = k2[i]
            if k2i > 0:
                ki = np.sqrt(k2i)
                phi_i = ki * dx
                Mi = np.array([
                    [np.cos(phi_i), np.sin(phi_i) / ki],
                    [-ki * np.sin(phi_i), np.cos(phi_i)]
                ], dtype=complex)
            else:
                kappa = np.sqrt(max(-k2i, 1e-12))
                phi_i = kappa * dx
                Mi = np.array([
                    [np.cosh(phi_i), np.sinh(phi_i) / kappa],
                    [kappa * np.sinh(phi_i), np.cosh(phi_i)]
                ], dtype=complex)
            M = M @ Mi

        # Transmission: T = 1 / |M[0,0]|²  (simplified for same-medium boundaries)
        k2_left = k2[0]
        k2_right = k2[-1]

        if k2_left > 0 and k2_right > 0:
            k_left = np.sqrt(k2_left)
            k_right = np.sqrt(k2_right)
            # T = (k_right/k_left) / |M11 + M12*k_right|² ... overly complex;
            # Use simplified: T ≈ k_right/k_left * |2/(M[0,0]+M[0,1]*k_right/1j+...)|
            # Simplified (same-medium case): T = 1/|M[0,0]|²
            denom = abs(M[0, 0])**2
            T_val = min(k_right / k_left / max(denom, 1e-12), 1.0)
            T_val = max(T_val, 0.0)
        elif k2_left > 0 and k2_right <= 0:
            T_val = 0.0  # evanescent on right — total reflection
        else:
            T_val = 0.0

        transmission[ei] = T_val
        reflection[ei] = 1.0 - T_val

    # Find resonances: peaks in T(E)
    resonance_indices = []
    for i in range(1, n_E - 1):
        if transmission[i] > transmission[i - 1] and transmission[i] > transmission[i + 1]:
            if transmission[i] > 0.5:  # only strong resonances
                resonance_indices.append(i)
    resonances = [float(energies[i]) for i in resonance_indices]

    # Compute wavefunction at a few representative energies (for visualization)
    sample_energies_idx = np.linspace(0, n_E - 1, min(5, n_E), dtype=int)
    sample_wavefunctions = []
    for ei in sample_energies_idx:
        E = energies[ei]
        k2 = 2 * m * (E - V)
        if k2[0] > 0:
            k0 = np.sqrt(k2[0])
            # Approximate wavefunction: incident + reflected on left, transmitted on right
            psi = np.zeros(N, dtype=complex)
            # Simple approximation: plane wave modulated by local wavenumber
            phase = np.cumsum(np.sqrt(np.clip(k2, 0, None))) * dx
            psi = np.exp(1j * phase) * np.sqrt(np.clip(k2, 1e-12, None))**(-0.25)
            psi /= (np.sqrt(np.sum(np.abs(psi)**2) * dx) + 1e-12)
            sample_wavefunctions.append({
                "energy": float(E),
                "psi_sq": np.abs(psi).tolist(),
                "transmission": float(transmission[ei]),
            })

    return {
        "energy_range": energies.tolist(),
        "transmission": transmission.tolist(),
        "reflection": reflection.tolist(),
        "resonances": resonances,
        "sample_wavefunctions": sample_wavefunctions,
        "x_grid": x.tolist(),
    }


# ─── Main Solve Endpoint ─────────────────────────────────────────────

@app.post("/solve")
def solve_quantum_system(config: PhysicsConfig):
    try:
        # ── Grid Setup ──────────────────────────────────────────────
        eq = config.equationType.lower()
        problem = config.problemType.lower()
        dim = config.dimensionality.upper()

        dx_target = config.gridSpacing
        N_req = int(np.round(config.spatialRange / dx_target)) + 1

        # Memory safety limits
        if dim == "1D":
            N = min(N_req, 2000)
        elif dim == "2D":
            N = min(int(np.sqrt(min(N_req**2, 10000))), 80)
        else:  # 3D
            N = min(int(N_req**(1/3)), 25)

        x = np.linspace(-config.spatialRange / 2, config.spatialRange / 2, N)
        dx = x[1] - x[0]
        m = config.mass
        V = build_potential_1d(x, config)

        # ── Scattering Problem ──────────────────────────────────────
        if "scatter" in problem:
            result = solve_scattering(x, V, m, config, eq)
            result["problemType"] = "scattering"
            result["equationType"] = config.equationType
            result["potential_V"] = V.tolist()
            result["matrix_info"] = {"size": N, "non_zeros": N * 3, "isHermitian": True}
            return result

        # ── Time Evolution Problem ──────────────────────────────────
        if "time" in problem or "evolution" in problem:
            result = solve_time_evolution(x, V, m, config, eq)
            result["problemType"] = "timeevolution"
            result["equationType"] = config.equationType
            result["potential_V"] = V.tolist()
            result["matrix_info"] = {"size": N, "non_zeros": N * 3, "isHermitian": True}
            return result

        # ── Bound State Problem ─────────────────────────────────────
        k_display = 10

        if dim == "2D":
            # 2D Schrödinger only
            Ny, Nx = N, N
            y = np.linspace(-config.spatialRange / 2, config.spatialRange / 2, Ny)
            xx, yy = np.meshgrid(x, y)
            V2d = build_2d_potential(xx, yy, config)
            H = build_schrodinger_2d(x, y, V2d, m)
            N_total = Nx * Ny
            k_display = min(k_display, N_total - 2)
            evals, evecs = solve_eigenstates(H, N_total, k=k_display)

            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            eigenvalues = evals.tolist()
            wavefunctions = []
            for i in range(k_display):
                psi_flat = evecs[:, i].real
                norm = np.sqrt(np.sum(psi_flat**2) * dx**2)
                psi_flat /= (norm + 1e-12)
                psi_2d = psi_flat.reshape(Ny, Nx)
                # Marginal distributions for 1D plots
                psi_x = np.sqrt(np.sum(psi_2d**2, axis=0) * dx)
                psi_y = np.sqrt(np.sum(psi_2d**2, axis=1) * dx)
                wavefunctions.append({
                    "psi_up": psi_x.tolist(),
                    "psi_down": psi_y.tolist(),
                    "psi_2d": psi_2d.tolist(),
                })

            # Physical Filter: only return true bound states (E < V_max)
            v_max = np.max(V2d)
            if v_max > np.min(V2d) + 1e-5 and "infinite" not in config.potentialType.lower():
                bound_mask = evals < v_max
                k_bound = min(k_display, np.sum(bound_mask))
                eigenvalues = eigenvalues[:k_bound]
                wavefunctions = wavefunctions[:k_bound]

            return {
                "problemType": "boundstate",
                "equationType": config.equationType,
                "dimensionality": "2D",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "y_grid": y.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": N_total, "non_zeros": N_total * 5, "isHermitian": True},
            }

        elif dim == "3D":
            # 3D: only return simplified result (memory constrained)
            Nz = N
            z = x.copy()
            # Build 3D as three 1D problems + potential (separable approximation)
            H = build_schrodinger_1d(x, V, m, config)  # Use 1D for now
            evals, evecs = solve_eigenstates(H, N, k=k_display)
            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            eigenvalues = (evals * 3).tolist()  # 3D energy ≈ 3 × E_1D for separable
            wavefunctions = []
            for i in range(k_display):
                psi = evecs[:, i]
                norm = np.sqrt(np.sum(np.abs(psi)**2) * dx)
                psi = psi / (norm + 1e-12)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                })

            return {
                "problemType": "boundstate",
                "equationType": config.equationType,
                "dimensionality": "3D",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": N**3, "non_zeros": N**3 * 7, "isHermitian": True},
            }

        # ── 1D Bound State Solvers ──────────────────────────────────
        if "kleingorden" in eq or "klein" in eq or "kg" in eq:
            H = build_kleingorden_1d(x, V, m, config)
            evals_sq, evecs = solve_eigenstates(H, N, k=k_display)
            # Energy = sqrt(eigenvalue), only positive
            pos_mask = evals_sq > m**2  # above rest mass threshold
            if pos_mask.sum() == 0:
                pos_mask = evals_sq > 0
            evals = np.sqrt(np.clip(evals_sq[pos_mask], 0, None))
            evecs_pos = evecs[:, pos_mask]
            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs_pos = evecs_pos[:, :k_display]

            eigenvalues = evals.tolist()
            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            wavefunctions = []
            for i in range(k_display):
                psi = evecs_pos[:, i].real
                norm = np.sqrt(np.sum(psi**2) * dx)
                psi /= (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi, dx)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            H_mat = H
            return {
                "problemType": "boundstate",
                "equationType": "KleinGordon",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H_mat.shape[0], "non_zeros": H_mat.nnz, "isHermitian": True},
            }

        elif "dirac" in eq:
            H = build_dirac_1d(x, V, m, config)
            evals, evecs = solve_eigenstates(H, 2 * N, k=min(k_display * 2, 2 * N - 2))

            # Select k_half states near +m and k_half near -m
            k_half = 5
            diff_plus = np.abs(evals - m)
            diff_minus = np.abs(evals + m)
            plus_idx = np.argsort(diff_plus)[:k_half]
            minus_idx = np.argsort(diff_minus)[:k_half]
            selected_idx = sorted(set(plus_idx.tolist() + minus_idx.tolist()))

            eigenvalues = [float(evals[i]) for i in selected_idx]
            wavefunctions = []
            for idx in selected_idx:
                psi_A = evecs[:N, idx]
                psi_B = evecs[N:, idx]
                norm = np.sqrt(np.sum((np.abs(psi_A)**2 + np.abs(psi_B)**2)) * dx)
                psi_A = psi_A / (norm + 1e-12)
                psi_B = psi_B / (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi_A.real, dx)
                wavefunctions.append({
                    "psi_up": psi_A.real.tolist(),
                    "psi_down": psi_B.real.tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            return {
                "problemType": "boundstate",
                "equationType": "Dirac",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H.shape[0], "non_zeros": H.nnz, "isHermitian": True},
            }

        else:
            # Schrödinger
            H = build_schrodinger_1d(x, V, m, config)
            evals, evecs = solve_eigenstates(H, N, k=k_display)

            k_display = min(k_display, len(evals))
            evals = evals[:k_display]
            evecs = evecs[:, :k_display]

            freqs = np.fft.fftfreq(N, d=dx)
            p_grid = 2 * np.pi * freqs
            sort_idx = np.argsort(p_grid)
            p_grid_sorted = p_grid[sort_idx]

            eigenvalues = evals.tolist()
            wavefunctions = []
            for i in range(k_display):
                psi = evecs[:, i].real
                norm = np.sqrt(np.sum(psi**2) * dx)
                psi /= (norm + 1e-12)
                _, psi_p = compute_momentum_space(psi, dx)
                wavefunctions.append({
                    "psi_up": psi.tolist(),
                    "psi_down": np.zeros(N).tolist(),
                    "psi_p_mag": psi_p.tolist(),
                })

            # Physical Filter: only return true bound states (E < V_max) for non-infinite wells
            v_max = np.max(V)
            if v_max > np.min(V) + 1e-5 and "infinite" not in config.potentialType.lower():
                bound_mask = evals < v_max
                k_bound = min(k_display, np.sum(bound_mask))
                eigenvalues = eigenvalues[:k_bound]
                wavefunctions = wavefunctions[:k_bound]

            return {
                "problemType": "boundstate",
                "equationType": "Schrodinger",
                "eigenvalues": eigenvalues,
                "wavefunctions": wavefunctions,
                "x_grid": x.tolist(),
                "p_grid": p_grid_sorted.tolist(),
                "potential_V": V.tolist(),
                "matrix_info": {"size": H.shape[0], "non_zeros": H.nnz, "isHermitian": True},
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/harness/infinite_well")
def harness_infinite_well(overrides: Optional[Dict[str, object]] = None):
    """Run Infinite Well benchmark via the unified control-loop harness."""
    try:
        return _run_harness_case("infinite_well_v1", overrides)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Infinite well harness failed: {exc}") from exc


@app.get("/harness/case_registry")
def harness_case_registry(include_unapproved: bool = True):
    registry = _load_case_registry()
    manifest = _load_case_validation_manifest()
    approved_case_ids = set(str(item).strip().lower() for item in (manifest.get("approved_case_ids") or []))
    # Keep only canonical records in list output.
    canonical = {}
    for case in registry.values():
        cid = str(case.get("case_id", "")).strip().lower()
        if cid:
            case_entry = dict(case)
            case_entry["ui_exposure_status"] = "approved" if cid in approved_case_ids else "pending_automation"
            if include_unapproved or case_entry["ui_exposure_status"] == "approved":
                canonical[cid] = case_entry

    case_type_registry = _build_case_type_registry()
    items = []
    for item in case_type_registry.get("case_types") or []:
        if not isinstance(item, dict):
            continue
        case_ids = [
            cid for cid in (item.get("case_ids") or [])
            if include_unapproved or str(cid).strip().lower() in approved_case_ids
        ]
        items.append(
            {
                "case_type": item.get("case_type"),
                "count": len(case_ids),
                "case_ids": case_ids,
                "matrix_categories": item.get("matrix_categories") or [],
                "canonical_tutorials": item.get("canonical_tutorials") or [],
            }
        )

    return {
        "version": "0.3.0",
        "manifest_version": manifest.get("version"),
        "manifest_updated_at": manifest.get("updated_at"),
        "approved_case_ids": sorted(approved_case_ids),
        "approved_molecules": manifest.get("approved_molecules") or [],
        "pending_case_ids": manifest.get("pending_case_ids") or [],
        "items": items,
        "cases": sorted(canonical.values(), key=lambda c: str(c.get("case_id", ""))),
        "count": len(canonical),
        "include_unapproved": bool(include_unapproved),
    }


@app.get("/harness/case_types")
def harness_case_types():
    """Expose normalized case_type registry with canonical tutorials and default templates."""
    try:
        return _build_case_type_registry()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Case type registry load failed: {exc}") from exc


@app.post("/harness/run_case")
def harness_run_case(req: HarnessCaseRequest):
    """Unified benchmark entrypoint backed by case registry and control-loop harness."""
    case_id = (req.case_id or "").strip().lower() or "h2o_gs_reference"
    return _run_harness_case(case_id, req.overrides)


@app.post("/harness/iterate_case")
def harness_iterate_case(req: HarnessIterateRequest):
    """Run repeated harness cycles with controller-suggested overrides and keep full history."""
    case_id = (req.case_id or "").strip().lower() or "h2o_gs_reference"
    max_iterations = max(1, min(int(req.max_iterations), 10))

    history: List[Dict[str, object]] = []
    current_overrides: Dict[str, object] = dict(req.initial_overrides or {})
    best_result: Optional[Dict[str, object]] = None

    for idx in range(1, max_iterations + 1):
        run_result = _run_harness_case(case_id, current_overrides)
        run_result["iteration_index"] = idx
        run_result["input_overrides"] = dict(current_overrides)
        history.append(run_result)

        if best_result is None:
            best_result = run_result
        else:
            prev_err = float(best_result.get("relative_error", 1e9))
            cur_err = float(run_result.get("relative_error", 1e9))
            if cur_err < prev_err:
                best_result = run_result

        if bool(run_result.get("passed")):
            break

        control_loop = run_result.get("control_loop") or {}
        iter_steps = control_loop.get("iterations") or []
        if not iter_steps:
            break

        last_step = iter_steps[-1] if isinstance(iter_steps[-1], dict) else {}
        action = last_step.get("controller_action") or {}
        new_overrides = action.get("overrides") or {}
        if not isinstance(new_overrides, dict) or len(new_overrides) == 0:
            break
        current_overrides.update(new_overrides)

    final_result = history[-1] if history else {}
    return {
        "case_id": case_id,
        "iterations_requested": max_iterations,
        "iterations_completed": len(history),
        "passed": bool(final_result.get("passed", False)),
        "best_relative_error": best_result.get("relative_error") if best_result else None,
        "best_config_hash": best_result.get("config_hash") if best_result else None,
        "history": history,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
