"""用尽下班的替班协调：先换替班，再整组回班，所有安排先在缓存中验证。"""

from copy import deepcopy
from datetime import datetime

from arknights_mower.utils.operators import TRADE_ORDER_AGENTS
from arknights_mower.utils.scheduler_task import rebalance_closing_dorm_slots


def plan_exhaust_support(op_data, candidates, can_rest, is_busy, protected=(), fia=()):
    """返回能让用尽组取得替班和床位的前置安排；失败不改变真实状态。"""
    protected = set(protected) | set(op_data.reserved_product_replacements)
    required = set(candidates)
    cover_names = {
        name
        for name in candidates
        for name in op_data.operators[name].replacement
        if name != "Free"
    }
    plan, selected = {}, set()
    data = op_data.project_arrangements([])

    def eligible(state, name):
        op = state.operators.get(name)
        return (
            op is not None
            and not op.is_high()
            and name not in protected | selected | required | set(TRADE_ORDER_AGENTS)
            and not state.is_dorm_replacement(name)
            and not is_busy(name)
        )

    def available(state, name):
        op = state.operators.get(name)
        return eligible(state, name) and (not op.current_room or op.is_resting())

    def protected_rest(state, name):
        op = state.operators[name]
        return op.is_resting() and (
            op.rest_in_full
            and op.exhaust_require
            or op.group in state.rest_in_full_group
            and op.group in state.exhaust_group
        )

    def recall(state, previous, name):
        op = state.operators[name]
        members = set(state.groups[op.group]) if op.group else {name}
        if members & (required | protected) or any(
            is_busy(member) or protected_rest(state, member) for member in members
        ):
            return None
        trial = deepcopy(previous)
        for member in members:
            worker = state.operators[member]
            if worker.is_working() and worker.current_room != worker.room:
                return None
            if (worker.current_room, worker.current_index) != (
                worker.room,
                worker.index,
            ):
                trial.setdefault(
                    worker.room, ["Current"] * len(state.plan[worker.room])
                )[worker.index] = member
        # 绑组宿舍回班可能关闭临时床位，复用已有迁移逻辑，不能挤丢入住者。
        simulation = state.project_arrangements([])
        recalled = rebalance_closing_dorm_slots(simulation, trial, members)
        if recalled & (required | protected) or any(
            is_busy(member) or protected_rest(state, member) for member in recalled
        ):
            return None
        projected = op_data.project_arrangements([trial])
        if any(
            worker.is_high()
            and worker.is_resting()
            and not projected.operators[worker.name].current_room
            and worker.name not in recalled
            for worker in state.operators.values()
        ):
            return None
        return trial, projected

    # 与普通下班一致的组内顺序；宿舍固定成员最后处理。
    ordered = sorted(
        candidates,
        key=lambda name: (
            data.operators[name].room.startswith("dorm"),
            name not in fia if fia else True,
            data.operators[name].current_room in ("factory", "train"),
            data.operators[name].current_mood() - data.operators[name].lower_limit,
        ),
    )
    for name in ordered:
        worker = data.operators[name]
        if data.is_auto_free_dorm_operator(worker):
            continue
        covers = data.replacement_candidates(worker)
        free = next((cover for cover in covers if available(data, cover)), None)
        if free is not None:
            selected.add(free)
            continue
        # 只协调正在给其他主班顶岗的替班，不能搬走原岗位主班或训练干员。
        occupied = []
        for cover in covers:
            if not eligible(data, cover):
                continue
            op = data.operators[cover]
            if not op.is_working() or op.current_room == "train":
                continue
            slots = data.plan.get(op.current_room, [])
            if not 0 <= op.current_index < len(slots):
                continue
            slot = slots[op.current_index]
            owner = data.operators.get(slot.agent)
            if (
                owner is not None
                and owner.name not in required | protected
                and not owner.is_working()
                and cover in owner.replacement
            ):
                occupied.append((cover, owner))
        resolved = False
        # 所有可换替班的方案优先于叫回任一休息组。
        for cover, owner in occupied:
            alternate = next(
                (
                    other
                    for other in data.replacement_candidates(owner)
                    if other not in cover_names and available(data, other)
                ),
                None,
            )
            if alternate is None:
                continue
            plan.setdefault(owner.room, ["Current"] * len(data.plan[owner.room]))[
                owner.index
            ] = alternate
            data = op_data.project_arrangements([plan])
            selected.add(cover)
            resolved = True
            break
        if not resolved:
            for cover, owner in occupied:
                result = recall(data, plan, owner.name)
                if result is None:
                    continue
                trial, projected = result
                if not available(projected, cover):
                    continue
                plan, data = trial, projected
                selected.add(cover)
                resolved = True
                break
        if not resolved:
            return None
    selected.clear()
    for name in ordered:
        worker = data.operators[name]
        if data.is_auto_free_dorm_operator(worker):
            continue
        cover = next(
            (
                other
                for other in data.replacement_candidates(worker)
                if available(data, other)
            ),
            None,
        )
        if cover is None:
            return None
        selected.add(cover)
    if can_rest(data):
        return plan

    # 替班已落实，才按原心情降序腾床；每次验证真实分床，不只比较人数。
    now = datetime.now()
    beds = sorted(
        data.dorm,
        key=lambda bed: (
            data.operators[bed.name].mood if bed.name in data.operators else 25
        ),
        reverse=True,
    )
    for bed in beds:
        op = data.operators.get(bed.name)
        if (
            op is None
            or not op.is_high()
            or not op.is_resting()
            or bed.time is not None
            and bed.time < now
            or not data.is_effective_free_slot(bed)
        ):
            continue
        result = recall(data, plan, op.name)
        if result is None or result[0] == plan:
            continue
        plan, data = result
        if can_rest(data):
            return plan
    return None
