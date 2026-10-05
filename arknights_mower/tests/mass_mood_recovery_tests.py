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


def test_current_rotation_accepts_measured_low_mood_without_rate(solver):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    for name in PRIMARY:
        solver.op_data.operators[name].mood = 0
    result = native_opportunity(solver, PRIMARY[:3], NOW, current_only=True)

    assert result.complete and result.opportunity == NOW
    solver.enter_room.assert_not_called()


def test_current_rotation_does_not_wait_for_future_shift_or_unknown_bed(solver):
    from datetime import timedelta

    from arknights_mower.utils.emergency_recovery import native_opportunity
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = solver.op_data
    required = PRIMARY[0]
    data.operators[required].mood = 0
    for name in COVERS:
        data.operators[name].mood = 0
    resident = data.operators[PRIMARY[-1]]
    resident._current_room, resident.current_index = "dormitory_1", 2
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 2))
    bed.name, bed.time = resident.name, None
    solver.tasks.append(
        SchedulerTask(
            time=NOW + timedelta(minutes=10),
            task_type=TaskTypes.SHIFT_OFF,
            task_plan={data.operators[required].room: [COVERS[0]]},
        )
    )
    before = repr(data), repr(solver.tasks)

    result = native_opportunity(solver, [required], NOW, current_only=True)

    assert result.complete and result.opportunity is None
    assert result.reason == "blocked"
    assert (repr(data), repr(solver.tasks)) == before
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("delay", [0, 10])
def test_current_rotation_accounts_for_due_return_but_not_future_return(solver, delay):
    from datetime import timedelta

    from arknights_mower.utils.emergency_recovery import native_opportunity
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = solver.op_data
    for name in PRIMARY[:2]:
        data.operators[name].mood = 0
    owner = data.operators[PRIMARY[2]]
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = owner.room, owner.index
    bed = data.dorm[0]
    owner._current_room, owner.current_index = bed.position
    bed.name, bed.time = owner.name, None
    due = SchedulerTask(
        time=NOW + timedelta(minutes=delay),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={owner.room: [owner.name]},
    )
    solver.tasks = [due]
    result = native_opportunity(solver, PRIMARY[:2], NOW, current_only=True)
    assert result.complete
    assert (result.opportunity == NOW) is (delay == 0)
    assert solver.tasks == [due]
    assert bed.name == owner.name
    assert cover.current_room == owner.room
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("delay,mood", [(0, 24), (10, 24), (0, 8)])
def test_current_rotation_accounts_for_executable_fiammetta(solver, delay, mood):
    from datetime import timedelta

    from arknights_mower.utils.emergency_recovery import native_opportunity
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 0
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=mood,
        time_stamp=NOW,
        operator_type="high",
        replacement=[PRIMARY[-1]],
    )
    task = SchedulerTask(
        time=NOW + timedelta(minutes=delay),
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"dormitory_1": [PRIMARY[-1], "菲亚梅塔"]},
        meta_data=PRIMARY[-1],
    )
    solver.tasks = [task]
    result = native_opportunity(solver, PRIMARY, NOW, current_only=True)
    assert result.complete
    assert (result.opportunity == NOW) is (delay == 0 and mood == 24)
    assert solver.tasks == [task]
    assert all(data.operators[name].mood == 0 for name in PRIMARY)
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("invalid", ["slot", "retry", "prediction", "unknown"])
def test_current_fiammetta_needs_confirmed_position_and_task(solver, invalid):
    from arknights_mower.utils.emergency_recovery import native_opportunity
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 0
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    fia = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=24,
        time_stamp=NOW,
        operator_type="high",
        replacement=[PRIMARY[-1]],
    )
    data.operators[fia.name] = fia
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"dormitory_1": [PRIMARY[-1], "菲亚梅塔"]},
        meta_data=PRIMARY[-1],
    )
    if invalid == "slot":
        fia.current_index = 1
    elif invalid == "retry":
        task.arrangement_retry_room = "dormitory_1"
    elif invalid == "prediction":
        fia.mood_is_prediction = True
    else:
        fia.time_stamp = None
    solver.tasks = [task]
    result = native_opportunity(solver, PRIMARY, NOW, current_only=True)
    assert result.complete and result.opportunity is None
    assert fia.mood == 24
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "case", ["due", "future", "wrong_bed", "changed_limit", "removed_limit", "ordinary"]
)
def test_current_rotation_honors_strict_release_operation_window(solver, case):
    import copy
    from datetime import timedelta

    from arknights_mower.utils.emergency_recovery import native_opportunity
    from arknights_mower.utils.scheduler_task import (
        SchedulerTask,
        TaskTypes,
        protect_priority_tasks,
    )

    data = solver.op_data
    for name in PRIMARY[:2]:
        data.operators[name].mood = 0
    for name, bed in zip(PRIMARY[2:], data.dorm[:2]):
        resident = data.operators[name]
        resident.mood = 10
        resident._current_room, resident.current_index = bed.position
        bed.name, bed.time = name, None
    limited = data.operators[PRIMARY[2]]
    data.config.operator_mood_limits = {limited.name: {"lower": 0, "upper": 12}}
    data.init_mood_limit()
    room, index = data.dorm[0].position
    row = ["Current"] * len(data.plan[room])
    row[index] = "Free"
    task = SchedulerTask(
        time=NOW + timedelta(seconds=45),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={room: row},
        meta_data=limited.name,
        strict_mood_limit=True,
        mood_limit=12,
    )
    protect_priority_tasks([task], time_now=NOW)
    assert task.time <= NOW < task.mood_limit_deadline
    assert limited.mood < limited.upper_limit
    if case == "future":
        task.time = NOW + timedelta(minutes=5)
    elif case == "wrong_bed":
        task.plan[room][index] = "Current"
        task.plan[room][index + 1] = "Free"
    elif case == "changed_limit":
        task.mood_limit = 11
    elif case == "removed_limit":
        data.config.operator_mood_limits.clear()
    elif case == "ordinary":
        task.strict_mood_limit = False
    solver.tasks = [task]
    before_task = copy.deepcopy(vars(task))
    before_operators = {
        name: copy.deepcopy(vars(op)) for name, op in data.operators.items()
    }
    before_beds = [copy.deepcopy(vars(bed)) for bed in data.dorm]

    # Compare the projected opportunity with the same real dispatch guard.
    dispatch = copy.copy(solver)
    dispatch.op_data = copy.deepcopy(data, {id(data.eval_model): data.eval_model})
    dispatch.tasks = []
    dispatched_task = copy.deepcopy(task)
    dispatch.prepare_release_dorm(dispatched_task)
    assert bool(dispatched_task.plan) is (case in ("due", "future"))

    result = native_opportunity(solver, PRIMARY[:2], NOW, current_only=True)

    assert result.complete
    assert (result.opportunity == NOW) is (case == "due")
    assert vars(task) == before_task
    assert {name: vars(op) for name, op in data.operators.items()} == before_operators
    assert [vars(bed) for bed in data.dorm] == before_beds
    assert solver.op_data is data and solver.tasks == [task]
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("at_floor", [False, True])
def test_current_native_projection_does_not_advance_exhaustion_shift(solver, at_floor):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    op = solver.op_data.operators[PRIMARY[0]]
    op.exhaust_require = True
    op.mood = op.lower_limit if at_floor else 3
    result = native_opportunity(solver, [op.name], NOW, current_only=True)
    assert result.complete
    assert (result.opportunity == NOW) is at_floor
    solver.enter_room.assert_not_called()
