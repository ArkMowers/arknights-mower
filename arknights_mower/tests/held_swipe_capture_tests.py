"""按住终点时截图，验证三种输入后端的释放与单帧复用。"""

from contextlib import contextmanager, nullcontext
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device import device as device_module
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.maatouch.core import Client as MaaTouch
from arknights_mower.utils.device.mumu12ipc.input import MuMuInputSession
from arknights_mower.utils.device.scrcpy.core import Client as Scrcpy
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.solver import BaseSolver


@pytest.fixture
def gesture(monkeypatch):
    events = []
    clock = SimpleNamespace(now=0.0)
    stop = Event()
    monkeypatch.setattr(config, "stop_mower", stop)
    monkeypatch.setattr(config, "MNT_COMPATIBILITY_MODE", False)
    monkeypatch.setattr(device_module.time, "monotonic", lambda: clock.now)

    def wait(seconds):
        csleep(0)
        clock.now += seconds

    monkeypatch.setattr(device_module, "budget_sleep", wait)
    device = object.__new__(Device)
    device._prepare_touch = lambda points, durations, up_wait: SimpleNamespace(
        points=points, durations=durations, up_wait=up_wait, display_frames=None
    )
    device._input_once = lambda operation, prepare: operation(prepare())
    device.control = object.__new__(Device.Control)
    device.control.mumu12IPC = device.control.scrcpy = device.control.maatouch = None

    frame = (None, np.zeros((1080, 1920, 3), dtype=np.uint8), np.zeros((1080, 1920)))

    def capture(**kwargs):
        assert kwargs == {"recover": False}
        events.append(("capture", clock.now))
        return frame

    device.screencap = capture
    return device, events, clock, wait, stop, frame


def attach_helper(monkeypatch, device, backend, events, wait):
    if backend == "scrcpy":
        helper = object.__new__(Scrcpy)
        helper.control = SimpleNamespace(
            input_operation=nullcontext,
            touch=lambda x, y, action: events.append(
                ("up" if action == 1 else "move", x, y)
            ),
        )
        monkeypatch.setattr(
            "arknights_mower.utils.device.scrcpy.core.budget_sleep", wait
        )
        device.control.scrcpy = helper
    elif backend == "mumu_ipc":
        helper = object.__new__(MuMuInputSession)
        helper.touch_down = lambda x, y: events.append(("move", x, y))
        helper.touch_up = lambda: events.append(("up",))
        helper._wait = wait
        device.control.mumu12IPC = helper
    else:
        helper = object.__new__(MaaTouch)
        conn = SimpleNamespace(max_x=1920, max_y=1080)

        def send(content):
            events.extend(
                ("up" if line.startswith("u ") else "command", line)
                for line in content.splitlines()
            )

        conn.send, conn.wait = send, wait

        @contextmanager
        def operation():
            yield conn

        helper._operation = operation
        device.control.maatouch = helper


@pytest.mark.parametrize("backend", ["scrcpy", "mumu_ipc", "maatouch"])
@pytest.mark.parametrize("failure", [None, ValueError("capture failed"), MowerExit()])
def test_capture_precedes_release_on_all_backends(
    monkeypatch, gesture, backend, failure
):
    device, events, clock, wait, stop, frame = gesture
    attach_helper(monkeypatch, device, backend, events, wait)
    original = device.screencap

    def capture(**kwargs):
        result = original(**kwargs)
        if failure:
            if isinstance(failure, MowerExit):
                stop.set()
            raise failure
        return result

    device.screencap = capture
    if failure:
        with pytest.raises(type(failure)) as caught:
            device.swipe_ext([(900, 970), (800, 970)], [0], up_wait=400, capture=True)
        assert caught.value is failure
    else:
        assert (
            device.swipe_ext([(900, 970), (800, 970)], [0], up_wait=400, capture=True)
            is frame
        )
    kinds = [event[0] for event in events]
    assert kinds.count("capture") == kinds.count("up") == 1
    assert kinds.index("capture") < kinds.index("up")
    if failure is None:
        assert clock.now >= 0.4


def test_hold_includes_capture_duration_without_an_extra_full_wait(gesture):
    device, events, clock, wait, stop, frame = gesture

    def control(points, durations, up_wait, **kwargs):
        kwargs["before_release"]()
        events.append(("up", clock.now))

    def capture(**kwargs):
        events.append(("capture", clock.now))
        clock.now += 0.15
        return frame

    device.control.swipe_ext = control
    device.screencap = capture
    device.swipe_ext([(0, 0), (1, 0)], [0], up_wait=400, capture=True)
    assert events == [("capture", pytest.approx(0.1)), ("up", pytest.approx(0.4))]


def test_release_failure_takes_precedence_over_capture_failure(gesture):
    device, events, clock, wait, stop, frame = gesture

    def control(*args, **kwargs):
        kwargs["before_release"]()
        raise OSError("release unknown")

    device.control.swipe_ext = control
    device.screencap = MagicMock(side_effect=ValueError("capture failed"))
    with pytest.raises(OSError, match="release unknown"):
        device.swipe_ext([(0, 0), (1, 0)], [0], up_wait=400, capture=True)
    device.screencap.assert_called_once()


def test_release_budget_survives_task_cancellation_and_expired_input_budget(
    monkeypatch,
):
    from arknights_mower.utils.device.io_budget import touch_release_budget

    stop = Event()
    monkeypatch.setattr(config, "stop_mower", stop)
    with device_io_budget(lambda: 0):
        stop.set()
        with touch_release_budget():
            assert 0 < io_timeout(5) <= 1
        assert io_timeout(5) == 0


