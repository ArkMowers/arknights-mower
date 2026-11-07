import os
import socket
import subprocess
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.tests.screenshot_fixtures import gzip_frame, rgba_frame
from arknights_mower.utils import config
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device import device as device_module
from arknights_mower.utils.device import screenshot
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget


def make_device(serial="USB-A", adb_path="chosen-adb"):
    device = Device.__new__(Device)
    device.device_id = serial
    device.adb_bin = adb_path
    device.connect = None
    device.strict_target = True
    device._profile = DeviceProfile(
        last_serial=serial, adb_path=adb_path, screenshot_backend="adb_gzip"
    )
    device.owner_pid = os.getpid()
    device._resource_lock = RLock()
    device._interrupted = Event()
    device._close_error = None
    device._interrupt_error = None
    device._pending_cleanup = []
    device._recovery_error = None
    device.control = None
    device.client = SimpleNamespace(
        device_id=serial, adb_bin=adb_path, close=lambda: None
    )
    return device


@pytest.fixture
def transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external I/O")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    guard = Mock()
    monkeypatch.setattr(screenshot, "guard_adb", guard)
    state = SimpleNamespace(
        sdk=b"27\n",
        frame=gzip_frame(rgba_frame(modern=True)),
        calls=[],
        failure=None,
        on_frame=None,
    )

    def output(serial, command, limit, remaining):
        timeout = remaining()
        state.calls.append((serial, command, timeout))
        if state.failure is not None:
            failure, state.failure = state.failure, None
            raise failure
        if not command.startswith("getprop") and state.on_frame is not None:
            callback, state.on_frame = state.on_frame, None
            callback()
        return state.sdk if command.startswith("getprop") else state.frame

    monkeypatch.setattr(screenshot, "_adb_output", output)
    monkeypatch.setattr(config.conf.droidcast, "enable", False)
    monkeypatch.setattr(
        device_module,
        "ADBClient",
        lambda serial, connect, **options: SimpleNamespace(
            device_id=serial, adb_bin=options["adb_bin"], close=lambda: None
        ),
    )
    monkeypatch.setattr(
        Device, "Control", lambda *args: SimpleNamespace(close=lambda: None)
    )
    monkeypatch.setattr(Device, "check_resolution", lambda self: True)
    state.guard = guard
    return state


def sdk_calls(transport):
    return [call for call in transport.calls if call[1].startswith("getprop")]


def test_device_reuses_sdk_for_normal_and_standard_frames(transport):
    device = make_device()
    for capture in (device.capture_frame, device.standard_frame, device.capture_frame):
        frame = capture()
        assert frame.shape == (1080, 1920, 3)
        assert frame.dtype == np.uint8
        assert frame[0, 0].tolist() == [255, 128, 0]
    assert len(sdk_calls(transport)) == 1
    assert transport.guard.call_count == 3
    assert {call[0] for call in transport.calls} == {"USB-A"}


def test_separate_devices_do_not_share_a_cached_sdk(transport):
    first, second = make_device(), make_device()
    first.capture_frame()
    second.capture_frame()
    first.capture_frame()
    assert len(sdk_calls(transport)) == 2


@pytest.mark.parametrize("change", ("serial", "adb_path"))
def test_changed_capture_target_queries_sdk_again(transport, change):
    device = make_device()
    device.capture_frame()
    if change == "serial":
        device.device_id = "USB-B"
    else:
        device.client.adb_bin = "other-adb"
    transport.sdk = b"26\n"
    transport.frame = gzip_frame(rgba_frame(modern=False))
    assert device.capture_frame()[0, 0].tolist() == [255, 128, 0]
    assert len(sdk_calls(transport)) == 2
    assert transport.calls[-1][0] == device.device_id


@pytest.mark.parametrize(
    "reset", ("rebuild_screenshot", "resume_verified", "reconnect", "rebind", "close")
)
def test_lifecycle_boundaries_query_sdk_again(transport, reset):
    device = make_device()
    device.capture_frame()
    if reset == "rebind":
        device.rebind_target("USB-B", "new-adb")
    elif reset == "close":
        device.close()
        device.start(wait_for_device=False)
    else:
        getattr(device, reset)()
    transport.sdk = b"26\n"
    transport.frame = gzip_frame(rgba_frame(modern=False))
    assert device.capture_frame()[0, 0].tolist() == [255, 128, 0]
    assert len(sdk_calls(transport)) == 2


