"""救急交接和轮休预演固定时间，并在计算期间响应取消。"""

from copy import deepcopy
from datetime import timedelta
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import emergency
from arknights_mower.tests.automatic_rescue_tests import make_episode
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.mood_calculation_projection_consumers_tests import (
    enable,
    observations,
)
from arknights_mower.utils import calculated_mood, config, emergency_recovery
from arknights_mower.utils.csleep import MowerExit, cancellation_scope
from arknights_mower.utils.emergency_recovery import NativeProjection
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture(autouse=True)
def cancellation(monkeypatch):
    stop = Event()
    monkeypatch.setattr(config, "stop_mower", stop)
    return stop


def test_ready_rescue_tick_hands_off_before_future_rotation(solver):
    state = make_episode(solver)
    state["next_read"] = state["observed_at"] = NOW
    solver._emergency_update_targets = MagicMock(
        side_effect=AssertionError("已满足交接条件时不应搜索未来轮休")
    )
    solver._emergency_restore = MagicMock(return_value=True)

    solver._emergency_tick()

    solver._emergency_restore.assert_called_once()
    solver._emergency_update_targets.assert_not_called()
    solver.enter_room.assert_not_called()


def test_incomplete_handoff_is_attempted_once_per_tick(solver):
    state = make_episode(solver)
    state["next_read"] = state["observed_at"] = NOW
    pending = SchedulerTask(time=NOW + timedelta(hours=1), task_type=TaskTypes.DEPOT)
    solver.tasks = [pending]

    def defer_handoff():
        state.update(phase="returning", handoff_plan={})
        return False

    solver._emergency_restore = MagicMock(side_effect=defer_handoff)
    solver._emergency_defer_read = MagicMock()

    solver._emergency_tick()

    solver._emergency_restore.assert_called_once()
    assert state["phase"] == "returning"
    assert any(task is pending for task in solver.tasks)
    assert pending.time == NOW + timedelta(hours=1)


@pytest.mark.parametrize("during", [False, True])
def test_native_search_propagates_stop_without_changing_live_state(
    solver, monkeypatch, cancellation, during
):
    before = observations(solver.op_data)
    if during:
        plan = type(solver).get_resting_plan

        def stop_after_candidate(candidate, *args, **kwargs):
            result = plan(candidate, *args, **kwargs)
            cancellation.set()
            return result

        monkeypatch.setattr(type(solver), "get_resting_plan", stop_after_candidate)
    else:
        cancellation.set()

    with pytest.raises(MowerExit):
        emergency_recovery.native_opportunity(
            solver, PRIMARY[:3], NOW, current_only=True
        )

    assert observations(solver.op_data) == before
    solver.enter_room.assert_not_called()


def test_native_search_propagates_candidate_exit(solver, monkeypatch):
    def cancelled(*args, **kwargs):
        raise MowerExit

    monkeypatch.setattr(type(solver), "get_resting_plan", cancelled)
    with pytest.raises(MowerExit):
        emergency_recovery.native_opportunity(solver, PRIMARY[:1], NOW)


def test_native_search_uses_scoped_cancellation(solver, cancellation):
    cancellation.set()
    with cancellation_scope(lambda: False):
        result = emergency_recovery.native_opportunity(solver, PRIMARY[:1], NOW)
    assert result.complete and result.opportunity == NOW
    assert cancellation.is_set()
    with cancellation_scope(lambda: True), pytest.raises(MowerExit):
        emergency_recovery.native_opportunity(solver, PRIMARY[:1], NOW)


def test_native_search_pins_candidate_queries_to_node_time(solver, monkeypatch):
    enable(solver.op_data, NOW, monkeypatch)
    before = deepcopy(vars(solver.op_data.mood_model)), observations(solver.op_data)
    plan = type(solver).get_resting_plan
    times = []

    def inspect(candidate, *args, **kwargs):
        at = getattr(candidate.op_data, "_projection_now", None)
        times.append(at)
        assert at == NOW
        assert all(
            op._projection_now == NOW for op in candidate.op_data.operators.values()
        )
        return plan(candidate, *args, **kwargs)

    monkeypatch.setattr(type(solver), "get_resting_plan", inspect)
    result = emergency_recovery.native_opportunity(solver, PRIMARY[:2], NOW)

    assert times and result.complete and result.opportunity == NOW
    assert (vars(solver.op_data.mood_model), observations(solver.op_data)) == before
    solver.enter_room.assert_not_called()


