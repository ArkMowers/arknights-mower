"""在岗普通替班按所选心情来源检查个人下限并安排检查期限。"""

from copy import copy, deepcopy
from datetime import datetime, timedelta
from math import isfinite

from arknights_mower.utils.dorm_candidates import (
    dorm_task_reservations,
    retained_task_reservations,
)
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.resting_correction import reconsider_low_mood_replacements
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

_TIMING_DEPENDENCY = "替班心情仍高于下限，等待有效心情消耗观测"


def _ordinary_replacements(data, owner):
    replacements = (
        data.shared_replacements(owner, data.resting_binding_groups(owner))
        if getattr(owner, "multi_group", False)
        else getattr(owner, "replacement", ())
    )
    return [
        name
        for name in replacements
        if name != "Free" and name not in TRADE_ORDER_AGENTS
    ]


def replacement_check_applies(data, target):
    room, index = target["room"], target["index"]
    slots = data.plan.get(room, ())
    owner = data.operators.get(target["owner"])
    cover = data.operators.get(target["cover"])
    return (
        not room.startswith("dorm")
        and room != "train"
        and 0 <= index < len(slots)
        and slots[index].agent == target["owner"]
        and owner is not None
        and callable(getattr(owner, "is_high", None))
        and owner.is_high()
        and cover is not None
        and callable(getattr(cover, "is_high", None))
        and not cover.is_high()
        and callable(getattr(cover, "is_working", None))
        and (cover.current_room, cover.current_index) == (room, index)
        and cover.is_working()
        and target["cover"] in _ordinary_replacements(data, owner)
        and len(set(_ordinary_replacements(data, owner))) > 1
        and not data.config.is_workaholic(target["cover"])
    )


def _reservations(solver, task):
    tasks = [queued for queued in solver.tasks if queued is not task]
    current = getattr(solver, "task", None)
    if (
        current is not None
        and current is not task
        and not any(queued is current for queued in tasks)
    ):
        tasks.append(current)
    names, slots = dorm_task_reservations(solver.op_data, tasks)
    retained_names, retained_slots = retained_task_reservations(solver.op_data, tasks)
    names.update(retained_names)
    slots.update(retained_slots)
    names.update(getattr(solver.op_data, "reserved_product_replacements", ()))
    slots.update(getattr(solver.op_data, "reserved_product_beds", ()))
    protected = getattr(solver, "_protected_training_names", None)
    if protected is not None:
        names.update(protected())
    return names, slots


