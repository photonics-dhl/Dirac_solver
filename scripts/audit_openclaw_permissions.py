#!/usr/bin/env python3
"""Audit OpenClaw execution readiness for Dirac automation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def match_any(patterns: List[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def effective_scopes(paired: Dict[str, Any]) -> List[str]:
    scopes: List[str] = []
    for _, item in paired.items():
        approved = item.get("approvedScopes") or []
        if isinstance(approved, list):
            for scope in approved:
                scope_str = str(scope).strip()
                if scope_str and scope_str not in scopes:
                    scopes.append(scope_str)
    return scopes


def classify_command(policy: Dict[str, Any], command: str) -> str:
    deny = policy.get("deny_commands") or []
    approve = policy.get("require_approval_commands") or []
    auto = policy.get("auto_allow_commands") or []
    if match_any(deny, command):
        return "deny"
    if match_any(approve, command):
        return "require_approval"
    if match_any(auto, command):
        return "auto_allow"
    return "unclassified"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit OpenClaw terminal execution readiness.")
    parser.add_argument("--openclaw-root", default="~/.openclaw", help="OpenClaw root path.")
    parser.add_argument(
        "--policy",
        default="orchestration/openclaw_exec_policy.json",
        help="Execution policy json path.",
    )
    parser.add_argument(
        "--sample-command",
        action="append",
        default=[],
        help="Sample command to classify against policy (can be repeated).",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    openclaw_root = Path(args.openclaw_root).expanduser()
    config = read_json(openclaw_root / "openclaw.json")
    paired = read_json(openclaw_root / "devices" / "paired.json")
    pending = read_json(openclaw_root / "devices" / "pending.json")
    policy = read_json(Path(args.policy))

    shell_env = (((config.get("env") or {}).get("shellEnv") or {}))
    shell_enabled = bool(shell_env.get("enabled", False))
    shell_timeout = int(shell_env.get("timeoutMs", 0) or 0)

    approved_scopes = effective_scopes(paired)
    required_scopes = [str(s) for s in (policy.get("required_device_scopes") or [])]
    missing_scopes = [s for s in required_scopes if s not in approved_scopes]

    samples = []
    for cmd in args.sample_command:
        samples.append({"command": cmd, "classification": classify_command(policy, cmd)})

    result = {
        "shell_env": {"enabled": shell_enabled, "timeoutMs": shell_timeout},
        "approved_scopes": approved_scopes,
        "required_scopes": required_scopes,
        "missing_scopes": missing_scopes,
        "pending_device_count": len(pending) if isinstance(pending, dict) else 0,
        "execution_ready": shell_enabled and not missing_scopes,
        "sample_classification": samples,
        "policy_mode": policy.get("mode", "unknown"),
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(f"shell_env.enabled={result['shell_env']['enabled']}")
        print(f"shell_env.timeoutMs={result['shell_env']['timeoutMs']}")
        print(f"approved_scopes={','.join(approved_scopes) if approved_scopes else '-'}")
        print(f"missing_scopes={','.join(missing_scopes) if missing_scopes else '-'}")
        print(f"pending_device_count={result['pending_device_count']}")
        print(f"execution_ready={result['execution_ready']}")
        if samples:
            print("sample_classification:")
            for item in samples:
                print(f"  - {item['classification']}: {item['command']}")

    return 0 if result["execution_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
