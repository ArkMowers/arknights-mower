"""独立救急排班的副表求值与设施校验。"""

from arknights_mower.data import agent_list

RESCUE_ROOMS = {"central": 5, "meeting": 2, "contact": 1} | {
    f"room_{floor}_{index}": 3 for floor in range(1, 4) for index in range(1, 4)
}

RESCUE_DORMS = {f"dormitory_{index}" for index in range(1, 5)}


def validate_rescue_roster(plan):
    """允许未配置的空表；已填写的位置必须为不重复的实际干员。"""
    seen = set()
    for room, names in plan.items():
        if room not in RESCUE_ROOMS:
            raise ValueError(f"救急主表不支持设施 {room}")
        if not names or len(names) > RESCUE_ROOMS[room]:
            raise ValueError(f"救急主表 {room} 岗位数量不正确")
        for name in names:
            if name == "菲亚梅塔":
                raise ValueError("救急排班的菲亚梅塔需要安排在宿舍")
            if name not in agent_list:
                raise ValueError(f"救急主表 {room} 的干员 {name or '（空）'} 无效")
            if name in seen:
                raise ValueError(f"救急主表重复安排干员：{name}")
            seen.add(name)
    return plan


def rescue_plan_for(data, plan):
    """检查生效救急排班覆盖当前普通设施及岗位数。"""
    validate_rescue_roster(plan)
    rooms = {room for room, row in data.plan.items() if room in RESCUE_ROOMS and row}
    if not rooms or set(plan) != rooms:
        missing = sorted(rooms - set(plan))
        extra = sorted(set(plan) - rooms)
        raise ValueError(f"救急排班与当前设施不一致：缺少 {missing}，多余 {extra}")
    for room, names in plan.items():
        if len(names) != len(data.plan[room]):
            raise ValueError(f"救急排班 {room} 需要填写 {len(data.plan[room])} 名干员")
    return {room: list(names) for room, names in plan.items()}


def configured_rescue_names(schedule):
    """初始化卡牌读数覆盖主表及各副表的显式驻员。"""
    return {
        slot.agent
        for plan in [schedule.plan1, *(backup.plan for backup in schedule.backup_plans)]
        for room in RESCUE_ROOMS.keys() | RESCUE_DORMS
        if (facility := getattr(plan, room, None)) is not None
        for slot in facility.plans
        if slot.agent not in ("", "Free", "Current")
    }


def effective_rescue_plan(data, schedule):
    """使用共享条件表达式选择救急副表，后面的生效副表覆盖前面的岗位。"""
    from arknights_mower.utils.logic_expression import get_logic_exp

    facilities = schedule.plan1.model_dump(exclude_none=True)
    for backup in schedule.backup_plans:
        definition = backup.model_dump(exclude_none=True)
        if not data.evaluate_expression(str(get_logic_exp(definition["trigger"]))):
            continue
        for room, facility in definition["plan"].items():
            if room not in RESCUE_ROOMS.keys() | RESCUE_DORMS:
                continue
            previous = facilities.get(room, {}).get("plans", [])
            rows = []
            for index, slot in enumerate(facility["plans"]):
                if slot["agent"] == "Current":
                    if index >= len(previous):
                        raise ValueError(
                            f"救急副表 {backup.name} 的 {room} 没有可保留岗位"
                        )
                    slot = previous[index]
                rows.append(slot)
            facilities[room] = {**facility, "plans": rows}
    roster = {
        room: [slot["agent"] for slot in facility["plans"]]
        for room, facility in facilities.items()
        if room in RESCUE_ROOMS and facility["plans"]
    }
    work = rescue_plan_for(data, roster)
    for room in RESCUE_DORMS - data.plan.keys():
        if any(
            slot["agent"] not in ("", "Free")
            for slot in facilities.get(room, {}).get("plans", [])
        ):
            raise ValueError(f"救急排班配置了不存在的宿舍 {room}")
    managers = {}
    seen = {name for row in work.values() for name in row}
    for room, original in data.plan.items():
        if room not in RESCUE_DORMS:
            continue
        configured = facilities.get(room, {}).get("plans", [])
        if len(configured) > len(original):
            raise ValueError(f"救急宿舍 {room} 的岗位数量超过当前宿舍容量")
        row = [slot["agent"] or "Free" for slot in configured]
        row += ["Free"] * (len(original) - len(row))
        for index, name in enumerate(row):
            if name == "Free":
                continue
            if name == "菲亚梅塔" and index == 1:
                raise ValueError("救急宿舍的菲亚梅塔不能安排在 2 号位")
            if name not in agent_list or name in seen:
                raise ValueError(f"救急宿舍 {room} 的干员 {name} 无效或重复")
            seen.add(name)
        managers[room] = row
    from arknights_mower.utils.operators import TRADE_ORDER_AGENTS

    for room in work:
        for slot in facilities[room]["plans"]:
            for name in slot.get("replacement", []):
                if name not in TRADE_ORDER_AGENTS:
                    raise ValueError(f"救急排班 {room} 的跑单人选 {name} 无效")
    run_orders = {
        room: [
            [name for name in slot.get("replacement", []) if name in TRADE_ORDER_AGENTS]
            for slot in facilities[room]["plans"]
        ]
        for room in work
    }
    fia_targets = [
        name
        for room, row in managers.items()
        for index, agent in enumerate(row)
        if agent == "菲亚梅塔"
        for name in facilities[room]["plans"][index].get("replacement", [])
    ]
    for name in fia_targets:
        if name not in agent_list or name == "菲亚梅塔":
            raise ValueError(f"救急排班的菲亚梅塔充能对象 {name} 无效")
    return {
        "rescue_plan": work,
        "dorm_layout": managers,
        "run_order_replacements": run_orders,
        "fia_targets": fia_targets,
    }
