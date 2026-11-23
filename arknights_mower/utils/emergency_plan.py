"""独立救急排班的副表求值与设施校验。"""

import copy

from arknights_mower.data import agent_list
from arknights_mower.utils.plan import all_replacements

RESCUE_ROOMS = {
    "central": 5,
    "meeting": 2,
    "contact": 1,
    "factory": 1,
    "train": 2,
    "recycle": 2,
} | {f"room_{floor}_{index}": 3 for floor in range(1, 4) for index in range(1, 4)}

RESCUE_DORMS = {f"dormitory_{index}" for index in range(1, 5)}
INHERITED_WORK_ROOMS = RESCUE_ROOMS.keys() - {"factory", "train"}


def _explicit_workers(plan):
    return any(
        slot.agent in agent_list
        for room, facility in plan
        if room in INHERITED_WORK_ROOMS and facility is not None
        for slot in facility.plans
    )


def _normal_facility(data, room):
    rows = data.plan.get(room, ())
    global_plan = getattr(data, "global_plan", {})
    original = global_plan.get(global_plan.get("default", "plan1"), {}).get(room, {})
    facility = (
        rows[0].facility
        if rows and hasattr(rows[0], "facility")
        else original.get("name", "")
    )
    product = getattr(data, "products", {}).get(room)
    if product is None and rows:
        product = getattr(rows[0], "product", None)
    result = {
        "name": facility,
        "plans": [
            {
                "agent": getattr(slot, "agent", ""),
                "group": getattr(slot, "group", ""),
                "replacement": copy.deepcopy(getattr(slot, "replacement", [])),
                "group_bindings": copy.deepcopy(getattr(slot, "group_bindings", [])),
            }
            for slot in rows
        ],
    }
    if isinstance(product, str) and product:
        result["product"] = product
    return result


def compile_rescue_schedule(data, schedule):
    """普通工作空缺继承正常生效岗位；专项、宿舍和副表 Current 保留原义。"""
    from arknights_mower.utils.config.plan import PlanModel

    document = schedule.model_dump(exclude_none=True)
    document["facility_levels"] = {
        **getattr(data, "facility_levels", {}),
        **schedule.facility_levels,
    }

    def inherit(room, facility, *, backup=False):
        normal = _normal_facility(data, room)
        supplied = facility.get("plans", [])
        capacity = len(normal["plans"])
        if len(supplied) > capacity:
            raise ValueError(
                f"救急排班 {room} 等级/岗位数不一致，岗位数量超过正常排班容量："
                f"正常排班 {capacity} 位，救急排班 {len(supplied)} 位"
            )
        rows = [
            copy.deepcopy(supplied[index])
            if index < len(supplied) and supplied[index]["agent"]
            else copy.deepcopy(normal["plans"][index])
            for index in range(len(supplied) if backup else capacity)
        ]
        if backup:
            return {**facility, "plans": rows}
        return {
            **normal,
            **facility,
            "name": facility.get("name") or normal["name"],
            "product": facility.get("product") or normal.get("product"),
            "plans": rows,
        }

    primary = document["plan1"]
    for room in INHERITED_WORK_ROOMS & data.plan.keys():
        primary[room] = inherit(room, primary.get(room, {}))
    for backup in document["backup_plans"]:
        for room, facility in backup["plan"].items():
            if room in INHERITED_WORK_ROOMS & data.plan.keys() and facility["plans"]:
                backup["plan"][room] = inherit(room, facility, backup=True)
    return PlanModel.model_validate(document)


def validate_rescue_roster(plan):
    """允许未配置的空表；已填写的位置必须为不重复的实际干员。"""
    seen = set()
    for room, names in plan.items():
        if room not in RESCUE_ROOMS:
            raise ValueError(f"救急主表不支持设施 {room}")
        if not names or len(names) > RESCUE_ROOMS[room]:
            raise ValueError(f"救急主表 {room} 岗位数量不正确")
        for name in names:
            if name == "" and room in ("factory", "train"):
                continue
            if name == "菲亚梅塔":
                raise ValueError("救急排班的菲亚梅塔需要安排在宿舍")
            if name not in agent_list:
                raise ValueError(f"救急主表 {room} 的干员 {name or '（空）'} 无效")
            if name in seen:
                raise ValueError(f"救急主表重复安排干员：{name}")
            seen.add(name)
    return plan


def rescue_plan_for(data, plan):
    """检查普通设施完整性及已配置岗位容量。"""
    validate_rescue_roster(plan)
    rooms = {room for room, row in data.plan.items() if room in RESCUE_ROOMS and row}
    rooms -= {"factory", "train"}
    configured = set(plan) - {"factory", "train"}
    if not rooms or configured != rooms:
        missing = sorted(rooms - configured)
        extra = sorted(configured - rooms)
        raise ValueError(f"救急排班与当前设施不一致：缺少 {missing}，多余 {extra}")
    for room, names in plan.items():
        if room in ("factory", "train"):
            continue
        if len(names) != len(data.plan[room]):
            raise ValueError(
                f"救急排班 {room} 等级/岗位数不一致：正常排班 {len(data.plan[room])} 位，"
                f"救急排班 {len(names)} 位"
            )
    return {room: list(names) for room, names in plan.items()}


