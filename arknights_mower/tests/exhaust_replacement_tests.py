"""用尽任务协调被占用的替班，不拆休息组、不提前改变实际床位。"""

import ctypes
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.dorm_candidates import dorm_task_reservations  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    generate_plan_by_drom,
)


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    config.conf.enable_mastery = False
    instance = object.__new__(BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "room_3_3": [Room("机械师", "", ["槐琥"])],
                "room_2_2": [Room("苍苔", "感知", ["槐琥", "引星棘刺", "结城理"])],
                "contact": [Room("絮雨", "感知", ["斥罪"])],
                "meeting": [Room("能天使", "", ["陈"])],
                "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                + [Room("Free", "", []) for _ in range(3)],
            },
            PlanConfig("机械师", "机械师", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.op_data = instance.op_data.project_arrangements(
        [
            {
                "room_3_3": ["机械师"],
                "room_2_2": ["槐琥"],
                "contact": ["斥罪"],
                "meeting": ["能天使"],
                "dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "Free"],
            }
        ]
    )
    for op in instance.op_data.operators.values():
        op.time_stamp, op.mood = datetime.now(), 12
    instance.op_data.operators["机械师"].mood = 0
    for bed in instance.op_data.dorm:
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=4)
    instance.tasks = []
    instance.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="机械师")
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    return instance


def run_retained(solver):
    """无法交接时保留原请求和实际驻员，不发送重复通知。"""
    original = solver.task
    original_time, original_plan = original.time, deepcopy(original.plan)
    previous = list(solver.tasks)
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    beds = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    solver.overtake_room()
    assert any(task is original for task in solver.tasks)
    assert all(any(task is old for task in solver.tasks) for old in previous)
    assert original.time == original_time
    assert original.plan == original_plan
    assert original.execution_failure
    assert positions == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    assert beds == [(bed.name, bed.time) for bed in solver.op_data.dorm]
    base_schedule.send_message.assert_not_called()
    return original


def finish_support(solver):
    """前置换班已读屏确认后的状态，再执行动态用尽规划。"""
    support, retry = solver.tasks
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    solver.tasks, solver.task = [], retry
    solver.overtake_room()
    return solver.tasks[0]


@pytest.fixture
def future_exhaust(solver, monkeypatch):
    """只替换倒计时读屏，保留真实用尽任务生成和资源规划。"""
    now = datetime.now()
    op = solver.op_data.operators["机械师"]
    op.mood, op.time_stamp, op.depletion_rate = 1, now, 1
    monkeypatch.setattr(solver, "enter_room", MagicMock())
    monkeypatch.setattr(solver, "back", MagicMock())
    monkeypatch.setattr(
        solver,
        "get_agent_from_room",
        MagicMock(return_value=[{"agent": "机械师", "time": now + timedelta(hours=2)}]),
    )
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    beds = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    support = MagicMock(wraps=solver._plan_exhaust_support)
    monkeypatch.setattr(solver, "_plan_exhaust_support", support)

    solver.run_order_solver()

    (task,) = solver.tasks
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.time > now + timedelta(hours=1)
    assert task.meta_data == "机械师"
    assert task.plan == {}
    assert dorm_task_reservations(solver.op_data, solver.tasks) == (set(), set())
    assert not solver.op_data.reserved_product_replacements
    assert not solver.op_data.reserved_product_beds
    assert before == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    assert beds == [(bed.name, bed.time) for bed in solver.op_data.dorm]
    support.assert_not_called()
    return task


def test_future_exhaust_does_not_reserve_cover_for_normal_group(solver, future_exhaust):
    # 用尽任务尚未执行时，普通组仍能使用同一个替班下班。
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    plan = {}
    solver.get_resting_plan(
        ["苍苔", "絮雨"], [], plan, solver.op_data.active_high_resting_count()
    )
    assert plan["room_2_2"] == ["槐琥"]
    assert plan["contact"] == ["斥罪"]
    assert solver.tasks == [future_exhaust]
    assert future_exhaust.plan == {}


