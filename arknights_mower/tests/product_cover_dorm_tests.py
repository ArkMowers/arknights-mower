"""切产物等待中的普通替班临时恢复保留工作预约及床位保护。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import product_shift_cycle_resume_tests as cycle
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = cycle.solver
shared_product_cycle = cycle.shared_product_cycle


@pytest.fixture
def waiting_cover(shared_product_cycle):
    instance, task = shared_product_cycle
    original = instance.op_data
    plans = deepcopy(original.global_plan)
    plans["default_plan"].plan["dormitory_2"] = [
        Room("杜林", "", []),
        Room("桃金娘", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    data = Operators(plans)
    assert data.init_and_validate() is None
    assert data.swap_plan([True, False], refresh=True) is None
    for name, op in original.operators.items():
        data.operators[name] = deepcopy(op)
    for name, index in (("芬", 2), ("香草", 3), ("翎羽", 4)):
        data.add(Operator(name, "", mood=12, time_stamp=datetime.now()))
        op = data.operators[name]
        op._current_room, op.current_index = "dormitory_2", index
    for name in ("杜林", "桃金娘"):
        op = data.operators[name]
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    for bed in data.dorm:
        occupant = data.get_current_operator(*bed.position)
        bed.name = occupant.name if occupant else ""
    data.group_shift_state = deepcopy(original.group_shift_state)
    data.first_init = False
    data.update_facility_state("room_1_2", "manufacture", "exp3")
    instance.op_data = data
    instance._prepare_group_shift(task)
    instance._prepare_shift_cycle(task)
    instance.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "等待制造完成", ready_at=task.time + timedelta(minutes=2)
        )
    )
    with pytest.raises(base.ProductSwitchDeferred):
        instance._switch_products_before_arrangement(task)
    instance._refresh_deferred_product_reservations()
    return instance, task


def open_independent_bed(data):
    op = data.operators["芬"]
    op._current_room, op.current_index = "", -1
    op.mood = 24
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_2", 2))
    bed.name, bed.time = "", None


def test_waiting_cover_enters_vacancy_through_planning_and_selection(waiting_cover):
    instance, locked = waiting_cover
    data = instance.op_data
    open_independent_bed(data)
    cover = data.operators["虎狼丸"]
    cover._current_room, cover.current_index = "", -1
    for bed in data.dorm:
        if bed.name == cover.name:
            bed.name, bed.time = "", None
    original_plan = {room: row.copy() for room, row in locked.plan.items()}
    assert "虎狼丸" in data.reserved_product_replacements
    assert instance._fill_empty_dorms(primary_planned=True)
    fill = next(task for task in instance.tasks if task is not locked)
    assert fill.type == TaskTypes.FILL_DORM
    assert any("虎狼丸" in row for row in fill.plan.values())
    instance._prepare_group_shift(fill)
    instance._prepare_shift_cycle(fill)
    instance._defer_conflicting_product_shift_slots(fill)
    projected = data.project_arrangements([fill.plan])
    assert projected.operators["虎狼丸"].is_resting()
    assert projected.operators["令"].current_room == "dormitory_1"
    assert projected.operators["香草"].current_room == "dormitory_2"
    assert data.operators["森蚺"].is_working()
    assert not data.group_is_resting("自动化")
    assert locked.plan == original_plan
    assert "虎狼丸" in data.reserved_product_replacements
    instance.tasks.remove(fill)
    instance.task = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
    )
    assert "虎狼丸" in instance.get_dorm_candidates().recovering


def test_waiting_cover_can_move_without_releasing_reserved_beds(waiting_cover):
    instance, locked = waiting_cover
    open_independent_bed(instance.op_data)
    reserved, beds = dorm_task_reservations(instance.op_data, [locked])
    assert "虎狼丸" not in reserved
    assert "森蚺" in reserved
    assert set(instance.op_data.reserved_product_beds) <= beds
    move = SchedulerTask(
        task_type=TaskTypes.NOT_SPECIFIC,
        task_plan={
            "dormitory_2": ["Current", "Current", "虎狼丸", "Current", "Current"]
        },
    )
    instance._defer_conflicting_product_shift_slots(move)
    instance.task = SchedulerTask(task_plan={"dormitory_2": ["Current"] * 5})
    assert (
        "虎狼丸"
        in instance.get_dorm_candidates(
            current_resident="虎狼丸", room="dormitory_1"
        ).recovering
    )


@pytest.mark.parametrize("conflict", ["work", "primary", "bed"])
def test_temporary_recovery_keeps_product_conflicts(waiting_cover, conflict):
    instance, locked = waiting_cover
    if conflict == "work":
        plan = {"room_1_2": ["虎狼丸"]}
    elif conflict == "primary":
        plan = {"dormitory_1": ["Current"] * 4 + ["森蚺"]}
    else:
        room, index = next(iter(instance.op_data.reserved_product_beds))
        plan = {room: ["Current"] * len(instance.op_data.plan[room])}
        plan[room][index] = "虎狼丸"
    other = SchedulerTask(task_plan=plan)
    with pytest.raises(base.ProductSwitchDeferred) as caught:
        instance._defer_conflicting_product_shift_slots(other)
    assert caught.value.dependencies == (locked,)


@pytest.mark.parametrize(
    "started",
    [
        "backup_shift_active",
        "product_switched_before_arrangement",
        "group_shift_expected",
        "arrangement_retry_room",
        "working",
    ],
)
def test_started_handoff_or_working_cover_stays_protected(waiting_cover, started):
    instance, locked = waiting_cover
    if started == "working":
        cover = instance.op_data.operators["虎狼丸"]
        cover._current_room, cover.current_index = "room_1_2", 0
    else:
        setattr(
            locked,
            started,
            {("meeting", 1): "虎狼丸"} if started == "group_shift_expected" else True,
        )
    assert "虎狼丸" in dorm_task_reservations(instance.op_data, [locked])[0]
    other = SchedulerTask(task_plan={"dormitory_1": ["Current"] * 4 + ["虎狼丸"]})
    with pytest.raises(base.ProductSwitchDeferred):
        instance._defer_conflicting_product_shift_slots(other)


def test_other_task_reservations_still_exclude_waiting_cover(waiting_cover):
    instance, locked = waiting_cover
    other = SchedulerTask(task_plan={"meeting": ["Current", "虎狼丸"]})
    instance.tasks.append(other)
    assert "虎狼丸" in dorm_task_reservations(instance.op_data, instance.tasks)[0]
    instance.task = None
    assert (
        "虎狼丸"
        not in instance.get_dorm_candidates(
            current_resident="虎狼丸", room="dormitory_1"
        ).filling
    )


@pytest.mark.parametrize("same_task", [False, True])
def test_urgent_task_keeps_name_and_bed_reservations(waiting_cover, same_task):
    instance, locked = waiting_cover
    urgent = locked if same_task else SchedulerTask()
    urgent.urgent_recovery_reserved_names = {"虎狼丸"}
    urgent.urgent_recovery_reserved_slots = {("dormitory_2", 2)}
    names, slots = dorm_task_reservations(instance.op_data, [locked, urgent])
    assert "虎狼丸" in names
    assert ("dormitory_2", 2) in slots


def test_only_original_lock_yields_to_its_independent_return(waiting_cover):
    instance, locked = waiting_cover
    returning = SchedulerTask(task_plan={"central": ["Current", "令"]})
    locked.product_wait_return_task = returning
    instance._defer_conflicting_product_shift_slots(returning)
    other = SchedulerTask(task_plan={"central": ["Current", "令"]})
    other.product_wait_independent_return = True
    with pytest.raises(base.ProductSwitchDeferred):
        instance._defer_conflicting_product_shift_slots(other)
