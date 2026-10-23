"""拖动后只能点击重新识别的房间，不能按请求位移平移旧坐标。"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils import solver as solver_module  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.device import device as device_module  # noqa: E402
from arknights_mower.utils.device.device import Device  # noqa: E402
from arknights_mower.utils.image import loadres  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

ROOM = "room_1_1"
ROOM_TITLES = Path(__file__).parent / "fixtures" / "room_titles"


@pytest.mark.parametrize("phase", ["entry", "interference", "settled"])
def test_archive_recycling_title_confirms_actual_room(phase):
    title = cv2.cvtColor(
        cv2.imread(str(ROOM_TITLES / f"recycle_{phase}_20261011.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    assert solver.detect_room_type() == "回收站"
    assert solver.detect_room() == "recycle"


@pytest.mark.parametrize("phase", ["entry", "interference", "repeated", "settled"])
def test_archive_workshop_title_confirms_actual_room(phase):
    title = cv2.cvtColor(
        cv2.imread(str(ROOM_TITLES / f"factory_{phase}_20261013.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    assert solver.detect_room() == "factory"


@pytest.mark.parametrize(
    ("facility", "name", "room"),
    [
        ("manufacture", "制造站", "room_2_2"),
        ("trade", "贸易站", "room_1_1"),
        ("power", "发电站", "room_1_3"),
        ("train", "训练室", "train"),
    ],
)
@pytest.mark.parametrize("hue", [25, 99, 36, 178, 32])
def test_facility_title_controls_room_identity_and_type(facility, name, room, hue):
    title = cv2.cvtColor(
        cv2.imread(str(ROOM_TITLES / f"{facility}_20261013.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    frame[20:92, 570:642] = cv2.cvtColor(
        np.full((72, 72, 3), (hue, 230, 220), dtype=np.uint8), cv2.COLOR_HSV2RGB
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    assert solver.detect_room_type() == name
    assert solver.detect_room() == room


@pytest.mark.parametrize(
    "room", ["central", "meeting", "contact", "recycle", "factory", "train"]
)
def test_positive_facility_title_precedes_conflicting_training_color(room):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    title = loadres(f"room/{room}")
    height, width = title.shape[:2]
    frame[18 : 18 + height, 568 : 568 + width] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    solver._detect_room_type_by_color = MagicMock(return_value="训练室")
    assert solver.detect_room() == room
    solver._detect_room_type_by_color.assert_not_called()


@pytest.mark.parametrize(
    ("room", "name"),
    [
        ("central", "控制中枢"),
        ("dormitory", "宿舍"),
        ("meeting", "会客室"),
        ("contact", "办公室"),
        ("recycle", "回收站"),
        ("factory", "加工站"),
        ("train", "训练室"),
    ],
)
def test_known_facility_type_does_not_fall_back_to_manufacturing_color(room, name):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    title = loadres(f"room/{room}")
    height, width = title.shape[:2]
    frame[18 : 18 + height, 568 : 568 + width] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    solver._detect_room_type_by_color = MagicMock(return_value="制造站")
    assert solver.detect_room_type() == name
    solver._detect_room_type_by_color.assert_not_called()


@pytest.mark.parametrize(
    ("room", "filename"),
    [
        ("recycle", "recycle_interference_20261011.png"),
        ("factory", "factory_entry_20261013.png"),
        ("factory", "factory_interference_20261013.png"),
        ("factory", "factory_repeated_20261013.png"),
    ],
)
def test_confirmed_entry_animation_does_not_trigger_home_recovery(
    monkeypatch, room, filename
):
    monkeypatch.setattr(config, "stop_mower", Event())
    title = cv2.cvtColor(
        cv2.imread(str(ROOM_TITLES / filename)),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    solver.find = MagicMock(return_value=None)
    solver.back_to_index = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.sleep = MagicMock()
    solver.scene = MagicMock(return_value=None)
    solver.enter_room(room)
    solver.back_to_index.assert_not_called()
    solver.back_to_infrastructure.assert_not_called()
    solver.sleep.assert_not_called()


def test_workshop_title_does_not_confirm_numbered_manufacturing_room(monkeypatch):
    monkeypatch.setattr(config, "stop_mower", Event())
    title = cv2.cvtColor(
        cv2.imread(str(ROOM_TITLES / "factory_entry_20261013.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[18:95, 568:957] = title
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    solver.find = MagicMock(return_value=None)
    solver.back_to_index = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.scene = MagicMock(return_value=Scene.INFRA_DETAILS)
    with pytest.raises(RuntimeError, match="未成功进入房间 room_1_3"):
        solver.enter_room("room_1_3", max_attempts=1)
    solver.back_to_infrastructure.assert_called()
    solver.back_to_index.assert_not_called()


@pytest.mark.parametrize(
    ("hue", "facility"),
    [(25, "制造站"), (99, "贸易站"), (36, "发电站")],
)
def test_facility_type_uses_actual_header_icon(hue, facility):
    hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
    hsv[25:84, 580:626] = (hue, 230, 220)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))
    assert solver.detect_room_type() == facility


def test_facility_type_is_unknown_without_matching_header_icon():
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
    assert solver.detect_room_type() is None


@pytest.mark.parametrize(
    ("hue", "room"),
    [(25, "room_2_3"), (99, "room_2_3"), (36, "room_2_3"), (178, "train")],
)
def test_unmatched_title_retains_colored_facility_identity(hue, room):
    hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
    hsv[25:84, 580:626] = (hue, 230, 220)
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    frame[42:72, 779:800] = loadres("room/2")
    frame[42:72, 821:842] = loadres("room/3")
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame)
    assert solver.detect_room() == room


def test_room_name_uses_header_icon_instead_of_warm_room_background():
    hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # 加工站暖色背景与制造站图标色相相近；只有图标是加工站黄色。
    hsv[18:95, 640:957] = (25, 230, 220)
    hsv[25:84, 580:626] = (32, 230, 220)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))
    assert solver.detect_room() == "factory"


def test_room_icon_right_edge_is_inside_color_sample():
    hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # 图标彩色右缘超过旧的 x=636；旧取色范围只含一列，达不到门槛。
    hsv[25:85, 635:641] = (32, 230, 220)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB))
    assert solver.detect_room() == "factory"


def test_white_room_template_needs_positive_match():
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=img)
    assert solver.detect_room() == ""
    img[18:95, 568:742] = loadres("room/dormitory")
    img[42:72, 742:763] = loadres("room/4")
    assert solver.detect_room() == "dormitory_4"


def test_captcha_solver_waits_when_false_positive_scene_has_no_white_panel():
    solver = BaseSolver.__new__(BaseSolver)
    solver.recog = SimpleNamespace(gray=np.zeros((1080, 1920), dtype=np.uint8))
    assert solver.solve_captcha() is None


def rectangle(x1, y1, x2, y2):
    return np.array([[x1, y1], [x1, y2], [x2, y2], [x2, y1]])


def test_right_side_rooms_can_swap_without_moving_other_facilities():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    anchor = ((400, 80), (600, 240))
    ordinary = base_mixin.segment.base(image, anchor)
    swapped = base_mixin.segment.base(
        image, anchor, right_side_room_order=("train", "contact", "recycle")
    )

    np.testing.assert_array_equal(swapped["train"], ordinary["contact"])
    np.testing.assert_array_equal(swapped["contact"], ordinary["train"])
    assert swapped.keys() == ordinary.keys()
    for room in ordinary.keys() - {"train", "contact"}:
        np.testing.assert_array_equal(swapped[room], ordinary[room])


def adjustment_solver(monkeypatch, width=1920, height=1080):
    monkeypatch.setattr(config, "stop_mower", Event())
    solver = BaseMixin()
    solver.recog = SimpleNamespace(w=width, h=height, update=MagicMock())
    solver.device = SimpleNamespace(swipe_ext=MagicMock())
    solver.sleep = MagicMock(side_effect=lambda *_, **kwargs: solver.recog.update())
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
@pytest.mark.parametrize("size", [(1920, 1080), (800, 480), (120, 101)])
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
    assert points[1][1] - points[0][1] == 100
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
        (rectangle(-300, 10, -100, 30), (1920, 100)),
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
    started = datetime(2026, 10, 23)
    clock = SimpleNamespace(now=started)
    monkeypatch.setattr(
        base_mixin, "perf_counter", lambda: (clock.now - started).total_seconds()
    )

    def sleep(interval=1):
        clock.now += timedelta(seconds=interval)
        solver.recog.update()

    solver.sleep.side_effect = sleep

    def find(name):
        frame = solver.recog.img
        if name == "connecting":
            return frame["kind"] == "mask"
        if name == "control_central" and frame["kind"] == "map":
            return frame["anchor"]
        return None

    def segment(
        frame, anchor, *, right_side_room_order=("contact", "train", "recycle")
    ):
        assert frame["kind"] == "map" and anchor == frame["anchor"]
        return {ROOM: frame["room"]}

    segmentation = MagicMock(side_effect=segment)
    monkeypatch.setattr(base_mixin.segment, "base", segmentation)
    solver.find = MagicMock(side_effect=find)
    solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    solver.detect_room = MagicMock(
        side_effect=lambda: ROOM if solver.recog.img["kind"] == "room" else "other"
    )
    solver.tap = MagicMock(side_effect=lambda *_, **kwargs: solver.recog.update())
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


def test_enter_room_passes_configured_right_side_layout(monkeypatch):
    monkeypatch.setattr(
        config.conf, "right_side_room_order", ["recycle", "contact", "train"]
    )
    room = rectangle(450, 350, 750, 600)
    solver, segmentation = navigation_solver(
        monkeypatch, [map_frame(room), {"kind": "room"}]
    )
    solver.enter_room(ROOM)
    assert segmentation.call_args.kwargs == {
        "right_side_room_order": ["recycle", "contact", "train"]
    }


@pytest.mark.parametrize("unconfirmed", [None, "dormitory_1"])
@pytest.mark.parametrize("delayed_frames", [1, 20])
@pytest.mark.parametrize("entry_click", [1, 5])
def test_entry_waits_for_room_title_feedback_before_leaving(
    monkeypatch, unconfirmed, delayed_frames, entry_click
):
    map_frames = 2 * entry_click - 1
    solver, _ = navigation_solver(
        monkeypatch,
        [map_frame(rectangle(450, 350, 750, 600))] * map_frames
        + [{"kind": "entering"}] * delayed_frames
        + [{"kind": "room"}],
    )
    solver.detect_room.side_effect = lambda: (
        ROOM if solver.recog.img["kind"] == "room" else unconfirmed
    )
    solver.scene.side_effect = lambda: (
        Scene.INFRA_MAIN if solver.recog.img["kind"] == "map" else Scene.INFRA_DETAILS
    )

    solver.enter_room(ROOM, max_attempts=1)

    assert solver.tap.call_count == entry_click
    assert solver.sleep.call_args_list == (
        [((0.2,),)] * (entry_click - 1) + [((0.1,),)] * delayed_frames
    )
    assert solver.recog.captures == map_frames + delayed_frames + 1
    solver.back_to_infrastructure.assert_not_called()
    solver.back_to_index.assert_not_called()


@pytest.mark.parametrize("unconfirmed", [None, "dormitory_1"])
@pytest.mark.parametrize("entry_click", [1, 5])
def test_unconfirmed_entry_exhausts_time_budget_before_existing_recovery(
    monkeypatch, unconfirmed, entry_click
):
    map_frames = 2 * entry_click - 1
    waits = entry_click - 1 + 20
    expected_waits = [((0.2,),)] * (entry_click - 1) + [((0.1,),)] * 20
    solver, _ = navigation_solver(
        monkeypatch,
        [map_frame(rectangle(450, 350, 750, 600))] * map_frames
        + [{"kind": "entering"}],
    )
    solver.detect_room.return_value = unconfirmed
    solver.detect_room.side_effect = None
    solver.scene.side_effect = lambda: (
        Scene.INFRA_MAIN if solver.recog.img["kind"] == "map" else Scene.INFRA_DETAILS
    )

    def recover():
        assert solver.sleep.call_args_list == expected_waits

    solver.back_to_infrastructure.side_effect = recover
    with pytest.raises(RuntimeError, match="未成功进入房间"):
        solver.enter_room(ROOM, max_attempts=1)

    assert solver.tap.call_count == entry_click
    solver.back_to_infrastructure.assert_not_called()
    solver.back_to_index.assert_not_called()
    assert solver.sleep.call_count == waits
    assert solver.sleep.call_args_list == expected_waits
    assert solver.recog.captures == map_frames + 21


def test_stop_during_room_title_wait_propagates_without_navigation(monkeypatch):
    solver, _ = navigation_solver(
        monkeypatch,
        [map_frame(rectangle(450, 350, 750, 600)), {"kind": "entering"}],
    )
    solver.scene.side_effect = lambda: (
        Scene.INFRA_MAIN if solver.recog.img["kind"] == "map" else Scene.INFRA_DETAILS
    )
    solver.sleep.side_effect = MowerExit

    with pytest.raises(MowerExit):
        solver.enter_room(ROOM)

    solver.sleep.assert_called_once_with(0.1)
    solver.tap.assert_called_once()
    solver.back_to_infrastructure.assert_not_called()
    solver.back_to_index.assert_not_called()


@pytest.mark.parametrize(
    "screenshot_interval,last_frame", [(1200, 2), (2000, 2), (2500, 1)]
)
@pytest.mark.parametrize(
    "confirmed,room_scene",
    [(True, Scene.INFRA_DETAILS), (False, Scene.INFRA_DETAILS), (False, Scene.UNKNOWN)],
)
def test_room_entry_stops_at_first_frame_after_deadline_with_slow_capture(
    monkeypatch, screenshot_interval, last_frame, confirmed, room_scene
):
    started = datetime(2026, 10, 23)
    clock = SimpleNamespace(now=started)
    captured_at = []

    def advance(seconds):
        clock.now += timedelta(seconds=seconds)

    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    monkeypatch.setattr(config.conf, "screenshot_interval", screenshot_interval)
    monkeypatch.setattr(
        config,
        "screenshot_time",
        started - timedelta(milliseconds=screenshot_interval),
    )
    monkeypatch.setattr(config, "screenshot_avg", None)
    monkeypatch.setattr(config, "screenshot_count", 0)
    monkeypatch.setattr(
        device_module, "datetime", SimpleNamespace(now=lambda: clock.now)
    )
    monkeypatch.setattr(device_module, "time", SimpleNamespace(sleep=advance))
    monkeypatch.setattr(device_module, "save_screenshot_frame", lambda *_, **__: None)
    monkeypatch.setattr(solver_module, "csleep", advance)
    monkeypatch.setattr(
        base_mixin, "perf_counter", lambda: (clock.now - started).total_seconds()
    )

    def capture():
        frame = np.full((1080, 1920, 3), len(captured_at), dtype=np.uint8)
        captured_at.append(clock.now)
        return SimpleNamespace(unwrap=lambda: frame)

    device = object.__new__(Device)
    device.check_current_focus = MagicMock(return_value=False)
    device.session_control = SimpleNamespace(capture=capture)
    solver = BaseMixin()
    solver.recog = Recognizer(device)
    solver.sleep = BaseSolver.sleep.__get__(solver)
    solver.find = MagicMock(
        side_effect=lambda name: (
            ((10, 10), (30, 30))
            if name == "control_central" and solver.recog.img[0, 0, 0] == 0
            else None
        )
    )
    monkeypatch.setattr(
        base_mixin.segment,
        "base",
        lambda *_, **__: {ROOM: rectangle(450, 350, 750, 600)},
    )
    solver.tap = MagicMock(side_effect=lambda *_, **__: solver.sleep(0.2))
    solver.detect_room = MagicMock(
        side_effect=lambda: (
            ROOM if confirmed and solver.recog.img[0, 0, 0] == last_frame else ""
        )
    )
    solver.scene = MagicMock(
        side_effect=lambda: (
            Scene.INFRA_MAIN if solver.recog.img[0, 0, 0] == 0 else room_scene
        )
    )
    solver.back_to_infrastructure = MagicMock()
    solver.back_to_index = MagicMock()

    if confirmed:
        solver.enter_room(ROOM, max_attempts=1)
        solver.back_to_infrastructure.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match="未成功进入房间"):
            solver.enter_room(ROOM, max_attempts=1)
        if room_scene == Scene.INFRA_DETAILS:
            solver.back_to_infrastructure.assert_called()
        else:
            solver.back_to_infrastructure.assert_not_called()

    assert captured_at == [
        started + timedelta(milliseconds=screenshot_interval * frame)
        for frame in range(last_frame + 1)
    ]
    assert config.screenshot_count == last_frame + 1
    assert captured_at[-1] >= started + timedelta(seconds=2.2)
    assert captured_at[-2] < started + timedelta(seconds=2.2)
    solver.tap.assert_called_once()
    solver.back_to_index.assert_not_called()


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


def test_optional_room_check_does_not_repeat_home_relocation(monkeypatch):
    solver, segmentation = navigation_solver(
        monkeypatch, [map_frame(rectangle(100, -200, 400, -100))]
    )
    with pytest.raises(RuntimeError, match="未成功进入房间"):
        solver.enter_room(ROOM, max_attempts=1)
    assert segmentation.call_count == 5
    solver.back_to_index.assert_not_called()
    solver.back_to_infrastructure.assert_not_called()


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
