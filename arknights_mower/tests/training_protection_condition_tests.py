from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.mastery_reader import RoomState
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def protected_solver(solver, monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver.find_next_task = lambda **kwargs: next(
        (task for task in solver.tasks if task.type == kwargs.get("task_type")), None
    )
    backup = Plan(
        {},
        PlanConfig("", "", ""),
        trigger=LogicExpression(
            "op_data.facility_is_protected('train')", "==", "False"
        ),
    )
    solver.op_data.backup_plans.append(backup)
    solver.op_data.plan_condition = [False]
    return solver


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        "database",
        "start_queue",
        "swap_queue",
        "assistant",
        "training",
        "waiting_collect",
        "protected",
        "read_failed",
        "amiya_form_waiting",
        "unreliable",
    ],
)
def test_selection_reuses_live_training_protection(
    protected_solver, monkeypatch, enabled, source
):
    s = protected_solver
    config.conf.enable_mastery = enabled
    if source == "database":
        monkeypatch.setattr(
            mastery_db, "get_active_plan", lambda: {"id": 1, "status": "arranging"}
        )
    elif source in ("start_queue", "swap_queue"):
        kind = (
            TaskTypes.SKILL_UPGRADE
            if source == "start_queue"
            else TaskTypes.SWAP_SUPPORT
        )
        s.tasks.append(SchedulerTask(task_type=kind))
    elif source == "assistant":
        s.op_data.add(Operator("艾丽妮", "", current_room="train", current_index=0))
    elif source in ("training", "waiting_collect"):
        s.train_room_state = RoomState(source)
    elif source == "unreliable":
        s.train_room_state = RoomState("empty", slots_read=True, slots_reliable=False)
    else:
        s.train_room_state = RoomState("empty", **{source: True})
    assert s._evaluate_backup_selection().conditions == [not enabled]
    assert (
        s.op_data.evaluate_expression("op_data.facility_is_protected('train')")
        is enabled
    )
    projected = s.op_data.project_arrangements([])
    assert projected.facility_is_protected("train") is enabled
    with pytest.raises(ValueError, match="训练室位置"):
        projected.facility_is_protected("room_1_1")


def test_backup_switches_on_queue_admission_and_release_without_repeated_tasks(
    protected_solver,
):
    s = protected_solver
    independent = SchedulerTask(
        time=datetime.now() + timedelta(hours=1), task_type=TaskTypes.CLUE
    )
    s.tasks = [independent]
    s.backup_plan_solver()
    assert s.op_data.plan_condition == [True]
    start = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    s.tasks.append(start)
    s.backup_plan_solver()
    assert s.op_data.plan_condition == [False]
    original = [(id(task), task.time) for task in s.tasks]
    for _ in range(3):
        s.backup_plan_solver()
    assert [(id(task), task.time) for task in s.tasks] == original
    assert independent in s.tasks and start in s.tasks
    s.tasks.remove(start)
    s.backup_plan_solver()
    assert s.op_data.plan_condition == [True]
    assert independent in s.tasks


def test_projected_selection_refreshes_without_changing_live_snapshot(protected_solver):
    s = protected_solver
    s.train_room_state = RoomState("empty", protected=True)
    s._evaluate_backup_selection()
    projected = s.op_data.project_arrangements([])
    s.train_room_state = RoomState("empty")
    assert s._evaluate_backup_selection(projected).conditions == [True]
    assert not projected.facility_is_protected("train")
    assert s.op_data.facility_is_protected("train")


@pytest.mark.parametrize("protected", [False, True])
def test_shift_projection_uses_protection_condition(protected_solver, protected):
    s = protected_solver
    s.train_room_state = RoomState("empty", protected=protected)
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    positions = {
        name: (op.current_room, op.current_index)
        for name, op in s.op_data.operators.items()
    }
    s._prepare_shift_backup(task)
    if protected:
        assert not hasattr(task, "backup_shift_conditions")
    else:
        assert task.backup_shift_conditions == [True]
    assert s.op_data.plan_condition == [False]
    assert positions == {
        name: (op.current_room, op.current_index)
        for name, op in s.op_data.operators.items()
    }


def test_query_does_not_read_unstarted_or_failed_plan_list(
    protected_solver, monkeypatch
):
    monkeypatch.setattr(
        mastery_db,
        "get_reconcile_plans",
        lambda: [{"status": "failed"}, {"status": "idle"}],
    )
    assert protected_solver._evaluate_backup_selection().conditions == [True]
