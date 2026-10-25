"""实例的窗口设置与界面偏好；读改写共用跨进程文件锁。"""

import errno
import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import contextmanager
from threading import RLock

import yaml
from yamlcore import CoreDumper, CoreLoader

from arknights_mower.utils.config import atomic_write, gui_path
from arknights_mower.utils.window_shell import WindowRatio

_gui_lock = RLock()
_KEY_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")
_MAX_GROUPS = 20
_MAX_KNOWN_KEYS = 100
_MAX_PLACEMENTS = 2200
_WATERMARK_CONFIRMATION = "反馈问题时务必说明具体版本"
_WATERMARK_SIGNATURE_MESSAGE = b"arknights-mower:watermark-hidden:v1"


class GuiStorageError(OSError):
    """Saved GUI preferences could not be read without losing existing data."""


@contextmanager
def _gui_file_lock(timeout=3.0):
    # Keep a stable lock file across atomic replacements and process exits.
    gui_path.parent.mkdir(parents=True, exist_ok=True)
    with gui_path.with_suffix(gui_path.suffix + ".lock").open("a+b") as stream:
        if os.name == "nt" and os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("界面配置正在保存，请稍后重试") from exc
                time.sleep(min(0.02, remaining))
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_gui_data(*, strict=False) -> dict:
    if not gui_path.is_file():
        return {}
    try:
        with gui_path.open("r", encoding="utf-8") as stream:
            data = yaml.load(stream, Loader=CoreLoader)
        if data is None:
            return {}
        if not isinstance(data, dict):
            if strict:
                raise ValueError("gui.yml 必须包含配置对象")
            return {}
        return data
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if strict:
            raise GuiStorageError("无法读取已保存的界面配置") from exc
        return {}


def update_gui_data(update):
    # 窗口与后端进程在锁内读取最新文件，再提交本次字段修改。
    with _gui_lock, _gui_file_lock():
        data = read_gui_data(strict=True)
        result = update(data)

        def dump(stream):
            yaml.dump(
                data, stream, Dumper=CoreDumper, encoding="utf-8", allow_unicode=True
            )

        atomic_write(gui_path, dump)
        return result


def _update_gui_data(**changes) -> None:
    update_gui_data(lambda data: data.update(changes))


def _valid_key(value) -> bool:
    return isinstance(value, str) and _KEY_PATTERN.fullmatch(value) is not None


def validate_sidebar(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("version")) is not int:
        raise ValueError("侧栏配置格式无效")
    if value["version"] != 3:
        raise ValueError("侧栏配置版本无效")
    groups = value.get("groups")
    placements = value.get("placements")
    known_keys = value.get("knownKeys")
    if (
        not isinstance(groups, list)
        or len(groups) > _MAX_GROUPS
        or not isinstance(placements, list)
        or len(placements) > _MAX_PLACEMENTS
        or not isinstance(known_keys, list)
        or len(known_keys) > _MAX_KNOWN_KEYS
        or any(not _valid_key(key) for key in known_keys)
        or len(set(known_keys)) != len(known_keys)
    ):
        raise ValueError("侧栏配置条目无效或超过上限")
    group_keys = {"ungrouped", "footer"}
    clean_groups = []
    for group in groups:
        if (
            not isinstance(group, dict)
            or not _valid_key(group.get("key"))
            or group["key"] in group_keys | {"pinned"}
            or not isinstance(group.get("title"), str)
            or not 1 <= len(group["title"].strip()) <= 80
            or type(group.get("collapsed")) is not bool
        ):
            raise ValueError("侧栏分组无效")
        group_keys.add(group["key"])
        clean_groups.append(
            {
                "key": group["key"],
                "title": group["title"].strip(),
                "collapsed": group["collapsed"],
            }
        )
    clean_placements = []
    placement_ids = set()
    for placement in placements:
        if (
            not isinstance(placement, dict)
            or not _valid_key(placement.get("id"))
            or placement["id"] in placement_ids
            or not _valid_key(placement.get("key"))
            or not isinstance(placement.get("group"), str)
            or placement["group"] not in group_keys
            or type(placement.get("visible")) is not bool
            or type(placement.get("pinned")) is not bool
        ):
            raise ValueError("侧栏入口无效")
        placement_ids.add(placement["id"])
        clean_placements.append(
            {key: placement[key] for key in ("id", "key", "group", "visible", "pinned")}
        )
    return {
        "version": 3,
        "knownKeys": list(known_keys),
        "groups": clean_groups,
        "placements": clean_placements,
    }


def load_sidebar() -> dict | None:
    value = read_gui_data(strict=True).get("sidebar")
    if not isinstance(value, dict):
        return None
    if type(value.get("version")) is int and value["version"] in (1, 2):
        return value
    try:
        return validate_sidebar(value)
    except ValueError:
        return None


def save_sidebar(value: object) -> dict:
    sidebar = validate_sidebar(value)
    _update_gui_data(sidebar=sidebar)
    return sidebar


def load_software_version_display() -> str:
    value = read_gui_data(strict=True).get("software_version_display")
    return value if value in ("version", "channel") else "version"


