"""实际换人前需要实读确认的恢复成员。"""

from arknights_mower.utils.group_recovery import group_recovery_deadline


def required_recovery_members(data, task):
    required = set()
    explicit = set(getattr(task, "backup_explicit_slots", ()))
    for room, row in task.plan.items():
        for index, name in enumerate(row):
            if (room, index) in explicit:
                continue
            op = data.operators.get(name)
            if op is None or room.startswith("dorm"):
                continue
            if not getattr(op, "rest_in_full", False) and not getattr(op, "group", ""):
                continue
            if (op.room, op.index) != (room, index) or op.is_working():
                continue
            if op.rest_in_full and not op.workaholic:
                required.add(name)
            if op.group:
                required.update(group_recovery_deadline(data, op.group)[0])
    targets = (
        task.release_dorm_targets() if hasattr(task, "release_dorm_targets") else {}
    )
    for name in targets:
        op = data.operators.get(name)
        if op is None or (
            not getattr(op, "rest_in_full", False) and not getattr(op, "group", "")
        ):
            continue
        group_required = group_recovery_deadline(data, op.group)[0] if op.group else ()
        if op.rest_in_full and not op.workaholic or name in group_required:
            required.add(name)
    return required
