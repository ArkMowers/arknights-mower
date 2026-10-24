"""同次下班使用替班接岗后腾出的床位，不提前移动实际驻员。"""

from copy import deepcopy
from datetime import datetime

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests import dorm_release_tests
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import TaskTypes

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data


@pytest.fixture
def solver(op_data, monkeypatch):
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    data = op_data
    data.first_init = False
    data.config.resting_threshold = 0.65
    data.config.resting_priority_replacement = ["红"]
    main, cover = data.operators["银灰"], data.operators["红"]
    main._current_room, main.current_index = "meeting", 0
    main.mood = 0
    data.operators["空爆"]._current_room = ""
    cover._current_room, cover.current_index = ROOM, 4
    data.dorm[0].name = cover.name
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data, instance.tasks, instance.task = data, [], None
    instance._protected_training_names = lambda: set()
    instance._refresh_deferred_product_reservations = lambda: None
    instance.check_fia = lambda: (None, None)
    return instance


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("cover_mood", [10, 24])
@pytest.mark.parametrize("main_mood", [0, 15])
def test_departure_uses_bed_of_its_selected_priority_cover(
    solver, free_room, cover_mood, main_mood
):
    data = solver.op_data
    data.config.free_room = free_room
    data.operators["红"].mood = cover_mood
    data.operators["银灰"].mood = main_mood
    before = deepcopy({name: vars(op) for name, op in data.operators.items()})
    plan, covers = {}, []

    assert solver.get_resting_plan(["银灰"], covers, plan, 0)

    assert plan == {"meeting": ["红"]}
    assert covers == ["红"]
    assert data.dorm[0].name == "银灰"
    assert data.dorm[0].time is None
    assert {name: vars(op) for name, op in data.operators.items()} == before
    assert solver.tasks == []


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("mood", [0, 15, 16])
def test_normal_planner_departs_at_threshold_with_cover_in_dorm(
    solver, free_room, mood
):
    data = solver.op_data
    data.config.free_room = free_room
    main = data.operators["银灰"]
    main.mood = mood
    solver.total_agent = [main]

    plan = solver.resting()

    if mood <= 15:
        assert plan == {"meeting": ["红"]}
        departures = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]
        assert len(departures) == 1
        assert departures[0].plan == plan
        assert data.dorm[0].name == main.name
    else:
        assert plan == {}
        assert not any(task.type == TaskTypes.SHIFT_OFF for task in solver.tasks)
        assert data.dorm[0].name == "红"
    assert main.current_room == "meeting"
    assert data.operators["红"].current_room == ROOM


def test_departure_cannot_take_an_unrelated_protected_bed(solver):
    data = solver.op_data
    data.operators["红"]._current_room, data.operators["红"].current_index = "", -1
    resident = data.operators["空爆"]
    resident._current_room, resident.current_index = ROOM, 4
    data.config.ope_resting_priority = [resident.name]
    resident.mood = 10
    data.dorm[0].name = resident.name
    before = deepcopy(vars(data.dorm[0]))
    plan, covers = {}, []

    assert not solver.get_resting_plan(["银灰"], covers, plan, 0)

    assert plan == {} and covers == []
    assert vars(data.dorm[0]) == before
    assert resident.current_room == ROOM


@pytest.mark.parametrize("free_room", [False, True])
def test_primary_recovery_queues_cover_and_arrival_together(
    solver, free_room, offline_maintenance
):
    data = solver.op_data
    data.config.free_room = free_room
    data.operators["红"].mood = 24

    assert solver._plan_primary_recovery(scan_moods=False)

    departures = [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]
    assert len(departures) == 1
    assert departures[0].plan == {
        "meeting": ["红"],
        ROOM: ["Current"] * 4 + ["银灰"],
    }
    assert data.operators["红"].current_room == ROOM
    assert data.operators["银灰"].current_room == "meeting"


def test_failed_departure_keeps_cover_bed_and_observations(solver):
    data = solver.op_data
    data.plan["meeting"].append(Room("能天使", "", ["陈"]))
    data.add(
        Operator("能天使", "meeting", index=1, replacement=["陈"], operator_type="high")
    )
    data.add(Operator("陈", "", mood=24, time_stamp=datetime.now()))
    main = data.operators["能天使"]
    main._current_room, main.current_index = "meeting", 1
    before = deepcopy((data.operators, data.dorm))
    plan, covers = {}, []

    assert not solver.get_resting_plan(["银灰", "能天使"], covers, plan, 0)

    assert plan == {} and covers == []
    assert [vars(op) for op in data.operators.values()] == [
        vars(op) for op in before[0].values()
    ]
    assert [vars(bed) for bed in data.dorm] == [vars(bed) for bed in before[1]]
