"""实时心情计算沿用普通下班阈值，旧版提前任务回归当前规划。"""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.mood_calculation_projection_consumers_tests import (
    enable,
    observations,
)
from arknights_mower.utils import calculated_mood
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def configure(solver, monkeypatch, *, mood=10, threshold=0.5, calculated=True):
    data = solver.op_data
    data.config.resting_threshold = threshold
    data.operators[PRIMARY[0]].mood = mood
    solver.total_agent = list(data.operators.values())
    solver.backup_plan_solver = MagicMock()
    if calculated:
        enable(data, NOW, monkeypatch)
    return data


def legacy_departure(*, time=NOW):
    task = SchedulerTask(
        time=time,
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "room_1_1": [COVERS[0]],
            "dormitory_1": ["Current", "Current", PRIMARY[0], "Current", "Current"],
        },
    )
    task.ordinary_coordination = True
    task.coordination_request_names = [PRIMARY[0]]
    task.mood_control_evidence = {"group": PRIMARY[0]}
    return task


def enter_home(solver):
    # 在首页识别前停止，入口清理仍经过真实 infra_main。
    solver.find = MagicMock(return_value=None)
    solver.back = MagicMock()
    solver.infra_main()


def test_scarce_shared_replacement_never_generates_early_departure(solver, monkeypatch):
    data = configure(solver, monkeypatch, threshold=0, calculated=False)
    for name in PRIMARY[2:]:
        data.operators[name].workaholic = True
    for index, name in enumerate(PRIMARY[:2]):
        op = data.operators[name]
        op.mood = 2 + index
        op.replacement = [COVERS[0]]
        op.rest_in_full = True
    data.dorm = data.dorm[:1]

    def rates(payload):
        result = {name: 0 for name in payload["moods"]}
        for room, state in payload["rooms"].items():
            for name in state["roster"]:
                if name in (*PRIMARY[:2], COVERS[0]):
                    result[name] = -24 if room.startswith("dorm") else 1
        return dict(rates=result, thresholds=[0, 24], automaticTargets={})

    monkeypatch.setattr(calculated_mood, "shared_rates", rates)
    enable(data, NOW, monkeypatch)
    before = data.mood_model.at, observations(data)
    for _ in range(2):
        assert solver.resting() == {}
        assert not any(
            task.type == TaskTypes.SHIFT_OFF
            or getattr(task, "mood_control_event", None)
            or getattr(task, "mood_control_evidence", None)
            for task in solver.tasks
        )
    assert (data.mood_model.at, observations(data)) == before
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("calculated", [False, True], ids=["observed", "calculated"])
@pytest.mark.parametrize("mood,expected", [(23, False), (10, True)])
def test_ordinary_rotation_uses_existing_threshold(
    solver, monkeypatch, calculated, mood, expected
):
    data = configure(solver, monkeypatch, mood=mood, calculated=calculated)
    result = solver.resting()
    departures = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert bool(departures) is expected
    assert bool(result) is expected
    if expected:
        assert (
            data.operators[PRIMARY[0]].lower_limit
            < mood
            <= data.resting_mood_threshold(data.operators[PRIMARY[0]])
        )
        assert departures[0].ordinary_coordination
        assert departures[0].coordination_request_names == [PRIMARY[0]]
        assert not hasattr(departures[0], "mood_control_evidence")
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "protection,value",
    [
        ("backup_shift_active", True),
        ("backup_explicit_slots", (("room_1_1", 0),)),
        ("product_shift_locked", True),
        ("group_shift_expected", {"old": True}),
    ],
)
def test_home_entry_discards_unstarted_early_intent_even_with_legacy_protection(
    solver, monkeypatch, protection, value
):
    configure(solver, monkeypatch, mood=23)
    old = legacy_departure()
    setattr(old, protection, value)
    solver.tasks, solver.task, solver.planned = [old], old, True
    enter_home(solver)
    assert old not in solver.tasks
    assert solver.task is None and not solver.planned
    assert solver.resting() == {}
    assert not any(task.type == TaskTypes.SHIFT_OFF for task in solver.tasks)
    solver.enter_room.assert_not_called()


def test_home_entry_rebuilds_legacy_intent_at_ordinary_threshold(solver, monkeypatch):
    data = configure(solver, monkeypatch)
    old = legacy_departure(time=NOW + timedelta(hours=1))
    solver.tasks, solver.task, solver.planned = [old], old, True
    enter_home(solver)
    assert old not in solver.tasks and solver.task is None and not solver.planned
    assert data.operators[PRIMARY[0]].lower_limit < 10
    assert solver.resting()
    replacement = next(
        task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF
    )
    assert replacement is not old and replacement.time == NOW
    assert replacement.coordination_request_names == [PRIMARY[0]]
    assert not hasattr(replacement, "mood_control_evidence")
    assert solver._prepare_ordinary_departure(replacement)
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("protection", ["started", "retained", "failed"])
@pytest.mark.parametrize("calculated", [False, True], ids=["observed", "calculated"])
def test_home_entry_preserves_started_or_retained_intent_and_original_time(
    solver, monkeypatch, protection, calculated
):
    configure(solver, monkeypatch, mood=23, calculated=calculated)
    old = legacy_departure(time=NOW - timedelta(hours=1))
    if protection == "started":
        old.mood_physical_started = True
    elif protection == "retained":
        old.execution_retained = True
    else:
        old.execution_failure = {"reason": "等待相关观测"}
    wake = SchedulerTask(time=NOW + timedelta(hours=2))
    wake.mood_control_event = {"at": wake.time.timestamp()}
    special = SchedulerTask(
        time=NOW + timedelta(hours=3), task_type=TaskTypes.SKILL_UPGRADE
    )
    solver.tasks, solver.task = [old, wake, special], old
    before = old.time, deepcopy(old.plan)
    enter_home(solver)
    assert solver.tasks == [old, special]
    assert solver.task is old and (old.time, old.plan) == before
    assert solver._prepare_ordinary_departure(old)
    solver.enter_room.assert_not_called()
