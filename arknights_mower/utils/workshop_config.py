"""Editable manual workshop settings, separate from the active runtime recipes."""

import json
from threading import RLock

from pydantic import BaseModel

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RIICPart
from arknights_mower.utils.path import get_path

workshop_lock = RLock()
_STATE_FIELDS = (
    "workshop_settings",
    "workshop_manual_backup",
    "workshop_auto_active",
    "workshop_manual_revision",
    "workshop_preset_migrated",
    "workshop_generation",
)


def settings(entries, source=None):
    result = []
    for entry in entries:
        value = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
        if source is not None:
            value["source"] = source
        result.append(RIICPart.WorkShopSetting(**value))
    return result


def _manual_form(conf):
    if conf.workshop_manual_backup is not None:
        return conf.workshop_manual_backup
    return settings(
        [s for s in conf.workshop_settings if s.source != "mastery"], "manual"
    )


def _import_legacy_preset(conf):
    path = get_path("@app/tmp/workshop_preset.json")
    if conf.workshop_manual_backup is None and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("settings") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("已保存的合成配置格式错误")
        conf.workshop_manual_backup = settings(entries, "manual")
        # Repairing a previously unreadable file may replace a form already open.
        conf.workshop_manual_revision += 1
    conf.workshop_preset_migrated = True


def initialize_manual_settings(conf):
    # Persist False too: an initialized form is not a legacy active snapshot.
    conf.workshop_auto_active = conf.workshop_auto_active
    if not conf.workshop_preset_migrated:
        try:
            _import_legacy_preset(conf)
        except (OSError, ValueError, TypeError):
            return (
                "旧合成配置无法读取，原文件和现有配置已保留。"
                "修复旧文件或修改下方设置后，可继续自动备料。"
            )
    if conf.workshop_manual_backup is None:
        conf.workshop_manual_backup = _manual_form(conf)
    return ""


def restore_manual_settings(conf):
    if not conf.workshop_auto_active:
        return False
    conf.workshop_settings = settings(conf.workshop_manual_backup or [], "manual")
    conf.workshop_auto_active = False
    conf.workshop_generation += 1
    return True


def save_conf(conf):
    previous = config.conf
    if conf == previous:
        return
    config.conf = conf
    try:
        config.save_conf()
    except Exception:
        config.conf = previous
        raise


def workshop_state(conf, warning=""):
    return {
        "workshop_settings": [s.model_dump() for s in conf.workshop_settings],
        "workshop_generation": conf.workshop_generation,
        "workshop_manual_settings": [s.model_dump() for s in _manual_form(conf)],
        "workshop_manual_revision": conf.workshop_manual_revision,
        "automatic": conf.workshop_auto_active,
        "workshop_preset_warning": warning,
    }


def read_user_config():
    with workshop_lock:
        conf = config.conf.model_copy(deep=True)
        warning = initialize_manual_settings(conf)
        save_conf(conf)
        return {**conf.model_dump(), **workshop_state(conf, warning)}


def _edit_manual(conf, req):
    if "workshop_manual_settings" not in req:
        return False
    if req.get("workshop_manual_settings_revision") != conf.workshop_manual_revision:
        return True
    incoming = settings(req["workshop_manual_settings"], "manual")
    if incoming != _manual_form(conf):
        conf.workshop_manual_backup = incoming
        conf.workshop_preset_migrated = True
        conf.workshop_manual_revision += 1
        if not conf.workshop_auto_active:
            conf.workshop_settings = settings(incoming)
            conf.workshop_generation += 1
    return False


def _edit_legacy(conf, req):
    if conf.workshop_auto_active or "workshop_settings" not in req:
        return
    if req.get("workshop_settings_generation", 0) != conf.workshop_generation:
        return
    incoming = settings(req["workshop_settings"])
    if any(s.source == "mastery" for s in incoming):
        return
    if incoming != conf.workshop_settings:
        conf.workshop_settings = incoming
        conf.workshop_manual_backup = settings(incoming, "manual")
        conf.workshop_preset_migrated = True
        conf.workshop_manual_revision += 1
        conf.workshop_generation += 1


def _merge_model_fields(model, updates):
    data = model.model_dump()
    for name, value in updates.items():
        current = getattr(model, name, None)
        data[name] = (
            _merge_model_fields(current, value)
            if isinstance(current, BaseModel) and isinstance(value, dict)
            else value
        )
    return data


def save_user_config(req):
    with workshop_lock:
        state = config.conf.model_copy(deep=True)
        warning = initialize_manual_settings(state)
        conflict = _edit_manual(state, req)
        if "workshop_manual_settings" not in req:
            _edit_legacy(state, req)
        editable = dict(req)
        for key in _STATE_FIELDS:
            editable[key] = getattr(state, key)
        editable.setdefault("workshop_deer_fodder", state.workshop_deer_fodder)
        # Web forms only submit fields they expose. Keep all other settings,
        # including values restored from a full configuration backup.
        conf = config.Conf(**_merge_model_fields(state, editable))
        if not conf.enable_mastery:
            restore_manual_settings(conf)
        save_conf(conf)
        if conf.workshop_preset_migrated:
            warning = ""
        return {**workshop_state(conf, warning), "workshop_manual_conflict": conflict}
