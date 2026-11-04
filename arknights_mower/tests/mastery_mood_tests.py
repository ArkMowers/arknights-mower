"""Assistant endurance gates use cached moods and retain the original start task."""

import pickle
import sys
from datetime import datetime, timedelta
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from arknights_mower.solvers import mastery, mastery_support_runtime
from arknights_mower.tests.mastery_support_fixtures import context_game as context_game
from arknights_mower.tests.mastery_support_fixtures import database as database
from arknights_mower.tests.mastery_support_fixtures import game as game
from arknights_mower.tests.mastery_support_fixtures import owned
from arknights_mower.tests.mastery_support_start_tests import scene_solver
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support_data
from arknights_mower.utils.mastery_mood import (
    SupportMoodWait,
    require_support_mood,
    support_mood_requirements,
)
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)


def stage(level, name="快教官", efficiency=100, **extra):
    return {"level": level, "operator": name, "efficiency": efficiency, **extra}


def moods(**values):
    return SimpleNamespace(
        operators={},
        dorm_mood_estimates={
            name: (mood, datetime.now()) for name, mood in values.items()
        },
    )


def test_complete_skill_accumulates_one_assistants_duty_without_central_bonus():
    routes = [stage(level, central_bonus=5) for level in (1, 2, 3)]
    required = support_mood_requirements(routes)
    assert required == {"快教官": pytest.approx(48 / 2.05)}
    solver = SimpleNamespace(op_data=moods(快教官=48 / 2.10))
    with pytest.raises(SupportMoodWait, match="快教官"):
        require_support_mood(solver, routes)
    solver.op_data = moods(快教官=48 / 2.05)
    require_support_mood(solver, routes)


def test_reducer_duty_and_earned_halving_accumulate_across_stages():
    routes = [stage(level, "艾丽妮", 30) for level in (1, 2, 3)]
    assert support_mood_requirements(routes) == {
        "艾丽妮": pytest.approx((8 + 8 + 12) / 1.35)
    }


def test_swap_and_primary_duty_are_budgeted_separately():
    routes = [
        stage(1, swap_target="艾丽妮", swap_efficiency=30, configured_swap_buffer=10),
        stage(2, swap_target="艾丽妮", swap_efficiency=30, configured_swap_buffer=10),
        stage(3),
    ]
    required = support_mood_requirements(routes)
    tail = 5 + 10 / 60
    first = (8 - tail * 1.35) / 2.05
    assert required["艾丽妮"] == pytest.approx(2 * tail, abs=0.001)
    assert required["快教官"] == pytest.approx(first * 2 + 12 / 2.05, abs=0.001)


def test_saved_halving_does_not_replace_confirmed_carry():
    route = stage(3, half_inherited=True, central_bonus=5)
    assert support_mood_requirements([route])["快教官"] == pytest.approx(24 / 2.05)
    assert support_mood_requirements([route], inherited=True)[
        "快教官"
    ] == pytest.approx(12 / 2.05)


@pytest.mark.parametrize("value", [None, -1, float("nan")])
def test_unknown_or_invalid_list_mood_does_not_allow_training(value):
    with pytest.raises(SupportMoodWait):
        require_support_mood(SimpleNamespace(op_data=moods(快教官=value)), [stage(1)])


