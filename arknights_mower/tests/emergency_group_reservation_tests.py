"""未完成整组义务通过共享预约阻止加工和普通补位抢人。"""

import pickle

import pytest

from arknights_mower.tests.emergency_group_staffing_tests import (
    legacy_solver as legacy_solver,
)
from arknights_mower.tests.emergency_group_staffing_tests import (
    recovery_fixture as recovery_fixture,
)
from arknights_mower.tests.emergency_group_staffing_tests import (
    staffing as staffing,  # noqa: F401
)
from arknights_mower.tests.emergency_group_staffing_tests import (
    staffing_task,
)
from arknights_mower.tests.group_resting_capacity_tests import (
    DEEP,
    apply_plan,
    occupy_beds,
)
from arknights_mower.tests.group_resting_capacity_tests import (
    solver as standby_solver,  # noqa: F401
)
from arknights_mower.tests.mass_mood_recovery_tests import PRIMARY
from arknights_mower.utils.dorm_candidates import dorm_task_reservations
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, try_reorder
from arknights_mower.utils.workshop_limits import workshop_operator_block_reason


@pytest.mark.parametrize("remaining", ["initial", "one_room", "check_only"])
def test_complete_group_remains_reserved_as_individual_room_plans_finish(
    staffing,
    remaining,  # noqa: F811
):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    members = set(task.emergency_staffing_members)
    assert members == set(PRIMARY)
    if remaining == "one_room":
        task.plan = {"room_1_1": ["红"]}
    elif remaining == "check_only":
        check = SchedulerTask(meta_data="自动救急继续安排")
        check.emergency_staffing_members = list(members)
        task = check
    task = pickle.loads(pickle.dumps(task))

    reserved, _ = dorm_task_reservations(solver.op_data, [task])

    assert members <= reserved
    for name in members:
        assert "自动救急换班任务预约" in workshop_operator_block_reason(
            solver.op_data, name, [task], minimum_mood=0
        )


def test_group_membership_reservation_does_not_block_unrelated_workshop_worker(
    staffing,  # noqa: F811
):
    solver = staffing.solver
    assert solver._emergency_schedule_staffing()
    task = staffing_task(solver)
    assert "冰酿" not in task.emergency_staffing_members

    assert (
        workshop_operator_block_reason(solver.op_data, "冰酿", [task], minimum_mood=22)
        is None
    )


def test_completed_group_releases_shared_obligation(staffing):  # noqa: F811
    solver = staffing.solver
    check = SchedulerTask(meta_data="自动救急继续安排")
    check.emergency_staffing_members = []

    assert "塑心" not in dorm_task_reservations(solver.op_data, [check])[0]
    assert (
        workshop_operator_block_reason(solver.op_data, "塑心", [check], minimum_mood=22)
        is None
    )


def test_workshop_keeps_explicit_standby_return_reservation(standby_solver):  # noqa: F811
    solver = standby_solver
    occupy_beds(solver, "high")
    plan = solver.resting()
    beds = try_reorder(solver.op_data, plan)
    apply_plan(solver, plan)
    apply_plan(solver, beds)
    data = solver.op_data
    name = DEEP[1]
    assert data.is_standby(name)
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={data.operators[name].room: [name]},
    )

    # Dormitory filling may offer a spare bed until the scheduled return;
    # crafting must retain the explicit working-facility reservation.
    assert name not in dorm_task_reservations(data, [task])[0]
    assert workshop_operator_block_reason(data, name, [task]) == "已被上班任务预约"
