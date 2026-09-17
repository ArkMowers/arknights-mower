import threading
from datetime import datetime, timedelta

from arknights_mower.scheduler.constants import PAUSE_WAKE_SLICE
from arknights_mower.scheduler.infra.pause_controller import PauseController


class ThreadPauseController(PauseController):
    def __init__(self) -> None:
        self._event = threading.Event()
        self._event.set()
        self._stop_event = threading.Event()

    def pause(self) -> None:
        self._event.clear()

    def resume(self) -> None:
        self._event.set()

    @property
    def is_paused(self) -> bool:
        return not self._event.is_set()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def request_stop(self) -> None:
        self._stop_event.set()
        self._event.set()

    def wait_if_paused(self) -> None:
        self._event.wait()

    def wait(self, seconds: float) -> None:
        if seconds <= 0:
            return
        deadline = datetime.now() + timedelta(seconds=seconds)
        while True:
            self.wait_if_paused()
            if self.is_stopped:
                return
            remaining = (deadline - datetime.now()).total_seconds()
            if remaining <= 0:
                return
            self._stop_event.wait(min(remaining, PAUSE_WAKE_SLICE))
