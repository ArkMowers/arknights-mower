import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skill_label import format_skill_label

_PLAN_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS mastery_plan ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "char_id TEXT NOT NULL,"
    "char_name TEXT,"
    "skill_index INTEGER NOT NULL,"
    "skill_name TEXT,"
    "target_level INTEGER NOT NULL,"
    "status TEXT NOT NULL DEFAULT 'idle',"
    "failed_reason TEXT,"
    "priority INTEGER NOT NULL DEFAULT 0,"
    "expires_at TEXT,"
    "swap_frozen INTEGER DEFAULT 0,"
    "created_at TEXT DEFAULT (datetime('now','localtime'))"
    ")"
)

_ROUTE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS mastery_route ("
    "profession TEXT NOT NULL,"
    "supports TEXT NOT NULL DEFAULT '{}',"
    "is_default INTEGER DEFAULT 0,"
    "optimal INTEGER NOT NULL DEFAULT 0,"
    "half_off INTEGER NOT NULL DEFAULT 1,"
    "created_at TEXT DEFAULT (datetime('now','localtime')),"
    "UNIQUE(profession, is_default)"
    ")"
)

_NOTIFY_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS mastery_notify ("
    "notify_type TEXT NOT NULL,"
    "dedup_key TEXT NOT NULL,"
    "sent_at TEXT DEFAULT (datetime('now','localtime')),"
    "PRIMARY KEY (notify_type, dedup_key)"
    ")"
)

VALID_STATUSES = (
    "idle",
    "arranging",
    "training",
    "waiting_collect",
    "completed",
    "failed",
)


def _db(path: Optional[str] = None) -> sqlite3.Connection:
    if path is None:
        get_path("@app/tmp").mkdir(exist_ok=True)
        path = str(get_path("@app/tmp/data.db"))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# 已建表库路径集合：`_ensure_tables` 进程内每个库只跑一次（表结构只在代码升级时变）。
# 连接仍每次新开（避开 sqlite 跨线程复用）。
_tables_created: set = set()


@contextmanager
def _conn(path: Optional[str] = None):
    if path is None:
        get_path("@app/tmp").mkdir(exist_ok=True)
        path = str(get_path("@app/tmp/data.db"))
    # 数据库文件被删/为空（新库）→ 重置该库建表标记，本次连接重建表（#86 同款守卫，
    # 防运行中丢库后 no-such-table；空文件=全新库尚未建表）
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        _tables_created.discard(path)
    conn = _db(path)
    try:
        _ensure_tables(conn, path)
        yield conn
    finally:
        conn.close()


def _ensure_tables(conn: sqlite3.Connection, path: str):
    """建表/迁移检查，每个库路径进程内只跑一次（#82）。"""
    if path in _tables_created:
        return
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mastery_plan'"
    )
    if cur.fetchone():
        cols = {row[1] for row in conn.execute("PRAGMA table_info(mastery_plan)")}
        if "target_level" not in cols:
            conn.execute("DROP TABLE mastery_plan")
    conn.execute(_PLAN_SCHEMA)
    conn.execute(_ROUTE_SCHEMA)
    conn.execute(_NOTIFY_SCHEMA)
    route_cols = {row[1] for row in conn.execute("PRAGMA table_info(mastery_route)")}
    if "optimal" not in route_cols:
        conn.execute(
            "ALTER TABLE mastery_route ADD COLUMN optimal INTEGER NOT NULL DEFAULT 0"
        )
    if "half_off" not in route_cols:
        conn.execute(
            "ALTER TABLE mastery_route ADD COLUMN half_off INTEGER NOT NULL DEFAULT 1"
        )
    conn.commit()
    _tables_created.add(path)


# --- Plan CRUD ---


def lazy_fill_plan_names(plan: dict, conn: sqlite3.Connection = None) -> dict:
    """存量计划懒填充（#63）：char_name 为 NULL 补干员名；skill_name 为占位
    `技能{N}` 时并入真名、写成规范格式 `{序数}技能·真名`。

    不改变行为；只在缺字段时写库，返回补全后的计划 dict。
    """
    changed = False
    if not plan.get("char_name"):
        name = _resolve_char_name(plan.get("char_id", ""))
        if name:
            plan["char_name"] = name
            changed = True
    skill_name = plan.get("skill_name") or ""
    if _is_placeholder_skill_name(skill_name):
        real = _resolve_skill_name(plan.get("char_id", ""), plan.get("skill_index", 0))
        plan["skill_name"] = format_skill_label(plan.get("skill_index", 0), real)
        changed = True
    if changed and conn is not None:
        conn.execute(
            "UPDATE mastery_plan SET char_name=?, skill_name=? WHERE id=?",
            (plan.get("char_name"), plan.get("skill_name"), plan["id"]),
        )
    return plan


