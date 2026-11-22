"""在现有大型任务空档执行个人极速模拟。"""

from datetime import datetime

from arknights_mower.solvers import record
from arknights_mower.utils import config, maa_control
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger
from arknights_mower.utils.long_task_windows import ONE_DAY, long_task_schedule
from arknights_mower.utils.scheduler_task import find_next_task

from .model import goal_reached, prepare_progress
from .solver import MATCH_SECONDS, GarrisonSolver, GarrisonYield


def dispatch_window(scheduler, run_key, match_limit, opening):
    pending = find_next_task(scheduler.tasks, op_data=scheduler.op_data)
    return (
        run_key,
        match_limit,
        opening,
        (pending.type, pending.time) if pending else None,
    )


def eligible_progress(conf, window, scheduler, opening):
    if window < 9 * 60:
        return None
    progress = prepare_progress(conf, record.load_garrison_progress())
    settings = conf.garrison
    match_limit = settings.match_limit if settings.mode == "matches" else None
    if getattr(scheduler, "garrison_last_window", None) == dispatch_window(
        scheduler, progress["key"], match_limit, opening
    ):
        return None
    if goal_reached(progress, settings.target_wins, match_limit):
        return None
    if not progress.get("match") and window < MATCH_SECONDS:
        return None
    return progress


@maa_control.execution()
def run_garrison(scheduler):
    from arknights_mower.solvers.manual_tasks import (
        long_task_deadline,
        resume_dorm_releases,
    )

    conf = config.conf
    dispatched_at = datetime.now()
    kind, limit, opening = long_task_schedule(conf, dispatched_at)
    if kind != "garrison":
        return False

    settings = conf.garrison.model_copy()
    deadline_reason = "执行时段结束"

    def deadline():
        nonlocal deadline_reason
        now = datetime.now()
        active, cutoff, _ = long_task_schedule(config.conf, now)
        if active != "garrison":
            deadline_reason = "执行时段结束" if now >= limit else "执行时段变更或停用"
            return now
        if config.conf.garrison != settings:
            deadline_reason = "卫戍协议设置变更"
            return now
        window_end = min(limit, cutoff)
        actual_end = long_task_deadline(scheduler, window_end)
        if actual_end < window_end:
            deadline_reason = "下一项基建任务到期"
        elif window_end == limit == dispatched_at + ONE_DAY:
            deadline_reason = "24 小时运行上限"
        else:
            deadline_reason = "执行时段结束"
        return actual_end

    actual_end = deadline()
    window = (actual_end - datetime.now()).total_seconds()
    progress = eligible_progress(conf, window, scheduler, opening)
    if progress is None:
        return False
    progress["error"] = ""
    record.save_garrison_progress(progress)
    solver = GarrisonSolver(
        scheduler.device,
        scheduler.recog,
        progress,
        record.save_garrison_progress,
        target_wins=settings.target_wins,
        match_limit=settings.match_limit if settings.mode == "matches" else None,
        deadline=deadline,
    )
    logger.debug(
        "卫戍协议派发诊断：开始=%s，时段来源=%s，时段上限=%s，实际截止=%s，截止依据=%s",
        dispatched_at,
        "旧每日时段" if conf.maa_long_task_weekly_windows is None else "周计划",
        limit,
        actual_end,
        deadline_reason,
    )
    logger.info("开始卫戍协议个人极速模拟")
    try:
        solver.run()
        if solver.yield_reason is not None:
            logger.debug(
                "卫戍协议交还设备原因：%s",
                deadline_reason
                if solver.yield_reason == GarrisonYield.DEADLINE
                else solver.yield_reason,
            )
    except MowerExit:
        logger.debug("卫戍协议交还设备原因：Mower 停止")
        raise
    except Exception as exc:
        progress["error"] = str(exc)
        record.save_garrison_progress(progress)
        logger.error(f"卫戍协议保留当前对局：{exc}")
    finally:
        resume_dorm_releases(scheduler)
        scheduler.garrison_last_window = dispatch_window(
            scheduler, progress["key"], solver.match_limit, opening
        )
    return True
