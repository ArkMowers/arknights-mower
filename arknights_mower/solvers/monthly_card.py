import cv2
import numpy as np

from arknights_mower.solvers.record import claim_monthly_card_reminder
from arknights_mower.utils import rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.email import send_message
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene


def expiry_visible(frame: np.ndarray) -> bool:
    region = frame[530:850, 900:1500]
    hue, saturation, value = cv2.split(cv2.cvtColor(region, cv2.COLOR_RGB2HSV))
    pink = (hue >= 155) & (saturation > 121) & (value > 85)
    mask = cv2.morphologyEx(
        pink.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8)
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for x, y, width, height, area in stats[1:]:
        if not (58 <= width <= 230 and 16 <= height <= 80 and area >= 500):
            continue
        if not 1.8 <= width / height <= 5:
            continue
        middle = slice(y + round(height * 0.24), y + round(height * 0.76))
        left = middle, slice(x + round(width * 0.07), x + round(width * 0.29))
        right = middle, slice(x + round(width * 0.44), x + round(width * 0.91))
        contrast = np.median(value[right]) - np.median(value[left])
        light_text = (saturation[right] < 125) & (value[right] > 155)
        if contrast < 35 or pink[right].mean() < 0.40 or light_text.mean() < 0.20:
            continue
        candidates.append((contrast, x, y, width, height))

    if not candidates:
        return False
    rapidocr.initialize_ocr()
    for _, x, y, width, height in sorted(candidates, reverse=True)[:3]:
        text = region[
            max(0, y - 3) : y + height + 3, x + round(width * 0.37) : x + width + 3
        ]
        text = cv2.resize(text, None, fx=2, fy=2)
        result, _ = rapidocr.engine(
            cv2.cvtColor(text, cv2.COLOR_RGB2BGR),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )
        if result and any(
            score >= 0.8 and "".join(label.split()) == "即将到期"
            for label, score in result
        ):
            return True
    return False


class MonthlyCardReminder:
    def __init__(self):
        self._checked_home_day = None
        self._reminded_day = None

    def observe(self, scene, recognizer):
        if scene != Scene.INDEX:
            self._checked_home_day = None
            return
        today = get_server_time().date()
        if today in (self._checked_home_day, self._reminded_day):
            return
        self._checked_home_day = today
        frame = recognizer.img
        try:
            if not expiry_visible(frame):
                return
            first_reminder = claim_monthly_card_reminder(today)
            self._reminded_day = today
            if first_reminder:
                logger.warning("月卡即将到期，请在游戏内查看剩余时间")
                send_message(
                    "请在游戏内查看月卡剩余时间。",
                    subject="月卡即将到期",
                    level="WARNING",
                )
        except MowerExit:
            raise
        except Exception:
            logger.debug("月卡到期提醒检查失败", exc_info=True)
