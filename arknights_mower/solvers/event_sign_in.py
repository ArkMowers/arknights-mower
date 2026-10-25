import time

import cv2
import numpy as np

from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.solver import StrategyError

ENTRY_SCOPE = ((90, 100), (270, 265))
PROGRESS_SCOPE = ((670, 205), (1800, 290))
DAY_SCOPE = ((690, 370), (1790, 500))
COSTUME_SCOPE = ((1500, 840), (1920, 1035))
PRESENTATION_SKIP_SCOPE = ((1680, 0), (1920, 180))
DAY_CENTERS = (697, 875, 1051, 1228, 1404, 1581, 1757)
PROGRESS_Y = 248


def progress_states(image):
    """仅接受位置匹配的七日圆点；返回已领、可领或未解锁。"""
    if image.shape != (1080, 1920, 3):
        return None
    band = cv2.cvtColor(cropimg(image, PROGRESS_SCOPE), cv2.COLOR_RGB2GRAY)
    circles = cv2.HoughCircles(
        band,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=30,
        param1=100,
        param2=20,
        minRadius=8,
        maxRadius=21,
    )
    if circles is None or len(circles[0]) != 7:
        return None
    centers = sorted(circles[0], key=lambda circle: circle[0])
    yy, xx = np.ogrid[-6:7, -6:7]
    core = xx * xx + yy * yy <= 36
    states = []
    for expected_x, (x, y, _) in zip(DAY_CENTERS, centers):
        if abs(x + 670 - expected_x) > 5 or abs(y + 205 - PROGRESS_Y) > 5:
            return None
        pixels = image[242:255, expected_x - 6 : expected_x + 7][core]
        color = np.median(pixels, axis=0)
        if np.max(color) <= 55:
            states.append("locked")
        elif np.min(color) >= 205 and np.ptp(color) <= 35:
            states.append("claimed")
        else:
            states.append("available")
    return tuple(states)


def day_positions(result):
    """只接受数字带内的大号日数，排除奖品数量和边缘残片。"""
    positions = {}
    for box, text, score in result or []:
        text = text.strip()
        if text not in tuple("1234567") or score < 0.9:
            continue
        points = np.asarray(box)
        left, top = points.min(axis=0)
        right, bottom = points.max(axis=0)
        if bottom - top < 60 or left < 3 or right > 1097:
            continue
        day = int(text)
        if day in positions:
            return {}
        positions[day] = (int((left + right) / 2 + 690), int((top + bottom) / 2 + 370))
    ordered = sorted(positions, key=positions.get)
    if any(b != a + 1 for a, b in zip(ordered, ordered[1:])):
        return {}
    return positions


