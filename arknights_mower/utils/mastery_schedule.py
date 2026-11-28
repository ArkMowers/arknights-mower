"""Check assistant reservations in possible schedules during training."""

import ast
from copy import deepcopy
from functools import lru_cache
from time import monotonic
from types import SimpleNamespace

from arknights_mower.utils.backup_validation import (
    BackupValidationLimitExceeded,
    possible_backup_conditions,
)
from arknights_mower.utils.logic_expression import get_logic_exp
from arknights_mower.utils.plan import RIGHT_SIDE_ROOM_CAPACITY, all_replacements


def trainee_replacement_conflict(name, plan=None):
    """Validate an isolated schedule with the trainee removed from every cover list."""
    from arknights_mower.utils import config
    from arknights_mower.utils.config.plan import PlanModel
    from arknights_mower.utils.operators import Operators, build_global_plan

    if plan is None:
        plan = config.plan
    document = (
        plan.model_dump(exclude_none=True)
        if hasattr(plan, "model_dump")
        else deepcopy(plan)
    )
    tables = [document.get(document.get("default", "plan1"), {})] + [
        backup.get("plan", {}) for backup in document.get("backup_plans", [])
    ]
    for table in tables:
        for room, facility in table.items():
            if not facility:
                continue
            for slot in facility.get("plans", []):
                if room != "train" and slot.get("agent") == name:
                    return f"{name} 是 {room} 的固定主班"
                for binding in (slot, *slot.get("group_bindings", ())):
                    binding["replacement"] = [
                        cover
                        for cover in binding.get("replacement", ())
                        if cover != name
                    ]
    for backup in document.get("backup_plans", []):
        for room, targets in (backup.get("task") or {}).items():
            if room != "train" and name in targets:
                return f"{name} 已配置在副表的 {room} 换人任务中"
    try:
        model = PlanModel(**document)
        data = Operators(
            build_global_plan(plan_model=model), facility_levels=model.facility_levels
        )
        result = data.validate_backup_plans(max_seconds=2, check_owned=False)
    except (ValueError, TypeError, KeyError) as error:
        return f"移除替班后的排班校验失败：{error}"
    if result["success"]:
        return None
    detail = result.get("reason", result["message"])
    return f"移除替班后的排班校验未通过：{detail}"


def trainee_runtime_conflict(solver, name):
    """Keep occupied or reserved trainees available to their unfinished staffing."""
    operators = getattr(getattr(solver, "op_data", None), "operators", None)
    if isinstance(operators, dict) and (operator := operators.get(name)):
        room = operator.current_room
        if room and room != "train":
            slots = solver.op_data.plan.get(room, ())
            resting = room.startswith("dorm") and (
                operator.current_index >= len(slots)
                or operator.current_index < 0
                or slots[operator.current_index].agent == "Free"
            )
            if not resting:
                return f"{name} 仍在 {room} 顶班，专精计划保持待执行"
    for task in (
        *getattr(solver, "tasks", ()),
        *getattr(solver, "waiting_group_shifts", ()),
    ):
        if any(
            name in names for room, names in task.plan.items() if room != "train"
        ) or any(
            occupant == name and position[0] != "train"
            for position, occupant in getattr(task, "group_shift_expected", {}).items()
        ):
            return f"{name} 已有排班换人预约，专精计划保持待执行"
    return None


def slot_names(slot):
    return {
        slot.get("agent", ""),
        *all_replacements(slot.get("replacement", ()), slot.get("group_bindings", ())),
    }


def assistant_conflicts(plan, names):
    """Unknown conditions retain all possible reservations; never read live state."""
    backups = [
        SimpleNamespace(
            trigger=get_logic_exp(deepcopy(backup["trigger"]))
            if "trigger" in backup
            else None,
            group_ids=backup.get("group_ids", [backup.get("group_id", "default")]),
            backup_type=backup.get("type", "global"),
        )
        for backup in plan.get("backup_plans", [])
    ]
    base = plan.get(plan.get("default", "plan1"), {})
    tables = [base, *(b.get("plan", {}) for b in plan.get("backup_plans", []))]
    # Index each physical slot once, including right-side facilities absent from the main plan.
    slots = {}
    for table_index, table in enumerate(tables):
        for room, facility in table.items():
            if room == "train" or not facility:
                continue
            for index, slot in enumerate(facility.get("plans", [])):
                if table_index and slot.get("agent") == "Current":
                    continue
                if (
                    table_index
                    and room not in RIGHT_SIDE_ROOM_CAPACITY
                    and (
                        room not in base
                        or index >= len((base[room] or {}).get("plans", []))
                    )
                ):
                    return names
                slots.setdefault((room, index), []).append(
                    (table_index, slot_names(slot))
                )

    # Each name only needs the slots it can occupy in at least one table.
    slots_by_name = {}
    for (room, _), versions in slots.items():
        latest_first = tuple(reversed(versions))
        for name in set().union(*(occupants for _, occupants in versions)):
            if name in names:
                slots_by_name.setdefault(name, []).append((room, latest_first))

    def can_reserve(name, versions, states):
        for state in states:
            for table_index, occupants in versions:
                if table_index == 0 or state[table_index - 1]:
                    if name in occupants:
                        return True
                    break
        return False

    referenced = set()
    sources = [str(backup.trigger) for backup in backups] + [
        str(get_logic_exp(deepcopy(group.get("trigger", {}))))
        for group in plan.get("backup_groups", ())
    ]
    for source in sources:
        try:
            tree = ast.parse(source, mode="eval")
        except (SyntaxError, ValueError, RecursionError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "current_room"
                and isinstance(node.value, ast.Subscript)
                and isinstance(node.value.slice, ast.Constant)
                and isinstance(node.value.slice.value, str)
            ):
                referenced.add(node.value.slice.value)

    result = {}
    deadline = monotonic() + 2

    @lru_cache(maxsize=128)
    def possible(name):
        return possible_backup_conditions(
            backups,
            4096,
            groups=plan.get("backup_groups", ()),
            training_support=name,
            deadline=deadline,
        )

    for name, original_rooms in names.items():
        try:
            states = possible(name if name in referenced else "")
        except (BackupValidationLimitExceeded, ValueError, TypeError, KeyError):
            result[name] = original_rooms
            continue
        # No feasible schedule is not evidence that an assistant is available.
        if not states:
            result[name] = original_rooms
            continue
        rooms = set()
        for room, versions in slots_by_name.get(name, ()):
            if room not in rooms and can_reserve(name, versions, states):
                rooms.add(room)
        if rooms:
            result[name] = rooms
    return result
