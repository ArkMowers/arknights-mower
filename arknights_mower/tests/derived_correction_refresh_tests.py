"""未执行的普通纠错只在相关观测变化后重算派生安排。"""

import copy
import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.solvers.base_schedule import GroupShiftBlocked
from arknights_mower.tests import multi_group_shift_tests as shared
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    solver = shared.solver.__wrapped__(monkeypatch)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    solver.op_data.first_init = False
    solver.task = None
    solver._refresh_deferred_product_reservations = MagicMock()
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "meeting": ["陈", "银灰"],
                "contact": ["黑角"],
                "dormitory_1": ["塑心", "冰酿", "伊内丝", "讯使", "Current"],
            }
        ]
    )
    solver.op_data.commit_group_shifts({"甲": True, "乙": False})
    assert solver.agent_get_mood(read_rooms=False) == "self_correction"
    assert len(solver.tasks) == 1
    return solver


def change_binding(solver, *, wrong_cover=False):
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "meeting": ["伊内丝", "初雪"],
                "contact": ["红" if wrong_cover else "黑角"],
                "dormitory_1": ["塑心", "冰酿", "银灰", "讯使", "Current"],
            }
        ]
    )
    solver.op_data.commit_group_shifts({"甲": False, "乙": True})


def retain(solver):
    task = solver.tasks[0]
    solver._retain_failed_task(task, "共享替班冲突", list(task.plan))
    return task


def test_generated_correction_marks_origin_and_refreshes_after_binding_observation(
    solver,
):
    task = retain(solver)
    assert task.derived_correction
    original_time = task.time
    independent = SchedulerTask(
        time=datetime.now() + timedelta(minutes=5), task_type=TaskTypes.SKILL_UPGRADE
    )
    solver.tasks.append(independent)
    assert find_next_task(solver.tasks) is independent
    before = copy.deepcopy(task.plan)
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task.plan == before
        assert hasattr(task, "execution_failure")
    change_binding(solver)
    solver._resume_failed_tasks()
    assert solver.tasks[0] is task
    assert solver.tasks[1] is independent
    assert task.time is original_time
    assert task.plan == {}
    assert not task.retains_execution
    solver.task = task
    solver._prepare_group_shift(task)
    assert task.plan == {}
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize("freshness", ["fresh", "stale", "unknown"])
def test_refresh_keeps_current_wrong_slot_and_same_post_observation_requests(
    solver, freshness
):
    task = retain(solver)
    original_time = task.time
    change_binding(solver, wrong_cover=True)
    worker = solver.op_data.operators["伊内丝"]
    worker.mood = 20
    if freshness == "stale":
        worker.time_stamp = datetime.now() - timedelta(hours=3)
    elif freshness == "unknown":
        worker.time_stamp = None
    solver._resume_failed_tasks()
    assert task.time is original_time
    assert task.plan["contact"] == ["黑角"]
    if freshness != "fresh":
        assert task.plan["meeting"][0] == "伊内丝"
    solver.enter_room.assert_not_called()


@pytest.mark.parametrize(
    "protection",
    [
        "unmarked",
        "started",
        "explicit",
        "backup",
        "intent",
        "conditions",
        "products",
        "support",
        "confirmation",
        "retry",
        "metadata",
    ],
)
def test_refresh_never_rewrites_unowned_or_started_requests(solver, protection):
    task = solver.tasks[0]
    if protection == "unmarked":
        task.derived_correction = False
    elif protection == "started":
        task.derived_correction_started = True
    elif protection == "explicit":
        task.backup_explicit_slots = {("contact", 0)}
    elif protection == "backup":
        task.backup_shift_active = True
    elif protection == "intent":
        task.backup_shift_intent = copy.deepcopy(task.plan)
    elif protection == "conditions":
        task.backup_shift_conditions = [True]
    elif protection == "products":
        task.product_shift_locked = True
    elif protection == "support":
        task.exhaust_support = True
    elif protection == "confirmation":
        task.group_shift_expected = {("contact", 0): "红"}
    elif protection == "retry":
        task.arrangement_retry_room = "contact"
    else:
        task.meta_data = "明确安排"
    retain(solver)
    before, original_time = copy.deepcopy(task.plan), task.time
    change_binding(solver)
    solver._resume_failed_tasks()
    assert task.plan == before
    assert task.time is original_time
    assert task.retains_execution


