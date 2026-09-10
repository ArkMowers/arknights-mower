"""Versioned, data-only backups of the current instance and shared settings."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import config, network_settings, update_runtime
from arknights_mower.utils.config.conf import RegularTaskPart
from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager
from arknights_mower.utils.github_download import normalize_proxy
from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_config import workshop_lock

FORMAT = "arknights-mower-config"
VERSION = 1
MAX_BACKUP_BYTES = 16 * 1024 * 1024
backup_lock = RLock()
MASTERY_TABLES = ("mastery_plan", "mastery_route")
BROWSER_SETTINGS = {
    "sc_preview",
    "reportDataOrder",
    "maa-weekly-plan-editor-mode",
    "maa-weekly-plan-table-stage-order",
    "maa-weekly-plan-table-stage-order-version",
}


def configuration_paths():
    # Fixed destinations: a backup never supplies filesystem paths or SQL.
    return {
        "conf": config.conf_path,
        "plan": config.plan_path,
        "weekly_plans": config.weekly_plans_path,
        "state": config.app_state_path,
        "gui": config.gui_path,
        "network": network_settings.settings_path(),
        "software_update": update_runtime.state_dir() / "settings.json",
        "skland_device_id": get_path("@app/config/skland_device_id.json", space=""),
        "sss": get_path("@app/sss.json"),
        "workshop_preset": get_path("@app/tmp/workshop_preset.json"),
    }


def _read(path):
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return (
        yaml.load(text, Loader=CoreLoader)
        if path.suffix == ".yml"
        else json.loads(text)
    )


def _mastery_snapshot():
    path = get_path("@app/tmp/data.db")
    result = {table: [] for table in MASTERY_TABLES}
    if not path.exists():
        return result
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in MASTERY_TABLES:
            if table in tables:
                result[table] = [
                    dict(row) for row in conn.execute(f"SELECT * FROM {table}")
                ]
        return result
    finally:
        conn.close()


def export_configuration():
    with backup_lock, workshop_lock:
        data = {name: _read(path) for name, path in configuration_paths().items()}
        # Include defaults and fields which have no control in the web UI.
        data["conf"] = {**(data["conf"] or {}), **config.conf.model_dump(mode="json")}
        data["plan"] = {
            **(data["plan"] or {}),
            **config.plan.model_dump(mode="json", exclude_none=True),
        }
        data["mastery"] = _mastery_snapshot()
        return {
            "format": FORMAT,
            "version": VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }


def serialize_backup(backup):
    return json.dumps(backup, ensure_ascii=False, indent=2, allow_nan=False)


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是对象")
    return value


def validate_configuration(backup):
    _object(backup, "备份")
    if (
        backup.get("format") != FORMAT
        or type(backup.get("version")) is not int
        or backup["version"] != VERSION
    ):
        raise ValueError("不是受支持的 Mower 完整配置备份（需要版本 1）")
    data = _object(backup.get("data"), "备份内容")
    for key in ("browser_settings", "current_browser_settings"):
        settings = _object(backup.get(key, {}), "页面偏好")
        if not set(settings) <= BROWSER_SETTINGS or any(
            value is not None and not isinstance(value, str)
            for value in settings.values()
        ):
            raise ValueError("页面偏好格式错误")
    if set(data) != {*configuration_paths(), "mastery"}:
        raise ValueError("备份配置项目不完整或包含不支持的项目")
    # Reject non-JSON values, NaN and oversized backups before touching storage.
    if len(serialize_backup(backup).encode("utf-8")) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 16 MB")
    conf = config.Conf(**_object(data["conf"], "主配置"))
    plan = config.PlanModel(**_object(data["plan"], "排班配置"))
    for name in (
        "state",
        "gui",
        "network",
        "software_update",
        "skland_device_id",
        "sss",
    ):
        if data[name] is not None:
            _object(data[name], name)
    if data["workshop_preset"] is not None and not isinstance(
        data["workshop_preset"], (dict, list)
    ):
        raise ValueError("加工站预设格式错误")
    state = data["state"] or {}
    if "active_weekly_plan" in state and not isinstance(
        state["active_weekly_plan"], str
    ):
        raise ValueError("当前周计划名称必须是字符串")
    if data["weekly_plans"] is not None:
        weekly = _object(data["weekly_plans"], "周计划")
        plans = _object(weekly.get("plans"), "周计划方案")
        for name, entries in plans.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(entries, list)
            ):
                raise ValueError("周计划名称或内容格式错误")
            for entry in entries:
                RegularTaskPart.MaaDailyPlan(**_object(entry, "周计划条目"))
        for name, rules in _object(
            weekly.get("inventory_configs", {}), "库存选关配置"
        ).items():
            WeeklyPlanManager._normalize_inventory_config(_object(rules, name))
        for key in (
            "activity_fallbacks",
            "activity_fallback_end_times",
            "activity_fallback_switch_times",
        ):
            for value in _object(weekly.get(key, {}), key).values():
                if key == "activity_fallbacks":
                    if not isinstance(value, str):
                        raise ValueError("活动回退方案必须是字符串")
                elif type(value) is not int or value < 0:
                    raise ValueError("活动切换时间必须是非负整数")
    if data["network"] is not None:
        network_settings.normalize_http_proxy(data["network"].get("http_proxy", ""))
        normalize_proxy(data["network"].get("github_proxy", ""))
    if data["software_update"] is not None:
        update = data["software_update"]
        if update.get("channel", "stable") not in {"stable", "beta", "dev"}:
            raise ValueError("软件更新渠道无效")
        for key in ("background", "auto_check", "auto_update"):
            if key in update and not isinstance(update[key], bool):
                raise ValueError("软件更新开关必须是布尔值")
        if "source_branch" in update:
            from arknights_mower.utils.software_update import normalize_source_ref

            normalize_source_ref(update["source_branch"])
    mastery = _object(data["mastery"], "专精配置")
    if set(mastery) != set(MASTERY_TABLES):
        raise ValueError("专精配置不完整")
    # Validate table columns and constraints in an isolated, empty database.
    from arknights_mower.utils.mastery_db import _PLAN_SCHEMA, _ROUTE_SCHEMA

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(_PLAN_SCHEMA)
        conn.execute(_ROUTE_SCHEMA)
        _replace_mastery(conn, mastery)
    except sqlite3.Error as exc:
        raise ValueError("专精配置的字段或数据格式错误") from exc
    finally:
        conn.close()
    return conf, plan


def _replace_mastery(conn, mastery):
    for table in MASTERY_TABLES:
        rows = mastery[table]
        if not isinstance(rows, list):
            raise ValueError("专精配置必须是列表")
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        conn.execute(f"DELETE FROM {table}")
        for row in rows:
            _object(row, "专精配置条目")
            if not row or not set(row) <= set(columns):
                raise ValueError("专精配置包含不支持的字段")
            selected = [column for column in columns if column in row]
            conn.execute(
                f"INSERT INTO {table} ({','.join(selected)}) VALUES ({','.join('?' for _ in selected)})",
                [row[column] for column in selected],
            )


def import_configuration(backup):
    conf, plan = validate_configuration(backup)
    from arknights_mower.utils.mastery_db import _conn

    with backup_lock, workshop_lock:
        paths = configuration_paths()
        previous = {
            name: path.read_text(encoding="utf-8") if path.exists() else None
            for name, path in paths.items()
        }
        recovery = (
            get_path("@app/config-backups")
            / f"before-import-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.json"
        )
        previous_backup = export_configuration()
        previous_backup["browser_settings"] = backup.get("current_browser_settings", {})
        config.atomic_write(
            recovery, lambda f: f.write(serialize_backup(previous_backup))
        )
        written = []
        # Preserve reports and inventory; stale scheduler snapshots refer to the
        # replaced plans and must be rebuilt on the next start.
        database_path = get_path("@app/tmp/data.db")
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with _conn(str(database_path)) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _replace_mastery(conn, backup["data"]["mastery"])
                if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='saved_state'"
                ).fetchone():
                    conn.execute("DELETE FROM saved_state")
                for name, path in paths.items():
                    value = backup["data"][name]
                    if value is None:
                        path.unlink(missing_ok=True)
                    else:
                        # JSON is also valid YAML; preserve every original key.
                        text = json.dumps(
                            value, ensure_ascii=False, indent=2, allow_nan=False
                        )
                        config.atomic_write(path, lambda f, text=text: f.write(text))
                    written.append(name)
                conn.commit()
            except Exception:
                conn.rollback()
                for name in reversed(written):
                    old = previous[name]
                    if old is None:
                        paths[name].unlink(missing_ok=True)
                    else:
                        config.atomic_write(
                            paths[name], lambda f, old=old: f.write(old)
                        )
                raise
        config.conf, config.plan = conf, plan
        if scheduler_module := sys.modules.get("arknights_mower.__main__"):
            scheduler_module.base_scheduler = None
        if skland_module := sys.modules.get("arknights_mower.utils.skland"):
            skland_module.skland_cache.clear()
            skland_module._device_id = ""
            skland_module._device_id_failed = False
        network_settings.apply_http_proxy()
        return str(recovery)
