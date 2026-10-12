"""Back up and restore instance configuration and persistent data as a ZIP."""

import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from threading import RLock
from time import monotonic
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile
from zlib import error as ZlibError

import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RegularTaskPart
from arknights_mower.utils.config.plan import (
    has_retired_dorm_options,
    migrate_legacy_dorm_order,
    parse_plan_document,
)
from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_config import workshop_lock

MAX_BACKUP_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1024
backup_lock = RLock()
IMPORT_PRESERVED_FILES = {"network.json", "gui.yml", "state.json"}
TMP_DATA_FILES = {
    "data.db",
    "cultivate.json",
    "growth_plan.json",
    "growth_history.json",
    "depotresult.csv",
    "depotmerged.csv",
    "report.csv",
    "skland.csv",
    "workshop_preset.json",
}


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


def _copy_database(source, destination):
    deadline = monotonic() + 10
    with (
        closing(
            sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=5)
        ) as reader,
        closing(sqlite3.connect(destination, timeout=5)) as writer,
    ):
        page_size = reader.execute("PRAGMA page_size").fetchone()[0]
        page_count = reader.execute("PRAGMA page_count").fetchone()[0]
        if page_count * page_size > MAX_BACKUP_BYTES:
            raise LocalConfigError("本机数据库超过 16 MB，无法生成备份")

        def progress(status, remaining, total):
            if status == sqlite3.SQLITE_DONE:
                return
            if total * page_size > MAX_BACKUP_BYTES:
                raise LocalConfigError("本机数据库超过 16 MB，无法生成备份")
            if monotonic() >= deadline:
                raise sqlite3.OperationalError("数据库备份超时，请停止写入后重试")

        reader.backup(writer, pages=256, progress=progress, sleep=0.05)


def _tmp_snapshot(total):
    root = get_path("@app/tmp")
    files = {}
    if root.is_symlink():
        raise LocalConfigError("本机 tmp 目录是符号链接，请改用普通目录后重试")
    if not root.exists():
        return files
    if not root.is_dir():
        raise LocalConfigError("本机 tmp 路径不是目录，请改用普通目录后重试")
    for suffix in ("-wal", "-shm", "-journal"):
        path = root / f"data.db{suffix}"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise LocalConfigError("本机数据库辅助文件包含符号链接或目录")
    for path in root.iterdir():
        if path.name.casefold() in TMP_DATA_FILES and (
            path.name not in TMP_DATA_FILES or path.is_symlink() or not path.is_file()
        ):
            raise LocalConfigError("本机 tmp 数据文件包含符号链接、目录或大小写冲突")
    for name in sorted(TMP_DATA_FILES):
        path = root / name
        if not path.is_file():
            continue
        if name == "data.db":
            try:
                with TemporaryDirectory() as directory:
                    snapshot = Path(directory) / "data.db"
                    _copy_database(path, snapshot)
                    content = snapshot.read_bytes()
            except sqlite3.Error as exc:
                raise LocalConfigError(
                    "本机数据库无法备份，请检查数据库或停止写入后重试"
                ) from exc
        else:
            with path.open("rb") as stream:
                content = stream.read(MAX_BACKUP_BYTES - total + 1)
        total += len(content)
        if total > MAX_BACKUP_BYTES:
            raise LocalConfigError("本机配置和数据内容超过 16 MB，无法生成备份")
        files[name] = content
    return files


def _archive_bytes(files, tmp_files):
    if len(files) + len(tmp_files) > MAX_ARCHIVE_ENTRIES:
        raise LocalConfigError("本机配置和数据文件数量超过 1024 个，请整理后重试")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("config/", b"")
        for name, content in files.items():
            archive.writestr(f"config/{name}", content)
        archive.writestr("tmp/", b"")
        for name, content in tmp_files.items():
            archive.writestr(f"tmp/{name}", content)
    raw = output.getvalue()
    if len(raw) > MAX_BACKUP_BYTES:
        raise LocalConfigError("本机配置生成的 ZIP 超过 16 MB，无法导出或生成恢复备份")
    return raw


def _write_bytes(path, content):
    config.atomic_write(path, lambda stream: stream.buffer.write(content))


def export_archive():
    with backup_lock, workshop_lock:
        files, _ = _local_snapshot()
        tmp_files = _tmp_snapshot(sum(map(len, files.values())))
        return _archive_bytes(files, tmp_files)


