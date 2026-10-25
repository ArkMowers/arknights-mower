"""房间心情条归零时，工作倒计时先于采样确认剩余小数心情。"""

import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.mood_estimate_sampling_tests import (
    room_reader as room_reader,
)
from arknights_mower.utils import calculated_mood, config
from arknights_mower.utils.dorm_candidates import scheduling_mood_observation
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.resting_priority import has_resting_mood

_REAL_CONNECTION = record._conn


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch):
    monkeypatch.setattr(config, "conf", config.conf.model_copy(deep=True))


@pytest.fixture
def fractional_reader(room_reader, monkeypatch, tmp_path):
    solver, target, clock = room_reader
    monkeypatch.setattr(record, "_conn", _REAL_CONNECTION)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path / "data.db" if path.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(calculated_mood, "datetime", clock)
    target.mood = 1.2
    target.depletion_rate = 0.8
    target.depletion_rate_position = ("central", 0)
    target.lower_limit = 0
    target.time_stamp = clock.now() - timedelta(hours=1)
    solver.op_data.true_exhaust_room = {"central"}
    solver.op_data.mood_model.at = clock.now()
    solver.op_data.mood_model.moods = {
        name: op.mood for name, op in solver.op_data.operators.items()
    }
    solver.op_data.mood_model.observed = {
        name: clock.now() for name in solver.op_data.operators
    }
    solver.read_accurate_mood.return_value = 0
    solver.read_time = MagicMock(return_value=1800)
    solver.detect_room = MagicMock(return_value="central")
    solver.find = MagicMock(
        side_effect=lambda resource, **kw: True if resource == "room_detail" else None
    )
    return solver, target, clock


@pytest.mark.parametrize("enabled,expected", [(False, 0.4), (True, 0.7)])
@pytest.mark.parametrize("lower", [0, 0.25, 6])
@pytest.mark.parametrize("request_time", [False, True])
def test_zero_bar_calibrates_readback_cache_database_and_model(
    fractional_reader, enabled, expected, lower, request_time
):
    solver, target, clock = fractional_reader
    config.conf.test_mood_calculation = enabled
    target.lower_limit = lower
    if enabled:
        # 夕：基础 1 - 中枢人数 0.05 - 自身恢复 0.05 + 自身消耗 0.5 = 1.4/h。
        # 旧模型已误到零时，也必须恢复正心情一侧的自身技能后求速率。
        solver.op_data.mood_model.moods[target.name] = 0
    result = solver.get_agent_from_room(
        "central", [0] if request_time else [], force_mood=True, strict_observation=True
    )[0]

    assert result["mood"] == target.mood == pytest.approx(expected)
    assert target.time_stamp == clock.now()
    assert target.depletion_rate == 0.8
    assert not target.working_mood_unconfirmed
    assert record._fetchall(
        "SELECT mood FROM agent_action WHERE name = ?", target.name
    ) == [(pytest.approx(expected),)]
    if enabled:
        assert solver.op_data.mood_model.moods[target.name] == pytest.approx(expected)
        assert target.current_mood() == pytest.approx(expected)
    else:
        assert target.current_mood() == pytest.approx(expected)
    if request_time:
        assert result["time"] == clock.now() + timedelta(minutes=30)
        assert target.exhaust_time == (
            clock.now() + timedelta(minutes=30)
            if lower == 0
            else clock.now()
            + timedelta(minutes=30) * max(0, (expected - lower) / expected)
        )
    else:
        assert "time" not in result
    solver.read_time.assert_called_once_with(((1650, 270), (1780, 305)), None)
    solver.read_operator_time.assert_not_called()
    solver.recog.update.assert_not_called()
    assert solver.tasks == []


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("old_mood", [0, 7])
@pytest.mark.parametrize("strict", [False, True])
def test_inconsistent_timer_is_unknown_and_repeated_observations_are_idempotent(
    fractional_reader, enabled, old_mood, strict
):
    solver, target, clock = fractional_reader
    config.conf.test_mood_calculation = enabled
    target.mood = old_mood
    solver.op_data.mood_model.moods[target.name] = old_mood
    sampled_at = target.time_stamp
    target.exhaust_time = clock.now() - timedelta(minutes=1)
    solver.read_time.return_value = 7200
    revision = None
    for _ in range(3):
        if strict:
            with pytest.raises(RecognizeError, match="未核实"):
                solver.get_agent_from_room(
                    "central", [0], force_mood=True, strict_observation=True
                )
        else:
            result = solver.get_agent_from_room("central", [0], force_mood=True)[0]
            assert result["mood"] == -1
            assert "time" not in result
        assert (target.mood, target.time_stamp) == (old_mood, sampled_at)
        assert target.current_mood() == -1
        assert target.exhaust_time is None
        assert not has_resting_mood(target)
        assert scheduling_mood_observation(solver.op_data, target.name) is None
        if enabled:
            assert target.name not in solver.op_data.mood_model.moods
            assert solver.op_data.calculated_mood(target.name) is None
            assert solver.op_data.calculated_mood_deadline(target.name, 0) is None
            if revision is not None:
                assert solver.op_data.mood_model.revision == revision
            revision = solver.op_data.mood_model.revision
    assert record._fetchall("SELECT mood FROM agent_action") == []
    assert solver.tasks == []
    solver.read_operator_time.assert_not_called()

    # 普通房间操作也会重读未确认槽位，不等新计时，也不沿用近期旧缓存。
    solver.read_accurate_mood.return_value = 2
    target.need_to_refresh = MagicMock(return_value=False)
    result = solver.get_agent_from_room("central")[0]
    assert result["mood"] == target.mood == 2
    assert not target.working_mood_unconfirmed
    assert has_resting_mood(target)
    assert record._fetchall("SELECT mood FROM agent_action") == [(2,)]


