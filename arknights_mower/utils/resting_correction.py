"""Prefer available replacements before recalling resting operators in correction."""

from datetime import datetime
from functools import cache

from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import TRADE_ORDER_AGENTS

PLACEHOLDERS = {"", "Current", "Free"}


def suppress_completed_dorm_returns(op_data, plan):
    """个人上限周期已完成的离宿者不被纠错或交接重新召回。"""
    for room, row in list(plan.items()):
        if not room.startswith("dorm"):
            continue
        for index, name in enumerate(row):
            if name not in PLACEHOLDERS and op_data.rest_mood_complete(name):
                current = op_data.get_current_operator(room, index)
                if current is None or current.name != name:
                    row[index] = "Current"
        if all(name == "Current" for name in row):
            del plan[room]


def _resting_members(op_data):
    ends = {d.name: d.time for d in op_data.all_dorms() if d.name}
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
        members = [
            op_data.operators[name]
            for name in op_data.groups[group]
            if not op_data.operators[name].room.startswith("dorm")
            and not op_data.operators[name].workaholic
        ]
        if any(
            not op.is_resting()
            and not (
                not op.current_room
                and (
                    op_data._can_standby(op)
                    or op_data.rest_mood_complete(op.name)
                    or op.time_stamp is not None
                    and op.mood >= op.upper_limit
                )
            )
            for op in members
        ):
            # 半组在岗、或成员离岗却没有有效满心情记录，不能当作整组
            # 正常轮休。让原有整组纠错完成回班，而不是逐人保留休息。
            resting.difference_update(op_data.groups[group])
        else:
            resting.update(op.name for op in members)
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


def reconsider_low_mood_replacements(op_data, fix_plan, is_busy):
    """已在岗合法替班真正用尽后，再按排班表顺序寻找下一候补。"""
    now = datetime.now()
    reserved = {
        name
        for names in fix_plan.values()
        for name in names
        if name not in PLACEHOLDERS
    } | set(getattr(op_data, "reserved_product_replacements", ()))
    for room, slots in op_data.plan.items():
        if room.startswith("dorm") or room == "train":
            continue
        actual = op_data.get_current_room(room, True)
        if actual is None:
            continue
        for index, slot in enumerate(slots):
            if index >= len(actual) or _requested(fix_plan, room, index) != "Current":
                continue
            current = actual[index]
            owner = op_data.operators.get(slot.agent)
            replacements = (
                owner.replacement
                if owner is not None and owner.multi_group
                else getattr(slot, "replacement", ())
            )
            if current not in replacements or current in TRADE_ORDER_AGENTS:
                continue
            cover = op_data.operators.get(current)
            if cover is None or not op_data.replacement_exhausted(current, now):
                # 当前替班只要还有可工作心情，就继续使用；后面的候补即使
                # 心情更高，也不能越过排班表里已经配置好的效率顺序。
                continue
            owner = op_data.operators.get(slot.agent)
            if owner is None:
                continue
            for name in op_data.replacement_candidates(owner):
                candidate = op_data.operators.get(name)
                if (
                    candidate is None
                    or name == current
                    or name in reserved
                    or name in TRADE_ORDER_AGENTS
                    or candidate.is_high()
                    and not op_data.is_same_group_dorm_replacement(owner, name)
                    or candidate.current_room
                    and not candidate.is_resting()
                    or candidate.time_stamp is None
                    or not 0 <= candidate.mood <= 24
                    or candidate.rest_in_full
                    and candidate.is_resting()
                    and candidate.current_mood(now) < candidate.upper_limit
                    or op_data.is_dorm_replacement(name)
                    or is_busy(name)
                    or op_data.replacement_exhausted(name, now)
                ):
                    continue
                fix_plan.setdefault(room, ["Current"] * len(slots))[index] = name
                reserved.add(name)
                logger.info("替班%s心情用尽，按顺序使用同岗位候补%s", current, name)
                break


def prefer_resting_replacements(op_data, fix_plan, is_busy):
    """完整轮休组优先维持替班；任一岗位无法替班时整组回班。"""
    if not fix_plan:
        return
    resting = _resting_members(op_data)
    if not resting:
        return
    requested = {room: slots.copy() for room, slots in fix_plan.items()}
    reserved = _reserved_names(op_data, requested, resting)
    is_busy = cache(is_busy)
    current = {room: op_data.get_current_room(room, True) for room in fix_plan}
    recalling_groups = set()
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
            for candidate in op_data.replacement_candidates(op):
                cover = op_data.operators.get(candidate)
                if (
                    cover is None
                    or cover.is_high()
                    and not op_data.is_same_group_dorm_replacement(op, candidate)
                    or candidate in reserved | resting
                    or candidate in TRADE_ORDER_AGENTS
                    or op_data.is_dorm_replacement(candidate)
                    or op_data.replacement_exhausted(candidate)
                    or not _can_move(cover, room, requested, resting)
                    or is_busy(candidate)
                ):
                    continue
                slots[index] = candidate
                reserved.add(candidate)
                break
            else:
                if (not op.group) and op.exhaust_require and op.rest_in_full:
                    # 独立暖机干员继续本轮恢复；正常规划按床位时间重建回班任务。
                    slots[index] = "Current"
                    continue
                if op.group:
                    recalling_groups.add(op.group)
                logger.debug(
                    f"{name}所在组正在休息，{room}暂无可用替班，保留原纠错叫回安排"
                )
    # 回班以组为单位覆盖之前逐槽尝试的替班结果，不能只叫回失败那一人。
    # 宿舍固定成员交给 correct_group_dorms，训练室仍尊重调用方的保护。
    for group in recalling_groups:
        for name in op_data.groups[group]:
            op = op_data.operators[name]
            if op.room.startswith("dorm"):
                continue
            current.setdefault(op.room, op_data.get_current_room(op.room, True))
            fix_plan.setdefault(op.room, ["Current"] * len(op_data.plan[op.room]))[
                op.index
            ] = name
    for room, slots in list(fix_plan.items()):
        for index, name in enumerate(slots):
            if name not in PLACEHOLDERS and name == current[room][index]:
                slots[index] = "Current"
        if all(name == "Current" for name in slots):
            del fix_plan[room]