def _is_placeholder_skill_name(skill_name) -> bool:
    from arknights_mower.utils.skill_label import is_placeholder_skill_name

    return is_placeholder_skill_name(skill_name)


def _resolve_char_name(char_id: str) -> str:
    from arknights_mower.utils.mastery_recommendation import get_skill_data

    try:
        return (
            get_skill_data().get("characters", {}).get(char_id, {}).get("name", char_id)
        )
    except Exception:
        return char_id


def _resolve_skill_name(char_id: str, skill_index: int):
    from arknights_mower.utils.mastery_recommendation import get_skill_real_name

    return get_skill_real_name(char_id, skill_index)


def insert_plan(
    char_id: str,
    skill_index: int,
    target_level: int,
    skill_name: Optional[str] = None,
    char_name: Optional[str] = None,
    priority: int = 0,
    path: Optional[str] = None,
) -> int:
    # #63：技能名存规范格式 `{序数}技能·真名`；占位/缺名时用真名懒填充再格式化。
    if not skill_name or _is_placeholder_skill_name(skill_name):
        skill_name = _resolve_skill_name(char_id, skill_index)
    skill_name = format_skill_label(skill_index, skill_name)
    if not char_name:
        char_name = _resolve_char_name(char_id)
    try:
        with _conn(path) as conn:
            cursor = conn.execute(
                "INSERT INTO mastery_plan (char_id, char_name, skill_index, skill_name, target_level, priority) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (char_id, char_name, skill_index, skill_name, target_level, priority),
            )
            conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"insert_plan failed: {e}")
        return -1


DEFAULT_TARGET_LEVEL = 3  # 与推荐层一致（R-03：推荐恒专三），#65/B7 统一计划创建目标


def add_plan_checked(
    char_id: str,
    skill_index: int,
    target_level: Optional[int] = None,
    skill_name: Optional[str] = None,
    char_name: Optional[str] = None,
    priority: int = 0,
    path: Optional[str] = None,
) -> tuple[int, Optional[str]]:
    """统一计划创建入口（#65/B7）：校验 target_level 范围 + 干员当前等级。

    target_level 缺省 = 专三（与推荐一致，消除「推荐专三、创建专一」分歧）。
    返回 (plan_id, error)：成功 (id>0, None)；拒绝/失败 (<=0, 错误文案)。
    干员当前等级取自 cultivate.json，读不到（文件缺失/干员不在）则跳过该校验——
    执行层已到target检测按截图兜底，#70 档位读失败保守化不回退。
    """
    if target_level is None:
        target_level = DEFAULT_TARGET_LEVEL
    # bool 是 int 子类（True==1），JSON true 不得被当作 target=1 静默接受
    if (
        isinstance(target_level, bool)
        or not isinstance(target_level, int)
        or target_level not in (1, 2, 3)
    ):
        return -1, f"目标专精等级无效: {target_level}（需 1/2/3）"
    from arknights_mower.utils.mastery_recommendation import (
        get_current_mastery_level,
    )

    current_level = get_current_mastery_level(char_id, skill_index)
    if current_level is not None and current_level >= target_level:
        return -1, f"该干员技能已专{current_level}，无需再练到专{target_level}"
    plan_id = insert_plan(
        char_id=char_id,
        skill_index=skill_index,
        target_level=target_level,
        skill_name=skill_name,
        char_name=char_name,
        priority=priority,
        path=path,
    )
    if plan_id > 0:
        return plan_id, None
    return -1, "插入失败"


def get_all_plans(path: Optional[str] = None) -> list[dict]:
    try:
        with _conn(path) as conn:
            rows = conn.execute(
                "SELECT * FROM mastery_plan WHERE status NOT IN ('completed', 'failed') "
                "ORDER BY priority, id"
            ).fetchall()
            return [lazy_fill_plan_names(dict(r), conn) for r in rows]
    except Exception as e:
        logger.error(f"get_all_plans failed: {e}")
        return []


def get_plan_by_id(plan_id: int, path: Optional[str] = None) -> Optional[dict]:
    try:
        with _conn(path) as conn:
            row = conn.execute(
                "SELECT * FROM mastery_plan WHERE id=?", (plan_id,)
            ).fetchone()
            return lazy_fill_plan_names(dict(row), conn) if row else None
    except Exception as e:
        logger.error(f"get_plan_by_id failed: {e}")
        return None


