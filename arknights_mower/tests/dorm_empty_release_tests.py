"""满心情清退真正留空，不用下一位满心情者填床。"""

from datetime import datetime
from types import MethodType

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_add_release_dorm,
)

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data


@pytest.fixture
def solver(op_data, monkeypatch):
    data = op_data
    residents = [slot.agent for slot in data.plan[ROOM]][:4] + ["空爆"]
    for index, name in enumerate(residents):
        data.operators[name]._current_room = ROOM
        data.operators[name].current_index = index
    for op in data.operators.values():
        op.mood, op.depletion_rate, op.time_stamp = 24, 0, datetime.now()
    instance, selected = selection_solver(monkeypatch, residents=residents)
    instance.op_data = data
    instance.tasks = []
    instance.task = SchedulerTask(
        task_plan={ROOM: residents[:4] + ["Free"]},
        task_type=TaskTypes.RELEASE_DORM,
        meta_data="空爆",
    )
    instance.get_free_list = MethodType(BaseSchedulerSolver.get_free_list, instance)
    instance.preserve_resting_crafters = MethodType(
        BaseSchedulerSolver.preserve_resting_crafters, instance
    )
    return instance, selected


def test_all_full_release_leaves_empty_bed_without_another_release(solver):
    instance, selected = solver
    plan = instance.task.plan
    assert instance.get_free_list([]) == []
    instance.choose_agent(plan[ROOM], ROOM)
    assert selected == plan[ROOM][:4]
    assert plan[ROOM][4] == ""
    instance.op_data = instance.op_data.project_arrangements([plan])
    tasks = plan_metadata(instance.op_data, [])
    try_add_release_dorm({}, None, instance.op_data, tasks)
    assert tasks == []
    correction = instance.agent_get_mood(read_rooms=False, return_plan=True)
    assert ROOM not in correction


def test_release_uses_cached_unfinished_replacement(solver):
    instance, _ = solver
    instance.op_data.operators["红"].mood = 10
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[4] == "红"


def test_unknown_replacement_remains_eligible_but_unknown_idle_does_not(solver):
    instance, _ = solver
    instance.op_data.operators["红"].time_stamp = None
    instance.op_data.add(Operator("陈", ""))
    free = instance.get_free_list([])
    assert "红" in free
    assert "陈" not in free
    assert "空爆" not in free


def test_clearing_inner_bed_tracks_compacted_positions(solver):
    instance, selected = solver
    data = instance.op_data
    data.plan[ROOM][3] = Room("Free", "", [])
    data.operators["空爆"].mood = 10
    plan = instance.task.plan[ROOM]
    plan[3:] = ["Free", "空爆"]
    instance.choose_agent(plan, ROOM)
    assert plan[3:] == ["空爆", ""]
    assert selected == plan[:4]
