"""Recognize the confirmed MuMu launcher advertisement from its UI hierarchy."""

import re
import xml.etree.ElementTree as ET

PACKAGE = "app.lawnchair"
MAX_UI_BYTES = 1024 * 1024
UI_DUMP_COMMAND = (
    "f=$(mktemp /data/local/tmp/mower-ui-XXXXXX) || exit 1; "
    "trap 'rm -f \"$f\"' EXIT; trap 'exit 1' HUP INT TERM; "
    'uiautomator dump "$f" >/dev/null 2>&1 && '
    f'head -c {MAX_UI_BYTES + 1} "$f"'
)


def is_mumu_launcher(focus: str) -> bool:
    return focus in {
        f"{PACKAGE}/{PACKAGE}.LawnchairLauncher",
        f"{PACKAGE}/.LawnchairLauncher",
    }


def startup_ad_close_point(data: bytes) -> tuple[int, int] | None:
    """Return a verified close-button center in Android display coordinates."""
    if not data or len(data) > MAX_UI_BYTES:
        raise ValueError("MuMu 控件信息为空或超过大小上限")
    start = data.find(b"<hierarchy")
    end = data.find(b"</hierarchy>", start)
    if start < 0 or end < 0:
        raise ValueError("MuMu 控件信息缺少完整层级")
    try:
        root = ET.fromstring(data[start : end + len(b"</hierarchy>")])
    except ET.ParseError as exc:
        raise ValueError("MuMu 控件信息无法解析") from exc

    def bounds(node):
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if match is None:
            raise ValueError("MuMu 广告控件的位置无效")
        left, top, right, bottom = map(int, match.groups())
        if not (left < right <= 16384 and top < bottom <= 16384):
            raise ValueError("MuMu 广告控件的位置超出范围")
        return left, top, right, bottom

    required = {f"{PACKAGE}:id/{name}" for name in ("pic", "member", "close")}
    for group in root.iter("node"):
        if not required.intersection(child.get("resource-id") for child in group):
            continue
        children = {
            child.get("resource-id"): child
            for child in group
            if child.get("package") == PACKAGE
        }
        pic = children.get(f"{PACKAGE}:id/pic")
        member = children.get(f"{PACKAGE}:id/member")
        close = children.get(f"{PACKAGE}:id/close")
        if (
            group.get("class") != "android.view.ViewGroup"
            or pic is None
            or member is None
            or close is None
            or pic.get("class") != "android.widget.ImageView"
        ):
            raise ValueError("MuMu 广告控件尚未完整确认")
        member_text = any(
            node.get("resource-id") == f"{PACKAGE}:id/memberText"
            and node.get("package") == PACKAGE
            and node.get("text") == "去广告"
            for node in member.iter("node")
        )
        if not member_text or any(
            node.get("clickable") != "true" or node.get("enabled") != "true"
            for node in (pic, close)
        ):
            raise ValueError("MuMu 广告关闭按钮尚未确认可点击")
        left, top, right, bottom = bounds(close)
        outer_left, outer_top, outer_right, outer_bottom = bounds(group)
        if not (
            outer_left <= left < right <= outer_right
            and outer_top <= top < bottom <= outer_bottom
        ):
            raise ValueError("MuMu 广告关闭按钮超出所属控件范围")
        return ((left + right) // 2, (top + bottom) // 2)
    return None