@pytest.mark.parametrize(
    "follow,replacement_mood", [(False, None), (True, 24), (True, 1), (False, 24)]
)
def test_start_wait_retains_plan_task_and_releases_only_with_enough_mood(
    database, monkeypatch, follow, replacement_mood
):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.operators import Operator

    route = stage(1, "艾丽妮", 30)
    pid = db.insert_plan(
        "char_fixture", 0, 1, char_name="能天使", support_plan={"stages": [route]}
    )
    plan = db.get_plan_by_id(pid)
    solver, events = scene_solver(Scene.TRAIN_MAIN, True)
    solver.op_data = moods(艾丽妮=1, 新协助=1)
    solver.op_data.operators = {
        "艾丽妮": Operator("艾丽妮", "", current_room="train", current_index=0),
        "新协助": Operator("新协助", ""),
    }
    occupant = ["艾丽妮"]
    read_slots = solver.get_agent_from_room.side_effect

    def observed_slots(room):
        rows = read_slots(room)
        if rows:
            rows[0]["agent"] = occupant[0]
        return rows

    solver.get_agent_from_room.side_effect = observed_slots
    at = datetime.now() - timedelta(minutes=1)
    task = SchedulerTask(at, task_type=TaskTypes.SKILL_UPGRADE)
    task.plan_key = str(pid)
    other = SchedulerTask(at, task_type=TaskTypes.NOT_SPECIFIC)
    solver.task, solver.tasks = task, [task, other]
    solver._task_failure_snapshot = Mock(return_value={})
    solver._retain_failed_task = MethodType(
        base_schedule.BaseSchedulerSolver._retain_failed_task, solver
    )
    solver._discard_legacy_ordinary_requests = Mock()
    solver._discard_legacy_recovery_checks = Mock()
    solver._discard_legacy_run_order_waits = Mock()
    solver._is_startup_priority_task = Mock(return_value=False)
    solver._initial_fia_checked = False
    resume = MethodType(base_schedule.BaseSchedulerSolver._resume_failed_tasks, solver)
    monkeypatch.setattr(
        mastery_support_runtime,
        "candidates",
        lambda *a, **k: (
            {
                "艾丽妮": {
                    level: {"name": "艾丽妮", "efficiency": 30, "halves": True}
                    for level in (1, 2, 3)
                },
                "新协助": {
                    level: {"name": "新协助", "efficiency": 100, "halves": False}
                    for level in (1, 2, 3)
                },
            },
            5,
        ),
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_mastery_requirement_error",
        lambda *a: None,
    )
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
        lambda *a: None,
    )
    monkeypatch.setattr(mastery_support_runtime, "schedule_context", lambda: ({}, 5))
    room = SimpleNamespace(train_slot="能天使", slots_reliable=True)
    with (
        patch.object(mastery, "_read_train_countdown3", return_value=("failed", None)),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slot_mastery_tier",
            return_value=0,
        ),
        patch(
            "arknights_mower.utils.config.conf",
            SimpleNamespace(assistant_follows_schedule=follow),
        ),
        patch.object(
            mastery, "_confirm_training_started", return_value="started"
        ) as confirm,
    ):
        mastery._start_new_training(solver, plan, room=room)
        assert db.get_plan_by_id(pid)["status"] == "idle"
        assert "恢复心情" in db.get_plan_by_id(pid)["failed_reason"]
        assert db.get_plan_by_id(pid)["support_runtime"] is None
        assert task.time == at and task.execution_failure["dependency"]
        solver.ctap.assert_not_called()
        confirm.assert_not_called()
        # Serialization preserves the exact task time and remaining requirement.
        restored = pickle.loads(pickle.dumps(task))
        assert (
            restored.time == at and restored.mastery_mood_wait == task.mastery_mood_wait
        )
        for _ in range(3):
            resume()
            assert task.execution_failure and task.time == at
            assert task_view(solver.tasks, TaskScope.DISPATCH) == [other]
        solver.op_data.dorm_mood_estimates["其他干员"] = (24, datetime.now())
        resume()
        assert task.execution_failure
        if replacement_mood is not None:
            solver.op_data.operators["艾丽妮"].current_room = ""
            solver.op_data.operators["艾丽妮"].current_index = -1
            solver.op_data.operators["新协助"].current_room = "train"
            solver.op_data.operators["新协助"].current_index = 0
            solver.op_data.dorm_mood_estimates["新协助"] = (
                replacement_mood,
                datetime.now(),
            )
            occupant[0] = "新协助"
            resume()
            if follow:
                assert not hasattr(task, "execution_failure")
                assert task.time == at and solver.tasks == [task, other]
                mastery._start_new_training(solver, db.get_plan_by_id(pid), room=room)
                if replacement_mood == 24:
                    confirm.assert_called_once()
                    return
                assert set(task.mastery_mood_wait["required"]) == {"新协助"}
                assert task.mastery_mood_wait["required"]["新协助"] == pytest.approx(
                    8 / 2.05
                )
                for _ in range(3):
                    resume()
                    assert task.execution_failure and task.time == at
                    assert task_view(solver.tasks, TaskScope.DISPATCH) == [other]
                solver.op_data.dorm_mood_estimates["新协助"] = (
                    8 / 2.05,
                    datetime.now(),
                )
            else:
                assert task.execution_failure
                solver.op_data.dorm_mood_estimates["艾丽妮"] = (
                    8 / 1.35,
                    datetime.now(),
                )
        else:
            solver.op_data.dorm_mood_estimates["艾丽妮"] = (8 / 1.35, datetime.now())
        resume()
        assert not hasattr(task, "execution_failure")
        assert task.time == at and solver.tasks == [task, other]
        mastery._start_new_training(solver, db.get_plan_by_id(pid), room=room)
        confirm.assert_called_once()
        assert events[-2:] == ["select", "confirm"]


@pytest.mark.parametrize("follow", [False, True])
def test_real_preparation_requires_later_assistants_and_schedule_occupant(
    monkeypatch, follow
):
    plan = {
        "id": 1,
        "char_id": "trainee",
        "char_name": "学员",
        "target_level": 3,
        "support_plan": {
            "stages": [
                stage(level, "快教官" if level != 2 else "后续教官")
                for level in (1, 2, 3)
            ]
        },
    }
    options = {
        name: {
            level: {"name": name, "efficiency": 100, "halves": False}
            for level in (1, 2, 3)
        }
        for name in ("快教官", "后续教官", "排班教官")
    }
    solver = SimpleNamespace(op_data=moods(快教官=24, 后续教官=1, 排班教官=1))
    monkeypatch.setattr(
        mastery_support_runtime, "candidates", lambda *a, **k: (options, 5)
    )
    monkeypatch.setattr(mastery_support_runtime, "schedule_context", lambda: ({}, 5))
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: ("排班教官", "学员")
    )
    monkeypatch.setattr(mastery_support_runtime, "halving_successor", lambda *a: None)
    monkeypatch.setattr(
        mastery_support_runtime, "basic_mastery_successor", lambda *a: False
    )
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=follow),
    )
    save = Mock()
    monkeypatch.setattr(mastery_support_runtime, "save_runtime", save)
    with pytest.raises(SupportMoodWait) as wait:
        mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
    assert set(wait.value.required) == (
        {"排班教官"} if follow else {"快教官", "后续教官"}
    )
    save.assert_not_called()
    solver.op_data = moods(快教官=24, 后续教官=24, 排班教官=24)
    mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
    assert save.call_args.args[1]["central_bonus"] == 5


