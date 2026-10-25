"""Combine selected settings and persistent data from bounded configuration ZIPs."""

import copy
import json
import re
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import yaml

from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils.config.plan import has_retired_dorm_options
from arknights_mower.utils.config.plan_advanced import export_advanced_settings
from arknights_mower.utils.config_profile_groups import (
    CONF_GROUPS,
    CONFIG_FILE_GROUPS,
    GROUPS,
)

WEEKLY_SELECTION_FILE = "profile-weekly.json"
TABLE_GROUPS = {
    "inventory": "inventory",
    "workshop_inventory_updates": "inventory",
    "workshop_inventory_pending": "inventory",
    "mastery_inventory_consumption": "inventory",
    "mastery_plan": "mastery",
    "mastery_notify": "mastery",
    "mastery_route": "mastery_routes",
    "agent_action": "mood_history",
    "trading_history": "trading_history",
    "operation_history": "operation_history",
    "recycling_collection": "recycling_history",
    "recycling_report_progress": "recycling_history",
    "recycling_valuation": "recycling",
    "log": "other_history",
}
TMP_GROUPS = {
    "growth_history.json": "growth_history",
    "depotresult.csv": "inventory",
    "depotmerged.csv": "inventory",
    "report.csv": "report_history",
    "skland.csv": "skland_history",
}
_SAFE_FUNCTIONS = {
    "abs",
    "coalesce",
    "date",
    "datetime",
    "ifnull",
    "julianday",
    "length",
    "like",
    "lower",
    "max",
    "min",
    "round",
    "strftime",
    "substr",
    "substring",
    "time",
    "trim",
    "typeof",
    "unixepoch",
    "upper",
}


def validate_groups(selected):
    if not isinstance(selected, list) or any(
        not isinstance(key, str) for key in selected
    ):
        raise ValueError("请选择需要保留的配置项目")
    if len(selected) != len(set(selected)) or set(selected) - {
        g["key"] for g in GROUPS
    }:
        raise ValueError("配置项目无效，请刷新页面后重试")
    return set(selected)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _database_connection(path, deadline, *, readonly=False):
    conn = sqlite3.connect(
        f"{path.as_uri()}?mode=ro" if readonly else path,
        uri=readonly,
        timeout=1,
    )
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, backup.MAX_BACKUP_BYTES)
    conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, backup.MAX_BACKUP_BYTES)
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    conn.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
    return conn


def _database_schema(conn):
    rows = conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    if any(kind in {"view", "trigger"} for kind, *_ in rows):
        raise ValueError("配置数据库不支持视图或触发器")
    if any(
        row[2] in {"virtual", "shadow"} for row in conn.execute("PRAGMA table_list")
    ):
        raise ValueError("配置数据库不支持虚拟表")
    tables = {
        name: sql
        for kind, name, _, sql in rows
        if kind == "table"
        and not name.casefold().startswith("sqlite_")
        and name.casefold() != "saved_state"
    }
    indexes = [
        (name, owner, sql)
        for kind, name, owner, sql in rows
        if kind == "index" and sql is not None
    ]
    return tables, indexes


def _schema_statement(conn, sql, *, table, index=None):
    expected = sqlite3.SQLITE_CREATE_INDEX if index else sqlite3.SQLITE_CREATE_TABLE

    def authorize(action, first, second, database, source):
        if database not in {None, "main"} or source is not None:
            return sqlite3.SQLITE_DENY
        if action == expected:
            allowed = (
                first == (index or table) and (index is None or second == table)
            ) or (index is None and first == "sqlite_sequence")
        elif action in {
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_READ,
        }:
            allowed = first in {"sqlite_master", "sqlite_sequence", table}
        elif action == sqlite3.SQLITE_FUNCTION:
            allowed = second in _SAFE_FUNCTIONS
        elif action == sqlite3.SQLITE_CREATE_TABLE:
            allowed = first == "sqlite_sequence"
        elif action == sqlite3.SQLITE_CREATE_INDEX:
            allowed = second == table and first.startswith("sqlite_autoindex_")
        elif action == sqlite3.SQLITE_REINDEX:
            allowed = first == index
        else:
            allowed = False
        return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY

    if not isinstance(sql, str) or not re.match(
        r"\ACREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\b", sql, re.I
    ):
        raise ValueError("配置数据库包含不支持的表结构")
    conn.set_authorizer(authorize)
    try:
        conn.execute(sql)
    finally:
        conn.set_authorizer(None)