@pytest.mark.parametrize("cover_released", [False, True])
@pytest.mark.parametrize("remaining_mood", [0, 0.18])
def test_exhaust_coordinates_latest_occupancy_at_execution(
    solver, future_exhaust, cover_released, remaining_mood
):
    # 倒计时生成后，原替班已释放，或第一候补已被别处使用。
    change = {"room_2_2": ["引星棘刺"]} if cover_released else {"meeting": ["引星棘刺"]}
    solver.op_data = solver.op_data.project_arrangements([change])
    solver.op_data.operators["机械师"].mood = remaining_mood
    solver.tasks, solver.task = [], future_exhaust
    solver.enter_room.reset_mock()
    solver.overtake_room()

    if cover_released:
        solver._plan_exhaust_support.assert_not_called()
        (task,) = solver.tasks
    else:
        solver._plan_exhaust_support.assert_called_once()
        support, retry = solver.tasks
        assert support.plan == {"room_2_2": ["结城理"]}
        assert retry.type == TaskTypes.EXHAUST_OFF
        assert retry.plan == {}
        assert retry.meta_data == "机械师"
        task = finish_support(solver)
    assert task.type == TaskTypes.SHIFT_OFF
    assert task.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in task.plan["dormitory_1"]
    solver.enter_room.assert_not_called()
    base_schedule.send_message.assert_not_called()


def test_swap_cover_then_rest_exhausted_operator(solver):
    before = deepcopy(solver.op_data.dorm)
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["引星棘刺"]}
    assert solver.tasks[1].type == TaskTypes.EXHAUST_OFF
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"
    assert [(b.name, b.time) for b in solver.op_data.dorm] == [
        (b.name, b.time) for b in before
    ]
    task = finish_support(solver)
    assert task.type == TaskTypes.SHIFT_OFF
    assert task.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in task.plan["dormitory_1"]
    assert solver.op_data.operators["苍苔"].is_resting()
    assert solver.op_data.operators["絮雨"].is_resting()
    solver.enter_room.assert_not_called()
    base_schedule.send_message.assert_not_called()


def test_exhaust_support_allows_zero_mood_cover_for_group_dorm_member(solver):
    data = solver.op_data
    data.add(Operator("黑角", ""))
    data.plan["dormitory_1"][1].group = "用尽"
    data.plan["dormitory_1"][1].replacement = ["黑角"]
    data.operators["闪灵"].group = "用尽"
    data.operators["闪灵"].replacement = ["黑角"]
    data.operators["机械师"].group = "用尽"
    data.groups["用尽"] = ["机械师", "闪灵"]

    blackhorn = data.operators["黑角"]
    blackhorn.mood = 0
    blackhorn.time_stamp = datetime.now()

    solver.task.meta_data = "机械师,闪灵"
    solver.overtake_room()

    assert solver.tasks[0].plan == {"room_2_2": ["引星棘刺"]}
    task = finish_support(solver)
    assert task.type == TaskTypes.SHIFT_OFF
    assert task.plan["room_3_3"] == ["槐琥"]
    assert task.plan["dormitory_1"][1] == "黑角"
    assert "机械师" in task.plan["dormitory_1"]


def test_no_other_cover_retains_request_without_reliable_recall_rates(solver):
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    # 心情更高的无关休息者不能抢先被叫回。
    solver.op_data = solver.op_data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current"] * 4 + ["能天使"]}]
    )
    solver.op_data.operators["能天使"].mood = 20
    run_retained(solver)
    assert solver.op_data.operators["苍苔"].is_resting()
    assert solver.op_data.operators["絮雨"].is_resting()
    assert solver.op_data.operators["能天使"].is_resting()


def test_cached_low_mood_alternate_is_deferred(solver):
    solver.op_data.operators["引星棘刺"].mood = 0
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["结城理"]}


def test_working_alternate_is_not_taken(solver):
    solver.op_data = solver.op_data.project_arrangements([{"meeting": ["引星棘刺"]}])
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["结城理"]}


def test_exhausted_full_rest_group_is_not_recalled(solver):
    data = solver.op_data
    data.operators["絮雨"].rest_in_full = True
    data.operators["苍苔"].replacement = ["槐琥"]
    data.rest_in_full_group.add("感知")
    data.exhaust_group.add("感知")
    before = deepcopy(data.dorm)
    original = run_retained(solver)
    assert solver.tasks == [original]
    assert [(b.name, b.time) for b in data.dorm] == [(b.name, b.time) for b in before]
    base_schedule.send_message.assert_not_called()


