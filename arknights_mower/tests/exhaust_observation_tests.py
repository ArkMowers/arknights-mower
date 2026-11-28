"""用尽预约只使用同一干员已核实的槽位读数。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 17, 1)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    members = {
        name: Operator(
            name,
            "central",
            index=index,
            current_room="central",
            current_index=index,
            operator_type="high",
            mood=1,
            time_stamp=Clock.now(),
            depletion_rate=1,
        )
        for index, name in enumerate(("旅骨", "幽灵鲨"))
    }
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        operators=members,
        exhaust_agent=list(members),
        rest_in_full_group=[],
        groups={},
        run_order_rooms={},
        refresh_run_order_rooms=lambda: None,
    )
    existing = SchedulerTask(
        time=Clock.now() - timedelta(minutes=9),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["能天使"]},
    )
    instance.tasks, instance.task = [existing], existing
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._emergency_frozen = MagicMock(return_value=False)
    instance.enter_room, instance.back = MagicMock(), MagicMock()
    instance.get_agent_from_room = MagicMock()
    return instance


@pytest.mark.parametrize(
    "reading",
    [
        [],
        [{"agent": "", "mood": -1, "observed": False}],
        [{"agent": "", "mood": -1}],
        [{"agent": "旅骨", "mood": 1}],
        [{"agent": "旅骨", "time": None}],
        [{"agent": "旅骨", "time": "02:00:00"}],
        [{"agent": "旅骨", "observed": False, "time": datetime(2026, 10, 17, 3)}],
        [{"agent": "卡达", "time": datetime(2026, 10, 17, 3)}],
    ],
)
def test_unconfirmed_slot_does_not_create_deadline_or_block_next_operator(
    solver, reading
):
    existing = solver.tasks[0]
    original_time, original_plan = existing.time, existing.plan.copy()
    reading = [
        {
            **row,
            "time": base.datetime.fromtimestamp(row["time"].timestamp()),
        }
        if isinstance(row.get("time"), datetime)
        else row
        for row in reading
    ]
    valid = [{}, {"agent": "幽灵鲨", "time": base.datetime.now() + timedelta(hours=2)}]
    solver.get_agent_from_room.side_effect = [reading, valid]

    solver.run_order_solver()

    assert solver.tasks[0] is existing
    assert (existing.time, existing.plan) == (original_time, original_plan)
    deadlines = [task for task in solver.tasks if task.type == TaskTypes.EXHAUST_OFF]
    assert [(task.meta_data, task.time) for task in deadlines] == [
        ("幽灵鲨", base.datetime.now() + timedelta(minutes=90))
    ]
    assert solver.get_agent_from_room.call_args_list == [
        call("central", [0]),
        call("central", [1]),
    ]
    assert solver.back.call_count == 2


def test_room_read_clearing_current_index_cannot_select_last_slots_timer(solver):
    deadline = base.datetime.now() + timedelta(hours=2)

    def read(room, indices):
        if indices == [0]:
            solver.op_data.operators["旅骨"].current_index = -1
            solver.op_data.operators["旅骨"].current_room = ""
            return [
                {"agent": "", "observed": False},
                {"agent": "幽灵鲨", "time": deadline},
            ]
        return [{}, {"agent": "幽灵鲨", "time": deadline}]

    solver.get_agent_from_room.side_effect = read

    solver.run_order_solver()

    deadlines = [task for task in solver.tasks if task.type == TaskTypes.EXHAUST_OFF]
    assert [(task.meta_data, task.time) for task in deadlines] == [
        ("幽灵鲨", base.datetime.now() + timedelta(minutes=90))
    ]


@pytest.mark.parametrize("minutes,expected", [(120, 90), (10, 0), (0, 15)])
def test_confirmed_operator_preserves_existing_exhaust_timing(
    solver, minutes, expected
):
    solver.op_data.exhaust_agent = ["旅骨"]
    solver.get_agent_from_room.return_value = [
        {"agent": "旅骨", "time": base.datetime.now() + timedelta(minutes=minutes)}
    ]

    solver.run_order_solver()

    deadlines = [task for task in solver.tasks if task.type == TaskTypes.EXHAUST_OFF]
    assert [(task.meta_data, task.time) for task in deadlines] == [
        ("旅骨", base.datetime.now() + timedelta(minutes=expected))
    ]
    solver.back.assert_called_once()