class EventSignInSolver(SceneGraphSolver):
    def run(self) -> bool:
        logger.info("开始活动签到")
        self.deadline = time.monotonic() + 180
        self.claimed_days = set()
        try:
            self._check_budget()
            try:
                rapidocr.initialize_ocr()
            except MowerExit:
                raise
            except Exception as exc:
                raise RecognizeError(f"OCR 初始化失败：{exc}") from exc
            self.back_to_index()
            self._check_budget()
            if not self.recog.detect_index_scene():
                return self._incomplete("未确认返回首页")
            entry = self._entry_position()
            if entry is None:
                logger.info("首页未发现活动签到入口")
                return True
            self.tap(entry)
            states = self._wait_panel()
            if states is None:
                return self._incomplete("未识别到支持的七日签到页面")
            for _ in range(8):
                self._check_budget()
                available = [
                    i + 1 for i, state in enumerate(states) if state == "available"
                ]
                if not available:
                    return self._close_panel()
                day = available[0]
                if day in self.claimed_days:
                    return self._incomplete("已确认领取的日数再次显示可领")
                logger.info("第 %s 日活动签到奖励可领取", day)
                position = self._day_position(day)
                if position is None:
                    if not self._scroll_to_edge(day):
                        return self._incomplete("未确认签到奖励列表边界")
                    position = self._day_position(day)
                if position is None:
                    return self._incomplete(f"未识别到第 {day} 日的奖励卡片")
                # OCR 之后再次核对状态，避免使用领取前或拖动前的观测点击。
                self.recog.update()
                states = self._panel_states()
                if states is None or states[day - 1] != "available":
                    return self._incomplete("领取前签到状态已变化")
                self.tap(position, interval=0)
                states = self._wait_reward(day)
                if states is None:
                    return self._incomplete(f"第 {day} 日奖励领取结果未确认")
                self.claimed_days.add(day)
                logger.info("活动签到已领取第 %s 日奖励", day)
            return self._incomplete("七日签到处理次数超出上限")
        except (RecognizeError, StrategyError) as exc:
            return self._incomplete(str(exc))

    def _check_budget(self):
        if config.stop_mower.is_set():
            raise MowerExit
        if time.monotonic() >= self.deadline:
            raise RecognizeError("活动签到操作超时")

    def scene(self):
        self._check_budget()
        return super().scene()

    def tap(self, poly, x_rate=0.5, y_rate=0.5, interval=1):
        self._check_budget()
        super().tap(poly, x_rate, y_rate, interval)

    def swipe(self, start, movement, duration=100, interval=1):
        self._check_budget()
        super().swipe(start, movement, duration, interval)

    def back(self, interval=1):
        self._check_budget()
        super().back(interval)

    def sleep(self, interval=1):
        self._check_budget()
        super().sleep(min(interval, max(0, self.deadline - time.monotonic())))
        self._check_budget()

    def _ocr(self, scope):
        self._check_budget()
        image = cropimg(self.recog.img, scope)
        try:
            result, _ = rapidocr.engine(
                image, use_det=True, use_cls=False, use_rec=True
            )
        except MowerExit:
            raise
        except Exception as exc:
            raise RecognizeError(f"OCR 识别失败：{exc}") from exc
        self._check_budget()
        return result

    def _entry_position(self):
        for box, text, score in self._ocr(ENTRY_SCOPE) or []:
            if score >= 0.9 and "签到" in "".join(text.split()):
                points = np.asarray(box)
                x, y = (points.min(axis=0) + points.max(axis=0)) / 2
                return (int(x + 90), int(y + 100))
        return None

    def _panel_states(self):
        self._check_budget()
        if self.recog.check_announcement() is None:
            return None
        return progress_states(self.recog.img)

    def _wait_panel(self):
        for _ in range(12):
            self.recog.update()
            if (states := self._panel_states()) is not None:
                return states
            self.sleep(0.5)
        return None

    def _day_position(self, day):
        return day_positions(self._ocr(DAY_SCOPE)).get(day)

    def _list_fingerprint(self):
        band = cv2.cvtColor(cropimg(self.recog.img, DAY_SCOPE), cv2.COLOR_RGB2GRAY)
        return cv2.resize(band, (320, 80)).astype(np.float32)

    def _scroll_to_edge(self, day):
        edge = "左端" if day <= 4 else "右端"
        logger.info("向签到奖励列表%s滑动，查找第 %s 日奖励", edge, day)
        unchanged = 0
        previous = self._list_fingerprint()
        start, movement = (
            ((800, 510), (900, 0)) if day <= 4 else ((1700, 510), (-900, 0))
        )
        for _ in range(12):
            self._check_budget()
            self.swipe(start, movement, duration=500, interval=0.5)
            if self._panel_states() is None:
                return False
            current = self._list_fingerprint()
            unchanged = (
                unchanged + 1 if np.mean(np.abs(current - previous)) < 1.5 else 0
            )
            if unchanged >= 3:
                logger.info("签到奖励列表已到%s", edge)
                return True
            previous = current
        return False

    def _reward_presentation(self):
        if self.find("recruit/agent_token") or self.find("recruit/agent_token_first"):
            return "干员", (960, 540)
        for box, text, score in self._ocr(PRESENTATION_SKIP_SCOPE) or []:
            if score >= 0.9 and "".join(text.split()).upper() in ("SKIP", "跳过"):
                points = np.asarray(box)
                x, y = (points.min(axis=0) + points.max(axis=0)) / 2
                return "时装动画", (int(x + 1680), int(y))
        for _, text, score in self._ocr(COSTUME_SCOPE) or []:
            if score >= 0.9 and "穿戴" in "".join(text.split()):
                return "时装", (450, 300)
        return None

    def _wait_reward(self, day):
        dismissed = False
        presentations = set()
        stable = 0
        deadline = min(self.deadline, time.monotonic() + 15)
        for _ in range(90):
            self._check_budget()
            if time.monotonic() >= deadline:
                break
            self.recog.update()
            material = self.find("materiel_ico")
            self._check_budget()
            if time.monotonic() >= deadline:
                break
            if material:
                if not dismissed:
                    logger.info("第 %s 日签到奖励的物资领取页面已打开", day)
                    self.tap((960, 960), interval=0)
                    dismissed = True
                stable = 0
            elif dismissed and (states := self._panel_states()) is not None:
                self._check_budget()
                if time.monotonic() >= deadline:
                    break
                if states[day - 1] == "claimed":
                    stable += 1
                    if stable >= 2:
                        return states
                else:
                    stable = 0
            elif not dismissed and self._panel_states() is None:
                presentation = self._reward_presentation()
                self._check_budget()
                if time.monotonic() >= deadline:
                    break
                if presentation is not None and presentation[0] not in presentations:
                    name, position = presentation
                    if name == "时装动画":
                        logger.info("跳过签到奖励的时装展示动画")
                    else:
                        logger.info("关闭签到奖励的%s展示页面", name)
                    self.tap(position, interval=0)
                    presentations.add(name)
                    deadline = min(self.deadline, time.monotonic() + 15)
                stable = 0
            else:
                stable = 0
            self.sleep(0.5)
        return None

    def _close_panel(self):
        if (position := self.recog.check_announcement()) is None:
            return self._incomplete("未识别到签到页面关闭按钮")
        self.tap(position)
        for _ in range(8):
            self._check_budget()
            self.recog.update()
            at_home = self.recog.detect_index_scene()
            self._check_budget()
            if at_home:
                logger.info("活动签到完成，已返回首页")
                return True
            self.sleep(0.5)
        return self._incomplete("未确认签到页面已关闭")

    @staticmethod
    def _incomplete(reason):
        logger.warning(
            "活动签到未完成：%s", reason, extra={"archive_screenshots": True}
        )
        return False
