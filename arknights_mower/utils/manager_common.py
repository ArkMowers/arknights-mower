"""Opt-in launch settings shared by desktop instances of one manager."""

import copy
import json
import math
import os
import sys
from pathlib import Path

from .path import get_path

# The bridge supplies the same field choices and bounds used for validation.
FIELDS = [
    dict(
        key="startup_mode",
        group="实例启动",
        label="启动方式",
        kind="select",
        default="window",
        options=[("window", "普通启动（显示窗口）"), ("background", "后台静默启动")],
        help=(
            "后台静默启动不显示启动画面和内置窗口，实例后台仍正常运行。"
            "可通过“打开实例页面”访问，或从托盘打开内置窗口；关闭网页不会停止实例。"
            "自动化是否开始仍由实例原有设置决定，保存后对下次启动生效。"
        ),
    ),
    dict(
        key="instance_page_mode",
        group="实例启动",
        label="实例页面打开方式",
        kind="select",
        default="browser",
        options=[("browser", "外部默认浏览器"), ("webview", "内置 WebView")],
        help="用于管理器打开单个或全部实例页面，不改变实例启动方式。",
    ),
    dict(
        key="device.installation_path",
        group="程序位置",
        label="模拟器安装目录",
        kind="directory",
        default="",
    ),
    dict(
        key="device.manager_path",
        group="程序位置",
        label="模拟器管理程序",
        kind="file",
        default="",
    ),
    dict(
        key="maa_path",
        group="程序位置",
        label="MAA 安装目录",
        kind="directory",
        default="@app/MAA",
    ),
    dict(
        key="device.adb_path",
        group="程序位置",
        label="ADB 程序",
        kind="file",
        default="",
    ),
    dict(
        key="device.screenshot_backend",
        group="连接方式",
        label="截图方式",
        kind="select",
        default="droidcast",
        options=[
            ("droidcast", "DroidCast"),
            ("adb_gzip", "ADB"),
            ("mumu_ipc", "MuMu 截图增强"),
            ("ld_native", "LD 截图增强"),
        ],
    ),
    dict(
        key="device.touch_backend",
        group="连接方式",
        label="触控方式",
        kind="select",
        default="scrcpy",
        options=[
            ("scrcpy", "scrcpy"),
            ("maatouch", "MaaTouch"),
            ("mumu_ipc", "MuMu IPC"),
        ],
    ),
    dict(
        key="maa_conn_preset",
        group="连接方式",
        label="MAA 连接预设",
        kind="text",
        default="CompatMac" if sys.platform == "darwin" else "General",
    ),
    dict(
        key="maa_touch_option",
        group="连接方式",
        label="MAA 触控方式",
        kind="select",
        default="maatouch",
        options=[("maatouch", "MaaTouch"), ("minitouch", "minitouch"), ("adb", "ADB")],
    ),
    dict(
        key="performance_mode",
        group="性能",
        label="设备性能适配",
        kind="select",
        default="auto",
        options=[
            ("auto", "自动"),
            ("xhigh", "极高"),
            ("high", "高"),
            ("medium", "中"),
            ("low", "低"),
        ],
    ),
    dict(
        key="screenshot_interval",
        group="性能",
        label="截图间隔（毫秒）",
        kind="integer",
        default=500,
        min=0,
        max=60000,
    ),
    dict(
        key="selection_poll_interval",
        group="性能",
        label="选人采样间隔（秒）",
        kind="number",
        default=0.1,
        min=0.1,
        max=2,
    ),
    dict(
        key="selection_transition_timeout",
        group="性能",
        label="选人切页超时（秒）",
        kind="number",
        default=2.5,
        min=1,
        max=20,
    ),
    dict(
        key="device.recovery_timeout",
        group="连接恢复",
        label="连接超时（秒）",
        kind="number",
        default=180,
        min=10,
        max=600,
    ),
    dict(
        key="device.recovery_attempts",
        group="连接恢复",
        label="最大重试次数",
        kind="integer",
        default=3,
        min=1,
        max=10,
    ),
    dict(
        key="device.recovery_local_wait",
        group="连接恢复",
        label="重试间隔（秒）",
        kind="number",
        default=10,
        min=1,
        max=60,
    ),
    dict(
        key="device.recovery_shutdown_wait",
        group="连接恢复",
        label="关停上限（秒）",
        kind="number",
        default=30,
        min=5,
        max=120,
    ),
    dict(
        key="device.manager_query_timeout",
        group="连接恢复",
        label="状态检测超时（秒）",
        kind="number",
        default=10,
        min=1,
        max=30,
    ),
    dict(
        key="screenshot",
        group="截图保存",
        label="截图保存时间（小时）",
        kind="number",
        default=1,
        min=0,
        max=8760,
    ),
    dict(
        key="screenshot_archive_limit_mb",
        group="截图保存",
        label="截图存档上限（MB/实例）",
        kind="integer",
        default=5120,
        min=0,
        max=1048576,
    ),
]
TEMPLATE_KEYS = frozenset(
    {
        "device.preset_id",
        "device.installation_path",
        "device.manager_path",
        "device.config_path",
    }
)
FIELDS.extend(
    [
        dict(
            key="device.preset_id",
            group="模拟器模板",
            label="模拟器预设",
            kind="select",
            default="manual.other",
            options=[
                (preset, preset)
                for preset in (
                    "windows.mumu12",
                    "windows.ldplayer9",
                    "windows.ldplayer14",
                    "windows.nox",
                    "windows.bluestacks5",
                    "macos.bluestacks_air",
                    "macos.avd",
                    "macos.mumu_pro",
                    "linux.waydroid",
                    "linux.avd",
                    "linux.redroid",
                    "linux.genymotion",
                    "manual.other",
                    "manual.physical",
                )
            ],
        ),
        dict(
            key="device.config_path",
            group="模拟器模板",
            label="模拟器配置文件",
            kind="file",
            default="",
        ),
    ]
)
FIELDS.extend(
    [
        dict(
            key="simulator.wait_time",
            group="连接恢复",
            label="模拟器启动等待（秒）",
            kind="integer",
            default=30,
            min=0,
            max=3600,
        ),
        dict(
            key="custom_screenshot.command",
            group="连接方式",
            label="自定义截图命令",
            kind="text",
            default="adb -s 127.0.0.1:5555 shell screencap -p 2>/dev/null",
        ),
        dict(
            key="droidcast.rotate",
            group="连接方式",
            label="旋转截图 180 度",
            kind="boolean",
            default=False,
        ),
        dict(
            key="device.simulator_hotkey",
            group="连接恢复",
            label="模拟器老板键",
            kind="text",
            default="",
        ),
        dict(
            key="device.simulator_hotkey_delay",
            group="连接恢复",
            label="老板键等待（秒）",
            kind="number",
            default=3.0,
            min=0,
            max=60,
        ),
        dict(
            key="tap_to_launch_game.mode",
            group="游戏启动与空闲",
            label="启动游戏方式",
            kind="select",
            default="adb",
            options=[("adb", "ADB"), ("tap", "点击屏幕"), ("custom", "自定义命令")],
        ),
        dict(
            key="tap_to_launch_game.x",
            group="游戏启动与空闲",
            label="启动点击 X",
            kind="integer",
            default=0,
            min=0,
            max=10000,
        ),
        dict(
            key="tap_to_launch_game.y",
            group="游戏启动与空闲",
            label="启动点击 Y",
            kind="integer",
            default=0,
            min=0,
            max=10000,
        ),
        dict(
            key="tap_to_launch_game.command",
            group="游戏启动与空闲",
            label="自定义游戏启动命令",
            kind="text",
            default="input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; am start -n {package}/{activity}",
        ),
        *[
            dict(
                key=key,
                group="游戏启动与空闲",
                label=label,
                kind="boolean",
                default=False,
            )
            for key, label in [
                ("close_simulator_when_idle", "空闲时关闭模拟器"),
                ("exit_game_when_idle", "空闲时退出游戏"),
                ("return_home_when_idle", "空闲时返回首页"),
                ("fix_mumu12_adb_disconnect", "关闭 MuMu 12 时断开当前 ADB 连接"),
            ]
        ],
    ]
)
FIELDS.append(
    dict(
        key="waiting_scene",
        group="运行参数",
        label="页面等待参数",
        kind="waiting_scene",
        scenes=[
            ("CONNECTING", "正在提交反馈至神经"),
            ("UNKNOWN", "未知"),
            ("LOADING", "加载中"),
            ("LOGIN_LOADING", "场景跳转时的等待界面"),
            ("LOGIN_MAIN_NOENTRY", "登录页面（无按钮入口）"),
            ("OPERATOR_ONGOING", "代理作战"),
        ],
    )
)
_RETIRED_SENDER_KEYS = frozenset(
    {
        "account",
        "pass_code",
        "custom_smtp_server.enable",
        "custom_smtp_server.server",
        "custom_smtp_server.encryption",
        "custom_smtp_server.ssl_port",
    }
)
_FIELDS_BY_KEY = {field["key"]: field for field in FIELDS}
MANAGER_ONLY_KEYS = frozenset({"startup_mode", "instance_page_mode"})
LOCAL_OVERRIDE_KEYS = frozenset(
    {"maa_path", "screenshot", "screenshot_archive_limit_mb"}
)
_BACKENDS = {"device.screenshot_backend", "device.touch_backend"}
SHARED_CONNECTION_KEYS = frozenset(
    field["key"]
    for field in FIELDS
    if field["group"] in {"连接方式", "连接恢复", "性能", "游戏启动与空闲"}
    or field["key"] in {"device.adb_path", "waiting_scene"}
    or field["key"] in TEMPLATE_KEYS
)
for _field in FIELDS:
    if _field["key"] in SHARED_CONNECTION_KEYS:
        _field["shared_connection"] = True
        if _field["key"] == "device.screenshot_backend":
            _field["options"].append(("custom", "自定义命令"))


