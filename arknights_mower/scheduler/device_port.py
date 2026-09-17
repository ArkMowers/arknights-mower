from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

import numpy as np

from arknights_mower.scheduler.constants import SCREEN_H, SCREEN_W

if TYPE_CHECKING:
    from arknights_mower.scheduler.infra.pause_controller import PauseController


class DevicePort(ABC):
    def __init__(self, pause: Optional[PauseController] = None) -> None:
        self._pause = pause

    def _wait(self, seconds: float) -> None:
        if self._pause is not None:
            self._pause.wait(seconds)

    @abstractmethod
    def tap(self, x: float, y: float) -> None:
        ...

    @abstractmethod
    def swipe(
        self, x1: float, y1: float, x2: float, y2: float, duration: int = 100
    ) -> None:
        ...

    @abstractmethod
    def screencap(self) -> np.ndarray:
        ...

    @abstractmethod
    def launch(self) -> None:
        ...

    @abstractmethod
    def exit(self) -> None:
        ...

    @abstractmethod
    def swipe_path(
        self, points: list[tuple[float, float]], durations: list[int]
    ) -> None:
        ...

    @abstractmethod
    def back(self) -> None:
        ...

    def swipe_noinertia(
        self,
        start: tuple[float, float],
        movement: tuple[int, int],
        interval: float = 0.2,
        duration: int = 20,
    ) -> None:
        sx, sy = start
        mx, my = movement
        if mx == 0:
            _dis = abs(my)
            points = [
                (sx, sy),
                (sx + 100 / SCREEN_W, sy),
                (sx + 100 / SCREEN_W, sy + my / SCREEN_H),
                (sx, sy + my / SCREEN_H),
            ]
            durations = [200, _dis * duration // 100, 200]
        else:
            _dis = abs(mx)
            points = [
                (sx, sy),
                (sx, sy + 100 / SCREEN_H),
                (sx + mx / SCREEN_W, sy + 100 / SCREEN_H),
                (sx + mx / SCREEN_W, sy),
            ]
            durations = [200, _dis * duration // 100, 200]
        self.swipe_path(points, durations)
        if interval > 0:
            self._wait(interval)

    @abstractmethod
    def check_focus(self) -> bool:
        ...

    @abstractmethod
    def reconnect(self) -> None:
        ...
