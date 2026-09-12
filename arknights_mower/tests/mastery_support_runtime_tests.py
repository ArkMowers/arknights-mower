"""Mastery assistant runtime regressions."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.tests.mastery_support_fixtures import (
    context_game as context_game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    stat as stat,
)
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils.mastery_support_types import StageSpec


@pytest.mark.parametrize("scheduled_trainee", [False, True])
def test_preflight_preserves_planned_reducer_without_changing_occupants(
    context_game, scheduled_trainee
):
    _, ids = context_game
    route = support.stage_route(stat("艾丽妮", 30, True), None, StageSpec(1, 8, 0, 10))
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 3,
        "support_plan": {"stages": [route]},
    }
    solver = MagicMock()
    with (
        patch.object(
            runtime,
            "schedule_context",
            return_value=({"能天使": {"room_1_1"}} if scheduled_trainee else {}, 0),
        ),
        patch.object(runtime, "save_runtime") as persist,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("", "能天使", None, True),
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=False),
        ),
    ):
        runtime.prepare_plan_supports(solver, plan, 1)
    assert persist.call_args.args[1]["operator"] == "艾丽妮"
    assert persist.call_args.args[1]["hours"] == pytest.approx(8 / 1.35)
    solver.choose_train.assert_not_called()
    solver.profession_filter.assert_not_called()
    solver.switch_arrange_order.assert_not_called()
    solver.ctap.assert_not_called()


@pytest.mark.parametrize("follow_schedule", [False, True])
def test_preflight_still_rejects_scheduled_assistant_in_use(
    context_game, follow_schedule
):
    _, ids = context_game
    route = support.stage_route(stat("艾丽妮", 30, True), None, StageSpec(1, 8))
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 3,
        "support_plan": {"stages": [route]},
    }
    # In automatic mode the planned assistant conflicts. In follow-schedule mode
    # the planned assistant is available, but the occupant to be retained conflicts.
    blocked_name = "逻各斯" if follow_schedule else "艾丽妮"
    solver = MagicMock()
    with (
        patch.object(
            runtime, "schedule_context", return_value=({blocked_name: {"room_3_2"}}, 0)
        ),
        patch.object(runtime, "save_runtime") as persist,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("逻各斯", "能天使", None, True),
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=follow_schedule),
        ),
    ):
        message = "协助位跟随排班" if follow_schedule else "计划协助者已不可用"
        with pytest.raises(support.SupportPlanError, match=message):
            runtime.prepare_plan_supports(solver, plan, 1)
    persist.assert_not_called()
    solver.choose_train.assert_not_called()


def test_waiting_collection_time_does_not_earn_five_hour_credit(context_game):
    _, ids = context_game
    route = support.stage_route(stat("艾丽妮", 30, True), None, StageSpec(2, 16, 0, 10))
    now = datetime.now()
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": {
            "level": 1,
            "working_operator": "艾丽妮",
            "working_halves": True,
            "working_since": (now - timedelta(hours=10)).isoformat(),
            "working_until": (now - timedelta(hours=6)).isoformat(),
        },
    }
    solver = MagicMock()
    with (
        patch.object(runtime, "schedule_context", return_value=({}, 0)),
        patch.object(runtime, "save_runtime") as persist,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("艾丽妮", "能天使", None, True),
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=False),
        ),
    ):
        runtime.prepare_plan_supports(solver, plan, 2)
    assert not persist.call_args.args[1]["half_inherited"]
    assert persist.call_args.args[1]["hours"] == pytest.approx(16 / 1.35)


def test_recovery_uses_saved_route_without_solving_or_reading_roster():
    route = support.stage_route(
        stat("教官", 50), stat("逻各斯", 0, True), StageSpec(2, 16, 0, 10)
    )
    plan = {
        "id": 1,
        "target_level": 3,
        "support_plan": {"stages": [route]},
        "support_runtime": {**route, "working_operator": "教官"},
    }
    panel = SimpleNamespace(
        mastery_tier=2, countdown=datetime.now() + timedelta(hours=8)
    )
    solver = MagicMock()
    solver.tasks = []
    with (
        patch.object(runtime, "refresh_end"),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("教官", "学员", None, True),
        ),
        patch.object(runtime, "candidates") as candidates,
        patch.object(support, "plan_supports") as optimize,
    ):
        assert runtime.recover(solver, plan, SimpleNamespace(panel=panel))
    candidates.assert_not_called()
    optimize.assert_not_called()
    assert len(solver.tasks) == 1
