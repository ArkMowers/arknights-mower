from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from multiprocessing import Pipe
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.tests.adb_capture_session_tests import make_device
from arknights_mower.tests.device_mumu_frame_tests import NativeRenderer, connected_ipc
from arknights_mower.tests.screenshot_adb_tests import CaptureSocket
from arknights_mower.tests.screenshot_fixtures import gzip_frame, rgba_frame
from arknights_mower.utils import config
from arknights_mower.utils.device import capture_time, ldplayer_capture, screenshot
from arknights_mower.utils.device import device as device_module
from arknights_mower.utils.device.mumu12ipc import capture as mumu_capture
from arknights_mower.utils.device.native_capture import NativeCaptureSession
from arknights_mower.utils.recognize import Recognizer


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        start = datetime(2026, 11, 23, 9)
        current = start

        @classmethod
        def now(cls):
            return cls.current

        @classmethod
        def advance(cls, seconds):
            cls.current += timedelta(seconds=seconds)

    monkeypatch.setattr(capture_time, "datetime", Clock)
    monkeypatch.setattr(device_module, "datetime", Clock)
    monkeypatch.setattr(
        device_module,
        "time",
        SimpleNamespace(
            sleep=Clock.advance, monotonic=lambda: 17.0, time_ns=lambda: 33
        ),
    )
    monkeypatch.setattr(device_module, "budget_sleep", Clock.advance)
    monkeypatch.setattr(device_module, "save_screenshot_frame", Mock())
    monkeypatch.setattr(config, "screenshot_time", Clock.start)
    monkeypatch.setattr(config, "screenshot_count", 0)
    monkeypatch.setattr(config, "screenshot_avg", None)
    monkeypatch.setattr(config.conf, "screenshot_interval", 0)
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    monkeypatch.setattr(config, "stop_mower", Event())
    return Clock


@pytest.mark.parametrize("held", [False, True])
def test_recognizer_times_adb_command_after_throttle_and_transport(
    clock, monkeypatch, held
):
    device = make_device()
    device.check_current_focus = Mock(return_value=False)
    recog = Recognizer(device)
    device._screenshot_owner = object()
    monkeypatch.setattr(config.conf, "screenshot_interval", 2000)
    monkeypatch.setattr(screenshot, "guard_adb", lambda *a, **kw: clock.advance(1))

    class Socket(CaptureSocket):
        def sendall(self, data):
            super().sendall(data)
            clock.advance(3 if b"exec:screencap " in data else 1)

    sockets = [Socket(b"30\n"), Socket(gzip_frame(rgba_frame(modern=True)))]
    monkeypatch.setattr(
        screenshot.socket, "create_connection", Mock(side_effect=sockets)
    )
    if held:
        frame = device.screencap(recover=False)
        assert isinstance(frame, tuple) and len(frame) == 3
        clock.advance(4)
        recog.set_frame(frame)
        assert recog.img is frame[1] and recog.gray is frame[2]
        device.check_current_focus.assert_not_called()
    else:
        recog.start()
        device.check_current_focus.assert_called_once_with()
    assert recog.capture_started_at == clock.start + timedelta(seconds=6)
    assert clock.now() == clock.start + timedelta(seconds=13 if held else 9)
    assert all(sock.closed for sock in sockets)
    archived = device_module.save_screenshot_frame.call_args
    assert archived.args[0] is recog.img
    assert archived.kwargs["capture_owner"] is device._screenshot_owner
    assert archived.kwargs["capture_started_at"] == 17.0
    assert archived.kwargs["capture_wall_ns"] == 33


def classic_device():
    device = make_device()
    ipc = connected_ipc(NativeRenderer())
    device.control = SimpleNamespace(mumu12IPC=ipc)
    return device


def test_nested_capture_keeps_the_request_for_each_returned_frame(clock, monkeypatch):
    outer, inner = classic_device(), classic_device()
    nested = []

    def save(rgb, **kwargs):
        if not nested:
            nested.append(None)
            clock.advance(2)
            nested[0] = inner.screencap()

    monkeypatch.setattr(device_module, "save_screenshot_frame", save)
    frame = outer.screencap()
    assert frame.requested_at == clock.start
    assert nested[0].requested_at == clock.start + timedelta(seconds=2)
    assert nested[0][1] is not frame[1]


