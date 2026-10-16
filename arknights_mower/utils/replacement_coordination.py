"""共享替班的完整交接、首选恢复及保守召回检查。"""

from datetime import datetime
from math import isfinite

from arknights_mower.utils.operators import TRADE_ORDER_AGENTS


def replacement_dependencies(data, names):
    names = set(names)
    while True:
        before = set(names)
        for op in data.operators.values():
            peers = data.shift_group_members(op.group) if op.group else []
            covers = replacements(data, op)
            if op.name in names or names.intersection(peers + covers):
                names.update([op.name, *peers, *(n for n in covers if n != "Free")])
        if names == before:
            return names


def replacements(data, op, required=()):
    transitions = {
        worker.group: True
        for name in required
        if (worker := data.operators.get(name)) is not None
        and worker.group
        and data.is_group_shift_anchor(worker)
    }
    return (
        data.shared_replacements(op, data.resting_binding_groups(op, transitions))
        if op.multi_group
        else op.replacement
    )


def coordination_reservations(data, tasks, current=None):
    from arknights_mower.utils.dorm_candidates import retained_task_reservations

    tasks = list(tasks)
    names = set(getattr(data, "reserved_product_replacements", ()))
    slots = set(getattr(data, "reserved_product_beds", ()))
    retained_names, retained_slots = retained_task_reservations(
        data, tasks, current_task=current
    )
    names.update(retained_names)
    slots.update(retained_slots)
    for task in tasks:
        if task is current:
            continue
        if getattr(task, "product_shift_locked", False):
            names.update(getattr(task, "product_lock_names", ()))
            slots.update(getattr(task, "product_lock_slots", ()))
        if getattr(task, "backup_shift_active", False) or getattr(
            task, "dorm_recovery_restore", ()
        ):
            names.update(getattr(task, "dorm_recovery_restore", ()))
            for room, row in task.plan.items():
                for index, name in enumerate(row):
                    if name != "Current":
                        slots.add((room, index))
                        if name in data.operators:
                            names.add(name)
    return names, slots


def _eligible(data, owner, name, protected, slots, is_busy, required=()):
    op = data.operators.get(name)
    same_group = data.is_same_group_primary_replacement(owner, name)
    return (
        op is not None
        and (not op.is_high() or same_group)
        and (name not in required or same_group)
        and name not in protected
        and name not in TRADE_ORDER_AGENTS
        and (op.current_room, op.current_index) not in slots
        and not data.is_dorm_replacement(name)
        and not data.is_free_room_excluded(name)
        and not data.replacement_exhausted(name, operator=owner)
        and not is_busy(name)
    )


def plan_replacement_handoff(data, candidates, is_busy, protected=(), slots=()):
    from arknights_mower.utils.exhaust_replacement import match_replacements

    required, protected, slots = set(candidates), set(protected), set(slots)
    owners, choices = {}, {}

    def visit(name):
        if name in owners:
            return
        owner = data.operators.get(name)
        if (
            owner is None
            or owner.room not in data.plan
            or name in protected
            or (owner.room, owner.index) in slots
        ):
            return
        owners[name] = owner
        raw = replacements(data, owner, required)
        choices[name] = []
        if owner.room.startswith("dorm") and "Free" in raw:
            return
        for cover in raw:
            if not _eligible(data, owner, cover, protected, slots, is_busy, required):
                continue
            op = data.operators[cover]
            if (
                not op.current_room
                or op.is_resting()
                or cover in required
                and data.is_same_group_primary_replacement(owner, cover)
                and (op.current_room, op.current_index) == (op.room, op.index)
            ):
                choices[name].append(cover)
                continue
            if op.current_room == "train":
                continue
            row = data.plan.get(op.current_room, [])
            occupied = (
                data.operators.get(row[op.current_index].agent)
                if 0 <= op.current_index < len(row)
                else None
            )
            if (
                occupied is None
                or occupied.name == cover
                or occupied.is_working()
                or (occupied.room, occupied.index) in slots
                or cover not in replacements(data, occupied, required)
            ):
                continue
            visit(occupied.name)
            if occupied.name in owners:
                choices[name].append(cover)

    for name in candidates:
        visit(name)
    if any(name not in owners for name in candidates):
        return None
    ordered = {
        name: choices[name]
        for name in sorted(owners, key=lambda n: n in required)
        if not (
            owners[name].room.startswith("dorm")
            and "Free" in replacements(data, owners[name], required)
        )
    }
    matching = match_replacements(ordered)
    if matching is None:
        return None
    plan = {}
    for name, cover in matching.items():
        if name in required:
            continue
        owner = owners[name]
        current = data.get_current_operator(owner.room, owner.index)
        if current is None or current.name != cover:
            plan.setdefault(owner.room, ["Current"] * len(data.plan[owner.room]))[
                owner.index
            ] = cover
    return plan


