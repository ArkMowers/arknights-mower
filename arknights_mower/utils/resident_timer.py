"""识别 1080p 进驻干员卡片上的原始倒计时。"""

import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils.image import loadimg

# 上下端各可见三岗，上端第 4 岗位于列表底部的渐变遮罩内。
_TIMER_ROWS = (270, 480, 690, 460, 668, 877, 898)
_DIGIT_STARTS = (12, 29, 51, 68, 90, 107)
_MAX_PIXEL_ERROR = 32  # 以背景为 0、白色为 255 的笔画强度。


def is_resident_timer_scope(scope):
    (left, top), (right, bottom) = scope
    return left == 1650 and right == 1780 and top in _TIMER_ROWS and bottom == top + 35


@lru_cache(maxsize=1)
def _glyphs():
    path = Path(__rootdir__) / "resources/room/resident_timer_glyphs.png"
    try:
        atlas = loadimg(path, gray=True)
    except (OSError, cv2.error):
        return None
    if atlas is None or atlas.shape != (24, 175):
        return None
    # 字模保留原图的灰背景和抗锯齿边缘，与实读图换算到相同的笔画强度。
    alpha = (atlas.astype(np.float32) - 137) * (255 / (255 - 137))
    digits = alpha[:, :170].reshape(24, 10, 17).transpose(1, 0, 2)
    return digits, alpha[:, 170:]


def _digit_cells(strip):
    return np.stack([strip[:, x : x + 17] for x in _DIGIT_STARTS])


