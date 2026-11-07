"""数据库管理接口（运行日志页「数据库管理」卡片）。

按白名单类**删行**（DELETE FROM），**绝不允许 DROP TABLE**——建表守卫进程内只跑
一次（`_tables_created` 按库路径记），被 DROP 的表不会被重建，下次读写即 no-such-table。
删除只影响行数据，不动表结构。表白名单硬编码，未知键直接拒绝（防注入 + 防误删其它表）。
"""

import sqlite3
from contextlib import nullcontext
from time import monotonic

from flask import Blueprint, abort, current_app, request

from arknights_mower.solvers import record
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils.config import gui
from arknights_mower.utils.log import logger
from arknights_mower.utils.web_auth import origin_allowed, require_token
from arknights_mower.views.mastery import _purge_plan_tasks

db_admin_bp = Blueprint("db_admin", __name__)

# 可删除的「类」白名单：前端展示 key → 表名。所有表都在同一个 data.db 文件里
# （record 与 mastery 共用 @app/tmp/data.db）。
CATEGORY_TABLES = {
    # 全自动专精
    "mastery_plan": "mastery_plan",  # 专精计划
    "mastery_route": "mastery_route",  # 专精路线配置
    "mastery_notify": "mastery_notify",  # 专精通知记录
    # 运行数据
    "log": "log",  # 运行日志
    "agent_action": "agent_action",  # 干员心情记录
    "operation_history": "operation_history",  # 作战记录
    "trading_history": "trading_history",  # 交易历史
    "inventory": "inventory",  # 仓库库存
    "saved_state": "saved_state",  # 运行缓存（重启续传书签）
}

# 「正在练」的专精计划状态集（与 mastery_db 的 active 集合一致：is_operator_busy / get_active_plan）
_ACTIVE_PLAN_STATUSES = ("arranging", "training", "waiting_collect")


def _count(conn, table):
    """统计某表行数；表尚未创建（全新安装从未用过该模块）→ 按 0 处理。"""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


@db_admin_bp.route("/db-admin/stats", methods=["GET"])
@require_token
def stats():
    """返回每类可删数据的行数（SELECT COUNT(*)，几乎零成本）。"""
    counts = {}
    try:
        with record._conn() as conn:
            for key, table in CATEGORY_TABLES.items():
                counts[key] = _count(conn, table)
            # 专精计划额外带 active（正在练）数量，供前端删除前警告
            active = 0
            try:
                active = conn.execute(
                    f"SELECT COUNT(*) FROM mastery_plan WHERE status IN "
                    f"({', '.join('?' * len(_ACTIVE_PLAN_STATUSES))})",
                    _ACTIVE_PLAN_STATUSES,
                ).fetchone()[0]
            except Exception:
                pass  # 表尚未创建（全新安装）→ active 按 0
            counts["mastery_plan_active"] = active
    except Exception as e:
        logger.error(f"db-admin stats 失败: {e}")
        return {"error": str(e)}, 500
    return counts


@db_admin_bp.route("/db-admin/delete", methods=["POST"])
@require_token
def delete():
    """按白名单类删行（DELETE FROM，绝不 DROP TABLE）。返回各类实际删除的行数。"""
    data = request.get_json(silent=True) or {}
    keys = data.get("categories") or []
    if not isinstance(keys, list) or not keys:
        return {"error": "categories 不能为空"}, 400
    invalid = [k for k in keys if k not in CATEGORY_TABLES]
    if invalid:
        return {"error": f"未知类别: {invalid}"}, 400
    deleted = {}
    plan_ids = []
    try:
        with record._conn() as conn:
            if "mastery_plan" in keys:
                # 批量删计划后清掉队列里的残留任务（plan_key=旧id 的
                # SKILL_UPGRADE/SWAP 照常派发到已删计划），先记下要删的 id
                try:
                    plan_ids = [
                        r[0] for r in conn.execute("SELECT id FROM mastery_plan")
                    ]
                except Exception:
                    plan_ids = []  # 表未创建 → 无数据可删，也无任务可清
            for key in keys:
                table = CATEGORY_TABLES[key]  # 白名单校验过，表名安全
                try:
                    cur = conn.execute(f"DELETE FROM {table}")
                    deleted[key] = cur.rowcount
                except Exception as e:
                    # 表尚未创建（全新安装）→ 本就无数据可删，按 0 处理
                    logger.debug(f"db-admin delete {table}: {e}")
                    deleted[key] = 0
            conn.commit()
    except Exception as e:
        logger.error(f"db-admin delete 失败: {e}")
        return {"error": str(e)}, 500
    for pid in plan_ids:
        _purge_plan_tasks(pid)
    logger.info(f"[db-admin] 删除 {len(keys)} 类数据 {deleted}")
    return {"deleted": deleted}


