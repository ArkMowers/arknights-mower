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
                    or op_data.is_dorm_replacement(candidate)
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


def correct_group_dorms(op_data, fix_plan, is_busy):
    """按非宿舍成员的轮休状态恢复宿舍原位，兼容重启和部分执行失败。"""
    for group, names in op_data.groups.items():
        residents = [
            op_data.operators[n]
            for n in names
            if op_data.operators[n].room.startswith("dorm")
        ]
        if not residents:
            continue
        # 纠错已经决定叫回工作成员时，宿舍成员也必须回班。
        recalling = any(
            not op_data.operators[n].room.startswith("dorm")
            and not op_data.operators[n].workaholic
            and _requested(
                fix_plan, op_data.operators[n].room, op_data.operators[n].index
            )
            == n
            for n in names
        )
        resting = op_data.group_is_resting(group) and not recalling
        changes = {}
        for op in residents:
            desired = op.name
            if resting:
                actual = op_data.get_current_operator(op.room, op.index)
                candidates = op_data.replacement_candidates(op)
                if actual and actual.name in candidates:
                    candidates.remove(actual.name)
                    candidates.insert(0, actual.name)
                reserved = {
                    name
                    for room, slots in fix_plan.items()
                    for index, name in enumerate(slots)
                    if (room, index) != (op.room, op.index)
                } | set(changes.values())
                desired = next(
                    (
                        name
                        for name in candidates
                        if (
                            name not in TRADE_ORDER_AGENTS
                            and name not in reserved
                            and not is_busy(name)
                            and not op_data.operators[name].is_high()
                            and (
                                actual is not None
                                and actual.name == name
                                or not op_data.is_dorm_replacement(name)
                                and (
                                    not op_data.operators[name].current_room
                                    or op_data.operators[name].is_resting()
                                )
                            )
                        )
                    ),
                    None,
                )
                if desired is None:
                    # 部分执行失败后没有可用替班，先保留原宿舍干员；
                    # 不抢占其他岗位，也不绕过训练室保护把整组叫回。
                    logger.debug(f"{op.name}宿舍替班暂不可用，保留本人并等待后续纠错")
                    desired = op.name
            changes[op.room, op.index] = desired
        for (room, index), name in changes.items():
            current = op_data.get_current_operator(room, index)
            if room not in fix_plan:
                if current and current.name == name:
                    continue
                fix_plan[room] = ["Current"] * len(op_data.plan[room])
            fix_plan[room][index] = (
                "Current" if current and current.name == name else name
            )
    for room, slots in list(fix_plan.items()):
        if all(name == "Current" for name in slots):
            del fix_plan[room]
