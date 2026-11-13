"""Prepare assistant plans after confirming the training-room scene."""

from dataclasses import replace
from datetime import datetime

from arknights_mower.utils.mastery_mood import require_support_mood
from arknights_mower.utils.mastery_order import (
    basic_mastery_successor,
    halving_successor,
)
from arknights_mower.utils.mastery_support import (
    BASE_HOURS,
    REDUCERS,
    StageSpec,
    SupportPlanError,
    TrainingInputs,
    candidates,
    decode_json,
    decode_supports,
    rate,
    schedule_context,
    stage_for,
    stage_route,
)
from arknights_mower.utils.mastery_support_types import DEFAULT_SWAP_BUFFER_MINUTES

from .mastery_support_state import (
    enqueue_support_swap,
    refresh_end,
    save_runtime,
    schedule_support_swap,
)


def _observed_support(solver):
    from arknights_mower.solvers.mastery_reader import _read_slots_checked

    support, trainee, _, reliable = _read_slots_checked(solver)
    if not reliable:
        raise SupportPlanError("无法确认当前训练室协助者，请重试")
    # This is the existing occupant, not necessarily the planned assistant.
    # candidates() filters the assistants used by _stage_trainers.
    return support, trainee


def _stage_trainers(options, route, level, support):
    from arknights_mower.utils import config

    if config.conf.assistant_follows_schedule:
        first = options.get(support, {}).get(level)
        if first is None:
            raise SupportPlanError("协助位跟随排班时，需要先安排可用协助者")
        return first, None
    first = options.get(route["operator"], {}).get(level)
    if first is None:
        raise SupportPlanError("计划协助者已不可用或已加入非训练室排班，请修改协助方案")
    swap = options.get(route.get("swap_target"), {}).get(level)
    return first, swap


def _carried_halving(plan, level, occupants):
    support, trainee = occupants
    previous = decode_json(plan.get("support_runtime")) or {}
    if not (
        trainee == plan.get("char_name")
        and (
            previous.get("level") == level - 1
            or previous.get("carry_from_skill") is not None
            and previous["carry_from_skill"] != plan.get("skill_index")
        )
        and previous.get("working_operator") == support
        and previous.get("working_halves")
        and previous.get("working_since")
    ):
        return None
    started = datetime.fromisoformat(previous["working_since"])
    ended = datetime.now()
    if previous.get("working_until"):
        ended = min(ended, datetime.fromisoformat(previous["working_until"]))
    return support if (ended - started).total_seconds() > 5 * 3600 else None


def _prepare_stage(first, swap, spec, carry):
    selected = stage_route(first, swap, spec) or stage_route(first, None, spec)
    selected.update(
        manual=spec.manual,
        activate_with=carry,
        half_inherited=bool(carry),
        working_operator=None,
        first_halves=first["halves"],
        swap_halves=swap["halves"] if swap else False,
    )
    return selected


def _non_reducer(options, level):
    selected = max(
        (stats[level] for stats in options.values() if not stats[level]["halves"]),
        key=lambda trainer: trainer["efficiency"],
        default=None,
    )
    if selected is None:
        raise SupportPlanError("下一技能为七级升专一，专三需要可用的非减半协助者")
    return selected


def route_without_unusable_reducer(plan, level, route):
    if not route:
        return route
    if not basic_mastery_successor(plan, level):
        return (
            dict(route, exclude_reducer=False)
            if route.get("exclude_reducer")
            else route
        )
    selected = dict(
        route,
        swap_target=None,
        swap_halves=False,
        switch_after=None,
        exclude_reducer=True,
    )
    if route["operator"] in REDUCERS:
        options, central = candidates(
            plan["char_id"],
            include_dynamic=route.get("manual", False),
            inputs=TrainingInputs(schedule=schedule_context()),
        )
        trainer = _non_reducer(options, level)
        selected.update(
            operator=trainer["name"],
            efficiency=trainer["efficiency"],
            first_halves=False,
            central_bonus=central,
        )
    selected["hours"] = (
        BASE_HOURS[level]
        * (0.5 if route.get("half_inherited") else 1)
        / rate(selected["efficiency"], selected.get("central_bonus", 0))
    )
    return selected


