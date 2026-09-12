"""拖动后只能点击重新识别的房间，不能按请求位移平移旧坐标。"""

import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

ROOM = "room_1_1"


def rectangle(x1, y1, x2, y2):
    return np.array([[x1, y1], [x1, y2], [x2, y2], [x2, y1]])


def adjustment_solver(monkeypatch, width=1920, height=1080):
    monkeypatch.setattr(config, "stop_mower", Event())
    solver = BaseMixin()
    solver.recog = SimpleNamespace(w=width, h=height, update=MagicMock())
    solver.device = SimpleNamespace(swipe_ext=MagicMock())
    solver.sleep = MagicMock(side_effect=lambda *_: solver.recog.update())
    solver.swipe_noinertia = BaseSolver.swipe_noinertia.__get__(solver)
    return solver


@pytest.mark.parametrize(
    "source,expected",
    [
        (rectangle(100, 200, 400, 600), rectangle(100, 200, 400, 600)),
        (rectangle(-100, -200, 400, 600), rectangle(0, 0, 400, 600)),
        (rectangle(1800, 1000, 2300, 1300), rectangle(1800, 1000, 1919, 1079)),
        (rectangle(-100, -200, 2200, 1200), rectangle(0, 0, 1919, 1079)),
    ],
)
def test_visible_rectangle_is_clipped_copy_without_drag(monkeypatch, source, expected):
    solver = adjustment_solver(monkeypatch)
    original = source.copy()
    source.flags.writeable = False
    actual = solver.adjust_room(source)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(source, original)
    assert not np.shares_memory(actual, source)
    solver.device.swipe_ext.assert_not_called()
    solver.sleep.assert_not_called()


@pytest.mark.parametrize("side", [-1, 1])
@pytest.mark.parametrize("distance", [500, 100000])
@pytest.mark.parametrize("size", [(1920, 1080), (800, 480), (120, 41)])
def test_offscreen_room_drags_entire_path_inside_screen_without_predicted_click(
    monkeypatch, side, distance, size
):
    width, height = size
    solver = adjustment_solver(monkeypatch, width, height)
    x = -distance - 100 if side < 0 else width + distance
    source = rectangle(x, 10, x + 50, 30)
    original = source.copy()
    assert solver.adjust_room(source) is None
    np.testing.assert_array_equal(source, original)
    solver.device.swipe_ext.assert_called_once()
    points = solver.device.swipe_ext.call_args.args[0]
    assert all(0 <= x < width and 0 <= y < height for x, y in points)
    assert points[1][1] - points[0][1] == 40
    assert (points[-1][0] - points[0][0]) * side < 0
    solver.sleep.assert_called_once_with(0.5)
    solver.recog.update.assert_called_once()


@pytest.mark.parametrize(
    "source,size",
    [
        (rectangle(100, -200, 300, -100), (1920, 1080)),
        (rectangle(100, 1080, 300, 1200), (1920, 1080)),
        (rectangle(100, 300, 100, 500), (1920, 1080)),
        (rectangle(100, 300, 500, 300), (1920, 1080)),
        (rectangle(-300, 10, -100, 30), (1920, 40)),
        (rectangle(100, 20, 300, 40), (1, 1080)),
        (np.array([[np.nan, 10]] * 4), (1920, 1080)),
        (np.zeros((2, 2)), (1920, 1080)),
    ],
)
def test_unclickable_or_invalid_rectangle_waits_without_tapping_edges(
    monkeypatch, source, size
):
    solver = adjustment_solver(monkeypatch, *size)
    assert solver.adjust_room(source) is None
    solver.device.swipe_ext.assert_not_called()
    solver.sleep.assert_called_once_with(0.5)


class MapRecognizer:
    w, h = 1920, 1080

    def __init__(self, frames):
        self.frames = iter(frames)
        self.last = None
        self._img = None
        self.captures = 0

    def update(self):
        self._img = None

    @property
    def img(self):
        if self._img is None:
            self.last = next(self.frames, self.last)
            self._img = self.last
            self.captures += 1
        return self._img


def map_frame(room, anchor=((10, 10), (30, 30))):
    return {"kind": "map", "room": room, "anchor": anchor}


