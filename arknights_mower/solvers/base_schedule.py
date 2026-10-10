import copy
import math
import os
import pathlib
import re
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta
from time import monotonic
from typing import Literal, Optional

import cv2
import requests
from packaging.version import InvalidVersion, Version

from arknights_mower.data import (
    agent_list,
    agent_profession,
    base_room_list,
    stage_data_full,
    workshop_formula,
)
from arknights_mower.solvers.base_mixin import (
    AgentSelectionNotReady,
    AgentSelectionPageChanged,
    BaseMixin,
    agent_card_selected,
    fixed_selection_profile,
)
from arknights_mower.solvers.credit import CreditSolver
from arknights_mower.solvers.cultivate_depot import cultivate as cultivateDepotSolver
from arknights_mower.solvers.depotREC import depotREC as DepotSolver
from arknights_mower.solvers.emergency import RESUME_META, EmergencyRecoveryMixin
from arknights_mower.solvers.local_operation import (
    FOLLOWUP_TASK_META,
    build_sanity_projection,
    compute_next_threshold_time,
    get_required_runs_total,
    get_stage_drain_runs_total,
)
from arknights_mower.solvers.mail import MailSolver
from arknights_mower.solvers.mission import MissionSolver
from arknights_mower.solvers.navigation import NavigationSolver
from arknights_mower.solvers.operation import OperationSolver
from arknights_mower.solvers.player_info import PlayerInfoClient
from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
from arknights_mower.solvers.record import (
    apply_workshop_inventory,
    battle_inventory_active,
    get_inventory_counts,
    invalidate_workshop_inventory,
    save_agent_action,
    save_exception,
    save_log,
)
from arknights_mower.solvers.recruit import RecruitSolver
from arknights_mower.solvers.report import ReportSolver
from arknights_mower.solvers.secret_front import SecretFront
from arknights_mower.solvers.shop import CreditShop
from arknights_mower.solvers.skland import SKLand
from arknights_mower.utils import config, detector, rapidocr
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.character_recognize import estimate_agent_mood
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.datetime import (
    format_time,
    get_server_weekday,
)
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    guard_adb,
)
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import io_timeout
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.dorm_candidates import (
    dorm_candidate_mood,
    dorm_candidates,
    dorm_task_reservations,
    vacant_dorm_slots,
)
from arknights_mower.utils.email import maa_template, send_message, task_template
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.maa_callback import (
    REPORT_REQUEST,
    MaaCallbackLog,
    parse_details,
)
from arknights_mower.utils.maa_report import upload_report
from arknights_mower.utils.manufacture_product import (
    DRONE_SECONDS,
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
    current_unit_remaining,
    drone_plan,
    parse_product_task_meta,
    product_task_meta,
)
from arknights_mower.utils.operation_timing import (
    estimate_dorm_minutes,
    record_selection_retry,
    timed_room,
    timed_step,
)
from arknights_mower.utils.operators import (
    TRADE_ORDER_AGENTS,
    Operator,
    Operators,
)
from arknights_mower.utils.path import get_path, resolve_config_path
from arknights_mower.utils.plan import RIGHT_SIDE_ROOM_CAPACITY
from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene
from arknights_mower.utils.resource_pkg import refresh_resource_at_boundary
from arknights_mower.utils.resting_priority import (
    RestingTier,
    bed_takeover_allowed,
    crafting_rest_candidates,
    has_resting_mood,
    resting_key,
    resting_mood,
    resting_tier,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    adjust_run_order_for_maintenance,
    blocked_run_order_ids,
    defer_dorm_before_priority_task,
    dorm_rebalance_signature,
    dorm_residents,
    find_next_task,
    plan_dorm_isolation,
    plan_metadata,
    prioritize_new_dorm_recovery,
    protect_priority_tasks,
    rebalance_plan_swap_dorms,
    restore_displaced_resting,
    scheduling,
    simplify_dorm_fill,
    try_add_release_dorm,
    try_reorder,
    try_workshop_tasks,
)
from arknights_mower.utils.simulator import restart_simulator
from arknights_mower.utils.skland_log import redact_signing_text
from arknights_mower.utils.trading_order import TradingOrder
from arknights_mower.utils.workshop_ui import (
    CONFIRM_OPERATOR,
    FORMULA_TABS,
    OPEN_FORMULA,
    scale_point,
)

# 只保留在当前进程；进房失败后即使重建调度器，也不再自动巡检训练室。
_training_room_scan_disabled = False


def _is_mastery_busy(operator_name: str) -> bool:
    try:
        from arknights_mower.utils.mastery_db import is_operator_busy

        return is_operator_busy(operator_name)
    except Exception:
        return False


def _merge_dorm_arrangement(plan: dict, dorm_plan: dict) -> None:
    """把同一轮演算出的动态床位直接并入下班任务。"""
    for room, names in dorm_plan.items():
        target = plan.setdefault(room, ["Current"] * len(names))
        for index, name in enumerate(names):
            if name != "Current":
                target[index] = name


def _merge_shift_transition(plan: dict, overlay: dict, op_data: Operators) -> None:
    """新换班位置覆盖旧位置；未执行的旧入住取消，不为它额外清床。"""
    destinations = {
        name: (room, index)
        for room, names in overlay.items()
        for index, name in enumerate(names)
        if name not in ("Current", "Free", "")
    }
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name in destinations and destinations[name] != (room, index):
                names[index] = "Current"
    _merge_plan_overlay(plan, overlay, op_data)


def _merge_plan_overlay(plan: dict, overlay: dict, op_data: Operators) -> None:
    """把内存演算的一层结果覆盖到最终任务，不产生中间任务。"""
    for room, names in overlay.items():
        if room in RIGHT_SIDE_ROOM_CAPACITY:
            if not names:
                continue
            target = plan.setdefault(room, [])
            target.extend(["Current"] * (len(names) - len(target)))
        else:
            if room not in op_data.plan:
                continue
            target = plan.setdefault(room, ["Current"] * len(op_data.plan[room]))
        for index, name in enumerate(names[: len(target)]):
            if name != "Current":
                target[index] = name


def _assigned_operator_names(plan: dict) -> set[str]:
    return {
        name
        for room, names in plan.items()
        if not room.startswith("dormitory_")
        for name in names
        if name not in ("", "Current", "Free")
    }


def _stop_if_scheduled_trainee(
    solver, trainee: str, room_state, *, detail_open=False
) -> None:
    # 进驻不等于开训；只用本次读到的有效训练倒计时阻断排班。
    if (
        room_state is None
        or room_state.read_failed
        or room_state.state != "training"
        or getattr(room_state.panel, "countdown_state", None) != "active"
    ):
        return
    from arknights_mower.utils.mastery_support_data import trainee_schedule_conflict

    reason = trainee_schedule_conflict(trainee)
    if reason is None:
        return
    message = (
        f"训练室检测到排班冲突：{reason}。为避免工作干员被手动专精占用导致卡表，"
        "已停止 Mower；请结束训练或从非训练室排班中移除该干员后再启动"
    )
    logger.warning(message)
    try:
        send_message(message, level="WARNING")
    except Exception as exc:
        logger.warning(f"训练室排班冲突通知发送失败: {exc}")
    # 通用心情读取停在进驻详情浮窗；先关浮窗，再退出训练室。
    try:
        if detail_open:
            solver.back()
        solver.back()
    except Exception as exc:
        logger.warning(f"训练室排班冲突后退出房间失败: {exc}")
    try:
        from arknights_mower.solvers.record import save_current_state

        save_current_state()
    except Exception as exc:
        logger.warning(f"训练室排班冲突后保存状态失败: {exc}")
    config.stop_mower.set()
    raise MowerExit


def _add_group_to_fix_plan(fix_plan: dict, op_data: Operators, group: str) -> None:
    """把组内真正不在岗的成员写进 fix_plan；已在静态槽位的成员跳过。

    已在岗成员写进去只是 no-op：arrange 逐房间对比后「任务与当前房间相同，
    跳过」。当唯一真实修复项（如训练室）被 _suppress_train_correction 抑制时，
    no-op 项撑起 fix_plan 永不收敛 → 排班死循环（#229）。
    """
    for name in op_data.groups[group]:
        agent = op_data.operators[name]
        if agent.room == agent.current_room and agent.index == agent.current_index:
            continue
        if agent.room not in fix_plan:
            fix_plan[agent.room] = ["Current"] * len(op_data.plan[agent.room])
        fix_plan[agent.room][agent.index] = name


def _maa_client_type(device=None) -> str:
    """推导 MAA 集成协议的客户端类型：官服 Official，B 服 Bilibili。"""
    package = getattr(device, "game_package", None)
    if package in {"com.hypergryph.arknights", "com.hypergryph.arknights.bilibili"}:
        return "Official" if package == "com.hypergryph.arknights" else "Bilibili"
    return "Official" if config.conf.package_type == 1 else "Bilibili"


# 战术分队类（对照 RoguelikeSquadIsProfessional），凹开局直升精二仅对这类分队下发
_PROFESSIONAL_SQUADS = (
    "突击战术分队",
    "堡垒战术分队",
    "远程战术分队",
    "破坏战术分队",
)

# 刷开局期望奖励键，与协议 collectible_mode_start_list 的九项一致
_COLLECTIBLE_START_KEYS = (
    "hot_water",
    "shield",
    "ingot",
    "hope",
    "random",
    "key",
    "dice",
    "ideas",
    "ticket",
)


class RoomArrangementDeferred(RuntimeError):
    """房间重试暂未成功，保留剩余任务并把调度权交回队列。"""

    def __init__(self, room, error):
        super().__init__(str(error))
        self.room = room


# MAA 掉落统计：回调随时可能到达，模块级初值保证首次回调不会因缺名而中断。
stage_drop = {"details": [], "summary": {}}


def _drop_entries(value):
    """掉落条目必须是对象列表；畸形负载不得进入 maa_stop 汇报模板。"""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def reset_stage_drop():
    """开始新一轮 MAA 前清空掉落统计，供回调累积与 maa_stop 汇报共用。"""
    stage_drop["details"] = []
    stage_drop["summary"] = {}


class ProductSwitchDeferred(Exception):
    def __init__(self, message: str, minutes: float = 15):
        super().__init__(message)
        self.minutes = minutes


class GroupShiftBlocked(ProductSwitchDeferred):
    def __init__(self, groups):
        self.groups = set(groups)
        waiting = "、".join(sorted(groups)) + "回班" if groups else "替班可用"
        super().__init__(f"多绑组替班冲突，挂起换班，等待{waiting}")


class BaseSchedulerSolver(EmergencyRecoveryMixin, SceneGraphSolver, BaseMixin):
    """
    收集基建的产物：物资、赤金、信赖
    """

    # MAA 回调日志：每次 initialize_maa 建立新实例，本轮 MAA 的可读进度行来自它。
    maa_callback: MaaCallbackLog | None = None

    def __init__(
        self,
        device: Device = None,
        recog: Recognizer = None,
        *,
        connection_retries: int = 3,
    ) -> None:
        super().__init__(device, recog, connection_retries=connection_retries)
        self.op_data = None
        self.party_time = None
        self.drone_time = None
        self.reload_time = None
        self.clue_count_limit = 9
        self.enable_party = True
        self.leifeng_mode = False
        self.digit_reader = DigitReader()
        self.error = False
        self.clue_count = 0
        self.tasks = []
        self.waiting_group_shifts = []
        self.free_clue = None
        self.credit_fight = None
        self.task_count = 0
        self.refresh_connecting = False
        self.recruit_time = None
        self.last_clue = None
        self.sleeping = False
        self._simulator_closed_for_idle = False
        self._idle_observation_pending = False
        self.operators = {}
        self.last_execution = {"maa": None, "recruit": None, "todo": None}
        self.order_reader = TradingOrder()
        self.sign_in = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_report = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_skland = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.daily_mail = (datetime.now() - timedelta(days=1, hours=8)).date()
        self.daily_visit_friend = (datetime.now() - timedelta(days=1, hours=4)).date()
        self.ideal_resting_count = 4
        self.choose_error = set()
        self.drop_send = False
        self.global_plan = {}
        self.local_operation_followup_time = None
        self.train_room_state = None
        self.emergency_state = None
        self._emergency_startup_pending = False

    def find_next_task(
        self,
        compare_time: datetime | None = None,
        task_type="",
        compare_type: Literal["<", "=", ">"] = "<",
        meta_data="",
    ):
        """找符合条件的下一个任务

        Args:
            tasks: 任务列表
            compare_time: 截止时间
        """
        return find_next_task(
            self.tasks, compare_time, task_type, compare_type, meta_data
        )

    @property
    def party_time(self):
        return self._party_time

    @party_time.setter
    def party_time(self, value):
        self._party_time = value
        if self.op_data is not None:
            current_party_time = getattr(self.op_data, "party_time", None)
            if current_party_time is None or (
                isinstance(current_party_time, datetime)
                and current_party_time <= datetime.now()
            ):
                self.op_data.party_time = value

    def set_detected_party_time(self, value):
        """写入会客室界面确认过的线索交流状态。

        ``party_time`` 的普通 setter 会保留尚未到期的旧值，避免开始刷新时的
        临时清空让依赖它的副表误切换。界面读取结果不是临时状态：读不到倒计时
        表示交流已经结束，必须覆盖旧预测，哪怕旧预测时间仍在未来。
        """
        self._party_time = value
        if self.op_data is not None:
            self.op_data.party_time = value

    def read_party_time(self):
        """读取线索交流结束时间；空倒计时表示交流已经结束。"""
        remaining = self.read_time(((1768, 438), (1902, 480)), None)
        if remaining is None:
            return None
        return datetime.now() + timedelta(seconds=remaining)

    def read_operator_time(self, room, index, cord):
        """读取干员倒计时；空值按非工作状态或心情耗尽处理。"""
        remaining = self.read_time(cord, None)
        if remaining is None:
            logger.info(
                f"{self.translate_room(room)} {index + 1}号位未显示干员倒计时，"
                "按非工作状态或心情耗尽处理"
            )
            return datetime.now()
        return datetime.now() + timedelta(seconds=remaining)

    def run(self) -> None:
        """
        :param clue_collect: bool, 是否收取线索
        """

        if config.maintenance_recheck.is_set():
            return
        self.error = False
        self._card_moods_scanned_this_run = False
        self.handle_error(True)
        self._emergency_filter_tasks()
        self._schedule_maintenance_backup_check()

        while True:
            if config.maintenance_recheck.is_set():
                return
            self._sync_run_order_tasks()
            self._resume_waiting_group_shifts()
            self._fill_empty_dorms()
            scheduling(self.tasks, op_data=getattr(self, "op_data", None))
            self.task = self.tasks[0] if self.tasks else None
            if self.task is None:
                break
            reschedule_time = (self.task.time - datetime.now()).total_seconds()
            if reschedule_time > 300:
                self.task = None
                break
            if reschedule_time <= 0:
                break
            logger.info(f"出现任务调度情况休息{reschedule_time}秒等待下一个任务开始")
            # 休眠可能被新增任务唤醒；返回后重新排序、选择并检查到期时间。
            self._idle_sleep(reschedule_time)
        if config.maintenance_recheck.is_set():
            return
        if self.party_time is not None and self.party_time < datetime.now():
            self.party_time = None
        if self.free_clue is not None and self.free_clue != get_server_weekday():
            self.free_clue = None
        if self.credit_fight is not None and self.credit_fight != get_server_weekday():
            self.credit_fight = None
        self.todo_task = False
        self.collect_notification = False
        self.planned = False
        if self.op_data is None or self.op_data.operators is None:
            self.initialize_operators()
        if not self._product_switching_enabled():
            self._discard_product_switches()
        self.op_data.correct_dorm()
        if not getattr(self, "defer_backup_plan_until_mood_read", False):
            self.backup_plan_solver()
            # 首次启动先随心情读取刷新实际产物；恢复缓存后也以实际状态为准。
            if not self._emergency_frozen():
                self.queue_product_switches()
        logMsg = "||".join([str(t) for t in self.tasks])
        logger.debug("当前任务: " + logMsg)
        save_log(logMsg, "{}" if not self.task else str(self.task), level="INFO")
        if config.maintenance_recheck.is_set():
            return
        return super().run()

    def _fill_empty_dorms(self, *, primary_planned=False):
        """统一空床入口：日常规划和调度前均检查，不等待五分钟空档或跑单延期事件。"""
        op_data = getattr(self, "op_data", None)
        if (
            self._emergency_frozen()
            or op_data is None
            or self._initial_mood_read_pending()
        ):
            return False
        due_fills = [
            task
            for task in self.tasks
            if task.type == TaskTypes.FILL_DORM
            and task.time <= datetime.now()
            and not getattr(task, "arrangement_retry_room", None)
            and not getattr(task, "dorm_recovery_restore", [])
            and not getattr(task, "product_shift_locked", False)
            and not getattr(task, "backup_shift_active", False)
            and not getattr(task, "strict_mood_limit", False)
            and set(task.plan) == set(getattr(task, "dorm_fill_plan", task.plan))
        ]
        if not due_fills and not vacant_dorm_slots(op_data):
            return False
        if not primary_planned:
            if any(
                task.type
                in (
                    TaskTypes.SHIFT_OFF,
                    TaskTypes.EXHAUST_OFF,
                )
                or task.type == TaskTypes.FILL_DORM
                and task not in due_fills
                or task.time <= datetime.now()
                and task.type
                in (
                    TaskTypes.SHIFT_ON,
                    TaskTypes.FIAMMETTA,
                    TaskTypes.SELF_CORRECTION,
                    TaskTypes.RE_ORDER,
                )
                or task.type == TaskTypes.NOT_SPECIFIC
                and any(room.startswith("dorm") for room in task.plan)
                for task in self.tasks
            ):
                return False
            # 延期补位到期后先释放其预约，给新出现的主班轮休需求让床。
            self.tasks[:] = [task for task in self.tasks if task not in due_fills]
            _, reserved_slots = dorm_task_reservations(op_data, self.tasks)
            if not due_fills and not vacant_dorm_slots(op_data, reserved_slots):
                return False
            superseded = False
            try:
                if not self._plan_primary_recovery():
                    return False
                if any(
                    task.time <= datetime.now()
                    and (
                        task.type in (TaskTypes.SHIFT_ON, TaskTypes.SHIFT_OFF)
                        or any(room.startswith("dorm") for room in task.plan)
                    )
                    for task in self.tasks
                ):
                    superseded = True
                    return False
            finally:
                if not superseded:
                    self.tasks.extend(
                        task for task in due_fills if task not in self.tasks
                    )
            if due_fills:
                return False
        had_tasks = len(self.tasks)
        try_add_release_dorm({}, None, op_data, self.tasks, empty_only=True)
        return len(self.tasks) > had_tasks

    def transition(self) -> None:
        if (scene := self.scene()) == Scene.INFRA_MAIN:
            return self.infra_main()
        elif scene == Scene.INFRA_TODOLIST:
            return self.todo_list()
        elif scene == Scene.RIIC_OPERATOR_SELECT:
            self.tap_element("confirm_blue")
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.INFRA_MAIN)
            self.last_room = ""
            logger.debug("重设上次房间为空")

    def overtake_room(self):
        candidates = self.task.meta_data.split(",")
        if len(candidates) == 0:
            return
        if self.op_data.operators[candidates[0]].group != "":
            candidates = self.op_data.groups[
                self.op_data.operators[candidates[0]].group
            ]
        logger.debug(f"更新下班小组信息为{candidates}")
        resting_members = [
            self.op_data.operators[name]
            for name in candidates
            if not self.op_data.operators[name].room.startswith("dorm")
            and not self.op_data.operators[name].workaholic
            and not self.op_data.operators[name].multi_group
        ]
        if resting_members and all(op.is_resting() for op in resting_members):
            logger.info(f"{self.task.meta_data} 已完成用尽下班，继续正常规划")
            return
        if self._has_pending_exhausted_shift(candidates):
            logger.debug("用尽下班已有完整待执行恢复安排：%s", candidates)
            return
        # 在candidate 中，计算出需要的high free 和 Low free 数量
        # 只计算无法直接接管的主力床位。低优、替班和临时休息干员会让床，
        # 不能在这里阻止整个大组尝试下班。
        current_resting = self.op_data.active_high_resting_count()
        plan = {}
        self.get_resting_plan(candidates, [], plan, current_resting)
        if len(plan.items()) > 0:
            re_order_dorm_plan = try_reorder(self.op_data, plan)
            if re_order_dorm_plan:
                logger.debug(f"合并宿舍任务{re_order_dorm_plan}")
                _merge_dorm_arrangement(plan, re_order_dorm_plan)
            self.tasks.append(
                SchedulerTask(
                    datetime.now(), task_plan=plan, task_type=TaskTypes.SHIFT_OFF
                )
            )
        else:
            support = self._plan_exhaust_support(candidates)
            if support:
                logger.info(f"用尽下班优先协调替班和床位：{support}")
                self.tasks.append(
                    SchedulerTask(
                        task_plan=support, task_type=TaskTypes.SELF_CORRECTION
                    )
                )
                # 先确认占用方接岗，再重算用尽下班；不能直接从工作站抽走替班。
                self.tasks.append(
                    SchedulerTask(
                        task_plan=copy.deepcopy(self.task.plan),
                        meta_data=self.task.meta_data,
                        task_type=self.task.type,
                    )
                )
            else:
                msg = f"无法完成 {self.task.meta_data} 的排班：没有同时满足替班和床位的方案"
                logger.warning(msg)
                send_message(msg, level="ERROR")
            self.skip()

    def _has_pending_exhausted_shift(self, candidates):
        """A concrete off-shift task covers every recovery-requiring member."""
        members = [
            self.op_data.operators[name]
            for name in candidates
            if not self.op_data.operators[name].room.startswith("dorm")
            and not self.op_data.operators[name].workaholic
            and not self.op_data.operators[name].multi_group
        ]
        if not members:
            return False
        for task in self.tasks:
            if task.type != TaskTypes.SHIFT_OFF:
                continue
            resting = {
                name
                for room, names in task.plan.items()
                if room.startswith("dorm")
                for name in names
                if name not in ("", "Current", "Free")
            }
            working = {
                name
                for room, names in task.plan.items()
                if not room.startswith("dorm")
                for name in names
            }
            for member in members:
                if not member.is_resting():
                    continue
                target = task.plan.get(member.current_room)
                if target is None or (
                    member.current_index >= 0
                    and target[member.current_index : member.current_index + 1]
                    in (["Current"], [member.name])
                ):
                    resting.add(member.name)
            resting.difference_update(working)
            if all(member.name in resting for member in members):
                return True
        return False

    def _plan_exhaust_support(self, candidates):
        from arknights_mower.utils.exhaust_replacement import plan_exhaust_support

        def can_rest(data):
            simulation = copy.copy(self)
            # Copy mutable scheduling state only: eval_model holds unpickleable PyCapsules.
            simulation.op_data = data.project_arrangements([])
            simulation.tasks = copy.deepcopy(self.tasks)
            result = {}
            simulation.get_resting_plan(
                candidates.copy(), [], result, data.active_high_resting_count()
            )
            return bool(result)

        protected = set()
        train_state = getattr(self, "train_room_state", None)
        if config.conf.enable_mastery and (
            self._train_mastery_active()
            or self._train_protected()
            or getattr(train_state, "locked", False)
            or getattr(train_state, "state", None) in ("training", "waiting_collect")
        ):
            protected.update(
                op.name
                for op in self.op_data.operators.values()
                if op.room == "train" or op.current_room == "train"
            )
        fia, _ = self.check_fia()
        return plan_exhaust_support(
            self.op_data, candidates, can_rest, _is_mastery_busy, protected, fia
        )

    def handle_error(self, force=False):
        if self.scene() == Scene.UNKNOWN:
            for retry in range(5):
                logger.warning(f"当前场景无法识别，尝试返回纠正，第{retry + 1}次")
                self.back()
                if self.scene() != Scene.UNKNOWN:
                    break
            else:
                logger.warning(
                    "连续返回 5 次后仍无法识别场景，退出游戏重进",
                    extra={"archive_screenshots": True},
                )
                self.device.exit()
                self.check_current_focus()
        if self.error or force:
            now = datetime.now()
            for task in self.tasks:
                if getattr(task, "run_order_restore_pending", False):
                    task.prepare_run_order_restoration()
            if self._emergency_active():
                for task in self.tasks:
                    if (
                        task.type == TaskTypes.RUN_ORDER
                        and task.meta_data
                        and hasattr(task, "emergency_original_roster")
                        and task.time < now - timedelta(minutes=15)
                    ):
                        task.plan = copy.deepcopy(task.emergency_original_roster)
                        task.meta_data = ""
                        task.time = now
                        logger.warning("过期跑单停止插拔，保留原临时驻员恢复")
            # 如果没有任何时间小于当前时间的任务才生成空任务
            if (
                self.find_next_task(now) is None
                and self.find_next_task(task_type=TaskTypes.SKILL_UPGRADE) is None
            ):
                logger.debug("由于出现错误情况，生成一次空任务来执行纠错")
                self.tasks.append(SchedulerTask())
            # 普通任务超过 15 分钟时重建排班；关键预约不因别的房间失败丢失。
            preserved = {
                TaskTypes.SKILL_UPGRADE,
                TaskTypes.SWAP_SUPPORT,
                TaskTypes.REFRESH_TIME,
                TaskTypes.SWITCH_PRODUCT,
                TaskTypes.FIAMMETTA,
            }
            future_preserved = {
                TaskTypes.RUN_ORDER,
                TaskTypes.FURNITURE,
                TaskTypes.DEPOT,
                TaskTypes.CLUE,
                TaskTypes.WORKSHOP,
            }
            if any(
                t.time < now - timedelta(minutes=15)
                and t.type not in preserved
                and not hasattr(t, "emergency_original_roster")
                and not getattr(t, "run_order_restore_pending", False)
                and not getattr(t, "group_shift_expected", {})
                and not getattr(t, "backup_shift_active", False)
                for t in self.tasks
            ):
                logger.info(
                    "检测到执行超过15分钟的任务，重建普通排班并保留关键预约与未来显式任务"
                )
                self.tasks = [
                    t
                    for t in self.tasks
                    if t.type in preserved
                    or (t.type in future_preserved and t.time > now)
                    or hasattr(t, "emergency_original_roster")
                    or getattr(t, "run_order_restore_pending", False)
                    or getattr(t, "group_shift_expected", {})
                    or getattr(t, "backup_shift_active", False)
                ]
                # #144：清队后补立即空任务——队列只剩远期专精重检时，让下一次
                # run() 走正常 planned 分支重读心情/换班/跑单，而不是睡到远期任务开始
                logger.debug("清队后补立即空任务，下一轮走正常流程重读心情/换班/跑单")
                self.tasks.append(SchedulerTask())
        elif self.find_next_task(datetime.now() + timedelta(hours=2.5)) is None:
            logger.debug("2.5小时内没有其他任务，生成一个空任务")
            self.tasks.append(SchedulerTask(time=datetime.now() + timedelta(hours=2.5)))
        return True

    def plan_fia(self):
        fia_plan, fia_room = self.check_fia()
        if fia_room is None or fia_plan is None:
            return
        self._refresh_fia_candidate_moods(fia_plan)
        fallback = self._emergency_fia_fallback(fia_plan)
        if fallback is not None:
            self._refresh_fia_candidate_moods(fallback)
            fia_plan = self._emergency_fia_fallback(fia_plan) or []
            logger.info(
                "自动救急：配置充能目标已满心情，按心情选择正常主班：%s", fia_plan
            )
        # 肥鸭充能新模式：https://github.com/ArkMowers/arknights-mower/issues/551
        target = None
        if not config.conf.fia_fool:
            fia_threshold = config.conf.fia_threshold
            logger.info(f"菲亚防呆设计未开启，菲亚阈值为{fia_threshold}")
        else:
            fia_threshold = 0.9
            logger.info(f"菲亚防呆设计已开启，菲亚阈值为{fia_threshold}")
        for operator in fia_plan:
            data = self.op_data.operators[operator]
            operator_morale = data.current_mood()
            operator_limit = data.lower_limit
            logger.debug(f"{operator}的心情为{operator_morale}")
            if operator_morale > fia_threshold * 24:
                logger.debug(f"{operator}的心情高于阈值，跳过充能")
                continue
            if data.rest_in_full and data.exhaust_require and not data.is_resting():
                logger.debug(f"{operator}为暖机干员但不在宿舍，跳过充能")
                continue
            if data.group:
                lowest = True
                for member in self.op_data.groups[data.group]:
                    if member == operator:
                        continue
                    # Lancet-2
                    if (
                        fallback is not None
                        and self.op_data.has_rest_mood_limit(member)
                        or self.op_data.operators[member].multi_group
                        or self.op_data.operators[member].room.startswith("dorm")
                        or self.op_data.operators[member].workaholic
                        and member not in fia_plan
                    ):
                        continue
                    member_morale = self.op_data.operators[member].current_mood()
                    member_limit = self.op_data.operators[member].lower_limit
                    logger.debug(f"{data.group}组内{member}的心情为{member_morale}")
                    if member_morale - member_limit < operator_morale - operator_limit:
                        lowest = False
                        logger.debug(f"{operator}的心情高于{member}，跳过充能")
                        break
                if not lowest:
                    continue
            target = operator
            break
        # 若全部跳过且关闭防呆则令目标干员为心情最低干员
        if target is None and fia_plan and not config.conf.fia_fool:
            target = fia_plan[0]
            op_mood = 24
            for op in fia_plan:
                data = self.op_data.operators[op]
                op_mood_t = data.current_mood()
                if data.rest_in_full and data.exhaust_require and not data.is_resting():
                    logger.debug(f"{operator}为暖机干员但不在宿舍，跳过充能")
                    continue
                if op_mood_t < op_mood:
                    target = op
                    op_mood = op_mood_t
        if target:
            self.tasks.append(
                SchedulerTask(
                    time=self.task.time,
                    task_type=TaskTypes.FIAMMETTA,
                    task_plan={fia_room: [target, "菲亚梅塔"]},
                    meta_data=target,
                    initial_fia=getattr(self.task, "initial_fia", False),
                )
            )
            self.tasks[-1].emergency_fia_fallback = fallback is not None
            # 充能结束后整组立即上班
            for task in self.tasks:
                if task.type == TaskTypes.SHIFT_ON:
                    for room, operators in task.plan.items():
                        if target in operators:
                            task.time = self.task.time + timedelta(seconds=1)
                            self.tasks.sort(key=lambda task: task.time)
                            return
        else:
            logger.info("肥鸭充能干员不足，请添加更多干员！")
            retry = SchedulerTask(
                time=self.task.time + timedelta(hours=24 * (1 - fia_threshold) / 2),
                task_type=TaskTypes.FIAMMETTA,
            )
            retry.fia_retry_after = retry.time
            self.tasks.append(retry)
            self.tasks.sort(key=lambda task: task.time)

    def _refresh_fia_candidate_moods(self, names):
        """挑选充能对象前补读失效缓存，同房候选只进房一次，不触发纠错或切表。"""
        rooms = {}
        for name in names:
            op = self.op_data.operators[name]
            room = op.current_room
            if (
                room
                and op.current_index >= 0
                and (
                    op.need_to_refresh(r=room)
                    or (op.is_working() and op.depletion_rate == 0)
                )
            ):
                rooms.setdefault(room, set()).add(op.current_index)
        for room, indexes in rooms.items():
            self.enter_room(room)
            self.get_agent_from_room(room, sorted(indexes))
            self.back()

    def _queue_initial_fia(self):
        """初始化实测满心情后优先充能，沿用目标筛选与原班恢复。"""
        if getattr(self, "_initial_fia_checked", False):
            return False
        self._initial_fia_checked = True
        for task in self.tasks:
            if getattr(task, "initial_fia", False):
                task.initial_fia = False
        targets, room = self.check_fia()
        fia = self.op_data.operators.get("菲亚梅塔")
        if (
            not targets
            or not room
            or not has_resting_mood(fia)
            or fia.mood < 24
            or not fia.current_room.startswith("dorm")
            or fia.current_index < 0
        ):
            return False
        existing = [task for task in self.tasks if task.type == TaskTypes.FIAMMETTA]
        # 未完成的充能或回岗沿用原任务；防呆延期不在初始化时强行重试。
        if any(
            getattr(task, "fia_retry_after", datetime.min) > datetime.now()
            for task in existing
        ):
            return False
        if any(task.plan for task in existing):
            for task in existing:
                if task.plan and task.time <= datetime.now():
                    task.initial_fia = True
            return any(getattr(task, "initial_fia", False) for task in existing)
        task = existing[0] if existing else SchedulerTask(task_type=TaskTypes.FIAMMETTA)
        task.time = datetime.now()
        task.initial_fia = True
        self.tasks[:] = [
            queued for queued in self.tasks if queued.type != TaskTypes.FIAMMETTA
        ]
        self.tasks.append(task)
        logger.info("初始化确认菲亚梅塔心情已满，优先执行充能任务")
        return True

    def _refresh_fiammetta_task(self, ready_at):
        """读到新的回满时间后更新充能预约，保留正在执行的充能／回岗任务。"""
        if self._initial_mood_read_pending():
            return
        if ready_at is None:
            self.tasks[:] = [
                task
                for task in self.tasks
                if task.type != TaskTypes.FIAMMETTA or task.plan or task is self.task
            ]
            return
        for task in self.tasks:
            if (
                task.type == TaskTypes.FIAMMETTA
                and not task.plan
                and task is not self.task
            ):
                task.time = max(ready_at, getattr(task, "fia_retry_after", ready_at))

    def craft_material(self):
        first_task = self.task
        restore_plan = {}
        last_agent = None
        processed_agents = set()
        try:
            while True:
                try:
                    agent = self._craft_material(restore_plan)
                    if agent is not None:
                        last_agent = agent
                        processed_agents.add(agent)
                except MowerExit:
                    raise
                except Exception as e:
                    last_agent = None
                    save_exception(e)
                    logger.exception("工厂任务失败: %s", e)
                    break
                # 后续任务按对象身份移除；首个任务在恢复成功后完成收尾。
                if self.task is not first_task:
                    self.tasks[:] = [t for t in self.tasks if t is not self.task]
                if first_task.type != TaskTypes.WORKSHOP or first_task.plan:
                    break
                next_task = self._next_workshop_task(first_task)
                if next_task is None:
                    break
                logger.info(f"连续加工，直接切换至{next_task.meta_data}")
                self.task = next_task
        finally:
            self.task = first_task

        if restore_plan and (
            len(restore_plan) > 1 or restore_plan["factory"] != [last_agent]
        ):
            try:
                logger.info("本轮加工结束，统一恢复干员位置")
                if self.agent_arrange(restore_plan, get_time=True) is False:
                    return
            except MowerExit:
                raise
            except Exception as e:
                save_exception(e)
                logger.exception("加工后恢复干员失败: %s", e)
                return
        if processed_agents:
            if (
                first_task.type == TaskTypes.WORKSHOP
                and not first_task.plan
                and first_task.meta_data in processed_agents
            ):
                # 已完成的加工不再占用任务预约，其他临近任务继续保留。
                self.tasks[:] = [t for t in self.tasks if t is not first_task]
            self.op_data.refresh_idle_dorm_search(
                reason="加工结束后复核恢复需求", names=processed_agents
            )
            if not self._plan_dorm_recovery(scan_moods=False):
                self.plan_metadata()

    def _next_workshop_task(self, first_task):
        # 每次交接重新检查队列，兼容新增/删除任务和专精换人保护。
        tasks = getattr(self, "tasks", [])
        protect_priority_tasks(tasks, op_data=getattr(self, "op_data", None))
        pending = sorted(
            (task for task in tasks if task is not first_task),
            key=lambda task: task.time,
        )
        if not pending:
            return None
        task = pending[0]
        if (
            task.type == TaskTypes.WORKSHOP
            and not task.plan
            and task.time <= datetime.now()
        ):
            return task
        return None

    def _craft_material(self, restore_plan):
        task = self.task
        from arknights_mower.utils.workshop_automation import workshop_task_snapshot

        snapshot = workshop_task_snapshot(task)
        if snapshot is None:
            logger.info("加工配置已更新，跳过旧的自动加工任务")
            return
        from arknights_mower.utils.workshop_limits import (
            workshop_material_block_reason,
            workshop_operator_block_reason,
        )

        setting = next(
            (item for item in snapshot.settings if item.operator == task.meta_data),
            None,
        )
        if setting is None:
            logger.info(f"{task.meta_data}不在加工站配置中，调人前跳过")
            return
        if not setting.enabled:
            logger.info(f"{task.meta_data}加工站任务被禁用，调人前跳过")
            return
        operator = self.op_data.operators.get(task.meta_data)
        mood = (
            operator.current_mood()
            if operator is not None and hasattr(operator, "current_mood")
            else getattr(operator, "mood", None)
        )
        reason = workshop_operator_block_reason(
            self.op_data,
            task.meta_data,
            getattr(self, "tasks", []),
            current_task=task,
        ) or workshop_material_block_reason(
            task.meta_data, setting.items, get_inventory_counts(), mood
        )
        if reason:
            logger.info(f"{task.meta_data}加工跳过：{reason}")
            return
        self.enter_room("factory")
        if "factory" not in restore_plan:
            restore_plan["factory"] = [
                row["agent"]
                for row in self.get_agent_from_room("factory")
                if row["agent"]
            ] or [task.meta_data]
            # 原本无人时沿用单次加工行为，首位加工干员作为最终留驻干员。
        agent_room = operator.current_room if operator is not None else ""
        agent_index = operator.current_index if operator is not None else -1
        logger.debug(f"本轮加工前工厂干员: {restore_plan['factory']}")
        logger.debug(f"当前加工干员位置: {agent_room}")
        if (
            restore_plan["factory"]
            and task.meta_data not in restore_plan["factory"]
            and agent_room
            and agent_room != "factory"
            and agent_index >= 0
        ):
            restore_plan.setdefault(
                agent_room, ["Current"] * len(self.op_data.plan[agent_room])
            )[agent_index] = task.meta_data
        self.agent_arrange({"factory": [task.meta_data]})
        if self.generate_product(task.meta_data, snapshot=snapshot) is False:
            raise RuntimeError("加工执行失败，停止本轮连续换人")
        if config.conf.workshop_auto_active and not snapshot.is_current():
            # A confirmed batch advances the recipe generation. Continue with
            # remaining mood instead of waiting for the normal fresh-task gate.
            try_workshop_tasks(self.op_data, self.tasks, minimum_mood=0)
        return task.meta_data

    def plan_metadata(self):
        if self._emergency_frozen():
            self._emergency_filter_tasks()
            self._emergency_replan_releases()
            return
        self.tasks = plan_metadata(self.op_data, self.tasks)
        self._resume_waiting_group_shifts()

    def prepare_release_dorm(self, task):
        """合并任务逐人核验；一人失效不取消其他人的清退。"""
        if not hasattr(task, "release_targets"):
            return self._prepare_release_dorm_member(task)
        plan, valid = {}, {}
        get_time = False
        for name, (room, index) in task.release_dorm_targets().items():
            row = ["Current"] * len(task.plan[room])
            row[index] = "Free"
            member = SchedulerTask(
                time=task.time,
                task_plan={room: row},
                task_type=TaskTypes.RELEASE_DORM,
                meta_data=name,
            )
            get_time |= self._prepare_release_dorm_member(member)
            if not member.plan:
                continue
            _merge_dorm_arrangement(plan, member.plan)
            valid[name] = (room, index)
        task.plan, task.release_targets = plan, valid
        task.meta_data = ",".join(valid)
        return get_time

    def _prepare_release_dorm_member(self, task):
        """逐人校验身份、床位和回满时刻，再更新原回班引用。"""
        strict = getattr(task, "strict_mood_limit", False)
        operator = self.op_data.operators.get(task.meta_data)
        if (
            strict
            and not (
                operator is not None
                and self.op_data.has_rest_mood_limit(task.meta_data)
                and getattr(task, "mood_limit", None) in (None, operator.upper_limit)
            )
            or (not strict)
            and self.op_data.skip_idle_dorm_release(task.meta_data)
        ):
            # 配置已变化，或普通清退对象已受保床保护。
            task.plan = {}
            return False
        room = next(iter(task.plan), None)
        if room is None or "Free" not in task.plan[room]:
            task.plan = {}
            return False
        index = task.plan[room].index("Free")
        if operator is None or (operator.current_room, operator.current_index) != (
            room,
            index,
        ):
            # 旧住客已离开或换位，不能清退后来的入住者。
            task.plan = {}
            return False
        now = datetime.now()
        if not strict and (
            not has_resting_mood(operator, now)
            or resting_mood(operator, now) < operator.upper_limit
        ):
            _, bed = self.op_data.get_dorm_by_name(operator.name)
            if bed is None or bed.time is None:
                # 未知心情和未读到的恢复时刻不能证明已经回满。
                task.plan = {}
                return False
            if bed.time > now:
                # 单人和合并清退共用重排；原任务仍由派发入口收尾。
                pending = copy.deepcopy(task)
                pending.time = bed.time
                self.tasks.append(pending)
                task.plan = {}
                return False
        # 宿舍清退只处理床位；加工使用独立任务。
        if operator.is_high() and operator.mood > 0:
            idx, dorm = self.op_data.get_dorm_by_name(operator.name)
            if idx is not None:
                update_task = find_next_task(
                    self.tasks,
                    task_type=TaskTypes.SHIFT_ON,
                    meta_data="dorm" + str(idx),
                )
                if update_task:
                    logger.debug("开始更新宿舍信息")
                    dorm_list = update_task.meta_data.split(",")
                    dorm_list.remove("dorm" + str(idx))
                    update_task.meta_data = ",".join(dorm_list)
                    if not (strict):
                        operator.mood = operator.upper_limit
                        operator.time_stamp = dorm.time
                        operator.mood_is_prediction = True
        return True

    def arrange_release_dorm(self):
        """执行队列中的合并清退；失败只重试尚未完成的房间。"""
        task = self.task
        get_time = self.prepare_release_dorm(task)
        original_plan = copy.deepcopy(task.plan)
        before = self.op_data.project_arrangements([])
        completed = False
        try:
            result = self.agent_arrange(task.plan, get_time)
            completed = result is not False
            return result, get_time
        finally:
            released = {
                room: names
                for room, names in original_plan.items()
                if completed or room not in task.plan
            }
            reserved_names, reserved_slots = dorm_task_reservations(
                self.op_data,
                [
                    pending
                    for pending in self.tasks
                    if pending is not task and pending.type != TaskTypes.SHIFT_ON
                ],
            )
            if not completed:
                reserved_slots.update(
                    (room, index)
                    for room, names in task.plan.items()
                    for index, name in enumerate(names)
                    if name != "Current"
                )
            rearranged = prioritize_new_dorm_recovery(
                before, released, reserved_slots, reserved_names=reserved_names
            )
            if rearranged != released:
                self.tasks.append(
                    SchedulerTask(task_type=TaskTypes.RE_ORDER, task_plan=rearranged)
                )
            # Free 在选人时会解析成姓名；重试仍按原身份核验，已完成房间不复原。
            task.plan = (
                {} if completed else {room: original_plan[room] for room in task.plan}
            )

    def infra_main(self):
        """位于基建首页"""
        if self.find("control_central") is None:
            self.back()
            return
        if not self._product_switching_enabled():
            self._discard_product_switches()
        if getattr(self, "_emergency_startup_pending", False):
            if (
                self.task is not None
                and self.task.type == TaskTypes.NOT_SPECIFIC
                and not self.task.plan
                and not self.task.meta_data
            ):
                self.tasks[:] = [task for task in self.tasks if task is not self.task]
                self.task = None
            self._emergency_startup()
            if self._emergency_active() and not self._emergency_startup_pending:
                self._emergency_tick()
        initial_fia_pending = any(
            getattr(task, "initial_fia", False) for task in self.tasks
        )
        blocked_orders = blocked_run_order_ids(
            self.tasks, getattr(self, "op_data", None)
        )
        if initial_fia_pending:
            protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
            candidate = self.tasks[0]
            if candidate.time <= datetime.now() and (
                getattr(candidate, "initial_fia", False)
                or getattr(candidate, "strict_mood_limit", False)
                or candidate.type == TaskTypes.RUN_ORDER
                and id(candidate) not in blocked_orders
                or config.conf.enable_mastery
                and candidate.type == TaskTypes.SWAP_SUPPORT
            ):
                self.task = candidate
            else:
                self.task = None
                self.skip()
                return True
        if getattr(self, "_emergency_startup_pending", False) and not (
            getattr(self.task, "strict_mood_limit", False)
            or getattr(self.task, "initial_fia", False)
            or initial_fia_pending
            and (
                getattr(self.task, "type", None) == TaskTypes.RUN_ORDER
                and id(self.task) not in blocked_orders
                or config.conf.enable_mastery
                and getattr(self.task, "type", None) == TaskTypes.SWAP_SUPPORT
            )
        ):
            self.skip()
            return True
        if self.task is not None:
            if getattr(self.task, "run_order_restore_pending", False):
                self.task.prepare_run_order_restoration()
            # Navigation/reconnection may have consumed the margin since run().
            # Recheck at a safe boundary, before any staff arrangement has started.
            protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
            blocked_orders = blocked_run_order_ids(
                self.tasks, getattr(self, "op_data", None)
            )
            if (
                self.task.time > datetime.now()
                or not any(task is self.task for task in self.tasks)
                or (
                    self.tasks
                    and self.tasks[0] is not self.task
                    and (
                        getattr(self.tasks[0], "strict_mood_limit", False)
                        or getattr(self.tasks[0], "initial_fia", False)
                        or (
                            self.tasks[0].type == TaskTypes.RUN_ORDER
                            and id(self.tasks[0]) not in blocked_orders
                            or config.conf.enable_mastery
                            and self.tasks[0].type == TaskTypes.SWAP_SUPPORT
                        )
                    )
                    and self.tasks[0].time <= datetime.now()
                )
            ):
                self.task = None
                self.skip()
                return True
            product_tasks = []
            remove_current_task = True
            arrangement_deferred = False
            completed_task = None
            try:
                if self.task.meta_data == RESUME_META or getattr(
                    self.task, "emergency_recovery_release", False
                ):
                    if self._emergency_active():
                        self._emergency_tick()
                elif self.task.type == TaskTypes.SKILL_UPGRADE:
                    from arknights_mower.solvers.mastery import run_mastery_task

                    run_mastery_task(self)
                    from arknights_mower.utils.workshop_automation import (
                        restore_if_no_plans,
                    )

                    restore_if_no_plans()
                elif self.task.type == TaskTypes.SWAP_SUPPORT:
                    from arknights_mower.solvers.mastery import run_swap_support

                    run_swap_support(self)
                elif self.task.type == TaskTypes.FURNITURE:
                    from arknights_mower.solvers.furniture import FurnitureDismantler
                    from arknights_mower.utils.furniture_task import (
                        FurnitureNavigationError,
                    )

                    try:
                        FurnitureDismantler(self).run()
                    except (MowerExit, FurnitureNavigationError, ConnectionError):
                        raise
                    except Exception:
                        # 保护失败、识别异常及提交结果不明都只执行一次。
                        # 先移除再交给通用异常记录，避免下一轮重跑同一任务。
                        self.tasks[:] = [t for t in self.tasks if t is not self.task]
                        raise
                elif self.task.type == TaskTypes.SWITCH_PRODUCT:
                    batch_cutoff = datetime.now()
                    product_tasks = [
                        task
                        for task in self.tasks
                        if task.type == TaskTypes.SWITCH_PRODUCT
                        and task.time <= batch_cutoff
                    ]
                    self.switch_base_products(product_tasks)
                    # switch_base_products 会自行移除已完成的任务，并保留、延期
                    # 当前无法切换的低等级贸易站任务。
                    remove_current_task = False
                elif len(self.task.plan.keys()) > 0:
                    get_time = False
                    if TaskTypes.SHIFT_OFF == self.task.type or (
                        self.task.type
                        in (TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER)
                        or (
                            self.task.type
                            in (TaskTypes.NOT_SPECIFIC, TaskTypes.FILL_DORM)
                            and any(room.startswith("dorm") for room in self.task.plan)
                        )
                    ):
                        # 纠偏／迁移／补床都可能更换单回目标；完成后以实际
                        # 读到的床位时间重建派生回班。
                        get_time = True
                    if (
                        config.conf.run_order_grandet_mode.back_to_index
                        and TaskTypes.RUN_ORDER == self.task.type
                        and self.task.meta_data
                        and not self.refresh_connecting
                        and config.conf.run_order_buffer_time > 0
                        and datetime.now() + timedelta(seconds=45)
                        < self.task.time
                        + timedelta(minutes=config.conf.run_order_delay)
                    ):
                        # 有45秒冗余时间才返回基地主界面
                        logger.info("跑单前返回主界面以保持登录状态")
                        self.back_to_index()
                        self.refresh_connecting = True
                        return
                    self.refresh_connecting = False
                    if self.task.type in (
                        TaskTypes.SHIFT_OFF,
                        TaskTypes.SHIFT_ON,
                        TaskTypes.EXHAUST_OFF,
                        TaskTypes.RE_ORDER,
                        TaskTypes.SELF_CORRECTION,
                    ):
                        self._prepare_group_shift(self.task)
                        self._prepare_shift_cycle(self.task)
                        self._defer_conflicting_product_shift_slots(self.task)
                        self._switch_products_before_arrangement(self.task)
                        self._activate_shift_backup(self.task)
                        self._prepare_group_shift(self.task, remember_targets=True)
                        get_time |= getattr(self.task, "backup_shift_active", False)
                        get_time |= any(
                            room.startswith("dorm") for room in self.task.plan
                        )
                    if self.task.type == TaskTypes.RELEASE_DORM:
                        result, get_time = self.arrange_release_dorm()
                        arrangement_deferred = result is False
                    else:
                        arrangement_deferred = (
                            self.agent_arrange(self.task.plan, get_time) is False
                        )
                    if not arrangement_deferred:
                        arrangement_deferred = not self._complete_group_shift(self.task)
                    if not arrangement_deferred:
                        self.task.backup_shift_active = False
                    if arrangement_deferred:
                        # 已处理的工作房间从原任务移除；副表覆盖的宿舍也会从
                        # 原任务移除。仅在还有未覆盖的宿舍时保留原任务续行。
                        remove_current_task = not self.task.plan
                        self.skip()
                    elif get_time:
                        generated_tasks = []
                        if not self.backup_plan_solver(
                            generated_tasks=generated_tasks,
                        ):
                            self.plan_metadata()
                        else:
                            logger.info("排班表切换已在缓存中收敛为单次最终任务")
                    if not arrangement_deferred and getattr(
                        self.task, "product_switched_before_arrangement", False
                    ):
                        self._refresh_orders_after_product_switch()
                    if (
                        not arrangement_deferred
                        and TaskTypes.RE_ORDER == self.task.type
                    ):
                        self.skip()
                # 如果任务名称包含干员名,则为动态生成的
                elif self.task.type == TaskTypes.FIAMMETTA:
                    self.plan_fia()
                elif self.task.type == TaskTypes.WORKSHOP:
                    self.craft_material()
                elif (
                    self.task.meta_data.split(",")[0] in agent_list
                    and self.task.type == TaskTypes.EXHAUST_OFF
                ):
                    self.overtake_room()
                elif self.task.type == TaskTypes.CLUE_PARTY:
                    self._run_clue_flow()
                elif self.task.type == TaskTypes.CLUE:
                    # 手动触发的会客室任务，与定时触发走同一条路径
                    self._run_clue_flow()
                elif self.task.type == TaskTypes.REFRESH_TIME:
                    self.plan_run_order(self.task.meta_data)
                    self.skip(["todo_task", "collect_notification"])
                elif self.task.type == TaskTypes.DEPOT:
                    self.仓库扫描()
                elif self.task.type == TaskTypes.NOT_SPECIFIC:
                    pass
                if remove_current_task:
                    completed_task = self.task
                    self.tasks[:] = [t for t in self.tasks if t is not self.task]
                    self._refresh_deferred_product_reservations()
                if (
                    not arrangement_deferred
                    and self.tasks
                    and self.tasks[0].type in [TaskTypes.SHIFT_ON]
                ):
                    self.backup_plan_solver()
            except RoomArrangementDeferred as e:
                task = self.task
                attempts = (
                    getattr(task, "arrangement_retry_count", 0)
                    if getattr(task, "arrangement_retry_room", None) == e.room
                    else 0
                ) + 1
                if not hasattr(task, "arrangement_retry_due_at"):
                    task.arrangement_retry_due_at = task.time
                task.arrangement_retry_room = e.room
                task.arrangement_retry_count = attempts
                task.time = datetime.now() + timedelta(minutes=min(attempts, 5))
                self.tasks.sort(key=lambda queued: queued.time)
                self.skip()
                logger.warning(
                    "%s 连续识别或换人失败，保留剩余安排，延至 %s 重试",
                    e.room,
                    task.time.strftime("%H:%M:%S"),
                )
                self.back_to_infrastructure()
            except GroupShiftBlocked as e:
                self._suspend_group_shift(self.task, e.groups)
                logger.warning(str(e))
                # Suspended arrangements must not occupy the dispatch queue or
                # prevent the returning groups from receiving their tasks.
                self.plan_metadata()
                self.skip()
            except ProductSwitchDeferred as e:
                retry_time = datetime.now() + timedelta(minutes=e.minutes)
                pending_ids = {id(task) for task in self.tasks}
                deferred_tasks = [
                    task
                    for task in product_tasks or [self.task]
                    if id(task) in pending_ids
                ]
                for task in deferred_tasks:
                    task.time = max(task.time, retry_time)
                self._refresh_deferred_product_reservations()
                self.tasks.sort(key=lambda task: task.time)
                logger.warning(
                    f"{e}，未完成的切换任务推迟至 {retry_time.strftime('%H:%M:%S')}"
                )
                self.skip()
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                save_exception(e)
                logger.exception(e)
                if (
                    type(e) is ConnectionAbortedError
                    or type(e) is AttributeError
                    or type(e) is ConnectionError
                ):
                    raise e
                else:
                    self.skip()
                    self.error = True
            self.task = None
            if self._emergency_active() and not getattr(
                self, "_emergency_startup_pending", False
            ):
                self._emergency_tick(completed_task=completed_task)
            if completed_task is not None and (
                getattr(completed_task, "initial_fia", False)
                and not any(getattr(task, "initial_fia", False) for task in self.tasks)
                or not arrangement_deferred
                and (
                    completed_task.type == TaskTypes.RE_ORDER
                    or completed_task.type == TaskTypes.SELF_CORRECTION
                    and completed_task.meta_data == "副表内存收敛"
                )
            ):
                # 延期或重启可能已消费切表时的空任务；完成边界补回规划责任。
                # 复用已到期的空任务，远期回班不能代替立即正常规划。
                if not any(
                    task.type == TaskTypes.NOT_SPECIFIC
                    and not task.plan
                    and not task.meta_data
                    and task.time <= datetime.now()
                    for task in self.tasks
                ):
                    self.tasks.append(SchedulerTask())
                self.skip()
                return True
        elif not self.planned:
            if self._emergency_active():
                self._emergency_tick()
                self.planned = True
                return True
            try:
                # 如果有任何type 则会最后修正
                if not self.no_pending_task(1):
                    self.skip(["planned", "todo_task", "collect_notification"])
                else:
                    # 正常运行保留原有心情读取间隔：缓存未过期直接信任，过期
                    # 才进房复核；缓存清零后 time_stamp 为空，会自然触发全量读取。
                    if getattr(self, "defer_backup_plan_until_mood_read", False):
                        # 首次读取不生成主表纠错；副表确定后才按最终排班规划。
                        self._read_agent_mood()
                        self._read_initial_card_mood()
                        self.defer_backup_plan_until_mood_read = False
                        if self._queue_initial_fia():
                            self.skip()
                            return True
                        self.backup_plan_solver()
                        self.queue_product_switches()
                        # 先执行副表差异、产物切换或扫描恢复出的训练室任务，
                        # 避免普通纠错覆盖这些任务的明确安排。
                        if not self.no_pending_task(1):
                            self.skip(["planned", "todo_task", "collect_notification"])
                            return True
                        mood_result = self.agent_get_mood(
                            skip_dorm=True, read_rooms=False
                        )
                    else:
                        mood_result = self.agent_get_mood(skip_dorm=True)
                    # 初始化完成后恢复正常规划。
                    self.defer_backup_plan_until_mood_read = False
                    if mood_result is not None:
                        self.skip(["planned", "todo_task", "collect_notification"])
                        return True
                    self.run_order_solver()
                    self.plan_solver()
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                save_exception(e)
                logger.exception(e)
                if (
                    type(e) is ConnectionAbortedError
                    or type(e) is AttributeError
                    or type(e) is ConnectionError
                ):
                    raise e
                else:
                    self.error = True
            self.planned = True
        elif not self.todo_task:
            if (
                self.enable_party
                and (
                    self.last_clue is None
                    or datetime.now() - self.last_clue > timedelta(hours=1)
                )
                and self.no_pending_task(3)
            ):
                self.clue_new()
                self.last_clue = datetime.now()
            if (
                self.drone_room not in self.op_data.run_order_rooms
                and (
                    self.drone_time is None
                    or self.drone_time
                    < datetime.now() - timedelta(hours=config.conf.drone_interval)
                )
                and self.drone_room is not None
                and self.no_pending_task(2)
            ):
                self.drone(self.drone_room)
                logger.info(f"记录本次无人机使用时间为:{datetime.now()}")
                self.drone_time = datetime.now()
            if self.no_pending_task(2) and (
                self.reload_time is None
                or self.reload_time
                < datetime.now() - timedelta(hours=config.conf.maa_gap)
            ):
                self.reload()
                logger.info(f"记录本次补货时间为:{datetime.now()}")
            self.todo_task = True
        elif not self.collect_notification:
            if self.no_pending_task(1):
                notification = detector.infra_notification(self.recog.img)
                if notification is None:
                    self.sleep(1)
                    notification = detector.infra_notification(self.recog.img)
                if notification is not None:
                    self.tap(notification)
            self.collect_notification = True
        else:
            return self.handle_error()

    def translate_room(self, room):
        translations = {
            "room": lambda parts: f"B{parts[1]}0{parts[2]}",
            "dormitory": lambda parts: f"{parts[1]}层宿舍",
            "contact": lambda parts: "办公室",
            "central": lambda parts: "控制中枢",
            "factory": lambda parts: "加工站",
            "meeting": lambda parts: "会客室",
            "train": lambda parts: "训练室",
            "recycle": lambda parts: "回收站",
        }

        for keyword, translation_func in translations.items():
            if keyword in room:
                parts = room.split("_")
                return translation_func(parts)

        return room

    def _read_agent_mood(self):
        """只刷新实际位置、心情及训练室状态，不按当前排班生成纠错。"""
        global _training_room_scan_disabled
        # 暂时规定纠错只适用于主班表
        need_read = {
            v.room
            for v in self.op_data.operators.values()
            if v.need_to_refresh() and v.room in base_room_list
        }

        force_rooms = {
            room
            for room in getattr(self, "_initial_mood_refresh_rooms", ())
            if room in self.op_data.plan and room in base_room_list
        }
        self._initial_mood_refresh_rooms = force_rooms
        need_read.update(force_rooms)

        # 正常心情刷新始终检查训练室，包含未启用专精时的手动训练。
        # 实际扫描仍受房间级 2.5 小时限频保护。
        need_read.add("train")

        for room in sorted(need_read):
            if room == "train":
                if _training_room_scan_disabled:
                    force_rooms.discard(room)
                    continue
                last_read = getattr(self, "last_train_mood_read", None)
                if (
                    room not in force_rooms
                    and last_read
                    and datetime.now() - last_read < timedelta(hours=2.5)
                ):
                    continue
            error_count = 0
            # 近期读过的房内干员无需重复扫描。训练室为空或识别失败时，上面的
            # 房间级时间同样限频，避免没有固定干员的训练室每轮被强制读取。
            current_working = [
                value
                for key, value in self.op_data.operators.items()
                if value.current_room == room
            ]

            if (
                room not in force_rooms
                and current_working
                and all(
                    operator.time_stamp
                    and operator.time_stamp
                    > datetime.now()
                    - timedelta(
                        hours=0.5 if operator.name in ["歌蕾蒂娅", "见行者"] else 2.5
                    )
                    for operator in current_working
                )
            ):
                for e in current_working:
                    logger.debug(e.time_stamp)
                logger.debug(f"{room} 所有干员不满足扫描条件，跳过")
                continue
            if getattr(
                self, "_emergency_startup_pending", False
            ) and not self._emergency_operation_fits(estimate_dorm_minutes(room) * 60):
                self.back_to_infrastructure()
                return False
            if room == "train":
                self.last_train_mood_read = datetime.now()
            skip_room_exit = False
            room_entered = False
            while True:
                try:
                    if room == "train":
                        self.enter_room(room, max_attempts=1)
                    else:
                        self.enter_room(room)
                    room_entered = True
                    if room == "train":
                        if config.conf.enable_mastery:
                            # #94 统一读取：一次 read_room_state(want_mood=True) 开一次
                            # 浮窗读全（协助位+训练位+心情）+ 左下角面板，消除原来
                            # get_agent_from_room（读心情）后再开一次浮窗读槽位的重复
                            # 浮窗开关（铁律 3 一次进房做全部）。
                            from arknights_mower.solvers.mastery_reader import (
                                read_room_state,
                                reconcile_short,
                            )

                            try:
                                room_state, mood_data = read_room_state(
                                    self, enter=False, want_mood=True
                                )
                                self.train_room_state = room_state
                                if room_state.read_failed or room_state.state not in (
                                    "empty",
                                    "training",
                                    "waiting_collect",
                                ):
                                    logger.warning(
                                        "训练室房态读取不可信，本轮跳过训练位排班冲突判定"
                                    )
                                else:
                                    trainee = room_state.train_slot or getattr(
                                        room_state.panel, "operator_name", ""
                                    )
                                    _stop_if_scheduled_trainee(
                                        self, trainee, room_state
                                    )
                                mood_info = [
                                    f"干员: '{item['agent']}', 心情: {round(item['mood'], 3)}"
                                    for item in mood_data
                                    if item.get("agent")
                                ]
                                if mood_info:
                                    logger.info(
                                        f"房间 {self.translate_room(room)}  {mood_info}"
                                    )
                                # 重启后训练室可能停在待收取（专精练完但没人收）：进训练室读
                                # 心情时顺便 reconcile——发现待收取就收（defer_collect=False
                                # 此刻就是要收），修正 DB（截图为准），打破「不收→等级不刷新
                                # →材料不够→不调度→更不收」死锁。enable_mastery 关闭时不跑
                                # 读取器（铁律 10），保留通用心情读取。
                                if room_state is not None:
                                    reconcile_short(
                                        self, room_state, defer_collect=False
                                    )
                            except MowerExit:
                                raise
                            except Exception as e:
                                logger.warning(f"训练室顺路更新状态失败: {e}")
                                raise
                        else:
                            # 手动训练也读取当前面板，但不启动专精调度或收取。
                            from arknights_mower.solvers.mastery_reader import (
                                read_room_state,
                            )

                            self.train_room_state = None
                            manual_room_state = read_room_state(self, enter=False)
                            _mood_data = self.get_agent_from_room(room, None)
                            trainee = (
                                _mood_data[1].get("agent", "")
                                if len(_mood_data) > 1
                                else ""
                            )
                            _stop_if_scheduled_trainee(
                                self, trainee, manual_room_state, detail_open=True
                            )
                            mood_info = [
                                f"干员: '{item['agent']}', 心情: {round(item['mood'], 3)}"
                                for item in _mood_data
                                if item.get("agent")
                            ]
                            if mood_info:
                                logger.info(
                                    f"房间 {self.translate_room(room)}  {mood_info}"
                                )
                    else:
                        num = len(self.op_data.plan[room])
                        previous = {
                            op.name
                            for op in self.op_data.operators.values()
                            if op.current_room == room
                        }
                        _mood_data = self.get_agent_from_room(
                            room,
                            list(range(num))
                            if room in self.op_data.true_exhaust_room
                            else None,
                            **({"force_mood": True} if room in force_rooms else {}),
                        )
                        actual = {
                            item["agent"] for item in _mood_data if item.get("agent")
                        }
                        for name in previous - actual:
                            op = self.op_data.operators[name]
                            op.current_room, op.current_index = "", -1
                            op.time_stamp = None
                        mood_info = [
                            f"干员: '{item['agent']}', 心情: {round(item['mood'], 3)}"
                            for item in _mood_data
                        ]
                        logger.info(f"房间 {self.translate_room(room)}  {mood_info}")
                    break
                except MowerExit:
                    raise
                except Exception as e:
                    if room == "train":
                        # 巡检不要求账号已建造训练室。进房本身已有有限重试，
                        # 失败后不能再由心情读取／纠错重复进入同一未建造房间。
                        self.train_room_state = None
                        if not room_entered:
                            _training_room_scan_disabled = True
                            logger.warning(
                                f"训练室未建造或进房失败，本次进程停用训练室巡检，继续其他房间：{e}"
                            )
                        else:
                            logger.warning(f"训练室本次读取失败，跳过本轮巡检：{e}")
                        self.back_to_infrastructure()
                        skip_room_exit = True
                        break
                    save_exception(e)
                    logger.exception(e)
                    if error_count > 3:
                        raise e
                    error_count += 1
                    self.back()
                    continue
            if not skip_room_exit:
                self.back()
            force_rooms.discard(room)
            if getattr(self, "_emergency_startup_pending", False):
                self._emergency_replan_releases()
                protect_priority_tasks(
                    self.tasks, op_data=getattr(self, "op_data", None)
                )
                self._emergency_save()

    def _read_initial_card_mood(self):
        """首次规划复用选人卡片预估，不选人或确认换班；失败仍继续启动。"""
        targets = {
            slot.agent
            for slots in self.op_data.plan.values()
            for slot in slots
            if slot.agent not in ("", "Free")
        } | set(self.op_data.config.resting_priority_replacement)
        missing = {
            name
            for name in targets
            if (op := self.op_data.operators.get(name)) is not None
            and name != "菲亚梅塔"
            and op.room != "train"
            and resting_tier(self.op_data, name) != RestingTier.EXCLUDED
            and dorm_candidate_mood(self.op_data, name) is None
        }
        if not missing and config.conf.automatic_rescue_enable:
            from arknights_mower.utils.emergency_plan import configured_rescue_names

            missing = any(
                dorm_candidate_mood(self.op_data, name) is None
                for name in configured_rescue_names(config.conf.automatic_rescue_plan)
            )
        if missing:
            self._scan_card_moods()

    @fixed_selection_profile
    def _scan_card_moods(self):
        """每轮真实规划共用一次升序扫描，首个绿色后的姓名按 24 预估。"""
        if getattr(self, "_card_moods_scanned_this_run", False):
            return
        room = next(
            (
                room
                for room, slots in self.op_data.plan.items()
                if slots
                and not room.startswith("dorm")
                and room not in ("train", "factory")
            ),
            None,
        )
        if room is None or not self.no_pending_task(1):
            return
        self._card_moods_scanned_this_run = True
        deadline = monotonic() + 45
        estimates = self.op_data.dorm_mood_estimates
        try:
            self.enter_room(room, max_attempts=1)
            self.turn_on_room_detail(room)
            for _ in range(4):
                if self.find("confirm_blue") is not None:
                    break
                if monotonic() >= deadline:
                    return
                self.tap((self.recog.w * 0.82, self.recog.h * 0.2))
            else:
                raise AgentSelectionNotReady("未进入卡牌观测页，继续正常巡检")
            # 清除选人页暂选，避免原住客置顶的绿色卡片截断心情升序扫描。
            # 返回基建时取消此页，实际驻员不变。
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.swipe_left(1, "ALL")
            self.switch_arrange_order("心情", room, True)
            previous = None
            observation = None
            observed_names = set()
            for page_index in range(20):
                if monotonic() >= deadline or not self.no_pending_task(1):
                    break
                page = self.wait_for_agent_page(
                    before=previous, observation=observation
                )
                if previous is not None and self.same_agent_page(
                    page, previous, allow_unknown=True
                ):
                    break
                observed_at = datetime.now()
                full_card = False
                for name, scope in page:
                    if agent_card_selected(self.recog.img, scope) is not False:
                        raise AgentSelectionNotReady(
                            "卡牌仍选中或边框不明，取消本轮心情预估"
                        )
                    first_observation = name not in observed_names
                    if name:
                        observed_names.add(name)
                    mood = estimate_agent_mood(self.recog.img, scope)
                    if name:
                        if mood is None:
                            if first_observation:
                                estimates.pop(name, None)
                        else:
                            estimates[name] = (mood, observed_at)
                    if mood == 24:
                        # 心情升序首次出现绿色后，其余姓名只获得短期满值预估。
                        # 绿色之前已观测但不可读的卡牌不被默认值覆盖。
                        estimates.update(
                            (candidate, (24, observed_at))
                            for candidate in agent_list
                            if candidate not in observed_names
                        )
                        full_card = True
                        logger.info(
                            "心情升序遇到绿色笑脸，停止翻页，其余干员按 24 预估"
                        )
                        break
                if full_card or page_index == 19 or monotonic() >= deadline:
                    break
                previous = page
                _, observation = self.swipe_agent_page(
                    page, "心情升序扫描", return_page=True
                )
        except (
            MowerExit,
            DeviceRecoveryError,
            ConnectionError,
            ConnectionAbortedError,
        ):
            raise
        except Exception as e:
            logger.warning(f"卡牌心情预估未完成，继续正常巡检：{e}")
        finally:
            self.back_to_infrastructure()

    def _observed_group_return_plan(self):
        """完整在岗观测生成回班意图，实际组状态仍由任务确认提交。"""
        if self._initial_mood_read_pending() or self._emergency_frozen():
            return {}
        pending = [
            getattr(self, "task", None),
            *getattr(self, "tasks", []),
            *getattr(self, "waiting_group_shifts", []),
        ]
        if any(
            getattr(task, "group_shift_expected", {})
            or getattr(task, "backup_shift_active", False)
            or getattr(task, "dorm_recovery_restore", [])
            or task is not None
            and task.type == TaskTypes.FIAMMETTA
            and task.time <= datetime.now()
            for task in pending
        ):
            return {}
        plan = {}
        for group, resting in self.op_data.group_shift_state.items():
            if not resting:
                continue
            members = [
                self.op_data.operators[name]
                for name in self.op_data.shift_group_members(group)
                if self.op_data.is_group_shift_anchor(self.op_data.operators[name])
            ]
            if not members or any(
                op.time_stamp is None
                or (op.current_room, op.current_index) != (op.room, op.index)
                for op in members
            ):
                continue
            anchor = next(
                (op for op in members if op.room not in ("train", "factory")), None
            )
            if anchor is None:
                training = {}
                for op in members:
                    if op.room == "train":
                        training.setdefault(
                            "train", ["Current"] * len(self.op_data.plan["train"])
                        )[op.index] = op.name
                self._suppress_train_correction(training)
                anchor = next(
                    (
                        self.op_data.operators[name]
                        for name in training.get("train", [])
                        if name != "Current"
                    ),
                    None,
                )
            if anchor is not None:
                plan.setdefault(
                    anchor.room, ["Current"] * len(self.op_data.plan[anchor.room])
                )[anchor.index] = anchor.name
        return plan

    def agent_get_mood(
        self,
        skip_dorm=False,
        force=False,
        *,
        read_rooms=True,
        return_plan=False,
        explicit_slots=(),
    ):
        """刷新缓存并生成纠偏计划。

        ``read_rooms=False`` 只使用已经缓存的干员位置和心情。副表切换使用
        这个模式在内存中收敛最终排班，禁止为了推导结果反复进入游戏房间。
        ``return_plan=True`` 返回差异而不把纠错任务塞进队列。
        ``explicit_slots`` 保留预演中已应用的副表显式驻员，优先于普通纠错。
        """
        if read_rooms and self._read_agent_mood() is False:
            return {} if return_plan else None
        if self._emergency_frozen():
            return {} if return_plan else None
        plan = self.op_data.plan
        fix_plan = {}
        for key in plan:
            need_fix = False
            _current_room = self.op_data.get_current_room(key, True)
            # 训练室读取固定两格；纠错只管理排班中明确配置的槽位。
            for idx, name in enumerate(_current_room[: len(plan[key])]):
                slot = plan[key][idx]
                owner = self.op_data.operators.get(slot.agent)
                replacements = (
                    owner.replacement if owner is not None else slot.replacement
                )
                if (key.startswith("dorm")) and plan[key][idx].agent == "Free":
                    # 动态床位允许空着；补床由需要休息的候选触发。
                    continue
                # 如果是空房间
                if name == "":
                    if not need_fix:
                        fix_plan[key] = ["Current"] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx].agent
                    continue
                # 随意人员则跳过
                if plan[key][idx].agent == "Free":
                    continue
                if not (
                    name == plan[key][idx].agent
                    or (
                        (name in replacements and name not in TRADE_ORDER_AGENTS)
                        and len(replacements) > 0
                    )
                ):
                    if not need_fix:
                        fix_plan[key] = ["Current"] * len(plan[key])
                        need_fix = True
                    fix_plan[key][idx] = plan[key][idx].agent
        # 最后如果有任何高效组心情没有记录 或者高效组在宿舍
        # 宿舍绑组成员由组状态纠错处理；下班期间离开固定位置是正常状态。
        if (
            not config.conf.enable_mastery
            and getattr(self, "train_room_state", None) is not None
        ):
            self.train_room_state = None
        train_room_state = (
            getattr(self, "train_room_state", None)
            if config.conf.enable_mastery
            else None
        )
        train_blocked = config.conf.enable_mastery and (
            getattr(train_room_state, "state", None) in ("training", "waiting_collect")
            or getattr(train_room_state, "locked", None) is True
            or getattr(train_room_state, "protected", None) is True
        )
        miss_list = {
            k: v
            for k, v in self.op_data.operators.items()
            if v.not_valid()
            and not (v.room == "train" and _training_room_scan_disabled)
            and not (v.group and v.room.startswith("dorm"))
            and not v.multi_group
            and not self.op_data.is_standby(k)
            and not (
                train_blocked
                and v.room == "train"
                and not (config.conf.assistant_follows_schedule and v.index == 0)
            )
        }
        if len(miss_list.keys()) > 0:
            # 替换到他应该的位置
            logger.debug(f"高效组心情没有记录{str(miss_list)}")
            for key in miss_list:
                _agent = miss_list[key]
                if (
                    _agent.group != ""
                    and self.op_data.group_is_resting(_agent.group)
                    and (
                        _agent.workaholic
                        or self.op_data.rest_mood_complete(key)
                        or _agent.time_stamp is not None
                        and (
                            _agent.current_mood() >= _agent.upper_limit
                            or _agent.mood >= _agent.upper_limit
                        )
                    )
                ):
                    logger.debug(f"跳过检查{_agent}")
                    continue
                elif _agent.group and self.op_data.is_group_shift_anchor(_agent):
                    # 把所有小组成员都移到工作站（已在岗成员跳过，避免 no-op 假任务）
                    _add_group_to_fix_plan(fix_plan, self.op_data, _agent.group)
                if _agent.room not in fix_plan.keys():
                    fix_plan[_agent.room] = ["Current"] * len(
                        self.op_data.plan[_agent.room]
                    )
                fix_plan[_agent.room][_agent.index] = key
                # 如果是错位：
                if (
                    _agent.current_index != -1 and _agent.current_index != _agent.index
                ) or (_agent.current_room != "" and _agent.room != _agent.current_room):
                    moved_room = _agent.current_room
                    moved_index = _agent.current_index
                    # 真实位置可能在未配置的训练室；只恢复排班明确管理的原槽位。
                    moved_slots = self.op_data.plan.get(moved_room, [])
                    if 0 <= moved_index < len(moved_slots):
                        fix_plan.setdefault(moved_room, ["Current"] * len(moved_slots))[
                            moved_index
                        ] = moved_slots[moved_index].agent
        # 还要确保同一组在同时上班
        for g in self.op_data.groups:
            g_agents = [
                name
                for name in self.op_data.groups[g]
                if not self.op_data.operators[name].room.startswith("dorm")
                and not self.op_data.operators[name].multi_group
                and not self.op_data.operators[name].workaholic
                and not self.op_data._can_standby(self.op_data.operators[name])
            ]
            is_any_working = next(
                (
                    x
                    for x in g_agents
                    if self.op_data.operators[x].current_room != ""
                    and not self.op_data.operators[x].is_resting()
                ),
                None,
            )
            if is_any_working is not None:
                # 确保所有人同时在上班
                is_any_resting = next(
                    (
                        x
                        for x in g_agents
                        if self.op_data.operators[x].current_room == ""
                        or self.op_data.operators[x].is_resting()
                    ),
                    None,
                )
                if is_any_resting is not None:
                    # 生成纠错任务
                    for x in g_agents:
                        if (
                            self.op_data.operators[x].current_room == ""
                            or self.op_data.operators[x].is_resting()
                        ):
                            room = self.op_data.operators[x].room
                            if room not in fix_plan:
                                fix_plan[room] = ["Current"] * len(plan[room])
                            fix_plan[room][self.op_data.operators[x].index] = x
        if len(fix_plan.keys()) > 0:
            # 不能在房间里安排同一个人 如果有重复则换成Free
            remove_keys = []
            logger.debug(f"Fix_plan {str(fix_plan)}")
            for key in fix_plan:
                if "dormitory" in key:
                    # 如果宿舍差Free干员  则跳过
                    if (
                        next(
                            (e for e in fix_plan[key] if e not in ["Free", "Current"]),
                            None,
                        )
                        is None
                        and skip_dorm
                    ):
                        remove_keys.append(key)
                        continue
            if len(remove_keys) > 0:
                for item in remove_keys:
                    del fix_plan[item]
            # #207：训练室受专精管理或受保护时不参与纠错——弹掉 fix_plan 里的 train 项
            # （受保护时发节流提醒邮件）。fix_plan 拿 op_data 缓存比对静态计划，专精
            # 活跃/受保护时缓存与计划必然错位，不弹会每轮生成训练室纠错（反复进出）。
            self._suppress_train_correction(fix_plan)
            # Prefer replacements after all correction passes; if none are available,
            # retain the original correction's recall instead of blocking it.
            from arknights_mower.utils.resting_correction import (
                prefer_resting_replacements,
            )

            prefer_resting_replacements(self.op_data, fix_plan, _is_mastery_busy)
            # 整组回班可能补入训练位，仍须经过相同的专精保护。
            self._suppress_train_correction(fix_plan)
        from arknights_mower.utils.resting_correction import (
            correct_group_dorms,
            suppress_completed_dorm_returns,
        )

        if read_rooms and not return_plan:
            _merge_plan_overlay(
                fix_plan, self._observed_group_return_plan(), self.op_data
            )
        if self.op_data.has_dorm_groups():
            correct_group_dorms(self.op_data, fix_plan, _is_mastery_busy)
        if read_rooms:
            from arknights_mower.utils.resting_correction import (
                reconsider_low_mood_replacements,
            )

            reconsider_low_mood_replacements(self.op_data, fix_plan, _is_mastery_busy)
        suppress_completed_dorm_returns(self.op_data, fix_plan)
        explicit = {}
        for room, index in explicit_slots:
            if room in plan and 0 <= index < len(plan[room]):
                current = self.op_data.get_current_operator(room, index)
                explicit.setdefault(room, ["Current"] * len(plan[room]))[index] = (
                    current.name if current else "Free"
                )
        _merge_shift_transition(fix_plan, explicit, self.op_data)
        if not self.op_data.normalize_shared_arrangement(
            fix_plan, explicit_slots=explicit_slots
        ):
            logger.debug("多绑组纠错替班暂不可用，保留当前安排")
            return {} if return_plan else None
        self._suppress_train_correction(fix_plan)
        if return_plan:
            return fix_plan
        if len(fix_plan.keys()) > 0:
            # 如果5分钟之内有任务则跳过心情读取
            next_task = self.find_next_task()
            next_shift_off = self.find_next_task(task_type=TaskTypes.SHIFT_OFF)
            second = (
                0
                if next_task is None
                else (next_task.time - datetime.now()).total_seconds()
            )
            # 如果下个任务的操作时间超过下个任务，则跳过
            shift_off_blocks = next_shift_off is not None and not (
                force and next_shift_off is self.task
            )
            if (
                not force
                and next_task is not None
                and len(fix_plan.keys()) * 45 > second
            ) or shift_off_blocks:
                logger.info("有未完成的任务，跳过纠错")
                self.skip()
                return
            else:
                correction = SchedulerTask(
                    task_plan=fix_plan, task_type=TaskTypes.SELF_CORRECTION
                )
                current_task = getattr(self, "task", None)
                duplicate = next(
                    (
                        task
                        for task in self.tasks
                        if task is not current_task
                        and task.type == TaskTypes.SELF_CORRECTION
                        and task.plan == fix_plan
                    ),
                    None,
                )
                if duplicate is not None:
                    logger.info("已存在相同纠错任务，跳过重复生成")
                    return "self_correction"
                self.tasks.append(correction)
                logger.info(f"纠错任务为-->{fix_plan}")
                return "self_correction"

    def _train_mastery_active(self) -> bool:
        """训练室是否受专精管理：enable_mastery 开 + DB 有 active 计划 或 队列有专精任务。

        #59：队列重启后可能没补回来，DB 为准；队列补队覆盖「idle 计划即将排」的竞态窗口。
        """
        if not config.conf.enable_mastery:
            return False
        try:
            from arknights_mower.utils.mastery_db import get_active_plan

            if get_active_plan() is not None:
                return True
        except Exception:
            pass
        return (
            self.find_next_task(task_type=TaskTypes.SKILL_UPGRADE) is not None
            or self.find_next_task(task_type=TaskTypes.SWAP_SUPPORT) is not None
        )

    def _train_protected(self) -> bool:
        """训练室是否受保护：协助位（槽0）是逻各斯/艾丽妮（§4.4）。

        铁律 10/§7.3：enable_mastery OFF 时保护全停、排班照常排训练室，故先按开关门控。
        用 op_data 缓存判定（深读训练室浮窗会让纠错生成阶段反复进出训练室，反而放大
        本票要消除的问题）；缓存漏过保护时，执行闸门 agent_arrange_room 在
        enable_mastery ON 路径读 room_state.protected 兜底（OFF 时保护本就全停，不兜底）。
        """
        if not config.conf.enable_mastery:
            return False
        return self.op_data.get_train_support() in ("逻各斯", "艾丽妮")

    def _suppress_train_correction(self, fix_plan: dict) -> None:
        """专精管理时保护训练位；协助位是否纠错由跟随排班开关决定。"""
        if "train" not in fix_plan:
            return
        if _training_room_scan_disabled:
            fix_plan.pop("train")
            logger.debug("本次进程已停用训练室巡检，跳过训练室纠错")
            return
        if not config.conf.enable_mastery:
            # 关闭自动专精后不消费旧计划／旧房态保护；执行前仍会实读训练室，
            # 保留训练位被占用时不强行换人的原有保护。
            self.train_room_state = None
            return
        train_room_state = getattr(self, "train_room_state", None)
        mastery_active = self._train_mastery_active()
        train_locked = (
            getattr(train_room_state, "state", None) in ("training", "waiting_collect")
            or getattr(train_room_state, "locked", None) is True
        )
        train_protected = (
            self._train_protected()
            or getattr(train_room_state, "protected", None) is True
        )
        if not (mastery_active or train_locked or train_protected):
            return
        if config.conf.assistant_follows_schedule:
            # 与实际换人闸门一致：跟随开启时允许协助位纠错，训练位不动。
            # 必须先于整房抑制，否则活跃专精计划会吞掉协助位纠错。
            if len(fix_plan["train"]) > 1:
                fix_plan["train"][1] = "Current"
            if all(slot == "Current" for slot in fix_plan["train"]):
                fix_plan.pop("train")
            return
        fix_plan.pop("train")
        if mastery_active:
            logger.debug("训练室受专精管理，跳过训练室纠错")
        elif train_protected:
            logger.debug("训练室受保护，跳过训练室纠错")
            self._notify_train_correction_skipped()
        else:
            logger.debug("训练室处于锁定状态且未开启协助位跟随，跳过训练室纠错")

    def _notify_train_correction_skipped(self) -> None:
        """训练室受保护导致纠错跳过 → 发节流提醒邮件（⑤ protected，key=协助位:训练位）。

        复用 ⑤ 类型与其 key 约定（铁律 8 通知共 8 类）；与 mastery_reader 的
        _notify_protected（mower 无法开始训练）同 key 去重——同一受保护组合至多一封。
        """
        from arknights_mower.utils.email import send_message
        from arknights_mower.utils.mastery_db import should_notify

        current = self.op_data.get_current_room("train", True)
        support = current[0] if current and current[0] else "未知"
        train_slot = current[1] if current and len(current) > 1 and current[1] else "空"
        key = f"{support}:{train_slot}"
        if should_notify("protected", key):
            msg = (
                f"训练室受保护（协助位 {support}），排班纠错已跳过该训练室，"
                "mower 不调整该房间"
            )
            send_message(msg, level="WARNING")

    def generate_product(self, agent: str, *, task=None, snapshot=None):
        """
        Process materials in a factory with specified operators
        Args:
            agent: List of operators that need two production cycles
        """

        from arknights_mower.utils.workshop_automation import (
            restore_if_no_plans,
            workshop_task_snapshot,
        )
        from arknights_mower.utils.workshop_config import workshop_lock
        from arknights_mower.utils.workshop_limits import (
            batch_delta,
            batch_limit,
            blocked_workshop_recipes,
            deer_batch_limit,
            recipe_quantities,
            reject_workshop_recipe,
        )
        from arknights_mower.utils.workshop_mood import mood_cost, operator_mood_rules

        try:
            if snapshot is None:
                snapshot = workshop_task_snapshot(task)
            if snapshot is None or not snapshot.is_current():
                return
            settings = snapshot.settings
            is_9colored = agent == "九色鹿"

            def deer_gap():
                for attempt in range(3):
                    self.recog.update()
                    causality = self.digit_reader.get_deer_causality(self.recog.gray)
                    if causality is not None:
                        return 40 - causality
                    if attempt < 2:
                        self.sleep()
                logger.error("九色鹿因果数字模板匹配失败，停止加工")
                return None

            if agent not in [s.operator for s in settings]:
                logger.info(f"当前干员{agent}不在加工站配置中")
                return
            item_list = next((s.items for s in settings if s.operator == agent))
            from arknights_mower.utils.workshop_recommendation import (
                scope_workshop_items,
            )

            item_list = scope_workshop_items(agent, item_list, workshop_formula)
            if not item_list:
                logger.info(f"{agent}没有符合材料范围的加工配置，跳过")
                return
            operator = self.op_data.operators[agent]
            mood_budget = max(0, min(24, operator.mood))
            if mood_budget < 1:
                logger.info(f"{agent}心情不足1点，跳过加工任务")
                return
            restore_if_no_plans()
            if not snapshot.is_current():
                return
            mood_rules, mood_rules_known = operator_mood_rules(agent)
            unknown_cnt = 0
            inventory_data = get_inventory_counts()
            seen = set()
            group = defaultdict(dict)
            recipe_moods = {}
            for item in item_list:
                for name in item.item_names:
                    if name in seen:
                        logger.warning(
                            f"当前干员{agent}的加工站配置中存在重复材料{item.item_names}，以第一个设置为准"
                        )
                        continue
                    seen.add(name)
                    metadata = workshop_formula[name]
                    if is_9colored and metadata["apCost"] > 4:
                        logger.warning("跳过心情大于4消耗的材料")
                    else:
                        group[metadata["tab"]][name] = item
                        recipe_moods[name] = mood_cost(
                            name, metadata, mood_rules, mood_rules_known
                        )
            blocked_materials = set()

            def available_groups():
                rejected = blocked_workshop_recipes(inventory_data)
                return {
                    tab: eligible
                    for tab, entries in group.items()
                    if (
                        eligible := {
                            name: setting
                            for name, setting in entries.items()
                            if name not in blocked_materials
                            and name not in rejected
                            and recipe_moods[name] <= mood_budget
                            and batch_limit(
                                name, workshop_formula[name], setting, inventory_data
                            )
                            > 0
                        }
                    )
                }

            tab_queue = deque(available_groups().items())
            reset_scan = True
            if not tab_queue:
                logger.info(
                    f"{agent}当前心情{mood_budget:.2f}，没有可加工材料，跳过加工"
                )
                return
            tab_pos = {
                name: scale_point(self.recog, point)
                for name, point in FORMULA_TABS.items()
            }
            current_material = None
            current_name = None
            tasks = ["enter", "select", "process"]
            inf_material = "基建材料"
            gap = 0
            start_time = datetime.now()
            while tasks:
                if not snapshot.is_current():
                    break
                if datetime.now() - start_time > timedelta(
                    minutes=5
                ):  # 检测是否超过 5 分钟
                    raise Exception("循环运行时间超过 5 分钟，可能卡死")
                scene = self.factory_scene()
                if scene == Scene.UNKNOWN:
                    unknown_cnt += 1
                    if unknown_cnt > 5:
                        unknown_cnt = 0
                        self.back_to_infrastructure()
                        self.enter_room("factory")
                    else:
                        self.sleep()
                elif scene == Scene.CONNECTING:
                    self.sleep()
                elif self.find("arrange_check_in") or self.find(
                    "arrange_check_in_small"
                ):
                    self.tap(scale_point(self.recog, CONFIRM_OPERATOR), interval=0.5)
                elif scene == Scene.FACTORY_DASHBOARD:
                    if tasks[0] == "enter":
                        if is_9colored:
                            gap = deer_gap()
                            if gap is None:
                                return
                            logger.debug(f"初次记录九色鹿技能差值{gap}")
                        del tasks[0]
                    elif tasks[0] == "select":
                        self.tap(scale_point(self.recog, OPEN_FORMULA), interval=0.5)
                    else:
                        add_btn = (self.recog.w * 0.84, self.recog.h * 0.4)
                        inventory_data = get_inventory_counts()
                        batch_count = batch_limit(
                            current_name,
                            current_material,
                            group[current_material["tab"]][current_name],
                            inventory_data,
                        )
                        if batch_count == 0:
                            tasks.insert(0, "select")
                            tab_queue = deque(available_groups().items())
                            reset_scan = True
                            continue
                        ap_cost = current_material["apCost"]
                        material_tab = current_material["tab"]
                        per_craft_mood = recipe_moods[current_name]
                        batch_count = min(
                            batch_count, int(mood_budget // per_craft_mood)
                        )
                        if batch_count == 0:
                            blocked_materials.add(current_name)
                            tasks.insert(0, "select")
                            tab_queue = deque(available_groups().items())
                            reset_scan = True
                            continue
                        is_crit = ap_cost == 4 and material_tab == "精英材料"
                        if is_9colored:
                            mood = self.op_data.operators[agent].mood
                            gap = deer_gap()
                            if gap is None:
                                return
                            logger.debug(f"九色鹿技能差值{gap}")
                            if gap > 40:
                                logger.error("识别九色鹿阈值出错拉!任务停止")
                                return
                            if 0 < gap < 5:
                                if mood >= 4:
                                    if not is_crit:
                                        tasks.insert(0, "select")
                                        tab_queue = deque(available_groups().items())
                                        reset_scan = True
                                        logger.info(
                                            "检测到九色鹿即将暴击，即将切换成暴击用材料"
                                        )
                                        continue
                                else:
                                    logger.info("暴击心情不足，任务结束")
                                    tasks = []
                                    continue
                            if gap >= 5:
                                if is_crit:
                                    tasks.insert(0, "select")
                                    tab_queue = deque(available_groups().items())
                                    reset_scan = True
                                    logger.info("切换成垫刀材料")
                                    continue
                            batch_count = min(
                                batch_count, deer_batch_limit(gap, ap_cost)
                            )
                        produce_btn = (self.recog.w * 0.88, self.recog.h * 0.88)
                        batch_count = int(batch_count)
                        logger.info(
                            f"{agent}加工{current_name}：库存"
                            f"{inventory_data[recipe_quantities(current_name, current_material)[0]]}，"
                            f"上限{group[material_tab][current_name].self_upper_limit}，"
                            f"本批最多{batch_count}次"
                        )
                        # The selected formula starts at one, as in the deer logic.
                        # Never use MAX: mood can allow more than the stock deficit.
                        for _ in range(batch_count - 1):
                            self.tap(add_btn, interval=0.1)
                        warning = self.find("factory_warning")
                        valid = self.item_valid()
                        if warning or not valid:
                            if not valid and not warning:
                                # Retain the rejection across workers with the same stock.
                                reject_workshop_recipe(current_name, inventory_data)
                                blocked_materials.add(current_name)
                                tasks.insert(0, "select")
                                tab_queue = deque(available_groups().items())
                                reset_scan = True
                                logger.info("检测到当前材料用完，切换其他材料")
                                continue
                            tasks = []
                            logger.info("检测到干员心情见底或材料不足，任务结束")
                            self.op_data.operators[agent].mood = 0
                            self.op_data.operators[agent].time_stamp = datetime.now()
                            self.op_data.operators[agent].mood_is_prediction = True
                            logger.debug("设置加工站干员心情为0，别问我，我懒得算了")
                            continue
                        batches = batch_count
                        output, _, costs = recipe_quantities(
                            current_name, current_material
                        )
                        try:
                            # Only submission holds the config lock; result reads don't.
                            with workshop_lock:
                                if not snapshot.is_current():
                                    break
                                self.tap(produce_btn, interval=2)
                            for _ in range(11):
                                if (
                                    self.factory_scene()
                                    == Scene.FACTORY_PRODUCT_COLLECT
                                ):
                                    break
                                self.sleep()
                            else:
                                raise ValueError("未确认加工完成")
                            self.recog.save_screencap("workshop")
                            delta = batch_delta(current_name, current_material, batches)
                            apply_workshop_inventory(delta)
                        except Exception:
                            uncertain = [output, *costs]
                            if current_material.get("goldCost"):
                                uncertain.append("龙门币")
                            invalidate_workshop_inventory(uncertain)
                            send_message(
                                f"{agent}加工{current_name}后未能确认加工完成，"
                                "已暂停相关材料的加工，请重新读取仓库。",
                                level="WARNING",
                            )
                            raise
                        if config.conf.enable_mastery:
                            from arknights_mower.utils.mastery_recommendation import (
                                auto_schedule_mastery_tasks,
                            )

                            try:
                                ready = auto_schedule_mastery_tasks(
                                    inventory=get_inventory_counts()
                                )
                                self._dispatch_scan_start_tasks(ready["scheduled"])
                            except MowerExit:
                                raise
                            except Exception:
                                logger.exception("加工库存已确认，但专精任务派发失败")
                        if config.conf.workshop_auto_active:
                            from arknights_mower.utils.workshop_automation import (
                                update_workshop_config,
                            )

                            update_workshop_config()
                        logger.info(
                            f"{agent}加工{current_name}完成{batches}次，库存变化{delta}"
                        )
                        inventory_data = get_inventory_counts()
                        blocked_materials.clear()
                        mood_budget = max(0, mood_budget - batches * per_craft_mood)
                        operator.mood = mood_budget
                        operator.time_stamp = datetime.now()
                        operator.mood_is_prediction = True
                        tab_queue = deque(available_groups().items())
                        if not tab_queue:
                            logger.info(
                                f"{agent}当前心情{mood_budget:.2f}，已无可加工材料，结束加工"
                            )
                            break
                        tasks.insert(0, "select")
                        reset_scan = True
                elif scene == Scene.FACTORY_FORMULA:
                    if tasks[0] in ["enter", "process"]:
                        self.back()
                    else:
                        if reset_scan:
                            # 重新切换材料则重头开始
                            self.tap(tab_pos["芯片"], interval=0.2)
                            self.tap(tab_pos[inf_material], interval=0.2)
                            logger.debug("切换到基建材料页")
                            reset_scan = False
                        if not tab_queue:
                            logger.info("没有任何材料满足条件，任务结束")
                            tasks = []
                            continue
                        tab, item_list = tab_queue.popleft()
                        item_list = set(item_list)
                        self.tap(tab_pos[tab], interval=0.2)
                        logger.info(f"开始检索{tab}的材料")
                        logger.debug(
                            f"[workshop-scan] tab={tab} initial_candidates={sorted(item_list)}"
                        )
                        last_scaned = []
                        scan_round = 0
                        while item_list:
                            scanned_items = self.item_list()
                            current_scan = [item for item, pos, valid in scanned_items]
                            logger.debug(
                                f"[workshop-scan] tab={tab} round={scan_round} "
                                f"current_scan={current_scan} remaining_candidates={sorted(item_list)}"
                            )
                            if current_scan == last_scaned:
                                logger.debug(
                                    f"[workshop-scan] tab={tab} reached_bottom "
                                    f"round={scan_round} last_scan={last_scaned}"
                                )
                                logger.info("已经到底了")
                                break
                            last_scaned = current_scan
                            for item, pos, valid in scanned_items:
                                if item in item_list:
                                    good_to_go = True
                                    if is_9colored:
                                        if 0 < gap < 5:
                                            good_to_go = (
                                                workshop_formula[item]["apCost"] == 4
                                                and workshop_formula[item]["tab"]
                                                != inf_material
                                            )
                                        else:
                                            good_to_go = (
                                                0 < workshop_formula[item]["apCost"] < 4
                                                or workshop_formula[item]["tab"]
                                                == inf_material
                                            )
                                    if valid and good_to_go:
                                        logger.info(f"检测到{item}满足条件，开始加工")
                                        self.tap(
                                            (
                                                (pos[0][0] + pos[1][0]) / 2,
                                                (pos[0][1] + pos[1][1]) / 2,
                                            ),
                                            interval=0.5,
                                        )
                                        current_material = workshop_formula[item]
                                        current_name = item
                                        item_list = []
                                        del tasks[0]
                                        break
                                    else:
                                        if not valid:
                                            reject_workshop_recipe(item, inventory_data)
                                        logger.info(f"检测到{item}不满足条件，跳过")
                                        item_list.remove(item)
                            scan_round += 1
                            self.swipe_noinertia(
                                (0.5 * self.recog.w, 0.9 * self.recog.h),
                                (0, -700),
                                interval=1,
                            )

                elif scene == Scene.FACTORY_PRODUCT_COLLECT:
                    self.recog.save_screencap("workshop")
                    self.back()
                elif scene == Scene.FACTORY_ROOM:
                    self.tap((self.recog.w * 0.1, self.recog.h * 0.95), 0.5)
                elif scene == Scene.INFRA_MAIN:
                    self.enter_room("factory")
                self.recog.update()
            self.back()
            self.back_to_infrastructure()
        except MowerExit:
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
            return False

    def _sync_run_order_tasks(self):
        op_data = getattr(self, "op_data", None)
        op_data.refresh_run_order_rooms()
        if self._emergency_frozen():
            self._emergency_filter_tasks()
        # 无房间标记的 RUN_ORDER 可能是插拔后的原班恢复，不得一并删除。
        invalid = [
            task
            for task in self.tasks
            if task.type in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
            and task.meta_data
            and task.meta_data not in op_data.run_order_rooms
            and not hasattr(task, "emergency_original_roster")
            and not getattr(task, "run_order_restore_pending", False)
        ]
        if invalid:
            logger.info(
                "移除不再参与跑单的房间任务：%s",
                sorted({task.meta_data for task in invalid}),
            )
            invalid_ids = {id(task) for task in invalid}
            self.tasks[:] = [task for task in self.tasks if id(task) not in invalid_ids]

    def plan_run_order(self, room):
        if any(
            room in getattr(task, "run_order_original_roster", {})
            for task in self.tasks
        ):
            return
        if not self._emergency_run_order_available(room):
            return
        if getattr(self, "maintenance_entry_pending", False):
            return
        self._sync_run_order_tasks()
        if room not in self.op_data.run_order_rooms:
            return
        replacements = self.op_data.run_order_replacements(room)
        if self.find_next_task(meta_data=room, task_type=TaskTypes.RUN_ORDER):
            return
        in_out_plan = {room: ["Current"] * len(replacements)}
        for idx, choices in enumerate(replacements):
            in_out_plan[room][idx] = next(
                (name for name in choices if name in TRADE_ORDER_AGENTS), "Current"
            )
        execute_time = self.get_run_order_time(room)
        # 读取订单页可能首次发现实际仍在卖玉，不能据此创建空转任务。
        self._sync_run_order_tasks()
        if room not in self.op_data.run_order_rooms:
            return
        self.tasks.append(
            SchedulerTask(
                time=execute_time,
                task_plan=in_out_plan,
                task_type=TaskTypes.RUN_ORDER,
                meta_data=room,
            )
        )

    def run_order_solver(self):
        self._sync_run_order_tasks()
        if len(self.op_data.run_order_rooms) > 0:
            valid = True
            if valid:
                # 处理龙舌兰/但书/佩佩的插拔
                run_order_rooms = self.op_data.run_order_rooms
                for k in list(run_order_rooms):
                    self.plan_run_order(k)
                run_order_rooms = self.op_data.run_order_rooms
                adj_tasks = scheduling(
                    self.tasks, op_data=self.op_data
                )  # 修改scheduling 同时输出撞在一起的前后两个任务
                max_execution = 3
                adj_count = 0

                if run_order_rooms is not None and len(run_order_rooms) >= 3:
                    n = len(run_order_rooms)
                    dp = [0] * (n + 1)
                    dp[1] = 0
                    if n > 1:
                        dp[2] = 1
                    for i in range(3, n + 1):
                        dp[i] = 3 * dp[i - 1] + 2 * dp[i - 2]
                    max_execution = min(
                        dp[n] * 1.25, 15
                    )  # 通过跑单房间计算得到循环次数 同时限制最大次数
                    logger.debug(f"max_execution = {max_execution}")
                    logger.info(run_order_rooms)
                    logger.info(
                        f"当前跑单房间数量为：{n}，计算最大循环次数为: {max_execution + 1}"
                    )
                while (
                    adj_tasks is not None and adj_count <= max_execution
                ):  # 由于改动会增加触发次数 改为<= 多触发一次
                    # logger.error("<UNK>,<UNK>")
                    adjust_0_room = self.get_run_order_adjust_room(
                        adj_tasks
                    )  # 抽离成单独的
                    if adjust_0_room is None:
                        logger.error(
                            f"adjust_0_room的结果为：{adjust_0_room}，获取跑单房间失败，停止循环"
                        )
                        return
                    is_run = self.drone(adjust_0_room, adjust_time=True)
                    adj_tasks = scheduling(
                        self.tasks, op_data=getattr(self, "op_data", None)
                    )
                    adj_count += 1
                    logger.info(f"第{adj_count}次循环结束")
                    if is_run is not None and not is_run:
                        return
        fia_plan, fia_room = self.check_fia()
        if fia_room is not None:
            # 副表可能把肥鸭移到另一宿舍或暂时撤下；只读实际所在的槽位。
            actual_room = self.op_data.operators["菲亚梅塔"].current_room
            fia_room = actual_room if actual_room.startswith("dorm") else None
            if fia_room is None:
                self._refresh_fiammetta_task(None)
        if fia_room is not None and fia_plan is not None:
            if self.find_next_task(task_type=TaskTypes.FIAMMETTA) is None:
                fia_data = self.op_data.operators["菲亚梅塔"]
                fia_idx = (
                    fia_data.current_index
                    if fia_data.current_index != -1
                    else fia_data.index
                )
                result = [{}] * (fia_idx + 1)
                result[fia_idx]["time"] = datetime.now()
                self.enter_room(fia_room)
                result = self.get_agent_from_room(fia_room, [fia_idx])
                self.back()
                if fia_idx >= len(result) or result[fia_idx].get("agent") != "菲亚梅塔":
                    logger.info("肥鸭实际位置已变化，等待纠偏后重新读取充能时间")
                else:
                    logger.info(
                        "下一次进行菲亚梅塔充能："
                        + result[fia_idx]["time"].strftime("%H:%M:%S")
                    )
                    self.tasks.append(
                        SchedulerTask(
                            time=result[fia_idx]["time"], task_type=TaskTypes.FIAMMETTA
                        )
                    )
        if self._emergency_frozen():
            return
        for name in self.op_data.exhaust_agent:
            op = self.op_data.operators[name]
            # skip operator_protected check (TrainingStateMachine removed)
            if (
                op.is_resting()
                or not op.is_high()
                or op.current_room not in base_room_list
            ):
                continue
            if op.current_mood() <= op.lower_limit + 2:
                candidates = self.op_data.groups[op.group] if op.group else [name]
                if self._has_pending_exhausted_shift(candidates):
                    continue
                if (
                    self.find_next_task(
                        task_type=TaskTypes.EXHAUST_OFF, meta_data=op.name
                    )
                    is None
                ):
                    self.enter_room(op.current_room)
                    result = self.get_agent_from_room(
                        op.current_room, [op.current_index]
                    )
                    _time = datetime.now()
                    margin = 20 if name not in self.op_data.rest_in_full_group else 0
                    if (
                        result[op.current_index]["time"] is not None
                        and result[op.current_index]["time"] > _time
                    ):
                        zero_time = result[op.current_index]["time"]
                        zero_time = Operator.exhaust_time_at_lower_limit(
                            op, zero_time, _time
                        )
                        _time = zero_time - timedelta(minutes=10 + margin)
                    elif (
                        op.current_mood() > 0.25 + op.lower_limit
                        and op.depletion_rate != 0
                    ):
                        _time = (
                            datetime.now()
                            + timedelta(
                                hours=(op.current_mood() - op.lower_limit - 0.25)
                                / op.depletion_rate
                            )
                            - timedelta(minutes=10 + margin)
                        )
                    self.back()
                    exhausted_time = _time < datetime.now()
                    if exhausted_time:
                        logger.info(
                            f"{op.name}的下班任务时间{_time}已早于当前时间，改为立即执行"
                        )
                        _time = datetime.now()
                    # plan 是空的是因为得动态生成
                    update_time = False
                    if op.group != "":
                        # 检查是否有其他同组任务，刷新时间
                        for item in self.op_data.groups[op.group]:
                            if item not in self.op_data.exhaust_agent:
                                continue
                            elif self.find_next_task(
                                task_type=TaskTypes.EXHAUST_OFF, meta_data=item
                            ):
                                update_time = True
                                exh_task = self.find_next_task(
                                    task_type=TaskTypes.EXHAUST_OFF,
                                    meta_data=item,
                                )
                                if _time < exh_task.time:
                                    logger.info(
                                        f"检测到用尽同组{op.name}比{item}提前下班，更新任务时间为{_time}"
                                    )
                                    exh_task.time = _time
                                exh_task.meta_data += f",{op.name}"
                                logger.debug(f"更新用尽meta_data为{exh_task.meta_data}")
                    if not update_time:
                        logger.info(f"生成{op.name}的下班任务")

                        self.tasks.append(
                            SchedulerTask(
                                time=_time,
                                task_type=TaskTypes.EXHAUST_OFF,
                                meta_data=op.name,
                            )
                        )
                    # 如果是生成的过去时间，则停止 plan 其他
                    if exhausted_time:
                        break

    # 根据优先级获取跑单冲突时应该要加速的房间
    def get_run_order_adjust_room(self, adj_tasks):
        # 此处出异常会一直运行，抛出None会终止循环，下面还没考虑过会出什么问题，可自行添加
        try:
            adj_0_task, adj_task = adj_tasks
        except TypeError:
            return None
        # Only trade order runs can be Drone Acceleration targets.
        run_orders = [
            t for t in adj_tasks if t.type == TaskTypes.RUN_ORDER and t.meta_data
        ]
        if len(run_orders) != 2:
            return run_orders[0].meta_data if len(run_orders) == 1 else None
        adjust_0_room = adj_0_task.meta_data
        adjust_room = adj_task.meta_data
        # 如果加速房间为跑单房间，则优先使用
        drone_room = self.drone_room
        if any(task.meta_data == drone_room for task in adj_tasks):
            logger.info("检测到加速房间在冲突的跑单任务中，直接采用")
            adjust_0_room = drone_room
        else:
            logger.info("开始比较跑单任务")
            run_order_rooms = self.op_data.run_order_rooms
            logger.debug(f"run_order_rooms：{run_order_rooms}")
            logger.debug(f"adjust_0_room：{adjust_0_room}")
            logger.debug(f"adjust_room：{adjust_room}")

            adjust_0_room_len = len(self.op_data.plan[adjust_0_room])  # 跑单任务首个
            adjust_room_len = len(self.op_data.plan[adjust_room])  # 跑单任务第二个
            # 正常情况按照82算法 1>3>2 进行加速
            # 如果 adjust_0_room 为 2 adjust_room 为 3 则是 2>3, 两者收益比较接近，先加速前面的订单可能更优，故保留特性
            if (
                adjust_0_room_len == 3 and adjust_room_len != 1
            ):  # 参考82算法 优先加速3级
                logger.debug(f"adjust_0_room_len ===> {adjust_0_room_len}")
                logger.debug(f"adjust_room_len ===> {adjust_room_len}")
            elif (
                adjust_0_room_len > adjust_room_len
            ):  # 如果首个任务房间比第二个大 #参考82算法
                adjust_0_room = adjust_room
                adjust_0_room_len = adjust_room_len
            logger.info(f"加速房间 :{adjust_0_room}")
            logger.info(f"加速房间长度 :{adjust_0_room_len}")

        # return adjust_0_room , adjust_0_room_len
        return adjust_0_room

    def _plan_primary_recovery(self, *, scan_moods=True):
        """共用主班轮休规划；普通补位和加工随后安排。"""
        if any(
            task.type == TaskTypes.FIAMMETTA and task.time <= datetime.now()
            for task in self.tasks
        ):
            logger.info("肥鸭任务已到期，充能回岗后再规划下班")
            return
        # 准备数据
        logger.debug(self.op_data.print())
        # 根据剩余心情排序
        self.total_agent = list(
            v
            for v in self.op_data.operators.values()
            if (v.is_high() or (v.current_room == "" and v.room == ""))
            and not v.room.startswith("dorm")
        )
        self.total_agent.sort(key=lambda x: x.current_mood(), reverse=False)
        # 目前有换班的计划后面改
        logger.debug(f"当前基地数据--> {self.total_agent}")
        new_plan = {}
        try:
            # 重新排序
            if self.find_next_task(task_type=TaskTypes.SHIFT_OFF):
                logger.info("有未完成的下班任务")
                return
            if scan_moods and not self._initial_mood_read_pending():
                reserved, _ = dorm_task_reservations(
                    self.op_data, [self.task, *self.tasks]
                )
                candidates = dorm_candidates(self.op_data, reserved)
                if not (candidates.recovering or candidates.estimated_recovering):
                    self._scan_card_moods()
            new_plan = self.resting()
        except (
            MowerExit,
            DeviceRecoveryError,
            ConnectionError,
            ConnectionAbortedError,
        ):
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
        # 更新宿舍任务
        re_order_dorm_plan = try_reorder(self.op_data, new_plan)
        if re_order_dorm_plan:
            if new_plan:
                # resting() 已把 new_plan 原对象放入 SHIFT_OFF；直接合并可确保
                # 工作站换班与宿舍入住一次执行，副表不会在两者之间看到
                # “已离岗但尚未入住宿舍”的瞬时状态并错误叫回整组。
                logger.debug(f"合并宿舍任务{re_order_dorm_plan}")
                _merge_dorm_arrangement(new_plan, re_order_dorm_plan)
            else:
                logger.debug(f"新增宿舍任务{re_order_dorm_plan}")
                self.tasks.append(
                    SchedulerTask(
                        task_plan=re_order_dorm_plan,
                        task_type=TaskTypes.NOT_SPECIFIC,
                    )
                )
        return True

    def _plan_dorm_recovery(self, *, scan_moods=True):
        """共用主班、空床和不养闲人规划；宿舍事件不等待加工入队空档。"""
        if self._emergency_frozen():
            self._emergency_tick()
            return True
        if self._initial_mood_read_pending():
            return False
        if not self._plan_primary_recovery(scan_moods=scan_moods):
            return False
        self._fill_empty_dorms(primary_planned=True)
        try_add_release_dorm({}, None, self.op_data, self.tasks)
        return True

    def plan_solver(self):
        if self._emergency_frozen():
            self._emergency_tick()
            return
        if not self._plan_dorm_recovery():
            return
        if not self.find_next_task(datetime.now() + timedelta(minutes=5)):
            try_workshop_tasks(self.op_data, self.tasks)
        if self.find_next_task(datetime.now() + timedelta(seconds=15)):
            logger.info("有其他任务,跳过宿舍纠错")
            return
        if self.agent_get_mood() is None:
            self.backup_plan_solver()

    def resting(self, *, returning=()):
        self._refresh_deferred_product_reservations()
        reserved_names = self.op_data.reserved_product_replacements
        now = datetime.now()
        # 沿用原下班顺序：只比较距心情下限的余量。显式名单、高低优和
        # 候补均属于宿舍分床规则，不能让仍有心情的组抢走红脸组的替班。
        moods = {
            op.name: dorm_candidate_mood(self.op_data, op.name, now)
            for op in self.total_agent
        }
        self.total_agent.sort(
            key=lambda op: (
                moods[op.name] is None,
                (moods[op.name] or 0) - op.lower_limit,
            )
        )
        shift_candidates = [
            op
            for op in self.total_agent
            if op.is_high()
            and not op.multi_group
            and (not op.group or self.op_data.is_group_shift_anchor(op))
        ]
        # 宿舍的普通空闲者统一交给补床入口，不依赖不养闲人开关；否则先预约
        # 床位并生成普通重排任务，会使真空床又被跑单避让推迟。
        self.plan_metadata()
        # 理想休息人数只描述主力轮休；低优占床另由 available_free("low")
        # 管理，不能抬高这里的当前人数或挡住可接管床位上的大组。
        current_resting = self.op_data.active_high_resting_count()
        effective_dorm_count = sum(
            1 for dorm in self.op_data.dorm if self.op_data.is_effective_free_slot(dorm)
        )
        # 阈值暂定为 0.5；理想休息人数不能超过当前副表下真实可用床位。
        self.ideal_resting_count = (
            min(4, effective_dorm_count)
            if self.op_data.average_mood()
            > self.op_data.config.resting_threshold * config.conf.rescue_threshold
            else effective_dorm_count
        )
        logger.debug(f"当前理想休息人数是{self.ideal_resting_count}")
        # #59：训练室干员跳过休息规划改为「DB 有没有 active 计划」，
        # 不再依赖队列里的 SKILL_UPGRADE（重启后队列可能没补回来 → 失真）。
        # #109：再挂 enable_mastery 门——OFF 时恒 False（残留 active DB 计划
        # 不得让训练室干员永不 SHIFT_OFF 耗光心情，§9 OFF 语义）。
        try:
            from arknights_mower.utils.mastery_db import get_active_plan

            has_active_mastery = (
                config.conf.enable_mastery and get_active_plan() is not None
            )
        except Exception:
            has_active_mastery = False
        _replacement = []
        _plan = {}
        dorm_admissions = {}
        _high_done = False
        attempted_groups = set()
        # 工作组先取得床位预约，空闲干员随后由统一补床入口安排。
        for op in shift_candidates:
            mood = moods[op.name]
            if mood is None:
                continue
            if op.name in returning or (
                op.group
                and any(
                    name in returning
                    and self.op_data.is_group_shift_anchor(self.op_data.operators[name])
                    for name in self.op_data.groups[op.group]
                )
            ):
                continue
            if op.name in _replacement:
                # 本轮已接工作替班的人不能又预约休息床位。
                continue
            if self._resting_tier(op) == RestingTier.EXCLUDED:
                continue
            if op.name in reserved_names:
                continue
            standby_scope = self.op_data.groups[op.group] if op.group else [op.name]
            can_standby = self.op_data.standby_candidates(standby_scope)
            can_preempt = self._resting_tier(op) <= RestingTier.LOW_MAIN and any(
                bed.name
                and resting_tier(self.op_data, bed.name) > self._resting_tier(op)
                and self.op_data._slot_takable(bed, requester=op.name)
                for bed in self.op_data.dorm
            )
            has_group_dorm_bed = op.group and self.op_data.group_dorm_bed_count(
                op.group
            )
            if _high_done and not (can_standby or can_preempt or has_group_dorm_bed):
                continue
            if (
                not can_standby
                and not can_preempt
                and not has_group_dorm_bed
                and current_resting + len(_replacement) >= self.ideal_resting_count
                and self.op_data.available_free() == 0
            ):
                _high_done = True
                continue
            if op.name in self.op_data.workaholic_agent:
                continue
            if (
                op.is_resting()
                or self.op_data.is_standby(op.name)
                or op.current_room in ["factory"]
                or (op.current_room in ["train"] and has_active_mastery)
                or op.room in ["factory"]
                or (op.room in ["train"] and has_active_mastery)
            ):
                continue
            # 忽略掉心情太高的
            if (
                mood >= op.upper_limit
                if self.op_data.custom_mood_limits(op.name) is not None
                else op.upper_limit - mood < 2
            ):
                continue
            # 忽略 用尽，已经处理
            if op.name in self.op_data.exhaust_agent:
                continue
            # 忽略掉心情值没低于上限的的
            if mood > self.op_data.resting_mood_threshold(op):
                continue
            if op.group != "":
                if op.group in self.op_data.exhaust_group:
                    # 忽略掉用尽心情的分组
                    continue
                if op.group in attempted_groups:
                    continue
                attempted_groups.add(op.group)
                group_resting = self.op_data.groups[op.group]
                self.get_resting_plan(
                    group_resting,
                    _replacement,
                    _plan,
                    current_resting,
                    dorm_admissions=dorm_admissions,
                )
            else:
                self.get_resting_plan(
                    [op.name],
                    _replacement,
                    _plan,
                    current_resting,
                    dorm_admissions=dorm_admissions,
                )
        if len(_plan.keys()) > 0:
            self.tasks.append(
                SchedulerTask(task_plan=_plan, task_type=TaskTypes.SHIFT_OFF)
            )
            logger.info(f"生成{_plan}的下班任务")
        return _plan

    def _resting_tier(self, op):
        return resting_tier(self.op_data, op.name)

    def _cached_changed_slot_plan(self, previous_plan, restored_slots=()):
        """合并副表改动的固定岗位，宿舍绑组沿用轮休规则，动态床位另行迁移。"""
        result = {}
        group_dorm_positions = set()
        replacement_positions = set()
        previous_owners = {
            slot.agent: (old_room, slot)
            for old_room, slots in previous_plan.items()
            for slot in slots
            if slot.agent not in ("", "Free", "Current")
        }
        for room, slots in self.op_data.plan.items():
            old_slots = previous_plan.get(room, [])
            for index, slot in enumerate(slots):
                if room.startswith("dormitory_") and slot.agent == "Free":
                    continue
                old = old_slots[index] if index < len(old_slots) else None
                unchanged = old is not None and (
                    old.agent,
                    old.group,
                    tuple(old.replacement),
                    old.group_bindings,
                ) == (
                    slot.agent,
                    slot.group,
                    tuple(slot.replacement),
                    slot.group_bindings,
                )
                if unchanged:
                    if (room, index) not in restored_slots:
                        continue
                    if room.startswith("dorm"):
                        if slot.group:
                            group_dorm_positions.add((room, index))
                        continue
                    # 仅执行任务的副表退出时，也不能召回仍在宿舍的主班。
                    if not self.op_data.operators[slot.agent].is_resting():
                        continue
                current = self.op_data.get_current_operator(room, index)
                owner = self.op_data.operators[slot.agent]
                previous_room, previous = previous_owners.get(slot.agent, (None, None))
                relocated = old is None or old.agent != slot.agent
                if previous is not None and (
                    # 未读驻员和心情的岗位沿用初始化纠错，不推断为离岗。
                    (
                        current is not None
                        or owner.current_room
                        or owner.time_stamp is not None
                    )
                    and previous.group == slot.group
                    and previous.facility == slot.facility
                    and (not relocated or slot.facility or previous_room == room)
                    and [b["group"] for b in previous.group_bindings]
                    == [b["group"] for b in slot.group_bindings]
                    # 在岗主班迁移到新岗位；离岗主班由新岗位的替班接替。
                    and (not relocated or not owner.current_room or owner.is_resting())
                    and (not relocated or not room.startswith("dorm"))
                ):
                    replacement_positions.add((room, index))
                    continue
                if room.startswith("dormitory_") and slot.group:
                    group_dorm_positions.add((room, index))
                    continue
                if current is not None and (
                    current.name == slot.agent
                    or not (relocated and previous is not None)
                    and current.name in self.op_data.operators[slot.agent].replacement
                    and current.name not in TRADE_ORDER_AGENTS
                ):
                    continue
                result.setdefault(room, ["Current"] * len(self.op_data.plan[room]))[
                    index
                ] = slot.agent
        return result, group_dorm_positions, replacement_positions

    def _switch_products_before_backup_plan(self):
        """独立条件触发副表时，等切产物任务完成再切表。"""
        if not self._product_switching_enabled():
            self._discard_product_switches()
            return True
        pending = [
            task
            for task in self.tasks
            if getattr(task, "pending_backup_product_switch", False)
        ]
        desired_products, desired_plan = self._products_after_arrangement({})
        targets = {}
        for room, target in desired_products.items():
            if target == self.op_data.products.get(room):
                continue
            room_plan = desired_plan.get(room) or []
            if not room_plan:
                continue
            facility = room_plan[0].facility
            if not (
                facility == "制造站"
                and target in MANUFACTURE_PRODUCTS
                or facility == "贸易站"
                and target in TRADE_PRODUCTS
            ):
                continue
            targets[room] = target
        existing = {}
        stale_ids = set()
        for task in pending:
            room, product = parse_product_task_meta(task.meta_data)
            if targets.get(room) != product or room in existing:
                stale_ids.add(id(task))
            else:
                existing[room] = task
        self.tasks[:] = [task for task in self.tasks if id(task) not in stale_ids]
        waiting = False
        for room, target in targets.items():
            current = existing.get(room)
            if current is not None:
                waiting = True
                continue
            if self.op_data.facility_states.get(room, {}).get("product") == target:
                continue
            task = SchedulerTask(
                task_type=TaskTypes.SWITCH_PRODUCT,
                meta_data=product_task_meta(room, target),
            )
            task.pending_backup_product_switch = True
            task.pending_product_targets = {room: target}
            self.tasks.append(task)
            waiting = True
            logger.info("副表产物先切换%s：%s", self.translate_room(room), target)
        return not waiting

    def _backup_transition_plan(
        self, previous_plan, original, conditions, previous_dorms, previous_dorm_layout
    ):
        """普通切表与换班推演共用最终岗位、显式任务和宿舍迁移规则。"""
        transition_plan = {}
        deactivated_slots = {}
        # 退出副表时恢复其任务写过的槽位；切入任务在最后覆盖，确保多个
        # 同时生效的副表与合并排班表的覆盖顺序一致。
        for index, bp in enumerate(self.op_data.backup_plans):
            if original[index] and not conditions[index] and bp.task:
                for room, names in bp.task.items():
                    indexes = deactivated_slots.setdefault(room, set())
                    indexes.update(
                        i for i, name in enumerate(names) if name != "Current"
                    )
        restore_plan = {}
        for room, indexes in deactivated_slots.items():
            active_room = self.op_data.plan.get(room)
            if active_room is None:
                continue
            names = ["Current"] * len(active_room)
            for index in indexes:
                if index < len(active_room):
                    names[index] = active_room[index].agent
            if any(name != "Current" for name in names):
                restore_plan[room] = names

        correction, group_dorm_positions, replacement_positions = (
            self._cached_changed_slot_plan(
                previous_plan,
                {
                    (room, index)
                    for room, indexes in deactivated_slots.items()
                    for index in indexes
                },
            )
        )
        # 退出副表恢复岗位时，保留休息的主班仍经替班匹配，不强制回班。
        for room, index in replacement_positions:
            if room in restore_plan:
                restore_plan[room][index] = "Current"
        _merge_plan_overlay(transition_plan, correction, self.op_data)
        _merge_plan_overlay(transition_plan, restore_plan, self.op_data)

        for index, bp in enumerate(self.op_data.backup_plans):
            if not original[index] and conditions[index] and bp.task:
                _merge_plan_overlay(
                    transition_plan, copy.deepcopy(bp.task), self.op_data
                )
                # 副表显式安排优先，不再用绑组默认岗位覆盖。
                group_dorm_positions.difference_update(
                    (room, index)
                    for room, names in bp.task.items()
                    for index, name in enumerate(names)
                    if name != "Current"
                )

        from arknights_mower.utils.resting_correction import (
            preserve_backup_replacements,
        )

        explicit_names = _assigned_operator_names(transition_plan)
        preserved = {
            op.name: (op.current_room, op.current_index)
            for room, index in replacement_positions
            if (op := self.op_data.operators[self.op_data.plan[room][index].agent]).name
            not in explicit_names
            and transition_plan.get(room, [])[index : index + 1] in ([], ["Current"])
        }
        reserved_names, reserved_slots = dorm_task_reservations(
            self.op_data,
            [
                task
                for task in self.tasks
                if task is not getattr(self, "task", None)
                and (
                    task.type != TaskTypes.SHIFT_ON
                    or getattr(task, "product_shift_locked", False)
                )
            ],
        )
        if not preserve_backup_replacements(
            self.op_data,
            transition_plan,
            replacement_positions,
            previous_dorms,
            _is_mastery_busy,
            reserved_names,
            reserved_slots,
        ):
            return None
        # 替班不足时允许召回本人；其余主班仍保留原位置与恢复时间。
        assigned = _assigned_operator_names(transition_plan)
        preserved = {
            name: position
            for name, position in preserved.items()
            if name not in assigned
        }
        recovery = {
            bed.name: (bed.position, bed.time)
            for bed in previous_dorms
            if bed.name in preserved
        }

        if group_dorm_positions:
            from arknights_mower.utils.resting_correction import correct_group_dorms

            # 等工作岗位与副表任务合并后再判断回班，避免把将被替班覆盖的
            # 中间岗位误判为整组召回；只处理切表实际改动的宿舍位置。
            correct_group_dorms(
                self.op_data,
                transition_plan,
                _is_mastery_busy,
                positions=group_dorm_positions,
            )

        current_dorm_layout = dorm_rebalance_signature(self.op_data)
        if previous_dorm_layout is None or previous_dorm_layout != current_dorm_layout:
            # 迁移须与副表已提出的槽位安排比较，不能把被该安排覆盖的
            # 原住者误判为无需移动，导致合并后丢失其床位。
            migration_data = self.op_data.project_arrangements([transition_plan])
            priority_changed = (
                previous_dorm_layout is not None
                and previous_dorm_layout[0] != current_dorm_layout[0]
            )
            dorm_migration = rebalance_plan_swap_dorms(
                migration_data,
                previous_dorms,
                reserved_names=_assigned_operator_names(transition_plan)
                | (reserved_names if priority_changed else set()),
                reorder=priority_changed,
                reserved_slots=(
                    reserved_slots
                    | {
                        (room, index)
                        for room, names in transition_plan.items()
                        for index, name in enumerate(names)
                        if name != "Current"
                    }
                    if priority_changed
                    else ()
                ),
            )
            self.op_data.dorm = migration_data.dorm
            _merge_shift_transition(transition_plan, dorm_migration, self.op_data)
            # 副表收回原床位时沿用宿舍迁移结果；新床的恢复时间须重新读取。
            for room, names in dorm_migration.items():
                for index, name in enumerate(names):
                    if name in recovery and recovery[name][0] != (room, index):
                        preserved[name] = (room, index)
                        recovery[name] = ((room, index), None)
                        for bed in self.op_data.all_dorms():
                            if bed.name == name:
                                bed.time = None
        else:
            logger.debug("副表未改变宿舍床位或房间顺序，跳过宿舍重排")

        from arknights_mower.utils.resting_correction import (
            suppress_completed_dorm_returns,
        )

        suppress_completed_dorm_returns(self.op_data, transition_plan)
        if preserved:
            projected = self.op_data.project_arrangements([transition_plan])
            if any(
                (
                    projected.operators[name].current_room,
                    projected.operators[name].current_index,
                )
                != position
                for name, position in preserved.items()
            ):
                return None
            projected_recovery = {
                bed.name: (bed.position, bed.time)
                for bed in projected.all_dorms()
                if bed.name in preserved
            }
            if any(
                projected_recovery.get(name) != expected
                for name, expected in recovery.items()
            ):
                return None
        transition_plan = {
            room: names
            for room, names in transition_plan.items()
            if any(name != "Current" for name in names)
        }
        return transition_plan

    def _coalesce_backup_transition(self, transition):
        """切表的新意图替换同轮旧安排，保留同批其他成员；返回被合并的任务。"""
        now = datetime.now()
        ordinary = {
            TaskTypes.SHIFT_ON,
            TaskTypes.SHIFT_OFF,
            TaskTypes.SELF_CORRECTION,
            TaskTypes.RE_ORDER,
            TaskTypes.NOT_SPECIFIC,
            TaskTypes.FILL_DORM,
        }

        def footprint(plan):
            names, slots = set(), set()
            for room, agents in plan.items():
                for index, name in enumerate(agents):
                    if name not in ("Current", ""):
                        slots.add((room, index))
                    if name not in ("Current", "Free", ""):
                        names.add(name)
            return names, slots

        names, slots = footprint(transition)
        merged_tasks = []
        remaining = [
            task
            for task in self.tasks
            if task.type in ordinary
            and task.plan
            and min(task.time, getattr(task, "arrangement_retry_due_at", task.time))
            <= now + timedelta(minutes=1)
            and not getattr(task, "strict_mood_limit", False)
            and not getattr(task, "dorm_recovery_restore", [])
        ]
        # 同一批任务可能经由第三条安排互相重叠，按关联范围一次收齐。
        while remaining:
            matched = []
            for task in remaining:
                task_names, task_slots = footprint(task.plan)
                if names & task_names or slots & task_slots:
                    matched.append(task)
                    names.update(task_names)
                    slots.update(task_slots)
            if not matched:
                break
            merged_tasks.extend(matched)
            ids = {id(task) for task in matched}
            remaining = [task for task in remaining if id(task) not in ids]
        if not merged_tasks:
            return transition, []
        merged = {}
        for task in sorted(merged_tasks, key=lambda task: task.time):
            _merge_shift_transition(merged, copy.deepcopy(task.plan), self.op_data)
        _merge_shift_transition(merged, transition, self.op_data)
        merged = {
            room: agents
            for room, agents in merged.items()
            if any(name != "Current" for name in agents)
        }
        logger.info(
            "副表收敛合并 %s 条旧安排，直接执行最终换班：%s", len(merged_tasks), merged
        )
        return merged, merged_tasks

    def _initial_mood_read_pending(self):
        return getattr(self, "defer_backup_plan_until_mood_read", False)

    def _exhaust_task_signatures(self):
        """动态用尽预约依赖生效岗位和组配置，不依赖临时驻员或心情读数。"""
        signatures = {}
        for task in self.tasks:
            if task.type != TaskTypes.EXHAUST_OFF or task.plan:
                continue
            names = set(task.meta_data.split(","))
            for name in tuple(names):
                op = self.op_data.operators.get(name)
                if op is not None and op.group:
                    names.update(self.op_data.groups.get(op.group, []))
            members = []
            for name in sorted(names):
                op = self.op_data.operators.get(name)
                if op is None:
                    members.append((name, None))
                    continue
                slots = self.op_data.plan.get(op.room, [])
                facility = (
                    slots[op.index].facility if 0 <= op.index < len(slots) else None
                )
                members.append(
                    (
                        name,
                        op.room,
                        op.index,
                        op.group,
                        tuple(op.replacement),
                        op.is_high(),
                        op.exhaust_require,
                        op.workaholic,
                        op.rest_in_full,
                        op.lower_limit,
                        op.upper_limit,
                        facility,
                        self.op_data.products.get(op.room),
                    )
                )
            signatures[id(task)] = tuple(members)
        return signatures

    def _invalidate_changed_exhaust_tasks(self, previous):
        current = self._exhaust_task_signatures()
        invalid = {
            task_id
            for task_id, signature in previous.items()
            if task_id in current and current[task_id] != signature
        }
        if invalid:
            self.tasks[:] = [task for task in self.tasks if id(task) not in invalid]
            logger.info("副表生效后移除 %s 条配置已改变的动态用尽预约", len(invalid))
        return bool(invalid)

    def _advance_orders_before_maintenance(self, conditions):
        """维护主班含跑单干员时直接切表，否则先完成停服前跑单。"""
        entering = any(
            active and not previous and backup.uses_major_maintenance_condition
            for active, previous, backup in zip(
                conditions, self.op_data.plan_condition, self.op_data.backup_plans
            )
        )
        if not entering:
            self.maintenance_entry_pending = False
            return False
        projected = copy.deepcopy(
            self.op_data, {id(self.op_data.eval_model): self.op_data.eval_model}
        )
        if error := projected.swap_plan(conditions):
            raise ValueError(f"维护副表预演失败：{error}")
        if projected.run_order_paused:
            self.maintenance_entry_pending = False
            return False
        blocked_orders = blocked_run_order_ids(self.tasks, self.op_data)
        pending = [
            task
            for task in self.tasks
            if getattr(task, "maintenance_advance_before_backup", False)
            and id(task) not in blocked_orders
        ]
        if not pending and not getattr(self, "maintenance_entry_pending", False):
            pending = adjust_run_order_for_maintenance(
                self.tasks, config.conf.run_order_delay, advance_time=datetime.now()
            )
            for task in pending:
                task.maintenance_advance_before_backup = True
            if pending:
                self.tasks.sort(key=lambda task: task.time)
                logger.info("提前执行停服前跑单任务，完成后再切换维护副表")
        self.maintenance_entry_pending = bool(pending)
        return self.maintenance_entry_pending

    def _schedule_maintenance_backup_check(self):
        if self._emergency_frozen():
            return
        op_data = getattr(self, "op_data", None)
        if not isinstance(op_data, Operators):
            return
        deadline = op_data.next_major_maintenance_check()
        checks = [
            task
            for task in self.tasks
            if task.type == TaskTypes.NOT_SPECIFIC
            and task.meta_data == "maintenance_backup_check"
        ]
        # 保留已到期检查，避免睡眠刚结束就删除尚未执行的唤醒。
        if any(task.time <= datetime.now() for task in checks):
            return
        if deadline is not None and len(checks) == 1 and checks[0].time == deadline:
            return
        check_ids = {id(task) for task in checks}
        self.tasks[:] = [task for task in self.tasks if id(task) not in check_ids]
        if deadline is not None:
            self.tasks.append(
                SchedulerTask(time=deadline, meta_data="maintenance_backup_check")
            )
            self.tasks.sort(key=lambda task: task.time)

    def backup_plan_solver(
        self,
        custom_task_time=None,
        generated_tasks=None,
    ):
        """用缓存状态一次性收敛副表，并只生成一张最终差异任务。

        每次检查计算全部条件直到稳定，再把副表任务、岗位纠偏和宿舍迁移合并。
        """
        if self._emergency_frozen() or self._initial_mood_read_pending():
            return False
        # 肥鸭充能中的临时离岗不能作为副表条件；任务间隙和重启恢复时，
        # 已到期的充能／回岗任务也属于同一流程，须等回岗完成再判断。
        now = datetime.now()
        if getattr(
            getattr(self, "task", None), "type", None
        ) == TaskTypes.FIAMMETTA or any(
            task.type == TaskTypes.FIAMMETTA and task.time <= now
            for task in getattr(self, "tasks", [])
        ):
            logger.debug("肥鸭充能或回岗任务尚未完成，跳过副表切换")
            return False
        if any(
            getattr(task, "backup_shift_active", False)
            or getattr(task, "group_shift_expected", {})
            for task in getattr(self, "tasks", [])
        ):
            logger.debug("换班最终安排尚未完成，避免用中间驻员状态重新切表")
            return False
        try:
            if not self.op_data.backup_plans:
                self.maintenance_entry_pending = False
                return False

            initial_conditions = [
                bool(self.op_data.evaluate_expression(str(backup.trigger)))
                for backup in self.op_data.backup_plans
            ]
            if self._advance_orders_before_maintenance(initial_conditions):
                return False

            if any(
                getattr(plan, "products", None) for plan in self.op_data.backup_plans
            ):
                if not self._switch_products_before_backup_plan():
                    return False

            original = list(self.op_data.plan_condition)
            previous_data = self.op_data.project_arrangements([])
            previous_exhaust = self._exhaust_task_signatures()
            previous_plan = copy.deepcopy(self.op_data.plan)
            previous_dorms = copy.deepcopy(self.op_data.all_dorms())
            previous_dorm_layout = dorm_rebalance_signature(self.op_data)
            seen = {tuple(original)}
            current = original
            conditions = initial_conditions
            while True:
                for bp in self.op_data.backup_plans:
                    logger.debug(str(bp.trigger))
                if conditions == current:
                    break
                if current != original and self._advance_orders_before_maintenance(
                    conditions
                ):
                    self.op_data.swap_plan(original, refresh=True)
                    return False
                key = tuple(conditions)
                if key in seen:
                    logger.error(
                        "副表条件在内存演算中出现循环 %s -> %s，保持切换前状态",
                        current,
                        conditions,
                    )
                    if current != original:
                        self.op_data.swap_plan(original, refresh=True)
                    return False
                seen.add(key)
                error = self.op_data.swap_plan(conditions, refresh=True)
                if error:
                    logger.error("副表内存演算失败：%s", error)
                    self.op_data.swap_plan(original, refresh=True)
                    return False
                current = conditions
                conditions = [
                    bool(self.op_data.evaluate_expression(str(bp.trigger)))
                    for bp in self.op_data.backup_plans
                ]

            if current == original:
                return False

            logger.info("副表条件一次性收敛：%s -> %s", original, current)
            had_rest_schedule = any(
                task.type in (TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM)
                for task in self.tasks
            )
            transition_plan = self._backup_transition_plan(
                previous_plan, original, current, previous_dorms, previous_dorm_layout
            )
            if transition_plan is None:
                self.op_data = previous_data
                logger.info("副表替班暂不可用，保留原排班和休息状态")
                return False
            self._invalidate_changed_exhaust_tasks(previous_exhaust)
            self._sync_run_order_tasks()
            self.queue_product_switches()
            generated = None
            if transition_plan:
                transition_plan, superseded = self._coalesce_backup_transition(
                    transition_plan
                )
                generated = SchedulerTask(
                    time=custom_task_time,
                    task_plan=transition_plan,
                    task_type=TaskTypes.RE_ORDER
                    if any(room.startswith("dormitory_") for room in transition_plan)
                    else TaskTypes.SELF_CORRECTION,
                    meta_data="副表内存收敛",
                )
                generated.backup_explicit_slots = self._backup_explicit_slots(
                    original, current
                )
                for pending in superseded:
                    generated.backup_explicit_slots.update(
                        (room, index)
                        for room, index in getattr(pending, "backup_explicit_slots", ())
                        if transition_plan.get(room, [])[index : index + 1]
                        == pending.plan.get(room, [])[index : index + 1]
                    )
                # 完整最终任务先入队，再撤销旧任务，避免丢失同批有效动作。
                self.tasks.append(generated)
                superseded_ids = {id(task) for task in superseded}
                self.tasks[:] = [
                    task for task in self.tasks if id(task) not in superseded_ids
                ]
                self._refresh_deferred_product_reservations()
                if generated_tasks is not None:
                    generated_tasks.append(generated)
                logger.info("副表最终差异任务：%s", transition_plan)

            # 只重建已有的回班队列，不凭切表制造普通回班。
            if had_rest_schedule:
                self.plan_metadata()
            # 回班重建和唤醒常规规划是两个独立步骤；没有实际换人也要规划。
            # 实际换班的完成边界会补回被延期或重启提前消费的空任务。
            followup = SchedulerTask(
                time=custom_task_time,
                task_plan={},
                task_type=TaskTypes.NOT_SPECIFIC,
            )
            self.tasks.append(followup)
            if generated_tasks is not None:
                generated_tasks.append(followup)
            return generated is not None
        except MowerExit:
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
        return False

    def rearrange_resting_priority(self, group):
        operators = [
            name
            for name in self.op_data.groups[group]
            if self.op_data.is_group_shift_anchor(self.op_data.operators[name])
        ]
        if len(operators) == len(self.op_data.groups[group]):
            operators = self.op_data.groups[group]
        # 肥鸭充能新模式：https://github.com/ArkMowers/arknights-mower/issues/551
        fia_plan, fia_room = self.check_fia()
        # 排序
        # 1. 肥鸭充能列表中的干员靠前
        # 2. 不在加工站的干员靠前
        # 3. 心情低的干员靠前
        operators.sort(
            key=lambda y: (
                y not in fia_plan if fia_plan else True,
                self.op_data.operators[y].current_room in ["factory", "train"],
                self.op_data.operators[y].current_mood()
                - self.op_data.operators[y].lower_limit,
            )
        )

        high_count = 0
        for operator in operators:
            if self.op_data.operators[operator].workaholic:
                continue
            if self.op_data.operators[operator].resting_priority == "high":
                high_count += 1
        for operator in operators:
            if self.op_data.operators[operator].workaholic:
                continue
            self.op_data.operators[operator].resting_priority = (
                "high" if high_count > 0 else "low"
            )
            high_count -= 1

    def get_resting_plan(
        self, agents, exist_replacement, plan, current_resting, *, dorm_admissions=None
    ):
        groups = list(
            dict.fromkeys(
                self.op_data.operators[name].group
                for name in agents
                if self.op_data.is_group_shift_anchor(self.op_data.operators[name])
                and self.op_data.operators[name].group
            )
        )
        followers = {
            name
            for group in groups
            for name in self.op_data.shift_group_members(group)
            if self.op_data.operators[name].multi_group
        }
        if not followers:
            return self._get_resting_plan(
                agents,
                exist_replacement,
                plan,
                current_resting,
                dorm_admissions=dorm_admissions,
            )
        transitions = self.op_data.arrangement_group_transitions(plan)
        transitions.update({group: True for group in groups})
        for name in followers:
            op = self.op_data.operators[name]
            resting = self.op_data.resting_binding_groups(op, transitions)
            common = self.op_data.shared_replacements(op, resting)
            if not common:
                logger.debug(
                    "多绑组替班不兼容，暂缓下班：%s，休息组：%s", name, resting
                )
                return
            if op.room.startswith("dorm"):
                bed = next(
                    (
                        bed
                        for bed in self.op_data.dorm
                        if bed.position == (op.room, op.index)
                    ),
                    None,
                )
                if bed is not None and bed.name and "Free" not in common:
                    return
        members = list(
            dict.fromkeys(
                [
                    *agents,
                    *(
                        name
                        for group in groups
                        for name in self.op_data.shift_group_members(group)
                    ),
                ]
            )
        )
        previous_groups = copy.deepcopy(self.op_data.groups)
        previous_state = self.op_data.group_shift_state
        previous = {
            name: (op.group, list(op.replacement))
            for name, op in self.op_data.operators.items()
            if op.multi_group
        }
        try:
            # Bed reservation is retained on admission; group state and bindings
            # remain hypothetical until the arrangement completes.
            self.op_data.group_shift_state = dict(previous_state)
            self.op_data.commit_group_shifts(transitions)
            return self._get_resting_plan(
                members,
                exist_replacement,
                plan,
                current_resting,
                dorm_admissions=dorm_admissions,
            )
        finally:
            self.op_data.group_shift_state = previous_state
            for name, (group, replacements) in previous.items():
                self.op_data.operators[name].group = group
                self.op_data.operators[name].replacement = replacements
            self.op_data.groups = previous_groups

    def _get_resting_plan(
        self, agents, exist_replacement, plan, current_resting, *, dorm_admissions=None
    ):
        from arknights_mower.utils.exhaust_replacement import match_replacements

        self._refresh_deferred_product_reservations()
        reserved_names = self.op_data.reserved_product_replacements
        if any(name in reserved_names for name in agents):
            logger.debug("整组含延期切产物换班预留干员，暂缓规划：%s", agents)
            return
        # 宿舍成员只跟随换班，不以自身心情抢占组内替班或休息优先级。
        dorm_agents = [
            name
            for name in agents
            if self.op_data.operators[name].room.startswith("dorm")
        ]
        if dorm_agents:
            agents = [name for name in agents if name not in dorm_agents]
        __replacement = []
        __plan = {}
        replacement_options = {}
        active_groups = {
            self.op_data.operators[name].group
            for name in [*agents, *dorm_agents]
            if self.op_data.operators[name].group
        }
        required = 0
        for x in agents:
            op = self.op_data.operators[x]
            if op.workaholic or op.room.startswith("dorm"):
                continue
            required += 1
        logger.debug(f"需求:{current_resting} 当前休息")
        logger.debug(f"需求:{required}宿舍空位")
        logger.debug(f"需求:{exist_replacement} 当前安排")
        logger.debug(f"当前计划{plan}")
        success = True

        fia_plan, fia_room = self.check_fia()
        agents.sort(
            key=lambda y: (
                y not in fia_plan if fia_plan else True,
                self.op_data.operators[y].current_room in ["factory", "train"],
                self.op_data.operators[y].current_mood()
                - self.op_data.operators[y].lower_limit,
            )
        )
        agents.extend(dorm_agents)
        for name in agents:
            op = self.op_data.operators[name]
            if not op.is_resting() and not self.op_data.is_standby(name):
                self.op_data.update_standby_low_priority(op)
        logger.debug(f"计算排班:{agents}")
        for agent in agents:
            if not success:
                break
            x = self.op_data.operators[agent]
            if (x.room, x.index) in self.op_data.reserved_product_beds:
                success = False
                break
            if x.room not in base_room_list:
                logger.debug(f"干员房间出错:{agent}")
                success = False
                break
            if (
                not x.multi_group
                and self.op_data.get_dorm_by_name(x.name)[0] is not None
            ):
                # 如果干员已经被安排了
                success = False
                break

            if self.op_data.is_auto_free_dorm_operator(x):
                # 同组姓名只开启这张临时床；不把该姓名安排进宿舍，固定
                # 宿舍成员离岗期间由统一动态床位算法决定实际入住者。
                actual = self.op_data.get_current_operator(x.room, x.index)
                __plan.setdefault(x.room, ["Current"] * len(self.op_data.plan[x.room]))[
                    x.index
                ] = (
                    "Current"
                    if x.multi_group and actual is not None and actual.name != x.name
                    else "Free"
                )
                continue

            def replacement_available(obj):
                replacement = self.op_data.operators[obj]
                in_slot = (replacement.current_room, replacement.current_index) == (
                    x.room,
                    x.index,
                )
                same_group_cover = self.op_data.is_same_group_dorm_replacement(x, obj)
                if (
                    replacement.current_room
                    and not replacement.is_resting()
                    and not (x.multi_group and in_slot)
                    and not (
                        same_group_cover
                        and obj in agents
                        and (replacement.current_room, replacement.current_index)
                        == (replacement.room, replacement.index)
                    )
                ):
                    return False
                if not x.room.startswith("dorm") and self.op_data.replacement_exhausted(
                    obj
                ):
                    return False
                return (
                    obj not in TRADE_ORDER_AGENTS
                    and not _is_mastery_busy(obj)
                    and (
                        obj not in exist_replacement
                        or x.multi_group
                        and plan.get(x.room, [])[x.index : x.index + 1] == [obj]
                    )
                    and obj not in reserved_names
                    and (not self.op_data.is_dorm_replacement(obj) or in_slot)
                    and (
                        x.room.startswith("dorm")
                        or replacement.current_room != x.room
                        or x.multi_group
                        and in_slot
                    )
                )

            replacement_options[agent] = [
                obj
                for obj in self.op_data.replacement_candidates(x)
                if replacement_available(obj)
            ]
        assignments = {}
        if success:
            assignments = match_replacements(replacement_options)
            if assignments is None:
                matched = match_replacements(replacement_options, allow_partial=True)
                missing = [name for name in replacement_options if name not in matched]
                logger.debug(
                    "整组替班不足，暂缓下班：%s；缺%s名替班，未匹配成员：%s；可用替班：%s",
                    agents,
                    len(missing),
                    missing,
                    replacement_options,
                )
                return
        if success:
            working = tuple(
                name
                for name in agents
                if not self.op_data.operators[name].room.startswith("dorm")
                and not self.op_data.operators[name].workaholic
            )
            previous = dorm_residents(self.op_data)
            allocation_plan = copy.deepcopy({**plan, **__plan})
            admissions = {}
            for task in sorted(self.tasks, key=lambda task: task.time):
                if task.type != TaskTypes.SHIFT_OFF:
                    continue
                for room, names in task.plan.items():
                    if not room.startswith("dorm"):
                        continue
                    for index, name in enumerate(names):
                        if index < len(self.op_data.plan.get(room, [])) and (
                            name in self.op_data.operators
                        ):
                            admissions.setdefault((room, index), name)
            admissions.update(dorm_admissions or {})
            # 已入队和本轮成功分床显式占用额度，不从陈旧床位缓存推断预约。
            for (room, index), name in admissions.items():
                row = allocation_plan.setdefault(
                    room, ["Current"] * len(self.op_data.plan[room])
                )
                if row[index] in ("Current", "Free"):
                    row[index] = name
            for attempt in range(2):
                if attempt:
                    assignments = match_replacements(
                        replacement_options, preferred=working
                    )
                    if assignments is None:
                        return
                fixed_resting = {
                    cover
                    for owner, cover in assignments.items()
                    if self.op_data.operators[owner].room.startswith("dorm")
                    and self.op_data.is_same_group_dorm_replacement(
                        self.op_data.operators[owner], cover
                    )
                }
                resting_agents = [
                    x
                    for x in agents
                    if not self.op_data.operators[x].workaholic
                    and not self.op_data.operators[x].room.startswith("dorm")
                    and x not in fixed_resting
                    and self.op_data.get_dorm_by_name(x)[0] is None
                    and not (
                        self.op_data.operators[x].multi_group
                        and any(bed.name == x for bed in self.op_data.all_dorms())
                        and plan.get(self.op_data.operators[x].room, [])[
                            self.op_data.operators[x].index : self.op_data.operators[
                                x
                            ].index
                            + 1
                        ]
                        not in ([], ["Current"])
                    )
                ]
                # 先按配置首选验证整组分床；床位不足时，完整匹配优先
                # 保留可恢复工作替班，不把固定宿舍位开放为普通 Free。
                dorms = self.op_data.assign_dorm_group(
                    resting_agents,
                    active_groups=active_groups,
                    plan=allocation_plan,
                )
                if dorms is not None:
                    break
            else:
                return
            for agent, replacement in assignments.items():
                x = self.op_data.operators[agent]
                __replacement.append(replacement)
                __plan.setdefault(x.room, ["Current"] * len(self.op_data.plan[x.room]))[
                    x.index
                ] = replacement
            restore_displaced_resting(
                self.op_data,
                previous,
                __plan,
                self.tasks,
                admitted={bed.position: bed.name for bed in dorms},
            )
            logger.debug(f"当前替换{__replacement}")
            exist_replacement.extend(__replacement)
            logger.debug(dorms)
            for k, v in __plan.items():
                if k not in plan.keys():
                    plan[k] = __plan[k]
                for idx, name in enumerate(__plan[k]):
                    owner = self.op_data.operators.get(self.op_data.plan[k][idx].agent)
                    if name != "Current" and (
                        plan[k][idx] == "Current"
                        or owner is not None
                        and owner.multi_group
                    ):
                        previous_cover = plan[k][idx]
                        if (
                            previous_cover in exist_replacement
                            and previous_cover != name
                        ):
                            exist_replacement.remove(previous_cover)
                        plan[k][idx] = name
            logger.debug(f"当前plan{plan}")
            if dorm_admissions is not None:
                dorm_admissions.update({bed.position: bed.name for bed in dorms})
            return True

    def initialize_operators(self):
        self.op_data = Operators(self.global_plan)
        Operators.current_room_changed_callback = self.current_room_changed
        return self.op_data.init_and_validate()

    @staticmethod
    def _product_switching_enabled():
        return getattr(getattr(config.conf, "product_switching", None), "enable", False)

    def _discard_product_switches(self):
        """停用切换时移除专用任务，释放预留并保留原换班安排。"""
        self.tasks[:] = [
            task for task in self.tasks if task.type != TaskTypes.SWITCH_PRODUCT
        ]
        for task in self.tasks:
            if getattr(task, "product_shift_locked", False):
                task.time = min(task.time, datetime.now())
            for attr in (
                "pending_product_targets",
                "product_shift_locked",
                "product_lock_slots",
                "product_lock_names",
                "product_switched_before_arrangement",
            ):
                if hasattr(task, attr):
                    delattr(task, attr)
        self.tasks.sort(key=lambda task: task.time)
        selected = getattr(self, "task", None)
        if selected is not None and selected.type == TaskTypes.SWITCH_PRODUCT:
            self.task = None
        self._refresh_deferred_product_reservations()

    def queue_product_switches(self):
        """仅为已识别且与当前排班目标不一致的生产站生成任务。"""
        if not self._product_switching_enabled():
            self._discard_product_switches()
            return
        products = getattr(self.op_data, "products", None)
        if products is None:
            return
        plan = getattr(self.op_data, "plan", {})
        facility_states = getattr(self.op_data, "facility_states", {})
        configured_rooms = set()
        pending_targets = {}
        for task in self.tasks:
            pending_targets.update(getattr(task, "pending_product_targets", {}))
        for room, target_product in (products | pending_targets).items():
            room_plan = plan.get(room) or []
            if not room_plan:
                continue
            facility = room_plan[0].facility
            supported = (
                facility == "制造站" and target_product in MANUFACTURE_PRODUCTS
            ) or (facility == "贸易站" and target_product in TRADE_PRODUCTS)
            if not supported:
                continue
            configured_rooms.add(room)

            existing = [
                task
                for task in self.tasks
                if task.type == TaskTypes.SWITCH_PRODUCT
                and task.meta_data.split(",", 1)[0] == room
            ]
            if room in pending_targets:
                # 关联换班或副表前置任务负责切换，不能被旧排班反向覆盖。
                obsolete_ids = {
                    id(task)
                    for task in existing
                    if not getattr(task, "pending_backup_product_switch", False)
                }
                self.tasks[:] = [
                    task for task in self.tasks if id(task) not in obsolete_ids
                ]
                continue
            state = facility_states.get(room)
            expected_facility = "manufacture" if facility == "制造站" else "trade"
            if not state or state.get("facility") != expected_facility:
                self.tasks[:] = [task for task in self.tasks if task not in existing]
                logger.debug(
                    f"{self.translate_room(room)}尚无设施状态缓存，暂不生成切换任务"
                )
                continue
            if state.get("product") == target_product:
                if existing:
                    self.tasks[:] = [
                        task for task in self.tasks if task not in existing
                    ]
                    logger.info(
                        f"{self.translate_room(room)}实际产物或订单已符合排班，"
                        "移除待切换任务"
                    )
                continue

            target_meta = product_task_meta(room, target_product)
            if len(existing) == 1 and existing[0].meta_data == target_meta:
                continue
            self.tasks[:] = [task for task in self.tasks if task not in existing]
            self.tasks.append(
                SchedulerTask(
                    task_type=TaskTypes.SWITCH_PRODUCT,
                    meta_data=target_meta,
                )
            )
            logger.info(
                f"生成{self.translate_room(room)}切换产物或订单的任务：{target_product}"
            )

        self.tasks[:] = [
            task
            for task in self.tasks
            if task.type != TaskTypes.SWITCH_PRODUCT
            or task.meta_data.split(",", 1)[0] in configured_rooms
        ]
        selected = getattr(self, "task", None)
        if (
            selected is not None
            and selected.type == TaskTypes.SWITCH_PRODUCT
            and selected not in self.tasks
        ):
            self.task = None

    def _products_after_arrangement(self, plan):
        """在排班快照上推演换班后的副表，不改动真实排班缓存。"""
        if self._initial_mood_read_pending():
            return self.op_data.products, self.op_data.plan
        projected = self.op_data.project_arrangements([plan])

        seen = {tuple(projected.plan_condition)}
        while projected.backup_plans:
            conditions = [
                bool(projected.evaluate_expression(str(bp.trigger)))
                for bp in projected.backup_plans
            ]
            if conditions == projected.plan_condition:
                break
            if tuple(conditions) in seen:
                logger.warning("换班前副表产物推演出现循环，维持当前目标")
                break
            seen.add(tuple(conditions))
            if error := projected.swap_plan(conditions):
                raise ValueError(f"换班前副表产物推演失败：{error}")
        return projected.products, projected.plan

    def _backup_explicit_slots(self, original, conditions):
        """Return concrete entry-task slots owned by newly activated backups."""
        return {
            (room, index)
            for active, enabled, bp in zip(
                original, conditions, self.op_data.backup_plans
            )
            if enabled and not active
            for room, names in (bp.task or {}).items()
            for index, name in enumerate(names)
            if name != "Current"
        }

    def _prepare_group_shift(self, task, *, remember_targets=False):
        """Revalidate queued shared slots without committing the pending shift."""
        for pending in self.tasks:
            if pending is not task and getattr(pending, "group_shift_expected", {}):
                raise ProductSwitchDeferred(
                    "等待未完成的绑组换班确认后再安排", minutes=1
                )
        self.op_data.commit_group_shifts({})
        transitions = dict(getattr(task, "group_shift_transitions", {}))
        transitions.update(self.op_data.arrangement_group_transitions(task.plan))
        proposed = copy.deepcopy(task.plan)
        reserved = {
            name
            for pending in self._deferred_product_locks(exclude=task)
            for name in pending.product_lock_names
        }
        if not self.op_data.normalize_shared_arrangement(
            proposed,
            transitions,
            reserved_replacements=reserved,
            explicit_slots=getattr(task, "backup_explicit_slots", ()),
        ):
            raise GroupShiftBlocked(self._shared_shift_blockers(task, transitions))
        task.plan = proposed
        task.group_shift_transitions = transitions
        if remember_targets and transitions:
            expected = getattr(task, "group_shift_expected", {})
            for room, names in proposed.items():
                for index, name in enumerate(names):
                    if name == "Current":
                        continue
                    expected.pop((room, index), None)
                    if name not in ("Free", ""):
                        expected = {
                            slot: occupant
                            for slot, occupant in expected.items()
                            if occupant != name
                        }
                        expected[room, index] = name
            task.group_shift_expected = expected

    def _shared_shift_blockers(self, task, transitions):
        """Identify confirmed resting dependencies without guessing return times."""
        groups = set()
        explicit = getattr(task, "backup_explicit_slots", ())
        for op in self.op_data.operators.values():
            if (
                not op.multi_group
                or (op.room, op.index) in explicit
                or not (
                    op.index < len(task.plan.get(op.room, []))
                    or any(b["group"] in transitions for b in op.group_bindings)
                )
            ):
                continue
            groups.update(
                group
                for group in self.op_data.resting_binding_groups(op, transitions)
                if self.op_data.group_is_resting(group)
            )
        return groups

    def _suspend_group_shift(self, task, groups):
        task.group_shift_waiting = set(groups)
        waiting = getattr(self, "waiting_group_shifts", [])
        if all(pending is not task for pending in waiting):
            waiting.append(task)
        self.waiting_group_shifts = waiting
        self.tasks[:] = [pending for pending in self.tasks if pending is not task]
        self._refresh_deferred_product_reservations()
        self.op_data.correct_dorm()

    def _resume_waiting_group_shifts(self):
        """Cached state changes release suspended work; no timer dispatch is used."""
        if not getattr(self, "waiting_group_shifts", ()):
            return
        if self._initial_mood_read_pending() or self._emergency_frozen():
            return
        for task in list(getattr(self, "waiting_group_shifts", ())):
            if any(
                self.op_data.group_is_resting(group)
                for group in task.group_shift_waiting
            ):
                continue
            transitions = dict(getattr(task, "group_shift_transitions", {}))
            transitions.update(self.op_data.arrangement_group_transitions(task.plan))
            proposed = copy.deepcopy(task.plan)
            if not self.op_data.normalize_shared_arrangement(
                proposed,
                transitions,
                explicit_slots=getattr(task, "backup_explicit_slots", ()),
            ):
                continue
            task.plan = proposed
            task.time = datetime.now()
            del task.group_shift_waiting
            self.waiting_group_shifts[:] = [
                pending for pending in self.waiting_group_shifts if pending is not task
            ]
            self.tasks.append(task)
            self._refresh_deferred_product_reservations()
            logger.info("多绑组互斥已解除，恢复换班：%s", task.plan)

    def _complete_group_shift(self, task):
        """Confirm required targets; mastery-owned slots retain their protection."""
        if not hasattr(task, "group_shift_transitions"):
            return True
        expected_plan = {}
        for (room, index), name in getattr(task, "group_shift_expected", {}).items():
            expected_plan.setdefault(room, ["Current"] * len(self.op_data.plan[room]))[
                index
            ] = name
        original_transitions = self.op_data.arrangement_group_transitions(expected_plan)
        # The execution gate may legitimately skip training slots. Reuse its
        # scheduling protection instead of recreating those slots every minute.
        self._suppress_train_correction(expected_plan)
        remaining_transitions = self.op_data.arrangement_group_transitions(
            expected_plan
        )
        for group in original_transitions.keys() - remaining_transitions.keys():
            # A task containing only protected anchors confirms no group change.
            task.group_shift_transitions.pop(group, None)
        for group, resting in remaining_transitions.items():
            if resting != original_transitions[group]:
                task.group_shift_transitions[group] = resting
        task.group_shift_expected = {
            (room, index): name
            for room, names in expected_plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        }
        missing = {}
        for (room, index), name in getattr(task, "group_shift_expected", {}).items():
            actual = self.op_data.get_current_operator(room, index)
            if actual is None or actual.name != name:
                missing.setdefault(room, ["Current"] * len(self.op_data.plan[room]))[
                    index
                ] = name
        if missing:
            task.plan = missing
            task.time = datetime.now() + timedelta(minutes=1)
            return False
        transitions = getattr(task, "group_shift_transitions", {})
        changes = {
            group: "下班" if resting else "上班"
            for group, resting in transitions.items()
            if self.op_data.group_is_resting(group) != resting
        }
        self.op_data.commit_group_shifts(transitions)
        if changes:
            logger.info("绑组换班确认完成：%s", changes)
        task.group_shift_expected = {}
        self._resume_waiting_group_shifts()
        return True

    def _prepare_shift_cycle(self, task):
        """在副本中收敛换班、副表、后续轮休和补床，成功后一次提交最终安排。"""
        if getattr(self, "maintenance_entry_pending", False):
            blocked_orders = blocked_run_order_ids(self.tasks, self.op_data)
            pending = [
                queued
                for queued in self.tasks
                if getattr(queued, "maintenance_advance_before_backup", False)
            ]
            if not pending or any(
                id(queued) not in blocked_orders for queued in pending
            ):
                raise ProductSwitchDeferred(
                    "等待停服前提前跑单及原班恢复完成后再换班", minutes=1
                )
            self.maintenance_entry_pending = False
        if (self._initial_mood_read_pending()) or getattr(
            task, "backup_shift_active", False
        ):
            return
        # 肥鸭、延期切产物和临近关键任务仍由原有调度边界处理。
        probe = SchedulerTask(task_type=TaskTypes.FILL_DORM)
        simplify_dorm_fill(probe, self.tasks, op_data=self.op_data)
        if (
            getattr(probe, "simple_dorm_fill", False)
            or any(
                t.type == TaskTypes.FIAMMETTA
                and t.time <= datetime.now()
                or getattr(t, "backup_shift_active", False)
                or getattr(t, "product_shift_locked", False)
                for t in self.tasks
                if t is not task
            )
            or getattr(task, "product_shift_locked", False)
        ):
            self._prepare_shift_backup(task)
            reserved_names, reserved_slots = dorm_task_reservations(
                self.op_data,
                [
                    pending
                    for pending in self.tasks
                    if pending is not task and pending.type != TaskTypes.SHIFT_ON
                ],
            )
            task.plan = prioritize_new_dorm_recovery(
                self.op_data,
                task.plan,
                reserved_slots,
                reserved_names=reserved_names,
            )
            task.plan = plan_dorm_isolation(self.op_data, task.plan, reserved_slots)
            return
        intent = copy.deepcopy(getattr(task, "backup_shift_intent", task.plan))
        explicit_slots = set(getattr(task, "backup_explicit_slots", ()))
        ordinary = {
            TaskTypes.SHIFT_ON,
            TaskTypes.SHIFT_OFF,
            TaskTypes.EXHAUST_OFF,
            TaskTypes.SELF_CORRECTION,
            TaskTypes.RE_ORDER,
            TaskTypes.FILL_DORM,
        }
        coalesced = [
            t
            for t in self.tasks
            if t is not task
            and t.type in ordinary
            and t.plan
            and t.time <= datetime.now()
            and not getattr(t, "strict_mood_limit", False)
            and not getattr(t, "dorm_recovery_restore", [])
        ]
        consumed = set()
        for queued in sorted(coalesced, key=lambda t: t.time):
            # 未执行的普通补床重新计算，不能作为轮休前必须保留的入住意图。
            if queued.type != TaskTypes.FILL_DORM:
                combined = copy.deepcopy(intent)
                _merge_shift_transition(
                    combined,
                    getattr(queued, "backup_shift_intent", queued.plan),
                    self.op_data,
                )
                explicit = self._plan_for_slots(intent, explicit_slots)
                _merge_shift_transition(
                    explicit,
                    self._plan_for_slots(
                        queued.plan, getattr(queued, "backup_explicit_slots", ())
                    ),
                    self.op_data,
                )
                _merge_shift_transition(combined, explicit, self.op_data)
                combined_explicit = explicit_slots | set(
                    getattr(queued, "backup_explicit_slots", ())
                )
                if not self.op_data.normalize_shared_arrangement(
                    combined, explicit_slots=combined_explicit
                ):
                    continue
                intent = combined
                explicit_slots = combined_explicit
            consumed.add(id(queued))
        simulation = copy.copy(self)
        # 求值模型只读复用；eval 注入的 Python 内建对象不能全部深拷贝。
        simulation.op_data = copy.deepcopy(
            self.op_data, {id(self.op_data.eval_model): self.op_data.eval_model}
        )
        simulation.op_data.commit_group_shifts(
            getattr(task, "group_shift_transitions", {})
        )
        pending = [t for t in self.tasks if t is not task and id(t) not in consumed]
        step = SchedulerTask(task_type=task.type, task_plan=copy.deepcopy(intent))
        step.backup_explicit_slots = explicit_slots
        step.dorm_fill_plan = copy.deepcopy(getattr(task, "dorm_fill_plan", {}))
        returning = {
            name
            for group, resting in getattr(task, "group_shift_transitions", {}).items()
            if not resting
            for name in simulation.op_data.shift_group_members(group)
        }
        seen = set()
        # Free 是执行时按游戏列表选人的占位符，预演不能把它当作已知干员。
        unresolved = set()
        ordinary_unknown = set()
        for _ in range(64):
            simulation.tasks = copy.deepcopy(pending)
            simulation.task = step
            simulation._prepare_shift_backup(step)
            explicit_slots = set(getattr(step, "backup_explicit_slots", ()))
            conditions = getattr(
                step, "backup_shift_conditions", simulation.op_data.plan_condition
            )
            if error := simulation.op_data.swap_plan(conditions, refresh=True):
                raise ValueError(f"完整换班预演失败：{error}")
            reserved_names, reserved_slots = dorm_task_reservations(
                simulation.op_data,
                [
                    pending
                    for pending in simulation.tasks
                    if pending.type != TaskTypes.SHIFT_ON
                ],
            )
            step.plan = prioritize_new_dorm_recovery(
                simulation.op_data,
                step.plan,
                reserved_slots,
                reserved_names=reserved_names,
            )
            step.plan = plan_dorm_isolation(
                simulation.op_data, step.plan, reserved_slots
            )
            returning.update(
                name
                for name in _assigned_operator_names(step.plan)
                if name in simulation.op_data.operators
                and not simulation.op_data.operators[name].is_working()
            )
            previous_positions = {
                name: (op.current_room, op.current_index)
                for name, op in simulation.op_data.operators.items()
            }
            simulation.op_data = simulation.op_data.project_arrangements([step.plan])
            for room, names in step.plan.items():
                for index, name in enumerate(names):
                    if name in previous_positions:
                        simulation._record_dorm_admission(
                            name, room, index, previous_positions[name]
                        )
            for room, names in step.plan.items():
                fill_row = step.dorm_fill_plan.get(room, [])
                for index, name in enumerate(names):
                    if name == "Free":
                        unresolved.add((room, index))
                        if index < len(fill_row) and fill_row[index] == "Free":
                            ordinary_unknown.add((room, index))
                        else:
                            ordinary_unknown.discard((room, index))
                    elif name != "Current":
                        unresolved.discard((room, index))
                        ordinary_unknown.discard((room, index))
            state = (
                tuple(conditions),
                tuple(sorted(unresolved)),
                tuple(
                    (name, op.current_room, op.current_index)
                    for name, op in simulation.op_data.operators.items()
                ),
            )
            if state in seen:
                raise ValueError("完整换班预演出现循环，保留原任务，暂不执行换人")
            seen.add(state)
            simulation.total_agent = [
                op
                for op in simulation.op_data.operators.values()
                if op.is_high() and not op.room.startswith("dorm")
            ]
            rest = simulation.resting(returning=returning)
            _merge_dorm_arrangement(rest, try_reorder(simulation.op_data, rest) or {})
            ordinary_fill = {}
            if not rest:
                # 副表可能改变刚选中的替班合法性；缓存纠错也在预演中完成。
                rest = (
                    simulation.agent_get_mood(
                        read_rooms=False,
                        return_plan=True,
                        explicit_slots=explicit_slots,
                    )
                    or {}
                )
                for room, names in rest.items():
                    for index, name in enumerate(names):
                        current = simulation.op_data.get_current_operator(room, index)
                        if current is not None and current.name == name:
                            names[index] = "Current"
                rest = {
                    room: names
                    for room, names in rest.items()
                    if any(name != "Current" for name in names)
                }
            if not rest:
                # 所有可下班组已安排后才补最终空床；补床触发的副表继续参与收敛。
                simulation.tasks = copy.deepcopy(pending)
                count = len(simulation.tasks)
                try_add_release_dorm(
                    {}, None, simulation.op_data, simulation.tasks, empty_only=True
                )
                for fill in simulation.tasks[count:]:
                    _merge_shift_transition(rest, fill.plan, simulation.op_data)
                    _merge_dorm_arrangement(ordinary_fill, fill.plan)
            # 不重复预演无法缓存的游戏选人，留给最终换人时一次读取。
            for room, names in rest.items():
                for index, name in enumerate(names):
                    if name == "Free" and (room, index) in unresolved:
                        names[index] = "Current"
            rest = {
                room: names
                for room, names in rest.items()
                if any(name != "Current" for name in names)
            }
            if rest:
                step = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=rest)
                step.backup_explicit_slots = explicit_slots
                step.dorm_fill_plan = ordinary_fill
                continue
            final = {}
            for room, slots in simulation.op_data.plan.items():
                for index in range(len(slots)):
                    old = self.op_data.get_current_operator(room, index)
                    new = simulation.op_data.get_current_operator(room, index)
                    old_name = old.name if old else ""
                    new_name = new.name if new else ""
                    if old_name != new_name or (room, index) in unresolved:
                        final.setdefault(room, ["Current"] * len(slots))[index] = (
                            new_name or "Free"
                        )
            task.group_shift_transitions = {
                group: resting
                for group, resting in simulation.op_data.group_shift_state.items()
                if self.op_data.group_is_resting(group) != resting
            }
            task.backup_shift_intent = intent
            task.backup_explicit_slots = explicit_slots
            task.backup_shift_conditions = list(conditions)
            task.plan = final
            task.dorm_fill_plan = {
                room: [
                    name
                    if name in simulation.op_data.operators
                    and simulation.op_data.operators[name].temporary_dorm_fill
                    or (room, index) in ordinary_unknown
                    else "Current"
                    for index, name in enumerate(names)
                ]
                for room, names in final.items()
                if room.startswith("dorm")
            }
            self.tasks[:] = [t for t in self.tasks if id(t) not in consumed]
            # 满心情兜底入住标记跟随最终名单，不提交预演中的其他状态。
            for room, names in final.items():
                if room.startswith("dorm"):
                    for name in names:
                        if name in self.op_data.operators:
                            self.op_data.operators[
                                name
                            ].dorm_mood_fallback = simulation.op_data.operators[
                                name
                            ].dorm_mood_fallback
            logger.info("完整换班收敛：副表 %s，最终安排 %s", conditions, final)
            return
        raise ValueError("完整换班预演未收敛，保留原任务，暂不执行换人")

    def _prepare_shift_backup(self, task):
        """从原换班意图推演副表及其动作，只改待执行任务，不伪造实际驻员。"""
        if (
            (self._initial_mood_read_pending())
            or task.type
            not in (
                TaskTypes.SHIFT_ON,
                TaskTypes.SHIFT_OFF,
                TaskTypes.EXHAUST_OFF,
                TaskTypes.SELF_CORRECTION,
                TaskTypes.RE_ORDER,
            )
            or not getattr(self.op_data, "backup_plans", [])
            or getattr(task, "backup_shift_active", False)
        ):
            return
        if any(
            t.type == TaskTypes.FIAMMETTA and t.time <= datetime.now()
            for t in self.tasks
        ):
            if hasattr(task, "backup_shift_conditions"):
                raise ProductSwitchDeferred(
                    "等待肥鸭任务完成后再执行最终换班", minutes=1
                )
            return
        active = [
            t
            for t in self.tasks
            if t is not task and getattr(t, "backup_shift_active", False)
        ]
        if active:
            retry = max(t.time for t in active) + timedelta(seconds=1)
            raise ProductSwitchDeferred(
                "等待上一轮最终换班完成后再推演",
                minutes=max(1, (retry - datetime.now()).total_seconds() / 60),
            )
        intent = copy.deepcopy(getattr(task, "backup_shift_intent", task.plan))
        original = list(self.op_data.plan_condition)
        seed = self.op_data.project_arrangements([intent])
        seed.commit_group_shifts(getattr(task, "group_shift_transitions", {}))
        conditions = [
            bool(seed.evaluate_expression(str(bp.trigger))) for bp in seed.backup_plans
        ]
        seen = set()
        for _ in range(64):
            key = tuple(conditions)
            if key in seen:
                raise ValueError("上下班副表推演出现循环，保留原任务，暂不执行换人")
            seen.add(key)
            simulation = copy.copy(self)
            simulation.op_data = seed.project_arrangements([])
            if error := simulation.op_data.swap_plan(conditions, refresh=True):
                raise ValueError(f"上下班副表推演失败：{error}")
            transition = simulation._backup_transition_plan(
                self.op_data.plan,
                original,
                conditions,
                copy.deepcopy(seed.all_dorms()),
                dorm_rebalance_signature(seed),
            )
            if transition is None:
                raise ProductSwitchDeferred(
                    "副表替班暂不可用，保留原换班安排", minutes=1
                )
            merged = copy.deepcopy(intent)
            _merge_shift_transition(merged, transition, simulation.op_data)
            # 从真实驻员重新投影，不能把上一轮的中间换人累积到下一轮。
            projected = self.op_data.project_arrangements([])
            if error := projected.swap_plan(conditions, refresh=True):
                raise ValueError(f"上下班副表推演失败：{error}")
            projected = projected.project_arrangements([merged])
            next_conditions = [
                bool(projected.evaluate_expression(str(bp.trigger)))
                for bp in projected.backup_plans
            ]
            if next_conditions == conditions:
                task.backup_explicit_slots = set(
                    getattr(task, "backup_explicit_slots", ())
                ) | self._backup_explicit_slots(original, conditions)
                if conditions == original and merged == intent:
                    task.plan = intent
                    for attr in ("backup_shift_intent", "backup_shift_conditions"):
                        if hasattr(task, attr):
                            delattr(task, attr)
                    if getattr(task, "product_shift_locked", False):
                        slots = {
                            (room, index)
                            for room, names in task.plan.items()
                            for index, name in enumerate(names)
                            if name != "Current"
                        }
                        self._reserve_deferred_product_shift(task, slots)
                        self._refresh_deferred_product_reservations()
                    return
                task.backup_shift_intent = intent
                task.backup_shift_conditions = conditions
                task.plan = {
                    room: names
                    for room, names in merged.items()
                    if any(name != "Current" for name in names)
                }
                if getattr(task, "product_shift_locked", False):
                    self._reserve_deferred_product_shift(task, set())
                    self._refresh_deferred_product_reservations()
                logger.info(
                    "上下班副表预演收敛：%s -> %s，最终安排：%s",
                    original,
                    conditions,
                    task.plan,
                )
                return
            conditions = next_conditions
        raise ValueError("上下班副表推演未收敛，保留原任务，暂不执行换人")

    def _activate_shift_backup(self, task):
        """前置操作成功后启用最终排班配置；实际位置仍由逐房读屏更新。"""
        if self._initial_mood_read_pending():
            return
        conditions = getattr(task, "backup_shift_conditions", None)
        if conditions is None or (
            getattr(task, "backup_shift_active", False)
            and self.op_data.plan_condition == conditions
        ):
            return
        if self._advance_orders_before_maintenance(conditions):
            raise ProductSwitchDeferred(
                "等待停服前提前跑单及原班恢复完成后再换班", minutes=1
            )
        previous = list(self.op_data.plan_condition)
        previous_exhaust = self._exhaust_task_signatures()
        if error := self.op_data.swap_plan(conditions, refresh=True):
            self.op_data.swap_plan(previous, refresh=True)
            raise ValueError(f"上下班最终排班生效失败：{error}")
        task.backup_shift_active = True
        if previous != conditions and self._invalidate_changed_exhaust_tasks(
            previous_exhaust
        ):
            # 重排任务完成后仍需按实读驻员重新计算用尽时间。
            self.tasks.append(SchedulerTask())
        self._sync_run_order_tasks()

    @staticmethod
    def _plan_for_slots(plan, slots):
        return {
            room: [
                name if (room, index) in slots else "Current"
                for index, name in enumerate(names)
            ]
            for room, names in plan.items()
            if any((room, index) in slots for index in range(len(names)))
        }

    def _product_dependent_slots(self, plan, rooms, baseline, projected):
        """用单人变动及撤销单人变动的反事实找出触发副表的槽位。"""
        changed = {
            (room, index)
            for room, names in plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        }
        occupants = {
            (op.current_room, op.current_index): op.name
            for op in self.op_data.operators.values()
        }
        involved = {}
        for room, index in changed:
            name = plan[room][index]
            for operator in (name, occupants.get((room, index))):
                if operator in self.op_data.operators:
                    involved.setdefault(operator, set()).add((room, index))
        held = set()
        for operator, slots in involved.items():
            only, _ = self._products_after_arrangement(
                self._plan_for_slots(plan, slots)
            )
            without, _ = self._products_after_arrangement(
                self._plan_for_slots(plan, changed - slots)
            )
            if any(
                only.get(room) != baseline.get(room)
                or without.get(room) != projected.get(room)
                for room in rooms
            ):
                held.update(slots)
                logger.debug("%s的排班动作影响副表产物", operator)
        return held or changed

    def _reserve_deferred_product_shift(self, task, slots):
        changed = {
            (room, index)
            for room, names in task.plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        }
        if not changed:
            return
        if hasattr(task, "backup_shift_conditions"):
            # 收敛后的上下班是一个整体，不能拆出会让副表条件改变的中间态。
            slots = changed
        if slots != changed:
            independent = self._plan_for_slots(task.plan, changed - slots)
            self.tasks.append(
                SchedulerTask(
                    task_plan=independent,
                    task_type=task.type,
                    meta_data=task.meta_data,
                )
            )
            task.plan = self._plan_for_slots(task.plan, slots)
            logger.info("副表依赖的换班槽位延期，其余槽位继续：%s", independent)
        task.product_shift_locked = True
        task.product_lock_slots = slots
        task.product_lock_names = {
            name
            for room, names in task.plan.items()
            for name in names
            if name in self.op_data.operators
        }
        for room, index in slots:
            if room.startswith("dormitory_"):
                continue
            current = self.op_data.get_current_operator(room, index)
            if current is not None:
                task.product_lock_names.add(current.name)

    def _deferred_product_locks(self, exclude=None):
        return [
            task
            for task in self.tasks
            if task is not exclude and getattr(task, "product_shift_locked", False)
        ]

    def _refresh_deferred_product_reservations(self):
        locks = self._deferred_product_locks()
        self.op_data.reserved_product_beds = {
            (room, index): names[index]
            for task in locks
            for room, names in task.plan.items()
            if room.startswith("dormitory_")
            for index, name in enumerate(names)
            if name in self.op_data.operators
        }
        self.op_data.reserved_product_replacements = (
            set().union(*(task.product_lock_names for task in locks))
            if locks
            else set()
        )

    def _defer_conflicting_product_shift_slots(self, task):
        locks = self._deferred_product_locks(exclude=task)
        if not locks:
            return
        reserved_slots = set().union(*(lock.product_lock_slots for lock in locks))
        reserved_names = set().union(*(lock.product_lock_names for lock in locks))
        conflicting = {
            (room, index)
            for room, names in task.plan.items()
            for index, name in enumerate(names)
            if name != "Current"
            and (
                (room, index) in reserved_slots
                or name in reserved_names
                or (current := self.op_data.get_current_operator(room, index))
                is not None
                and current.name in reserved_names
            )
        }
        if not conflicting:
            return
        changed = {
            (room, index)
            for room, names in task.plan.items()
            for index, name in enumerate(names)
            if name != "Current"
        }
        retry = max(lock.time for lock in locks) + timedelta(seconds=1)
        # 绑组换班保留完整安排和确认责任，不能只执行共享岗位就提交整组状态。
        if (
            changed - conflicting
            and not hasattr(task, "backup_shift_conditions")
            and not getattr(task, "group_shift_transitions", {})
            and not getattr(task, "group_shift_expected", {})
        ):
            blocked = SchedulerTask(
                time=retry,
                task_plan=self._plan_for_slots(task.plan, conflicting),
                task_type=task.type,
                meta_data=task.meta_data,
            )
            self.tasks.append(blocked)
            task.plan = self._plan_for_slots(task.plan, changed - conflicting)
            logger.info("与延期换班共享床位或替班的槽位延后：%s", blocked.plan)
            return
        delay = max(1, (retry - datetime.now()).total_seconds() / 60)
        raise ProductSwitchDeferred("床位或替班已为切产物后的换班预留", minutes=delay)

    def _switch_products_before_arrangement(self, task):
        """把将由本次换班触发的切产物作为换班的前置操作。"""
        if not self._product_switching_enabled():
            self._discard_product_switches()
            return
        if not getattr(self.op_data, "products", None) and not any(
            getattr(plan, "products", None)
            for plan in getattr(self.op_data, "backup_plans", [])
        ):
            return
        baseline = self.op_data.products
        baseline, _ = self._products_after_arrangement({})
        products, projected_plan = self._products_after_arrangement(task.plan)
        targets = {}
        switches = []
        for room, target in products.items():
            if target == baseline.get(room):
                continue
            room_plan = projected_plan.get(room) or []
            if not room_plan:
                continue
            facility = room_plan[0].facility
            valid = (facility == "制造站" and target in MANUFACTURE_PRODUCTS) or (
                facility == "贸易站" and target in TRADE_PRODUCTS
            )
            if not valid:
                continue
            actual = self.op_data.facility_states.get(room, {}).get("product")
            if actual == target or (
                actual is None and target == self.op_data.products.get(room)
            ):
                continue
            targets[room] = target
            switches.append(
                SchedulerTask(
                    task_type=TaskTypes.SWITCH_PRODUCT,
                    meta_data=product_task_meta(room, target),
                )
            )
        if not switches:
            return
        task.pending_product_targets = targets
        logger.info("换班前先切换产物或订单：%s", targets)
        try:
            self.switch_base_products(switches, before_arrangement=True)
        except ProductSwitchDeferred:
            slots = self._product_dependent_slots(
                task.plan, targets, baseline, products
            )
            self._reserve_deferred_product_shift(task, slots)
            self._refresh_deferred_product_reservations()
            raise
        unfinished = {
            room: target
            for room, target in targets.items()
            if self.op_data.facility_states.get(room, {}).get("product") != target
        }
        if unfinished:
            raise ProductSwitchDeferred(f"换班前切换未完成：{unfinished}", minutes=5)
        task.product_switched_before_arrangement = True

    def _refresh_orders_after_product_switch(self):
        """产物和驻员均已变化，废弃旧订单倒计时并重新从游戏读取。"""
        rooms = set(self.op_data.run_order_rooms)
        if not rooms:
            return
        self.tasks[:] = [
            task
            for task in self.tasks
            if not (
                task.type in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
                and task.meta_data in rooms
                and not getattr(task, "run_order_restore_pending", False)
            )
        ]
        for room in rooms:
            self.tasks.append(
                SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data=room)
            )
        logger.info("切产物并换班后重新读取订单倒计时：%s", sorted(rooms))

    def check_fia(self):
        if self._emergency_frozen():
            state = self.emergency_state
            targets = state.get("fia_targets", [])
            if not targets:
                return None, None
            fia = self.op_data.operators.get("菲亚梅塔")
            for room, row in state.get("dorm_layout", {}).items():
                if "菲亚梅塔" in row:
                    index = row.index("菲亚梅塔")
                    if (
                        fia is not None
                        and self.op_data.plan[room][index].agent == "菲亚梅塔"
                        and (fia.current_room, fia.current_index) == (room, index)
                    ):
                        return targets, room
            return None, None
        if "菲亚梅塔" in self.op_data.operators.keys() and self.op_data.operators[
            "菲亚梅塔"
        ].room.startswith("dormitory"):
            return self.op_data.operators[
                "菲亚梅塔"
            ].replacement, self.op_data.operators["菲亚梅塔"].room
        return None, None

    def _run_order_time_region(self):
        """#85：跑单剩余时间的双端坐标（三处调用点曾各自复制，UI 调整只改这里）。"""
        return (
            (int(self.recog.w * 650 / 2496), int(self.recog.h * 660 / 1404)),
            (int(self.recog.w * 815 / 2496), int(self.recog.h * 710 / 1404)),
        )

    @timed_step("order_navigation")
    def _wait_drone_interface(
        self, interval=0.2, accelerate_template=None, page_template=None
    ):
        """#85：等待进入订单或制造详情界面。

        ``accelerate_template`` 用于贸易站专属流程；未指定时制造站/贸易站任一
        加速按钮都视为成功。``page_template`` 用于没有加速按钮的空订单页面，
        且仅在已点击页面入口后才接受，避免把设施信息遮罩后的背景误判为成功。
        """
        templates = (
            (accelerate_template,)
            if accelerate_template is not None
            else ("manufacture_accelerate", "bill_accelerate")
        )
        pending = None
        retry_ready = False
        for _ in range(10):
            if self.find("connecting"):
                retry_ready = False
                self.sleep()
                continue
            if any(self.find(template) is not None for template in templates):
                return
            close = self.find("arrange_check_in_on")
            action = "close_detail" if close is not None else "open_order"
            if (
                page_template is not None
                and pending == "open_order"
                and self.find(page_template) is not None
            ):
                return
            if pending == action and not retry_ready:
                # 等上次点击的反馈；旧面板仍在时先换帧，不连续戳同一入口。
                retry_ready = True
                self.sleep(0.2)
                continue
            self.tap(
                close
                if close is not None
                else (self.recog.w * 0.05, self.recog.h * 0.95),
                interval=interval,
            )
            pending, retry_ready = action, False
        # 最后一次点击之后也要读到结果，再交回原有房间恢复流程。
        ready = any(self.find(template) is not None for template in templates)
        if page_template is not None and pending == "open_order":
            ready = ready or self.find(page_template) is not None
        if self.find("connecting") or not ready:
            raise RecognizeError("未成功进入订单或制造详情界面")

    def get_run_order_time(self, room):
        logger.info("基建：读取插拔时间")
        # 点击进入该房间
        self.enter_room(room)
        # 进入房间详情
        self._wait_drone_interface(interval=1, accelerate_template="bill_accelerate")
        self._cache_facility_state_from_current_page(room, "trade")
        execute_time = self.double_read_time(
            self._run_order_time_region(),
            use_digit_reader=True,
        )
        execute_time = execute_time - timedelta(
            seconds=(60 * config.conf.run_order_delay)
        )
        logger.info("下一次进行插拔的时间为：" + execute_time.strftime("%H:%M:%S"))
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        return execute_time

    def todo_list(self) -> None:
        """处理基建 Todo 列表"""
        tapped = False
        collect = {
            "bill": "订单",
            "factory": "制造站产物",
            "trust": "信赖",
            "recycle": "回收站产物",
        }
        if self.last_execution["todo"] is None or self.last_execution[
            "todo"
        ] <= datetime.now() - timedelta(minutes=15):
            for res, name in collect.items():
                if pos := self.find(f"infra_collect_{res}"):
                    logger.info(f"收取{name}")
                    self.tap(pos)
                    tapped = True
            self.last_execution["todo"] = datetime.now()
        if not tapped:
            # 点击右上角的通知图标
            # 可能被产物收取提示挡住，所以直接点位置
            self.tap((1840, 140))
            self.todo_task = True

    def _run_clue_flow(self):
        """跑一次完整会客室流程。

        定时趴体（线索交流结束后触发）和手动「线索任务」共用这一条路径。
        先清掉缓存的线索交流结束时间，让 clue_new() 从界面上重新读取；跑完
        刷新 last_clue，把下一次定时触发顺延一小时。
        """
        self.party_time = None
        self.clue_new()
        self.last_clue = datetime.now()
        self.skip(["collect_notification"])

    def _run_clue_shop(self):
        conf = config.conf
        if getattr(
            conf,
            "should_run_mower_mall",
            getattr(conf, "maa_mall_enable", True)
            and getattr(conf, "maa_mall_mode", "maa") == "mower",
        ):
            shop_solver = CreditShop(self.device, self.recog)
            shop_solver.run()
            self.scene_graph_navigation(Scene.INFRA_MAIN)

    def clue_new(self):
        try:
            logger.info("基建：线索")
            self.scene_graph_navigation(Scene.INFRA_MAIN)
            self.enter_room("meeting")

            clue_size = (162, 216)
            clue_top_left = {
                "daily": (1118, 334),
                "receive": (1305, 122),
                "give_away": (30, 208),
                # 摆放线索界面，线索框的左上角
                1: (72, 228),
                2: (374, 334),
                3: (679, 198),
                4: (1003, 265),
                5: (495, 660),
                6: (805, 573),
                7: (154, 608),
            }
            dot_offset = (168, -8)
            main_offset = (425, 0)
            main_time_offset = (443, 257)

            def va(a, b):
                return a[0] + b[0], a[1] + b[1]

            def tl2p(top_left):
                return top_left, va(top_left, clue_size)

            def is_orange(dot):
                orange_dot = (255, 104, 1)
                return all([abs(dot[i] - orange_dot[i]) < 3 for i in range(3)])

            clue_scope = {}
            for index, top_left in clue_top_left.items():
                clue_scope[index] = tl2p(top_left)
            clue_dots = {}
            main_dots = {}
            main_time = {}
            main_scope = {}
            for i in range(1, 8):
                clue_dots[i] = va(clue_top_left[i], dot_offset)
                main_dots[i] = va(clue_dots[i], main_offset)
                main_time[i] = va(clue_top_left[i], main_time_offset)
                main_scope[i] = tl2p(va(clue_top_left[i], main_offset))

            class ClueTaskManager:
                def __init__(self):
                    # 操作顺序：信息板信用、领取每日线索、接收好友线索、摆线索、送线索、更新线索交流结束时间
                    self.task_list = [
                        "message_board",
                        "daily",
                        "receive",
                        "place",
                        "give_away",
                        "party_time",
                    ]
                    self.task = self.task_list[0]

                def complete(self, task):
                    task = task or self.task
                    if task in self.task_list:
                        self.task_list.remove(task)
                    self.task = self.task_list[0] if self.task_list else None

            tm_thres = 0.6

            def clue_cls(scope):
                scope_dict = clue_scope if isinstance(scope, str) else main_scope
                img = cropimg(self.recog.img, scope_dict[scope])
                for i in range(1, 8):
                    res = loadres(f"clue/{i}")
                    result = cv2.matchTemplate(img, res, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                    if max_val > tm_thres:
                        return i
                return None

            exit_pos = (1239, 144)

            ctm = ClueTaskManager()

            clue_status = {}

            def place_index():
                for cl, st in clue_status.items():
                    if st in ["available", "self", "available_self_only"]:
                        return cl, st
                return None, None

            def detect_unlock():
                unlock_pos = self.find("clue/button_unlock")
                if unlock_pos is None:
                    return None
                color = self.get_color(self.get_pos(unlock_pos))
                if all(color > [252] * 3):
                    return unlock_pos
                return None

            while ctm.task:
                scene = self.scene()

                if scene == Scene.INFRA_DETAILS:
                    logger.info("INFRA_DETAILS")
                    if ctm.task == "message_board":
                        self.wait_product_complete()

                        # 左下角 (680, 1000) 在这个界面上有两处用途：一是信息板入口
                        # 没露出来时按它唤出入口，二是关掉领取信用后的确认页
                        bottom_left = (680, 1000)

                        # 线索交流提示占住右上角一小块，会挡住会客室界面，先点掉
                        if self.find("clue/title_party"):
                            self.tap_element("clue/title_party")

                        # 提示关掉后入口可能已经露出来了，先匹配一次。
                        # tap_element 不会重新抓帧，这里得先取一帧再匹配，否则
                        # 找的还是关提示之前那张图
                        self.recog.update()
                        board_pos = self.find("clue/message_board")

                        if board_pos is None:
                            # 入口没露出来：按左下角把它唤出，再匹配几次等动画走完
                            self.tap(bottom_left)
                            for _ in range(3):
                                self.recog.update()
                                board_pos = self.find("clue/message_board")
                                if board_pos:
                                    break
                                self.sleep(0.5)

                        if board_pos:
                            logger.info("打开会客室信息板")
                            self.tap(board_pos)

                            # 用信息板页面自己的场景判断有没有进去，好处是日志里
                            # 会留下一条 get_scene: Scene 229。不能用 room/meeting：
                            # 它匹配的是会客室顶栏，信息板页面上同样可见，会在刚
                            # 进入时就把人退出来
                            opened = False
                            for _ in range(6):
                                self.sleep(0.5)
                                self.recog.update()
                                if self.scene() == Scene.CLUE_MESSAGE_BOARD:
                                    opened = True
                                    break

                            if opened:
                                if collect := self.find("clue/message_board_collect"):
                                    logger.info("领取信息板信用")
                                    self.tap(collect)
                                    for _ in range(6):
                                        self.sleep(0.5)
                                        self.recog.update()
                                        if not self.find("clue/message_board_collect"):
                                            # 领取后弹「领取物资」确认页，点任意位置关掉
                                            self.tap(bottom_left)
                                            break

                                self.back()
                                # 等淡出结束、确实回到房间详情页再往下走，否则后续的
                                # tap((330, 1000)) 会打在还在淡出的信息板上
                                for _ in range(4):
                                    self.recog.update()
                                    if self.scene() == Scene.INFRA_DETAILS:
                                        break
                                    self.sleep(0.5)
                            else:
                                # 没进去就不按返回：可能只是板子还没淡入完，下一轮循环
                                # 识别到 Scene.CLUE_MESSAGE_BOARD 时会把它退掉
                                logger.info("信息板未打开，跳过")
                        else:
                            logger.info("未找到信息板入口，跳过")
                        ctm.complete("message_board")
                    elif ctm.task == "party_time":
                        self.wait_product_complete()
                        if pos := self.find("clue/check_party"):
                            logger.info("tap")
                            self.tap(pos)
                        party_time = self.read_party_time()
                        if party_time is not None and party_time > datetime.now():
                            self.set_detected_party_time(party_time)
                            logger.info(f"线索交流结束时间：{self.party_time}")
                            if not find_next_task(
                                self.tasks,
                                task_type=TaskTypes.CLUE_PARTY,
                            ):
                                self.tasks.append(
                                    SchedulerTask(
                                        time=self.party_time
                                        - timedelta(milliseconds=1),
                                        task_type=TaskTypes.CLUE_PARTY,
                                    )
                                )
                        else:
                            self.set_detected_party_time(None)
                            logger.info("线索交流未开启或已结束")
                        # party_time 是副表表达式可引用的状态。界面确认状态后立即
                        # 重算，不能等下一轮调度，否则跃跃等会客室副表不会及时触发。
                        self.backup_plan_solver()
                        ctm.complete("party_time")
                    else:
                        # 点击左下角，关闭进驻信息，进入线索界面
                        self.tap((330, 1000))

                elif scene == Scene.CLUE_MESSAGE_BOARD:
                    # 停在信息板页面上：退回房间详情，后面的任务都在那里继续。
                    # 兜底用——message_board 分支正常会自己退出来，这里接住
                    # 淡出中途被识别成信息板、或者上一次没退干净的情况
                    logger.info("CLUE_MESSAGE_BOARD")
                    self.back()

                elif scene == Scene.INFRA_CONFIDENTIAL:
                    logger.info("INFRA_CONFIDENTIAL")
                    if ctm.task == "daily":
                        # 检查是否领过线索
                        daily_scope = ((1815, 200), (1895, 250))
                        if self.find("clue/badge_new", scope=daily_scope):
                            self.tap((1800, 270))
                        else:
                            ctm.complete("daily")
                    elif ctm.task == "receive":
                        receive_scope = ((1815, 360), (1895, 410))
                        if self.find("clue/badge_new", scope=receive_scope):
                            self.ctap((1800, 430))
                        else:
                            ctm.complete("receive")
                    elif ctm.task == "place":
                        if fast_place := self.find("clue/fast_place"):
                            logger.info("快速摆放线索")
                            self.tap(fast_place, interval=2)
                            if unlock_pos := detect_unlock():
                                self.tap(unlock_pos)
                        ctm.complete("place")
                    elif ctm.task == "give_away":
                        self.ctap((1799, 578))
                    elif ctm.task == "party_time":
                        self.back()

                elif scene == Scene.CLUE_DAILY:
                    logger.info("CLUE_DAILY")
                    if not self.find(
                        "clue/icon_notification", scope=((1400, 0), (1920, 400))
                    ) and (clue := clue_cls("daily")):
                        logger.info(f"领取今日线索（{clue}号）")
                        self.tap_element("clue/button_get")
                        ctm.complete("daily")
                    else:
                        # 今日线索已领取，点X退出
                        self.tap((1484, 152))

                elif scene == Scene.CLUE_RECEIVE:
                    logger.info("CLUE_RECEIVE")
                    self.wait_product_complete()
                    if clue := clue_cls("receive"):
                        name_scope = ((1580, 220), (1880, 255))
                        name_img = cropimg(self.recog.gray, name_scope)
                        name_img = cv2.copyMakeBorder(
                            name_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                        )
                        name = rapidocr.engine(
                            name_img,
                            use_det=True,
                            use_cls=False,
                            use_rec=True,
                        )[0][0][1]
                        name = name.strip() if name else "好友"
                        logger.info(f"接收{name}的{clue}号线索")
                        self.tap(name_scope)
                    else:
                        ctm.complete("receive")
                        self.tap(exit_pos)

                elif scene == Scene.CLUE_PLACE:
                    logger.info("CLUE_PLACE")
                    cl, st = place_index()
                    if cl is None:
                        if unlock_pos := detect_unlock():
                            self.tap(unlock_pos)
                        else:
                            ctm.complete("place")
                            self.tap(exit_pos)
                        continue
                    if self.get_color((1328 + 77 * cl, 114))[0] < 150:
                        # 右上角 1-7
                        self.tap(clue_scope[cl])
                        continue
                    receive = st in ["available", "self"]
                    filter_receive = (1900, 45)
                    filter_self = (1610, 70)
                    filter_pos = filter_receive if receive else filter_self
                    if not all(self.get_color(filter_pos) > [252] * 3):
                        self.tap(filter_pos)
                        continue
                    clue_pos = ((1305, 208), (1305, 503), (1305, 797))
                    clue_list = []
                    for cp in clue_pos:
                        clue_img = cropimg(self.recog.img, tl2p(cp))
                        res = loadres(f"clue/{cl}")
                        result = cv2.matchTemplate(clue_img, res, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                        if max_val > tm_thres:
                            name_scope = (va(cp, (274, 99)), va(cp, (580, 134)))
                            name_img = cropimg(self.recog.gray, name_scope)
                            name_img = cv2.copyMakeBorder(
                                name_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                            )
                            name = rapidocr.engine(
                                name_img,
                                use_det=True,
                                use_cls=False,
                                use_rec=True,
                            )[0][0][1]
                            if name:
                                name = name.strip()
                            time_scope = (va(cp, (45, 222)), va(cp, (168, 255)))
                            time_hsv = cropimg(self.recog.img, time_scope)
                            time_hsv = cv2.cvtColor(time_hsv, cv2.COLOR_RGB2HSV)
                            if 165 < time_hsv[0][0][0] < 175:
                                time_img = thres2(
                                    cropimg(self.recog.gray, time_scope), 180
                                )
                                time_img = cv2.copyMakeBorder(
                                    time_img, 48, 48, 48, 48, cv2.BORDER_REPLICATE
                                )
                                time = rapidocr.engine(
                                    time_img,
                                    use_det=True,
                                    use_cls=False,
                                    use_rec=True,
                                )[0][0][1]
                                if time:
                                    time = time.strip()
                            else:
                                time = None
                            clue_list.append(
                                {"name": name, "time": time, "scope": tl2p(cp)}
                            )
                        else:
                            break
                    if clue_list:
                        list_name = "接收库" if receive else "自有库"
                        logger.info(f"{cl}号线索{list_name}：{clue_list}")
                        selected = None
                        for c in clue_list:
                            if c["time"]:
                                selected = c
                                break
                        selected = selected or clue_list[0]
                        self.tap(selected["scope"])
                        if clue_status[cl] == "available":
                            clue_status[cl] = "friend"
                        elif clue_status[cl] == "available_self_only":
                            clue_status[cl] = "self_only"
                        elif clue_status[cl] == "self":
                            clue_status[cl] = "friend"
                        else:
                            clue_status[cl] = None
                    else:
                        if clue_status[cl] == "available":
                            clue_status[cl] = "available_self_only"
                        elif clue_status[cl] == "available_self_only":
                            clue_status[cl] = None
                        elif clue_status[cl] == "self":
                            clue_status[cl] = "self_only"
                        else:
                            clue_status[cl] = None

                elif scene == Scene.CLUE_GIVE_AWAY:
                    give_away_true = self.leifeng_mode or (
                        not self.leifeng_mode
                        and self.clue_count > self.clue_count_limit
                    )
                    if give_away_true and (
                        fast_giveaway := self.find("clue/fast_giveaway")
                    ):
                        logger.info("快速送出线索")
                        self.tap(fast_giveaway)
                    ctm.complete("give_away")
                    self.tap((1868, 54))

                elif scene == Scene.CLUE_SUMMARY:
                    logger.info("CLUE_SUMMARY")
                    self.back()
                elif scene == Scene.INFRA_ARRANGE_ORDER:
                    self.back()
                elif scene in self.waiting_scene:
                    logger.info("waiting_scene")
                    self.waiting_solver()

                else:
                    self.scene_graph_navigation(Scene.INFRA_MAIN)
                    self.enter_room("meeting")
            self._run_clue_shop()
        except Exception as e:
            save_exception(e)
            logger.exception(e)
            return

    def adjust_order_time(self, accelerate, room):
        action_required_task = scheduling(
            self.tasks, op_data=getattr(self, "op_data", None)
        )
        # logger.error(f"action_required_task:{action_required_task}")
        logger.debug(f"room:{room}")
        logger.debug(self.get_run_order_adjust_room(action_required_task) == room)
        # while  action_required_task is not None and any(task.meta_data == room for task in action_required_task):

        # 设置为每次循环都验证一次当前房间 是否适合加速
        while (
            action_required_task is not None
            and self.get_run_order_adjust_room(action_required_task) == room
        ):
            # 如果不加判断 在无人机为0时将会一直触发循环 暂时设置默认值为20 可以考虑动态值
            drone_count = self.digit_reader.get_drone(self.recog.gray)
            logger.info(f"当前无人机数量为：{drone_count}")
            if drone_count <= 20:
                logger.error("无人机数量不足无法加速")
                # 看订单加速本体触发的频率，考虑到无人机回复较慢暂时先不加延迟触发了
                return False
            self.tap(accelerate)
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return None
            self.tap((self.recog.w * 1320 // 1920, self.recog.h * 502 // 1080))
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return None
            self.tap((self.recog.w * 3 // 4, self.recog.h * 4 // 5))
            if self.scene() in self.waiting_scene:
                if not self.waiting_solver():
                    return None

            self._wait_drone_interface(
                interval=1, accelerate_template="bill_accelerate"
            )

            _time = self.double_read_time(
                (
                    (self.recog.w * 650 // 2496, self.recog.h * 660 // 1404),
                    (self.recog.w * 815 // 2496, self.recog.h * 710 // 1404),
                ),
                use_digit_reader=True,
            )
            task_time = _time - timedelta(minutes=config.conf.run_order_delay)
            if task := find_next_task(
                self.tasks, task_type=TaskTypes.RUN_ORDER, meta_data=room
            ):
                task.time = task_time
                logger.info(
                    f"房间 {room} 无人机加速后接单时间为 {task_time.strftime('%H:%M:%S')}"
                )
                action_required_task = scheduling(
                    self.tasks, op_data=getattr(self, "op_data", None)
                )
            else:
                break
        return None

    def _tap_drone_accelerate(
        self,
        accelerate_res: str,
        all_in_res: str,
        max_retry: int = 3,
        interval: float = 1,
    ) -> Optional[tp.Scope]:
        """点击无人机加速按钮并确认加速面板打开，有界重试。

        首次点击可能因界面未响应而未打开面板，此时仍停留在详情页；若不确认
        all_in 出现就继续操作，会在详情页上误触。每次重试前重新识别加速按钮，
        确认仍处于可点击的详情页后再点击。持续失败时抛出异常，让上层保留任务
        并按既有策略退避，而不是把未执行的跑单当成已完成。
        """
        accelerate = self.find(accelerate_res)
        for _ in range(max_retry):
            if accelerate is None:
                break
            self.tap(accelerate, interval=interval)
            all_in = self.find(all_in_res)
            if all_in is not None:
                return all_in
            logger.debug(f"无人机加速面板未出现，重新识别 {accelerate_res} 后重试")
            accelerate = self.find(accelerate_res)
            if accelerate is None:
                # 加速按钮消失通常意味着面板已打开：等一帧再确认 all_in，避免误判
                self.sleep(0.5)
                all_in = self.find(all_in_res)
                if all_in is not None:
                    return all_in
                break
        raise RecognizeError(f"无人机加速面板未出现：未识别到 {all_in_res}")

    def _tap_product_point(self, point, interval=0.5):
        x, y = point
        self.tap(
            (self.recog.w * x // 1920, self.recog.h * y // 1080),
            interval=interval,
        )

    def _wait_product_resource(self, resource, *, present=True, retries=8):
        for _ in range(retries):
            found = self.find(resource)
            if bool(found) == present:
                return found
            self.sleep(0.5)
            self.recog.update()
        state = "出现" if present else "消失"
        raise RecognizeError(f"等待 {resource} {state}超时")

    def _product_ocr_text(self, scope) -> str:
        if rapidocr.engine is None:
            rapidocr.initialize_ocr()
        roi = cropimg(self.recog.img, scope)
        result = rapidocr.engine(
            roi,
            use_det=True,
            use_cls=False,
            use_rec=True,
        )[0]
        texts = []

        def collect(value):
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    collect(item)

        collect(result)
        return "".join(texts).replace(" ", "")

    def read_manufacture_product(self) -> str:
        product_scope = (
            (self.recog.w * 1540 // 1920, self.recog.h * 330 // 1080),
            (self.recog.w * 1835 // 1920, self.recog.h * 430 // 1080),
        )
        text = self._product_ocr_text(product_scope)
        for product_id in ("gold", "exp3"):
            product = MANUFACTURE_PRODUCTS[product_id]
            if product.name in text:
                logger.info(f"识别到当前制造产物：{product.name}")
                return product_id

        # 源石碎片标题位于复杂背景上，实机 OCR 可能为空；材料名位于纯色背景，
        # 同时还能直接区分固源岩和装置配方。
        material_scope = (
            (self.recog.w * 430 // 1920, self.recog.h * 330 // 1080),
            (self.recog.w * 650 // 1920, self.recog.h * 430 // 1080),
        )
        material_text = self._product_ocr_text(material_scope)
        material_products = {
            "固源岩": "orirock",
            "装置": "orirock_device",
        }
        for material, product_id in material_products.items():
            if material in material_text:
                logger.info(
                    f"识别到当前制造产物：{MANUFACTURE_PRODUCTS[product_id].name}"
                )
                return product_id
        if "源石碎片" in text:
            raise RecognizeError(
                f"无法识别源石碎片配方：{material_text or 'OCR 无结果'}"
            )
        raise RecognizeError(f"无法识别当前制造产物：{text or 'OCR 无结果'}")

    def _manufacture_is_idle(self) -> bool:
        """识别制造站因缺少材料且未补货而没有正在制造的状态。"""
        status_scope = (
            (self.recog.w * 1540 // 1920, self.recog.h * 430 // 1080),
            (self.recog.w * 1835 // 1920, self.recog.h * 700 // 1080),
        )
        text = self._product_ocr_text(status_scope)
        return "已完成" in text or "空闲中" in text or "00:00:00" in text

    def _cache_facility_state(self, room: str, facility: str, product: str) -> None:
        op_data = getattr(self, "op_data", None)
        if op_data is not None:
            op_data.update_facility_state(room, facility, product)

    def refresh_facility_state(self, room: str) -> None:
        """进入房间读取心情时，按标题栏刷新实际设施类型、产物或订单。"""
        if not self._product_switching_enabled():
            return
        if not room.startswith("room_"):
            return
        facility_by_name = {
            "制造站": "manufacture",
            "贸易站": "trade",
            "发电站": "power",
        }
        try:
            facility = facility_by_name.get(self.detect_room_type())
        except MowerExit:
            raise
        except Exception as e:
            logger.warning(f"刷新{self.translate_room(room)}设施类型失败：{e}")
            return
        if facility is None:
            return
        self.op_data.update_facility_state(room, facility)
        if facility == "power":
            return
        if (
            facility == "trade"
            and getattr(getattr(self, "task", None), "type", None)
            == TaskTypes.RUN_ORDER
        ):
            logger.debug("跑单换人后跳过贸易站订单类型刷新")
            return

        try:
            if facility == "manufacture":
                self._wait_drone_interface(
                    interval=3, accelerate_template="manufacture_accelerate"
                )
            else:
                self._wait_drone_interface(
                    interval=3,
                    accelerate_template="bill_accelerate",
                    page_template="order_label",
                )
            self._cache_facility_state_from_current_page(room, facility)
        except MowerExit:
            raise
        except Exception as e:
            logger.warning(f"刷新{self.translate_room(room)}设施状态失败：{e}")
        self.scene_graph_navigation(Scene.INFRA_DETAILS)

    def _confirm_drone_count(self, count: int):
        """在已打开的加速面板中精确选择无人机数量并确认。"""
        if count <= 0:
            return
        for _ in range(count):
            self._tap_product_point((1320, 502), interval=0.1)
        self._tap_product_point((1440, 864), interval=0.5)
        if self.scene() in self.waiting_scene:
            if not self.waiting_solver():
                raise RecognizeError("无人机加速确认后界面未恢复")

    def _select_manufacture_product(
        self, target_product: str, confirm_after: datetime | None = None
    ):
        product = MANUFACTURE_PRODUCTS[target_product]
        self._tap_product_point((1680, 500))
        self._wait_product_resource("manufacture_product_select")
        self._tap_product_point(product.category)
        self._tap_product_point(product.recipe)
        self._wait_product_resource("manufacture_product_change_confirm")
        self._tap_product_point((1425, 895))
        self._wait_product_resource("manufacture_product_change_confirm", present=False)

        # 更换配方还会二次确认取消旧制造计划。
        self._wait_product_resource("manufacture_product_cancel_confirm")
        if confirm_after is not None:
            remaining = (confirm_after - datetime.now()).total_seconds()
            if remaining > 0:
                logger.info("在制造计划取消确认页等待%.1f秒后确认", remaining)
                self.sleep(remaining)
                self.recog.update()
                self._wait_product_resource("manufacture_product_cancel_confirm")
        self._tap_product_point((1440, 742))
        self._wait_product_resource("manufacture_product_cancel_confirm", present=False)

        # 新配方默认只排一份；补到当前仓库容量允许的最大值。
        self._tap_product_point((1450, 305))
        for _ in range(8):
            if self.find("manufacture_product_change_confirm"):
                self._tap_product_point((1425, 895))
                self._wait_product_resource(
                    "manufacture_product_change_confirm", present=False
                )
                break
            # 配方切换后可能直接返回设施列表，不再弹出补满队列的确认框。
            if self.find("factory_collect"):
                logger.info("制造站已返回设施列表，跳过补满队列确认")
                break
            self.sleep(0.5)
        else:
            raise RecognizeError("等待制造站补满队列确认或返回设施列表超时")

    def _open_manufacture_product_detail(self, room: str):
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        self.enter_room(room)
        self._wait_drone_interface(
            interval=3, accelerate_template="manufacture_accelerate"
        )

    def _read_manufacture_total_seconds(self) -> int:
        hours, minutes, seconds = self.digit_reader.识别制造加速总剩余时间(
            self.recog.gray, self.recog.h, self.recog.w
        )
        return hours * 3600 + minutes * 60 + seconds

    def _read_manufacture_adjusted_total_seconds(self) -> int:
        """读取制造站产品卡上计入生产力加成的总剩余时间。"""
        scope = (
            (self.recog.w * 1580 // 1920, self.recog.h * 615 // 1080),
            (self.recog.w * 1790 // 1920, self.recog.h * 680 // 1080),
        )
        text = self._product_ocr_text(scope).replace("：", ":")
        match = re.search(r"(\d{1,3}):(\d{2}):(\d{2})", text)
        if not match:
            raise RecognizeError(f"无法识别制造站实际剩余时间：{text}")
        hours, minutes, seconds = map(int, match.groups())
        if minutes >= 60 or seconds >= 60:
            raise RecognizeError(f"制造站实际剩余时间无效：{text}")
        return hours * 3600 + minutes * 60 + seconds

    def _read_manufacture_speed(self) -> float:
        """从制造站页面的生产力一栏读取 1 + 干员加成。"""
        scope = (
            (self.recog.w * 1130 // 1920, self.recog.h * 940 // 1080),
            (self.recog.w * 1380 // 1920, self.recog.h * 1000 // 1080),
        )
        text = self._product_ocr_text(scope).replace("−", "-").replace("－", "-")
        expression = re.match(r"1(?:[+-]\d+(?:\.\d+)?)*", text)
        if expression is None:
            raise RecognizeError(f"无法识别制造站生产力：{text}")
        speed = 1 + sum(
            float(value)
            for value in re.findall(r"[+-]\d+(?:\.\d+)?", expression.group())
        )
        if not 0.1 <= speed <= 10:
            raise RecognizeError(f"制造站生产力无效：{text}")
        return speed

    def _product_switch_drone_plan(self, remaining: int, unit: int, max_loss: int):
        count, wait = drone_plan(remaining, unit, max_loss)
        limit = getattr(
            getattr(config.conf, "product_switching", None),
            "max_drones_per_switch",
            0,
        )
        if limit and count > limit:
            count = limit
            wait = max(0, remaining - count * DRONE_SECONDS)
        return count, wait

    def _survey_manufacture_switch(self, room: str, target_product: str) -> dict:
        """只读取一个制造站，为批量计划收集快照，不消耗无人机。"""
        self._open_manufacture_product_detail(room)
        current_product = self.read_manufacture_product()
        self._cache_facility_state(room, "manufacture", current_product)
        observation = {
            "room": room,
            "facility": "manufacture",
            "target_product": target_product,
            "current_product": current_product,
            "needs_switch": current_product != target_product,
        }
        if not observation["needs_switch"]:
            return observation

        observation["available_drones"] = self.digit_reader.get_drone(
            self.recog.gray, self.recog.h, self.recog.w
        )
        if self._manufacture_is_idle():
            observation.update(
                total_seconds=0,
                current_remaining=0,
                drone_count=0,
                wait_seconds=0,
            )
            logger.info(f"{self.translate_room(room)}当前空闲，无需使用无人机")
            return observation
        rate = 1.0
        adjusted_total = None
        rate = None
        try:
            rate = self._read_manufacture_speed()
        except MowerExit:
            raise
        except Exception as e:
            logger.warning("读取制造站生产力失败：%s，尝试用页面倒计时估算", e)
            try:
                adjusted_total = self._read_manufacture_adjusted_total_seconds()
                adjusted_at = datetime.now()
            except MowerExit:
                raise
            except Exception as timer_error:
                logger.warning("读取制造站实际倒计时失败：%s", timer_error)
        self._tap_drone_accelerate("manufacture_accelerate", "all_in")
        total_seconds = self._read_manufacture_total_seconds()
        self._tap_product_point((480, 864))
        if rate is None and adjusted_total:
            adjusted_now = max(
                1, adjusted_total - (datetime.now() - adjusted_at).total_seconds()
            )
            rate = total_seconds / adjusted_now
        if rate is None or not 0.1 <= rate <= 10:
            logger.warning("制造速度估算异常，使用基础速度")
            rate = 1.0
        unit_seconds = MANUFACTURE_PRODUCTS[current_product].unit_seconds
        setting = getattr(config.conf, "product_switching", None)
        max_loss_seconds = (
            getattr(setting, "drone_loss_seconds", 30)
            if getattr(setting, "grandet_mode", True)
            else DRONE_SECONDS
        )
        drone_count, wait_seconds = self._product_switch_drone_plan(
            total_seconds, unit_seconds, max_loss_seconds
        )
        natural_only = (
            (getattr(setting, "grandet_mode", True))
            and not getattr(setting, "use_drones_when_leaving_orirock", True)
            and current_product in {"orirock", "orirock_device"}
            and target_product not in {"orirock", "orirock_device"}
        )
        if natural_only:
            logger.info(
                "%s切出源石碎片按设置等待当前一份自然完成，不使用无人机",
                self.translate_room(room),
            )
            drone_count = 0
        observation.update(
            total_seconds=total_seconds,
            current_remaining=current_unit_remaining(total_seconds, unit_seconds),
            drone_count=drone_count,
            wait_seconds=wait_seconds,
            production_rate=rate,
            observed_at=datetime.now(),
            natural_only=natural_only,
        )
        logger.info(
            f"{self.translate_room(room)}计划：使用{drone_count}架无人机，"
            f"余下至多等待{wait_seconds}秒"
        )
        return observation

    @staticmethod
    def _product_switch_entry_lead_seconds():
        """参考跑单提前量，避免过早占用基建界面。"""
        return max(120, min(300, config.conf.run_order_delay * 60))

    def _estimate_product_switch_ready_seconds(self, observations, available):
        """基础剩余量按页面生产速度减少，同时估算无人机恢复。"""
        setting = getattr(config.conf, "product_switching", None)
        max_loss = (
            getattr(setting, "drone_loss_seconds", 30)
            if getattr(setting, "grandet_mode", True)
            else DRONE_SECONDS
        )

        def required_after(seconds):
            required = 0
            for item in observations:
                remaining = max(
                    0,
                    math.ceil(
                        item["current_remaining"]
                        - item.get("production_rate", 1.0) * seconds
                    ),
                )
                unit = MANUFACTURE_PRODUCTS[item["current_product"]].unit_seconds
                required += self._product_switch_drone_plan(remaining, unit, max_loss)[
                    0
                ]
            return required

        high = max(
            math.ceil(item["current_remaining"] / item.get("production_rate", 1.0))
            for item in observations
        )
        low = 0
        while low < high:
            middle = (low + high) // 2
            # 充能加成、当前一架的部分进度只会使实际可用时间更早。
            if required_after(middle) <= available + middle // 360:
                high = middle
            else:
                low = middle + 1
        logger.info(
            "换班前切产物预计约%d秒后无人机足够，实测制造速率=%s",
            low,
            [round(item.get("production_rate", 1.0), 2) for item in observations],
        )
        return low

    def _execute_manufacture_acceleration(self, observation: dict) -> int:
        """按快照复核当前份进度，只允许把计划中的无人机数向下修正。"""
        self._open_manufacture_product_detail(observation["room"])
        current_product = self.read_manufacture_product()
        if current_product == observation["target_product"]:
            return 0
        if current_product != observation["current_product"]:
            raise RecognizeError(
                f"{self.translate_room(observation['room'])}产物在规划期间发生变化"
            )

        if self._manufacture_is_idle():
            logger.info(
                f"{self.translate_room(observation['room'])}当前空闲，直接切换产物"
            )
            return 0

        available_drones = self.digit_reader.get_drone(
            self.recog.gray, self.recog.h, self.recog.w
        )
        self._tap_drone_accelerate("manufacture_accelerate", "all_in")
        current_total = self._read_manufacture_total_seconds()
        progressed = max(0, observation["total_seconds"] - current_total)
        remaining = max(0, observation["current_remaining"] - progressed)
        setting = getattr(config.conf, "product_switching", None)
        max_loss_seconds = (
            getattr(setting, "drone_loss_seconds", 30)
            if getattr(setting, "grandet_mode", True)
            else DRONE_SECONDS
        )
        unit_seconds = MANUFACTURE_PRODUCTS[current_product].unit_seconds
        drone_count, wait_seconds = self._product_switch_drone_plan(
            remaining, unit_seconds, max_loss_seconds
        )
        drone_count = min(drone_count, observation["drone_count"])
        wait_seconds = max(0, remaining - drone_count * DRONE_SECONDS)
        if available_drones < drone_count:
            self._tap_product_point((480, 864))
            raise ProductSwitchDeferred(
                f"无人机不足：需要{drone_count}架，当前{available_drones}架"
            )
        if drone_count:
            self._confirm_drone_count(drone_count)
        else:
            self._tap_product_point((480, 864))
        observation["remaining_after_acceleration"] = max(
            0, remaining - drone_count * DRONE_SECONDS
        )
        observation["accelerated_at"] = datetime.now()
        logger.info(
            f"{self.translate_room(observation['room'])}执行计划："
            f"使用{drone_count}架无人机，余下至多等待{wait_seconds}秒"
        )
        return wait_seconds

    def _change_manufacture_product(self, observation: dict, direct=False):
        self._open_manufacture_product_detail(observation["room"])
        current_product = self.read_manufacture_product()
        self._cache_facility_state(observation["room"], "manufacture", current_product)
        if current_product == observation["target_product"]:
            return
        confirm_after = None
        if (not direct) and not self._manufacture_is_idle():
            try:
                rate = self._read_manufacture_speed()
            except MowerExit:
                raise
            except Exception as e:
                logger.warning("切换前重读生产力失败：%s，使用巡检值", e)
                rate = observation.get("production_rate", 1.0)
            if "accelerated_at" in observation:
                elapsed = max(
                    0, (datetime.now() - observation["accelerated_at"]).total_seconds()
                )
                conservative_rate = min(rate, observation.get("production_rate", rate))
                remaining_base = max(
                    0,
                    observation["remaining_after_acceleration"]
                    - elapsed * conservative_rate,
                )
            else:
                self._tap_drone_accelerate("manufacture_accelerate", "all_in")
                current_total = self._read_manufacture_total_seconds()
                self._tap_product_point((480, 864))
                boundary = (
                    observation["total_seconds"] - observation["current_remaining"]
                )
                remaining_base = max(0, current_total - boundary)
            setting = config.conf.product_switching
            buffer_seconds = (
                getattr(setting, "waiting_seconds", 2)
                if getattr(setting, "grandet_mode", True)
                else 0
            )
            wait_seconds = math.ceil(remaining_base / rate) + buffer_seconds
            lead = self._product_switch_entry_lead_seconds()
            if wait_seconds > lead:
                raise ProductSwitchDeferred(
                    f"{self.translate_room(observation['room'])}当前一份尚需约"
                    f"{wait_seconds}秒，稍后进入切换确认页",
                    minutes=max(15, wait_seconds - lead) / 60,
                )
            confirm_after = datetime.now() + timedelta(seconds=wait_seconds)
        self._select_manufacture_product(
            observation["target_product"], confirm_after=confirm_after
        )
        self.recog.update()
        final_product = self.read_manufacture_product()
        self._cache_facility_state(observation["room"], "manufacture", final_product)
        if final_product != observation["target_product"]:
            raise RecognizeError(
                f"制造站产物切换校验失败：期望"
                f"{MANUFACTURE_PRODUCTS[observation['target_product']].name}，"
                f"实际{MANUFACTURE_PRODUCTS[final_product].name}"
            )

    def _open_trade_product_detail(self, room: str):
        self.scene_graph_navigation(Scene.INFRA_MAIN)
        self.enter_room(room)
        self._wait_drone_interface(
            interval=3,
            accelerate_template="bill_accelerate",
            page_template="order_label",
        )

    def _read_trade_product_card(self) -> tuple[str, bool]:
        """从订单列表右下角卡片读取订单类型及是否允许切换。"""
        scope = (
            (self.recog.w * 1400 // 1920, self.recog.h * 840 // 1080),
            (self.recog.w * 1810 // 1920, self.recog.h * 1040 // 1080),
        )
        text = self._product_ocr_text(scope)
        locked = "3级后可切换" in text or ("3级" in text and "切换" in text)
        if "开采协力" in text:
            product_id = "orundum"
        elif "龙门商法" in text or locked:
            product_id = "lmd"
        else:
            raise RecognizeError(f"无法识别当前贸易站订单类型：{text or 'OCR 无结果'}")
        logger.info(
            f"识别到当前贸易站订单类型：{TRADE_PRODUCTS[product_id].strategy_name}"
        )
        if locked:
            logger.info("识别到低等级贸易站，订单类型固定为龙门商法")
        return product_id, not locked

    def _cache_facility_state_from_current_page(
        self, room: str, facility: Literal["manufacture", "trade"]
    ) -> None:
        """在当前生产页面顺带更新设施状态，不进入或退出任何页面。"""
        if not self._product_switching_enabled():
            return
        if facility not in ("manufacture", "trade"):
            raise ValueError(f"未知设施类型：{facility}")
        try:
            if facility == "manufacture":
                product = self.read_manufacture_product()
                label = MANUFACTURE_PRODUCTS[product].name
            else:
                product, _ = self._read_trade_product_card()
                label = TRADE_PRODUCTS[product].strategy_name
            self._cache_facility_state(room, facility, product)
            logger.info(f"已在当前页面刷新{self.translate_room(room)}设施状态：{label}")
        except MowerExit:
            raise
        except Exception as e:
            logger.warning(f"刷新{self.translate_room(room)}设施状态失败：{e}")

    def _close_trade_product_select(self):
        # 订单类型点击后立即生效，但选择弹窗不会自行关闭。
        self._tap_product_point((1600, 200))
        self._wait_product_resource("trade_strategy_select", present=False)

    def _survey_trade_switch(self, room: str, target_product: str) -> dict:
        self._open_trade_product_detail(room)
        current_product, switchable = self._read_trade_product_card()
        self._cache_facility_state(room, "trade", current_product)
        return {
            "room": room,
            "facility": "trade",
            "target_product": target_product,
            "current_product": current_product,
            "needs_switch": current_product != target_product,
            "switchable": switchable,
        }

    def _change_trade_product(self, observation: dict):
        self._open_trade_product_detail(observation["room"])
        current_product, switchable = self._read_trade_product_card()
        self._cache_facility_state(observation["room"], "trade", current_product)
        if current_product == observation["target_product"]:
            return
        if not switchable:
            if observation["target_product"] == "lmd":
                return
            raise ProductSwitchDeferred(
                f"{self.translate_room(observation['room'])}等级不足，"
                "无法切换至开采协力",
                minutes=60,
            )
        self._tap_product_point((1580, 955))
        self._wait_product_resource("trade_strategy_select")
        self._tap_product_point(TRADE_PRODUCTS[observation["target_product"]].option)
        self._close_trade_product_select()
        self.recog.update()
        final_product, _ = self._read_trade_product_card()
        self._cache_facility_state(observation["room"], "trade", final_product)
        if final_product != observation["target_product"]:
            raise RecognizeError(
                f"贸易站订单切换校验失败：期望"
                f"{TRADE_PRODUCTS[observation['target_product']].strategy_name}，"
                f"实际{TRADE_PRODUCTS[final_product].strategy_name}"
            )

    def switch_base_products(
        self,
        tasks: list[SchedulerTask],
        before_arrangement: bool = False,
        waited_for_drones: bool = False,
    ):
        """先巡检全部目标站，再统一执行最省无人机的产物与订单计划。"""
        if not self._product_switching_enabled():
            self._discard_product_switches()
            return
        task_observations = []
        for task in tasks:
            room, target_product = parse_product_task_meta(task.meta_data)
            if target_product in MANUFACTURE_PRODUCTS:
                observation = self._survey_manufacture_switch(room, target_product)
            else:
                observation = self._survey_trade_switch(room, target_product)
            task_observations.append((task, observation))

        locked_trade = [
            (task, observation)
            for task, observation in task_observations
            if observation["facility"] == "trade"
            and observation["needs_switch"]
            and not observation.get("switchable", True)
        ]
        if locked_trade and before_arrangement:
            rooms = "、".join(
                self.translate_room(observation["room"])
                for _, observation in locked_trade
            )
            raise ProductSwitchDeferred(
                f"{rooms}等级不足，换班前无法切换订单", minutes=60
            )
        if locked_trade:
            rooms = "、".join(
                self.translate_room(observation["room"])
                for _, observation in locked_trade
            )
            retry_time = datetime.now() + timedelta(minutes=60)
            for task, _ in locked_trade:
                task.time = max(task.time, retry_time)
            logger.warning(
                f"{rooms}等级不足，无法切换至开采协力；"
                f"对应任务推迟至 {retry_time.strftime('%H:%M:%S')}"
            )
            locked_task_ids = {id(task) for task, _ in locked_trade}
            task_observations = [
                item for item in task_observations if id(item[0]) not in locked_task_ids
            ]

        pending_manufacture = [
            observation
            for _, observation in task_observations
            if observation["facility"] == "manufacture" and observation["needs_switch"]
        ]
        natural_only = [
            item for item in pending_manufacture if item.get("natural_only", False)
        ]
        accelerated_manufacture = [
            item for item in pending_manufacture if not item.get("natural_only", False)
        ]
        planned_drones = sum(item["drone_count"] for item in accelerated_manufacture)
        available = min(
            (item["available_drones"] for item in accelerated_manufacture),
            default=planned_drones,
        )
        if available == 201:
            raise RecognizeError("无人机数量识别异常")
        logger.info(
            f"制造站批量切产物计划共需至多{planned_drones}架无人机，"
            f"当前可用{available}架"
        )
        insufficient_drones = planned_drones > available
        allow_direct = getattr(
            getattr(config.conf, "product_switching", None),
            "direct_when_drones_insufficient",
            False,
        )
        if insufficient_drones and before_arrangement and not allow_direct:
            ready_seconds = self._estimate_product_switch_ready_seconds(
                accelerated_manufacture, available
            )
            lead = self._product_switch_entry_lead_seconds()
            if ready_seconds > lead or waited_for_drones:
                retry_seconds = (
                    max(15, ready_seconds - lead) if not waited_for_drones else 60
                )
                raise ProductSwitchDeferred(
                    f"换班前切产物无人机不足：需要{planned_drones}架，当前{available}架；"
                    "提前进入制造站复核",
                    minutes=retry_seconds / 60,
                )
            logger.info("预计%d秒后无人机足够，留在基建等待并复核", ready_seconds)
            self.sleep(ready_seconds + 2)
            self.recog.update()
            return self.switch_base_products(
                tasks,
                before_arrangement=before_arrangement,
                waited_for_drones=True,
            )

        # 入站时间可以提前，但确认必须在这一份完成之后。无人机上限也会
        # 增加自然等待时间，过早到站时先延期，不在确认页长时间占用界面。
        lead = self._product_switch_entry_lead_seconds()
        now = datetime.now()
        for item in pending_manufacture:
            if insufficient_drones and allow_direct and not item.get("natural_only"):
                continue
            remaining_base = max(
                0,
                item.get("current_remaining", 0) - item["drone_count"] * DRONE_SECONDS,
            )
            elapsed = max(0, (now - item.get("observed_at", now)).total_seconds())
            wait_seconds = max(
                0,
                math.ceil(remaining_base / item.get("production_rate", 1.0) - elapsed),
            )
            if wait_seconds > lead:
                raise ProductSwitchDeferred(
                    f"{self.translate_room(item['room'])}当前一份还需约{wait_seconds}秒，"
                    "稍后进入切换确认页",
                    minutes=max(15, wait_seconds - lead) / 60,
                )

        # 订单不使用无人机，巡检完成后直接切换，不受制造站无人机余量影响。
        if not before_arrangement:
            for _, observation in task_observations:
                if observation["facility"] == "trade" and observation["needs_switch"]:
                    self._change_trade_product(observation)
            resolved_before_manufacture = {
                id(task)
                for task, observation in task_observations
                if observation["facility"] == "trade" or not observation["needs_switch"]
            }
            self.tasks[:] = [
                task
                for task in self.tasks
                if id(task) not in resolved_before_manufacture
            ]

        if insufficient_drones and not allow_direct:
            raise ProductSwitchDeferred(
                f"批量切产物无人机不足：需要{planned_drones}架，当前{available}架"
            )

        if insufficient_drones:
            logger.warning("无人机不足，按设置直接取消当前份进度并切换产物")
            execution_order = []
            direct_switch_rooms = {item["room"] for item in accelerated_manufacture}
        else:
            # 余数大的站先处理，把更快自然跨过三分钟边界的站留到后面。
            execution_order = sorted(
                accelerated_manufacture,
                key=lambda item: (item["wait_seconds"], item["drone_count"]),
                reverse=True,
            )
            direct_switch_rooms = set()

        waits = []
        for item in execution_order:
            try:
                waits.append(self._execute_manufacture_acceleration(item))
            except ProductSwitchDeferred:
                if not allow_direct:
                    raise
                logger.warning(
                    "%s无人机在执行前变得不足，直接切换产物",
                    self.translate_room(item["room"]),
                )
                direct_switch_rooms.add(item["room"])

        # 每个站各自在取消旧计划的确认页等待，完成约两秒后再点击。
        for observation in natural_only:
            self._change_manufacture_product(observation)
        for observation in accelerated_manufacture:
            if observation["room"] in direct_switch_rooms:
                self._change_manufacture_product(observation, direct=True)
            else:
                self._change_manufacture_product(observation)
        if before_arrangement:
            for _, observation in task_observations:
                if observation["facility"] == "trade" and observation["needs_switch"]:
                    self._change_trade_product(observation)

        task_ids = {id(task) for task, _ in task_observations}
        self.tasks[:] = [task for task in self.tasks if id(task) not in task_ids]
        self.tasks.sort(key=lambda task: task.time)
        logger.info(
            f"基建批量切换完成，共处理{len(task_observations)}个生产站，"
            f"延期{len(locked_trade)}个低等级贸易站"
        )

    def drone(
        self,
        room: str,
        not_customize=False,
        not_return=False,
        adjust_time=False,
        skip_enter=False,
    ):
        logger.info("基建：无人机加速" if not adjust_time else "开始调整订单时间")
        all_in = 0
        if not not_customize:
            all_in = len(self.op_data.run_order_rooms)
        # 点击进入该房间
        if not skip_enter:
            self.enter_room(room)
        # 进入房间详情

        self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
        # 关闭掉房间总览
        self._wait_drone_interface(interval=3)

        accelerate = self.find("manufacture_accelerate")
        if accelerate:
            self._cache_facility_state_from_current_page(room, "manufacture")
            drone_count = self.digit_reader.get_drone(self.recog.gray)
            logger.info(f"当前无人机数量为：{drone_count}")
            if drone_count < config.conf.drone_count_limit:
                logger.info(f"无人机数量小于{config.conf.drone_count_limit}->停止")
                return
            logger.info("制造站加速")
            all_in_scope = self._tap_drone_accelerate(
                "manufacture_accelerate", "all_in"
            )
            # 如果不是全部all in
            if all_in > 0:
                tap_times = (
                    drone_count - config.conf.drone_count_limit
                )  # 修改为无人机阈值
                for _count in range(tap_times):
                    self.tap((self.recog.w * 0.7, self.recog.h * 0.5), interval=0.1)
            else:
                self.tap(all_in_scope)
            self.tap(accelerate, y_rate=1)
        else:
            accelerate = self.find("bill_accelerate")
            while accelerate and not adjust_time:
                logger.info("贸易站加速")
                all_in_scope = self._tap_drone_accelerate("bill_accelerate", "all_in")
                self.tap(all_in_scope)
                self.tap((self.recog.w * 0.75, self.recog.h * 0.8))
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
                self.recog.update()
                self.accept_order()
                if not (
                    self.drone_room is None
                    or (
                        self.drone_room == room and room in self.op_data.run_order_rooms
                    )
                ):
                    break
                if not_customize:
                    drone_count = self.digit_reader.get_drone(self.recog.gray)
                    logger.info(f"当前无人机数量为：{drone_count}")
                    # 200 为识别错误
                    if (
                        drone_count < config.conf.drone_count_limit
                        or drone_count == 201
                    ):
                        logger.info(
                            f"无人机数量小于{config.conf.drone_count_limit}->停止"
                        )
                        break
                accelerate = self.find("bill_accelerate")
            if adjust_time:
                return self.adjust_order_time(accelerate, room)
        if not_return:
            return
        self.scene_graph_navigation(Scene.INFRA_MAIN)

    # 用于制造站切换产物，请注意在调用该函数前有足够的无人机，并补足相应制造站产物，目前仅支持中级作战记录与赤金之间的切换
    # def 制造站切换产物(self, room: str, 目标产物: str, not_customize=False, not_return=False):
    #     # 点击进入该房间
    #     self.enter_room(room)
    #     while self.get_infra_scene() == 9:
    #         time.sleep(1)
    #         self.recog.update()
    #     # 进入房间详情
    #     self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
    #     # 关闭掉房间总览
    #     error_count = 0
    #     while self.find('manufacture_accelerate') is None:
    #         if error_count > 5:
    #             raise Exception('未成功进入制造详情界面')
    #         self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=3)
    #         error_count += 1
    #     accelerate = self.find('manufacture_accelerate')
    #     无人机数量 = self.digit_reader.get_drone(self.recog.gray, self.recog.h, self.recog.w)
    #     if accelerate:
    #         self.tap_element('manufacture_accelerate')
    #         self.recog.update()
    #         剩余制造加速总时间 = self.digit_reader.识别制造加速总剩余时间(self.recog.gray, self.recog.h, self.recog.w)
    #         # logger.info(f'制造站 B{room[5]}0{room[7]} 剩余制造总时间为 {剩余制造加速总时间}')
    #         时 = int(剩余制造加速总时间[0:3])
    #         if 时 > 118: 当前产物 = '经验'
    #         else:   当前产物 = '赤金'
    #         if 当前产物 == 目标产物:
    #             logger.info('返回基建主界面')
    #             while self.get_infra_scene() != 201:
    #                 if self.find('index_infrastructure') is not None:
    #                     self.tap_element('index_infrastructure')
    #                 elif self.find('12cadpa') is not None:
    #                     self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                 else:
    #                     self.back()
    #                 self.recog.update()
    #         else:
    #             logger.info(f'制造站 B{room[5]}0{room[7]} 当前产物为{当前产物}，切换产物为{目标产物}')
    #             需要无人机数 = 0
    #             while 需要无人机数 < 10:
    #                 总分钟数 = int(剩余制造加速总时间[4:6]) + 60 * 时
    #                 if 当前产物 == '赤金':
    #                     需要无人机数 = (总分钟数 % 72) // 3 + 1
    #                 elif 当前产物 == '经验':
    #                     需要无人机数 = (总分钟数 % 180) // 3 + 1
    #                 else:
    #                     logger.warning('目前不支持该产物切换策略，尚待完善')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #                 if 需要无人机数 > 无人机数量 - 10:
    #                     logger.warning(f'''
    #                     切换产物需要无人机{需要无人机数}个，当前仅有{无人机数量}个，
    #                     无法切换产物，建议该任务至少在{(需要无人机数 - 无人机数量 + 10) * 3.5 // 3}分钟后再执行
    #                     ''')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #                 else:
    #                     logger.warning(f'需要加无人机{需要无人机数}个')
    #                     for 次数 in range(需要无人机数):
    #                         self.tap((self.recog.w * 1320 // 1920, self.recog.h * 502 // 1080), interval=0.05)
    #                     self.recog.update()
    #                     剩余制造加速总时间 = self.digit_reader.识别制造加速总剩余时间(
    #                         self.recog.gray, self.recog.h, self.recog.w)
    #                     # logger.info(f'制造站 B{room[5]}0{room[7]} 剩余制造总时间为 {剩余制造加速总时间}')
    #                 总分钟数 = int(剩余制造加速总时间[4:6]) + 60 * 时
    #                 if 当前产物 == '赤金':
    #                     需要无人机数 = (总分钟数 % 72) // 3 + 1
    #                 elif 当前产物 == '经验':
    #                     需要无人机数 = (总分钟数 % 180) // 3 + 1
    #                 else:
    #                     logger.warning('目前不支持该产物切换策略，尚待完善')
    #                     logger.info('返回基建主界面')
    #                     while self.get_infra_scene() != 201:
    #                         if self.find('index_infrastructure') is not None:
    #                             self.tap_element('index_infrastructure')
    #                         elif self.find('12cadpa') is not None:
    #                             self.device.tap((self.recog.w // 2, self.recog.h // 2))
    #                         else:
    #                             self.back()
    #                         self.recog.update()
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 4 // 5), interval=3)    # 确认加速
    #             self.tap((self.recog.w * 9 // 10, self.recog.h // 2), interval=1)     # 点击当前产品
    #             if 目标产物 == '经验':
    #                 self.tap((self.recog.w // 2, self.recog.h // 2), interval=1)    # 点击中级作战记录
    #             elif 目标产物 == '赤金':
    #                 self.tap((self.recog.w // 10, self.recog.h // 3), interval=1)   # 进入贵金属分类
    #                 self.tap((self.recog.w // 2, self.recog.h // 4), interval=1)    # 点击赤金
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 2 // 7), interval=1)    # 点击最多
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 5 // 6), interval=1)    # 确认数量
    #             self.tap((self.recog.w * 3 // 4, self.recog.h * 7 // 10), interval=1)   # 确认更改

    def get_order(self, name):
        if name in self.op_data.operators:
            return True, self.op_data.operators[name].arrange_order
        else:
            return False, ["技能", "false"]

    @timed_step("confirm")
    def tap_confirm(self, room, new_plan=None):
        if new_plan is None:
            new_plan = {}
        self.recog.update()
        if (
            self.task.type == TaskTypes.RUN_ORDER
            and not self.task.adjusted
            and room in self.op_data.run_order_rooms
            and self.task.meta_data
            and len(new_plan) == 1
            and config.conf.run_order_buffer_time > 0
        ):
            wait_confirm = round(
                (
                    (self.task.time - datetime.now()).total_seconds()
                    + config.conf.run_order_delay * 60
                    - config.conf.run_order_buffer_time
                ),
                1,
            )
            if wait_confirm > 0:
                logger.info(f"等待跑单 {str(wait_confirm)} 秒")
                self.sleep(wait_confirm)
        for template in ("confirm_blue", "confirm_train", "arrange_confirm"):
            clicks = 0
            retry_ready = False
            for _ in range(12):
                if self.find("connecting"):
                    retry_ready = False
                    self.sleep()
                    continue
                # 已点击后提高按钮清晰度要求，避免再次点击淡出动画里的残影。
                # 初次按钮沿用原识别规则，兼容不同背景和训练室。
                pos = self.find(template, score=0.9) if clicks else self.find(template)
                if pos is None:
                    if not clicks:
                        break
                    if (
                        self.find(template, score=0.9)
                        if clicks
                        else self.find(template)
                    ) is None and any(
                        self.find(destination)
                        for destination in (
                            "confirm_blue",
                            "confirm_train",
                            "arrange_confirm",
                            "room_detail",
                            "arrange_check_in",
                            "arrange_check_in_small",
                            "arrange_check_in_on",
                            "recycle/dashboard",
                        )
                        if destination != template
                    ):
                        break
                    # 按钮消失但目标页尚未出现也是过渡帧，不能漏掉迟到的二次确认。
                    retry_ready = False
                    self.sleep(0.2)
                    continue
                if clicks and not retry_ready:
                    # 可能仍是点击前的旧帧；再观察一次才判断点击未生效。
                    retry_ready = True
                    self.sleep(0.2)
                    continue
                if clicks >= 4:
                    raise RecognizeError("干员确认点击未生效，返回房间重试")
                target = (
                    (self.recog.w // 3 * 2, self.recog.h - 10)
                    if template == "arrange_confirm"
                    else pos
                )
                # tap 自己完成一次等待及缓存失效，不再叠加 sleep(0.5)。
                self.tap(target, interval=0.2)
                clicks += 1
                retry_ready = False
            else:
                raise RecognizeError("干员确认画面仍未稳定，返回房间重试")

    def _open_check_in_detail(self):
        """#92：训练室主页面点 arrange_check_in（屏幕左侧 ~(101,441)）开进驻信息浮窗。

        旧代码 tap((0.25w, 0.95h))=(480,1026)——该坐标在训练室落在左下角技能/进度
        面板，弹出技能详情浮窗而非进驻信息浮窗（Scene -1 空转 7s 后出房重进）。
        与 turn_on_room_detail 同源：找不到模板就 sleep 等动画重扫。
        """
        if pos := self.find("arrange_check_in"):
            self.tap(pos, interval=0.5)
        elif pos := self.find("arrange_check_in_small"):
            self.tap(pos, interval=0.5)
        else:
            self.sleep()

    def choose_train(self, agents: list[str], fast_mode=True, choose_error=0):
        tasks = ["scan"]
        select_targets = []
        unknown_cnt = 0
        start_time = datetime.now()
        while tasks:
            if datetime.now() - start_time > timedelta(minutes=2):
                raise Exception("选人流程超时，自动退出")
            scene = self.scene()
            if scene == Scene.UNKNOWN:
                unknown_cnt += 1
                if unknown_cnt > 5:
                    unknown_cnt = 0
                    self.back_to_infrastructure()
                    self.enter_room("train")
                else:
                    self.sleep()
                continue
            elif scene == Scene.CONNECTING:
                self.sleep(1)
                continue
            elif scene == Scene.INFRA_DETAILS and not self.find("room_detail"):
                self._open_check_in_detail()
                continue
            elif scene == Scene.INFRA_MAIN:
                self.enter_room("train")
                continue
            elif scene == Scene.INFRA_DETAILS and self.find("room_detail"):
                if tasks[0] == "scan":
                    scan_result = self.get_agent_from_room(
                        "train", departing_plan=agents
                    )
                    logger.debug(f"需要选择的干员：{scan_result}")
                    if len(scan_result) < len(agents):
                        scan_result.extend([""] * (len(agents) - len(scan_result)))
                    desired = list(agents)
                    logger.debug(f"需要选择的desired干员：{desired}")
                    for idx, name in enumerate(desired):
                        if name == "Current":
                            # #53：替换为实际干员名（scan_result[idx] 是 dict，不能直接当名字）
                            desired[idx] = scan_result[idx]["agent"]
                    select_targets = [
                        (idx, desired_name)
                        for idx, desired_name in enumerate(desired)
                        if scan_result[idx]["agent"] != desired_name
                    ]
                    if not select_targets:
                        tasks = []
                        return
                    # #211：训练位锁定判断已归调用方（gate 冻结 idx1 / 坐错人纠正
                    # 用三态判空闲），choose_train 不再自查锁定，只执行换人。
                    tasks[0] = "select"
                    logger.debug(f"需要选择的干员：{select_targets}")
                else:
                    if not select_targets:
                        tasks = []
                        return
                    idx = select_targets[0][0]
                    self.ctap((self.recog.w * 0.82, self.recog.h * 0.18 * (idx + 1)))
                continue
            elif scene == Scene.TRAIN_FINISH:
                self.tap((self.recog.w * 0.05, self.recog.h * 0.95), interval=0.5)
                continue
            elif scene == Scene.TRAIN_MAIN:
                self._open_check_in_detail()
                continue
            elif scene == Scene.INFRA_ARRANGE_ORDER:
                logger.info(tasks)
                if tasks[0] == "scan":
                    self.back()
                else:
                    if not select_targets:
                        tasks = []
                        return
                    logger.info(f"需要选择的干员：{select_targets}")
                    idx = select_targets[0][0]
                    if idx == 0:
                        if agents[idx] == "Free":
                            select_targets.pop(0)
                            if select_targets:
                                continue
                            tasks[0] = "scan"
                            continue
                        # #53：选人用 desired[idx]（Current 已替换为实际干员名），
                        # 不能用 agents[idx]——否则 Current 会被当干员名选人、必然失败
                        if choose_error:
                            self.choose_agent(
                                [desired[idx]],
                                "train",
                                fast_mode,
                                choose_error=choose_error,
                            )
                        else:
                            self.choose_agent([desired[idx]], "train", fast_mode)
                    else:
                        if choose_error:
                            self.choose_train_ope(
                                desired[idx], choose_error=choose_error
                            )
                        else:
                            self.choose_train_ope(desired[idx])
                    self.tap_confirm("train")
                    select_targets.pop(0)
                    if select_targets:
                        continue
                    tasks[0] = "scan"
            else:
                self.back_to_infrastructure()

    @fixed_selection_profile
    def choose_train_ope(self, ope: str, choose_error=0):
        found = False
        profession = "ALL"
        if ope != "阿米娅" and ope not in ["Current", "Free"]:
            profession = agent_profession[ope]
            self.profession_filter(profession)
        if ope == "Free":
            self.profession_filter("ALL")
        right_swipe = 0
        max_swipe = 50
        observation = None
        previous_page = None
        while not found:
            sel, ret = self.scan_agent(
                [ope] if ope != "Free" else self.get_free_list([]),
                max_agent_count=1,
                train=True,
                observation=observation,
                respect_train_selection=ope != "Free",
            )
            observation = None
            if sel and (sel == [ope] or ope == "Free"):
                ope = sel[0]
                found = True
                break
            if right_swipe >= max_swipe:
                raise AgentSelectionNotReady("训练干员搜索达到上限，返回房间重试")
            if (
                not self.low_frame_rate_mode
                and right_swipe >= 3
                and ret == previous_page
            ):
                if choose_error >= 2:
                    logger.warning(
                        f"训练位干员列表中未找到 ['{ope}']，请检查是否为 ['{ope}'] 设置了特别关注"
                    )
                if hasattr(self, "choose_error") and self.choose_error is not None:
                    self.choose_error.add(ope)
                raise AgentSelectionNotReady("训练干员列表已到末尾，返回房间重试")
            previous_page = ret
            moved, observation = self.swipe_agent_page(
                ret, [ope], train=True, return_page=True
            )
            right_swipe += moved
        right_swipe = self.swipe_left(
            right_swipe, special_filter=profession, train=True
        )
        self.ctap((1280, 60), 0.3)
        self.ctap((1280, 60), 0.3)
        logger.debug("验证训练位干员选择")
        if not self.verify_agent([ope], "train", train=True):
            logger.debug([ope])
            raise Exception("检测到干员选择错误，重新选择")
        self.last_room = "train"

    def get_free_list(
        self,
        agents: list[str] = None,
        *,
        include_full=False,
        current_resident="",
        room=None,
    ) -> list[str]:
        agents = agents or []
        candidates = self.get_dorm_candidates(
            agents, current_resident=current_resident, room=room
        )
        return candidates.filling if include_full else candidates.recovering

    def get_dorm_candidates(self, agents=(), *, current_resident="", room=None):
        excluded, _ = dorm_task_reservations(
            self.op_data, [self.task, *getattr(self, "tasks", [])], agents
        )
        residents = set(current_resident.split(",")) | set(
            getattr(self.task, "dorm_mood_residents", ())
        )
        if room is not None:
            residents = {
                name
                for name in residents
                if (op := self.op_data.operators.get(name)) is not None
                and op.current_room == room
            }
        return dorm_candidates(self.op_data, excluded, current_residents=residents)

    def dorm_mood_fallback_candidates(self, agents, room, candidates=None):
        """缓存无人需休息时仍搜索未知空闲者；原住者可参加最低心情比较。"""
        task = getattr(self, "task", None)
        if (
            (not room.startswith("dorm"))
            or task is None
            or task.type == TaskTypes.FIAMMETTA
        ):
            return []
        if candidates is None:
            candidates = self.get_dorm_candidates(
                agents,
                current_resident=(
                    task.meta_data if task.type == TaskTypes.RELEASE_DORM else ""
                ),
                room=room,
            )
        names = candidates.filling
        if (
            getattr(self.op_data, "idle_dorm_search_exhausted", False)
            and not candidates.estimated_recovering
        ):
            return []
        if (
            not any(
                not self.op_data.operators[name].current_room
                for name in candidates.recovering
            )
            and candidates.unknown
        ):
            # 空床、普通补床和清退共用游戏心情升序确认，未知缓存不能关闭搜索。
            return names
        resident_names = list(getattr(task, "dorm_mood_residents", ()))
        if task.type == TaskTypes.RELEASE_DORM:
            resident_names.extend(task.meta_data.split(","))
        if not resident_names:
            return []
        residents = [
            op
            for name in resident_names
            if (op := self.op_data.operators.get(name)) is not None
            and op.current_room == room
            and has_resting_mood(op)
            and resting_mood(op) >= op.upper_limit
            and not self.op_data.skip_idle_dorm_release(name)
            and not self.op_data.has_rest_mood_limit(name)
        ]
        if not residents:
            return []
        if self.op_data.config.mood_limits is None or not any(
            resting_mood(self.op_data.operators.get(name)) < resting_mood(current)
            for current in residents
            for name in names
        ):
            return []
        return names

    def preserve_resting_crafters(self, agents, room):
        """按统一层级解析 Free，并让实际选人遵守正在休息者的接管规则。"""
        if not room.startswith("dorm") or (
            getattr(getattr(self, "task", None), "type", None) == TaskTypes.FIAMMETTA
        ):
            return
        capacity_plan = dict(getattr(self.task, "plan", {}) or {})
        capacity_plan[room] = agents
        # 补床任务入队后名单也可能改变；执行时重新检查明确写入的姓名。
        for index, name in enumerate(agents):
            current = self.op_data.get_current_operator(room, index)
            if (
                getattr(self.task, "simple_dorm_fill", False)
                and current is not None
                and current.name == name
            ):
                continue
            if (
                name not in ("", "Current", "Free")
                and self.op_data.is_dynamic_dorm_position(room, index, name)
                and (
                    resting_tier(self.op_data, name) == RestingTier.EXCLUDED
                    or (
                        (current is None or current.name != name)
                        and not self.op_data.dorm_capacity_allows(
                            name, (room, index), plan=capacity_plan
                        )
                    )
                )
            ):
                agents[index] = "Free"
        moving = (
            {
                name
                for target_room, names in self.task.plan.items()
                for target_index, name in enumerate(names)
                if name not in ("Current", "Free", "")
                and (
                    (op := self.op_data.operators.get(name)) is None
                    or (op.current_room, op.current_index)
                    != (target_room, target_index)
                )
            }
            if self.task is not None
            else set()
        )
        # 名单可能在任务入队后才修改；已写明新入住者的旧补床任务也须保床。
        # 本次已明确上班或换床的原入住者不受保护，个人上限任务仍可离宿。
        for index in range(len(agents)):
            current = self.op_data.get_current_operator(room, index)
            if (
                current is not None
                and current.name not in (set(agents) | moving)
                and self.op_data.is_free_room_excluded(current.name)
                and self.op_data.is_dynamic_dorm_position(room, index, current.name)
                and not (
                    getattr(self.task, "strict_mood_limit", False)
                    and self.task.meta_data == current.name
                )
            ):
                agents[index] = current.name
        if "Free" not in agents:
            return
        now = datetime.now()
        current_resident = (
            self.task.meta_data
            if self.task is not None and self.task.type == TaskTypes.RELEASE_DORM
            else ""
        )
        candidates = self.get_dorm_candidates(
            agents, current_resident=current_resident, room=room
        )
        mood_fallback = self.dorm_mood_fallback_candidates(agents, room, candidates)
        replacements = [
            self.op_data.operators[name]
            for name in candidates.recovering
            if not self.op_data.operators[name].current_room
        ]
        for index, name in enumerate(agents):
            if name != "Free":
                continue
            current = self.op_data.get_current_operator(room, index)
            if (
                current is not None
                and resting_tier(self.op_data, current.name) == RestingTier.EXCLUDED
            ):
                # 满员兜底也不能重新安排被排除的原住者。
                current = None
            eligible = [
                candidate
                for candidate in replacements
                if self.op_data.dorm_capacity_allows(
                    candidate.name, (room, index), plan=capacity_plan
                )
            ]
            replacement = next(iter(eligible), None)
            if (
                current is not None
                and self.op_data.is_dynamic_dorm_position(room, index, current.name)
                and current.name not in (set(agents) | moving)
                and not (
                    getattr(self.task, "strict_mood_limit", False)
                    and self.task.meta_data == current.name
                )
                and not self.op_data.rest_mood_complete(current.name)
                and not (
                    getattr(self.task, "type", None) == TaskTypes.RELEASE_DORM
                    and self.task.release_dorm_targets().get(current.name)
                    == (room, index)
                )
            ):
                replacement = next(
                    (
                        candidate
                        for candidate in eligible
                        if bed_takeover_allowed(
                            self.op_data, candidate.name, current.name
                        )
                    ),
                    None,
                )
                if replacement is None:
                    agents[index] = current.name
                    continue
            if mood_fallback and (
                current is None
                or has_resting_mood(current, now)
                and resting_mood(current, now) >= current.upper_limit
                and not self.op_data.is_free_room_excluded(current.name)
            ):
                # 保留 Free，实际选人时从心情升序列表第一页开始找。
                continue
            if (
                current is not None
                and getattr(self.task, "strict_mood_limit", False)
                and self.task.meta_data == current.name
                and self.op_data.has_rest_mood_limit(current.name)
            ):
                # 上限释放必须真正换出本人，不能被主班床位保护抵消。
                current = None
            if current is not None and current.name in (set(agents) | moving):
                current = None
            if current is not None:
                mood = resting_mood(current, now)
                bed = next(
                    (d for d in self.op_data.dorm if d.position == (room, index)),
                    None,
                )
                full = (
                    has_resting_mood(current, now) and mood >= current.upper_limit
                ) or (bed is not None and bed.time is not None and bed.time <= now)
                slot = self.op_data.plan[room][index]
                if (
                    current.is_high()
                    and not full
                    and self.op_data.is_auto_free_dorm_slot(room, index)
                    and slot.agent == current.name
                ):
                    continue
                if not full:
                    if (
                        replacement is None
                        or bed is None
                        or not self.op_data._slot_takable(
                            bed, requester=replacement.name, plan=capacity_plan
                        )
                    ):
                        agents[index] = current.name
                        continue
            if replacement is not None:
                agents[index] = replacement.name
                replacements.remove(replacement)
            elif (
                current is not None
                and self.op_data.is_dynamic_dorm_position(room, index, current.name)
                and not self.op_data.rest_mood_complete(current.name)
            ):
                # 无人需要接替时保留原住者，满心情本身不应制造空床。
                agents[index] = current.name
                if has_resting_mood(current, now) and mood >= current.upper_limit:
                    current.dorm_mood_fallback = room
                    logger.info(
                        f"{room} 保留满心情干员 {current.name}："
                        "没有缓存有效且需要恢复的空闲候选，优先保持宿舍满员"
                    )
            else:
                full_candidates = [
                    name
                    for name in candidates.filling
                    if name not in candidates.recovering
                    and name not in candidates.unknown
                    and name not in agents
                    and self.op_data.dorm_capacity_allows(
                        name, (room, index), plan=capacity_plan
                    )
                    and (
                        name not in self.op_data.operators
                        or not self.op_data.operators[name].current_room
                    )
                ]
                known = next(iter(full_candidates), None)
                if known is not None:
                    if known in self.op_data.operators:
                        agents[index] = known
                        self.op_data.operators[known].dorm_mood_fallback = room
                    else:
                        agents[index] = "Free"
                else:
                    # 未知心情统一交给游戏页面，不能直接按默认24指定姓名。
                    agents[index] = "Free" if candidates.unknown else ""
        # 游戏确认后会把空位挤到末尾，后续读房和恢复计时使用同一位置。
        if "Current" not in agents:
            agents[:] = [name for name in agents if name] + [""] * agents.count("")
        return [name for name in mood_fallback if name not in agents]

    def prepare_dorm_selection(self, agents, room, *, preserve_dorm_occupants=False):
        """执行边界统一解析名单；解析结果同时交给单回排序和实际选人。"""
        # 充能和归位均使用肥鸭任务的明确名单；不养闲人、上限清退及
        # 普通补床不能把充能对象改成 Free，也不能用原入住者覆盖它。
        if getattr(getattr(self, "task", None), "type", None) == TaskTypes.FIAMMETTA:
            return []
        current_list = set()
        for idx, n in enumerate(agents):
            if getattr(getattr(self, "task", None), "simple_dorm_fill", False):
                current = self.op_data.get_current_operator(room, idx)
                if current is not None and current.name == n:
                    current_list.add(n)
                    continue
            if n not in current_list:
                current_list.add(n)
            elif n not in ("", "Free", "Current"):
                agents[idx] = "Free"
            if (
                room.startswith("dorm")
                and agents[idx] in self.op_data.operators
                and self.op_data.rest_mood_complete(agents[idx])
                and self.op_data.is_dynamic_dorm_position(room, idx, agents[idx])
            ):
                self.op_data.operators[agents[idx]].depletion_rate = 0
                expected = getattr(
                    getattr(self, "task", None), "group_shift_expected", {}
                )
                if expected.get((room, idx)) == agents[idx]:
                    # 恢复目标在执行边界合法取消，不再要求重新入住才能确认换班。
                    expected.pop((room, idx))
                agents[idx] = "Free"
                logger.info("检测个人心情上限释放休息位")
        if not preserve_dorm_occupants:
            fallback = self.preserve_resting_crafters(agents, room) or []
            expected = getattr(getattr(self, "task", None), "group_shift_expected", {})
            relocated = {}
            for slot, name in list(expected.items()):
                if slot[0] == room and name in agents:
                    # 空位整理可移动其他恢复目标；确认位置跟随最终名单。
                    relocated[room, agents.index(name)] = name
                    expected.pop(slot)
            expected.update(relocated)
            return fallback
        return []

    @timed_step("selection")
    @fixed_selection_profile
    def choose_agent(
        self,
        agents: list[str],
        room: str,
        fast_mode=True,
        train_index=0,
        preserve_dorm_occupants=False,
        choose_error=0,
        dorm_mood_candidates=None,
    ) -> None:
        """
        :param order: ArrangeOrder, 选择干员时右上角的排序功能
        """
        max_swipe = 50
        clear_interval = 0.3 if self.performance_profile.mode == "high" else 0.5
        if getattr(getattr(self, "task", None), "emergency_staffing", False):
            fast_mode = False
        mood_fallback = (
            self.prepare_dorm_selection(
                agents,
                room,
                preserve_dorm_occupants=preserve_dorm_occupants,
            )
            if dorm_mood_candidates is None
            else dorm_mood_candidates
        )
        fallback_selected = []
        # Free 已尝试满心情和未登记空闲者兜底，明确留空的位置不参与选人。
        if "" in agents:
            fast_mode = False
            agents = [item for item in agents if item != ""]
        if (not agents) and not fast_mode:
            self.tap(
                (self.recog.w * 0.38, self.recog.h * 0.95), interval=clear_interval
            )
        agent = copy.deepcopy(agents)
        exists = []
        if fast_mode:
            current_room = self.op_data.get_current_room(room, True)
            if room.startswith("dorm"):
                self.profession_filter()
                # 缓存只提供名单，差量取消必须使用页面实际卡片顺序。
                # 意外入住或缺人时完整重选，不能把错人当作原宿管保留。
                current_room = self.wait_for_arranged_agents(
                    [n for n in current_room if n], ordered=False
                )
                if current_room is None:
                    logger.info(f"{room} 实际已选名单与缓存不一致，改为完整选人")
                    fast_mode = False
                    current_room = []
            # 如果空位置进房间会被向前挤
            # 训练室的协助位和训练位固定，空协助位不能让训练位前移。
            if room != "train":
                current_room = sorted(current_room, key=lambda x: x == "")
            differences = []
            for i in range(len(current_room)):
                if current_room[i] not in agents:
                    differences.append(i)
                else:
                    exists.append(current_room[i])
            if room == "train":
                differences = [x for x in differences if x == train_index]
            for pos in differences:
                if current_room[pos] != "":
                    self.tap(
                        (
                            self.recog.w * self.agent_selection_positions[pos][0],
                            self.recog.h * self.agent_selection_positions[pos][1],
                        ),
                        interval=0.2 if self.low_frame_rate_mode else 0,
                    )
            agent = [x for x in agents if x not in exists]
        logger.info(f"安排干员 ：{agent}")
        # 若不是空房间，则清空工作中的干员
        is_dorm = room.startswith("dorm")
        not_production = not room.startswith("room")
        first_time = True
        # 在 agent 中 'Free' 表示任意空闲干员
        free_num = agent.count("Free")
        for i in range(agent.count("Free")):
            agent.remove("Free")
        single_visible_target = (
            room.startswith("room") and free_num == 0 and len(agent) == 1
        )
        index_change = False
        pre_order = ["技能", False]
        right_swipe = 0
        retry_count = 0
        selected = []
        logger.debug(f"上次进入房间为：{self.last_room},本次房间为：{room}")
        self.profession_filter()
        if self.detect_arrange_order(room)[0] == "信赖值":
            self.switch_arrange_order("工作状态", room)
        siege = False  # 推进之王
        last_special_filter = "ALL"
        start_time, finish_time = datetime.now(), datetime.now()
        observation = None
        previous_page = None
        while len(agent) > 0:
            if retry_count > 1:
                raise Exception("到达最大尝试次数 1次")
            if right_swipe > max_swipe:
                # 到底了则返回再来一次
                self.choose_error.add(agent[0])
                raise Exception("重试一次")
            if first_time:
                # 清空
                if is_dorm:
                    self.switch_arrange_order("心情", room, "true")
                    pre_order = [3, "true"]
                if not fast_mode:
                    self.tap(
                        (self.recog.w * 0.38, self.recog.h * 0.95),
                        interval=clear_interval,
                    )
                changed, ret = self.scan_agent(
                    agent, full_scan=last_special_filter == "ALL"
                )
                if changed:
                    selected.extend(changed)
                    if len(agent) == 0:
                        break
                    index_change = True

            # 如果选中了人，则可能需要重新排序
            if index_change or first_time:
                # 第一次则调整
                is_custom, arrange_type = self.get_order(agent[0])
                if is_dorm and not (
                    agent[0] in self.op_data.operators.keys()
                    and self.op_data.operators[agent[0]].room.startswith("dormitory")
                ):
                    arrange_type = ("心情", "true")
                # 如果重新排序则复位到列表起点
                if pre_order[0] != arrange_type[0] or pre_order[1] != arrange_type[1]:
                    self.switch_arrange_order(arrange_type[0], room, arrange_type[1])
                    if not siege:
                        if single_visible_target and len(agent) == 1:
                            # 单个生产房目标已经可见时先选择，最终刷新排序并校验完整名单。
                            changed, ret = self.scan_agent(
                                agent, full_scan=last_special_filter == "ALL"
                            )
                            if changed:
                                selected.extend(changed)
                                logger.debug(
                                    f"排序后已在当前页选中目标{changed}，继续最终名单校验"
                                )
                                break
                        right_swipe, observation = self.swipe_left(
                            right_swipe, last_special_filter, return_page=True
                        )
                    pre_order = arrange_type
            first_time = False
            if (
                not siege
                and not is_dorm
                and agent
                and all(element in self.op_data.profession_filter for element in agent)
            ):
                siege = True
                if agent[0] in self.op_data.profession_filter:
                    profession = agent_profession[agent[0]]
                    if last_special_filter != profession:
                        self.profession_filter(profession)
                        right_swipe = 0
                    last_special_filter = profession
            elif agent and agent[0] in agent_list:
                if (is_dorm or not_production) and agent[0] != "阿米娅":
                    # 在宿舍并且不是阿米娅则打开职介筛选
                    profession = agent_profession[agent[0]]
                    if last_special_filter != profession:
                        self.profession_filter(profession)
                        right_swipe = 0
                        if index_change:
                            self.switch_arrange_order("心情", room, "true")
                    last_special_filter = profession
                elif (
                    (is_dorm or not_production)
                    and agent[0] == "阿米娅"
                    and last_special_filter != "ALL"
                ):
                    # 如果是阿米娅且filter 不是all
                    self.profession_filter("ALL")
                    right_swipe = 0
                    last_special_filter = "ALL"
                if (
                    not self.low_frame_rate_mode
                    and agent[0] in self.op_data.operators
                    and self.op_data.operators[agent[0]].is_resting()
                    and fast_mode
                    and is_dorm
                    and agent[0] != "阿米娅"
                    and agent[0] not in self.choose_error
                ):
                    # 普通设备保留休息干员的末页快路；低帧率设备逐页确认。
                    swipe_map = [20, 3, 5, 3, 3, 3, 3, 3, 3]
                    right_swipe = swipe_map[
                        self.profession_labels.index(last_special_filter)
                    ]
                    for _ in range(right_swipe):
                        self.swipe_noinertia(
                            (0.8 * self.recog.w, 0.5 * self.recog.h),
                            (-1900, 0),
                            interval=0,
                        )
                    self.sleep(0.5 if self.performance_profile.mode == "high" else 1)
            changed, ret = self.scan_agent(
                agent,
                full_scan=last_special_filter == "ALL",
                observation=observation,
            )
            observation = None
            if changed:
                selected.extend(changed)
                # 如果找到了
                index_change = True
                siege = False
            else:
                index_change = False
                if (
                    not self.low_frame_rate_mode
                    and right_swipe >= 3
                    and ret == previous_page
                ):
                    if choose_error >= 2:
                        if room == "train":
                            logger.warning(
                                f"训练位干员列表中未找到 ['{agent[0]}']，请检查是否为 ['{agent[0]}'] 设置了特别关注"
                            )
                    if hasattr(self, "choose_error") and self.choose_error is not None:
                        self.choose_error.add(agent[0])
                    raise AgentSelectionNotReady("干员列表已到末尾，返回房间重试")
                previous_page = ret
                moved, observation = self.swipe_agent_page(
                    ret, agent, full_scan=last_special_filter == "ALL", return_page=True
                )
                right_swipe += moved
            if len(agent) == 0:
                if siege:
                    if last_special_filter != "ALL":
                        right_swipe = 0
                break

        # 安排空闲干员
        if free_num:
            if free_num == len(agents):
                self.tap(
                    (self.recog.w * 0.38, self.recog.h * 0.95), interval=clear_interval
                )
            if last_special_filter != "ALL":
                # Free 搜索的目标就是 ALL；真实切换本身会复位列表，
                # 无需先恢复原职业再切一次 ALL。
                self.profession_filter("ALL")
                last_special_filter = "ALL"
                right_swipe = 0
            elif not first_time:
                right_swipe = self.swipe_left(right_swipe, last_special_filter)
            self.switch_arrange_order("心情", room, "true")
            # 满心情兜底按游戏心情顺序选人，普通补床仍遵守宿舍层级。
            free_list = (
                list(mood_fallback)
                if mood_fallback
                else self.get_free_list(agents, room=room)
            )
            idle_fallback = not free_list
            if idle_fallback:
                free_list = self.get_free_list(agents, include_full=True, room=room)
            if mood_fallback or idle_fallback:
                right_swipe = self.swipe_left(right_swipe, last_special_filter)
            selection_time = datetime.now()
            estimates = getattr(self.op_data, "dorm_mood_estimates", None)
            # 有可保留的实读满心情住客时，先筛选低心情卡片，避免满员试住。
            resident_names = list(getattr(self.task, "dorm_mood_residents", ()))
            if self.task is not None and self.task.type == TaskTypes.RELEASE_DORM:
                resident_names.extend(self.task.meta_data.split(","))
            retainable = [
                name
                for name in dict.fromkeys(resident_names)
                if name in free_list
                and (op := self.op_data.operators.get(name)) is not None
                and op.current_room == room
                and has_resting_mood(op)
                and resting_mood(op) >= op.upper_limit
                and not self.op_data.has_rest_mood_limit(name)
            ]
            screening = bool(
                mood_fallback and estimates is not None and len(retainable) >= free_num
            )
            observation = None
            previous_page = None
            while free_num:
                if room.startswith("dorm"):
                    capacity_plan = dict(getattr(self.task, "plan", {}) or {})
                    capacity_plan[room] = agents
                    bed_position = (room, agents.index("Free"))
                    free_list = [
                        name
                        for name in free_list
                        if self.op_data.dorm_capacity_allows(
                            name, bed_position, plan=capacity_plan
                        )
                    ]
                    if not free_list and not idle_fallback:
                        idle_fallback = True
                        free_list = self.get_free_list(
                            agents, include_full=True, room=room
                        )
                        right_swipe = self.swipe_left(right_swipe, last_special_filter)
                        observation, previous_page = None, None
                        continue
                if not free_list or right_swipe > max_swipe:
                    raise Exception("没有找到足够的可用宿舍候选干员")
                # scan_agent 按屏幕顺序点击，单纯排序名单不能保证层级和心情顺序。
                # 一次只允许选择当前最高优先级、最低已知心情的候选。
                if not (mood_fallback or idle_fallback):
                    first_key = resting_key(self.op_data, free_list[0], selection_time)
                    candidates = [
                        name
                        for name in free_list
                        if resting_key(self.op_data, name, selection_time) == first_key
                    ]
                else:
                    candidates = (
                        list(free_list) if mood_fallback or idle_fallback else free_list
                    )
                crafting = set(crafting_rest_candidates(self.op_data, free_list))
                if crafting:
                    boundary = next(
                        i for i, name in enumerate(free_list) if name in crafting
                    )
                    permitted = set(free_list[:boundary] if boundary else free_list[:1])
                    candidates = [name for name in candidates if name in permitted]
                selected_name, ret = self.scan_agent(
                    candidates,
                    max_agent_count=1
                    if room.startswith("dorm")
                    and any(
                        resting_tier(self.op_data, name)
                        <= RestingTier.PRIORITY_REPLACEMENT
                        for name in candidates
                    )
                    else free_num,
                    full_scan=last_special_filter == "ALL",
                    observation=observation,
                    mood_estimates=estimates,
                    skip_full_mood=screening,
                )
                observation = None
                if screening and not selected_name:
                    visible = [name for name, _ in ret if name in candidates]
                    # 心情升序的首个合格候选已是满条，其后的候选不必逐个试住。
                    if (
                        visible
                        and (estimate := estimates.get(visible[0])) is not None
                        and estimate[0] >= 24
                    ):
                        free_list = [
                            name
                            for name in retainable
                            if name in free_list and name not in agents
                        ][:free_num]
                        screening = False
                        previous_page = None
                        right_swipe = self.swipe_left(right_swipe, last_special_filter)
                        logger.info("选人页合格候选已是满条，保留实读满心情住客")
                        continue
                selected.extend(selected_name)
                if mood_fallback or idle_fallback:
                    fallback_selected.extend(selected_name)
                free_num -= len(selected_name)
                changed = bool(selected_name)
                while len(selected_name) > 0:
                    agents[agents.index("Free")] = selected_name[0]
                    free_list.remove(selected_name[0])
                    selected_name.remove(selected_name[0])
                if free_num == 0:
                    break
                elif changed:
                    right_swipe = self.swipe_left(right_swipe, last_special_filter)
                else:
                    if right_swipe >= max_swipe:
                        raise AgentSelectionNotReady(
                            "空闲干员搜索达到上限，返回房间重试"
                        )
                    if (
                        not self.low_frame_rate_mode
                        and right_swipe >= 3
                        and ret == previous_page
                    ):
                        raise AgentSelectionNotReady(
                            "空闲干员列表已到末尾，返回房间重试"
                        )
                    previous_page = ret
                    moved, observation = self.swipe_agent_page(
                        ret,
                        free_list,
                        full_scan=last_special_filter == "ALL",
                        return_page=True,
                    )
                    right_swipe += moved
        # 重排按完整已选名单的位置点击，不能保留最后一名干员的职业筛选。
        # 单回暂留名单没有 Free，也必须在重排和校验前恢复全部职业。
        if last_special_filter != "ALL":
            self.profession_filter("ALL")
            last_special_filter = "ALL"
            right_swipe = 0
        # 排序
        verified = False
        reordered = False
        if len(agents) != 1:
            self.switch_arrange_order("技能", room)
            # 未翻页时先定位目标卡片，名字匹配后无需再切筛选复位。
            exists = None
            if right_swipe == 0:
                try:
                    exists = self.wait_for_arranged_agents(agents, ordered=False)
                except AgentSelectionPageChanged:
                    raise
                except AgentSelectionNotReady:
                    logger.debug("当前已选名单尚不能确认，筛选复位后再校验")
            if exists is None:
                right_swipe, observation = self.swipe_left(
                    right_swipe, last_special_filter, return_page=True
                )
                exists = self.wait_for_arranged_agents(
                    agents, ordered=False, observation=observation
                )
            if exists is None:
                raise Exception("检测到干员选择错误，重新选择")
            logger.info(exists)
            # 蓝框只说明卡片被选中；返回名单按页面位置排序，不能由此推断
            # 卡片上的选择编号。即使页面顺序恰好等于目标也须重新按目标点击。
            if any(a not in exists for a in agents):
                raise Exception("检测到干员选择错误，重新选择")
            if agents:
                # 按目标顺序完成点击后统一校验完整名单。
                self.reorder_selected_agents(agents, exists)
                reordered = True
            else:
                # 空目标没有需要重排和校验的卡片。
                verified = True
        if not verified:
            logger.debug("验证干员选择..")
            self.switch_arrange_order("技能", room)
            verify_options = {"ordered": False} if reordered else {}
            if right_swipe == 0:
                try:
                    verified = self.verify_agent(agents, room, **verify_options)
                except AgentSelectionPageChanged:
                    raise
                except AgentSelectionNotReady:
                    logger.debug("当前已选顺序尚不能确认，筛选复位后再校验")
            if not verified:
                _, observation = self.swipe_left(
                    right_swipe, last_special_filter, return_page=True
                )
                verified = self.verify_agent(
                    agents, room, observation=observation, **verify_options
                )
        finish_time = datetime.now()
        if finish_time - start_time > timedelta(seconds=15) * len(agents):
            # 如果超过5分钟，则所有里面的干员自动用职介筛选
            for agent in agents:
                if agent != "阿米娅" and agent:
                    logger.debug(f"检测到{agent}选择时间过长，自动使用职介筛选")
                    self.op_data.profession_filter.add(agent)
        if not verified:
            logger.debug(agents)
            logger.debug(room)
            raise Exception("检测到干员选择错误，重新选择")
        self.last_room = room
        if fallback_selected and self.task is not None:
            # 查找机会由所有宿舍共享，必须等实际读回心情才判定耗尽。
            pending = getattr(self.task, "idle_dorm_search_names", {})
            pending.setdefault(room, set()).update(fallback_selected)
            self.task.idle_dorm_search_names = pending
        for name in fallback_selected:
            if name not in self.op_data.operators:
                self.op_data.add(Operator(name, ""))
            self.op_data.operators[name].dorm_mood_fallback = room
            self.op_data.operators[name].dorm_mood_peers = {
                peer: self.op_data.operators[peer].time_stamp
                for peer in mood_fallback
                if peer != name and peer in self.op_data.operators
            }
            logger.info(f"按心情升序补入{name}；读满后停止连续试住，个人上限仍强制离宿")

    def reset_room_time(self, room):
        for _operator in self.op_data.operators.keys():
            if self.op_data.operators[_operator].room == room:
                self.op_data.operators[_operator].time_stamp = None

    @timed_step("room_detail")
    def turn_on_room_detail(self, room):
        for enter_times in range(3):
            pending = False
            for retry_times in range(19):
                if self.find("connecting"):
                    self.sleep()
                elif room == "recycle" and self.find("recycle/dashboard"):
                    # 材料转化页没有进驻信息按钮，先回到房间视图。
                    self.back()
                elif pos := self.find("room_detail"):
                    if all(self.get_color((1233, 1)) > [252] * 3):
                        return
                    logger.info("等待动画")
                    self.sleep(interval=0.5)
                elif (pos := self.find("arrange_check_in")) or (
                    pos := self.find("arrange_check_in_small")
                ):
                    if pending:
                        pending = False
                        self.sleep(0.2)
                    else:
                        self.tap(pos, interval=0.2)
                        pending = True
                else:
                    self.sleep()
            if (
                not self.find("connecting")
                and self.find("room_detail")
                and all(self.get_color((1233, 1)) > [252] * 3)
            ):
                return
            for back_time in range(3):
                if pos := self.find("control_central"):
                    break
                self.back()
            if not pos:
                self.back_to_infrastructure()
            self.enter_room(room)
        self.reset_room_time(room)
        raise Exception("未成功进入房间")

    def scroll_room_operators(self, *, bottom):
        """滚动房间详情名单；弹窗或滚动不生效时交回原有房间重试。"""
        point = (1800, 930 if bottom else 138)
        direction = -1 if bottom else 1
        self.recog.update()
        for attempt in range(7):
            if self.find("confirm") or self.find("double_confirm/main"):
                raise RecognizeError("读取房间名单时出现确认弹窗，返回场景导航处理")
            if not self.find("room_detail"):
                raise RecognizeError("读取房间名单时已离开房间详情，重新定位")
            if self.get_color(point)[0] <= 51:
                return
            if attempt == 6:
                break
            self.swipe(
                (self.recog.w * 0.8, self.recog.h * 0.5),
                (0, direction * self.recog.h * 0.45),
                duration=500,
                interval=1,
            )
        raise RecognizeError("房间名单滚动六次仍未到达边界，返回房间重试")

    def get_agent_from_room(
        self,
        room,
        read_time_index=None,
        related_operators=None,
        *,
        departing_plan=None,
        force_mood=False,
    ):
        # 只观察真实读房；初始化试住和肥鸭临时换位不产生新的休息周期。
        released_support = None
        if self._can_refresh_idle_dorm_search():
            released_support = self.op_data.get_current_operator("train", 0)
        retain_dorm_time = room.startswith("dorm")
        if read_time_index is None:
            read_time_index = []
        if related_operators is None:
            related_operators = {}
        swap_target = None
        swap_recorded_at = None
        swap_target_snapshot = None
        swap_moods = {}
        if (
            related_operators
            and self.task is not None
            and self.task.type == TaskTypes.FIAMMETTA
            and self.task.meta_data in self.op_data.operators
        ):
            swap_target = self.task.meta_data
            swap_recorded_at = datetime.now()
            target = self.op_data.operators[swap_target]
            swap_target_snapshot = {
                "agent_current_room": target.current_room,
                "is_high": target.is_high(),
                "agent_group": target.group,
            }
        if room == "meeting" and not self.leifeng_mode:
            self.sleep(0.5)
            self.recog.update()
            clue_res = self.read_screen(
                self.recog.img, limit=10, cord=((439, 987), (577, 1033))
            )
            if clue_res != 11:
                self.clue_count = clue_res
                logger.info(f"当前拥有线索数量为{self.clue_count}")
        self.refresh_facility_state(room)
        self.turn_on_room_detail(room)
        # 如果是宿舍则全读取
        if room.startswith("dorm"):
            if self.task is not None and self.task.type == TaskTypes.FIAMMETTA:
                # 充能时菲亚梅塔会被临时换到任务指定的槽位，
                # 与静态排班中的位置无关；保留 agent_arrange 传入的
                # 实际槽位，否则无法采样并记录本次充能对象。
                read_time_index = list(dict.fromkeys(read_time_index))
            else:
                dorm_read_time_index = [
                    i
                    for i, obj in enumerate(self.op_data.plan[room])
                    if obj.agent in ("Free", "菲亚梅塔")
                ]
                read_time_index = list(
                    dict.fromkeys([*read_time_index, *dorm_read_time_index])
                )
        self.wait_product_complete()
        if room in RIGHT_SIDE_ROOM_CAPACITY:
            length = RIGHT_SIDE_ROOM_CAPACITY[room]
        else:
            length = len(self.op_data.plan[room])
        if length > 3:
            self.scroll_room_operators(bottom=False)
        slot_x = (1288, 1869)
        slot_y = [(135, 326), (344, 535), (553, 744), (532, 723), (741, 932)]
        slot_p = [tuple(zip(slot_x, y)) for y in slot_y]
        # 姓名从 x≈1470 开始；整张槽位卡片含头像和心情条，模板只保留
        # 左上角 265×46 像素时会截断长姓名。空槽检测仍使用完整槽位范围。
        name_x = (1460, 1785)
        name_p = [tuple(zip(name_x, (top + 25, top + 80))) for top, _ in slot_y]
        time_x = (1650, 1780)
        time_y = [(270, 305), (480, 515), (690, 725), (668, 703), (877, 912)]
        time_p = [tuple(zip(time_x, y)) for y in time_y]
        mood_x = (1470, 1780)
        mood_y = (219, 428, 637, 615, 823)
        mood_y = [(y, y + 1) for y in mood_y]
        mood_p = [tuple(zip(mood_x, y)) for y in mood_y]
        result = []
        swiped = False
        for i in range(0, length):
            if i >= 3 and not swiped:
                self.scroll_room_operators(bottom=True)
                swiped = True
            data = {}
            _name = ""
            for read_try in range(3):
                if self.find("infra_no_operator", scope=slot_p[i]):
                    _name = ""
                    break
                _name = self.read_screen(
                    cropimg(self.recog.gray, name_p[i]), type="name"
                )
                if _name != "":
                    break
                if read_try < 2:
                    logger.debug(
                        f"房间 {room} 第 {i + 1} 槽位干员未识别或置信度过低，等待 0.25s 原地重试 ({read_try + 1}/2)"
                    )
                    self.sleep(0.25)
                    self.recog.update()
            _mood = 24
            # 如果房间不为空
            update_time = False
            if _name != "":
                if _name not in self.op_data.operators.keys() and _name in agent_list:
                    self.op_data.add(Operator(_name, ""))

                agent = self.op_data.operators[_name]
                previous_position = (agent.current_room, agent.current_index)
                should_read_mood = (
                    force_mood
                    or self.op_data.operators[_name].need_to_refresh(r=room)
                    or (self.tasks and self.tasks[0].type == TaskTypes.SHIFT_ON)
                    or i in read_time_index
                    or (
                        departing_plan is not None
                        and i < len(departing_plan)
                        and departing_plan[i] != "Current"
                        and _name not in departing_plan
                    )
                    or previous_position != (room, i)
                )
                if (
                    room.startswith("dorm")
                    and self.task is not None
                    and self.task.type == TaskTypes.FIAMMETTA
                    and self.task.meta_data
                    and not force_mood
                ):
                    fia_read_names = {"菲亚梅塔"}
                    if self.task.meta_data:
                        fia_read_names.add(self.task.meta_data)
                    should_read_mood = _name in fia_read_names and i in read_time_index
                refresh_fia = retain_dorm_time and _name == "菲亚梅塔"
                if refresh_fia:
                    # 充能后归位也要实读，不能沿用交换前心情或原槽位的倒计时。
                    should_read_mood = True
                    if i not in read_time_index:
                        read_time_index.append(i)
                if should_read_mood:
                    _mood = self.read_accurate_mood(cropimg(self.recog.gray, mood_p[i]))
                    update_time = True
                else:
                    _mood = self.op_data.operators[_name].current_mood()
                # 估算值只用于本次读数，保留与原采样时间配对的心情，避免重复扣减。
                update_args = (
                    _name,
                    _mood if update_time else agent.mood,
                    room,
                    i,
                    update_time,
                )
                related_operator = related_operators.get(i)
                record_kwargs = {}
                if update_time:
                    if _name == "菲亚梅塔" and related_operator:
                        record_kwargs = {
                            "related_operator": related_operator,
                            "mood_event": "fiammetta_charge",
                        }
                        if swap_recorded_at is not None:
                            record_kwargs["recorded_at"] = swap_recorded_at + timedelta(
                                seconds=1
                            )
                    if (
                        swap_recorded_at is not None
                        and _name == "菲亚梅塔"
                        and related_operator == swap_target
                    ):
                        swap_moods["before"] = _mood
                        swap_fia_snapshot = {
                            "agent_current_room": agent.current_room,
                            "is_high": agent.is_high(),
                            "agent_group": agent.group,
                        }
                    elif swap_recorded_at is not None and _name == swap_target:
                        record_kwargs = {
                            "related_operator": "菲亚梅塔",
                            "mood_event": "fiammetta_after",
                            "recorded_at": swap_recorded_at + timedelta(seconds=1),
                        }
                        swap_moods["after"] = _mood
                # 充能临时进出宿舍只更新心情采样，不清零工作消耗速度，
                # 也不把宿舍恢复或充能跳变计入工作消耗速度。
                charge_transition = (
                    self.task is not None
                    and self.task.type == TaskTypes.FIAMMETTA
                    and bool(self.task.plan)
                    and (
                        room.startswith("dorm") or agent.current_room.startswith("dorm")
                    )
                )
                if charge_transition:
                    record_kwargs["preserve_depletion_rate"] = True
                high_no_time = self.op_data.update_detail(*update_args, **record_kwargs)
                BaseSchedulerSolver._record_dorm_admission(
                    self, _name, room, i, previous_position
                )
                pending = getattr(self.task, "idle_dorm_search_names", {}).get(
                    room, set()
                )
                if update_time and _name in pending:
                    pending.discard(_name)
                    if _mood >= agent.upper_limit:
                        self.op_data.stop_idle_dorm_search()
                data["depletion_rate"] = agent.depletion_rate
                if high_no_time is not None and high_no_time not in read_time_index:
                    logger.debug(
                        f"检测到高效组休息时间数据不存在:{room},{high_no_time}"
                    )
                    read_time_index.append(high_no_time)
            else:
                _mood = -1
            data["agent"] = _name
            data["mood"] = _mood
            if (
                retain_dorm_time
                and _name != "菲亚梅塔"
                and _name in self.op_data.operators
            ):
                _, bed = self.op_data.get_dorm_by_name(_name)
                if bed is not None and bed.name == _name and bed.time is not None:
                    # 位置没变时沿用预计回满记录，换位后的缺失记录顺带读取。
                    data["time"] = bed.time
                    result.append(data)
                    continue
            if i in read_time_index and _name != "":
                exhausted_working = False
                if (
                    room == "central"
                    and room in self.op_data.true_exhaust_room
                    and _name != "菲亚梅塔"
                    and update_time
                    and _mood == 0
                    and agent.is_working()
                ):
                    # 中枢耗尽后不再显示倒计时；换帧复核房间、干员和心情，
                    # 不用缓存估算值或一次空 OCR 推断耗尽，宿舍恢复时间仍照常读。
                    self.recog.update()
                    exhausted_working = (
                        not self.find("connecting")
                        and self.find("room_detail") is not None
                        and self.detect_room() == room
                        and self.read_screen(
                            cropimg(self.recog.gray, name_p[i]), type="name"
                        )
                        == _name
                        and self.read_accurate_mood(cropimg(self.recog.gray, mood_p[i]))
                        == 0
                    )
                if exhausted_working:
                    data["time"] = datetime.now()
                    logger.debug(f"中枢干员 {_name} 已复核心情耗尽，无需读取倒计时")
                elif _mood == 24 or room in ["meeting", "factory"] and not update_time:
                    data["time"] = datetime.now()
                else:
                    logger.debug(f"开始记录时间:{room},{i}")
                    data["time"] = self.read_operator_time(room, i, time_p[i])
                self.op_data.refresh_dorm_time(room, i, data)
                if _name == "菲亚梅塔" and update_time and room.startswith("dorm"):
                    self._refresh_fiammetta_task(data["time"])
                logger.debug(f"停止记录时间:{str(data)}")
            result.append(data)
        if (
            swap_target_snapshot is not None
            and "before" in swap_moods
            and "after" in swap_moods
        ):
            save_agent_action(
                swap_target,
                swap_target_snapshot["agent_current_room"],
                room,
                swap_target_snapshot["is_high"],
                swap_target_snapshot["agent_group"],
                swap_moods["before"],
                related_operator="菲亚梅塔",
                mood_event="fiammetta_before",
                current_time=swap_recorded_at,
            )
            # 充能技能以满心情触发；补记自身交换前的 24，展示时间
            # 与实读的交换后心情相差一秒，不改写实际采样或恢复计时。
            save_agent_action(
                "菲亚梅塔",
                swap_fia_snapshot["agent_current_room"],
                room,
                swap_fia_snapshot["is_high"],
                swap_fia_snapshot["agent_group"],
                24,
                related_operator=swap_target,
                mood_event="fiammetta_charge",
                current_time=swap_recorded_at,
            )
        for _operator in self.op_data.operators.keys():
            if self.op_data.operators[
                _operator
            ].current_room == room and _operator not in [
                res["agent"] for res in result
            ]:
                if room.startswith("dorm"):
                    _idx, dorm = self.op_data.get_dorm_by_name(_operator)
                    # 该床可能已在本次读取中写入新入住者。旧入住者仍保留
                    # 旧坐标时只能清理自己的缓存，不能把新入住者一并抹掉。
                    if dorm is not None and dorm.name == _operator:
                        dorm.reset()
                self.op_data.operators[_operator].current_room = ""
                self.op_data.operators[_operator].current_index = -1
                if (
                    (room.startswith("dorm"))
                    and getattr(self.task, "strict_mood_limit", False)
                    and self.task.meta_data == _operator
                ):
                    # 实际离宿后才记账，不改写真实心情；等待原回班任务，
                    # 防止提前清退者被重新塞回宿舍或触发整组纠错。
                    op = self.op_data.operators[_operator]
                    op.rest_mood_release_limit = op.upper_limit
                if _operator == "菲亚梅塔":
                    self._refresh_fiammetta_task(None)
                if self.task is not None and self.task.type != TaskTypes.SHIFT_OFF:
                    release_task = self.find_next_task(
                        task_type=TaskTypes.RELEASE_DORM, meta_data=_operator
                    )
                    if release_task and self.task is not release_task:
                        release_task.remove_release_dorm_operator(_operator)
                        if not release_task.plan:
                            self.tasks.remove(release_task)
                logger.info(f"重设 {_operator} 至空闲")
        if released_support is not None and (
            not released_support.current_room or released_support.is_resting()
        ):
            self.op_data.refresh_idle_dorm_search(
                reason="专精协助位干员已释放", names=[released_support.name]
            )
        return result

    def refresh_current_room(self, room, current_index=None):
        _current_room = self.op_data.get_current_room(room, current_index=current_index)
        if _current_room is None:
            self.get_agent_from_room(room)
            _current_room = self.op_data.get_current_room(room, True)
        return _current_room

    def get_order_remaining_time(self):
        self._wait_drone_interface()
        # 订单剩余时间
        execute_time = self.double_read_time(
            self._run_order_time_region(),
            use_digit_reader=True,
        )
        return round((execute_time - datetime.now()).total_seconds(), 1)

    def _cancel_pending_shift_on(self, name):
        """实际重新上岗后，撤销本人的旧回班预约，保留同批其他人的动作。"""
        locks_changed = False
        for task in self.tasks[:]:
            if (
                task is getattr(self, "task", None)
                or task.type != TaskTypes.SHIFT_ON
                or getattr(task, "group_shift_expected", {})
                or not any(
                    name in names
                    for plan in (task.plan, getattr(task, "backup_shift_intent", {}))
                    for names in plan.values()
                )
            ):
                continue
            if hasattr(task, "backup_shift_intent") and not getattr(
                task, "backup_shift_active", False
            ):
                task.plan = copy.deepcopy(task.backup_shift_intent)
                del task.backup_shift_intent
                del task.backup_shift_conditions
            task.plan = {
                room: ["Current" if agent == name else agent for agent in names]
                for room, names in task.plan.items()
                if any(agent not in (name, "Current") for agent in names)
            }
            locked = getattr(task, "product_shift_locked", False)
            locks_changed |= locked
            # 只剩清床动作时也移除，不能留下无人回班的旧清床任务。
            if not any(
                agent not in ("Current", "Free", "")
                for names in task.plan.values()
                for agent in names
            ):
                self.tasks[:] = [queued for queued in self.tasks if queued is not task]
            elif locked:
                slots = {
                    (room, index)
                    for room, names in task.plan.items()
                    for index, agent in enumerate(names)
                    if agent != "Current"
                }
                self._reserve_deferred_product_shift(task, slots)
            logger.info(f"{name}已重新上岗，撤销其旧上班安排")
        if locks_changed:
            self._refresh_deferred_product_reservations()

    def _record_dorm_admission(self, name, room, index, previous_position):
        """实际入住后区分普通补床与集中恢复正式批次。"""
        if not room.startswith("dorm"):
            return
        task = getattr(self, "task", None)
        names = getattr(task, "plan", {}).get(room, [])
        if index >= len(names) or names[index] not in (name, "Free"):
            return
        op = self.op_data.operators[name]
        ordinary_plan = getattr(task, "dorm_fill_plan", {}).get(room, [])
        if (
            getattr(task, "type", None) in (TaskTypes.FILL_DORM, TaskTypes.RELEASE_DORM)
            or any(name in row for row in getattr(task, "dorm_fill_plan", {}).values())
            or index < len(ordinary_plan)
            and ordinary_plan[index] in (name, "Free")
            or getattr(task, "simple_dorm_fill", False)
        ):
            if (
                previous_position != (room, index)
                and not (previous_position[0] or "").startswith("dorm")
                and not op.is_high()
                and self.op_data.is_dynamic_dorm_position(room, index, name)
            ):
                op.temporary_dorm_fill = True
        elif getattr(task, "type", None) in (
            TaskTypes.SHIFT_OFF,
            TaskTypes.EXHAUST_OFF,
        ):
            op.temporary_dorm_fill = False

    def current_room_changed(self, instance, *, started_working=False):
        if self._initial_mood_read_pending():
            return
        # 构造干员及副表演算也可能设置位置；仅实际登记对象的上岗使预约失效。
        if self.op_data.operators.get(instance.name) is not instance:
            return
        if started_working:
            self._cancel_pending_shift_on(instance.name)
        if not self.op_data.first_init:
            logger.info(f"{instance.name} 房间变动")
            if instance.refresh_order_room[0]:
                ref_rooms = (
                    instance.refresh_order_room[1]
                    if instance.refresh_order_room[1]
                    else list(self.op_data.run_order_rooms.keys())
                )
                for ref_room in ref_rooms:
                    self.refresh_run_order_time(ref_room)
            if (
                instance.name in self.op_data.operators
                and self.op_data.operators[instance.name].refresh_drained
            ):
                self.refresh_drained_time()

    def refresh_drained_time(self):
        logger.debug("刷新用尽倒计时")
        solved = []
        for agent in self.op_data.exhaust_agent:
            if agent in solved:
                continue
            logger.debug(f"开始检查{agent}")
            shift_off = self.find_next_task(
                datetime.now() + timedelta(minutes=1),
                task_type=TaskTypes.EXHAUST_OFF,
                meta_data=agent,
                compare_type=">",
            )
            if shift_off:
                logger.info(f"移除 {shift_off.meta_data} 用尽下班任务以刷新时间")
                exhausts = shift_off.meta_data.split(",")
                solved.extend(exhausts)
                self.tasks.remove(shift_off)
                for o in exhausts:
                    self.op_data.operators[o].time_stamp = None
                self.task
            else:
                self.op_data.operators[agent].time_stamp = None
        if solved:
            self.tasks.append(
                (
                    SchedulerTask(
                        time=datetime.now(),
                        task_plan={},
                        task_type=TaskTypes.NOT_SPECIFIC,
                    )
                )
            )

    def refresh_run_order_time(self, room):
        logger.debug("检测到插拔房间人员变动！")
        limit = 15
        if run_order_task := self.find_next_task(
            datetime.now() + timedelta(minutes=limit),
            task_type=TaskTypes.RUN_ORDER,
            meta_data=room,
            compare_type=">",
        ):
            if getattr(run_order_task, "run_order_restore_pending", False):
                return
            logger.info(f"移除超过{limit}分钟的跑单任务以刷新时间")
            self.tasks.remove(run_order_task)
        run_order_task = self.find_next_task(
            datetime.now() + timedelta(minutes=limit),
            task_type=TaskTypes.RUN_ORDER,
            meta_data=room,
            compare_type="<",
        )
        if run_order_task and getattr(
            run_order_task, "run_order_restore_pending", False
        ):
            return
        if run_order_task and run_order_task.time > datetime.now():
            task_time = datetime.now()
            if len(self.tasks) > 0 and self.tasks[0].type != TaskTypes.FIAMMETTA:
                task_time = self.tasks[0].time - timedelta(seconds=1)
            logger.info(f"移除{limit}分钟以内的跑单任务以强X刷新时间")
            self.tasks.remove(run_order_task)
            logger.info("新增强X刷新跑单时间任务")
            self.tasks.append(
                (
                    SchedulerTask(
                        time=task_time,
                        task_plan={},
                        task_type=TaskTypes.REFRESH_TIME,
                        meta_data=room,
                    )
                )
            )

    def ensure_dorm_recovery_order(self, room, agents, fast_mode=True):
        """先确认单回目标的入驻顺序，再由原任务恢复完整阵容。

        中间名单只用于这次点击，不能覆盖持久化任务中的完整恢复名单。
        目标及垫位结果均识别成功后才记录；床位未变时不重复确认。
        """
        from arknights_mower.utils.dorm_recovery import (
            recovery_managers,
            recovery_order_plan,
            recovery_target,
        )

        if not room.startswith("dorm") or self.task.type == TaskTypes.FIAMMETTA:
            return False
        pending = getattr(self.task, "dorm_recovery_restore", [])
        if (getattr(self.task, "simple_dorm_fill", False)) and room not in pending:
            return False
        reserved_names = {
            name
            for task in self.tasks
            for task_room, names in task.plan.items()
            if task is not self.task or task_room != room
            for name in names
        }
        retained = recovery_order_plan(self.op_data, room, agents, reserved_names)
        if retained is None:
            return room in pending
        target = recovery_target(self.op_data, room, agents)
        vip_index = agents.index(target.name)
        # 一轮下班先替班接岗、再分床；不要为即将被下一条分床任务换走的
        # 原占位者额外清房。以队列中明确的目标覆盖为准，不猜测未来排班。
        for task in self.tasks:
            upcoming = task.plan.get(room, [])
            if (
                task is not self.task
                and self.task.time <= task.time <= self.task.time + timedelta(seconds=1)
                and len(upcoming) > vip_index
                and upcoming[vip_index] not in ("Current", "Free", "", target.name)
            ):
                return room in pending
        if room not in pending:
            pending.append(room)
        self.task.dorm_recovery_restore = pending
        current = self.op_data.get_current_room(room, True)
        expected = retained + [""] * (len(agents) - len(retained))
        if current != expected:
            logger.info(f"宿舍单回排序：{room} 保留目标 {target.name}，暂留 {retained}")
            for attempt in range(5):
                if self.find("confirm_blue") is not None:
                    break
                if attempt == 4:
                    raise Exception("未成功进入干员选择界面")
                # 首次点按可能被线索弹窗或过渡帧吞掉；ctap 的 10 秒去重
                # 会使后续循环完全没有重试操作。
                self.tap((self.recog.w * 0.82, self.recog.h * 0.2))
            try:
                self.choose_agent(
                    retained.copy(), room, fast_mode, preserve_dorm_occupants=True
                )
                self.tap_confirm(room, {})
                current = [item["agent"] for item in self.get_agent_from_room(room)]
                if current != expected:
                    raise Exception("宿舍单回排序确认失败，保留原任务重试")
            except MowerExit:
                raise
            except Exception as e:
                if (
                    isinstance(e, AgentSelectionNotReady)
                    or "检测到干员选择错误" in str(e)
                    or "宿舍单回排序确认失败" in str(e)
                    or (isinstance(e, RecognizeError) and str(e).startswith("干员确认"))
                ):
                    self.record_selection_failure()
                raise
        if current != agents:
            # 目标床位不再移动，不能因此沿用临时阵容下的恢复倒计时。
            # 补回宿管和其余入住者后，由紧接着的正常读房重新采样。
            _, bed = self.op_data.get_dorm_by_name(target.name)
            if bed is not None and bed.name == target.name:
                bed.time = None
        # 垫位者的缓存可能已过期，读回无法保证目标最低时只恢复最终阵容，
        # 不把本次单回当作已确认。下一次按新的真实心情重新选垫位者。
        manager_names = {
            name for name, _, _ in recovery_managers(self.op_data, room, agents)
        }
        # 菲亚梅塔不接受单回加成，不参与垫位者的心情比较。
        padding = set(retained[:vip_index]) - manager_names - {"菲亚梅塔"}
        if any(
            not has_resting_mood(self.op_data.operators[name])
            or self.op_data.operators[name].mood <= target.mood
            for name in padding
        ):
            target.clear_dorm_recovery()
            logger.info(f"{room} 单回垫位者心情不高于目标，恢复阵容后重新确认")
            return True
        if target.mood < 24:
            target.dorm_recovery_room = room
            target.dorm_recovery_index = vip_index
            target.dorm_recovery_fixed = recovery_managers(self.op_data, room, agents)
        else:
            target.clear_dorm_recovery()
        logger.info(
            f"宿舍单回排序确认：{room} 目标 {target.name} 固定在第{vip_index + 1}位，补回其余干员"
        )
        return True

    @timed_room
    def agent_arrange_room(
        self,
        new_plan,
        room,
        plan,
        skip_enter=False,
        get_time=False,
    ):
        finished = False
        # 延期重试也先读实际驻员，避免确认已成功却重复选人／充能。
        choose_error = int(getattr(self.task, "arrangement_retry_room", None) == room)
        checked = False
        reconcile_after_confirmation = False
        reconcile_after_selection = False
        while not finished:
            confirmation_pending = False
            selection_attempted = False
            try:
                error_count = 0
                if not skip_enter:
                    self.enter_room(room)
                    if room == "train":
                        # #74 gate L0 先读再判：删除「DB active 就跳过」的预判（原
                        # base_schedule.py:3257 死锁——DB 是意图缓存可能过期，排班一进门
                        # 就因 DB active 整房跳过、永不读屏幕、永不修正 DB → 重启后训练室
                        # 僵住，违背「截图为准」铁律）。现在一律先进房读屏幕，截图权威更新
                        # DB，再按锁定/保护判定跳过/冻结；空闲×未保护正常安排。
                        from arknights_mower.solvers.mastery_reader import (
                            _compute_protected,
                            read_room_state,
                            reconcile_short,
                        )

                        try:
                            room_state = read_room_state(self, enter=False)
                        except Exception as e:
                            logger.warning(f"训练室状态读取失败: {e}")
                            room_state = None
                        self.train_room_state = (
                            room_state if config.conf.enable_mastery else None
                        )
                        if room_state is not None and config.conf.enable_mastery:
                            # #61 短动作排班路径内联：顺路核实/帮收/重置/更新状态，并据截图
                            # 修正 DB（空闲×DB active 冲突 → 重置 idle，以截图为准）。不
                            # 开始训练；退出训练室由本 gate 的跳过/冻结分支统一负责。
                            # #75 方案 C：defer_collect=True——待收取格若队列已有任一
                            # 专精任务则跳过收集（留给队列任务收，避免残留任务空闲房
                            # 触发开始训练）；队列空时照常收集兜底。
                            collected = False
                            try:
                                # #210：返回是否收集——收集后房间物理变空闲（面板全空），
                                # gate 用 ① 的槽位 + 状态设空闲 + 按空闲规则重算保护，
                                # 不再重读 read_room_state；没收集时状态/保护都没变。
                                collected = reconcile_short(
                                    self, room_state, defer_collect=True
                                )
                            except Exception as e:
                                logger.warning(f"训练室顺路更新状态失败: {e}")
                            if room_state.state == "waiting_collect" and collected:
                                if room_state.slots_read:
                                    # ① 在 TRAIN_MAIN 读过槽位（收集不挪人）→ 复用 +
                                    # 状态设空闲 + 按空闲规则重算保护（深读保留）
                                    room_state.state = "empty"
                                    room_state.protected = _compute_protected(
                                        self, room_state
                                    )
                                else:
                                    # ① 在 TRAIN_FINISH 横幅页首次进房，未读槽位 →
                                    # 收集后面板回到主页面，重读拿进驻数据 + 保护
                                    try:
                                        room_state = read_room_state(self, enter=False)
                                    except Exception:
                                        room_state = None
                                self.train_room_state = (
                                    room_state if config.conf.enable_mastery else None
                                )
                        # §4.4 保护检查：locked（训练中/待收取）、protected（逻各斯/艾丽妮
                        # 保护训练室）或读失败（room_state=None）都算「不能排班」→ 冻结/
                        # 跳过（#211：读失败保守不碰训练位，替代已删除的 train_slot_locked）。
                        if (
                            room_state is None
                            or room_state.locked
                            or room_state.protected
                        ):
                            self.train_room_state = (
                                room_state if config.conf.enable_mastery else None
                            )
                            if config.conf.assistant_follows_schedule:
                                if len(plan[room]) > 1:
                                    plan[room][1] = "Current"
                            else:
                                del plan[room]
                                self.back()
                                return new_plan
                self.turn_on_room_detail(room)
                if reconcile_after_confirmation:
                    actual = [item["agent"] for item in self.get_agent_from_room(room)]
                    reconcile_after_confirmation = False
                    selection_was_attempted = reconcile_after_selection
                    reconcile_after_selection = False
                    if len(actual) == len(plan[room]) and all(
                        current == target or target == "Free"
                        for current, target in zip(actual, plan[room])
                    ):
                        logger.info(f"{room} 确认后实际驻员已符合目标，结束排班")
                        if selection_was_attempted:
                            self.record_selection_success()
                        finished = True
                        if room in getattr(self.task, "dorm_recovery_restore", []):
                            self.task.dorm_recovery_restore.remove(room)
                        del plan[room]
                        break
                error_count = 0
                if not checked:
                    roster = self.op_data.get_current_room(room, True)
                    if len(plan[room]) > len(roster):
                        extra = plan[room][len(roster) :]
                        message = (
                            f"{room} 排班超出当前设施的 {len(roster)} 个岗位：{extra}；"
                            "请检查主表、副表与游戏设施岗位数是否一致"
                        )
                        logger.error(message)
                        config.stop_mower.set()
                        raise MowerExit(message)
                    normal_order = (
                        self.task.type == TaskTypes.RUN_ORDER
                        and self.task.meta_data == room
                        and any(name in TRADE_ORDER_AGENTS for name in plan[room])
                        and not self._emergency_frozen()
                    )
                    if normal_order or getattr(
                        self.task, "run_order_restore_pending", False
                    ):
                        actual = [
                            item["agent"] for item in self.get_agent_from_room(room)
                        ]
                        if normal_order and (
                            len(actual) != len(roster)
                            or not actual
                            or len(set(actual)) != len(actual)
                            or any(
                                name in ("", "Free", "Current", *TRADE_ORDER_AGENTS)
                                for name in actual
                            )
                        ):
                            logger.warning(
                                "%s 跑单前实际驻员不完整或仍含跑单干员：%s，先执行普通纠错",
                                room,
                                actual,
                            )
                            self.reset_room_time(room)
                            plan.clear()
                            self.tasks.append(SchedulerTask())
                            self.back_to_infrastructure()
                            return False
                    if (
                        self.task.type == TaskTypes.RUN_ORDER
                        and any(
                            any(char in item for item in plan[room])
                            for char in TRADE_ORDER_AGENTS
                        )
                        and not room.startswith("dormitory")
                        and room != "train"
                    ):
                        new_plan[room] = (
                            actual.copy()
                            if normal_order
                            else self.refresh_current_room(room)
                        )
                    if "菲亚梅塔" in plan[room] and len(plan[room]) == 2:
                        new_plan[room] = self.refresh_current_room(room)
                        target = self.op_data.operators[plan[room][0]]
                        working_room = (
                            target.current_room
                            if self._emergency_frozen()
                            else target.room
                        )
                        if working_room and working_room != room:
                            new_plan[working_room] = self.op_data.get_current_room(
                                working_room, True
                            )
                    if room != "train" and (
                        "Current" in plan[room] or "" in plan[room]
                    ):
                        self.refresh_current_room(
                            room,
                            [
                                index
                                for index, value in enumerate(plan[room])
                                if value == "Current"
                            ],
                        )
                        _current_room = self.op_data.get_current_room(room, True)
                        for current_idx, _name in enumerate(plan[room]):
                            if _name == "Current":
                                plan[room][current_idx] = (
                                    _current_room[current_idx]
                                    if _current_room[current_idx] != ""
                                    else "Free"
                                )
                            if _name == "" and not (
                                getattr(self.task, "emergency_staffing", False)
                                or getattr(self.task, "emergency_dorm", False)
                                or (
                                    self._emergency_frozen()
                                    and self.task.type
                                    in (TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA)
                                )
                            ):
                                plan[room][current_idx] = "Free"
                    if (
                        room in self.op_data.run_order_rooms
                        and len(new_plan) == 0
                        and self.task.type != TaskTypes.RUN_ORDER
                    ):
                        if plan[room] != self.op_data.get_current_room(room):
                            self.refresh_run_order_time(room)
                checked = True
                confirmation_pending = True
                dorm_mood_candidates = None
                if room.startswith("dorm"):
                    dorm_mood_candidates = self.prepare_dorm_selection(plan[room], room)
                recovery_ordered = self.ensure_dorm_recovery_order(
                    room, plan[room], fast_mode=choose_error <= 0
                )
                read_time_index = []
                related_operators = {}
                fia_arrangement = (
                    self.task is not None
                    and self.task.type == TaskTypes.FIAMMETTA
                    and "菲亚梅塔" in plan[room]
                )
                if fia_arrangement:
                    fia_index = plan[room].index("菲亚梅塔")
                    # 菲亚梅塔的读数代表目标交换前心情；目标自身的
                    # 读数代表交换后心情，两点在历史曲线上相差一秒。
                    read_time_index.append(fia_index)
                    if self.task is not None and self.task.meta_data:
                        related_operators[fia_index] = self.task.meta_data
                        if self.task.meta_data in plan[room]:
                            read_time_index.append(
                                plan[room].index(self.task.meta_data)
                            )
                    read_time_index = sorted(set(read_time_index))
                    logger.info("肥鸭换入完成，读取交换后心情")
                elif get_time or recovery_ordered:
                    refresh_indexes = self.op_data.get_refresh_index(room, plan[room])
                    if recovery_ordered:
                        refresh_indexes = sorted(
                            set(refresh_indexes)
                            | {
                                i
                                for i, slot in enumerate(self.op_data.plan[room])
                                if slot.agent == "Free"
                            }
                        )
                    if (
                        getattr(self.task, "emergency_dorm", False)
                        and "菲亚梅塔" in plan[room]
                    ):
                        refresh_indexes = sorted(
                            set(refresh_indexes) | {plan[room].index("菲亚梅塔")}
                        )
                    read_time_index = list(
                        dict.fromkeys([*read_time_index, *refresh_indexes])
                    )

                if choose_error > 0:
                    if len(new_plan) > 1:
                        self.op_data.operators["菲亚梅塔"].time_stamp = None
                        self.op_data.operators[plan[room][0]].time_stamp = None
                    if related_operators:
                        current = self.get_agent_from_room(
                            room, read_time_index, related_operators
                        )
                    else:
                        current = self.get_agent_from_room(room, read_time_index)
                    same = True
                    for idx, name in enumerate(plan[room]):
                        if current[idx]["agent"] != name and name not in (
                            "Free",
                            "Current",
                        ):
                            if not (room == "train" and idx == 1):
                                same = False
                                break
                    if same:
                        logger.info(f"重试复核发现 {room} 目标干员已在岗并完成采样")
                else:
                    current_room = self.op_data.get_current_room(room, True)
                    same = len(plan[room]) == len(current_room)
                    if same:
                        for item1, item2 in zip(plan[room], current_room):
                            if item1 != item2:
                                same = False
                if not same:
                    if (
                        self._emergency_active()
                        and room.startswith("dorm")
                        and self.task.type == TaskTypes.RELEASE_DORM
                        and getattr(self.task, "strict_mood_limit", False)
                        or self._can_refresh_idle_dorm_search()
                        and self.task.type != TaskTypes.RUN_ORDER
                        and room != "train"
                    ):
                        # 换人前顺路读取离开者，不额外读取其工作／恢复倒计时。
                        self.get_agent_from_room(room, departing_plan=plan[room])
                    # 沿用原跑单流程：换人前校准确认时刻，选人失败重试不重复读。
                    if (
                        self.task.type == TaskTypes.RUN_ORDER
                        and not self.task.adjusted
                        and len(new_plan) == 1
                        and config.conf.run_order_buffer_time > 0
                        and choose_error <= 0
                    ):
                        remaining_time = self.get_order_remaining_time()
                        if 0 < remaining_time < (config.conf.run_order_delay + 10) * 60:
                            self.task.time = (
                                datetime.now()
                                + timedelta(seconds=remaining_time)
                                - timedelta(minutes=config.conf.run_order_delay)
                            )
                            logger.info(f"订单倒计时 {remaining_time}秒")
                            self.back()
                            self.turn_on_room_detail(room)
                        else:
                            logger.info("检测到漏单")
                            send_message("检测到漏单！", level="WARNING")
                            self.reset_room_time(room)
                            raise Exception("检测到漏单！")
                    if room == "train":
                        # #59：idx1 冻结已在 gate L1 按锁定状态处理好（Current），
                        # 不再依赖 find_next_task(SKILL_UPGRADE) 的脆弱信号。
                        selection_attempted = True
                        self.choose_train(
                            plan[room],
                            fast_mode=choose_error <= 0,
                            choose_error=choose_error,
                        )
                    else:
                        while self.find("confirm_blue") is None:
                            if error_count > 3:
                                raise Exception("未成功进入干员选择界面")
                            self.tap((self.recog.w * 0.82, self.recog.h * 0.2))
                            error_count += 1
                        if normal_order and not getattr(
                            self.task, "run_order_restore_pending", False
                        ):
                            self.task.run_order_original_roster = copy.deepcopy(
                                new_plan
                            )
                            self.task.run_order_restore_pending = True
                        selection_attempted = True
                        if recovery_ordered:
                            self.choose_agent(
                                plan[room],
                                room,
                                fast_mode=choose_error <= 0,
                                preserve_dorm_occupants=True,
                                choose_error=choose_error,
                                dorm_mood_candidates=dorm_mood_candidates,
                            )
                        else:
                            self.choose_agent(
                                plan[room],
                                room,
                                fast_mode=choose_error <= 0,
                                choose_error=choose_error,
                                dorm_mood_candidates=dorm_mood_candidates,
                            )
                        confirmation_pending = True
                        self.tap_confirm(room, new_plan)
                    if len(new_plan) > 1:
                        self.op_data.operators["菲亚梅塔"].time_stamp = None
                        self.op_data.operators[plan[room][0]].time_stamp = None
                    if related_operators:
                        current = self.get_agent_from_room(
                            room, read_time_index, related_operators
                        )
                    else:
                        current = self.get_agent_from_room(room, read_time_index)
                    for idx, name in enumerate(plan[room]):
                        if current[idx]["agent"] != name and name not in (
                            "Free",
                            "Current",
                        ):
                            if not (room == "train" and idx == 1):
                                logger.error(
                                    f"检测到的干员{current[idx]['agent']},需要安排的干员{name}"
                                )
                                raise Exception("检测到安排干员未成功")
                elif choose_error == 0:
                    if fia_arrangement:
                        # 失败重试或回岗名单恰好一致，也必须刷新充能后的计时。
                        self.get_agent_from_room(room, read_time_index)
                    logger.info(f"任务与当前房间相同，跳过安排{room}人员")
                if selection_attempted or choose_error > 0:
                    self.record_selection_success()
                finished = True
                skip_enter = False
                if room in getattr(self.task, "dorm_recovery_restore", []):
                    self.task.dorm_recovery_restore.remove(room)
                if getattr(self.task, "arrangement_retry_room", None) == room:
                    del self.task.arrangement_retry_room
                    del self.task.arrangement_retry_count
                # 如果完成则移除该任务
                del plan[room]
                # back to 基地主界面
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
            except (MowerExit, DeviceRecoveryError):
                raise
            except Exception as e:
                save_exception(e)
                logger.exception(e)
                if getattr(self.task, "emergency_staffing", False) and isinstance(
                    e, AgentSelectionNotReady
                ):
                    self.back_to_infrastructure()
                    self._emergency_read_rooms([room])
                    if getattr(self.task, "emergency_recovery_release", False):
                        plan.clear()
                    elif getattr(self.task, "emergency_staffing_members", ()):
                        self.emergency_state["staffing_complete"] = False
                        plan.clear()
                    else:
                        self.emergency_state.get("staffing_plan", {}).pop(room, None)
                        plan.pop(room, None)
                    self.emergency_state["next_read"] = datetime.now()
                    self._emergency_save()
                    return False
                record_selection_retry()
                if selection_attempted and (
                    isinstance(e, AgentSelectionNotReady)
                    or "检测到干员选择错误" in str(e)
                    or "检测到安排干员未成功" in str(e)
                    or (isinstance(e, RecognizeError) and str(e).startswith("干员确认"))
                ):
                    self.record_selection_failure()
                if (
                    getattr(self.task, "run_order_restore_pending", False)
                    and self.task.meta_data
                ):
                    # 首次换入失败交回任务补偿边界，后续只恢复实测原班。
                    raise
                choose_error += 1
                self.recog.update()
                if "检测到漏单！" in str(e):
                    return {}
                if confirmation_pending:
                    reconcile_after_confirmation = True
                    reconcile_after_selection = selection_attempted
                # 跑单和肥鸭有临时换入／恢复的连续步骤，保留原有原地重试。
                queued = (
                    self.task is not None
                    and self.task.type
                    not in (
                        TaskTypes.RUN_ORDER,
                        TaskTypes.FIAMMETTA,
                        TaskTypes.SKILL_UPGRADE,
                        TaskTypes.SWAP_SUPPORT,
                    )
                    and any(task is self.task for task in getattr(self, "tasks", []))
                )
                blocked_orders = (
                    blocked_run_order_ids(self.tasks, self.op_data) if queued else set()
                )
                urgent = (
                    queued
                    and not getattr(self.task, "dorm_recovery_restore", [])
                    and any(
                        task is not self.task
                        and id(task) not in blocked_orders
                        and task.type
                        in (
                            TaskTypes.FIAMMETTA,
                            TaskTypes.RUN_ORDER,
                            TaskTypes.SWAP_SUPPORT,
                            TaskTypes.SKILL_UPGRADE,
                        )
                        and task.time <= datetime.now() + timedelta(minutes=1)
                        for task in self.tasks
                    )
                )
                if queued and (choose_error > 3 or urgent):
                    raise RoomArrangementDeferred(room, e) from e
                if choose_error > 3:
                    raise e
                # 确认后的失败统一返回再读实际驻员，由下一轮决定是否重选。
                back_count = 0
                while self.scene() != Scene.INFRA_MAIN:
                    self.back(interval=0.5)
                    back_count += 1
                    if back_count > 3:
                        if queued:
                            raise RoomArrangementDeferred(room, e) from e
                        raise e
                continue
        if len(new_plan) != 1:
            self.back(0.5)
        else:
            if config.conf.run_order_buffer_time <= 0:
                self.back(0.5)
        return new_plan

    def accept_order(self):
        task = getattr(self, "task", None)
        if task is not None and task.type == TaskTypes.RUN_ORDER and task.meta_data:
            self._cache_facility_state_from_current_page(task.meta_data, "trade")
        wait = 0
        # 等待订单完成
        while self.find("order_ready", scope=((450, 675), (600, 750))) is None:
            if wait > 6:
                break
            self.recog.update()
            self.sleep(0.5)
            wait += 1
        not_take = True
        while self.find("order_ready", scope=((450, 675), (600, 750))) is not None:
            if not_take:
                # 动画过渡防抖：若首帧已充分定格则直接放行，否则最多等待 2 次采样 (~0.3s)
                scores = self.order_reader.get_buff_scores(self.recog.img)
                if not self.order_reader.has_distinct_buff(scores):
                    for _ in range(2):
                        self.sleep(0.15)
                        self.recog.update()
                        new_scores = self.order_reader.get_buff_scores(self.recog.img)
                        if self.order_reader.has_distinct_buff(
                            new_scores
                        ) or self.order_reader.is_stable(scores, new_scores):
                            break
                        scores = new_scores

                self.recog.save_screencap("run_order")
                self.order_reader.save(self.recog.img)
                not_take = False
            self.tap((self.recog.w * 0.25, self.recog.h * 0.25), interval=0.5)

    def _can_refresh_idle_dorm_search(self):
        return (
            not getattr(self, "defer_backup_plan_until_mood_read", False)
        ) and getattr(self.task, "type", None) != TaskTypes.FIAMMETTA

    def _track_idle_dorm_shift(self, plan):
        """任务首次执行时记录成组下班者，延期重试沿用同一份名单。"""
        if (
            not self._can_refresh_idle_dorm_search()
            or self.task.type
            not in (
                TaskTypes.SHIFT_OFF,
                TaskTypes.EXHAUST_OFF,
                TaskTypes.SELF_CORRECTION,
                TaskTypes.RE_ORDER,
            )
            or hasattr(self.task, "idle_dorm_shift_groups")
        ):
            return
        groups = {}
        for room, names in plan.items():
            if not room.startswith("dorm"):
                continue
            for name in names:
                op = self.op_data.operators.get(name)
                if (
                    op is not None
                    and op.group
                    and op.is_high()
                    and not op.room.startswith("dorm")
                    and not op.workaholic
                    and not op.is_resting()
                ):
                    groups.setdefault(op.group, set()).add(name)
        self.task.idle_dorm_shift_groups = {
            group: names for group, names in groups.items() if len(names) >= 2
        }

    def _finish_idle_dorm_shift(self):
        if not self._can_refresh_idle_dorm_search():
            return
        groups = getattr(self.task, "idle_dorm_shift_groups", {})
        completed = [
            group
            for group, names in groups.items()
            if all(
                (op := self.op_data.operators.get(name)) is not None and op.is_resting()
                for name in names
            )
        ]
        if completed:
            self.op_data.refresh_idle_dorm_search(
                reason=f"成组下班已完成：{', '.join(completed)}",
                names={name for group in completed for name in groups[group]},
            )
            for group in completed:
                del groups[group]

    def _retain_run_order_restoration(self, *, delay=False):
        """保留实测原班，后续调度仅恢复驻员，不重复插拔。"""
        self.task.prepare_run_order_restoration()
        self.task.time = datetime.now() + timedelta(minutes=int(delay))
        if not any(task is self.task for task in self.tasks):
            self.tasks.append(self.task)
        return False

    def agent_arrange(self, plan: tp.BasePlan, get_time=False):
        restoring_order = getattr(self.task, "run_order_restore_pending", False)
        if restoring_order:
            self.task.prepare_run_order_restoration()
            plan = self.task.plan
            if not self._emergency_compensation_available(plan):
                self.task.time = datetime.now() + timedelta(minutes=1)
                return False
        elif self.task.type == TaskTypes.RUN_ORDER and self.task.meta_data:
            if any(
                task is not self.task
                and getattr(task, "run_order_restore_pending", False)
                for task in self.tasks
            ):
                self.task.time = datetime.now() + timedelta(minutes=1)
                return False
        if self._emergency_frozen():
            if (
                self.task.type == TaskTypes.RUN_ORDER
                and hasattr(self.task, "emergency_original_roster")
                and not self._emergency_compensation_available(plan)
            ):
                self.task.time = datetime.now() + timedelta(minutes=1)
                return False
            if self.task.type in (TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA):
                if not restoring_order and not hasattr(
                    self.task, "emergency_original_roster"
                ):
                    self.task.emergency_original_roster = {
                        room: self.op_data.get_current_room(room, True) for room in plan
                    }
            elif (
                not getattr(self.task, "emergency_staffing", False)
                and any(not room.startswith("dorm") for room in plan)
                and self.task.type
                not in (
                    TaskTypes.WORKSHOP,
                    TaskTypes.SKILL_UPGRADE,
                    TaskTypes.SWAP_SUPPORT,
                )
            ):
                raise RuntimeError("救急期间暂停普通工作站换班")
        logger.info("基建：排班")
        if (
            self.task.type in (TaskTypes.NOT_SPECIFIC, TaskTypes.FILL_DORM)
            and hasattr(self.task, "dorm_fill_plan")
            and not getattr(self.task, "emergency_dorm", False)
            and not any(
                getattr(self.task, attribute, False)
                for attribute in (
                    "arrangement_retry_room",
                    "dorm_recovery_restore",
                    "product_shift_locked",
                    "backup_shift_active",
                    "strict_mood_limit",
                )
            )
            and not self._emergency_frozen()
        ):
            # 排队期间身份和恢复层级可以变化；复用分床规划器重新准入。
            pending = copy.deepcopy(
                [task for task in self.tasks if task is not self.task]
            )
            existing = {id(task): task for task in pending}
            projected = self.op_data.project_arrangements([{}])
            try_add_release_dorm({}, None, projected, pending)
            updated = next((task for task in pending if id(task) not in existing), None)
            self.task.plan.clear()
            self.task.plan.update(updated.plan if updated is not None else {})
            if updated is not None:
                self.task.type = updated.type
            for attribute in (
                "dorm_fill_plan",
                "dorm_mood_residents",
                "simple_dorm_fill",
            ):
                if hasattr(updated, attribute):
                    setattr(self.task, attribute, getattr(updated, attribute))
                elif hasattr(self.task, attribute):
                    delattr(self.task, attribute)
            if updated is not None:
                protect_priority_tasks(self.tasks, op_data=self.op_data)
                if (
                    self.task.time > datetime.now()
                    or not self.tasks
                    or self.tasks[0] is not self.task
                ):
                    return False
            for dorm_room, names in self.task.plan.items():
                if dorm_room.startswith("dorm"):
                    for name in names:
                        if name in self.op_data.operators:
                            self.op_data.operators[name].dorm_mood_fallback = (
                                dorm_room
                                if projected.operators[name].dorm_mood_fallback
                                else ""
                            )
            plan = self.task.plan
        self._track_idle_dorm_shift(plan)
        if self.task.type == TaskTypes.FILL_DORM and not getattr(
            self.task, "emergency_dorm", False
        ):
            simplify_dorm_fill(self.task, self.tasks, op_data=self.op_data)
            if getattr(self.task, "simple_dorm_fill", False):
                if self.task.plan and defer_dorm_before_priority_task(
                    self.task,
                    self.tasks,
                    next(iter(self.task.plan)),
                    datetime.now(),
                    self.op_data,
                ):
                    return False
                # 任务等待期间床位可能已变化；简化补位只碰现在仍为空的床。
                vacancies = vacant_dorm_slots(self.op_data)
                remaining = {}
                for room, names in self.task.plan.items():
                    for index, name in enumerate(names):
                        if name == "Current" or (room, index) not in vacancies:
                            continue
                        op = self.op_data.operators.get(name)
                        if op is not None and op.current_room:
                            name = "Free"
                        remaining.setdefault(room, ["Current"] * len(names))[index] = (
                            name
                        )
                self.task.plan.clear()
                self.task.plan.update(remaining)
            plan = self.task.plan
        if self.task.type != TaskTypes.FIAMMETTA and not self._emergency_frozen():
            previous = dorm_residents(self.op_data)
            for dorm_room in list(plan):
                if dorm_room.startswith("dorm"):
                    self.preserve_resting_crafters(plan[dorm_room], dorm_room)
            restore_displaced_resting(self.op_data, previous, plan, self.tasks)
        rooms = list(plan.keys())
        # 救急跑单失败沿用换入意图；普通跑单由实测原班补偿接续。
        original_plan = (
            copy.deepcopy(plan)
            if self.task.type == TaskTypes.RUN_ORDER and self._emergency_frozen()
            else None
        )
        new_plan = {}
        # 优先替换工作站再替换宿舍
        rooms.sort(
            key=lambda x: (
                x.startswith("dormitory_"),
                int(x.split("_")[1]) if x.startswith("dormitory_") else 0,
            )
        )
        for room in rooms:
            if (not new_plan) and defer_dorm_before_priority_task(
                self.task, self.tasks, room, datetime.now(), self.op_data
            ):
                return False
            try:
                new_plan = self.agent_arrange_room(
                    new_plan, room, plan, get_time=get_time
                )
            except BaseException:
                if getattr(self.task, "run_order_restore_pending", False):
                    self._retain_run_order_restoration(delay=True)
                raise
            if new_plan is False or new_plan is None:
                self._finish_idle_dorm_shift()
                if getattr(self.task, "run_order_restore_pending", False):
                    return self._retain_run_order_restoration(delay=True)
                return False
        self._finish_idle_dorm_shift()
        if restoring_order:
            del self.task.run_order_original_roster
            del self.task.run_order_restore_pending
        if (
            len(new_plan) == 1
            and room != "train"
            and self.task.type == TaskTypes.RUN_ORDER
        ):
            try:
                if config.conf.run_order_buffer_time <= 0 or self.task.adjusted:
                    if self.task.adjusted:
                        logger.info("检测到跑单已调整，强制使用无人机跑单")
                    logger.info("开始插拔")
                    try:
                        self.drone(room, not_customize=True)
                    except Exception:
                        if original_plan is not None:
                            self.task.plan = original_plan
                        raise
                else:
                    # 葛朗台跑单模式
                    # agent_arrange_room 已完成换人并读屏校验进驻结果；
                    # 此时才进入订单页读倒计时，避免换人前往返进入房间。
                    wait_time = self.get_order_remaining_time()
                    logger.debug(f"订单剩余时间 {wait_time} 秒")
                    if 0 < wait_time < config.conf.run_order_delay * 60:
                        logger.info(f"停止{wait_time}秒等待订单完成")
                        self.sleep(wait_time)
                        # 等待服务器交互
                        if self.scene() in self.waiting_scene:
                            if not self.waiting_solver():
                                if getattr(
                                    self.task, "run_order_restore_pending", False
                                ):
                                    return self._retain_run_order_restoration(
                                        delay=True
                                    )
                                return False
                    else:
                        logger.error("检测到漏单", extra={"archive_screenshots": True})
                        save_exception(Exception("检测到漏单"))
                        send_message("检测到漏单！", level="WARNING")
                    self.accept_order()
                    if self.drone_room is None or (
                        self.drone_room == room and room in self.op_data.run_order_rooms
                    ):
                        drone_count = self.digit_reader.get_drone(self.recog.gray)
                        logger.info(f"当前无人机数量为：{drone_count}")
                        if drone_count >= config.conf.drone_count_limit:
                            self.drone(
                                room,
                                not_return=True,
                                not_customize=True,
                                skip_enter=True,
                            )
                    if config.conf.run_order_buffer_time > 0:
                        while self.find("bill_accelerate") is not None:
                            self.back(interval=0.5)
                    else:
                        self.back(interval=0.5)
                        self.back(interval=0.5)
                # 防止由于意外导致的死循环
                run_order_room = next(iter(new_plan))
                if getattr(self.task, "run_order_restore_pending", False):
                    new_plan = copy.deepcopy(self.task.run_order_original_roster)
                    if config.conf.run_order_buffer_time <= 0:
                        return self._retain_run_order_restoration()
                elif self._emergency_frozen() and hasattr(
                    self.task, "emergency_original_roster"
                ):
                    new_plan = copy.deepcopy(self.task.emergency_original_roster)
                if config.conf.run_order_buffer_time > 0 and (
                    not self._emergency_frozen()
                    or self._emergency_compensation_available(new_plan)
                ):
                    restored = self.agent_arrange_room(
                        {}, run_order_room, new_plan, skip_enter=True
                    )
                    if getattr(self.task, "run_order_restore_pending", False):
                        if restored is False or restored is None:
                            return self._retain_run_order_restoration(delay=True)
                        del self.task.run_order_original_roster
                        del self.task.run_order_restore_pending
                else:
                    restore_task = SchedulerTask(
                        time=self.tasks[0].time,
                        task_plan=new_plan,
                        task_type=TaskTypes.RUN_ORDER,
                    )
                    if self._emergency_frozen():
                        restore_task.emergency_original_roster = copy.deepcopy(
                            self.task.emergency_original_roster
                        )
                    if getattr(self.task, "maintenance_advance_before_backup", False):
                        restore_task.maintenance_advance_before_backup = True
                    self.tasks.append(restore_task)
                    self.skip()
            except BaseException:
                if getattr(self.task, "run_order_restore_pending", False):
                    self._retain_run_order_restoration(delay=True)
                raise
        elif new_plan and self.task.type == TaskTypes.FIAMMETTA:
            self.tasks.append(
                SchedulerTask(
                    time=self.tasks[0].time,
                    task_plan=new_plan,
                    task_type=TaskTypes.FIAMMETTA,
                    initial_fia=getattr(self.task, "initial_fia", False),
                )
            )
            # 急速换班
            self.skip()
        logger.info("返回基建主界面")

    def skip(self, task_names="All"):
        if task_names == "All":
            task_names = ["planned", "collect_notification", "todo_task"]
        if "planned" in task_names:
            self.planned = True
        if "todo_task" in task_names:
            self.todo_task = True
        if "collect_notification" in task_names:
            self.collect_notification = True

    def no_pending_task(self, minute=0):
        return self.find_next_task(datetime.now() + timedelta(minutes=minute)) is None

    def reload(self):
        """按生效排班表配置的源石碎片房间补货，不读取当前产物。"""
        error = False
        for room, product in self.op_data.products.items():
            if not room.startswith("room_") or product not in (
                "orirock",
                "orirock_device",
            ):
                continue
            try:
                self.enter_room(room)
                self._wait_drone_interface(
                    interval=0.25, accelerate_template="manufacture_accelerate"
                )
                logger.info(
                    f"开始搓玉补货:{room}（{MANUFACTURE_PRODUCTS[product].name}）"
                )
                # 补货
                self.tap((self.recog.w * 0.75, self.recog.h * 0.3), interval=0.5)
                self.tap((self.recog.w * 0.75, self.recog.h * 0.9), interval=0.5)
                if self.scene() in self.waiting_scene:
                    if not self.waiting_solver():
                        return
                self.scene_graph_navigation(Scene.INFRA_MAIN)
            except MowerExit:
                raise
            except Exception as e:
                save_exception(e)
                logger.exception(e)
                error = True
                self.recog.update()
                back_count = 0
                while self.scene() != Scene.INFRA_MAIN:
                    self.back()
                    back_count += 1
                    if back_count > 3:
                        raise e
        if not error:
            self.reload_time = datetime.now()

    def on_maa_callback(self, msg, details, arg):
        """MAA 回调入口：累积掉落统计、代发上报请求、输出可读日志行。"""
        d = parse_details(details)
        logger.debug("MAA 回调 %s %s", msg, d)
        if msg == 3:  # AllTasksCompleted follows the final StageDrops receipt.
            battle_inventory_active.clear()
        if msg == 20003 and d.get("what") == "StageDrops":
            try:
                from arknights_mower.utils.maa_inventory import MaaDropInventory

                if getattr(self, "maa_drop_inventory", None) is None:
                    self.maa_drop_inventory = MaaDropInventory()
                self.maa_drop_inventory.record(d)
                self.refresh_maa_inventory_targets()
            except Exception:
                logger.exception("MAA 掉落入库或停止目标更新失败，请检查库存")
            inner = d.get("details")
            inner = inner if isinstance(inner, dict) else {}
            drops = _drop_entries(inner.get("drops"))
            stats = _drop_entries(inner.get("stats"))
            if drops:
                stage_drop["details"].append(drops)
            if stats:
                stage_drop["summary"] = stats
        if msg in (10002, 10000, 10004) and type(d.get("taskid")) is int:
            getattr(self, "maa_inventory_tasks", {}).pop(d["taskid"], None)
        if msg == 10001 and d.get("taskchain") == "Fight":
            try:
                self.refresh_maa_inventory_targets()
            except Exception:
                logger.exception("MAA 库存目标更新失败")
        if msg == REPORT_REQUEST:
            # 上报在守护线程里进行；此处仍要兜住线程创建失败，回调不得抛错。
            try:
                upload_report(d)
            except Exception as e:
                logger.warning(f"MAA 上报请求处理失败：{e}")
        if self.maa_callback is None:
            return
        line = self.maa_callback.describe(msg, d)
        if line is not None:
            logger.log(line.level, line.text)

    def refresh_maa_inventory_targets(self):
        """Update only inventory-bound Fight tasks; preserve all other parameters."""
        tasks = getattr(self, "maa_inventory_tasks", {})
        if not tasks:
            return
        from arknights_mower.utils.maa_stage_inventory import (
            load_inventory_snapshot,
            maa_fight_drop_targets,
        )

        inventory, _ = load_inventory_snapshot()
        for task_id, entry in list(tasks.items()):
            params, rules = entry
            targets = maa_fight_drop_targets(
                params["stage"],
                rules,
                inventory,
                self.maa_drop_inventory.accumulated(task_id),
            )
            updated = {**params, "drops": targets["drops"]}
            if targets["reached"]:
                updated.update(times=0, medicine=0, stone=0, expiring_medicine=0)
            if updated == params:
                continue
            if self.MAA.set_task_params(task_id, updated):
                tasks[task_id] = (updated, rules)
                if targets["reached"] and params["times"]:
                    logger.info(
                        "%s 库存已达上限，结束该关并继续后续任务", params["stage"]
                    )
            else:
                logger.warning("%s 库存停止目标未被 MAA 接受", params["stage"])

    def report_maa_progress(self):
        """按间隔播报 MAA 进度；未到间隔不产生日志行。"""
        if self.maa_callback is None:
            return
        line = self.maa_callback.heartbeat()
        if line is not None:
            logger.log(line.level, line.text)

    def initialize_maa(self):
        from arknights_mower.utils.maa_backup import VerifiedAsst, update_transaction
        from arknights_mower.utils.maa_inventory import MaaDropInventory

        self.maa_drop_inventory = MaaDropInventory()
        self.maa_inventory_tasks = {}
        battle_inventory_active.set()

        if os.environ.get("MOWER_ANDROID") == "1":
            from mower_android.maa import Asst

            config.stop_maa.clear()
            self.maa_callback = MaaCallbackLog()
            self.MAA = VerifiedAsst(Asst, config.conf.maa_path, self.on_maa_callback)
            self.stages = []
            if not self.MAA.connect():
                raise RuntimeError("安卓 MAA 引擎未连接")
            return
        config.stop_maa.clear()
        conf = config.conf
        path = pathlib.Path(resolve_config_path(conf.maa_path))
        asst_path = os.path.dirname(path / "Python" / "asst")
        if asst_path not in sys.path:
            sys.path.append(asst_path)

        try:
            from asst.asst import Asst
            from asst.utils import InstanceOptionType

            logger.info("MAA Python模块导入成功")
        except Exception as e:
            save_exception(e)
            logger.exception(
                f"MAA Python模块导入失败：{str(e)}",
                extra={"archive_screenshots": False},
            )
            raise Exception("MAA Python模块导入失败")

        try:
            logger.debug("开始更新MAA活动关卡导航……")
            ota_tasks_url = (
                "https://api.maa.plus/MaaAssistantArknights/api/resource/tasks.json"
            )
            ota_tasks_path = path / "cache" / "resource" / "tasks.json"
            ota_tasks_path.parent.mkdir(parents=True, exist_ok=True)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
            }
            with requests.get(ota_tasks_url, headers=headers, timeout=60) as response:
                response.raise_for_status()
                res = response.content.decode("utf-8")
            with open(ota_tasks_path, "w", encoding="utf-8") as f:
                f.write(res)
            logger.info("MAA活动关卡导航更新成功")
        except Exception as e:
            logger.error(
                f"MAA活动关卡导航更新失败：{str(e)}",
                extra={"archive_screenshots": False},
            )
            save_exception(e)

        @update_transaction
        def create_verified_asst():
            Asst.load(path=path, incremental_path=path / "cache")
            return VerifiedAsst(Asst, path, self.on_maa_callback)

        # 覆盖 Asst.load 与连接阶段：连接信息回调在 connect 期间就会到达。
        self.maa_callback = MaaCallbackLog()
        self.MAA = create_verified_asst()
        self.stages = []
        self.MAA.set_instance_option(
            InstanceOptionType.touch_type, conf.maa_touch_option
        )
        adb_path = getattr(self.device.client, "adb_bin", None) or resolve_config_path(
            conf.maa_adb_path
        )
        for name in ("adblite_enabled", "kill_on_adb_exit"):
            option = getattr(InstanceOptionType, name, None)
            if option is not None:
                self.MAA.set_instance_option(option, "0")
        guard_adb(adb_path, timeout=io_timeout(10))
        if self.MAA.connect(
            adb_path,
            self.device.client.device_id,
            conf.maa_conn_preset,
        ):
            logger.info("MAA 连接成功")
        else:
            logger.info("MAA 连接失败")
            raise Exception("MAA 连接失败")

    def append_maa_task(self, type):
        if type == "StartUp":
            self.MAA.append_task(
                "StartUp",
                {"client_type": _maa_client_type(getattr(self, "device", None))},
            )
        elif type == "Fight":
            self.maybe_switch_expired_activity_plan()
            conf = config.conf
            server_weekday = get_server_weekday()
            _plan = conf.maa_weekly_plan[server_weekday]
            logger.info(f"现在服务器是{_plan.weekday}")
            medicine_expire_days = 0
            if conf.medicine_expire_days > 0:
                if conf.expiring_medicine_on_weekend:
                    medicine_expire_days = (
                        conf.medicine_expire_days if server_weekday >= 5 else 0
                    )
                else:
                    medicine_expire_days = conf.medicine_expire_days
            stages = self.apply_maa_stage_inventory_rules(_plan.stage)
            from arknights_mower.utils.maa_stage_inventory import (
                load_inventory_snapshot,
                maa_fight_drop_targets,
            )

            inventory, _ = load_inventory_snapshot()
            rules = (
                copy.deepcopy(conf.maa_stage_limit_rules)
                if conf.maa_stage_inventory_enable
                else []
            )
            if not hasattr(self, "maa_inventory_tasks"):
                self.maa_inventory_tasks = {}
            for stage in stages:
                targets = maa_fight_drop_targets(stage, rules, inventory)
                if targets["reached"]:
                    continue
                logger.info(f"添加关卡:{stage}")
                params = {
                    # 空值表示上一次
                    # 'stage': '',
                    "stage": stage,
                    "medicine": _plan.medicine,
                    "stone": 999 if conf.maa_eat_stone else 0,
                    "times": 999,
                    "series": 0,
                    "report_to_penguin": conf.maa_report_to_penguin,
                    "client_type": _maa_client_type(getattr(self, "device", None)),
                    "penguin_id": conf.maa_penguin_id,
                    "DrGrandet": False,
                    "server": "CN",
                    "medicine_expire_days": medicine_expire_days,
                    "report_to_yituliu": conf.maa_report_to_yituliu,
                    "yituliu_id": conf.maa_yituliu_id,
                }
                if targets["bound"]:
                    params.update(drops=targets["drops"])
                task_id = self.MAA.append_task("Fight", params)
                if targets["bound"] and task_id:
                    self.maa_inventory_tasks[task_id] = (params, rules)
                self.stages.append(stage)

        elif type == "Mall":
            conf = config.conf
            self.MAA.append_task(
                "Mall",
                {
                    "shopping": getattr(
                        conf,
                        "should_run_maa_mall",
                        getattr(conf, "maa_mall_enable", True)
                        and getattr(conf, "maa_mall_mode", "maa") == "maa",
                    ),
                    "buy_first": conf.maa_mall_buy.split(","),
                    "blacklist": conf.maa_mall_blacklist.split(","),
                    "credit_fight": conf.maa_credit_fight
                    and "" not in self.stages
                    and self.credit_fight is None,
                    "formation_index": max(0, min(4, conf.credit_fight.squad)),
                    "force_shopping_if_credit_full": conf.maa_mall_ignore_blacklist_when_full,
                    "visit_friends": getattr(
                        conf,
                        "should_run_maa_visit_friend",
                        getattr(conf, "visit_friend_enable", False)
                        and getattr(conf, "visit_friend_mode", "maa") == "maa",
                    ),
                    "only_buy_discount": conf.maa_mall_only_buy_discount,
                    "reserve_max_credit": conf.maa_mall_reserve_max_credit,
                },
            )
        elif type == "Award":
            self.MAA.append_task(
                "Award",
                {
                    "award": True,
                    "mail": config.conf.maa_mail,
                    "recruit": config.conf.maa_recruit,
                    "orundum": config.conf.maa_orundum,
                    "mining": config.conf.maa_mining,
                    "specialaccess": config.conf.maa_specialaccess,
                },
            )

    def maybe_switch_expired_activity_plan(self):
        """刷理智实际选关前，根据活动方案的切换时间更新周计划。"""
        try:
            from arknights_mower.utils.config.weekly_plan_loader import (
                get_weekly_plan_manager,
            )

            return get_weekly_plan_manager().maybe_switch_expired_activity_plan()
        except Exception:
            logger.exception(
                "检测活动结束并切换刷理智周计划失败，继续使用当前方案",
                extra={"archive_screenshots": False},
            )
            return None

    def maa_stop(self, stop=True):
        if stop:
            self.MAA.stop()
        battle_inventory_active.clear()
        logger.debug(stage_drop)
        # 有掉落东西再发
        if stage_drop["details"] and not self.drop_send:
            send_message(
                maa_template.render(stage_drop=stage_drop),
                "MAA停止",
            )
            self.drop_send = True

    def restore_maa_theme(self):
        """本轮 MAA 任务收尾时恢复指定主题，为下次调度预留时间。"""
        conf = config.conf
        if not conf.maa_restore_theme_enable or self.MAA is None:
            return
        theme = conf.maa_restore_theme.strip()
        if not theme:
            logger.warning("未选择目标主题，跳过恢复主题")
            return
        if config.stop_maa.is_set() or config.stop_mower.is_set():
            return

        queued = False
        try:
            version = self.MAA.get_version()
            try:
                supported = Version(version) >= Version("6.17.3")
            except InvalidVersion:
                supported = False
            if not supported:
                logger.warning(
                    f"恢复主题需要 MAA v6.17.3 或更高版本，当前为 {version}，跳过恢复"
                )
                return

            deadline = min(
                datetime.now() + timedelta(seconds=120),
                self.tasks[0].time - timedelta(seconds=5),
            )
            if (deadline - datetime.now()).total_seconds() < 10:
                logger.info("距离下次调度时间过近，跳过恢复主题")
                return

            # 大型任务可能被调度器中断；清空原队列后只运行恢复任务。
            self.MAA.stop()
            if config.stop_maa.is_set() or config.stop_mower.is_set():
                return
            task_id = self.MAA.append_task("SwitchTheme", {"themes": [theme]})
            if not task_id:
                logger.warning("添加恢复主题任务失败，请检查 MAA 核心及配套资源版本")
                return
            queued = True
            if not self.MAA.start():
                logger.warning("恢复主题任务启动失败")
                return
            logger.info(f"开始恢复游戏主题：{theme}")
            while self.MAA.running():
                if config.stop_maa.is_set():
                    logger.info("收到停止指令，停止恢复主题")
                    return
                if (
                    datetime.now() >= deadline
                    or (self.tasks[0].time - datetime.now()).total_seconds() <= 5
                ):
                    logger.warning("恢复主题超时或即将开始下次调度，停止恢复")
                    return
                csleep(1)
            logger.info("恢复主题任务结束，具体切换结果请查看 MAA 日志")
        except MowerExit:
            raise
        except Exception:
            logger.exception("恢复主题失败，继续原定调度")
        finally:
            if queued:
                self.MAA.stop()
                self.recog.reset_after_external_control()

    def has_maa_daily_tasks(self) -> bool:
        conf = config.conf
        if hasattr(conf, "has_maa_daily_tasks"):
            return conf.has_maa_daily_tasks
        return (
            (
                getattr(conf, "stage_plan_enable", True)
                and getattr(conf, "stage_plan_runner", "maa") == "maa"
            )
            or (
                getattr(conf, "maa_mall_enable", True)
                and getattr(conf, "maa_mall_mode", "maa") == "maa"
            )
            or (
                getattr(conf, "visit_friend_enable", False)
                and getattr(conf, "visit_friend_mode", "maa") == "maa"
            )
            or any(
                [
                    getattr(conf, "maa_mail", False),
                    getattr(conf, "maa_recruit", False),
                    getattr(conf, "maa_orundum", False),
                    getattr(conf, "maa_mining", False),
                    getattr(conf, "maa_specialaccess", False),
                ]
            )
        )

    def has_maa_tasks(self) -> bool:
        conf = config.conf
        if hasattr(conf, "has_maa_tasks"):
            return conf.has_maa_tasks
        return (
            self.has_maa_daily_tasks()
            or getattr(conf, "RG", False)
            or getattr(conf, "SSS", False)
            or getattr(conf, "RCL", False)
        )

    def maa_plan_solver(self, tasks="All", one_time=False):
        """清日常"""
        try:
            self.drop_send = False
            restore_theme = False
            conf = config.conf
            if (
                not one_time
                and len(self.tasks) > 0
                and (self.tasks[0].time - datetime.now()).total_seconds() < 300
            ):
                logger.info("距离下次基建任务不足5分钟，跳过MAA日常任务")
                return
            if (
                not one_time
                and self.last_execution["maa"] is not None
                and (
                    delta := (
                        timedelta(hours=conf.maa_gap)
                        + self.last_execution["maa"]
                        - datetime.now()
                    )
                )
                > timedelta()
            ):
                logger.info(f"{format_time(delta.total_seconds())}后开始做日常任务")
            elif tasks == "All" and not self.has_maa_daily_tasks():
                logger.info("没有启用的 MAA 日常任务，跳过日常")
            else:
                send_message("启动MAA")
                self.back_to_index()
                # 任务及参数请参考 docs/集成文档.md
                self.initialize_maa()
                if tasks == "All":
                    tasks = ["StartUp"]
                    if getattr(
                        conf,
                        "should_run_maa_stage_plan",
                        getattr(conf, "stage_plan_enable", True)
                        and getattr(conf, "stage_plan_runner", "maa") == "maa",
                    ):
                        tasks.append("Fight")
                    if getattr(
                        conf,
                        "should_run_maa_mall_task",
                        (
                            getattr(conf, "maa_mall_enable", True)
                            and getattr(conf, "maa_mall_mode", "maa") == "maa"
                        )
                        or (
                            getattr(conf, "visit_friend_enable", False)
                            and getattr(conf, "visit_friend_mode", "maa") == "maa"
                        ),
                    ):
                        tasks.append("Mall")
                    tasks.append("Award")
                for maa_task in tasks:
                    self.append_maa_task(maa_task)
                self.MAA.start()
                stop_time = None
                if one_time:
                    stop_time = datetime.now() + timedelta(minutes=5)
                else:
                    reset_stage_drop()

                logger.info("MAA 启动")
                hard_stop = False
                while self.MAA.running():
                    self.report_maa_progress()
                    self.recog.update()
                    self.recog.save_screencap(None)
                    # 单次任务默认5分钟
                    if one_time and stop_time < datetime.now():
                        self.maa_stop()
                        hard_stop = True
                    # 5分钟之前就停止
                    elif (
                        not one_time
                        and (self.tasks[0].time - datetime.now()).total_seconds() < 300
                    ):
                        self.maa_stop()
                        hard_stop = True
                    elif config.stop_maa.is_set():
                        self.maa_stop()
                        hard_stop = True
                    else:
                        self.sleep(5)
                # MAA 运行期间只保存截图，没有连续执行 Mower 场景识别。
                self.recog.reset_after_external_control()
                restore_theme = not hard_stop
                if hard_stop:
                    hard_stop_msg = "MAA任务未完成，等待3分钟"
                    logger.info(hard_stop_msg)
                    send_message(hard_stop_msg)
                    self.sleep(180)
                    self.device.exit()
                    if self.device.check_current_focus():
                        self.recog.update()
                elif not one_time:
                    logger.info("记录MAA 本次执行时间")
                    self.last_execution["maa"] = datetime.now()
                    logger.info(self.last_execution["maa"])
                    if "Mall" in tasks and self.credit_fight is None:
                        self.credit_fight = get_server_weekday()
                        logger.info("记录首次信用作战")
                        self.maa_stop(False)
                else:
                    send_message("MAA单次任务停止")
                    if (
                        self.find_next_task(datetime.now() + timedelta(minutes=15))
                        is None
                    ):
                        logger.debug(
                            "MAA单次任务结束15分钟内没有其他任务，新增单次任务防止漏单"
                        )
                        self.tasks.insert(0, SchedulerTask(time=datetime.now()))
            conf = config.conf
            now_time = datetime.now().time()
            try:
                min_time = datetime.strptime(conf.maa_rg_sleep_min, "%H:%M").time()
                max_time = datetime.strptime(conf.maa_rg_sleep_max, "%H:%M").time()
                if max_time < min_time:
                    rg_sleep = now_time > min_time or now_time < max_time
                else:
                    rg_sleep = min_time < now_time < max_time
            except ValueError:
                rg_sleep = False
            if (conf.RG or conf.SSS or conf.RCL) and not rg_sleep:
                logger.info("准备开始：肉鸽/保全/盐酸")
                send_message("启动 肉鸽/保全/盐酸")
                while True:
                    restore_theme = False
                    self.MAA = None
                    self.initialize_maa()
                    self.recog.reset_after_external_control()
                    self.back_to_index()
                    if conf.RG:
                        # Roguelike 通用字段按协议条件下发（#264）：投资类字段仅在
                        # investment_enabled 时下发（值内联各自的策略/主题限制，与 MAA 一致），
                        # stop_at_final_boss 除 Phantom 外可用且仅策略 0 下发，
                        # expected_collapsal_paradigms 仅 Sami + 策略 5 且列表非空时下发，
                        # 烧水字段仅策略 4 下发，勾选「只凹开局干员直升精二」时
                        # 撤销 collectible_mode_start_list，指路鳞的值内联 Mizuki 限制。
                        # 月度小队/深入调查字段仅策略 6/7 下发（通信检查需先勾自动切换），
                        # first_floor_foldartal 与 start_foldartal_list 仅 Sami + 策略 4
                        # （板子列表另限生活至上分队），黑流树海字段仅刷襁褓动物模式下发，
                        # find_playTime_target 仅界园刷常乐节点模式下发。
                        professional = conf.rogue.squad in _PROFESSIONAL_SQUADS
                        rogue_params = {
                            "theme": conf.maa_rg_theme,
                            "squad": conf.rogue.squad,
                            "roles": conf.rogue.roles,
                            "core_char": conf.rogue.core_char,
                            "use_support": conf.rogue.use_support,
                            "use_nonfriend_support": conf.rogue.use_nonfriend_support,
                            "mode": conf.rogue.mode,
                            "starts_count": 9999999,
                            "investments_count": 9999999,
                            "difficulty": conf.rogue.difficulty,
                            "investment_enabled": conf.rogue.investment_enabled,
                            "refresh_trader_with_dice": (
                                conf.maa_rg_theme == "Mizuki"
                                and conf.rogue.refresh_trader_with_dice
                            ),
                        }
                        if conf.rogue.investment_enabled:
                            rogue_params["investment_with_more_score"] = (
                                conf.maa_rg_theme != "BlackFlow"
                                and conf.rogue.investment_with_more_score
                                and conf.rogue.mode == 1
                            )
                            rogue_params["stop_when_investment_full"] = (
                                conf.rogue.stop_when_investment_full
                                and conf.rogue.mode == 1
                            )
                        if conf.maa_rg_theme != "Phantom" and conf.rogue.mode == 0:
                            rogue_params["stop_at_final_boss"] = (
                                conf.rogue.stop_at_final_boss
                            )
                        if conf.rogue.mode == 0:
                            rogue_params["stop_at_max_level"] = (
                                conf.rogue.stop_at_max_level
                            )
                        if (
                            conf.maa_rg_theme == "Sami"
                            and conf.rogue.mode == 5
                            and conf.rogue.expected_collapsal_paradigms
                        ):
                            rogue_params["expected_collapsal_paradigms"] = (
                                conf.rogue.expected_collapsal_paradigms
                            )
                        if conf.rogue.mode == 4:
                            rogue_params["collectible_mode_shopping"] = (
                                conf.rogue.collectible_mode_shopping
                            )
                            rogue_params["collectible_mode_squad"] = (
                                conf.rogue.collectible_mode_squad
                            )
                            # 协议值语义：直升需与战术分队类同步，只凹仅受主题/策略限制
                            rogue_params["start_with_elite_two"] = (
                                conf.rogue.start_with_elite_two
                                and professional
                                and conf.maa_rg_theme in ("Mizuki", "Sami")
                            )
                            rogue_params["only_start_with_elite_two"] = (
                                conf.rogue.only_start_with_elite_two
                                and conf.maa_rg_theme in ("Mizuki", "Sami")
                            )
                            # 勾选「只凹开局干员直升精二」时不刷奖励，撤销下发
                            elite_two_only = (
                                conf.rogue.only_start_with_elite_two
                                and conf.rogue.start_with_elite_two
                                and conf.maa_rg_theme != "Phantom"
                                and professional
                            )
                            if not elite_two_only:
                                rogue_params["collectible_mode_start_list"] = {
                                    key: conf.rogue.collectible_mode_start_list.get(
                                        key, False
                                    )
                                    for key in _COLLECTIBLE_START_KEYS
                                }
                        if conf.rogue.mode == 6:
                            rogue_params["monthly_squad_auto_iterate"] = (
                                conf.rogue.monthly_squad_auto_iterate
                            )
                            if conf.rogue.monthly_squad_auto_iterate:
                                rogue_params["monthly_squad_check_comms"] = (
                                    conf.rogue.monthly_squad_check_comms
                                )
                        if conf.rogue.mode == 7:
                            rogue_params["deep_exploration_auto_iterate"] = (
                                conf.rogue.deep_exploration_auto_iterate
                            )
                        if (
                            conf.maa_rg_theme == "Sami"
                            and conf.rogue.mode == 4
                            and conf.rogue.first_floor_foldartal
                        ):
                            rogue_params["first_floor_foldartal"] = (
                                conf.rogue.first_floor_foldartal
                            )
                        if (
                            conf.maa_rg_theme == "Sami"
                            and conf.rogue.mode == 4
                            and conf.rogue.squad == "生活至上分队"
                            and conf.rogue.start_foldartal_list
                        ):
                            rogue_params["start_foldartal_list"] = (
                                conf.rogue.start_foldartal_list
                            )
                        if (
                            conf.maa_rg_theme == "BlackFlow"
                            and conf.rogue.mode == 30001
                        ):
                            # 协议固定刷襁褓动物策略，仅目标品种可选
                            rogue_params["blackflow_strategy"] = "baby_animal"
                            rogue_params["blackflow_cultivation_target"] = (
                                conf.rogue.blackflow_cultivation_target
                            )
                        if (
                            conf.maa_rg_theme == "JieGarden"
                            and conf.rogue.mode == 20001
                        ):
                            rogue_params["find_playTime_target"] = (
                                conf.rogue.find_playtime_target
                            )
                        self.MAA.append_task("Roguelike", rogue_params)
                    elif conf.SSS:
                        copilot = get_path("@app/sss.json")
                        if (
                            not copilot.is_file()
                            or conf.sss.type not in [1, 2]
                            or conf.sss.ec not in [1, 2, 3]
                        ):
                            raise Exception("保全派驻配置错误")
                        if self.to_sss():
                            raise Exception("保全派驻导航失败")
                        self.MAA.append_task(
                            "SSSCopilot",
                            {"filename": str(copilot), "loop_times": 9999999},
                        )
                    elif conf.RCL:
                        self.to_reclamation(conf.maa_rcl_theme, conf.rcl.mode)
                        self.MAA.append_task(
                            "Reclamation",
                            {
                                "theme": conf.maa_rcl_theme,
                                "mode": conf.rcl.mode,
                                "tools_to_craft": conf.rcl.tools_to_craft,
                                "increment_mode": conf.rcl.increment_mode,
                                "num_craft_batches": conf.rcl.num_craft_batches,
                            },
                        )
                    logger.info("启动")
                    self.MAA.start()
                    while self.MAA.running():
                        csleep(5)
                        self.report_maa_progress()
                        self.recog.update()
                        self.recog.save_screencap(None)
                        if (
                            self.tasks[0].time - datetime.now() < timedelta(seconds=30)
                            or config.stop_maa.is_set()
                        ):
                            self.maa_stop()
                            restore_theme = True
                            break
                    self.recog.reset_after_external_control()
                    break

            elif not rg_sleep:
                if conf.RA:
                    self.back_to_index()
                    ra_solver = ReclamationAlgorithm(self.device, self.recog)
                    ra_solver.run(self.tasks[0].time - datetime.now())
                elif conf.SF:
                    self.back_to_index()
                    sf_solver = SecretFront(self.device, self.recog)
                    sf_solver.run(self.tasks[0].time - datetime.now())

            if restore_theme:
                self.restore_maa_theme()
            self.MAA = None
        except (MowerExit, DeviceRecoveryError, SharedADBError):
            if self.MAA is not None:
                self.maa_stop()
                logger.info("停止MAA")
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
            self.MAA = None
            battle_inventory_active.clear()
            send_message(str(e), "MAA调用出错！", level="ERROR")
            remaining_time = (self.tasks[0].time - datetime.now()).total_seconds()
            if remaining_time > 0:
                # 参照 rest_until_next_task：休眠前重置场景计时，避免 check_freeze
                # 把这段休眠当成「同一场景超时」而再次调用 device.exit() 关闭游戏。
                self.recog.last_scene = None
                logger.info(
                    f"休息 {format_time(remaining_time)}，到{self.tasks[0].time.strftime('%H:%M:%S')}开始工作"
                )
                self._idle_sleep(remaining_time)
        else:
            # 空闲唤醒故障交回设备恢复，不能作为 MAA 任务故障报告。
            battle_inventory_active.clear()
            self.rest_until_next_task()
        finally:
            battle_inventory_active.clear()

    def skland_plan_solver(self):
        solver = None
        try:
            solver = SKLand()
            return solver.start()
        except MowerExit:
            raise
        except Exception as e:
            secrets = getattr(solver, "_log_secrets", ()) if solver else ()
            message = (
                f"森空岛签到失败（{type(e).__name__}）："
                f"{redact_signing_text(e, *secrets)}"
            )
            save_log(message, level="ERROR")
            logger.error(message, extra={"archive_screenshots": False})
            send_message(message, level="ERROR")
        # 仅尝试一次 不再尝试
        return (datetime.now() - timedelta(hours=4)).date()

    def recruit_plan_solver(self):
        if self.last_execution[
            "recruit"
        ] is None or datetime.now() > self.last_execution["recruit"] + timedelta(
            hours=config.conf.recruit_gap
        ):
            RecruitSolver(self.device, self.recog).run()

            self.last_execution["recruit"] = datetime.now()
            logger.info(f"下一次公开招募执行时间在{config.conf.recruit_gap}小时之后")

    def apply_maa_stage_inventory_rules(self, stages) -> list[str]:
        conf = config.conf
        original = list(stages)
        if not conf.maa_stage_inventory_enable:
            return original

        from arknights_mower.utils.maa_stage_inventory import (
            load_inventory_snapshot,
            select_stages_by_inventory,
        )

        if not conf.maa_stage_limit_rules and not conf.maa_stage_ratio_rules:
            return select_stages_by_inventory(original)["stages"]

        inventory, updated_at = load_inventory_snapshot()
        selection = select_stages_by_inventory(
            original,
            limit_rules=conf.maa_stage_limit_rules,
            ratio_rules=conf.maa_stage_ratio_rules,
            inventory=inventory,
        )
        if selection["limit_skipped"]:
            logger.info(
                "库存达到上限，跳过关卡: %s",
                selection["limit_skipped"],
            )
        for decision in selection["ratio_decisions"]:
            logger.info(
                "库存比例选关 | rule=%s | selected=%s | candidates=%s",
                decision["name"],
                decision["selected"],
                decision["candidates"],
            )
        logger.info(
            "库存选关完成 | snapshot=%s | original=%s | selected=%s",
            updated_at,
            original,
            selection["stages"],
        )
        return selection["stages"]

    def mower_stage_plan(self, excluded_stages=()) -> list[str]:
        self.maybe_switch_expired_activity_plan()
        plan = config.conf.maa_weekly_plan[get_server_weekday()]
        stages = []
        for stage in plan.stage:
            if not isinstance(stage, str):
                continue
            stage = stage.strip()
            if not stage or stage in excluded_stages:
                continue
            stages.append(stage)
        return self.apply_maa_stage_inventory_rules(stages)

    def mower_stage_ap_cost(self, stage_id: str) -> int | None:
        stage_meta = next(
            (item for item in stage_data_full if item.get("id") == stage_id),
            None,
        )
        if stage_meta is None:
            return self._ap_fallback_or_none()
        ap_cost = stage_meta.get("apCost")
        if not isinstance(ap_cost, int) or ap_cost <= 0:
            return self._ap_fallback_or_none()
        return ap_cost

    def _ap_fallback_or_none(self) -> int | None:
        from arknights_mower.utils.config import conf

        fallback = conf.ap_fallback
        if isinstance(fallback, int) and fallback > 0:
            return fallback
        return None

    def clear_local_operation_followups(self):
        existing_count = sum(
            1 for task in self.tasks if task.meta_data == FOLLOWUP_TASK_META
        )
        self.tasks = [
            task for task in self.tasks if task.meta_data != FOLLOWUP_TASK_META
        ]
        self.local_operation_followup_time = None
        if existing_count:
            logger.info(
                "clear local operation follow-up tasks | count=%s",
                existing_count,
            )

    def upsert_local_operation_followup(self, run_at: datetime | None):
        self.clear_local_operation_followups()
        if run_at is None:
            logger.info("skip local operation follow-up insert because run_at is empty")
            return
        self.tasks.append(SchedulerTask(time=run_at, meta_data=FOLLOWUP_TASK_META))
        self.tasks.sort(key=lambda task: task.time)
        self.local_operation_followup_time = run_at
        logger.info(
            "schedule local operation follow-up task | run_at=%s",
            run_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def get_local_operation_stage_target(
        self,
        stage: str,
        simulated_current_ap: int | None,
        threshold_control_failed: bool,
        threshold: int,
        maa_gap: float,
    ):
        ap_cost = self.mower_stage_ap_cost(stage)
        projection = None
        if threshold_control_failed:
            target_total_runs = get_stage_drain_runs_total(
                simulated_current_ap,
                ap_cost,
            )
        else:
            target_total_runs, projection = get_required_runs_total(
                simulated_current_ap,
                threshold,
                maa_gap,
                ap_cost,
            )
        return ap_cost, target_total_runs, projection

    def run_local_operation_stage(
        self,
        stage: str,
        next_task_time: datetime,
        simulated_current_ap: int | None,
        ap_cost: int | None,
        target_total_runs: int | None,
        mode: str,
        threshold: int | None = None,
    ):
        remaining_runs = target_total_runs
        executed_any = False

        while True:
            if next_task_time - datetime.now() < timedelta(minutes=5):
                logger.info("skip local operation because time is not enough")
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": True,
                }
            if remaining_runs is not None and remaining_runs <= 0:
                logger.info(
                    "local operation stage completed | stage=%s | mode=%s",
                    stage,
                    mode,
                )
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }

            logger.info(
                "start navigation before operation | stage=%s | mode=%s | simulated_current_ap=%s | ap_cost=%s | remaining_runs=%s",
                stage,
                mode,
                simulated_current_ap,
                ap_cost,
                remaining_runs,
            )
            if not NavigationSolver(self.device, self.recog).run(stage):
                logger.warning(f"navigation failed, skip stage: {stage}")
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }

            logger.info(
                "navigation succeeded, start operation | stage=%s | mode=%s | target_total_runs=%s",
                stage,
                mode,
                remaining_runs,
            )
            result = OperationSolver(self.device, self.recog).run(
                next_task_time=next_task_time,
                stage_id=stage,
                target_total_runs=remaining_runs,
                simulated_current_ap=simulated_current_ap,
                ap_cost=ap_cost,
                sanity_threshold=threshold,
            )
            logger.info(
                "local operation stage result | stage=%s | mode=%s | result=%s",
                stage,
                mode,
                result,
            )

            simulated_current_ap = (
                simulated_current_ap
                if result["simulated_current_ap"] is None
                else result["simulated_current_ap"]
            )
            if result["executed_runs"] > 0:
                executed_any = True
            if result.get("inventory_unconfirmed", False):
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": True,
                    "inventory_unconfirmed": True,
                }
            if result["sanity_drain"] or result["stopped_by_deadline"]:
                logger.info(
                    "stop local operation stage loop | stage=%s | mode=%s | sanity_drain=%s | stopped_by_deadline=%s",
                    stage,
                    mode,
                    result["sanity_drain"],
                    result["stopped_by_deadline"],
                )
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": True,
                }
            if result.get("stopped_by_inventory", False):
                logger.info("库存达到上限，结束当前本地刷关: %s", stage)
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }
            if remaining_runs is None:
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }

            next_remaining_runs = result["remaining_runs"]
            if next_remaining_runs is None or next_remaining_runs <= 0:
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }
            if result["executed_runs"] <= 0:
                logger.warning(
                    "local operation stage made no progress, stop rerun loop | stage=%s | mode=%s | remaining_runs=%s",
                    stage,
                    mode,
                    next_remaining_runs,
                )
                return {
                    "simulated_current_ap": simulated_current_ap,
                    "executed_any": executed_any,
                    "should_break": False,
                }

            remaining_runs = next_remaining_runs
            logger.info(
                "local operation stage has remaining runs, rerun after renavigation | stage=%s | mode=%s | remaining_runs=%s | simulated_current_ap=%s",
                stage,
                mode,
                remaining_runs,
                simulated_current_ap,
            )

    def mower_plan_solver(self, one_time=False):
        try:
            conf = config.conf
            followup_due = (
                self.local_operation_followup_time is not None
                and datetime.now() >= self.local_operation_followup_time
            )
            if followup_due:
                self.local_operation_followup_time = None
            logger.info(
                "start mower_plan_solver | one_time=%s | followup_due=%s | last_execution=%s | current_tasks=%s",
                one_time,
                followup_due,
                self.last_execution["maa"],
                len(self.tasks),
            )
            if (
                not one_time
                and not followup_due
                and self.last_execution["maa"] is not None
                and (
                    delta := (
                        timedelta(hours=conf.maa_gap)
                        + self.last_execution["maa"]
                        - datetime.now()
                    )
                )
                > timedelta()
            ):
                logger.info(
                    f"{format_time(delta.total_seconds())} later start local daily tasks"
                )
            else:
                stages = self.mower_stage_plan()
                logger.info(f"local operation plan: {stages}")
                next_task_time = (
                    datetime.now() + timedelta(days=1)
                    if one_time
                    else self.tasks[0].time
                )
                logger.info(
                    "local operation scheduling window | next_task_time=%s | one_time=%s",
                    next_task_time.strftime("%Y-%m-%d %H:%M:%S"),
                    one_time,
                )

                executed_any = False
                inventory_unconfirmed = False
                threshold_control_failed = False
                threshold_control_reason = ""
                next_threshold_time = None
                simulated_current_ap = None
                threshold = 0

                if stages:
                    player_info = PlayerInfoClient()
                    snapshot = player_info.get_first_available_snapshot()
                    if snapshot is None:
                        logger.warning(
                            "failed to fetch skland player info, fallback to drain sanity"
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
                        logger.info(
                            "loaded local operation sanity context | skland_seed_ap=%s | threshold=%s | maa_gap=%s",
                            simulated_current_ap,
                            threshold,
                            conf.maa_gap,
                        )
                        if threshold <= 0:
                            logger.info(
                                "disable threshold control because threshold <= 0, fallback to drain sanity mode"
                            )
                            threshold_control_failed = True
                            threshold_control_reason = "threshold_non_positive"
                        if any(
                            self.mower_stage_ap_cost(stage) is None for stage in stages
                        ):
                            missing = [
                                stage
                                for stage in stages
                                if self.mower_stage_ap_cost(stage) is None
                            ]
                            logger.error(
                                f"关卡信息未找到，无法获取体力消耗: {missing}，"
                                "请在「刷理智周计划」中设置 AP fallback（关卡体力消耗默认值）"
                            )
                            logger.warning(
                                "stage apCost missing in weekly plan, disable threshold control and fallback to drain sanity"
                            )
                            threshold_control_failed = True
                            threshold_control_reason = "missing_ap_cost"

                if not stages:
                    logger.info(
                        "skip local operation because weekly plan has no stages"
                    )
                    self.clear_local_operation_followups()
                else:
                    mode = "fallback" if threshold_control_failed else "threshold"
                    logger.info(
                        "enter local operation stage loop | mode=%s | reason=%s",
                        mode,
                        threshold_control_reason or "",
                    )
                    self.back_to_index()
                    if threshold_control_failed:
                        self.clear_local_operation_followups()

                    attempted_stages = set()
                    while True:
                        # Confirmed drops can cap later stages or unlock fallback stages.
                        stages = self.mower_stage_plan(excluded_stages=attempted_stages)
                        if not stages:
                            break
                        stage = stages[0]
                        attempted_stages.add(stage)
                        if next_task_time - datetime.now() < timedelta(minutes=5):
                            logger.info(
                                "skip local operation because time is not enough"
                            )
                            break

                        if (
                            not threshold_control_failed
                            and self.mower_stage_ap_cost(stage) is None
                        ):
                            threshold_control_failed = True
                            threshold_control_reason = "missing_ap_cost"
                            mode = "fallback"
                            self.clear_local_operation_followups()
                            logger.warning(
                                "reselected stage apCost missing, disable threshold control | stage=%s",
                                stage,
                            )

                        ap_cost, target_total_runs, projection = (
                            self.get_local_operation_stage_target(
                                stage,
                                simulated_current_ap,
                                threshold_control_failed,
                                threshold,
                                conf.maa_gap,
                            )
                        )

                        if threshold_control_failed:
                            logger.info(
                                "local operation fallback evaluation | stage=%s | ap_cost=%s | simulated_current_ap=%s | target_total_runs=%s",
                                stage,
                                ap_cost,
                                simulated_current_ap,
                                target_total_runs,
                            )
                        else:
                            logger.info(
                                "local operation threshold evaluation | stage=%s | ap_cost=%s | simulated_current_ap=%s | threshold=%s | projection_minutes=%s | projected_ap=%s | excess_ap=%s | target_total_runs=%s",
                                stage,
                                ap_cost,
                                simulated_current_ap,
                                threshold,
                                projection.projection_minutes,
                                projection.projected_ap,
                                projection.excess_ap,
                                target_total_runs,
                            )

                        if (
                            simulated_current_ap is not None
                            and ap_cost is not None
                            and simulated_current_ap < ap_cost
                        ):
                            logger.info(
                                "skip stage because simulated ap is below stage cost | stage=%s | simulated_current_ap=%s | ap_cost=%s",
                                stage,
                                simulated_current_ap,
                                ap_cost,
                            )
                            continue
                        if target_total_runs is not None and target_total_runs <= 0:
                            logger.info(
                                "skip stage because target_total_runs is zero | stage=%s",
                                stage,
                            )
                            continue

                        stage_run_result = self.run_local_operation_stage(
                            stage=stage,
                            next_task_time=next_task_time,
                            simulated_current_ap=simulated_current_ap,
                            ap_cost=ap_cost,
                            target_total_runs=target_total_runs,
                            mode=mode,
                            threshold=None if threshold_control_failed else threshold,
                        )
                        simulated_current_ap = stage_run_result["simulated_current_ap"]
                        executed_any = executed_any or stage_run_result["executed_any"]
                        if stage_run_result.get("inventory_unconfirmed", False):
                            inventory_unconfirmed = True
                            self.clear_local_operation_followups()
                        if stage_run_result["should_break"]:
                            break

                    remaining_stages = self.mower_stage_plan()
                    if not remaining_stages:
                        self.clear_local_operation_followups()
                    if (
                        remaining_stages
                        and not inventory_unconfirmed
                        and not threshold_control_failed
                        and not one_time
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
                        logger.info(
                            "computed local operation follow-up time | simulated_current_ap=%s | threshold=%s | projection_minutes=%s | projected_ap=%s | excess_ap=%s | next_threshold_time=%s",
                            simulated_current_ap,
                            threshold,
                            projection.projection_minutes,
                            projection.projected_ap,
                            projection.excess_ap,
                            next_threshold_time.strftime("%Y-%m-%d %H:%M:%S")
                            if next_threshold_time is not None
                            else None,
                        )
                        self.upsert_local_operation_followup(next_threshold_time)

                logger.info("run mission solver after local operation")
                MissionSolver(self.device, self.recog).run()
                if executed_any or inventory_unconfirmed:
                    self.last_execution["maa"] = datetime.now()
                    logger.info(
                        f"record local task execution time: {self.last_execution['maa']}"
                    )
                else:
                    logger.info("local operation finished without executing any stage")

            scheduling(self.tasks, op_data=getattr(self, "op_data", None))
        except (MowerExit, DeviceRecoveryError):
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
            self.device.exit()
            send_message(str(e), "mower local operation error", level="ERROR")
            self.check_current_focus()

    def mail_plan_solver(self):
        if config.conf.check_mail_enable:
            MailSolver(self.device, self.recog).run()
        return True

    def report_plan_solver(self):
        if config.conf.report_enable:
            return ReportSolver(self.device, self.recog).run()

    def visit_friend_plan_solver(self):
        if config.conf.visit_friend_enable and config.conf.visit_friend_mode == "mower":
            return CreditSolver(self.device, self.recog).run()

    def sign_in_plan_solver(self):
        if not config.conf.sign_in.enable:
            return
        try:
            import sign_in

            sign_in_solver = sign_in.SignInSolver(self.device, self.recog)
            return sign_in_solver.run()
        except MowerExit:
            raise
        except Exception as e:
            save_exception(e)
            logger.exception(e)
            return True

    def 仓库扫描(self):
        try:
            cultivateDepotSolver().start()
            DepotSolver(self.device, self.recog).run()
            self._auto_schedule_mastery_after_scan()
        except Exception as e:
            save_exception(e)
            logger.exception(f"先不运行 出bug了 : {e}")
            return False
        return True

    def _auto_schedule_mastery_after_scan(self):
        try:
            from arknights_mower.utils.mastery_db import retry_failed_plans

            retried = retry_failed_plans()
            if retried > 0:
                logger.info(f"仓库扫描: 已重置 {retried} 个失败的专精计划为待执行")

            from arknights_mower.utils.mastery_recommendation import (
                auto_schedule_mastery_tasks,
            )

            res = auto_schedule_mastery_tasks()
            logger.debug(
                "仓库扫描: 专精调度完毕, "
                f"scheduled={len(res.get('scheduled', []))}, "
                f"skipped={len(res.get('skipped', []))}"
            )

            # #74 第3段：扫描 = 唯一周期派发点。对 DB 里材料足够的 idle 计划入队
            # 「开始训练」SKILL_UPGRADE（plan_key 指定计划；房间状态决定开始/收集）。
            # 材料判断用 auto_schedule 的 scheduled 结果（扫描时核算），不违背「删材料
            # 门控」——删的是开始前现场查那套。受 enable_mastery 门控（OFF 停专精自动化）。
            if config.conf.enable_mastery:
                self._dispatch_scan_start_tasks(res.get("scheduled", []))

            from arknights_mower.utils.workshop_automation import update_workshop_config

            update_workshop_config()
        except Exception as e:
            logger.exception(
                f"自动安排专精/合成配置失败: {e}",
                extra={"archive_screenshots": False},
            )

    def _dispatch_scan_start_tasks(self, scheduled):
        """材料确认后，为材料足够的 idle 计划入队「开始训练」任务。

        scheduled 来自 auto_schedule_mastery_tasks（已按链级材料核算），元素带
        char_id/skill_index。按 (char_id, skill_index) 匹配 DB 里 status=='idle' 的
        计划（get_all_plans 按 priority, id 排序 → 高优先级计划先入队先开始），入队一条
        plan_key=计划id 的开始任务（meta_data 仅描述性标签，无逻辑标记）。TASK-01 按
        plan_key 去重恒 ≤1 条，重复扫描原地刷新；计划开始训练后该任务原位升级为收取任务。

        两轮扫描，兜住存量库里的重复计划（同干员同技能多行，见
        doc/mastery-constraints.md §5.1）：第一轮记下正被 reconcile 管着的键
        （arranging/training/waiting_collect），第二轮每个键只对第一条 idle 行派发。
        否则「按行派发」会给同一个技能各发一条一模一样的任务，只有一条能真跑、其余
        扑空报错（实测 `scheduled=1` 却打出「已为 7 个……安排开始训练」）。
        """
        if not scheduled:
            return
        from arknights_mower.solvers.mastery_reader import _schedule_scan_start
        from arknights_mower.utils.mastery_db import (
            get_all_plans,
            get_material_waiting_plan,
        )

        # 带 current_level 的扫描条目：安排步级 = 当前级 + 1（森空岛数据，最可靠）
        confirmed = {
            (entry.get("char_id"), entry.get("skill_index")): entry
            for entry in scheduled
        }
        plans = get_all_plans()  # 非终态，按 priority, id 排序
        # 第一轮：这些键正被 reconcile 管着，同键的重复行不该再去开训练
        managed = {
            (plan["char_id"], plan["skill_index"])
            for plan in plans
            if plan["status"] in ("arranging", "training", "waiting_collect")
        }
        waiting = get_material_waiting_plan(plans)
        if waiting is not None:
            plans = [waiting]
        # 第二轮：每个键只对第一条 idle 行派发（排序后第一条就是该管的那个）
        dispatched = 0
        seen: set = set()
        for plan in plans:
            if plan["status"] != "idle":
                continue
            key = (plan["char_id"], plan["skill_index"])
            if key in managed or key in seen:
                continue
            entry = confirmed.get(key)
            if entry is None:
                continue
            seen.add(key)
            step_level = entry.get("current_level", 0) + 1
            _schedule_scan_start(self, plan, step_level=step_level)
            dispatched += 1
        if dispatched:
            logger.info(f"已为 {dispatched} 个材料足够的空闲专精计划安排开始训练")

    def _idle_sleep(self, remaining_time, allow_wakeup=True):
        """等待任务并统一维护 `sleeping` 与连续场景观测边界。

        普通等待响应调度器唤醒；维护等待仅响应停止信号。
        成功恢复时清理标准画面帧、场景和计时；设备恢复失败时保留待完成的识别复位。
        主循环成功恢复设备后完成复位；取消与错误始终复位 `sleeping`。
        """
        self.sleeping = True
        try:
            end_time = datetime.now() + timedelta(seconds=remaining_time)
            while datetime.now() < end_time:
                refresh_resource_at_boundary()
                if allow_wakeup and config.wake_scheduler.is_set():
                    config.wake_scheduler.clear()
                    break
                csleep(min(1, (end_time - datetime.now()).total_seconds()))
            if config.stop_mower.is_set():
                raise MowerExit
            self._idle_observation_pending = True
            refresh_resource_at_boundary()
            if (
                config.conf.close_simulator_when_idle
                and self._simulator_closed_for_idle
            ):
                logger.info("休眠结束，启动自动关闭的模拟器")
                if not restart_simulator(stop=False, start=True):
                    raise ConnectionError("休眠结束后模拟器启动失败")
                # 启动成功即结束本轮的主动启动，后续连接故障交由正常重连恢复。
                self._simulator_closed_for_idle = False
                self.device.reconnect()
            self.recog.reset_after_external_control()
            self._idle_observation_pending = False
        finally:
            self.sleeping = False

    def rest_until_next_task(self):
        """完成本轮任务后休息到 `tasks[0].time`，是调度器唯一的「任务间空闲」收尾。

        发休息通知、累计任务计数、并真正睡到下个任务。
        maa_plan_solver / mower_plan_solver / __main__ 主循环此前各自复制了
        一份几乎相同的实现，其中两份漏掉了 `sleeping`，正是 /status 卡在
        working 的根因。现在全部收口到这里，只有 `_idle_sleep` 一个状态写入点。
        """
        self._schedule_maintenance_backup_check()
        if any(
            getattr(task, "strict_mood_limit", False)
            or config.conf.enable_mastery
            and task.type == TaskTypes.SWAP_SUPPORT
            for task in self.tasks
        ):
            # 睡眠前计算清退与专精换人的提前量，避免等到原任务时间才避让。
            protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
        first = self.tasks[0]
        remaining_time = (first.time - datetime.now()).total_seconds()
        self.handle_idle_action(remaining_time)
        timezone_offset = config.conf.timezone_offset
        subject = (
            f"休息 {format_time(remaining_time)}，到"
            f"{first.time.strftime('%H:%M:%S')}开始工作"
        )
        context = f"下一次任务:{first.plan if len(first.plan) != 0 else '空任务' if first.type == '' else first.type}"
        logger.info(context)
        logger.info(subject)
        self.task_count += 1
        logger.info(f"第{self.task_count}次任务结束")
        body = task_template.render(
            tasks=[obj.format(timezone_offset) for obj in self.tasks],
            base_scheduler=self,
        )
        send_message(
            body,
            f"休息 {format_time(remaining_time)}，到{first.format(timezone_offset).time.strftime('%H:%M:%S')}开始工作",
        )
        if remaining_time > 0:
            self._idle_sleep(remaining_time)
            self.check_current_focus()

    def handle_idle_action(self, remaining_time=0):
        if config.conf.close_simulator_when_idle and remaining_time > 300:
            if restart_simulator(start=False):
                self._simulator_closed_for_idle = True
            else:
                logger.warning(
                    "空闲关闭模拟器失败，继续等待；请检查所选实例和管理程序。"
                )
        elif config.conf.exit_game_when_idle and remaining_time > 300:
            self.device.exit()
        elif config.conf.return_home_when_idle:
            self.device.return_home()
