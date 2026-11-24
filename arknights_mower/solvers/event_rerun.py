from datetime import datetime
from time import monotonic

from arknights_mower.solvers import record
from arknights_mower.solvers.activity_navigation import ActivityNavigation
from arknights_mower.solvers.manual_tasks import (
    long_task_deadline,
    resume_dorm_releases,
)
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.solvers.operation import OperationSolver
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import CopilotConf, CopilotScriptConf
from arknights_mower.utils.csleep import MowerExit, check_cancelled, csleep
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.event_rerun import STAGE_SECONDS, current_rerun
from arknights_mower.utils.log import logger
from arknights_mower.utils.long_task_windows import long_task_schedule
from arknights_mower.utils.maa_backup import MaaCallError
from arknights_mower.utils.maa_copilot import (
    MAX_SCRIPT_BYTES,
    build_copilot_params,
    parse_script,
    script_path,
)
from arknights_mower.utils.scene import Scene


def pending_rerun(scheduler):
    conf = config.conf
    now = datetime.now()
    kind, cutoff, _ = long_task_schedule(conf, now)
    if kind != "event_rerun":
        return None
    settings = conf.event_rerun
    if not settings.event_key:
        return None
    if (long_task_deadline(scheduler, cutoff) - now).total_seconds() < STAGE_SECONDS:
        return None
    try:
        event = current_rerun()
    except (OSError, ValueError):
        logger.exception("读取复刻SS活动关卡失败")
        return None
    if not event or event["key"] != settings.event_key:
        return None

    progress = record.load_event_rerun_progress(event["key"])
    fingerprint = settings.model_dump_json()
    blocked_key, blocked = getattr(scheduler, "event_rerun_blocked", (None, set()))
    if blocked_key != fingerprint:
        blocked = set()
        scheduler.event_rerun_blocked = fingerprint, blocked

    stages = [stage for stage in event["stages"] if stage["code"] in settings.stages]
    if settings.raid_enabled and settings.script_id and event["raid"]:
        stages.append(event["raid"])
    for stage in stages:
        code = stage["code"]
        if (
            code not in progress
            and code not in blocked
            and stage["start_ts"] <= event["now"]
            and stage["end_ts"] - event["now"] >= STAGE_SECONDS
        ):
            return event, stage, settings.model_copy(deep=True), blocked
    return None


def _raid_params(stage, settings):
    target = stage["code"].removesuffix(" 突袭")
    with script_path(settings.script_id).open("rb") as stream:
        stage_name = parse_script(stream.read(MAX_SCRIPT_BYTES + 1))[
            "stage_name"
        ].strip()
    if stage_name.casefold() not in {
        name.casefold() for name in stage["script_stage_names"]
    }:
        raise ValueError(f"所选作业的关卡与 {target} 不符")
    return target, build_copilot_params(
        CopilotConf(
            formation=True,
            use_sanity_potion=settings.use_sanity_potion,
            scripts=[
                CopilotScriptConf(
                    id=settings.script_id, nav_name_override=target, is_raid=True
                )
            ],
        )
    )


def _play_ordinary(scheduler, stage, settings, prepare, claim, complete):
    navigator = NavigationSolver(scheduler.device, scheduler.recog)
    with device_io_budget(prepare):
        if (
            not navigator.run(stage["code"])
            or navigator.scene() != Scene.OPERATOR_BEFORE
        ):
            return "blocked"
        target = navigator.normalize_stage_text(stage["code"])
        if not any(
            navigator.normalize_stage_text(text) == target
            for _, text, _ in ActivityNavigation(navigator).read()
        ):
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


def _play_raid(scheduler, stage, settings, prepare, claim, complete):
    if scheduler._maa_refresh_deadline() is not None:
        return "defer"
    target, params = _raid_params(stage, settings)
    task_id = None
    start_called = False
    ended = False

    def on_task_event(msg, details):
        if (
            msg == 10002
            and task_id is not None
            and details.get("taskid") == task_id
            and details.get("taskchain") == "Copilot"
        ):
            try:
                complete()
            except Exception:
                logger.exception("保存复刻SS活动突袭结算失败")

    try:
        with device_io_budget(prepare):
            scheduler.initialize_maa(on_task_event=on_task_event)
            navigator = NavigationSolver(scheduler.device, scheduler.recog)
            if not navigator.run(target):
                return "blocked"
            scheduler.recog.update()
            scheduler.scene_graph_navigation(Scene.OPERATOR_CHOOSE_LEVEL)
            if scheduler.scene() != Scene.OPERATOR_CHOOSE_LEVEL:
                return "blocked"
            task_id = scheduler.MAA.append_task("Copilot", params)
        if scheduler._maa_refresh_deadline() is not None or not claim():
            return "defer"
        start_called = True
        try:
            scheduler.MAA.start()
        except MaaCallError as exc:
            if exc.operation != "start":
                raise
            logger.warning("复刻SS活动突袭未能启动：%s", exc)
            return "rejected"
        while scheduler.MAA.running():
            if config.stop_maa.is_set():
                return "defer"
            csleep(1)
        ended = True
        return "attempted"
    finally:
        try:
            if start_called and not ended:
                scheduler.MAA.stop()
        finally:
            record.battle_inventory_active.clear()
            scheduler.release_maa()
            scheduler.recog.reset_after_external_control()


def run_event_rerun(scheduler):
    pending = pending_rerun(scheduler)
    if pending is None:
        return False
    config.stop_maa.clear()
    started_any = False

    try:
        while pending is not None:
            event, stage, settings, blocked = pending
            key, code = event["key"], stage["code"]
            observed_at = monotonic()
            navigation_deadline = observed_at + 60

            def available():
                now = datetime.now()
                kind, cutoff, _ = long_task_schedule(config.conf, now)
                if kind != "event_rerun":
                    return 0
                return min(
                    (long_task_deadline(scheduler, cutoff) - now).total_seconds(),
                    stage["end_ts"] - event["now"] - (monotonic() - observed_at),
                )

            def can_start():
                check_cancelled()
                return (
                    not config.stop_maa.is_set()
                    and not config.maintenance_recheck.is_set()
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

            def claim():
                nonlocal claimed
                claimed = can_start() and record.claim_event_rerun_stage(key, code)
                return claimed

            def complete(key=key, code=code):
                record.complete_event_rerun_stage(key, code)

            try:
                if stage is event["raid"]:
                    outcome = _play_raid(
                        scheduler,
                        stage,
                        settings,
                        prepare,
                        claim,
                        complete,
                    )
                else:
                    outcome = _play_ordinary(
                        scheduler, stage, settings, prepare, claim, complete
                    )
            except (MowerExit, SharedADBError, DeviceRecoveryError):
                raise
            except InterruptedError:
                started_any |= claimed
                break
            except Exception:
                logger.exception("复刻SS活动关卡 %s 未完成", code)
                outcome = "blocked"
            if outcome == "rejected":
                record.release_event_rerun_stage(key, code)
                blocked.add(code)
                claimed = False
            started_any |= claimed
            if outcome == "defer" or not can_start():
                break
            if outcome == "blocked" and not claimed:
                logger.warning("复刻SS活动关卡 %s 未能开始", code)
                blocked.add(code)
            pending = pending_rerun(scheduler)
    finally:
        resume_dorm_releases(scheduler)
    return started_any
