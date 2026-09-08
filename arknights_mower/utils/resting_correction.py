"""Prefer available replacements before recalling resting operators in correction."""

from datetime import datetime
from functools import cache

from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS

PLACEHOLDERS = {"", "Current", "Free"}


def _resting_members(op_data):
    ends = {d.name: d.time for d in op_data.dorm if d.name}
    resting, groups = set(), set()
    now = datetime.now()
    for name, op in op_data.operators.items():
        if (
            not op.is_high()
            or op.workaholic
            or op.room.startswith("dorm")
            or not op.is_resting()
        ):
            continue
        end = ends.get(name)
        unfinished = end > now if end is not None else 0 <= op.mood < op.upper_limit
        if unfinished:
            resting.add(name)
            if op.group:
                groups.add(op.group)
    for group in groups:
        resting.update(
            name
            for name in op_data.groups[group]
            if not op_data.operators[name].workaholic
        )
    return resting


def _requested(plan, room, index):
    slots = plan.get(room, [])
    return slots[index] if 0 <= index < len(slots) else "Current"


def _reserved_names(op_data, plan, resting):
    reserved = {
        name
        for slots in plan.values()
        for name in slots
        if name not in PLACEHOLDERS and name not in resting
    }
    for name, op in op_data.operators.items():
        if not op.current_room or op.is_resting():
            continue
        requested = _requested(plan, op.current_room, op.current_index)
        # Preserve occupants of unchanged slots, including an already valid cover.
        cover = (
            requested in resting and name in op_data.operators[requested].replacement
        )
        if requested in ("Current", name) or cover:
            reserved.add(name)
    return reserved


def _can_move(op, room, plan, resting):
    if not op.current_room or op.is_resting() or op.current_room == room:
        return True
    replacement = _requested(plan, op.current_room, op.current_index)
    # A replacement in another workplace is available only when this correction
    # explicitly vacates its slot. Never take it from an unrelated working group.
    return replacement not in PLACEHOLDERS | resting | {op.name}


def prefer_resting_replacements(op_data, fix_plan, is_busy):
    """Try replacements; otherwise retain the original correction's recall."""
    if not fix_plan:
        return
    resting = _resting_members(op_data)
    if not resting:
        return
    requested = {room: slots.copy() for room, slots in fix_plan.items()}
    reserved = _reserved_names(op_data, requested, resting)
    is_busy = cache(is_busy)
    current = {room: op_data.get_current_room(room, True) for room in fix_plan}
    for room, slots in fix_plan.items():
        if room.startswith("dorm"):
            continue
        for index, name in enumerate(slots):
            if name not in resting:
                continue
            op = op_data.operators[name]
            if (room, index) != (op.room, op.index):
                continue
            actual = current[room][index]
            if actual == name or (
                actual in op.replacement and actual not in TRADE_ORDER_AGENTS
            ):
                slots[index] = "Current"
                continue
            for candidate in op.replacement:
                cover = op_data.operators.get(candidate)
                if (
                    cover is None
                    or cover.is_high()
                    or candidate in reserved | resting
                    or candidate in TRADE_ORDER_AGENTS
                    or not _can_move(cover, room, requested, resting)
                    or is_busy(candidate)
                ):
                    continue
                slots[index] = candidate
                reserved.add(candidate)
                break
            else:
                logger.debug(
                    f"{name}所在组正在休息，{room}暂无可用替班，保留原纠错叫回安排"
                )
    for room, slots in list(fix_plan.items()):
        for index, name in enumerate(slots):
            if name not in PLACEHOLDERS and name == current[room][index]:
                slots[index] = "Current"
        if all(name == "Current" for name in slots):
            del fix_plan[room]
