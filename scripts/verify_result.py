#!/usr/bin/env python3
"""Verify Octopus calculation results against Dirac reference database.

Usage:
    python scripts/verify_result.py --result result.json
    python scripts/verify_result.py --case-id n_atom_gs_official --energy -9.637 --eigenvalues -0.672,-0.268
    python scripts/verify_result.py --case-id ch4_gs_official --energy -8.0213
    python scripts/verify_result.py --batch results/*.json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "knowledge_base" / "dirac_ref.db"

HARTREE_TO_EV = 27.211386245988


def get_connection(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}. Run build_reference_db.py first.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def verify_single(
    conn: sqlite3.Connection,
    case_id: str,
    computed_energy: float | None,
    eigenvalues: list[float] | None = None,
) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case = cur.fetchone()
    if not case:
        return {"case_id": case_id, "status": "ERROR", "error": f"Case not found: {case_id}"}

    cur.execute("SELECT * FROM energies WHERE case_id = ?", (case['id'],))
    ref_energies = cur.fetchall()

    checks = []
    overall_pass = True

    if computed_energy is not None:
        for ref in ref_energies:
            if ref['quantity'] == 'total_energy':
                ref_val = ref['value_hartree']
                error = abs(computed_energy - ref_val) / (abs(ref_val) + 1e-12)
                passed = error <= ref['tolerance_relative']
                if not passed:
                    overall_pass = False
                checks.append({
                    "type": "total_energy",
                    "computed_ha": round(computed_energy, 6),
                    "computed_ev": round(computed_energy * HARTREE_TO_EV, 3),
                    "reference_ha": ref_val,
                    "reference_ev": ref['value_ev'],
                    "relative_error": round(error, 6),
                    "tolerance": ref['tolerance_relative'],
                    "passed": passed,
                    "source": ref['source'],
                })

    if eigenvalues:
        for ref in ref_energies:
            if ref['quantity'] == 'eigenvalue':
                orbital = ref['orbital_label']
                label_map = {"1s": 0, "2s": 0, "2p": 1, "3s": 2, "3p": 2}
                idx = label_map.get(orbital, 0)
                if idx < len(eigenvalues):
                    calc_val = float(eigenvalues[idx])
                    ref_val = ref['value_hartree']
                    error = abs(calc_val - ref_val) / (abs(ref_val) + 1e-12)
                    passed = error <= ref['tolerance_relative']
                    if not passed:
                        overall_pass = False
                    checks.append({
                        "type": "eigenvalue",
                        "orbital": orbital,
                        "computed_ha": round(calc_val, 6),
                        "reference_ha": ref_val,
                        "nist_reference_ha": ref['nist_reference_hartree'],
                        "relative_error": round(error, 6),
                        "tolerance": ref['tolerance_relative'],
                        "passed": passed,
                    })

    return {
        "case_id": case_id,
        "formula": case['formula'],
        "species_mode": case['species_mode'],
        "confidence_tier": case['confidence_tier'],
        "status": "PASS" if overall_pass else "FAIL",
        "checks": checks,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_from_json(conn: sqlite3.Connection, result_path: Path) -> dict:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    case_id = result.get("case_id", "").strip()

    if not case_id:
        mol = result.get("molecule", result.get("formula", ""))
        cur = conn.cursor()
        cur.execute("SELECT case_id FROM cases WHERE formula = ? LIMIT 1", (mol,))
        row = cur.fetchone()
        if row:
            case_id = row['case_id']
        else:
            return {"case_id": case_id or mol, "status": "ERROR", "error": f"No matching case for molecule '{mol}'"}

    energy = result.get("total_energy_hartree") or result.get("total_energy")
    if energy is None:
        evals = result.get("eigenvalues", [])
        if evals:
            energy = float(evals[0])

    eigenvalues = result.get("eigenvalues", [])
    if eigenvalues:
        eigenvalues = [float(e) for e in eigenvalues]

    return verify_single(conn, case_id, float(energy) if energy is not None else None, eigenvalues)


def verify_batch(conn: sqlite3.Connection, result_paths: list[Path]) -> list[dict]:
    results = []
    for path in result_paths:
        try:
            r = verify_from_json(conn, path)
            r["source_file"] = str(path)
            results.append(r)
        except Exception as exc:
            results.append({"source_file": str(path), "status": "ERROR", "error": str(exc)})
    return results


def print_verdict(result: dict):
    status = result.get("status", "ERROR")
    case_id = result.get("case_id", "?")
    formula = result.get("formula", "?")

    if status == "PASS":
        print(f"  {case_id} ({formula}): PASS")
    elif status == "FAIL":
        print(f"  {case_id} ({formula}): FAIL")
    else:
        print(f"  {case_id} ({formula}): {status} - {result.get('error', '')}")

    for check in result.get("checks", []):
        check_type = check['type']
        if check_type == 'total_energy':
            print(f"    Energy: {check['computed_ha']:.6f} Ha vs {check['reference_ha']:.6f} Ha (err={check['relative_error']*100:.4f}%, tol={check['tolerance']*100:.1f}%) {'PASS' if check['passed'] else 'FAIL'}")
        elif check_type == 'eigenvalue':
            nist_str = f" (NIST: {check['nist_reference_ha']:.6f} Ha)" if check.get('nist_reference_ha') else ""
            print(f"    {check['orbital']}: {check['computed_ha']:.6f} Ha vs {check['reference_ha']:.6f} Ha (err={check['relative_error']*100:.4f}%){nist_str} {'PASS' if check['passed'] else 'FAIL'}")


def main():
    parser = argparse.ArgumentParser(description="Verify Octopus results against Dirac reference DB")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--result", type=Path, help="JSON result file from Octopus")
    parser.add_argument("--batch", type=Path, nargs="+", help="Batch verify multiple result files")
    parser.add_argument("--case-id", type=str, help="Case ID to verify against")
    parser.add_argument("--energy", type=float, help="Computed total energy in Hartree")
    parser.add_argument("--eigenvalues", type=str, help="Comma-separated eigenvalues in Hartree")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    conn = get_connection(args.db_path)

    if args.batch:
        results = verify_batch(conn, args.batch)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            passed = sum(1 for r in results if r.get("status") == "PASS")
            failed = sum(1 for r in results if r.get("status") == "FAIL")
            errors = sum(1 for r in results if r.get("status") == "ERROR")
            for r in results:
                print_verdict(r)
            print(f"\nSummary: {passed} PASS, {failed} FAIL, {errors} ERROR (total: {len(results)})")
    elif args.result:
        result = verify_from_json(conn, args.result)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_verdict(result)
    elif args.case_id:
        eigenvalues = None
        if args.eigenvalues:
            eigenvalues = [float(e.strip()) for e in args.eigenvalues.split(",")]
        result = verify_single(conn, args.case_id, args.energy, eigenvalues)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print_verdict(result)
    else:
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