def correct_group_dorms(op_data, fix_plan, is_busy, *, positions=None):
    """按工作成员的轮休状态安排宿舍岗位；切表时可限定到发生变化的位置。"""
    for group, names in op_data.groups.items():
        residents = [
            op_data.operators[n]
            for n in names
            if op_data.operators[n].room.startswith("dorm")
            and (
                positions is None
                or (op_data.operators[n].room, op_data.operators[n].index) in positions
            )
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
                if op_data.is_auto_free_dorm_operator(op):
                    # 该位置已经转为普通动态床位；保留现有休息者，空床则
                    # 明确留空，绝不把替班名单中的同组姓名固定塞进来。
                    desired = (
                        actual.name
                        if actual is not None and actual.name != op.name
                        else "Free"
                    )
                    changes[op.room, op.index] = desired
                    continue
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
                            and (
                                not op_data.operators[name].is_high()
                                or op_data.is_same_group_dorm_replacement(op, name)
                            )
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
                    desired = "Current" if op.is_working() else op.name
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


def preserve_backup_replacements(
    op_data,
    plan,
    positions,
    previous_dorms,
    is_busy,
    reserved_names=(),
    reserved_slots=(),
):
    """切产物或替班优先保留主班状态；替班不足时召回可用主班。"""
    from arknights_mower.utils.exhaust_replacement import match_replacements

    positions = {
        position for position in positions if _requested(plan, *position) == "Current"
    }
    owners = {
        op_data.plan[room][index].agent: (room, index)
        for room, index in sorted(positions)
    }
    reserved = set(reserved_names) | set(op_data.reserved_product_replacements)
    assigned = {
        name for row in plan.values() for name in row if name not in PLACEHOLDERS
    }
    reserved.update(assigned)
    reserved_slots = set(reserved_slots) | set(op_data.reserved_product_beds)
    beds = {bed.position: bed.name for bed in previous_dorms if bed.name}
    options, changes = {}, {}
    # 明确被本轮安排替换的原岗位也释放其替班，允许跨设施迁移。
    movable = {
        (room, index)
        for room, row in plan.items()
        for index, name in enumerate(row)
        if name != "Current"
        and (room, index) not in reserved_slots
        and (actual := op_data.get_current_operator(room, index)) is not None
        and actual.name != name
    }
    for name, position in owners.items():
        owner = op_data.operators[name]
        actual = op_data.get_current_operator(*position)
        if actual is not None and actual.name == name:
            continue
        if op_data.is_auto_free_dorm_operator(owner):
            # 开放床位时保留已有入住者；不以 Free 清走休息中的干员。
            if actual is None:
                if position in reserved_slots:
                    return False
                changes[position] = "Free"
            continue
        if position in reserved_slots:
            if actual is not None and actual.name in owner.replacement:
                reserved.add(actual.name)
                continue
            return False
        options[name] = []
        movable.add(position)

    for name in options:
        owner = op_data.operators[name]
        position = owners[name]
        actual = op_data.get_current_operator(*position)
        candidates = op_data.replacement_candidates(owner)
        if actual is not None and actual.name in candidates:
            candidates.remove(actual.name)
            candidates.insert(0, actual.name)
        for candidate in candidates:
            cover = op_data.operators.get(candidate)
            if cover is None:
                continue
            source = (cover.current_room, cover.current_index)
            if source == position and candidate not in assigned:
                options[name].append(candidate)
                continue
            if (
                candidate in reserved | set(owners) | set(TRADE_ORDER_AGENTS)
                or is_busy(candidate)
                or cover.is_high()
                and (
                    not op_data.is_same_group_dorm_replacement(owner, candidate)
                    or source == (cover.room, cover.index)
                )
                or not owner.room.startswith("dorm")
                and op_data.replacement_exhausted(candidate)
                or cover.rest_in_full
                and cover.is_resting()
                and cover.current_mood() < cover.upper_limit
            ):
                continue
            if source not in movable and (
                op_data.is_dorm_replacement(candidate)
                or cover.current_room
                and not cover.is_resting()
            ):
                continue
            # 原动态床或固定恢复位被占用时，不能以切替班的名义挤走住客。
            if position in beds and beds[position] != candidate:
                continue
            options[name].append(candidate)
    # 先最大匹配可用替班，再以主班补足缺口，避免过早召回仍有替班的人。
    preferred = {
        candidate for candidates in options.values() for candidate in candidates
    }
    for name, candidates in options.items():
        owner = op_data.operators[name]
        position = owners[name]
        source = (owner.current_room, owner.current_index)
        if (
            name not in reserved
            and not (owner.multi_group and op_data.resting_binding_groups(owner))
            and not is_busy(name)
            and source not in reserved_slots
            and (not owner.current_room or owner.is_resting())
            and position not in beds
        ):
            candidates.append(name)
    matching = match_replacements(options, preferred=preferred)
    if matching is None:
        logger.debug("副表替班与主班均不可用，暂缓切表：%s", options)
        return False
    changes.update({owners[name]: candidate for name, candidate in matching.items()})
    for (room, index), candidate in changes.items():
        actual = op_data.get_current_operator(room, index)
        if actual is not None and actual.name == candidate:
            continue
        plan.setdefault(room, ["Current"] * len(op_data.plan[room]))[index] = candidate
    return True
