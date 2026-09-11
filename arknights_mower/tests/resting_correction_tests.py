"""Correction prefers replacements and recalls operators when none are available."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.operators import Dormitory, Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Room  # noqa: E402
from arknights_mower.utils.resting_correction import (  # noqa: E402
    prefer_resting_replacements,
)


@pytest.fixture
def solver():
    data = object.__new__(Operators)
    data.plan = {
        "central": [Room("歌蕾蒂娅", "深海", ["薇薇安娜"])],
        "room_2_2": [Room("引星棘刺", "自动化", ["淬羽赫默"])],
        "room_3_2": [Room("清流", "", ["砾"]), Room("温蒂", "自动化", ["多萝西"])],
        "room_3_3": [
            Room("斯卡蒂", "深海", ["多萝西"]),
            Room("幽灵鲨", "深海", ["淬羽赫默"]),
        ],
        "dormitory_1": [Room("Free", "", [])],
        "train": [Room("逻各斯", "", ["赫默"])],
    }
    data.groups = {
        "深海": ["歌蕾蒂娅", "斯卡蒂", "幽灵鲨"],
        "自动化": ["引星棘刺", "温蒂"],
    }
    data.operators = {}
    for room, slots in data.plan.items():
        for index, slot in enumerate(slots):
            if slot.agent == "Free":
                continue
            data.operators[slot.agent] = Operator(
                slot.agent,
                room,
                index=index,
                group=slot.group,
                replacement=slot.replacement,
                operator_type="high",
                time_stamp=datetime.now(),
            )
    for name in ("薇薇安娜", "淬羽赫默", "多萝西", "归溟幽灵鲨", "砾", "赫默"):
        data.operators[name] = Operator(name, "", time_stamp=datetime.now())
    actual = {
        "central": ["薇薇安娜"],
        "room_3_3": ["引星棘刺", "温蒂"],
        "room_3_2": ["多萝西", "淬羽赫默"],
        "dormitory_1": ["歌蕾蒂娅"],
        "train": ["归溟幽灵鲨"],
    }
    for room, names in actual.items():
        for index, name in enumerate(names):
            data.operators[name].current_room = room
            data.operators[name].current_index = index
    data.operators["歌蕾蒂娅"].mood = 0
    data.dorm = [
        Dormitory(("dormitory_1", 0), "歌蕾蒂娅", datetime.now() + timedelta(hours=7))
    ]
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data, instance.tasks = data, []
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    instance._suppress_train_correction = lambda plan: plan.pop("train", None)
    return instance


def apply_plan(solver, plan):
    """Apply confirmed placements to the cache without operating a device."""
    for room, names in plan.items():
        for index, name in enumerate(names):
            if name in ("Current", "Free"):
                continue
            for op in solver.op_data.operators.values():
                if op.current_room == room and op.current_index == index:
                    op.current_room, op.current_index = "", -1
            op = solver.op_data.operators[name]
            op.current_room, op.current_index = room, index


def test_backup_room_change_converges_using_replacements(solver, monkeypatch):
    monkeypatch.setattr(
        "arknights_mower.solvers.base_schedule._is_mastery_busy", lambda name: False
    )
    assert solver.agent_get_mood() == "self_correction"
    plan = solver.tasks.pop().plan
    assert plan["room_3_3"] == ["多萝西", "淬羽赫默"]
    assert plan["room_3_2"] == ["清流", "温蒂"]
    assert plan["room_2_2"] == ["引星棘刺"]
    assert "central" not in plan
    apply_plan(solver, plan)
    for _ in range(3):
        assert solver.agent_get_mood() is None
        assert solver.tasks == []
    assert solver.op_data.operators["歌蕾蒂娅"].current_room == "dormitory_1"
    solver.enter_room.assert_not_called()


def test_partial_group_at_work_does_not_wake_resting_member(solver):
    apply_plan(
        solver,
        {
            "room_2_2": ["引星棘刺"],
            "room_3_2": ["清流", "温蒂"],
            "room_3_3": ["斯卡蒂", "幽灵鲨"],
        },
    )
    # The protected training room still seeds the legacy group-synchronization pass.
    assert solver.agent_get_mood() is None
    assert solver.tasks == []
    assert solver.op_data.operators["歌蕾蒂娅"].mood == 0
    assert solver.op_data.operators["歌蕾蒂娅"].is_resting()


@pytest.mark.parametrize("configured_slots", [0, 1])
@pytest.mark.parametrize("trainee_present", [False, True])
def test_correction_leaves_unconfigured_training_slot_alone(
    solver, configured_slots, trainee_present
):
    solver.op_data.plan["train"] = solver.op_data.plan["train"][:configured_slots]
    if not configured_slots:
        del solver.op_data.operators["逻各斯"]
    if trainee_present:
        trainee = Operator("号角", "", time_stamp=datetime.now())
        trainee.current_room, trainee.current_index = "train", 1
        solver.op_data.operators[trainee.name] = trainee
    # 不依赖专精保护抑制纠错，也不得为用户未配置的训练位生成安排。
    solver._suppress_train_correction = lambda plan: None
    solver.agent_get_mood()
    for task in solver.tasks:
        if configured_slots:
            assert task.plan.get("train", ["逻各斯"]) == ["逻各斯"]
        else:
            assert "train" not in task.plan
    if trainee_present:
        assert solver.op_data.operators["号角"].current_room == "train"


def test_completed_rest_allows_normal_group_return(solver):
    solver.op_data.dorm[0].time = datetime.now() - timedelta(seconds=1)
    solver.op_data.operators["歌蕾蒂娅"].mood = 24
    solver.agent_get_mood()
    first = solver.tasks.pop().plan
    apply_plan(solver, first)
    if "central" not in first:
        solver.agent_get_mood()
        first = solver.tasks.pop().plan
    assert first["central"] == ["歌蕾蒂娅"]


def test_replacements_in_other_working_rooms_are_not_taken(solver):
    plan = {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    busy = MagicMock(return_value=False)
    prefer_resting_replacements(solver.op_data, plan, busy)
    assert plan == {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    busy.assert_not_called()


def test_shared_replacement_is_assigned_only_once(solver):
    data = solver.op_data
    data.operators["多萝西"].current_room = ""
    data.operators["幽灵鲨"].replacement = ["多萝西"]
    plan = {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    busy = MagicMock(return_value=False)
    prefer_resting_replacements(data, plan, busy)
    assert plan == {"room_3_3": ["多萝西", "幽灵鲨"]}
    busy.assert_called_once_with("多萝西")


def test_mastery_busy_replacement_is_not_used_and_checked_once(solver):
    data = solver.op_data
    data.operators["多萝西"].current_room = ""
    data.operators["幽灵鲨"].replacement = ["多萝西"]
    plan = {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    busy = MagicMock(return_value=True)
    prefer_resting_replacements(data, plan, busy)
    assert plan == {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    busy.assert_called_once_with("多萝西")


def test_replacement_reserved_by_another_correction_is_not_reused(solver):
    data = solver.op_data
    data.operators["多萝西"].current_room = ""
    plan = {"room_3_2": ["Current", "多萝西"], "room_3_3": ["斯卡蒂", "幽灵鲨"]}
    prefer_resting_replacements(data, plan, MagicMock(return_value=False))
    assert plan == {
        "room_3_2": ["Current", "多萝西"],
        "room_3_3": ["斯卡蒂", "淬羽赫默"],
    }


def test_correctly_placed_replacement_is_not_stolen_for_another_slot(solver):
    data = solver.op_data
    apply_plan(solver, {"room_3_3": ["多萝西", "Current"]})
    data.operators["幽灵鲨"].replacement = ["多萝西"]
    plan = {"room_3_3": ["Current", "幽灵鲨"]}
    prefer_resting_replacements(data, plan, MagicMock(return_value=False))
    assert plan == {"room_3_3": ["Current", "幽灵鲨"]}


@pytest.mark.parametrize("end", [None, "future"])
def test_individual_rest_is_also_protected(solver, end):
    data = solver.op_data
    data.operators["歌蕾蒂娅"].group = ""
    data.dorm[0].time = None if end is None else datetime.now() + timedelta(hours=1)
    # A missing bed deadline still has valid cached mood and an actual dorm slot.
    plan = {"central": ["歌蕾蒂娅"]}
    prefer_resting_replacements(data, plan, MagicMock(return_value=False))
    assert plan == {}


def test_zero_mood_workaholic_does_not_block_group_correction(solver):
    data = solver.op_data
    data.operators["歌蕾蒂娅"].workaholic = True
    plan = {"room_3_3": ["斯卡蒂", "幽灵鲨"]}
    prefer_resting_replacements(data, plan, MagicMock(return_value=False))
    assert plan == {"room_3_3": ["斯卡蒂", "幽灵鲨"]}


def test_temporary_trade_operator_is_replaced_by_regular_cover(solver):
    data = solver.op_data
    data.operators["但书"] = Operator("但书", "", time_stamp=datetime.now())
    data.operators["斯卡蒂"].replacement = ["但书", "多萝西"]
    data.operators["多萝西"].current_room = ""
    apply_plan(solver, {"room_3_3": ["但书", "Current"]})
    plan = {"room_3_3": ["斯卡蒂", "Current"]}
    prefer_resting_replacements(data, plan, MagicMock(return_value=False))
    assert plan == {"room_3_3": ["多萝西", "Current"]}


def test_no_available_replacement_allows_group_correction_to_recall(solver):
    apply_plan(
        solver,
        {
            "room_2_2": ["引星棘刺"],
            "room_3_2": ["清流", "温蒂"],
            "room_3_3": ["斯卡蒂", "幽灵鲨"],
        },
    )
    # The only cover is working elsewhere and this correction does not free her.
    solver.op_data.operators["薇薇安娜"].current_room = "contact"
    assert solver.agent_get_mood() == "self_correction"
    plan = solver.tasks.pop().plan
    assert plan == {"central": ["歌蕾蒂娅"]}
    assert solver.op_data.operators["歌蕾蒂娅"].mood == 0
    apply_plan(solver, plan)
    assert solver.agent_get_mood(skip_dorm=True) is None
    assert solver.tasks == []
    solver.enter_room.assert_not_called()


def test_correction_outside_planned_slot_is_not_silently_removed(solver):
    apply_plan(solver, {"room_3_2": ["清流", "温蒂"]})
    plan = {"room_3_2": ["斯卡蒂", "Current"]}
    prefer_resting_replacements(solver.op_data, plan, MagicMock(return_value=False))
    assert plan == {"room_3_2": ["斯卡蒂", "Current"]}