def test_future_native_node_uses_recovery_time_for_every_operator(solver, monkeypatch):
    data = solver.op_data
    required, resident = (data.operators[name] for name in PRIMARY[:2])
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = resident.room, resident.index
    bed = data.dorm[0]
    resident._current_room, resident.current_index = bed.position
    resident.mood = required.mood = 12
    bed.name, bed.time = resident.name, None
    for name in COVERS[1:]:
        data.operators[name].mood = 0
    enable(data, NOW, monkeypatch)
    plan = type(solver).get_resting_plan
    times = []

    def inspect(candidate, *args, **kwargs):
        at = candidate.op_data._projection_now
        times.append(at)
        assert all(
            op._projection_now == at for op in candidate.op_data.operators.values()
        )
        return plan(candidate, *args, **kwargs)

    monkeypatch.setattr(type(solver), "get_resting_plan", inspect)
    result = emergency_recovery.native_opportunity(solver, [required.name], NOW)

    expected = NOW + timedelta(hours=12 / 4.55)
    assert result.complete and result.opportunity is not None
    assert abs(result.opportunity - expected) <= timedelta(microseconds=1)
    assert NOW in times
    assert any(abs(at - expected) <= timedelta(microseconds=1) for at in times)
    assert data.operators[resident.name].is_resting()
    assert bed.time is None


def test_recovery_target_groups_share_one_projection_time(solver, monkeypatch):
    make_episode(solver)
    enable(solver.op_data, NOW, monkeypatch)
    times = []

    def inspect(probe, members):
        times.append(getattr(probe.op_data, "_projection_now", None))
        return NativeProjection(NOW + timedelta(hours=1), True)

    monkeypatch.setattr(emergency, "history_rate", lambda *args: 1)
    monkeypatch.setattr(emergency, "native_opportunity", inspect)

    solver._emergency_update_targets()

    assert len(times) == len(PRIMARY)
    assert set(times) == {NOW}


def test_empirical_future_node_does_not_count_working_time_twice(solver, monkeypatch):
    data = solver.op_data
    required, resident = (data.operators[name] for name in PRIMARY[:2])
    required.mood, required.depletion_rate = 12, 1
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = resident.room, resident.index
    bed = data.dorm[0]
    resident._current_room, resident.current_index = bed.position
    resident.mood = 12
    due = NOW + timedelta(hours=4)
    bed.name, bed.time = resident.name, due
    for name in COVERS[1:]:
        data.operators[name].mood = 0
    plan = type(solver).get_resting_plan
    readings = []

    def inspect(candidate, *args, **kwargs):
        if candidate.op_data._projection_now == due:
            readings.append(
                candidate.op_data.operators[required.name].current_mood(due)
            )
        return plan(candidate, *args, **kwargs)

    monkeypatch.setattr(type(solver), "get_resting_plan", inspect)
    result = emergency_recovery.native_opportunity(solver, [required.name], NOW)

    assert result.complete and result.opportunity == due
    assert readings and set(readings) == {8}
    assert required.mood == 12 and required.time_stamp == NOW


@pytest.mark.parametrize("query", ["advance", "deadline"])
def test_mood_segments_stop_after_cancellation(monkeypatch, cancellation, query):
    model = calculated_mood.CalculatedMood()
    model.at = NOW
    model.moods = {"worker": 24}
    model.thresholds = [0, 12, 24]
    before = deepcopy(vars(model))
    calls = []

    def rates(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            cancellation.set()
        return {"worker": 1}

    monkeypatch.setattr(calculated_mood.CalculatedMood, "_rates", rates)
    with pytest.raises(MowerExit):
        if query == "advance":
            model.advance(NOW + timedelta(hours=24))
        else:
            model.deadline("worker", 0, NOW)
    assert len(calls) == 2
    assert vars(model) == before


def test_cached_mood_query_obeys_scoped_cancellation(monkeypatch, cancellation):
    model = calculated_mood.CalculatedMood()
    model.at = NOW
    model.moods = {"worker": 24}
    monkeypatch.setattr(model, "_rates", lambda: {"worker": 1})
    with cancellation_scope(lambda: True), pytest.raises(MowerExit):
        model.value("worker", NOW)
