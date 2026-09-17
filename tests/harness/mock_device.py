"""假设备：实现 `DevicePort` 的**全部**抽象方法，并记录调用序列。

设计要点
--------
1. **继承而不是鸭子类型**。`MockDevicePort(DevicePort)` 让协议一旦漂移
   （新增/改名抽象方法）立刻在实例化时报 `TypeError`，而不是等到某天
   某个用例悄悄跑在假实现上。这是本夹具存在的首要理由。
2. **记录可读的调用序列**。`device.taps` 给出 tap 的归一化坐标列表，
   `device.swipes` 给出滑动，`device.calls` 给出**全量**按序调用
   （含 `launch`/`exit`/`back`/`reconnect`），供断言"点了什么、顺序如何"。
3. **`tap(name)` 具名点击**。用例可以 `device.tap_named("CLEAR_ALL", *INFRA_CLEAR_ALL)`，
   之后用 `device.tap_names()` 得到 `["CLEAR_ALL", "SLOT0", ...]`，比反查坐标稳。
4. **`points` 之外的一切都是显式注入的**：截图来自 `screencap_factory`，
   不接触真实设备、不做真实等待。

用法
----
    from tests.harness.mock_device import MockDevicePort

    device = MockDevicePort(screencap_factory=lambda: frame)
    port.tap(0.5, 0.5)
    assert device.taps == [(0.5, 0.5)]
"""

from __future__ import annotations

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.device_port import DevicePort


class DeviceCall:
    """一次设备调用的人类可读记录。"""

    __slots__ = ("name", "args", "label")

    def __init__(self, name: str, args: tuple, label: str = "") -> None:
        self.name = name
        self.args = args
        self.label = label

    def __repr__(self) -> str:
        detail = self.label or ", ".join(repr(a) for a in self.args)
        return f"{self.name}({detail})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, DeviceCall):
            return (self.name, self.args) == (other.name, other.args)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.args))


class MockDevicePort(DevicePort):
    """记录调用序列的假 DevicePort。

    `pause` 一律传 `None`：单测禁止真实等待，`DevicePort._wait()` 因此成为
    无副作用的空操作。
    """

    def __init__(self, screencap_factory=None) -> None:
        super().__init__(pause=None)
        # 全量按序调用记录
        self.calls: list[DeviceCall] = []
        # tap 的归一化坐标，按序
        self.taps: list[tuple[float, float]] = []
        # tap 的具名标签（未具名时为 None），与 self.taps 一一对应
        self.tap_labels: list[str | None] = []
        # swipe 的 (x1, y1, x2, y2, duration)，按序
        self.swipes: list[tuple[float, float, float, float, int]] = []
        # swipe_path 的点序列，按序
        self.swipe_paths: list[tuple[list[tuple[float, float]], list[int]]] = []
        self.launch_count = 0
        self.exit_count = 0
        self.back_count = 0
        self.check_focus_count = 0
        self.reconnect_count = 0
        self._pending_tap_label: str | None = None
        self._screencap_factory = screencap_factory
        self._screencap_count = 0

    # ------------------------------------------------------------------ 录制

    def _record(self, name: str, args: tuple, label: str = "") -> DeviceCall:
        call = DeviceCall(name, args, label)
        self.calls.append(call)
        return call

    # ------------------------------------------------------ DevicePort 抽象面

    def tap(self, x: float, y: float) -> None:
        label = self._pending_tap_label
        self._pending_tap_label = None
        self.taps.append((x, y))
        self.tap_labels.append(label)
        self._record("tap", (x, y), label or f"{x:.4f},{y:.4f}")

    def tap_named(self, name: str, x: float, y: float) -> None:
        """带语义标签的 tap：`tap_names()` 会返回 `name` 而不是坐标。"""
        self._pending_tap_label = name
        self.tap(x, y)

    def swipe(
        self, x1: float, y1: float, x2: float, y2: float, duration: int = 100
    ) -> None:
        self.swipes.append((x1, y1, x2, y2, duration))
        self._record("swipe", (x1, y1, x2, y2, duration))

    def swipe_path(
        self, points: list[tuple[float, float]], durations: list[int]
    ) -> None:
        self.swipe_paths.append((list(points), list(durations)))
        self._record("swipe_path", (tuple(points), tuple(durations)))

    def screencap(self) -> np.ndarray:
        self._screencap_count += 1
        self._record("screencap", ())
        if self._screencap_factory is None:
            # 默认给一张全黑 1080p 帧：识别层拿它当"什么都没找到"，不会崩
            return np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
        frame = self._screencap_factory(self._screencap_count)
        return frame

    def launch(self) -> None:
        self.launch_count += 1
        self._record("launch", ())

    def exit(self) -> None:
        self.exit_count += 1
        self._record("exit", ())

    def back(self) -> None:
        self.back_count += 1
        self._record("back", ())

    def check_focus(self) -> bool:
        self.check_focus_count += 1
        self._record("check_focus", ())
        return True

    def reconnect(self) -> None:
        self.reconnect_count += 1
        self._record("reconnect", ())

    # ------------------------------------------------------------- 断言辅助

    def call_names(self) -> list[str]:
        """全量调用名序列，如 `["screencap", "tap", "back"]`。"""
        return [c.name for c in self.calls]

    def tap_names(self, resolver=None) -> list[str]:
        """把每次 tap 解析成可读名。

        未具名的 tap 交给 `resolver(x, y) -> str | None` 反查；
        `resolver` 返回 None 时退化为 `"@x,y"`。
        """
        names: list[str] = []
        for (x, y), label in zip(self.taps, self.tap_labels):
            if label is not None:
                names.append(label)
                continue
            resolved = None if resolver is None else resolver(x, y)
            names.append(resolved if resolved is not None else f"@{x:.4f},{y:.4f}")
        return names

    def reset(self) -> None:
        """清空记录，保留注入的 factory（用例之间复用同一实例时用）。"""
        self.calls.clear()
        self.taps.clear()
        self.tap_labels.clear()
        self.swipes.clear()
        self.swipe_paths.clear()
        self.launch_count = 0
        self.exit_count = 0
        self.back_count = 0
        self.check_focus_count = 0
        self.reconnect_count = 0
        self._pending_tap_label = None
        self._screencap_count = 0
