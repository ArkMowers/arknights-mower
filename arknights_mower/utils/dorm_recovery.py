"""为首个 Free 位建立单回入驻顺序，不改变最终床位分配。"""


def recovery_target(op_data, room, agents):
    slots = op_data.plan.get(room, [])
    if not room.startswith("dorm") or len(agents) != len(slots):
        return None
    index = next((i for i, slot in enumerate(slots) if slot.agent == "Free"), None)
    if index is None:
        return None
    target = op_data.operators.get(agents[index])
    if target is None or target.mood >= 24 or target.room.startswith("dorm"):
        return None
    return target


def recovery_order_plan(op_data, room, agents):
    """返回一次确认用的紧凑名单；完整恢复名单仍由原任务持有。

    所有其他 Free 位暂时撤下，未满心情（或心情未知）的绑组宿舍替班
    也暂时撤下。空位不能用 Free 表达，否则选人阶段会立即填人。
    """
    target = recovery_target(op_data, room, agents)
    if target is None:
        return None
    if (
        getattr(target, "dorm_recovery_room", "") == room
        and target.current_room == room
    ):
        return None
    retained = []
    for index, name in enumerate(agents):
        if name == target.name:
            retained.append(name)
            continue
        slot = op_data.plan[room][index]
        if slot.agent == "Free":
            continue
        op = op_data.operators.get(name)
        if op_data.is_dorm_replacement_for_slot(name, room, index) and (
            op is None or op.time_stamp is None or op.mood < 24
        ):
            continue
        if name in ("", "Free", "Current"):
            # 未解析的固定位置不能据此清房。
            return None
        retained.append(name)
    return retained