@pytest.mark.parametrize("remaining", [float("nan"), float("inf"), -1, "bad"])
def test_invalid_timer_does_not_confirm_exhaustion(fractional_reader, remaining):
    solver, target, _ = fractional_reader
    old_sample = (target.mood, target.time_stamp)
    solver.read_time.return_value = remaining
    assert solver.get_agent_from_room("central", force_mood=True)[0]["mood"] == -1
    assert (target.mood, target.time_stamp) == old_sample
    solver.recog.update.assert_not_called()
    assert record._fetchall("SELECT mood FROM agent_action") == []


@pytest.mark.parametrize("rate", [0, -1, None, float("nan")])
def test_missing_empirical_rate_never_invents_fractional_mood(fractional_reader, rate):
    solver, target, _ = fractional_reader
    target.depletion_rate = rate
    with pytest.raises(RecognizeError, match="未核实"):
        solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert target.mood == 1.2
    assert record._fetchall("SELECT mood FROM agent_action") == []


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("remaining", [None, 0])
def test_confirmed_zero_with_no_remaining_countdown_still_leaves(
    fractional_reader, enabled, remaining
):
    solver, target, clock = fractional_reader
    config.conf.test_mood_calculation = enabled
    solver.read_time.return_value = remaining
    result = solver.get_agent_from_room(
        "central", [0], force_mood=True, strict_observation=True
    )[0]
    assert result["mood"] == target.mood == 0
    assert result["time"] == target.exhaust_time == clock.now()
    assert record._fetchall("SELECT mood FROM agent_action") == [(0,)]
    assert solver.read_accurate_mood.call_count == 2
    solver.read_time.assert_called_once()
    solver.read_operator_time.assert_not_called()


def test_unknown_work_mood_survives_saved_state_and_operator_rebuild(fractional_reader):
    solver, target, _ = fractional_reader
    solver.read_time.return_value = 7200
    target.mood = 0
    solver.get_agent_from_room("central", force_mood=True)
    assert record.save_state_to_db({"operators": {target.name: target}})
    blob = record._fetchall("SELECT state FROM saved_state")[0][0]
    restored = pickle.loads(blob)["operators"][target.name]
    assert restored.mood == 0
    assert restored.working_mood_unconfirmed
    assert restored.current_mood() == -1
    solver.op_data.shadow_copy = {target.name: restored}
    from arknights_mower.utils.operators import Operator

    replacement = Operator(target.name, "central", index=0)
    solver.op_data.add(replacement)
    assert replacement.working_mood_unconfirmed
    assert replacement.current_mood() == -1


@pytest.mark.parametrize("enabled", [False, True])
def test_positive_mood_observation_does_not_read_timer_or_fractional_rate(
    fractional_reader, enabled, monkeypatch
):
    solver, target, _ = fractional_reader
    config.conf.test_mood_calculation = enabled
    solver.read_accurate_mood.return_value = 2
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    fractional_rate = MagicMock(
        side_effect=AssertionError("非零心情不应计算倒计时心情")
    )
    monkeypatch.setattr(BaseSchedulerSolver, "_fractional_work_mood", fractional_rate)
    assert solver.get_agent_from_room("central", force_mood=True)[0]["mood"] == 2
    fractional_rate.assert_not_called()
    solver.read_time.assert_not_called()
    solver.read_operator_time.assert_not_called()