def replacement_check_snapshot(solver, task):
    """记录岗位环境、候补实测及预约，不把时钟推进作为新事实。"""
    data, target = solver.op_data, task.replacement_check
    owner = data.operators.get(target["owner"])
    candidates = _ordinary_replacements(data, owner) if owner is not None else []
    names = set(candidates) | {target["owner"], target["cover"]}
    rooms = {target["room"]} | {
        op.current_room
        for name in names
        if (op := data.operators.get(name)) is not None and op.current_room
    }
    reserved, slots = _reservations(solver, task)
    observations = {}
    previous = getattr(task, "replacement_check_source", {}).get("observations", {})
    observation_names = names
    if getattr(data, "mood_calculation_enabled", False):
        observation_names = names | {
            name for name, op in data.operators.items() if op.current_room == "central"
        }
    for name in sorted(observation_names):
        op = data.operators.get(name)
        if op is None:
            continue
        if (
            getattr(op, "mood_is_prediction", False)
            or op.time_stamp is None
            or not _finite_mood(op.mood)
        ):
            # 预估及其失效不能抹掉上次实测，也不能借数值变化重开失败检查。
            sample = previous.get(name, (None,) * 5)[2:]
        else:
            sample = (
                op.mood,
                op.time_stamp,
                op.depletion_rate if isfinite(op.depletion_rate) else None,
            )
        observations[name] = (op.current_room, op.current_index, *sample)
    environment = {
        "slots": [vars(slot) for slot in data.plan.get(target["room"], ())],
        "candidates": candidates,
        "limits": {
            name: (
                op.lower_limit,
                op.upper_limit,
                op.rest_in_full,
                data.config.is_workaholic(name),
            )
            for name in sorted(names)
            if (op := data.operators.get(name)) is not None
        },
        "occupants": sorted(
            (op.current_index, name)
            for name, op in data.operators.items()
            if op.current_room == target["room"]
        ),
        "product": getattr(data, "products", {}).get(target["room"]),
        "actual_product": getattr(data, "facility_states", {})
        .get(target["room"], {})
        .get("product"),
        "refresh_drained": sorted(
            (name, op.current_room, op.current_index)
            for name, op in data.operators.items()
            if getattr(op, "refresh_drained", False)
        ),
    }
    if getattr(data, "mood_calculation_enabled", False):
        model = data.mood_model
        relevant = names | {
            name for name, op in data.operators.items() if op.current_room == "central"
        }
        environment["calculated_mood"] = {
            "stages": model.stages,
            "single_targets": model.single_targets,
            "rooms": {
                room: (
                    sorted(
                        (op.current_index, name)
                        for name, op in data.operators.items()
                        if op.current_room == room
                    ),
                    getattr(data, "facility_states", {}).get(room, {}).get("facility"),
                    getattr(data, "facility_states", {}).get(room, {}).get("product"),
                    getattr(data, "products", {}).get(room),
                    model.rooms.get(room, {}).get(
                        "level",
                        5 if room.startswith("dorm") or room == "central" else 3,
                    ),
                    [getattr(slot, "facility", "") for slot in data.plan[room]],
                )
                for room in data.plan
            },
            "observations": {
                name: (model.observed.get(name), model.barriers.get(name))
                for name in sorted(relevant)
            },
        }
    return deepcopy(
        {
            "target": target,
            "environment": environment,
            "observations": observations,
            "reservations": (
                sorted(names & reserved),
                sorted(
                    slots
                    & {
                        (target["room"], target["index"]),
                        *(
                            (op.current_room, op.current_index)
                            for name in names
                            if (op := data.operators.get(name)) is not None
                        ),
                    }
                ),
            ),
            "room_observations": {
                room: getattr(data, "room_observations", {}).get(room)
                for room in sorted(rooms)
            },
            "revision": getattr(task, "replacement_check_revision", 0),
        }
    )


