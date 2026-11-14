from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import shift_backup_convergence_tests as backup
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils import calculated_mood, dorm_candidates, operators
from arknights_mower.utils.operators import Operators

solver = backup.solver


@pytest.mark.parametrize("entry", ["_prepare_shift_cycle", "_prepare_shift_backup"])
@pytest.mark.parametrize("inherited", [False, True])
def test_convergence_queries_share_clock_without_freezing_live_reads(
    solver, monkeypatch, entry, inherited
):
    data = solver.op_data
    started = datetime.now()
    for op in data.operators.values():
        op.time_stamp = started
    enable(data, started, monkeypatch)
    if inherited:
        solver.op_data = data.project_arrangements([], now=started + timedelta(hours=1))
        data = solver.op_data
    before = (
        backup.positions(data),
        {name: (op.mood, op.time_stamp) for name, op in data.operators.items()},
        getattr(data, "_projection_now", None),
        deepcopy(data.group_shift_state),
        deepcopy((data.mood_model.at, data.mood_model.moods, data.mood_model.observed)),
    )

    class AdvancingClock(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return started + timedelta(microseconds=cls.calls)

    for module in (base, calculated_mood, operators, dorm_candidates):
        monkeypatch.setattr(module, "datetime", AdvancingClock)
    original_select = Operators.evaluate_backup_selection
    original_deadline = calculated_mood.CalculatedMood.deadline
    original_value = calculated_mood.CalculatedMood.value
    original_swap = Operators.swap_plan
    original_transition = base.BaseSchedulerSolver._backup_transition_plan
    original_prioritize = base.prioritize_new_dorm_recovery
    snapshots = []
    deadline_queries = []
    value_queries = []
    stale_key = ("薇薇安娜", 0, 1)
    refresh_checks = []

    def swap(projected, *args, **kwargs):
        result = original_swap(projected, *args, **kwargs)
        if result is None and getattr(projected, "_projection_now", None) is not None:
            projected._projection_deadlines[stale_key] = started
        return result

    def transition(instance, *args, **kwargs):
        assert stale_key not in instance.op_data._projection_deadlines
        refresh_checks.append("backup")
        return original_transition(instance, *args, **kwargs)

    def prioritize(projected, *args, **kwargs):
        assert stale_key not in projected._projection_deadlines
        refresh_checks.append("cycle")
        return original_prioritize(projected, *args, **kwargs)

    def record_deadline(model, *args, **kwargs):
        deadline_queries.append(model)
        return original_deadline(model, *args, **kwargs)

    def record_value(model, name, now=None):
        value_queries.append((model, name, now))
        return original_value(model, name, now)

    def select(projected):
        assert projected is not data
        when = getattr(projected, "_projection_now", None)
        assert when is not None
        snapshots.append(when)
        op = projected.operators["薇薇安娜"]
        assert op._projection_now == when
        assert op._projection_deadlines is projected._projection_deadlines
        model_before = projected.mood_model.at
        count = len(deadline_queries)
        queried = len(value_queries)
        for _ in range(3):
            AdvancingClock.now()
            op.current_mood()
            projected.calculated_mood(op.name)
            projected.calculated_mood_deadline(op.name, 0)
        assert len(deadline_queries) - count <= 1
        assert {
            query_time
            for model, name, query_time in value_queries[queried:]
            if model is projected.mood_model and name == op.name
        } == {when}
        assert projected.mood_model.at == model_before
        future = when + timedelta(minutes=5)
        assert op.current_mood(future) == projected.calculated_mood(op.name, future)
        assert value_queries[-1][2] == value_queries[-2][2] == future
        return original_select(projected)

    monkeypatch.setattr(calculated_mood.CalculatedMood, "deadline", record_deadline)
    monkeypatch.setattr(calculated_mood.CalculatedMood, "value", record_value)
    monkeypatch.setattr(Operators, "evaluate_backup_selection", select)
    monkeypatch.setattr(Operators, "swap_plan", swap)
    monkeypatch.setattr(base.BaseSchedulerSolver, "_backup_transition_plan", transition)
    monkeypatch.setattr(base, "prioritize_new_dorm_recovery", prioritize)
    task = backup.downshift(solver)
    getattr(solver, entry)(task)

    assert snapshots
    assert "backup" in refresh_checks
    if entry == "_prepare_shift_cycle":
        assert "cycle" in refresh_checks
    assert len(set(snapshots)) == 1
    if inherited:
        assert snapshots[0] == started + timedelta(hours=1)
    assert AdvancingClock.calls > 3
    assert (
        backup.positions(data),
        {name: (op.mood, op.time_stamp) for name, op in data.operators.items()},
        getattr(data, "_projection_now", None),
        data.group_shift_state,
        (data.mood_model.at, data.mood_model.moods, data.mood_model.observed),
    ) == before
