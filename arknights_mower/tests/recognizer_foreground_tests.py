"""普通识别截图先恢复游戏前台，外部画面和手势截图保持原有路径。"""

from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import config, recognize
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.recognize import Recognizer, Scene


@pytest.fixture
def observation(monkeypatch):
    monkeypatch.setattr(config, "stop_mower", Event())
    image = np.full((1080, 1920, 3), 37, dtype=np.uint8)
    frame = (b"fresh frame", image, image[:, :, 0])
    device = SimpleNamespace(
        check_current_focus=Mock(return_value=False),
        screencap=Mock(return_value=frame),
    )
    return Recognizer(device), device, frame


def test_each_new_observation_checks_focus_before_capture_and_reuses_cache(observation):
    recog, device, frame = observation
    calls = Mock()
    calls.attach_mock(device.check_current_focus, "focus")
    calls.attach_mock(device.screencap, "capture")
    previous_scene = Scene.INDEX
    previous_time = datetime.now() - timedelta(minutes=1)
    recog.last_scene = previous_scene
    recog.last_scene_time = previous_time
    recog.loading_time = 3

    assert recog.img is frame[1]
    assert recog.gray is frame[2]
    assert recog.screencap is frame[0]
    assert [call[0] for call in calls.mock_calls] == ["focus", "capture"]
    assert recog.last_scene == previous_scene
    assert recog.last_scene_time == previous_time
    assert recog.loading_time == 3

    recog.update()
    assert recog.img is frame[1]
    assert [call[0] for call in calls.mock_calls] == [
        "focus",
        "capture",
        "focus",
        "capture",
    ]


def test_recovery_discards_stale_observation_and_watchdog_before_capture(
    observation, monkeypatch
):
    recog, device, frame = observation

    class Clock(datetime):
        current = datetime(2026, 10, 18, 9, 0)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(recognize, "datetime", Clock)
    old_image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    recog.set_frame((b"old frame", old_image, old_image[:, :, 0]))
    recog.scene = Scene.INDEX
    recog._matcher = object()
    recog.capture_started_at = Clock.current - timedelta(minutes=10)
    recog.last_scene = Scene.INDEX
    recog.last_scene_time = Clock.current - timedelta(hours=1)
    recog.loading_time = 6

    def recover():
        Clock.current += timedelta(seconds=2)
        return True

    def capture():
        assert recog._screencap is None
        assert recog._img is None
        assert recog._gray is None
        assert recog._matcher is None
        assert recog.capture_started_at is None
        assert recog.scene == Scene.UNDEFINED
        assert recog.last_scene is None
        assert recog.last_scene_time == Clock.current
        assert recog.loading_time == 0
        Clock.current += timedelta(seconds=1)
        return frame

    device.check_current_focus.side_effect = recover
    device.screencap.side_effect = capture

    recog.start()

    device.check_current_focus.assert_called_once_with()
    device.screencap.assert_called_once_with()
    assert recog.img is frame[1]
    assert recog.gray is frame[2]
    assert recog.screencap is frame[0]
    assert recog.capture_started_at == datetime(2026, 10, 18, 9, 0, 2)
    assert recog.last_scene_time == datetime(2026, 10, 18, 9, 0, 2)


@pytest.mark.parametrize("recovered", [False, True])
def test_explicit_focus_check_reports_recovery_without_capturing(
    observation, recovered
):
    recog, device, frame = observation
    recog.set_frame(frame)
    previous_time = datetime.now() - timedelta(hours=1)
    previous_matcher = object()
    recog.scene = Scene.INDEX
    recog.last_scene = Scene.INDEX
    recog.last_scene_time = previous_time
    recog.loading_time = 6
    recog._matcher = previous_matcher
    device.check_current_focus.return_value = recovered

    assert recog.check_current_focus() is recovered

    device.screencap.assert_not_called()
    if recovered:
        assert recog._img is None
        assert recog._gray is None
        assert recog._screencap is None
        assert recog._matcher is None
        assert recog.scene == Scene.UNDEFINED
        assert recog.last_scene is None
        assert recog.last_scene_time > previous_time
        assert recog.loading_time == 0
    else:
        assert recog._img is frame[1]
        assert recog._gray is frame[2]
        assert recog._screencap is frame[0]
        assert recog._matcher is previous_matcher
        assert recog.scene == Scene.INDEX
        assert recog.last_scene == Scene.INDEX
        assert recog.last_scene_time == previous_time
        assert recog.loading_time == 6


def test_supplied_offline_image_never_checks_or_changes_device(observation):
    _, device, frame = observation
    ok, encoded = cv2.imencode(".png", frame[1])
    assert ok
    encoded = encoded.tobytes()

    recog = Recognizer(device, encoded)

    np.testing.assert_array_equal(recog.img, frame[1])
    np.testing.assert_array_equal(recog.gray, frame[2])
    assert recog.screencap == encoded
    assert recog.capture_started_at is None
    device.check_current_focus.assert_not_called()
    device.screencap.assert_not_called()


def test_held_frame_is_installed_without_focus_recovery_or_recapture(observation):
    recog, device, frame = observation
    device.check_current_focus.side_effect = AssertionError("unexpected recovery")

    recog.set_frame(frame)

    assert recog.img is frame[1]
    assert recog.gray is frame[2]
    assert recog.screencap is frame[0]
    device.check_current_focus.assert_not_called()
    device.screencap.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [DeviceRecoveryError("focus unavailable"), MowerExit(), RuntimeError("focus")],
)
def test_failed_focus_check_prevents_capture(observation, failure):
    recog, device, _ = observation
    device.check_current_focus.side_effect = failure

    with pytest.raises(type(failure)) as caught:
        _ = recog.img

    assert caught.value is failure
    device.check_current_focus.assert_called_once_with()
    device.screencap.assert_not_called()
    assert recog._img is None
    assert recog.capture_started_at is None
