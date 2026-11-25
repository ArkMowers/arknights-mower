"""训练位卡片搜索失败后，按源岗位、练度或实际候选重新准入。"""

from copy import copy

from arknights_mower.utils.schedule_roster import cached_training_progress


def _free_candidates(solver, task):
    if getattr(solver, "task", None) is not task:
        # 复核时可能正在派发其他任务。选人使用失败任务自己的预约和宿舍住客。
        solver = copy(solver)
        solver.task = task
    return set(solver.get_free_list([]))


def training_selection_wait(solver, task, target, *, source=None, candidates=None):
    """卡片搜索失败后保留当时的证据，供原任务恢复时比较。"""
    if task is None:
        return None
    train_plan = tuple(task.plan.get("train", ()))
    if len(train_plan) < 2 or train_plan[1] != target or target in ("", "Current"):
        return None
    if target == "Free":
        if candidates is None:
            return None
        occupant = solver.op_data.get_current_operator("train", 1)
        return {
            "target": target,
            "train_plan": train_plan,
            "occupant": occupant.name if occupant is not None else None,
            "candidates": tuple(sorted(set(candidates))),
        }

    wait = {
        "target": target,
        "train_plan": train_plan,
        "skill_blocked": cached_training_progress(target).selectable is False,
    }
    if source is not None:
        room, index = source
        row = task.plan.get(room, ())
        if (
            room != "train"
            and 0 <= index < len(row)
            and row[index] not in ("Current", "Free", target)
        ):
            wait["source"] = (room, index)
            wait["source_target"] = row[index]
    return wait


def training_selection_ready(solver, task, wait) -> bool | None:
    """返回是否可重选。缺少可先执行的源岗位安排时，None 交回普通快照。"""
    if tuple(task.plan.get("train", ())) != tuple(wait["train_plan"]):
        return True
    target = wait["target"]
    data = solver.op_data
    occupant = data.get_current_operator("train", 1)
    if target == "Free":
        if occupant is not None and occupant.name != wait["occupant"]:
            return True
        return _free_candidates(solver, task) != set(wait["candidates"])
    if occupant is not None and occupant.name == target:
        return True

    source = wait.get("source")
    if source is not None:
        room, index = source
        row = task.plan.get(room, ())
        if index >= len(row) or row[index] != wait["source_target"]:
            return True
        operator = data.operators.get(target)
        if operator is not None and (operator.current_room, operator.current_index) != (
            room,
            index,
        ):
            return True
        resident = data.get_current_operator(room, index)
        if resident is not None and resident.name != target:
            return True

    selectable = cached_training_progress(target).selectable
    if selectable is False:
        wait["skill_blocked"] = True
    if wait["skill_blocked"] and selectable is True:
        return True
    return False if source is not None else None