def fields():
    from .config import Conf

    result = copy.deepcopy(FIELDS)
    next(field for field in result if field["key"] == "waiting_scene")["default"] = (
        Conf().waiting_scene.model_dump(mode="json")
    )
    return result


def validate_waiting_scene(value):
    from .config import Conf

    model = Conf.model_fields["waiting_scene"].annotation
    if not isinstance(value, dict) or set(value) != set(model.model_fields):
        raise ValueError("页面等待参数必须包含完整的六个场景")
    if any(
        not isinstance(pair, (list, tuple))
        or len(pair) != 2
        or any(type(item) is not int for item in pair)
        for pair in value.values()
    ):
        raise ValueError("页面等待参数每个场景必须包含两个整数")
    return model.model_validate(
        {key: tuple(pair) for key, pair in value.items()}, strict=True
    ).model_dump(mode="json")


def settings_path():
    return get_path("@app/config/manager-common.json", space="")


def validate_settings(values):
    if not isinstance(values, dict) or values.keys() - _FIELDS_BY_KEY.keys():
        raise ValueError("不支持的公共配置项")
    result = copy.deepcopy(values)
    for key, value in values.items():
        field = _FIELDS_BY_KEY[key]
        kind = field["kind"]
        valid = True
        if kind == "waiting_scene":
            result[key] = validate_waiting_scene(value)
            continue
        if kind == "boolean":
            valid = type(value) is bool
        elif kind in {"integer", "number"}:
            valid = (
                type(value) in ({int} if kind == "integer" else {int, float})
                and math.isfinite(value)
                and field["min"] <= value <= field["max"]
            )
        else:
            valid = isinstance(value, str) and len(value) <= 4096 and "\0" not in value
            if kind == "select":
                valid = valid and value in {item[0] for item in field["options"]}
            if kind in {"directory", "file"} and key not in TEMPLATE_KEYS | {
                "device.adb_path"
            }:
                valid = valid and bool(value.strip())
        if not valid:
            raise ValueError(f"{field['label']}的值无效")
    if values.keys() & _BACKENDS:
        if not _BACKENDS <= values.keys():
            raise ValueError("截图与触控方式需要一起配置")
        if (values["device.screenshot_backend"] == "mumu_ipc") != (
            values["device.touch_backend"] == "mumu_ipc"
        ):
            raise ValueError("MuMu IPC 必须同时用于截图与触控")
    return result


