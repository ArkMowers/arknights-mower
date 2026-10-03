"""Local-only, append-only Arknights headhunting archive.

Keep one archive per Mower data directory.  Account credentials never enter this DB.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from arknights_mower.utils.path import get_path


def archive_path() -> Path:
    return get_path("@app/config/gacha_local/records.sqlite3", space="")


def channel_name(raw: str = "", is_official: bool | None = None) -> str:
    label = str(raw or "").lower()
    if "bilibili" in label or "b服" in label or "b站" in label:
        return "bilibili"
    if is_official is True or "官服" in label:
        return "official"
    return "other"


def identity(uid: str, channel: str) -> str:
    if not uid or channel not in ("official", "bilibili", "other"):
        raise ValueError("UID 或区服无效")
    return f"{channel}:{uid}"


def normalize_record(raw: dict, category: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("单条记录不是对象")
    pool_id = str(raw.get("poolId") or raw.get("pool_id") or "")
    char_id = str(raw.get("charId") or raw.get("char_id") or "")
    timestamp = raw.get("gachaTs", raw.get("timestamp"))
    position = raw.get("pos")
    if not pool_id or not char_id or timestamp is None or position is None:
        raise ValueError("记录缺少 poolId、charId、gachaTs 或 pos")
    try:
        ts = int(str(timestamp))
        pos = int(position)
        rarity = int(raw.get("rarity"))
    except (ValueError, TypeError) as error:
        raise ValueError("记录时间、顺序或稀有度格式错误") from error
    if ts < 100000000000:
        ts *= 1000
    if not (0 <= rarity <= 5 and 0 <= pos <= 1000 and ts > 0):
        raise ValueError("记录时间、顺序或稀有度超出范围")
    # Includes position: two identical characters in one ten-pull are two records.
    source_id = json.dumps(
        [pool_id, char_id, ts, pos], separators=(",", ":"), ensure_ascii=False
    )
    return {
        "id": hashlib.sha256(source_id.encode("utf-8")).hexdigest(),
        "category": str(category),
        "pool_id": pool_id,
        "pool_name": str(raw.get("poolName") or pool_id),
        "char_id": char_id,
        "char_name": str(raw.get("charName") or char_id),
        "rarity": rarity + 1,  # upstream uses zero-based rarity
        "is_new": bool(raw.get("isNew", False)),
        "gacha_ts": ts,
        "position": pos,
    }


class GachaArchive:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else archive_path()
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    uid TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    last_sync INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    account_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    pool_id TEXT NOT NULL,
                    pool_name TEXT NOT NULL,
                    char_id TEXT NOT NULL,
                    char_name TEXT NOT NULL,
                    rarity INTEGER NOT NULL,
                    is_new INTEGER NOT NULL,
                    gacha_ts INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(account_id, id),
                    FOREIGN KEY(account_id) REFERENCES accounts(id)
                );
                CREATE INDEX IF NOT EXISTS idx_gacha_by_account_time
                    ON records(account_id, gacha_ts DESC, position DESC);
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def ensure_account(self, uid: str, channel: str, nickname: str) -> str:
        account_id = identity(uid, channel)
        with self.lock, self._connect() as db:
            db.execute(
                """INSERT INTO accounts(id,uid,channel,nickname,created_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET nickname=excluded.nickname""",
                (account_id, uid, channel, nickname or uid, int(time.time())),
            )
        return account_id

    def accounts(self) -> list[dict]:
        with self.lock, self._connect() as db:
            rows = db.execute(
                """SELECT a.id, a.uid, a.channel, a.nickname, a.last_sync,
                          COUNT(r.id) AS total
                   FROM accounts a LEFT JOIN records r ON r.account_id=a.id
                   GROUP BY a.id ORDER BY a.created_at, a.id"""
            ).fetchall()
            return [dict(row) for row in rows]

    def append(
        self, account_id: str, rows: list[dict], *, finished: bool = False
    ) -> int:
        with self.lock, self._connect() as db:
            existing = db.execute(
                "SELECT 1 FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if not existing:
                raise ValueError("账号尚未保存")
            before = db.total_changes
            db.executemany(
                """INSERT OR IGNORE INTO records
                   (account_id,id,category,pool_id,pool_name,char_id,char_name,
                    rarity,is_new,gacha_ts,position) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        account_id,
                        row["id"],
                        row["category"],
                        row["pool_id"],
                        row["pool_name"],
                        row["char_id"],
                        row["char_name"],
                        row["rarity"],
                        int(row["is_new"]),
                        row["gacha_ts"],
                        row["position"],
                    )
                    for row in rows
                ],
            )
            added = db.total_changes - before
            if finished:
                db.execute(
                    "UPDATE accounts SET last_sync=? WHERE id=?",
                    (int(time.time()), account_id),
                )
        return added

    def list_records(
        self,
        account_id: str,
        limit: int = 100,
        offset: int = 0,
        category: str = "",
        pool_id: str = "",
        rarity: int | None = None,
        rarity_min: int | None = None,
        new_only: bool = False,
        search: str = "",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[dict]:
        if not 1 <= limit <= 300 or offset < 0:
            raise ValueError("分页范围无效")
        if (rarity is not None and rarity not in (3, 4, 5, 6)) or (
            rarity_min is not None and rarity_min not in (3, 4, 5, 6)
        ):
            raise ValueError("星级筛选无效")
        if len(search) > 64:
            raise ValueError("搜索文字过长")
        where = ["account_id=?"]
        params: list = [account_id]
        if category:
            where.append("category=?")
            params.append(category)
        if pool_id:
            where.append("pool_id=?")
            params.append(pool_id)
        if rarity is not None:
            where.append("rarity=?")
            params.append(rarity)
        if rarity_min is not None:
            where.append("rarity>=?")
            params.append(rarity_min)
        if new_only:
            where.append("is_new=1")
        if search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            where.append("char_name LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        if start_ms is not None:
            where.append("gacha_ts >= ?")
            params.append(start_ms)
        if end_ms is not None:
            where.append("gacha_ts <= ?")
            params.append(end_ms)
        with self.lock, self._connect() as db:
            rows = db.execute(
                f"""SELECT category, pool_id, pool_name, char_id, char_name,
                           rarity, is_new, gacha_ts, position
                    FROM records WHERE {" AND ".join(where)}
                    ORDER BY gacha_ts DESC, position DESC
                    LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
            return [dict(row) for row in rows]

    def summary(self, account_id: str) -> dict:
        """Distinguish pull order in one pool from intervals between six stars.

        A pool's earliest saved pull is *not* proof of a complete pity history.
        Never mix different pool IDs or imply shared-pity rules.
        """
        with self.lock, self._connect() as db:
            rows = db.execute(
                """SELECT category,pool_id,pool_name,char_id,char_name,rarity,
                          is_new,gacha_ts,position FROM records
                   WHERE account_id=? ORDER BY gacha_ts,position""",
                (account_id,),
            ).fetchall()
            account = db.execute(
                "SELECT nickname,channel,uid,last_sync FROM accounts WHERE id=?",
                (account_id,),
            ).fetchone()
        if account is None:
            raise ValueError("找不到已保存的角色")
        by_category: dict[str, dict] = {}
        pools: dict[tuple[str, str], dict] = {}
        stars = {"3": 0, "4": 0, "5": 0, "6": 0}
        distinct = set()
        for row in rows:
            category = row["category"]
            star = row["rarity"]
            stars[str(star)] = stars.get(str(star), 0) + 1
            distinct.add(row["char_id"])
            part = by_category.setdefault(
                category, {"count": 0, "six_star": 0, "five_star": 0, "since_six": 0}
            )
            part["count"] += 1
            part["since_six"] += 1
            part["six_star"] += star == 6
            part["five_star"] += star == 5
            if star == 6:
                part["since_six"] = 0
            key = (category, row["pool_id"])
            pool = pools.setdefault(
                key,
                {
                    "category": category,
                    "pool_id": row["pool_id"],
                    "pool_name": row["pool_name"],
                    "count": 0,
                    "six_star": 0,
                    "five_star": 0,
                    "six_operators": [],
                    "latest_ms": 0,
                    "first_ms": row["gacha_ts"],
                },
            )
            pool["count"] += 1
            pool["latest_ms"] = max(pool["latest_ms"], row["gacha_ts"])
            pool["six_star"] += star == 6
            pool["five_star"] += star == 5
            if star == 6:
                previous = pool["six_operators"][-1] if pool["six_operators"] else None
                index = pool["count"]
                pool["six_operators"].append(
                    {
                        "char_name": row["char_name"],
                        "char_id": row["char_id"],
                        "gacha_ts": row["gacha_ts"],
                        "is_new": bool(row["is_new"]),
                        "pool_index": index,
                        "interval_count": index - previous["pool_index"]
                        if previous
                        else index,
                        "interval_complete": previous is not None,
                    }
                )
        ordered_pools = sorted(
            pools.values(), key=lambda p: (-p["latest_ms"], p["pool_name"])
        )
        for pool in ordered_pools:
            for index, op in enumerate(pool["six_operators"]):
                op["until_next_six"] = (
                    pool["six_operators"][index + 1]["pool_index"] - op["pool_index"]
                    if index + 1 < len(pool["six_operators"])
                    else None
                )
                op["after_count"] = (
                    pool["count"] - op["pool_index"]
                    if index == len(pool["six_operators"]) - 1
                    else None
                )
        return {
            "account": dict(account),
            "total": len(rows),
            "six_star": stars["6"],
            "five_star": stars["5"],
            "distinct_operators": len(distinct),
            "stars": stars,
            "categories": by_category,
            "pools": ordered_pools,
            "oldest_ms": rows[0]["gacha_ts"] if rows else None,
            "newest_ms": rows[-1]["gacha_ts"] if rows else None,
            "history_incomplete": True,
        }

    def export(self, account_id: str) -> dict:
        with self.lock, self._connect() as db:
            account = db.execute(
                "SELECT uid, channel, nickname FROM accounts WHERE id=?", (account_id,)
            ).fetchone()
            if account is None:
                raise ValueError("找不到已保存的角色")
            rows = db.execute(
                "SELECT * FROM records WHERE account_id=? ORDER BY gacha_ts,position",
                (account_id,),
            ).fetchall()
        return {
            "format": "mower-gacha-v1",
            "account": dict(account),
            "records": [
                {k: v for k, v in dict(row).items() if k != "account_id"}
                for row in rows
            ],
        }