def test_invalid_sdk_never_enters_frame_read_or_publishes_a_cache(transport):
    device = make_device()
    transport.sdk = b"unknown"
    with pytest.raises(ValueError, match="SDK"):
        device.capture_frame()
    assert len(transport.calls) == 1
    transport.sdk = b"27"
    device.capture_frame()
    device.capture_frame()
    assert len(sdk_calls(transport)) == 2


def test_failed_first_frame_does_not_publish_the_verified_sdk(transport):
    device = make_device()
    transport.frame = gzip_frame(rgba_frame(modern=True)[:-4])
    with pytest.raises(ValueError, match="长度"):
        device.capture_frame()
    transport.sdk = b"26"
    transport.frame = gzip_frame(rgba_frame(modern=False))
    device.capture_frame()
    device.capture_frame()
    assert len(sdk_calls(transport)) == 2


@pytest.mark.parametrize("failure", (MowerExit(), TimeoutError("expired")))
def test_failed_cached_frame_discards_sdk_before_next_capture(transport, failure):
    device = make_device()
    device.capture_frame()
    transport.failure = failure
    with pytest.raises(type(failure)):
        device.capture_frame()
    transport.sdk = b"26"
    transport.frame = gzip_frame(rgba_frame(modern=False))
    device.capture_frame()
    assert len(sdk_calls(transport)) == 2


def test_cached_layout_still_rejects_a_truncated_modern_frame(transport):
    device = make_device()
    device.capture_frame()
    transport.frame = gzip_frame(rgba_frame(modern=True)[:-4])
    with pytest.raises(ValueError, match="长度"):
        device.capture_frame()


def test_rebuilt_session_is_not_replaced_by_a_late_successful_frame(transport):
    device = make_device()
    transport.on_frame = device.rebuild_screenshot
    device.capture_frame()
    device.capture_frame()
    assert len(sdk_calls(transport)) == 2


def test_cached_frames_have_fresh_deadlines_and_stop_after_guard_expiration(
    transport, monkeypatch
):
    now = [0]
    monkeypatch.setattr(screenshot.time, "monotonic", lambda: now[0])
    device = make_device()
    device.capture_frame()
    now[0] = 100
    device.capture_frame()
    assert len(sdk_calls(transport)) == 1
    assert transport.calls[-1][2] == screenshot.CAPTURE_TIMEOUT
    transport.guard.side_effect = lambda *args, **kwargs: now.__setitem__(0, 111)
    transport.calls.clear()
    with pytest.raises(TimeoutError, match="超时"):
        device.capture_frame()
    assert transport.calls == []


def test_deadline_expiring_after_decode_does_not_publish_the_sdk(
    transport, monkeypatch
):
    now = [0]
    monkeypatch.setattr(screenshot.time, "monotonic", lambda: now[0])
    decode = screenshot.decode_adb_frame

    def expired_decode(*args, **kwargs):
        frame = decode(*args, **kwargs)
        now[0] += 11
        return frame

    monkeypatch.setattr(screenshot, "decode_adb_frame", expired_decode)
    device = make_device()
    with pytest.raises(TimeoutError, match="超时"):
        device.capture_frame()
    monkeypatch.setattr(screenshot, "decode_adb_frame", decode)
    transport.sdk = b"26"
    transport.frame = gzip_frame(rgba_frame(modern=False))
    device.capture_frame()
    assert len(sdk_calls(transport)) == 2


def test_cached_capture_retains_parent_budget_and_guard_failure(transport):
    device = make_device()
    device.capture_frame()
    transport.calls.clear()
    transport.guard.reset_mock()
    with device_io_budget(lambda: 0.5):
        device.capture_frame()
    assert len(transport.calls) == 1
    assert 0 < transport.calls[0][2] <= 0.5
    assert 0 < transport.guard.call_args.kwargs["timeout"] <= 0.5
    transport.guard.side_effect = TimeoutError("guard expired")
    transport.calls.clear()
    with pytest.raises(TimeoutError, match="guard expired"):
        device.capture_frame()
    assert transport.calls == []


def test_independent_capture_keeps_querying_sdk_for_each_call(transport):
    screenshot.capture_adb_frame("chosen-adb", "USB-A")
    screenshot.capture_adb_frame("chosen-adb", "USB-A")
    assert len(sdk_calls(transport)) == 2
