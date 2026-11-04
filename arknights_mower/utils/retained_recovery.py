"""失败任务的附带宿舍移动与其他组的正常回班分开处理。"""


def _unstarted_failed_task(task):
    return bool(getattr(task, "execution_failure", None)) and not any(
        getattr(task, flag, False)
        for flag in (
            "backup_shift_active",
            "group_shift_expected",
            "mood_physical_started",
            "derived_correction_started",
            "product_shift_locked",
            "dorm_recovery_restore",
        )
    )


def completed_ordinary_rest_request(op_data, task):
    """实际入住已完成的普通下班请求不再占有未执行的附带安排。"""
    if (
        not _unstarted_failed_task(task)
        or not getattr(task, "ordinary_coordination", False)
        or getattr(task, "exhaust_support", False)
        or getattr(task, "backup_explicit_slots", ())
        or getattr(task, "backup_group_request", None)
        or getattr(getattr(task, "type", None), "name", "")
        not in ("SHIFT_OFF", "EXHAUST_OFF")
    ):
        return False
    requested = getattr(task, "coordination_request_names", ())
    if not requested or any(name not in op_data.operators for name in requested):
        return False
    groups = set(op_data.shift_request_groups(requested))
    members = {
        member for group in groups for member in op_data.shift_group_members(group)
    } | {name for name in requested if not op_data.operators[name].group}
    required = [
        op_data.operators[name]
        for name in members
        if op_data.operators[name].is_high()
        and not op_data.operators[name].room.startswith("dorm")
        and not op_data.operators[name].workaholic
        and not op_data._can_standby(op_data.operators[name])
        and (
            not op_data.operators[name].multi_group
            or op_data.operators[name].shift_group in groups
            or len(requested) == 1
            and op_data.operators[name].independent_rest
        )
    ]
    return bool(required) and all(
        op.is_resting()
        and op_data.get_current_operator(op.current_room, op.current_index) is op
        for op in required
    )


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
                and (not room.startswith("dorm") or explicit)
            ):
                return False
            current = op_data.get_current_operator(room, index)
            if explicit and current is not None and current.name in members:
                return False
    return True


def retained_bed_allows_return(op_data, task, name):
    """未执行的入住任务允许当前住客正常回班腾床，保留原入住目标。"""
    if not _unstarted_failed_task(task):
        return False
    op = op_data.operators.get(name)
    if (
        op is None
        or not op.is_high()
        or op.group
        or not op.room
        or op.room.startswith("dorm")
        or not op.is_resting()
        or op.multi_group
        and op_data.resting_binding_groups(op)
        or name in task.release_dorm_targets()
    ):
        return False
    bed = op_data.get_dorm_by_name(name)
    if bed is None or bed[1].position != (op.current_room, op.current_index):
        return False
    target = task.plan.get(op.current_room, ())[op.current_index : op.current_index + 1]
    if not target or target[0] not in op_data.operators or target[0] == name:
        return False
    intent = getattr(task, "backup_shift_intent", None) or task.plan
    for plan in (intent, task.plan):
        if any(name in row for row in plan.values()):
            return False
        own_target = plan.get(op.room, ())[op.index : op.index + 1]
        if own_target and own_target[0] != "Current":
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
    expected = getattr(task, "group_shift_expected", None)
    if expected is not None:
        task.group_shift_expected = {
            position: name
            for position, name in expected.items()
            if not (position[0].startswith("dorm") and name in returned)
        }
    transitions = getattr(task, "group_shift_transitions", {})
    for group in returned_groups:
        transitions.pop(group, None)
    return returned_groups