def sync_replacement_checks(solver):
    """同步真实在岗替班；同一份观测保留原检查及失败状态。"""
    data = getattr(solver, "op_data", None)
    if data is None or not all(
        hasattr(data, field)
        for field in ("plan", "operators", "config", "get_current_operator")
    ):
        return
    if not callable(getattr(data.config, "is_workaholic", None)):
        return
    pending = getattr(solver, "_initial_mood_read_pending", None)
    if pending is not None and pending():
        return
    calculated = getattr(data, "mood_calculation_enabled", False)
    frozen = getattr(solver, "_emergency_frozen", None)
    targets = {}
    concrete_slots = {
        (room, index)
        for queued in solver.tasks
        if getattr(queued, "replacement_check", None) is None
        and (queued is getattr(solver, "task", None) or queued.time <= datetime.now())
        for room, row in queued.plan.items()
        for index, name in enumerate(row)
        if name != "Current"
        and (
            (actual := data.get_current_operator(room, index)) is None
            or name != actual.name
        )
    }
    if frozen is None or not frozen():
        for room, slots in data.plan.items():
            for index, slot in enumerate(slots):
                actual = data.get_current_operator(room, index)
                if actual is None:
                    continue
                target = {
                    "owner": slot.agent,
                    "cover": actual.name,
                    "room": room,
                    "index": index,
                }
                if replacement_check_applies(data, target):
                    targets[(room, index, slot.agent, actual.name)] = target
    existing = {}
    remove = []
    for task in solver.tasks:
        target = getattr(task, "replacement_check", None)
        if target is None:
            continue
        key = (target["room"], target["index"], target["owner"], target["cover"])
        if (
            key not in targets
            or key in existing
            or (target["room"], target["index"]) in concrete_slots
            and not task.retains_execution
        ):
            remove.append(task)
            continue
        existing[key] = task
        failure = getattr(task, "execution_failure", None)
        if failure and failure["reason"] == _TIMING_DEPENDENCY:
            # 旧快照没有保存依赖分类；加载后仍按正常观测依赖处理。
            failure["dependency"] = True
        snapshot = replacement_check_snapshot(solver, task)
        previous = getattr(task, "replacement_check_source", None)
        if calculated:
            if not task.retains_execution:
                task.meta_data = f"替班下限确认：{target['cover']}"
            task.__dict__.pop("replacement_check_read_after", None)
            if (
                previous != snapshot
                or getattr(task, "replacement_check_deadline", None) is None
            ) and not task.retains_execution:
                _sync_calculated_deadline(solver, task)
            else:
                task.replacement_check_source = snapshot
            continue
        if previous is not None:
            if previous["environment"] != snapshot["environment"] or (
                previous["revision"] != snapshot["revision"]
                and getattr(task, "replacement_check_read_after", None) is None
            ):
                task.replacement_check_read_after = datetime.now()
        cover = data.operators[target["cover"]]
        observation = snapshot["observations"][target["cover"]]
        previous_observation = (
            previous["observations"].get(target["cover"]) if previous else None
        )
        rate_changed = (
            observation[4] is not None
            and observation[4] > 0
            and (
                previous_observation is None
                or previous_observation[4] != observation[4]
            )
        )
        # 候选恢复和预约释放只重新开放失败检查，不移动已有工作期限。
        # 仅更新采样保留工作期限；达到下限或实测速率改变时重新核实心情。
        if (
            previous is not None
            and (
                previous["environment"] != snapshot["environment"]
                or (
                    previous_observation != observation
                    and cover.time_stamp is not None
                    and not getattr(cover, "mood_is_prediction", False)
                    and _finite_mood(cover.mood)
                    and (cover.mood <= cover.lower_limit or rate_changed)
                )
                or previous["revision"] != snapshot["revision"]
            )
            and not task.retains_execution
        ):
            task.time = min(task.time, datetime.now())
        task.replacement_check_source = snapshot
    solver.tasks[:] = [
        task for task in solver.tasks if not any(task is stale for stale in remove)
    ]
    for key, target in targets.items():
        if key in existing or (target["room"], target["index"]) in concrete_slots:
            continue
        # 执行时先复用已有观测，不因新建检查而强制进房。
        task = SchedulerTask(
            meta_data=f"替班心情检查：{target['cover']}",
            task_type=TaskTypes.NOT_SPECIFIC,
        )
        task.replacement_check = target
        task.replacement_check_deadline = None
        task.replacement_check_source = replacement_check_snapshot(solver, task)
        solver.tasks.append(task)
        if calculated:
            task.meta_data = f"替班下限确认：{target['cover']}"
            _sync_calculated_deadline(solver, task)


def _sync_calculated_deadline(solver, task):
    """直接安排模型下限期限，未知输入等待正常观测，不派发额外检查。"""
    data = solver.op_data
    cover = data.operators[task.replacement_check["cover"]]
    now = datetime.now()
    mood = data.calculated_mood(cover.name, now)
    if not _finite_mood(mood):
        return _retain(solver, task, "替班心情计算尚无有效观测", dependency=True)
    if mood <= cover.lower_limit:
        # 正常操作已经实读到下限时，该次观测直接完成确认，不再专门进房。
        deadline = (
            cover.time_stamp
            if cover.time_stamp is not None
            and cover.time_stamp <= now
            and not getattr(cover, "mood_is_prediction", False)
            and _finite_mood(cover.mood)
            and cover.mood <= cover.lower_limit
            else now
        )
    else:
        deadline = data.calculated_mood_deadline(cover.name, cover.lower_limit, now)
    if deadline is None or mood > cover.lower_limit and deadline <= now:
        return _retain(solver, task, _TIMING_DEPENDENCY, dependency=True)
    task.time = deadline
    task.replacement_check_deadline = deadline
    task.replacement_check_source = replacement_check_snapshot(solver, task)


