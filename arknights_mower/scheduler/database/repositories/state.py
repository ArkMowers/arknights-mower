from __future__ import annotations

from typing import Any

from arknights_mower.scheduler.database.storage_port import StoragePort


class StateRepository:
    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    def save(self, key: str, data: dict[str, Any]) -> None:
        self._storage.save(key, data)

    def load(self, key: str) -> dict[str, Any] | None:
        return self._storage.load(key)

    def delete(self, key: str) -> None:
        self._storage.delete(key)

    def list_keys(self) -> list[str]:
        return self._storage.list_keys()
