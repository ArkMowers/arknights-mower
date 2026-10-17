"""用尽下班的替班协调：先换替班，再整组回班，所有安排先在缓存中验证。"""

from collections import deque
from copy import deepcopy
from datetime import datetime

from arknights_mower.utils.operators import TRADE_ORDER_AGENTS
from arknights_mower.utils.scheduler_task import rebalance_closing_dorm_slots


def match_replacements(options, *, allow_partial=False, preferred=()):
    """保留可行首选；床位不足时先保留固定恢复替班的最大匹配。"""
    preferred = set(preferred)
    seed = (
        match_replacements(
            {
                name: [cover for cover in covers if cover in preferred]
                for name, covers in options.items()
            },
            allow_partial=True,
        )
        if preferred
        else {}
    )
    owners = {cover: name for name, cover in seed.items()}

    def reserve(name, seen):
        for cover in options[name]:
            if cover not in owners:
                owners[cover] = name
                return True
        for cover in options[name]:
            if cover in seen:
                continue
            seen.add(cover)
            if reserve(owners[cover], seen):
                owners[cover] = name
                return True
        return False

    for name in options:
        if name in owners.values():
            continue
        if not reserve(name, set()) and not allow_partial:
            return None
    return {name: cover for cover, name in owners.items()}


def plan_exhaust_support(
    op_data,
    candidates,
    can_rest,
    is_busy,
    protected=(),
    fia=(),
    reserved_slots=(),
    *,
    urgent=False,
    recall_blocked=False,
):
    """先保留既有换替班方案，再联合召回实际阻塞的休息组。"""
    pending, visited = deque([()]), {()}
    while pending:
        seeds, dependencies = pending.popleft(), set()
        result = _plan_exhaust_support_attempt(
            op_data,
            candidates,
            can_rest,
            is_busy,
            protected,
            fia,
            reserved_slots,
            urgent=urgent,
            recall_blocked=recall_blocked,
            seeds=seeds,
            dependency=dependencies.add,
        )
        if result is not None:
            return result
        if not urgent or recall_blocked:
            return None
        for name in sorted(dependencies):
            if name in seeds:
                continue
            updated = tuple(sorted((*seeds, name)))
            if updated not in visited:
                visited.add(updated)
                pending.append(updated)
    return None


