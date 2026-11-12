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

    @lru_cache(maxsize=256)
    def reserved(flags):
        result = {}
        active = (True, *flags)
        for (room, _), versions in slots.items():
            for index, occupants in reversed(versions):
                if active[index]:
                    for name in occupants:
                        result.setdefault(name, set()).add(room)
                    break
        return result

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
        rooms = set().union(*(reserved(state).get(name, set()) for state in states))
        if rooms:
            result[name] = rooms
    return result
