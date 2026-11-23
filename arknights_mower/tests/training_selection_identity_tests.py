"""训练室选人与提交都核对当前岗位的确认按钮。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers.base_mixin import AgentSelectionNotReady
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask

FIXTURES = Path(__file__).parent / "fixtures/selection"


def selection_frame(layout):
    if layout == "popup":
        return bytes2img(
            (FIXTURES / "staffing_secondary_confirm_20261024.jpg").read_bytes()
        )
    # 原图分别记录协助位、训练位的职业栏展开与收起，保留完整的确认按钮。
    names = ("support_open", "support_closed", "trainee_open", "trainee_closed")
    strips = bytes2img(
        (FIXTURES / "training_slot_confirm_buttons_20261123.png").read_bytes()
    )
    frame = np.zeros((1080, 1920, 3), np.uint8)
    samples = np.split(strips, 4)
    strip = samples[names.index(layout) if layout in names else 3]
    if layout == "blurred":
        strip = cv2.GaussianBlur(strip, (31, 31), 8)
    if layout == "conflicting":
        # 合成按钮同时可见的冲突画面，两个按钮的像素均来自真实截图。
        strip = samples[1].copy()
        strip[:, :200] = samples[2][:, :200]
    frame[966:1070, 1500:] = strip
    return frame


@pytest.mark.parametrize(
    "index,layout,allowed",
    [
        (0, "support_open", True),
        (0, "support_closed", True),
        (1, "trainee_open", True),
        (1, "trainee_closed", True),
        (0, "trainee_closed", False),
        (1, "support_closed", False),
        (1, "blurred", False),
        (0, "conflicting", False),
        (0, "popup", False),
    ],
)
def test_training_room_requires_the_requested_slot_before_selection(
    index, layout, allowed
):
    solver = object.__new__(BaseSchedulerSolver)
    device = solver.device = MagicMock()
    device.check_current_focus.return_value = False
    image = selection_frame(layout)
    shot = (None, image, cv2.cvtColor(image, cv2.COLOR_RGB2GRAY))
    device.screencap.return_value = shot
    solver.recog = Recognizer(device)
    state = "room"
    desired = ["Current", "Current"]
    desired[index] = ("望", "余")[index]

    def find(resource, *args, **kwargs):
        if state != "selection":
            return True if resource == "room_detail" else None
        return solver.recog.find(resource, *args, **kwargs)

    def open_slot(position, **kwargs):
        nonlocal state
        assert state == "room"
        state = "selection"
        solver.recog.set_frame(shot)

    def submit(*args, **kwargs):
        nonlocal state
        assert allowed, "当前画面不能证实所请求的岗位，却提交了选人"
        state = "finished"

    def read(*args, **kwargs):
        return [
            {"agent": name if state == "finished" and slot == index else ""}
            for slot, name in enumerate(desired)
        ]

    solver.find = find
    solver.tap = open_slot
    solver.scene = lambda: (
        Scene.INFRA_ARRANGE_ORDER if state == "selection" else Scene.INFRA_DETAILS
    )
    solver.sleep = lambda *args: solver.recog.update()
    solver.get_agent_from_room = read
    solver.choose_agent = MagicMock()
    solver.choose_train_ope = MagicMock()
    solver.tap_confirm = MagicMock(side_effect=submit)
    if allowed:
        solver.choose_train(desired)
        assert (solver.choose_agent.call_count, solver.choose_train_ope.call_count) == (
            int(index == 0),
            int(index == 1),
        )
        solver.tap_confirm.assert_called_once_with("train", training_slot=index)
    else:
        with pytest.raises(AgentSelectionNotReady):
            solver.choose_train(desired)
        solver.choose_agent.assert_not_called()
        solver.choose_train_ope.assert_not_called()
        solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize(
    "index,initial,refreshed",
    [
        (0, "support_closed", "trainee_closed"),
        (1, "trainee_closed", "support_closed"),
        (1, "trainee_closed", "popup"),
    ],
)
def test_training_confirm_rechecks_the_role_on_the_new_frame(index, initial, refreshed):
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(run_order_rooms={})
    device = solver.device = MagicMock()
    device.check_current_focus.return_value = False
    solver.recog = Recognizer(device)
    before, after = selection_frame(initial), selection_frame(refreshed)
    solver.recog.set_frame((None, before, cv2.cvtColor(before, cv2.COLOR_RGB2GRAY)))
    device.screencap.return_value = (
        None,
        after,
        cv2.cvtColor(after, cv2.COLOR_RGB2GRAY),
    )
    solver.sleep = lambda *args: solver.recog.update()

    with pytest.raises(AgentSelectionNotReady):
        solver.tap_confirm("train", training_slot=index)

    assert device.screencap.call_count >= 1
    device.tap.assert_not_called()
