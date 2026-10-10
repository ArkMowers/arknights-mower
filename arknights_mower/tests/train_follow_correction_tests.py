"""协助位跟随排班与专精保护共存，开关关闭时保持原行为。"""

import sys
from datetime import datetime
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, mastery_reader  # noqa: E402
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests import base_scheduler_tests  # noqa: E402
from arknights_mower.utils import config, mastery_db  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
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
    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
    solver._can_refresh_idle_dorm_search = lambda: False
    solver.choose_train = MagicMock()
    solver.record_selection_success = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": "褐果"}, {"agent": "桃金娘"}]
    )
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
            solver.refresh_current_room.assert_not_called()
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


def test_train_current_reaches_live_reader_without_stale_cache_substitution(
    monkeypatch,
):
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    plan = {"train": ["Current", "桃金娘"]}
    solver = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
    solver._can_refresh_idle_dorm_search = lambda: False
    solver._emergency_active = lambda: False
    solver.op_data.get_current_room.return_value = ["褐果", "余"]
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("empty"),
    )
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": "望"}, {"agent": "桃金娘"}]
    )
    solver.choose_train = MagicMock()
    solver.record_selection_success = MagicMock()
    solver.agent_arrange_room({}, "train", plan)
    solver.choose_train.assert_called_once_with(
        ["Current", "桃金娘"], fast_mode=True, choose_error=0
    )
    solver.refresh_current_room.assert_not_called()
    assert plan == {}


