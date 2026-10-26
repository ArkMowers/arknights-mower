"""零读数复用工作倒计时，调度期限与速率采样分别保持真实依据。"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests.mood_estimate_sampling_tests import (
    room_reader as room_reader,
)
from arknights_mower.utils import calculated_mood, config


@pytest.fixture
def zero_reader(room_reader, monkeypatch):
    solver, op, clock = room_reader
    clock.current = clock(2026, 9, 11, 12)
    monkeypatch.setattr(calculated_mood, "datetime", clock)
    op.lower_limit = 0
    op.mood = 1.2
    op.depletion_rate = 0.8
    op.time_stamp = clock.now() - timedelta(hours=1)
    solver.op_data.exhaust_agent.add(op.name)
    solver.leifeng_mode = True
    solver.find = MagicMock(
        side_effect=lambda name, scope=None: (
            name == "infra_no_operator" and scope[0][1] == 344
        )
    )
    solver.read_accurate_mood.return_value = 0
    solver.read_time = MagicMock(return_value=1800)
    solver.read_operator_time = BaseSchedulerSolver.read_operator_time.__get__(solver)
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    return solver, op, clock


def test_observed_countdown_defers_calculated_exhaustion_and_confirms_at_end(
    zero_reader,
):
    solver, op, clock = zero_reader
    config.conf.test_mood_calculation = True
    observed = solver.get_agent_from_room(
        "central", force_mood=True, strict_observation=True
    )[0]
    end = clock.now() + timedelta(minutes=30)
    assert observed["time"] == op.exhaust_time == end
    assert observed["mood"] == op.mood == 0
    solver._schedule_calculated_exhaustion(op)
    task = solver.tasks[0]
    solver.task = task
    for _ in range(3):
        solver._schedule_calculated_exhaustion(op)
        assert solver._confirm_calculated_exhaustion([op]) is False
        assert solver.tasks == [task]
        assert task.time == end
    solver.enter_room.assert_not_called()
    clock.current = end
    solver.read_time.return_value = None
    assert solver._confirm_calculated_exhaustion([op]) is True
    solver.enter_room.assert_called_once_with("central")
    assert op.exhaust_time == clock.now()


def test_due_confirmation_uses_new_countdown_without_duplicate_task(zero_reader):
    solver, op, clock = zero_reader
    config.conf.test_mood_calculation = True
    solver.op_data.mood_model.observe(op.name, 0, clock.now())
    solver._schedule_calculated_exhaustion(op)
    solver.task = solver.tasks[0]
    assert solver.task.time == clock.now()
    assert solver._confirm_calculated_exhaustion([op]) is False
    assert solver.task.time == clock.now() + timedelta(minutes=30)
    assert len(solver.tasks) == 1
    assert solver._confirm_calculated_exhaustion([op]) is False
    solver.enter_room.assert_called_once()


@pytest.mark.parametrize("enabled", [False, True])
def test_zero_samples_do_not_train_work_rate_or_next_baseline(zero_reader, enabled):
    solver, op, clock = zero_reader
    config.conf.test_mood_calculation = enabled
    for _ in range(2):
        solver.get_agent_from_room("central", force_mood=True)
        assert op.depletion_rate == 0.8
        assert getattr(op, "recall_work_rate", None) is None
        assert not op.work_rate_sample_eligible
        clock.current += timedelta(hours=1)
    solver.read_accurate_mood.return_value = 2
    solver.get_agent_from_room("central", force_mood=True)
    assert op.depletion_rate == 0.8
    assert op.exhaust_time is None
    clock.current += timedelta(hours=1)
    solver.read_accurate_mood.return_value = 1.5
    solver.get_agent_from_room("central", force_mood=True)
    assert op.depletion_rate == 0.5


def test_position_change_clears_observed_working_deadline(zero_reader):
    solver, op, clock = zero_reader
    solver.get_agent_from_room("central", force_mood=True)
    assert op.exhaust_time == clock.now() + timedelta(minutes=30)
    solver.op_data.update_detail(op.name, 0, "contact", 0, False)
    assert op.exhaust_time is None
    assert op.working_zero_deadline(clock.now()) is None


@pytest.mark.parametrize("enabled", [False, True])
def test_ordinary_return_window_keeps_countdown_and_existing_margin(
    zero_reader, enabled
):
    solver, op, clock = zero_reader
    config.conf.test_mood_calculation = enabled
    solver.read_time.return_value = 3009
    solver.get_agent_from_room("central", force_mood=True)
    assert op.predict_exhaust(clock.now()) == clock.now() + timedelta(seconds=1209)


def test_invalidated_mood_observation_does_not_reuse_working_deadline(zero_reader):
    solver, op, clock = zero_reader
    config.conf.test_mood_calculation = True
    solver.get_agent_from_room("central", force_mood=True)
    assert (
        solver.op_data.calculated_mood_deadline(op.name, 0, clock.now()) > clock.now()
    )
    solver._schedule_calculated_exhaustion(op)
    solver.refresh_drained_time()
    assert op.time_stamp is None
    assert op.working_zero_deadline(clock.now()) is None
    assert (
        solver.op_data.calculated_mood_deadline(op.name, 0, clock.now()) == clock.now()
    )
