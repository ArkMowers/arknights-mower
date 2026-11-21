"""部分换班的完整确认目标继续预约，独立回班与个人上限离宿照常规划。"""

import copy
import pickle
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.retained_recovery import reconcile_retained_recovery
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
    plan_metadata,
)


@pytest.fixture
def partial_confirmation(monkeypatch, offline_maintenance):
    forbidden_io = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden_io)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "recycle": [Room("旅骨", "", ["砾", "空爆"])],
                    "contact": [Room("银灰", "甲组", ["红"])],
                    "meeting": [
                        Room("能天使", "乙组", ["初雪"]),
                        Room("讯使", "乙组", ["黑角"]),
                    ],
                    "dormitory_1": [
                        Room("塑心", "", []),
                        Room("冰酿", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                    "dormitory_2": [
                        Room("杜林", "", []),
                        Room("闪灵", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig(
                    "",
                    "",
                    "",
                    resting_standby="讯使",
                    operator_mood_limits={
                        "旅骨": {"lower": 0, "upper": 24},
                        "能天使": {"lower": 0, "upper": 24},
                        "空爆": {"lower": 0, "upper": 12},
                    },
                ),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    now = datetime.now()
    for op in data.operators.values():
        op.mood, op.time_stamp = 24, now
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
    for name in ("旅骨", "能天使", "讯使"):
        data.operators[name]._current_room = ""
        data.operators[name].current_index = -1
    resident = data.operators["空爆"]
    resident._current_room, resident.current_index = "dormitory_1", 3
    resident.mood, resident.upper_limit = 12, 12
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 3))
    bed.name, bed.time = resident.name, now
    task = SchedulerTask(
        now - timedelta(hours=2),
        {"dormitory_2": ["Current", "Current", "银灰", "Current", "Current"]},
        TaskTypes.SHIFT_ON,
    )
    task.group_shift_expected = {
        ("dormitory_1", 4): "旅骨",
        ("dormitory_2", 2): "银灰",
    }
    task.execution_failure = {"reason": "宿舍确认未完成", "rooms": ["dormitory_2"]}
    yield data, task
    forbidden_io.assert_not_called()


def test_partial_confirmation_prevents_duplicate_return_and_allows_independent_work(
    partial_confirmation,
):
    data, original = partial_confirmation
    before = copy.deepcopy(original.__dict__)
    tasks = [original]
    for _ in range(4):
        tasks = plan_metadata(data, tasks)
        assert not any(
            task is not original and "旅骨" in row
            for task in tasks
            for row in task.plan.values()
        )
        assert any(
            task.type == TaskTypes.SHIFT_ON and "能天使" in row
            for task in tasks
            for row in task.plan.values()
        )
        assert any(
            task.strict_mood_limit
            and task.release_dorm_targets() == {"空爆": ("dormitory_1", 3)}
            for task in tasks
        )
        assert sum(task is original for task in tasks) == 1
        assert original.__dict__ == before
        assert find_next_task([original]) is None
    tasks = plan_metadata(data, [task for task in tasks if task is not original])
    assert sum("旅骨" in row for task in tasks for row in task.plan.values()) == 1


@pytest.mark.parametrize("state", ["paused", "reopened", "restored"])
def test_confirmation_names_and_positions_survive_remaining_plan_cleanup(
    partial_confirmation, state
):
    data, task = partial_confirmation
    if state == "reopened":
        del task.execution_failure
        task.execution_retained = True
    elif state == "restored":
        task = pickle.loads(pickle.dumps(task))
    names, slots = retained_task_reservations(data, [task])
    assert "旅骨" in names
    assert ("dormitory_1", 4) in slots
    assert {"银灰", "旅骨"} <= names
    assert not {"能天使", "讯使", "空爆"} & names
    assert retained_task_reservations(data, [task], current_task=task) == (set(), set())


def test_expected_position_preserves_actual_occupant_reservation(partial_confirmation):
    data, task = partial_confirmation
    actual = data.operators["砾"]
    actual._current_room, actual.current_index = "dormitory_1", 4
    task.group_shift_expected[("dormitory_1", 4)] = "Free"
    names, slots = retained_task_reservations(data, [task])
    assert actual.name in names
    assert ("dormitory_1", 4) in slots
    assert not {"Current", "Free", ""} & names


def test_incidental_confirmation_targets_keep_normal_group_return_exemption(
    partial_confirmation,
):
    data, task = partial_confirmation
    task.group_shift_expected[("dormitory_1", 2)] = "讯使"
    standby = data.operators["讯使"]
    standby._current_room, standby.current_index = "dormitory_1", 2
    held_names, held_slots = retained_task_reservations(data, [task])
    assert {"能天使", "讯使"} <= held_names
    assert ("dormitory_1", 2) in held_slots
    names, slots = retained_task_reservations(data, [task], returning_groups={"乙组"})
    assert not {"能天使", "讯使"} & names
    assert ("dormitory_1", 2) not in slots
    assert "旅骨" in names and ("dormitory_1", 4) in slots
    tasks = plan_metadata(data, [task])
    assert any(
        planned.type == TaskTypes.SHIFT_ON and "能天使" in row
        for planned in tasks
        for row in planned.plan.values()
    )


@pytest.fixture
def observed_incidental_return(partial_confirmation):
    data, task = partial_confirmation
    task.backup_shift_intent = copy.deepcopy(task.plan)
    task.plan["dormitory_1"] = [
        "Current",
        "Current",
        "能天使",
        "讯使",
        "Current",
    ]
    task.dorm_fill_plan = {"dormitory_1": task.plan["dormitory_1"].copy()}
    task.group_shift_expected.update(
        {("dormitory_1", 2): "能天使", ("dormitory_1", 3): "讯使"}
    )
    task.group_shift_transitions = {"甲组": True, "乙组": True}
    task.execution_failure["snapshot"] = {"observations": {}}
    for name, old_index in (("能天使", 2), ("讯使", 3)):
        op = data.operators[name]
        task.execution_failure["snapshot"]["observations"][name] = (
            "dormitory_1",
            old_index,
            op.time_stamp - timedelta(minutes=1),
        )
        op._current_room, op.current_index = op.room, op.index
    return data, task


def test_confirmed_incidental_return_is_not_reserved_again_after_reopening(
    observed_incidental_return,
):
    data, task = observed_incidental_return
    original_time, original_failure = task.time, task.execution_failure
    assert reconcile_retained_recovery(data, task) == {"乙组"}
    assert task.group_shift_expected == {
        ("dormitory_1", 4): "旅骨",
        ("dormitory_2", 2): "银灰",
    }
    assert task.group_shift_transitions == {"甲组": True}
    assert "dormitory_1" not in task.plan
    assert task.dorm_fill_plan == {}
    assert task.time is original_time and task.execution_failure is original_failure
    del task.execution_failure
    task.execution_retained = True
    task = pickle.loads(pickle.dumps(task))
    names, slots = retained_task_reservations(data, [task])
    assert not {"能天使", "讯使"} & names
    assert {"旅骨", "银灰"} <= names
    assert not {("dormitory_1", 2), ("dormitory_1", 3)} & slots


@pytest.mark.parametrize("observation", ["predicted", "incomplete", "explicit"])
def test_incidental_confirmation_cleanup_keeps_unconfirmed_or_explicit_groups(
    observed_incidental_return, observation
):
    data, task = observed_incidental_return
    if observation == "predicted":
        data.operators["能天使"].mood_is_prediction = True
    elif observation == "incomplete":
        op = data.operators["讯使"]
        op.resting_priority = "high"
        op._current_room, op.current_index = "dormitory_1", 2
    else:
        task.backup_shift_intent["dormitory_1"] = task.plan["dormitory_1"].copy()
        task.backup_explicit_slots = {("dormitory_1", 2)}
    before = copy.deepcopy(task.__dict__)
    assert reconcile_retained_recovery(data, task) == set()
    assert task.__dict__ == before


def test_incidental_cleanup_preserves_working_confirmation_targets(
    observed_incidental_return,
):
    data, task = observed_incidental_return
    task.group_shift_expected[("meeting", 0)] = "能天使"
    assert reconcile_retained_recovery(data, task) == {"乙组"}
    assert task.group_shift_expected[("meeting", 0)] == "能天使"
    assert ("dormitory_1", 2) not in task.group_shift_expected


def test_remaining_confirmation_does_not_reverse_an_observed_group_return(
    observed_incidental_return,
):
    with patch.dict(sys.modules, {"arknights_mower.utils.skland": Mock()}):
        from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    data, task = observed_incidental_return
    data.commit_group_shifts({"甲组": False, "乙组": False})
    assert reconcile_retained_recovery(data, task) == {"乙组"}
    for (room, index), name in task.group_shift_expected.items():
        op = data.operators[name]
        op._current_room, op.current_index = room, index
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.task, solver.tasks = data, task, [task]
    solver.waiting_group_shifts = []
    assert solver._complete_group_shift(task)
    assert data.group_is_resting("甲组")
    assert not data.group_is_resting("乙组")
    assert task.group_shift_expected == {}
    assert not task.retains_execution
