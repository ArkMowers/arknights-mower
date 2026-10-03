"""Mower 自动救急的临时驻员、宿舍恢复与正常排班交接。"""

import copy
from datetime import datetime, timedelta

from arknights_mower.data import base_room_list
from arknights_mower.solvers.record import emergency_mood_history, save_current_state
from arknights_mower.utils import config, detector
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_candidates import (
    dorm_candidate_mood,
    dorm_task_reservations,
)
from arknights_mower.utils.dorm_skills import (
    is_group_recovery_manager,
    is_single_recovery_manager,
)
from arknights_mower.utils.emergency_plan import effective_rescue_plan, rescue_plan_for
from arknights_mower.utils.emergency_recovery import (
    ORDINARY_SHIFTS,
    emergency_dorm_plan,
    history_cycle,
    history_rate,
    mood_context,
    native_opportunity,
    primary_names,
    recovery_target,
)
from arknights_mower.utils.emergency_staffing import eligible_worker
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_timing import estimate_dorm_minutes
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Dormitory, Operator
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.resting_correction import suppress_completed_dorm_returns
from arknights_mower.utils.resting_priority import busy_resting_names, has_resting_mood
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_mood_limit_releases,
    protect_priority_tasks,
    try_workshop_tasks,
)

RESUME_META = "自动救急继续安排"
COLLECTION_COOLDOWN = timedelta(minutes=15)


