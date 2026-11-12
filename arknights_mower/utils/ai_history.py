"""Bounded textual conversations, separate from configuration and tool execution."""

import sqlite3
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from threading import RLock
from uuid import uuid4

from arknights_mower.utils.path import get_path

MAX_CONVERSATIONS = 20
MAX_INSTANCE_CONVERSATIONS = 100
MAX_TURNS = 100
MAX_HISTORY_CHARS = 262144
MAX_REPLY_CHARS = 32768
MAX_CONTEXT_CHARS = 24000
MAX_CONTEXT_TURNS = 10
_lock = RLock()
_active = set()


class HistoryError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


@dataclass
class Turn:
    conversation_id: str
    context: list
    reply: str = ""
    complete: bool = False
    turn_id: int = 0

    def append(self, text):
        if len(self.reply) + len(text) > MAX_REPLY_CHARS:
            raise HistoryError("回复超过保存上限，本轮已中断，请缩小问题范围")
        self.reply += text


class HistoryStore:
    def __init__(self, profile_id):
        self.profile_id = profile_id
        self.path = get_path("@app/ai-history.sqlite3")

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA secure_delete = ON")
            db.executescript(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "id TEXT PRIMARY KEY, profile TEXT NOT NULL, title TEXT NOT NULL,"
                "updated REAL NOT NULL);"
                "CREATE TABLE IF NOT EXISTS turns ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT NOT NULL "
                "REFERENCES conversations(id) ON DELETE CASCADE,"
                "user TEXT NOT NULL, assistant TEXT NOT NULL DEFAULT '',"
                "status TEXT NOT NULL DEFAULT 'interrupted');"
            )
            yield db

    def _key(self, identifier):
        return (str(self.path), identifier)

    def _find(self, db, identifier):
        if not isinstance(identifier, str) or len(identifier) != 32:
            raise HistoryError("会话标识无效", 400)
        row = db.execute(
            "SELECT * FROM conversations WHERE id=? AND profile=?",
            (identifier, self.profile_id),
        ).fetchone()
        if row is None:
            raise HistoryError("会话不存在或已被删除，请开始新对话", 404)
        return dict(row)

    def list(self):
        with _lock, self._db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,title,updated FROM conversations WHERE profile=? "
                    "ORDER BY updated DESC,id DESC",
                    (self.profile_id,),
                )
            ]

    def read(self, identifier):
        with _lock, self._db() as db:
            result = self._find(db, identifier)
            result["turns"] = [
                dict(row)
                for row in db.execute(
                    "SELECT id,user,assistant,status FROM turns WHERE conversation=? ORDER BY id",
                    (identifier,),
                )
            ]
            result["busy"] = self._key(identifier) in _active
            return result

    def delete(self, identifier=None):
        with _lock, self._db() as db:
            if identifier is not None:
                self._find(db, identifier)
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM conversations WHERE profile=?", (self.profile_id,)
                )
                if identifier is None or row[0] == identifier
            ]
            if any(self._key(item) in _active for item in ids):
                raise HistoryError("会话正在回复，请等待结束后删除")
            db.executemany(
                "DELETE FROM conversations WHERE id=?", [(item,) for item in ids]
            )

    def _prune(self, db, identifier):
        rows = db.execute(
            "SELECT id,length(user)+length(assistant) AS size FROM turns "
            "WHERE conversation=? ORDER BY id DESC",
            (identifier,),
        ).fetchall()
        size = 0
        for index, row in enumerate(rows):
            size += row["size"]
            if index >= MAX_TURNS or size > MAX_HISTORY_CHARS:
                db.execute(
                    "DELETE FROM turns WHERE conversation=? AND id<=?",
                    (identifier, row["id"]),
                )
                break

    def _evict(self, db):
        rows = db.execute(
            "SELECT id,profile FROM conversations ORDER BY updated DESC,id DESC"
        ).fetchall()
        counts = {}
        total = 0
        for row in rows:
            profile = row["profile"]
            counts[profile] = counts.get(profile, 0) + 1
            total += 1
            if (
                counts[profile] > MAX_CONVERSATIONS
                or total > MAX_INSTANCE_CONVERSATIONS
            ):
                if self._key(row["id"]) in _active:
                    raise HistoryError("历史容量已满且旧会话正在回复，请稍后重试")
                db.execute("DELETE FROM conversations WHERE id=?", (row["id"],))

    @contextmanager
    def turn(self, identifier, user):
        with _lock:
            with self._db() as db:
                if identifier is None:
                    identifier = uuid4().hex
                    db.execute(
                        "INSERT INTO conversations VALUES (?,?,?,?)",
                        (identifier, self.profile_id, user[:60], time.time()),
                    )
                else:
                    self._find(db, identifier)
                key = self._key(identifier)
                if key in _active:
                    raise HistoryError("会话正在回复，请等待结束后继续")
                # Use only a contiguous suffix of complete turns after any interruption.
                rows = db.execute(
                    "SELECT user,assistant,status FROM turns WHERE conversation=? "
                    "ORDER BY id DESC LIMIT ?",
                    (identifier, MAX_CONTEXT_TURNS),
                ).fetchall()
                selected, size = [], 0
                for row in rows:
                    size += len(row["user"]) + len(row["assistant"])
                    if row["status"] != "complete" or size > MAX_CONTEXT_CHARS:
                        break
                    selected.append(row)
                context = []
                for row in reversed(selected):
                    context.extend(
                        [
                            {"role": "user", "content": row["user"]},
                            {"role": "assistant", "content": row["assistant"]},
                        ]
                    )
                cursor = db.execute(
                    "INSERT INTO turns(conversation,user) VALUES (?,?)",
                    (identifier, user),
                )
                turn = Turn(identifier, context, turn_id=cursor.lastrowid)
                db.execute(
                    "UPDATE conversations SET updated=? WHERE id=?",
                    (time.time(), identifier),
                )
                self._prune(db, identifier)
                self._evict(db)
            _active.add(key)
        try:
            yield turn
        finally:
            with _lock:
                try:
                    with self._db() as db:
                        db.execute(
                            "UPDATE turns SET assistant=?,status=? WHERE id=?",
                            (
                                turn.reply,
                                "complete" if turn.complete else "interrupted",
                                turn.turn_id,
                            ),
                        )
                        db.execute(
                            "UPDATE conversations SET updated=? WHERE id=?",
                            (time.time(), identifier),
                        )
                        self._prune(db, identifier)
                finally:
                    _active.discard(key)
