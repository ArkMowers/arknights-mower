"""用尽任务协调被占用的替班，不拆休息组、不提前改变实际床位。"""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture(params=[False, True])
def solver(request, monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    config.conf.enable_mastery = False
    config.conf.experimental_dorm_logic = request.param
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
            PlanConfig("机械师", "机械师", "", experimental_dorm_logic=request.param),
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


def finish_support(solver):
    """前置换班已读屏确认后的状态，再执行动态用尽规划。"""
    support, retry = solver.tasks
    solver.op_data = solver.op_data.project_arrangements([support.plan])
    solver.tasks, solver.task = [], retry
    solver.overtake_room()
    return solver.tasks[0]


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


def test_no_other_cover_recalls_only_owning_group(solver):
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    # 心情更高的无关休息者不能抢先被叫回。
    solver.op_data = solver.op_data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current"] * 4 + ["能天使"]}]
    )
    solver.op_data.operators["能天使"].mood = 20
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    task = finish_support(solver)
    assert task.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in task.plan["dormitory_1"]
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
    data.operators["苍苔"].replacement = ["槐琥"]
    data.rest_in_full_group.add("感知")
    data.exhaust_group.add("感知")
    before = deepcopy(data.dorm)
    solver.overtake_room()
    assert solver.tasks == []
    assert [(b.name, b.time) for b in data.dorm] == [(b.name, b.time) for b in before]
    base_schedule.send_message.assert_called_once()


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
    solver.overtake_room()
    assert solver.tasks == []
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"


def test_bed_shortage_is_checked_after_replacement_conflict(solver):
    solver.op_data = solver.op_data.project_arrangements(
        [{"meeting": ["陈"], "dormitory_1": ["Current"] * 4 + ["能天使"]}]
    )
    solver.op_data.operators["能天使"].mood = 20
    solver.overtake_room()
    assert solver.tasks[0].plan == {"room_2_2": ["引星棘刺"], "meeting": ["能天使"]}
    task = finish_support(solver)
    assert task.plan["room_3_3"] == ["槐琥"]
    assert "机械师" in task.plan["dormitory_1"]


def test_busy_alternates_and_group_member_block_recall(solver, monkeypatch):
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: name != "槐琥")
    solver.overtake_room()
    assert solver.tasks == []


def test_pending_product_reservation_is_not_taken(solver):
    if not solver.op_data.experimental_dorm_logic:
        pytest.skip("延期产物换班只在实验模式启用")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"room_2_2": ["槐琥"]}
    )
    task.product_shift_locked = True
    task.product_lock_names = {"槐琥"}
    solver.tasks.append(task)
    solver.overtake_room()
    assert solver.tasks == [task]


def test_free_cover_uses_normal_shift_without_support(solver):
    solver.op_data = solver.op_data.project_arrangements([{"room_2_2": ["结城理"]}])
    solver.overtake_room()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SHIFT_OFF
    assert solver.tasks[0].plan["room_3_3"] == ["槐琥"]


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
    solver.overtake_room()
    assert solver.tasks == []


def test_group_recall_restores_temporary_dorm_slot_and_keeps_occupant(solver):
    if not solver.op_data.experimental_dorm_logic:
        pytest.skip("临时宿舍床位只在实验模式启用")
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
    solver.overtake_room()
    support = solver.tasks[0].plan
    assert support["room_2_2"] == ["苍苔"]
    assert support["contact"] == ["絮雨"]
    assert support["dormitory_1"][1] == "爱丽丝"
    finish_support(solver)
    assert solver.op_data.operators["砾"].is_resting()