def test_full_rest_group_can_keep_resting_with_another_cover(solver):
    solver.op_data.rest_in_full_group.add("感知")
    solver.op_data.exhaust_group.add("感知")
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["引星棘刺"]}


def test_no_bed_does_not_commit_cover_swap(solver):
    data = solver.op_data
    solver.op_data = data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current"] * 4 + ["能天使"]}]
    )
    for name in ("苍苔", "絮雨", "能天使"):
        op = solver.op_data.operators[name]
        op.rest_in_full = op.exhaust_require = True
    original = run_retained(solver)
    assert solver.tasks == [original]
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"


def test_bed_shortage_is_checked_after_replacement_conflict(solver):
    solver.op_data = solver.op_data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current"] * 4 + ["能天使"]}]
    )
    solver.op_data.operators["能天使"].mood = 20
    run_retained(solver)
    assert solver.op_data.operators["能天使"].is_resting()
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"


def test_busy_alternates_and_group_member_block_recall(solver, monkeypatch):
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: name != "槐琥")
    original = run_retained(solver)
    assert solver.tasks == [original]


def test_pending_product_reservation_is_not_taken(solver):
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_2_2": ["槐琥"]}
    )
    task.product_shift_locked = True
    task.product_lock_names = {"槐琥"}
    solver.tasks.append(task)
    original = run_retained(solver)
    assert solver.tasks == [task, original]


def test_free_cover_uses_normal_shift_without_support(solver):
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["结城理"]}])
    solver.overtake_room()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SHIFT_OFF
    assert solver.tasks[0].plan["room_3_3"] == ["槐琥"]


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("mood", [0, 12])
def test_completed_exhaust_off_preserves_normal_planning(solver, grouped, mood):
    if grouped:
        solver.op_data.operators["机械师"].group = "用尽"
        solver.op_data.groups["用尽"] = ["机械师", "苍苔"]
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_3_3": ["槐琥"], "dormitory_1": ["Current"] * 4 + ["机械师"]}]
    )
    for op in solver.op_data.operators.values():
        op.mood, op.time_stamp = mood, datetime.now()
    solver.planned = solver.todo_task = solver.collect_notification = False
    solver.get_resting_plan = MagicMock(wraps=solver.get_resting_plan)
    solver._plan_exhaust_support = MagicMock(wraps=solver._plan_exhaust_support)
    before = deepcopy(solver.op_data.dorm)
    solver.overtake_room()
    assert solver.tasks == []
    assert not solver.planned
    assert not solver.todo_task
    assert not solver.collect_notification
    assert [(bed.name, bed.time) for bed in solver.op_data.dorm] == [
        (bed.name, bed.time) for bed in before
    ]
    solver.get_resting_plan.assert_not_called()
    solver._plan_exhaust_support.assert_not_called()
    solver.enter_room.assert_not_called()
    base_schedule.send_message.assert_not_called()


