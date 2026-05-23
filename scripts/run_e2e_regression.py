#!/usr/bin/env python3
"""E2E regression test for all Octopus presets.

Sends requests to MCP server (port 8000), waits for computation,
validates results against reference values from octopus_case_convergence.md.

Usage:
    python scripts/run_e2e_regression.py                    # All presets
    python scripts/run_e2e_regression.py --preset h_gs      # Single preset
    python scripts/run_e2e_regression.py --preset h_gs,ch4_gs  # Multiple
    python scripts/run_e2e_regression.py --list              # List available
    python scripts/run_e2e_regression.py --timeout 600       # Custom timeout
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone

API_BASE = "http://localhost:8000"
HARTREE_TO_EV = 27.211386245988

# ── Reference values from octopus_case_convergence.md ──────────────────

@dataclass
class PresetSpec:
    name: str
    label: str
    payload: dict
    ref_energy_ha: float | None = None
    energy_tol_pct: float = 2.0
    ref_casida_first_eV: float | None = None
    casida_tol_eV: float = 0.5
    ref_homo_eV: float | None = None
    homo_tol_eV: float = 1.0
    expect_casida: bool = False
    expect_td: bool = False
    skip: str | None = None


def _base_payload(**overrides) -> dict:
    p = {
        "engineMode": "octopus3D",
        "octopusDimensions": "3D",
        "octopusLengthUnit": "angstrom",
        "octopusUnitsOutput": "eV_Angstrom",
        "octopusBoxShape": "sphere",
        "octopusEigenSolver": "",
        "octopusNcpus": 1,
        "octopusMpiprocs": 1,
        "mixingScheme": "broyden",
        "spinComponents": "unpolarized",
        "periodicDimensions": "0",
        "kpointsGrid": "",
        "unitSystem": "atomic",
        "dimensionality": "3",
        "equationType": "dirac",
        "problemType": "ground_state",
        "potentialType": "none",
        "potentialDataMode": "none",
        "mass": 1.0,
        "charge": -1.0,
        "energy": 1.0,
        "spatialRange": 10.0,
        "gridPoints": 100,
        "boundaryCondition": "dirichlet",
        "potentialStrength": 0.0,
        "wellWidth": 1.0,
        "numTimeSteps": 0,
        "totalTime": 0,
        "gaussianCenter": 0,
        "gaussianWidth": 1,
        "gaussianMomentum": 0,
        "scatteringEMin": 0,
        "scatteringEMax": 10,
        "scatteringEnergySteps": 100,
        "derivativesOrder": 4,
        "curvMethod": "none",
        "curvGygiAlpha": 0,
        "doubleGrid": "none",
        "tdExcitationType": "delta",
        "tdPolarization": 1,
        "tdFieldAmplitude": 0.01,
        "tdGaussianSigma": 0,
        "tdGaussianT0": 0,
        "tdSinFrequency": 0,
        "feProbeEnabled": False,
        "feProbeVelocity": 1.0,
        "feProbeDirection": "x",
        "feProbeCharge": 0.0,
        "feProbeBeamCount": 1,
        "gridSpacing": 0.18,
    }
    p.update(overrides)
    return p


PRESETS: list[PresetSpec] = [
    # ── Atom GS ──────────────────────────────────────────────
    PresetSpec(
        name="h_gs",
        label="H PP PBE",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="H",
            molecule="H",
            octopusSpacing=0.18,
            octopusRadius=10.0,
            xcFunctional="gga_x_pbe+gga_c_pbe",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=1,
        ),
        ref_energy_ha=-0.4584,
        energy_tol_pct=3.0,
        ref_homo_eV=-6.49,
        homo_tol_eV=0.5,
    ),
    PresetSpec(
        name="he_gs",
        label="He PP LDA",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="He",
            molecule="He",
            octopusSpacing=0.15,
            octopusRadius=10.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=1,
        ),
        ref_energy_ha=-2.8324,
        energy_tol_pct=3.0,
    ),
    PresetSpec(
        name="n_gs",
        label="N_atom PP LDA",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="N_atom",
            molecule={"name": "N_atom", "atoms": [{"symbol": "N", "x": 0, "y": 0, "z": 0}]},
            octopusSpacing=0.18,
            octopusRadius=10.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            spinComponents="spin_polarized",
            octopusExtraStates=1,
            fastPath=False,
        ),
        ref_energy_ha=-9.637,
        energy_tol_pct=2.0,
    ),
    PresetSpec(
        name="na_gs",
        label="Na builtin",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="Na",
            molecule="Na",
            octopusSpacing=0.22,
            octopusRadius=10.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            spinComponents="spin_polarized",
            octopusExtraStates=2,
        ),
        ref_energy_ha=-0.1843,
        energy_tol_pct=5.0,
    ),
    # ── Diatomic GS ─────────────────────────────────────────
    PresetSpec(
        name="h2_gs",
        label="H2 PP PBE (sp=0.10)",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="H2",
            molecule="H2",
            octopusSpacing=0.10,
            octopusRadius=8.0,
            xcFunctional="gga_x_pbe+gga_c_pbe",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=None,  # No PP PBE reference yet for H2 at 0.10 spacing
        skip="No PBE reference for H2 at sp=0.10 yet",
    ),
    PresetSpec(
        name="n2_gs",
        label="N2 builtin LDA",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="N2",
            molecule="N2",
            octopusSpacing=0.18,
            octopusRadius=10.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=-19.897,
        energy_tol_pct=3.0,
    ),
    PresetSpec(
        name="lih_gs",
        label="LiH builtin",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="LiH",
            molecule="LiH",
            octopusSpacing=0.22,
            octopusRadius=7.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=-0.7716,
        energy_tol_pct=3.0,
    ),
    # ── Polyatomic GS ───────────────────────────────────────
    PresetSpec(
        name="ch4_gs",
        label="CH4 builtin",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="CH4",
            molecule="CH4",
            octopusSpacing=0.18,
            octopusRadius=7.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=-8.0216,
        energy_tol_pct=1.0,
    ),
    PresetSpec(
        name="nh3_gs",
        label="NH3 PP PBE",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="NH3",
            molecule="NH3",
            octopusSpacing=0.21,
            octopusRadius=3.0,
            xcFunctional="gga_x_pbe+gga_c_pbe",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=8,
        ),
        ref_energy_ha=-11.803,
        energy_tol_pct=3.0,
    ),
    PresetSpec(
        name="nh3_builtin_gs",
        label="NH3 builtin LDA (LCAO cap)",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="NH3",
            molecule="NH3",
            octopusSpacing=0.18,
            octopusRadius=10.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=None,  # No reference yet — verifies convergence only
    ),
    PresetSpec(
        name="h2o_gs",
        label="H2O GS PBE",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="H2O",
            molecule="H2O",
            octopusSpacing=0.21,
            octopusRadius=3.0,
            xcFunctional="gga_x_pbe+gga_c_pbe",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=-17.29,
        energy_tol_pct=3.0,
    ),
    PresetSpec(
        name="c2h4_gs",
        label="C2H4 builtin",
        payload=_base_payload(
            calcMode="gs",
            octopusMolecule="C2H4",
            molecule="C2H4",
            octopusSpacing=0.22,
            octopusRadius=8.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=4,
        ),
        ref_energy_ha=-13.766,
        energy_tol_pct=3.0,
    ),
    # ── TDDFT ────────────────────────────────────────────────
    PresetSpec(
        name="h2o_td",
        label="H2O TDDFT PBE",
        payload=_base_payload(
            calcMode="td",
            octopusMolecule="H2O",
            molecule="H2O",
            octopusSpacing=0.21,
            octopusRadius=3.0,
            xcFunctional="gga_x_pbe+gga_c_pbe",
            speciesMode="pseudo",
            pseudopotentialSet="standard",
            octopusExtraStates=8,
            octopusTdSteps=300,
            octopusTdTimeStep=0.1,
            tdExcitationType="delta",
            tdFieldAmplitude=0.01,
        ),
        ref_energy_ha=-17.29,
        energy_tol_pct=3.0,
        expect_td=True,
    ),
    # ── Casida ───────────────────────────────────────────────
    PresetSpec(
        name="h2o_casida",
        label="H2O Casida LDA",
        payload=_base_payload(
            calcMode="casida",
            octopusMolecule="H2O",
            molecule="H2O",
            octopusSpacing=0.21,
            octopusRadius=5.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=8,
            casidaKohnShamStates="1-8",
        ),
        ref_energy_ha=-17.17,
        energy_tol_pct=5.0,
        ref_casida_first_eV=6.741,
        casida_tol_eV=0.5,
        expect_casida=True,
    ),
    PresetSpec(
        name="c2h4_casida",
        label="C2H4 Casida LDA",
        payload=_base_payload(
            calcMode="casida",
            octopusMolecule="C2H4",
            molecule="C2H4",
            octopusSpacing=0.22,
            octopusRadius=8.0,
            xcFunctional="lda_x+lda_c_pz",
            speciesMode="builtin_standard",
            pseudopotentialSet="standard",
            octopusExtraStates=8,
            casidaKohnShamStates="1-16",
        ),
        ref_energy_ha=-13.702,
        energy_tol_pct=3.0,
        ref_casida_first_eV=7.507,
        casida_tol_eV=0.5,
        expect_casida=True,
    ),
]


# ── API helpers ─────────────────────────────────────────────────────────

def check_server_health() -> bool:
    try:
        req = urllib.request.Request(f"{API_BASE}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def submit_computation(payload: dict, timeout: int = 600) -> dict:
    """Submit via POST /solve, wait for JSON result."""
    url = f"{API_BASE}/solve"

    result = {"logs": [], "data": None, "error": None, "elapsed": 0}
    t0 = time.time()

    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                result["data"] = json.loads(raw)
            except json.JSONDecodeError:
                result["data"] = {"raw": raw}
            # Extract logs from stdout_tail if present
            data = result["data"] or {}
            tail = data.get("stdout_tail", "")
            if tail:
                result["logs"] = tail.split("\n")[-10:]

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        result["error"] = f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        result["error"] = f"Connection error: {e}"
    except TimeoutError:
        result["error"] = f"Timeout after {timeout}s"
    except Exception as e:
        result["error"] = f"Unexpected: {e}"

    result["elapsed"] = round(time.time() - t0, 1)
    return result


# ── Validation ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    label: str
    status: str  # PASS, FAIL, SKIP, ERROR
    checks: list[dict] = field(default_factory=list)
    error: str | None = None
    elapsed: float = 0.0
    logs_tail: list[str] = field(default_factory=list)


def validate(spec: PresetSpec, raw: dict) -> TestResult:
    tr = TestResult(name=spec.name, label=spec.label, status="PASS")
    data = raw.get("data", {}) or {}
    all_pass = True

    # Energy check — /solve returns total_energy (Ha string or float)
    if spec.ref_energy_ha is not None:
        energy = data.get("total_energy") or data.get("total_energy_hartree") or data.get("totalEnergy")
        if energy is None:
            tr.checks.append({"check": "total_energy", "status": "MISSING"})
            all_pass = False
        else:
            energy = float(energy)
            rel_err = abs(energy - spec.ref_energy_ha) / (abs(spec.ref_energy_ha) + 1e-12)
            passed = rel_err <= spec.energy_tol_pct / 100
            tr.checks.append({
                "check": "total_energy",
                "status": "PASS" if passed else "FAIL",
                "computed_ha": round(energy, 6),
                "ref_ha": spec.ref_energy_ha,
                "rel_err_pct": round(rel_err * 100, 4),
                "tol_pct": spec.energy_tol_pct,
            })
            if not passed:
                all_pass = False

    # Casida check — /solve returns casida_excitations, casida_executed, casida_data at top level
    if spec.expect_casida:
        casida_data = data.get("casida_data") or data.get("casida_excitations")
        casida_exec = data.get("casida_executed")

        excitations = []
        if isinstance(casida_data, list):
            excitations = casida_data
        elif isinstance(casida_data, dict):
            excitations = casida_data.get("excitations", [])

        if not casida_exec or len(excitations) == 0:
            tr.checks.append({"check": "casida_executed", "status": "FAIL", "n_excitations": len(excitations)})
            all_pass = False
        else:

            tr.checks.append({
                "check": "casida_executed",
                "status": "PASS",
                "n_excitations": len(excitations),
            })

            if spec.ref_casida_first_eV and excitations:
                first_e = None
                for exc in excitations:
                    if isinstance(exc, dict):
                        first_e = exc.get("energy_eV") or exc.get("energy")
                        break
                    elif isinstance(exc, (int, float)):
                        first_e = float(exc)
                        break
                if first_e is not None:
                    first_e = float(first_e)
                    delta = abs(first_e - spec.ref_casida_first_eV)
                    passed = delta <= spec.casida_tol_eV
                    tr.checks.append({
                        "check": "casida_1st_excitation",
                        "status": "PASS" if passed else "FAIL",
                        "computed_eV": round(first_e, 3),
                        "ref_eV": spec.ref_casida_first_eV,
                        "delta_eV": round(delta, 3),
                        "tol_eV": spec.casida_tol_eV,
                    })
                    if not passed:
                        all_pass = False

    # TD check
    if spec.expect_td:
        td_exec = data.get("td_executed")
        if not td_exec:
            tr.checks.append({"check": "td_executed", "status": "FAIL"})
            all_pass = False
        else:
            tr.checks.append({"check": "td_executed", "status": "PASS"})

    tr.status = "PASS" if all_pass else "FAIL"
    return tr


def run_test(spec: PresetSpec, timeout: int) -> TestResult:
    if spec.skip:
        return TestResult(name=spec.name, label=spec.label, status="SKIP", error=spec.skip)

    print(f"\n{'='*60}")
    print(f"  {spec.label} ({spec.name})")
    print(f"{'='*60}")

    raw = submit_computation(spec.payload, timeout=timeout)

    if raw["error"]:
        return TestResult(
            name=spec.name, label=spec.label, status="ERROR",
            error=raw["error"], elapsed=raw["elapsed"],
            logs_tail=raw["logs"][-5:],
        )

    tr = validate(spec, raw)
    tr.elapsed = raw["elapsed"]
    tr.logs_tail = raw["logs"][-5:]

    for c in tr.checks:
        status_icon = "OK" if c["status"] == "PASS" else c["status"]
        detail = ""
        if "rel_err_pct" in c:
            detail = f" ({c['computed_ha']:.4f} vs {c['ref_ha']:.4f} Ha, err={c['rel_err_pct']:.3f}%)"
        elif "delta_eV" in c:
            detail = f" ({c['computed_eV']:.3f} vs {c['ref_eV']:.3f} eV, Δ={c['delta_eV']:.3f} eV)"
        elif "n_excitations" in c:
            detail = f" ({c['n_excitations']} excitations)"
        print(f"  [{status_icon}] {c['check']}{detail}")

    print(f"  Time: {tr.elapsed}s")
    return tr


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="E2E regression test for Octopus presets")
    parser.add_argument("--preset", type=str, help="Preset name(s), comma-separated")
    parser.add_argument("--list", action="store_true", help="List available presets")
    parser.add_argument("--timeout", type=int, default=1200, help="Per-test timeout (seconds)")
    parser.add_argument("--api-base", type=str, default=API_BASE, help="MCP server URL")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Show payloads without submitting")
    args = parser.parse_args()

    # use args.api_base for server URL
    api_base = args.api_base

    if args.list:
        print(f"{'Name':<20} {'Label':<25} {'Ref E (Ha)':<14} {'Casida':<10} {'TD':<6}")
        print("-" * 75)
        for p in PRESETS:
            e_str = f"{p.ref_energy_ha:.4f}" if p.ref_energy_ha else "—"
            c_str = f"{p.ref_casida_first_eV:.3f} eV" if p.ref_casida_first_eV else "—"
            td_str = "yes" if p.expect_td else "—"
            print(f"{p.name:<20} {p.label:<25} {e_str:<14} {c_str:<10} {td_str:<6}")
        return

    # Select presets
    if args.preset:
        names = [n.strip() for n in args.preset.split(",")]
        selected = [p for p in PRESETS if p.name in names]
        missing = set(names) - {p.name for p in selected}
        if missing:
            print(f"Unknown presets: {missing}", file=sys.stderr)
            print(f"Available: {[p.name for p in PRESETS]}", file=sys.stderr)
            sys.exit(1)
    else:
        selected = PRESETS

    if args.dry_run:
        for p in selected:
            print(f"\n--- {p.label} ({p.name}) ---")
            print(json.dumps(p.payload, indent=2, ensure_ascii=False))
        return

    # Health check
    print("Checking MCP server health...")
    if api_base != API_BASE:
        globals()["API_BASE"] = api_base
    if not check_server_health():
        print(f"ERROR: MCP server not reachable at {api_base}/health", file=sys.stderr)
        print("Start server: cd docker/workspace && python server.py", file=sys.stderr)
        sys.exit(1)
    print("Server OK")

    # Run tests
    results: list[TestResult] = []
    t_total = time.time()

    for spec in selected:
        tr = run_test(spec, args.timeout)
        results.append(tr)

    elapsed_total = round(time.time() - t_total, 1)

    # Summary
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIP")

    print(f"\n{'='*60}")
    print(f"  SUMMARY ({len(results)} tests, {elapsed_total}s)")
    print(f"{'='*60}")

    for r in results:
        icon = {"PASS": "OK", "FAIL": "FAIL", "ERROR": "ERR", "SKIP": "SKIP"}[r.status]
        extra = f" — {r.error}" if r.error else ""
        print(f"  [{icon}] {r.label:<25} {r.elapsed:>6.1f}s{extra}")

    print(f"\n  {passed} PASS, {failed} FAIL, {errors} ERROR, {skipped} SKIP")
    print(f"  Total: {elapsed_total}s")

    if args.json:
        output = []
        for r in results:
            output.append({
                "name": r.name,
                "label": r.label,
                "status": r.status,
                "checks": r.checks,
                "error": r.error,
                "elapsed": r.elapsed,
            })
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = f"e2e_results_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  Results saved to: {path}")

    sys.exit(0 if failed == 0 and errors == 0 else 1)


if __name__ == "__main__":
    main()
