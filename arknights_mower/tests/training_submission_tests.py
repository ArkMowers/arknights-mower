"""进驻信息遮住提交提示时，等待游戏更新驻员后再读取训练室。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.image import loadres  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


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
    solver.ctap = MagicMock(
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
    solver.ctap.assert_not_called()
    solver.choose_train_ope.assert_not_called()
    solver.tap_confirm.assert_not_called()


def test_confirmation_waits_for_occluded_submission_without_reclicking():
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
    solver.sleep.assert_called_once_with()
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
