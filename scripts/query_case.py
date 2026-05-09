#!/usr/bin/env python3
"""Query the Dirac reference database.

Usage:
    python scripts/query_case.py --case-id n_atom_gs_official
    python scripts/query_case.py --formula CH4
    python scripts/query_case.py --list-all
    python scripts/query_case.py --tier A-ready
    python scripts/query_case.py --category dft_gs_3d
    python scripts/query_case.py --verify octopus_output.json
"""

import argparse
import json
import sqlite3
import sys
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


def list_all(conn: sqlite3.Connection, tier: str | None = None, category: str | None = None):
    query = """
        SELECT c.case_id, c.formula, c.category, c.species_mode, c.confidence_tier,
               c.description, c.source_url, c.updated_at
        FROM cases c
        WHERE 1=1
    """
    params = []
    if tier:
        query += " AND c.confidence_tier = ?"
        params.append(tier)
    if category:
        query += " AND c.category = ?"
        params.append(category)
    query += " ORDER BY c.formula, c.case_id"

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    print(f"{'CASE ID':<35} {'FORMULA':<8} {'MODE':<20} {'TIER':<18} {'CATEGORY':<15}")
    print("-" * 100)
    for row in rows:
        print(f"{row['case_id']:<35} {row['formula']:<8} {row['species_mode']:<20} {row['confidence_tier']:<18} {row['category']:<15}")
    print(f"\n{len(rows)} cases found.")


def show_case(conn: sqlite3.Connection, case_id: str):
    cur = conn.cursor()

    cur.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case = cur.fetchone()
    if not case:
        print(f"Case '{case_id}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Case: {case['case_id']}")
    print(f"{'='*60}")
    print(f"  Formula:        {case['formula']}")
    print(f"  Category:       {case['category']}")
    print(f"  Calculation:    {case['calculation_mode']}")
    print(f"  Species Mode:   {case['species_mode']}")
    print(f"  XC Functional:  {case['xc_functional'] or 'N/A'}")
    print(f"  Confidence:     {case['confidence_tier']}")
    print(f"  Description:    {case['description']}")
    print(f"  Source URL:     {case['source_url'] or 'N/A'}")

    # Energies
    cur.execute("SELECT * FROM energies WHERE case_id = ?", (case['id'],))
    energies = cur.fetchall()
    if energies:
        print(f"\n  Reference Energies:")
        for e in energies:
            nist_info = ""
            if e['nist_reference_hartree']:
                nist_info = f" (NIST: {e['nist_reference_hartree']} Ha, match: {e['nist_match_percent']}%)"
            print(f"    {e['quantity']}: {e['value_hartree']} Ha ({e['value_ev']} eV) [{e['orbital_label'] or 'total'}] tol={e['tolerance_relative']}{nist_info}")

    # Parameters
    cur.execute("SELECT * FROM parameters WHERE case_id = ? ORDER BY is_critical DESC", (case['id'],))
    params = cur.fetchall()
    if params:
        print(f"\n  Parameters:")
        for p in params:
            unit_str = f" [{p['unit']}]" if p['unit'] else ""
            crit = " *" if p['is_critical'] else ""
            print(f"    {p['param_name']}: {p['param_value']}{unit_str}{crit}")

    # Provenance
    cur.execute("SELECT * FROM provenance WHERE case_id = ?", (case['id'],))
    provs = cur.fetchall()
    if provs:
        print(f"\n  Provenance:")
        for p in provs:
            print(f"    [{p['source_type']}] {p['source_name']}")
            if p['source_url']:
                print(f"      URL: {p['source_url']}")
            if p['citation']:
                print(f"      Citation: {p['citation']}")
            if p['doi']:
                print(f"      DOI: {p['doi']}")

    # Properties
    cur.execute("SELECT * FROM properties WHERE case_id = ?", (case['id'],))
    props = cur.fetchall()
    if props:
        print(f"\n  Properties:")
        for p in props:
            unit_str = f" [{p['unit']}]" if p['unit'] else ""
            method_str = f" ({p['methodology']})" if p['methodology'] else ""
            print(f"    {p['property_name']}: {p['property_value']}{unit_str}{method_str}")

    print()


