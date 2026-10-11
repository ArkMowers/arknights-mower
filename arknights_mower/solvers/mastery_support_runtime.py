"""Prepare assistant plans after confirming the training-room scene."""

from datetime import datetime

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
    # candidates() filters the assistants used by _stage_trainers/_follow_schedule.
    return support, trainee


def _stage_trainers(options, route, level):
    first = options.get(route["operator"], {}).get(level)
    if first is None:
        raise SupportPlanError("计划协助者已不可用或已加入非训练室排班，请修改协助方案")
    swap = options.get(route.get("swap_target"), {}).get(level)
    return first, swap


def _follow_schedule(trainers, options, level, support):
    from arknights_mower.utils import config

    first, swap = trainers
    if config.conf.assistant_follows_schedule:
        first = options.get(support, {}).get(level)
        if first is None:
            raise SupportPlanError("协助位跟随排班时，需要先安排可用协助者")
        swap = None
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
    saved = decode_supports(plan)
    if not saved:
        return
    route = next((s for s in saved["stages"] if s["level"] == level), None)
    if route is None:
        raise SupportPlanError("专精阶段与协助方案不一致，请重新添加计划")
    options, central = candidates(
        plan["char_id"],
        include_dynamic=route.get("manual", False),
        inputs=TrainingInputs(schedule=schedule_context()),
    )
    from arknights_mower.utils import config

    exclude_reducer = (
        not config.conf.assistant_follows_schedule
        and basic_mastery_successor(plan, level)
    )
    trainers = (
        (_non_reducer(options, level), None)
        if exclude_reducer
        else _stage_trainers(options, route, level)
    )
    occupants = _observed_support(solver)
    first, swap = _follow_schedule(trainers, options, level, occupants[0])
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
    save_runtime(plan, prepared)


def recover(solver, plan, room):
    """Reuse the room visit and restore a final-stage reducer when the queue changes."""
    from arknights_mower.solvers.mastery_reader import (
        _read_slots_checked,
    )

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
    support, _, _, reliable = _read_slots_checked(solver)
    if not reliable:
        return False
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