@pytest.mark.parametrize("room", ["central", "contact", "meeting", "room_1_1"])
def test_continuous_work_rooms_use_operator_row_countdown(room_reader, room):
    solver, target, clock = room_reader
    target.current_room = room
    solver.leifeng_mode = True
    solver.find = MagicMock(
        side_effect=lambda resource, scope=None: (
            resource == "infra_no_operator" and scope[0][1] == 344
        )
    )
    solver.op_data.plan[room] = solver.op_data.plan["central"]
    solver.read_time = MagicMock(return_value=1800)
    solver.read_accurate_mood.return_value = 0
    target.depletion_rate = 0.8
    target.depletion_rate_position = (room, 0)
    result = solver.get_agent_from_room(room, force_mood=True)[0]
    assert result["mood"] == pytest.approx(0.4)
    solver.read_time.assert_called_once_with(((1650, 270), (1780, 305)), None)


def test_future_empirical_sample_cannot_supply_fractional_rate(fractional_reader):
    solver, target, clock = fractional_reader
    target.time_stamp = clock.now() + timedelta(hours=1)
    with pytest.raises(RecognizeError, match="未核实"):
        solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert record._fetchall("SELECT mood FROM agent_action") == []


@pytest.mark.parametrize("enabled", [False, True])
def test_unknown_worker_does_not_open_room_again_or_move_pending_work(
    fractional_reader,
    enabled,
):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, target, clock = fractional_reader
    config.conf.test_mood_calculation = enabled
    solver.read_time.return_value = 7200
    solver.get_agent_from_room("central", force_mood=True)
    pending = SchedulerTask(time=clock.now(), task_type=TaskTypes.NOT_SPECIFIC)
    solver.tasks = [pending]
    solver.op_data.exhaust_agent = {target.name}
    solver.op_data.run_order_rooms = {}
    solver._sync_run_order_tasks = MagicMock()
    solver.check_fia = MagicMock(return_value=(None, None))
    solver._emergency_frozen = MagicMock(return_value=False)
    solver.enter_room = MagicMock()
    for _ in range(3):
        solver.run_order_solver()
    assert solver.tasks == [pending]
    assert solver.tasks[0] is pending
    assert pending.time == clock.now()
    solver.enter_room.assert_not_called()
    solver.read_time.assert_called_once()


def test_due_exhaustion_confirmation_defers_fractional_worker(fractional_reader):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, target, clock = fractional_reader
    config.conf.test_mood_calculation = True
    solver.op_data.mood_model.moods[target.name] = 0
    pending = SchedulerTask(
        time=clock.now(), task_type=TaskTypes.EXHAUST_OFF, meta_data=target.name
    )
    solver.tasks, solver.task = [pending], pending
    solver.enter_room, solver.back = MagicMock(), MagicMock()
    assert solver._confirm_calculated_exhaustion([target]) is False
    assert solver.tasks == [pending]
    assert pending.plan == {}
    assert pending.time == clock.now() + timedelta(minutes=30)
    assert target.mood == pytest.approx(0.7)
    solver.enter_room.assert_called_once_with("central")
    solver.read_time.assert_called_once()


@pytest.mark.parametrize("position", [None, ("meeting", 0), ("central", 1)])
def test_fractional_read_rejects_rate_without_current_position_evidence(
    fractional_reader, position
):
    solver, target, _ = fractional_reader
    if position is None:
        del target.depletion_rate_position
    else:
        target.depletion_rate_position = position
    with pytest.raises(RecognizeError, match="未核实"):
        solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    assert target.working_mood_unconfirmed
    assert record._fetchall("SELECT mood FROM agent_action") == []


def test_empirical_work_observation_supplies_fractional_rate_position(
    fractional_reader,
):
    solver, target, clock = fractional_reader
    del target.depletion_rate_position
    target.mood = 2
    solver.op_data.update_detail(target.name, 1.2, "central", 0, True)
    assert target.depletion_rate_position == ("central", 0)
    assert solver.get_agent_from_room("central", force_mood=True)[0][
        "mood"
    ] == pytest.approx(0.4)
