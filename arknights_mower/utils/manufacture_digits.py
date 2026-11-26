import re
from functools import lru_cache

import cv2
import numpy as np

from arknights_mower.utils.image import loadres


def _normalize(ink):
    x, y, width, height = cv2.boundingRect(ink)
    pixels = cv2.resize(
        ink[y : y + height, x : x + width].astype(np.float32) / 255,
        (24, 32),
        interpolation=cv2.INTER_AREA,
    )
    return pixels, width / height


@lru_cache(maxsize=1)
def _digit_templates():
    glyphs = []
    for digit in range(10):
        try:
            template = loadres(f"drone_count/{digit}", gray=True)
        except (OSError, cv2.error):
            return None
        if template is None or not np.ptp(template):
            return None
        low, high, _, _ = cv2.minMaxLoc(template)
        # 字号和字色改变时，二值化后的笔画宽度也会变。
        glyphs.extend(
            _normalize(cv2.inRange(template, low + weight * (high - low), 255))
            for weight in (0.3, 0.4, 0.5, 0.6, 0.7)
        )
    pixels, ratios = map(np.asarray, zip(*glyphs))
    return pixels, ratios


def _match_digit(ink, max_error, min_gap):
    templates = _digit_templates()
    if templates is None:
        return None
    pixels, ratios = templates
    glyph, ratio = _normalize(ink)
    error = np.mean((pixels - glyph) ** 2, axis=(1, 2))
    error += 0.25 * np.minimum(np.abs(np.log(ratios / ratio)), 0.4)
    scores = error.reshape(10, -1).min(axis=1)
    best, second = np.argsort(scores)[:2]
    if scores[best] <= max_error and scores[second] - scores[best] >= min_gap:
        return str(best)


def _components(mask):
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    return labels, sorted(
        (
            (x, y, w, h, i)
            for i, (x, y, w, h, area) in enumerate(stats[1:], 1)
            if area >= 5
        )
    )


def _component_ink(labels, x, y, w, h, label):
    return cv2.inRange(labels[y : y + h, x : x + w], int(label), int(label))


def read_manufacture_quantity(image):
    if getattr(image, "shape", None) != (80, 135, 3) or image.dtype != np.uint8:
        return None
    labels, boxes = _components(cv2.inRange(image, (175, 175, 175), (255, 255, 255)))
    # 数量框显示两位数字。少一位可能是过渡帧，交给原有读数路径处理。
    if len(boxes) != 2:
        return None
    digits = []
    for (x, y, w, h, label), center in zip(boxes, (49, 92)):
        if not (abs(x + w / 2 - center) <= 9 and 12 <= y <= 16 and 52 <= h <= 58):
            return None
        digit = _match_digit(_component_ink(labels, x, y, w, h, label), 0.12, 0.06)
        if digit is None:
            return None
        digits.append(digit)
    return int("".join(digits))


def read_manufacture_adjusted_clock(image):
    if getattr(image, "shape", None) != (65, 210, 3) or image.dtype != np.uint8:
        return None
    red, green, blue = cv2.split(image)
    mask = cv2.inRange(red, 145, 255) & cv2.inRange(green, 130, 255)
    mask &= cv2.inRange(cv2.subtract(green, blue), 40, 255)
    labels, boxes = _components(mask)
    parts, upper_dots, lower_dots = [], [], []
    for x, y, w, h, label in boxes:
        if 20 <= y <= 25 and 28 <= h <= 33 and 9 <= w <= 25:
            digit = _match_digit(_component_ink(labels, x, y, w, h, label), 0.18, 0.045)
            if digit is None:
                return None
            parts.append((x, digit))
        elif 2 <= w <= 6 and 2 <= h <= 6:
            if 30 <= y <= 37:
                upper_dots.append(x)
            elif 47 <= y <= 54:
                lower_dots.append(x)
            else:
                return None
        else:
            return None

    if len(upper_dots) != 2 or len(lower_dots) != 2:
        return None
    # 同一冒号的两个点可能相差数个像素，先按行配对，再与数字排序。
    for upper, lower in zip(upper_dots, lower_dots):
        if abs(upper - lower) > 3:
            return None
        parts.append((upper, ":"))
    clock = "".join(symbol for _, symbol in sorted(parts))
    if not re.fullmatch(r"[0-9]{1,3}:[0-5][0-9]:[0-5][0-9]", clock):
        return None
    # 小时每多一位，两个冒号都随之右移；防止把漏掉的小时首位当作正常读数。
    first, second = upper_dots
    expected_first = 52 + 24 * (clock.index(":") - 1)
    if abs(first - expected_first) <= 3 and abs(second - first - 56) <= 3:
        return clock
