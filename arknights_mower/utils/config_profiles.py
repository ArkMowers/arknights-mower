"""Manage named instance configurations with atomic activation and generation checks."""

import copy
import json
import re
import sys
from uuid import uuid4

from arknights_mower.utils import config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils.config_profile_groups import GROUPS
from arknights_mower.utils.config_selection import (
    WEEKLY_SELECTION_FILE,
    combine_archives,
    default_archive,
    validate_groups,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.workshop_config import workshop_lock

MAX_PROFILES = 20
MAX_NAME_LENGTH = 64
MAX_INDEX_BYTES = 65536
_ID = re.compile(r"[a-f0-9]{32}\Z")


class ProfileConflict(ValueError):
    code = "configuration_changed"

    def __init__(self):
        super().__init__("当前档案已改变，请刷新页面后重试")


def _root():
    path = get_path("@app/config-profiles")
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise backup.LocalConfigError("档案目录必须是普通目录")
    return path


def _regular_bytes(path, limit, *, optional=False):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise backup.LocalConfigError("档案包含链接或非普通文件")
    if not path.exists():
        if optional:
            return None
        raise backup.LocalConfigError("档案缺失，请检查档案目录")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise backup.LocalConfigError("档案超过大小限制")
    return raw


def _profile_path(identifier):
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        raise ValueError("档案标识无效")
    path = _root() / f"{identifier}.zip"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise backup.LocalConfigError("档案必须是普通文件")
    return path


def _name(value):
    if not isinstance(value, str):
        raise ValueError("请输入档案名称")
    value = value.strip()
    if (
        not value
        or len(value) > MAX_NAME_LENGTH
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("档案名称需要 1 至 64 个字符，且不能包含控制字符")
    return value


def _read_registry():
    raw = _regular_bytes(_root() / "index.json", MAX_INDEX_BYTES, optional=True)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError()
        entries = data["profiles"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PROFILES:
            raise ValueError()
        ids, names = set(), set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "name"}:
                raise ValueError()
            identifier, name = entry["id"], _name(entry["name"])
            if name != entry["name"] or identifier in ids or name.casefold() in names:
                raise ValueError()
            path = _profile_path(identifier)
            initial_active = data.get("generation") == "0" and identifier == data.get(
                "active_id"
            )
            if (not path.exists() and not initial_active) or (
                path.exists() and path.stat().st_size > backup.MAX_BACKUP_BYTES
            ):
                raise ValueError()
            ids.add(identifier)
            names.add(name.casefold())
        generation = data["generation"]
        if (
            data["active_id"] not in ids
            or not isinstance(generation, str)
            or not (generation == "0" or _ID.fullmatch(generation))
        ):
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise backup.LocalConfigError(
            "档案目录损坏，请检查 index.json 和对应 ZIP 文件"
        ) from exc


def _write_registry(data):
    backup._write_bytes(
        _root() / "index.json",
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
    )


def _state():
    raw = _regular_bytes(config.app_state_path, backup.MAX_BACKUP_BYTES, optional=True)
    if raw is None:
        return None, {}
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return raw, value
    except (ValueError, TypeError, RecursionError) as exc:
        raise backup.LocalConfigError(
            "本机窗口状态无法读取，请检查 state.json"
        ) from exc


def export_current_archive():
    """Include the selected weekly preset without exporting other process state."""
    with backup.backup_lock, workshop_lock:
        files, tmp = backup.read_archive(backup.export_archive(), include_tmp=True)
        _, state = _state()
        selected = state.get("active_weekly_plan", "")
        if not isinstance(selected, str):
            raise backup.LocalConfigError("本机周计划选择无效")
        files[WEEKLY_SELECTION_FILE] = json.dumps(
            {"active_weekly_plan": selected}, ensure_ascii=False
        ).encode("utf-8")
        if (
            sum(map(len, files.values())) + sum(map(len, tmp.values()))
            > backup.MAX_BACKUP_BYTES
        ):
            raise backup.LocalConfigError("本机配置和数据内容超过 16 MB，无法生成备份")
        return backup._archive_bytes(files, tmp)


def _initial_registry():
    identifier = uuid4().hex
    return {
        "version": 1,
        "active_id": identifier,
        "generation": "0",
        "profiles": [{"id": identifier, "name": "默认档案"}],
    }


def _registry():
    data = _read_registry()
    if data is None:
        data = _initial_registry()
        _write_registry(data)
    return data


def current_generation():
    with backup.backup_lock, workshop_lock:
        data = _read_registry()
        return data["generation"] if data else "0"


def check_generation(value, *, allow_legacy=True):
    with backup.backup_lock, workshop_lock:
        actual = current_generation()
        if value != actual and not (value is None and allow_legacy and actual == "0"):
            raise ProfileConflict()


def _public(data):
    return {
        "ok": True,
        "active_id": data["active_id"],
        "generation": data["generation"],
        "profiles": copy.deepcopy(data["profiles"]),
        "groups": copy.deepcopy(GROUPS),
    }


def list_profiles():
    with backup.backup_lock, workshop_lock:
        return _public(_registry())


def _find(data, identifier):
    _profile_path(identifier)
    for entry in data["profiles"]:
        if entry["id"] == identifier:
            return entry
    raise ValueError("找不到所选档案，请刷新页面后重试")


def _unique_name(data, value, identifier=None):
    value = _name(value)
    if any(
        entry["id"] != identifier and entry["name"].casefold() == value.casefold()
        for entry in data["profiles"]
    ):
        raise ValueError("已存在同名档案，请使用其他名称")
    return value


def _weekly_selection(raw):
    files = backup.read_archive(raw)
    selected = backup._object_file(files, WEEKLY_SELECTION_FILE, optional=True)
    value = selected.get("active_weekly_plan", "") if selected is not None else ""
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("周计划选择格式错误")
    return value


def _restore(path, raw):
    if raw is None:
        path.unlink(missing_ok=True)
    else:
        backup._write_bytes(path, raw)


def import_backup(raw, *, expected_generation=None):
    """Restore a backup and invalidate drafts from the previous configuration."""
    with backup.backup_lock, workshop_lock:
        check_generation(expected_generation)
        data = _read_registry() or _initial_registry()
        data["generation"] = uuid4().hex
        index_path = _root() / "index.json"
        snapshot_path = _profile_path(data["active_id"])
        previous_index = _regular_bytes(index_path, MAX_INDEX_BYTES, optional=True)
        previous_snapshot = _regular_bytes(
            snapshot_path, backup.MAX_BACKUP_BYTES, optional=True
        )

        def commit():
            try:
                backup._write_bytes(snapshot_path, export_current_archive())
                _write_registry(data)
            except Exception:
                logger.exception("备份导入元数据提交失败")
                for path, previous in (
                    (snapshot_path, previous_snapshot),
                    (index_path, previous_index),
                ):
                    try:
                        _restore(path, previous)
                    except Exception:
                        logger.exception("备份导入元数据回滚失败：%s", path)
                raise

        return backup.import_configuration(raw, commit=commit)


def _activate(data, identifier, raw, outgoing):
    # The outgoing snapshot may advance even when activation later fails.
    backup._write_bytes(_profile_path(data["active_id"]), outgoing)
    next_data = copy.deepcopy(data)
    next_data["active_id"] = identifier
    next_data["generation"] = uuid4().hex
    index_path, target_path = _root() / "index.json", _profile_path(identifier)
    previous_index = _regular_bytes(index_path, MAX_INDEX_BYTES)
    previous_snapshot = _regular_bytes(
        target_path, backup.MAX_BACKUP_BYTES, optional=True
    )
    previous_state, state = _state()
    selected = _weekly_selection(raw)
    if selected:
        state["active_weekly_plan"] = selected
    else:
        state.pop("active_weekly_plan", None)

    def commit():
        try:
            backup._write_bytes(
                config.app_state_path,
                json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            backup._write_bytes(target_path, export_current_archive())
            _write_registry(next_data)
        except Exception:
            logger.exception("档案元数据提交失败")
            for path, previous in (
                (config.app_state_path, previous_state),
                (target_path, previous_snapshot),
                (index_path, previous_index),
            ):
                try:
                    _restore(path, previous)
                except Exception:
                    logger.exception("档案元数据回滚失败：%s", path)
            raise

    recovery = backup.import_configuration(raw, replace_tmp=True, commit=commit)
    config.operation_feedback_avg = None
    config.operation_feedback_count = 0
    config.operation_feedback_mode = None
    config.operation_feedback_cap = None
    config.operation_failure_streak = 0
    config.operation_recovery_successes = 0
    if module := sys.modules.get("arknights_mower.utils.workshop_automation"):
        module._refresh_error = None
    if module := sys.modules.get("arknights_mower.solvers.record"):
        module.workshop_inventory_changed.clear()
    if module := sys.modules.get("arknights_mower.utils.workshop_limits"):
        module._rejected_recipes.clear()
    return {**_public(next_data), "recovery_path": recovery}


def create_profile(name, inherit, *, expected_generation):
    with backup.backup_lock, workshop_lock:
        check_generation(expected_generation, allow_legacy=False)
        data = _registry()
        if len(data["profiles"]) >= MAX_PROFILES:
            raise ValueError("最多保存 20 份档案")
        name = _unique_name(data, name)
        selected = validate_groups(inherit)
        outgoing = export_current_archive()
        combined = combine_archives(default_archive(), outgoing, selected)
        identifier = uuid4().hex
        data["profiles"].append({"id": identifier, "name": name})
        return _activate(data, identifier, combined, outgoing)


def import_profile(raw, name, keep, *, expected_generation):
    with backup.backup_lock, workshop_lock:
        check_generation(expected_generation, allow_legacy=False)
        data = _registry()
        if len(data["profiles"]) >= MAX_PROFILES:
            raise ValueError("最多保存 20 份档案")
        name = _unique_name(data, name)
        selected = validate_groups(keep)
        outgoing = export_current_archive()
        combined = combine_archives(raw, outgoing, selected)
        identifier = uuid4().hex
        data["profiles"].append({"id": identifier, "name": name})
        return _activate(data, identifier, combined, outgoing)


def activate_profile(identifier, keep, *, expected_generation):
    with backup.backup_lock, workshop_lock:
        check_generation(expected_generation, allow_legacy=False)
        data = _registry()
        _find(data, identifier)
        selected = validate_groups(keep)
        if identifier == data["active_id"]:
            return _public(data)
        incoming = _regular_bytes(_profile_path(identifier), backup.MAX_BACKUP_BYTES)
        outgoing = export_current_archive()
        combined = combine_archives(incoming, outgoing, selected)
        return _activate(data, identifier, combined, outgoing)


def rename_profile(identifier, name, *, expected_generation):
    with backup.backup_lock, workshop_lock:
        check_generation(expected_generation, allow_legacy=False)
        data = _registry()
        entry = _find(data, identifier)
        entry["name"] = _unique_name(data, name, identifier)
        _write_registry(data)
        return _public(data)
