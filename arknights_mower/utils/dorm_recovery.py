"""为首个 Free 位建立单回入驻顺序，不改变最终床位分配。"""

from arknights_mower.utils.dorm_candidates import dorm_candidates
from arknights_mower.utils.resting_priority import has_resting_mood, resting_mood


def active_recovery_position(op):
    """旧缓存没有床位记录，或实际换过位置，都不能沿用原单回标记。"""
    room = getattr(op, "dorm_recovery_room", "")
    index = getattr(op, "dorm_recovery_index", -1)
    if room and index >= 0 and (op.current_room, op.current_index) == (room, index):
        return room, index
    return None


def recovery_managers(op_data, room, agents):
    """只记录前两位单回宿管的位置及移动版本，移走又归位也须重配。"""
    slots = op_data.plan.get(room, [])
    if len(agents) != len(slots):
        return ()
    op_data.refresh_dorm_manager_flags()
    return tuple(
        (name, index, getattr(op_data.operators.get(name), "dorm_position_version", 0))
        for index, name in enumerate(agents[:2])
        if getattr(op_data.operators.get(name), "single_recovery_manager", False)
    )


def recovery_target(op_data, room, agents):
    slots = op_data.plan.get(room, [])
    if not room.startswith("dorm") or len(agents) != len(slots):
        return None
    index = next(
        (
            i
            for i, name in enumerate(agents)
            if op_data.is_dynamic_dorm_position(room, i, name)
        ),
        None,
    )
    if index is None:
        return None
    target = op_data.operators.get(agents[index])
    if target is None or target.mood >= 24 or target.room.startswith("dorm"):
        return None
    return target


def recovery_order_plan(op_data, room, agents, reserved_names=()):
    """建立单回时就占住最终床位，补回其他人后目标仍在原位。

    保留前两位的单回宿管；其他 Free 位和未满心情（或心情未知）的
    绑组宿舍替班暂时撤下。中间空缺只能用已读到真实 24 心情的空闲者垫位，
    不能留空让游戏压缩名单。没有合适垫位者时不执行这次单回确认。
    """
    target = recovery_target(op_data, room, agents)
    if target is None:
        return None
    managers = recovery_managers(op_data, room, agents)
    if not managers:
        return None
    target_index = agents.index(target.name)
    if (
        active_recovery_position(target) == (room, target_index)
        and getattr(target, "dorm_recovery_fixed", ()) == managers
        and all(
            (
                op_data.operators[name].current_room,
                op_data.operators[name].current_index,
            )
            == (room, index)
            for name, index, _ in managers
        )
    ):
        return None
    retained = []
    manager_names = {name for name, _, _ in managers}
    for index, name in enumerate(agents):
        if name == target.name or name in manager_names:
            retained.append(name)
            continue
        if op_data.is_dynamic_dorm_position(room, index, name):
            retained.append("")
            continue
        op = op_data.operators.get(name)
        if op_data.is_dorm_replacement_for_slot(name, room, index) and (
            op is None or op.time_stamp is None or op.mood < 24
        ):
            retained.append("")
            continue
        if name in ("", "Free", "Current"):
            # 未解析的固定位置不能据此清房。
            return None
        retained.append(name)
    while retained and not retained[-1]:
        retained.pop()
    if "" in retained:
        candidates = dorm_candidates(
            op_data,
            set(agents) | set(reserved_names),
            current_residents=op_data.get_current_room(room, True),
        )
        padding = iter(
            candidate
            for candidate in candidates.full
            if has_resting_mood(op_data.operators[candidate])
            and resting_mood(op_data.operators[candidate]) >= 24
        )
        for index, name in enumerate(retained):
            if not name:
                retained[index] = next(padding, None)
                if retained[index] is None:
                    return None
    return retained
