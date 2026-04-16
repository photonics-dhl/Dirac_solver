#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

HARTREE_TO_EV = 27.211386245988
REF_TOTAL_ENERGY_HA = -0.5
REF_TOTAL_ENERGY_EV = REF_TOTAL_ENERGY_HA * HARTREE_TO_EV
REF_URL = "https://physics.nist.gov/cgi-bin/cuu/Value?rydhcev"
REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "harness_reports" / "octopus_case_optimal_parameters_20260413.md"


def post_json(url: str, payload: dict, timeout: int) -> dict:
    req = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def get_total_ha(result: dict) -> float | None:
    molecular = result.get("molecular") or {}
    total = result.get("total_energy")
    if total is None:
        total = molecular.get("total_energy_hartree")
    try:
        return float(total) if total is not None else None
    except Exception:
        return None


def step2_backend_verify(api_base: str, timeout: int) -> dict:
    payload = {
        "engineMode": "octopus3D",
        "calcMode": "gs",
        "octopusCalcMode": "gs",
        "caseType": "dft_gs_3d",
        "octopusDimensions": "3D",
        "octopusPeriodic": "off",
        "octopusBoxShape": "sphere",
        "octopusMolecule": "H",
        "molecule": "H",
        "speciesMode": "all_electron",
        "allElectronType": "full_gaussian",
        "potentialType": "Coulomb",
        "potentialStrength": 1,
        "octopusSpacing": 0.12,
        "octopusRadius": 12.0,
        "equationType": "Schrodinger",
        "problemType": "boundstate",
        "skipRunExplanation": True,
        "fastPath": False,
        "octopusMaxScfIterations": 260,
        "octopusScfTolerance": 1e-6,
    }
    result = post_json(f"{api_base}/api/physics/run", payload, timeout)
    total_ha = get_total_ha(result)
    return {
        "payload": payload,
        "result": result,
        "total_energy_hartree": total_ha,
        "total_energy_ev": (total_ha * HARTREE_TO_EV) if total_ha is not None else None,
        "relative_delta": (abs(total_ha - REF_TOTAL_ENERGY_HA) / abs(REF_TOTAL_ENERGY_HA)) if total_ha is not None else None,
    }


def step3_frontend_verify(api_base: str, timeout: int) -> dict:
    payload = {
        "engineMode": "octopus3D",
        "calcMode": "gs",
        "octopusCalcMode": "gs",
        "caseType": "dft_gs_3d",
        "octopusDimensions": "3D",
        "speciesMode": "all_electron",
        "allElectronType": "full_gaussian",
        "potentialType": "Coulomb",
        "potentialStrength": 1,
        "octopusLengthUnit": "angstrom",
        "octopusUnitsOutput": "eV_Angstrom",
        "octopusSpacing": 0.12,
        "octopusRadius": 12.0,
        "octopusBoxShape": "sphere",
        "octopusExtraStates": 4,
        "spinComponents": "unpolarized",
        "fastPath": False,
        "octopusNcpus": 32,
        "octopusMpiprocs": 32,
        "molecule": "H",
        "octopusMolecule": "H",
    }
    result = post_json(f"{api_base}/api/physics/run", payload, timeout)
    total_ha = get_total_ha(result)
    return {
        "payload": payload,
        "result": result,
        "total_energy_hartree": total_ha,
        "total_energy_ev": (total_ha * HARTREE_TO_EV) if total_ha is not None else None,
        "relative_delta": (abs(total_ha - REF_TOTAL_ENERGY_HA) / abs(REF_TOTAL_ENERGY_HA)) if total_ha is not None else None,
    }


def append_doc(api_base: str, step2: dict, step3: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    e2 = step2.get("total_energy_hartree")
    e3 = step3.get("total_energy_hartree")
    inter_delta_ev = ((e3 - e2) * HARTREE_TO_EV) if (e2 is not None and e3 is not None) else None
    step2_ok = step2.get("relative_delta") is not None and step2["relative_delta"] <= 0.15
    step3_ok = step3.get("relative_delta") is not None and step3["relative_delta"] <= 0.15
    match_ok = inter_delta_ev is not None and abs(inter_delta_ev) <= 0.2
    completed = bool(match_ok)
    ref_aligned_strict = bool((step2.get("relative_delta") is not None and step2["relative_delta"] <= 0.03) and (step3.get("relative_delta") is not None and step3["relative_delta"] <= 0.03))

    lines = []
    lines.append(f"## 10) Hydrogen 三步法验证记录 (Coulomb all-electron, {now})")
    lines.append("")
    lines.append("- Step1 (检索):")
    lines.append(f"  - Reference source: {REF_URL}")
    lines.append(f"  - Target: {REF_TOTAL_ENERGY_HA:.6f} Ha ({REF_TOTAL_ENERGY_EV:.6f} eV)")
    lines.append("- Step2 (后端求解验证): backend-profile payload 调用 `/api/physics/run` (Coulomb + all_electron)")
    lines.append("- Step3 (前端发起复核): frontend-equivalent payload 调用 `/api/physics/run` (同一物理设定)")
    lines.append(f"- API base: `{api_base}`")
    lines.append("")
    lines.append("| Step | total_energy (Ha) | total_energy (eV) | rel.delta vs ref | within 15% |")
    lines.append("|---|---:|---:|---:|:---:|")
    lines.append(f"| Step2 Backend | {e2 if e2 is not None else 'N/A'} | {step2.get('total_energy_ev') if step2.get('total_energy_ev') is not None else 'N/A'} | {step2.get('relative_delta') if step2.get('relative_delta') is not None else 'N/A'} | {'Y' if step2_ok else 'N'} |")
    lines.append(f"| Step3 Frontend | {e3 if e3 is not None else 'N/A'} | {step3.get('total_energy_ev') if step3.get('total_energy_ev') is not None else 'N/A'} | {step3.get('relative_delta') if step3.get('relative_delta') is not None else 'N/A'} | {'Y' if step3_ok else 'N'} |")
    lines.append("")
    lines.append(f"- Inter-step delta (Step3-Step2): {inter_delta_ev:.6f} eV" if inter_delta_ev is not None else "- Inter-step delta (Step3-Step2): N/A")
    lines.append(f"- Workflow completion verdict (backend/frontend consistency): {'COMPLETED' if completed else 'NOT_COMPLETED'}")
    lines.append(f"- Strict reference alignment (<=3% both steps): {'ALIGNED' if ref_aligned_strict else 'NOT_ALIGNED'}")
    lines.append("")

    existing = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    DOC_PATH.write_text(existing.rstrip() + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hydrogen 3-step validation flow")
    parser.add_argument("--api-base", default="http://10.72.212.33:3001")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    api_base = str(args.api_base).rstrip("/")

    try:
        step2 = step2_backend_verify(api_base, max(30, int(args.timeout)))
        step3 = step3_frontend_verify(api_base, max(30, int(args.timeout)))
        append_doc(api_base, step2, step3)
        print(json.dumps({"ok": True, "step2": step2.get("total_energy_hartree"), "step3": step3.get("total_energy_hartree")}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
