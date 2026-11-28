from threading import Event
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from arknights_mower.solvers import mastery_reader as reader
from arknights_mower.utils import config, recognize
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.screenshot import ScreenshotStore
from arknights_mower.utils.screenshot_cleanup import ScreenshotCleanup


@pytest.mark.parametrize("planned", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("button_at", [1, 3, 8, None])
def test_collection_saves_only_waiting_button_and_result(
    monkeypatch, planned, enabled, button_at
):
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "save_mastery_screenshots", enabled)
    captures = []
    saved = []

    def capture():
        image = np.full((2, 2, 3), len(captures), dtype=np.uint8)
        captures.append(image)
        return None, image, image[:, :, 0]

    device = Mock()
    device.check_current_focus.return_value = False
    device.screencap.side_effect = capture
    recog = Recognizer(device)
    solver = MagicMock()
    solver.recog = recog
    attempts = 0
    waiting = []
    button = ((10, 10), (20, 20))

    def find(resource):
        nonlocal attempts
        image = recog.img
        if resource == "training_completed":
            return button
        attempts += 1
        waiting.append(int(image[0, 0, 0]))
        return button if button_at is not None and attempts >= button_at else None

    solver.find.side_effect = find
    solver.tap.side_effect = lambda *a, **kw: recog.update()
    solver.sleep.side_effect = lambda *a: recog.update()
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    monkeypatch.setattr(
        recognize,
        "save_screenshot_frame",
        lambda image, folder: saved.append((int(image[0, 0, 0]), folder)),
    )
    room = reader.RoomState("waiting_collect", reader.RoomPanel(mastery_tier=2))
    plan = {"id": 1}
    with (
        patch.object(reader, "_reconcile_after_collect", return_value=plan),
        patch.object(reader, "_notify_help_collect"),
        patch.object(reader, "_dispatch_after_collect"),
    ):
        if planned:
            assert reader._collect_plan(solver, plan, room) is plan
        else:
            reader._collect_silent(solver, room)
    if not enabled:
        assert saved == []
        return
    expected = [waiting[0]]
    if button_at is not None and button_at > 1:
        expected.append(waiting[button_at - 1])
    # The result is the final capture, before the confirmation wait begins.
    expected.append(int(captures[-2][0, 0, 0]))
    assert saved == [(index, "mastery") for index in expected]
    assert len(saved) <= 3
    assert room.collected


def test_screenshot_failure_does_not_interrupt_collection(monkeypatch):
    monkeypatch.setattr(config.conf, "save_mastery_screenshots", True)
    solver = MagicMock()
    solver.find.return_value = ((10, 10), (20, 20))
    solver.recog.save_screencap.side_effect = OSError("disk unavailable")
    panel = reader.RoomPanel(mastery_tier=2)
    assert reader.collect_flow(solver, None, panel) is solver.recog.img
    assert solver.tap.call_count == 2


@pytest.mark.parametrize("error", [MowerExit(), DeviceRecoveryError("disconnected")])
def test_screenshot_preserves_cancellation_and_device_recovery(monkeypatch, error):
    monkeypatch.setattr(config.conf, "save_mastery_screenshots", True)
    solver = MagicMock()
    solver.recog.save_screencap.side_effect = error
    with pytest.raises(type(error)):
        reader.collect_flow(solver, None, reader.RoomPanel(mastery_tier=2))
    assert solver.tap.call_count == 1


@pytest.mark.parametrize("retention", [0, 1])
@pytest.mark.parametrize("raw", [False, True])
def test_mastery_screenshots_persist_without_daily_history(tmp_path, retention, raw):
    store = ScreenshotStore(
        tmp_path,
        lambda: retention,
        Mock(),
        encoder=lambda image: bytes(image.flat),
    )
    image = np.full((2, 2, 3), 47, dtype=np.uint8)
    payload = bytes(image.flat)
    try:
        filename = (
            store.submit_frame(image, "mastery")
            if raw
            else store.submit(payload, "mastery")
        )
        ordinary = store.submit(b"ordinary")
        store.start()
        result = store.close()
        assert not result["remaining_threads"]
        assert (tmp_path / filename).read_bytes() == payload
        assert (tmp_path / ordinary).exists() == bool(retention)
    finally:
        store.close()


def test_mastery_cleanup_retains_latest_hundred(tmp_path):
    folder = tmp_path / "mastery"
    folder.mkdir()
    for index in range(104):
        (folder / f"{index + 1}.jpg").write_bytes(b"image")
    cleaner = ScreenshotCleanup(tmp_path, lambda: 0)
    try:
        for _ in range(20):
            if cleaner.step()["complete"]:
                break
        else:
            pytest.fail("cleanup did not complete")
    finally:
        cleaner.close()
    assert {int(path.stem) for path in folder.iterdir()} == set(range(5, 105))


def test_mastery_screenshot_configuration_round_trip():
    assert not Conf().save_mastery_screenshots
    saved = Conf(save_mastery_screenshots=True).model_dump()
    assert Conf.model_validate(saved).save_mastery_screenshots