def prepare_plan_supports(solver, plan, level):
    """Validate the stage and carried halving without changing occupants."""
    from arknights_mower.utils import config

    saved = decode_supports(plan)
    if not saved:
        return
    route = next((s for s in saved["stages"] if s["level"] == level), None)
    if route is None:
        raise SupportPlanError("专精阶段与协助方案不一致，请重新添加计划")
    inputs = TrainingInputs(schedule=schedule_context())
    options, central = candidates(
        plan["char_id"],
        include_dynamic=config.conf.assistant_follows_schedule
        or route.get("manual", False),
        inputs=inputs,
    )
    exclude_reducer = (
        not config.conf.assistant_follows_schedule
        and basic_mastery_successor(plan, level)
    )
    occupants = _observed_support(solver)
    first, swap = (
        (_non_reducer(options, level), None)
        if exclude_reducer
        else _stage_trainers(options, route, level, occupants[0])
    )
    if not config.conf.assistant_follows_schedule and level >= plan["target_level"]:
        if halving_successor(plan, level):
            reducers = [
                stats[level] for stats in options.values() if stats[level]["halves"]
            ]
            swap = max(reducers, key=lambda item: item["efficiency"], default=None)
        else:
            swap = None
    carry = _carried_halving(plan, level, occupants)
    spec = StageSpec(
        level,
        BASE_HOURS[level] * (0.5 if carry else 1),
        central,
        route.get(
            "configured_swap_buffer",
            route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
        ),
        manual=route.get("manual", False),
    )
    prepared = _prepare_stage(first, swap, spec, carry)
    prepared["exclude_reducer"] = exclude_reducer
    prepared = _admit_or_replace(solver, plan, prepared, spec, carry, inputs)
    save_runtime(plan, prepared)


def prepare_legacy_support_mood(solver, plan, level):
    """Budget legacy manual routes through the same endurance boundary."""
    from arknights_mower.solvers.mastery import _get_plan_route
    from arknights_mower.utils import config

    occupants = _observed_support(solver)
    carry = _carried_halving(plan, level, occupants)
    options = None
    if config.conf.assistant_follows_schedule:
        options, _ = candidates(plan["char_id"], include_dynamic=True)
    route = _get_plan_route(plan, level)
    if not route or not route.get("operator"):
        raise SupportPlanError("无法确认当前阶段协助方案，停止开训")
    route = {
        **route,
        "level": level,
        "swap_efficiency": route.get(
            "swap_efficiency", 30 if route.get("job_match") else 0
        ),
    }
    if options is not None:
        trainer = options.get(occupants[0], {}).get(level)
        if trainer is None:
            raise SupportPlanError("无法确认排班协助干员，停止开训")
        route.update(
            operator=trainer["name"],
            efficiency=trainer["efficiency"],
            first_halves=trainer["halves"],
            swap_target=None,
        )
    spec = StageSpec(
        level,
        BASE_HOURS[level] * (0.5 if carry else 1),
        route.get("central_bonus", 0),
        route.get(
            "configured_swap_buffer",
            route.get("mastery_swap_buffer", DEFAULT_SWAP_BUFFER_MINUTES),
        ),
        manual=route.get("manual", False),
    )
    selected = _admit_or_replace(solver, plan, route, spec, carry, None)
    if selected.get("mood_fallback") or (
        decode_json(plan.get("support_runtime")) or {}
    ).get("mood_fallback"):
        save_runtime(plan, selected)


