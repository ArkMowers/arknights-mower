"""失败任务的附带宿舍移动与其他组的正常回班分开处理。"""


def retained_recovery_may_return(op_data, task, group):
    """只释放失败预演的附带宿舍动作，明确任务和进行中的安排继续保留。"""
    if (
        not getattr(task, "execution_failure", None)
        or getattr(task, "backup_shift_active", False)
        or getattr(task, "product_shift_locked", False)
        or getattr(task, "dorm_recovery_restore", ())
    ):
        return False
    members = set(op_data.shift_group_members(group))
    if not members or members.intersection(task.release_dorm_targets()):
        return False
    intent = getattr(task, "backup_shift_intent", None)
    if intent is None:
        intent = task.plan
    explicit_slots = set(getattr(task, "backup_explicit_slots", ()))
    for room, row in intent.items():
        slots = op_data.plan.get(room, ())
        for index, name in enumerate(row):
            if name in ("Current", ""):
                continue
            op = op_data.operators.get(name)
            owner = (
                op_data.operators.get(slots[index].agent)
                if index < len(slots)
                else None
            )
            explicit = (room, index) in explicit_slots
            if (
                owner is not None
                and owner.name in members
                and (
                    not room.startswith("dorm")
                    or (owner.room, owner.index) == (room, index)
                )
            ):
                return False
            if (
                op is not None
                and op.name in members
                and (
                    not room.startswith("dorm")
                    or not op_data._can_standby(op)
                    or explicit
                )
            ):
                return False
            current = op_data.get_current_operator(room, index)
            if explicit and current is not None and current.name in members:
                return False
    return True


def reconcile_retained_recovery(op_data, task):
    """完整回班实读后清理过期附带宿舍动作，返回已确认回班的组。"""
    failure = getattr(task, "execution_failure", None)
    if not failure:
        return set()
    observations = failure.get("snapshot", {}).get("observations", {})

    def actually_working(op):
        return (
            bool(op.room)
            and (op.current_room, op.current_index) == (op.room, op.index)
            and not getattr(op, "mood_is_prediction", False)
        )

    candidates = {
        op.group
        for name, op in op_data.operators.items()
        if getattr(op, "group", "")
        and op_data.is_group_shift_anchor(op)
        and (previous := observations.get(name))
        and previous[0].startswith("dorm")
        and actually_working(op)
        and retained_recovery_may_return(op_data, task, op.group)
    }
    returned_groups = {
        group
        for group in candidates
        if all(
            actually_working(op_data.operators[name])
            for name in op_data.shift_group_members(group)
            if op_data.is_group_shift_anchor(op_data.operators[name])
        )
    }
    returned = {
        name
        for group in returned_groups
        for name in op_data.shift_group_members(group)
        if not op_data.operators[name].room.startswith("dorm")
        and actually_working(op_data.operators[name])
    }
    if not returned:
        return set()
    for plan in (
        task.plan,
        getattr(task, "backup_shift_intent", None),
        getattr(task, "dorm_fill_plan", None),
    ):
        if plan is None:
            continue
        for room, row in list(plan.items()):
            if not room.startswith("dorm"):
                continue
            changed = False
            for index, name in enumerate(row):
                if name in returned:
                    row[index] = "Current"
                    changed = True
            if changed and all(name == "Current" for name in row):
                del plan[room]
    return returned_groups