def navigation_solver(monkeypatch, frames):
    solver = adjustment_solver(monkeypatch)
    solver.recog = MapRecognizer(frames)

    def find(name):
        frame = solver.recog.img
        if name == "connecting":
            return frame["kind"] == "mask"
        if name == "control_central" and frame["kind"] == "map":
            return frame["anchor"]
        return None

    def segment(frame, anchor):
        assert frame["kind"] == "map" and anchor == frame["anchor"]
        return {ROOM: frame["room"]}

    segmentation = MagicMock(side_effect=segment)
    monkeypatch.setattr(base_mixin.segment, "base", segmentation)
    solver.find = MagicMock(side_effect=find)
    solver.detect_room = MagicMock(
        side_effect=lambda: ROOM if solver.recog.img["kind"] == "room" else "other"
    )
    solver.tap = MagicMock(side_effect=lambda *_: solver.recog.update())
    solver.back_to_index = MagicMock(side_effect=solver.recog.update)
    solver.back_to_infrastructure = MagicMock(side_effect=solver.recog.update)
    return solver, segmentation


@pytest.mark.parametrize("intermediate", [None, "old", "mask"])
def test_drag_relocates_using_new_frame_and_new_central_anchor(
    monkeypatch, intermediate
):
    old = rectangle(-800, 300, -600, 500)
    new = rectangle(450, 350, 750, 600)
    before = map_frame(old)
    frames = [before]
    if intermediate:
        frames.append(before if intermediate == "old" else {"kind": "mask"})
    frames.extend([map_frame(new, ((90, 60), (130, 90))), {"kind": "room"}])
    solver, segmentation = navigation_solver(monkeypatch, frames)
    solver.enter_room(ROOM)
    solver.tap.assert_called_once()
    np.testing.assert_array_equal(solver.tap.call_args.args[0], new)
    np.testing.assert_array_equal(old, rectangle(-800, 300, -600, 500))
    expected_drags = 2 if intermediate == "old" else 1
    assert solver.device.swipe_ext.call_count == expected_drags
    assert segmentation.call_count == expected_drags + 1
    assert solver.recog.captures == len(frames)
    solver.back_to_index.assert_not_called()
    solver.back_to_infrastructure.assert_not_called()


def test_ineffective_drags_use_existing_attempt_and_home_budgets(monkeypatch):
    solver, segmentation = navigation_solver(
        monkeypatch, [map_frame(rectangle(20000, 300, 20300, 600))]
    )
    with pytest.raises(RuntimeError, match="未成功进入房间 room_1_1"):
        solver.enter_room(ROOM)
    assert segmentation.call_count == 15
    assert solver.device.swipe_ext.call_count == 15
    assert solver.sleep.call_count == 15
    solver.tap.assert_not_called()
    assert solver.back_to_index.call_count == 2
    assert solver.back_to_infrastructure.call_count == 2


def test_invalid_map_rectangles_do_not_exceed_existing_budget(monkeypatch):
    solver, segmentation = navigation_solver(
        monkeypatch, [map_frame(rectangle(100, -200, 400, -100))]
    )
    with pytest.raises(RuntimeError, match="未成功进入房间 room_1_1"):
        solver.enter_room(ROOM)
    assert segmentation.call_count == 15
    assert solver.sleep.call_count == 15
    solver.tap.assert_not_called()
    solver.device.swipe_ext.assert_not_called()
    assert solver.back_to_index.call_count == 2
    assert solver.back_to_infrastructure.call_count == 2


@pytest.mark.parametrize("stop_before", [True, False])
def test_stop_during_map_adjustment_is_not_retried(monkeypatch, stop_before):
    solver, segmentation = navigation_solver(
        monkeypatch, [map_frame(rectangle(-800, 300, -600, 500))]
    )
    if stop_before:
        config.stop_mower.set()
    else:
        solver.device.swipe_ext.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.enter_room(ROOM)
    assert segmentation.call_count == 1
    assert solver.device.swipe_ext.call_count == (0 if stop_before else 1)
    solver.tap.assert_not_called()
    solver.back_to_index.assert_not_called()
    solver.back_to_infrastructure.assert_not_called()


@pytest.mark.parametrize(
    "source", [rectangle(-800, 300, -600, 500), rectangle(100, -200, 400, -100)]
)
def test_stop_during_post_adjustment_wait_does_not_continue_navigation(
    monkeypatch, source
):
    solver, segmentation = navigation_solver(monkeypatch, [map_frame(source)])
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.enter_room(ROOM)
    assert segmentation.call_count == 1
    solver.sleep.assert_called_once_with(0.5)
    solver.tap.assert_not_called()
    solver.back_to_index.assert_not_called()
    solver.back_to_infrastructure.assert_not_called()
