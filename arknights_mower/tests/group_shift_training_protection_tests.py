"""专精保护的训练位不成为绑组确认的永久重试目标。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule, mastery_reader
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