def invalidate_replacement_checks(solver):
    """环境事件重算模型期限；旧识别模式仍要求重新实读。"""
    calculated = getattr(solver.op_data, "mood_calculation_enabled", False)
    for task in solver.tasks:
        if getattr(task, "replacement_check", None) is not None:
            if not calculated:
                task.replacement_check_read_after = datetime.now()
            task.replacement_check_revision = (
                getattr(task, "replacement_check_revision", 0) + 1
            )
            if not calculated and not task.retains_execution:
                task.time = min(task.time, datetime.now())


def _retain(solver, task, reason, *, dependency=False):
    # 本轮已经产生的观测先纳入来源，不能在下一轮把自己的读数当新事件。
    task.replacement_check_source = replacement_check_snapshot(solver, task)
    solver._retain_failed_task(
        task, reason, [task.replacement_check["room"]], dependency=dependency
    )
    return False


def _finite_mood(value):
    return isinstance(value, (int, float)) and isfinite(value) and 0 <= value <= 24


def _cached_work_mood(cover, task):
    """近期实读仍高于下限时复用；预计到期及工作环境变化仍须新观测。"""
    now = datetime.now()
    sampled_at = cover.time_stamp
    read_after = getattr(task, "replacement_check_read_after", None)
    # 旧任务沿用保存的原期限；新建检查显式标记尚无期限。
    deadline = getattr(task, "replacement_check_deadline", task.time)
    if (
        sampled_at is None
        or not sampled_at <= now
        or getattr(cover, "mood_is_prediction", False)
        or getattr(cover, "working_mood_unconfirmed", False)
        or not _finite_mood(cover.mood)
        or cover.need_to_refresh(r=cover.current_room)
        or (read_after is not None and sampled_at <= read_after)
        or (deadline is not None and sampled_at < deadline <= now)
    ):
        return None
    rate = cover.depletion_rate
    mood = cover.mood
    if isfinite(rate) and rate > 0:
        mood -= rate * (now - sampled_at).total_seconds() / 3600
    return mood if mood > cover.lower_limit else None


def _check_read_values(snapshot, room):
    """比较实读前后的业务值，排除本次读房产生的采样时间和观测次数。"""
    values = deepcopy(snapshot)
    for name, observation in values["observations"].items():
        if observation[0] == room:
            values["observations"][name] = (*observation[:2], None)
    values["room_observations"].pop(room, None)
    facility = values["facilities"].get(room)
    if facility is not None:
        facility.pop("updated_at", None)
    source = values["replacement_check"]
    for name, observation in source["observations"].items():
        if observation[0] == room:
            source["observations"][name] = (
                *observation[:3],
                None,
                *observation[4:],
            )
    source["room_observations"].pop(room, None)
    model = source["environment"].get("calculated_mood", {})
    for name, observation in model.get("observations", {}).items():
        if source["observations"].get(name, (None,))[0] == room:
            model["observations"][name] = (None, observation[1])
    return values


def _preserve_peer_failures(solver, peers, room):
    for peer, failure, before in peers:
        if getattr(peer, "execution_failure", None) is not failure:
            continue
        # 读取前已有相关变化时不能消费，否则会遗漏候补释放等恢复条件。
        if failure["snapshot"] != before:
            continue
        after = solver._task_failure_snapshot(peer, failure["rooms"])
        if _check_read_values(before, room) == _check_read_values(after, room):
            failure["snapshot"] = after