@pytest.fixture
def arrangement_solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kwargs: mastery_reader.RoomState("empty"),
    )
    monkeypatch.setattr(
        mastery_reader, "reconcile_short", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(base_schedule, "save_exception", lambda *_: None)
    plan = {"train": ["褐果", "桃金娘"]}
    solver = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    solver.scene.return_value = Scene.INFRA_MAIN
    solver._emergency_active = lambda: False
    solver.record_selection_failure = MagicMock()
    solver.op_data.get_current_room.return_value = ["褐果", "黍"]
    return solver, plan


def test_failed_training_selection_retries_the_named_trainee(arrangement_solver):
    solver, plan = arrangement_solver
    solver.choose_train.side_effect = [AgentSelectionNotReady("选人失败"), None]
    solver.get_agent_from_room.side_effect = [
        [{"agent": "褐果"}, {"agent": "黍"}],
        [{"agent": "褐果"}, {"agent": "黍"}],
        [{"agent": "褐果"}, {"agent": "桃金娘"}],
    ]

    solver.agent_arrange_room({}, "train", plan)

    assert solver.choose_train.call_count == 2
    solver.choose_train.assert_called_with(
        ["褐果", "桃金娘"], fast_mode=False, choose_error=1
    )
    assert solver.get_agent_from_room.call_count == 3
    solver.record_selection_failure.assert_called_once()
    solver.record_selection_success.assert_called_once()
    assert plan == {}


def test_training_readback_mismatch_is_not_reported_as_success(arrangement_solver):
    solver, plan = arrangement_solver
    solver.get_agent_from_room.side_effect = [
        [{"agent": "褐果"}, {"agent": "黍"}],
        [{"agent": "褐果"}, {"agent": "桃金娘"}],
    ]

    solver.agent_arrange_room({}, "train", plan)

    solver.choose_train.assert_called_once_with(
        ["褐果", "桃金娘"], fast_mode=True, choose_error=0
    )
    assert solver.get_agent_from_room.call_count == 2
    solver.record_selection_failure.assert_called_once()
    solver.record_selection_success.assert_called_once()
    assert plan == {}


@pytest.mark.parametrize("actual", [["余", "桃金娘"], ["褐果", "黍"]])
def test_unfinished_training_arrangement_keeps_bounded_retry(
    arrangement_solver, actual
):
    solver, plan = arrangement_solver
    solver.task.arrangement_retry_room = "train"
    solver.task.arrangement_retry_count = 1
    solver.get_agent_from_room.return_value = [{"agent": name} for name in actual]

    with pytest.raises(Exception, match="检测到安排干员未成功"):
        solver.agent_arrange_room({}, "train", plan)

    assert plan == {"train": ["褐果", "桃金娘"]}
    assert solver.choose_train.call_count == 3
    assert solver.record_selection_failure.call_count == 3
    solver.record_selection_success.assert_not_called()


@pytest.mark.parametrize("target", ["桃金娘", "Current", "Free"])
def test_training_retry_accepts_observed_targets_and_placeholders(
    arrangement_solver, target
):
    solver, plan = arrangement_solver
    plan["train"][1] = target
    solver.task.arrangement_retry_room = "train"
    solver.task.arrangement_retry_count = 1
    solver.get_agent_from_room.return_value = [
        {"agent": "褐果"},
        {"agent": "桃金娘" if target == "桃金娘" else "黍"},
    ]

    solver.agent_arrange_room({}, "train", plan)

    solver.choose_train.assert_not_called()
    solver.record_selection_failure.assert_not_called()
    solver.record_selection_success.assert_called_once()
    assert not hasattr(solver.task, "arrangement_retry_room")
    assert plan == {}


@pytest.mark.parametrize(
    "state", ["training", "waiting_collect", "protected", "unknown"]
)
def test_training_retry_keeps_protected_current_trainee(
    arrangement_solver, monkeypatch, state
):
    solver, plan = arrangement_solver
    config.conf.enable_mastery = config.conf.assistant_follows_schedule = True
    room_state = (
        None
        if state == "unknown"
        else mastery_reader.RoomState(
            "empty" if state == "protected" else state, protected=state == "protected"
        )
    )
    monkeypatch.setattr(mastery_reader, "read_room_state", lambda *a, **kw: room_state)
    solver.task.arrangement_retry_room = "train"
    solver.task.arrangement_retry_count = 1
    solver.get_agent_from_room.return_value = [{"agent": "褐果"}, {"agent": "黍"}]
    targets = plan["train"]

    solver.agent_arrange_room({}, "train", plan)

    assert targets == ["褐果", "Current"]
    solver.choose_train.assert_not_called()
    solver.record_selection_failure.assert_not_called()
    assert plan == {}


@pytest.mark.parametrize("requested", ["桃金娘", "Free"])
def test_training_search_can_select_the_target_behind_profession_sidebar(
    arrangement_solver, monkeypatch, requested
):
    from arknights_mower.solvers import base_mixin

    solver, _ = arrangement_solver
    config.conf.performance_mode = "high"
    scope = ((584, 479), (759, 506))
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    sidebar = {"open": True}
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.profession_filter = MagicMock()
    solver.swipe_left = MagicMock(return_value=0)
    solver.swipe_agent_page = MagicMock(
        side_effect=AgentSelectionNotReady("目标不可见")
    )
    solver.get_free_list = MagicMock(return_value=["桃金娘"])
    solver.ctap = MagicMock()
    solver.sleep = MagicMock()

    def find(resource, *args, **kwargs):
        if resource == "confirm_train":
            left = 1554 if sidebar["open"] else 1669
            return ((left, 997), (left + 182, 1054))
        return None

    def tap(position, *args, **kwargs):
        if position == (1860, 60):
            sidebar["open"] = False
        else:
            assert not sidebar["open"] and position == scope
            cv2.rectangle(frame, (565, 113), (766, 522), (0, 180, 230), 7)

    solver.find = MagicMock(side_effect=find)
    solver.tap = MagicMock(side_effect=tap)
    monkeypatch.setattr(
        base_mixin,
        "operator_list_train",
        lambda _: (("黍" if sidebar["open"] else "桃金娘", scope),),
    )

    solver.choose_train_ope(requested)

    assert not sidebar["open"]
    assert solver.tap.call_count == 2
    solver.tap.assert_any_call((1860, 60), interval=0.1)
    solver.tap.assert_any_call(scope, interval=0)
    solver.swipe_agent_page.assert_not_called()
    assert solver.last_room == "train"