def _admit_or_replace(solver, plan, route, spec, carry, inputs):
    from arknights_mower.utils import config
    from arknights_mower.utils.log import logger
    from arknights_mower.utils.mastery_mood import (
        SupportMoodWait,
        support_mood_requirements,
        support_mood_shortages,
    )

    try:
        _require_stage_mood(solver, route, inherited=bool(carry))
        return route
    except SupportMoodWait as error:
        if config.conf.assistant_follows_schedule:
            raise
        waiting = error
    options, central = candidates(plan["char_id"], inputs=inputs, include_dynamic=False)
    spec = replace(spec, central=central, manual=False)
    exclude_reducer = basic_mastery_successor(plan, spec.level)
    successor = halving_successor(plan, spec.level)
    last_name = route.get("swap_target") or route["operator"]
    retain_halving = bool(successor) and (
        route.get("swap_halves", last_name in REDUCERS)
        if route.get("swap_target")
        else route.get("first_halves", last_name in REDUCERS)
    )
    trainers = [stats[spec.level] for stats in options.values()]
    if exclude_reducer:
        trainers = [trainer for trainer in trainers if not trainer["halves"]]
    reducers = (
        [trainer for trainer in trainers if trainer["halves"]] if retain_halving else []
    )
    alternatives = []
    for first in trainers:
        for swap in [None, *reducers]:
            projected = stage_route(first, swap, spec)
            if projected is None:
                continue
            last = swap if projected["swap_target"] else first
            if retain_halving and (
                not last["halves"]
                or projected["hours"] - (projected["switch_after"] or 0) <= 5
            ):
                continue
            prepared = _prepare_stage(first, swap, spec, carry)
            prepared.update(exclude_reducer=exclude_reducer, mood_fallback=True)
            required = support_mood_requirements(prepared, inherited=bool(carry))
            alternatives.append((prepared, required))
    alternatives.sort(
        key=lambda pair: (
            pair[0]["hours"],
            bool(pair[0]["swap_target"]),
            pair[0]["operator"],
            pair[0].get("swap_target") or "",
        )
    )

    def available():
        return next(
            (
                prepared
                for prepared, required in alternatives
                if not support_mood_shortages(solver.op_data, required)
            ),
            None,
        )

    selected = available()
    task = getattr(solver, "task", None)
    observed = getattr(task, "mastery_mood_observation", None)
    if selected is None and (not observed or observed[0] != spec.level):
        unknown = next(
            (
                prepared
                for prepared, required in alternatives
                if any(
                    value is None
                    for value in support_mood_shortages(
                        solver.op_data, required
                    ).values()
                )
            ),
            None,
        )
        if unknown is not None:
            try:
                _require_stage_mood(solver, unknown, inherited=bool(carry))
            except SupportMoodWait:
                pass
            selected = available()
    if selected is None:
        waiting.alternatives = [required for _, required in alternatives]
        raise waiting
    logger.info(
        "专精协助干员心情不足或未知，当前阶段改用 %s，预计 %.2f 小时",
        " → ".join(filter(None, (selected["operator"], selected.get("swap_target")))),
        selected["hours"],
    )
    return selected


def _require_stage_mood(solver, route, *, inherited):
    from arknights_mower.utils.mastery_mood import SupportMoodWait

    try:
        require_support_mood(solver, route, inherited=inherited)
        return
    except SupportMoodWait as error:
        if not any(value is None for value in error.shortages.values()):
            raise
        task = getattr(solver, "task", None)
        observation = (route["level"], tuple(sorted(error.required.items())))
        scan = getattr(solver, "_scan_card_moods", None)
        if not callable(scan) or observation == getattr(
            task, "mastery_mood_observation", None
        ):
            raise
        scanned = scan(mastery=True)
        if task is not None:
            task.mastery_mood_observation_pending = scanned is False
            if scanned is not False:
                task.mastery_mood_observation = observation
        if scanned is not False:
            solver.enter_room("train", max_attempts=1)
    require_support_mood(solver, route, inherited=inherited)