@pytest.mark.parametrize("primaries_zero_mood", [False, True])
@pytest.mark.parametrize("departed_dorm_member", [False, True])
def test_residual_exhaust_off_requeues_run_order_after_coordination(
    solver, monkeypatch, primaries_zero_mood, departed_dorm_member
):
    if primaries_zero_mood:
        for op in solver.op_data.operators.values():
            if op.is_high():
                op.mood, op.time_stamp = 0, datetime.now()
    solver.overtake_room()
    support, residual = solver.tasks
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    solver.tasks, solver.task = [], residual
    solver.overtake_room()
    solver.op_data = solver.op_data.project_arrangements([solver.tasks[0].plan])
    assert solver.op_data.operators["机械师"].is_resting()
    assert all(bed.name for bed in solver.op_data.dorm)
    if departed_dorm_member:
        worker = solver.op_data.operators["机械师"]
        resident = solver.op_data.operators["闪灵"]
        worker.group = resident.group = "用尽"
        solver.op_data.groups["用尽"] = [worker.name, resident.name]
        resident.current_room, resident.current_index = "", -1
    solver.op_data.plan["room_1_1"] = [Room("鸿雪", "", ["但书"])]
    solver.op_data.products["room_1_1"] = "lmd"
    solver.op_data.add(Operator("鸿雪", "room_1_1", index=0, replacement=["但书"]))
    solver.op_data.add(Operator("但书", ""))
    solver.op_data.operators["鸿雪"].current_room = "room_1_1"
    solver.op_data.operators["鸿雪"].current_index = 0
    solver.op_data.refresh_run_order_rooms()
    old_run_order = SchedulerTask(
        time=datetime.now() + timedelta(hours=2),
        task_plan={"room_1_1": ["但书"]},
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    solver.tasks, solver.task = [residual, old_run_order], residual
    solver.refresh_run_order_time("room_1_1")
    (refresh,) = [task for task in solver.tasks if task is not residual]
    assert refresh.type == TaskTypes.REFRESH_TIME
    assert refresh.meta_data == "room_1_1"
    assert old_run_order not in solver.tasks
    refresh_time = refresh.time
    solver.planned = solver.todo_task = solver.collect_notification = False
    solver.find = MagicMock(return_value=True)
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.plan_solver = MagicMock()
    solver.restart_after_mood_read = False
    execute_time = datetime.now() + timedelta(hours=1)
    solver.get_run_order_time = MagicMock(return_value=execute_time)
    monkeypatch.setattr(base_schedule, "scheduling", MagicMock(return_value=None))
    solver.infra_main()
    assert solver.task is None
    (replacement_check,) = [task for task in solver.tasks if task is not refresh]
    assert refresh in solver.tasks and refresh.time == refresh_time
    assert replacement_check.replacement_check == {
        "owner": "苍苔",
        "cover": "引星棘刺",
        "room": "room_2_2",
        "index": 0,
    }
    assert replacement_check.type == TaskTypes.NOT_SPECIFIC
    assert replacement_check.plan == {}
    assert not solver.planned
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[
            {
                "agent": "引星棘刺",
                "mood": 12,
                "time": datetime.now() + timedelta(hours=2),
            }
        ]
    )
    solver.op_data.operators["引星棘刺"].depletion_rate = 6
    sampled_at = solver.op_data.operators["引星棘刺"].time_stamp
    solver.task = replacement_check
    solver.infra_main()
    assert solver.task is None
    assert len(solver.tasks) == 2
    assert refresh in solver.tasks and replacement_check in solver.tasks
    assert replacement_check.time > execute_time
    solver.get_agent_from_room.assert_not_called()
    assert solver.op_data.operators["引星棘刺"].time_stamp == sampled_at
    assert not solver.planned
    solver.task = refresh
    solver.infra_main()
    assert refresh not in solver.tasks
    assert solver.task is None
    solver.infra_main()
    assert len(solver.tasks) == 2
    assert any(task is replacement_check for task in solver.tasks)
    (run_order,) = [task for task in solver.tasks if task is not replacement_check]
    assert run_order.type == TaskTypes.RUN_ORDER
    assert run_order.meta_data == "room_1_1"
    assert run_order.time == execute_time
    assert run_order.time != old_run_order.time
    assert run_order.plan == {"room_1_1": ["但书"]}
    solver.get_run_order_time.assert_called_once_with("room_1_1")
    solver.plan_solver.assert_called_once()
    solver.run_order_solver()
    assert len(solver.tasks) == 2
    assert any(task is replacement_check for task in solver.tasks)
    assert any(task is run_order for task in solver.tasks)
    solver.get_run_order_time.assert_called_once()
    solver.enter_room.assert_not_called()
    base_schedule.send_message.assert_not_called()


@pytest.mark.parametrize("member_room", ["", "meeting"])
def test_completed_exhaust_ignores_nonresting_workaholic(solver, member_room):
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_3_3": ["槐琥"], "dormitory_1": ["Current"] * 4 + ["机械师"]}]
    )
    worker = solver.op_data.operators["机械师"]
    member = solver.op_data.operators["能天使"]
    worker.group = member.group = "用尽"
    member.workaholic = True
    member.current_room = member_room
    solver.op_data.groups["用尽"] = [worker.name, member.name]
    solver.planned = solver.todo_task = solver.collect_notification = False
    solver.get_resting_plan = MagicMock(wraps=solver.get_resting_plan)
    solver._plan_exhaust_support = MagicMock(wraps=solver._plan_exhaust_support)

    solver.overtake_room()

    assert solver.tasks == []
    assert not solver.planned
    solver.get_resting_plan.assert_not_called()
    solver._plan_exhaust_support.assert_not_called()
    base_schedule.send_message.assert_not_called()


