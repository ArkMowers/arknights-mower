import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from arknights_mower.scheduler.database.storage_port import StoragePort
from arknights_mower.utils.path import get_path


class SQLiteStorage(StoragePort):
    def __init__(self, db_name: str = "mower.db") -> None:
        self._path = str(get_path("@app/tmp") / db_name)
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._path)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, data TEXT)"
            )
        return self._conn

    def save(self, key: str, data: dict[str, Any]) -> None:
        c = self._ensure()
        c.execute(
            "INSERT OR REPLACE INTO kv_store (key, data) VALUES (?, ?)",
            (key, json.dumps(data)),
        )
        c.commit()

    def load(self, key: str) -> Optional[dict[str, Any]]:
        try:
            c = self._ensure()
            row = c.execute("SELECT data FROM kv_store WHERE key = ?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def delete(self, key: str) -> None:
        c = self._ensure()
        c.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        c.commit()

    def list_keys(self) -> list[str]:
        c = self._ensure()
        rows = c.execute("SELECT key FROM kv_store").fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
