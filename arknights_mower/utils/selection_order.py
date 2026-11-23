from functools import cache

import cv2
import numpy as np

from arknights_mower.utils.image import loadres


def room_shows_two_slots(img) -> bool:
    """在入住详情的同一行核对“进驻人数”和分母“/2”。"""
    if not isinstance(img, np.ndarray) or img.shape != (1080, 1920, 3):
        return False
    try:
        template = loadres("room/occupancy_two", gray=True)
    except (OSError, cv2.error):
        return False
    if template is None or template.shape != (45, 210):
        return False
    footer = cv2.cvtColor(img[1003:1060, 1650:], cv2.COLOR_RGB2GRAY)
    locations = []
    for part in (template[:, :137], template[:, 173:]):
        score = cv2.matchTemplate(footer, part, cv2.TM_CCOEFF_NORMED)
        _, best, _, location = cv2.minMaxLoc(score)
        if best < 0.95:
            return False
        locations.append(location)
    (x, y), (end_x, end_y) = locations
    return abs(end_y - y) <= 1 and 165 <= end_x - x <= 181


@cache
def _slot_templates():
    try:
        atlas = loadres("selection_slot_digits", gray=True)
    except (OSError, cv2.error):
        return ()
    if atlas is None or atlas.shape != (400, 66):
        return ()
    digits = atlas.reshape(5, 80, 66)
    if np.ptp(digits, axis=(1, 2)).min() != 255:
        return ()
    return tuple(digits)


def selection_slot(img, scope) -> int | None:
    """从普通选人页面的姓名框定位卡片右上角，读取白色进驻序号。"""
    if (
        not isinstance(img, np.ndarray)
        or img.ndim != 3
        or img.shape[2] != 3
        or scope is None
    ):
        return None
    (left, top), (right, bottom) = scope
    if (
        not 180 <= right - left <= 210
        or bottom - top != 32
        or left < 0
        or top < 330
        or bottom > img.shape[0]
        or left + 189 > img.shape[1]
    ):
        return None
    templates = _slot_templates()
    if not templates:
        return None
    # 模板四周多读四像素，容纳姓名分割与滚动造成的位置偏差。
    region = img[top - 330 : top - 242, left + 115 : left + 189]
    white = cv2.inRange(region, (233, 233, 233), (255, 255, 255))
    scores = sorted(
        (
            (cv2.matchTemplate(white, digit, cv2.TM_CCOEFF_NORMED).max(), number)
            for number, digit in enumerate(templates, 1)
        ),
        reverse=True,
    )
    score, number = scores[0]
    if score >= 0.90 and score - scores[1][0] >= 0.08:
        return number
    return None
