#!/usr/bin/env python3
"""
Dirac_solver 定时清理脚本
=========================
设计原则：
  1. 仅清理 harness_reports（计算产物）
  2. 保留 state/ 和 knowledge_base/ 不动
  3. 每次清理形成经验记录到 memory/

定时配置（crontab -e）：
  # 每6小时运行一次，保留最近2次运行
  0 */6 * * * cd /data/home/zju321/.openclaw/workspace/projects/Dirac && python scripts/scheduled_cleanup.py >> logs/cleanup_cron.log 2>&1

  # 手动触发
  python scripts/scheduled_cleanup.py --dry-run  # 预览
  python scripts/scheduled_cleanup.py --trigger-reason manual  # 执行
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ── 路径配置 ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
CLEANUP_SCRIPT = REPO_ROOT / "scripts" / "cleanup_harness_reports.py"
STATE_SYNC = REPO_ROOT / "state" / "dirac_solver_progress_sync.json"
MEMORY_DIR = Path.home() / ".claude" / "memory"
LEARN_FILE = MEMORY_DIR / "cleanup_lessons.md"
LOG_FILE = REPO_ROOT / "logs" / "cleanup_cron.log"


# ── 保留策略 ──────────────────────────────────────────────────────────────────
KEEP_PER_CASE = 2   # 每个 case 保留最近 2 次运行
KEEP_GLOBAL = 3      # 全局类（master/kb）保留最近 3 次


@dataclass
class CleanupLesson:
    """单次清理的经验教训记录"""
    timestamp: str
    trigger_reason: str
    files_scanned: int
    files_deleted: int
    files_kept: int
    categories_affected: List[str]
    notable_decisions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dirac 定时清理调度器")
    parser.add_argument("--keep-per-case", type=int, default=KEEP_PER_CASE,
                        help=f"每个 case 保留最近几次运行 (默认 {KEEP_PER_CASE})")
    parser.add_argument("--keep-global", type=int, default=KEEP_GLOBAL,
                        help=f"全局类别保留最近几次 (默认 {KEEP_GLOBAL})")
    parser.add_argument("--trigger-reason", default="cron",
                        choices=["cron", "manual", "breathing_threshold", "startup"],
                        help="触发原因")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不删除")
    parser.add_argument("--breathing-threshold", type=int, default=1200,
                        help="触发呼吸式清理的文件数量阈值")
    return parser.parse_args()


def ensure_memory_dir() -> None:
    """确保 memory 目录存在"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def load_reports_summary() -> Dict:
    """返回 harness_reports 目录概况"""
    reports_dir = REPO_ROOT / "docs" / "harness_reports"
    if not reports_dir.exists():
        return {"total_files": 0, "categories": {}}

    all_files = list(reports_dir.glob("*.*"))
    categories: Dict[str, int] = {}
    for f in all_files:
        cat = _category_of(f.name)
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_files": len(all_files),
        "categories": categories,
        "oldest_file_mtime": min((f.stat().st_mtime for f in all_files), default=0),
        "newest_file_mtime": max((f.stat().st_mtime for f in all_files), default=0),
    }


def _category_of(name: str) -> str:
    """复刻 cleanup_harness_reports.py 的分类逻辑"""
    if name.startswith("harness_acceptance_"): return "acceptance"
    if name.startswith("harness_sweep_"): return "sweep"
    if name.startswith("harness_master_"): return "master"
    if name.startswith("kb_ingestion_report_"): return "kb"
    if name.startswith("octopus_first_principles_"): return "octopus"
    if name.startswith("multi_agent_orchestration_"): return "multi_agent"
    if name.startswith("task_dispatch_"): return "task_dispatch"
    if name.startswith("replan_packet_"): return "replan_packet"
    if name.startswith("replan_execution_"): return "replan_execution"
    if name.startswith("escalation_packet_"): return "escalation_packet"
    return "other"


def run_cleanup(args: argparse.Namespace) -> tuple[int, int, int]:
    """
    调用底层 cleanup_harness_reports.py
    返回 (scanned, kept, deleted)
    """
    cmd = [
        sys.executable, str(CLEANUP_SCRIPT),
        "--reports-dir", str(REPO_ROOT / "docs" / "harness_reports"),
        "--openclaw-sync-path", str(STATE_SYNC),
        "--keep-per-case", str(args.keep_per_case),
        "--keep-global", str(args.keep_global),
        "--trigger-reason", args.trigger_reason,
        "--breathing-file-threshold", str(args.breathing_threshold),
    ]
    if args.dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, capture_output=True, text=True)
    scanned = kept = deleted = 0
    for line in result.stdout.splitlines():
        if "=" in line:
            key, val = line.strip().split("=", 1)
            if key == "total_files_scanned":
                scanned = int(val)
            elif key == "kept_files":
                kept = int(val)
            elif key == "deleted_files":
                deleted = int(val)

    return scanned, kept, deleted


