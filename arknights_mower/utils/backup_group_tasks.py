"""副表按绑组请求换班，并按执行方式约束回班。"""

from datetime import datetime


def active_group_tasks(data):
    result = {}
    for index, (active, backup) in enumerate(
        zip(getattr(data, "plan_condition", ()), getattr(data, "backup_plans", ()))
    ):
        if not active:
            continue
        for task in getattr(backup, "group_tasks", ()):
            result[(index, task["group"], task["action"], task.get("mode", "once"))] = (
                task
            )
    directions = {}
    for task in result.values():
        group, action = task["group"], task["action"]
        if group in directions and directions[group] != action:
            raise ValueError(f"生效副表对同一绑组安排了相反的上下班任务：{group}")
        directions[group] = action
    return result


def held_rest_groups(data, *, forced_only=False):
    return {
        task["group"]
        for task in active_group_tasks(data).values()
        if task["action"] == "off"
        and task.get("mode")
        in (("forced",) if forced_only else ("while_active", "forced"))
    }


def validate_group_tasks(data):
    for task in active_group_tasks(data).values():
        if not any(
            data.is_group_shift_anchor(data.operators[name])
            for name in data.shift_group_members(task["group"])
        ):
            raise ValueError(f"绑组任务找不到工作主班：{task['group']}")


def forced_group_cover_reservations(data):
    groups = {
        group
        for group in held_rest_groups(data, forced_only=True)
        if data.group_is_resting(group)
    }
    names, slots = set(), set()
    for group in groups:
        for name in data.shift_group_members(group):
            owner = data.operators[name]
            cover = data.get_current_operator(owner.room, owner.index)
            if cover is not None and cover.name != name:
                names.add(cover.name)
                slots.add((owner.room, owner.index))
    return names, slots


def sync_group_tasks(solver, *, now=None):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
    from arknights_mower.utils.urgent_recovery import urgent_support_blocked

    data = solver.op_data
    if getattr(solver, "_emergency_frozen", lambda: False)() or getattr(
        solver, "_coordination_projection", False
    ):
        return
    active = active_group_tasks(data)
    state = getattr(solver, "backup_group_task_issued", set())
    solver.backup_group_task_issued = state = set(state).intersection(active)
    queues = [solver.tasks, getattr(solver, "waiting_group_shifts", [])]
    for queue in queues:
        queue[:] = [
            task
            for task in queue
            if not (request := getattr(task, "backup_group_request", None))
            or tuple(request) in active
            or getattr(task, "mood_physical_started", False)
            or getattr(task, "backup_shift_active", False)
            or getattr(task, "group_shift_expected", {})
        ]
    for token in active:
        group, action, mode = token[1:]
        members = data.shift_group_members(group)
        anchors = [
            name for name in members if data.is_group_shift_anchor(data.operators[name])
        ]
        if not anchors:
            raise ValueError(f"绑组任务找不到工作主班：{group}")
        if mode == "once" and token in state:
            continue
        if any(
            tuple(getattr(task, "backup_group_request", ()))[1:3] == token[1:3]
            for queue in queues
            for task in queue
        ):
            continue
        if data.group_is_resting(group) == (action == "off"):
            state.add(token)
            continue
        if action == "off" and urgent_support_blocked(data, members, solver.tasks):
            continue
        task = SchedulerTask(
            time=now or datetime.now(),
            task_plan={},
            task_type=TaskTypes.EXHAUST_OFF if action == "off" else TaskTypes.SHIFT_ON,
            meta_data=anchors[0],
        )
        task.backup_group_request = token
        if action == "on":
            task.meta_data = ""
            for name in members:
                op = data.operators[name]
                if op.room in data.plan:
                    task.plan.setdefault(
                        op.room, ["Current"] * len(data.plan[op.room])
                    )[op.index] = name
        solver.tasks.append(task)
        state.add(token)


def filter_held_returns(data, tasks):
    """只裁剪未开始的派生回班；协调回班及已开始的交接保持原责任。"""
    from arknights_mower.utils.scheduler_task import TaskTypes

    held = held_rest_groups(data)
    if not held:
        return
    for task in tasks[:]:
        if (
            task.type != TaskTypes.SHIFT_ON
            or task.retains_execution
            or getattr(task, "backup_group_request", None)
            or getattr(task, "exhaust_support", False)
            or getattr(task, "backup_shift_active", False)
            or getattr(task, "mood_physical_started", False)
            or getattr(task, "product_shift_locked", False)
            or getattr(task, "dorm_recovery_restore", ())
        ):
            continue
        blocked = {
            group
            for group, resting in data.arrangement_group_transitions(task.plan).items()
            if not resting and group in held
        }
        members = {
            name for group in blocked for name in data.shift_group_members(group)
        }
        if not members:
            continue
        for room, row in list(task.plan.items()):
            for index, name in enumerate(row):
                resident = data.get_current_operator(room, index)
                if (
                    name in members
                    or room.startswith("dorm")
                    and resident
                    and resident.name in members
                ):
                    row[index] = "Current"
            if all(name == "Current" for name in row):
                del task.plan[room]
        if not task.plan:
            tasks.remove(task)
        else:
            for field in (
                "backup_shift_intent",
                "backup_shift_conditions",
                "group_shift_transitions",
            ):
                task.__dict__.pop(field, None)