def test_legacy_route_uses_the_same_complete_skill_mood_gate(monkeypatch):
    plan = {"id": 1, "char_id": "trainee", "char_name": "学员", "target_level": 3}
    monkeypatch.setattr(mastery, "_get_plan_route", lambda p, level: stage(level))
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: ("快教官", "学员")
    )
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=False),
    )
    with pytest.raises(SupportMoodWait) as wait:
        mastery_support_runtime.prepare_legacy_support_mood(
            SimpleNamespace(op_data=moods(快教官=10)), plan, 1
        )
    assert wait.value.required["快教官"] == pytest.approx(48 / 2.05)


def test_central_speed_is_excluded_while_explicit_swap_margin_is_preserved():
    route = stage(
        2,
        swap_target="艾丽妮",
        swap_efficiency=30,
        central_bonus=5,
        configured_swap_buffer={
            "no_central": 1,
            "central": 20,
            "central_unhalved_m2": 40,
        },
    )
    required = support_mood_requirements([route])
    assert required["艾丽妮"] == pytest.approx(5 + 40 / 60, abs=0.001)
    assert required["快教官"] == pytest.approx(
        (16 - (5 + 40 / 60) * 1.35) / 2.05, abs=0.001
    )


@pytest.mark.parametrize(
    "first_manual,second_manual,first_name,second_name,allowed",
    [
        (False, True, "假日威龙陈", "左乐", True),
        (True, False, "左乐", "假日威龙陈", True),
        (True, False, "左乐", "左乐", False),
    ],
)
def test_each_remaining_stage_uses_its_own_candidate_policy(
    database,
    context_game,
    monkeypatch,
    first_manual,
    second_manual,
    first_name,
    second_name,
    allowed,
):
    _, ids = context_game
    roster = [owned(ids[name]) for name in ("能天使", "假日威龙陈", "左乐")]
    monkeypatch.setattr(mastery_support_data, "owned_roster", lambda: roster)
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=False),
    )
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: (first_name, "能天使")
    )
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 2,
        "support_plan": {
            "stages": [
                stage(1, first_name, manual=first_manual),
                stage(2, second_name, manual=second_manual),
            ]
        },
    }
    solver = SimpleNamespace(op_data=moods(假日威龙陈=24, 左乐=24))
    save = Mock()
    monkeypatch.setattr(mastery_support_runtime, "save_runtime", save)
    if not allowed:
        with pytest.raises(
            mastery_support_runtime.SupportPlanError, match="计划协助者已不可用"
        ):
            mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        save.assert_not_called()
        return
    mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
    assert save.call_args.args[1]["operator"] == first_name
    mastery_support_runtime.prepare_plan_supports(solver, plan, 2)
    assert save.call_args.args[1]["operator"] == second_name


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("blocked_level", [1, 2])
@pytest.mark.parametrize("occupant", ["假日威龙陈", "左乐"])
@pytest.mark.parametrize("mood", [1, 24])
def test_follow_schedule_ignores_saved_assistants_but_checks_occupant_mood(
    database, context_game, monkeypatch, follow, blocked_level, occupant, mood
):
    _, ids = context_game
    roster = [owned(ids[name]) for name in ("能天使", "假日威龙陈", "左乐", "艾丽妮")]
    monkeypatch.setattr(mastery_support_data, "owned_roster", lambda: roster)
    monkeypatch.setattr(
        mastery_support_runtime,
        "schedule_context",
        lambda: ({"艾丽妮": {"room_1_1"}}, 0),
    )
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=follow),
    )
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: (occupant, "能天使")
    )
    plan = {
        "id": 1,
        "char_id": ids["能天使"],
        "char_name": "能天使",
        "target_level": 2,
        "support_plan": {
            "stages": [
                stage(
                    level,
                    "艾丽妮" if level == blocked_level else "假日威龙陈",
                    manual=False,
                )
                for level in (1, 2)
            ]
        },
    }
    solver = SimpleNamespace(op_data=moods(**{occupant: mood}))
    save = Mock()
    monkeypatch.setattr(mastery_support_runtime, "save_runtime", save)
    if not follow:
        with pytest.raises(
            mastery_support_runtime.SupportPlanError, match="计划协助者已不可用"
        ):
            mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        save.assert_not_called()
    elif mood == 1:
        with pytest.raises(SupportMoodWait) as wait:
            mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        assert set(wait.value.required) == {occupant}
        assert wait.value.required[occupant] > 1
        save.assert_not_called()
    else:
        mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        prepared = save.call_args.args[1]
        assert prepared["operator"] == occupant
        assert prepared["swap_target"] is None
