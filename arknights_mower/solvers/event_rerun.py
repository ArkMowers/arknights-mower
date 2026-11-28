import sqlite3
from datetime import datetime
from time import monotonic

from arknights_mower.solvers import record
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.solvers.operation import OperationSolver
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, check_cancelled
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.event_rerun import current_rerun
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene_recovery import SceneRecoveryExhausted


def pending_rerun(scheduler, deadline, visited=()):
    conf = config.conf
    settings = getattr(conf, "event_rerun", None)
    if not settings or not settings.enabled or not conf.stage_plan_enable:
        return None
    if deadline() <= datetime.now():
        return None
    observed_at = monotonic()
    try:
        event = current_rerun()
        if not event:
            return None
        reasons = {}
        progress = record.event_rerun_status(event["key"], failure_reasons=reasons)
    except (OSError, ValueError, sqlite3.Error):
        logger.exception("读取复刻SS活动关卡或进度失败，本轮继续执行周计划")
        return None
    for stage in event["stages"]:
        code = stage["code"]
        if (event["key"], code) in visited:
            continue
        eligible = code not in progress or (
            progress[code] == "failed"
            and record.event_rerun_failure_retries(reasons.get(code))
        )
        if eligible and stage["start_ts"] <= event["now"] < stage["end_ts"]:
            return event, stage, settings.model_copy(deep=True), observed_at
    return None


def _play_ordinary(scheduler, stage, settings, prepare, claim, complete, fail):
    navigator = NavigationSolver(scheduler.device, scheduler.recog)
    with device_io_budget(prepare):
        if not navigator.run(stage["code"]):
            fail("未能导航到目标关卡")
            return
        if not navigator.confirm_selected_stage():
            fail("未能在详情页确认目标关卡")
            return

    battle_started = False

    def start_single_battle():
        nonlocal battle_started
        battle_started = claim()
        return battle_started

    def remaining():
        return float("inf") if battle_started else prepare()

    with device_io_budget(remaining):
        result = OperationSolver(scheduler.device, scheduler.recog).run(
            stage_id=stage["code"],
            ap_cost=stage["ap_cost"],
            inventory_limit_rules=[],
            use_sanity_potion=settings.use_sanity_potion,
            before_single_battle=start_single_battle,
            on_single_battle_settlement=complete,
            on_single_battle_failure=fail,
        )
    if result["executed_runs"] and battle_started:
        return
    if result["sanity_drain"] or result.get("stopped_by_deadline"):
        return "defer"
    if not battle_started:
        fail("未能完成单次代理作战准备")


def run_event_rerun(scheduler, deadline) -> bool | None:
    """Return None if no stage was eligible, otherwise whether a battle was admitted."""
    visited = set()
    pending = pending_rerun(scheduler, deadline, visited)
    if pending is None:
        return None
    started_any = False

    while pending is not None:
        event, stage, settings, observed_at = pending
        key, code = event["key"], stage["code"]
        visited.add((key, code))

        def available():
            now = datetime.now()
            return min(
                (deadline() - now).total_seconds(),
                stage["end_ts"] - event["now"] - (monotonic() - observed_at),
            )

        def can_start():
            check_cancelled()
            return (
                not config.stop_maa.is_set()
                and not config.maintenance_recheck.is_set()
                and config.conf.stage_plan_enable
                and config.conf.event_rerun == settings
                and available() > 0
            )

        def prepare():
            if not can_start():
                raise InterruptedError
            time_left = available()
            if time_left <= 0:
                raise InterruptedError
            return time_left

        claimed = False
        already_claimed = False
        reported_failure = False

        def claim():
            nonlocal claimed, already_claimed
            if not can_start():
                return False
            if not record.claim_event_rerun_stage(key, code, previous):
                already_claimed = True
                return False
            try:
                claimed = can_start()
                return claimed
            finally:
                if not claimed:
                    record.release_event_rerun_stage(key, code, previous)

        def complete(key=key, code=code):
            record.complete_event_rerun_stage(key, code)

        def fail(reason):
            nonlocal reported_failure
            if reported_failure or already_claimed or (not claimed and not can_start()):
                return
            record.fail_event_rerun_stage(
                key, code, reason, attempted=claimed, previous=previous
            )
            reported_failure = True

        try:
            with record.event_rerun_execution(key, code) as previous:
                outcome = None
                if previous is not None:
                    try:
                        outcome = _play_ordinary(
                            scheduler, stage, settings, prepare, claim, complete, fail
                        )
                    except (
                        MowerExit,
                        SharedADBError,
                        DeviceRecoveryError,
                        SceneRecoveryExhausted,
                        InterruptedError,
                        sqlite3.Error,
                    ):
                        raise
                    except Exception:
                        logger.exception("复刻SS活动关卡 %s 未完成", code)
                        if not claimed:
                            fail("准备关卡时发生异常，详情请查看日志")
        except InterruptedError:
            started_any |= claimed
            break
        except sqlite3.Error:
            logger.exception("读写复刻SS活动关卡 %s 进度失败", code)
            started_any |= claimed
            break
        started_any |= claimed
        if outcome == "defer" or not can_start():
            break
        pending = pending_rerun(scheduler, deadline, visited)
    return started_any
