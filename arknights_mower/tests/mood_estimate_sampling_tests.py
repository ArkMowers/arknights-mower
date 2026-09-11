"""Cached room reads must not turn estimated mood into another measured sample."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import record  # noqa: E402
from arknights_mower.utils import config, operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402


@pytest.fixture
def room_reader(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 11, 12)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(record, "_conn", MagicMock())
    config.conf.enable_mastery = False
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room("夕", "感知", ["诗怀雅"])],
                "contact": [Room("絮雨", "感知", ["斥罪"])],
                "dormitory_1": [
                    Room("塑心", "感知", ["隐德来希"]),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", "", ling_xi=1, resting_threshold=0.65),
        ),
        "backup_plans": [],
    }
    assert solver.initialize_operators() is None
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    for op in solver.op_data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp = Clock.now() - timedelta(hours=1)
        op.mood = 24
    target = solver.op_data.operators["夕"]
    target.mood, target.depletion_rate = 21, 1
    solver.tasks = []
    solver.task = None
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.turn_on_room_detail = MagicMock()
    solver.detect_product_complete = MagicMock(return_value=None)
    solver.find = MagicMock(return_value=None)
    solver.read_screen = MagicMock(return_value="夕")
    solver.read_accurate_mood = MagicMock(return_value=20)
    solver.double_read_time = MagicMock(return_value=Clock.now() + timedelta(hours=1))
    solver.plan_metadata = MagicMock()
    solver.total_agent = [target, solver.op_data.operators["絮雨"]]
    return solver, target, Clock


def test_repeated_cached_reads_do_not_schedule_premature_group_downshift(room_reader):
    solver, target, clock = room_reader
    sample_time = target.time_stamp
    readings = [solver.get_agent_from_room("central")[0]["mood"] for _ in range(3)]
    solver.resting()
    assert solver.tasks == []  # 当前 20 高于下班线 19，宿舍成员不应跟着撤下。
    assert readings == [20, 20, 20]
    assert (target.mood, target.time_stamp) == (21, sample_time)
    assert target.current_mood() == 20
    solver.read_accurate_mood.assert_not_called()


def test_elapsed_time_is_deducted_once_across_cached_reads(room_reader):
    solver, target, clock = room_reader
    assert solver.get_agent_from_room("central")[0]["mood"] == 20
    clock.current += timedelta(minutes=30)
    assert solver.get_agent_from_room("central")[0]["mood"] == 19.5
    assert target.current_mood() == 19.5
    assert target.predict_exhaust() == datetime(2026, 9, 11, 19, 30)


def test_real_read_still_updates_sample_and_depletion_from_measurements(room_reader):
    solver, target, clock = room_reader
    sample_time = target.time_stamp
    solver.get_agent_from_room("central")
    solver.read_accurate_mood.return_value = 19.5
    result = solver.get_agent_from_room("central", read_time_index=[0])
    assert result[0]["mood"] == 19.5
    assert target.time_stamp == clock.now() > sample_time
    assert target.mood == 19.5
    assert target.depletion_rate == 1.5
    solver.read_accurate_mood.assert_called_once()


def test_room_countdown_uses_its_row_crop_instead_of_fixed_order_region(room_reader):
    solver, target, clock = room_reader
    solver.get_agent_from_room("central", read_time_index=[0])
    solver.double_read_time.assert_called_once_with(((1650, 270), (1780, 305)))
