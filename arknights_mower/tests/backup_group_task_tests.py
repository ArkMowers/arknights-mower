"""副表绑组任务保留持续意图，并遵守替班交接与强制下班要求。"""

import pickle
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.exhaust_replacement_tests import solver as solver
from arknights_mower.utils.backup_group_tasks import (
    filter_held_returns,
    held_rest_groups,
    sync_group_tasks,
)
from arknights_mower.utils.config.plan import BackupPlan, PlanModel
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, plan_metadata


def enable(solver, mode="while_active", action="off"):
    backup = Plan(
        {},
        PlanConfig("", "", ""),
        group_tasks=[{"group": "感知", "action": action, "mode": mode}],
    )
    solver.op_data.backup_plans = [backup]
    solver.op_data.global_plan["backup_plans"] = [backup]
    solver.op_data.plan_condition = [True]
    solver._emergency_frozen = lambda: False
    return backup


def test_once_is_preserved_across_restart_and_resets_on_reactivation(solver):
    enable(solver, "once", "on")
    now = datetime(2026, 10, 31)
    sync_group_tasks(solver, now=now)
    (task,) = solver.tasks
    assert task.time == now
    assert task.plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    assert SchedulerTask().plan == {}
    solver.backup_group_task_issued = pickle.loads(
        pickle.dumps(solver.backup_group_task_issued)
    )
    solver.tasks.clear()
    sync_group_tasks(solver)
    assert solver.tasks == []
    solver.op_data.plan_condition = [False]
    sync_group_tasks(solver)
    solver.op_data.plan_condition = [True]
    sync_group_tasks(solver)
    assert len(solver.tasks) == 1


def test_compatible_requests_from_two_backups_share_pending_group_work(solver):
    backup = enable(solver, "once", "on")
    solver.op_data.backup_plans = [backup, backup]
    solver.op_data.plan_condition = [True, True]
    for _ in range(6):
        sync_group_tasks(solver)
    assert len(solver.tasks) == 1
    solver.op_data = solver.op_data.project_arrangements([solver.tasks[0].plan])
    solver.op_data.commit_group_shifts({"感知": False})
    solver.tasks.clear()
    sync_group_tasks(solver)
    assert solver.tasks == []
    assert len(solver.backup_group_task_issued) == 2


@pytest.mark.parametrize("mode", ["while_active", "forced"])
def test_hold_suppresses_derived_return_and_exit_restores_deadline(solver, mode):
    enable(solver, mode)
    solver.tasks = plan_metadata(solver.op_data, solver.tasks)
    assert not any(t.type == TaskTypes.SHIFT_ON for t in solver.tasks)
    solver.op_data.plan_condition = [False]
    sync_group_tasks(solver)
    solver.tasks = plan_metadata(solver.op_data, solver.tasks)
    returns = [t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]
    assert returns
    assert all(t.time > datetime.now() for t in returns)


def test_hold_preserves_other_groups_in_mixed_return(solver):
    enable(solver)
    mixed = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"room_2_2": ["苍苔"], "contact": ["絮雨"], "meeting": ["能天使"]},
    )
    solver.tasks = [mixed]
    filter_held_returns(solver.op_data, solver.tasks)
    assert mixed.plan == {"meeting": ["能天使"]}
    assert solver.tasks == [mixed]


def test_hold_waits_for_support_recovery_then_requests_rest_again(solver):
    enable(solver)
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "room_3_3": ["槐琥"],
                "dormitory_1": ["冰酿", "闪灵", "机械师", "Free", "Free"],
            }
        ]
    )
    solver.op_data.commit_group_shifts({"感知": False})
    solver.op_data.urgent_recovery_supporters = {"机械师": ["苍苔", "絮雨"]}
    for _ in range(5):
        sync_group_tasks(solver)
    assert solver.tasks == []
    solver.op_data.urgent_recovery_supporters.clear()
    sync_group_tasks(solver)
    (request,) = solver.tasks
    assert request.type == TaskTypes.EXHAUST_OFF
    for _ in range(5):
        sync_group_tasks(solver)
    assert solver.tasks == [request]


@pytest.mark.parametrize("mode,allowed", [("while_active", True), ("forced", False)])
def test_real_exhaust_coordination_respects_hold_mode(solver, mode, allowed):
    enable(solver, mode)
    solver.op_data.operators["苍苔"].replacement = ["槐琥"]
    solver.op_data.plan["room_2_2"][0].replacement = ["槐琥"]
    solver.check_fia = MagicMock(return_value=([], None))
    assert bool(solver._plan_exhaust_support(["机械师"], urgent=True)) == allowed
    assert held_rest_groups(solver.op_data, forced_only=True) == (
        {"感知"} if not allowed else set()
    )