@pytest.mark.parametrize("member_room", ["", "meeting"])
def test_unfinished_group_member_still_requires_exhaust_planning(solver, member_room):
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_3_3": ["槐琥"], "dormitory_1": ["Current"] * 4 + ["机械师"]}]
    )
    worker = solver.op_data.operators["机械师"]
    member = solver.op_data.operators["能天使"]
    worker.group = member.group = "用尽"
    member.current_room = member_room
    solver.op_data.groups["用尽"] = [worker.name, member.name]
    solver.get_resting_plan = MagicMock()
    solver._plan_exhaust_support = MagicMock(return_value=None)
    solver.skip = MagicMock()

    run_retained(solver)

    solver.get_resting_plan.assert_called_once()
    solver._plan_exhaust_support.assert_called_once()
    solver.skip.assert_called_once()
    base_schedule.send_message.assert_not_called()


def test_exhaust_off_without_workable_replacements_preserves_occupancy(solver):
    data = solver.op_data
    data.operators["机械师"].replacement.append("红")
    data.add(Operator("红", ""))
    for op in data.operators.values():
        op.mood, op.time_stamp = 0, datetime.now()
    before = {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    }

    original = run_retained(solver)

    assert solver.tasks == [original]
    assert {
        name: (op.current_room, op.current_index) for name, op in data.operators.items()
    } == before
    base_schedule.send_message.assert_not_called()


def test_exhaust_coordinates_only_cover_even_at_zero_mood(solver):
    solver.op_data.operators["槐琥"].mood = 0

    solver.overtake_room()

    assert solver.tasks[0].plan == {"room_2_2": ["引星棘刺"]}
    task = finish_support(solver)
    assert task.type == TaskTypes.SHIFT_OFF
    assert task.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in task.plan["dormitory_1"]
    solver.enter_room.assert_not_called()


def test_alternate_does_not_take_another_exhausted_members_cover(solver):
    data = solver.op_data
    data.plan["room_1_1"] = [Room("阿罗玛", "用尽", ["引星棘刺"])]
    op = Operator(
        "阿罗玛",
        "room_1_1",
        index=0,
        group="用尽",
        replacement=["引星棘刺"],
        operator_type="high",
    )
    op.mood, op.time_stamp = 0, datetime.now()
    data.add(op)
    data.operators["机械师"].group = "用尽"
    data.groups["用尽"] = ["机械师", "阿罗玛"]
    solver.op_data = data.project_arrangements(
        [{"room_1_1": ["阿罗玛"], "dormitory_1": ["Current"] * 3 + ["Free", "Current"]}]
    )
    solver.op_data.operators["絮雨"].mood = 24
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["结城理"]}
    task = finish_support(solver)
    assert task.plan["room_1_1"] == ["引星棘刺"]
    assert task.plan["room_3_3"] == ["槐琥"]
    assert {"机械师", "阿罗玛"} <= set(task.plan["dormitory_1"])


def test_training_protection_prevents_partial_group_recall(solver):
    config.conf.enable_mastery = True
    solver._train_mastery_active = MagicMock(return_value=True)
    solver._train_protected = MagicMock(return_value=False)
    data = solver.op_data
    data.plan["train"] = [Room("逻各斯", "感知", ["赫默"])]
    op = Operator(
        "逻各斯",
        "train",
        index=0,
        group="感知",
        replacement=["赫默"],
        operator_type="high",
    )
    data.add(op)
    data.groups["感知"].append("逻各斯")
    data.operators["苍苔"].replacement = ["槐琥"]
    original = run_retained(solver)
    assert solver.tasks == [original]


def test_unknown_recall_keeps_temporary_dorm_slot_and_occupant(solver):
    solver.global_plan["default_plan"].plan["dormitory_1"][1] = Room(
        "爱丽丝", "感知", ["Free"]
    )
    assert solver.initialize_operators() is None
    solver.op_data.add(Operator("砾", ""))
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "room_3_3": ["机械师"],
                "room_2_2": ["槐琥"],
                "contact": ["斥罪"],
                "meeting": ["能天使"],
                "dormitory_1": ["冰酿", "砾", "苍苔", "絮雨", "Free"],
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.time_stamp, op.mood = datetime.now(), 5
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    run_retained(solver)
    assert solver.op_data.operators["苍苔"].is_resting()
    assert solver.op_data.operators["絮雨"].is_resting()
    assert solver.op_data.operators["砾"].is_resting()
    assert solver.op_data.operators["砾"].current_index == 1