def get_active_plan(path: Optional[str] = None) -> Optional[dict]:
    try:
        with _conn(path) as conn:
            row = conn.execute(
                "SELECT * FROM mastery_plan WHERE status IN ('arranging', 'training', 'waiting_collect') "
                "LIMIT 1"
            ).fetchone()
            return lazy_fill_plan_names(dict(row), conn) if row else None
    except Exception as e:
        logger.error(f"get_active_plan failed: {e}")
        return None


def get_next_idle_plan(path: Optional[str] = None) -> Optional[dict]:
    try:
        with _conn(path) as conn:
            row = conn.execute(
                "SELECT * FROM mastery_plan WHERE status='idle' ORDER BY priority, id LIMIT 1"
            ).fetchone()
            return lazy_fill_plan_names(dict(row), conn) if row else None
    except Exception as e:
        logger.error(f"get_next_idle_plan failed: {e}")
        return None


def get_failed_plans(path: Optional[str] = None) -> list[dict]:
    """failed 状态的计划（含 failed_reason）。

    消费方：① 前端展示失败原因（避免计划"凭空消失"）；② `get_reconcile_plans`
    （#98：reconcile 计划集 = 非终态 + failed，按截图恢复 training——§4 SM-09 的
    「执行循环不含 failed」已随 #98 修改，reconcile 现在能看到 failed）。
    """
    try:
        with _conn(path) as conn:
            rows = conn.execute(
                "SELECT * FROM mastery_plan WHERE status='failed' ORDER BY priority, id"
            ).fetchall()
            return [lazy_fill_plan_names(dict(r), conn) for r in rows]
    except Exception as e:
        logger.error(f"get_failed_plans failed: {e}")
        return []


def get_reconcile_plans(path: Optional[str] = None) -> list[dict]:
    """#98：reconcile 用计划集 = 非终态 + failed（completed 仍排除）。

    此前 get_all_plans 排除 failed → `_match_plan` 永不命中 failed，DB failed 但实际
    在训练时计划状态永不改正（2026-08-16 若叶睦事故）。reconcile 需要看到 failed 以便
    按截图恢复 training；completed 是真正终态（已收取完成），不恢复。按 (priority, id)
    排序——重复计划（同干员技能）时优先高优先级一条，不重复管理。
    """
    plans = get_all_plans(path) + get_failed_plans(path)
    plans.sort(key=lambda p: (p.get("priority", 0), p.get("id", 0)))
    return plans


def update_plan_status(
    plan_id: int,
    status: str,
    failed_reason: Optional[str] = None,
    expires_at: Optional[str] = None,
    swap_frozen: Optional[int] = None,
    path: Optional[str] = None,
) -> bool:
    if status not in VALID_STATUSES:
        logger.error(f"Invalid status: {status}")
        return False
    try:
        with _conn(path) as conn:
            fields = ["status=?"]
            values: list = [status]
            if failed_reason is not None:
                fields.append("failed_reason=?")
                values.append(failed_reason)
            if expires_at is not None:
                fields.append("expires_at=?")
                values.append(expires_at)
            if swap_frozen is not None:
                fields.append("swap_frozen=?")
                values.append(swap_frozen)
            values.append(plan_id)
            conn.execute(
                f"UPDATE mastery_plan SET {', '.join(fields)} WHERE id=?", values
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"update_plan_status failed: {e}")
        return False


def update_plan_priority(
    plan_id: int, priority: int, path: Optional[str] = None
) -> bool:
    try:
        with _conn(path) as conn:
            conn.execute(
                "UPDATE mastery_plan SET priority=? WHERE id=?", (priority, plan_id)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"update_plan_priority failed: {e}")
        return False


