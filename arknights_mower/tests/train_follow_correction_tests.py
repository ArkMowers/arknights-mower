"""专精接管训练位，协助位按跟随设置参与普通排班。"""

import sys
from datetime import datetime
from pathlib import Path
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
def test_protected_assistant_respects_follow_setting(solver, protected_by, follow):
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
    assert reconcile.called is (enabled and (state == "empty" or follow))
    if state != "empty" and enabled and not follow:
        solver.turn_on_room_detail.assert_not_called()
    else:
        solver.turn_on_room_detail.assert_called_once_with("train")
        if state != "empty":
            solver.refresh_current_room.assert_not_called()
            solver.choose_train.assert_called_once_with(
                ["褐果", "Current"], fast_mode=True, choose_error=0
            )
    assert not plan


@pytest.mark.parametrize("follow", [False, True])
def test_mastery_off_ignores_assistant_protection_during_execution(monkeypatch, follow):
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", follow)
    monkeypatch.setattr(BaseSchedulerSolver, "__init__", lambda _: None)
    plan = {"train": ["艾丽妮", "桃金娘"]}
    solver = base_scheduler_tests.TestTrainGateReadThenJudge._make_solver(plan)
    solver.op_data.get_current_room.return_value = ["逻各斯", "桃金娘"]
    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION, task_plan=plan)
    solver._can_refresh_idle_dorm_search = lambda: False
    solver.choose_train = MagicMock()
    solver.record_selection_success = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": "艾丽妮"}, {"agent": "桃金娘"}]
    )
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *args, **kw: mastery_reader.RoomState("empty", protected=True),
    )
    reconcile = MagicMock(side_effect=AssertionError("mastery disabled"))
    monkeypatch.setattr(mastery_reader, "reconcile_short", reconcile)

    solver.agent_arrange_room({}, "train", plan)

    solver.choose_train.assert_called_once_with(
        ["艾丽妮", "桃金娘"], fast_mode=True, choose_error=0
    )
    reconcile.assert_not_called()
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
    monkeypatch.setattr(
        config, "conf", config.Conf(enable_crafting=True, enable_mastery=False)
    )
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
        [{"agent": "褐果"}, {"agent": "桃金娘"}],
    ]

    solver.agent_arrange_room({}, "train", plan)

    assert solver.choose_train.call_count == 2
    solver.choose_train.assert_called_with(
        ["褐果", "桃金娘"], fast_mode=False, choose_error=1
    )
    assert solver.get_agent_from_room.call_count == 2
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
    solver.choose_train.assert_called_once()
    solver.record_selection_failure.assert_called_once()
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
@pytest.mark.parametrize("follow", [False, True])
def test_training_retry_skips_only_owned_positions(
    arrangement_solver, monkeypatch, state, follow
):
    solver, plan = arrangement_solver
    config.conf.enable_mastery = True
    config.conf.assistant_follows_schedule = follow
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

    assert targets == (["褐果", "Current"] if follow else ["Current", "Current"])
    assert solver.turn_on_room_detail.called is follow
    solver.choose_train.assert_not_called()
    solver.record_selection_failure.assert_not_called()
    assert plan == {}


@pytest.mark.parametrize("requested", ["桃金娘", "Free"])
@pytest.mark.parametrize(
    ("initial_order", "ascending"),
    [("等级", False), ("稀有度", False), ("信赖值", False), ("信赖值", True)],
)
def test_training_search_can_select_the_target_behind_profession_sidebar(
    arrangement_solver, monkeypatch, requested, initial_order, ascending
):
    from arknights_mower.solvers import base_mixin
    from arknights_mower.utils.image import loadimg

    solver, _ = arrangement_solver
    config.conf.performance_mode = "high"
    scope = ((584, 479), (759, 506))
    frame = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    source = (
        Path(__file__).parent
        / "fixtures/selection/training_ulpianus_first_20261009.jpg"
    )
    level_header = loadimg(str(source))[:95]
    frame[:95] = level_header
    if initial_order != "等级":
        # 平移截图中实际的排序箭头，模拟沿用另一列的状态。
        shift = 147 if initial_order == "稀有度" else 294
        arrow = level_header[63:81, 1260:1301]
        frame[63:81, 1260 + shift : 1301 + shift] = arrow[::-1] if ascending else arrow
        frame[63:81, 1260:1301] = level_header[63:81, 1320:1321]
    sidebar = {"open": True}
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.profession_filter = MagicMock()
    solver.swipe_left = MagicMock(return_value=0)
    solver.swipe_agent_page = MagicMock(
        side_effect=AgentSelectionNotReady("目标不可见")
    )
    solver.get_free_list = MagicMock(return_value=["桃金娘"])
    solver.ctap = MagicMock()
    pending_sort = False

    def refresh(*args):
        nonlocal pending_sort
        if pending_sort:
            frame[:95] = level_header
            pending_sort = False

    solver.sleep = MagicMock(side_effect=refresh)

    def find(resource, *args, **kwargs):
        if resource == "confirm_train":
            left = 1554 if sidebar["open"] else 1669
            return ((left, 997), (left + 182, 1054))
        return None

    def tap(position, *args, **kwargs):
        nonlocal pending_sort
        if position == (1860, 60):
            sidebar["open"] = False
        elif position == (1291, 60):
            assert solver.detect_arrange_order("train_trainee") == ("信赖值", ascending)
            pending_sort = True
        else:
            assert solver.detect_arrange_order("train_trainee")[0] in ("等级", "稀有度")
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
    assert solver.tap.call_count == 2 + int(initial_order == "信赖值")
    solver.tap.assert_any_call((1860, 60), interval=0.1)
    solver.tap.assert_any_call(scope, interval=0)
    solver.swipe_agent_page.assert_not_called()
    assert solver.last_room == "train"


