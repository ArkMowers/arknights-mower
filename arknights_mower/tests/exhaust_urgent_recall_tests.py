"""用尽急救允许整组让出替班，普通回班保护仍独立生效。"""

from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils.recovery_execution import required_recovery_members
from arknights_mower.utils.scheduler_task import TaskTypes


@pytest.mark.parametrize("ordinary", [False, True])
def test_exhausted_worker_recalls_cover_owner_without_ordinary_wait(solver, ordinary):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.group_recovery_full_members = {"感知": ["苍苔", "絮雨"]}
    solver.task.ordinary_coordination = ordinary
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    original = solver.task
    solver.overtake_room()
    support = [task for task in solver.tasks if getattr(task, "exhaust_support", False)]
    if ordinary:
        assert support == []
    else:
        assert len(support) == 1
        assert support[0].plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
        assert original in solver.tasks
        assert original.execution_failure
        assert original.type == TaskTypes.EXHAUST_OFF
        solver.task = support[0]
        assert solver._coordination_support_valid(support[0].plan, ["机械师"])
        assert required_recovery_members(data, support[0]) == set()
    assert data.operators["苍苔"].is_resting()
    assert data.operators["槐琥"].current_room == "room_2_2"


def test_exhausted_worker_still_respects_explicit_full_recovery(solver):
    data = solver.op_data
    data.operators["苍苔"].replacement = ["槐琥"]
    data.plan["room_2_2"][0].replacement = ["槐琥"]
    data.operators["絮雨"].rest_in_full = True
    solver.check_fia = MagicMock(return_value=([], None))
    assert solver._plan_exhaust_support(["机械师"], urgent=True) is None


def test_failed_support_is_reused_without_rebuilding_request(solver):
    solver.check_fia = MagicMock(return_value=([], None))
    solver.skip = MagicMock()
    original = solver.task
    solver.overtake_room()
    support = next(
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    )
    solver._retain_failed_task(support, "副表改变交接条件", list(support.plan))
    original_time, support_time = original.time, support.time
    for _ in range(5):
        solver.task = original
        solver.overtake_room()
    assert [
        task for task in solver.tasks if getattr(task, "exhaust_support", False)
    ] == [support]
    assert support.execution_failure
    assert original in solver.tasks
    assert (original.time, support.time) == (original_time, support_time)


def test_support_rechecks_replacements_in_final_backup_without_mutating_actual(solver):
    from arknights_mower.utils.plan import Plan, PlanConfig, Room
    from arknights_mower.utils.scheduler_task import SchedulerTask

    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    solver.task.exhaust_support = True
    plan = {"room_2_2": ["引星棘刺"]}
    assert solver._coordination_support_valid(plan, ["机械师"])
    solver.op_data.backup_plans = [
        Plan({"room_3_3": [Room("机械师", "", [])]}, PlanConfig("", "", ""))
    ]
    solver.op_data.global_plan["backup_plans"] = solver.op_data.backup_plans
    solver.op_data.plan_condition = [False]
    solver.task.backup_shift_conditions = [True]
    assert not solver._coordination_support_valid(plan, ["机械师"])
    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.operators["机械师"].replacement == ["槐琥"]
    assert solver.op_data.operators["槐琥"].current_room == "room_2_2"