def validate_rescue_schedule(data, schedule):
    """静态校验救急主副表自身；条件生效后的设施对照交给初始化。"""
    from arknights_mower.utils.backup_group_tasks import validate_group_task_names
    from arknights_mower.utils.operators import (
        TRADE_ORDER_AGENTS,
        build_global_plan,
        select_run_order_agents,
    )

    source = schedule
    schedule = compile_rescue_schedule(data, schedule)
    validate_group_task_names(build_global_plan(plan_model=schedule))

    primary = schedule.plan1.model_dump(exclude_none=True)
    roster = {
        room: [slot["agent"] for slot in facility["plans"]]
        for room, facility in primary.items()
        if room in RESCUE_ROOMS and facility["plans"]
    }
    validate_rescue_roster(roster)
    available = set(roster) | {
        room
        for entry in schedule.backup_plans
        for room, facility in entry.plan.model_dump(exclude_none=True).items()
        if any(slot["agent"] for slot in facility["plans"])
    }
    required = {
        room
        for room, row in data.plan.items()
        if row and room in RESCUE_ROOMS and room not in {"factory", "train"}
    }
    if missing := sorted(required - available):
        raise ValueError(f"救急排班缺少必填工作设施：{missing}")
    for label, plan, backup in [
        ("主表", schedule.plan1, False),
        *((f"副表 {entry.name}", entry.plan, True) for entry in schedule.backup_plans),
    ]:
        seen = set()
        for room, facility in plan.model_dump(exclude_none=True).items():
            rows = facility["plans"]
            if not rows:
                continue
            capacity = RESCUE_ROOMS.get(room, 5 if room in RESCUE_DORMS else 0)
            if not capacity or len(rows) > capacity:
                raise ValueError(f"救急{label} {room} 岗位数量不正确")
            if (
                not backup
                and room.startswith("room_")
                and facility.get("name", "") in ("", "贸易站")
            ):
                select_run_order_agents(
                    room,
                    (
                        all_replacements(
                            slot.get("replacement", ()), slot.get("group_bindings", ())
                        )
                        for slot in rows
                    ),
                )
            for index, slot in enumerate(rows):
                name = slot["agent"]
                if name == "Current" and backup:
                    continue
                if name == "" and (
                    room in ("factory", "train") or room in RESCUE_DORMS
                ):
                    continue
                if name == "Free" and room in RESCUE_DORMS:
                    if slot.get("group") or slot.get("group_bindings"):
                        raise ValueError(f"救急{label} {room} Free 不能参与绑组")
                    continue
                if name not in agent_list:
                    raise ValueError(
                        f"救急{label} {room} 的干员 {name or '（空）'} 无效"
                    )
                if name in seen:
                    raise ValueError(f"救急{label}重复安排干员：{name}")
                seen.add(name)
                if name == "菲亚梅塔" and (room not in RESCUE_DORMS or index == 1):
                    raise ValueError(
                        f"救急{label}的菲亚梅塔需安排在宿舍且不能在 2 号位"
                    )
                if name == "菲亚梅塔" and (
                    slot.get("group") or slot.get("group_bindings")
                ):
                    raise ValueError(f"救急{label}的菲亚梅塔不能参与绑组")
                bindings = [
                    {
                        "group": slot.get("group", ""),
                        "replacement": slot.get("replacement", []),
                    },
                    *slot.get("group_bindings", []),
                ]
                if slot.get("group_bindings"):
                    groups = [binding["group"].strip() for binding in bindings]
                    if len(groups) != len(set(groups)):
                        raise ValueError(
                            f"救急{label} {name}的多绑组名称不能重复，空绑组最多填写一次"
                        )
                for binding in bindings:
                    replacements = binding["replacement"]
                    if sum(n in TRADE_ORDER_AGENTS for n in replacements) > 1:
                        raise ValueError(
                            f"救急{label} {name}的替换名单不能含多个跑单干员"
                        )
                    for replacement in replacements:
                        if (
                            replacement == "Free"
                            and room in RESCUE_DORMS
                            and binding["group"]
                        ):
                            continue
                        if replacement not in agent_list or replacement == "菲亚梅塔":
                            raise ValueError(
                                f"救急{label} {name}的替换干员 {replacement} 无效"
                            )
    if not any(
        _explicit_workers(plan)
        for plan in [source.plan1, *(backup.plan for backup in source.backup_plans)]
    ):
        raise ValueError(
            "救急排班没有显式配置工作干员，全部沿用正常排班，尚无有效救急配置"
        )
    if source.facility_levels and hasattr(data, "global_plan"):
        from arknights_mower.utils.calculated_mood import _facility_levels

        levels = _facility_levels(data)
        for room, level in source.facility_levels.items():
            if level != levels.get(room):
                raise ValueError(
                    f"救急排班 {room} 设施等级不一致："
                    f"正常排班 {levels.get(room)} 级，救急排班 {level} 级"
                )
    return schedule


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
    from arknights_mower.utils.plan import PlanConfig

    def recovery_config(conf):
        return PlanConfig(
            "",
            "",
            "",
            workaholic=conf.workaholic,
            free_blacklist=conf.free_blacklist,
            dorm_order=conf.dorm_order,
            dorm_order_override=getattr(
                conf, "dorm_order_override", bool(conf.dorm_order)
            ),
        )

    source = schedule
    schedule = validate_rescue_schedule(data, schedule)
    worker_config = recovery_config(schedule.conf)
    facilities = schedule.plan1.model_dump(exclude_none=True)
    from types import SimpleNamespace

    from arknights_mower.utils.backup_groups import select_backup_plans

    backups = [
        SimpleNamespace(
            group_ids=backup.group_ids,
            backup_type=backup.type,
            trigger=get_logic_exp(backup.trigger.model_dump()),
        )
        for backup in schedule.backup_plans
    ]
    groups = [
        {"id": group.id, "trigger": get_logic_exp(group.trigger.model_dump())}
        for group in schedule.backup_groups
    ]
    selection = select_backup_plans(
        backups, groups, lambda trigger: bool(data.evaluate_expression(str(trigger)))
    )
    if not _explicit_workers(source.plan1) and not any(
        active and _explicit_workers(backup.plan)
        for backup, active in zip(source.backup_plans, selection.conditions)
    ):
        raise ValueError("当前没有生效的救急工作干员，全部沿用正常排班")
    for backup, active in zip(schedule.backup_plans, selection.conditions):
        definition = backup.model_dump(exclude_none=True)
        if not active:
            continue
        worker_config = worker_config.merge_config(recovery_config(backup.conf))
        for room, facility in definition["plan"].items():
            if room not in RESCUE_ROOMS.keys() | RESCUE_DORMS:
                continue
            previous_facility = facilities.get(room, {})
            previous = previous_facility.get("plans", [])
            rows = []
            for index, slot in enumerate(facility["plans"]):
                if slot["agent"] == "Current":
                    if index >= len(previous):
                        raise ValueError(
                            f"救急副表 {backup.name} 的 {room} 没有可保留岗位"
                        )
                    slot = previous[index]
                rows.append(slot)
            if rows:
                rows.extend(copy.deepcopy(previous[len(rows) :]))
            facilities[room] = {
                **previous_facility,
                **facility,
                "plans": rows or previous,
            }
            if not facility.get("name"):
                facilities[room]["name"] = previous_facility.get("name", "")
    roster = {
        room: [slot["agent"] for slot in facility["plans"]]
        for room, facility in facilities.items()
        if room in RESCUE_ROOMS and facility["plans"]
    }
    work = rescue_plan_for(data, roster)
    for room in work:
        if not room.startswith("room_"):
            continue
        normal_type = getattr(data.plan[room][0], "facility", "")
        rescue_type = facilities[room].get("name", "")
        if rescue_type != normal_type:
            raise ValueError(
                f"救急排班 {room} 设施类型不一致：正常排班 {normal_type or '未填写'}，"
                f"救急排班 {rescue_type or '未填写'}"
            )
        if normal_type in ("制造站", "贸易站"):
            normal_product = (
                getattr(data, "products", {}).get(room)
                or getattr(data.plan[room][0], "product", None)
                or None
            )
            rescue_product = facilities[room].get("product") or None
            if rescue_product != normal_product:
                from arknights_mower.utils.manufacture_product import (
                    MANUFACTURE_PRODUCTS,
                    TRADE_PRODUCTS,
                )

                labels = {
                    key: value.name for key, value in MANUFACTURE_PRODUCTS.items()
                }
                labels.update(
                    {key: value.strategy_name for key, value in TRADE_PRODUCTS.items()}
                )
                raise ValueError(
                    f"救急排班 {room} 产物不一致：正常排班 {labels.get(normal_product, normal_product or '未填写')}，"
                    f"救急排班 {labels.get(rescue_product, rescue_product or '未填写')}"
                )
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
    from arknights_mower.utils.operators import (
        TRADE_ORDER_AGENTS,
        select_run_order_agents,
    )

    run_orders = {
        room: [
            [
                name
                for name in all_replacements(
                    slot.get("replacement", ()), slot.get("group_bindings", ())
                )
                if name in TRADE_ORDER_AGENTS
            ]
            for slot in facilities[room]["plans"]
        ]
        for room in work
    }
    for room, choices in run_orders.items():
        if room.startswith("room_") and facilities[room].get("name", "") in (
            "",
            "贸易站",
        ):
            select_run_order_agents(room, choices)
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
        "worker_config": {
            key: ",".join(getattr(worker_config, key))
            for key in ("workaholic", "free_blacklist", "dorm_order")
        },
        "worker_groups": {
            room: [slot.get("group", "") for slot in facilities[room]["plans"]]
            for room in work
        },
        "worker_replacements": {
            room: [
                [
                    name
                    for name in slot.get("replacement", [])
                    if name not in TRADE_ORDER_AGENTS
                ]
                for slot in facilities[room]["plans"]
            ]
            for room in work
        },
        "dorm_layout": managers,
        "run_order_replacements": run_orders,
        "fia_targets": fia_targets,
    }
