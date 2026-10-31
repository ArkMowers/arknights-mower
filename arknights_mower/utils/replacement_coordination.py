"""共享替班的完整交接、首选恢复及保守召回检查。"""

from copy import deepcopy
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
    from arknights_mower.utils.backup_group_tasks import forced_group_cover_reservations

    op = data.operators.get(name)
    forced, _ = forced_group_cover_reservations(data)
    same_group = data.is_same_group_primary_replacement(owner, name)
    return (
        op is not None
        and (
            name not in forced
            or (op.current_room, op.current_index) == (owner.room, owner.index)
        )
        and (not op.is_high() or same_group)
        and (name not in required or same_group)
        and name not in protected
        and name not in TRADE_ORDER_AGENTS
        and (op.current_room, op.current_index) not in slots
        and not data.is_dorm_replacement(name)
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


def ordinary_recall_mood_admissible(data, recalled, candidates, *, now=None):
    """普通请求到急救线后才评估召回，双方必须有有效心情读数。"""
    now = now or getattr(data, "_projection_now", None) or datetime.now()

    def anchor(op):
        return data.is_group_shift_anchor(op) or (
            len(candidates) == 1
            and op.is_high()
            and op.independent_rest
            and not op.workaholic
            and not op.room.startswith("dorm")
            and not data._can_standby(op)
        )

    from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

    def mood(op):
        return dorm_candidate_mood(data, op.name, now)

    request_moods = [
        (op, value)
        for name in candidates
        if (op := data.operators.get(name)) is not None
        and anchor(op)
        and op.is_working()
        and (value := mood(op)) is not None
    ]
    if not any(value <= data.rescue_mood_threshold(op) for op, value in request_moods):
        return False
    for name in recalled:
        op = data.operators.get(name)
        if op is None:
            return False
        if not anchor(op):
            continue
        value = mood(op)
        if value is None:
            return False
    return True


def recall_can_sustain(
    original, admitted, recalled, candidates, *, rates=None, now=None, urgent=False
):
    """普通召回检查续航，用尽交接仅保留明确恢复要求。"""
    from arknights_mower.utils.group_recovery import group_recovery_deadline
    from arknights_mower.utils.recovery_execution import (
        recovery_ready_for_arrangement,
    )
    from arknights_mower.utils.urgent_recovery import (
        active_urgent_recovery,
        urgent_support_blocked,
    )

    if set(recalled) & active_urgent_recovery(
        original
    ).keys() or urgent_support_blocked(original, candidates):
        return False
    from arknights_mower.utils.backup_group_tasks import held_rest_groups

    if any(
        original.operators[name].group in held_rest_groups(original, forced_only=True)
        for name in recalled
    ):
        return False
    now = now or datetime.now()
    for name in recalled:
        op = original.operators[name]
        if op.rest_in_full and not recovery_ready_for_arrangement(
            original, name, sampled_after=None, now=now
        ):
            return False
        if op.group:
            required, _ = group_recovery_deadline(original, op.group, now=now)
            if urgent:
                required = [
                    name for name in required if original.operators[name].rest_in_full
                ]
            if any(
                not recovery_ready_for_arrangement(
                    original, member, sampled_after=None, now=now
                )
                for member in required
            ):
                return False
    if urgent:
        # 用尽急救不能被普通回班等待和未来续航预测阻挡。
        return True
    if not ordinary_recall_mood_admissible(original, recalled, candidates, now=now):
        return False
    from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

    def mood_at_check(op):
        return dorm_candidate_mood(original, op.name, now)

    connected = replacement_dependencies(
        original,
        [
            *candidates,
            *recalled,
            *(bed.name for bed in admitted.all_dorms() if bed.name),
        ],
    )
    if getattr(original, "mood_calculation_enabled", False):
        forecast = deepcopy(admitted, {id(admitted.eval_model): admitted.eval_model})
        horizon = now
        working = []
        for name in connected:
            op = forecast.operators.get(name)
            if op is None or not op.current_room:
                continue
            mood = forecast.calculated_mood(name, now)
            if mood is None:
                return False
            if (
                op.is_resting()
                and op.is_high()
                and not op.workaholic
                and not op.room.startswith("dorm")
                and mood < op.upper_limit
            ):
                deadline = forecast.calculated_mood_deadline(name, op.upper_limit, now)
                if deadline is None:
                    return False
                horizon = max(horizon, deadline)
            elif op.is_working() and not op.workaholic:
                rate = forecast.calculated_mood_rate(name, now)
                if rate is None or mood <= op.lower_limit:
                    return False
                working.append((name, op.lower_limit))
        for name, lower in working:
            exhausted = forecast.calculated_mood_deadline(
                name,
                lower,
                now,
                max_hours=max(0, (horizon - now).total_seconds() / 3600),
            )
            if exhausted is not None and exhausted <= horizon:
                return False
        for name, lower in working:
            mood = forecast.calculated_mood(name, horizon)
            if mood is None or mood <= lower:
                return False
        return True
    if rates is None:
        from arknights_mower.utils.recall_estimates import estimated_recall_rates

        rates = estimated_recall_rates(original, admitted, now=now)
    work, recovery = rates
    horizon = 0.0
    for name in connected:
        op = admitted.operators.get(name)
        observed = original.operators.get(name)
        if op is None or not op.current_room:
            continue
        if observed is None or mood_at_check(observed) is None:
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
