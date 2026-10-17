"""用尽交接后保留受援者本轮恢复，避免反向或连续强制召回。"""

from arknights_mower.utils.group_recovery import (
    completed_mood_limit_release,
    observed_full_mood,
)

PENDING_FIELDS = (
    "urgent_recovery_request_names",
    "urgent_recovery_support_names",
    "urgent_recovery_reserved_names",
    "urgent_recovery_reserved_slots",
)


def recovery_owner(data, op, requested):
    return data.is_group_shift_anchor(op) or (
        len(requested) == 1
        and op.name in requested
        and op.independent_rest
        and not op.workaholic
        and not data._can_standby(op)
    )


def active_urgent_recovery(data):
    """正常回班或实读完成后解除本人保护，其余受援者继续保留支持关系。"""
    return {
        name: list(supporters)
        for name, supporters in getattr(data, "urgent_recovery_supporters", {}).items()
        if (op := data.operators.get(name)) is not None
        and not (
            (op.current_room, op.current_index) == (op.room, op.index)
            and not op.room.startswith("dorm")
            or observed_full_mood(op)
            or completed_mood_limit_release(data, op)
        )
    }


def pending_urgent_reservations(tasks, current=None):
    """前置交接释放的替班和床位归原用尽请求使用，直到实际入宿。"""
    names, slots = set(), set()
    own = set(getattr(current, "urgent_recovery_request_names", ()))
    for task in tasks:
        if task is None or task is current:
            continue
        if own and own == set(getattr(task, "urgent_recovery_request_names", ())):
            continue
        names.update(getattr(task, "urgent_recovery_reserved_names", ()))
        slots.update(getattr(task, "urgent_recovery_reserved_slots", ()))
    return names, slots


def urgent_support_blocked(data, candidates, tasks=(), current=None):
    supporters = {
        name for names in active_urgent_recovery(data).values() for name in names
    }
    for task in tasks:
        if task is not current and not getattr(task, "exhaust_support", False):
            supporters.update(getattr(task, "urgent_recovery_support_names", ()))
    return bool(supporters.intersection(candidates))


def prepare_urgent_support(data, task, candidates):
    """预留交接后供原请求使用的资源，实际入宿前不登记恢复保护。"""
    initial_positions = getattr(task, "urgent_recovery_initial_positions", {})
    if any(
        (op := data.operators.get(name)) is not None
        and initial_positions.get(name) != (op.current_room, op.current_index)
        and (op.current_room, op.current_index) == (op.room, op.index)
        for name in getattr(task, "urgent_recovery_support_names", ())
    ):
        task.urgent_recovery_started = True
    for field in (
        *PENDING_FIELDS,
        "urgent_recovery_freed_names",
        "urgent_recovery_freed_slots",
    ):
        task.__dict__.pop(field, None)
    if not getattr(task, "urgent_recovery_started", False) or not initial_positions:
        task.urgent_recovery_initial_positions = {
            op.name: (op.current_room, op.current_index)
            for op in data.operators.values()
        }
        task.urgent_recovery_initial_workers = [
            op.name
            for op in data.operators.values()
            if op.is_resting()
            and (
                data.is_group_shift_anchor(op)
                or op.independent_rest
                and not data.resting_binding_groups(op)
                and not op.workaholic
                and not data._can_standby(op)
            )
        ]
    before = task.urgent_recovery_initial_positions
    projected = data.project_arrangements([task.plan])
    supporters = [
        name
        for name in task.urgent_recovery_initial_workers
        if (op := projected.operators.get(name)) is not None
        and (op.current_room, op.current_index) == (op.room, op.index)
        and not op.room.startswith("dorm")
    ]
    if not supporters:
        return
    task.urgent_recovery_request_names = list(candidates)
    task.urgent_recovery_support_names = supporters
    task.urgent_recovery_freed_names = [
        op.name
        for op in data.operators.values()
        if before.get(op.name, ("", -1))[0]
        and not projected.operators[op.name].current_room
        and not op.is_high()
    ]
    task.urgent_recovery_freed_slots = [before[name] for name in supporters]

    task.urgent_recovery_reserved_names = list(task.urgent_recovery_freed_names)
    task.urgent_recovery_reserved_slots = list(task.urgent_recovery_freed_slots)


def complete_urgent_recovery(data, task, tasks):
    """只在实际目标确认后传递交接资源或登记本轮受援恢复。"""
    active = active_urgent_recovery(data)
    requested = set(getattr(task, "urgent_recovery_request_names", ()))
    supporters = list(getattr(task, "urgent_recovery_support_names", ()))
    if requested and supporters:
        if getattr(task, "exhaust_support", False):
            for pending in tasks:
                if (
                    pending is task
                    or getattr(getattr(pending, "type", None), "name", "")
                    != "EXHAUST_OFF"
                    or requested
                    != set(getattr(pending, "coordination_request_names", ()))
                ):
                    continue
                pending.urgent_recovery_request_names = list(requested)
                pending.urgent_recovery_support_names = supporters
                pending.urgent_recovery_reserved_names = list(
                    getattr(task, "urgent_recovery_freed_names", ())
                )
                pending.urgent_recovery_reserved_slots = list(
                    getattr(task, "urgent_recovery_freed_slots", ())
                )
        for name in requested:
            op = data.operators.get(name)
            if (
                op is not None
                and recovery_owner(data, op, requested)
                and op.is_resting()
            ):
                active[name] = supporters
    data.urgent_recovery_supporters = active
