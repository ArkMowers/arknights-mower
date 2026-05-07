from __future__ import annotations

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W
from arknights_mower.scheduler.device_port import DevicePort
from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.session import Session
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.simulator import restart_simulator


class PCDevicePort(DevicePort):
    def __init__(self, device: Device) -> None:
        self._device = device

    def tap(self, x: float, y: float) -> None:
        self._device.tap((int(x * SCREEN_W), int(y * SCREEN_H)))

    def swipe(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        duration: int = 100,
    ) -> None:
        self._device.swipe(
            (int(x1 * SCREEN_W), int(y1 * SCREEN_H)),
            (int(x2 * SCREEN_W), int(y2 * SCREEN_H)),
            duration,
        )

    def swipe_path(
        self, points: list[tuple[float, float]], durations: list[int]
    ) -> None:
        pixel_points = [
            (int(x * SCREEN_W), int(y * SCREEN_H)) for x, y in points
        ]
        self._device.swipe_ext(pixel_points, durations)

    def screencap(self) -> np.ndarray:
        _, img, _ = self._device.screencap()
        return img

    def launch(self) -> None:
        self._device.launch()

    def exit(self) -> None:
        self._device.exit()

    def back(self) -> None:
        self._device.send_keyevent(4)

    def check_focus(self) -> bool:
        self._device.check_current_focus()
        return True

    def reconnect(self) -> None:
        restart_simulator()
        self._device.client.check_server_alive()
        Session().connect(config.conf.adb)
        if config.conf.droidcast.enable:
            self._device.start_droidcast()
