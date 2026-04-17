#!/usr/bin/env python3
"""Debug utility for Dirac solver execution and state synchronization."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
BRIDGE_PATH = REPO_ROOT / "state" / "copilot_openclaw_bridge.json"
QUEUE_PATH = REPO_ROOT / "state" / "dirac_exec_queue.json"
PIDS_DIR = REPO_ROOT / ".pids"
WORKER_LOG = REPO_ROOT / "logs" / "dirac_exec_worker.log"
HOOK_LOG = Path.home() / ".openclaw" / "logs" / "exec-hook.log"
OCTOPUS_OUTPUT = REPO_ROOT / "@Octopus_docs" / "output"

SCF_ITERS_RE = re.compile(r"SCF\s+converged\s+in\s+(\d+)\s+iterations", re.IGNORECASE)
TOTAL_RE = re.compile(r"^\s*Total\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
EIGEN_HEADER_RE = re.compile(r"Eigenvalues\s*\[H\]", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def tail_lines(path: Path, count: int) -> List[str]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = text.splitlines()
    return lines[-max(1, int(count)) :]


def worker_alive() -> Dict[str, Any]:
    pid_file = PIDS_DIR / "dirac_exec_worker.pid"
    pid = None
    alive = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            alive = True
        except Exception:
            alive = False
    return {"pid": pid, "alive": alive, "pid_file": pid_file.as_posix()}


def parse_octopus_info() -> Dict[str, Any]:
    info_file = OCTOPUS_OUTPUT / "info"
    if not info_file.exists():
        return {"available": False}

    text = info_file.read_text(encoding="utf-8", errors="replace")
    scf_match = SCF_ITERS_RE.search(text)

    total_energy = None
    for line in text.splitlines():
        m = TOTAL_RE.search(line)
        if m:
            try:
                total_energy = float(m.group(1))
            except Exception:
                total_energy = None
            break

    homo = None
    lumo = None
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if EIGEN_HEADER_RE.search(line):
            start = idx
            break
    if start is not None:
        for line in lines[start + 1 :]:
            raw = line.strip()
            if not raw:
                if homo is not None:
                    break
                continue
            parts = raw.split()
            if len(parts) < 4:
                continue
            try:
                value = float(parts[2])
                occ = float(parts[3])
            except Exception:
                continue
            if occ > 0.1:
                homo = value
            elif lumo is None:
                lumo = value
                if homo is not None:
                    break

    return {
        "available": True,
        "scf_converged": bool(scf_match),
        "scf_iterations": int(scf_match.group(1)) if scf_match else None,
        "total_energy_ha": total_energy,
        "homo_ha": homo,
        "lumo_ha": lumo,
        "gap_ha": (lumo - homo) if (homo is not None and lumo is not None) else None,
        "info_file": info_file.as_posix(),
    }


def parse_td_energy() -> Dict[str, Any]:
    energy_file = OCTOPUS_OUTPUT / "td.general" / "energy"
    if not energy_file.exists():
        return {"available": False}

    rows = []
    for line in energy_file.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 4:
            continue
        try:
            step = int(parts[0])
            time_hbar_over_h = float(parts[1])
            total_energy = float(parts[2])
            rows.append((step, time_hbar_over_h, total_energy))
        except Exception:
            continue

    if not rows:
        return {"available": True, "rows": 0, "energy_file": energy_file.as_posix()}

    last = rows[-1]
    first = rows[0]
    return {
        "available": True,
        "rows": len(rows),
        "first": {"step": first[0], "time": first[1], "total_energy": first[2]},
        "last": {"step": last[0], "time": last[1], "total_energy": last[2]},
        "energy_file": energy_file.as_posix(),
    }


def snapshot_state(log_tail: int) -> Dict[str, Any]:
    sync = read_json(SYNC_PATH, {})
    bridge = read_json(BRIDGE_PATH, {})
    queue = read_json(QUEUE_PATH, {"tasks": []})

    tasks = queue.get("tasks") if isinstance(queue, dict) else []
    tasks = tasks if isinstance(tasks, list) else []
    depth = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for item in tasks:
        status = str(item.get("status") or "")
        if status in depth:
            depth[status] += 1

    return {
        "worker": worker_alive(),
        "sync": {
            "updated_at": sync.get("updated_at") if isinstance(sync, dict) else None,
            "phase": sync.get("phase") if isinstance(sync, dict) else None,
            "last_task": (sync.get("last_task") if isinstance(sync, dict) else None),
            "multi_agent_checks": ((sync.get("multi_agent") or {}).get("reviewer") or {}).get("checks") if isinstance(sync, dict) else None,
        },
        "bridge": ((bridge.get("execution_bus") or {}).get("last_task") if isinstance(bridge, dict) else None),
        "queue": {
            "updated_at": queue.get("updated_at") if isinstance(queue, dict) else None,
            "depth": depth,
            "last_task": tasks[-1] if tasks else None,
        },
        "octopus": {
            "static": parse_octopus_info(),
            "td": parse_td_energy(),
        },
        "logs": {
            "worker_tail": tail_lines(WORKER_LOG, log_tail),
            "hook_tail": tail_lines(HOOK_LOG, log_tail),
        },
    }


def run_dispatch(task: str, source: str, execute: bool, auto_replan: bool, timeout: int) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "scripts/dispatch_dirac_task.py",
        "--task",
        task,
        "--source",
        source,
    ]
    if execute:
        cmd.append("--execute")
    if auto_replan:
        cmd.append("--auto-execute-replan")

    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=max(20, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(cmd),
            "exit_code": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"timeout_after_{timeout}s",
            "kv": {},
        }

    kv: Dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        idx = line.find("=")
        if idx > 0:
            kv[line[:idx].strip()] = line[idx + 1 :].strip()

    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "kv": kv,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dirac debug operations tool")
    parser.add_argument("--mode", choices=["snapshot", "dispatch", "full"], default="snapshot")
    parser.add_argument("--task", default="Dirac_solver 调试")
    parser.add_argument("--source", default="cli-debug-tool")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--auto-replan", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--log-tail", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result: Dict[str, Any] = {
        "tool": "run_dirac_debug_ops",
        "mode": args.mode,
        "generated_at": now_iso(),
        "ok": True,
        "steps": {},
    }

    if args.mode in {"snapshot", "full"}:
        result["steps"]["snapshot_before"] = snapshot_state(args.log_tail)

    if args.mode in {"dispatch", "full"}:
        dispatch_result = run_dispatch(
            task=args.task,
            source=args.source,
            execute=bool(args.execute),
            auto_replan=bool(args.auto_replan),
            timeout=int(args.timeout),
        )
        result["steps"]["dispatch"] = dispatch_result
        if int(dispatch_result.get("exit_code", 1)) != 0:
            result["ok"] = False

    if args.mode == "full":
        result["steps"]["snapshot_after"] = snapshot_state(args.log_tail)

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