def preferred_replacement_restore(data, is_busy, protected=(), slots=()):
    plan, protected, slots = {}, set(protected), set(slots)
    shadow = data
    while True:
        changed = False
        for owner in shadow.operators.values():
            if (
                not owner.is_high()
                or owner.room.startswith("dorm")
                or owner.is_working()
                or owner.name in protected
                or (owner.room, owner.index) in slots
            ):
                continue
            current = shadow.get_current_operator(owner.room, owner.index)
            ordered = replacements(shadow, owner)
            if (
                current is None
                or current.name not in ordered
                or current.name in protected
            ):
                continue
            index = ordered.index(current.name)
            if not _eligible(shadow, owner, current.name, protected, slots, is_busy):
                continue
            preferred = next(
                (
                    name
                    for name in ordered[:index]
                    if _eligible(shadow, owner, name, protected, slots, is_busy)
                    and (
                        not shadow.operators[name].current_room
                        or shadow.operators[name].is_resting()
                    )
                ),
                None,
            )
            if preferred is None:
                continue
            plan.setdefault(owner.room, ["Current"] * len(shadow.plan[owner.room]))[
                owner.index
            ] = preferred
            shadow = data.project_arrangements([plan])
            changed = True
        if not changed:
            return plan


def recall_can_sustain(
    original, admitted, recalled, candidates, *, rates=None, now=None
):
    """用实测近似速率检查关联组的恢复周期，未知数据不授权召回。"""
    from arknights_mower.utils.group_recovery import group_recovery_deadline
    from arknights_mower.utils.recovery_execution import (
        recovery_ready_for_arrangement,
    )

    now = now or datetime.now()
    for name in recalled:
        op = original.operators[name]
        if op.rest_in_full and not recovery_ready_for_arrangement(
            original, name, sampled_after=None, now=now
        ):
            return False
        if op.group:
            required, _ = group_recovery_deadline(original, op.group, now=now)
            if any(
                not recovery_ready_for_arrangement(
                    original, member, sampled_after=None, now=now
                )
                for member in required
            ):
                return False
    if rates is None:
        from arknights_mower.utils.recall_estimates import estimated_recall_rates

        rates = estimated_recall_rates(original, admitted, now=now)
    work, recovery = rates

    def mood_at_check(op):
        # 休息期间保守沿用实读心情，不把旧工作掉率套在恢复阶段。
        if op.is_resting():
            return op.mood
        elapsed = max(0, (now - op.time_stamp).total_seconds() / 3600)
        return max(0, min(24, op.mood - max(0, op.depletion_rate) * elapsed))

    connected = replacement_dependencies(
        original,
        [
            *candidates,
            *recalled,
            *(bed.name for bed in admitted.all_dorms() if bed.name),
        ],
    )
    horizon = 0.0
    for name in connected:
        op = admitted.operators.get(name)
        observed = original.operators.get(name)
        if op is None or not op.current_room:
            continue
        if (
            observed is None
            or observed.time_stamp is None
            or getattr(observed, "mood_is_prediction", False)
            or observed.time_stamp > now
            or not isfinite(observed.mood)
            or not 0 <= observed.mood <= 24
        ):
            return False
        if (
            op.is_resting()
            and op.is_high()
            and not op.workaholic
            and not op.room.startswith("dorm")
        ):
            rate = recovery.get(name)
            if rate is None or not isfinite(rate) or rate <= 0:
                return False
            horizon = max(
                horizon, max(0, op.upper_limit - mood_at_check(observed)) / rate
            )
    if horizon <= 0:
        return True
    for name in connected:
        op = admitted.operators.get(name)
        if op is None or not op.is_working() or op.workaholic:
            continue
        rate = work.get(name)
        if (
            rate is None
            or not isfinite(rate)
            or rate < 0
            or mood_at_check(original.operators[name]) - rate * horizon
            <= op.lower_limit
        ):
            return False
    return True
