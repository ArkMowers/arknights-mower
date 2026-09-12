"""识别耗时不能替代下一张画面的等待：旧截图不会随耗时变成新帧。"""

import sys
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils import solver as solver_module  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.solver import BaseSolver  # noqa: E402

OLD_SCOPE = ((631, 488), (820, 520))
NEW_SCOPE = ((1063, 909), (1252, 941))


class VirtualClock:
    def __init__(self, stop):
        self.now = 0.0
        self.stop = stop
        self.waits = []
        self.stop_at = None

    def sleep(self, seconds):
        if self.stop.is_set():
            raise MowerExit
        self.waits.append(seconds)
        self.now += seconds
        if self.stop_at is not None and self.now >= self.stop_at:
            self.stop.set()
        if self.stop.is_set():
            raise MowerExit


class DelayedFrameDevice:
    """截图结束后才记录间隔；新页到达取决于时钟，不取决于调用次数。"""

    def __init__(self, clock, interval):
        self.clock = clock
        self.interval = interval
        self.last_capture = -interval
        self.captures = []
        self.taps = []

    def screencap(self):
        remaining = self.last_capture + self.interval - self.clock.now
        self.clock.now += max(0.0, remaining) + 0.1
        self.last_capture = self.clock.now
        marker = int(self.clock.now >= 1.1)
        self.captures.append((self.clock.now, marker))
        # 名字两条横带均有页面标记，真实 reader 会缓存同一页的结果。
        img = np.full((1080, 1920, 3), marker, dtype=np.uint8)
        return b"unused", img, img[:, :, 0]

    def tap(self, coordinate):
        self.taps.append((self.clock.now, coordinate))


class DelayedFrameSolver(BaseMixin, BaseSolver):
    def __init__(self, device):
        self.device = device
        self.recog = Recognizer(device)

    def find(self, name):
        assert name == "connecting"
        # 与 connecting 检查相同，必须触发懒截图，且保留这次截图。
        self.recog.img
        return False


def delayed_frame_scenario(monkeypatch, interval):
    stop = Event()
    clock = VirtualClock(stop)
    device = DelayedFrameDevice(clock, interval)
    solver = DelayedFrameSolver(device)
    reads = []

    def match(img, **kwargs):
        marker = int(img[488, 600, 0])
        reads.append((clock.now, marker))
        clock.now += 0.8
        scope = NEW_SCOPE if marker else OLD_SCOPE
        return (("砾", scope),)

    monkeypatch.setattr(config, "stop_mower", stop)
    monkeypatch.setattr(solver_module, "csleep", clock.sleep)
    monkeypatch.setattr(base_mixin, "perf_counter", lambda: clock.now)
    monkeypatch.setattr(base_mixin, "operator_list", match)
    return solver, clock, reads


def select_confirmed_target(solver):
    page = solver.wait_for_agent_page()
    solver.tap(page[0][1], interval=0.2)
    return page


@pytest.mark.parametrize("interval", [0, 0.5])
def test_slow_matching_waits_for_late_frame_before_using_coordinates(
    monkeypatch, interval
):
    solver, clock, reads = delayed_frame_scenario(monkeypatch, interval)

    page = select_confirmed_target(solver)

    assert page == (("砾", NEW_SCOPE),)
    assert [marker for _, marker in solver.device.captures] == [0, 1, 1]
    assert [at for at, _ in solver.device.captures] == pytest.approx([0.1, 1.5, 2.9])
    # 旧页、新页各冷识别一次；第三帧相同区域命中真实 reader 缓存。
    assert [marker for _, marker in reads] == [0, 1]
    assert solver.device.taps == [(pytest.approx(2.9), BaseSolver.get_pos(NEW_SCOPE))]
    assert clock.waits == [0.5, 0.5, 0.2]


@pytest.mark.parametrize("interval", [0, 0.5])
def test_stop_before_first_lazy_capture_does_not_select(monkeypatch, interval):
    solver, clock, reads = delayed_frame_scenario(monkeypatch, interval)
    clock.stop.set()

    with pytest.raises(MowerExit):
        select_confirmed_target(solver)

    assert solver.device.captures == []
    assert reads == []
    assert solver.device.taps == []


@pytest.mark.parametrize("interval", [0, 0.5])
def test_stop_during_wait_after_cold_match_does_not_select(monkeypatch, interval):
    solver, clock, reads = delayed_frame_scenario(monkeypatch, interval)
    clock.stop_at = 1.0

    with pytest.raises(MowerExit):
        select_confirmed_target(solver)

    assert [marker for _, marker in solver.device.captures] == [0]
    assert [marker for _, marker in reads] == [0]
    assert solver.device.taps == []
