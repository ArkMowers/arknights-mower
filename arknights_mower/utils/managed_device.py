"""Manager ownership of device and performance settings in managed processes."""

import copy
import math
import ntpath
import os

# Keep legacy inputs in the same boundary as their Device Profile equivalents.
DERIVED_IDENTITY_FIELDS = ("instance_uuid", "topology_fingerprint")

SETTINGS = (
    "device",
    "simulator",
    "adb",
    "maa_adb_path",
    "maa_path",
    "maa_conn_preset",
    "maa_touch_option",
    "package_type",
    "custom_screenshot",
    "droidcast",
    "mumu12IPC",
    "touch_method",
    "tap_to_launch_game",
    "close_simulator_when_idle",
    "exit_game_when_idle",
    "return_home_when_idle",
    "fix_mumu12_adb_disconnect",
    "performance_mode",
    "low_frame_rate_mode",
    "screenshot_interval",
    "selection_poll_interval",
    "selection_transition_timeout",
    "waiting_scene",
    "maa_mirrorchyan_token",
    "maa_update_channel",
    "maa_auto_check_update",
    "maa_auto_update",
    "maa_resource_auto_check_update",
    "maa_resource_auto_update",
)

EXTRA_SETTINGS = (
    "resource_update",
    "screenshot",
    "screenshot_archive_limit_mb",
    "depot_history_limit",
    "depot_history_keep",
)


def extra_settings_allowed(configuration):
    return not enabled() or configuration.extra_settings_visible


def protected_settings(configuration):
    keys = SETTINGS
    if not extra_settings_allowed(configuration):
        keys += EXTRA_SETTINGS
    elif enabled() and not configuration.updates_enabled:
        keys += ("resource_update",)
    if enabled():
        from . import config

        keys = tuple(dict.fromkeys((*keys, *config.manager_inherited_settings)))
    return keys


def operation_blocked(path, method, configuration):
    if not enabled() or method == "OPTIONS":
        return False
    if path in {
        "/device/preflight",
        "/device/discover",
        "/device/start",
        "/device/avd/start",
        "/device/redroid/start",
        "/device/genymotion/start",
        "/device/boss_key",
        "/test-custom-screenshot",
        "/check-maa",
        "/maa-conn-preset",
    } or (path == "/device/performance-test" and method not in {"GET", "HEAD"}):
        return True
    if path.startswith(("/maa-update/", "/maa-resource-update/")):
        return not path.endswith(("/info", "/status"))
    if extra_settings_allowed(configuration):
        return False
    return (
        (path in {"/network/settings", "/network/test"} and method == "POST")
        or (
            path.startswith("/software-update/")
            and (
                (method not in {"GET", "HEAD"} and path != "/software-update/check")
                or path.endswith(
                    ("/source/history", "/source/pulls", "/release/rollback-options")
                )
            )
        )
        or path
        in {"/resource/install", "/resource-update/manual", "/config-backup/import"}
    )


def enabled():
    return os.environ.get("MOWER_MANAGED") == "1"


def snapshot(configuration):
    data = configuration.model_dump(mode="json")
    return {key: copy.deepcopy(data[key]) for key in SETTINGS}


def changed(current, proposed):
    return snapshot(current) != snapshot(proposed)


def preserve(data, current):
    """Imports retain the current manager-owned values, including legacy aliases."""
    if enabled():
        current_values = current.model_dump(mode="json")
        for key in protected_settings(current):
            data[key] = copy.deepcopy(current_values[key])
        webview = data.get("webview")
        if isinstance(webview, dict):
            webview.update(port=current.webview.port, token=current.webview.token)
        for key in (
            "start_automatically",
            "ai_assistant_enabled",
            "updates_enabled",
            "extra_settings_visible",
        ):
            data[key] = getattr(current, key)
        from .manager_common import MANAGER_ONLY_KEYS, instance_override, read_document
        from .path import get_path

        document = read_document()
        selected = set(document["values"]) | set(
            instance_override(document, get_path("@app"))["local_keys"]
        )
        for key in selected:
            if key in MANAGER_ONLY_KEYS:
                continue
            parts = key.split(".")
            source, destination = current_values, data
            for part in parts[:-1]:
                source = source[part]
                if not isinstance(destination.get(part), dict):
                    destination[part] = {}
                destination = destination[part]
            destination[parts[-1]] = copy.deepcopy(source[parts[-1]])
    return data


