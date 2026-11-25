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
from arknights_mower.utils.event_rerun import STAGE_SECONDS, current_rerun
from arknights_mower.utils.log import logger


def pending_rerun(scheduler, deadline):
    conf = config.conf
    settings = getattr(conf, "event_rerun", None)
    if not settings or not settings.enabled or not conf.stage_plan_enable:
        return None
    if (deadline() - datetime.now()).total_seconds() < STAGE_SECONDS:
        return None
    observed_at = monotonic()
    try:
        event = current_rerun()
        if not event:
            return None
        progress = record.event_rerun_status(event["key"])
    except (OSError, ValueError, sqlite3.Error):
        logger.exception("读取复刻SS活动关卡或进度失败，本轮继续执行周计划")
        return None
    fingerprint = (event["key"], settings.use_sanity_potion)
    blocked_key, blocked = getattr(scheduler, "event_rerun_blocked", (None, set()))
    if blocked_key != fingerprint:
        blocked = set()
        scheduler.event_rerun_blocked = fingerprint, blocked

    for stage in event["stages"]:
        code = stage["code"]
        if (
            code not in progress
            and code not in blocked
            and stage["start_ts"] <= event["now"]
            and stage["end_ts"] - event["now"] >= STAGE_SECONDS
        ):
            return event, stage, settings.model_copy(deep=True), blocked, observed_at
    return None


def _play_ordinary(scheduler, stage, settings, prepare, claim, complete):
    navigator = NavigationSolver(scheduler.device, scheduler.recog)
    with device_io_budget(prepare):
        if not navigator.run(stage["code"]) or not navigator.confirm_selected_stage():
            return "blocked"

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
        )
    if result["executed_runs"]:
        return "completed"
    if result["sanity_drain"]:
        return "defer"
    return "blocked"


def run_event_rerun(scheduler, deadline) -> bool | None:
    """Return None if no stage was eligible, otherwise whether a battle was admitted."""
    pending = pending_rerun(scheduler, deadline)
    if pending is None:
        return None
    started_any = False

    while pending is not None:
        event, stage, settings, blocked, observed_at = pending
        key, code = event["key"], stage["code"]
        navigation_deadline = monotonic() + 60

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
                and available() >= STAGE_SECONDS
            )

        def prepare():
            if not can_start():
                raise InterruptedError
            spare = available() - STAGE_SECONDS
            if spare <= 0:
                raise InterruptedError
            navigation_left = navigation_deadline - monotonic()
            if navigation_left <= 0:
                raise TimeoutError("复刻SS活动导航超时")
            return min(spare, navigation_left)

        claimed = False
        already_claimed = False

        def claim():
            nonlocal claimed, already_claimed
            if not can_start():
                return False
            if not record.claim_event_rerun_stage(key, code):
                already_claimed = True
                return False
            try:
                claimed = can_start()
                return claimed
            finally:
                if not claimed:
                    record.release_event_rerun_stage(key, code)

        def complete(key=key, code=code):
            record.complete_event_rerun_stage(key, code)

        try:
            with record.event_rerun_execution(key, code) as active:
                if active:
                    outcome = _play_ordinary(
                        scheduler, stage, settings, prepare, claim, complete
                    )
                else:
                    outcome = "skipped"
        except (MowerExit, SharedADBError, DeviceRecoveryError):
            raise
        except InterruptedError:
            started_any |= claimed
            break
        except Exception:
            logger.exception("复刻SS活动关卡 %s 未完成", code)
            outcome = "blocked"
        started_any |= claimed
        if outcome == "defer" or not can_start():
            break
        if outcome == "blocked" and not claimed and not already_claimed:
            logger.warning("复刻SS活动关卡 %s 未能开始", code)
            blocked.add(code)
        pending = pending_rerun(scheduler, deadline)
    return started_any
