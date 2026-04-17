#!/usr/bin/env python3
"""Ensure OpenClaw terminal execution capability baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect_approved_scopes(paired: Dict[str, Any]) -> List[str]:
    scopes: List[str] = []
    for _, item in paired.items():
        approved = item.get("approvedScopes") or []
        if isinstance(approved, list):
            for scope in approved:
                scope_str = str(scope).strip()
                if scope_str and scope_str not in scopes:
                    scopes.append(scope_str)
    return scopes


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure OpenClaw exec capability is enabled.")
    parser.add_argument("--openclaw-root", default="~/.openclaw", help="OpenClaw root path.")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="Minimum shellEnv timeoutMs.")
    parser.add_argument(
        "--required-scope",
        action="append",
        default=["operator.read", "operator.write", "operator.approvals"],
        help="Required approved scope (repeatable).",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    root = Path(args.openclaw_root).expanduser()
    config_path = root / "openclaw.json"
    paired_path = root / "devices" / "paired.json"

    config = read_json(config_path)
    before_shell = (((config.get("env") or {}).get("shellEnv") or {}))

    env_obj = config.setdefault("env", {})
    shell_env = env_obj.setdefault("shellEnv", {})

    changed = False
    if not bool(shell_env.get("enabled", False)):
        shell_env["enabled"] = True
        changed = True

    current_timeout = int(shell_env.get("timeoutMs", 0) or 0)
    if current_timeout < args.timeout_ms:
        shell_env["timeoutMs"] = args.timeout_ms
        changed = True

    backup_path = None
    if changed and config_path.exists():
        backup_path = config_path.with_suffix(f".backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
        write_json(config_path, config)

    paired = read_json(paired_path)
    approved_scopes = collect_approved_scopes(paired)
    required_scopes = [str(s).strip() for s in args.required_scope if str(s).strip()]
    missing_scopes = [s for s in required_scopes if s not in approved_scopes]

    result = {
        "timestamp": now_iso(),
        "config_path": config_path.as_posix(),
        "changed": changed,
        "backup_path": backup_path.as_posix() if backup_path else None,
        "shell_env_before": {
            "enabled": bool(before_shell.get("enabled", False)),
            "timeoutMs": int(before_shell.get("timeoutMs", 0) or 0),
        },
        "shell_env_after": {
            "enabled": bool(shell_env.get("enabled", False)),
            "timeoutMs": int(shell_env.get("timeoutMs", 0) or 0),
        },
        "approved_scopes": approved_scopes,
        "required_scopes": required_scopes,
        "missing_scopes": missing_scopes,
        "execution_ready": bool(shell_env.get("enabled", False)) and not missing_scopes,
        "note": (
            "If missing_scopes is not empty, use OpenClaw device approval/grant flow to authorize this device."
        ),
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(f"changed={result['changed']}")
        print(f"shell_env.enabled={result['shell_env_after']['enabled']}")
        print(f"shell_env.timeoutMs={result['shell_env_after']['timeoutMs']}")
        print(f"missing_scopes={','.join(missing_scopes) if missing_scopes else '-'}")
        print(f"execution_ready={result['execution_ready']}")
        if backup_path:
            print(f"backup_path={backup_path.as_posix()}")

    return 0 if result["execution_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