def _database_size(conn):
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    pages = conn.execute("PRAGMA page_count").fetchone()[0]
    free = conn.execute("PRAGMA freelist_count").fetchone()[0]
    return {"database_bytes": pages * page_size, "reclaimable_bytes": free * page_size}


def _maintenance_status():
    with record._conn() as conn:
        size = _database_size(conn)
    busy = current_app.config.get(
        "CONFIG_PROFILES_BUSY",
        current_app.config.get("CONFIG_BACKUP_BUSY", lambda: False),
    )()
    return {
        **size,
        "backup_limit_mib": backup.get_backup_limit_bytes() // (1024 * 1024),
        "max_backup_limit_mib": backup.MAX_BACKUP_LIMIT_MIB,
        "busy": bool(busy),
    }


def _compact_database():
    with record._conn() as conn:
        deadline = monotonic() + 60
        conn.execute("PRAGMA busy_timeout=5000")
        conn.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
        try:
            if conn.execute("PRAGMA integrity_check(1)").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("数据库完整性检查未通过，未执行整理")
            before = _database_size(conn)["database_bytes"]
            conn.execute("VACUUM")
            # WAL databases retain vacuum output until the checkpoint finishes.
            if conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise sqlite3.OperationalError("数据库仍被占用，未完成空间回收")
            after = _database_size(conn)["database_bytes"]
            return {"before_bytes": before, "after_bytes": after}
        finally:
            conn.set_progress_handler(None, 0)


def _maintenance(action=None):
    if action is not None:
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and not origin_allowed(origin):
            abort(403)
    factory = current_app.config.get("CONFIG_PROFILES_LOCKS")
    locks = (
        factory()
        if factory
        else current_app.config.get("CONFIG_BACKUP_MAINTENANCE_LOCK", nullcontext())
    )
    try:
        with backup.backup_lock, locks:
            status = _maintenance_status()
            if action is None:
                return {"ok": True, **status}
            if status["busy"]:
                return {
                    "message": "请先停止 Mower，并等待设备操作、更新任务、AI 回复和回收站上报结束"
                }, 409
            result = action()
            return {"ok": True, **_maintenance_status(), **result}
    except ValueError as exc:
        return {"message": str(exc)}, 400
    except (OSError, sqlite3.Error) as exc:
        logger.exception("数据库维护失败")
        return {
            "message": f"数据库维护未完成：{exc}。请检查数据库占用、磁盘空间和目录权限后重试"
        }, 503


@db_admin_bp.get("/db-admin/maintenance")
@require_token
def maintenance_status():
    return _maintenance()


@db_admin_bp.post("/db-admin/compact")
@require_token
def compact():
    return _maintenance(_compact_database)


@db_admin_bp.put("/db-admin/backup-limit")
@require_token
def set_backup_limit():
    def save():
        body = request.get_json(silent=True)
        value = body.get("backup_limit_mib") if isinstance(body, dict) else None
        if type(value) is not int or not 1 <= value <= backup.MAX_BACKUP_LIMIT_MIB:
            raise ValueError(
                f"备份大小上限需要是 1 至 {backup.MAX_BACKUP_LIMIT_MIB} MiB 的整数"
            )
        gui.update_gui_data(lambda data: data.update(backup_limit_mib=value))
        return {}

    return _maintenance(save)
