"""补床与清退统一确认未知心情，缓存缺失不等同于无人需要恢复。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils import resting_priority
from arknights_mower.utils.dorm_candidates import (
    dorm_candidates,
    dorm_task_reservations,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


@pytest.mark.parametrize("task_type", [TaskTypes.NOT_SPECIFIC, TaskTypes.SHIFT_OFF])
def test_ordinary_arrangement_searches_unknown_before_retaining_full_resident(
    solver, task_type
):
    instance, selected = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    instance.task.type = task_type
    instance.task.meta_data = ""
    plan = instance.task.plan[ROOM]
    candidates = instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "Free"
    assert "红" in candidates
    assert not data.operators["空爆"].dorm_mood_fallback
    instance.choose_agent(plan, ROOM, dorm_mood_candidates=candidates)
    assert plan[-1] == "红"
    assert selected == plan
    data.update_detail("红", 8, ROOM, 4, True)
    assert not data.idle_dorm_search_exhausted
    assert not data.is_full_dorm_fallback("红")


def test_empty_bed_compares_unknown_with_known_full_candidate(solver):
    instance, selected = solver
    data = instance.op_data
    data.update_detail("空爆", 24, "", -1, True)
    selected.pop()
    data.operators["红"].time_stamp = None
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    plan = instance.task.plan[ROOM]
    candidates = instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "Free"
    assert {"红", "空爆"} <= set(candidates)
    scan = instance.scan_agent.side_effect

    def lowest(names, max_agent_count=None, **kwargs):
        if max_agent_count:
            names.sort(key=lambda name: name != "红")
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = lowest
    instance.choose_agent(plan, ROOM, dorm_mood_candidates=candidates)
    assert plan[-1] == "红"
    data.update_detail("红", 9, ROOM, 4, True)
    assert not data.idle_dorm_search_exhausted


def test_unknown_search_preserves_unfinished_resident(solver):
    instance, _ = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    data.operators["空爆"].mood = 8
    data.operators["空爆"].time_stamp = datetime.now()
    instance.task.type = TaskTypes.SHIFT_OFF
    instance.task.meta_data = ""
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "空爆"
    assert not data.operators["空爆"].dorm_mood_fallback


@pytest.mark.parametrize("invalid", ["missing", "out_of_range"])
def test_candidate_states_separate_unknown_from_verified_full(
    solver, monkeypatch, invalid
):
    instance, _ = solver
    data = instance.op_data
    if invalid == "missing":
        data.operators["红"].time_stamp = None
    else:
        data.operators["红"].mood = -1
    data.add(Operator("陈", "", mood=24, time_stamp=datetime.now()))
    monkeypatch.setattr(resting_priority, "agent_list", [*data.operators, "伊芙利特"])
    candidates = instance.get_dorm_candidates([])
    assert candidates.recovering == []
    assert candidates.full == ["陈"]
    assert set(candidates.unknown) == {"红", "伊芙利特"}
    assert "红" not in candidates.full


def test_execution_and_planning_share_standby_and_room_reservations(
    solver, monkeypatch
):
    instance, _ = solver
    data = instance.op_data
    data.operators["银灰"].mood = 8
    monkeypatch.setattr(data, "is_standby", lambda name: name == "银灰")
    pending = SchedulerTask(
        task_plan={"meeting": ["银灰", "红"], ROOM: ["Current"] * 4 + ["Free"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    instance.task = None
    instance.tasks = [pending]
    reserved, slots = dorm_task_reservations(data, instance.tasks)
    assert reserved == {"红"}
    assert slots == {(ROOM, 4)}
    planned = dorm_candidates(data, reserved)
    executing = instance.get_dorm_candidates([])
    assert planned.filling == executing.filling
    assert executing.recovering == ["银灰"]


def test_ordinary_unknown_comparison_can_keep_the_original_lowest_resident(solver):
    instance, selected = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    instance.task.dorm_mood_residents = ["空爆"]
    scan = instance.scan_agent.side_effect
    comparisons = []

    def lowest(names, max_agent_count=None, **kwargs):
        if max_agent_count:
            comparisons.append(set(names))
            assert {"空爆", "红"} <= set(names)
            names.sort(key=lambda name: name != "空爆")
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = lowest
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert comparisons
    assert plan[-1] == "空爆"
    assert selected == plan


def test_batch_comparison_does_not_borrow_residents_from_another_dorm(solver):
    instance, _ = solver
    data = instance.op_data
    data.operators["红"].time_stamp = None
    data.add(
        Operator(
            "陈",
            "",
            mood=24,
            time_stamp=datetime.now(),
            current_room="dormitory_2",
            current_index=4,
        )
    )
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    instance.task.dorm_mood_residents = ["空爆", "陈"]
    instance.task.plan["dormitory_2"] = ["Current"] * 4 + ["Free"]
    first = instance.dorm_mood_fallback_candidates(instance.task.plan[ROOM], ROOM)
    assert {"空爆", "红"} <= set(first)
    assert "陈" not in first
    # 前一房间已经完成后，后续房间不能再搬走它的入住者。
    del instance.task.plan[ROOM]
    second = instance.get_free_list(["Free"], include_full=True, room="dormitory_2")
    assert "陈" in second
    assert "空爆" not in second


@pytest.mark.parametrize("invalid", ["default", "missing", "out_of_range"])
@pytest.mark.parametrize("deadline", [None, "future", "expired"])
def test_unknown_main_resident_needs_completion_evidence_in_planning_and_selection(
    solver, invalid, deadline
):
    instance, _ = solver
    data = instance.op_data
    resident = data.operators["空爆"]
    resident.operator_type, resident.resting_priority = "high", "high"
    resident.mood = {"default": 24, "missing": 8, "out_of_range": -1}[invalid]
    resident.time_stamp = datetime.now() if invalid == "out_of_range" else None
    data.operators["红"].mood = 10
    data.dorm[0].time = (
        None
        if deadline is None
        else datetime.now() + timedelta(hours=3 if deadline == "future" else -3)
    )
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    expected = "红" if deadline == "expired" else resident.name
    if deadline == "expired":
        assert tasks[0].plan[ROOM][-1] == expected
    else:
        assert tasks == []
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    plan = instance.task.plan[ROOM]
    instance.prepare_dorm_selection(plan, ROOM)
    assert plan[-1] == expected
    assert not resident.dorm_mood_fallback


def test_unknown_resident_does_not_gain_verified_full_fallback(solver):
    instance, _ = solver
    data = instance.op_data
    resident = data.operators["空爆"]
    resident.time_stamp = None
    data.dorm[0].time = datetime.now() + timedelta(hours=3)
    data.operators["红"].time_stamp = None
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    plan = instance.task.plan[ROOM]
    instance.prepare_dorm_selection(plan, ROOM)
    assert plan[-1] == resident.name
    assert not resident.dorm_mood_fallback
    resident.dorm_mood_fallback = ROOM
    assert not data.is_full_dorm_fallback(resident.name)
