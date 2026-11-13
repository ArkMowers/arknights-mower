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


@pytest.fixture(autouse=True)
def disable_wait_notifications(monkeypatch):
    monkeypatch.setattr(db, "should_notify", lambda *a: False)


def stage(level, name="快教官", efficiency=100, **extra):
    return {"level": level, "operator": name, "efficiency": efficiency, **extra}


def moods(**values):
    return SimpleNamespace(
        operators={},
        dorm_mood_estimates={
            name: (mood, datetime.now()) for name, mood in values.items()
        },
    )


def test_current_stage_budgets_one_assistants_duty_without_central_bonus():
    routes = [stage(level, central_bonus=5) for level in (1, 2, 3)]
    required = support_mood_requirements(routes[0])
    assert required == {"快教官": pytest.approx(8 / 2.05)}
    solver = SimpleNamespace(op_data=moods(快教官=8 / 2.10))
    with pytest.raises(SupportMoodWait, match="快教官"):
        require_support_mood(solver, routes[0])
    solver.op_data = moods(快教官=8 / 2.05)
    require_support_mood(solver, routes[0])


def test_reducer_duty_does_not_include_future_stages():
    routes = [stage(level, "艾丽妮", 30) for level in (1, 2, 3)]
    assert support_mood_requirements(routes[0]) == {"艾丽妮": pytest.approx(8 / 1.35)}


def test_swap_and_primary_duty_are_budgeted_separately():
    routes = [
        stage(1, swap_target="艾丽妮", swap_efficiency=30, configured_swap_buffer=10),
        stage(2, swap_target="艾丽妮", swap_efficiency=30, configured_swap_buffer=10),
        stage(3),
    ]
    required = support_mood_requirements(routes[0])
    tail = 5 + 10 / 60
    first = (8 - tail * 1.35) / 2.05
    assert required["艾丽妮"] == pytest.approx(tail, abs=0.001)
    assert required["快教官"] == pytest.approx(first, abs=0.001)


def test_saved_halving_does_not_replace_confirmed_carry():
    route = stage(3, half_inherited=True, central_bonus=5)
    assert support_mood_requirements(route)["快教官"] == pytest.approx(24 / 2.05)
    assert support_mood_requirements(route, inherited=True)["快教官"] == pytest.approx(
        12 / 2.05
    )


@pytest.mark.parametrize("value", [None, -1, float("nan")])
def test_unknown_or_invalid_list_mood_does_not_allow_training(value):
    with pytest.raises(SupportMoodWait):
        require_support_mood(SimpleNamespace(op_data=moods(快教官=value)), stage(1))


@pytest.mark.parametrize(
    "follow,replacement_mood", [(False, None), (True, 24), (True, 1), (False, 24)]
)
@pytest.mark.parametrize("legacy_wait", [False, True])
def test_start_wait_retains_plan_task_and_releases_only_with_enough_mood(
    database, monkeypatch, follow, replacement_mood, legacy_wait
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
        if legacy_wait:
            restored.mastery_mood_wait["required"] = {"艾丽妮": 35.56}
            restored.mastery_mood_wait["context"].pop("mood_scope")
            solver.task, solver.tasks = restored, [restored, other]
            task = restored
            resume()
            assert task.time == at and not hasattr(task, "execution_failure")
            mastery._start_new_training(solver, db.get_plan_by_id(pid), room=room)
            assert task.mastery_mood_wait["required"] == {
                "艾丽妮": pytest.approx(8 / 1.35)
            }
            assert task.execution_failure
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
            if follow or replacement_mood == 24:
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
@pytest.mark.parametrize("later_mood", [None, 1])
def test_real_preparation_only_requires_current_assistants_or_schedule_occupant(
    monkeypatch, follow, later_mood
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
    solver = SimpleNamespace(op_data=moods(快教官=24, 后续教官=later_mood, 排班教官=1))
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
    if follow:
        with pytest.raises(SupportMoodWait) as wait:
            mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        assert set(wait.value.required) == {"排班教官"}
        save.assert_not_called()
    else:
        mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
        assert save.call_args.args[1]["central_bonus"] == 5
        solver.op_data = moods(快教官=1, 后续教官=later_mood, 排班教官=1)
        with pytest.raises(SupportMoodWait) as wait:
            mastery_support_runtime.prepare_plan_supports(solver, plan, 2)
        assert set(wait.value.required) == {"后续教官"}
    solver.op_data = moods(快教官=24, 后续教官=24, 排班教官=24)
    mastery_support_runtime.prepare_plan_supports(solver, plan, 2)
    assert save.call_args.args[1]["level"] == 2


def test_legacy_route_uses_the_same_current_stage_mood_gate(monkeypatch):
    plan = {"id": 1, "char_id": "trainee", "char_name": "学员", "target_level": 3}
    monkeypatch.setattr(mastery, "_get_plan_route", lambda p, level: stage(level))
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: ("快教官", "学员")
    )
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=False),
    )
    monkeypatch.setattr(mastery_support_runtime, "candidates", lambda *a, **k: ({}, 0))
    with pytest.raises(SupportMoodWait) as wait:
        mastery_support_runtime.prepare_legacy_support_mood(
            SimpleNamespace(op_data=moods(快教官=1)), plan, 1
        )
    assert wait.value.required["快教官"] == pytest.approx(8 / 2.05)


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
    required = support_mood_requirements(route)
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
    mastery_support_runtime.prepare_plan_supports(solver, plan, 1)
    assert save.call_args.args[1]["operator"] == first_name
    save.reset_mock()
    if not allowed:
        with pytest.raises(
            mastery_support_runtime.SupportPlanError, match="计划协助者已不可用"
        ):
            mastery_support_runtime.prepare_plan_supports(solver, plan, 2)
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
            mastery_support_runtime.prepare_plan_supports(solver, plan, blocked_level)
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


