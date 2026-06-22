import sqlite3
from datetime import datetime
from typing import Optional

from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def _db() -> sqlite3.Connection:
    get_path("@app/tmp").mkdir(exist_ok=True)
    conn = sqlite3.connect(get_path("@app/tmp/data.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mastery_plan ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "char_id TEXT NOT NULL,"
        "skill_index INTEGER NOT NULL,"
        "status TEXT NOT NULL,"
        "failed_reason TEXT,"
        "level INTEGER DEFAULT 1,"
        "skill_name TEXT,"
        "created_at TEXT DEFAULT (datetime('now','localtime'))"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mastery_route ("
        "profession TEXT NOT NULL,"
        "supports TEXT NOT NULL DEFAULT '{}',"
        "is_default INTEGER DEFAULT 0,"
        "created_at TEXT DEFAULT (datetime('now','localtime')),"
        "UNIQUE(profession, is_default)"
        ")"
    )


def insert_plan(
    char_id: str,
    skill_index: int,
    status: str,
    failed_reason: Optional[str] = None,
    level: int = 1,
    skill_name: Optional[str] = None,
) -> int:
    conn = _db()
    try:
        _ensure_tables(conn)
        cursor = conn.execute(
            "INSERT INTO mastery_plan (char_id, skill_index, status, failed_reason, level, skill_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (char_id, skill_index, status, failed_reason, level, skill_name),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"insert_plan failed: {e}")
        return -1
    finally:
        conn.close()


def get_current_plan(char_id: str, skill_index: int) -> Optional[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT * FROM mastery_plan WHERE id IN ("
            "SELECT MAX(id) FROM mastery_plan WHERE char_id=? AND skill_index=?"
            ")",
            (char_id, skill_index),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_current_plan failed: {e}")
        return None
    finally:
        conn.close()


def get_all_plans() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT * FROM mastery_plan WHERE id IN ("
            "SELECT MAX(id) FROM mastery_plan GROUP BY char_id, skill_index"
            ") ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_plans failed: {e}")
        return []
    finally:
        conn.close()


def get_pending_plans() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT p.* FROM mastery_plan p INNER JOIN ("
            "SELECT char_id, skill_index, MAX(id) as max_id "
            "FROM mastery_plan GROUP BY char_id, skill_index"
            ") latest ON p.id = latest.max_id "
            "WHERE p.status IN ('pending', 'failed')"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_pending_plans failed: {e}")
        return []
    finally:
        conn.close()


def get_pending_only() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT p.* FROM mastery_plan p INNER JOIN ("
            "SELECT char_id, skill_index, MAX(id) as max_id "
            "FROM mastery_plan GROUP BY char_id, skill_index"
            ") latest ON p.id = latest.max_id "
            "WHERE p.status = 'pending'"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_pending_only failed: {e}")
        return []
    finally:
        conn.close()


def get_history(char_id: str, skill_index: int) -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT * FROM mastery_plan WHERE char_id=? AND skill_index=? "
            "ORDER BY id DESC LIMIT 10",
            (char_id, skill_index),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_history failed: {e}")
        return []
    finally:
        conn.close()


def get_all_history() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT * FROM mastery_plan ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_history failed: {e}")
        return []
    finally:
        conn.close()


def set_plan_status(
    char_id: str,
    skill_index: int,
    new_status: str,
    failed_reason: Optional[str] = None,
    level: int = 1,
    skill_name: Optional[str] = None,
) -> int:
    return insert_plan(char_id, skill_index, new_status, failed_reason, level, skill_name)


def save_route(
    profession: str,
    supports_json: str,
    is_default: int = 0,
):
    conn = _db()
    try:
        _ensure_tables(conn)
        conn.execute(
            "INSERT OR REPLACE INTO mastery_route "
            "(profession, supports, is_default) "
            "VALUES (?, ?, ?)",
            (profession, supports_json, is_default),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"save_route failed: {e}")
    finally:
        conn.close()


def get_route(profession: str) -> Optional[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT * FROM mastery_route WHERE profession=? AND is_default=0",
            (profession,),
        ).fetchone()
        if row:
            return dict(row)
        row = conn.execute(
            "SELECT * FROM mastery_route WHERE profession=? AND is_default=1",
            (profession,),
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_route failed: {e}")
        return None
    finally:
        conn.close()


def get_all_routes() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT * FROM mastery_route ORDER BY profession"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_routes failed: {e}")
        return []
    finally:
        conn.close()


def get_user_routes() -> list[dict]:
    conn = _db()
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            "SELECT * FROM mastery_route WHERE is_default=0"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_user_routes failed: {e}")
        return []
    finally:
        conn.close()


def retry_plan(char_id: str, skill_index: int, skill_name: Optional[str] = None) -> int:
    return insert_plan(char_id, skill_index, "pending", skill_name=skill_name)


def has_train_group_plan() -> bool:
    try:
        from arknights_mower.utils.config import plan
        train_plan = plan.plan1.train
        if train_plan and train_plan.plans:
            for p in train_plan.plans:
                if p.group and p.group.strip():
                    return True
    except Exception:
        pass
    return False
