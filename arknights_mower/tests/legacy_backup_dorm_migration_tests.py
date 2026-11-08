"""旧版副表宿舍迁移按实际固定替班职责重算，保留原任务与真实承诺。"""

import pickle
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests import group_dorm_migration_tests as roles
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = roles.solver
isolated_agent_history = roles.isolated_agent_history
covered_group_bed = roles.covered_group_bed
pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def waiting_migration(covered_group_bed, solver):
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=10),
        task_type=TaskTypes.RE_ORDER,
        meta_data="副表内存收敛",
        task_plan={"dormitory_1": ["塑心", "Current", "银灰", "讯使", "伊内丝"]},
    )
    task.group_shift_waiting = {"联动"}
    task.group_shift_predecessors = ()
    task.backup_refresh_rules = {"伊内丝": (False, [False, []])}
    task.log_source_title = "副表宿舍调整"
    solver.tasks = []
    solver.waiting_group_shifts = [task]
    solver.task = None
    return solver, task


def actual_state(data):
    return (
        {
            name: (op.current_room, op.current_index, op.mood, op.time_stamp)
            for name, op in data.operators.items()
        },
        [(bed.position, bed.name, bed.time) for bed in data.all_dorms()],
        {group: data.group_is_resting(group) for group in data.groups},
    )


@pytest.mark.parametrize("restore", [False, True])
def test_stale_migration_resumes_once_without_waiting_for_its_own_reservation(
    waiting_migration, restore
):
    scheduler, original = waiting_migration
    independent = SchedulerTask(task_type=TaskTypes.CLUE)
    scheduler.tasks.append(independent)
    if restore:
        scheduler.tasks, scheduler.waiting_group_shifts = pickle.loads(
            pickle.dumps((scheduler.tasks, scheduler.waiting_group_shifts))
        )
        independent = scheduler.tasks[0]
        original = scheduler.waiting_group_shifts[0]
    before = actual_state(scheduler.op_data)
    at, refresh = original.time, deepcopy(original.backup_refresh_rules)
    assert scheduler.op_data.group_is_resting("联动")
    for _ in range(3):
        scheduler._resume_waiting_group_shifts()
        assert not scheduler.waiting_group_shifts
        assert sum(task is original for task in scheduler.tasks) == 1
        assert any(task is independent for task in scheduler.tasks)
        assert original.time == at
        assert original.backup_refresh_rules == refresh
        assert actual_state(scheduler.op_data) == before
    assert not original.plan
    assert scheduler._complete_group_shift(original)


def test_replanning_keeps_uncached_displaced_primary_and_other_reservations(
    waiting_migration,
):
    scheduler, original = waiting_migration
    data = scheduler.op_data
    data.global_plan["backup_plans"].append(
        Plan(
            {
                "dormitory_1": [
                    Room("Current", "", []),
                    Room("Current", "", []),
                    Room("Current", "", []),
                    Room("年", "", []),
                    Room("Current", "", []),
                ]
            },
            PlanConfig("", "", ""),
        )
    )
    assert data.swap_plan([True], refresh=True) is None
    data.displaced_dorms = []
    assert data.get_dorm_by_name("讯使")[1] is None
    assert data.operators["讯使"].current_room == "dormitory_1"
    protected = SchedulerTask(
        task_type=TaskTypes.RE_ORDER,
        task_plan={"dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]},
    )
    protected.execution_retained = True
    scheduler.tasks.append(protected)
    protected_plan = deepcopy(protected.plan)
    before = actual_state(data)
    assert scheduler._refresh_derived_correction(original)
    assert original.plan["dormitory_1"][3] == "年"
    assert original.plan["dormitory_1"][4] == "讯使"
    assert original.plan["dormitory_1"][1] == "Current"
    assert protected.plan == protected_plan
    assert actual_state(data) == before


def test_cycle_refresh_keeps_an_unrelated_started_waiting_batch(waiting_migration):
    scheduler, original = waiting_migration
    protected = SchedulerTask(
        time=original.time - timedelta(minutes=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]},
    )
    protected.group_shift_waiting = set()
    protected.group_shift_expected = {("dormitory_1", 1): "冰酿"}
    scheduler.waiting_group_shifts.insert(0, protected)
    before, physical = pickle.dumps(protected), actual_state(scheduler.op_data)

    scheduler._resume_waiting_group_shifts(refresh_migrations_only=True)

    assert scheduler.waiting_group_shifts == [protected]
    assert scheduler.waiting_group_shifts[0] is protected
    assert pickle.dumps(protected) == before
    assert sum(task is original for task in scheduler.tasks) == 1
    assert not original.plan
    assert actual_state(scheduler.op_data) == physical


@pytest.mark.parametrize(
    "field,value",
    [
        ("meta_data", "手动宿舍调整"),
        ("execution_failure", {"reason": "尚未确认"}),
        ("execution_retained", True),
        ("mood_physical_started", True),
        ("derived_correction_started", True),
        ("group_shift_expected", {("dormitory_1", 0): "塑心"}),
        ("backup_shift_active", True),
        ("backup_explicit_slots", {("dormitory_1", 0)}),
        ("product_shift_locked", True),
        ("backup_retention_admissions", {"伊内丝"}),
        ("backup_retention_releases", {"伊内丝": ("dormitory_1", 0)}),
        ("backup_retention_empty_slots", {("dormitory_1", 0): "伊内丝"}),
    ],
)
def test_explicit_or_started_migration_preserves_its_saved_plan(
    waiting_migration, field, value
):
    scheduler, original = waiting_migration
    setattr(original, field, deepcopy(value))
    before = pickle.dumps(original)
    assert not scheduler._refresh_derived_correction(original)
    assert pickle.dumps(original) == before


def test_mixed_work_arrangement_is_not_replaced_as_dorm_migration(waiting_migration):
    scheduler, original = waiting_migration
    original.plan["meeting"] = ["伊内丝", "银灰"]
    before = pickle.dumps(original)
    assert not scheduler._refresh_derived_correction(original)
    assert pickle.dumps(original) == before


def test_lost_fixed_role_is_not_mistaken_for_a_stale_migration(waiting_migration):
    scheduler, original = waiting_migration
    scheduler.op_data.plan["dormitory_1"][0].replacement = ["银灰"]
    scheduler.op_data.operators["塑心"].replacement = ["银灰"]
    before = pickle.dumps(original)
    assert not scheduler._refresh_derived_correction(original)
    assert pickle.dumps(original) == before
