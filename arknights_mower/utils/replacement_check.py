"""在岗普通替班按实读工作倒计时检查个人心情下限。"""

from copy import copy, deepcopy
from datetime import datetime
from math import isfinite

from arknights_mower.utils.dorm_candidates import (
    dorm_task_reservations,
    retained_task_reservations,
)
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.resting_correction import reconsider_low_mood_replacements
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


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


def _target_applies(data, target):
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
    for name in sorted(names):
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
                if _target_applies(data, target):
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
        snapshot = replacement_check_snapshot(solver, task)
        previous = getattr(task, "replacement_check_source", None)
        cover = data.operators[target["cover"]]
        # 候选恢复和预约释放只重新开放失败检查，不移动已有工作期限。
        # 整房实读会更新同房替班的采样；未到下限时保留各自工作倒计时。
        if (
            previous is not None
            and (
                previous["environment"] != snapshot["environment"]
                or (
                    previous["observations"].get(target["cover"])
                    != snapshot["observations"].get(target["cover"])
                    and cover.time_stamp is not None
                    and not getattr(cover, "mood_is_prediction", False)
                    and _finite_mood(cover.mood)
                    and cover.mood <= cover.lower_limit
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
        # 旧消耗速率没有工作段来源；新上岗先核实一次当前工作倒计时。
        task = SchedulerTask(
            meta_data=f"替班心情检查：{target['cover']}",
            task_type=TaskTypes.NOT_SPECIFIC,
        )
        task.replacement_check = target
        task.replacement_check_source = replacement_check_snapshot(solver, task)
        solver.tasks.append(task)


def invalidate_replacement_checks(solver):
    """已确认影响工作消耗的环境事件使原倒计时需要重新实读。"""
    for task in solver.tasks:
        if getattr(task, "replacement_check", None) is not None:
            task.replacement_check_revision = (
                getattr(task, "replacement_check_revision", 0) + 1
            )
            if not task.retains_execution:
                task.time = min(task.time, datetime.now())


def _retain(solver, task, reason):
    # 本轮已经产生的观测先纳入来源，不能在下一轮把自己的读数当新事件。
    task.replacement_check_source = replacement_check_snapshot(solver, task)
    solver._retain_failed_task(task, reason, [task.replacement_check["room"]])
    return False


def _finite_mood(value):
    return isinstance(value, (int, float)) and isfinite(value) and 0 <= value <= 24


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
    """到期核实原岗位；确认达到个人下限后复用普通替班纠错。"""
    target, data = task.replacement_check, solver.op_data
    if not _target_applies(data, target):
        return True
    room, index = target["room"], target["index"]
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
            [index],
            force_mood=True,
            strict_observation=True,
            force_working_time=True,
        )
        solver.back()
    except RecognizeError as exc:
        _preserve_peer_failures(solver, peers, room)
        return _retain(solver, task, f"替班心情检查未取得有效读数：{exc}")
    _preserve_peer_failures(solver, peers, room)
    observed = result[index] if 0 <= index < len(result) else {}
    if observed.get("observed") is False or not _finite_mood(observed.get("mood")):
        return _retain(solver, task, "替班心情检查未取得有效读数")
    if observed.get("agent") != target["cover"]:
        if observed.get("observed", True) and isinstance(observed.get("agent"), str):
            return True
        return _retain(solver, task, "替班心情检查未确认原岗位驻员")
    if not _target_applies(data, target):
        return True
    cover = data.operators[target["cover"]]
    mood = observed["mood"]
    now = datetime.now()
    if mood > cover.lower_limit:
        end = observed.get("time")
        if not isinstance(end, datetime) or end <= now:
            return _retain(solver, task, "替班仍有工作心情，但工作倒计时未核实")
        deadline = now + (end - now) * ((mood - cover.lower_limit) / mood)
        if task.retains_execution:
            successor = SchedulerTask(time=deadline, meta_data=task.meta_data)
            successor.replacement_check = deepcopy(target)
            successor.replacement_check_revision = getattr(
                task, "replacement_check_revision", 0
            )
            successor.replacement_check_source = replacement_check_snapshot(
                solver, successor
            )
            solver.tasks.append(successor)
            return True
        task.time = deadline
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