@pytest.mark.parametrize("mode,allowed", [("while_active", True), ("forced", False)])
def test_forced_hold_keeps_occupied_cover_even_when_owner_has_an_alternate(
    solver, mode, allowed
):
    enable(solver, mode)
    solver.check_fia = MagicMock(return_value=([], None))
    support = solver._plan_exhaust_support(["机械师"], urgent=True)
    assert bool(support) == allowed
    if allowed:
        assert support["room_2_2"] == ["引星棘刺"]


def test_exit_cancels_unstarted_request_and_keeps_started_work(solver):
    enable(solver, "once", "on")
    sync_group_tasks(solver)
    (request,) = solver.tasks
    request.mood_physical_started = True
    solver.op_data.plan_condition = [False]
    sync_group_tasks(solver)
    assert solver.tasks == [request]
    request.mood_physical_started = False
    sync_group_tasks(solver)
    assert solver.tasks == []


@pytest.mark.parametrize(
    "entries",
    [
        [{"group": "感知", "action": "on", "mode": "forced"}],
        [{"group": "感知"}, {"group": "感知"}],
        [{"group": " 感知"}],
    ],
)
def test_invalid_group_task_schema_is_rejected(entries):
    with pytest.raises(ValueError):
        BackupPlan(group_tasks=entries)


def test_waiting_request_is_not_duplicated_and_is_cancelled_on_exit(solver):
    enable(solver, "while_active", "off")
    solver.op_data = solver.op_data.project_arrangements(
        [{"room_2_2": ["苍苔"], "contact": ["絮雨"]}]
    )
    solver.op_data.commit_group_shifts({"感知": False})
    sync_group_tasks(solver)
    (request,) = solver.tasks
    solver.waiting_group_shifts = [request]
    solver.tasks = []
    for _ in range(6):
        sync_group_tasks(solver)
    assert solver.tasks == []
    assert solver.waiting_group_shifts == [request]
    solver.op_data.plan_condition = [False]
    sync_group_tasks(solver)
    assert solver.waiting_group_shifts == []


def test_request_owner_survives_complete_departure_planning(solver):
    enable(solver)
    solver.op_data = solver.op_data.project_arrangements(
        [
            {
                "room_2_2": ["苍苔"],
                "contact": ["絮雨"],
                "dormitory_1": ["冰酿", "闪灵", "Free", "Free", "Free"],
            }
        ]
    )
    solver.op_data.commit_group_shifts({"感知": False})
    sync_group_tasks(solver)
    (request,) = solver.tasks
    solver.task = request
    solver.overtake_room()
    departure = next(task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF)
    assert departure.backup_group_request == request.backup_group_request
    assert "苍苔" in departure.plan["dormitory_1"]
    assert "絮雨" in departure.plan["dormitory_1"]


def test_plan_schema_rejects_unknown_group_even_in_inactive_backup():
    with pytest.raises(ValueError, match="绑组任务组名不存在"):
        PlanModel(backup_plans=[{"group_tasks": [{"group": "missing"}]}])


def test_plan_schema_accepts_group_declared_by_another_backup_and_round_trips():
    source = {
        "advanced_settings": {"group_mood_gap_threshold_minutes": 90},
        "backup_plans": [
            {
                "name": "休息",
                "group_tasks": [{"group": "感知", "mode": "while_active"}],
            },
            {
                "name": "岗位",
                "plan": {"contact": {"plans": [{"agent": "絮雨", "group": "感知"}]}},
            },
        ],
    }
    model = PlanModel.model_validate(source)
    restored = PlanModel.model_validate_json(model.model_dump_json())
    assert restored.backup_plans[0].group_tasks[0].model_dump() == {
        "group": "感知",
        "action": "off",
        "mode": "while_active",
    }
    assert restored.advanced_settings == source["advanced_settings"]


def test_combination_validation_checks_group_requests_with_identical_room_plans(solver):
    enable(solver, "while_active", "off")
    backup = Plan(
        {},
        PlanConfig("", "", ""),
        group_tasks=[{"group": "感知", "action": "on", "mode": "once"}],
    )
    solver.op_data.backup_plans.append(backup)
    solver.op_data.global_plan["backup_plans"] = solver.op_data.backup_plans
    result = solver.op_data.validate_backup_plans(check_owned=False)
    assert result["success"] is False
    assert "相反" in result["message"]