@pytest.mark.parametrize(
    "level,needed", [(1, 8 / 1.35), (2, 16 / 1.35), (3, 24 / 1.35)]
)
@pytest.mark.parametrize("legacy", [False, True])
def test_each_stage_admits_full_mood_without_budgeting_later_stages(
    monkeypatch, level, needed, legacy
):
    routes = [stage(i, "格拉尼", 30) for i in (1, 2, 3)]
    plan = {
        "id": 1,
        "char_id": "trainee",
        "char_name": "学员",
        "target_level": 3,
        "support_plan": {"stages": routes},
    }
    options = {
        "格拉尼": {
            i: {"name": "格拉尼", "efficiency": 30, "halves": False} for i in (1, 2, 3)
        }
    }
    monkeypatch.setattr(
        mastery_support_runtime, "candidates", lambda *a, **k: (options, 5)
    )
    monkeypatch.setattr(mastery_support_runtime, "schedule_context", lambda: ({}, 5))
    monkeypatch.setattr(
        mastery_support_runtime, "_observed_support", lambda _: ("格拉尼", "学员")
    )
    monkeypatch.setattr(mastery_support_runtime, "halving_successor", lambda *a: None)
    monkeypatch.setattr(
        mastery_support_runtime, "basic_mastery_successor", lambda *a: False
    )
    monkeypatch.setattr(mastery_support_runtime, "save_runtime", Mock())
    monkeypatch.setattr(mastery, "_get_plan_route", lambda p, i: routes[i - 1])
    monkeypatch.setattr(
        "arknights_mower.utils.config.conf",
        SimpleNamespace(assistant_follows_schedule=False),
    )
    prepare = (
        mastery_support_runtime.prepare_legacy_support_mood
        if legacy
        else mastery_support_runtime.prepare_plan_supports
    )
    solver = SimpleNamespace(op_data=moods(格拉尼=24))
    prepare(solver, plan, level)
    solver.op_data = moods(格拉尼=needed - 0.1)
    with pytest.raises(SupportMoodWait) as wait:
        prepare(solver, plan, level)
    assert wait.value.required == {"格拉尼": pytest.approx(needed)}
    solver.op_data = moods(格拉尼=needed)
    prepare(solver, plan, level)


@pytest.mark.parametrize("calculated", [False, True])
@pytest.mark.parametrize("observed", [None, 1, 24])
def test_unknown_current_assistant_observed_once_before_wait(
    monkeypatch, calculated, observed
):
    solver = SimpleNamespace(op_data=moods(), task=SimpleNamespace())
    solver.op_data.mood_calculation_enabled = calculated
    solver.op_data.calculated_mood = lambda *a: None

    def scan(**kwargs):
        assert kwargs == {"mastery": True}
        if observed is not None:
            solver.op_data.dorm_mood_estimates["快教官"] = (observed, datetime.now())

    solver._scan_card_moods = Mock(side_effect=scan)
    solver.enter_room = Mock()
    for _ in range(3):
        if observed == 24:
            mastery_support_runtime._require_stage_mood(
                solver, stage(2), inherited=False
            )
        else:
            with pytest.raises(SupportMoodWait) as wait:
                mastery_support_runtime._require_stage_mood(
                    solver, stage(2), inherited=False
                )
            assert wait.value.shortages == {"快教官": observed}
    solver._scan_card_moods.assert_called_once()
    solver.enter_room.assert_called_once_with("train", max_attempts=1)


def test_stale_card_mood_remains_unknown_in_calculation_mode():
    from arknights_mower.utils.mastery_mood import support_mood_shortages

    data = moods(快教官=24)
    data.mood_calculation_enabled = True
    data.calculated_mood = lambda *a: None
    data.dorm_mood_estimates["快教官"] = (24, datetime.now() - timedelta(hours=2))
    assert support_mood_shortages(data, {"快教官": 5}) == {"快教官": None}


def test_wait_reports_unknown_mood_and_deduplicates_notifications(monkeypatch):
    send = Mock()
    warning = Mock()
    notify = Mock(side_effect=[True, False])
    monkeypatch.setattr("arknights_mower.utils.email.send_message", send)
    monkeypatch.setattr(mastery.logger, "warning", warning)
    monkeypatch.setattr(db, "should_notify", notify)
    plan = {"id": 1, "char_name": "学员", "skill_index": 0, "target_level": 2}
    error = SupportMoodWait({"快教官": 8}, {"快教官": None})
    for _ in range(2):
        mastery._notify_support_mood_wait(plan, error)
    send.assert_called_once()
    assert "确认心情" in send.call_args.args[0]
    assert "宿舍" in send.call_args.args[0]
    assert warning.call_count == 2
    assert notify.call_args_list[0] == notify.call_args_list[1]


def test_interrupted_observation_preserves_next_attempt():
    from arknights_mower.utils.csleep import MowerExit

    solver = SimpleNamespace(op_data=moods(), task=SimpleNamespace(), enter_room=Mock())
    solver._scan_card_moods = Mock(side_effect=MowerExit())
    with pytest.raises(MowerExit):
        mastery_support_runtime._require_stage_mood(solver, stage(1), inherited=False)
    assert not hasattr(solver.task, "mastery_mood_observation")
    solver.enter_room.assert_not_called()
