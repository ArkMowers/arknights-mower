"""断线弹窗或无效滚动不能把房间读取困在固定像素 while 循环中。"""

import sys
from unittest.mock import Mock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", Mock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError  # noqa: E402


def solver():
    result = object.__new__(BaseSchedulerSolver)
    result.recog = Mock(w=1920, h=1080)
    result.find = Mock(side_effect=lambda name: name == "room_detail")
    result.get_color = Mock(return_value=(255, 255, 255))
    result.swipe = Mock()
    return result


@pytest.mark.parametrize("bottom", [False, True])
def test_unchanged_scroll_has_bounded_room_recovery(bottom):
    result = solver()
    with pytest.raises(RecognizeError, match="六次"):
        result.scroll_room_operators(bottom=bottom)
    assert result.swipe.call_count == 6


@pytest.mark.parametrize("dialog", ["confirm", "double_confirm/main"])
def test_popup_interrupts_scroll_before_another_gesture(dialog):
    result = solver()
    result.find.side_effect = lambda name: (
        name == "room_detail" or (result.swipe.call_count == 1 and name == dialog)
    )
    with pytest.raises(RecognizeError, match="确认弹窗"):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_called_once()


def test_left_room_is_not_read_as_scroll_boundary():
    result = solver()
    result.find.return_value = None
    result.find.side_effect = None
    result.get_color.return_value = (0, 0, 0)
    with pytest.raises(RecognizeError, match="离开房间"):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_not_called()


def test_last_gesture_result_is_checked_before_failure():
    result = solver()
    result.get_color.side_effect = [(255, 255, 255)] * 6 + [(0, 0, 0)]
    result.scroll_room_operators(bottom=True)
    assert result.swipe.call_count == 6


def test_already_at_boundary_does_not_swipe():
    result = solver()
    result.get_color.return_value = (0, 0, 0)
    result.scroll_room_operators(bottom=False)
    result.swipe.assert_not_called()


def test_user_stop_is_not_converted_to_recovery():
    result = solver()
    result.recog.update.side_effect = MowerExit
    with pytest.raises(MowerExit):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_not_called()


@pytest.mark.parametrize(
    "frame", ["room_empty_bottom_20261020.jpg", "room_empty_bottom_again_20261020.jpg"]
)
@pytest.mark.parametrize("starts_at_bottom", [False, True])
def test_recorded_empty_slots_stop_at_first_bottom_frame(frame, starts_at_bottom):
    from pathlib import Path

    import numpy as np
    from PIL import Image

    result = solver()
    image = np.array(Image.open(Path(__file__).parent / "fixtures/selection" / frame))
    top = np.array(
        Image.open(
            Path(__file__).parent / "fixtures/selection/room_empty_top_20261020.jpg"
        )
    )
    result.get_color.side_effect = lambda point: (
        image if starts_at_bottom or result.swipe.call_count else top
    )[point[1], point[0]]
    result.scroll_room_operators(bottom=True)
    assert result.swipe.call_count == (0 if starts_at_bottom else 1)
