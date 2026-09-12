"""Back up and restore the current instance's config directory as a ZIP."""

import json
import sqlite3
import stat
import sys
from contextlib import closing, nullcontext
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from threading import RLock
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from zlib import error as ZlibError

import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RegularTaskPart
from arknights_mower.utils.config.plan import parse_plan_document
from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_config import workshop_lock

MAX_BACKUP_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1024
backup_lock = RLock()
IMPORT_PRESERVED_FILES = {"network.json", "gui.yml", "state.json"}


class LocalConfigError(ValueError):
    """The destination directory cannot be backed up safely."""


EXPORT_EXCLUDED_FILES = {"state.json"}


def _local_snapshot():
    """Read originals and index file/directory names with one directory walk."""
    root = config.conf_path.parent
    files, names = {}, {}
    total = 0
    if root.is_symlink():
        raise LocalConfigError("本机 config 目录是符号链接，请改用普通目录后重试")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise LocalConfigError("本机 config 目录包含符号链接，请移除链接后重试")
        name = path.relative_to(root).as_posix()
        names[name.casefold()] = name
        if not path.is_file() or name.casefold() in EXPORT_EXCLUDED_FILES:
            continue
        if len(files) >= MAX_ARCHIVE_ENTRIES:
            raise LocalConfigError("本机配置文件数量超过 1024 个，请整理后重试")
        with path.open("rb") as stream:
            content = stream.read(MAX_BACKUP_BYTES - total + 1)
        total += len(content)
        if total > MAX_BACKUP_BYTES:
            raise LocalConfigError("本机配置内容超过 16 MB，无法生成备份")
        files[name] = content
    return files, names


def _archive_bytes(files):
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("config/", b"")
        for name, content in files.items():
            archive.writestr(f"config/{name}", content)
    raw = output.getvalue()
    if len(raw) > MAX_BACKUP_BYTES:
        raise LocalConfigError("本机配置生成的 ZIP 超过 16 MB，无法导出或生成恢复备份")
    return raw


def _write_bytes(path, content):
    config.atomic_write(path, lambda stream: stream.buffer.write(content))


def export_archive():
    with backup_lock, workshop_lock:
        files, _ = _local_snapshot()
        return _archive_bytes(files)


def read_archive(raw):
    """Read bounded regular files without extracting ZIP paths to the filesystem."""
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 16 MB")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES + sum(
                info.filename == "config/" for info in infos
            ):
                raise ValueError("压缩包文件数量过多")
            if sum(info.file_size for info in infos) > MAX_BACKUP_BYTES:
                raise ValueError("解压后的配置不能超过 16 MB")
            files, seen, kinds = {}, set(), {}
            for info in infos:
                name = info.filename
                parts = name.rstrip("/").split("/")
                mode = info.external_attr >> 16
                if (
                    name.rstrip("/").casefold() in seen
                    or "\\" in name
                    or any(
                        part in {"", ".", ".."}
                        or any(c in part for c in ':<>"|?*')
                        or any(ord(c) < 32 for c in part)
                        or part.endswith((" ", "."))
                        or part.split(".")[0].upper()
                        in {
                            "CON",
                            "PRN",
                            "AUX",
                            "NUL",
                            *(f"COM{i}" for i in range(1, 10)),
                            *(f"LPT{i}" for i in range(1, 10)),
                        }
                        for part in parts
                    )
                    or parts[0] != "config"
                    or (
                        len(parts) > 2 and parts[1].casefold() in IMPORT_PRESERVED_FILES
                    )
                    or info.flag_bits & 1
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                    or "\x00" in info.orig_filename
                ):
                    raise ValueError("压缩包包含无效路径、重复文件或链接")
                seen.add(name.rstrip("/").casefold())
                for index in range(1, len(parts) + 1):
                    path = "/".join(parts[:index])
                    key = path.casefold()
                    is_dir = index < len(parts) or info.is_dir()
                    if key in kinds and kinds[key] != (path, is_dir):
                        raise ValueError("压缩包中的文件与目录或大小写冲突")
                    kinds[key] = (path, is_dir)
                if info.is_dir():
                    continue
                if len(parts) < 2:
                    raise ValueError("配置文件必须位于 config 目录内")
                relative = PurePosixPath(*parts[1:]).as_posix()
                files[relative] = archive.read(info)
            # Also reject file/directory collisions before any writes.
            for name in files:
                if any(
                    parent.as_posix() in files for parent in PurePosixPath(name).parents
                ):
                    raise ValueError("压缩包中的文件与目录冲突")
            return files
    except (BadZipFile, RuntimeError, NotImplementedError, ZlibError) as exc:
        raise ValueError("请选择包含 config 文件夹的 ZIP 备份") from exc


