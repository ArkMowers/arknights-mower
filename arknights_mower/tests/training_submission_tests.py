"""进驻信息遮住提交提示时，等待游戏更新驻员后再读取训练室。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests import (  # noqa: E402
    scheduler_recovery_preservation_tests as recovery,
)
from arknights_mower.tests import (  # noqa: E402
    training_occupancy_read_tests as occupancy,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.image import loadres  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

FIXTURES = Path(__file__).parent / "fixtures" / "selection"
solver = occupancy.solver
training_reader = occupancy.training_reader
scheduler = recovery.scheduler


def test_exhausted_training_room_yields_until_a_new_observation(
    scheduler, training_reader, monkeypatch
):
    instance = scheduler.solver
    instance.op_data = training_reader.op_data
    now = scheduler.clock.now()
    task = SchedulerTask(now, {"train": ["Current", "余"]}, TaskTypes.SELF_CORRECTION)
    depot = SchedulerTask(now, task_type=TaskTypes.DEPOT)
    instance.task, instance.tasks = task, [task, depot]
    for method in (
        "back_to_infrastructure",
        "enter_room",
        "turn_on_room_detail",
        "refresh_current_room",
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "_fill_empty_dorms",
        "plan_metadata",
    ):
        setattr(instance, method, MagicMock())
    instance._complete_group_shift = MagicMock(return_value=True)
    instance.get_agent_from_room = MagicMock(
        return_value=[{"agent": "望"}, {"agent": ""}]
    )
    instance.choose_train = MagicMock(
        side_effect=base.AgentSelectionNotReady("训练位提交未确认")
    )
    instance.仓库扫描 = MagicMock()
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("empty"),
    )
    monkeypatch.setattr(base, "save_exception", MagicMock())

    instance.infra_main()

    assert instance.choose_train.call_count == 2
    assert task.execution_failure["rooms"] == ("train",)
    assert task.time == now and task.plan == {"train": ["Current", "余"]}
    for _ in range(3):
        instance._resume_failed_tasks()
        assert find_next_task(instance.tasks) is depot
    instance.run()
    instance.仓库扫描.assert_called_once()
    assert task in instance.tasks and depot not in instance.tasks
    assert find_next_task([task]) is None
    assert instance.choose_train.call_count == 2
    instance.op_data.room_observations["train"] += 1
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    assert task.time == now and task.plan == {"train": ["Current", "余"]}
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("settles_after", [1, 3, None])
def test_late_training_occupant_after_submission(training_reader, settles_after):
    instance = training_reader
    for method in ("train_scene", "detect_room", "find", "read_screen"):
        delattr(instance, method)
    transition, settled = (
        Recognizer(
            None,
            screencap=(
                FIXTURES / f"training_trainee_{stage}_20261123.jpg"
            ).read_bytes(),
        )
        for stage in ("transition", "settled")
    )
    selection = Recognizer(
        None, screencap=(FIXTURES / "training_selected_yu_20261123.jpg").read_bytes()
    )
    instance.recog = transition
    find = instance.find
    instance.find = lambda resource, *args, **kwargs: (
        instance.recog.get_train_scene() == Scene.INFRA_DETAILS
        if resource == "room_detail"
        else find(resource, *args, **kwargs)
    )
    page = Scene.INFRA_DETAILS
    instance.scene = lambda: page
    selections = []
    waits = []
    submitted_revision = None

    def open_slot(pos, **kwargs):
        nonlocal page
        assert pos == (1920 * 0.82, 1080 * 0.36)
        assert not selections, "训练位提交后再次进入选人页"
        instance.recog = selection
        page = Scene.INFRA_ARRANGE_ORDER

    def submit(room, *, training_slot):
        nonlocal page, submitted_revision
        assert room == "train" and training_slot == 1
        submitted_revision = instance.op_data.room_observations["train"]
        instance.recog = transition
        page = Scene.INFRA_DETAILS

    def next_frame(interval=1):
        assert instance.op_data.room_observations["train"] == submitted_revision
        waits.append(interval)
        if len(waits) == settles_after:
            instance.recog = settled
        assert len(waits) < 12

    instance.tap = instance.ctap = open_slot
    instance.choose_train_ope = selections.append
    instance.tap_confirm = submit
    instance.sleep = next_frame
    instance.selection_transition_timing = lambda: (0.75, 6)
    if settles_after is None:
        with pytest.raises(base.AgentSelectionNotReady, match="训练位.*未确认"):
            instance.choose_train(["望", "余"])
        assert instance.op_data.get_current_room("train", True) == ["望", ""]
    else:
        instance.choose_train(["望", "余"])
        assert len(waits) == settles_after
        assert instance.op_data.get_current_room("train", True) == ["望", "余"]
    assert selections == ["余"]


@pytest.mark.parametrize("input_feedback", ["delayed", "dropped", "absent"])
def test_training_slot_waits_for_its_own_input(monkeypatch, input_feedback):
    page = Scene.INFRA_DETAILS
    elapsed = 0
    taps = []
    occupants = ["望", ""]
    instance = MagicMock()
    instance.recog.w, instance.recog.h = 1920, 1080
    instance.scene.side_effect = lambda: page
    instance.get_agent_from_room.side_effect = lambda *args, **kwargs: [
        {"agent": name} for name in occupants
    ]
    monkeypatch.setattr(base, "monotonic", lambda: elapsed)

    def tap(pos):
        nonlocal page
        assert pos == (1920 * 0.82, 1080 * 0.36)
        taps.append(elapsed)
        if input_feedback == "dropped" and len(taps) == 2:
            page = Scene.INFRA_ARRANGE_ORDER

    def next_frame(interval=1):
        nonlocal elapsed, page
        elapsed += interval
        if input_feedback == "delayed" and elapsed >= 3:
            page = Scene.INFRA_ARRANGE_ORDER

    def confirm(room, *, training_slot):
        nonlocal page
        assert training_slot == 1
        occupants[1] = "余"
        page = Scene.INFRA_DETAILS

    instance.tap.side_effect = tap
    instance.sleep.side_effect = next_frame
    instance.tap_confirm.side_effect = confirm
    if input_feedback == "absent":
        with pytest.raises(base.AgentSelectionNotReady, match="未能打开"):
            BaseSchedulerSolver.choose_train(instance, ["Current", "余"])
        instance.choose_train_ope.assert_not_called()
    else:
        BaseSchedulerSolver.choose_train(instance, ["Current", "余"])
        instance.choose_train_ope.assert_called_once_with("余")
        assert occupants == ["望", "余"]
    assert taps == ([0] if input_feedback == "delayed" else [0, 10])


def captured_recognizer(submitting):
    filename = (
        "training_submission_20261010.jpg"
        if submitting
        else "training_submitted_20261010.jpg"
    )
    device = MagicMock()
    device.screencap.side_effect = AssertionError("离线重放不得请求设备截图")
    return Recognizer(device, screencap=(FIXTURES / filename).read_bytes())


def test_submission_behind_residence_panel_is_connecting():
    recog = captured_recognizer(True)
    assert recog.find("room_detail") is not None
    assert recog.get_scene() == Scene.CONNECTING
    recog.device.screencap.assert_not_called()


def test_submitted_training_room_remains_actionable():
    recog = captured_recognizer(False)
    assert recog.find("connecting") is None
    assert recog.get_scene() == Scene.INFRA_DETAILS


def test_training_readback_waits_for_submission_before_reselecting(monkeypatch):
    solver = object.__new__(BaseSchedulerSolver)
    solver.recog = captured_recognizer(True)
    pending = solver.recog
    pending_bytes = pending.screencap
    completed = captured_recognizer(False)
    pending.device.screencap.side_effect = None
    pending.device.screencap.return_value = (
        completed.screencap,
        completed.img,
        completed.gray,
    )
    waits = []
    monkeypatch.setattr("arknights_mower.utils.solver.csleep", waits.append)
    solver.tap = MagicMock(
        side_effect=AssertionError("提交过渡帧导致再次打开训练位选人")
    )
    reads = []

    def read_occupants(room, **kwargs):
        submitting = solver.recog.find("connecting") is not None
        # 原始提交截图仍显示黍；提交完成截图才显示桃金娘。
        name = "黍" if solver.recog.screencap == pending_bytes else "桃金娘"
        reads.append((submitting, name))
        return [{"agent": "褐果"}, {"agent": name}]

    solver.get_agent_from_room = MagicMock(side_effect=read_occupants)
    solver.choose_train_ope = MagicMock()
    solver.tap_confirm = MagicMock()

    solver.choose_train(["Current", "桃金娘"])

    assert reads == [(False, "桃金娘")]
    assert waits == [1]
    assert solver.recog is pending
    pending.device.screencap.assert_called_once_with()
    solver.tap.assert_not_called()
    solver.choose_train_ope.assert_not_called()
    solver.tap_confirm.assert_not_called()


def test_confirmation_waits_for_occluded_submission_without_reclicking(monkeypatch):
    monkeypatch.setattr(config.conf.waiting_scene, "CONNECTING", (1, 10))
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(run_order_rooms={})
    device = MagicMock()
    device.screencap.side_effect = AssertionError("离线重放不得请求设备截图")
    solver.recog = Recognizer(
        device,
        screencap=(FIXTURES / "training_tail_returned_20261010.jpg").read_bytes(),
    )
    # 重放的初始帧已安装；后续输入和等待分别安装真实提交帧与完成帧。
    solver.recog.update = MagicMock()

    def submit(*args, **kwargs):
        solver.recog = captured_recognizer(True)

    def finish(*args, **kwargs):
        solver.recog = captured_recognizer(False)

    solver.tap = MagicMock(side_effect=submit)
    solver.sleep = MagicMock(side_effect=finish)

    solver.tap_confirm("train")

    assert solver.tap.call_count == 1
    profile = solver.performance_profile
    solver.sleep.assert_called_once_with(
        max(profile.poll_interval, profile.screenshot_interval / 1000)
    )
    assert solver.recog.get_scene() == Scene.INFRA_DETAILS
    device.screencap.assert_not_called()


@pytest.mark.parametrize("with_panel", [False, True])
def test_complete_submission_prompt_preserves_existing_match(with_panel):
    recog = captured_recognizer(False)
    if not with_panel:
        recog._gray[0:110, 1231:1920] = 0
    prompt = loadres("connecting", True)
    h, w = prompt.shape
    recog._gray[978 : 978 + h, 1087 : 1087 + w] = prompt
    assert recog.find("connecting") == ((1087, 978), (1087 + w, 978 + h))


@pytest.mark.parametrize("missing", ["prompt", "panel"])
def test_partial_submission_requires_visible_text_and_residence_panel(missing):
    recog = captured_recognizer(True)
    if missing == "prompt":
        recog._gray[978:1015, 1087:1231] = 0
    else:
        recog._gray[0:110, 1231:1920] = 0
    assert recog.find("connecting") is None


def test_submission_text_outside_fixed_location_is_not_connecting():
    recog = captured_recognizer(False)
    prompt = loadres("connecting", True)
    h, w = prompt.shape
    recog._gray[900 : 900 + h, 1087 : 1087 + w] = prompt
    assert recog.find("connecting") is None


def test_training_room_without_prompt_does_not_use_feature_matcher():
    recog = captured_recognizer(False)
    recog._matcher = MagicMock()
    assert recog.find("connecting") is None
    recog._matcher.match.assert_not_called()


def test_unrelated_bright_footer_is_not_a_submission_prompt():
    recog = captured_recognizer(False)
    recog._gray[970:1020, 1080:1231] = np.full((50, 151), 220, dtype=np.uint8)
    assert recog.find("connecting") is None
