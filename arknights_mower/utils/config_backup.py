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
PRESERVED_FILES = {"network.json", "gui.yml", "state.json"}


def _local_files():
    root = config.conf_path.parent
    files = {}
    if root.is_symlink():
        raise ValueError("配置目录不能是符号链接")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("配置目录包含符号链接")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
    return files


def export_archive():
    with backup_lock, workshop_lock:
        files = _local_files()
        if len(files) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("配置文件数量过多")
        output = BytesIO()
        total = 0
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("config/", b"")
            for name, path in files.items():
                if name.casefold() == "state.json":
                    continue
                content = path.read_bytes()
                total += len(content)
                if total > MAX_BACKUP_BYTES:
                    raise ValueError("配置内容不能超过 16 MB")
                archive.writestr(f"config/{name}", content)
        raw = output.getvalue()
        if len(raw) > MAX_BACKUP_BYTES:
            raise ValueError("备份文件不能超过 16 MB")
        return raw


def read_archive(raw):
    """Read bounded regular files without extracting ZIP paths to the filesystem."""
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 16 MB")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES + 1:
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
                    or (len(parts) > 2 and parts[1].casefold() in PRESERVED_FILES)
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
    except (BadZipFile, RuntimeError, NotImplementedError) as exc:
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
        local = _local_files()
        # Reject collisions with destination directories/symlinks before backup or write.
        local_names = {}
        for path in root.rglob("*"):
            name = path.relative_to(root).as_posix()
            local_names[name.casefold()] = name
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
        previous = {name: path.read_bytes() for name, path in local.items()}
        recovery = (
            get_path("@app/config-backups")
            / f"before-import-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.zip"
        )
        recovery_bytes = export_archive()
        config.atomic_write(recovery, lambda f: f.buffer.write(recovery_bytes))
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
                for name in sorted(set(local) | set(contents)):
                    if name.casefold() in PRESERVED_FILES:
                        continue
                    target = root / name
                    if name in contents:
                        content = contents[name]
                        config.atomic_write(
                            target, lambda f, content=content: f.buffer.write(content)
                        )
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
                        config.atomic_write(
                            target, lambda f, content=content: f.buffer.write(content)
                        )
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
