"""Prepare assistant plans after confirming the training-room scene."""

from datetime import datetime

from arknights_mower.utils.mastery_support import (
    BASE_HOURS,
    REDUCERS,
    StageSpec,
    SupportPlanError,
    TrainingInputs,
    candidates,
    decode_json,
    decode_supports,
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
        and previous.get("level") == level - 1
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
    trainers = _stage_trainers(options, route, level)
    occupants = _observed_support(solver)
    first, swap = _follow_schedule(trainers, options, level, occupants[0])
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
    save_runtime(plan, _prepare_stage(first, swap, spec, carry))


def recover(solver, plan, room):
    """Reuse the room visit; no roster scan or optimizer in the scheduler loop."""
    from arknights_mower.solvers.mastery_reader import (
        _find_swap_task,
        _read_slots_checked,
    )

    level = room.panel.mastery_tier
    route = stage_for(plan, level)
    if not route or plan.get("swap_frozen"):
        return False
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
            and (room.panel.countdown - datetime.now()).total_seconds()
            < (300 + route["mastery_swap_buffer"]) * 60
        ):
            return False
        enqueue_support_swap(solver, plan, datetime.now(), route["operator"])
        return True
    if _find_swap_task(solver, str(plan["id"])) is not None:
        return True
    if not route.get("working_operator"):
        # Observed now; do not invent a historical start time or a halving credit.
        route["working_operator"] = support
        save_runtime(plan, route)
    return schedule_support_swap(solver, plan, room.panel.countdown, level) is not None