def test_exhaust_simulation_clones_mutable_state_without_copying_eval_capsule(
    solver, monkeypatch
):
    """Regression for the PyCapsule deepcopy crash in exhausted-shift fallback."""
    make_capsule = ctypes.pythonapi.PyCapsule_New
    make_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    make_capsule.restype = ctypes.py_object
    source = solver.op_data
    # Real expression evaluators may contain extension-backed PyCapsules.
    source._test_unpicklable_capsule = make_capsule(ctypes.c_void_p(42), None, None)
    before_mood = source.operators["机械师"].mood
    before_bed = source.dorm[0].name

    def check_simulated_rest(instance, _names, _replacement, plan, _count):
        assert instance is not solver
        assert instance.op_data is not source
        assert instance.op_data.eval_model is source.eval_model
        assert (
            instance.op_data._test_unpicklable_capsule
            is source._test_unpicklable_capsule
        )
        assert instance.op_data.operators["机械师"] is not source.operators["机械师"]
        assert instance.op_data.dorm[0] is not source.dorm[0]
        instance.op_data.operators["机械师"].mood = 18
        instance.op_data.dorm[0].name = "机械师"
        plan.update(
            {
                "room_3_3": ["槐琥"],
                "room_2_2": ["引星棘刺"],
                "dormitory_1": ["Current"] * 4 + ["机械师"],
            }
        )

    monkeypatch.setattr(BaseSchedulerSolver, "get_resting_plan", check_simulated_rest)
    monkeypatch.setattr(
        "arknights_mower.utils.exhaust_replacement.plan_exhaust_support",
        lambda data, candidates, can_rest, _mastery, _protected, _fia, _slots, **_options: (
            can_rest(data)
        ),
    )
    assert solver._plan_exhaust_support(["机械师"]) is True
    assert source.operators["机械师"].mood == before_mood
    assert source.dorm[0].name == before_bed


def test_partially_resting_exhaust_group_retains_planning(solver):
    solver.op_data.operators["苍苔"].group = "用尽"
    solver.op_data.groups["用尽"] = ["苍苔", "机械师"]
    solver.task.meta_data = "苍苔"
    solver.get_resting_plan = MagicMock()
    solver._plan_exhaust_support = MagicMock(return_value=None)

    original = run_retained(solver)

    assert solver.tasks == [original]
    solver.get_resting_plan.assert_called_once_with(["苍苔", "机械师"], [], {}, 2)
    solver._plan_exhaust_support.assert_called_once_with(
        ["苍苔", "机械师"], urgent=True
    )
    assert solver.planned
    base_schedule.send_message.assert_not_called()


@pytest.fixture
def partially_resting_group(solver):
    solver.global_plan = {
        "default_plan": Plan(
            {
                "central": [
                    Room("薇薇安娜", "红松", ["斩业星熊"]),
                    Room("焰尾", "红松", ["诗怀雅"]),
                ],
                "room_1_2": [
                    Room("远牙", "红松", ["结城理"]),
                    Room("野鬃", "红松", ["苍苔"]),
                    Room("灰毫", "红松", ["引星棘刺"]),
                ],
                "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                + [Room("Free", "", []) for _ in range(3)],
                "dormitory_2": [Room("流明", "", []), Room("波登可", "", [])]
                + [Room("Free", "", []) for _ in range(3)],
            },
            PlanConfig("", "薇薇安娜", ""),
        ),
        "backup_plans": [],
    }
    assert solver.initialize_operators() is None
    for name in ("食铁兽", "酒神", "红豆"):
        solver.op_data.add(Operator(name, ""))
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "central": ["薇薇安娜", "焰尾"],
                "room_1_2": ["食铁兽", "酒神", "红豆"],
                "dormitory_1": ["冰酿", "闪灵", "野鬃", "诗怀雅", "斩业星熊"],
                "dormitory_2": ["流明", "波登可", "灰毫", "远牙", "Free"],
            }
        ]
    )
    for op in solver.op_data.operators.values():
        op.time_stamp, op.mood = datetime.now(), 24
    for name, mood in (
        ("薇薇安娜", 1.2),
        ("焰尾", 1.7),
        ("野鬃", 20.4),
        ("灰毫", 20.8),
        ("远牙", 23),
    ):
        solver.op_data.operators[name].mood = mood
    for bed in solver.op_data.dorm:
        if bed.name:
            bed.time = datetime.now() + timedelta(hours=2)
    solver.task = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="薇薇安娜")
    return solver