def _timer_gray(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        return None
    if image.shape == (35, 130, 3):
        gray = image[:, :, 1]
        if any(
            cv2.norm(gray, image[:, :, channel], cv2.NORM_INF) > 4 for channel in (0, 2)
        ):
            return None
        return gray
    if image.shape == (35, 130):
        return image
    return None


def resident_timer_is_blank(gray, top):
    """满心情卡的计时栏只留灰底。上端第四岗有逐行渐变的遮罩。"""
    low, high, _, _ = cv2.minMaxLoc(gray)
    # 空栏灰底为 137。JPEG 压缩后，允许至多四个像素超出常规灰度范围，偏差仍须小于等于 12。
    if 131 <= low <= high <= 143:
        return True
    if 125 <= low <= high <= 149:
        background_pixels = cv2.countNonZero(cv2.inRange(gray, 131, 143))
        if gray.size - background_pixels <= 4:
            return True
    return (
        top == 898
        and 125 <= low <= high <= 175
        and np.ptp(gray, axis=1).max() <= 16
        and int(gray[-1, 0]) - int(gray[0, 0]) >= 8
    )


def read_resident_timer(image: np.ndarray) -> str | None:
    """六个数字和两个冒号须逐像素吻合。空栏、遮盖或滚动中的残字交回 OCR。"""
    gray = _timer_gray(image)
    if gray is None:
        return None
    background = int(gray[0, 0])
    low, high, _, _ = cv2.minMaxLoc(gray)
    if background > 184 or low < background - 3 or high < 248:
        return None
    mask = cv2.compare(gray, (255 + background) // 2, cv2.CMP_GT)
    _, y, _, height = cv2.boundingRect(mask)
    if height != 22 or y < 2 or y + 24 > 35:
        return None
    glyphs = _glyphs()
    if glyphs is None:
        return None
    digits, colon = glyphs
    alpha = (gray.astype(np.float32) - background) * (255 / (255 - background))
    strip = alpha[y - 1 : y + 23]
    for start in (46, 85):
        if np.max(np.abs(strip[:, start : start + 5] - colon)) > _MAX_PIXEL_ERROR:
            return None
    errors = np.abs(_digit_cells(strip)[:, None] - digits)
    matches = np.max(errors, axis=(2, 3)) <= _MAX_PIXEL_ERROR
    if not np.all(matches.sum(axis=1) == 1):
        return None
    # 字框以外仍须是背景，额外一位数字或遮盖边缘都使本次读数无效。
    strip[:, 12:124] = 0
    if np.max(np.abs(alpha)) > 8:
        return None
    h1, h2, m1, m2, s1, s2 = matches.argmax(axis=1)
    if m1 > 5 or s1 > 5:
        return None
    return f"{h1}{h2}:{m1}{m2}:{s1}{s2}"


def _shaded_clock(gray):
    # 上端第 4 岗的固定遮罩会逐行降低文字对比度。左右边距保留了各行的背景色。
    background = np.median(gray[:, :10], axis=1).astype(np.float32)
    if background[-1] - background[0] < 8:
        return None
    contrast = gray.astype(np.float32) - background[:, None]
    peaks = contrast[:, 12:124].max(axis=1)
    rows = np.flatnonzero(peaks >= 30)
    if (
        not 20 <= len(rows) <= 24
        or rows[0] < 2
        or rows[-1] > 32
        or rows[-1] - rows[0] + 1 != len(rows)
    ):
        return None
    # 避开首尾抗锯齿边缘，用两段完整笔画估计每一行的白色亮度。
    a, b = int(rows[0]) + 4, int(rows[-1]) - 4
    upper = np.median(peaks[a - 2 : a + 3])
    lower = np.median(peaks[b - 2 : b + 3])
    gain = upper + (np.arange(35, dtype=np.float32) - a) * (lower - upper) / (b - a)
    normalized = 137 + contrast * 118 / np.maximum(gain[:, None], 30)
    return np.clip(np.rint(normalized), 0, 255).astype(np.uint8)


def resident_timer_supports_ocr(image: np.ndarray, text: str, top: int) -> bool:
    """OCR 给出合法时间时，仍须看得到完整数字和两个冒号的上下两点。"""
    if not re.fullmatch(r"[0-9]{2}:[0-5][0-9]:[0-5][0-9]", text):
        return False
    gray = _timer_gray(image)
    if gray is None:
        return False
    if top == 898 and gray.max() < 240:
        gray = _shaded_clock(gray)
        if gray is None:
            return False
    background = int(gray[0, 0])
    darkest, brightest, _, _ = cv2.minMaxLoc(gray)
    if brightest < 240 or background > 185:
        return False
    mask = gray > (255 + background) // 2
    _, y, _, height = cv2.boundingRect(mask.astype(np.uint8))
    if not 18 <= height <= 25 or y == 0 or y + height >= 35:
        return False
    for x in _DIGIT_STARTS:
        column = mask[y : y + height, x : x + 17]
        if not column[:3].any() or not column[-3:].any():
            return False
    for x in (46, 85):
        if gray[:, x : x + 5].max() < 240:
            return False
        dots = mask[:, x : x + 5].any(axis=1)
        starts = np.flatnonzero(dots & ~np.roll(dots, 1))
        ends = np.flatnonzero(dots & ~np.roll(dots, -1))
        if (
            len(starts) != 2
            or len(ends) != 2
            or not np.all((ends - starts >= 1) & (ends - starts <= 4))
            or not y + 4 <= starts[0] <= y + 11
            or not y + height - 5 <= ends[1] <= y + height - 1
        ):
            return False
    glyphs = _glyphs()
    if glyphs is None:
        return True
    if height not in (21, 22) or y + 23 > 35:
        return False
    digits, colon = glyphs
    expected = np.concatenate(
        [colon if char == ":" else digits[int(char)] for char in text], axis=1
    )
    # 卡片纵向移动时，笔画的亮度可落在相邻像素行之间。保留数字的横向位置。
    vertical = np.ones((3, 1), np.uint8)
    # JPEG 压缩会在灰底的白色笔画旁留下暗边和浅亮点。只在复核 OCR 时容许这些亮度偏差。
    pixel_error = 48 if darkest < background - 3 else _MAX_PIXEL_ERROR
    low = cv2.erode(expected, vertical) - pixel_error
    high = cv2.dilate(expected, vertical) + pixel_error
    alpha = np.maximum(gray.astype(np.float32) - background, 0) * (
        255 / (255 - background)
    )
    strip = alpha[y - 1 : y + 23, 12:124]
    bad = (strip < low) | (strip > high)
    # 每个数字或冒号至多容许四个像素破损。两个冒号的四个点已逐一检查。
    for cell in np.split(bad, (17, 34, 39, 56, 73, 78, 95), axis=1):
        if np.count_nonzero(cell) > 4:
            return False
    strip[:] = 0
    return np.max(alpha) <= pixel_error