def delete_plan(plan_id: int, path: Optional[str] = None) -> bool:
    try:
        with _conn(path) as conn:
            conn.execute("DELETE FROM mastery_plan WHERE id=?", (plan_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"delete_plan failed: {e}")
        return False


def get_all_history(path: Optional[str] = None) -> list[dict]:
    try:
        with _conn(path) as conn:
            rows = conn.execute(
                "SELECT * FROM mastery_plan ORDER BY id DESC LIMIT 200"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_history failed: {e}")
        return []


def is_operator_busy(name_or_id: str, path: Optional[str] = None) -> bool:
    """干员是否被专精占用（arranging/training/waiting_collect）。

    #59：状态集补 waiting_collect（练完没收时干员仍锁在训练室）；
    名/ID 归一化——按 char_id 或 char_name 匹配，NULL char_name 的存量
    计划回退查表（char_name 填充前按名会漏判 → 训练中干员被当空闲挪走）。
    """
    try:
        with _conn(path) as conn:
            rows = conn.execute(
                "SELECT char_id, char_name FROM mastery_plan "
                "WHERE status IN ('arranging', 'training', 'waiting_collect')"
            ).fetchall()
        for row in rows:
            if row["char_id"] == name_or_id or row["char_name"] == name_or_id:
                return True
            if (
                row["char_name"] is None
                and _resolve_char_name(row["char_id"]) == name_or_id
            ):
                return True
        return False
    except Exception:
        return False


def retry_failed_plans(path: Optional[str] = None) -> int:
    """仓库扫描后调用：将 failed 状态的计划重置为 idle，允许重新尝试。返回重置数量。"""
    try:
        with _conn(path) as conn:
            cursor = conn.execute(
                "UPDATE mastery_plan SET status='idle', failed_reason=NULL "
                "WHERE status='failed'"
            )
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.error(f"retry_failed_plans failed: {e}")
        return 0


# --- 通知去重（#61：仅三类各一次） ---


def should_notify(notify_type: str, dedup_key: str, path: Optional[str] = None) -> bool:
    """某类型通知的 (type, dedup_key) 是否尚未发过；首次为 True 并落库去重。

    dedup_key：① 用倒计时结束时刻（训练未变不重发）；②③ 用 plan id。
    """
    try:
        with _conn(path) as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO mastery_notify (notify_type, dedup_key) VALUES (?, ?)",
                (notify_type, dedup_key),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"should_notify failed: {e}")
        return True


# --- Route CRUD ---


def save_route(
    profession: str,
    supports_json: str,
    is_default: int = 0,
    optimal: bool = False,
    half_off: bool = True,
    path: Optional[str] = None,
):
    try:
        with _conn(path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mastery_route "
                "(profession, supports, is_default, optimal, half_off) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    profession,
                    supports_json,
                    is_default,
                    int(optimal),
                    int(half_off),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"save_route failed: {e}")


# 全局路线设置的保留职业行（#91 修订）：中枢加成 + 换人缓冲时间，存 supports JSON。
# 归在「路线配置」里——DB 管理删「专精路线配置」会一起清掉（回默认）；get_all_routes 排除。
_SETTINGS_PROFESSION = "__mastery_settings__"
_SETTINGS_DEFAULTS = {"central_bonus": 0, "mastery_swap_buffer": 10}


def get_route_settings(path: Optional[str] = None) -> dict:
    """全局路线设置：central_bonus（0/5）+ mastery_swap_buffer（分钟）。

    存 `mastery_route` 保留行（_SETTINGS_PROFESSION 的 supports JSON），缺行回默认
    (0, 10)。不再走 conf（旧 `mastery_control_center`/`mastery_swap_buffer` 已废弃）。
    """
    defaults = dict(_SETTINGS_DEFAULTS)
    try:
        with _conn(path) as conn:
            row = conn.execute(
                "SELECT * FROM mastery_route WHERE profession=? AND is_default=0",
                (_SETTINGS_PROFESSION,),
            ).fetchone()
            if row:
                try:
                    parsed = json.loads(row["supports"])
                except (TypeError, ValueError):
                    parsed = {}
                if isinstance(parsed, dict):
                    defaults.update({k: parsed[k] for k in defaults if k in parsed})
    except Exception as e:
        logger.error(f"get_route_settings failed: {e}")
    return defaults


def save_route_settings(
    central_bonus: int = 0,
    mastery_swap_buffer: int = 10,
    path: Optional[str] = None,
):
    try:
        payload = json.dumps(
            {
                "central_bonus": int(central_bonus),
                "mastery_swap_buffer": int(mastery_swap_buffer),
            },
            ensure_ascii=False,
        )
        with _conn(path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mastery_route "
                "(profession, supports, is_default) VALUES (?, ?, 0)",
                (_SETTINGS_PROFESSION, payload),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"save_route_settings failed: {e}")


def get_route(profession: str, path: Optional[str] = None) -> Optional[dict]:
    try:
        with _conn(path) as conn:
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


def get_all_routes(path: Optional[str] = None) -> list[dict]:
    try:
        with _conn(path) as conn:
            rows = conn.execute(
                "SELECT * FROM mastery_route WHERE profession != ? ORDER BY profession",
                (_SETTINGS_PROFESSION,),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_routes failed: {e}")
        return []
