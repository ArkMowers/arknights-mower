"""Opt-in launch settings shared by desktop instances of one manager."""

import copy
import json
import math
import sys

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
            "可通过“在浏览器中打开”访问，或从托盘打开内置窗口；关闭网页不会停止实例。"
            "自动化是否开始仍由实例原有设置决定，保存后对下次启动生效。"
        ),
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
    dict(key="account", group="邮件发信人", label="发件邮箱", kind="text", default=""),
    dict(
        key="pass_code",
        group="邮件发信人",
        label="邮箱授权码或密码",
        kind="password",
        default="",
    ),
    dict(
        key="custom_smtp_server.enable",
        group="邮件发信人",
        label="自定义 SMTP",
        kind="boolean",
        default=False,
    ),
    dict(
        key="custom_smtp_server.server",
        group="邮件发信人",
        label="SMTP 服务器",
        kind="text",
        default="",
    ),
    dict(
        key="custom_smtp_server.encryption",
        group="邮件发信人",
        label="SMTP 加密方式",
        kind="select",
        default="starttls",
        options=[("starttls", "STARTTLS"), ("tls", "SSL/TLS")],
    ),
    dict(
        key="custom_smtp_server.ssl_port",
        group="邮件发信人",
        label="SMTP 端口",
        kind="integer",
        default=587,
        min=1,
        max=65535,
    ),
]
_FIELDS_BY_KEY = {field["key"]: field for field in FIELDS}
_BACKENDS = {"device.screenshot_backend", "device.touch_backend"}


def settings_path():
    return get_path("@app/config/manager-common.json", space="")


def validate_settings(values):
    if not isinstance(values, dict) or values.keys() - _FIELDS_BY_KEY.keys():
        raise ValueError("不支持的公共配置项")
    for key, value in values.items():
        field = _FIELDS_BY_KEY[key]
        kind = field["kind"]
        valid = True
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
            if kind in {"directory", "file"}:
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
    return copy.deepcopy(values)


def read_settings(path=None):
    try:
        raw = (path or settings_path()).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return validate_settings(json.loads(raw))


def apply_settings(conf, values):
    """Apply a launch snapshot using Conf's existing target and legacy rules."""
    values = validate_settings(values)
    if not values:
        return conf
    patch = {}
    for key, value in values.items():
        if key == "startup_mode":
            continue
        if "." in key:
            parent, name = key.split(".", 1)
            patch.setdefault(parent, {})[name] = value
        else:
            patch[key] = value
    return conf.updated(patch) if patch else conf


def for_launch(conf, *, managed):
    return apply_settings(conf, read_settings()) if managed else conf
