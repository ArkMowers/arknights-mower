from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


@dataclass
class MethodEntry:
    id: int
    method_key: str
    method_hash: str
    file_path: str
    file_sha256: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]
    summary: str
    model: Optional[str]
    method_embedding: Optional[List[float]]
    metadata: Dict
    created_at: str
    updated_at: str
    hit_count: int


class MethodCache:
    def __init__(self, db_path: Path | str = ".cache/behavior_cache.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as conn:
            self._init_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _init_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS behavior_method_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                method_key TEXT NOT NULL,
                method_hash TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_sha256 TEXT,
                start_line INTEGER,
                end_line INTEGER,
                summary TEXT NOT NULL,
                model TEXT,
                method_embedding TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_method_key_hash
            ON behavior_method_cache(method_key, method_hash);
            CREATE INDEX IF NOT EXISTS idx_method_file ON behavior_method_cache(file_path);
            CREATE INDEX IF NOT EXISTS idx_method_updated ON behavior_method_cache(updated_at DESC);
            """
        )

    def get(self, method_key: str, method_hash: str) -> Optional[MethodEntry]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM behavior_method_cache WHERE method_key=? AND method_hash=?",
                (method_key, method_hash),
            ).fetchone()
            if not row:
                return None
            entry = self._row_to_entry(row)
            conn.execute(
                "UPDATE behavior_method_cache SET hit_count = hit_count + 1, updated_at=? WHERE id=?",
                (_utcnow(), entry.id),
            )
            return entry

    def put(
        self,
        method_key: str,
        method_hash: str,
        summary: str,
        *,
        file_path: str,
        file_sha256: Optional[str],
        start_line: Optional[int],
        end_line: Optional[int],
        model: Optional[str] = None,
        metadata: Optional[Dict] = None,
        method_embedding: Optional[List[float]] = None,
    ) -> MethodEntry:
        now = _utcnow()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO behavior_method_cache (
                    method_key, method_hash, file_path, file_sha256,
                    start_line, end_line, summary, model, method_embedding,
                    metadata, created_at, updated_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(method_key, method_hash) DO UPDATE SET
                    file_path=excluded.file_path,
                    file_sha256=excluded.file_sha256,
                    start_line=excluded.start_line,
                    end_line=excluded.end_line,
                    summary=excluded.summary,
                    model=excluded.model,
                    method_embedding=COALESCE(excluded.method_embedding, method_embedding),
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    method_key,
                    method_hash,
                    file_path,
                    file_sha256,
                    start_line,
                    end_line,
                    summary,
                    model,
                    json.dumps(method_embedding)
                    if method_embedding is not None
                    else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM behavior_method_cache WHERE method_key=? AND method_hash=?",
                (method_key, method_hash),
            ).fetchone()
            return self._row_to_entry(row)

    def list_by_files(
        self, file_paths: List[str], *, only_with_embedding: bool = True
    ) -> List[MethodEntry]:
        if not file_paths:
            return []
        norm = [str(Path(p).resolve()) for p in file_paths]
        placeholders = ",".join(["?"] * len(norm))
        where = f"file_path IN ({placeholders})"
        if only_with_embedding:
            where += " AND method_embedding IS NOT NULL"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM behavior_method_cache WHERE {where}", tuple(norm)
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MethodEntry:
        return MethodEntry(
            id=row["id"],
            method_key=row["method_key"],
            method_hash=row["method_hash"],
            file_path=row["file_path"],
            file_sha256=row["file_sha256"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            summary=row["summary"],
            model=row["model"],
            method_embedding=(
                json.loads(row["method_embedding"]) if row["method_embedding"] else None
            ),
            metadata=(json.loads(row["metadata"]) if row["metadata"] else {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            hit_count=row["hit_count"],
        )
