"""只读生成任务名称和设施安排；展示说明不参与调度。"""

import re

from arknights_mower.utils.scheduler_task import TaskTypes

_FACILITIES = {"trade": "贸易站", "manufacture": "制造站", "power": "发电站"}
_FIXED_ROOMS = {
    "central": "控制中枢",
    "meeting": "会客室",
    "factory": "加工站",
    "contact": "办公室",
    "train": "训练室",
    "recycle": "回收站",
}
_SHIFT_TYPES = {
    TaskTypes.SHIFT_ON,
    TaskTypes.SHIFT_OFF,
    TaskTypes.EXHAUST_OFF,
    TaskTypes.SELF_CORRECTION,
    TaskTypes.RE_ORDER,
    TaskTypes.FILL_DORM,
    TaskTypes.RELEASE_DORM,
    TaskTypes.NOT_SPECIFIC,
}
_DIRECTION_TYPES = {
    TaskTypes.SHIFT_ON,
    TaskTypes.SHIFT_OFF,
    TaskTypes.EXHAUST_OFF,
    TaskTypes.NOT_SPECIFIC,
}
_PLACEHOLDERS = {"", "Current", "Free", "_"}


def facility_label(room, op_data=None):
    """优先采用实际设施类型，其次采用生效排班中的类型。"""
    if match := re.fullmatch(r"room_([1-3])_([1-3])", room):
        code = f"B{match[1]}0{match[2]}"
        state = getattr(op_data, "facility_states", {}).get(room, {})
        name = _FACILITIES.get(state.get("facility"))
        if not name:
            for slot in getattr(op_data, "plan", {}).get(room, []):
                value = (
                    slot.get("facility", slot.get("name"))
                    if isinstance(slot, dict)
                    else getattr(slot, "facility", None)
                )
                if value in _FACILITIES.values():
                    name = value
                    break
        return f"{name} {code}" if name else code
    if room in _FIXED_ROOMS:
        return _FIXED_ROOMS[room]
    if match := re.fullmatch(r"dormitory_([1-4])(_low)?", room):
        return f"宿舍{match[1]}" + ("（低优先级）" if match[2] else "")
    if match := re.fullmatch(r"gaming_([1-3])", room):
        return f"活动室{match[1]}"
    return room


def backup_changes(op_data, before, after):
    """返回本轮副表变化的名称快照，允许同时激活和停用多张。"""
    plans = getattr(op_data, "backup_plans", ())
    return [
        {"name": str(plan.name), "active": bool(target)}
        for plan, current, target in zip(plans, before, after)
        if bool(current) != bool(target)
    ]


def format_backup_staffing_title(changes):
    return "调整干员（副表：" + "、".join(change["name"] for change in changes) + "）"


def remember_backup_changes(task, op_data, before, after):
    """规划收敛时保存名称，避免副表改名后重写原任务的来源。"""
    task.log_backup_changes = backup_changes(op_data, before, after)
    task.log_backup_change_indices = [
        index
        for index, (current, target) in enumerate(zip(before, after))
        if bool(current) != bool(target)
    ]


def _pending_backups(task, op_data):
    if getattr(task, "backup_shift_active", False):
        return []
    target = getattr(task, "backup_shift_conditions", None)
    if target is None:
        return []
    captured = getattr(task, "log_backup_changes", None)
    if captured is None:
        captured = backup_changes(
            op_data, getattr(op_data, "plan_condition", ()), target
        )
    indices = getattr(task, "log_backup_change_indices", ())
    current = getattr(op_data, "plan_condition", ())
    return [
        {"name": str(item["name"]), "active": bool(item["active"])}
        for offset, item in enumerate(captured)
        if offset >= len(indices)
        or indices[offset] >= len(current)
        or bool(current[indices[offset]]) != item["active"]
    ]


def format_backup_changes(changes, *, completed=False):
    """按实际阶段组织副表激活和停用的中文说明。"""
    parts = []
    for active, action in ((True, "激活"), (False, "停用")):
        names = [item["name"] for item in changes if item["active"] is active]
        if names:
            label = f"已{action}的副表：" if completed else f"预计{action}的副表："
            parts.append(label + "、".join(names))
    return "；".join(parts)


def _group_members(data, group):
    resolve = getattr(data, "shift_group_members", None)
    values = (
        resolve(group)
        if callable(resolve)
        else getattr(data, "groups", {}).get(group, ())
    )
    return list(dict.fromkeys(name for name in values if name not in _PLACEHOLDERS))


def _new_rest_targets(data, plan):
    operators = getattr(data, "operators", {})
    targets = set()
    for room, names in plan.items():
        if not room.startswith("dorm"):
            continue
        for name in names:
            op = operators.get(name)
            if name in _PLACEHOLDERS or op is None:
                continue
            current = getattr(op, "current_room", None)
            if (
                current is None
                or current.startswith("dorm")
                or getattr(op, "room", "").startswith("dorm")
                or current
                and getattr(op, "current_index", -1) < 0
            ):
                continue
            targets.add(name)
    return targets