def recover(solver, plan, room):
    """Reuse the room visit and restore a final-stage reducer when the queue changes."""
    from arknights_mower.solvers.mastery_reader import (
        _read_slots_checked,
    )
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.recovery import DeviceRecoveryError
    from arknights_mower.utils.scheduler_task import TaskTypes

    pending = next(
        (
            task
            for task in solver.tasks
            if task.type == TaskTypes.SWAP_SUPPORT
            and getattr(task, "plan_key", None) == str(plan["id"])
        ),
        None,
    )
    if pending is not None and (
        getattr(pending, "execution_failure", None)
        or getattr(pending, "execution_retained", False)
    ):
        return True

    level = room.panel.mastery_tier
    saved_route = stage_for(plan, level)
    route = route_without_unusable_reducer(plan, level, saved_route)
    if not route:
        return False
    if route != saved_route:
        save_runtime(plan, route)
    if plan.get("swap_frozen") and not route.get("exclude_reducer"):
        return False
    if (
        level >= plan["target_level"]
        and not route.get("swap_target")
        and halving_successor(plan, level)
    ):
        from arknights_mower.utils import config

        if not config.conf.assistant_follows_schedule:
            options, central = candidates(
                plan["char_id"], inputs=TrainingInputs(schedule=schedule_context())
            )
            reducers = [
                stats[level] for stats in options.values() if stats[level]["halves"]
            ]
            reducer = max(reducers, key=lambda item: item["efficiency"], default=None)
            if reducer and reducer["name"] != route["operator"]:
                route.update(
                    swap_target=reducer["name"],
                    swap_efficiency=reducer["efficiency"],
                    swap_halves=True,
                    central_bonus=central,
                )
                save_runtime(plan, route)
    try:
        support, _, _, reliable = _read_slots_checked(solver)
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception:
        support, reliable = None, False
    if not reliable:
        if pending is None:
            if schedule_support_swap(solver, plan, room.panel.countdown, level) is None:
                enqueue_support_swap(solver, plan, datetime.now(), route["operator"])
        return True
    if support == route.get("working_operator"):
        refresh_end(plan, level, room.panel.countdown)
    if support == route.get("swap_target"):
        return False
    if support != route["operator"]:
        if (
            support in REDUCERS
            and not route.get("exclude_reducer")
            and (room.panel.countdown - datetime.now()).total_seconds()
            < (300 + route["mastery_swap_buffer"]) * 60
        ):
            return False
        enqueue_support_swap(solver, plan, datetime.now(), route["operator"])
        return True
    if not route.get("working_operator"):
        # Observed now; do not invent a historical start time or a halving credit.
        route["working_operator"] = support
        save_runtime(plan, route)
    return schedule_support_swap(solver, plan, room.panel.countdown, level) is not None


def central_training_occupants(solver):
    from arknights_mower.utils.mastery_support_types import CONTROL_TRAINERS

    return frozenset(
        name
        for name, op in solver.op_data.operators.items()
        if name in CONTROL_TRAINERS and op.current_room == "central"
    )


def refresh_after_central_change(solver, previous):
    """Refresh only after a relevant operator actually enters or leaves central."""
    from arknights_mower.solvers.mastery_reader import read_room_state, reconcile_short
    from arknights_mower.utils import config
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.recovery import DeviceRecoveryError
    from arknights_mower.utils.log import logger
    from arknights_mower.utils.mastery_db import get_active_plan

    if previous == central_training_occupants(solver) or not config.conf.enable_mastery:
        return
    plan = get_active_plan()
    if not plan or plan.get("status") != "training":
        return
    try:
        room = read_room_state(solver)
        solver.train_room_state = room
        reconcile_short(solver, room, defer_collect=True)
    except (MowerExit, DeviceRecoveryError):
        raise
    except Exception as exc:
        logger.warning(f"中枢换班已确认，训练倒计时本次刷新失败：{exc}")
    solver.back_to_infrastructure()