class EmergencyRecoveryMixin:
    def _emergency_active(self):
        state = getattr(self, "emergency_state", None)
        return isinstance(state, dict) and state.get("phase") in (
            "staffing",
            "recovering",
            "returning",
        )

    def _emergency_frozen(self):
        return self._emergency_active() and not getattr(
            self, "_emergency_handoff", False
        )

    def _emergency_replan_releases(self):
        """恢复目标与个人上限共用清退规划；交接期间只保留个人上限。"""
        state = getattr(self, "emergency_state", None) or {}
        targets = state.get("targets", {}) if state.get("phase") != "returning" else {}
        releases = plan_mood_limit_releases(
            self.op_data, recovery_targets=targets, previous_tasks=self.tasks
        )
        refreshed = {task.meta_data for task in releases}
        self.tasks[:] = [
            task
            for task in self.tasks
            if not getattr(task, "emergency_recovery_release", False)
            and (
                not getattr(task, "strict_mood_limit", False)
                or (
                    getattr(self, "_emergency_handoff", False)
                    and task.meta_data not in refreshed
                    and (op := self.op_data.operators.get(task.meta_data)) is not None
                    and op.current_room in task.plan
                    and 0 <= op.current_index < len(task.plan[op.current_room])
                    and task.plan[op.current_room][op.current_index] == "Free"
                )
            )
        ]
        self.tasks.extend(releases)

    def _emergency_operation_fits(self, seconds):
        start = min(
            (
                task.time
                for task in self.tasks
                if getattr(task, "strict_mood_limit", False) and task.plan
            ),
            default=datetime.max,
        )
        return datetime.now() + timedelta(seconds=seconds + 1) < start

    def _emergency_defer_read(self):
        """中断的实际操作使用一次续行任务，不创建周期读心情任务。"""
        due = datetime.now() + timedelta(minutes=1)
        if self._emergency_active():
            self.emergency_state["next_read"] = due
            self.tasks[:] = [
                task
                for task in self.tasks
                if not getattr(task, "emergency_recovery_release", False)
            ]
        meta = "" if getattr(self, "_emergency_startup_pending", False) else RESUME_META
        task = next(
            (
                t
                for t in self.tasks
                if t.meta_data == meta
                and not t.plan
                and t.type == TaskTypes.NOT_SPECIFIC
            ),
            None,
        )
        if task is None:
            self.tasks.append(SchedulerTask(time=due, meta_data=meta))
        else:
            task.time = due
        self._emergency_save()

    def _emergency_read_rooms(self, rooms, *, yield_to_releases=False):
        """读实际名单并清除本房间未出现的旧驻员；不生成工作站纠错。"""
        for name in (getattr(self, "emergency_state", None) or {}).get("targets", {}):
            op = self.op_data.operators.get(name)
            if op is not None and not op.current_room and op.mood_is_prediction:
                op.time_stamp = None
                op.rest_mood_release_limit = None
        state = self.emergency_state if self._emergency_active() else None
        rooms = sorted(
            room for room in set(rooms) if room in self.op_data.plan and room != "train"
        )
        if yield_to_releases:
            if state is not None:
                rooms = state.setdefault("pending_read_rooms", rooms)
        for room in list(rooms):
            if yield_to_releases and not self._emergency_operation_fits(
                estimate_dorm_minutes(room) * 60
            ):
                self.back_to_infrastructure()
                return False
            self.enter_room(room)
            previous = {
                op.name
                for op in self.op_data.operators.values()
                if op.current_room == room
            }
            observed = self.get_agent_from_room(room, None, force_mood=True)
            actual = {item["agent"] for item in observed if item.get("agent")}
            for name in previous - actual:
                op = self.op_data.operators[name]
                op.current_room, op.current_index = "", -1
                op.time_stamp = None
            self.back()
            if yield_to_releases:
                rooms.remove(room)
                self._emergency_replan_releases()
                protect_priority_tasks(self.tasks)
                self._emergency_save()
        self.back_to_infrastructure()
        if yield_to_releases and state is not None:
            state.pop("pending_read_rooms", None)
        return True

    def _emergency_sync_reservations(self):
        state = getattr(self, "emergency_state", None) or {}
        self.op_data.emergency_run_order_replacements = (
            state.get("run_order_replacements", {})
            if state and state.get("phase") != "returning"
            else None
        )
        self.op_data.emergency_reserved_agents = (
            set(state.get("ready_members", ()))
            | set(state.get("staffing_members", ()))
            | set(state.get("release_members", ()))
        )

    def _emergency_save(self):
        self._emergency_sync_reservations()
        if not save_current_state():
            raise RuntimeError("自动救急运行状态保存失败，未安排临时换班")

    def _emergency_startup(self):
        """初始化检查一次；恢复已有批次先核对实际驻员及未完成安排。"""
        if getattr(self, "emergency_state", None) is not None:
            self._emergency_validate_state()
        if not self._emergency_active() and getattr(
            getattr(self, "task", None), "strict_mood_limit", False
        ):
            return
        if getattr(self, "_initial_fia_checked", False) and any(
            getattr(task, "initial_fia", False) for task in self.tasks
        ):
            return
        if self._emergency_active():
            self.plan_metadata()
        else:
            self._emergency_replan_releases()
        protect_priority_tasks(self.tasks)
        if self._emergency_active() and self.emergency_state.get("handoff_observing"):
            self._emergency_startup_pending = False
            self._emergency_defer_read()
            return
        if not hasattr(self, "_initial_mood_refresh_rooms"):
            self._initial_mood_refresh_rooms = {
                room for room in self.op_data.plan if room in base_room_list
            }
        observed = self._read_agent_mood()
        if observed is False or not self._emergency_operation_fits(45):
            self._emergency_startup_pending = True
            self._emergency_defer_read()
            return
        self._read_initial_card_mood()
        if self._queue_initial_fia():
            return
        self.defer_backup_plan_until_mood_read = False
        if self._emergency_active():
            self.emergency_state.pop("pending_read_rooms", None)
            self.emergency_state.pop("read_collection_pending", None)
            if self.emergency_state["phase"] != "returning":
                self._open_emergency_beds()
            self.emergency_state["next_read"] = datetime.now()
            self.emergency_state["observed_at"] = datetime.now()
            self.emergency_state["temporary_roster"] = {
                room: self.op_data.get_current_room(room, True)
                for room in self.op_data.plan
                if not room.startswith("dorm")
            }
            self._emergency_startup_pending = False
            return
        self.backup_plan_solver()
        self._emergency_startup_pending = False
        self._emergency_save()
        if not config.conf.automatic_rescue_enable:
            return
        data = self.op_data
        names = primary_names(data)
        required = []
        low_groups = set()
        now = datetime.now()
        for name in names:
            op = data.operators[name]
            if (
                not has_resting_mood(op)
                or op.mood_is_prediction
                or data._can_standby(op)
            ):
                continue
            if op.mood < data.rescue_mood_threshold(op):
                low_groups.add(("group", op.group) if op.group else ("operator", name))
                if not op.is_resting():
                    required.append(name)
        if not required or len(low_groups) < 2:
            return
        projection = native_opportunity(self, required, now, current_only=True)
        if projection.opportunity is not None:
            logger.info("当前原生轮休可执行，不启动自动救急")
            return
        if not projection.complete:
            logger.info("原生轮休检查未完成，不启动自动救急：%s", projection.reason)
            return
        try:
            resolved = effective_rescue_plan(data, config.conf.automatic_rescue_plan)
        except ValueError as exc:
            logger.warning("自动救急未启动：%s，请在设置旁填写救急主表", exc)
            return
        rescue_plan = resolved["rescue_plan"]
        shared = set(names) & {name for row in rescue_plan.values() for name in row}
        if shared:
            logger.warning(
                "自动救急驻员与正常主班重名，仍按救急排班持续工作：%s",
                "、".join(sorted(shared)),
            )
        names = [name for name in names if name not in shared]
        logger.info(
            "多组主班实测低于救急线且当前原生轮休无法安排，启动自动救急：%s", required
        )
        state = {
            **resolved,
            "phase": "staffing",
            "frozen_conditions": list(data.plan_condition),
            "backup_names": [backup.name for backup in data.backup_plans],
            "work_contexts": {
                name: mood_context(data, data.operators[name].room) for name in names
            },
            "targets": {name: recovery_target(data, name)[0] for name in names},
            "target_sources": {name: "fallback" for name in names},
            "target_basis": {},
            "temporary_roster": {},
            "next_read": now,
        }
        self.emergency_state = state
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.type
            not in ORDINARY_SHIFTS | {TaskTypes.FILL_DORM, TaskTypes.RELEASE_DORM}
            and not getattr(task, "backup_shift_active", False)
            and not (
                task.type == TaskTypes.NOT_SPECIFIC
                and any(not room.startswith("dorm") for room in task.plan)
                and not getattr(task, "emergency_staffing", False)
            )
        ]
        state["observed_at"] = datetime.now()
        self._emergency_save()

    def _emergency_validate_state(self):
        state = self.emergency_state
        if not (
            isinstance(state, dict)
            and state.get("phase") in ("staffing", "recovering", "returning")
            and isinstance(state.get("rescue_plan"), dict)
            and isinstance(state.get("targets"), dict)
            and isinstance(state.get("backup_names"), list)
            and isinstance(state.get("frozen_conditions"), list)
            and isinstance(state.get("work_contexts"), dict)
            and len(state["backup_names"]) == len(state["frozen_conditions"])
            and all(
                isinstance(value, (int, float)) and 0 <= value < float("inf")
                for value in state["targets"].values()
            )
        ):
            raise MowerExit("自动救急缓存结构不完整，保留缓存并停止")

    def _emergency_schedule_staffing(self):
        """按本轮生效救急排班部署驻员，沿用训练室换人保护。"""
        state, data = self.emergency_state, self.op_data
        if (
            state.get("release_plan") is not None
            or state["phase"] == "returning"
            or any(getattr(task, "emergency_staffing", False) for task in self.tasks)
        ):
            return True
        if state.get("staffing_complete"):
            return True
        plan = rescue_plan_for(data, state["rescue_plan"])
        if "train" in plan:
            self._suppress_train_correction(plan)
        reserved, _ = dorm_task_reservations(data, self.tasks)
        reserved |= busy_resting_names()
        reserved.update(
            name
            for rows in state.get("run_order_replacements", {}).values()
            for row in rows
            for name in row
        )
        pending = {}
        for room, names in plan.items():
            current = data.get_current_room(room, True)
            if current is not None and all(
                name == "Current" or index < len(current) and current[index] == name
                for index, name in enumerate(names)
            ):
                continue
            if any(
                hasattr(task, "emergency_original_roster")
                and room in set(task.plan) | set(task.emergency_original_roster)
                for task in self.tasks
            ):
                logger.info("自动救急 %s：等待专项任务恢复原驻员后执行救急主表", room)
                return False
            for index, name in enumerate(names):
                if name in ("", "Current"):
                    continue
                if (
                    current is not None
                    and index < len(current)
                    and current[index] == name
                ):
                    continue
                mood = dorm_candidate_mood(data, name, datetime.now())
                if not eligible_worker(data, name, mood, reserved):
                    logger.warning(
                        "自动救急 %s：救急主表干员 %s 心情不足、读数未知或被预约，暂缓换班",
                        room,
                        name,
                    )
                    return False
            pending[room] = list(names)
        if not pending:
            state["staffing_complete"] = True
            state["staffing_plan"] = {}
            state.pop("staffing_members", None)
            state["phase"] = "recovering"
            return True
        if not self._emergency_operation_fits(45 * len(pending)):
            return False
        for row in pending.values():
            for name in row:
                if name not in ("", "Current") and name not in data.operators:
                    data.add(Operator(name, ""))
        state["staffing_plan"] = copy.deepcopy(pending)
        state["staffing_members"] = list(state["targets"])
        state["temporary_roster"] = {
            room: data.get_current_room(room, True) for room in plan
        }
        state["phase"] = "staffing"
        self._emergency_save()
        task = SchedulerTask(task_plan=copy.deepcopy(pending))
        task.emergency_staffing = True
        task.emergency_staffing_members = list(state["targets"])
        self.tasks.append(task)
        logger.info("自动救急：按救急主表生成全部工作站换班任务：%s", pending)
        return True

    def _open_emergency_beds(self):
        """按救急宿舍配置，每房先补一名群回，余量再补一名单回。"""
        data, state = self.op_data, self.emergency_state
        layout = state.get("dorm_layout", {})
        if not layout:
            return
        if any(task.type == TaskTypes.FIAMMETTA and task.plan for task in self.tasks):
            return
        data.emergency_dorm_agents = {
            name
            for row in layout.values()
            for name in row
            if name not in ("", "Free", "Current")
        }
        runners = {
            name
            for rows in state.get("run_order_replacements", {}).values()
            for row in rows
            for name in row
        }
        for name in (
            data.emergency_dorm_agents | set(state.get("fia_targets", ())) | runners
        ):
            if name not in data.operators:
                data.add(Operator(name, ""))
        times = {bed.position: bed.time for bed in data.all_dorms()}
        data.dorm, data.group_dorm = [], []
        need = {
            name
            for name, target in state["targets"].items()
            if name not in state.get("ready_members", ())
            and (op := data.operators.get(name)) is not None
            and not data._can_standby(op)
            and (not has_resting_mood(op) or op.mood_is_prediction or op.mood < target)
        }
        capacity = sum(name != "菲亚梅塔" for row in layout.values() for name in row)
        spare = max(0, capacity - len(need))
        reserved, _ = dorm_task_reservations(data, self.tasks)
        restored = {}
        for classify, required_count in (
            (is_group_recovery_manager, 0),
            (is_single_recovery_manager, 1),
        ):
            for index in range(max(map(len, layout.values()))):
                for room, row in layout.items():
                    positions = restored.get(room, ())
                    if (
                        index >= len(row)
                        or spare <= 0
                        or len(positions) != required_count
                        or index in positions
                    ):
                        continue
                    name = row[index]
                    manager = data.operators.get(name)
                    resident = data.get_current_operator(room, index)
                    if (
                        manager is None
                        or name == "菲亚梅塔"
                        or not classify(name)
                        or name in need
                        or name in reserved
                        or manager.is_working()
                        or resident is not None
                        and resident.name in need
                    ):
                        continue
                    restored[room] = (*positions, index)
                    spare -= 1
        for room, row in layout.items():
            for index, name in enumerate(row):
                if name == "菲亚梅塔":
                    fia = data.operators[name]
                    if (fia.current_room, fia.current_index) == (room, index):
                        fia.room, fia.index = room, index
                fixed = name == "菲亚梅塔" or index in restored.get(room, ())
                data.plan[room][index].agent = name if fixed else "Free"
                if fixed:
                    continue
                resident = data.get_current_operator(room, index)
                data.dorm.append(
                    Dormitory(
                        (room, index),
                        resident.name if resident else "",
                        times.get((room, index)),
                    )
                )
        if layout:
            data.refresh_dorm_manager_flags(force=True)

    def _emergency_update_targets(self):
        data, state = self.op_data, self.emergency_state
        if state["phase"] == "returning":
            return
        probe = copy.copy(self)
        normal = copy.deepcopy(data, {id(data.eval_model): data.eval_model})
        if normal.swap_plan(list(state["frozen_conditions"]), refresh=True):
            return
        plan = {
            room: [slot.agent for slot in slots]
            for room, slots in data.plan.items()
            if not room.startswith("dorm")
        }
        probe.op_data = normal.project_arrangements([plan])
        probe.tasks = []
        probe._emergency_handoff = True
        opportunities = {}
        for name in state["targets"]:
            op = data.operators.get(name)
            if op is None or name in state.get("ready_members", ()):
                continue
            rows = emergency_mood_history(name)
            rate = history_rate(rows, op.room, state["work_contexts"].get(name))
            members = data.groups.get(op.group, [name])
            group = tuple(members)
            if rate and group not in opportunities:
                opportunities[group] = native_opportunity(probe, members).opportunity
            opportunity = opportunities.get(group) if rate else None
            cycle = history_cycle(rows, op.room, state["work_contexts"].get(name))
            immediate = opportunity
            if opportunity is not None and cycle is not None:
                opportunity = max(opportunity, datetime.now() + timedelta(hours=cycle))
            # 可执行的充能预约优先使用实测生成的时刻；空的肥鸭任务不证明机会。
            charges = [
                task.time
                for task in self.tasks
                if task.type == TaskTypes.FIAMMETTA
                and task.plan
                and task.meta_data == name
            ]
            if charges and rate:
                opportunity = max(datetime.now(), min(charges))
            target, source = recovery_target(data, name, rate, opportunity)
            if target > op.upper_limit and immediate is not None:
                # 历史周期过长时改用已证明可执行的更早轮休，而非截断目标。
                target, source = recovery_target(data, name, rate, immediate)
                source = "earlier_native_rotation"
            state["targets"][name], state["target_sources"][name] = target, source
            state.setdefault("target_basis", {})[name] = {
                "work_context": state["work_contexts"].get(name),
                "rate": rate,
                "cycle_hours": cycle,
                "opportunity": opportunity,
                "calculated_at": datetime.now(),
                "normal_line": data.resting_mood_threshold(op),
                "source": source,
            }

    def _emergency_run_order_available(self, room, plan=None):
        if not self._emergency_frozen():
            return True
        configured = {
            name
            for row in self.op_data.run_order_replacements(room)
            for name in row
            if name in TRADE_ORDER_AGENTS
        }
        required = (
            {
                name
                for names in plan.values()
                for name in names
                if name in TRADE_ORDER_AGENTS
            }
            if plan
            else {
                name
                for row in self.op_data.run_order_replacements(room)
                for name in row
                if name in TRADE_ORDER_AGENTS
            }
        )
        return (
            bool(required)
            and required <= configured
            and all(
                (op := self.op_data.operators.get(name)) is not None
                and (not op.is_working() or op.current_room == room)
                for name in required
            )
        )

    def _emergency_compensation_available(self, plan):
        """专项补偿等待其他工作设施释放原驻员，不抢占其岗位。"""
        return all(
            (op := self.op_data.operators.get(name)) is None
            or not op.is_working()
            or op.current_room == room
            for room, row in plan.items()
            for name in row
            if name not in ("", "Free", "Current")
        )

    def _emergency_filter_tasks(self):
        if not self._emergency_frozen():
            return
        fia_targets = set(self.emergency_state.get("fia_targets", ()))
        fia_rooms = {
            room
            for room, row in self.emergency_state.get("dorm_layout", {}).items()
            if "菲亚梅塔" in row
        }
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.type not in ORDINARY_SHIFTS
            and not (
                task.type == TaskTypes.FIAMMETTA
                and not hasattr(task, "emergency_original_roster")
                and (not task.plan or task.meta_data)
                and (
                    not fia_targets
                    or not fia_rooms
                    or task.meta_data
                    and (
                        task.meta_data not in fia_targets or set(task.plan) != fia_rooms
                    )
                )
            )
            and not getattr(task, "backup_shift_active", False)
            and not (
                self.emergency_state["phase"] == "returning"
                and getattr(task, "emergency_dorm", False)
            )
            and not (
                task.type == TaskTypes.NOT_SPECIFIC
                and any(not room.startswith("dorm") for room in task.plan)
                and not getattr(task, "emergency_staffing", False)
            )
            and not (
                task.type in (TaskTypes.RUN_ORDER, TaskTypes.REFRESH_TIME)
                and task.meta_data
                and not hasattr(task, "emergency_original_roster")
                and not self._emergency_run_order_available(task.meta_data, task.plan)
            )
        ]

    def _emergency_reconcile_staffing(self):
        """已派发安排以实际驻员核销，尚未读到的房间保留待办。"""
        state = self.emergency_state
        if state["phase"] == "returning" or any(
            getattr(task, "emergency_staffing", False) for task in self.tasks
        ):
            return False
        pending = state.get("staffing_plan", {})
        if not pending:
            return False
        if "train" in pending:
            self._suppress_train_correction(pending)
        state["staffing_plan"] = {
            room: row
            for room, row in pending.items()
            if (actual := self.op_data.get_current_room(room, True)) is None
            or any(
                name != "Current" and (index >= len(actual) or name != actual[index])
                for index, name in enumerate(row)
            )
        }
        if state["staffing_plan"]:
            return False
        state.pop("staffing_members", None)
        state["staffing_complete"] = True
        state["phase"] = "recovering"
        state["temporary_roster"] = {
            room: self.op_data.get_current_room(room, True)
            for room in self.op_data.plan
            if not room.startswith("dorm")
        }
        return True

    def _emergency_observe_recovery(self):
        """正常查询或预计换人时读取相关宿舍；初始化读数直接复用。"""
        state = self.emergency_state

        if state.pop("observed_at", None) is not None:
            return True
        rotation_rooms = {
            room
            for task in self.tasks
            if getattr(task, "emergency_recovery_release", False)
            and task.time <= datetime.now()
            for room in task.plan
        }
        rooms = {
            op.current_room
            for name, target in state["targets"].items()
            if (op := self.op_data.operators.get(name)) is not None
            and op.is_resting()
            and (not has_resting_mood(op) or op.mood_is_prediction or op.mood < target)
            and (
                op.current_room in rotation_rooms
                or op.need_to_refresh()
                or state["phase"] == "returning"
            )
        }
        if "pending_read_rooms" not in state:
            state["read_collection_pending"] = True
            state["pending_read_rooms"] = sorted(rooms)
        if state.get("read_collection_pending"):
            last = self.last_execution.get("todo")
            collection_due = (
                last is None or datetime.now() >= last + COLLECTION_COOLDOWN
            )
            if collection_due and not self._emergency_operation_fits(90):
                return False
            self._emergency_collect()
            state.pop("read_collection_pending", None)
        if self._emergency_read_rooms(rooms, yield_to_releases=True) is False:
            return False
        return True

    def _emergency_tick(self, *, completed_task=None):
        """只有到期观测或已完成的驻员变更推进恢复，不随空转循环重做规划。"""
        self.plan_metadata()
        protect_priority_tasks(self.tasks)
        state = self.emergency_state
        pending_staffing = [
            task for task in self.tasks if getattr(task, "emergency_staffing", False)
        ]
        if pending_staffing:
            state["next_read"] = max(
                state.get("next_read", datetime.now()),
                min(task.time for task in pending_staffing) + timedelta(minutes=1),
                datetime.now() + timedelta(minutes=1),
            )
            self._emergency_save()
            return
        staffing_completed = self._emergency_reconcile_staffing()
        read_due = datetime.now() >= state.get("next_read", datetime.now()) or any(
            getattr(task, "emergency_recovery_release", False)
            and task.time <= datetime.now()
            for task in self.tasks
        )
        read_due = read_due or (
            not any(
                task.meta_data == RESUME_META and task.time > datetime.now()
                for task in self.tasks
            )
            and any(
                op.is_resting() and op.need_to_refresh()
                for name in state["targets"]
                if (op := self.op_data.operators.get(name)) is not None
            )
        )
        specialized_completed = completed_task is not None and (
            completed_task.type
            in (
                TaskTypes.FIAMMETTA,
                TaskTypes.WORKSHOP,
                TaskTypes.SWAP_SUPPORT,
                TaskTypes.RUN_ORDER,
                TaskTypes.DEPOT,
            )
            or getattr(completed_task, "emergency_dorm", False)
            or getattr(completed_task, "strict_mood_limit", False)
        )
        plan_due = read_due or staffing_completed or specialized_completed
        if read_due:
            if state.get("handoff_observing"):
                if not self._emergency_restore():
                    self._emergency_defer_read()
                return
            if not self._emergency_observe_recovery():
                self._emergency_defer_read()
                return
            self.plan_metadata()
            protect_priority_tasks(self.tasks)
        if plan_due:
            self.tasks[:] = [
                task
                for task in self.tasks
                if not getattr(task, "emergency_recovery_release", False)
            ]
            state["ready_members"] = [
                name
                for name in state.get("ready_members", [])
                if (op := self.op_data.operators.get(name)) is not None
                and not op.is_working()
                and has_resting_mood(op)
                and not op.mood_is_prediction
                and op.mood >= state["targets"][name]
            ]
            self._emergency_update_targets()
            self._emergency_release_ready()
            if self._emergency_ready() and self._emergency_restore():
                return
            if state["phase"] == "returning":
                self._emergency_defer_read()
            else:
                self._open_emergency_beds()
                scanned = self._emergency_schedule_staffing()
                if state.get("staffing_complete"):
                    self._emergency_plan_beds(state)
                if not scanned:
                    self._emergency_defer_read()
                elif read_due:
                    state["next_read"] = datetime.now() + timedelta(hours=2)
        self._emergency_sync_reservations()
        if plan_due:
            self._emergency_replan_releases()
            protect_priority_tasks(self.tasks)
        if (
            plan_due
            and state["phase"] == "recovering"
            and not any(
                getattr(task, "emergency_staffing", False) for task in self.tasks
            )
        ):
            try_workshop_tasks(self.op_data, self.tasks)
            self.run_order_solver()
        self._emergency_save()

    def _emergency_plan_beds(self, state):
        plan = emergency_dorm_plan(self.op_data, state, self.tasks)
        for room, original in state.get("dorm_layout", {}).items():
            for index, name in enumerate(original):
                if (
                    name not in ("", "Free", "Current")
                    and self.op_data.plan[room][index].agent == name
                ):
                    current = self.op_data.get_current_operator(room, index)
                    if current is None or current.name != name:
                        plan.setdefault(room, ["Current"] * len(original))[index] = name
        if plan and not any(
            getattr(task, "emergency_dorm", False) for task in self.tasks
        ):
            task = SchedulerTask(task_type=TaskTypes.FILL_DORM, task_plan=plan)
            task.emergency_dorm = True
            self.tasks.append(task)

    def _emergency_release_ready(self):
        """个人实测达标后只清空宿舍位置，待命主班不改变临时工作组合。"""
        state, data = self.emergency_state, self.op_data
        if state["phase"] == "returning" or any(
            getattr(task, "emergency_staffing", False)
            or hasattr(task, "emergency_original_roster")
            or task.plan
            and task.type in (TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER)
            and task.time <= datetime.now()
            for task in self.tasks
        ):
            return False
        ready = set(state.get("ready_members", ()))
        members = set(state.get("release_members", ()))
        plan = {}
        for name, target in state["targets"].items():
            op = data.operators.get(name)
            if (
                op is None
                or op.is_working()
                or not has_resting_mood(op)
                or op.mood_is_prediction
                or op.mood < target
            ):
                continue
            if not op.current_room:
                ready.add(name)
                members.discard(name)
                op.depletion_rate = 0
            elif op.is_resting():
                members.add(name)
                plan.setdefault(
                    op.current_room, ["Current"] * len(data.plan[op.current_room])
                )[op.current_index] = ""
        # 已离宿但实测失效者由 targets 重新入宿，旧清退只保留实际住客。
        members = {
            name
            for name in members
            if name in data.operators and data.operators[name].is_resting()
        }
        changed = ready != set(state.get("ready_members", ())) or members != set(
            state.get("release_members", ())
        )
        state["ready_members"] = sorted(ready)
        state["release_members"] = sorted(members)
        self._emergency_sync_reservations()
        for task in self.tasks:
            if not getattr(task, "emergency_dorm", False):
                continue
            for room, row in list(task.plan.items()):
                task.plan[room] = [
                    "Current" if name in ready | members else name for name in row
                ]
                if all(name == "Current" for name in task.plan[room]):
                    del task.plan[room]
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.plan or not getattr(task, "emergency_dorm", False)
        ]
        if not members:
            state.pop("release_plan", None)
            state.pop("release_members", None)
            if changed:
                self._emergency_save()
            return changed
        if not plan or not self._emergency_operation_fits(
            sum(estimate_dorm_minutes(room) * 60 for room in plan)
        ):
            state["release_members"] = sorted(members)
            state["release_plan"] = copy.deepcopy(plan)
            self._emergency_save()
            return False
        state["release_plan"] = copy.deepcopy(plan)
        state["release_members"] = sorted(members)
        self._emergency_save()
        previous_task = self.task
        self.task = SchedulerTask(task_plan=copy.deepcopy(plan))
        self.task.emergency_staffing = True
        self.task.emergency_recovery_release = True
        self.task.emergency_staffing_members = sorted(members)
        try:
            self.agent_arrange(self.task.plan, get_time=True)
        finally:
            self.task = previous_task
        for name in members:
            op = self.op_data.operators[name]
            if (
                not op.current_room
                and has_resting_mood(op)
                and not op.mood_is_prediction
                and op.mood >= state["targets"][name]
            ):
                ready.add(name)
                op.depletion_rate = 0
        state["ready_members"] = sorted(ready)
        remaining = {
            name
            for name in members - ready
            if self.op_data.operators[name].is_resting()
        }
        if not remaining:
            state.pop("release_plan", None)
            state.pop("release_members", None)
        else:
            state["release_members"] = sorted(remaining)
        self._emergency_save()
        return True

    def _emergency_ready(self):
        if not self.emergency_state.get("staffing_complete"):
            return False
        if (
            self.emergency_state.get("staffing_plan")
            or self.emergency_state.get("release_plan") is not None
        ) or any(getattr(task, "emergency_staffing", False) for task in self.tasks):
            return False
        if any(
            task.plan
            and (
                task.type in (TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER)
                and task.time <= datetime.now()
                or getattr(task, "strict_mood_limit", False)
                and task.time <= datetime.now()
                or hasattr(task, "emergency_original_roster")
            )
            for task in self.tasks
        ):
            return False
        if (
            self.emergency_state["phase"] == "returning"
            and "handoff_plan" in self.emergency_state
        ):
            return True
        if not all(
            (op := self.op_data.operators.get(name)) is not None
            and (
                self.op_data._can_standby(op)
                or has_resting_mood(op)
                and not op.mood_is_prediction
            )
            for name in self.emergency_state["targets"]
        ):
            return False
        if all(
            self.op_data._can_standby(self.op_data.operators[name])
            or self.op_data.operators[name].mood >= target
            for name, target in self.emergency_state["targets"].items()
        ):
            return True
        # 尚未离开工作站的待恢复主班先完成救急换班，避免入口立即交回。
        if any(
            self.op_data.operators[name].is_working()
            and self.op_data.operators[name].mood < target
            for name, target in self.emergency_state["targets"].items()
        ):
            return False
        probe = copy.copy(self)
        probe.op_data = copy.deepcopy(
            self.op_data, {id(self.op_data.eval_model): self.op_data.eval_model}
        )
        probe.tasks = copy.deepcopy(self.tasks)
        probe._emergency_handoff = True
        error = probe.op_data.swap_plan(
            self.emergency_state["frozen_conditions"], refresh=True
        )
        if error:
            return False
        plan = probe._emergency_resting_handoff({})
        return plan is not None and probe._emergency_handoff_feasible(plan)

    def _emergency_resting_handoff(self, plan):
        """复用正常整组替班规划，为交接后仍需休息的组同时预留岗位和床位。"""
        data = self.op_data
        groups = {}
        for name in primary_names(data):
            op = data.operators[name]
            if data._can_standby(op):
                continue
            if not has_resting_mood(op) or op.mood_is_prediction:
                return None
            target = self.emergency_state["targets"].get(
                name, recovery_target(data, name)[0]
            )
            if op.mood < target:
                groups[op.group or name] = data.groups.get(op.group, [name])
        if not groups:
            return plan
        from arknights_mower.utils.emergency_plan import RESCUE_ROOMS

        baseline = {
            room: [slot.agent for slot in row]
            for room, row in data.plan.items()
            if room in RESCUE_ROOMS or room.startswith("dorm")
        }
        probe = copy.copy(self)
        probe.op_data = data.project_arrangements([baseline])
        probe.op_data.emergency_reserved_agents = set()
        probe.op_data.emergency_dorm_agents = set()
        probe.tasks = copy.deepcopy(self.tasks)
        probe.task = None
        probe._emergency_handoff = True
        resting = {}
        replacements = []
        members = list(
            dict.fromkeys(name for group in groups.values() for name in group)
        )
        probe.get_resting_plan(
            members, replacements, resting, probe.op_data.active_high_resting_count()
        )
        if not replacements:
            return None
        for bed in probe.op_data.all_dorms():
            if bed.name:
                room, index = bed.position
                resting.setdefault(room, ["Current"] * len(data.plan[room]))[index] = (
                    bed.name
                )
        result = copy.deepcopy(plan)
        result.update(baseline)
        for room, row in resting.items():
            target = result.setdefault(room, ["Current"] * len(row))
            for index, name in enumerate(row):
                if name != "Current":
                    target[index] = name
        return result

    def _emergency_restore(self):
        """重新求值副表，交接成功后清除批次；失败按实际驻员继续交接。"""
        state = self.emergency_state
        saved_beds = {
            bed.position: (bed.name, bed.time) for bed in self.op_data.all_dorms()
        }
        state["phase"] = "returning"
        self._emergency_filter_tasks()
        self._emergency_handoff = True
        try:
            names = [backup.name for backup in self.op_data.backup_plans]
            previous = dict(
                zip(
                    state.get("handoff_names", state["backup_names"]),
                    state.get("handoff_conditions", state["frozen_conditions"]),
                )
            )
            error = self.op_data.swap_plan(
                [previous.get(name, False) for name in names], refresh=True
            )
            if error:
                raise RuntimeError(error)
            if state.get("handoff_observing"):
                return self._emergency_finish_handoff()
            generated = []
            if "handoff_plan" not in state:
                self.backup_plan_solver(generated_tasks=generated)
            plan = (
                copy.deepcopy(state.get("handoff_plan"))
                if "handoff_plan" in state
                else self.agent_get_mood(read_rooms=False, return_plan=True) or {}
            )
            for task in generated:
                for room, slots in task.plan.items():
                    row = plan.setdefault(room, ["Current"] * len(slots))
                    for index, name in enumerate(slots):
                        if name != "Current":
                            row[index] = name
                suppress_completed_dorm_returns(self.op_data, task.plan)
            suppress_completed_dorm_returns(self.op_data, plan)
            if "handoff_plan" not in state:
                plan = self._emergency_resting_handoff(plan)
                if plan is None:
                    return False
            duration = timedelta(
                minutes=sum(
                    estimate_dorm_minutes(room) if room.startswith("dorm") else 0.75
                    for room in plan
                )
            )
            if not self._emergency_operation_fits(duration.total_seconds()):
                return False
            if not self._emergency_handoff_feasible(plan):
                for key in ("handoff_plan", "handoff_names", "handoff_conditions"):
                    state.pop(key, None)
                return False
            state["handoff_plan"] = copy.deepcopy(plan)
            state["handoff_names"] = names
            state["handoff_conditions"] = list(self.op_data.plan_condition)
            self._emergency_save()
            if plan:
                previous_task = self.task
                self.task = SchedulerTask(task_plan=plan)
                try:
                    arranged = self.agent_arrange(plan, get_time=True)
                finally:
                    self.task = previous_task
                if arranged is False:
                    state["handoff_plan"] = copy.deepcopy(plan)
                    self._emergency_save()
                    return False
            state["handoff_observing"] = True
            self._emergency_save()
            return self._emergency_finish_handoff()
        finally:
            self._emergency_handoff = False
            if self.emergency_state:
                if "handoff_plan" not in state:
                    state["phase"] = "recovering"
                if state["phase"] != "returning":
                    self._open_emergency_beds()
                self._emergency_sync_reservations()
                for bed in self.op_data.all_dorms():
                    saved = saved_beds.get(bed.position)
                    if saved is not None and bed.name == saved[0] and bed.time is None:
                        bed.time = saved[1]

    def _emergency_handoff_feasible(self, plan):
        state = self.emergency_state
        probe = copy.copy(self)
        probe.op_data = self.op_data.project_arrangements([plan])
        probe.tasks = []
        # 各组需要完整替班与床位；不同组不要求同时占满普通床位。
        groups = {}
        feasible = True
        for name in primary_names(probe.op_data):
            op = probe.op_data.operators[name]
            if probe.op_data._can_standby(op):
                continue
            if op.is_resting():
                if not has_resting_mood(op) or op.mood_is_prediction:
                    return False
                if any(
                    not (member := probe.op_data.operators[other]).room.startswith(
                        "dorm"
                    )
                    and member.is_working()
                    and not member.workaholic
                    for other in probe.op_data.groups.get(op.group, [name])
                ):
                    return False
                occupant = probe.op_data.get_current_operator(op.room, op.index)
                if (
                    occupant is None
                    or occupant.name not in probe.op_data.replacement_candidates(op)
                    or not has_resting_mood(occupant)
                    or occupant.mood_is_prediction
                    or probe.op_data.replacement_exhausted(occupant.name)
                ):
                    return False
                continue
            actual = self.op_data.operators.get(name)
            returned = (
                ("handoff_plan" in state)
                and actual is not None
                and actual.is_working()
                and (actual.current_room, actual.current_index) == (op.room, op.index)
            )
            if (
                not has_resting_mood(op)
                or op.mood_is_prediction
                or not returned
                and op.mood
                < state["targets"].get(name, recovery_target(probe.op_data, name)[0])
            ):
                feasible = False
                break
            groups[op.group or name] = probe.op_data.groups.get(op.group, [name])
        if feasible:
            feasible = all(
                native_opportunity(probe, members).opportunity is not None
                for members in groups.values()
            )
        return feasible

    def _emergency_finish_handoff(self):
        state = self.emergency_state
        if (
            self._emergency_read_rooms(
                (room for room in self.op_data.plan if room in base_room_list),
                yield_to_releases=True,
            )
            is False
        ):
            self._emergency_defer_read()
            return False
        if not self._emergency_ready():
            return False
        if not self._emergency_handoff_feasible({}):
            for key in (
                "handoff_observing",
                "handoff_plan",
                "handoff_names",
                "handoff_conditions",
            ):
                state.pop(key, None)
            self._emergency_save()
            return False
        state.pop("handoff_observing", None)
        remaining = self.agent_get_mood(read_rooms=False, return_plan=True)
        if remaining:
            state["handoff_plan"] = copy.deepcopy(remaining)
            self._emergency_save()
            return False
        self.emergency_state = None
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.meta_data != RESUME_META
            and not getattr(task, "emergency_recovery_release", False)
        ]
        self._emergency_sync_reservations()
        self.run_order_solver()
        self.plan_metadata()
        self._emergency_save()
        logger.info("正常排班已接回周转，未恢复的组继续休息，自动救急结束")
        return True

    def _emergency_collect(self):
        """正常查询或宿舍换人时顺便收取，沿用普通收取的防重复间隔。"""
        last = self.last_execution.get("todo")
        if last is not None and datetime.now() < last + COLLECTION_COOLDOWN:
            return
        self.recog.update()
        notification = detector.infra_notification(self.recog.img)
        if notification is None:
            self.last_execution["todo"] = datetime.now()
            return
        self.tap(notification)
        self.scene_graph_navigation(Scene.INFRA_TODOLIST)
        self.todo_list()
        self.scene_graph_navigation(Scene.INFRA_MAIN)
