"""Keep unconfirmed legacy handoffs and their collection continuation intact."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.solvers.mastery_reader import RoomPanel, RoomState
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def handoff(monkeypatch):
    end = datetime.now() + timedelta(minutes=270)
    panel = RoomPanel(
        operator_name="能天使",
        skill_name="过载模式",
        mastery_tier=1,
        countdown=end,
        countdown_state="active",
    )
    plan = {
        "id": 71,
        "char_id": "char_103_angel",
        "char_name": "能天使",
        "skill_index": 2,
        "skill_name": "过载模式",
        "target_level": 3,
        "status": "training",
        "swap_frozen": 0,
    }
    route = {
        "operator": "夜半",
        "swap_target": "逻各斯",
        "efficiency": 75,
        "job_match": True,
        "central_bonus": 0,
    }
    task = SchedulerTask(
        time=datetime.now() - timedelta(minutes=8), task_type=TaskTypes.SWAP_SUPPORT
    )
    task.plan_key = str(plan["id"])
    solver = SimpleNamespace(
        task=task,
        tasks=[task],
        enter_room=Mock(),
        train_scene=Mock(return_value=mastery.Scene.TRAIN_MAIN),
        choose_train=Mock(),
        back=Mock(),
        sleep=Mock(),
    )
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: plan)

    def save(_key, _status, **fields):
        plan.update(fields)
        return True

    monkeypatch.setattr(mastery_db, "update_plan_status", Mock(side_effect=save))
    monkeypatch.setattr(mastery, "read_main_panel", Mock(return_value=panel))
    monkeypatch.setattr(mastery, "_get_plan_route", Mock(return_value=route))
    monkeypatch.setattr(mastery, "_warn_training_room_group", Mock())
    monkeypatch.setattr(
        mastery,
        "_read_slots_checked",
        Mock(return_value=("夜半", "能天使", None, True)),
    )
    monkeypatch.setattr(
        mastery, "_read_train_countdown3", Mock(return_value=("active", end))
    )
    return SimpleNamespace(solver=solver, plan=plan, panel=panel, end=end)


@pytest.mark.parametrize(
    "failure", ["panel", "countdown", "tier", "scene", "slots", "route"]
)
def test_unconfirmed_handoff_keeps_original_work(handoff, failure):
    solver, panel = handoff.solver, handoff.panel
    task, due = solver.task, solver.task.time
    if failure == "panel":
        mastery.read_main_panel.return_value = None
    elif failure == "countdown":
        panel.countdown_state, panel.countdown = "failed", None
    elif failure == "tier":
        panel.mastery_tier = 0
    elif failure == "scene":
        solver.train_scene.return_value = mastery.Scene.TRAIN_SKILL_SELECT
    elif failure == "slots":
        mastery._read_slots_checked.return_value = ("", "", None, False)
    else:
        mastery._get_plan_route.return_value = None
    with pytest.raises(mastery.TrainingObservationError):
        mastery.run_swap_support(solver)
    assert solver.tasks == [task]
    assert task.time == due
    assert handoff.plan["swap_frozen"] == 0
    solver.choose_train.assert_not_called()


def test_successful_swap_retains_collection_then_resumes_without_another_swap(handoff):
    solver, task = handoff.solver, handoff.solver.task
    due = task.time
    mastery._read_train_countdown3.return_value = ("failed", None)
    with pytest.raises(mastery.TrainingObservationError):
        mastery.run_swap_support(solver)
    assert task.mastery_collect_pending is True
    assert handoff.plan["swap_frozen"] == 1
    assert solver.tasks == [task]
    assert task.time == due
    solver.choose_train.assert_called_once_with(["逻各斯", "Current"])

    mastery._read_slots_checked.side_effect = AssertionError(
        "collection cannot repeat staffing"
    )
    mastery._read_train_countdown3.return_value = ("active", handoff.end)
    mastery.run_swap_support(solver)
    solver.choose_train.assert_called_once()
    collect = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
    assert len(collect) == 1
    assert collect[0].plan_key == "71"
    assert collect[0].time == handoff.end
    assert task.time == due


def test_completed_swap_record_failure_does_not_repeat_the_arrangement(handoff):
    solver, task = handoff.solver, handoff.solver.task
    mastery_db.update_plan_status.side_effect = RuntimeError("database unavailable")
    with pytest.raises(mastery.TrainingObservationError):
        mastery.run_swap_support(solver)
    assert task.mastery_collect_pending is True
    assert solver.tasks == [task]
    mastery.run_swap_support(solver)
    solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
    assert len([t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]) == 1


@pytest.mark.parametrize("already_reducer", [False, True])
def test_collection_continuation_does_not_skip_new_stage_handoff(
    handoff, already_reducer
):
    solver, task = handoff.solver, handoff.solver.task
    due = task.time
    task.mastery_collect_pending = True
    task.mastery_collect_level = 1
    handoff.plan["swap_frozen"] = 1
    handoff.panel.mastery_tier = 2
    if already_reducer:
        mastery._read_slots_checked.return_value = ("逻各斯", "能天使", None, True)
    mastery.run_swap_support(solver)
    if already_reducer:
        solver.choose_train.assert_not_called()
    else:
        solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
    assert task.mastery_collect_pending is True
    assert task.mastery_collect_level == 2
    assert task.time == due
    mastery_db.update_plan_status.assert_any_call(71, "training", swap_frozen=0)
    collect = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
    assert len(collect) == 1
    assert "专一 → 专二" in collect[0].meta_data


def test_old_plan_task_cannot_swap_the_new_active_training(handoff):
    handoff.plan["id"] = 72
    mastery.run_swap_support(handoff.solver)
    handoff.solver.enter_room.assert_not_called()
    handoff.solver.choose_train.assert_not_called()
    mastery._read_slots_checked.assert_not_called()
    assert handoff.solver.tasks == [handoff.solver.task]


def test_skill_dispatch_retains_work_when_real_reconciliation_cannot_read_room(
    handoff, monkeypatch
):
    solver = handoff.solver
    solver.task.type = TaskTypes.SKILL_UPGRADE
    due = solver.task.time
    room = RoomState("training", RoomPanel(), read_failed=True)
    monkeypatch.setattr(mastery_reader, "read_room_state", lambda *_args, **_kw: room)
    monkeypatch.setattr(mastery_db, "get_plan_by_id", lambda _key: handoff.plan)
    monkeypatch.setattr(mastery_db, "get_reconcile_plans", lambda: [handoff.plan])
    monkeypatch.setattr(mastery_reader, "_restore_unconfirmed_swap", Mock())
    with pytest.raises(mastery.TrainingObservationError):
        mastery.run_mastery_task(solver)
    assert solver.task in solver.tasks
    assert solver.task.time == due
    assert handoff.plan["status"] == "training"
    solver.choose_train.assert_not_called()
    mastery_reader._restore_unconfirmed_swap.assert_called_once_with(
        solver, handoff.plan
    )


@pytest.mark.parametrize("finished", ["zero", "banner"])
def test_confirmed_completion_schedules_immediate_collection(handoff, finished):
    solver = handoff.solver
    if finished == "zero":
        handoff.panel.countdown_state, handoff.panel.countdown = "zero", None
    else:
        solver.train_scene.return_value = mastery.Scene.TRAIN_FINISH
    before = datetime.now()
    mastery.run_swap_support(solver)
    collect = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
    assert len(collect) == 1
    assert before <= collect[0].time <= datetime.now()
    solver.choose_train.assert_not_called()
    mastery._read_slots_checked.assert_not_called()


@pytest.mark.parametrize("finished", ["zero", "banner"])
def test_collection_continuation_handles_completion_without_timer(handoff, finished):
    solver = handoff.solver
    if finished == "zero":
        mastery._read_train_countdown3.return_value = ("zero", None)
    else:
        solver.train_scene.return_value = mastery.Scene.TRAIN_FINISH
    before = datetime.now()
    mastery._schedule_collect_after_swap(solver, handoff.plan, tier=1)
    collect = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
    assert len(collect) == 1
    assert before <= collect[0].time <= datetime.now()


@pytest.mark.parametrize("retained", ["execution_failure", "execution_retained"])
def test_reconciliation_does_not_retime_retained_swap(handoff, retained):
    solver, task = handoff.solver, handoff.solver.task
    solver.task = None
    setattr(
        task, retained, {"reason": "OCR"} if retained == "execution_failure" else True
    )
    due = task.time
    assert mastery._schedule_swap_if_needed(solver, handoff.plan, handoff.end, 1) == due
    assert solver.tasks == [task]
    assert task.time == due


def test_confirmed_empty_slot_rearms_a_countdown_dependent_successor(handoff):
    solver, original = handoff.solver, handoff.solver.task
    handoff.panel.countdown = datetime.now() + timedelta(minutes=500)
    mastery._read_slots_checked.return_value = ("", "能天使", None, True)
    mastery.run_swap_support(solver)
    solver.choose_train.assert_called_once_with(["夜半", "Current"])
    solver.tasks[:] = [task for task in solver.tasks if task is not original]
    assert len(solver.tasks) == 1
    assert solver.tasks[0].type == TaskTypes.SWAP_SUPPORT
    assert solver.tasks[0].plan_key == "71"
    assert solver.tasks[0].time > datetime.now()


@pytest.mark.parametrize("exception", [MowerExit, DeviceRecoveryError])
@pytest.mark.parametrize("source", ["panel", "slots", "arrange", "countdown"])
def test_cancellation_and_device_recovery_propagate(handoff, exception, source):
    solver = handoff.solver
    error = exception("interrupted")
    if source == "panel":
        mastery.read_main_panel.side_effect = error
    elif source == "slots":
        mastery._read_slots_checked.side_effect = error
    elif source == "arrange":
        solver.choose_train.side_effect = error
    else:
        mastery._read_train_countdown3.side_effect = error
    with pytest.raises(exception) as caught:
        mastery.run_swap_support(solver)
    assert caught.value is error
    assert solver.tasks == [solver.task]
