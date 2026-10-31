"""副表条件在一次选择中使用同刻心情，下一次选择重新取时。"""

import copy
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from arknights_mower.tests import shift_backup_convergence_tests
from arknights_mower.tests.backup_snapshot_tests import solver as solver
from arknights_mower.tests.shift_backup_convergence_tests import downshift
from arknights_mower.utils import calculated_mood, config, operators
from arknights_mower.utils.calculated_mood import sync_model
from arknights_mower.utils.logic_expression import LogicExpression

shift_solver = shift_backup_convergence_tests.solver
pytestmark = pytest.mark.usefixtures("offline_maintenance")
NOW = datetime(2026, 10, 28, 8)


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = NOW + timedelta(seconds=1)
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            result = cls.current
            cls.current += timedelta(microseconds=100)
            return result

    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(calculated_mood, "datetime", Clock)
    monkeypatch.setattr("arknights_mower.solvers.base_schedule.datetime", Clock)
    monkeypatch.setattr(calculated_mood, "_runtime", threading.local())
    monkeypatch.setattr(
        "arknights_mower.utils.mastery_recommendation.get_cultivate_snapshot",
        lambda: None,
    )
    return Clock


def enable(data, *, recovering=False):
    if recovering:
        data = data.project_arrangements(
            [
                {
                    "meeting": ["陈"],
                    "dormitory_1": ["塑心", "伊内丝", "Current", "Current", "Current"],
                }
            ]
        )
    config.conf.test_mood_calculation = True
    for room, slots in data.plan.items():
        if room.startswith("room_"):
            for slot in slots:
                slot.facility = "制造站"
    for name, op in data.operators.items():
        op.mood = 12 if name in ("伊内丝", "野鬃") else 24
        op.time_stamp = NOW
        data.mood_model.observe(name, op.mood, NOW)
    sync_model(data, NOW)
    return data


def condition(group="一组", name="伊内丝", comparison="!="):
    return LogicExpression(
        f"op_data.group_min_mood('{group}')",
        comparison,
        f"op_data.operators['{name}'].current_mood()",
    )


@pytest.mark.parametrize("calculated", [False, True])
def test_selection_compares_group_and_member_at_same_time(solver, clock, calculated):
    data = solver.op_data
    if calculated:
        data = enable(data, recovering=True)
    else:
        data.operators["伊内丝"].depletion_rate = -1
        data.operators["伊内丝"].time_stamp = NOW
        data.operators["伊内丝"].mood = 12
    data.backup_plans[0].trigger = condition()
    before = data.mood_model.at
    with patch.object(
        calculated_mood.CalculatedMood,
        "__deepcopy__",
        autospec=True,
        side_effect=calculated_mood.CalculatedMood.__deepcopy__,
    ) as clone:
        assert data.evaluate_backup_selection().conditions == [False]
        # 一次选择中的任意多个心情读取至多构造一次模型投影。
        assert clone.call_count == (1 if calculated else 0)
    assert data.mood_model.at == before
    assert getattr(data, "_projection_now", None) is None
    assert all(
        getattr(op, "_projection_now", None) is None for op in data.operators.values()
    )


def test_group_and_backup_conditions_share_time_and_next_selection_advances(
    solver, clock
):
    data = enable(solver.op_data, recovering=True)
    data.backup_groups = [
        {
            "id": "recovering",
            "name": "恢复",
            "trigger": {
                "left": "op_data.operators['伊内丝'].current_mood()",
                "operator": "<",
                "right": "13",
            },
        }
    ]
    backup = data.backup_plans[0]
    backup.group_ids = ["recovering"]
    backup.trigger = condition(comparison="==")
    second = copy.copy(backup)
    second.trigger = LogicExpression(
        "op_data.operators['伊内丝'].current_mood()", "<", "13"
    )
    data.backup_plans.append(second)
    # 所有读取均到同一时刻；直接查询到一小时后的心情已超过 13。
    assert data.operators["伊内丝"].current_mood(NOW + timedelta(hours=1)) > 13
    first_calls = clock.calls
    selected = data.evaluate_backup_selection()
    assert (selected.group_id, selected.conditions) == ("recovering", [True, True])
    assert clock.calls - first_calls == 1
    clock.current = NOW + timedelta(hours=1)
    selected = data.evaluate_backup_selection()
    assert (selected.group_id, selected.conditions) == ("default", [False, False])