def save_software_version_display(value: object) -> str:
    save_appearance({"software_version_display": value})
    return value


def load_software_version_language() -> str:
    value = read_gui_data(strict=True).get("software_version_language")
    return value if value in ("zh", "en") else "en"


def load_task_settings_layout() -> str:
    value = read_gui_data(strict=True).get("task_settings_layout")
    return value if value in ("checklist", "waterfall") else "checklist"


def load_watermark_visible() -> bool:
    data = read_gui_data(strict=True)
    if data.get("watermark_visible") is not False:
        return True
    signature = data.get("watermark_signature")
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        return True
    key = _watermark_key()
    return key is None or not hmac.compare_digest(signature, _watermark_signature(key))


def _watermark_key(*, create=False) -> bytes | None:
    path = gui_path.with_name("gui-watermark.key")
    try:
        with path.open("rb") as stream:
            raw = stream.read(65)
    except FileNotFoundError:
        raw = b""
    try:
        key = bytes.fromhex(raw.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        key = b""
    if len(raw) == 64 and len(key) == 32:
        return key
    if not create:
        return None
    key = secrets.token_bytes(32)
    atomic_write(path, lambda stream: stream.write(key.hex()))
    return key


def _watermark_signature(key: bytes) -> str:
    return hmac.new(key, _WATERMARK_SIGNATURE_MESSAGE, hashlib.sha256).hexdigest()


def save_appearance(changes: dict) -> dict:
    fields = {
        "software_version_display": (
            str,
            ("version", "channel"),
            "软件版本显示方式无效",
        ),
        "software_version_language": (str, ("zh", "en"), "软件版本类型语言无效"),
        "task_settings_layout": (
            str,
            ("checklist", "waterfall"),
            "任务配置显示方式无效",
        ),
        "watermark_visible": (bool, (True, False), "版本水印显示设置无效"),
    }
    if (
        not isinstance(changes, dict)
        or not changes
        or not changes.keys() <= fields.keys() | {"watermark_confirmation"}
    ):
        raise ValueError("请提供有效的外观配置")
    values = {key: value for key, value in changes.items() if key in fields}
    if not values:
        raise ValueError("请提供有效的外观配置")
    for key, value in values.items():
        value_type, choices, message = fields[key]
        if not isinstance(value, value_type) or value not in choices:
            raise ValueError(message)
    if values.get("watermark_visible") is False:
        if changes.get("watermark_confirmation") != _WATERMARK_CONFIRMATION:
            raise ValueError("隐藏版本水印前，请输入：反馈问题时务必说明具体版本")
    elif "watermark_confirmation" in changes:
        raise ValueError("仅隐藏版本水印时需要提交确认文字")

    def update(data):
        data.update(values)
        if values.get("watermark_visible") is False:
            data["watermark_signature"] = _watermark_signature(
                _watermark_key(create=True)
            )
        elif values.get("watermark_visible") is True:
            data.pop("watermark_signature", None)

    update_gui_data(update)
    return values


def load_window_mode() -> str:
    mode = read_gui_data().get("window_mode")
    return mode if mode in ("normal", "maximized") else "normal"


def save_window_mode(mode: str) -> None:
    if mode not in ("normal", "maximized"):
        raise ValueError("Unsupported window mode")
    _update_gui_data(window_mode=mode)


def load_window_ratio() -> WindowRatio | None:
    """读取窗口尺寸占屏幕工作区的比例（width/height 各一个 0~3 之间的数）。

    存比例而不是绝对像素：窗口大小是设备相关的配置，换电脑/换分辨率时绝对像素
    会不匹配；比例则始终按当前屏幕换算。文件缺失或内容非法返回 None。
    """
    try:
        ratio = read_gui_data()["ratio"]
        width = float(ratio["width"])
        height = float(ratio["height"])
        if not (0 < width <= 3 and 0 < height <= 3):
            return None
        return WindowRatio(width, height)
    except (OSError, TypeError, KeyError, ValueError):
        return None


def save_window_ratio(ratio: WindowRatio) -> None:
    """写入窗口尺寸比例（调用方已消毒，非法值不进盘），走原子写。"""
    _update_gui_data(ratio={"width": ratio.width, "height": ratio.height})


def load_close_preference() -> dict:
    value = read_gui_data().get("close_preference")
    if not isinstance(value, dict):
        return {"choice": "tray", "remember": False}
    return {
        "choice": value.get("choice")
        if value.get("choice") in ("tray", "exit")
        else "tray",
        "remember": value.get("remember") is True,
    }


def save_close_preference(choice: str, remember: bool) -> bool:
    if choice not in ("tray", "exit") or type(remember) is not bool:
        raise ValueError("Invalid close preference")
    _update_gui_data(close_preference={"choice": choice, "remember": remember})
    return True


def load_window_launch_mode() -> str:
    mode = read_gui_data().get("window_launch_mode")
    return mode if mode in ("last", "normal", "maximized") else "last"


def save_window_launch_mode(mode: str) -> bool:
    if mode not in ("last", "normal", "maximized"):
        raise ValueError("Invalid launch mode")
    _update_gui_data(window_launch_mode=mode)
    return True
