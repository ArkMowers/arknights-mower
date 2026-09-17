from __future__ import annotations

from abc import ABC, abstractmethod


class PauseController(ABC):
    @abstractmethod
    def pause(self) -> None:
        ...

    @abstractmethod
    def resume(self) -> None:
        ...

    @property
    @abstractmethod
    def is_paused(self) -> bool:
        ...

    @property
    @abstractmethod
    def is_stopped(self) -> bool:
        ...

    @abstractmethod
    def request_stop(self) -> None:
        ...

    @abstractmethod
    def wait_if_paused(self) -> None:
        ...

    @abstractmethod
    def wait(self, seconds: float) -> None:
        """Pause-aware wait. Blocks while paused, returns early once stopped."""