def test_concurrent_captures_return_their_own_request(clock, monkeypatch):
    first, second = classic_device(), classic_device()
    first_ready = Event()
    both_ready = Barrier(2)
    first._screenshot_owner = object()

    def save(rgb, *, capture_owner, **kwargs):
        if capture_owner is first._screenshot_owner:
            first_ready.set()
        both_ready.wait(timeout=3)

    monkeypatch.setattr(device_module, "save_screenshot_frame", save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(first.screencap)
        assert first_ready.wait(timeout=3)
        clock.advance(2)
        other = second.screencap()
        frame = pending.result(timeout=3)
    assert frame.requested_at == clock.start
    assert other.requested_at == clock.start + timedelta(seconds=2)


def test_unrelated_probe_cannot_supply_another_frames_request(clock):
    device = classic_device()
    source = device.control.mumu12IPC
    probes = []

    def capture():
        probe = source.capture_display()
        probes.append(probe)
        other = np.zeros_like(probe)
        return SimpleNamespace(unwrap=lambda: other)

    device.session_control = SimpleNamespace(capture=capture)
    assert device.screencap().requested_at is None
    assert len(probes) == 1


@pytest.mark.parametrize(
    "backend", [mumu_capture, ldplayer_capture], ids=["mumu", "ld"]
)
def test_native_capture_uses_worker_request_after_renderer_start(
    clock, monkeypatch, backend
):
    device = make_device()
    parent, child = Pipe()
    native = NativeCaptureSession(backend._capture_worker, (), label="native")
    native._process = object()
    native._channel = parent
    native._buffer = bytearray(1920 * 1080 * 3)
    device.session_control = SimpleNamespace(capture_once=native.capture_frame)
    captures = []

    def initialize():
        # 父进程的请求已在管道内，工作进程此时仍未完成渲染器初始化。
        assert child.poll(3)
        clock.advance(2)

    def vendor_capture():
        captures.append(clock.now())
        clock.advance(3)

    def receive():
        command = child.recv()
        clock.advance(1)
        return command

    worker_channel = SimpleNamespace(recv=receive, send=child.send, close=child.close)
    monkeypatch.setattr(backend, "datetime", clock)
    if backend is mumu_capture:

        class Renderer(NativeRenderer):
            def nemu_capture_display(self, *args):
                vendor_capture()
                return super().nemu_capture_display(*args)

        def load_renderer(ipc):
            initialize()
            ipc._dll = Renderer()

        monkeypatch.setattr(backend.MuMu12IPC, "_load_renderer", load_renderer)
        args = ("MuMu", "3", "com.hypergryph.arknights")
    else:

        def renderer_factory(*args):
            initialize()
            renderer = Mock()
            renderer.capture_frame.side_effect = lambda **kwargs: vendor_capture()
            return renderer

        monkeypatch.setattr(backend, "_LDRenderer", renderer_factory)
        args = ("ldopengl64.dll", 3, 42)

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(
            backend._capture_worker, *args, native._buffer, worker_channel
        )
        try:
            frame = device.screencap(recover=False)
        finally:
            parent.close()
            worker.result(timeout=3)

    assert captures == [clock.start + timedelta(seconds=3)]
    assert frame.requested_at == captures[0]
    assert clock.now() == clock.start + timedelta(seconds=6)


def test_custom_command_timed_after_adb_guard_and_output_preparation(
    clock, monkeypatch
):
    from arknights_mower.utils.device import manager_io

    device = make_device()
    device._profile.screenshot_backend = "custom"
    monkeypatch.setattr(
        config.conf.custom_screenshot, "command", "adb shell screencap -p"
    )
    monkeypatch.setattr(
        device_module, "guard_adb", lambda *a, **kw: clock.advance(2) or 8
    )
    _, png = cv2.imencode(".png", np.zeros((1080, 1920, 3), dtype=np.uint8))

    capture_stream = manager_io._capture_stream

    def prepare_stream(stack):
        clock.advance(4)
        return capture_stream(stack)

    def spawn(argv, *, stdout, **kwargs):
        assert argv == ["chosen-adb", "-s", "USB-A", "shell", "screencap", "-p"]
        clock.advance(3)
        stdout.write(png.tobytes())
        stdout.flush()
        return SimpleNamespace(stdin=None, poll=lambda: 0, returncode=0)

    monkeypatch.setattr(manager_io, "_capture_stream", prepare_stream)
    monkeypatch.setattr(manager_io.subprocess, "Popen", spawn)
    frame = device.screencap(recover=False)
    assert frame.requested_at == clock.start + timedelta(seconds=6)
    assert clock.now() == clock.start + timedelta(seconds=9)
