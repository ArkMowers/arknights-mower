"""卫戍协议主题面板的文字与区域，坐标基于 1920 × 1080 画面。"""

from .model import GarrisonError, normal_name

DEFAULT_THEME = "卫戍协议终端"
THEMES = (DEFAULT_THEME, "乌萨斯齐心团", "“全能的”可露希尔")
TITLE = (0, 927, 930, 1010)
CARDS = (1430, 100, 1900, 910)
ACTION = (1440, 930, 1890, 1060)


def theme_label(frame, region, name=None):
    for text in frame.texts:
        x, y = text.center
        if text.score < 0.6 or not (
            region[0] <= x < region[2] and region[1] <= y < region[3]
        ):
            continue
        for theme in (name,) if name else THEMES:
            if normal_name(text.text) == normal_name(theme):
                return theme, text.center
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