def test_existing_projection_time_is_preserved(solver, clock):
    data = enable(solver.op_data, recovering=True).project_arrangements([], now=NOW)
    data.backup_plans[0].trigger = condition()
    clock.current = NOW + timedelta(hours=1)
    before = clock.calls
    assert data.evaluate_backup_selection().conditions == [False]
    assert clock.calls == before
    assert data._projection_now == NOW
    assert all(op._projection_now == NOW for op in data.operators.values())
    assert data.eval_model is solver.op_data.eval_model


@pytest.mark.parametrize("frozen", [False, True])
def test_selection_exception_restores_all_clocks(solver, clock, monkeypatch, frozen):
    data = solver.op_data
    if frozen:
        data._projection_now = NOW
        data.operators["伊内丝"]._projection_now = NOW
    original = [
        (obj, copy.copy(obj.__dict__)) for obj in (data, *data.operators.values())
    ]

    def fail(*args, **kwargs):
        assert data._projection_now == (
            NOW if frozen else clock.current - timedelta(microseconds=100)
        )
        assert all(
            op._projection_now == data._projection_now for op in data.operators.values()
        )
        raise RuntimeError("injected selection failure")

    with monkeypatch.context() as context:
        context.setattr("arknights_mower.utils.backup_groups.select_backup_plans", fail)
        with pytest.raises(RuntimeError, match="injected selection failure"):
            data.evaluate_backup_selection()
    for obj, state in original:
        assert obj.__dict__.get("_projection_now") == state.get("_projection_now")
        assert ("_projection_now" in obj.__dict__) == ("_projection_now" in state)
    data.backup_plans[0].trigger = condition()
    assert data.evaluate_backup_selection().conditions == [False]


def test_unchanged_dispatch_does_not_regenerate_backup_tasks(solver, clock):
    solver.op_data = enable(solver.op_data, recovering=True)
    data = solver.op_data
    data.backup_plans[0].trigger = condition()
    pending, deadline = solver.tasks[0], solver.tasks[0].time
    for _ in range(5):
        assert solver.backup_plan_solver() is False
        assert data.plan_condition == [False]
        assert solver.tasks == [pending]
        assert pending.time == deadline
    assert data.evaluate_backup_selection().conditions == [False]


def test_full_shift_and_live_selection_agree_without_new_backup_task(
    shift_solver, clock
):
    solver = shift_solver
    solver.op_data = enable(solver.op_data)
    solver.op_data.backup_plans[0].trigger = condition("红松", "野鬃")
    assert 0 < solver.op_data.operators["野鬃"].current_mood(NOW) < 24
    task = downshift(solver)
    solver._prepare_shift_cycle(task)
    assert task.backup_shift_conditions == [False]
    pending = list(solver.tasks)
    for _ in range(3):
        assert solver.op_data.evaluate_backup_selection().conditions == [False]
        assert solver.backup_plan_solver() is False
        assert solver.op_data.plan_condition == [False]
        assert solver.tasks == pending


def test_expression_error_does_not_freeze_later_selection(solver, clock):
    data = enable(solver.op_data, recovering=True)
    data.backup_plans[0].trigger = LogicExpression("1 / 0", "==", "1")
    assert data.evaluate_backup_selection().conditions == [False]
    assert getattr(data, "_projection_now", None) is None
    assert all(
        getattr(op, "_projection_now", None) is None for op in data.operators.values()
    )
    data.backup_plans[0].trigger = LogicExpression(
        "op_data.operators['伊内丝'].current_mood()", ">", "13"
    )
    clock.current = NOW + timedelta(hours=1)
    assert data.evaluate_backup_selection().conditions == [True]
