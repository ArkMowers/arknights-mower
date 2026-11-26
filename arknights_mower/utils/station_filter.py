"""从选人画面读取进驻筛选标题和菜单开合状态。"""

from functools import cache

import cv2
import numpy as np
from PIL import Image

from arknights_mower import __rootdir__

_TITLES = ("进驻状态", "宿舍锁定", "未进驻")
_MENU_ITEM = "全部"
_TITLE_SCOPE = ((1600, 35), (1715, 82))
_MENU_SCOPE = ((1645, 115), (1710, 163))
_ATLAS = __rootdir__ / "resources/room/station_filter_glyphs.png"


def _trim(mask):
    x, y, width, height = cv2.boundingRect(mask)
    return mask[y : y + height, x : x + width]


@cache
def _templates():
    # 前四行是 22 px 思源黑体字模，末两行是旧宿舍截图中的向下和向上箭头。
    try:
        with Image.open(_ATLAS) as image:
            if image.mode != "L" or image.size != (104, 156):
                return None
            atlas = np.asarray(image)
    except OSError:
        return None
    bands = [_trim(band) for band in np.vsplit(atlas, 6)]
    if any(band.size == 0 for band in bands):
        return None
    return dict(zip((*_TITLES, _MENU_ITEM), bands[:4], strict=True)), bands[4:]


def _ink(channel):
    return _trim(cv2.threshold(channel, 145, 255, cv2.THRESH_BINARY)[1])


def _overlap(sample, template):
    height, width = sample.shape
    template = cv2.resize(
        template, (width, height), interpolation=cv2.INTER_NEAREST_EXACT
    )
    common = cv2.countNonZero(cv2.bitwise_and(sample, template))
    return 2 * common / (cv2.countNonZero(sample) + cv2.countNonZero(template))


def _word(sample, templates, names):
    height, width = sample.shape
    if not 18 <= height <= 23:
        return None
    scores = sorted(
        (
            (_overlap(sample, templates[name]), name)
            for name in names
            if abs(width - len(name) * 22) <= 5
        ),
        reverse=True,
    )
    if not scores or scores[0][0] < 0.80:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.12:
        return None
    return scores[0][1]


def _match(frame):
    if (
        not isinstance(frame, np.ndarray)
        or frame.dtype != np.uint8
        or frame.shape != (1080, 1920, 3)
    ):
        return None
    templates = _templates()
    if templates is None:
        return None
    words, arrows = templates
    title = _word(_ink(frame[35:82, 1600:1711, 2]), words, _TITLES)
    if title is None:
        return None
    arrow = _ink(frame[35:82, 1711:1745, 2])
    height, width = arrow.shape
    if not (12 <= height <= 17 and 24 <= width <= 30):
        return None
    down, up = (_overlap(arrow, template) for template in arrows)
    if max(down, up) < 0.81 or abs(down - up) < 0.18:
        return None
    opened = up > down
    menu_item = _word(_ink(frame[115:163, 1645:1710, 2]), words, (_MENU_ITEM,))
    if opened != (menu_item == _MENU_ITEM):
        return None
    return title, opened


def _read_title_and_menu(frame, read_screen, *, menu):
    match = _match(frame)
    if match is not None:
        title, opened = match
        return title, menu and opened
    title = read_screen(frame, type="text", cord=_TITLE_SCOPE)
    if title not in (*_TITLES, _MENU_ITEM):
        return None, False
    opened = menu and read_screen(frame, type="text", cord=_MENU_SCOPE) == _MENU_ITEM
    return title, opened


def read_station_filter(frame, read_screen, *, menu=True) -> tuple[str | None, bool]:
    """字模无法判定时，用原读屏函数在同一帧读取标题和所需的菜单项。"""
    title, opened = _read_title_and_menu(frame, read_screen, menu=menu)
    return (_MENU_ITEM if title == "进驻状态" else title), opened


def station_filter_shows_all(frame, read_screen) -> bool:
    """选人排序和相邻页记录只接受筛选标题原文“进驻状态”。"""
    title, _ = _read_title_and_menu(frame, read_screen, menu=False)
    return title == "进驻状态"