@pytest.mark.parametrize("dispatch", [False, True])
@pytest.mark.parametrize("resting_cover", [False, True])
def test_partially_resting_group_completes_remaining_departures(
    partially_resting_group, dispatch, resting_cover
):
    solver = partially_resting_group
    if resting_cover:
        solver.op_data.operators["薇薇安娜"].replacement.insert(0, "野鬃")
    residents = {"野鬃", "灰毫", "远牙"}
    before = {
        bed.name: (bed.position, bed.time)
        for bed in solver.op_data.dorm
        if bed.name in residents
    }
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    if dispatch:
        solver.overtake_room()
        (task,) = solver.tasks
        assert task.type == TaskTypes.SHIFT_OFF
        plan = task.plan
        admissions = {
            (room, index): name
            for room, row in plan.items()
            if room.startswith("dorm")
            for index, name in enumerate(row)
        }
    else:
        plan, admissions = {}, {}
        assert solver.get_resting_plan(
            list(solver.op_data.groups["红松"]),
            [],
            plan,
            solver.op_data.active_high_resting_count(),
            dorm_admissions=admissions,
        )
        assert before == {
            bed.name: (bed.position, bed.time)
            for bed in solver.op_data.dorm
            if bed.name in residents
        }
    assert plan["central"] == ["斩业星熊", "诗怀雅"]
    assert "room_1_2" not in plan
    assert {"薇薇安娜", "焰尾"} <= set(admissions.values())
    projected = solver.op_data.project_arrangements([plan])
    assert all(projected.operators[name].is_resting() for name in residents)
    assert positions == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("shortage", ["replacement", "bed", "reservation"])
def test_partially_resting_group_preserves_state_when_admission_fails(
    partially_resting_group, shortage
):
    solver = partially_resting_group
    if shortage == "replacement":
        solver.op_data.operators["焰尾"].replacement = []
    elif shortage == "bed":
        vacant = {
            "dormitory_1": ["Current"] * 3 + ["Free", "Free"],
            "dormitory_2": ["Current"] * 4 + ["Free"],
        }
        solver.op_data = solver.op_data.project_arrangements([vacant])
        pending = SchedulerTask(task_plan=vacant, task_type=TaskTypes.SELF_CORRECTION)
        pending.execution_retained = True
        solver.tasks.append(pending)
    else:
        pending = SchedulerTask(
            task_plan={"room_1_2": ["Current", "野鬃", "Current"]},
            task_type=TaskTypes.SHIFT_ON,
        )
        pending.execution_retained = True
        solver.tasks.append(pending)
    before = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    plan, replacements, admissions = {}, [], {}
    solver.get_resting_plan(
        list(solver.op_data.groups["红松"]),
        replacements,
        plan,
        solver.op_data.active_high_resting_count(),
        dorm_admissions=admissions,
    )
    assert plan == {}
    assert replacements == []
    assert admissions == {}
    assert before == [(bed.name, bed.time) for bed in solver.op_data.dorm]


