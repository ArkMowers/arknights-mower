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

    @abstractmethod
    def wait_if_paused(self) -> None:
        ...