def merge_databases(incoming, current, selected):
    """Copy complete ordinary tables under one deadline without executing triggers."""
    if incoming is None and current is None:
        return None
    deadline = monotonic() + 10
    try:
        with TemporaryDirectory() as directory, ExitStack() as stack:
            directory = Path(directory)
            sources, schemas = {}, {}
            for key, content in (("incoming", incoming), ("current", current)):
                if content is None:
                    continue
                if len(content) > backup.MAX_BACKUP_BYTES or not content.startswith(
                    b"SQLite format 3\x00"
                ):
                    raise ValueError("配置中的 data.db 不是有效的 SQLite 数据库")
                path = directory / f"{key}.db"
                path.write_bytes(content)
                conn = stack.enter_context(
                    closing(_database_connection(path, deadline, readonly=True))
                )
                if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ValueError("配置数据库完整性校验失败")
                sources[key], schemas[key] = conn, _database_schema(conn)
            target = directory / "combined.db"
            writer = stack.enter_context(
                closing(_database_connection(target, deadline))
            )
            writer.execute("PRAGMA user_version=0")
            chosen = {}
            for key, (tables, _) in schemas.items():
                for name in tables:
                    group = TABLE_GROUPS.get(name.casefold(), "other_history")
                    if (key == "current") == (group in selected):
                        chosen[name] = key
            with writer:
                for name, key in sorted(chosen.items()):
                    if monotonic() >= deadline:
                        raise ValueError("配置数据库合并超时，请缩小数据量后重试")
                    reader = sources[key]
                    _schema_statement(writer, schemas[key][0][name], table=name)
                    information = reader.execute(
                        f"PRAGMA table_xinfo({_quote(name)})"
                    ).fetchall()
                    columns = [row[1] for row in information if row[6] == 0]
                    without_rowid = next(
                        row[4]
                        for row in reader.execute("PRAGMA table_list")
                        if row[1] == name
                    )
                    if not without_rowid:
                        existing_columns = {row[1].casefold() for row in information}
                        rowid = next(
                            (
                                alias
                                for alias in ("_rowid_", "rowid", "oid")
                                if alias not in existing_columns
                            ),
                            None,
                        )
                        if rowid is not None:
                            columns.insert(0, rowid)
                    names = ", ".join(map(_quote, columns))
                    placeholders = ", ".join("?" for _ in columns)
                    cursor = reader.execute(f"SELECT {names} FROM {_quote(name)}")
                    while rows := cursor.fetchmany(256):
                        writer.executemany(
                            f"INSERT INTO {_quote(name)} ({names}) VALUES ({placeholders})",
                            rows,
                        )
                        if (
                            writer.execute("PRAGMA page_count").fetchone()[0]
                            * writer.execute("PRAGMA page_size").fetchone()[0]
                            > backup.MAX_BACKUP_BYTES
                        ):
                            raise ValueError("合并后的配置数据库不能超过 16 MB")
                    for index, owner, sql in schemas[key][1]:
                        if owner == name:
                            _schema_statement(writer, sql, table=name, index=index)
                    if (
                        reader.execute(
                            "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'"
                        ).fetchone()
                        and writer.execute(
                            "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'"
                        ).fetchone()
                    ):
                        row = reader.execute(
                            "SELECT seq FROM sqlite_sequence WHERE name=?", (name,)
                        ).fetchone()
                        if row is not None:
                            writer.execute(
                                "DELETE FROM sqlite_sequence WHERE name=?", (name,)
                            )
                            writer.execute(
                                "INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)",
                                (name, row[0]),
                            )
            content = target.read_bytes()
            if len(content) > backup.MAX_BACKUP_BYTES:
                raise ValueError("合并后的配置数据库不能超过 16 MB")
            return content
    except sqlite3.Error as exc:
        raise ValueError("配置数据库无法安全合并，请检查备份内容") from exc


def _merge_cultivate(incoming, current, selected):
    if incoming is None and current is None:
        return None
    sources = []
    for content in (incoming, current):
        value = json.loads(content.decode("utf-8-sig")) if content is not None else {}
        if (
            not isinstance(value, dict)
            or value.get("code", 0) != 0
            or ("data" in value and not isinstance(value["data"], dict))
        ):
            raise ValueError("干员与库存快照格式错误")
        sources.append(value)
    result = {}
    for index, source in enumerate(sources):
        for key, value in source.items():
            if key == "data":
                continue
            group = (
                "inventory" if key == "_mower_inventory_observed_at" else "operators"
            )
            if (index == 1) == (group in selected):
                result[key] = copy.deepcopy(value)
        for key, value in source.get("data", {}).items():
            group = "inventory" if key == "items" else "operators"
            if (index == 1) == (group in selected):
                result.setdefault("data", {})[key] = copy.deepcopy(value)
    if result:
        data = result.setdefault("data", {})
        data.setdefault("items", [])
        return _json_bytes(result)
    return None


