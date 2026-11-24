from threading import Lock, Thread, current_thread

import cv2
import numpy as np

from arknights_mower.solvers.record import (
    claim_monthly_card_reminder,
    restore_monthly_card_reminder,
)
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.datetime import get_server_time
from arknights_mower.utils.email import send_message
from arknights_mower.utils.log import logger
from arknights_mower.utils.ocr_shared import SharedOCREngine
from arknights_mower.utils.scene import Scene

_HOME_REGION = np.s_[530:850, 900:1500]
_reminder_slot = Lock()


def expiry_visible(region: np.ndarray) -> bool:
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

    ocr = rapidocr.engine
    if not candidates or ocr is None:
        return False
    if isinstance(ocr, SharedOCREngine):
        ocr = SharedOCREngine(ocr.score, directory=ocr.directory, timeout=5)
    for _, x, y, width, height in sorted(candidates, reverse=True)[:3]:
        text = region[
            max(0, y - 3) : y + height + 3, x + round(width * 0.37) : x + width + 3
        ]
        text = cv2.resize(text, None, fx=2, fy=2)
        result, _ = ocr(
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
        if recognizer.capture_started_at is None:
            return
        self._checked_home_day = today
        if config.stop_mower.is_set() or not _reminder_slot.acquire(blocking=False):
            return
        try:
            region = recognizer.img[_HOME_REGION].copy()
            Thread(
                target=self._check,
                args=(region, today, current_thread()),
                name="mower-monthly-card-reminder",
                daemon=True,
            ).start()
        except Exception:
            _reminder_slot.release()
            logger.debug("未能启动月卡到期提醒检查", exc_info=True)

    def _check(self, region, today, owner):
        def active():
            return (
                owner.is_alive()
                and not config.stop_mower.is_set()
                and today == get_server_time().date()
            )

        try:
            if not expiry_visible(region) or not active():
                return
            first_reminder, previous_day = claim_monthly_card_reminder(today)
            if not active():
                if first_reminder:
                    restore_monthly_card_reminder(today, previous_day)
                return
            self._reminded_day = today
            if first_reminder:
                try:
                    send_message(
                        "请在游戏内查看月卡剩余时间。",
                        subject="月卡即将到期",
                        level="WARNING",
                    )
                finally:
                    logger.warning("月卡即将到期，请在游戏内查看剩余时间")
        except Exception:
            logger.debug("月卡到期提醒检查失败", exc_info=True)
        finally:
            _reminder_slot.release()