def _action(kind, subject, action):
    return {"kind": kind, "subject": subject, "action": action}


def _group_actions(task, data, plan, rest_targets):
    if task.type not in _SHIFT_TYPES:
        return [], set(), set()
    supplied = getattr(task, "group_shift_transitions", None)
    transitions = dict(supplied or {})
    resolve = getattr(data, "arrangement_group_transitions", None)
    if supplied is None and callable(resolve):
        derived = resolve(plan, group_transitions=transitions)
        if isinstance(derived, dict):
            transitions = derived
    actions, groups, covered_rest = [], set(), set()
    operators = getattr(data, "operators", {})
    for group, resting in transitions.items():
        if not group or type(resting) is not bool:
            continue
        read_state = getattr(data, "group_is_resting", None)
        current = (
            read_state(group)
            if callable(read_state)
            else getattr(data, "group_shift_state", {}).get(group)
        )
        if type(current) is not bool or current == resting:
            continue
        members = _group_members(data, group)
        subject = members[0] if len(members) == 1 else group
        kind = "operator" if len(members) == 1 else "group"
        action = "下班" if resting else "上班"
        recovering = {
            name
            for name in members
            if (op := operators.get(name)) is not None
            and not getattr(op, "room", "").startswith("dorm")
            and not getattr(op, "workaholic", False)
        }
        # 组状态只说明上下班；完整且有实际来源的入宿目标才能说明全组休息。
        if resting and recovering and recovering <= rest_targets:
            action = "休息"
            covered_rest.update(recovering)
        description = _action(kind, subject, action)
        if kind == "group":
            description["members"] = list(members)
        actions.append(description)
        groups.add(group)
    return actions, groups, covered_rest


def _bound_groups(op):
    if getattr(op, "multi_group", False):
        return {
            item["group"] for item in getattr(op, "group_bindings", ()) if item["group"]
        }
    return {getattr(op, "group", "")} - {""}


def _cleared_dorm_actions(data, plan, named_targets, covered_groups, preceding_names):
    """只有完整具名安排能排除再次选回原住者时，才描述转为空闲。"""
    if not any(re.fullmatch(r"dormitory_[1-4]", room) for room in plan):
        return []
    if any(
        not isinstance(name, str) or name in {"Free", "", "_"}
        for names in plan.values()
        for name in names
    ):
        return []
    operators = getattr(data, "operators", {})
    occupants = {}
    for name, op in operators.items():
        room = getattr(op, "current_room", None)
        index = getattr(op, "current_index", -1)
        if not isinstance(room, str) or type(index) is not int:
            continue
        capacity = (
            5
            if re.fullmatch(r"dormitory_[1-4]", room)
            else len(getattr(data, "plan", {}).get(room, ()))
        )
        if 0 <= index < capacity:
            occupants.setdefault((room, index), []).append(name)
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name == "Current":
                current = occupants.get((room, index), ())
                if len(current) != 1 or current[0] in named_targets:
                    return []
    cleared = []
    for name, op in operators.items():
        room = getattr(op, "current_room", None)
        index = getattr(op, "current_index", -1)
        if (
            not isinstance(room, str)
            or not re.fullmatch(r"dormitory_[1-4]", room)
            or type(index) is not int
            or occupants.get((room, index)) != [name]
            or name in named_targets
            or name in preceding_names
            or _bound_groups(op) & covered_groups
        ):
            continue
        targets = plan.get(room, ())
        if index < len(targets) and targets[index] not in _PLACEHOLDERS:
            cleared.append(_action("operator", name, "转为空闲"))
    return cleared


def _individual_actions(
    task,
    data,
    covered_groups,
    covered_rest,
    plan,
    rest_targets,
    preceding_names,
    allow_cleared,
):
    if task.type not in _SHIFT_TYPES:
        return []
    returning, departing, resting = [], [], []
    operators = getattr(data, "operators", {})
    named_targets = {
        name for names in plan.values() for name in names if name not in _PLACEHOLDERS
    }
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name in _PLACEHOLDERS or (op := operators.get(name)) is None:
                continue
            if name in rest_targets and name not in covered_rest:
                resting.append(_action("operator", name, "休息"))
                continue
            if _bound_groups(op) & covered_groups:
                continue
            if getattr(op, "multi_group", False) and not getattr(
                op, "independent_rest", False
            ):
                continue
            current = getattr(op, "current_room", None)
            if (
                (room in _FIXED_ROOMS or re.fullmatch(r"room_[1-3]_[1-3]", room))
                and not getattr(op, "workaholic", False)
                and (
                    current == ""
                    or isinstance(current, str)
                    and current.startswith("dorm")
                    and getattr(op, "current_index", -1) >= 0
                )
            ):
                returning.append(_action("operator", name, "上班"))
    for name, op in operators.items():
        current = getattr(op, "current_room", None)
        index = getattr(op, "current_index", -1)
        if (
            not current
            or current.startswith("dorm")
            or index < 0
            or name in named_targets
            or name in preceding_names
            or _bound_groups(op) & covered_groups
        ):
            continue
        targets = plan.get(current, ())
        # 只有明确替换已确认的工作岗位，且没有其他去向，才称为撤岗下班。
        if index < len(targets) and targets[index] not in ("Current", "Free", name):
            departing.append(_action("operator", name, "下班"))
    result = []
    cleared = (
        _cleared_dorm_actions(
            data, plan, named_targets, covered_groups, preceding_names
        )
        if allow_cleared
        else []
    )
    for action in [*returning, *departing, *resting, *cleared]:
        if action not in result:
            result.append(action)
    return result


