"""可靠空闲且没有固定排班的训练室驻员可直接接替工作岗位。"""

import copy
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.tests.group_replacement_matching_tests import MEMBERS
from arknights_mower.tests.group_replacement_matching_tests import (
    solver as group_solver,
)
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch, bundled_mastery_skills):
    instance = group_solver.__wrapped__(monkeypatch)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(side_effect=AssertionError("device access"))
    data = instance.op_data
    for name, index in (("逻各斯", 0), ("赫默", 1)):
        data.operators[name] = Operator(
            name,
            "",
            current_room="train",
            current_index=index,
            mood=24,
            time_stamp=datetime.now(),
        )
    data.operators[MEMBERS[0]].replacement = ["逻各斯"]
    data.operators[MEMBERS[1]].replacement = ["赫默"]
    instance.train_room_state = reader.RoomState(
        "empty",
        support_slot="逻各斯",
        train_slot="赫默",
        slots_read=True,
        slots_reliable=True,
    )
    return instance


def request_group_rest(solver):
    plan, replacements = {}, []
    solver.get_resting_plan(MEMBERS.copy(), replacements, plan, 0)
    return plan, replacements


@pytest.mark.parametrize("train_plan", [None, []])
@pytest.mark.parametrize("tiers", [[0, 0, 3], [3, 3, 3]])
@pytest.mark.parametrize("projected", [False, True])
def test_group_rest_uses_both_idle_training_occupants_after_deep_release(
    solver, monkeypatch, train_plan, tiers, projected
):
    if train_plan is not None:
        solver.op_data.plan["train"] = train_plan
    solver.train_scene = MagicMock(return_value=Scene.TRAIN_SKILL_SELECT)
    monkeypatch.setattr(reader, "_read_slot_mastery_tier", MagicMock(side_effect=tiers))
    monkeypatch.setattr(reader, "_back_to_train_main", MagicMock())
    solver.train_room_state.protected = reader._compute_protected(
        solver, solver.train_room_state
    )
    if projected:
        solver = copy.copy(solver)
        solver.op_data = solver.op_data.project_arrangements([])
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    plan, replacements = request_group_rest(solver)

    assert plan["central"] == ["逻各斯"]
    assert plan["contact"] == ["赫默"]
    assert len(replacements) == len(set(replacements)) == len(MEMBERS)
    assert set(MEMBERS) <= {bed.name for bed in solver.op_data.dorm}
    assert "train" not in plan
    assert {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    } == positions
    solver.enter_room.assert_not_called()


def test_idle_room_without_halving_support_uses_actual_occupants(solver):
    data = solver.op_data
    support = data.operators.pop("逻各斯")
    support.name = "红"
    data.operators["红"] = support
    data.operators[MEMBERS[0]].replacement = ["红"]
    solver.train_room_state.support_slot = "红"

    plan, replacements = request_group_rest(solver)

    assert plan["central"] == ["红"]
    assert plan["contact"] == ["赫默"]
    assert len(replacements) == len(set(replacements)) == len(MEMBERS)
    assert set(MEMBERS) <= {bed.name for bed in data.dorm}
    assert support.current_room == "train"
    assert data.operators["赫默"].current_room == "train"
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "blocker",
    [
        "training",
        "waiting_collect",
        "read_failed",
        "unread_slots",
        "unreliable_slots",
        "no_observation",
        "partial_mastery",
        "unknown_mastery",
        "trainee_mismatch",
        "support_mismatch",
        "active_plan",
        "skill_task",
        "swap_task",
        "fixed_support",
        "fixed_trainee",
        "factory",
        "invalid_index",
        "mastery_disabled",
    ],
)
def test_group_rest_keeps_training_and_fixed_staff_protection(
    solver, monkeypatch, blocker
):
    state = solver.train_room_state
    if blocker in ("training", "waiting_collect"):
        state.state = blocker
    elif blocker in ("read_failed", "unread_slots", "unreliable_slots"):
        setattr(
            state,
            {"unread_slots": "slots_read", "unreliable_slots": "slots_reliable"}.get(
                blocker, blocker
            ),
            blocker == "read_failed",
        )
    elif blocker == "no_observation":
        solver.train_room_state = None
    elif blocker in ("partial_mastery", "unknown_mastery"):
        solver.train_scene = MagicMock(return_value=Scene.TRAIN_SKILL_SELECT)
        monkeypatch.setattr(
            reader,
            "_read_slot_mastery_tier",
            lambda *_: 1 if blocker == "partial_mastery" else None,
        )
        monkeypatch.setattr(reader, "_back_to_train_main", MagicMock())
        state.protected = reader._compute_protected(solver, state)
    elif blocker in ("trainee_mismatch", "support_mismatch"):
        setattr(
            state,
            "train_slot" if blocker == "trainee_mismatch" else "support_slot",
            "其他干员",
        )
    elif blocker == "active_plan":
        monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"id": 1})
    elif blocker in ("skill_task", "swap_task"):
        task = SchedulerTask(
            task_type=TaskTypes.SKILL_UPGRADE
            if blocker == "skill_task"
            else TaskTypes.SWAP_SUPPORT
        )
        solver.tasks.append(task)
        solver.find_next_task.side_effect = lambda **kw: (
            task if task.type == kw.get("task_type") else None
        )
    elif blocker in ("fixed_support", "fixed_trainee"):
        solver.op_data.plan["train"] = [
            Room("逻各斯" if blocker == "fixed_support" else "赫默", "", [])
        ]
    elif blocker == "factory":
        solver.op_data.operators["赫默"]._current_room = "factory"
    elif blocker == "invalid_index":
        solver.op_data.operators["赫默"].current_index = 2
    else:
        monkeypatch.setattr(config.conf, "enable_mastery", False)
    before_beds = [(bed.name, bed.time) for bed in solver.op_data.dorm]

    plan, replacements = request_group_rest(solver)

    assert plan == {}
    assert replacements == []
    assert [(bed.name, bed.time) for bed in solver.op_data.dorm] == before_beds
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("slot", ["support_slot", "train_slot"])
def test_old_idle_observation_does_not_release_training_arrangement(solver, slot):
    setattr(solver.train_room_state, slot, "其他干员")
    plan = {"central": ["赫默"]}

    solver._suppress_train_arrangement(plan)

    assert plan == {}
    assert solver.op_data.operators["赫默"].current_room == "train"
