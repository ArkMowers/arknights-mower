"""宿舍优先满员；只有强制心情上限允许无接替者时清空。"""

from datetime import datetime
from types import MethodType

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import dorm_release_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import resting_priority
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
    # 本组模拟账号仅有已登记的这些干员；未登记空闲者由专门用例加入。
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
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


def test_all_full_release_keeps_resident_without_another_release(solver):
    instance, selected = solver
    plan = instance.task.plan
    assert instance.get_free_list([]) == []
    instance.choose_agent(plan[ROOM], ROOM)
    assert selected == plan[ROOM]
    assert plan[ROOM][4] == "空爆"
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


def test_unknown_mood_only_fills_empty_beds(solver):
    instance, _ = solver
    instance.op_data.operators["红"].time_stamp = None
    instance.op_data.add(Operator("陈", ""))
    free = instance.get_free_list([])
    assert "红" not in free
    assert "陈" not in free
    assert "空爆" not in free
    assert {"红", "陈"} <= set(instance.get_free_list([], include_full=True))
    # 未知心情不触发二次试住，也不清退已满的原住者。
    plan = instance.task.plan[ROOM]
    assert instance.dorm_mood_fallback_candidates(plan, ROOM) == []
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "空爆"


def test_clearing_inner_bed_tracks_compacted_positions(solver):
    instance, selected = solver
    data = instance.op_data
    data.plan[ROOM][3] = Room("Free", "", [])
    data.operators["空爆"].mood = 10
    data.plan["meeting"][0].replacement.append("桃金娘")
    for name in ("桃金娘", "红"):
        data.config.operator_mood_limits[name] = {"lower": 0, "upper": 20}
        data.operators[name].upper_limit = 20
    plan = instance.task.plan[ROOM]
    plan[3:] = ["Free", "空爆"]
    instance.choose_agent(plan, ROOM)
    assert plan[3:] == ["空爆", ""]
    assert selected == plan[:4]


def test_empty_bed_accepts_known_full_operator_without_repeated_release(solver):
    instance, selected = solver
    data = instance.op_data
    data.update_detail("空爆", 24, "", -1, True)
    selected.pop()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    incoming = tasks[0].plan[ROOM][-1]
    assert data.operators[incoming].mood == 24
    instance.task = tasks[0]
    plan = instance.op_data.get_current_room(ROOM, True)
    plan[-1] = incoming
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == incoming
    assert selected == plan
    data.update_detail(incoming, 24, ROOM, 4, True)
    for _ in range(3):
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []


def test_no_full_for_full_replacement_when_dorm_is_occupied(solver):
    instance, _ = solver
    data = instance.op_data
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "空爆"
    assert data.is_full_dorm_fallback("空爆")


def test_empty_bed_remains_empty_if_all_candidates_have_reached_strict_cap(solver):
    instance, _ = solver
    data = instance.op_data
    data.plan["meeting"][0].replacement.append("空爆")
    data.config.operator_mood_limits = {
        name: {"lower": 0, "upper": 20}
        for name in data.operators
        if data.is_planned_operator(name)
    }
    for op in data.operators.values():
        data.apply_custom_mood_limits(op)
    data.update_detail("空爆", 24, "", -1, True)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []
    instance.task.meta_data = ""
    plan = ["Current"] * 4 + ["Free"]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == ""


@pytest.mark.parametrize("limit", [20, 24])
def test_unknown_replacement_fills_empty_bed_and_real_read_controls_recovery(
    solver, limit
):
    instance, _ = solver
    data = instance.op_data
    data.config.mood_limits = {"lower": 0, "upper": limit}
    for op in data.operators.values():
        data.apply_custom_mood_limits(op)
    data.operators["红"].time_stamp = None
    data.operators["空爆"].current_room = "meeting"
    data.dorm[0].name = ""
    data.dorm[0].time = None
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"
    data.update_detail("红", 8, ROOM, 4, True)
    assert not data.is_full_dorm_fallback("红")
    assert data.operators["红"].mood == 8
