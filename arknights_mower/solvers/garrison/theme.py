"""卫戍协议主题面板的文字与区域，坐标基于 1920 × 1080 画面。"""

from .model import GarrisonError, normal_name

DEFAULT_THEME = "卫戍协议终端"
THEMES = (DEFAULT_THEME, "乌萨斯齐心团", "“全能的”可露希尔")
TITLE = (0, 927, 930, 1010)
CARDS = (1430, 100, 1900, 910)
ACTION = (1440, 930, 1890, 1060)


def theme_label(frame, region, name=None):
    labels = sorted(
        (
            t
            for t in frame.texts
            if t.score >= 0.6
            and region[0] <= t.center[0] < region[2]
            and region[1] <= t.center[1] < region[3]
        ),
        key=lambda t: t.x,
    )
    names = {normal_name(theme): theme for theme in ((name,) if name else THEMES)}
    for label in labels:
        if theme := names.get(normal_name(label.text)):
            return theme, label.center
    if region == TITLE and len(labels) > 1:
        for left, right in zip(labels, labels[1:]):
            height = min(left.height, right.height)
            if (
                abs(left.center[1] - right.center[1]) > height / 2
                or abs(right.x - (left.x + left.width)) > height
            ):
                return None
        if theme := names.get(normal_name("".join(t.text for t in labels))):
            return theme, labels[0].center
    return None


def equipped(frame):
    if frame.screen == "theme" and frame.find("^[已己]设置$", ACTION):
        if title := theme_label(frame, TITLE):
            return title[0]
    return None


def open_equipped(owner, frame):
    # 重新打开后，游戏默认展示实际启用的主题，即使上一次停在其他主题的预览页。
    if frame.screen == "theme" and not equipped(frame):
        owner.click((65, 58))
        frame = owner.wait(lambda f: f.screen == "lobby")
    if frame.screen == "lobby":
        owner.text_click(frame, "^更换主题$", (300, 910, 720, 1080))
        frame = owner.wait(equipped)
    if not equipped(frame):
        raise GarrisonError("无法确认卫戍协议当前使用的主题")
    return frame


def apply(owner, frame, name):
    if equipped(frame) == name:
        return
    card = theme_label(frame, CARDS, name)
    if not card:
        raise GarrisonError(f"主题列表中未识别到「{name}」")
    owner.click(card[1])
    frame = owner.wait(
        lambda f: (
            f.screen == "theme"
            and theme_label(f, TITLE, name)
            and (equipped(f) == name or f.find("^设置主题$", ACTION))
        )
    )
    if equipped(frame) != name:
        owner.text_click(frame, "^设置主题$", ACTION)
        owner.wait(lambda f: equipped(f) == name)
