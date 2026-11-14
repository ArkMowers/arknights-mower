"""工作换位的主班回原位前，必须在完整交接中接回其覆盖岗位。"""

from copy import deepcopy
from datetime import datetime

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.tests.mood_calculation_projection_consumers_tests import enable
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = exhaust_replacement_tests.solver


@pytest.fixture(params=[False, True], ids=["same-group", "multiple-binding"])
def working_chain(solver, request):
    plan = solver.global_plan["default_plan"].plan
    plan["room_3_3"][0].replacement = ["灰毫"]
    plan["room_2_2"][0].replacement = ["槐琥"]
    plan["room_1_1"] = [
        Room(
            "槐琥",
            "红松" if request.param else "感知",
            ["灰毫"],
            group_bindings=[{"group": "感知", "replacement": ["灰毫"]}]
            if request.param
            else None,
        )
    ]
    assert solver.initialize_operators() is None
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "room_3_3": ["机械师"],
                "room_1_1": ["灰毫"],
                "room_2_2": ["槐琥"],
                "contact": ["斥罪"],
                "meeting": ["能天使"],
                "dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "Free"],
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp = 12, datetime.now()
    solver.op_data.operators["机械师"].mood = 0
    assert solver.op_data.is_same_group_primary_replacement(
        solver.op_data.operators["苍苔"], "槐琥"
    )
    if request.param:
        assert solver.op_data.operators["槐琥"].shift_group == "红松"
        assert not solver.op_data.group_is_resting("红松")
    return solver


@pytest.mark.parametrize("calculated", [False, True])
def test_exhaust_support_restores_complete_legal_working_chain(
    working_chain, monkeypatch, calculated
):
    solver = working_chain
    if calculated:
        enable(solver.op_data, datetime.now(), monkeypatch)
    before = deepcopy(
        solver.op_data, {id(solver.op_data.eval_model): solver.op_data.eval_model}
    )
    original = solver.task
    at, request = original.time, original.meta_data
    solver.overtake_room()
    support = next(task for task in solver.tasks if task is not original)
    assert support.plan["room_1_1"] == ["槐琥"]
    assert support.plan["room_2_2"] == ["苍苔"]
    assert support.plan["contact"] == ["絮雨"]
    assert (
        original in solver.tasks
        and original.time == at
        and original.meta_data == request
    )
    assert {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    } == {
        name: (op.current_room, op.current_index)
        for name, op in before.operators.items()
    }
    solver.task = support
    assert solver._coordination_support_valid(support.plan, ["机械师"])
    solver._validate_calculated_arrangement()
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    solver.tasks, solver.task = [], original
    solver.overtake_room()
    departure = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.plan["room_3_3"] == ["灰毫"]
    assert "机械师" in departure.plan["dormitory_1"]
    assert solver.op_data.operators["槐琥"].current_room == "room_1_1"
    final = solver.op_data.project_arrangements([departure.plan])
    assert all(
        op.mood > op.lower_limit
        for op in final.operators.values()
        if op.is_working() and not op.workaholic
    )
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("urgent", [False, True])
def test_remote_owner_alternate_cannot_replace_complete_chain_return(
    working_chain, monkeypatch, urgent
):
    solver = working_chain
    data = solver.op_data
    data.operators["苍苔"].replacement.append("引星棘刺")
    data.plan["room_2_2"][0].replacement.append("引星棘刺")
    data.add(Operator("引星棘刺", "", mood=12, time_stamp=datetime.now()))
    from arknights_mower.utils import recall_estimates

    rates = ({name: 1 for name in data.operators}, {name: 4 for name in data.operators})
    monkeypatch.setattr(
        recall_estimates, "estimated_recall_rates", lambda *a, **k: rates
    )
    support = solver._plan_exhaust_support(["机械师"], urgent=urgent)
    assert support and support["room_1_1"] == ["槐琥"]
    assert support["room_2_2"] == ["苍苔"]