def default_archive():
    files = {
        "conf.yml": yaml.safe_dump(
            config.Conf(device={}).model_dump(), allow_unicode=True, sort_keys=False
        ).encode("utf-8"),
        "plan.json": _json_bytes(config.PlanModel().model_dump(exclude_none=True)),
        WEEKLY_SELECTION_FILE: _json_bytes({"active_weekly_plan": ""}),
    }
    return backup._archive_bytes(files, {})


def combine_archives(incoming_raw, current_raw, selected):
    selected = validate_groups(list(selected))
    incoming, incoming_tmp = backup.read_archive(incoming_raw, include_tmp=True)
    current, current_tmp = backup.read_archive(current_raw, include_tmp=True)
    for files, tmp in ((incoming, incoming_tmp), (current, current_tmp)):
        for name in backup.LEGACY_TMP_CONFIG_FILES:
            if name not in files and name in tmp:
                if any(path.casefold() == name for path in files):
                    raise ValueError("持久化配置文件名大小写冲突")
                files[name] = tmp[name]
            tmp.pop(name, None)
        data, conf, plan, migrated, rescue_plan = backup._validate_configuration(files)
        # Resolve legacy-derived fields and defaults in their source configuration.
        # Original values retain unknown nested fields while new keys come from Conf.
        data = {**conf.model_dump(), **data}
        if migrated or has_retired_dorm_options(
            backup._object_file(files, "plan.json")
        ):
            files["plan.json"] = _json_bytes(plan.model_dump(exclude_none=True))
        data.pop("dorm_order", None)
        if "rescue_plan.json" not in files:
            if any(name.casefold() == "rescue_plan.json" for name in files):
                raise ValueError("救急排班文件名必须为 rescue_plan.json")
            files["rescue_plan.json"] = _json_bytes(
                rescue_plan.model_dump(exclude_none=True)
            )
        data.pop("automatic_rescue_plan", None)
        files["conf.yml"] = yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False
        ).encode("utf-8")
    configs = [backup._object_file(files, "conf.yml") for files in (incoming, current)]
    field_groups = {
        field: group for group, fields in CONF_GROUPS.items() for field in fields
    }
    merged = {}
    for index, data in enumerate(configs):
        for key, value in data.items():
            group = field_groups.get(key, "other_settings")
            if (index == 1) == (group in selected):
                merged[key] = copy.deepcopy(value)
    merged["ai_assistant_enabled"] = config.conf.ai_assistant_enabled
    merged.pop("updates_enabled", None)
    merged["extra_settings_visible"] = config.conf.extra_settings_visible
    webview = merged.setdefault("webview", {})
    if not isinstance(webview, dict):
        raise ValueError("窗口设置格式错误")
    for key in ("port", "token", "tray"):
        webview[key] = getattr(config.conf.webview, key)
    files = {}
    for index, source in enumerate((incoming, current)):
        for name, content in source.items():
            if name == "conf.yml" or name.casefold() in backup.IMPORT_PRESERVED_FILES:
                continue
            group = (
                "weekly_plan"
                if name == WEEKLY_SELECTION_FILE
                else CONFIG_FILE_GROUPS.get(name, "other_settings")
            )
            if (index == 1) == (group in selected):
                files[name] = content
    for name in backup.IMPORT_PRESERVED_FILES - {"state.json"}:
        if name in current:
            files[name] = current[name]
    files["conf.yml"] = yaml.safe_dump(
        merged, allow_unicode=True, sort_keys=False
    ).encode("utf-8")
    # The ordinary Scheduling Plan and its conditional backups share one document.
    files.setdefault("plan.json", default_plan_bytes())
    plan = backup._object_file(files, "plan.json")
    plan["advanced_settings"] = export_advanced_settings(config.Conf(**merged))
    files["plan.json"] = _json_bytes(plan)
    tmp = {}
    for index, source in enumerate((incoming_tmp, current_tmp)):
        for name, content in source.items():
            if name in {"data.db", "cultivate.json"}:
                continue
            if (index == 1) == (TMP_GROUPS[name] in selected):
                tmp[name] = content
    database = merge_databases(
        incoming_tmp.get("data.db"), current_tmp.get("data.db"), selected
    )
    if database is not None:
        tmp["data.db"] = database
    cultivate = _merge_cultivate(
        incoming_tmp.get("cultivate.json"), current_tmp.get("cultivate.json"), selected
    )
    if cultivate is not None:
        tmp["cultivate.json"] = cultivate
    total = sum(map(len, files.values())) + sum(map(len, tmp.values()))
    if total > backup.MAX_BACKUP_BYTES:
        raise ValueError("合并后的配置和数据不能超过 16 MB")
    raw = backup._archive_bytes(files, tmp)
    backup._validate_configuration(files)
    return raw


def default_plan_bytes():
    return _json_bytes(config.PlanModel().model_dump(exclude_none=True))
