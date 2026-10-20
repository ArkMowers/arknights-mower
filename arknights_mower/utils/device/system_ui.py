"""Validate Android system-error dialog controls before closing the dialog."""

import re
import xml.etree.ElementTree as ET

MAX_UI_BYTES = 1024 * 1024


def wallpaper_color_state(value: str | None, current_user: int) -> str | None:
    """Classify the current user's colors in a recognized SparseArray dump."""
    if (
        not isinstance(value, str)
        or not value.startswith("{")
        or not value.endswith("}")
        or type(current_user) is not int
        or not 0 <= current_user <= 2147483647
    ):
        return None
    body = value[1:-1]
    states = {}
    if body:
        for entry in body.split(", "):
            match = re.fullmatch(
                r"(0|[1-9][0-9]{0,9})="
                r"(null|\[WallpaperColors: (?:[0-9a-f]{1,8} )+"
                r"h: (0|-?[1-9][0-9]{0,9})\])",
                entry,
            )
            if match is None:
                return None
            user = int(match.group(1))
            hints = match.group(3)
            if (
                user > 2147483647
                or user in states
                or hints is not None
                and not -2147483648 <= int(hints) <= 2147483647
            ):
                return None
            states[user] = "absent" if match.group(2) == "null" else "present"
    return states.get(current_user, "unread")


def system_ui_error_close_point(
    data: bytes | str, *, anr: bool
) -> tuple[int, int] | None:
    """Return the confirmed close-button center, or wait while it is disabled."""
    if not isinstance(data, (bytes, str)) or not data or len(data) > MAX_UI_BYTES:
        raise ValueError("系统界面控件信息为空或超过大小上限")
    try:
        raw = data.encode("utf8") if isinstance(data, str) else data
        raw.decode("utf8")
    except UnicodeError as exc:
        raise ValueError("系统界面控件信息无法解码") from exc
    if len(raw) > MAX_UI_BYTES:
        raise ValueError("系统界面控件信息超过大小上限")
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("系统界面控件信息包含不支持的 XML 声明")
    start = raw.find(b"<hierarchy")
    end = raw.find(b"</hierarchy>", start)
    if start < 0 or end < 0 or raw.count(b"<hierarchy") != 1:
        raise ValueError("系统界面控件信息缺少完整层级")
    prefix = re.sub(rb"<\?xml\s+[^?]*\?>", b"", raw[:start])
    suffix = raw[end + len(b"</hierarchy>") :]
    if any(mark in prefix or mark in suffix for mark in (b"<", b">")):
        raise ValueError("系统界面控件信息包含额外 XML 内容")
    try:
        root = ET.fromstring(raw[start : end + len(b"</hierarchy>")])
    except ET.ParseError as exc:
        raise ValueError("系统界面控件信息无法解析") from exc
    if any(node.tag != "node" for node in root.iter() if node is not root):
        raise ValueError("系统界面控件信息包含未知层级")

    names = ("alertTitle", "aerr_close", "aerr_wait")
    matches = {
        name: [
            node
            for node in root.iter("node")
            if node.get("resource-id") == f"android:id/{name}"
        ]
        for name in names
    }
    if any(len(matches[name]) != 1 for name in names[:2]) or len(
        matches["aerr_wait"]
    ) != int(anr):
        raise ValueError("系统界面错误弹窗控件尚未完整确认")
    controls = {name: values[0] for name, values in matches.items() if values}
    parents = {child: node for node in root.iter() for child in node}

    def ancestors(node):
        result = []
        while node is not root:
            result.append(node)
            node = parents[node]
        return result

    paths = {name: ancestors(node) for name, node in controls.items()}
    dialog = paths["alertTitle"][-1]
    if dialog in controls.values() or any(
        path[-1] is not dialog for path in paths.values()
    ):
        raise ValueError("系统界面错误弹窗控件不属于同一窗口")
    if any(node.get("package") != "android" for node in dialog.iter("node")):
        raise ValueError("系统界面错误弹窗包含其他应用控件")
    for name, node in controls.items():
        expected = "TextView" if name == "alertTitle" else "Button"
        if node.get("class") != f"android.widget.{expected}":
            raise ValueError("系统界面错误弹窗控件类型尚未确认")
        if name != "alertTitle" and node.get("clickable") != "true":
            raise ValueError("系统界面错误弹窗按钮尚未确认可点击")

    def bounds(node):
        match = re.fullmatch(
            r"\[([0-9]+),([0-9]+)\]\[([0-9]+),([0-9]+)\]",
            node.get("bounds", ""),
        )
        if match is None:
            raise ValueError("系统界面错误弹窗控件的位置无效")
        left, top, right, bottom = map(int, match.groups())
        if not (left < right <= 16384 and top < bottom <= 16384):
            raise ValueError("系统界面错误弹窗控件的位置超出范围")
        return left, top, right, bottom

    close_ancestors = set(paths["aerr_close"])
    common = next(node for node in paths["alertTitle"][1:] if node in close_ancestors)
    dialog_bounds = bounds(dialog)
    common_bounds = bounds(common)

    def contains(outer, inner):
        left, top, right, bottom = inner
        return (
            outer[0] <= left < right <= outer[2]
            and outer[1] <= top < bottom <= outer[3]
        )

    for name, node in controls.items():
        observed = bounds(node)
        if not contains(dialog_bounds, observed) or (
            name != "aerr_wait" and not contains(common_bounds, observed)
        ):
            raise ValueError("系统界面错误弹窗控件超出所属容器范围")
    close = controls["aerr_close"]
    enabled = close.get("enabled")
    if enabled not in {"true", "false"}:
        raise ValueError("系统界面错误弹窗关闭按钮状态尚未确认")
    if enabled == "false":
        return None
    left, top, right, bottom = bounds(close)
    return (left + right) // 2, (top + bottom) // 2