def read_archive(raw, *, include_tmp=False):
    """Read bounded regular files without extracting ZIP paths to the filesystem."""
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("备份文件不能超过 16 MB")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES + sum(
                info.filename in {"config/", "tmp/"} for info in infos
            ):
                raise ValueError("压缩包文件数量过多")
            if sum(info.file_size for info in infos) > MAX_BACKUP_BYTES:
                raise ValueError("解压后的配置和数据不能超过 16 MB")
            files, seen, kinds = {}, set(), {}
            tmp_files = {}
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
                    or parts[0] not in {"config", "tmp"}
                    or (
                        parts[0] == "tmp"
                        and len(parts) > 1
                        and (
                            len(parts) != 2
                            or parts[1] not in TMP_DATA_FILES
                            or info.is_dir()
                        )
                    )
                    or (
                        parts[0] == "config"
                        and len(parts) > 2
                        and parts[1].casefold() in IMPORT_PRESERVED_FILES
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
                target = tmp_files if parts[0] == "tmp" else files
                target[relative] = archive.read(info)
            # Also reject file/directory collisions before any writes.
            for name in files:
                if any(
                    parent.as_posix() in files for parent in PurePosixPath(name).parents
                ):
                    raise ValueError("压缩包中的文件与目录冲突")
            return (files, tmp_files) if include_tmp else files
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
    legacy_dorm_order = str(data.get("dorm_order", "") or "")
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
    if os.environ.get("MOWER_ANDROID") == "1":
        conf.sync_legacy_device_fields()
        data.update(conf.model_dump(exclude_unset=True))
    plan_data = _object_file(files, "plan.json")
    # Some older exports were normalized through the newer schema and therefore carry
    # an empty main-plan field even though the global value was still authoritative.
    if (legacy_dorm_order) and plan_data.get("conf", {}).get("dorm_order") == "":
        plan_data["conf"].pop("dorm_order")
    plan = parse_plan_document(plan_data)
    dorm_order_migrated = migrate_legacy_dorm_order(plan, plan_data, legacy_dorm_order)
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
    return data, conf, plan, dorm_order_migrated


def _prepare_database(content, path):
    if not content.startswith(b"SQLite format 3\x00"):
        raise ValueError("备份中的 data.db 不是有效的 SQLite 数据库")
    path.write_bytes(content)
    try:
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("PRAGMA trusted_schema=OFF")
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("备份中的 data.db 完整性校验失败")
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='saved_state'"
            ).fetchone():
                conn.execute("DELETE FROM saved_state")
    except sqlite3.Error as exc:
        raise ValueError("备份中的 data.db 无法读取") from exc


def import_configuration(raw):
    with backup_lock, workshop_lock, TemporaryDirectory() as directory:
        files, tmp_files = read_archive(raw, include_tmp=True)
        data, conf, plan, dorm_order_migrated = _validate_configuration(files)
        prepared = Path(directory) / "incoming.db"
        if "data.db" in tmp_files:
            _prepare_database(tmp_files["data.db"], prepared)
        root = config.conf_path.parent
        previous, local_names = _local_snapshot()
        previous_tmp = _tmp_snapshot(sum(map(len, previous.values())))
        if "data.db" not in tmp_files and "data.db" in previous_tmp:
            _prepare_database(previous_tmp["data.db"], prepared)
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
        _write_bytes(recovery, _archive_bytes(previous, previous_tmp))
        contents = dict(files)
        contents["conf.yml"] = yaml.safe_dump(
            {
                key: value
                for key, value in data.items()
                if key
                not in {
                    "experimental_dorm_logic",
                    "refresh_backup_plan_after_mood",
                    "workshop_low_priority_rest",
                    "dorm_order",
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        if dorm_order_migrated or has_retired_dorm_options(
            _object_file(files, "plan.json")
        ):
            contents["plan.json"] = json.dumps(
                plan.model_dump(exclude_none=True), ensure_ascii=False, indent=2
            ).encode("utf-8")
        tmp_root = get_path("@app/tmp")
        database = tmp_root / "data.db"
        database_existed = database.is_file()
        originals = {
            **{root / name: content for name, content in previous.items()},
            **{tmp_root / name: content for name, content in previous_tmp.items()},
        }
        targets = {root / name: content for name, content in contents.items()}
        targets.update(
            {
                tmp_root / name: content
                for name, content in tmp_files.items()
                if name != "data.db"
            }
        )
        removed = {root / name for name in previous.keys() - contents.keys()}
        written = []
        try:
            for target in sorted(set(targets) | removed):
                if (
                    target.parent == root
                    and target.name.casefold() in IMPORT_PRESERVED_FILES
                ):
                    continue
                if target in targets:
                    _write_bytes(target, targets[target])
                else:
                    target.unlink()
                written.append(target)
            if prepared.exists():
                database.parent.mkdir(parents=True, exist_ok=True)
                _copy_database(prepared, database)
        except Exception:
            if not database_existed:
                database.unlink(missing_ok=True)
            for target in reversed(written):
                if target in originals:
                    _write_bytes(target, originals[target])
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
