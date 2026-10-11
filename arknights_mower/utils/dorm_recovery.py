"""在目标最终床位建立单回入驻顺序。"""

from arknights_mower.utils import dorm_skills
from arknights_mower.utils.dorm_candidates import (
    dorm_candidates,
    full_dorm_candidate,
)


class DormRecoveryPaddingUnavailable(Exception):
    """选人页没有足够的满心情空闲垫位者，继续正常阵容。"""


def active_recovery_position(op):
    """旧缓存没有床位记录，或实际换过位置，都不能沿用原单回标记。"""
    room = getattr(op, "dorm_recovery_room", "")
    index = getattr(op, "dorm_recovery_index", -1)
    if room and index >= 0 and (op.current_room, op.current_index) == (room, index):
        return room, index
    return None


def recovery_managers(op_data, room, agents):
    """只记录完整入住名单中位置最靠前的单回宿管。"""
    slots = op_data.plan.get(room, [])
    if len(agents) != len(slots):
        return ()
    for index, name in enumerate(agents):
        op = op_data.operators.get(name)
        if op is None:
            continue
        op.single_recovery_manager = dorm_skills.is_single_recovery_manager(name)
        if op.single_recovery_manager:
            return ((name, index, getattr(op, "dorm_position_version", 0)),)
    return ()


def recovery_target(
    op_data, room, agents, manager_names=None, *, group_transitions=None
):
    slots = op_data.plan.get(room, [])
    if not room.startswith("dorm") or len(agents) != len(slots):
        return None
    if manager_names is None:
        manager_names = {
            name for name, _, _ in recovery_managers(op_data, room, agents)
        }
    index = next(
        (
            i
            for i, name in enumerate(agents)
            if name not in manager_names
            and (
                op_data.is_dynamic_dorm_position(
                    room, i, name, group_transitions=group_transitions
                )
                or (bed := op_data.get_group_dorm(room, i)) is not None
                and op_data.is_recovery_dorm(
                    bed, name, group_transitions=group_transitions
                )
            )
        ),
        None,
    )
    if index is None:
        return None
    target = op_data.operators.get(agents[index])
    if target is None or target.mood >= 24 or target.room.startswith("dorm"):
        return None
    return target


def recovery_order_plan(
    op_data, room, agents, reserved_names=(), *, group_transitions=None
):
    """建立单回时就占住最终床位，补回其他人后目标仍在原位。

    保留单回宿管、菲亚梅塔及所有已确认满心情的入住者；
    其他前置位置使用无单回技能的满心情空闲者垫位，
    不能留空让游戏压缩名单。没有足够合格垫位者时不执行这次单回确认。
    """
    managers = recovery_managers(op_data, room, agents)
    if not managers:
        return None
    manager_names = {name for name, _, _ in managers}
    target = recovery_target(
        op_data, room, agents, manager_names, group_transitions=group_transitions
    )
    if target is None:
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
    for index, name in enumerate(agents):
        if (
            name in (target.name, "菲亚梅塔")
            or name in manager_names
            or index < target_index
            and dorm_skills.is_single_recovery_manager(name)
        ):
            retained.append(name)
            continue
        if full_dorm_candidate(op_data, name):
            retained.append(name)
            continue
        if (
            index < target_index
            or op_data.is_dynamic_dorm_position(
                room, index, name, group_transitions=group_transitions
            )
            or op_data.is_dorm_replacement_for_slot(
                name, room, index, group_transitions=group_transitions
            )
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
        current = op_data.get_current_room(room, True)
        candidates = dorm_candidates(
            op_data,
            set(agents) | set(reserved_names),
            current_residents=current,
        )
        for index, name in enumerate(retained):
            if not name:
                # 重试保留原位垫位者；新垫位在选人页按心情降序实际选择。
                previous = current[index]
                retained[index] = (
                    previous
                    if (target.current_room, target.current_index)
                    == (room, target_index)
                    and previous in candidates.filling
                    and full_dorm_candidate(op_data, previous)
                    and not dorm_skills.is_single_recovery_manager(previous)
                    else "Free"
                )
    return retained


def compact_dorm_vacancies(data, plan):
    """显式空床放到末尾；菲亚位置之前的空缺交由普通补位填充。"""
    for room, row in plan.items():
        if not room.startswith("dorm") or "" not in row:
            continue
        current = data.get_current_room(room, True)
        resolved = [
            current[index] if name == "Current" else name
            for index, name in enumerate(row)
        ]
        occupants = [name for name in resolved if name]
        if "菲亚梅塔" in resolved:
            fixed = resolved.index("菲亚梅塔")
            missing = fixed - occupants.index("菲亚梅塔")
            occupants[fixed - missing : fixed - missing] = ["Free"] * missing
        compacted = occupants + [""] * (len(row) - len(occupants))
        if compacted != resolved:
            plan[room] = compacted
    return plan
