"""Unconfirmed training observations preserve the pending assistant handoff."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from arknights_mower.solvers import mastery_support_dispatch as dispatch
from arknights_mower.solvers import mastery_support_runtime as runtime
from arknights_mower.solvers import mastery_support_state as state
from arknights_mower.solvers import mastery_support_swap as swap
from arknights_mower.tests.mastery_support_fixtures import swap_case
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.mastery_support import SupportPlanError
from arknights_mower.utils.mastery_support_types import TrainingObservationError
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.mark.parametrize("read_error", [None, ValueError("OCR")])
@pytest.mark.parametrize("trainee,reliable", [("", False), ("其他学员", True)])
def test_slot_failure_preserves_handoff_without_freezing_or_collecting(
    read_error, trainee, reliable
):
    plan, panel, solver, _ = swap_case()
    with (
        patch.object(dispatch, "_matches_training", return_value=True),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("快教官", trainee, None, reliable),
            side_effect=read_error,
        ),
        patch.object(dispatch, "perform_swap") as perform,
        patch.object(state, "finish_support_swap") as finish,
        patch("arknights_mower.utils.mastery_db.update_plan_status") as update,
    ):
        with pytest.raises(TrainingObservationError):
            dispatch.run_planned_swap(solver, plan, panel)
    perform.assert_not_called()
    finish.assert_not_called()
    update.assert_not_called()


@pytest.mark.parametrize("failure", ["panel", "route", "candidates", "confirmation"])
def test_unconfirmed_execution_never_finishes_stage(failure):
    plan, panel, solver, options = swap_case()
    if failure == "panel":
        panel = None
    if failure == "route":
        plan["support_plan"]["stages"] = []
    with (
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch.object(
            swap,
            "candidates",
            return_value=(options, 0),
            side_effect=SupportPlanError("名单暂不可用")
            if failure == "candidates"
            else None,
        ),
        patch.object(swap, "schedule_context", return_value=({}, 0)),
        patch.object(
            swap,
            "confirm_training_panel",
            return_value=panel,
            side_effect=TrainingObservationError("倒计时未确认")
            if failure == "confirmation"
            else None,
        ),
        patch.object(swap, "finish_support_swap") as finish,
        patch.object(swap, "notify_support_failure") as notify,
    ):
        with pytest.raises(TrainingObservationError):
            swap.perform_swap(solver, plan, panel, "快教官")
    finish.assert_not_called()
    notify.assert_not_called()
    solver.choose_train.assert_not_called()


def test_unconfirmed_readback_preserves_work_after_actual_selection():
    plan, panel, solver, _ = swap_case()
    with (
        patch.object(swap, "schedule_context", return_value=({}, 0)),
        patch.object(swap, "confirm_training_panel", return_value=panel),
        patch.object(swap, "record_work") as record,
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            return_value=("", "", None, False),
        ),
    ):
        with pytest.raises(TrainingObservationError):
            swap.place_support(solver, plan, 2, "艾丽妮")
    solver.choose_train.assert_called_once_with(["艾丽妮", "Current"])
    record.assert_not_called()


def test_confirmed_target_after_interruption_records_observed_work_without_reselection():
    plan, panel, solver, _ = swap_case()
    with (
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch.object(swap, "record_work") as record,
        patch.object(swap, "refresh_end") as refresh,
        patch.object(swap, "candidates") as candidates,
        patch.object(swap, "finish_support_swap") as finish,
    ):
        swap.perform_swap(solver, plan, panel, "艾丽妮")
    record.assert_called_once_with(plan, 2, "艾丽妮", panel.countdown)
    refresh.assert_not_called()
    candidates.assert_not_called()
    solver.choose_train.assert_not_called()
    finish.assert_called_once_with(solver, plan, 2, False)


@pytest.mark.parametrize("retained", ["execution_failure", "execution_retained"])
def test_queue_refresh_preserves_retained_swap_identity_and_time(retained):
    task = SchedulerTask(
        time=datetime.now() - timedelta(hours=1), task_type=TaskTypes.SWAP_SUPPORT
    )
    task.plan_key = "1"
    setattr(
        task, retained, {"reason": "read"} if retained == "execution_failure" else True
    )
    original = task.time
    solver = SimpleNamespace(tasks=[task], task=None)
    returned = state.enqueue_support_swap(solver, {"id": 1}, datetime.now(), "艾丽妮")
    assert returned is task
    assert solver.tasks == [task]
    assert task.time == original
    assert getattr(task, retained)


@pytest.mark.parametrize("saved_work", [False, True])
@pytest.mark.parametrize("read_error", [None, ValueError("OCR")])
def test_recovery_preserves_swap_intent_despite_failed_resident_read(
    saved_work, read_error
):
    plan, panel, _, _ = swap_case()
    if saved_work:
        route = dict(plan["support_plan"]["stages"][0])
        plan["support_runtime"] = route
    else:
        del plan["support_plan"]["stages"][0]["working_operator"]
    solver = SimpleNamespace(tasks=[], task=None)
    with patch(
        "arknights_mower.solvers.mastery_reader._read_slots_checked",
        return_value=("", "", None, False),
        side_effect=read_error,
    ):
        assert runtime.recover(solver, plan, SimpleNamespace(panel=panel))
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SWAP_SUPPORT
    assert solver.tasks[0].plan_key == "1"
    assert "working_since" not in plan.get("support_runtime", {})


@pytest.mark.parametrize("retained", ["execution_failure", "execution_retained"])
def test_recovery_preserves_existing_retained_swap_without_duplicate(retained):
    plan, panel, _, _ = swap_case()
    task = SchedulerTask(
        time=datetime.now() - timedelta(hours=1), task_type=TaskTypes.SWAP_SUPPORT
    )
    task.plan_key = "1"
    setattr(
        task, retained, {"reason": "read"} if retained == "execution_failure" else True
    )
    original = task.time
    solver = SimpleNamespace(tasks=[task], task=None)
    with patch("arknights_mower.solvers.mastery_reader._read_slots_checked") as read:
        assert runtime.recover(solver, plan, SimpleNamespace(panel=panel))
    read.assert_not_called()
    assert solver.tasks == [task]
    assert task.time == original


@pytest.mark.parametrize("boundary", ["dispatch", "execution", "recovery"])
@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("device")])
def test_stop_and_device_failures_propagate_from_support_boundaries(boundary, error):
    plan, panel, solver, _ = swap_case()
    solver.tasks = []
    with (
        patch(
            "arknights_mower.solvers.mastery_reader._plan_matches_room",
            return_value=True,
        ),
        patch(
            "arknights_mower.solvers.mastery_reader._read_slots_checked",
            side_effect=error,
        ),
        patch.object(swap, "candidates", side_effect=error),
        patch.object(state, "finish_support_swap") as finish,
    ):
        with pytest.raises(type(error)) as raised:
            if boundary == "dispatch":
                dispatch.run_planned_swap(solver, plan, panel)
            elif boundary == "execution":
                swap.perform_swap(solver, plan, panel, "快教官")
            else:
                runtime.recover(solver, plan, SimpleNamespace(panel=panel))
    assert raised.value is error
    finish.assert_not_called()
