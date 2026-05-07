import threading

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
