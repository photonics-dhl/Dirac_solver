#!/usr/bin/env python3
"""Search benchmark parameter combinations and report best computed results."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "harness_reports"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _default_case_matrix() -> List[Dict[str, Any]]:
    return [
        {
            "case_id": "hydrogen_gs_reference",
            "molecule": "H",
            "calc_mode": "gs",
            "combos": [
                {"name": "h_default", "args": []},
                {
                    "name": "h_num_refine_1",
                    "args": [
                        "--octopus-spacing",
                        "0.2",
                        "--octopus-radius",
                        "8.0",
                        "--octopus-max-scf-iterations",
                        "320",
                        "--octopus-scf-tolerance",
                        "1e-8",
                    ],
                },
                {
                    "name": "h_num_refine_2",
                    "args": [
                        "--octopus-spacing",
                        "0.18",
                        "--octopus-radius",
                        "8.0",
                        "--octopus-max-scf-iterations",
                        "420",
                        "--octopus-scf-tolerance",
                        "1e-9",
                    ],
                },
                {"name": "h_model_pbe", "args": ["--octopus-xc", "pbe"]},
                {"name": "h_model_lda", "args": ["--octopus-xc", "lda"]},
                {
                    "name": "h_model_mix",
                    "args": [
                        "--octopus-xc",
                        "pbe",
                        "--octopus-propagator",
                        "aetrs",
                        "--octopus-spacing",
                        "0.2",
                        "--octopus-radius",
                        "8.0",
                    ],
                },
            ],
        },
        {
            "case_id": "h2o_gs_reference",
            "molecule": "H2O",
            "calc_mode": "gs",
            "combos": [
                {"name": "w_default", "args": []},
                {
                    "name": "w_num_refine_1",
                    "args": [
                        "--octopus-spacing",
                        "0.3",
                        "--octopus-radius",
                        "5.0",
                        "--octopus-max-scf-iterations",
                        "320",
                        "--octopus-scf-tolerance",
                        "1e-8",
                    ],
                },
                {
                    "name": "w_num_refine_2",
                    "args": [
                        "--octopus-spacing",
                        "0.25",
                        "--octopus-radius",
                        "6.0",
                        "--octopus-max-scf-iterations",
                        "420",
                        "--octopus-scf-tolerance",
                        "1e-8",
                    ],
                },
                {"name": "w_model_pbe", "args": ["--octopus-xc", "pbe"]},
                {"name": "w_model_lda", "args": ["--octopus-xc", "lda"]},
                {
                    "name": "w_model_mix",
                    "args": [
                        "--octopus-xc",
                        "pbe",
                        "--octopus-spacing",
                        "0.3",
                        "--octopus-radius",
                        "5.0",
                    ],
                },
            ],
        },
    ]


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_report_path(stdout: str) -> Optional[str]:
    match = re.search(r"multi_agent_report_json=(.+)", stdout or "")
    if not match:
        return None
    return match.group(1).strip()


def _combo_params_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "octopusSpacing": config.get("octopusSpacing"),
        "octopusRadius": config.get("octopusRadius"),
        "octopusMaxScfIterations": config.get("octopusMaxScfIterations"),
        "octopusScfTolerance": config.get("octopusScfTolerance"),
        "octopusXC": config.get("octopusXC"),
        "octopusPropagator": config.get("octopusPropagator"),
        "octopusPseudopotentialSet": config.get("octopusPseudopotentialSet"),
        "octopusExtraStates": config.get("octopusExtraStates"),
    }


def _evaluate_run(report: Dict[str, Any]) -> Dict[str, Any]:
    executor = report.get("executor") if isinstance(report.get("executor"), dict) else {}
    reviewer = report.get("reviewer") if isinstance(report.get("reviewer"), dict) else {}

    physics = executor.get("physics_result") if isinstance(executor.get("physics_result"), dict) else {}
    benchmark = executor.get("benchmark_review") if isinstance(executor.get("benchmark_review"), dict) else {}
    delta = benchmark.get("delta") if isinstance(benchmark.get("delta"), dict) else {}

    octopus = executor.get("octopus") if isinstance(executor.get("octopus"), dict) else {}
    oct_result = octopus.get("result") if isinstance(octopus.get("result"), dict) else {}
    config = oct_result.get("config") if isinstance(oct_result.get("config"), dict) else {}

    rel_error = delta.get("relative_error")
    energy = physics.get("ground_state_energy_hartree")
    threshold = delta.get("threshold")

    return {
        "relative_error": float(rel_error) if isinstance(rel_error, (int, float)) else None,
        "ground_state_energy_hartree": float(energy) if isinstance(energy, (int, float)) else None,
        "threshold": float(threshold) if isinstance(threshold, (int, float)) else None,
        "within_tolerance": bool(delta.get("within_tolerance", False)),
        "reviewer_verdict": str(reviewer.get("final_verdict") or ""),
        "next_action": str(benchmark.get("next_action") or ""),
        "mcp_passed": bool((executor.get("mcp") or {}).get("passed", False)) if isinstance(executor.get("mcp"), dict) else False,
        "effective_params": _combo_params_from_config(config),
    }


def _sort_key(item: Dict[str, Any]) -> Tuple[float, int, int]:
    rel_error = item.get("relative_error")
    if not isinstance(rel_error, (int, float)):
        return (float("inf"), 1, 1)
    params = item.get("effective_params") if isinstance(item.get("effective_params"), dict) else {}
    param_coverage = sum(1 for value in params.values() if value is not None and str(value).strip() != "")
    return (
        float(rel_error),
        0 if bool(item.get("within_tolerance", False)) else 1,
        0 if str(item.get("reviewer_verdict") or "").upper() == "PASS" else 1,
        -int(param_coverage),
    )


def _load_historical_rows(case_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    pattern = f"multi_agent_orchestration_{case_id}_*.json"
    candidates = sorted(DEFAULT_OUTPUT_DIR.glob(pattern), reverse=True)
    rows: List[Dict[str, Any]] = []
    for path in candidates[: max(1, int(limit))]:
        report = _read_json(path)
        evaluation = _evaluate_run(report)
        rows.append(
            {
                "case_id": case_id,
                "combo_name": f"historical::{path.stem}",
                "combo_args": [],
                "exit_code": 0,
                "timed_out": False,
                "stderr": "",
                "report_path": path.as_posix(),
                "source": "historical_artifact",
                **evaluation,
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search benchmark parameter combinations via orchestration runs.")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001")
    parser.add_argument("--harness-base", default="http://127.0.0.1:8101")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--python-bin", default=sys.executable, help="Python executable used to run orchestration.")
    parser.add_argument("--orchestration-script", default="scripts/run_multi_agent_orchestration.py")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--per-run-timeout",
        type=int,
        default=240,
        help="Timeout seconds for one orchestration attempt.",
    )
    parser.add_argument(
        "--max-combos-per-case",
        type=int,
        default=0,
        help="If >0, only run first N combos for each case.",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Skip live orchestration runs and select best from historical artifacts only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, Any]] = []
    case_matrix = _default_case_matrix()

    for case_info in case_matrix:
        case_id = str(case_info["case_id"])
        molecule = str(case_info["molecule"])
        calc_mode = str(case_info["calc_mode"])
        combos = case_info["combos"]
        if args.max_combos_per_case > 0:
            combos = combos[: int(args.max_combos_per_case)]

        if args.skip_live:
            continue

        for combo in combos:
            combo_name = str(combo["name"])
            combo_args = list(combo["args"])

            cmd = [
                args.python_bin,
                args.orchestration_script,
                "--api-base",
                args.api_base,
                "--harness-base",
                args.harness_base,
                "--case-id",
                case_id,
                "--max-iterations",
                str(args.max_iterations),
                "--octopus-molecule",
                molecule,
                "--octopus-calc-mode",
                calc_mode,
                "--timeout",
                str(args.timeout),
            ] + combo_args

            timed_out = False
            timeout_seconds = max(60, int(args.per_run_timeout))
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                exit_code = int(proc.returncode)
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = str(exc.stdout or "")
                stderr = str(exc.stderr or "")
                exit_code = 124
            report_path_raw = _extract_report_path(stdout)
            report_path = Path(report_path_raw) if report_path_raw else None
            if report_path and not report_path.is_absolute():
                report_path = REPO_ROOT / report_path

            report_data: Dict[str, Any] = {}
            if report_path and report_path.exists():
                report_data = _read_json(report_path)

            evaluation = _evaluate_run(report_data)
            all_rows.append(
                {
                    "case_id": case_id,
                    "combo_name": combo_name,
                    "combo_args": combo_args,
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "stderr": stderr,
                    "report_path": report_path.as_posix() if report_path else "",
                    **evaluation,
                }
            )

    results_by_case: Dict[str, Dict[str, Any]] = {}
    known_case_ids = sorted({str(case["case_id"]) for case in case_matrix})
    for case_id in known_case_ids:
        valid_rows = [
            row
            for row in all_rows
            if row["case_id"] == case_id and isinstance(row.get("relative_error"), (int, float)) and row["relative_error"] >= 0
        ]
        if not valid_rows:
            historical_rows = _load_historical_rows(case_id)
            valid_rows = [
                row
                for row in historical_rows
                if isinstance(row.get("relative_error"), (int, float)) and row["relative_error"] >= 0
            ]
        valid_rows.sort(key=_sort_key)
        best = valid_rows[0] if valid_rows else None
        results_by_case[case_id] = {
            "best": best,
            "top": valid_rows[: max(1, int(args.top_k))],
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "api_base": args.api_base,
        "harness_base": args.harness_base,
        "rows": all_rows,
        "results_by_case": results_by_case,
    }

    out_path = output_dir / f"benchmark_param_search_{utc_stamp()}.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")

    for case_id, payload in results_by_case.items():
        best = payload.get("best")
        if not isinstance(best, dict):
            print(f"RESULT case={case_id} status=NO_VALID_RUN")
            continue
        print(
            "RESULT "
            f"case={case_id} "
            f"combo={best.get('combo_name')} "
            f"energy={best.get('ground_state_energy_hartree')} "
            f"relative_error={best.get('relative_error')} "
            f"within_tolerance={best.get('within_tolerance')} "
            f"report={best.get('report_path')}"
        )
    print(f"summary_json={out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