def test_unrelated_operator_observation_does_not_rearm_correction(solver):
    task = retain(solver)
    original = task.execution_failure
    solver.op_data.operators["银灰"].time_stamp += timedelta(seconds=1)
    with patch.object(
        solver, "_refresh_derived_correction", wraps=solver._refresh_derived_correction
    ) as refresh:
        solver._resume_failed_tasks()
        refresh.assert_not_called()
    assert task.execution_failure is original


def test_confirmed_binding_change_alone_rearms_derived_correction(solver):
    task = retain(solver)
    original_time = task.time
    before = {
        name: (op.current_room, op.current_index, op.time_stamp)
        for name, op in solver.op_data.operators.items()
    }
    solver.op_data.commit_group_shifts({"甲": False, "乙": True})
    assert before == {
        name: (op.current_room, op.current_index, op.time_stamp)
        for name, op in solver.op_data.operators.items()
    }
    with patch.object(
        solver, "_refresh_derived_correction", wraps=solver._refresh_derived_correction
    ) as refresh:
        solver._resume_failed_tasks()
        refresh.assert_called_once_with(task)
    assert not task.retains_execution
    assert task.time is original_time
    assert task.plan.get("contact", ["Current"]) != ["红"]


def test_actual_arrangement_boundary_marks_started_before_failure(solver):
    task = solver.tasks[0]
    before = copy.deepcopy(task.plan)
    solver.task = task
    solver.agent_arrange = MagicMock(side_effect=RuntimeError("readback interrupted"))
    with pytest.raises(RuntimeError, match="readback interrupted"):
        solver._arrange_with_shift_refresh_rules(task, False)
    assert task.derived_correction_started
    retain(solver)
    change_binding(solver)
    solver._resume_failed_tasks()
    assert task.plan == before
    assert task.retains_execution


def test_pending_derived_origin_survives_snapshot_serialization(solver):
    task = retain(solver)
    restored = pickle.loads(pickle.dumps(task))
    solver.tasks = [restored]
    original_time = restored.time
    change_binding(solver)
    solver._resume_failed_tasks()
    assert solver.tasks[0] is restored
    assert restored.derived_correction
    assert restored.time is original_time
    assert restored.plan == {}
    assert not restored.retains_execution


@pytest.fixture
def ordinary_solver(monkeypatch):
    solver = shared.solver.__wrapped__(monkeypatch)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [Room("伊内丝", "甲", ["陈"])],
                "dormitory_1": [
                    Room("塑心", "", []),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [],
    }
    solver.op_data = None
    assert solver.initialize_operators() is None
    solver.op_data.first_init = False
    solver.task = None
    solver._refresh_deferred_product_reservations = MagicMock()
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    solver.op_data = solver.op_data.project_arrangements([{"meeting": ["陈"]}])
    solver.op_data.commit_group_shifts({"甲": False})
    assert solver.agent_get_mood(read_rooms=False) == "self_correction"
    return solver


@pytest.mark.parametrize("protection", [None, "started", "explicit"])
def test_waiting_correction_refreshes_only_after_predecessor_finishes(
    ordinary_solver, protection
):
    solver = ordinary_solver
    task = solver.tasks[0]
    before, original_time = copy.deepcopy(task.plan), task.time
    assert before == {"meeting": ["伊内丝"]}
    if protection == "started":
        task.derived_correction_started = True
    elif protection == "explicit":
        task.backup_explicit_slots = {("meeting", 0)}
    predecessor = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈"]}
    )
    predecessor.group_shift_expected = {("meeting", 0): "陈"}
    independent = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks.extend([predecessor, independent])
    with pytest.raises(GroupShiftBlocked) as blocked:
        solver._prepare_group_shift(task)
    assert predecessor in blocked.value.predecessors
    solver._suspend_group_shift(
        task, blocked.value.groups, predecessors=blocked.value.predecessors
    )
    with patch.object(
        solver, "_refresh_derived_correction", wraps=solver._refresh_derived_correction
    ) as refresh:
        for _ in range(3):
            solver._resume_waiting_group_shifts()
        refresh.assert_not_called()
        assert solver.waiting_group_shifts == [task]
        assert task.plan == before
        assert independent in solver.tasks
        solver.tasks.remove(predecessor)
        solver.op_data.commit_group_shifts({"甲": True})
        assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
        solver._resume_waiting_group_shifts()
        refresh.assert_called_once_with(task)
        solver._resume_waiting_group_shifts()
        refresh.assert_called_once_with(task)
    assert any(queued is task for queued in solver.tasks)
    assert solver.waiting_group_shifts == []
    assert task.time is original_time
    assert task.plan == (before if protection else {})
    assert independent in solver.tasks
    solver.enter_room.assert_not_called()