def validate_patch(values):
    from .manager_common import validate_waiting_scene

    definitions = {field["key"]: field for field in fields()}
    if not isinstance(values, dict) or not values or set(values) - definitions.keys():
        raise ValueError("不支持的设备配置项")
    patch = {}
    for key, value in values.items():
        field = definitions[key]
        kind = field["kind"]
        if kind == "waiting_scene":
            patch[key] = validate_waiting_scene(value)
            continue
        valid = (
            type(value) is bool
            if kind == "boolean"
            else type(value) is int
            if kind == "integer"
            else type(value) in (int, float) and math.isfinite(value)
            if kind == "number"
            else isinstance(value, str)
        )
        if not valid or (
            kind == "select" and value not in [item[0] for item in field["options"]]
        ):
            raise ValueError(f"{field['label']} 的值无效")
        if isinstance(value, str) and (len(value) > 4096 or "\0" in value):
            raise ValueError(f"{field['label']} 的文本无效")
        if kind in {"integer", "number"} and (
            value < field.get("min", 0) or value > field.get("max", float("inf"))
        ):
            raise ValueError(f"{field['label']} 超出范围")
        if "." in key:
            parent, child = key.split(".", 1)
            patch.setdefault(parent, {})[child] = value
        else:
            patch[key] = value
    return patch


def discover(configuration):
    """Reuse bounded device discovery without installing a process-wide Conf."""
    from .device.avd import AVDController
    from .device.discovery import DiscoveryService
    from .device.genymotion import GenymotionController
    from .device.preflight import PreflightService
    from .device.preflight_io import ProductionPreflightIO
    from .device.redroid import RedroidController
    from .device.session_io import ProductionSimulator
    from .device.waydroid import WaydroidController
    from .device.windows_discovery import WindowsDiscoveryIO

    avd, waydroid = AVDController(), WaydroidController()
    redroid, genymotion = RedroidController(), GenymotionController()
    simulator = ProductionSimulator(
        avd=avd, waydroid=waydroid, redroid=redroid, genymotion=genymotion
    )
    preflight = PreflightService(ProductionPreflightIO(lambda: configuration))
    service = DiscoveryService(
        WindowsDiscoveryIO(),
        simulator,
        avd=avd,
        waydroid=waydroid,
        redroid=redroid,
        genymotion=genymotion,
    )
    return service.discover(
        configuration.device, preflight.host_platform(), preflight
    ).to_dict()


def project_shared_candidates(result, shared_values):
    """Keep detected identities within the selected shared simulator template."""
    from .manager_common import TEMPLATE_KEYS
    from .path import resolve_config_path

    template = {key.split(".")[1]: shared_values[key] for key in TEMPLATE_KEYS}
    windows = template["preset_id"].startswith("windows.")

    def normalized(value):
        value = resolve_config_path(value)
        return (
            ntpath.normcase(ntpath.normpath(value))
            if windows
            else os.path.normpath(os.path.expanduser(value))
        )

    locator = None
    if template["preset_id"] == "windows.nox":
        from .device.nox_discovery import locate_nox_manager

        locator = locate_nox_manager
    elif template["preset_id"] in {"windows.ldplayer9", "windows.ldplayer14"}:
        from .device.ldplayer_discovery import locate_ldplayer_manager

        locator = locate_ldplayer_manager
    elif template["preset_id"] == "windows.mumu12":
        from .device.mumu_discovery import MuMuDiscoveryIO

        locator = MuMuDiscoveryIO._manager_candidate

    def matches_path(key, expected, actual):
        if not expected or normalized(actual) == normalized(expected):
            return True
        if (
            locator is not None
            and key in {"installation_path", "manager_path"}
            and actual
        ):
            try:
                selected_manager, _ = locator(expected)
                detected_manager, _ = locator(actual)
                return bool(
                    selected_manager
                    and detected_manager
                    and normalized(str(selected_manager))
                    == normalized(str(detected_manager))
                )
            except (OSError, ValueError):
                return False
        return False

    result = copy.deepcopy(result)
    for candidate in result.get("candidates", []):
        binding = candidate.get("binding", {})
        matches = binding.get("preset_id") == template["preset_id"] and all(
            matches_path(key, value, binding.get(key, ""))
            for key, value in template.items()
            if key != "preset_id"
        )
        candidate["shared_template_matches"] = matches
        if matches:
            candidate["binding"] = {**binding, **template}
    return result