def policy_key(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def _validate_stored_settings(values):
    # Retired sender settings are accepted only when reading existing documents.
    if isinstance(values, dict):
        values = {
            key: value
            for key, value in values.items()
            if key not in _RETIRED_SENDER_KEYS
        }
    return validate_settings(values)


def read_document(path=None):
    try:
        raw = (path or settings_path()).read_text(encoding="utf-8")
    except FileNotFoundError:
        return dict(version=0, values={}, independent_instances={})
    data = json.loads(raw)
    if isinstance(data, dict) and "version" in data:
        if (
            set(data)
            != (
                {"version", "values", "independent_instances"}
                | ({"instance_overrides"} if data.get("version") == 2 else set())
            )
            or type(data["version"]) is not int
            or data["version"] not in {1, 2}
        ):
            raise ValueError("公共连接配置格式不正确")
        policies = data["independent_instances"]
        if not isinstance(policies, dict) or any(
            not isinstance(key, str)
            or len(key) > 4096
            or "\0" in key
            or not Path(key).is_absolute()
            or type(value) is not bool
            for key, value in policies.items()
        ):
            raise ValueError("独立连接配置格式不正确")
        values = _validate_stored_settings(data["values"])
        if (
            not SHARED_CONNECTION_KEYS - TEMPLATE_KEYS - {"waiting_scene"}
            <= values.keys()
        ):
            raise ValueError("公共连接配置缺少共享参数")
        result = dict(
            version=data["version"],
            values=values,
            independent_instances=policies.copy(),
        )
        if data["version"] == 2:
            overrides = data["instance_overrides"]
            if not isinstance(overrides, dict) or any(
                not isinstance(key, str)
                or len(key) > 4096
                or "\0" in key
                or not Path(key).is_absolute()
                for key in overrides
            ):
                raise ValueError("实例配置继承格式不正确")
            result["instance_overrides"] = {
                key: validate_override(value) for key, value in overrides.items()
            }
        return result
    return dict(
        version=0, values=_validate_stored_settings(data), independent_instances={}
    )


def read_settings(path=None):
    return read_document(path)["values"]


def validate_override(value):
    if not isinstance(value, dict) or set(value) != {"local_keys", "manager_values"}:
        raise ValueError("实例配置继承格式不正确")
    keys, manager = value["local_keys"], value["manager_values"]
    if (
        not isinstance(keys, list)
        or any(not isinstance(key, str) for key in keys)
        or len(keys) != len(set(keys))
        or set(keys) - LOCAL_OVERRIDE_KEYS
        or not isinstance(manager, dict)
        or manager.keys() - MANAGER_ONLY_KEYS
    ):
        raise ValueError("实例配置继承格式不正确")
    return dict(local_keys=sorted(keys), manager_values=validate_settings(manager))


def instance_override(document, path):
    return document.get("instance_overrides", {}).get(
        policy_key(path), dict(local_keys=[], manager_values={})
    )


def effective_values(values, *, independent=False, override=None):
    override = override or dict(local_keys=[], manager_values={})
    return {
        **{
            key: value
            for key, value in values.items()
            if not (independent and key in SHARED_CONNECTION_KEYS)
            and key not in override["local_keys"]
        },
        **override["manager_values"],
    }


def instance_values(document, path, *, values=None):
    return effective_values(
        document["values"] if values is None else values,
        independent=document["independent_instances"].get(policy_key(path), False),
        override=instance_override(document, path),
    )


def apply_settings(conf, values, *, independent=False):
    """Apply a launch snapshot using Conf's existing target and legacy rules."""
    values = effective_values(validate_settings(values), independent=independent)
    if not values:
        return conf
    patch = {}
    for key, value in values.items():
        if key in MANAGER_ONLY_KEYS:
            continue
        if "." in key:
            parent, name = key.split(".", 1)
            patch.setdefault(parent, {})[name] = value
        else:
            patch[key] = value
    if any(key in values for key in TEMPLATE_KEYS):
        patch.setdefault("device", {})["instance_name"] = conf.device.instance_name
    return conf.updated(patch) if patch else conf


def launch_snapshot(conf, *, managed):
    if not managed:
        return conf, frozenset()
    document = read_document()
    values = instance_values(document, get_path("@app"))
    return apply_settings(conf, values), frozenset(values.keys() & LOCAL_OVERRIDE_KEYS)


def for_launch(conf, *, managed):
    return launch_snapshot(conf, managed=managed)[0]