def append_lesson_to_memory(lesson: CleanupLesson) -> None:
    """将清理经验追加到 memory/cleanup_lessons.md"""
    ensure_memory_dir()

    decision_str = "\n  - ".join(f'"{d}"' for d in lesson.notable_decisions) if lesson.notable_decisions else "无"
    warning_str = "\n  - ".join(f'"{w}"' for w in lesson.warnings) if lesson.warnings else "无"

    entry = f"""
## {lesson.timestamp} | trigger={lesson.trigger_reason}

| 指标 | 值 |
|------|-----|
| 扫描文件数 | {lesson.files_scanned} |
| 删除文件数 | {lesson.files_deleted} |
| 保留文件数 | {lesson.files_kept} |
| 涉及类别 | {", ".join(lesson.categories_affected)} |
| 重要决策 | {decision_str} |
| 警告 | {warning_str} |
"""

    if LEARN_FILE.exists():
        existing = LEARN_FILE.read_text(encoding="utf-8")
        # 在 ## 一、Memory Index 之后插入
        if "## 一、Memory Index" in existing:
            idx = existing.index("## 一、Memory Index")
            LEARN_FILE.write_text(existing[:idx] + entry + "\n" + existing[idx:],
                                  encoding="utf-8")
        else:
            LEARN_FILE.write_text(existing + entry, encoding="utf-8")
    else:
        LEARN_FILE.write_text(
            f"# 清理经验记录 (Cleanup Lessons)\n\n"
            f"> 本文件由 `scripts/scheduled_cleanup.py` 自动生成。\n"
            f"> 每次清理后追加经验记录，长期积累后用于优化保留策略。\n\n"
            f"## 一、Memory Index\n"
            f"| 日期 | 触发 | 扫描 | 删除 | 保留 |\n"
            f"|------|------|-----:|-----:|-----:|\n"
            f"| {lesson.timestamp} | {lesson.trigger_reason} "
            f"| {lesson.files_scanned} | {lesson.files_deleted} | {lesson.files_kept} |\n"
            f"\n{entry}",
            encoding="utf-8"
        )


def check_breathing_threshold() -> tuple[bool, str]:
    """
    检查是否需要触发呼吸式清理。
    如果文件数 > 阈值，返回 (True, reason)。
    """
    reports_dir = REPO_ROOT / "docs" / "harness_reports"
    if not reports_dir.exists():
        return False, ""

    all_files = list(reports_dir.glob("*.*"))
    total = len(all_files)

    if total >= 1200:
        return True, f"文件总数 {total} >= 阈值 {1200}"
    if total >= 800:
        # 按类别检查
        cats: Dict[str, int] = {}
        for f in all_files:
            cat = _category_of(f.name)
            cats[cat] = cats.get(cat, 0) + 1

        # acceptance 或 sweep 超过 200 个则触发
        for cat in ["acceptance", "sweep"]:
            if cats.get(cat, 0) >= 200:
                return True, f"类别 {cat} 文件数 {cats[cat]} >= 200"

    return False, ""


def init_log() -> None:
    """初始化日志文件"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8") + line + "\n",
                         encoding="utf-8")


def main() -> int:
    args = parse_args()
    init_log()
    log(f"=== cleanup start trigger={args.trigger_reason} keep_per_case={args.keep_per_case} ===")

    # 1. 呼吸式检查（仅自动触发时）
    if args.trigger_reason == "cron":
        should_trigger, reason = check_breathing_threshold()
        if not should_trigger:
            log(f"跳过：文件数量未达阈值 ({reason or '检查通过'})")
            return 0
        args.trigger_reason = "breathing_threshold"
        log(f"呼吸式触发：{reason}")

    # 2. 执行清理
    before = load_reports_summary()
    log(f"清理前：共 {before['total_files']} 个文件，类别分布: {before['categories']}")

    try:
        scanned, kept, deleted = run_cleanup(args)
    except Exception as exc:
        log(f"ERROR: cleanup_harness_reports.py 执行失败: {exc}")
        return 1

    after = load_reports_summary()
    log(f"清理后：共 {after['total_files']} 个文件")
    log(f"结果：扫描={scanned} 保留={kept} 删除={deleted}")

    # 3. 提取涉及类别
    cats = list(before.get("categories", {}).keys())

    # 4. 记录经验
    lesson = CleanupLesson(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        trigger_reason=args.trigger_reason,
        files_scanned=scanned,
        files_deleted=deleted,
        files_kept=kept,
        categories_affected=cats,
        notable_decisions=[
            f"keep_per_case={args.keep_per_case}",
            f"keep_global={args.keep_global}",
        ],
        warnings=[],
    )

    if deleted == 0 and before["total_files"] > 100:
        lesson.warnings.append("清理了0个文件但目录中仍有大量文件，可能是 pinned 文件或 'other' 类别过多")

    if before["total_files"] - deleted > 800:
        lesson.warnings.append(f"清理后仍有 {before['total_files'] - deleted} 个文件，可能需要提高清理频率或 keep_per_case")

    append_lesson_to_memory(lesson)
    log(f"经验已记录到 {LEARN_FILE}")

    log("=== cleanup done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
