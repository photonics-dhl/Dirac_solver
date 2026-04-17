#!/usr/bin/env python3
"""Run a real Octopus first-principles case after simple harness gating."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENCLAW_SYNC_PATH = REPO_ROOT.parent / "OpenClaw" / "state" / "dirac_solver_progress_sync.json"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@contextmanager
def file_lock(lock_path: Path, timeout_seconds: float = 8.0):
    start = time.time()
    acquired_fd = None
    while True:
        try:
            acquired_fd = os.open(lock_path.as_posix(), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if (time.time() - start) >= timeout_seconds:
                raise TimeoutError(f"lock timeout: {lock_path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        if acquired_fd is not None:
            try:
                os.close(acquired_fd)
            except Exception:
                pass
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            try:
                backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def post_json(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def post_json_with_fallback(urls: list[str], payload: Dict[str, Any], timeout: float) -> tuple[Dict[str, Any], str]:
    errors: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = url.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return post_json(normalized, payload, timeout=timeout), normalized
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors) if errors else "No endpoint candidates provided")


def write_openclaw_sync(path: Path, summary: Dict[str, Any], report_json: Path, report_md: Path) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path):
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                backup_path = path.with_suffix(path.suffix + ".bak")
                try:
                    existing = json.loads(backup_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}

        existing["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing["project"] = "Dirac_solver"
        if not isinstance(existing.get("last_task"), dict):
            existing["phase"] = "phaseA_plus"
            existing["status"] = "in_progress"
        existing["octopus_first_principles"] = {
            "simple_model_case": summary.get("simple_model_case"),
            "simple_model_passed": summary.get("simple_model_passed"),
            "octopus_molecule": summary.get("octopus_molecule"),
            "octopus_calc_mode": summary.get("octopus_calc_mode"),
            "workflow_passed": summary.get("workflow_passed"),
            "report_json": report_json.as_posix(),
            "report_md": report_md.as_posix(),
        }

        write_json_atomic(path, existing)


def render_markdown(summary: Dict[str, Any], command: str, report_json: Path) -> str:
    lines = [
        "# Octopus First-Principles Workflow Report",
        "",
        "## Gating and Result",
        "",
        f"- Simple Model Case: {summary.get('simple_model_case')}",
        f"- Simple Model Passed: {summary.get('simple_model_passed')}",
        f"- Octopus Molecule: {summary.get('octopus_molecule')}",
        f"- Octopus Calculation Mode: {summary.get('octopus_calc_mode')}",
        f"- Workflow Passed: {summary.get('workflow_passed')}",
        "",
        "## Notes",
        "",
        "- Workflow enforces harness gating before Octopus first-principles execution.",
        "- If simple model fails, Octopus execution is blocked by design.",
        "",
        "## Artifact",
        "",
        f"- JSON: {report_json.as_posix()}",
        "",
        "## Invocation",
        "",
        "```bash",
        command,
        "```",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Octopus first-principles case after simple harness validation.")
    parser.add_argument("--api-base", default="http://127.0.0.1:3001", help="Node API base URL.")
    parser.add_argument("--harness-base", default="", help="Optional direct Harness API base URL (e.g. http://127.0.0.1:8001).")
    parser.add_argument("--simple-case", default="infinite_well_v1", help="Harness simple model case ID.")
    parser.add_argument("--molecule", default="H2", help="Octopus molecule key, e.g. H2, N2, CH4, Benzene.")
    parser.add_argument("--calc-mode", default="gs", choices=["gs", "td", "unocc", "opt", "em", "vib"], help="Octopus calc mode.")
    default_timeout = float(os.environ.get("OCTOPUS_FP_HTTP_TIMEOUT_SECONDS", "180"))
    parser.add_argument("--timeout", type=float, default=default_timeout, help="HTTP timeout in seconds.")
    parser.add_argument("--output-dir", default="docs/harness_reports", help="Output directory for report files.")
    parser.add_argument("--openclaw-sync-path", default=str(DEFAULT_OPENCLAW_SYNC_PATH), help="OpenClaw sync JSON path.")
    parser.add_argument("--skip-openclaw-sync", action="store_true", help="Skip updating OpenClaw sync status.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero on workflow failure.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    harness_result: Dict[str, Any] = {}
    harness_candidates = [
        f"{args.api_base.rstrip('/')}/api/harness/run-case",
        f"{args.api_base.rstrip('/')}/api/harness/run_case",
        "http://127.0.0.1:3001/api/harness/run-case",
    ]
    if args.harness_base.strip():
        base = args.harness_base.rstrip("/")
        harness_candidates.extend(
            [
                f"{base}/harness/run_case",
                f"{base}/harness/run-case",
                f"{base}/api/harness/run-case",
                f"{base}/api/harness/run_case",
            ]
        )
    harness_candidates.append("http://127.0.0.1:8001/harness/run_case")
    harness_result, harness_url = post_json_with_fallback(
        harness_candidates, {"case_id": args.simple_case}, timeout=args.timeout
    )
    simple_passed = bool(harness_result.get("passed", False))

    workflow_passed = False
    octopus_result: Dict[str, Any] = {}
    failure_reason = ""

    if simple_passed:
        octopus_payload = {
            "engineMode": "octopus3D",
            "calcMode": args.calc_mode,
            "octopusCalcMode": args.calc_mode,
            "octopusDimensions": "3D",
            "octopusPeriodic": "off",
            "octopusSpacing": 0.5,
            "octopusRadius": 3.0,
            "octopusBoxPadding": 2.5,
            "octopusBoxShape": "sphere",
            "octopusMolecule": args.molecule,
            "molecule": args.molecule,
            "dimensionality": "3D",
            "equationType": "Schrodinger",
            "problemType": "boundstate",
            "potentialType": "Harmonic",
            "fastPath": True,
            "skipRunExplanation": True,
            "octopusMaxScfIterations": 40,
        }
        octopus_url = f"{args.api_base.rstrip('/')}/api/physics/run"
        try:
            octopus_result = post_json(octopus_url, octopus_payload, timeout=args.timeout)
            workflow_passed = not bool(octopus_result.get("error"))
            if not workflow_passed:
                failure_reason = str(octopus_result.get("error") or "Octopus run returned error")
        except Exception as exc:
            failure_reason = str(exc)
            workflow_passed = False
    else:
        failure_reason = "simple model gate failed"

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "simple_model_case": args.simple_case,
        "simple_model_passed": simple_passed,
        "octopus_molecule": args.molecule,
        "octopus_calc_mode": args.calc_mode,
        "workflow_passed": workflow_passed,
        "failure_reason": failure_reason,
        "harness": harness_result,
        "harness_endpoint": harness_url,
        "octopus": octopus_result,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_compact()
    report_json = output_dir / f"octopus_first_principles_{args.molecule}_{args.calc_mode}_{stamp}.json"
    report_md = output_dir / f"octopus_first_principles_{args.molecule}_{args.calc_mode}_{stamp}.md"

    command_text = (
        f"python scripts/run_octopus_first_principles_case.py --api-base {args.api_base} "
        + (f"--harness-base {args.harness_base} " if args.harness_base.strip() else "")
        + f"--simple-case {args.simple_case} --molecule {args.molecule} --calc-mode {args.calc_mode}"
    )

    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    report_md.write_text(render_markdown(summary, command_text, report_json), encoding="utf-8")

    if not args.skip_openclaw_sync:
        write_openclaw_sync(Path(args.openclaw_sync_path), summary, report_json, report_md)

    print(f"octopus_report_json={report_json.as_posix()}")
    print(f"octopus_report_md={report_md.as_posix()}")
    print(f"simple_model_passed={simple_passed}")
    print(f"workflow_passed={workflow_passed}")
    if failure_reason:
        print(f"failure_reason={failure_reason}")
    if not args.skip_openclaw_sync:
        print(f"openclaw_sync_json={Path(args.openclaw_sync_path).as_posix()}")

    if args.strict and not workflow_passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
