"""Inspect assistant and activity-room trust during the daily-task window."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic

import cv2
import numpy as np

from arknights_mower.data import agent_list
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import RECOVERABLE_DEVICE_ERRORS
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


class TrustReadingError(RuntimeError):
    """An unverified page or trust reading cannot authorize an assignment."""


@dataclass(frozen=True)
class TrustCard:
    trust: int
    scope: tuple
    selected: bool
    assistant: bool
    activity: bool

    def available(self, kind):
        return not self.selected and not getattr(self, kind)


def replacement_limit(prefer, threshold):
    return threshold if prefer else 200


def should_replace(current, candidate, prefer, threshold):
    return candidate < 200 and (
        current is None
        or current >= 200
        or (prefer and current >= threshold and candidate < threshold)
    )


def rank_candidates(cards, kind, prefer=False, threshold=100):
    return sorted(
        (card for card in cards if card.available(kind) and card.trust < 200),
        key=lambda card: (
            prefer and card.trust >= threshold,
            card.trust,
            card.scope[0][0],
            card.scope[0][1],
        ),
    )


def parse_trust(text):
    match = re.search(r"(?<!\d)(\d{1,3})\s*[%％]", text)
    if match and 0 <= int(match[1]) <= 200:
        return int(match[1])
    return None


def empty_assignment(image):
    """Require the white admission cross on a neutral empty card."""
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    if hsv[:, :, 1].mean() > 25:
        return False
    white = cv2.inRange(hsv, (0, 0, 225), (180, 40, 255))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (35 <= w <= 150 and 0.85 < w / h < 1.15):
            continue
        cross = white[y : y + h, x : x + w] > 0
        if (
            cross[:, w // 2].mean() > 0.95
            and cross[h // 2, :].mean() > 0.95
            and 0.15 < cross.mean() < 0.5
        ):
            return True
    return False


def trust_order_ascending(image):
    mask = cv2.inRange(
        cv2.cvtColor(image, cv2.COLOR_RGB2HSV), (90, 100, 100), (110, 255, 255)
    )
    spans = [np.ptp(np.flatnonzero(row)) if row.any() else 0 for row in mask]
    upper, lower = max(spans[:7], default=0), max(spans[-7:], default=0)
    return None if upper == lower else upper < lower


def skill_priority_active(image):
    mask = cv2.inRange(
        cv2.cvtColor(image, cv2.COLOR_RGB2HSV), (20, 100, 100), (40, 255, 255)
    )
    return np.count_nonzero(mask) > 20


def run_trust_rotation(device, recog, next_task_time):
    """Persist only a completed inspection; a failed inspection remains due."""
    conf = config.conf
    if not conf.trust_rotation_enable:
        return False
    now = datetime.now()
    state_path = get_path("@app/tmp/trust_rotation.json")
    try:
        last = datetime.fromisoformat(
            json.loads(state_path.read_text())["completed_at"]
        )
        if now < last + timedelta(hours=conf.trust_rotation_interval):
            return False
    except (OSError, ValueError, KeyError, TypeError):
        pass
    seconds = min(480, (next_task_time - now).total_seconds() - 60)
    if seconds <= 0:
        return False
    solver = TrustRotationSolver(device, recog)
    try:
        solver.run(seconds=seconds)
        config.atomic_write(
            state_path,
            lambda stream: json.dump(
                {"completed_at": datetime.now().isoformat()}, stream
            ),
        )
        return True
    except (MowerExit, *RECOVERABLE_DEVICE_ERRORS):
        raise
    except Exception:
        solver.discard_pending_selection()
        logger.exception("自动切换信赖未完成，下次日常窗口重试")
        return False


class TrustRotationSolver(SceneGraphSolver):
    ASSISTANT_POINTS = ((635, 350), (275, 800), (515, 800), (755, 800), (995, 800))
    ASSISTANT_TRUST = (
        ((590, 495), (720, 540)),
        ((230, 940), (365, 990)),
        ((470, 940), (605, 990)),
        ((710, 940), (845, 990)),
        ((950, 940), (1085, 990)),
    )

    def _check_budget(self):
        if config.stop_mower.is_set():
            raise MowerExit
        if monotonic() >= self.deadline:
            raise TrustReadingError("信赖检查到达本轮时间预算")

    def scene(self):
        self._check_budget()
        return super().scene()

    def tap(self, *args, **kwargs):
        self._check_budget()
        return super().tap(*args, **kwargs)

    def swipe(self, *args, **kwargs):
        self._check_budget()
        return super().swipe(*args, **kwargs)

    def _ocr(self, scope):
        self._check_budget()
        result, _ = rapidocr.engine(cropimg(self.recog.img, scope))
        self._check_budget()
        return [(box, text, score) for box, text, score in result or [] if score >= 0.8]

    def _text(self, scope):
        return " ".join(text for _, text, _ in self._ocr(scope))

    def _require(self, text, scope):
        if text not in self._text(scope):
            raise TrustReadingError(f"未确认{text}页面，停止信赖选人")

    def _trust(self, scope):
        value = parse_trust(self._text(scope))
        if value is None:
            raise TrustReadingError("无法确认当前干员信赖，不更换")
        return value

    def _assignment_trust(self, scope, card_scope):
        value = parse_trust(self._text(scope))
        if value is not None:
            return value
        if empty_assignment(cropimg(self.recog.img, card_scope)):
            return None
        raise TrustReadingError("驻员信赖和空位均未确认")

    def _assistant_trust(self, index):
        (x, y), (right, bottom) = scope = self.ASSISTANT_TRUST[index]
        return self._assignment_trust(scope, ((x - 50, y - 320), (x + 140, bottom + 5)))

    def run(self, *, seconds=480):
        self.deadline = monotonic() + seconds
        self.prefer = config.conf.trust_rotation_prefer_low
        self.threshold = config.conf.trust_rotation_threshold
        rapidocr.initialize_ocr()
        self.discard_pending_selection()
        self.back_to_infrastructure()
        self._enter_control_center()
        self._require("基建副手", ((15, 530), (210, 720)))
        self.tap((95, 625))
        self._require("罗德岛基建副手", ((750, 170), (1220, 300)))
        self.assistant_names = {}
        for index, point in enumerate(self.ASSISTANT_POINTS):
            if self._assistant_trust(index) is None:
                continue
            self.tap(point)
            self._require("确认", ((1350, 970), (1770, 1075)))
            self.assistant_names[index] = self._name(((20, 155), (350, 215)))
            self._leave_selection()
        if len(set(self.assistant_names.values())) != len(self.assistant_names):
            raise TrustReadingError("无法确认副手名单唯一性")
        for index, point in enumerate(self.ASSISTANT_POINTS):
            self._check_budget()
            trust = self._assistant_trust(index)
            limit = replacement_limit(self.prefer, self.threshold)
            if trust is not None and trust < limit:
                logger.info("副手%s信赖%s%%，保留至%s%%", index + 1, trust, limit)
                continue
            self.tap(point)
            outcome = self._replace("assistant", trust, index=index)
            if outcome == "full":
                self._leave_selection()
                break
            self._require("罗德岛基建副手", ((750, 170), (1220, 300)))
        self._return_from_assistants()
        self._activity_rooms()

    def discard_pending_selection(self):
        if config.stop_mower.is_set():
            return
        deadline = self.deadline
        self.deadline = monotonic() + 10
        try:
            if "确认" in self._text(((1350, 970), (1770, 1075))):
                self.tap((65, 55))
            if "当前使用者信息" in self._text(((1260, 15), (1860, 110))):
                self.tap((65, 55))
            elif "罗德岛基建副手" in self._text(((750, 170), (1220, 300))):
                self.tap((65, 55))
                self.tap((65, 55))
        except (MowerExit, *RECOVERABLE_DEVICE_ERRORS):
            raise
        except Exception:
            logger.warning("信赖检查页面未确认，停止退出输入")
        finally:
            self.deadline = deadline

    def _enter_control_center(self):
        self._require("进驻总览", ((25, 120), (360, 245)))
        for _ in range(5):
            labels = self._ocr(((360, 100), (1720, 370)))
            for box, text, _ in labels:
                if "控制中枢" in text:
                    x = round(sum(p[0] for p in box) / 4) + 360
                    y = round(sum(p[1] for p in box) / 4) + 100
                    self.tap((x, y + 40))
                    self._require("控制中枢", ((630, 15), (1010, 100)))
                    return
            self.swipe((450, 520), (1150, 0), duration=500)
        raise TrustReadingError("平移后仍无法确认控制中枢位置")

    def _leave_selection(self):
        self._require("确认", ((1350, 970), (1770, 1075)))
        self.tap((65, 55))

    def _return_from_assistants(self):
        self._require("罗德岛基建副手", ((750, 170), (1220, 300)))
        self.tap((65, 55))
        self.tap((65, 55))
        self._require("进驻总览", ((25, 120), (360, 245)))

    def _prepare_selection(self):
        self._require("确认", ((1350, 970), (1770, 1075)))
        if skill_priority_active(self.recog.img[20:90, 1100:1170]):
            self.tap((1140, 55))
        if skill_priority_active(self.recog.img[20:90, 1100:1170]):
            raise TrustReadingError("基建优先排序未取消")
        filters = ((1795, 90), (1919, 185))
        if "ALL" not in self._text(filters):
            self.tap((1850, 55))
        self._require("ALL", filters)
        self.tap((1850, 135))  # ALL also resets any profession filter.
        self._require("信赖值", ((1500, 20), (1640, 100)))
        for _ in range(3):
            if trust_order_ascending(self.recog.img[62:81, 1555:1593]):
                break
            self.tap((1574, 50))
        else:
            raise TrustReadingError("无法确认信赖升序排列")
        # An already-active filter can retain its scroll position.
        for _ in range(40):
            before = cv2.resize(self.recog.img[120:930, 790:1780], (80, 64))
            self.swipe((650, 520), (1050, 0), duration=400)
            after = cv2.resize(self.recog.img[120:930, 790:1780], (80, 64))
            if np.abs(before.astype(float) - after.astype(float)).mean() < 1:
                break
        else:
            raise TrustReadingError("无法确认信赖名单起点")

    def _cards(self, *, badges=True):
        cards = []
        badge_rows = {
            top: self._ocr(((560, top + 170), (1790, top + 310))) if badges else []
            for top in (120, 540)
        }
        for y in (450, 870):
            for box, text, _ in self._ocr(((560, y), (1790, y + 65))):
                trust = parse_trust(text)
                if trust is None:
                    continue
                left = round(min(p[0] for p in box)) + 560 - 60
                top = 120 if y == 450 else 540
                right, bottom = left + 184, top + 394
                if left < 565 or right > 1795:
                    continue  # A clipped card is never a click target.
                scope = ((left, top), (right, bottom))
                badge = " ".join(
                    text
                    for box, text, _ in badge_rows[top]
                    if left <= min(p[0] for p in box) + 560 < right
                )
                frame = self.recog.img[top - 8 : bottom + 10, left - 8 : right + 12]
                blue = (
                    cv2.inRange(
                        cv2.cvtColor(frame, cv2.COLOR_RGB2HSV),
                        (90, 140, 150),
                        (110, 255, 255),
                    )
                    > 0
                )
                selected = blue[:, :8].mean() > 0.45
                assistant = bool(re.search(r"ASSISTANT|中枢|B[1-4](?!\d)", badge, re.I))
                activity = bool(re.search(r"ACTIVITY|B\d{3}|活动", badge, re.I))
                cards.append(TrustCard(trust, scope, selected, assistant, activity))
        if not cards:
            raise TrustReadingError("干员信赖名单为空或无法识别")
        return cards

    def _find_candidate(self, kind):
        previous = None
        for _ in range(40):
            self._check_budget()
            cards = self._cards(badges=kind == "activity")
            unassigned = [card for card in cards if card.available(kind)]
            # Pinned occupied cards do not establish the lowest available trust.
            if unassigned:
                if min(card.trust for card in unassigned) == 200:
                    logger.info("%s同类名单以外的候选均满信赖，跳过该类剩余位置", kind)
                    return "full"
                candidates = rank_candidates(cards, kind, self.prefer, self.threshold)
                for candidate in candidates:
                    self.tap(candidate.scope)
                    self._require("确认", ((1350, 970), (1770, 1075)))
                    try:
                        name = self._name(((20, 155), (350, 215)))
                    except TrustReadingError:
                        logger.warning("候选姓名无法确认，跳过且不提交该候选")
                        continue
                    if kind == "assistant" and name in self.assistant_names.values():
                        continue
                    return candidate, name
            signature = cv2.resize(self.recog.img[120:930, 790:1780], (80, 64))
            if (
                previous is not None
                and np.abs(signature.astype(float) - previous.astype(float)).mean() < 1
            ):
                raise TrustReadingError("名单到底仍无法确认可用候选")
            previous = signature
            self.swipe((1680, 520), (-870, 0), duration=400)
        raise TrustReadingError("信赖名单超过本轮扫描上限")

    def _name(self, scope):
        name = re.sub(r"\s+", "", self._text(scope))
        if name not in agent_list:
            raise TrustReadingError("无法确认所选干员姓名")
        return name

    def _replace(self, kind, trust, *, index=0):
        self._prepare_selection()
        current = [item for item in self._cards(badges=False) if item.selected]
        if len(current) != (0 if trust is None else 1) or (
            current and current[0].trust != trust
        ):
            raise TrustReadingError("当前选中状态与设施读数不一致")
        candidate = self._find_candidate(kind)
        if candidate == "full":
            return candidate
        card, name = candidate
        if not should_replace(trust, card.trust, self.prefer, self.threshold):
            self._leave_selection()
            return "retained"
        # Readback authorizes the confirmation, never the stale clicked frame.
        self._require("确认", ((1350, 970), (1770, 1075)))
        selected = [item for item in self._cards(badges=False) if item.selected]
        if (
            len(selected) != 1
            or selected[0].trust != card.trust
            or abs(selected[0].scope[0][0] - card.scope[0][0]) > 8
            or selected[0].scope[0][1] != card.scope[0][1]
        ):
            raise TrustReadingError("无法确认唯一选中干员，保留原安排")
        if self._name(((20, 155), (350, 215))) != name:
            raise TrustReadingError("确认前所选干员姓名变化")
        logger.info("信赖切换：%s → %s（%s%%）", kind, name, card.trust)
        self.tap((1575, 1025))
        if kind == "activity":
            self._require("当前使用者信息", ((1260, 15), (1860, 110)))
            actual = self._name(((1420, 640), (1750, 710)))
            actual_trust = self._trust(((1480, 705), (1660, 775)))
        else:
            self._require("罗德岛基建副手", ((750, 170), (1220, 300)))
            actual_trust = self._trust(self.ASSISTANT_TRUST[index])
            self.tap(self.ASSISTANT_POINTS[index])
            self._require("确认", ((1350, 970), (1770, 1075)))
            actual = self._name(((20, 155), (350, 215)))
            self._leave_selection()
        if actual != name or actual_trust != card.trust:
            raise TrustReadingError("信赖更换后的实际干员未确认")
        if kind == "assistant":
            self.assistant_names[index] = name
        return "replaced"

    def _activity_rooms(self):
        # Pan the map instead of entering or changing the four functional rooms.
        for _ in range(2):
            self.swipe((1700, 520), (-1400, 0), duration=500)
        self._require("进驻总览", ((25, 120), (360, 245)))
        labels = self._ocr(((360, 360), (1900, 1020)))
        rooms = []
        for box, text, _ in labels:
            if "活动室" in text:
                x = round(min(p[0] for p in box)) + 360
                y = round(min(p[1] for p in box)) + 360
                rooms.append((x + 100, y + 55))
        if len(rooms) > 8:
            raise TrustReadingError("活动室识别超过八个位置")
        for point in sorted(rooms, key=lambda p: (p[1], p[0])):
            self._check_budget()
            self.tap(point)
            self._require("活动室", ((620, 15), (1020, 100)))
            panel = ((1260, 15), (1860, 110))
            if "当前使用者信息" not in self._text(panel):
                self.tap((95, 410))  # At most one user-tab click per room.
            self._require("当前使用者信息", panel)
            trust = self._assignment_trust(
                ((1480, 705), (1660, 775)), ((1430, 245), (1705, 775))
            )
            if trust is None or trust >= replacement_limit(self.prefer, self.threshold):
                self.tap((1560, 460))
                if self._replace("activity", trust) == "full":
                    self._leave_selection()
                    self.tap((65, 55))
                    return
                self._require("当前使用者信息", panel)
            self.tap((65, 55))
            self._require("进驻总览", ((25, 120), (360, 245)))