@pytest.mark.parametrize(
    "scenario",
    [
        "visible",
        "second",
        "third",
        "early_end",
        "branch",
        "branch_next",
        "two_gestures",
        "stale_first",
        "rebound",
        "branch_end",
        "wrong_blue",
        "unknown_page",
        "verify_exit",
        "unreadable",
        "unsupported",
        "disabled",
        "retry",
        "page_exit",
    ],
)
def test_trainee_search_falls_back_to_the_whole_profession(
    arrangement_solver, monkeypatch, scenario
):
    from arknights_mower.solvers.base_mixin import (
        AgentCardObservationNotReady,
        AgentPageNotAdvanced,
        AgentSelectionPageChanged,
    )
    from arknights_mower.tests.selection_branch_tests import frame

    solver, _ = arrangement_solver
    solver.op_data.profession_filter = set() if scenario == "disabled" else {"余"}
    solver.recog.img = frame("tank_all_closed")
    solver.detect_arrange_order = MagicMock(return_value=("等级", False))
    solver.choose_error = set()
    solver.ctap = MagicMock()
    solver.verify_agent = MagicMock(return_value=True)
    if scenario in ("wrong_blue", "unknown_page"):
        solver.verify_agent.side_effect = [False, True]
    if scenario == "verify_exit":
        solver.verify_agent.side_effect = AgentSelectionPageChanged()
    solver.find = MagicMock(
        return_value=None if scenario == "unknown_page" else ((1669, 990), (1758, 1041))
    )
    solver.require_agent_selection_page = MagicMock()
    solver.swipe_left = MagicMock(return_value=0)
    opens = []
    state = {"branch": False, "sidebar": True, "page": 0, "gestures": 0}
    scans = []

    def profession(name):
        assert name in ("ALL", "TANK")
        state.update(branch=False, sidebar=True, page=0)

    def set_open(value):
        state["sidebar"] = value

    def narrow(instance, name, branch):
        assert instance is solver and state["sidebar"]
        assert (name, branch) == ("TANK", "本源铁卫")
        assert state["page"] == 2 and not opens
        opens.append(branch)
        state["branch"] = scenario != "unsupported"
        state["page"] = 0
        return state["branch"]

    def scan(names, *, max_agent_count, train, observation, respect_train_selection):
        assert not state["sidebar"] and names == ["余"]
        assert train and respect_train_selection and max_agent_count == 1
        scans.append((state["branch"], state["page"]))
        if state["page"] == 0 and scenario not in ("stale_first", "rebound"):
            assert observation is None
        if state["branch"]:
            if scenario == "unreadable":
                raise AgentCardObservationNotReady()
            if scenario == "page_exit":
                raise AgentSelectionPageChanged()
        if state["branch"]:
            visible = (
                scenario not in ("branch_end", "branch_next") or state["page"] == 1
            )
        else:
            wanted_page = {
                "visible": 0,
                "second": 1,
                "third": 2,
                "disabled": 3,
                "retry": 3,
            }
            visible = bool(opens) or state["page"] == wanted_page.get(scenario)
        return (names if visible else []), (
            (str(state["page"]), ((584, 479), (759, 506))),
        )

    def swipe(*args, **kwargs):
        if state["branch"] and scenario == "branch_end" or scenario == "early_end":
            raise AgentPageNotAdvanced()
        state["gestures"] += 1
        if scenario == "rebound" and state["gestures"] == 2:
            state["page"] = 0
        elif not (scenario == "stale_first" and state["gestures"] == 1):
            state["page"] += 1
        return (2 if scenario == "two_gestures" else 1), object()

    solver.profession_filter = MagicMock(side_effect=profession)
    solver._set_profession_filter_open = set_open
    solver._close_profession_filter = lambda: set_open(False)
    solver.scan_agent = scan
    solver.swipe_agent_page = MagicMock(side_effect=swipe)
    monkeypatch.setattr(base_schedule, "select_visible_branch", narrow)
    if scenario == "early_end":
        with pytest.raises(AgentPageNotAdvanced):
            solver.choose_train_ope("余")
        assert not opens and scans == [(False, 0)]
        return
    if scenario in ("page_exit", "verify_exit"):
        with pytest.raises(AgentSelectionPageChanged):
            solver.choose_train_ope("余")
        assert solver.profession_filter.call_count == 1
        assert solver.verify_agent.call_count == int(scenario == "verify_exit")
        solver.ctap.assert_not_called()
        return
    if scenario == "unknown_page":
        with pytest.raises(AgentSelectionNotReady, match="选人页尚未确认"):
            solver.choose_train_ope("余")
        assert solver.profession_filter.call_count == 1
        solver.ctap.assert_not_called()
        return
    solver.choose_train_ope("余", choose_error=int(scenario == "retry"))
    assert opens == (
        []
        if scenario in ("visible", "second", "third", "disabled", "retry")
        else ["本源铁卫"]
    )
    if scenario in ("branch_end", "unreadable"):
        assert scans == [(False, 0), (False, 1), (False, 2), (True, 0), (False, 0)]
        assert not solver.choose_error
    assert not state["sidebar"]
    if scenario == "wrong_blue":
        assert not state["branch"] and solver.verify_agent.call_count == 2
        assert solver.ctap.call_count == 2
    else:
        assert state["branch"] == (
            scenario
            in ("branch", "branch_next", "two_gestures", "stale_first", "rebound")
        )
        solver.ctap.assert_not_called()
        solver.verify_agent.assert_called_once_with(["余"], "train", train=True)
