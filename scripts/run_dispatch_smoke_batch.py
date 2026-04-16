#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_compact() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def parse_kv_lines(stdout: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        result[key] = value.strip()
    return result


@dataclass
class RunResult:
    index: int
    run_id: str
    started_at: str
    duration_seconds: float
    process_exit_code: int
    dispatch_status: str
    workflow_state: str
    workflow_event: str
    execution_exit_code: str
    convergence_gate_passed: str
    dispatch_report: str
    success: bool
    stderr_excerpt: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run sequential Dirac dispatch smoke tests and write a summary report.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--source", default="cli-smoke-batch")
    parser.add_argument("--exec-timeout-seconds", type=int, default=240)
    parser.add_argument("--task-prefix", default="Dirac_solver 调试 workflow=fullchain mode=autonomous case=infinite_well_v1 octopus=required ncpus=64 mpiprocs=64")
    parser.add_argument("--sync-state", default="state/dirac_solver_progress_sync.json")
    parser.add_argument("--report-dir", default="docs/harness_reports")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dispatch_script = repo_root / "scripts" / "dispatch_dirac_task.py"
    report_dir = (repo_root / args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []
    started_batch = utc_now().isoformat()

    for index in range(1, args.runs + 1):
        run_id = f"SMOKE-{ts_compact()}-{index:02d}"
        task_text = f"{args.task_prefix} run_id={run_id}"
        cmd = [
            sys.executable,
            str(dispatch_script),
            "--task",
            task_text,
            "--source",
            args.source,
            "--execute",
            "--exec-timeout-seconds",
            str(args.exec_timeout_seconds),
            "--auto-execute-replan",
            "--sync-state",
            args.sync_state,
        ]

        t0 = time.perf_counter()
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = round(time.perf_counter() - t0, 3)
        parsed = parse_kv_lines(proc.stdout)

        dispatch_status = parsed.get("dispatch_status", "")
        workflow_state = parsed.get("workflow_state", "")
        workflow_event = parsed.get("workflow_event", "")
        execution_exit_code = parsed.get("execution_exit_code", "")
        convergence_gate_passed = parsed.get("convergence_gate_passed", "")
        dispatch_report = parsed.get("dispatch_report", "")

        success = (
            proc.returncode == 0
            and dispatch_status == "success"
            and workflow_state == "DONE"
            and workflow_event == "REVIEW_PASS"
            and execution_exit_code == "0"
        )

        results.append(
            RunResult(
                index=index,
                run_id=run_id,
                started_at=utc_now().isoformat(),
                duration_seconds=duration,
                process_exit_code=proc.returncode,
                dispatch_status=dispatch_status,
                workflow_state=workflow_state,
                workflow_event=workflow_event,
                execution_exit_code=execution_exit_code,
                convergence_gate_passed=convergence_gate_passed,
                dispatch_report=dispatch_report,
                success=success,
                stderr_excerpt=proc.stderr.strip()[:500],
            )
        )

        print(
            f"run={index} run_id={run_id} dispatch_status={dispatch_status or '-'} "
            f"workflow_state={workflow_state or '-'} workflow_event={workflow_event or '-'} "
            f"exec_exit={execution_exit_code or '-'} success={success}"
        )

    passed = sum(1 for item in results if item.success)
    summary = {
        "timestamp": ts_compact(),
        "started_at": started_batch,
        "runs": args.runs,
        "passed": passed,
        "failed": args.runs - passed,
        "pass_rate": round((passed / args.runs) if args.runs > 0 else 0.0, 4),
        "criteria": {
            "process_exit_code": 0,
            "dispatch_status": "success",
            "workflow_state": "DONE",
            "workflow_event": "REVIEW_PASS",
            "execution_exit_code": "0",
        },
        "results": [asdict(item) for item in results],
    }

    stamp = ts_compact()
    json_path = report_dir / f"dispatch_smoke_batch_{stamp}.json"
    md_path = report_dir / f"dispatch_smoke_batch_{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Dispatch Smoke Batch Report",
        "",
        f"- timestamp: {stamp}",
        f"- runs: {args.runs}",
        f"- passed: {passed}",
        f"- failed: {args.runs - passed}",
        f"- pass_rate: {summary['pass_rate']}",
        "",
        "## Per-run",
        "",
        "| run | run_id | dispatch_status | workflow_state | workflow_event | exec_exit | success | report |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in results:
        md_lines.append(
            "| "
            f"{item.index} | {item.run_id} | {item.dispatch_status or '-'} | "
            f"{item.workflow_state or '-'} | {item.workflow_event or '-'} | "
            f"{item.execution_exit_code or '-'} | {item.success} | {item.dispatch_report or '-'} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"summary_json={json_path.as_posix()}")
    print(f"summary_md={md_path.as_posix()}")
    print(f"pass_rate={summary['pass_rate']}")
    return 0 if passed == args.runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