@pytest.mark.parametrize(
    "blocked",
    [
        "foreign-working",
        "missing-cover",
        "explicit-full",
        "name",
        "source-slot",
        "middle-slot",
        "beds",
        "busy",
    ],
)
def test_blocked_working_chain_preserves_request_and_actual_occupancy(
    working_chain, monkeypatch, blocked
):
    solver = working_chain
    data = solver.op_data
    if blocked == "foreign-working":
        data.operators["苍苔"].replacement = ["斥罪"]
        data.plan["room_2_2"][0].replacement = ["斥罪"]
    elif blocked == "missing-cover":
        data.operators["机械师"].replacement = []
        data.plan["room_3_3"][0].replacement = []
    elif blocked == "explicit-full":
        data.operators["絮雨"].rest_in_full = True
    elif blocked in ("name", "source-slot", "middle-slot", "beds"):
        lock = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
        lock.product_shift_locked = True
        lock.product_lock_names = {"槐琥"} if blocked == "name" else set()
        lock.product_lock_slots = (
            {bed.position for bed in data.dorm}
            if blocked == "beds"
            else {("room_1_1" if blocked == "source-slot" else "room_2_2", 0)}
            if blocked != "name"
            else set()
        )
        if blocked == "beds":
            reserved = ["夜烟", "夜刀", "黑角"]
            for name in reserved:
                data.add(Operator(name, "", mood=12, time_stamp=datetime.now()))
            lock.plan = {"dormitory_1": ["Current", "Current", *reserved]}
            lock.product_lock_names = set(reserved)
        solver.tasks = [lock]
    elif blocked == "busy":
        monkeypatch.setattr(
            exhaust_replacement_tests.base_schedule,
            "_is_mastery_busy",
            lambda name: name == "槐琥",
        )
    before = deepcopy(data, {id(data.eval_model): data.eval_model})
    previous_tasks = list(solver.tasks)
    original = solver.task
    original_time, original_request = original.time, original.meta_data
    solver.overtake_room()
    assert solver.tasks == [*previous_tasks, original]
    assert original.time == original_time and original.meta_data == original_request
    assert original.execution_failure
    assert [(bed.name, bed.time) for bed in data.all_dorms()] == [
        (bed.name, bed.time) for bed in before.all_dorms()
    ]
    assert {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    } == {
        name: (op.current_room, op.current_index)
        for name, op in before.operators.items()
    }
    solver.enter_room.assert_not_called()


def test_effective_replacement_change_keeps_actual_owner_recovery_dependency(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["结城理"]
    data.plan["room_2_2"][0].replacement = ["结城理"]
    support = solver._plan_exhaust_support(["机械师"], urgent=True)
    assert support == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    assert data.operators["槐琥"].current_room == "room_2_2"


@pytest.mark.parametrize("calculated", [False, True])
@pytest.mark.parametrize("protection", ["full", "personal-limit"])
@pytest.mark.parametrize("mood,allowed", [(12, False), (24, True), (None, False)])
def test_working_full_member_must_be_ready_before_support_and_execution(
    working_chain, monkeypatch, calculated, protection, mood, allowed
):
    solver = working_chain
    data = solver.op_data
    now = datetime.now()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(exhaust_replacement_tests.base_schedule, "datetime", Clock)
    data._projection_now = now
    for op in data.operators.values():
        op.time_stamp, op.depletion_rate = now, 0
    member = data.operators["槐琥"]
    member.rest_in_full = protection == "full"
    scale = 1 if protection == "full" else 0.5
    if protection == "personal-limit":
        data.config.operator_mood_limits[member.name] = {"lower": 0, "upper": 12}
        member.upper_limit = 12
    member.mood = 12 * scale if mood is None else mood * scale
    if mood is None:
        member.time_stamp = None
    if calculated:
        enable(data, now, monkeypatch, omitted=[member.name] if mood is None else ())
    original = solver.task
    solver.overtake_room()
    supports = [
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    ]
    assert bool(supports) is allowed
    assert original in solver.tasks
    if allowed:
        (support,) = supports
        solver.task = support
        assert solver._coordination_support_valid(support.plan, ["机械师"])
        solver._validate_calculated_arrangement()
        member.mood = 12 * scale
        if calculated:
            data.mood_model.observe(member.name, member.mood, now)
        assert not solver._coordination_support_valid(support.plan, ["机械师"])
        if calculated:
            with pytest.raises(
                exhaust_replacement_tests.base_schedule.MoodArrangementChanged
            ):
                solver._validate_calculated_arrangement()
    else:
        assert solver.tasks == [original]
    solver.enter_room.assert_not_called()
