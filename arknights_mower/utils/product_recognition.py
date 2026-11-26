import cv2
import numpy as np

from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import RecognizeError


def _word_matches(gray, resource, columns, threshold, *, rows=1):
    try:
        template = loadres(resource, True)
    except (OSError, cv2.error):
        return False
    if template is None or template.shape != gray.shape:
        return False
    height, width = gray.shape
    # 相邻配方可能只差首字。每个字都要与模板吻合。
    for row in range(rows):
        y = slice(row * height // rows, (row + 1) * height // rows)
        for col in range(columns):
            x = slice(col * width // columns, (col + 1) * width // columns)
            sample, glyph = gray[y, x], template[y, x]
            if np.ptp(sample) == 0 or np.ptp(glyph) == 0:
                return False
            score = cv2.matchTemplate(sample, glyph, cv2.TM_CCOEFF_NORMED).item()
            if not np.isfinite(score) or score < threshold:
                return False
    return True


def room_product_label(label):
    if label.shape != (50, 253):
        return None
    field = label[3:49, 4:244]
    low, high, _, _ = cv2.minMaxLoc(field)
    if high - low < 60:
        return None
    mask = cv2.threshold(field, (low + high) / 2, 255, cv2.THRESH_BINARY)[1]
    x, y, width, height = cv2.boundingRect(mask)
    if not (8 <= x <= 14 and 4 <= y <= 8 and 32 <= height <= 36):
        return None
    if 69 <= width <= 73:
        product, resource, target_width, columns = "gold", "room/product_gold", 71, 2
    elif 214 <= width <= 218:
        product, resource, target_width, columns = "exp3", "room/product_exp3", 216, 6
    else:
        return None
    word = field[y : y + height, x : x + width]
    if word.shape != (34, target_width):
        word = cv2.resize(word, (target_width, 34), interpolation=cv2.INTER_AREA)
    return product if _word_matches(word, resource, columns, 0.91) else None


def manufacture_detail_product(frame):
    if getattr(frame, "shape", None) != (1080, 1920, 3):
        return None
    # 从图案中分出浅色的完整标题，排除材料名、双芯片和局部遮挡。
    red, green, blue = cv2.split(frame[359:406, 1552:1817])
    low = cv2.min(red, cv2.min(green, blue))
    high = cv2.max(red, cv2.max(green, blue))
    mask = ((low >= 145) & (high - low <= 28)).astype(np.uint8)
    x, _, width, height = cv2.boundingRect(mask)
    if not 29 <= height <= 39:
        return None
    if 91 <= x <= 98 and 69 <= width <= 77:
        word = cv2.cvtColor(frame[365:402, 1645:1721], cv2.COLOR_RGB2GRAY)
        return (
            "gold" if _word_matches(word, "room/product_detail_gold", 2, 0.83) else None
        )
    if 15 <= x <= 22 and 222 <= width <= 231:
        word = cv2.cvtColor(frame[365:402, 1570:1798], cv2.COLOR_RGB2GRAY)
        return (
            "exp3" if _word_matches(word, "room/product_detail_exp3", 6, 0.85) else None
        )
    return None


def trade_strategy_card(frame):
    if getattr(frame, "shape", None) != (1080, 1920, 3):
        return None
    red, green, blue, _ = cv2.mean(frame[940:946, 1698:1704])
    if blue - red >= 90 and green >= 75 and blue >= 120:
        product, expected, other = "lmd", "room/strategy_lmd", "room/strategy_orundum"
    elif red - blue >= 60 and red >= 75 and green < 35:
        product, expected, other = (
            "orundum",
            "room/strategy_orundum",
            "room/strategy_lmd",
        )
    elif (
        max(red, green, blue) <= 80
        and max(red, green, blue) - min(red, green, blue) <= 40
    ):
        caption = cv2.cvtColor(frame[979:1006, 1463:1700], cv2.COLOR_RGB2GRAY)
        if caption.max() >= 140 and _word_matches(
            caption, "room/strategy_locked", 9, 0.89
        ):
            return "lmd", False
        return None
    else:
        return None
    words = cv2.cvtColor(frame[912:1003, 1606:1694], cv2.COLOR_RGB2GRAY)
    if words.max() >= 170:
        if _word_matches(words, expected, 2, 0.93, rows=2):
            return product, True
        if _word_matches(words, other, 2, 0.93, rows=2):
            raise RecognizeError("贸易站订单名称与卡片底色不一致")
    return None
