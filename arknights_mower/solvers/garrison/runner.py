"""在现有大型任务空档执行个人极速模拟。"""

from datetime import datetime, timedelta

from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger

from .model import prepare_progress, status
from .solver import HANDOVER_SECONDS, MATCH_SECONDS, GarrisonSolver


def eligible_progress(conf, window):
    if window < 9 * 60:
        return None
    progress = prepare_progress(conf, record.load_garrison_progress())
    if not progress.get("match") and window < MATCH_SECONDS + HANDOVER_SECONDS:
        return None
    if progress.get("failed") or status(conf, progress)["completed"]:
        return None
    return progress


def run_garrison(scheduler):
    from arknights_mower.solvers.manual_tasks import (
        long_task_deadline,
        resume_dorm_releases,
    )

    conf = config.conf
    if not conf.GARRISON:
        return False
    limit = datetime.now() + timedelta(hours=24)

    def deadline():
        return long_task_deadline(scheduler, limit)

    window = (deadline() - datetime.now()).total_seconds()
    progress = eligible_progress(conf, window)
    if progress is None:
        return False
    record.save_garrison_progress(progress)
    config.stop_maa.clear()
    solver = GarrisonSolver(
        scheduler.device,
        scheduler.recog,
        progress,
        record.save_garrison_progress,
        target_wins=conf.garrison.target_wins,
        deadline=deadline,
    )
    logger.info("开始卫戍协议个人极速模拟")
    try:
        solver.run()
    except MowerExit:
        raise
    except Exception as exc:
        progress.update(failed=True, error=str(exc))
        record.save_garrison_progress(progress)
        logger.error(f"卫戍协议保留当前对局：{exc}")
    finally:
        resume_dorm_releases(scheduler)
    return True
