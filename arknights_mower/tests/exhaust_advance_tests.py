"""用尽下班提前量沿用个人及所属组的回满要求。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

with pytest.MonkeyPatch.context() as imports:
    imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule as base

from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import TaskTypes

TARGET = "阿罗玛"
PEER = "砾"
GROUP = "制造组"


@pytest.fixture
def solver_factory(monkeypatch, offline_maintenance):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 18, 12)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )

    def make(group, full_name, *, peer_group=None, countdown=True):
        data = Operators(
            {
                "default_plan": Plan(
                    {
                        "room_1_1": [Room(TARGET, group, ["引星棘刺"])],
                        "room_1_2": [
                            Room(
                                PEER,
                                group if peer_group is None else peer_group,
                                ["红"],
                            )
                        ],
                        "dormitory_1": [
                            Room("杜林", "", []),
                            Room("桃金娘", "", []),
                            *[Room("Free", "", []) for _ in range(3)],
                        ],
                    },
                    PlanConfig(full_name, TARGET, ""),
                ),
                "backup_plans": [],
            }
        )
        assert data.init_and_validate() is None
        for op in data.operators.values():
            op.current_room, op.current_index = (
                (op.room, op.index) if op.is_high() else ("", -1)
            )
            op.mood, op.time_stamp = 24, Clock.now()
        target = data.operators[TARGET]
        target.mood, target.depletion_rate = 1.25, 0.5

        instance = object.__new__(base.BaseSchedulerSolver)
        instance.op_data = data
        instance.tasks, instance.task = [], None
        instance.check_fia = MagicMock(return_value=(None, None))
        instance._emergency_frozen = MagicMock(return_value=False)
        instance.enter_room, instance.back = MagicMock(), MagicMock()
        instance.get_agent_from_room = MagicMock(
            return_value=[
                {
                    "agent": TARGET,
                    "time": Clock.now() + timedelta(hours=2)
                    if countdown
                    else Clock.now(),
                }
            ]
        )
        return instance

    return make


@pytest.mark.parametrize("countdown", [True, False], ids=["countdown", "estimate"])
@pytest.mark.parametrize(
    "group,full_name,expected_time",
    [
        pytest.param("", TARGET, (13, 50), id="personal-full"),
        pytest.param(GROUP, TARGET, (13, 50), id="group-own-full"),
        pytest.param(GROUP, PEER, (13, 50), id="group-peer-full"),
        pytest.param("", "", (13, 30), id="personal-ordinary"),
        pytest.param(GROUP, "", (13, 30), id="group-ordinary"),
    ],
)
def test_exhaust_advance_uses_effective_full_recovery_requirement(
    solver_factory, group, full_name, expected_time, countdown
):
    solver = solver_factory(group, full_name, countdown=countdown)

    solver.run_order_solver()

    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.meta_data == TARGET
    # 两小时归零；估算分支保留原有的 0.25 点余量。
    assert task.time == base.datetime(2026, 10, 18, *expected_time)
    solver.get_agent_from_room.assert_called_once_with("room_1_1", [0])


@pytest.mark.parametrize("countdown", [True, False], ids=["countdown", "estimate"])
def test_unrelated_full_group_named_after_operator_does_not_change_advance(
    solver_factory, countdown
):
    solver = solver_factory("", PEER, peer_group=TARGET, countdown=countdown)
    assert solver.op_data.rest_in_full_group == {TARGET}
    assert not solver.op_data.operators[TARGET].rest_in_full

    solver.run_order_solver()

    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == base.datetime(2026, 10, 18, 13, 30)
