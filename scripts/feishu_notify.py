#!/usr/bin/env python3
"""
集中式飞书通知 helper — Dirac_solver OpenClaw 自动化框架。

所有飞书状态通知统一通过此模块发送，确保：
1. 所有 Agent（人发起或自主发起）的任务状态都能在飞书中看到
2. 通知格式统一: [Dirac-{Agent}] {Event} | {Progress}% | {Detail} | {Directive}
3. 触发点覆盖完整: RECEIVED → PLANNED → EXECUTING → REVIEWING → REPLAN → DONE/FAILED
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

OPENCLAW_CLI = os.environ.get(
    "DIRAC_REMOTE_OPENCLAW_BIN",
    "/data/home/zju321/.local/bin/openclaw"
)

FEISHU_BINDINGS = {
    "planner":   "oc_e7930d06b52382cfbc1a8ca2e5d7b5d6",
    "executor":  "oc_73e53172795bfd5b51daac1c557861d3",
    "reviewer":  "oc_a7643f705e509872fbccb82f77055dd7",
    "debugger":  "ou_2a1621d3f2beb1d361f426945c91218d",
    "bot_dm":    "ou_2a1621d3f2beb1d361f426945c91218d",
    "user":      "ou_2a1621d3f2beb1d361f426945c91218d",
}

ALL_AGENTS = ["planner", "executor", "reviewer", "debugger"]


def notify(
    agent: str,
    event: str,
    progress_pct: int,
    detail: str,
    directive: str = "",
    target_override: Optional[str] = None,
) -> bool:
    resolved_target = target_override or FEISHU_BINDINGS.get(agent, FEISHU_BINDINGS["bot_dm"])
    if not resolved_target:
        return False
    msg = f"[Dirac-{agent.capitalize()}] {event} | {progress_pct}%\n{detail}"
    if directive:
        msg += f"\n| {directive}"
    return _send(resolved_target, msg)


def notify_all(
    event: str,
    progress_pct: int,
    detail: str,
    directive: str = "",
) -> None:
    for agent in ALL_AGENTS:
        notify(agent, event, progress_pct, detail, directive)


def _send(target: str, message: str) -> bool:
    if not target:
        return False
    cli = OPENCLAW_CLI.strip()
    cmd = [cli, "message", "send", "--channel", "feishu", "--target", target, "--message", message[:3500]]
    try:
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, timeout=25, text=True, capture_output=True)
        return True
    except Exception:
        return False


def notify_received(run_id: str, initiator: str = "human", run_id_short: str = "") -> bool:
    """任务被接收（入口）— 通知 Planner 开始规划。"""
    initiator_text = "您（人工）" if initiator == "human" else "OpenClaw Agent"
    detail = (
        f"任务已登记，正在交给 Planner 分析\n"
        f"  run_id: {run_id}\n"
        f"  来源: {initiator_text}\n"
        f"  下一步: Planner 将选择计算案例（case）并确定验收阈值"
    )
    return notify("planner", "RECEIVED", 5, detail)


def notify_planned(run_id: str, case: str, threshold: float, plan_summary: str = "") -> bool:
    """Planner 完成规划 — 通知 Executor 开始执行。"""
    case_display = case.replace("_", " ").upper() if case else "?"
    detail = (
        f"规划完成，Harness 即将启动\n"
        f"  run_id: {run_id}\n"
        f"  案例: {case_display}\n"
        f"  验收阈值: delta <= {threshold:.3f} (benchmark 比对误差)\n"
        f"  计算模式: {'TDDFT (时域)' if 'td' in (plan_summary or '').lower() else '基态 (GS)'}\n"
        f"  下一步: Octopus 执行迭代收敛 -> Reviewer 验证结果"
    )
    return notify("planner", "PLANNED", 20, detail)


def notify_executing(run_id: str, stage: str, case: str = "", pct: int = None) -> bool:
    """Executor 开始执行 — Harness 正在迭代收敛。"""
    progress = pct if pct is not None else 40
    stage_display = {
        "harness_start": "Harness 启动，参数扫描中",
        "harness_iterate": "Harness 迭代收敛",
        "harness_complete": "Harness 收敛完成",
    }.get(stage, stage)
    detail = (
        f"Octopus 计算进行中 [{progress}%]\n"
        f"  run_id: {run_id}\n"
        f"  状态: {stage_display}\n"
        f"  案例: {case or 'hydrogen_gs_reference'}\n"
        f"  下一步: 等待 delta 收敛 -> 自动进入 Reviewer 验证"
    )
    return notify("executor", "EXECUTING", progress, detail)


def notify_reviewing(run_id: str, checks_pending: int = 0, case: str = "") -> bool:
    """Reviewer 开始评审 — 正在验证计算结果。"""
    checks_text = f"({checks_pending} 项检查)" if checks_pending > 0 else "(完整性 + 物理合理性 + benchmark 比对)"
    detail = (
        f"结果验证中 [80%]\n"
        f"  run_id: {run_id}\n"
        f"  检查项: {checks_text}\n"
        f"  案例: {case or 'hydrogen_gs_reference'}\n"
        f"  验证内容: delta <= 满值? -> 物理单位正确? -> 收敛曲线正常?\n"
        f"  下一步: PASS -> 生成报告 | FAIL -> 触发 REPLAN"
    )
    return notify("reviewer", "REVIEWING", 80, detail)


def notify_replan(
    run_id: str,
    reason: str,
    retry_current: int,
    retry_max: int,
    failure_type: str = "",
) -> bool:
    """触发 REPLAN — Planner 重新生成修复方案。"""
    reason_display = {
        "provenance_unverified": "基准数据溯源失败",
        "delta_exceeded": "benchmark delta 超限",
        "convergence_failed": "Harness 收敛失败",
        "kb_richness_insufficient": "知识库信息不足",
    }.get(reason, reason)
    is_last = retry_current >= retry_max
    next_step = "人工介入" if is_last else f"Planner 重试 ({retry_current}/{retry_max})"
    detail = (
        f"需要重新规划 [90%]\n"
        f"  run_id: {run_id}\n"
        f"  失败原因: {reason_display}\n"
        f"  重试进度: {retry_current}/{retry_max}\n"
        f"  类型: {failure_type or 'L0 自动重试'}\n"
        f"  下一步: {next_step}"
    )
    directive = "请查看 replan_packet 了解具体修复方案" if not is_last else "已达最大重试次数，需要人工处理"
    return notify("planner", "REPLAN", 90, detail, directive)


def notify_debugger(
    run_id: str,
    case_id: str,
    failure_signature_hash: str,
    failure_type: str,
    verdict: str,
    repeat_count: int = 0,
) -> bool:
    """Reviewer 返回 FAIL — 通知 Debugger 进行诊断。"""
    verdict_text = "通过" if verdict.upper() in {"PASS", "REVIEW_PASS"} else "未通过"
    detail = (
        f"[Dirac-Reviewer] FAIL | 需要Debugger诊断\n"
        f"  run_id: {run_id}\n"
        f"  案例: {case_id}\n"
        f"  判定: {verdict_text}\n"
        f"  失败类型: {failure_type}\n"
        f"  失败签名: {failure_signature_hash or 'N/A'}\n"
        f"  重复次数: {repeat_count}\n"
        f"  下一步: Debugger 将分析错误链并返回 required_fixes"
    )
    directive = "请执行诊断并返回 required_fixes 列表"
    return notify("debugger", "DIAGNOSE_REQUEST", 85, detail, directive)


def notify_done(run_id: str, verdict: str, report_path: str = "", case: str = "") -> bool:
    """任务完成（PASS 或 FAIL）— 通知用户最终结果。"""
    is_pass = verdict.upper() in {"PASS", "REVIEW_PASS"}
    verdict_text = "通过" if is_pass else "未通过"
    status_emoji = "[PASS]" if is_pass else "[FAIL]"
    report_short = "/".join(report_path.split("/")[-2:]) if report_path else "见 docs/harness_reports/"
    detail = (
        f"{status_emoji} 任务 {verdict_text}\n"
        f"  run_id: {run_id}\n"
        f"  案例: {case or 'hydrogen_gs_reference'}\n"
        f"  判定: {verdict_text}\n"
        f"  报告: {report_short}\n"
        f"  {('可以开始下一项任务' if is_pass else '将触发自动重试或人工介入')}"
    )
    return notify("reviewer", "DONE", 100, detail)


def notify_escalating(run_id: str, severity: str, blocker: str) -> bool:
    """升级到人工介入 — 通知 Debugger 和用户。"""
    severity_text = {"low": "低", "medium": "中", "high": "高"}.get(severity.lower(), severity)
    blocker_text = {
        "replan_triggered": "自动重规划已触发",
        "kb_unavailable": "知识库服务不可用",
        "harness_stuck": "Harness 卡住无法收敛",
        "octopus_crash": "Octopus 计算崩溃",
    }.get(blocker, blocker)
    detail = (
        f"[ESCALATING] 需要人工处理\n"
        f"  run_id: {run_id}\n"
        f"  严重程度: {severity_text}\n"
        f"  问题: {blocker_text}\n"
        f"  等待: Debugger 调查或人工干预"
    )
    directive = "请查看任务报告或联系 Debugger"
    return notify("debugger", "ESCALATING", 95, detail, directive)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("[feishu_notify] Sending test message to debugger DM...")
        ok = notify("debugger", "TEST", 99, "feishu_notify module loaded OK", "")
        print(f"[feishu_notify] Result: {'OK' if ok else 'FAILED'}")
        sys.exit(0 if ok else 1)
    print("[feishu_notify] Module loaded. Usage: python feishu_notify.py --test")
