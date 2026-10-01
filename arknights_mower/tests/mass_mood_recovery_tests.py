"""原生轮休预演使用离线驻员快照。"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import config, operators, scheduler_task  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402

NOW = datetime(2026, 9, 30, 8)
PRIMARY = ["伊内丝", "银灰", "讯使", "能天使"]
COVERS = ["陈", "槐琥", "斥罪", "结城理"]


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.enable_mastery = False
    config.conf.rescue_threshold = 0.75
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    data = Operators(
        {
            "default_plan": Plan(
                {
                    **{
                        f"room_{(index - 1) // 3 + 1}_{(index - 1) % 3 + 1}": [
                            Room(name, "", [COVERS[index - 1]])
                        ]
                        for index, name in enumerate(PRIMARY, 1)
                    },
                    "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                    + [Room("Free", "", []) for _ in range(3)],
                },
                PlanConfig("", "", "", resting_priority_replacement=",".join(COVERS)),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    for operator in data.operators.values():
        operator.mood, operator.time_stamp, operator.depletion_rate = 24, NOW, 0
        operator._current_room, operator.current_index = operator.room, operator.index
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data = data
    instance.tasks, instance.task = [], None
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._refresh_deferred_product_reservations = MagicMock()
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    return instance


def test_native_projection_accepts_complete_rotation_without_device_io(solver):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    result = native_opportunity(solver, PRIMARY[:3], NOW)
    assert result.complete and result.opportunity == NOW
    solver.enter_room.assert_not_called()


def test_native_projection_distinguishes_blocked_and_unknown(solver):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    result = native_opportunity(solver, PRIMARY, NOW)
    assert result.complete and result.opportunity is None
    assert result.reason == "blocked"
    incomplete = native_opportunity(solver, PRIMARY, NOW, budget=0)
    assert not incomplete.complete
    solver.enter_room.assert_not_called()
