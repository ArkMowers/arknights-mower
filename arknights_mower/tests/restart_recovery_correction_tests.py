"""重启纠错保留未完成的回满要求，并继续无关主班的回班。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import TaskTypes, plan_metadata


@pytest.fixture(params=[False, True], ids=["fixed-primary", "shared-primary"])
def solver(monkeypatch, request):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "room_3_2": [
                    Room("阿罗玛", "自动化", ["多萝西"]),
                    Room(
                        "槐琥",
                        "自动化",
                        ["淬羽赫默"],
                        group_bindings=(
                            [{"group": "另一组", "replacement": ["淬羽赫默"]}]
                            if request.param
                            else None
                        ),
                    ),
                ],
                **(
                    {"meeting": [Room("银灰", "另一组", ["初雪"])]}
                    if request.param
                    else {}
                ),
                "central": [Room("森蚺", "", ["斑点"])],
                "dormitory_1": [
                    Room("杜林", "", []),
                    Room("桃金娘", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("阿罗玛,槐琥", "", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.op_data = instance.op_data.project_arrangements(
        [
            {
                "room_3_2": ["多萝西", "淬羽赫默"],
                **({"meeting": ["银灰"]} if request.param else {}),
                "central": ["斑点"],
                "dormitory_1": ["杜林", "桃金娘", "槐琥", "森蚺", "Free"],
            }
        ]
    )
    instance.op_data.commit_group_shifts({"自动化": True})
    now = datetime.now()
    for op in instance.op_data.operators.values():
        op.mood, op.time_stamp = 24, now
    unknown = instance.op_data.operators["阿罗玛"]
    unknown.current_room, unknown.current_index, unknown.time_stamp = "", -1, None
    recovering = instance.op_data.operators["槐琥"]
    recovering.mood = 2.4
    instance.op_data.get_dorm_by_name(recovering.name)[1].time = now + timedelta(
        hours=7
    )
    instance.op_data.get_dorm_by_name("森蚺")[1].time = now
    instance.tasks, instance.task = [], None
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    instance._suppress_train_correction = lambda plan: None
    return instance


@pytest.mark.parametrize("cover_available", [False, True])
@pytest.mark.parametrize("expired", [False, True], ids=["future", "expired"])
def test_unknown_idle_group_member_does_not_recall_unfinished_full_member(
    solver, cover_available, expired
):
    if not cover_available:
        cover = solver.op_data.operators["多萝西"]
        cover.current_room, cover.current_index = "contact", 0
    bed = solver.op_data.get_dorm_by_name("槐琥")[1]
    if expired:
        bed.time = datetime.now() - timedelta(seconds=1)
    deadline = bed.time
    for _ in range(3):
        plan = solver.agent_get_mood(skip_dorm=True, read_rooms=False, return_plan=True)
        assert plan.get("central") == ["森蚺"]
        assert "槐琥" not in plan.get("room_3_2", [])
        assert "阿罗玛" not in plan.get("room_3_2", [])
        assert bed.time == deadline
        assert solver.tasks == []
    assert solver.op_data.operators["槐琥"].is_resting()
    assert solver.op_data.operators["阿罗玛"].time_stamp is None
    if not cover_available:
        assert cover.current_room == "contact"
    solver.enter_room.assert_not_called()


def test_confirmed_full_recovery_releases_group_return(solver):
    now = datetime.now()
    bed = solver.op_data.get_dorm_by_name("槐琥")[1]
    bed.time = now - timedelta(seconds=1)
    for name in ("阿罗玛", "槐琥"):
        op = solver.op_data.operators[name]
        op.mood, op.time_stamp = 24, now
    for name in ("多萝西", "淬羽赫默"):
        op = solver.op_data.operators[name]
        op.current_room, op.current_index = "", -1

    plan = solver.agent_get_mood(skip_dorm=True, read_rooms=False, return_plan=True)
    assert plan["room_3_2"] == ["阿罗玛", "槐琥"]

    tasks = plan_metadata(solver.op_data, [])
    returns = [
        task
        for task in tasks
        if task.type == TaskTypes.SHIFT_ON and "room_3_2" in task.plan
    ]
    assert len(returns) == 1
    assert returns[0].plan["room_3_2"] == ["阿罗玛", "槐琥"]
    assert returns[0].time <= datetime.now()
    assert solver.op_data.operators["槐琥"].is_resting()
    solver.enter_room.assert_not_called()


def test_idle_group_without_resting_members_still_returns(solver):
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["杜林", "桃金娘", "Free", "森蚺", "Free"]}]
    )

    plan = solver.agent_get_mood(skip_dorm=True, read_rooms=False, return_plan=True)

    assert plan["room_3_2"] == ["阿罗玛", "槐琥"]
    assert plan["central"] == ["森蚺"]
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("solver", [True], indirect=True, ids=["shared-primary"])
@pytest.mark.parametrize("expired", [False, True], ids=["future", "expired"])
def test_shared_member_keeps_recovery_protection_from_another_binding(
    solver, monkeypatch, expired
):
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["杜林", "桃金娘", "阿罗玛", "森蚺", "Free"]}]
    )
    data, now = solver.op_data, datetime.now()
    data.select_group_binding("槐琥", "另一组")
    primary = data.operators["阿罗玛"]
    primary.mood, primary.time_stamp = 2.4, now
    shared = data.operators["槐琥"]
    shared.rest_in_full, shared.time_stamp = False, None
    cover = data.operators["淬羽赫默"]
    cover.current_room, cover.current_index = "contact", 0
    bed = data.get_dorm_by_name(primary.name)[1]
    deadline = bed.time = now + (
        timedelta(seconds=-1) if expired else timedelta(hours=7)
    )
    data.get_dorm_by_name("森蚺")[1].time = now - timedelta(seconds=1)

    for _ in range(3):
        plan = solver.agent_get_mood(skip_dorm=True, read_rooms=False, return_plan=True)
        assert plan.get("central") == ["森蚺"]
        assert not {"阿罗玛", "槐琥"}.intersection(plan.get("room_3_2", []))
        assert shared.group == "另一组"
        assert bed.time == deadline
        assert solver.tasks == []

    assert solver.agent_get_mood(skip_dorm=True, read_rooms=False) == "self_correction"
    (task,) = solver.tasks
    solver.task = task
    original_time = task.time
    before = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    monkeypatch.setattr(solver, "_read_recovery_rooms", lambda rooms: None)
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    assert solver._verify_required_recovery(task)
    assert task.plan.get("central") == ["森蚺"]
    assert not {"阿罗玛", "槐琥"}.intersection(task.plan.get("room_3_2", []))
    assert not getattr(task, "execution_failure", None)
    assert task.time == original_time
    assert bed.time == deadline
    assert before == {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("expired", [False, True], ids=["future", "expired"])
def test_derived_correction_preparation_keeps_independent_return_executable(
    solver, monkeypatch, expired
):
    bed = solver.op_data.get_dorm_by_name("槐琥")[1]
    if expired:
        bed.time = datetime.now() - timedelta(seconds=1)
    assert solver.agent_get_mood(skip_dorm=True, read_rooms=False) == "self_correction"
    (task,) = solver.tasks
    assert task.derived_correction
    original_time = task.time
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    solver.task = task

    def read(rooms):
        for op in solver.op_data.operators.values():
            if op.current_room in rooms:
                op.time_stamp = datetime.now()

    monkeypatch.setattr(solver, "_read_recovery_rooms", read)
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    assert solver._verify_required_recovery(task)
    assert task.plan.get("central") == ["森蚺"]
    assert "槐琥" not in task.plan.get("room_3_2", [])
    assert not getattr(task, "execution_failure", None)
    assert not getattr(solver, "waiting_group_shifts", [])
    assert task.time == original_time
    assert before == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    solver.enter_room.assert_not_called()
