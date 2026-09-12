"""Central-aware final checks and stage-specific margins for reducer handoffs."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers import mastery
from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.solvers import mastery_support_swap as swap
from arknights_mower.tests.mastery_support_fixtures import stat
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils.mastery_optimizer import stage_route
from arknights_mower.utils.mastery_support_types import (
    DEFAULT_SWAP_BUFFERS,
    StageSpec,
    configured_swap_buffer,
    stage_for,
    swap_buffer_minutes,
)


def test_saved_old_numeric_buffer_stays_custom_and_can_return_to_defaults(tmp_path):
    path = str(tmp_path / "mastery.db")
    assert configured_swap_buffer(db.get_route_settings(path)) == DEFAULT_SWAP_BUFFERS
    # Existing installations saved only these two fields; do not reinterpret
    # their smaller explicit values as the new automatic margin.
    with db._conn(path) as conn:
        conn.execute(
            "INSERT INTO mastery_route (profession, supports, is_default) VALUES (?, ?, 0)",
            ("__mastery_settings__", '{"central_bonus":5,"mastery_swap_buffer":5}'),
        )
        conn.commit()
    settings = db.get_route_settings(path)
    assert configured_swap_buffer(settings) == {key: 5 for key in DEFAULT_SWAP_BUFFERS}
    custom = {"no_central": 4, "central": 7, "central_unhalved_m2": 6}
    db.save_route_settings(5, path=path, mastery_swap_buffers=custom)
    assert configured_swap_buffer(db.get_route_settings(path)) == custom


@pytest.mark.parametrize("central", [0, 5])
@pytest.mark.parametrize("configured", [None, 0, 5, 45])
def test_legacy_routes_apply_defaults_only_when_requested(central, configured):
    settings = {
        "central_bonus": central,
        "mastery_swap_buffer": 10 if configured is None else configured,
        "mastery_swap_buffers": dict(DEFAULT_SWAP_BUFFERS)
        if configured is None
        else {key: configured for key in DEFAULT_SWAP_BUFFERS},
    }
    with (
        patch.object(db, "get_route_settings", return_value=settings),
        patch.object(db, "get_route", return_value=None),
    ):
        for level in (1, 2):
            route = mastery.get_route_config("医疗", level)
            expected = (
                (10 if not central else 15 if level == 1 else 30)
                if configured is None
                else configured
            )
            assert route["mastery_swap_buffer"] == expected
            assert route["configured_swap_buffer"] == settings["mastery_swap_buffers"]


@pytest.mark.parametrize("central", [0, 5])
@pytest.mark.parametrize("level,work", [(1, 8), (2, 8), (2, 16)])
def test_preview_and_runtime_share_effective_buffer(central, level, work):
    expected = 10 if not central else 30 if (level, work) == (2, 16) else 15
    first, reducer = stat("教官", 60), stat("艾丽妮", 0, True)
    route = stage_route(first, reducer, StageSpec(level, work, central))
    assert route["mastery_swap_buffer"] == expected
    assert route["configured_swap_buffer"] is None
    route["working_operator"] = "教官"
    plan = {"id": 1, "target_level": 3, "support_plan": {"stages": [route]}}
    now = datetime(2026, 9, 12, 12)
    end = now + timedelta(hours=work / (1.65 + central / 100))
    with patch.object(state, "datetime") as clock:
        clock.now.return_value = now
        solver = SimpleNamespace(tasks=[], task=None)
        at = state.schedule_support_swap(solver, plan, end, level)
    assert at == end - timedelta(
        minutes=(300 + expected) * (1.05 + central / 100) / 1.65
    )
    assert abs((at - now).total_seconds() - route["switch_after"] * 3600) < 1


@pytest.mark.parametrize("configured", [0, 1, 5, 10, 45])
@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("central", [0, 5])
def test_smaller_and_larger_manual_buffers_are_preserved(level, central, configured):
    assert swap_buffer_minutes(level, configured, central=central) == configured


@pytest.mark.parametrize("central", [0, 5])
@pytest.mark.parametrize("inherited", [False, True])
def test_independent_custom_buffers_follow_actual_inheritance(central, inherited):
    configured = {"no_central": 4, "central": 7, "central_unhalved_m2": 6}
    route = stage_route(
        stat("教官", 60), stat("减半", 0, True), StageSpec(2, 8, central, configured)
    )
    plan = {
        "support_plan": {"stages": [route]},
        "support_runtime": {"level": 2, "half_inherited": inherited},
    }
    expected = 4 if not central else 7 if inherited else 6
    assert stage_for(plan, 2)["mastery_swap_buffer"] == expected
    assert stage_for(plan, 2)["configured_swap_buffer"] == configured


@pytest.mark.parametrize(
    "preview_inherited,actual_inherited", [(True, False), (False, True)]
)
def test_preparation_recalculates_buffer_from_observed_previous_stage(
    preview_inherited, actual_inherited
):
    first, reducer = stat("教官", 60), stat("艾丽妮", 0, True)
    planned = stage_route(
        first, reducer, StageSpec(2, 8 if preview_inherited else 16, 5)
    )
    now = datetime.now()
    previous = {
        "level": 1,
        "working_operator": "艾丽妮",
        "working_halves": True,
        "working_since": (now - timedelta(hours=6)).isoformat(),
        "working_until": (
            now - timedelta(minutes=5 if actual_inherited else 90)
        ).isoformat(),
    }
    plan = {
        "id": 1,
        "char_id": "target",
        "char_name": "学员",
        "support_plan": {"stages": [planned]},
        "support_runtime": previous,
    }
    with (
        patch.object(
            runtime,
            "candidates",
            return_value=({"教官": {2: first}, "艾丽妮": {2: reducer}}, 5),
        ),
        patch.object(runtime, "schedule_context", return_value=({}, 5)),
        patch.object(runtime, "_observed_support", return_value=("艾丽妮", "学员")),
        patch.object(
            runtime, "_follow_schedule", side_effect=lambda trainers, *_: trainers
        ),
        patch.object(runtime, "save_runtime") as save,
    ):
        runtime.prepare_plan_supports(MagicMock(), plan, 2)
    saved = save.call_args.args[1]
    assert saved["half_inherited"] is actual_inherited
    assert saved["mastery_swap_buffer"] == (15 if actual_inherited else 30)
    assert saved["configured_swap_buffer"] is None
    plan["support_runtime"] = saved
    assert stage_for(plan, 2)["mastery_swap_buffer"] == saved["mastery_swap_buffer"]


def test_logged_warfarin_countdown_passes_final_check_without_postponement():
    route = stage_route(stat("阿", 60), stat("艾丽妮", 0, True), StageSpec(2, 8, 5))
    execution = SimpleNamespace(
        route=route,
        level=2,
        plan={"target_level": 3},
        solver=MagicMock(),
        handoff=MagicMock(),
        collect=MagicMock(),
    )
    now = datetime(2026, 9, 12, 19, 49, 26)
    panel = SimpleNamespace(countdown=now + timedelta(hours=3, minutes=17, seconds=13))
    options = {"阿": {2: stat("阿", 60)}, "艾丽妮": {2: stat("艾丽妮", 0, True)}}
    with (
        patch.object(swap, "datetime") as clock,
        patch.object(swap, "confirm_training_panel", return_value=panel),
    ):
        clock.now.return_value = now
        swap._apply_swap(execution, "阿", options, 5)
    selected, delay, central = execution.handoff.call_args.args
    assert (selected["name"], delay, central) == ("艾丽妮", 0, 5)
    execution.collect.assert_not_called()
    legacy = {"efficiency": 60, "job_match": False, "central_bonus": 5}
    assert mastery._swap_worthwhileness(197 + 13 / 60, legacy)


@pytest.mark.parametrize("central", [0, 5])
@pytest.mark.parametrize("efficiency", [30, 60, 95])
@pytest.mark.parametrize("reducer_efficiency", [0, 30])
@pytest.mark.parametrize("tail,allowed", [(300.5, False), (301.5, True)])
def test_final_check_threshold_counts_same_central_bonus_on_both_sides(
    central, efficiency, reducer_efficiency, tail, allowed
):
    speed = 1.05 + (efficiency + central) / 100
    dest = 1.05 + (reducer_efficiency + central) / 100
    remaining = tail * dest / speed
    selected, _ = state.select_swap_support(
        remaining * 60 * speed,
        speed,
        [stat("减半", reducer_efficiency, True)],
        (central, 15),
        schedule_rate=1.05 + efficiency / 100,
    )
    route = {
        "efficiency": efficiency,
        "central_bonus": central,
        "job_match": bool(reducer_efficiency),
    }
    assert (selected is not None) is allowed
    assert mastery._swap_worthwhileness(remaining, route) is allowed
    assert (
        mastery.calc_swap_threshold(
            efficiency, bool(reducer_efficiency), central, remaining, 15
        )[0]
        is allowed
    )


@pytest.mark.parametrize("central", [0, 5])
def test_nominal_final_check_does_not_delay_the_conservative_deadline(central):
    speed = 1.65 + central / 100
    dest = 1.05 + central / 100
    remaining = 315 * dest / 1.65
    selected, delay = state.select_swap_support(
        remaining * 60 * speed,
        speed,
        [stat("减半", 0, True)],
        (central, 15),
        schedule_rate=1.65,
    )
    assert selected is not None
    assert delay == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("level,work", [(1, 480), (2, 480), (2, 960)])
@pytest.mark.parametrize("central", [0, 5])
@pytest.mark.parametrize("reducer_efficiency", [0, 30])
def test_default_margin_covers_five_minute_operation_estimate(
    level, work, central, reducer_efficiency
):
    # Five minutes is a verification assumption, not a scheduler timeout. Use
    # the worst central transition: absent at the initial read, then always on.
    buffer = swap_buffer_minutes(
        level, central=central, inherited=work == 480 and level == 2
    )
    for efficiency in range(30, 96):
        first = 1.05 + efficiency / 100
        dest = 1.05 + (reducer_efficiency + central) / 100
        scheduled = work / first - (300 + buffer) * dest / first
        actual_work = work - (first + central / 100) * (scheduled + 5)
        assert actual_work / dest > 300


def test_zero_custom_buffer_keeps_existing_one_minute_execution_margin():
    configured = {key: 0 for key in DEFAULT_SWAP_BUFFERS}
    route = stage_route(
        stat("教官", 60), stat("减半", 0, True), StageSpec(2, 8, 5, configured)
    )
    plan = {"support_plan": {"stages": [route]}}
    assert route["configured_swap_buffer"] == configured
    assert route["mastery_swap_buffer"] == 1
    assert stage_for(plan, 2)["mastery_swap_buffer"] == 1
