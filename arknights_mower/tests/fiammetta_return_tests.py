"""肥鸭充能与原班恢复完成后，保留整组回班及真实恢复限制。"""

import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import exhaust_replacement_tests
from arknights_mower.utils import config
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, plan_metadata

solver = exhaust_replacement_tests.solver
GroupShiftBlocked = exhaust_replacement_tests.base_schedule.GroupShiftBlocked


@pytest.fixture(params=[True, False], ids=["existing-return", "no-return-batch"])
def charged_return(solver, monkeypatch, offline_maintenance, request):
    monkeypatch.setattr(config.conf, "group_rest_in_full_on_mood_gap", False)
    solver.check_fia = lambda: (["絮雨"], "dormitory_1")
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.op_data.operators["苍苔"].resting_priority = "high"
    solver.op_data.operators["絮雨"].resting_priority = "low"
    original = SchedulerTask(
        time=solver.task.time + timedelta(hours=4),
        task_plan={"room_2_2": ["苍苔"], "contact": ["絮雨"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    solver.tasks = [original] if request.param else []
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock()
    solver.back = MagicMock()
    solver.plan_fia()
    charge = next(task for task in solver.tasks if task.type == TaskTypes.FIAMMETTA)
    solver.task = charge
    return solver, original, charge


def finish_restoration(solver, charge, monkeypatch, *, confirmed=True, additional=None):
    solver.task = charge
    charge.fia_charge_confirmed = confirmed
    charge.plan = {"dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "Free"]}
    monkeypatch.setattr(solver, "_emergency_frozen", lambda: False)
    monkeypatch.setattr(solver, "_suppress_facility_arrangement", lambda plan: None)
    monkeypatch.setattr(
        solver, "_prepare_group_shift_execution_targets", lambda task: None
    )
    monkeypatch.setattr(
        solver, "_defer_arrangement_for_priority_task", lambda room, plan: False
    )
    monkeypatch.setattr(solver, "_finish_idle_dorm_shift", lambda: None)
    monkeypatch.setattr(solver, "_track_idle_dorm_shift", lambda plan: None)
    monkeypatch.setattr(solver, "back_to_infrastructure", lambda: None)
    monkeypatch.setattr(solver, "skip", lambda *args: None)
    monkeypatch.setattr(
        "arknights_mower.solvers.base_schedule.defer_dorm_before_priority_task",
        lambda *args: False,
    )
    monkeypatch.setattr(
        "arknights_mower.solvers.mastery_support_runtime.central_training_occupants",
        lambda _: {},
    )
    monkeypatch.setattr(
        "arknights_mower.solvers.mastery_support_runtime.refresh_after_central_change",
        lambda *args: None,
    )

    def arrange(restoration, room, plan, **kwargs):
        plan.pop(room)
        return additional or restoration

    monkeypatch.setattr(solver, "agent_arrange_room", arrange)
    solver.agent_arrange(charge.plan)
    solver.tasks[:] = [task for task in solver.tasks if task is not charge]


def test_confirmed_fia_return_survives_metadata_rebuild(charged_return, monkeypatch):
    solver, original, charge = charged_return
    data = solver.op_data
    now = charge.time
    target = data.operators["絮雨"]
    target.mood, target.time_stamp = 24, now
    finish_restoration(solver, charge, monkeypatch)
    requested = next(
        task for task in solver.tasks if getattr(task, "fia_return_target", None)
    )
    assert requested.plan == {"room_2_2": ["苍苔"], "contact": ["絮雨"]}
    due = requested.time
    for _ in range(3):
        solver.tasks = plan_metadata(data, solver.tasks, now=now)
        assert any(task is requested for task in solver.tasks)
        assert requested.time == due
        assert (
            len([task for task in solver.tasks if task.type == TaskTypes.SHIFT_ON]) == 1
        )
    assert data.operators["苍苔"].current_room == "dormitory_1"
    assert data.operators["苍苔"].mood == 12
    assert all(task is not original for task in solver.tasks)


def test_unconfirmed_charge_does_not_force_group_return(charged_return, monkeypatch):
    solver, _, charge = charged_return
    finish_restoration(solver, charge, monkeypatch, confirmed=False)
    assert not any(getattr(task, "fia_return_target", None) for task in solver.tasks)


def test_return_requires_explicit_full_recovery(charged_return, monkeypatch):
    solver, _, charge = charged_return
    finish_restoration(solver, charge, monkeypatch)
    task = next(
        task for task in solver.tasks if getattr(task, "fia_return_target", None)
    )
    data = solver.op_data
    data.operators["苍苔"].rest_in_full = True
    original = task.time
    solver._prepare_fia_return(task)
    assert task.time == data.get_dorm_by_name("苍苔")[1].time
    data.operators["苍苔"].mood = 24
    solver._prepare_fia_return(task)
    assert task.time == original


def test_return_without_required_deadline_waits_for_observation(
    charged_return, monkeypatch
):
    solver, _, charge = charged_return
    finish_restoration(solver, charge, monkeypatch)
    task = next(
        task for task in solver.tasks if getattr(task, "fia_return_target", None)
    )
    data = solver.op_data
    data.operators["苍苔"].rest_in_full = True
    data.get_dorm_by_name("苍苔")[1].time = None
    original = task.time
    with pytest.raises(GroupShiftBlocked) as blocked:
        solver._prepare_fia_return(task)
    assert "苍苔" in blocked.value.recovery_names
    assert task.time == original
    data.operators["苍苔"].mood = 24
    solver._prepare_fia_return(task)
    assert task.time == original


def test_return_persists_request_and_remaining_targets(charged_return, monkeypatch):
    solver, _, charge = charged_return
    finish_restoration(solver, charge, monkeypatch)
    task = next(
        task for task in solver.tasks if getattr(task, "fia_return_target", None)
    )
    task.plan.pop("contact")
    restored = pickle.loads(pickle.dumps(task))
    assert restored.fia_return_target == "絮雨"
    assert restored.time == task.time
    assert restored.plan == {"room_2_2": ["苍苔"]}
    assert restored.retains_execution


def test_request_carries_through_restoration_and_is_not_queued_twice(
    charged_return, monkeypatch
):
    scheduler, _, charge = charged_return
    requested_time = charge.fia_return_time
    finish_restoration(
        scheduler,
        charge,
        monkeypatch,
        additional={"dormitory_1": ["冰酿", "闪灵", "苍苔", "絮雨", "Free"]},
    )
    restoring = next(
        task for task in scheduler.tasks if task.type == TaskTypes.FIAMMETTA
    )
    assert restoring.fia_return_target == "絮雨"
    assert restoring.fia_return_time == requested_time
    assert restoring.fia_charge_confirmed
    assert not any(
        getattr(task, "fia_return_target", None) and task.type == TaskTypes.SHIFT_ON
        for task in scheduler.tasks
    )
    finish_restoration(scheduler, restoring, monkeypatch)
    requested = next(
        task for task in scheduler.tasks if getattr(task, "fia_return_target", None)
    )
    for _ in range(3):
        scheduler._queue_fia_return()
    assert [
        task for task in scheduler.tasks if getattr(task, "fia_return_target", None)
    ] == [requested]


def test_started_return_keeps_remaining_work_despite_later_unknown_mood(
    charged_return, monkeypatch
):
    scheduler, _, charge = charged_return
    finish_restoration(scheduler, charge, monkeypatch)
    task = next(
        task for task in scheduler.tasks if getattr(task, "fia_return_target", None)
    )
    task.plan.pop("contact")
    task.mood_physical_started = True
    scheduler.op_data.operators["苍苔"].rest_in_full = True
    scheduler.op_data.get_dorm_by_name("苍苔")[1].time = None
    before = task.time
    scheduler._prepare_fia_return(task)
    assert task.time == before
    assert task.plan == {"room_2_2": ["苍苔"]}