def _plan_exhaust_support_attempt(
    op_data,
    candidates,
    can_rest,
    is_busy,
    protected=(),
    fia=(),
    reserved_slots=(),
    *,
    urgent=False,
    recall_blocked=False,
    seeds=(),
    dependency=lambda name: None,
):
    """返回能让用尽组取得替班和床位的前置安排；失败不改变真实状态。"""
    protected = set(protected) | set(op_data.reserved_product_replacements)
    required = set(candidates)
    cover_names = {
        name
        for name in candidates
        for name in op_data.operators[name].replacement
        if name != "Free"
    }
    from arknights_mower.utils.replacement_coordination import plan_replacement_handoff

    plan = (
        plan_replacement_handoff(
            op_data, candidates, is_busy, protected, reserved_slots
        )
        or {}
    )
    selected = set()
    data = op_data.project_arrangements([plan])

    request_groups = {
        op_data.operators[name].group
        for name in candidates
        if op_data.operators[name].group
        and op_data.is_group_shift_anchor(op_data.operators[name])
    }
    transitions = dict.fromkeys(request_groups, True)

    def covers(state, worker):
        replacement = (
            state.shared_replacements(
                worker,
                state.resting_binding_groups(
                    worker, transitions if worker.name in required else None
                ),
            )
            if worker.multi_group
            else worker.replacement
        )
        return state.replacement_candidates(worker, replacement_override=replacement)

    def depend_on(state, worker, group=None):
        if worker is None:
            return
        group = worker.group if group is None else group
        if group:
            if group in request_groups or not state.group_is_resting(group):
                return
            anchor = next(
                (
                    name
                    for name in state.shift_group_members(group)
                    if state.is_group_shift_anchor(state.operators[name])
                    and state.operators[name].is_resting()
                ),
                None,
            )
            if anchor is not None:
                dependency(anchor)
        elif worker.is_high() and worker.is_resting() and worker.name not in required:
            dependency(worker.name)

    def shared_dependencies(state, trial):
        changes = state.arrangement_group_transitions(trial)
        for worker in state.operators.values():
            if worker.multi_group:
                groups = state.resting_binding_groups(worker, changes)
                if not state.shared_replacements(worker, groups):
                    for group in groups:
                        depend_on(state, worker, group)

    def replacement_dependencies(state, worker):
        groups = (
            state.resting_binding_groups(worker, transitions)
            if worker.multi_group
            else [worker.group]
        )
        if worker.multi_group:
            for group in groups:
                depend_on(state, worker, group)
        names = (
            {
                cover
                for group in groups
                for cover in worker.replacements_for_group(group)
            }
            if worker.multi_group
            else set(worker.replacement)
        )
        for name in names:
            cover = state.operators.get(name)
            if cover is None or not cover.current_room:
                continue
            slots = state.plan.get(cover.current_room, [])
            if not 0 <= cover.current_index < len(slots):
                continue
            owner = state.operators.get(slots[cover.current_index].agent)
            if owner is not None and owner.name != name and not owner.is_working():
                depend_on(state, owner)

    def eligible(state, name, target):
        op = state.operators.get(name)
        return (
            op is not None
            and (
                not op.is_high()
                or state.is_same_group_primary_replacement(target, name)
            )
            and (op.current_room, op.current_index) not in reserved_slots
            and name not in protected | selected | set(TRADE_ORDER_AGENTS)
            and (
                name not in required
                or state.is_same_group_primary_replacement(target, name)
            )
            and (
                not state.is_dorm_replacement(name)
                or (op.current_room, op.current_index) == (target.room, target.index)
            )
            and not state.replacement_exhausted(name, operator=target)
            and not is_busy(name)
        )

    def available(state, name, target):
        op = state.operators.get(name)
        return eligible(state, name, target) and (
            not op.current_room
            or op.is_resting()
            or state.is_same_group_primary_replacement(target, name)
            and name in required
            and (op.current_room, op.current_index) == (op.room, op.index)
        )

    def protected_rest(state, name):
        from arknights_mower.utils.urgent_recovery import active_urgent_recovery

        if name in active_urgent_recovery(state):
            return True
        from arknights_mower.utils.group_recovery import group_recovery_deadline
        from arknights_mower.utils.recovery_execution import (
            recovery_ready_for_arrangement,
        )

        op = state.operators[name]
        if not op.is_resting():
            return False
        now = datetime.now()
        if op.rest_in_full and not recovery_ready_for_arrangement(
            state, name, sampled_after=None, now=now
        ):
            return True
        if op.group:
            required, _ = group_recovery_deadline(state, op.group, now=now)
            if urgent:
                required = [
                    member
                    for member in required
                    if state.operators[member].rest_in_full
                ]
            return any(
                not recovery_ready_for_arrangement(
                    state, member, sampled_after=None, now=now
                )
                for member in required
            )
        return False

    def recall(state, previous, names):
        if recall_blocked:
            return None
        names = [names] if isinstance(names, str) else names
        transitions = state.arrangement_group_transitions(previous)
        for name in names:
            if state.operators[name].group:
                transitions[state.operators[name].group] = False
        members = {
            member
            for name in names
            for op in [state.operators[name]]
            for member in (state.shift_group_members(op.group) if op.group else [name])
            if not state.operators[member].multi_group
            or not state.resting_binding_groups(state.operators[member], transitions)
        }
        required_anchors = {
            member
            for member in required
            if not (
                state.operators[member].multi_group
                and (
                    not state.operators[member].independent_rest
                    or state._can_standby(state.operators[member])
                    and not state.operators[member].current_room
                )
                and any(
                    state.is_group_shift_anchor(state.operators[other])
                    and any(
                        binding["group"] == state.operators[other].group
                        for binding in state.operators[member].group_bindings
                    )
                    for other in required - {member}
                )
            )
        }
        trial = deepcopy(previous)
        for member in members:
            worker = state.operators[member]
            if worker.is_working() and worker.current_room != worker.room:
                working_slots = state.plan.get(worker.current_room, [])
                covered = (
                    state.operators.get(working_slots[worker.current_index].agent)
                    if 0 <= worker.current_index < len(working_slots)
                    else None
                )
                if (
                    covered is None
                    or covered.name not in members
                    or not state.is_same_group_primary_replacement(covered, member)
                ):
                    return None
            if (worker.current_room, worker.current_index) != (
                worker.room,
                worker.index,
            ):
                trial.setdefault(
                    worker.room, ["Current"] * len(state.plan[worker.room])
                )[worker.index] = member
        if not state.normalize_shared_arrangement(
            trial, transitions, reserved_replacements=protected
        ):
            shared_dependencies(state, trial)
            return None

        def actual_returns():
            return {
                worker.name
                for worker in state.operators.values()
                if worker.is_high()
                and trial.get(worker.room, [])[worker.index : worker.index + 1]
                == [worker.name]
                and (worker.current_room, worker.current_index)
                != (worker.room, worker.index)
            }

        members = actual_returns()
        if members & (required_anchors | protected) or any(
            is_busy(member) or protected_rest(state, member) for member in members
        ):
            return None
        # 绑组宿舍回班可能关闭临时床位，复用已有迁移逻辑，不能挤丢入住者。
        simulation = state.project_arrangements([])
        rebalance_closing_dorm_slots(simulation, trial, members)
        if not state.normalize_shared_arrangement(
            trial, reserved_replacements=protected
        ):
            shared_dependencies(state, trial)
            return None
        recalled = actual_returns()
        moved = {
            member
            for room, row in trial.items()
            for index, member in enumerate(row)
            if member in state.operators
            and (
                state.operators[member].current_room,
                state.operators[member].current_index,
            )
            != (room, index)
        }
        if (
            recalled & moved & required_anchors
            or moved & protected
            or any(is_busy(member) for member in moved)
            or any(protected_rest(state, member) for member in recalled & moved)
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

    if seeds:
        seeded = recall(data, plan, seeds)
        if seeded is None:
            return None
        plan, data = seeded

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

    def free_matching(*, allow_partial=True):
        selected.clear()
        options = {
            name: [
                cover
                for cover in covers(data, data.operators[name])
                if available(data, cover, data.operators[name])
            ]
            for name in ordered
            if not data.is_auto_free_dorm_operator(data.operators[name])
        }
        matching = match_replacements(options, allow_partial=allow_partial)
        if matching is not None:
            selected.update(matching.values())
        return matching

    matching = free_matching()
    for name in ordered:
        worker = data.operators[name]
        if data.is_auto_free_dorm_operator(worker) or name in matching:
            continue
        worker_covers = covers(data, worker)
        # 只协调正在给其他主班顶岗的替班，不能搬走原岗位主班或训练干员。
        occupied = []
        for cover in worker_covers:
            if not eligible(data, cover, worker):
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
                    for other in covers(data, owner)
                    if other not in cover_names and available(data, other, owner)
                ),
                None,
            )
            if alternate is None:
                continue
            plan.setdefault(owner.room, ["Current"] * len(data.plan[owner.room]))[
                owner.index
            ] = alternate
            data = op_data.project_arrangements([plan])
            resolved = True
            break
        if not resolved:
            for cover, owner in occupied:
                result = recall(data, plan, owner.name)
                if result is None:
                    continue
                trial, projected = result
                if not available(projected, cover, worker):
                    continue
                plan, data = trial, projected
                resolved = True
                break
        if not resolved:
            replacement_dependencies(data, worker)
            return None
        matching = free_matching()
        if name not in matching:
            replacement_dependencies(data, worker)
            return None
    if free_matching(allow_partial=False) is None:
        for name in ordered:
            replacement_dependencies(data, data.operators[name])
        return None
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
        depend_on(data, op)
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
