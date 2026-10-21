import json
import re
from threading import RLock

from arknights_mower.utils import update_runtime as runtime

_state_lock = RLock()


def _read_state():
    state = runtime.read_json(state_path(), {})
    return state if isinstance(state, dict) else {}


def state_path():
    return runtime.state_dir() / "ui-state.json"


def get_log_layout():
    state = _read_state()
    layout = state.get("log_layout", {})
    return {
        "screenshot_height": layout.get("screenshot_height"),
        "task_height": layout.get("task_height"),
    }


def save_log_layout(data):
    with _state_lock:
        return _save_log_layout(data)


def _save_log_layout(data):
    state = _read_state()
    layout = state.get("log_layout", {})
    limits = {
        "screenshot_height": (90, 500),
        "task_height": (90, 600),
    }
    for key, (minimum, maximum) in limits.items():
        if key not in data:
            continue
        value = data[key]
        if value is None:
            layout.pop(key, None)
            continue
        if not isinstance(value, (int, float)):
            raise ValueError("界面布局参数无效")
        layout[key] = round(max(minimum, min(maximum, value)))
    state["log_layout"] = layout
    runtime.write_json(state_path(), state, indent=2)
    return get_log_layout()


def _names(value, *, count=512, length=160):
    if not isinstance(value, list) or len(value) > count:
        raise ValueError("心情报表偏好中的名单无效")
    if any(
        not isinstance(name, str) or not name.strip() or len(name) > length
        for name in value
    ):
        raise ValueError("心情报表偏好中的名称无效")
    return list(dict.fromkeys(value))


def _mood_board_patch(data):
    fields = {"groupOrder", "hiddenLines", "hiddenGroups", "defaultOperators", "views"}
    if not isinstance(data, dict) or data.keys() - fields:
        raise ValueError("心情报表偏好字段无效")
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 128 * 1024:
        raise ValueError("心情报表偏好过大")
    patch = {}
    for key, value in data.items():
        if key in ("groupOrder", "hiddenGroups"):
            patch[key] = _names(value)
        elif key in ("hiddenLines", "defaultOperators"):
            if not isinstance(value, dict) or len(value) > 512:
                raise ValueError("心情报表编组偏好无效")
            _names(list(value))
            patch[key] = {
                name: _names(names) if key == "hiddenLines" else _names([names])[0]
                for name, names in value.items()
            }
        else:
            if not isinstance(value, list) or len(value) > 12:
                raise ValueError("自选观察表数量无效")
            views = []
            ids = set()
            names = set()
            for view in value:
                if not isinstance(view, dict):
                    raise ValueError("自选观察表无效")
                identifier = view.get("id")
                name = view.get("name")
                if (
                    not isinstance(identifier, str)
                    or not re.fullmatch(r"[\w-]{4,80}", identifier, re.ASCII)
                    or identifier in ids
                    or not isinstance(name, str)
                    or not name.strip()
                    or len(name) > 30
                    or name in names
                ):
                    raise ValueError("自选观察表名称或标识无效")
                ids.add(identifier)
                names.add(name)
                views.append(
                    {
                        "id": identifier,
                        "name": name,
                        "operators": _names(view.get("operators"), count=16, length=40),
                    }
                )
            patch[key] = views
    return patch


def _mood_board(state):
    value = state.get("mood_board")
    if not isinstance(value, dict):
        return None
    return {
        "groupOrder": [],
        "hiddenLines": {},
        "hiddenGroups": [],
        "defaultOperators": {},
        "views": [],
        **_mood_board_patch(value),
    }


def get_mood_board():
    return {"preferences": _mood_board(_read_state())}


def save_mood_board(data, *, initialize=False):
    patch = _mood_board_patch(data)
    with _state_lock:
        state = _read_state()
        current = _mood_board(state)
        if initialize and current is not None:
            return {"preferences": current}
        state["mood_board"] = _mood_board_patch({**(current or {}), **patch})
        runtime.write_json(state_path(), state, indent=2)
        return {"preferences": _mood_board(state)}