def test_raw_capture_never_invokes_session_recovery(monkeypatch):
    device = object.__new__(Device)
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    device.capture_frame = MagicMock(return_value=image)
    device.session_control = SimpleNamespace(
        capture_once=MagicMock(return_value=image), capture=MagicMock()
    )
    monkeypatch.setattr(config.conf, "screenshot_interval", 0)
    monkeypatch.setattr(device_module, "save_screenshot_frame", MagicMock())
    assert device.screencap(recover=False)[1] is image
    device.session_control.capture.assert_not_called()
    device.session_control.capture_once.assert_called_once()
    device.capture_frame.assert_not_called()


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_noinertia_installs_held_frame_and_uses_shared_hold(monkeypatch, mode):
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    frame = (None, np.zeros((1080, 1920, 3), dtype=np.uint8), np.zeros((1080, 1920)))
    solver = object.__new__(BaseSolver)
    solver.device = SimpleNamespace(swipe_ext=MagicMock(return_value=frame))
    solver.recog = Recognizer(solver.device)
    solver.sleep = MagicMock(side_effect=lambda interval: solver.recog.update())
    solver.swipe_noinertia((1490, 488), (-860, 0), capture=True)
    assert solver.recog.img is frame[1]
    assert solver.device.swipe_ext.call_args.kwargs == {
        "durations": [200, 172, 200],
        "up_wait": 400,
        "capture": True,
    }
    solver.recog.update()
    assert solver.recog._img is None


@pytest.mark.parametrize("mode", ["xhigh", "high"])
def test_fast_scan_uses_held_frame_without_recapturing(monkeypatch, mode):
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver = BaseMixin()
    solver.device = SimpleNamespace(
        screencap=MagicMock(side_effect=AssertionError("extra capture"))
    )
    solver.recog = Recognizer(solver.device)
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    scope = ((631, 488), (820, 520))
    solver.recog.set_frame((None, image, image[:, :, 0]))
    observed = solver.observe_agent_page(())
    solver.find = MagicMock(return_value=False)
    solver.tap = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())
    monkeypatch.setattr(
        base_mixin, "operator_list", lambda img, **kwargs: (("砾", scope),)
    )
    monkeypatch.setattr(
        base_mixin, "agent_card_selected", lambda *args, **kwargs: False
    )
    assert solver.scan_agent(["砾"], observation=observed)[0] == ["砾"]
    solver.device.screencap.assert_not_called()
    assert observed.image is None
    solver.tap.assert_called_once_with(scope, interval=0)


@pytest.mark.parametrize("cancel", [False, True])
def test_capture_error_releases_without_latching_an_input_failure(monkeypatch, cancel):
    from arknights_mower.tests.device_touch_tests import TouchTests

    fixture = TouchTests()
    fixture.setUp()
    try:
        device = fixture.control.start().unwrap()
        events = []

        def control(*args, **kwargs):
            kwargs["before_release"]()
            events.append("up")

        device.control.swipe_ext = control
        failure = MowerExit() if cancel else ValueError("capture failed")

        def capture(**kwargs):
            if cancel:
                config.stop_mower.set()
            raise failure

        monkeypatch.setattr(device, "screencap", capture)
        with pytest.raises(type(failure)):
            device.swipe_ext([(0, 0), (100, 0)], [0], up_wait=400, capture=True)
        assert events == ["up"]
        assert not getattr(device, "_recovery_error", None)
        assert fixture.factory.call_count == 1
        fixture.peer.assert_not_called()
    finally:
        config.stop_mower.clear()
        fixture.doCleanups()


def test_invalid_held_frame_produces_structured_capture_failure(monkeypatch):
    from arknights_mower.utils.device.screenshot_backend import ScreenshotFailure

    device = object.__new__(Device)
    device._profile = config.conf.device.model_copy()
    invalid = np.zeros((10, 10, 3), dtype=np.uint8)
    device.capture_frame = MagicMock()
    device.session_control = SimpleNamespace(
        capture_once=MagicMock(return_value=invalid), capture=MagicMock()
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "screenshot_interval", 0)
    with pytest.raises(ScreenshotFailure) as caught:
        device.screencap(recover=False)
    assert caught.value.code == "frame_size_mismatch"
    device.session_control.capture.assert_not_called()
    device.session_control.capture_once.assert_called_once()
    device.capture_frame.assert_not_called()


def test_slow_held_capture_extends_hold_and_still_releases(gesture):
    device, events, clock, wait, stop, frame = gesture

    def control(*args, **kwargs):
        kwargs["before_release"]()
        events.append(("up", clock.now))

    def capture(**kwargs):
        events.append(("capture", clock.now))
        clock.now += 0.6
        return frame

    device.control.swipe_ext = control
    device.screencap = capture
    device.swipe_ext([(0, 0), (100, 0)], [0], up_wait=400, capture=True)
    assert events == [("capture", pytest.approx(0.1)), ("up", pytest.approx(0.7))]


def test_failed_release_keeps_structured_unknown_input_without_replay(monkeypatch):
    from arknights_mower.tests.device_touch_tests import TouchTests

    fixture = TouchTests()
    fixture.setUp()
    try:
        device = fixture.control.start().unwrap()
        releases = []

        def control(*args, **kwargs):
            kwargs["before_release"]()
            releases.append("up")
            raise OSError("release unknown")

        device.control.swipe_ext = control
        monkeypatch.setattr(
            device, "screencap", MagicMock(side_effect=ValueError("capture failed"))
        )
        result = fixture.control.execute(
            lambda target: target.swipe_ext(
                [(0, 0), (100, 0)], [0], up_wait=400, capture=True
            )
        )
        assert result.error.code == "touch_result_unknown"
        assert result.error.cause.delivery_unknown
        assert releases == ["up"]
        assert fixture.factory.call_count == 1
        fixture.peer.assert_not_called()
    finally:
        fixture.doCleanups()
