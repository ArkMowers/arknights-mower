import time
from dataclasses import dataclass, replace

import cv2
import numpy as np

from arknights_mower.solvers.event_sign_in_recognition import (
    Card,
    Progress,
    detect_progress,
    read_cards,
    supplement_day_numbers,
)
from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import RecognizeError
from arknights_mower.utils.solver import StrategyError
from arknights_mower.utils.swipe import NOINERTIA_OFFSET

ENTRY_SCOPE = ((90, 100), (270, 347))
EXPAND_SCOPE = ((20, 265), (115, 410))
COSTUME_SCOPE = ((1500, 840), (1920, 1035))
PRESENTATION_SKIP_SCOPE = ((1680, 0), (1920, 180))
MAX_DAYS = 15


@dataclass(frozen=True)
class Page:
    progress: Progress
    cards: tuple[Card, ...]
    image: np.ndarray
    first_day: int | None = None


def sign_in_entries(result):
    """按首页活动槽位保留签到入口，同名活动仍各占一个槽位。"""
    rows = {}
    for box, text, score in result or []:
        text = "".join(text.split())
        if score < 0.9:
            continue
        points = np.asarray(box)
        x, y = (points.min(axis=0) + points.max(axis=0)) / 2
        slot = int((y + ENTRY_SCOPE[0][1] - 104) // 81)
        if 0 <= slot < 3:
            rows.setdefault(slot, []).append((text, (int(x + 90), int(y + 100))))
    entries = []
    for slot, labels in sorted(rows.items()):
        if any("登录" in text for text, _ in labels):
            continue
        for text, position in labels:
            if "签到" in text:
                entries.append((slot, text, position))
                break
    return entries


def activity_expand_position(image):
    """只识别活动列表向下展开箭头，已展开时不再点击。"""
    band = cv2.cvtColor(cropimg(image, EXPAND_SCOPE), cv2.COLOR_RGB2GRAY)
    template = loadres("event_sign_in/expand", True)
    scores = cv2.matchTemplate(band, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, position = cv2.minMaxLoc(scores)
    if score >= 0.92:
        x, y = position
        height, width = template.shape
        return (x + 20 + width // 2, y + 265 + height // 2)
    return None


class EventSignInSolver(SceneGraphSolver):
    def run(self) -> bool:
        logger.info("开始活动签到")
        self.deadline = time.monotonic() + 180
        self.claimed_days = set()
        self.attempted_days = set()
        self.activity_days = None
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
            entries = self._home_entries()
            if not entries:
                logger.info("首页未发现活动签到入口")
                return True
            completed = True
            for index, entry in enumerate(entries):
                if index:
                    fresh = self._home_entries()
                    entry = next(
                        (item for item in fresh if item[:2] == entry[:2]), None
                    )
                    if entry is None:
                        return self._incomplete("待检查的签到活动入口已变化")
                logger.info("检查第 %s 个签到活动：%s", index + 1, entry[1])
                self.claimed_days = set()
                self.attempted_days = set()
                self.activity_days = None
                self.tap(entry[2])
                page = self._wait_panel()
                if page is None:
                    completed = self._incomplete("未识别到支持的签到进度")
                else:
                    self.activity_days = page.progress.total_days
                    if not self._collect_activity(page):
                        return False
                if not self._close_panel():
                    return False
            if completed:
                logger.info("活动签到检查完成，共检查 %s 个活动", len(entries))
            return completed
        except (RecognizeError, StrategyError) as exc:
            return self._incomplete(str(exc))

    def _collect_activity(self, page):
        page = self._seek_left(page)
        if page is None:
            return self._incomplete("未确认签到奖励列表最左端")
        completed = True
        unchanged = 0
        gestures = 0
        for _ in range(MAX_DAYS * 2 + 3):
            self._check_budget()
            target = next(
                (
                    card
                    for card in page.cards
                    if card.day is not None
                    and card.day <= page.progress.unlocked_days
                    and not card.claimed
                    and card.day not in self.attempted_days
                ),
                None,
            )
            if target is not None:
                day = target.day
                logger.info("检查第 %s 日活动签到奖励", day)
                fresh = self._wait_panel()
                if fresh is None:
                    return self._incomplete("领取前未确认签到奖励页面")
                earlier = next(
                    (
                        card
                        for card in fresh.cards
                        if card.day is not None
                        and card.day <= fresh.progress.unlocked_days
                        and not card.claimed
                        and card.day not in self.attempted_days
                    ),
                    None,
                )
                if earlier is not None and earlier.day != day:
                    page = fresh
                    continue
                target = next((card for card in fresh.cards if card.day == day), None)
                if target is None:
                    return self._incomplete(f"领取前未确认第 {day} 日奖励卡片")
                page = fresh
                if target.claimed:
                    continue
                if day > page.progress.unlocked_days:
                    return self._incomplete("领取前累计登录天数已变化")
                self.attempted_days.add(day)
                self.tap(target.position, interval=0)
                claimed = self._wait_reward(day, target)
                if claimed is None:
                    completed = self._incomplete(f"第 {day} 日奖励领取结果未确认")
                    page = self._wait_panel()
                    if page is None:
                        return False
                else:
                    page = claimed
                    self.claimed_days.add(day)
                    logger.info("活动签到已领取第 %s 日奖励", day)
                if page.first_day is None:
                    page = replace(page, first_day=fresh.first_day)
                continue
            if self._unreadable_unlocked_cards(page):
                completed = self._incomplete("有奖励卡片的日数或领取状态未确认")
            covered = (
                page.first_day + len(page.cards) - 1
                if page.first_day is not None
                else 0
            )
            if covered >= page.progress.unlocked_days:
                return completed
            if gestures >= MAX_DAYS:
                return self._incomplete("签到奖励翻页次数超出上限")
            moved = self._move_page(page, -1, retry=unchanged > 0)
            if moved is None:
                return self._incomplete("未确认签到奖励列表翻页结果")
            page, changed = moved
            gestures += 1
            unchanged = 0 if changed else unchanged + 1
            if unchanged >= 3:
                return self._incomplete("列表未继续移动，仍有已解锁日数尚未检查")
        return self._incomplete("签到奖励处理次数超出上限")

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

    def swipe_noinertia(
        self, start, movement, duration=20, interval=0.2, *, retry=False, capture=False
    ):
        self._check_budget()
        super().swipe_noinertia(
            start, movement, duration, interval, retry=retry, capture=capture
        )

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
        return self._ocr_image(image)

    def _ocr_image(self, image, *, use_det=True):
        self._check_budget()
        try:
            result, _ = rapidocr.engine(
                image, use_det=use_det, use_cls=False, use_rec=True
            )
        except MowerExit:
            raise
        except Exception as exc:
            raise RecognizeError(f"OCR 识别失败：{exc}") from exc
        self._check_budget()
        return result

    @staticmethod
    def _same_positions(before, after):
        return before.keys() == after.keys() and all(
            max(abs(a - b) for a, b in zip(before[key], after[key])) <= 8
            for key in before
        )

    def _home_entries(self):
        previous = None
        attempted_expand = False
        saw_sign_in = False
        observed_slots = set()
        for _ in range(8):
            self._check_budget()
            self.recog.update()
            if not self.recog.detect_index_scene():
                raise RecognizeError("扫描活动入口时未确认首页")
            expand = activity_expand_position(self.recog.img)
            if expand is not None:
                if not attempted_expand:
                    logger.info("展开首页活动列表")
                    self.tap(expand)
                    attempted_expand = True
                self.sleep(0.3)
                continue
            result = self._ocr(ENTRY_SCOPE)
            saw_sign_in = saw_sign_in or any(
                "签到" in "".join(text.split()) for _, text, _ in result or []
            )
            entries = sign_in_entries(result)
            observed_slots.update(slot for slot, _, _ in entries)
            pending_slots = set()
            for box, text, score in result or []:
                if "签到" not in "".join(text.split()) or score >= 0.9:
                    continue
                points = np.asarray(box)
                y = (points[:, 1].min() + points[:, 1].max()) / 2
                pending_slots.add(int((y + 100 - 104) // 81))
            observed_slots.update(slot for slot in pending_slots if 0 <= slot < 3)
            if observed_slots != {slot for slot, _, _ in entries}:
                previous = None
                self.sleep(0.3)
                continue
            positions = {(slot, label): point for slot, label, point in entries}
            if positions and previous is not None:
                if self._same_positions(previous, positions):
                    return entries
            previous = positions
            self.sleep(0.3)
        if attempted_expand and expand is not None:
            raise RecognizeError("未确认首页活动列表已展开")
        if saw_sign_in:
            raise RecognizeError("未确认完整的活动签到入口")
        return []

    def _panel_states(self):
        self._check_budget()
        if self.recog.check_announcement() is None:
            return None
        image = self.recog.img
        progress = detect_progress(image)
        if progress is None or self.activity_days not in (None, progress.total_days):
            return None
        result = supplement_day_numbers(
            image, progress, self._ocr(progress.day_scope), self._ocr_image
        )
        if result is None:
            return None
        cards = read_cards(image, progress, result)
        self._check_budget()
        if not cards:
            return None
        offsets = {
            card.day - index for index, card in enumerate(cards) if card.day is not None
        }
        if len(offsets) > 1:
            return None
        first_day = next(iter(offsets), None)
        if first_day is not None and (
            first_day < 1 or first_day + len(cards) - 1 > progress.total_days
        ):
            return None
        return Page(progress, tuple(cards), image, first_day)

    @staticmethod
    def _same_page(before, after):
        return (
            before is not None
            and before.progress.total_days == after.progress.total_days
            and before.progress.unlocked_days == after.progress.unlocked_days
            and len(before.cards) == len(after.cards)
            and all(
                left.day == right.day
                and left.claimed == right.claimed
                and max(abs(a - b) for a, b in zip(left.position, right.position)) <= 8
                for left, right in zip(before.cards, after.cards)
            )
        )

    @staticmethod
    def _unreadable_unlocked_cards(page):
        return any(
            card.day is None
            and not card.claimed
            and (
                page.first_day is None
                or page.first_day + index <= page.progress.unlocked_days
            )
            for index, card in enumerate(page.cards)
        )

    def _wait_panel(self):
        previous = None
        partial = None
        for _ in range(6):
            self.recog.update()
            page = self._panel_states()
            if (
                page is not None
                and not any(card.day is not None for card in page.cards)
                and any(not card.claimed for card in page.cards)
            ):
                previous = None
                partial = None
                self.sleep(0.3)
                continue
            if page is not None and self._same_page(previous, page):
                if self._unreadable_unlocked_cards(page):
                    partial = page
                else:
                    return page
            else:
                partial = None
            previous = page
            self.sleep(0.3)
        return partial

    @staticmethod
    def _list_fingerprint(page):
        band = cv2.cvtColor(
            cropimg(page.image, page.progress.card_scope), cv2.COLOR_RGB2GRAY
        )
        return cv2.resize(band, (320, 80)).astype(np.float32)

    @staticmethod
    def _card_signature(page, card, *, whole=False):
        (left, top), (right, bottom) = card.scope
        # 避开卡片中部共用的领取印章，保留底部奖励图案。
        start_y = top if whole else top + (bottom - top) * 2 // 3
        band = cropimg(page.image, ((left, start_y), (right, bottom)))
        gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
        return cv2.resize(gray, (96, 160) if whole else (48, 64))

    def _card_match_score(self, before, anchor, after, card, *, whole=False):
        signature = self._card_signature(before, anchor, whole=whole)
        candidate = self._card_signature(after, card, whole=whole)
        # 卡片区域取整后可能错开少量像素，允许归一化图像在一像素内对齐。
        scores = cv2.matchTemplate(
            candidate, signature[1:-1, 1:-1], cv2.TM_CCOEFF_NORMED
        )
        return cv2.minMaxLoc(scores)[1]

    def _move_page(self, page, direction, *, retry=False):
        if len(page.cards) < 2:
            return None
        anchor, opposite = (
            (page.cards[-1], page.cards[0])
            if direction < 0
            else (page.cards[0], page.cards[-1])
        )
        movement = opposite.position[0] - anchor.position[0]
        logger.info("向%s翻阅签到奖励列表", "后" if direction < 0 else "前")
        self.swipe_noinertia(
            (anchor.position[0], round(page.progress.drag_y) - NOINERTIA_OFFSET),
            (movement, 0),
            interval=0.2,
            retry=retry,
        )
        after = self._wait_panel()
        if after is None:
            return None
        unchanged = (
            np.mean(
                np.abs(self._list_fingerprint(page) - self._list_fingerprint(after))
            )
            < 1.5
        )
        if unchanged:
            if not self._same_page(page, after):
                return None
            if after.first_day is None:
                after = replace(after, first_day=page.first_day)
            return after, False
        before_days = [card.day for card in page.cards if card.day is not None]
        after_days = [card.day for card in after.cards if card.day is not None]
        if before_days and after_days:
            advanced = (
                max(after_days) > max(before_days)
                if direction < 0
                else min(after_days) < min(before_days)
            )
            if not advanced:
                return None
        candidates = [
            card
            for card in after.cards
            if (card.position[0] - anchor.position[0]) * direction
            >= 20 * page.progress.scale
        ]
        if anchor.day is not None:
            matched = [card for card in candidates if card.day == anchor.day]
            if matched:
                return self._retain_page_offset(page, after, anchor, matched[0]), True
        if anchor.claimed:
            matches = []
            for card in candidates:
                if not card.claimed:
                    continue
                score = self._card_match_score(page, anchor, after, card)
                if score >= 0.85:
                    matches.append(card)
            if len(matches) == 1:
                return self._retain_page_offset(page, after, anchor, matches[0]), True
            if len(matches) > 1:
                scored = sorted(
                    (
                        (
                            self._card_match_score(
                                page, anchor, after, card, whole=True
                            ),
                            index,
                        )
                        for index, card in enumerate(matches)
                    ),
                    reverse=True,
                )
                if scored[0][0] >= 0.85 and scored[0][0] - scored[1][0] >= 0.01:
                    matched = matches[scored[0][1]]
                    return self._retain_page_offset(page, after, anchor, matched), True
        return None

    @staticmethod
    def _retain_page_offset(before, after, anchor, matched):
        if before.first_day is None:
            return after
        first_day = (
            before.first_day + before.cards.index(anchor) - after.cards.index(matched)
        )
        if (
            first_day < 1
            or first_day + len(after.cards) - 1 > after.progress.total_days
            or after.first_day not in (None, first_day)
        ):
            raise RecognizeError("翻页后卡片日数与重叠位置不一致")
        return replace(after, first_day=first_day)

    def _seek_left(self, page):
        unchanged = 0
        for _ in range(MAX_DAYS):
            self._check_budget()
            if page.first_day == 1:
                return page
            moved = self._move_page(page, 1, retry=unchanged > 0)
            if moved is None:
                return None
            page, changed = moved
            unchanged = 0 if changed else unchanged + 1
            if unchanged >= 3:
                return (
                    replace(page, first_day=1) if page.first_day in (None, 1) else None
                )
        return page if page.first_day == 1 else None

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

    def _wait_reward(self, day, target):
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
            elif dismissed and (page := self._panel_states()) is not None:
                self._check_budget()
                if time.monotonic() >= deadline:
                    break
                card = next((card for card in page.cards if card.day == day), None)
                if card is None:
                    card = next(
                        (
                            card
                            for card in page.cards
                            if card.day is None
                            and abs(card.position[0] - target.position[0])
                            <= (target.scope[1][0] - target.scope[0][0]) * 0.2
                        ),
                        None,
                    )
                if card is not None and card.claimed:
                    stable += 1
                    if stable >= 2:
                        return page
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
                logger.info("已关闭活动签到页面并返回首页")
                return True
            self.sleep(0.5)
        return self._incomplete("未确认签到页面已关闭")

    @staticmethod
    def _incomplete(reason):
        logger.warning(
            "活动签到未完成：%s", reason, extra={"archive_screenshots": True}
        )
        return False
