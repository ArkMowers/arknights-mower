from arknights_mower.utils import update_runtime as runtime


def state_path():
    return runtime.state_dir() / "ui-state.json"


def get_log_layout():
    state = runtime.read_json(state_path(), {}) or {}
    layout = state.get("log_layout", {})
    return {
        "screenshot_height": layout.get("screenshot_height"),
        "task_height": layout.get("task_height"),
    }


def save_log_layout(data):
    state = runtime.read_json(state_path(), {}) or {}
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