@pytest.mark.parametrize("returned_in_same_room", [False, True])
def test_partially_working_group_completes_remaining_returns(
    partially_resting_group, returned_in_same_room
):
    solver = partially_resting_group
    if returned_in_same_room:
        solver.op_data = solver.op_data.project_arrangements(
            [{"room_1_2": ["远牙", "Current", "Current"]}]
        )
    solver.op_data.commit_group_shifts({"红松": True})
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    beds = [bed for bed in solver.op_data.dorm if bed.name in {"远牙", "野鬃", "灰毫"}]
    (task,) = generate_plan_by_drom({datetime.now(): (beds, True)}, solver.op_data)
    assert task.type == TaskTypes.SHIFT_ON
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["room_1_2"] == ["远牙", "野鬃", "灰毫"]
    assert positions == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    assert solver.op_data.group_is_resting("红松")
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    solver.op_data.commit_group_shifts({"红松": True})
    assert solver._complete_group_shift(task)
    assert not solver.op_data.group_is_resting("红松")
    assert all(
        (op.current_room, op.current_index) == (op.room, op.index)
        for name in solver.op_data.groups["红松"]
        for op in [solver.op_data.operators[name]]
    )
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("coordinatable", [False, True])
def test_rescue_projection_checks_occupied_cover_coordination(solver, coordinatable):
    from arknights_mower.utils.emergency_recovery import native_opportunity

    data = solver.op_data
    if not coordinatable:
        data.operators["苍苔"].rest_in_full = True
        data.operators["苍苔"].exhaust_require = True
        for name in ("引星棘刺", "结城理"):
            data.operators[name].mood = 0
    before = {
        name: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for name, op in data.operators.items()
    }
    now = datetime.now()
    result = native_opportunity(solver, ["机械师"], now, current_only=True)

    assert result.complete
    assert (result.opportunity == now) is coordinatable
    assert before == {
        name: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for name, op in data.operators.items()
    }
    assert solver.tasks == []
    solver.enter_room.assert_not_called()
    base_schedule.send_message.assert_not_called()


@pytest.mark.parametrize("recall", [False, True])
@pytest.mark.parametrize("restored", [False, True])
def test_exhaust_support_dispatch_preserves_recovery_capacity(solver, recall, restored):
    import jsonpickle

    if recall:
        solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    solver.overtake_room()
    if restored:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
    support, retry = solver.tasks
    expected = (
        {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
        if recall
        else {"room_2_2": ["引星棘刺"]}
    )
    assert support.plan == expected
    original_time = support.time
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    beds = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    solver.task = support
    solver._prepare_group_shift(support)
    solver._prepare_shift_cycle(support)
    solver._prepare_group_shift(support, remember_targets=True)
    assert support.plan == expected
    assert support.time == original_time
    assert positions == {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }
    assert beds == [(bed.name, bed.time) for bed in solver.op_data.dorm]
    # 仅在前置接岗已确认后重算用尽下班，不允许普通轮休抢占最后一床。
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    assert solver._complete_group_shift(support)
    solver.tasks, solver.task = [], retry
    solver.overtake_room()
    (off,) = solver.tasks
    assert off.type == TaskTypes.SHIFT_OFF
    assert off.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in off.plan["dormitory_1"]
    assert "能天使" not in off.plan.get("dormitory_1", [])
    base_schedule.send_message.assert_not_called()


def test_backup_coalescing_preserves_exhaust_support_task(solver):
    solver.overtake_room()
    support, retry = solver.tasks
    original_plan, original_time = deepcopy(support.plan), support.time
    _, consumed = solver._coalesce_backup_transition({"room_2_2": ["结城理"]})
    assert not any(task is support for task in consumed)
    assert support.plan == original_plan
    assert support.time == original_time
    assert solver.tasks == [support, retry]


def test_ordinary_cycle_does_not_consume_exhaust_support(solver):
    solver.overtake_room()
    support, retry = solver.tasks
    ordinary = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan={})
    solver.tasks.append(ordinary)
    solver.task = ordinary
    solver._prepare_shift_cycle(ordinary)
    assert any(task is support for task in solver.tasks)
    assert any(task is retry for task in solver.tasks)


def test_exhaust_support_still_prepares_explicit_backup_entry(solver):
    from arknights_mower.utils.logic_expression import LogicExpression

    data = solver.op_data
    data.backup_plans = [
        Plan(
            {},
            PlanConfig("", "", ""),
            trigger=LogicExpression(
                "op_data.operators['槐琥'].current_room", "!=", "'room_2_2'"
            ),
            task={"meeting": ["陈"]},
        )
    ]
    data.global_plan["backup_plans"] = data.backup_plans
    data.plan_condition = [False]
    solver.overtake_room()
    support, _ = solver.tasks
    solver.task = support
    solver._prepare_group_shift(support)
    solver._prepare_shift_cycle(support)
    assert support.backup_shift_conditions == [True]
    assert support.plan["room_2_2"] == ["引星棘刺"]
    assert support.plan["meeting"] == ["陈"]
    assert data.plan_condition == [False]
    assert data.operators["槐琥"].current_room == "room_2_2"