def verify_result(conn: sqlite3.Connection, result_path: Path):
    """Verify an Octopus output JSON against the reference database."""
    if not result_path.exists():
        print(f"Error: Result file not found: {result_path}", file=sys.stderr)
        sys.exit(1)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    case_id = result.get("case_id", "").strip()

    cur = conn.cursor()
    cur.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
    case = cur.fetchone()
    if not case:
        # Try matching by formula/species
        mol = result.get("molecule", result.get("formula", ""))
        cur.execute("SELECT * FROM cases WHERE formula = ? LIMIT 1", (mol,))
        case = cur.fetchone()
        if not case:
            print(f"Error: No matching case found for '{case_id}' or molecule '{mol}'", file=sys.stderr)
            sys.exit(1)

    cur.execute("SELECT * FROM energies WHERE case_id = ?", (case['id'],))
    ref_energies = cur.fetchall()

    computed_energy = result.get("total_energy_hartree") or result.get("total_energy")
    if computed_energy is None:
        eigenvalues = result.get("eigenvalues", [])
        if eigenvalues:
            computed_energy = float(eigenvalues[0])

    if computed_energy is None:
        print("Error: No energy value found in result file", file=sys.stderr)
        sys.exit(1)

    computed_energy = float(computed_energy)

    print(f"\nVerification: {case['case_id']} ({case['formula']})")
    print(f"  Computed energy: {computed_energy:.6f} Ha ({computed_energy * HARTREE_TO_EV:.3f} eV)")

    for ref in ref_energies:
        if ref['quantity'] == 'total_energy':
            ref_val = ref['value_hartree']
            error = abs(computed_energy - ref_val) / (abs(ref_val) + 1e-12)
            passed = error <= ref['tolerance_relative']
            status = "PASS" if passed else "FAIL"
            print(f"  Reference:       {ref_val:.6f} Ha (tol: {ref['tolerance_relative']*100:.1f}%)")
            print(f"  Relative error:  {error*100:.4f}%")
            print(f"  Status:          {status}")

    # Also check eigenvalues if available
    eigenvalues = result.get("eigenvalues", [])
    if eigenvalues:
        print(f"\n  Eigenvalue check:")
        cur.execute(
            "SELECT * FROM energies WHERE case_id = ? AND quantity = 'eigenvalue'",
            (case['id'],),
        )
        ref_evals = cur.fetchall()
        for ref_eval in ref_evals:
            orbital = ref_eval['orbital_label']
            # Map orbital label to eigenvalue index
            label_map = {"1s": 0, "2s": 0, "2p": 1, "3s": 2}
            idx = label_map.get(orbital, 0)
            if idx < len(eigenvalues):
                calc_val = float(eigenvalues[idx])
                ref_val = ref_eval['value_hartree']
                error = abs(calc_val - ref_val) / (abs(ref_val) + 1e-12)
                passed = error <= ref_eval['tolerance_relative']
                status = "PASS" if passed else "FAIL"
                print(f"    {orbital}: computed={calc_val:.6f} Ha, ref={ref_val:.6f} Ha, error={error*100:.4f}%, {status}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Query Dirac reference database")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--case-id", type=str, help="Show details for a specific case")
    parser.add_argument("--formula", type=str, help="Filter by chemical formula")
    parser.add_argument("--list-all", action="store_true", help="List all cases")
    parser.add_argument("--tier", type=str, choices=["A-ready", "B-needs-evidence", "C-pending"], help="Filter by confidence tier")
    parser.add_argument("--category", type=str, help="Filter by category")
    parser.add_argument("--verify", type=Path, help="Verify Octopus output JSON against reference")
    args = parser.parse_args()

    conn = get_connection(args.db_path)

    if args.verify:
        verify_result(conn, args.verify)
    elif args.case_id:
        show_case(conn, args.case_id)
    elif args.list_all or args.tier or args.category:
        list_all(conn, tier=args.tier, category=args.category)
    elif args.formula:
        cur = conn.cursor()
        cur.execute("SELECT case_id FROM cases WHERE formula = ?", (args.formula,))
        rows = cur.fetchall()
        for row in rows:
            show_case(conn, row['case_id'])
    else:
        list_all(conn)

    conn.close()


if __name__ == "__main__":
    main()
