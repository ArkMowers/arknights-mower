"""Mower 智能救急的临时驻员、宿舍恢复与正常排班交接。"""

import copy
from datetime import datetime, timedelta
from time import monotonic

from arknights_mower.data import base_room_list
from arknights_mower.solvers.base_mixin import fixed_selection_profile
from arknights_mower.solvers.record import emergency_mood_history, save_current_state
from arknights_mower.utils import config, detector
from arknights_mower.utils.building_skills import (
    load_skill_snapshot,
    owned_operator,
    unlocked_skills,
)
from arknights_mower.utils.character_recognize import estimate_agent_mood
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.dorm_skills import is_group_recovery_manager
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
from arknights_mower.utils.emergency_staffing import (
    StaffingCandidate,
    card_skills,
    eligible_worker,
    facility_score,
    select_workers,
)
from arknights_mower.utils.exhaust_replacement import match_replacements
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

CHECK_META = "automatic_rescue_check"
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
        """每房实测后刷新强制清退；交接读房仍不生成普通换班。"""
        releases = plan_mood_limit_releases(self.op_data)
        refreshed = {task.meta_data for task in releases}
        self.tasks[:] = [
            task
            for task in self.tasks
            if not getattr(task, "strict_mood_limit", False)
            or (
                getattr(self, "_emergency_handoff", False)
                and task.meta_data not in refreshed
                and (op := self.op_data.operators.get(task.meta_data)) is not None
                and op.current_room in task.plan
                and 0 <= op.current_index < len(task.plan[op.current_room])
                and task.plan[op.current_room][op.current_index] == "Free"
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
        due = datetime.now() + timedelta(minutes=1)
        if self._emergency_active():
            self.emergency_state["next_read"] = due
        check = next((t for t in self.tasks if t.meta_data == CHECK_META), None)
        if check is None:
            self.tasks.append(SchedulerTask(time=due, meta_data=CHECK_META))
        else:
            check.time = due
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
            else:
                if getattr(self, "_emergency_startup_rooms", None) is None:
                    self._emergency_startup_rooms = rooms
                rooms = self._emergency_startup_rooms
                rooms[:] = [room for room in rooms if room in self.op_data.plan]
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

    def _emergency_save(self):
        if not save_current_state():
            raise RuntimeError("智能救急运行状态保存失败，未安排临时换班")

    def _emergency_startup(self):
        """初始化检查一次；恢复已有批次先核对实际驻员及未完成安排。"""
        if getattr(self, "emergency_state", None) is not None:
            self._emergency_validate_state()
        if not self._emergency_active() and getattr(
            getattr(self, "task", None), "strict_mood_limit", False
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
        observed = self._emergency_read_rooms(
            (room for room in self.op_data.plan if room in base_room_list),
            yield_to_releases=True,
        )
        if observed is False or not self._emergency_operation_fits(45):
            self._emergency_startup_pending = not self._emergency_active()
            self._emergency_defer_read()
            return
        self._read_initial_card_mood()
        self._emergency_startup_rooms = None
        self.defer_backup_plan_until_mood_read = False
        if self._emergency_active():
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
        rates, deadlines = {}, {}
        now = datetime.now()
        for name in names:
            op = data.operators[name]
            if not has_resting_mood(op) or op.is_resting() or data._can_standby(op):
                continue
            line = data.rescue_mood_threshold(op)
            rate = history_rate(
                emergency_mood_history(name),
                op.current_room,
                mood_context(data, op.current_room),
            )
            if rate:
                rates[name] = rate
            if op.mood < line:
                required.append(name)
            elif rate:
                crossing = now + timedelta(hours=(op.mood - line) / rate)
                if crossing <= now + timedelta(hours=12):
                    deadlines[name] = crossing
                    required.append(name)
        if not required:
            return
        projection = native_opportunity(
            self, required, now, deadlines=deadlines, rates=rates
        )
        if projection.opportunity is not None or not projection.complete:
            logger.info("原生救急仍有恢复机会或观察不足，不启动智能救急")
            return
        state = {
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
            "dorm_layout": {
                room: [slot.agent for slot in row]
                for room, row in data.plan.items()
                if room.startswith("dorm")
            },
            "next_read": now,
        }
        self.emergency_state = state
        self._emergency_update_targets()
        self._open_emergency_beds()
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
        self._emergency_save()
        self.plan_metadata()
        self._emergency_schedule_staffing(initial=True)
        state["observed_at"] = datetime.now()
        self._emergency_save()

    def _emergency_validate_state(self):
        state = self.emergency_state
        if not (
            isinstance(state, dict)
            and state.get("phase") in ("staffing", "recovering", "returning")
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
            raise MowerExit("智能救急缓存结构不完整，保留缓存并停止")

    @fixed_selection_profile
    def _emergency_scan_workers(
        self, room, facility, reserved, *, snapshot=None, fixed=()
    ):
        """每个设施最多扫描二十页、四十五秒；观测后取消暂选。"""
        deadline = monotonic() + 45
        candidates, seen = [], set()
        if snapshot is None:
            snapshot = load_skill_snapshot()
        try:
            self.enter_room(room, max_attempts=1)
            self.turn_on_room_detail(room)
            self.refresh_facility_state(room)
            for _ in range(4):
                if self.find("confirm_blue") is not None:
                    break
                self.tap((self.recog.w * 0.82, self.recog.h * 0.2))
            else:
                raise RuntimeError("未进入智能救急选人页")
            self.profession_filter("ALL")
            self.tap((self.recog.w * 0.38, self.recog.h * 0.95), interval=0.5)
            self.switch_arrange_order("技能", room)
            self.swipe_left(1, "ALL")
            previous, observation = None, None
            for page_index in range(20):
                if monotonic() >= deadline:
                    break
                page = self.wait_for_agent_page(
                    before=previous, observation=observation
                )
                if previous is not None and self.same_agent_page(
                    page, previous, allow_unknown=True
                ):
                    break
                for name, scope in page:
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    mood = estimate_agent_mood(self.recog.img, scope)
                    if name not in fixed and (
                        owned_operator(name, snapshot) is False
                        or not eligible_worker(self.op_data, name, mood, reserved)
                    ):
                        continue
                    if mood is not None and 0 <= mood <= 24:
                        self.op_data.dorm_mood_estimates[name] = (mood, datetime.now())
                    skills = unlocked_skills(name, facility, snapshot)
                    if skills is None:
                        skills = card_skills(self.recog.img, scope, name, facility)
                    candidates.append(StaffingCandidate(name, mood, skills))
                if page_index == 19 or monotonic() >= deadline:
                    break
                previous = page
                _, observation = self.swipe_agent_page(
                    page, "智能救急技能扫描", return_page=True
                )
        finally:
            self.back_to_infrastructure()
        return candidates

    def _emergency_schedule_staffing(self, *, initial=False):
        """完整工作替班可执行后离岗；床位按个人需求分批安排。"""
        state, data = self.emergency_state, self.op_data
        if (
            state.get("release_plan") is not None
            or state["phase"] == "returning"
            or any(getattr(task, "emergency_staffing", False) for task in self.tasks)
        ):
            return True
        protect_priority_tasks(self.tasks)
        if state.get("staffing_rescore"):
            return self._emergency_rescore_staffing()

        pending = copy.deepcopy(state.get("staffing_plan", {}))
        if pending:
            self._emergency_save()
            task = SchedulerTask(task_plan=pending)
            task.emergency_staffing = True
            task.emergency_staffing_members = list(state.get("staffing_members", ()))
            self.tasks.append(task)
            return True

        reserved, _ = dorm_task_reservations(data, self.tasks)
        reserved |= busy_resting_names() | set(TRADE_ORDER_AGENTS)
        reserved |= set(state["targets"])
        reserved |= set(state.get("release_members", ()))
        reserved |= {op.name for op in data.operators.values() if op.is_working()}
        facilities = {
            "central": "中枢",
            "contact": "人力办公室",
            "meeting": "会客室",
        }
        supported = {"中枢", "人力办公室", "会客室", "制造站", "贸易站", "发电站"}
        groups = {}
        for name in primary_names(data):
            if name not in state["targets"]:
                continue
            op = data.operators[name]
            key = op.group or name
            if name not in state.get("ready_members", ()):
                groups[key] = list(data.groups.get(op.group, [name]))
        reserved.update(name for members in groups.values() for name in members)
        snapshot = None
        completed = True
        for members in groups.values():
            workers = [
                name
                for name in members
                if name in state["targets"]
                and name in data.operators
                and not data.operators[name].room.startswith("dorm")
            ]
            if not workers or not any(
                not has_resting_mood(data.operators[name])
                or data.operators[name].mood < state["targets"][name]
                for name in workers
            ):
                continue
            working = [name for name in workers if data.operators[name].is_working()]
            if working and len(working) != len(workers):
                continue
            if any(
                name in data.operators
                and data.operators[name].is_working()
                and name not in workers
                for name in members
            ):
                continue
            planned_slots = {}
            for name in workers:
                op = data.operators[name]
                if op.room not in data.plan or not 0 <= op.index < len(
                    data.plan[op.room]
                ):
                    break
                facility = facilities.get(op.room, data.plan[op.room][0].facility)
                if facility not in supported:
                    break
                current = data.get_current_operator(op.room, op.index)
                if (
                    working
                    or current is None
                    or not eligible_worker(
                        data,
                        current.name,
                        current.current_mood() if has_resting_mood(current) else None,
                        reserved - {current.name},
                    )
                ):
                    planned_slots.setdefault(op.room, []).append((op.index, name))
            else:
                if not planned_slots or any(
                    hasattr(task, "emergency_original_roster")
                    and set(planned_slots).intersection(
                        set(task.plan) | set(task.emergency_original_roster)
                    )
                    for task in self.tasks
                ):
                    continue
                group_reserved = reserved
                probe = copy.deepcopy(data, {id(data.eval_model): data.eval_model})
                for name in working:
                    probe.operators[name]._current_room = ""
                    probe.operators[name].current_index = -1
                dorm_plan = emergency_dorm_plan(
                    probe, state, self.tasks, members=workers
                )
                pending = copy.deepcopy(dorm_plan)
                options, preferred = {}, {}
                for room, slots in planned_slots.items():
                    if not self._emergency_operation_fits(45):
                        completed = False
                        break
                    if snapshot is None:
                        snapshot = load_skill_snapshot()
                    facility = facilities.get(room, data.plan[room][0].facility)
                    product = data.facility_states.get(room, {}).get("product")
                    current = data.get_current_room(room, True)
                    changed_indices = {index for index, _ in slots}
                    fixed_names = [
                        actual.name
                        for index, slot in enumerate(data.plan[room])
                        if index not in changed_indices
                        and (actual := data.get_current_operator(room, index))
                        is not None
                        and actual.name == slot.agent
                    ]
                    observed = self._emergency_scan_workers(
                        room,
                        facility,
                        group_reserved,
                        snapshot=snapshot,
                        fixed=fixed_names,
                    )
                    by_name = {candidate.name: candidate for candidate in observed}
                    fixed = []
                    for name in fixed_names:
                        skills = unlocked_skills(name, facility, snapshot)
                        if skills is None:
                            skills = by_name[name].skills if name in by_name else ()
                        op = data.operators[name]
                        fixed.append(StaffingCandidate(name, op.current_mood(), skills))
                    candidates = [
                        candidate
                        for candidate in observed
                        if eligible_worker(
                            data, candidate.name, candidate.mood, group_reserved
                        )
                    ]
                    names = select_workers(
                        candidates,
                        facility,
                        product,
                        len(slots),
                        current=current,
                        fixed=fixed,
                    )
                    if len(names) != len(slots):
                        completed = False
                        break
                    candidates.sort(
                        key=lambda candidate: (
                            facility_score([candidate, *fixed], facility, product),
                            candidate.name in current,
                            candidate.mood,
                        ),
                        reverse=True,
                    )
                    for (_, primary), replacement in zip(slots, names):
                        preferred[primary] = replacement
                        options[primary] = list(
                            dict.fromkeys(
                                [
                                    replacement,
                                    *(candidate.name for candidate in candidates),
                                ]
                            )
                        )
                else:
                    replacements = (
                        preferred
                        if len(set(preferred.values())) == len(preferred)
                        else match_replacements(options)
                    )
                    if replacements is None:
                        completed = False
                        continue
                    for room, slots in planned_slots.items():
                        row = pending.setdefault(
                            room, ["Current"] * len(data.plan[room])
                        )
                        for index, primary in slots:
                            row[index] = replacements[primary]
                    duration = sum(
                        estimate_dorm_minutes(room) * 60
                        if room.startswith("dorm")
                        else 45
                        for room in pending
                    )
                    if not self._emergency_operation_fits(duration):
                        return False
                    for name in replacements.values():
                        if name not in data.operators:
                            data.add(Operator(name, ""))
                    state["staffing_plan"] = copy.deepcopy(pending)
                    state["staffing_members"] = list(workers)
                    state.setdefault("automatic_replacements", {}).update(replacements)
                    state["temporary_roster"] = {
                        room: data.get_current_room(room, True)
                        for room in data.plan
                        if not room.startswith("dorm")
                    }
                    state["phase"] = "recovering"
                    state.pop("staffing_remaining", None)
                    self._emergency_save()
                    task = SchedulerTask(task_plan=copy.deepcopy(pending))
                    task.emergency_staffing = True
                    task.emergency_staffing_members = list(workers)
                    self.tasks.append(task)
                    return True
                pending = {}
        state["phase"] = "recovering"
        state["temporary_roster"] = {
            room: data.get_current_room(room, True)
            for room in data.plan
            if not room.startswith("dorm")
        }
        return completed

    def _emergency_rescore_staffing(self):
        """保留原位主班，以实测候选心情重选全部临时岗位的设施组合。"""
        state, data = self.emergency_state, self.op_data
        facilities = {
            "central": "中枢",
            "contact": "人力办公室",
            "meeting": "会客室",
        }
        supported = {"中枢", "人力办公室", "会客室", "制造站", "贸易站", "发电站"}
        unfinished = copy.deepcopy(state.get("staffing_plan", {}))
        planned_slots, fixed_by_room = {}, {}
        members = set(state.get("staffing_members", ()))
        for room, configured in data.plan.items():
            if (
                not configured
                or facilities.get(room, configured[0].facility) not in supported
            ):
                continue
            fixed_by_room[room] = []
            for index, slot in enumerate(configured):
                actual = data.get_current_operator(room, index)
                row = unfinished.get(room, ())
                required = (
                    index < len(row)
                    and row[index] not in ("Current", "Free", "")
                    and (actual is None or actual.name != row[index])
                )
                if actual is not None and actual.name == slot.agent and not required:
                    fixed_by_room[room].append(actual.name)
                else:
                    planned_slots.setdefault(room, []).append((index, slot.agent))
                    if slot.agent in data.operators:
                        op = data.operators[slot.agent]
                        members.update(data.groups.get(op.group, [op.name]))
        reserved, _ = dorm_task_reservations(data, self.tasks)
        reserved |= (
            busy_resting_names() | set(TRADE_ORDER_AGENTS) | set(state["targets"])
        )
        reserved |= {name for names in fixed_by_room.values() for name in names}
        reserved |= {
            name
            for room, row in unfinished.items()
            if room.startswith("dorm")
            for name in row
            if name not in ("Current", "Free", "")
        }
        reserved |= {
            op.name
            for op in data.operators.values()
            if op.is_working() and op.current_room not in planned_slots
        }
        reserved |= {
            op.name for op in data.operators.values() if op.room.startswith("dorm")
        }
        reserved |= {
            member
            for name in state["targets"]
            if (op := data.operators.get(name)) is not None
            for member in data.groups.get(op.group, [name])
        }
        if any(
            hasattr(task, "emergency_original_roster")
            and set(planned_slots).intersection(
                set(task.plan) | set(task.emergency_original_roster)
            )
            for task in self.tasks
        ):
            return False
        snapshot = load_skill_snapshot()
        options, preferred = {}, {}
        for room, slots in planned_slots.items():
            if not self._emergency_operation_fits(45):
                return False
            facility = facilities.get(room, data.plan[room][0].facility)
            product = data.facility_states.get(room, {}).get("product")
            fixed_names = fixed_by_room[room]
            observed = self._emergency_scan_workers(
                room, facility, reserved, snapshot=snapshot, fixed=fixed_names
            )
            by_name = {candidate.name: candidate for candidate in observed}
            fixed = []
            for name in fixed_names:
                skills = unlocked_skills(name, facility, snapshot)
                if skills is None:
                    skills = by_name[name].skills if name in by_name else ()
                op = data.operators.get(name)
                fixed.append(
                    StaffingCandidate(
                        name, op.current_mood() if has_resting_mood(op) else 0, skills
                    )
                )
            candidates = [
                candidate
                for candidate in observed
                if eligible_worker(data, candidate.name, candidate.mood, reserved)
            ]
            names = select_workers(
                candidates, facility, product, len(slots), fixed=fixed
            )
            if len(names) != len(slots):
                return False
            candidates.sort(
                key=lambda candidate: (
                    facility_score([candidate, *fixed], facility, product),
                    candidate.mood,
                ),
                reverse=True,
            )
            for (index, _), replacement in zip(slots, names):
                key = (room, index)
                preferred[key] = replacement
                options[key] = list(
                    dict.fromkeys(
                        [replacement, *(candidate.name for candidate in candidates)]
                    )
                )
        replacements = (
            preferred
            if len(set(preferred.values())) == len(preferred)
            else match_replacements(options)
        )
        if replacements is None:
            return False
        pending = {
            room: row for room, row in unfinished.items() if room.startswith("dorm")
        }
        automatic = {}
        for room, slots in planned_slots.items():
            for index, primary in slots:
                replacement = replacements[(room, index)]
                actual = data.get_current_operator(room, index)
                if actual is None or actual.name != replacement:
                    pending.setdefault(room, ["Current"] * len(data.plan[room]))[
                        index
                    ] = replacement
                if primary in data.operators:
                    automatic[primary] = replacement
        duration = sum(
            estimate_dorm_minutes(room) * 60 if room.startswith("dorm") else 45
            for room in pending
        )
        if pending and not self._emergency_operation_fits(duration):
            return False
        for name in replacements.values():
            if name not in data.operators:
                data.add(Operator(name, ""))
        state.setdefault("automatic_replacements", {}).update(automatic)
        state.pop("staffing_rescore", None)
        state["staffing_plan"] = copy.deepcopy(pending)
        if pending:
            state["staffing_members"] = sorted(members)
            self._emergency_save()
            task = SchedulerTask(task_plan=copy.deepcopy(pending))
            task.emergency_staffing = True
            task.emergency_staffing_members = sorted(members)
            self.tasks.append(task)
        else:
            state.pop("staffing_members", None)
        return True

    def _open_emergency_beds(self):
        """救急开放宿管床位，余量仅补回群回宿管；菲亚保持原位。"""
        data, state = self.op_data, self.emergency_state
        layout = state.get("dorm_layout", {})
        if not layout:
            return
        data.emergency_dorm_agents = {
            name
            for row in layout.values()
            for name in row
            if name not in ("", "Free", "Current")
        }
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
        restored = set()
        for index in range(max(map(len, layout.values()))):
            for room, row in layout.items():
                if index >= len(row) or spare <= 0:
                    continue
                name = row[index]
                manager = data.operators.get(name)
                resident = data.get_current_operator(room, index)
                if (
                    manager is None
                    or name == "菲亚梅塔"
                    or not is_group_recovery_manager(name)
                    or name in need
                    or name in reserved
                    or manager.is_working()
                    or resident is not None
                    and resident.name in need
                ):
                    continue
                restored.add((room, index))
                spare -= 1
        for room, row in layout.items():
            for index, name in enumerate(row):
                fixed = name == "菲亚梅塔" or (room, index) in restored
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
        for name in state["targets"]:
            op = data.operators.get(name)
            if op is None or name in state.get("ready_members", ()):
                continue
            rows = emergency_mood_history(name)
            rate = history_rate(rows, op.room, state["work_contexts"].get(name))
            members = data.groups.get(op.group, [name])
            opportunity = (
                native_opportunity(probe, members).opportunity if rate else None
            )
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
                for slot in self.op_data.plan.get(room, [])
                for name in slot.replacement
                if name in TRADE_ORDER_AGENTS
            }
        )
        return bool(required) and all(
            (op := self.op_data.operators.get(name)) is not None
            and (not op.is_working() or op.current_room == room)
            for name in required
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
        self.tasks[:] = [
            task
            for task in self.tasks
            if task.type not in ORDINARY_SHIFTS
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

    def _emergency_tick(self):
        self._emergency_filter_tasks()
        state = self.emergency_state
        now = datetime.now()
        if not any(getattr(t, "emergency_staffing", False) for t in self.tasks):
            pending = state.get("staffing_plan", {})
            state["staffing_plan"] = {
                room: row
                for room, row in pending.items()
                if (actual := self.op_data.get_current_room(room, True)) is not None
                and any(
                    name != "Current" and name != actual[index]
                    for index, name in enumerate(row)
                )
            }
            if pending and not state["staffing_plan"]:
                state.pop("staffing_members", None)
                state["phase"] = "recovering"
                state["temporary_roster"] = {
                    room: self.op_data.get_current_room(room, True)
                    for room in self.op_data.plan
                    if not room.startswith("dorm")
                }
                self.run_order_solver()
        read_due = now >= state.get("next_read", now)
        self.plan_metadata()
        protect_priority_tasks(self.tasks)
        if read_due:
            if state.get("handoff_observing"):
                if not self._emergency_restore():
                    self._emergency_defer_read()
                return
            rooms = (
                {room for room in self.op_data.plan if room.startswith("dorm")}
                | {
                    op.current_room
                    for name in state["targets"]
                    if (op := self.op_data.operators.get(name)) is not None
                    and op.current_room in base_room_list
                }
                | set(state.get("temporary_roster", {}))
            )
            if "pending_read_rooms" not in state:
                state["read_collection_pending"] = True
                if "observed_at" not in state:
                    state["pending_read_rooms"] = sorted(rooms)
            if state.get("read_collection_pending"):
                last = self.last_execution.get("todo")
                collection_due = (
                    last is None or datetime.now() >= last + COLLECTION_COOLDOWN
                )
                if collection_due and not self._emergency_operation_fits(90):
                    self._emergency_defer_read()
                    return
                self._emergency_collect()
                state.pop("read_collection_pending", None)
            if state.pop("observed_at", None) is None:
                if self._emergency_read_rooms(rooms, yield_to_releases=True) is False:
                    self._emergency_defer_read()
                    return
        self.plan_metadata()
        protect_priority_tasks(self.tasks)
        if read_due:
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
            if self._emergency_ready():
                if self._emergency_restore():
                    return
            if state["phase"] == "returning":
                state["next_read"] = now + timedelta(minutes=5)
            else:
                self._open_emergency_beds()
                scanned = self._emergency_schedule_staffing(
                    initial=state["phase"] == "staffing"
                )
                self._emergency_plan_beds(state)
                state["next_read"] = datetime.now() + timedelta(
                    minutes=self._emergency_read_minutes() if scanned else 1
                )
        check = next((t for t in self.tasks if t.meta_data == CHECK_META), None)
        if check is None:
            check = SchedulerTask(time=state["next_read"], meta_data=CHECK_META)
            self.tasks.append(check)
        else:
            check.time = state["next_read"]
        check.emergency_staffing_members = sorted(
            set(state.get("ready_members", ()))
            | set(state.get("staffing_members", ()))
            | set(state.get("release_members", ()))
        )
        if state["phase"] == "recovering":
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
        for task in self.tasks:
            if task.meta_data == CHECK_META:
                task.emergency_staffing_members = sorted(
                    ready | members | set(state.get("staffing_members", ()))
                )
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
        for task in self.tasks:
            if task.meta_data == CHECK_META:
                task.emergency_staffing_members = sorted(
                    ready | remaining | set(state.get("staffing_members", ()))
                )
        if not remaining:
            state.pop("release_plan", None)
            state.pop("release_members", None)
        else:
            state["release_members"] = sorted(remaining)
        self._emergency_save()
        return True

    def _emergency_read_minutes(self):
        waits = []
        for name, target in self.emergency_state["targets"].items():
            op = self.op_data.operators.get(name)
            if (
                op is None
                or not op.is_resting()
                or not has_resting_mood(op)
                or op.mood >= target
            ):
                continue
            rate = history_rate(
                emergency_mood_history(name),
                op.current_room,
                mood_context(self.op_data, op.current_room),
                op.current_index,
                recovering=True,
            )
            waits.append((target - op.mood) / rate * 60 if rate else 15)
        return max(5, min(30, min(waits, default=15)))

    def _emergency_ready(self):
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
        return all(
            (op := self.op_data.operators.get(name)) is not None
            and (
                self.op_data._can_standby(op)
                or has_resting_mood(op)
                and not op.mood_is_prediction
                and op.mood >= target
            )
            for name, target in self.emergency_state["targets"].items()
        )

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
        self.tasks[:] = [task for task in self.tasks if task.meta_data != CHECK_META]
        self.run_order_solver()
        self.plan_metadata()
        self._emergency_save()
        logger.info("主班实际心情满足目标且原生周转可行，智能救急结束")
        return True

    def _emergency_collect(self):
        """心情复查时顺便收取，沿用普通收取的防重复间隔。"""
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