def fields():
    from pydantic import TypeAdapter

    from .config import Conf
    from .manager_common import FIELDS

    shared = {field["key"]: field for field in FIELDS}
    groups = {
        "模拟器与设备": {
            "device.preset_id": "模拟器预设",
            "device.installation_path": "模拟器安装目录",
            "device.manager_path": "模拟器管理程序",
            "device.config_path": "模拟器配置文件",
            "device.adb_path": "ADB 程序",
            "device.instance_id": "模拟器实例编号",
            "device.instance_name": "模拟器实例名称",
            "device.instance_uuid": "实例 UUID",
            "device.topology_fingerprint": "实例拓扑指纹",
            "device.last_serial": "ADB 连接地址",
            "device.game_package": "游戏包名",
            "simulator.wait_time": "模拟器启动等待（秒）",
        },
        "截图与触控": {
            "device.screenshot_backend": "截图后端",
            "device.touch_backend": "触控后端",
            "custom_screenshot.command": "自定义截图命令",
            "droidcast.rotate": "旋转截图 180 度",
            "maa_conn_preset": "MAA 连接预设",
            "maa_touch_option": "MAA 触控方式",
        },
        "连接恢复": {
            "device.recovery_timeout": "恢复总时限（秒）",
            "device.recovery_attempts": "恢复尝试次数",
            "device.recovery_local_wait": "局部恢复等待（秒）",
            "device.recovery_shutdown_wait": "关闭等待（秒）",
            "device.manager_query_timeout": "管理程序查询时限（秒）",
            "device.simulator_hotkey": "模拟器老板键",
            "device.simulator_hotkey_delay": "老板键等待（秒）",
        },
        "游戏启动与空闲": {
            "tap_to_launch_game.mode": "启动游戏方式",
            "tap_to_launch_game.x": "启动点击 X",
            "tap_to_launch_game.y": "启动点击 Y",
            "tap_to_launch_game.command": "自定义游戏启动命令",
            "close_simulator_when_idle": "空闲时关闭模拟器",
            "exit_game_when_idle": "空闲时退出游戏",
            "return_home_when_idle": "空闲时返回首页",
            "fix_mumu12_adb_disconnect": "关闭 MuMu 12 时断开当前 ADB 连接",
        },
        "运行参数": {"waiting_scene": "页面等待参数"},
        "MAA": {"maa_path": "MAA 目录"},
        "截图归档": {
            "screenshot": "截图保存时间（小时）",
            "screenshot_archive_limit_mb": "报错归档空间上限（MiB）",
        },
        "性能": {
            "performance_mode": "设备性能适配",
            "screenshot_interval": "截图间隔（毫秒）",
            "selection_poll_interval": "选人采样间隔（秒）",
            "selection_transition_timeout": "选人反馈超时（秒）",
        },
    }
    result = []
    for group, paths in groups.items():
        for key, label in paths.items():
            model = Conf
            parts = key.split(".")
            for part in parts[:-1]:
                model = model.model_fields[part].annotation
            schema = TypeAdapter(
                model.model_fields[parts[-1]].rebuild_annotation()
            ).json_schema()
            field = dict(key=key, label=label, group=group)
            if key in {f"device.{name}" for name in DERIVED_IDENTITY_FIELDS}:
                field["read_only"] = True
            kind = schema.get("type", "string")
            field["kind"] = {
                "boolean": "boolean",
                "integer": "integer",
                "number": "number",
            }.get(kind, "text")
            if "enum" in schema:
                field.update(kind="select", options=[(v, v) for v in schema["enum"]])
            if key == "tap_to_launch_game.mode":
                field.update(
                    kind="select",
                    options=[
                        ("adb", "ADB"),
                        ("tap", "点击屏幕"),
                        ("custom", "自定义命令"),
                    ],
                )
            if key in shared:
                field.update(
                    {
                        k: copy.deepcopy(v)
                        for k, v in shared[key].items()
                        if k in {"kind", "options", "min", "max", "scenes"}
                    }
                )
            if (
                key == "device.screenshot_backend"
                and ("custom", "自定义命令") not in field["options"]
            ):
                field["options"].append(("custom", "自定义命令"))
            if key in {"device.config_path", "device.manager_path"}:
                field["kind"] = "file"
            if key in {"device.installation_path", "maa_path"}:
                field["kind"] = "directory"
            for source, target in (("minimum", "min"), ("maximum", "max")):
                if source in schema:
                    field[target] = schema[source]
            result.append(field)
    return result
