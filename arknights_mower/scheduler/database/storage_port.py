from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class StoragePort(ABC):
    @abstractmethod
    def save(self, key: str, data: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def load(self, key: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def list_keys(self) -> list[str]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...
