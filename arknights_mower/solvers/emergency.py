"""Mower 自动救急的临时驻员、宿舍恢复与正常排班交接。"""

import copy
from datetime import datetime, timedelta

from arknights_mower.data import base_room_list
from arknights_mower.solvers.record import emergency_mood_history, save_current_state
from arknights_mower.utils import config, detector
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.dorm_candidates import (
    dorm_candidate_mood,
    dorm_task_reservations,
    retained_task_reservations,
    scheduling_mood_reaches,
)
from arknights_mower.utils.dorm_recovery import compact_dorm_vacancies
from arknights_mower.utils.dorm_skills import (
    is_group_recovery_manager,
    is_single_recovery_manager,
)
from arknights_mower.utils.emergency_plan import effective_rescue_plan, rescue_plan_for
from arknights_mower.utils.emergency_recovery import (
    ORDINARY_SHIFTS,
    NativeProjection,
    emergency_dorm_plan,
    exhaust_rest_due,
    history_cycle,
    history_rate,
    mood_context,
    native_opportunity,
    primary_names,
    recovery_target,
)
from arknights_mower.utils.emergency_staffing import worker_block_reason
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_timing import estimate_dorm_minutes
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS, Dormitory, Operator
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.resting_correction import suppress_completed_dorm_returns
from arknights_mower.utils.resting_priority import (
    RestingTier,
    busy_resting_names,
    has_resting_mood,
    resting_tier,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    merge_release_dorm,
    plan_mood_limit_releases,
    protect_priority_tasks,
    task_view,
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
        targets = (
            state.get("targets", {})
            if state.get("phase") != "returning"
            and not state.get("dorm_replan_pending")
            else {}
        )
        retained_members = {
            name
            for task in self.tasks
            if task.retains_execution
            and getattr(task, "emergency_staffing", False)
            and getattr(task, "emergency_recovery_release", False)
            for name in getattr(task, "emergency_staffing_members", ())
        }
        targets = {
            name: target
            for name, target in targets.items()
            if name not in retained_members
        }
        releases = plan_mood_limit_releases(
            self.op_data, recovery_targets=targets, previous_tasks=self.tasks
        )
        previous_tasks = list(self.tasks)
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
        merge_release_dorm(
            self.tasks, config.conf.merge_interval, previous_tasks=previous_tasks
        )

    def _emergency_operation_fits(self, seconds):
        start = min(
            (
                task.time
                for task in task_view(self.tasks, TaskScope.DISPATCH, self.op_data)
                if getattr(task, "strict_mood_limit", False) and task.plan
            ),
            default=datetime.max,
        )
        return datetime.now() + timedelta(seconds=seconds + 1) < start

    def _emergency_progress_snapshot(self):
        """续行只比较相关实测、安排和真实前置，不把时钟变化当成进展。"""
        state = getattr(self, "emergency_state", None) or {}
        rooms = set(state.get("pending_read_rooms", ()))
        for key in (
            "release_plan",
            "handoff_plan",
            "staffing_plan",
            "worker_replacements",
        ):
            rooms.update(state.get(key) or {})
        names = set(state.get("targets", ()))
        rooms.update(
            op.current_room
            for name in names
            if (op := self.op_data.operators.get(name)) is not None and op.current_room
        )
        if getattr(self, "_emergency_startup_pending", False):
            rooms.update(getattr(self, "_initial_mood_refresh_rooms", ()))
        dependencies = [
            task
            for task in self.tasks
            if getattr(task, "strict_mood_limit", False)
            or getattr(task, "emergency_staffing", False)
            or getattr(task, "emergency_dorm", False)
            or getattr(task, "emergency_recovery_release", False)
            or getattr(task, "run_order_restore_pending", False)
            or hasattr(task, "emergency_original_roster")
            or task.type in (TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER)
            and task.plan
        ]
        rooms.update(room for task in dependencies for room in task.plan)
        probe = SchedulerTask()
        return {
            "rooms": tuple(sorted(rooms)),
            "observation": self._task_failure_snapshot(probe, sorted(rooms)),
            "targets": {
                name: (
                    op.current_room,
                    op.current_index,
                    None if op.mood_is_prediction else op.time_stamp,
                )
                for name in names
                if (op := self.op_data.operators.get(name)) is not None
            },
            "dependencies": sorted(
                [
                    (task.type, task.meta_data, task.time, copy.deepcopy(task.plan))
                    for task in dependencies
                ],
                key=lambda item: (item[2], item[0].name, item[1], repr(item[3])),
            ),
        }

    def _emergency_continuation_checkpoint(self):
        state = getattr(self, "emergency_state", None) or {}
        return state.get("continuation_wait") or getattr(
            self, "_emergency_continuation_wait", None
        )

    def _request_emergency_continuation_observation(self, checkpoint):
        """正常等待后只给等待前已有的中断责任一次实际观察机会。"""
        if (
            checkpoint is not None
            and checkpoint is self._emergency_continuation_checkpoint()
        ):
            self._emergency_continuation_observation = checkpoint

    def _emergency_continuation_waiting(self, completed_task=None):
        state = getattr(self, "emergency_state", None) or {}
        saved = self._emergency_continuation_checkpoint()
        if saved is None:
            return False
        for observations in (saved["targets"], saved["observation"]["observations"]):
            for name, previous in observations.items():
                op = self.op_data.operators.get(name)
                if (
                    op is not None
                    and (op.current_room, op.current_index) == previous[:2]
                    and (op.time_stamp is None or op.mood_is_prediction)
                ):
                    # 丢失旧读数或转为预测不构成新的成功观察。
                    observations[name] = (*previous[:2], None)
        observe = (
            self.__dict__.pop("_emergency_continuation_observation", None) is saved
        )
        completed = completed_task is not None and any(
            (completed_task.type, completed_task.meta_data, completed_task.time)
            == dependency[:3]
            for dependency in saved["dependencies"]
        )
        waiting = (
            not observe
            and not completed
            and saved == self._emergency_progress_snapshot()
        )
        for task in self.tasks:
            if not getattr(task, "emergency_continuation", False):
                continue
            if waiting:
                if not getattr(task, "execution_failure", None):
                    self._retain_failed_task(
                        task,
                        "自动救急续行等待相关观测或前置完成",
                        saved["rooms"],
                        dependency=True,
                    )
            else:
                task.__dict__.pop("execution_failure", None)
                task.execution_retained = True
        if not waiting:
            state.pop("continuation_wait", None)
            self.__dict__.pop("_emergency_continuation_wait", None)
            if observe and self._emergency_active():
                state.pop("observed_at", None)
                state.setdefault("pending_read_rooms", list(saved["rooms"]))
        return waiting

    def _emergency_defer_read(self):
        """保留中断责任及原时间，等待相关观测或真实前置完成后续行。"""
        task = next(
            (
                t
                for t in self.tasks
                if t.meta_data == RESUME_META
                and not t.plan
                and t.type == TaskTypes.NOT_SPECIFIC
            ),
            None,
        )
        if task is None:
            task = SchedulerTask(meta_data=RESUME_META)
            self.tasks.append(task)
        task.emergency_continuation = True
        snapshot = self._emergency_progress_snapshot()
        self._retain_failed_task(
            task,
            "自动救急续行等待相关观测或前置完成",
            snapshot["rooms"],
            dependency=True,
        )
        if self._emergency_active():
            self.emergency_state["continuation_wait"] = snapshot
        else:
            self._emergency_continuation_wait = snapshot
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
            room
            for room in set(rooms)
            if room in self.op_data.plan
            and (
                room != "train"
                or any(
                    getattr(task, "emergency_staffing", False)
                    and room
                    in (getattr(task, "execution_failure", None) or {}).get("rooms", ())
                    for task in self.tasks
                )
            )
        )
        if yield_to_releases:
            if state is not None:
                rooms = state.setdefault("pending_read_rooms", rooms)
        for room in list(rooms):
            if yield_to_releases and not self._emergency_operation_fits(
                estimate_dorm_minutes(room, 1.5) * 60
            ):
                self.back_to_infrastructure()
                return False
            self.enter_room(room)
            self.get_agent_from_room(room, None, force_mood=True)
            self.back()
            if yield_to_releases:
                rooms.remove(room)
                self._emergency_replan_releases()
                protect_priority_tasks(
                    self.tasks, op_data=getattr(self, "op_data", None)
                )
                self._emergency_save()
        self.back_to_infrastructure()
        if yield_to_releases and state is not None:
            state.pop("pending_read_rooms", None)
        return True

    def _emergency_sync_reservations(self):
        state = getattr(self, "emergency_state", None) or {}
        if state.get("worker_config") is not None and state.get("phase") != "returning":
            from arknights_mower.utils.plan import PlanConfig

            self.op_data.config = self.op_data.config.merge_config(
                PlanConfig("", "", "", **state["worker_config"])
            )
            for op in self.op_data.operators.values():
                op.workaholic = self.op_data.config.is_workaholic(op.name)
        self.op_data.emergency_run_order_replacements = (
            state.get("run_order_replacements", {})
            if state and state.get("phase") != "returning"
            else None
        )
        normal_names = self.op_data.global_plan["default_plan"].scheduled_names()
        self.op_data.emergency_reserved_agents = (
            set(state.get("ready_members", ()))
            | set(state.get("staffing_members", ()))
            | set(state.get("release_members", ()))
            | (set(state.get("standby_workers", ())) - normal_names)
        )

    def _emergency_save(self):
        self._emergency_sync_reservations()
        if not save_current_state():
            raise RuntimeError("自动救急运行状态保存失败，未安排临时换班")

    def _finish_emergency_startup(self):
        """关闭启动派发门控，保存完成状态前一并释放旧任务的观察依赖。"""
        self._emergency_startup_pending = False
        for task in self.tasks:
            task.__dict__.pop("startup_observation_pending", None)

    def _emergency_startup(self):
        """初始化检查一次；恢复已有批次先核对实际驻员及未完成安排。"""
        if getattr(self, "emergency_state", None) is not None:
            self._emergency_validate_state()
        if self._emergency_continuation_waiting():
            return
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
        protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
        if self._emergency_active() and self.emergency_state.get("handoff_observing"):
            self._finish_emergency_startup()
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
            self._finish_emergency_startup()
            return
        self.backup_plan_solver()
        self._finish_emergency_startup()
        reconciled = self._reconcile_initial_staffing()
        self._emergency_save()
        if reconciled or getattr(self, "_initial_staffing_pending", False):
            return
        if not config.conf.automatic_rescue_enable:
            return
        if any(
            getattr(task, "run_order_restore_pending", False) for task in self.tasks
        ):
            # 普通纠错先释放原驻员；救急准入不能清除这条补偿依赖。
            logger.info("自动救急准入等待普通跑单恢复原驻员")
            return
        now = datetime.now()
        trial = copy.copy(self)
        data = trial.op_data = self.op_data.project_arrangements([])
        estimated = []
        for name, op in data.operators.items():
            if name == "菲亚梅塔" or (
                has_resting_mood(op) and not op.mood_is_prediction
            ):
                continue
            op.time_stamp = None
            mood = dorm_candidate_mood(data, name, now)
            if mood is not None and 0 <= mood <= 24:
                # 只在准入预演中使用卡牌心情，不写入实测或恢复计时。
                op.mood, op.time_stamp = mood, now
                op.mood_is_prediction, op.depletion_rate = False, 0
                estimated.append(name)
        if estimated:
            logger.info("自动救急准入使用卡牌心情预估：%s", "、".join(estimated))
        names = primary_names(data)
        required = []
        low_groups = set()
        for name in names:
            op = data.operators[name]
            if (
                op.multi_group
                or not has_resting_mood(op)
                or op.mood_is_prediction
                or data._can_standby(op)
                or not exhaust_rest_due(data, op, self.tasks, now)
            ):
                continue
            if op.mood < data.rescue_mood_threshold(op):
                low_groups.add(("group", op.group) if op.group else ("operator", name))
                required.append(name)
        if not required or len(low_groups) < 2:
            return
        # 已在宿舍不代表正常排班能接回：清缓存后实际岗位可能仍是救急驻员。
        normal_handoff = None
        if any(data.operators[name].is_resting() for name in required):
            trial.emergency_state = {
                "targets": {name: recovery_target(data, name)[0] for name in names}
            }
            plan = trial._emergency_resting_handoff({})
            if plan is None:
                unknown = any(
                    not has_resting_mood(data.operators[name])
                    or data.operators[name].mood_is_prediction
                    for name in names
                    if not data._can_standby(data.operators[name])
                )
                projection = NativeProjection(
                    None,
                    not unknown,
                    "normal_handoff_unknown" if unknown else "normal_handoff_blocked",
                )
            else:
                normal_handoff = plan
                trial.op_data = data.project_arrangements([plan])
                projection = native_opportunity(trial, required, now, current_only=True)
                if (
                    projection.opportunity is not None
                    and not trial._emergency_handoff_feasible({})
                ):
                    projection = NativeProjection(None, True, "normal_handoff_blocked")
        else:
            projection = native_opportunity(trial, required, now, current_only=True)
        if projection.opportunity is not None:
            if normal_handoff:
                self.tasks[:] = [
                    task
                    for task in self.tasks
                    if task.type not in ORDINARY_SHIFTS - {TaskTypes.SWITCH_PRODUCT}
                ]
                self.tasks.append(
                    SchedulerTask(
                        task_plan=normal_handoff,
                        task_type=TaskTypes.SELF_CORRECTION,
                        meta_data="初始化正常轮休交接",
                    )
                )
                self._emergency_save()
            logger.info("当前原生轮休可执行，不启动自动救急")
            return
        if not projection.complete:
            logger.info("原生轮休检查未完成，不启动自动救急：%s", projection.reason)
            return
        try:
            resolved = effective_rescue_plan(data, config.rescue_plan)
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
            "多组主班心情低于救急线且当前原生轮休无法安排，启动自动救急：%s", required
        )
        state = {
            **resolved,
            "phase": "staffing",
            "dorm_replan_pending": True,
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
        if missing := (
            set(state.get("skipped_rooms", ()))
            - {"factory", "train"}
            - state["rescue_plan"].keys()
        ):
            raise MowerExit(
                f"已保存救急排班与当前设施不一致：缺少 {sorted(missing)}；"
                "保留缓存，请补齐救急表并核对未完成交接"
            )

    def _emergency_replace_low_workers(self):
        """救急替班接管工作位；离岗正常主班纳入恢复，其他驻员待命。"""
        from arknights_mower.utils.exhaust_replacement import match_replacements

        state, data = self.emergency_state, self.op_data
        reserved, _ = dorm_task_reservations(data, self.tasks)
        reserved |= busy_resting_names()
        protected = set(reserved)
        reserved |= set(state["targets"])
        reserved.update(
            name
            for rows in state.get("run_order_replacements", {}).values()
            for row in rows
            for name in row
        )
        reserved.update(name for row in state["rescue_plan"].values() for name in row)
        groups, blocked = {}, set()
        for room, rows in state.get("worker_replacements", {}).items():
            for index, candidates in enumerate(rows):
                op = data.get_current_operator(room, index)
                configured_groups = state.get("worker_groups", {}).get(room, [])
                group = (
                    configured_groups[index] if index < len(configured_groups) else ""
                )
                key = group or (room, index)
                if (
                    room == "train"
                    or op is None
                    or op.name in protected
                    or op.name != state["rescue_plan"][room][index]
                ):
                    blocked.add(key)
                    continue
                groups.setdefault(key, []).append((room, index, op, candidates))
        assignments = {}
        for key, members in groups.items():
            if key in blocked:
                continue
            if not any(
                bool(candidates)
                and not data.config.is_workaholic(op.name)
                and has_resting_mood(op)
                and not op.mood_is_prediction
                and op.current_mood() < data.rescue_mood_threshold(op)
                for _, _, op, candidates in members
            ):
                continue
            options = {
                (room, index): [
                    name
                    for name in candidates
                    if name not in reserved
                    and (
                        (candidate := data.operators.get(name)) is None
                        or not candidate.is_working()
                    )
                    and worker_block_reason(
                        data,
                        name,
                        dorm_candidate_mood(data, name, datetime.now()),
                        reserved,
                        allow_zero=False,
                    )
                    is None
                ]
                for room, index, op, candidates in members
                if candidates and not data.config.is_workaholic(op.name)
            }
            matched = match_replacements(options)
            if matched:
                assignments.update(matched)
                reserved.update(matched.values())
        if not assignments:
            return False
        standby = set(state.get("standby_workers", ()))
        normal_primaries = set(primary_names(data))
        for (room, index), name in assignments.items():
            previous = data.get_current_operator(room, index).name
            if previous in normal_primaries:
                target, source = recovery_target(data, previous)
                state["targets"].setdefault(previous, target)
                state.setdefault("target_sources", {}).setdefault(previous, source)
                state.setdefault("work_contexts", {}).setdefault(
                    previous, mood_context(data, room)
                )
            else:
                standby.add(previous)
            standby.discard(name)
            state["rescue_plan"][room][index] = name
        state["standby_workers"] = sorted(standby)
        state["staffing_complete"] = False
        self._emergency_save()
        return True

    def _emergency_protect_training(self, plan, room_state):
        """救急跳过受保护训练室及其驻员，其他岗位继续接管。"""
        if not (
            room_state is None
            or getattr(room_state, "locked", False) is True
            or getattr(room_state, "read_failed", False) is True
            or getattr(room_state, "amiya_form_waiting", False) is True
            or getattr(room_state, "slots_read", False) is True
            and getattr(room_state, "slots_reliable", False) is not True
            or config.conf.enable_mastery
            and getattr(room_state, "protected", False) is True
        ):
            return False
        protected = {
            op.name
            for op in self.op_data.operators.values()
            if op.current_room == "train"
        }
        for room, row in plan.items():
            for index, name in enumerate(row):
                if room == "train" or name in protected:
                    row[index] = "Current"
        return True

    def _emergency_sync_compensation(self, plan):
        """专项恢复只采用已确认接管的实际驻员，跳过目标保留原恢复责任。"""
        for queued in self.tasks:
            for attribute in ("run_order_original_roster", "emergency_original_roster"):
                snapshot = getattr(queued, attribute, None)
                if not isinstance(snapshot, dict):
                    continue
                for room in snapshot.keys() & plan.keys():
                    actual = self.op_data.get_current_room(room, True)
                    if actual is None:
                        continue
                    previous = snapshot[room]
                    updated = list(previous)
                    for index, name in enumerate(plan[room]):
                        if (
                            name not in ("Current", "Free")
                            and index < len(actual)
                            and index < len(updated)
                            and actual[index] == name
                        ):
                            updated[index] = name
                    snapshot[room] = updated
                    if getattr(queued, "run_order_restore_pending", False) or (
                        queued.plan.get(room) == previous
                    ):
                        queued.plan[room] = list(updated)

    def _emergency_schedule_staffing(self):
        """救急表立即接管全部已配置工作岗位，实际驻员核验完成状态。"""
        state, data = self.emergency_state, self.op_data
        state.setdefault(
            "takeover_complete",
            bool(state.get("staffing_complete")),
        )
        if state["phase"] == "returning" or any(
            getattr(task, "emergency_staffing", False)
            for task in task_view(self.tasks, TaskScope.DISPATCH, data)
        ):
            return True
        replaced = (
            state.get("staffing_complete") or state.get("takeover_complete")
        ) and self._emergency_replace_low_workers()
        retained_staffing = [
            task
            for task in self.tasks
            if getattr(task, "emergency_staffing", False)
            and not getattr(task, "emergency_recovery_release", False)
        ]
        reserved, positions = retained_task_reservations(data, self.tasks)
        plan = {
            room: [
                "Current" if (room, index) in positions or name in reserved else name
                for index, name in enumerate(row)
            ]
            for room, row in rescue_plan_for(data, state["rescue_plan"]).items()
        }
        self._suppress_train_arrangement(plan)
        if (room_state := getattr(self, "train_room_state", None)) is not None:
            self._emergency_protect_training(plan, room_state)
        plan = {
            room: names
            for room, names in plan.items()
            if any(name != "Current" for name in names)
        }
        if state.get("staffing_complete") and not replaced:
            self._emergency_reconcile_staffing()
            if state.get("staffing_complete"):
                return True
        pending = {}
        for room, names in plan.items():
            if all(name == "Current" for name in names):
                continue
            current = data.get_current_room(room, True)
            if current is not None and all(
                name == "Current" or index < len(current) and current[index] == name
                for index, name in enumerate(names)
            ):
                self._emergency_sync_compensation({room: names})
                continue
            pending[room] = list(names)
        if not pending:
            if retained_staffing:
                state["staffing_complete"] = False
                return True
            self._emergency_sync_compensation(plan)
            state["staffing_complete"] = True
            state["takeover_complete"] = True
            state["staffing_plan"] = {}
            state.pop("staffing_members", None)
            state["phase"] = "recovering"
            return True
        for row in pending.values():
            for name in row:
                if name not in ("", "Current") and name not in data.operators:
                    data.add(Operator(name, ""))
        summary = copy.deepcopy(pending)
        for queued in retained_staffing:
            for room, row in queued.plan.items():
                target = summary.setdefault(room, ["Current"] * len(row))
                for index, name in enumerate(row):
                    if name != "Current":
                        target[index] = name
        state["staffing_plan"] = summary
        state["staffing_members"] = list(state["targets"])
        temporary = state.setdefault("temporary_roster", {})
        for room in plan:
            if (
                not any(task.retains_execution for task in self.tasks)
                or room not in temporary
            ):
                temporary[room] = data.get_current_room(room, True)
        state["phase"] = "staffing"
        task = SchedulerTask(task_plan=copy.deepcopy(pending))
        task.emergency_staffing = True
        task.emergency_takeover = not state["takeover_complete"]
        task.emergency_staffing_members = list(state["targets"])
        self._emergency_save()
        self.tasks.append(task)
        logger.info(
            "自动救急：%s工作岗位：%s",
            "立即接管" if task.emergency_takeover else "轮换",
            pending,
        )
        return True

    def _open_emergency_beds(self):
        """主班优先占床，余床依次恢复菲亚、群回和单回宿管。"""
        data, state = self.op_data, self.emergency_state
        layout = state.get("dorm_layout", {})
        if not layout:
            return
        if any(
            task.type == TaskTypes.FIAMMETTA
            and task.plan
            or getattr(task, "emergency_dorm", False)
            for task in self.tasks
        ):
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
            and (not scheduling_mood_reaches(self.op_data, name, target))
        }
        need.update(
            op.name
            for op in data.operators.values()
            if op.is_resting() and data.is_free_room_excluded(op.name)
        )
        capacity = sum(len(row) for row in layout.values())
        spare = max(0, capacity - len(need))
        reserved, slots = dorm_task_reservations(data, self.tasks)
        waiting = any(not data.operators[name].is_resting() for name in need)
        fia_position = None
        for room, row in layout.items():
            if "菲亚梅塔" not in row:
                continue
            index = row.index("菲亚梅塔")
            resident = data.get_current_operator(room, index)
            if (
                spare > 0
                and not waiting
                and "菲亚梅塔" not in reserved
                and (room, index) not in slots
                and (resident is None or resident.name not in need)
            ):
                fia_position = (room, index)
                spare -= 1
            was_fixed = data.plan[room][index].agent == "菲亚梅塔"
            if was_fixed != (fia_position == (room, index)):
                state["dorm_replan_pending"] = True
                state.pop("dorm_replan_plan", None)
        restored = {}
        for classify in (is_group_recovery_manager, is_single_recovery_manager):
            selected_rooms = set()
            for index in range(max(map(len, layout.values()))):
                for room, row in layout.items():
                    positions = restored.get(room, ())
                    if (
                        index >= len(row)
                        or spare <= 0
                        or room in selected_rooms
                        or index in positions
                        or (room, index) in slots
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
                    selected_rooms.add(room)
                    spare -= 1
        for room, row in layout.items():
            for index, name in enumerate(row):
                if name == "菲亚梅塔":
                    fia = data.operators[name]
                    if (fia.current_room, fia.current_index) == (room, index):
                        fia.room, fia.index = room, index
                fixed = (room, index) == fia_position or index in restored.get(room, ())
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
            if op is None:
                continue
            if normal.operators[name].rest_in_full:
                state["targets"][name] = normal.operators[name].upper_limit
                state["target_sources"][name] = "rest_in_full"
                if (
                    op.mood_is_prediction
                    or not has_resting_mood(op)
                    or op.mood < state["targets"][name]
                ):
                    state["ready_members"] = [
                        member
                        for member in state.get("ready_members", ())
                        if member != name
                    ]
                continue
            if normal._can_standby(normal.operators[name]):
                state["targets"][name], state["target_sources"][name] = recovery_target(
                    normal, name
                )
                continue
            if name in state.get("ready_members", ()):
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

    def _emergency_fia_fallback(self, configured):
        """配置对象均满心情后，按心情选择无特殊上限的正常主班。"""
        if not self._emergency_frozen() or not configured:
            return None
        data = self.op_data
        if not all(
            (op := data.operators.get(name)) is not None
            and has_resting_mood(op)
            and not op.mood_is_prediction
            and op.current_mood() >= 24
            for name in configured
        ):
            return None
        reserved, _ = dorm_task_reservations(data, self.tasks)
        reserved |= busy_resting_names()
        candidates = [
            name
            for name in primary_names(data)
            if not data.has_rest_mood_limit(name)
            and name not in reserved
            and (op := data.operators[name]).upper_limit == 24
            and op.current_room not in ("train", "factory")
            and has_resting_mood(op)
            and not op.mood_is_prediction
            and op.current_mood() < 24
        ]
        return sorted(
            candidates, key=lambda name: (data.operators[name].current_mood(), name)
        )

    def _emergency_filter_tasks(self):
        if not self._emergency_frozen():
            return
        self.tasks[:] = [
            task
            for task in self.tasks
            if not getattr(task, "mood_control_event", None)
            or task.retains_execution
            or getattr(task, "mood_physical_started", False)
        ]
        fia_targets = set(self.emergency_state.get("fia_targets", ()))
        fia = self.op_data.operators.get("菲亚梅塔")
        fia_rooms = {
            room
            for room, row in self.emergency_state.get("dorm_layout", {}).items()
            if "菲亚梅塔" in row
            and fia is not None
            and (fia.current_room, fia.current_index) == (room, row.index("菲亚梅塔"))
            and any(
                slot.agent == "菲亚梅塔" for slot in self.op_data.plan.get(room, ())
            )
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
                        (
                            task.meta_data not in fia_targets
                            and not (
                                getattr(task, "emergency_fia_fallback", False)
                                and task.meta_data in primary_names(self.op_data)
                                and not self.op_data.has_rest_mood_limit(task.meta_data)
                                and self.op_data.operators[task.meta_data].upper_limit
                                == 24
                            )
                        )
                        or set(task.plan) != fia_rooms
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
                and not getattr(task, "run_order_restore_pending", False)
                and not self._emergency_run_order_available(task.meta_data, task.plan)
            )
        ]

    def _emergency_reconcile_staffing(self):
        """已派发安排以实际驻员核销，尚未读到的房间保留待办。"""
        state = self.emergency_state
        if state["phase"] == "returning":
            return False
        pending = state.get("staffing_plan", {})
        if not pending:
            return False
        self._suppress_train_arrangement(pending)
        if (room_state := getattr(self, "train_room_state", None)) is not None:
            self._emergency_protect_training(pending, room_state)
        self._emergency_sync_compensation(pending)
        state["staffing_plan"] = {
            room: row
            for room, row in pending.items()
            if any(name != "Current" for name in row)
            and (
                (actual := self.op_data.get_current_room(room, True)) is None
                or any(
                    name != "Current"
                    and (index >= len(actual) or name != actual[index])
                    for index, name in enumerate(row)
                )
            )
        }
        if state["staffing_plan"] or any(
            getattr(task, "emergency_staffing", False)
            and not getattr(task, "emergency_recovery_release", False)
            for task in self.tasks
        ):
            state["staffing_complete"] = False
            return False
        state.pop("staffing_members", None)
        state["staffing_complete"] = True
        state["takeover_complete"] = True
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
            and (not scheduling_mood_reaches(self.op_data, name, target))
            and (
                op.current_room in rotation_rooms
                or op.need_to_refresh()
                or state["phase"] == "returning"
            )
        }
        rooms.update(
            room
            for room, rows in state.get("worker_replacements", {}).items()
            if room != "train"
            and any(
                candidates
                and (op := self.op_data.get_current_operator(room, index)) is not None
                and op.need_to_refresh()
                for index, candidates in enumerate(rows)
            )
        )
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
        state = self.emergency_state
        if self._emergency_continuation_waiting(completed_task):
            return
        staffing_completed = self._emergency_reconcile_staffing()
        if state["phase"] == "staffing" and not state.get("staffing_complete"):
            self._emergency_schedule_staffing()
            protect_priority_tasks(self.tasks, op_data=self.op_data)
            self._emergency_save()
            pending = [
                task
                for task in self.tasks
                if getattr(task, "emergency_staffing", False)
            ]
            if not pending or task_view(pending, TaskScope.DISPATCH, self.op_data):
                return
        self.plan_metadata()
        protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
        pending_staffing = [
            task
            for task in task_view(self.tasks, TaskScope.DISPATCH, self.op_data)
            if getattr(task, "emergency_staffing", False)
        ]
        if pending_staffing:
            self._emergency_save()
            return
        self._emergency_sync_reservations()
        read_due = datetime.now() >= state.get("next_read", datetime.now()) or any(
            getattr(task, "emergency_recovery_release", False)
            and task.time <= datetime.now()
            for task in task_view(self.tasks, TaskScope.DISPATCH, self.op_data)
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
            or (
                getattr(completed_task, "emergency_recovery_release", False)
                and getattr(completed_task, "emergency_staffing", False)
            )
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
            self._resume_failed_tasks()
            self.plan_metadata()
            protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
        if plan_due:
            self.tasks[:] = [
                task
                for task in self.tasks
                if task.retains_execution
                or not getattr(task, "emergency_recovery_release", False)
            ]
            state["ready_members"] = [
                name
                for name in state.get("ready_members", [])
                if (op := self.op_data.operators.get(name)) is not None
                and not op.is_working()
                and scheduling_mood_reaches(self.op_data, name, state["targets"][name])
            ]
            self._emergency_update_targets()
            self._emergency_release_ready()
            release_waiting = state.get("release_plan") is not None
            if release_waiting and not any(
                task.retains_execution
                and getattr(task, "emergency_staffing", False)
                and getattr(task, "emergency_recovery_release", False)
                for task in self.tasks
            ):
                self._emergency_defer_read()
                return
            if self._emergency_ready() and self._emergency_restore():
                return
            if state["phase"] == "returning":
                self._emergency_defer_read()
            else:
                self._open_emergency_beds()
                scanned = self._emergency_schedule_staffing()
                if state.get("staffing_complete") or (
                    state.get("takeover_complete")
                    and not any(
                        getattr(task, "emergency_staffing", False)
                        for task in task_view(
                            self.tasks, TaskScope.DISPATCH, self.op_data
                        )
                    )
                ):
                    self._emergency_plan_beds(state)
                if not scanned:
                    self._emergency_defer_read()
                elif read_due and not release_waiting:
                    state["next_read"] = datetime.now() + timedelta(hours=2)
        self._emergency_sync_reservations()
        if plan_due:
            self._emergency_replan_releases()
            protect_priority_tasks(self.tasks, op_data=getattr(self, "op_data", None))
        if (
            plan_due
            and (
                state["phase"] == "recovering"
                or state["phase"] == "staffing"
                and state.get("takeover_complete")
            )
            and not any(
                getattr(task, "emergency_staffing", False)
                for task in task_view(self.tasks, TaskScope.DISPATCH, self.op_data)
            )
        ):
            try_workshop_tasks(self.op_data, self.tasks)
            self.run_order_solver()
        if plan_due and release_waiting:
            self._emergency_defer_read()
        else:
            self._emergency_save()

    def _emergency_recovery_order(self):
        """限量比较恢复组合；预测只用于分床排序，不写回实测或批准退出。"""
        import heapq

        data, state = self.op_data, self.emergency_state
        groups = {}
        reserved, _ = dorm_task_reservations(data, self.tasks)
        for name, target in state["targets"].items():
            op = data.operators.get(name)
            if (
                op is None
                or name in reserved
                or name in state.get("ready_members", ())
                or op.room.startswith("dorm")
                or data.rest_mood_complete(name)
                or resting_tier(data, name) == RestingTier.EXCLUDED
                or op.is_working()
                or not has_resting_mood(op)
                or op.mood_is_prediction
                or op.mood >= target
                or target > op.upper_limit
            ):
                continue
            groups.setdefault(op.group or name, []).append(name)
        units = sorted(groups.values(), key=lambda names: tuple(sorted(names)))
        if len(units) < 2:
            return {}
        costs = [
            sum(state["targets"][name] - data.operators[name].mood for name in names)
            for names in units
        ]
        # 每次分床最多 64 次隔离交接核验，不扫描游戏或引入周期任务。
        queue = [(cost, (i,)) for i, cost in enumerate(costs)]
        heapq.heapify(queue)
        chosen = set()
        for _ in range(64):
            if not queue:
                break
            cost, indices = heapq.heappop(queue)
            probe = copy.copy(self)
            probe.op_data = copy.deepcopy(data, {id(data.eval_model): data.eval_model})
            probe.tasks = copy.deepcopy(self.tasks)
            probe.emergency_state = copy.deepcopy(state)
            for index in indices:
                for name in units[index]:
                    op = probe.op_data.operators[name]
                    op.mood, op.time_stamp, op.depletion_rate = (
                        state["targets"][name],
                        datetime.now(),
                        0,
                    )
            if probe._emergency_ready():
                chosen = {name for index in indices for name in units[index]}
                break
            for index in range(indices[-1] + 1, len(units)):
                heapq.heappush(queue, (cost + costs[index], (*indices, index)))
        return {
            name: (0 if name in chosen else 1, costs[index])
            for index, names in enumerate(units)
            for name in names
        }

    def _emergency_plan_beds(self, state):
        if any(getattr(task, "emergency_dorm", False) for task in self.tasks):
            return
        reallocate = state.get("dorm_replan_pending", False)
        if reallocate and any(
            task.type == TaskTypes.FIAMMETTA and task.plan for task in self.tasks
        ):
            return
        previous = state.get("dorm_replan_plan")
        if previous and all(
            (actual := self.op_data.get_current_room(room, True)) is not None
            and all(
                name in ("Current", "Free")
                or index < len(actual)
                and actual[index] == name
                for index, name in enumerate(row)
            )
            for room, row in previous.items()
        ):
            state.pop("dorm_replan_plan", None)
            state["dorm_replan_pending"] = False
            return
        plan = (
            copy.deepcopy(previous)
            if previous
            else emergency_dorm_plan(
                self.op_data,
                state,
                self.tasks,
                reallocate=reallocate,
                recovery_order=self._emergency_recovery_order(),
            )
        )
        reserved, slots = dorm_task_reservations(self.op_data, self.tasks)
        for room, original in state.get("dorm_layout", {}).items():
            for index, name in enumerate(original):
                if (
                    name not in ("", "Free", "Current")
                    and name not in reserved
                    and (room, index) not in slots
                    and self.op_data.plan[room][index].agent == name
                ):
                    current = self.op_data.get_current_operator(room, index)
                    if current is None or current.name != name:
                        plan.setdefault(room, ["Current"] * len(original))[index] = name
        compact_dorm_vacancies(self.op_data, plan)
        if not plan:
            if reallocate:
                state["dorm_replan_pending"] = False
            return
        if reallocate:
            state["dorm_replan_plan"] = copy.deepcopy(plan)
        task = SchedulerTask(task_type=TaskTypes.FILL_DORM, task_plan=plan)
        task.emergency_dorm = True
        self.tasks.append(task)

    def _emergency_release_ready(self):
        """个人实测达标后只清空宿舍位置，待命主班不改变临时工作组合。"""
        state, data = self.emergency_state, self.op_data
        if (
            state.get("dorm_replan_pending")
            or state["phase"] == "returning"
            or any(
                getattr(task, "emergency_staffing", False)
                or hasattr(task, "emergency_original_roster")
                or getattr(task, "run_order_restore_pending", False)
                or task.plan
                and task.type in (TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER)
                and task.time <= datetime.now()
                for task in task_view(self.tasks, TaskScope.DISPATCH, self.op_data)
            )
        ):
            return False
        retained_releases = [
            task
            for task in self.tasks
            if task.retains_execution
            and getattr(task, "emergency_staffing", False)
            and getattr(task, "emergency_recovery_release", False)
        ]
        retained_members = {
            name
            for task in retained_releases
            for name in getattr(task, "emergency_staffing_members", ())
            if name in data.operators and data.operators[name].is_resting()
        }

        def remember_release(plan, members):
            summary = {}
            for pending in [*(task.plan for task in retained_releases), plan]:
                for room, row in pending.items():
                    target = summary.setdefault(room, ["Current"] * len(row))
                    for index, name in enumerate(row):
                        if name != "Current":
                            target[index] = name
            if summary:
                state["release_plan"] = summary
                state["release_members"] = sorted(retained_members | members)
            else:
                state.pop("release_plan", None)
                state.pop("release_members", None)

        reserved_names, reserved_slots = retained_task_reservations(data, self.tasks)
        ready = set(state.get("ready_members", ()))
        members = set(state.get("release_members", ())) - retained_members
        plan = {}
        for name, target in state["targets"].items():
            op = data.operators.get(name)
            if (
                op is None
                or name in reserved_names
                or (op.current_room, op.current_index) in reserved_slots
                or op.is_working()
                or not scheduling_mood_reaches(self.op_data, name, target)
            ):
                continue
            if not op.current_room:
                ready.add(name)
                members.discard(name)
                op.depletion_rate = 0
            elif op.is_resting() and data.is_free_room_excluded(name):
                ready.add(name)
                members.discard(name)
            elif op.is_resting():
                members.add(name)
                plan.setdefault(
                    op.current_room, ["Current"] * len(data.plan[op.current_room])
                )[op.current_index] = ""
        # 已离宿但实测失效者由 targets 重新入宿，旧清退只保留实际住客。
        members = {
            name
            for name in members
            if name in data.operators
            and data.operators[name].is_resting()
            and not data.is_free_room_excluded(name)
        }
        changed = ready != set(state.get("ready_members", ())) or (
            members | retained_members
        ) != set(state.get("release_members", ()))
        state["ready_members"] = sorted(ready)
        state["release_members"] = sorted(members | retained_members)
        self._emergency_sync_reservations()
        for task in task_view(self.tasks, TaskScope.REPLAN):
            if not getattr(task, "emergency_dorm", False):
                continue
            for room, row in list(task.plan.items()):
                task.plan[room] = [
                    "Current"
                    if name in ready | members and not data.is_free_room_excluded(name)
                    else name
                    for name in row
                ]
                if all(name == "Current" for name in task.plan[room]):
                    del task.plan[room]
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.retains_execution
            or task.plan
            or not getattr(task, "emergency_dorm", False)
        ]
        if not members:
            remember_release({}, set())
            if changed:
                self._emergency_save()
            return changed and not retained_releases
        if not plan or not self._emergency_operation_fits(
            sum(estimate_dorm_minutes(room) * 60 for room in plan)
        ):
            remember_release(plan, members)
            self._emergency_save()
            return False
        compact_dorm_vacancies(data, plan)
        if state.get("staffing_complete") and not any(
            getattr(task, "emergency_dorm", False) for task in self.tasks
        ):
            # 在离宿后的隔离驻员上规划补床，一次执行最终宿舍名单。
            probe = copy.copy(self)
            probe.op_data = data.project_arrangements([plan])
            probe.emergency_state = copy.deepcopy(state)
            probe.emergency_state["ready_members"] = sorted(ready | members)
            probe.tasks = copy.deepcopy(self.tasks)
            probe._open_emergency_beds()
            probe._emergency_plan_beds(probe.emergency_state)
            fills = [
                task.plan
                for task in probe.tasks
                if getattr(task, "emergency_dorm", False)
            ]
            if fills:
                final = probe.op_data.project_arrangements(fills)
                rooms = set(plan) | {room for fill in fills for room in fill}
                if self._emergency_operation_fits(
                    sum(estimate_dorm_minutes(room) * 60 for room in rooms)
                ):
                    plan = {
                        room: final.get_current_room(room, True)
                        for room in sorted(rooms)
                    }
                    compact_dorm_vacancies(data, plan)
        remember_release(plan, members)
        self._emergency_save()
        previous_task = self.task
        self.task = SchedulerTask(task_plan=copy.deepcopy(plan))
        self.task.emergency_staffing = True
        self.task.emergency_recovery_release = True
        self.task.emergency_staffing_members = sorted(members)
        release_task = self.task
        release_task.execution_retained = True
        self.tasks.append(release_task)
        try:
            self._emergency_save()
            deferred = self.agent_arrange(self.task.plan, get_time=True) is False
        except (MowerExit, DeviceRecoveryError, SharedADBError):
            raise
        except Exception as exc:
            from arknights_mower.solvers.base_schedule import RoomArrangementDeferred

            rooms = (
                [exc.room]
                if isinstance(exc, RoomArrangementDeferred)
                else self.task.plan
            )
            self._retain_failed_task(release_task, str(exc), rooms)
            self._emergency_save()
            return False
        finally:
            self.task = previous_task
        if not release_task.plan:
            self.tasks[:] = [task for task in self.tasks if task is not release_task]
        for name in members:
            op = self.op_data.operators[name]
            if not op.current_room and scheduling_mood_reaches(
                self.op_data, name, state["targets"][name]
            ):
                ready.add(name)
                op.depletion_rate = 0
        state["ready_members"] = sorted(ready)
        remaining = {
            name
            for name in members - ready
            if self.op_data.operators[name].is_resting()
        }
        remember_release(release_task.plan, remaining)
        if remaining and not release_task.plan:
            self._emergency_defer_read()
        self._emergency_save()
        return not deferred or bool(ready & members)

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
                or getattr(task, "run_order_restore_pending", False)
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
        from arknights_mower.utils.emergency_plan import RESCUE_ROOMS

        normal = {
            room: [slot.agent for slot in row]
            for room, row in probe.op_data.plan.items()
            if room in RESCUE_ROOMS or room.startswith("dorm")
        }
        suppress_completed_dorm_returns(probe.op_data, normal)
        plan = probe._emergency_resting_handoff(normal)
        return plan is not None and probe._emergency_handoff_feasible(plan)

    def _emergency_resting_handoff(self, plan):
        """复用正常整组替班规划，为交接后仍需休息的组同时预留岗位和床位。"""
        data = self.op_data
        groups = {}
        for name in primary_names(data):
            op = data.operators[name]
            if data._can_standby(op):
                continue
            mood = dorm_candidate_mood(data, name)
            if mood is None:
                return None
            target = (
                op.upper_limit
                if op.rest_in_full
                else self.emergency_state["targets"].get(
                    name, recovery_target(data, name)[0]
                )
            )
            if mood < target:
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
        data = self.op_data.project_arrangements([plan])
        # 当前正常岗位覆盖即可交接，后续轮休由正常调度处理。
        feasible = True
        for name in primary_names(data):
            op = data.operators[name]
            if data._can_standby(op):
                continue
            if op.is_resting():
                if not has_resting_mood(op) or op.mood_is_prediction:
                    return False
                if any(
                    not (member := data.operators[other]).room.startswith("dorm")
                    and member.is_working()
                    and not member.workaholic
                    for other in data.groups.get(op.group, [name])
                ):
                    return False
                occupant = data.get_current_operator(op.room, op.index)
                if (
                    occupant is None
                    or occupant.name not in data.replacement_candidates(op)
                    or not has_resting_mood(occupant)
                    or occupant.mood_is_prediction
                    or data.replacement_exhausted(occupant.name, operator=op)
                ):
                    return False
                continue
            actual = self.op_data.operators.get(name)
            returned = (
                "handoff_plan" in state
                and actual is not None
                and actual.is_working()
                and (actual.current_room, actual.current_index) == (op.room, op.index)
            )
            if (
                not has_resting_mood(op)
                or op.mood_is_prediction
                or op.mood
                < (
                    data.resting_mood_threshold(op)
                    if returned
                    else op.upper_limit
                    if op.rest_in_full
                    else state["targets"].get(name, recovery_target(data, name)[0])
                )
            ):
                feasible = False
                break
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
        # 直接交接不经过普通换班任务；在副本中按最终实读重新核验组状态。
        observed = {
            room: [
                occupant.name
                if (occupant := self.op_data.get_current_operator(room, index))
                else "Current"
                for index in range(len(slots))
            ]
            for room, slots in self.op_data.plan.items()
        }
        transitions = self.op_data.arrangement_group_transitions(observed)
        probe = copy.copy(self)
        probe.op_data = self.op_data.project_arrangements([observed])
        probe.tasks = copy.deepcopy(self.tasks)
        if not probe._emergency_handoff_feasible({}):
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
        remaining = probe.agent_get_mood(read_rooms=False, return_plan=True)
        if not probe.op_data.normalize_shared_arrangement(remaining, transitions):
            self._emergency_save()
            return False
        if remaining:
            state["handoff_plan"] = copy.deepcopy(remaining)
            self._emergency_save()
            return False
        self.op_data.commit_group_shifts(transitions)
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