def run_replacement_check(solver, task):
    """到期核实原岗位心情，达到个人下限后复用普通替班纠错。"""
    target, data = task.replacement_check, solver.op_data
    if not replacement_check_applies(data, target):
        return True
    room, index = target["room"], target["index"]
    cover = data.operators[target["cover"]]
    calculated = getattr(data, "mood_calculation_enabled", False)
    mood = (
        data.calculated_mood(cover.name)
        if calculated
        else _cached_work_mood(cover, task)
    )
    observed = {"agent": cover.name, "mood": mood}
    deadline = getattr(task, "replacement_check_deadline", None)
    confirmed_floor = (
        calculated
        and deadline is not None
        and cover.time_stamp is not None
        and deadline <= cover.time_stamp <= datetime.now()
        and not getattr(cover, "mood_is_prediction", False)
        and _finite_mood(cover.mood)
        and cover.mood <= cover.lower_limit
    )
    if (not calculated and mood is None) or (
        calculated
        and _finite_mood(mood)
        and mood <= cover.lower_limit
        and not confirmed_floor
    ):
        peers = [
            (peer, failure, solver._task_failure_snapshot(peer, failure["rooms"]))
            for peer in solver.tasks
            if peer is not task
            and getattr(peer, "replacement_check", None)
            and (failure := getattr(peer, "execution_failure", None))
        ]
        try:
            solver.enter_room(room)
            result = solver.get_agent_from_room(
                room,
                force_mood=True,
                strict_observation=True,
            )
            solver.back()
        except RecognizeError as exc:
            _preserve_peer_failures(solver, peers, room)
            return _retain(solver, task, f"替班心情检查未取得有效读数：{exc}")
        _preserve_peer_failures(solver, peers, room)
        observed = result[index] if 0 <= index < len(result) else {}
    if observed.get("observed") is False or not _finite_mood(observed.get("mood")):
        return _retain(
            solver,
            task,
            "替班心情计算尚无有效观测" if calculated else "替班心情检查未取得有效读数",
            dependency=calculated,
        )
    if observed.get("agent") != target["cover"]:
        if observed.get("observed", True) and isinstance(observed.get("agent"), str):
            return True
        return _retain(solver, task, "替班心情检查未确认原岗位驻员")
    if not replacement_check_applies(data, target):
        return True
    task.__dict__.pop("replacement_check_read_after", None)
    cover = data.operators[target["cover"]]
    mood = observed["mood"]
    now = datetime.now()
    if mood > cover.lower_limit:
        end = observed.get("time")
        if calculated:
            deadline = data.calculated_mood_deadline(cover.name, cover.lower_limit, now)
            if deadline is None or deadline <= now:
                return _retain(solver, task, _TIMING_DEPENDENCY, dependency=True)
        elif isfinite(cover.depletion_rate) and cover.depletion_rate > 0:
            deadline = now + timedelta(
                hours=(mood - cover.lower_limit) / cover.depletion_rate
            )
        elif room != "recycle" and isinstance(end, datetime) and end > now:
            deadline = now + (end - now) * ((mood - cover.lower_limit) / mood)
        else:
            return _retain(
                solver,
                task,
                _TIMING_DEPENDENCY,
                dependency=True,
            )
        if task.retains_execution:
            successor = SchedulerTask(time=deadline, meta_data=task.meta_data)
            successor.replacement_check = deepcopy(target)
            successor.replacement_check_revision = getattr(
                task, "replacement_check_revision", 0
            )
            successor.replacement_check_source = replacement_check_snapshot(
                solver, successor
            )
            successor.replacement_check_deadline = deadline
            solver.tasks.append(successor)
            return True
        task.time = deadline
        task.replacement_check_deadline = deadline
        task.replacement_check_source = replacement_check_snapshot(solver, task)
        return False

    from arknights_mower.solvers.base_schedule import _is_mastery_busy

    reserved, reserved_slots = _reservations(solver, task)
    if target["cover"] in reserved or (room, index) in reserved_slots:
        return _retain(solver, task, "替班岗位仍由其他任务预约")
    view = copy(data)
    view.plan = {room: data.plan[room]}
    view.reserved_product_replacements = reserved
    actual = data.get_current_room(room, True)
    if actual is None or index >= len(actual):
        return _retain(solver, task, "替班心情检查未确认房间驻员")
    plan = {room: list(actual)}
    plan[room][index] = "Current"
    reconsider_low_mood_replacements(view, plan, _is_mastery_busy)
    replacement = plan[room][index]
    if replacement in ("", "Current", target["cover"]):
        return _retain(solver, task, "替班达到个人心情下限，尚无可用候补")
    row = ["Current"] * len(data.plan[room])
    row[index] = replacement
    solver.tasks.append(
        SchedulerTask(task_plan={room: row}, task_type=TaskTypes.SELF_CORRECTION)
    )
    return True