def _object_file(files, name, *, optional=False):
    if optional and name not in files:
        return None
    if name not in files:
        raise ValueError(f"备份缺少 {name}")
    text = files[name].decode("utf-8-sig")
    value = (
        yaml.load(text, Loader=CoreLoader)
        if name.endswith(".yml")
        else json.loads(text)
    )
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须包含配置对象")
    return value


def plan_from_archive(files):
    return parse_plan_document(_object_file(files, "plan.json"))


def _validate_configuration(files):
    data = _object_file(files, "conf.yml")
    webview = data.get("webview", {})
    if not isinstance(webview, dict):
        raise ValueError("窗口设置格式错误")
    data["webview"] = {
        **webview,
        "port": config.conf.webview.port,
        "token": config.conf.webview.token,
        "tray": config.conf.webview.tray,
    }
    conf = config.Conf(**data)
    plan = plan_from_archive(files)
    if plan != config.plan:
        conf.dorm_order = ""
        data["dorm_order"] = ""
    weekly = _object_file(files, "weekly_plans.yml", optional=True)
    if weekly is not None:
        plans = weekly.get("plans")
        if not isinstance(plans, dict):
            raise ValueError("周计划格式错误")
        for name, entries in plans.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(entries, list)
            ):
                raise ValueError("周计划方案格式错误")
            for entry in entries:
                RegularTaskPart.MaaDailyPlan(**entry)
        from arknights_mower.utils.config.weekly_plan_loader import WeeklyPlanManager

        inventory = weekly.get("inventory_configs", {})
        if not isinstance(inventory, dict):
            raise ValueError("库存选关配置格式错误")
        for rules in inventory.values():
            if not isinstance(rules, dict):
                raise ValueError("库存选关规则格式错误")
            WeeklyPlanManager._normalize_inventory_config(rules)
        for key in (
            "activity_fallbacks",
            "activity_fallback_end_times",
            "activity_fallback_switch_times",
        ):
            mapping = weekly.get(key, {})
            if not isinstance(mapping, dict):
                raise ValueError("活动回退配置格式错误")
            for value in mapping.values():
                if key == "activity_fallbacks":
                    if not isinstance(value, str):
                        raise ValueError("活动回退方案必须是字符串")
                elif type(value) is not int or value < 0:
                    raise ValueError("活动切换时间必须是非负整数")
    return data, conf, plan


def import_configuration(raw):
    with backup_lock, workshop_lock:
        files = read_archive(raw)
        data, conf, plan = _validate_configuration(files)
        root = config.conf_path.parent
        previous, local_names = _local_snapshot()
        # Reject destination path collisions before backup or write.
        for name in files:
            for part in (PurePosixPath(name), *PurePosixPath(name).parents):
                normalized = part.as_posix()
                existing = local_names.get(normalized.casefold())
                if existing is not None and existing != normalized:
                    raise ValueError("配置路径与本机文件的大小写冲突")
            target = root / name
            if target.is_dir() or any(
                parent.is_file() for parent in target.parents if parent != root
            ):
                raise ValueError("配置文件与现有目录结构冲突")
        recovery = (
            get_path("@app/config-backups")
            / f"before-import-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.zip"
        )
        _write_bytes(recovery, _archive_bytes(previous))
        contents = dict(files)
        contents["conf.yml"] = yaml.safe_dump(
            data, allow_unicode=True, sort_keys=False
        ).encode("utf-8")
        written = []
        database = get_path("@app/tmp/data.db")
        transaction = (
            closing(sqlite3.connect(database))
            if database.is_file()
            else nullcontext(None)
        )
        with transaction as conn:
            try:
                if conn is not None:
                    conn.execute("BEGIN IMMEDIATE")
                    if conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='saved_state'"
                    ).fetchone():
                        conn.execute("DELETE FROM saved_state")
                for name in sorted(set(previous) | set(contents)):
                    if name.casefold() in IMPORT_PRESERVED_FILES:
                        continue
                    target = root / name
                    if name in contents:
                        content = contents[name]
                        _write_bytes(target, content)
                    else:
                        target.unlink()
                    written.append(name)
                if conn is not None:
                    conn.commit()
            except Exception:
                if conn is not None:
                    conn.rollback()
                for name in reversed(written):
                    target = root / name
                    if name in previous:
                        content = previous[name]
                        _write_bytes(target, content)
                    else:
                        target.unlink(missing_ok=True)
                raise
        config.conf, config.plan = conf, plan
        if module := sys.modules.get("arknights_mower.utils.config.weekly_plan_loader"):
            module._weekly_plan_manager = None
        if module := sys.modules.get("arknights_mower.__main__"):
            module.base_scheduler = None
        if module := sys.modules.get("arknights_mower.utils.skland"):
            module.skland_cache.clear()
            module._device_id = ""
            module._device_id_failed = False
        return str(recovery)
