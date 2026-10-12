"""专精保护的训练位不成为绑组确认的永久重试目标。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, mastery_reader
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import base_scheduler_tests
from arknights_mower.tests.multi_group_shift_tests import A
from arknights_mower.tests.multi_group_shift_tests import solver as solver
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def training_group(solver, monkeypatch):
    plan = solver.global_plan["default_plan"].plan
    plan.pop("contact")
    plan["train"] = [Room("褐果", "甲", ["望"]), Room("桃金娘", "甲", ["余"])]
    assert solver.initialize_operators() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.time_stamp = datetime.now()
    del solver._suppress_train_correction
    config.conf.enable_mastery = True
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    return solver


@pytest.mark.parametrize("source", ["queue", "database", "observed"])
@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("other_confirmed", [False, True])
def test_protected_training_does_not_requeue_but_other_targets_still_confirm(
    training_group, monkeypatch, source, follow, other_confirmed
):
    s = training_group
    config.conf.assistant_follows_schedule = follow
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"], "train": ["望", "余"]},
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    # Protection can become known only when the task enters the training room.
    if source == "queue":
        s.tasks.append(SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE))
        s.find_next_task.side_effect = lambda **kw: next(
            (t for t in s.tasks if t.type == kw.get("task_type")), None
        )
    elif source == "database":
        monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"id": 1})
    else:
        s.train_room_state = mastery_reader.RoomState("training")
    observed = {}
    if other_confirmed:
        observed["meeting"] = ["陈", "Current"]
    if follow:
        observed["train"] = ["望", "Current"]
    projected = s.op_data.project_arrangements([observed])
    s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
    task.plan.clear()
    assert s._complete_group_shift(task) is other_confirmed
    assert s.op_data.group_is_resting("甲") is other_confirmed
    if not other_confirmed:
        assert task.plan == {"meeting": ["陈", "Current"]}
        assert ("train", 1) not in task.group_shift_expected
        if not follow:
            assert ("train", 0) not in task.group_shift_expected


def test_assistant_follow_still_requires_actual_assistant(training_group):
    s = training_group
    config.conf.assistant_follows_schedule = True
    s.train_room_state = mastery_reader.RoomState("training")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    task.plan.clear()
    assert not s._complete_group_shift(task)
    assert task.plan == {"train": ["望", "Current"]}
    assert not s.op_data.group_is_resting("甲")


def test_training_only_skipped_transition_does_not_commit_group(training_group):
    s = training_group
    config.conf.assistant_follows_schedule = False
    s.train_room_state = mastery_reader.RoomState("training")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert not s.op_data.group_is_resting("甲")
    assert s.op_data.operators[A].current_room == "meeting"


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("resting", [False, True])
def test_partial_group_targets_skip_protected_training_without_waiting(
    training_group, follow, resting
):
    s = training_group
    config.conf.assistant_follows_schedule = follow
    s.train_room_state = mastery_reader.RoomState("training")
    s.op_data.commit_group_shifts({"甲": not resting})
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF if resting else TaskTypes.SHIFT_ON,
        task_plan={"meeting": ["陈" if resting else A, "Current"]},
    )
    s.task, s.tasks = task, [task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert task.time == before
    assert ("train", 1) not in task.group_shift_expected
    assert (("train", 0) in task.group_shift_expected) is follow
    projected = s.op_data.project_arrangements([task.plan])
    projected.group_shift_state = dict(s.op_data.group_shift_state)
    s.op_data = projected
    task.plan.clear()
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("甲") is resting


def test_dispatch_finishes_group_after_live_training_gate_skips_room(
    training_group, monkeypatch
):
    s = training_group
    config.conf.assistant_follows_schedule = False
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"meeting": ["陈", "Current"], "train": ["望", "余"]},
    )
    s.task, s.tasks = task, [task]
    s.find = MagicMock(return_value=(1, 1))
    s.refresh_connecting = False
    s._prepare_shift_cycle = MagicMock()
    s._switch_products_before_arrangement = MagicMock()
    s.backup_plan_solver = MagicMock(return_value=False)
    s.skip = MagicMock()
    s.enter_room, s.back = MagicMock(), MagicMock()
    s.turn_on_room_detail = MagicMock(side_effect=AssertionError("protected room"))
    monkeypatch.setattr(
        base_schedule, "protect_priority_tasks", lambda tasks, **kwargs: None
    )
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("training"),
    )
    monkeypatch.setattr(mastery_reader, "reconcile_short", lambda *a, **kw: False)

    def arrange(plan, get_time):
        projected = s.op_data.project_arrangements([{"meeting": plan.pop("meeting")}])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
        s.agent_arrange_room({}, "train", plan)
        assert not plan

    s.agent_arrange = MagicMock(side_effect=arrange)
    s.infra_main()
    s.agent_arrange.assert_called_once()
    s.turn_on_room_detail.assert_not_called()
    assert task not in s.tasks
    assert s.op_data.group_is_resting("甲")
    assert not task.group_shift_expected
    assert s.op_data.get_current_room("train", True) == ["褐果", "桃金娘"]


@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("state", ["training", "waiting_collect", "unreadable"])
@pytest.mark.parametrize("other_confirmed", [False, True])
def test_mastery_off_confirms_assistant_without_requeueing_busy_trainee(
    training_group, monkeypatch, follow, state, other_confirmed
):
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    config.conf.enable_mastery = False
    config.conf.assistant_follows_schedule = follow
    plan = {"train": ["望", "余"], "meeting": ["陈", "Current"]}
    s = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    s.op_data = training_group.op_data
    s.find_next_task = MagicMock(return_value=None)
    s._resume_waiting_group_shifts = MagicMock()
    task = s.task
    s._prepare_group_shift(task, remember_targets=True)
    s.choose_train = MagicMock()

    def select(names, **kwargs):
        assert names == ["望", "Current"]
        projected = s.op_data.project_arrangements([{"train": names}])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm

    s.choose_train.side_effect = select
    s.get_agent_from_room = MagicMock(
        side_effect=lambda *a, **kw: [
            {"agent": name} for name in s.op_data.get_current_room("train", True)
        ]
    )
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: (
            None if state == "unreadable" else mastery_reader.RoomState(state)
        ),
    )
    reconcile = MagicMock(side_effect=AssertionError("mastery disabled"))
    monkeypatch.setattr(mastery_reader, "reconcile_short", reconcile)

    s.agent_arrange_room({}, "train", plan)
    s.choose_train.assert_called_once()
    assert s.op_data.get_current_room("train", True) == ["望", "桃金娘"]
    if other_confirmed:
        projected = s.op_data.project_arrangements([{"meeting": plan["meeting"]}])
        s.op_data.operators, s.op_data.dorm = projected.operators, projected.dorm
    plan.clear()

    assert s._complete_group_shift(task) is other_confirmed
    assert s.op_data.group_is_resting("甲") is other_confirmed
    assert ("train", 1) not in task.group_shift_expected
    if not other_confirmed:
        assert task.plan == {"meeting": ["陈", "Current"]}
    reconcile.assert_not_called()


def test_mastery_off_skipped_only_trainee_does_not_commit_group(
    training_group, monkeypatch
):
    s = training_group
    config.conf.enable_mastery = False
    config.conf.assistant_follows_schedule = False
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"train": ["Current", "余"]},
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task, remember_targets=True)
    s.enter_room, s.back = MagicMock(), MagicMock()
    s.turn_on_room_detail = MagicMock(side_effect=AssertionError("no named target"))
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("training"),
    )

    s.agent_arrange_room({}, "train", task.plan)

    assert not task.plan
    assert s._complete_group_shift(task)
    assert not s.op_data.group_is_resting("甲")
    assert s.op_data.get_current_room("train", True) == ["褐果", "桃金娘"]
