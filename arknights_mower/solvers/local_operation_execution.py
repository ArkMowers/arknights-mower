from datetime import datetime, timedelta

from arknights_mower.solvers.event_rerun import run_event_rerun
from arknights_mower.solvers.local_operation import (
    build_sanity_projection,
    compute_next_threshold_time,
)
from arknights_mower.solvers.mission import MissionSolver
from arknights_mower.solvers.player_info import PlayerInfoClient
from arknights_mower.solvers.record import save_exception
from arknights_mower.utils import config
from arknights_mower.utils.activity_observations import (
    activity_observation,
    finish_running_observations,
    observe_activity,
)
from arknights_mower.utils.crash_recovery import is_memory_error
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.datetime import format_time, get_server_weekday, is_game_date
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.email import send_message
from arknights_mower.utils.log import logger
from arknights_mower.utils.scheduler_task import scheduling


def run_local_operation(scheduler, one_time=False, *, manual=False):
    activity_started = False
    try:
        from arknights_mower.solvers.manual_tasks import manual_task_deadline

        conf = config.conf
        followup_due = (
            scheduler.local_operation_followup_time is not None
            and datetime.now() >= scheduler.local_operation_followup_time
        )
        if followup_due:
            scheduler.local_operation_followup_time = None
        logger.debug(
            "start mower_plan_solver | one_time=%s | followup_due=%s | last_execution=%s | current_tasks=%s",
            one_time,
            followup_due,
            scheduler.last_execution["maa"],
            len(scheduler.tasks),
            extra={"log_group": "local-operation"},
        )
        if (
            not one_time
            and not manual
            and not followup_due
            and scheduler.last_execution["maa"] is not None
            and (
                delta := (
                    timedelta(hours=conf.maa_gap)
                    + scheduler.last_execution["maa"]
                    - datetime.now()
                )
            )
            > timedelta()
        ):
            logger.info(
                "%s后开始刷理智",
                format_time(delta.total_seconds()),
                extra={"log_group": "local-operation"},
            )
        else:
            observe_activity(scheduler, "stage-plan", "mower", "running")
            activity_started = True

            def deadline():
                if manual:
                    return manual_task_deadline(scheduler)
                return fixed_deadline if one_time else scheduler.tasks[0].time

            fixed_deadline = datetime.now() + timedelta(days=1)
            rerun_played = run_event_rerun(scheduler, deadline)
            if rerun_played is not None and (
                config.maintenance_recheck.is_set()
                or (deadline() - datetime.now()) < timedelta(minutes=5)
            ):
                finish_running_observations(
                    scheduler,
                    "mower",
                    key="stage-plan",
                    outcome="checked",
                    reason="plan_checked",
                )
                return False if manual else None
            stages, _ = scheduler.mower_stage_plan()
            logger.debug(
                f"local operation plan: {stages}",
                extra={"log_group": "local-operation"},
            )
            if stages:
                logger.info(
                    "开始刷理智：%s",
                    "、".join(stages),
                    extra={"log_group": "local-operation"},
                )
            next_task_time = deadline()
            logger.debug(
                "local operation scheduling window | next_task_time=%s | one_time=%s",
                next_task_time.strftime("%Y-%m-%d %H:%M:%S"),
                one_time,
                extra={"log_group": "local-operation"},
            )

            executed_any = bool(rerun_played)
            inventory_unconfirmed = False
            skipped_stages = set()
            threshold_control_failed = False
            threshold_control_reason = ""
            next_threshold_time = None
            simulated_current_ap = None
            threshold = 0

            if stages and is_game_date(getattr(conf, "medicine_use_all_date", None)):
                threshold_control_failed = True
                threshold_control_reason = "use_all_medicine"
                logger.info(
                    "今天允许使用全部理智药，按游戏内剩余理智刷关",
                    extra={"log_group": "local-operation"},
                )
            elif stages:
                player_info = PlayerInfoClient()
                snapshot = player_info.get_first_available_snapshot()
                if snapshot is None:
                    logger.warning(
                        "没有读取到森空岛的理智，这次不按体力阈值计算作战次数",
                        extra={"log_group": "local-operation"},
                    )
                    threshold_control_failed = True
                    threshold_control_reason = "missing_player_info"
                else:
                    player_info.log_snapshot(snapshot)
                    # Fetch SKLand AP once before operation starts; after this point
                    # all AP changes are simulated locally by OperationSolver.
                    simulated_current_ap = snapshot.current_ap
                    threshold = max(
                        0,
                        int(
                            getattr(
                                config.conf.maa_weekly_plan[get_server_weekday()],
                                "sanity_threshold",
                                0,
                            )
                            or 0
                        ),
                    )
                    logger.debug(
                        "loaded local operation sanity context | skland_seed_ap=%s | threshold=%s | maa_gap=%s",
                        simulated_current_ap,
                        threshold,
                        conf.maa_gap,
                        extra={"log_group": "local-operation"},
                    )
                    if threshold <= 0:
                        logger.info(
                            "今天的体力阈值为 0，这次把当前理智刷完",
                            extra={"log_group": "local-operation"},
                        )
                        threshold_control_failed = True
                        threshold_control_reason = "threshold_non_positive"
                    if any(
                        scheduler.mower_stage_ap_cost(stage) is None for stage in stages
                    ):
                        missing = [
                            stage
                            for stage in stages
                            if scheduler.mower_stage_ap_cost(stage) is None
                        ]
                        logger.error(
                            f"关卡信息未找到，无法获取体力消耗: {missing}，"
                            "请在「刷理智周计划」中设置 AP fallback（关卡体力消耗默认值）",
                            extra={"log_group": "local-operation"},
                        )
                        logger.warning(
                            "有关卡缺少体力消耗，这次不按体力阈值计算作战次数",
                            extra={"log_group": "local-operation"},
                        )
                        threshold_control_failed = True
                        threshold_control_reason = "missing_ap_cost"

            if not stages:
                logger.info(
                    "今天没有需要刷的关卡，跳过刷理智",
                    extra={"log_group": "local-operation"},
                )
                scheduler.clear_local_operation_followups()
            else:
                mode = "fallback" if threshold_control_failed else "threshold"
                logger.debug(
                    "enter local operation stage loop | mode=%s | reason=%s",
                    mode,
                    threshold_control_reason or "",
                    extra={"log_group": "local-operation"},
                )
                scheduler.back_to_index()
                if threshold_control_failed:
                    scheduler.clear_local_operation_followups()

                attempted_stages = set()
                attempted_growth = set()
                while True:
                    stages, growth = scheduler.mower_stage_plan(
                        excluded_stages=attempted_stages,
                        attempted_growth=attempted_growth,
                    )
                    if not stages:
                        break
                    stage = stages[0]
                    growth_rule = growth.rules.get(stage) if growth else None
                    if growth_rule:
                        attempted_growth.add((growth.char_id, stage))
                    else:
                        attempted_stages.add(stage)
                    if manual:
                        next_task_time = manual_task_deadline(scheduler)
                    if next_task_time - datetime.now() < timedelta(minutes=5):
                        logger.info(
                            "离下一个任务开始不到 5 分钟，结束本次刷关",
                            extra={"log_group": "local-operation"},
                        )
                        break

                    if (
                        not threshold_control_failed
                        and scheduler.mower_stage_ap_cost(stage) is None
                    ):
                        threshold_control_failed = True
                        threshold_control_reason = "missing_ap_cost"
                        mode = "fallback"
                        scheduler.clear_local_operation_followups()
                        logger.warning(
                            "%s 缺少体力消耗，接下来不按体力阈值计算作战次数",
                            stage,
                            extra={"log_group": "local-operation"},
                        )

                    ap_cost, target_total_runs, projection = (
                        scheduler.get_local_operation_stage_target(
                            stage,
                            simulated_current_ap,
                            threshold_control_failed,
                            threshold,
                            conf.maa_gap,
                        )
                    )

                    if threshold_control_failed:
                        logger.debug(
                            "local operation fallback evaluation | stage=%s | ap_cost=%s | simulated_current_ap=%s | target_total_runs=%s",
                            stage,
                            ap_cost,
                            simulated_current_ap,
                            target_total_runs,
                            extra={"log_group": "local-operation"},
                        )
                    else:
                        logger.debug(
                            "local operation threshold evaluation | stage=%s | ap_cost=%s | simulated_current_ap=%s | threshold=%s | projection_minutes=%s | projected_ap=%s | excess_ap=%s | target_total_runs=%s",
                            stage,
                            ap_cost,
                            simulated_current_ap,
                            threshold,
                            projection.projection_minutes,
                            projection.projected_ap,
                            projection.excess_ap,
                            target_total_runs,
                            extra={"log_group": "local-operation"},
                        )

                    if (
                        simulated_current_ap is not None
                        and ap_cost is not None
                        and simulated_current_ap < ap_cost
                    ):
                        logger.info(
                            "估算剩余理智为 %s，不够打一次 %s（每次消耗 %s 理智），跳过这一关",
                            simulated_current_ap,
                            stage,
                            ap_cost,
                            extra={"log_group": "local-operation"},
                        )
                        continue
                    if target_total_runs is not None and target_total_runs <= 0:
                        logger.info(
                            "预计 %s内理智不会超过体力阈值 %s，跳过 %s",
                            format_time(projection.projection_minutes * 60),
                            threshold,
                            stage,
                            extra={"log_group": "local-operation"},
                        )
                        continue

                    stage_run_result = scheduler.run_local_operation_stage(
                        stage=stage,
                        next_task_time=next_task_time,
                        simulated_current_ap=simulated_current_ap,
                        ap_cost=ap_cost,
                        target_total_runs=target_total_runs,
                        mode=mode,
                        threshold=None if threshold_control_failed else threshold,
                        inventory_limit_rules=[growth_rule] if growth_rule else None,
                    )
                    simulated_current_ap = stage_run_result["simulated_current_ap"]
                    executed_any = executed_any or stage_run_result["executed_any"]
                    if stage_run_result.get("inventory_unconfirmed", False):
                        inventory_unconfirmed = True
                        scheduler.clear_local_operation_followups()
                    if stage_run_result.get("annihilation_skipped", False):
                        skipped_stages.add(stage)
                    if stage_run_result["should_break"]:
                        break

                # A skipped Annihilation stage gets no follow-up from this
                # dispatch; the next dispatch checks it again.
                remaining_stages, _ = scheduler.mower_stage_plan(
                    excluded_stages=skipped_stages
                )
                if not remaining_stages:
                    scheduler.clear_local_operation_followups()
                if (
                    remaining_stages
                    and not inventory_unconfirmed
                    and not threshold_control_failed
                    and not one_time
                    and not manual
                    and simulated_current_ap is not None
                ):
                    projection = build_sanity_projection(
                        simulated_current_ap,
                        threshold,
                        conf.maa_gap,
                    )
                    next_threshold_time = compute_next_threshold_time(
                        simulated_current_ap,
                        threshold,
                    )
                    if projection.excess_ap > 0:
                        next_threshold_time = max(
                            datetime.now() + timedelta(minutes=1),
                            next_threshold_time,
                        )
                    logger.debug(
                        "computed local operation follow-up time | simulated_current_ap=%s | threshold=%s | projection_minutes=%s | projected_ap=%s | excess_ap=%s | next_threshold_time=%s",
                        simulated_current_ap,
                        threshold,
                        projection.projection_minutes,
                        projection.projected_ap,
                        projection.excess_ap,
                        next_threshold_time.strftime("%Y-%m-%d %H:%M:%S")
                        if next_threshold_time is not None
                        else None,
                        extra={"log_group": "local-operation"},
                    )
                    logger.info(
                        "本地刷关阈值复查安排在 %s",
                        next_threshold_time.strftime("%m-%d %H:%M"),
                        extra={"log_group": "local-operation"},
                    )
                    scheduler.upsert_local_operation_followup(next_threshold_time)

            finish_running_observations(
                scheduler,
                "mower",
                key="stage-plan",
                outcome="checked",
                reason="plan_checked",
            )
            if skipped_stages:
                # 关卡检查已结束，领取任务奖励失败时仍保留本次剿灭检查时间。
                scheduler.last_execution["maa"] = datetime.now()
            logger.debug(
                "run mission solver after local operation",
                extra={"log_group": "local-operation"},
            )
            with activity_observation(
                scheduler, "mission", "mower", stopped_exceptions=(MowerExit,)
            ):
                MissionSolver(scheduler.device, scheduler.recog).run()
            # A skipped Annihilation stage counts as a local run, so the next
            # check waits for maa_gap instead of the next main-loop pass.
            if executed_any or inventory_unconfirmed or skipped_stages:
                scheduler.last_execution["maa"] = datetime.now()
                logger.debug(
                    f"record local task execution time: {scheduler.last_execution['maa']}",
                    extra={"log_group": "local-operation"},
                )
            else:
                logger.debug(
                    "local operation finished without executing any stage",
                    extra={"log_group": "local-operation"},
                )

        scheduler._refresh_workshop_inventory()
        scheduling(scheduler.tasks, op_data=getattr(scheduler, "op_data", None))
    except (MowerExit, DeviceRecoveryError, SharedADBError):
        if activity_started:
            finish_running_observations(
                scheduler,
                "mower",
                key="stage-plan",
                outcome="stopped",
                reason="interrupted",
            )
        raise
    except Exception as e:
        if activity_started:
            finish_running_observations(
                scheduler,
                "mower",
                key="stage-plan",
                outcome="error",
                reason="exception",
            )
        if is_memory_error(e):
            raise
        save_exception(e)
        logger.exception(e, extra={"log_group": "local-operation"})
        scheduler.device.exit()
        send_message(str(e), "本地作战任务出错", level="ERROR")
        if manual:
            raise
        scheduler.check_current_focus()
    finally:
        if activity_started:
            finish_running_observations(
                scheduler,
                "mower",
                key="stage-plan",
                outcome="checked",
                reason="plan_checked",
            )
