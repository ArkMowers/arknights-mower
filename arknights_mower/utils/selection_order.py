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
def _occupancy_templates():
    try:
        caption = loadres("room/occupancy_two", gray=True)
        digits = loadres("room/occupancy_digits", gray=True)
    except (OSError, cv2.error):
        return None
    if not isinstance(caption, np.ndarray) or caption.shape != (45, 210):
        return None
    if not isinstance(digits, np.ndarray) or digits.shape != (270, 67):
        return None
    caption = caption[:, :137]
    digits = digits.reshape(6, 45, 67)
    if (
        np.ptp(caption) == 0
        or np.ptp(digits[:, :, :28], axis=(1, 2)).min() == 0
        or np.ptp(digits[[1, 2, 3, 5], :, 28:], axis=(1, 2)).min() == 0
    ):
        return None
    return caption, digits


def read_room_occupancy(
    img, expected_capacity: int | None = None
) -> tuple[int, int] | None:
    """在同一栏核对标题、人形、分子和分母，返回实际人数与容量。"""
    capacities = (1, 2, 3, 5)
    if expected_capacity is not None:
        if type(expected_capacity) is not int or expected_capacity not in capacities:
            return None
        capacities = (expected_capacity,)
    if not isinstance(img, np.ndarray) or img.dtype != np.uint8:
        return None
    if img.shape == (1080, 1920):
        footer = img[1003:1060, 1595:]
    elif img.shape == (1080, 1920, 3):
        footer = cv2.cvtColor(img[1003:1060, 1595:], cv2.COLOR_RGB2GRAY)
    else:
        return None
    templates = _occupancy_templates()
    if templates is None:
        return None
    caption, digits = templates
    scores = cv2.matchTemplate(footer[:, 65:245], caption, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    x += 65
    if score < 0.95 or x + 213 > footer.shape[1]:
        return None
    columns = [x - dx for dx in (7, 21, 34, 48, 61)]
    heads = [int(footer[y + 4, col]) for col in columns]
    count = sum(v < 105 for v in heads)
    for i, col in enumerate(columns):
        body = footer[y + 20, col]
        if i < count:
            if heads[i] >= 105 or body >= 105 or footer[y + 10, col] < 130:
                return None
        elif heads[i] < 180 or body < 180:
            return None

    def matches(left, glyph):
        region = footer[y : y + 45, x + left - 2 : x + left + glyph.shape[1] + 2]
        return cv2.matchTemplate(region, glyph, cv2.TM_CCOEFF_NORMED).max() >= 0.95

    if not matches(146, digits[count, :, :28]):
        return None
    capacities = [
        size
        for size in capacities
        if size >= count and matches(172, digits[size, :, 28:])
    ]
    if len(capacities) == 1:
        return count, capacities[0]
    return None


def room_occupancy(img, capacity: int) -> int | None:
    if capacity is None:
        return None
    reading = read_room_occupancy(img, capacity)
    return reading[0] if reading is not None else None


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
