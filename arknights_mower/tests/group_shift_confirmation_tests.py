"""换班确认保留有效目标，并允许预约所属任务和共同候补继续执行。"""

# ruff: noqa: E402

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import ProductSwitchDeferred
from arknights_mower.tests.multi_group_shift_tests import SHARED, A, B, shift_off
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("reserved", [False, True])
def test_available_common_cover_is_considered(solver, reserved):
    data = solver.op_data
    shared = data.operators[SHARED]
    shared.group_bindings[0]["replacement"] = ["红", "黑角"]
    shared.group_bindings[1]["replacement"] = ["红", "黑角"]
    shared.replacement = ["红", "黑角"]
    assert shift_off(solver, "甲")[0]
    assert shift_off(solver, "乙")[0]
    data = solver.op_data
    # The queued first return still requests the shared primary. The current
    # cover has subsequently been taken by another facility; 黑角 is idle.
    data.operators["红"]._current_room = "factory"
    data.operators["红"].current_index = 0
    assert not data.operators["黑角"].current_room
    plan = {"meeting": [A, "Current"], "contact": [SHARED]}
    if reserved:
        data.reserved_product_replacements = {"黑角"}
        assert not data.normalize_shared_arrangement(plan)
        assert plan["contact"] == [SHARED]
        return
    assert data.normalize_shared_arrangement(plan)
    assert plan["contact"] == ["黑角"]


@pytest.mark.parametrize("recovered", [False, True])
@pytest.mark.parametrize("contact_confirmed", [False, True])
def test_released_recovery_target_does_not_block_completed_shift(
    solver, recovered, contact_confirmed
):
    data = solver.op_data
    data.config.operator_mood_limits[B] = {"lower": 0, "upper": 12}
    data.operators[B].mood = 5
    data.operators[B].upper_limit = 12
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["Current", "初雪"],
            "contact": ["黑角"],
            "dormitory_1": ["Current", "Current", B, SHARED, "Current"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    # Other rooms finish while contact stays pending. A personal-limit release
    # may execute during the pending shift and legitimately remove this resident.
    observed = data.project_arrangements([task.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    data.operators[B].mood = 12 if recovered else 5
    data.operators[B].time_stamp = datetime.now()
    data.operators[B].rest_mood_release_limit = 12 if recovered else None
    data.operators[B]._current_room = ""
    data.operators[B].current_index = -1
    assert bool(data.rest_mood_complete(B)) is recovered
    task.plan = {}
    assert not solver._complete_group_shift(task)
    assert task.plan["dormitory_1"][2] == B
    task.backup_shift_active = True
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    solver._prepare_group_shift(task, remember_targets=True)
    # The real selection boundary correctly discards this expired recovery
    # target, but confirmation must also forget that obsolete expectation.
    solver.preserve_resting_crafters = lambda agents, room: None
    solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
    assert task.plan["dormitory_1"][2] == ("Free" if recovered else B)
    if not contact_confirmed:
        data.operators["黑角"]._current_room = ""
        data.operators["黑角"].current_index = -1
    task.plan = {}
    assert solver._complete_group_shift(task) is (recovered and contact_confirmed)
    assert data.group_is_resting("乙") is (recovered and contact_confirmed)
    if not contact_confirmed:
        assert task.group_shift_expected[("contact", 0)] == "黑角"


@pytest.mark.parametrize("other_owner", [False, True])
def test_product_lock_owner_can_retry_its_own_shift(solver, other_owner):
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "meeting": ["陈", "Current"],
            "contact": ["红"],
        },
    )
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task)
    solver._reserve_deferred_product_shift(task, {("meeting", 0), ("contact", 0)})
    if other_owner:
        other = SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF,
            task_plan={
                "meeting": ["陈", "Current"],
                "contact": ["红"],
            },
        )
        solver.tasks.append(other)
        solver._reserve_deferred_product_shift(other, {("meeting", 0), ("contact", 0)})
    solver._refresh_deferred_product_reservations()
    assert "红" in solver.op_data.reserved_product_replacements
    # A retry must reach the product-switch operation to release its own lock.
    reserved = set(solver.op_data.reserved_product_replacements)
    if other_owner:
        with pytest.raises(ProductSwitchDeferred):
            solver._prepare_group_shift(task)
    else:
        solver._prepare_group_shift(task)
        assert task.plan["contact"] == ["红"]
    assert solver.op_data.reserved_product_replacements == reserved


def test_fixed_dorm_target_at_personal_limit_still_requires_confirmation(solver):
    data = solver.op_data
    data.config.operator_mood_limits["塑心"] = {"lower": 0, "upper": 12}
    op = data.operators["塑心"]
    op.mood = op.upper_limit = 12
    op._current_room, op.current_index = "", -1
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"dormitory_1": ["塑心", "Current", "Current", "Current", "Current"]},
    )
    task.group_shift_transitions = {"甲": True}
    task.group_shift_expected = {("dormitory_1", 0): "塑心"}
    solver.task, solver.tasks = task, [task]
    solver.preserve_resting_crafters = lambda agents, room: None
    solver.prepare_dorm_selection(task.plan["dormitory_1"], "dormitory_1")
    assert task.plan["dormitory_1"][0] == "塑心"
    assert not solver._complete_group_shift(task)
    assert task.group_shift_expected == {("dormitory_1", 0): "塑心"}


def test_common_alternatives_allow_complete_matching_across_shared_slots(solver):
    plan = solver.global_plan["default_plan"].plan
    plan["contact"][0].replacement = ["红", "黑角"]
    plan["contact"][0].group_bindings[0]["replacement"] = ["红", "黑角"]
    plan["factory"] = [
        Room(
            "褐果",
            "甲",
            ["红"],
            group_bindings=[{"group": "乙", "replacement": ["红"]}],
        )
    ]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
    proposed = {"meeting": ["陈", "初雪"], "contact": ["红"], "factory": ["红"]}
    assert solver.op_data.normalize_shared_arrangement(proposed)
    assert proposed["contact"] == ["黑角"]
    assert proposed["factory"] == ["红"]
    assert not solver.op_data.group_is_resting("甲")
