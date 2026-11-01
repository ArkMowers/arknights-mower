"""失床补偿保留仍被其他下班组需要的共享干员与具名恢复目标。"""

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.multi_group_shift_tests import SHARED as WORKER
from arknights_mower.tests.multi_group_shift_tests import A, B, apply, shift_off
from arknights_mower.tests.multi_group_shift_tests import dorm_solver as dorm_solver
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
)

DORM = "dormitory_3"
SHARED = ("岳羽由加莉", "埃癸斯")
INCOMING = "凯尔希·思衡托"


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    def unexpected_io(*args, **kwargs):
        pytest.fail("排班补偿回归禁止设备、网络与数据库访问")

    monkeypatch.setattr("socket.socket.connect", unexpected_io)
    monkeypatch.setattr("requests.sessions.Session.request", unexpected_io)
    monkeypatch.setattr("sqlite3.connect", unexpected_io)


@pytest.fixture
def shared_solver(solver, monkeypatch):
    solver.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [Room("诗怀雅", "赤金线", ["火龙S黑角"])],
                "factory": [Room("至简", "赤金线", [SHARED[0]])],
                "contact": [Room(INCOMING, "公招", ["斥罪"])],
                "train": [Room("逻各斯", "公招", [SHARED[0]])],
                "room_2_3": [Room("烛煌", "公招", [SHARED[1]])],
                "room_3_1": [Room("结城理", "sees", ["玛露西尔"])],
                "dormitory_1": [
                    Room("流明", "", []),
                    Room("聆音", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
                DORM: [
                    Room("斥罪", "公招", ["夜莺"]),
                    Room("琴柳", "", []),
                    *[
                        Room(
                            name,
                            "sees",
                            ["Free"],
                            group_bindings=[
                                {"group": "赤金线", "replacement": ["Free"]},
                                {"group": "公招", "replacement": ["Free"]},
                            ],
                        )
                        for name in SHARED
                    ],
                    Room("Free", "", []),
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    assert solver.initialize_operators() is None
    data = solver.op_data
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 8, datetime.now()
    for name in ("至简", *SHARED):
        data.operators[name]._current_room, data.operators[name].current_index = "", -1
    data.operators[SHARED[0]]._current_room = "factory"
    data.operators[SHARED[0]].current_index = 0
    data.operators["诗怀雅"]._current_room = DORM
    data.operators["诗怀雅"].current_index = 3
    data.operators["火龙S黑角"]._current_room = "meeting"
    data.operators["火龙S黑角"].current_index = 0
    data.commit_group_shifts({"赤金线": True, "公招": False, "sees": False})
    for bed in data.all_dorms():
        resident = data.get_current_operator(*bed.position)
        if resident is not None:
            bed.name = resident.name
            bed.time = datetime.now() + timedelta(hours=2)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(base_schedule, "save_current_state", MagicMock())
    return solver


def shift_plan():
    return {
        "meeting": ["诗怀雅"],
        "factory": ["至简"],
        "contact": ["斥罪"],
        "train": [SHARED[0]],
        "room_2_3": [SHARED[1]],
        "room_3_1": ["结城理"],
        DORM: ["夜莺", "Current", INCOMING, "Free", "Free"],
    }


@pytest.mark.parametrize("consumed_work", [False, True])
def test_arrangement_preserves_pending_off_group_and_confirms_named_dorm_target(
    shared_solver, monkeypatch, consumed_work
):
    solver = shared_solver
    data = solver.op_data
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=shift_plan())
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected[DORM, 2] == INCOMING
    assert task.group_shift_transitions["公招"] is True
    if consumed_work:
        for room in list(task.plan):
            if room.startswith("dorm"):
                continue
            for index, name in enumerate(task.plan.pop(room)):
                for op in data.operators.values():
                    if (op.current_room, op.current_index) == (room, index):
                        op._current_room, op.current_index = "", -1
                data.operators[name]._current_room = room
                data.operators[name].current_index = index
    confirmed = deepcopy(data.group_shift_state)
    selected = {}

    def arrange_room(new_plan, room, plan, **kwargs):
        names = plan.pop(room)
        if room.startswith("dorm"):
            solver._check_group_shift_targets(names, room, reason="回归验证")
        selected[room] = list(names)
        for index, name in enumerate(names):
            if name in ("Current", "Free", ""):
                continue
            for op in data.operators.values():
                if (op.current_room, op.current_index) == (room, index):
                    op._current_room, op.current_index = "", -1
            data.operators[name]._current_room = room
            data.operators[name].current_index = index
        return new_plan

    monkeypatch.setattr(solver, "agent_arrange_room", arrange_room)
    solver.agent_arrange(task.plan)

    assert selected[DORM][2] == INCOMING
    assert not set(SHARED) & set(selected[DORM])
    assert data.operators[SHARED[0]].current_room == "train"
    assert data.operators[SHARED[1]].current_room == "room_2_3"
    assert data.group_shift_state == confirmed
    assert not config.stop_mower.is_set()
    assert solver._complete_group_shift(task)
    assert data.group_is_resting("公招")
    assert not data.group_is_resting("赤金线")
    assert not data.group_is_resting("sees")


@pytest.mark.parametrize("role", ["worker", "dorm"])
@pytest.mark.parametrize("first,second", [("甲", "乙"), ("乙", "甲")])
def test_exclusive_covers_wait_for_group_return(request, role, first, second):
    solver = request.getfixturevalue("solver" if role == "worker" else "dorm_solver")
    follower = WORKER if role == "worker" else "塑心"
    room = "contact" if role == "worker" else "dormitory_1"
    for name in (A, B, follower):
        solver.op_data.operators[name].mood = 8
    covers = {"甲": "红", "乙": "黑角"}
    assert shift_off(solver, first)[0]
    data = solver.op_data
    before_state = deepcopy(data.group_shift_state)
    before_beds = [(bed.name, bed.time) for bed in data.all_dorms()]
    before_binding = data.operators[follower].group

    admitted, rejected = shift_off(solver, second)

    assert not admitted and rejected == {}
    assert data.group_shift_state == before_state
    assert [(bed.name, bed.time) for bed in data.all_dorms()] == before_beds
    assert data.operators[follower].group == before_binding
    assert data.get_current_operator(room, 0).name == covers[first]
    anchor = A if first == "甲" else B
    recall = {
        data.operators[anchor].room: ["Current"]
        * len(data.plan[data.operators[anchor].room])
    }
    recall[data.operators[anchor].room][data.operators[anchor].index] = anchor
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=recall)
    solver._prepare_group_shift(task)
    recall = task.plan

    assert recall[room][0] == follower
    assert data.group_shift_state == before_state
    apply(solver, recall)
    assert not solver.op_data.group_is_resting(first)
    admitted, plan = shift_off(solver, second)
    assert admitted and plan[room][0] == covers[second]
    assert solver.op_data.group_is_resting(second)
    assert not solver.op_data.group_is_resting(first)


@pytest.mark.parametrize("first,second", [("甲", "乙"), ("乙", "甲")])
def test_overlapping_covers_keep_common_candidate_through_group_return(
    solver, first, second
):
    slot = solver.global_plan["default_plan"].plan["contact"][0]
    slot.replacement = ["红", "黑角"]
    slot.group_bindings[0]["replacement"] = ["黑角", "砾"]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 8, datetime.now()
    assert shift_off(solver, first)[0]
    assert shift_off(solver, second)[0]
    data = solver.op_data
    assert data.get_current_operator("contact", 0).name == "黑角"
    bed = data.get_dorm_by_name(WORKER)[1]
    bed.time = datetime.now() + timedelta(hours=2)
    recovery = bed.position, bed.name, bed.time
    anchor = A if first == "甲" else B
    recall = {
        data.operators[anchor].room: ["Current"]
        * len(data.plan[data.operators[anchor].room])
    }
    recall[data.operators[anchor].room][data.operators[anchor].index] = anchor
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=recall)
    solver._prepare_group_shift(task)
    recall = task.plan

    assert "contact" not in recall
    assert (bed.position, bed.name, bed.time) == recovery
    assert data.get_current_operator("contact", 0).name == "黑角"
    apply(solver, recall)
    assert solver.op_data.group_is_resting(second)
    assert not solver.op_data.group_is_resting(first)
    assert solver.op_data.get_current_operator("contact", 0).name == "黑角"