def _actions_title(actions):
    descriptions = []
    for action in dict.fromkeys(item["action"] for item in actions):
        subjects = [item["subject"] for item in actions if item["action"] == action]
        descriptions.append("、".join(dict.fromkeys(subjects)) + action)
    return "；".join(descriptions)


def build_task_presentation(task, op_data, *, predecessors=()):
    """读取当前可证明的意图，不投影、派发、更新组状态或改动任务。

    执行时刻由日志和任务接口各自沿用同一时间规则；本函数只组织名称及目标。
    前置任务用于排除重复的离岗描述，干员来源仍读取当前已知驻员。
    """
    plan = {room: list(agents) for room, agents in list(task.plan.items())}
    rooms = [
        {"id": room, "label": facility_label(room, op_data), "agents": list(agents)}
        for room, agents in plan.items()
    ]
    rest_targets = _new_rest_targets(op_data, plan)
    preceding_names = {
        name
        for previous in predecessors
        for names in previous.plan.values()
        for name in names
        if name not in _PLACEHOLDERS
    }
    for previous in predecessors:
        for action in build_task_presentation(previous, op_data)["actions"]:
            if action["kind"] == "operator":
                preceding_names.add(action["subject"])
            else:
                preceding_names.update(action.get("members", ()))
    actions, groups, covered_rest = _group_actions(task, op_data, plan, rest_targets)
    actions.extend(
        _individual_actions(
            task,
            op_data,
            groups,
            covered_rest,
            plan,
            rest_targets,
            preceding_names,
            not predecessors,
        )
    )
    backups = _pending_backups(task, op_data)
    source_title = getattr(task, "log_source_title", "")
    if (
        task.type == TaskTypes.RUN_ORDER
        and getattr(task, "run_order_restore_pending", False)
        and not task.meta_data
    ):
        title = task.display_name
    elif actions:
        title = _actions_title(actions)
    elif source_title:
        title = source_title
    elif backups:
        title = format_backup_staffing_title(backups)
    elif task.type in _DIRECTION_TYPES:
        if task.plan:
            title = "安排干员"
        elif (
            task.type == TaskTypes.NOT_SPECIFIC
            and isinstance(task.meta_data, str)
            and task.meta_data
        ):
            title = task.meta_data
        else:
            title = task.display_name
    elif (
        task.type == TaskTypes.FIAMMETTA
        and isinstance(task.meta_data, str)
        and task.meta_data not in _PLACEHOLDERS | {"菲亚梅塔"}
        and any(
            re.fullmatch(r"dormitory_[1-4]", room)
            and task.meta_data in agents
            and "菲亚梅塔" in agents
            for room, agents in plan.items()
        )
    ):
        title = f"肥鸭 充 {task.meta_data}"
    else:
        title = {
            TaskTypes.SWAP_SUPPORT: "自动专精换协助位",
            TaskTypes.SKILL_UPGRADE: "自动专精",
        }.get(task.type, task.display_name)
    targets = []
    if task.type == TaskTypes.REFRESH_TIME and not getattr(
        task, "recovery_observation_rooms", None
    ):
        room = task.meta_data
        if isinstance(room, str) and re.fullmatch(r"room_[1-3]_[1-3]", room):
            targets.append({"id": room, "label": facility_label(room, op_data)})
    return {
        "title": title,
        "rooms": rooms,
        "backups": backups,
        "targets": targets,
        "actions": actions,
    }


def format_wait_duration(seconds):
    """以中文时分秒记录预告发布时的剩余时长，省略零值单位。"""
    hours, remaining = divmod(max(0, int(seconds)), 3600)
    minutes, seconds = divmod(remaining, 60)
    parts = []
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分")
    if seconds or not parts:
        parts.append(f"{seconds} 秒")
    return " ".join(parts)


def format_task_log_message(presentation, header):
    """文件日志和旧客户端仍能读取完整安排，不能只保留结构化字段。"""
    parts = [header]
    if targets := presentation["targets"]:
        parts[0] += " · " + "、".join(target["label"] for target in targets)
    if changes := format_backup_changes(presentation["backups"]):
        parts.append(changes)
    parts.extend(
        f"{room['label']}：{'、'.join(str(name) for name in room['agents'])}"
        for room in presentation["rooms"]
    )
    return "\n".join(parts)
