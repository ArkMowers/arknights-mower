"""协助位跟随排班与专精保护共存，开关关闭时保持原行为。"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests import base_scheduler_tests  # noqa: E402
from arknights_mower.utils import config, mastery_db  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    plan = Plan(
        {"train": [Room("褐果", "", []), Room("桃金娘", "", [])]},
        PlanConfig("", "", ""),
    )
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = Operators({"default_plan": plan, "backup_plans": []})
    for index, name in enumerate(("褐果", "桃金娘")):
        instance.op_data.operators[name] = Operator(
            name, "train", index=index, operator_type="high"
        )
    for index, name in enumerate(("夜莺", "号角")):
        instance.op_data.operators[name] = Operator(
            name,
            "",
            current_room="train",
            current_index=index,
            time_stamp=datetime.now(),
        )
    instance.tasks, instance.task = [], None
    instance._notify_train_correction_skipped = MagicMock()
    return instance


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("source", ["none", "database", "queue"])
def test_active_plan_correction_respects_follow_switch(
    solver, monkeypatch, enabled, follow, source
):
    config.conf.enable_mastery = enabled
    config.conf.assistant_follows_schedule = follow
    solver.train_room_state = mastery_reader.RoomState("empty")
    if source == "database":
        monkeypatch.setattr(
            mastery_db, "get_active_plan", lambda: {"id": 1, "status": "training"}
        )
    elif source == "queue":
        solver.tasks = [SchedulerTask(task_type=TaskTypes.SWAP_SUPPORT)]
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    if enabled and source != "none":
        assert plan == ({"train": ["褐果", "Current"]} if follow else {})
    else:
        assert plan == {"train": ["褐果", "桃金娘"]}
    solver._notify_train_correction_skipped.assert_not_called()


@pytest.mark.parametrize("state", ["training", "waiting_collect"])
@pytest.mark.parametrize("follow", [False, True])
def test_no_database_plan_uses_observed_training_state(solver, state, follow):
    config.conf.enable_mastery = True
    config.conf.assistant_follows_schedule = follow
    solver.train_room_state = mastery_reader.RoomState(state)
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan == ({"train": ["褐果", "Current"]} if follow else {})


@pytest.mark.parametrize("protected_by", ["occupant", "snapshot"])
@pytest.mark.parametrize("follow", [False, True])
def test_protected_assistant_can_follow_schedule(solver, protected_by, follow):
    config.conf.enable_mastery = True
    config.conf.assistant_follows_schedule = follow
    solver.train_room_state = mastery_reader.RoomState(
        "empty", protected=protected_by == "snapshot"
    )
    if protected_by == "occupant":
        solver.op_data.operators.pop("夜莺")
        solver.op_data.operators["逻各斯"] = Operator(
            "逻各斯", "", current_room="train", current_index=0
        )
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert plan == ({"train": ["褐果", "Current"]} if follow else {})
    assert solver._notify_train_correction_skipped.called is (not follow)


def test_only_trainee_mismatch_does_not_leave_empty_correction(solver, monkeypatch):
    config.conf.enable_mastery = config.conf.assistant_follows_schedule = True
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"id": 1})
    solver.op_data.operators["夜莺"].current_room = ""
    support = solver.op_data.operators["褐果"]
    support.current_room, support.current_index = "train", 0
    support.time_stamp = datetime.now()
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("follow", [False, True])
def test_mastery_off_ignores_stale_locked_snapshot(solver, enabled, follow):
    config.conf.enable_mastery = enabled
    config.conf.assistant_follows_schedule = follow
    solver.train_room_state = mastery_reader.RoomState("training")
    plan = solver.agent_get_mood(read_rooms=False, return_plan=True)
    if enabled:
        assert plan == ({"train": ["褐果", "Current"]} if follow else {})
    else:
        assert plan == {"train": ["褐果", "桃金娘"]}
        assert solver.train_room_state is None


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("follow", [False, True])
@pytest.mark.parametrize("state", ["training", "waiting_collect", "empty"])
def test_execution_keeps_live_trainee_and_off_does_not_run_mastery(
    monkeypatch, enabled, follow, state
):
    monkeypatch.setattr(config.conf, "enable_mastery", enabled)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", follow)
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    plan = {"train": ["褐果", "桃金娘"]}
    solver = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kw: mastery_reader.RoomState(state),
    )
    reconcile = MagicMock(return_value=False)
    monkeypatch.setattr(mastery_reader, "reconcile_short", reconcile)
    solver.agent_arrange_room({}, "train", plan)
    assert reconcile.called is enabled
    if state != "empty" and not follow:
        solver.turn_on_room_detail.assert_not_called()
    else:
        solver.turn_on_room_detail.assert_called_once_with("train")
        if state != "empty":
            solver.refresh_current_room.assert_called_once_with("train", [1])
    assert not plan


@pytest.mark.parametrize("train_size", [None, 0, 1])
@pytest.mark.parametrize("current_index", [0, 1])
@pytest.mark.parametrize("enabled", [False, True])
def test_correction_from_unscheduled_train_slot_keeps_configured_targets(
    solver, train_size, current_index, enabled
):
    config.conf.enable_mastery = enabled
    config.conf.assistant_follows_schedule = False
    data = solver.op_data
    data.plan = {"central": [Room("褐果", "", [])]}
    data.operators = {name: op for name, op in data.operators.items() if name == "褐果"}
    worker = data.operators["褐果"]
    worker.room, worker.index = "central", 0
    worker.current_room, worker.current_index = "train", current_index
    worker.time_stamp = datetime.now()
    if train_size is not None:
        data.plan["train"] = [Room("夜莺", "", [])] * train_size
        if train_size:
            data.operators["夜莺"] = Operator(
                "夜莺",
                "",
                current_room="train" if current_index == 1 else "",
                current_index=0,
            )
    original = {room: list(slots) for room, slots in data.plan.items()}
    result = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert result["central"] == ["褐果"]
    if train_size == 1 and current_index == 0:
        assert result["train"] == ["夜莺"]
    else:
        assert "train" not in result
    assert data.plan == original
