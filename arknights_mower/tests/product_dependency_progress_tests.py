"""换班依赖保留原任务，不用计时重试阻止独立安排。"""

import copy
from datetime import datetime, timedelta

import jsonpickle
import pytest

from arknights_mower.tests import product_shift_dispatch_tests as dispatch
from arknights_mower.utils.dorm_candidates import (
    dorm_task_reservations,
    retained_task_reservations,
)
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)

pending_return = dispatch.pending_return


@pytest.mark.parametrize("kind", ["shift", "fia"])
def test_failed_global_predecessor_does_not_postpone_independent_shift(
    pending_return, kind
):
    solver, product, returning, changes = pending_return
    solver.tasks.remove(product)
    previous = SchedulerTask(
        time=returning.time - timedelta(minutes=20),
        task_plan={"room_1_2": ["Lancet-2"]},
        task_type=TaskTypes.FIAMMETTA if kind == "fia" else TaskTypes.RE_ORDER,
    )
    previous.backup_shift_active = kind == "shift"
    solver.tasks.insert(0, previous)
    solver.op_data.update_facility_state("room_1_2", "manufacture", "exp3")
    solver._retain_failed_task(previous, "驻员尚未确认", list(previous.plan))
    returning.backup_shift_conditions = list(solver.op_data.plan_condition)
    solver.task = returning
    before = previous.time, returning.time, copy.deepcopy(previous.plan)
    solver.infra_main()
    assert any(item[0] == "arrange" for item in changes)
    assert returning not in solver.tasks
    assert previous in solver.tasks and previous.execution_failure
    assert (previous.time, returning.time, previous.plan) == before
    if kind == "shift":
        assert not [change for change in changes if change[0] == "product"]
        assert solver.op_data.products["room_1_2"] == "exp3"


@pytest.mark.parametrize("serialized", [False, True])
def test_shared_slot_wait_keeps_original_and_releases_after_owner_completion(
    pending_return, serialized, monkeypatch
):
    solver, product, returning, changes = pending_return
    solver.tasks.remove(product)
    owner = SchedulerTask(
        time=returning.time, task_plan={"central": ["红"]}, task_type=TaskTypes.RE_ORDER
    )
    owner.product_shift_locked = True
    owner.product_lock_slots = {("central", 0)}
    owner.product_lock_names = {"红"}
    owner.backup_shift_active = True
    solver.tasks.insert(0, owner)
    solver._retain_failed_task(owner, "生产结果未确认", ["central"])
    returning.backup_shift_intent = copy.deepcopy(returning.plan)
    returning.backup_shift_conditions = list(solver.op_data.plan_condition)
    original_time, original_plan = returning.time, copy.deepcopy(returning.plan)
    solver.task = returning
    solver.infra_main()
    assert returning.time == original_time
    assert returning.plan == original_plan
    assert returning.execution_failure["dependency"]
    if serialized:
        solver.tasks = jsonpickle.decode(jsonpickle.encode(solver.tasks))
        owner = next(task for task in solver.tasks if task.type == TaskTypes.RE_ORDER)
        returning = next(
            task for task in solver.tasks if task.type == TaskTypes.SHIFT_ON
        )
        assert returning.product_shift_predecessors == (owner,)

    class Clock(datetime):
        current = datetime.now()

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(dispatch.base, "datetime", Clock)
    for _ in range(4):
        Clock.current += timedelta(minutes=5)
        solver._resume_failed_tasks()
        assert returning not in task_view(
            solver.tasks, TaskScope.DISPATCH, solver.op_data
        )
        assert returning.time == original_time
    # Waiting work must not reserve the replacement needed by its predecessor.
    names, slots = retained_task_reservations(solver.op_data, [returning])
    assert not names and not slots
    assert dorm_task_reservations(solver.op_data, [returning]) == (set(), set())
    solver.tasks.remove(owner)
    solver._resume_failed_tasks()
    assert returning in task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
    solver.task = returning
    solver.infra_main()
    assert returning not in solver.tasks
    assert returning.time == original_time
    assert solver.op_data.operators["陈"].is_working()
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.products["room_1_2"] == "gold"


def test_waiting_dorm_target_does_not_reserve_predecessor_bed(pending_return):
    solver, _, _, _ = pending_return
    task = SchedulerTask(
        task_type=TaskTypes.RE_ORDER, task_plan={"dormitory_1": ["红"]}
    )
    task.product_shift_waiting = True
    solver._retain_failed_task(task, "等待前置安排", ["dormitory_1"], dependency=True)
    assert retained_task_reservations(solver.op_data, [task]) == (set(), set())
    assert dorm_task_reservations(solver.op_data, [task]) == (set(), set())
    task.backup_shift_active = True
    names, slots = dorm_task_reservations(solver.op_data, [task])
    assert "红" in names and ("dormitory_1", 0) in slots


def test_product_lock_allows_source_release_but_keeps_destination(pending_return):
    solver, product, _, _ = pending_return
    owner = SchedulerTask(task_type=TaskTypes.RE_ORDER, task_plan={"room_1_2": ["红"]})
    owner.product_shift_locked = True
    owner.product_lock_slots = {("room_1_2", 0)}
    owner.product_lock_names = {"红", "Lancet-2"}
    source = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"central": ["陈"]}
    )
    solver.tasks = [owner, source]
    solver._retain_failed_task(owner, "等待源岗位释放", list(owner.plan))
    solver._refresh_deferred_product_reservations()
    plan = copy.deepcopy(source.plan)
    solver.task = source
    solver._suppress_retained_arrangements(plan)
    assert plan == source.plan
    solver._defer_conflicting_product_shift_slots(source)
    names, slots = retained_task_reservations(solver.op_data, [owner])
    assert "红" in names
    assert ("room_1_2", 0) in slots and ("central", 0) not in slots


def test_due_charging_does_not_skip_owned_product_switch(pending_return):
    solver, product, returning, _ = pending_return
    solver.tasks.remove(product)
    solver.op_data.update_facility_state("room_1_2", "manufacture", "exp3")
    returning.product_shift_locked = True
    returning.pending_product_targets = {"room_1_2": "gold"}
    solver.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    solver._switch_products_before_arrangement(returning)
    assert solver.op_data.facility_states["room_1_2"]["product"] == "gold"
