"""Locate installed RIIC code for evidence-based diagnosis without guessing lines."""

import hashlib

from arknights_mower.agent.tools.get_source_snippet import (
    _MAX_SOURCE_BYTES,
    _allowed_source_path,
)

SOURCE_ENTRIES = (
    (
        "ui/src/riic/incomeWorker.js",
        "演算报告生成与统计输出",
        ("export function calculateIncome(",),
    ),
    (
        "ui/src/riic/vendor/simulator/scheduleSimulation.ts",
        "演算工作、休息、零心情统计与下班延期",
        (
            "export function simulateSchedule(",
            "if(resting)s.restHours+=dt",
            "const deferrals:",
        ),
    ),
    (
        "ui/src/riic/vendor/scheduler/mowerSourceRuntime.ts",
        "演算与原生调度逻辑的适配",
        (
            "export function getMowerSourceRuntime(",
            "export function makeMowerSchedulingData(",
        ),
    ),
    (
        "arknights_mower/utils/operators.py",
        "实际调度的心情阈值、共享替班和替班可用性",
        (
            "def resting_mood_threshold(",
            "def shared_replacements(",
            "def replacement_candidates(",
        ),
    ),
    (
        "arknights_mower/solvers/base_schedule.py",
        "实际调度的轮休规划、入宿安排和任务派发",
        ("def plan_solver(", "def get_resting_plan(", "def resting("),
    ),
    (
        "arknights_mower/solvers/emergency.py",
        "实际调度的救急进入、换班与退出",
        ("def _emergency_startup(", "def _emergency_schedule_staffing("),
    ),
)


def riic_code_locations():
    """Read an allowlisted local source inventory; missing code remains unavailable."""
    sources = []
    for relative, purpose, markers in SOURCE_ENTRIES:
        item = {"file_path": relative, "purpose": purpose, "available": False}
        sources.append(item)
        try:
            path = _allowed_source_path(relative)
            with path.open("rb") as source:
                raw = source.read(_MAX_SOURCE_BYTES + 1)
            if len(raw) > _MAX_SOURCE_BYTES:
                raise ValueError("source size")
            lines = raw.decode("utf-8-sig").splitlines()
        except (OSError, UnicodeError, ValueError):
            item["reason"] = "当前安装未提供可读取源码或文件超出读取范围"
            continue
        locations = []
        missing = []
        for marker in markers:
            index = next((i for i, line in enumerate(lines) if marker in line), None)
            if index is None:
                missing.append(marker)
            else:
                locations.append(
                    {
                        "symbol": marker,
                        "line_number": index + 1,
                        "line_preview": lines[index].strip()[:240],
                    }
                )
        item.update(
            available=True,
            sha256=hashlib.sha256(raw).hexdigest(),
            line_count=len(lines),
            locations=locations,
            missing_symbols=missing,
        )
    return {
        "scope": "当前安装源码位置，不是故障时版本，也不证明这些位置有缺陷",
        "next_step": "用返回的 file_path 和 line_number 调用 get_source_snippet 读取上下文；未找到的符号不得猜测行号",
        "sources": sources,
    }
