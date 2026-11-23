from functools import lru_cache
from pathlib import Path
from time import monotonic

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from arknights_mower.utils import config, rapidocr
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.log import logger
from arknights_mower.utils.swipe import swipe_duration_ms

PROFESSION_LABELS = (
    "ALL",
    "PIONEER",
    "WARRIOR",
    "TANK",
    "SNIPER",
    "CASTER",
    "MEDIC",
    "SUPPORT",
    "SPECIAL",
)
_MENU_CHANGE_FRACTION = 0.015


def _blue(img):
    return cv2.inRange(img, (0, 115, 172), (100, 245, 255))


def branch_filter_state(img, profession):
    """读取亮起职业旁的箭头方向和具体分支标记。未能定位时返回未知。"""
    if (
        profession not in PROFESSION_LABELS[1:]
        or not isinstance(img, np.ndarray)
        or img.shape != (1080, 1920, 3)
    ):
        return None
    y = 220 + 113 * (PROFESSION_LABELS.index(profession) - 1)
    if not _blue(img[y - 2 : y + 3, 1915:1919]).all():
        return None
    mask = _blue(img[y - 18 : y + 19, 1803:1825])
    _, components, stats, _ = cv2.connectedComponentsWithStats(mask)
    for label, (x, top, width, height, area) in enumerate(stats[1:], 1):
        if not (12 <= width <= 17 and 24 <= height <= 30 and 65 <= area <= 140):
            continue
        arrow = components[top : top + height, x : x + width] == label
        middle = np.flatnonzero(arrow[height // 2])
        ends = np.flatnonzero(arrow[2] | arrow[-3])
        if not middle.size or not ends.size:
            continue
        direction = middle.mean() - ends.mean()
        if direction > 5:
            all_highlighted = np.count_nonzero(_blue(img[39:77, 1650:1720])) > 80
            return True, not all_highlighted
        if direction < -5:
            dot = mask[12:25, 15:21]
            return False, np.count_nonzero(dot) > 12
    return None


def _wait(solver, check, *, timeout=None):
    interval, attempts = solver.selection_transition_timing()
    if timeout is not None:
        next_sample = monotonic()
        deadline = next_sample + timeout
        attempts = max(3, attempts)
    for attempt in range(attempts):
        if config.stop_mower.is_set():
            raise MowerExit
        if attempt:
            delay = interval
            if timeout is not None:
                now = monotonic()
                # 手势后的第一帧可能仍是原菜单，后续两帧分别核对移动和稳定。
                if attempt >= 3 and now >= deadline:
                    break
                delay = max(0, min(next_sample, deadline) - now)
            solver.sleep(delay)
        if timeout is not None:
            next_sample = monotonic() + interval
        solver.require_agent_selection_page()
        img = solver.recog.img
        if timeout is not None and config.stop_mower.is_set():
            raise MowerExit
        if check(img):
            return True
    return False


def set_branch_menu_open(solver, profession, opened):
    solver.require_agent_selection_page()
    state = branch_filter_state(solver.recog.img, profession)
    if state is None:
        return False
    if state[0] == opened:
        return True
    y = 220 + 113 * (PROFESSION_LABELS.index(profession) - 1)
    solver.tap((1813, y), interval=0.1)
    return _wait(
        solver,
        lambda img: (s := branch_filter_state(img, profession)) and s[0] == opened,
    )


def _ocr(region, *, detect):
    if rapidocr.engine is None:
        return ()
    try:
        rows, _ = rapidocr.engine(region, use_det=detect, use_cls=False, use_rec=True)
        return rows or ()
    except MowerExit:
        raise
    except Exception as exc:
        logger.debug(f"未能读取分支菜单文字：{exc}")
        return ()


@lru_cache(maxsize=1)
def _branch_font():
    path = (
        Path(__file__).resolve().parents[1] / "fonts/SourceHanSansCN-Medium-mastery.ttf"
    )
    try:
        return ImageFont.truetype(str(path), 24)
    except OSError:
        return None


@lru_cache(maxsize=128)
def _branch_template(name):
    if (
        not isinstance(name, str)
        or not 2 <= len(name) <= 5
        or not all("\u3400" <= char <= "\u9fff" for char in name)
    ):
        return None
    font = _branch_font()
    if font is None:
        return None
    missing = bytes(font.getmask(chr(0x10FFEF)))
    if any(bytes(font.getmask(char)) == missing for char in name):
        return None
    image = Image.new("L", (len(name) * 24 + 12, 36))
    ImageDraw.Draw(image).text((4, 4), name, font=font, fill=255, anchor="lt")
    ink = np.asarray(image)
    x, y, width, height = cv2.boundingRect(np.uint8(ink > 48))
    return ink[y - 2 : y + height + 2, x - 2 : x + width + 2].copy()


_STROKE_KERNEL = np.ones((5, 5), np.uint8)


def _match_strokes(foreground, template, minimum):
    height, width = template.shape
    if foreground.shape[0] < height or foreground.shape[1] < width:
        return None
    scores = cv2.matchTemplate(foreground, template, cv2.TM_CCOEFF_NORMED)
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    if (
        best < minimum
        or x < 2
        or x + width > foreground.shape[1] - 2
        or y < 2
        or y + height > foreground.shape[0] - 2
    ):
        return None
    scores[max(0, y - 38) : y + 39] = -1
    if best - cv2.minMaxLoc(scores)[1] < 0.08:
        return None
    # 两侧若仍有笔画，“铁卫”可能只是“哨戒铁卫”的后半段。
    band = foreground[y : y + height]
    threshold = max(18, np.percentile(band[:, x : x + width], 95) * 0.44)
    for edge in (band[:, max(0, x - 20) : x], band[:, x + width : x + width + 20]):
        if np.count_nonzero(edge > threshold) > 8:
            return None
    return y + height // 2


def _template_row(gray, name, observed=None):
    generated = _branch_template(name)
    if generated is None and observed is None:
        return None
    foreground = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, _STROKE_KERNEL)
    if (
        observed is not None
        and (y := _match_strokes(foreground, observed, 0.94)) is not None
    ):
        return y
    if generated is not None:
        return _match_strokes(foreground, generated, 0.82)
    return None


def _visible_rows(img):
    # 只检测文字列，分支图标和底层干员姓名均不参与识别。
    region = img[100:1060, 1655:1792]
    positions = {}
    for box, text, score in _ocr(region, detect=True):
        xs, ys = zip(*box)
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        if (
            score >= 0.92
            and not text.isdigit()
            and 16 <= height <= 45
            and 19 * len(text) <= width <= 30 * len(text) + 12
            and 2 < min(xs)
            and max(xs) < region.shape[1] - 2
            and 2 < min(ys)
            and max(ys) < region.shape[0] - 2
        ):
            y = round((min(ys) + max(ys)) / 2) + 100
            positions[text] = None if text in positions else y
    return positions


def _branch_rows(img, name, observed=None):
    region = cv2.cvtColor(img[100:1060, 1655:1792], cv2.COLOR_RGB2GRAY)
    y = _template_row(region, name, observed)
    return {name: y + 100} if y is not None else _visible_rows(img)


def _can_scroll_down(img):
    # 展开动画中三角随菜单横向移动，其高度和朝向保持不变。
    mask = cv2.inRange(img[1032:1055, 1668:1792], (140, 140, 140), (255, 255, 255))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    for label, (x, y, width, height, area) in enumerate(stats[1:], 1):
        if not (15 <= width <= 21 and 12 <= height <= 17 and 95 <= area <= 185):
            continue
        triangle = labels[y : y + height, x : x + width] == label
        if (
            np.count_nonzero(triangle[:3]) >= 37
            and 1 <= np.count_nonzero(triangle[-3:]) <= 15
            and triangle[:, width // 2].sum() >= height - 2
        ):
            return True
    return False


def _menu_text_mask(img):
    return cv2.cvtColor(img[105:1055, 1655:1792], cv2.COLOR_RGB2GRAY) > 80


def _scroll_menu(solver, profession, down):
    before = _menu_text_mask(solver.recog.img)
    previous = None

    def moved_and_settled(img):
        nonlocal previous
        if (state := branch_filter_state(img, profession)) is None or not state[0]:
            previous = None
            return False
        current = _menu_text_mask(img)
        if np.mean(current != before) <= _MENU_CHANGE_FRACTION:
            previous = None
            return False
        stable = previous is not None and np.mean(current != previous) < 0.004
        previous = current
        return stable

    start, distance = ((1630, 954), -699) if down else ((1630, 255), 699)
    solver.swipe(
        start, (0, distance), duration=swipe_duration_ms(distance), interval=0.1
    )
    return _wait(
        solver, moved_and_settled, timeout=solver.performance_profile.transition_timeout
    )


def _find_branch_row(solver, profession, branch_name):
    tried = set()
    down = True
    observed = getattr(solver, "_branch_text_samples", {}).get(branch_name)
    while True:
        img = solver.recog.img
        rows = _branch_rows(img, branch_name, observed)
        if not rows and not tried:
            interval, attempts = solver.selection_transition_timing()
            for _ in range(min(2, attempts - 1)):
                solver.sleep(interval)
                solver.require_agent_selection_page()
                img = solver.recog.img
                state = branch_filter_state(img, profession)
                if state is None or not state[0]:
                    return None
                if rows := _branch_rows(img, branch_name, observed):
                    break
        if not rows:
            return None
        if (y := rows.get(branch_name)) is not None:
            return y
        if len(tried) >= 5:
            return None
        # 打开菜单时下箭头可能尚未出现。每次按当前可见行和箭头重新选择方向。
        page = frozenset(rows)
        for direction in (down, not down):
            if (page, direction) not in tried and (
                not direction or _can_scroll_down(img)
            ):
                down = direction
                break
        else:
            return None
        tried.add((page, down))
        if not _scroll_menu(solver, profession, down):
            latest = solver.recog.img
            state = branch_filter_state(latest, profession)
            if state is None or not state[0]:
                return None
            if (
                np.mean(_menu_text_mask(img) != _menu_text_mask(latest))
                > _MENU_CHANGE_FRACTION
            ):
                # 文字已经移动却未读到连续稳定画面，交回职业筛选重新定位。
                return None
            down = not down


def _branch_label_ink(region):
    mask = cv2.inRange(region, (0, 105, 165), (99, 249, 255))
    if np.count_nonzero(mask) > 60:
        return mask
    # 训练位的部分选中行使用较暗的蓝字，未选行仍为灰字。
    return cv2.inRange(region, (0, 85, 125), (99, 249, 255))


def _select_menu_row(solver, profession, branch_name):
    y = _find_branch_row(solver, profession, branch_name)
    if y is None:
        return False

    last_text = None

    def selected(img):
        nonlocal last_text
        if branch_filter_state(img, profession) != (True, True):
            return False
        # 选择后菜单可能重新定位。从整列蓝字找当前选中行，再复核完整分支名称。
        mask = _branch_label_ink(img[100:1060, 1655:1792])
        ink = np.flatnonzero(np.count_nonzero(mask, axis=1) >= 2)
        if not ink.size or not 16 <= ink[-1] - ink[0] + 1 <= 45:
            return False
        band = slice(max(0, ink[0] - 8), ink[-1] + 9)
        text = mask[band]
        if np.count_nonzero(text) <= 60 or np.array_equal(last_text, text):
            return False
        region = img[100:1060, 1655:1792][band]
        # 保留蓝字的灰度笔画，训练位和普通页采用不同亮度的蓝色。
        blue = np.where(
            cv2.subtract(region[:, :, 2], region[:, :, 0]) > 30,
            cv2.cvtColor(region, cv2.COLOR_RGB2GRAY),
            0,
        )
        samples = getattr(solver, "_branch_text_samples", {})
        if _template_row(blue, branch_name, samples.get(branch_name)) is None:
            result = _ocr(cv2.cvtColor(text, cv2.COLOR_GRAY2RGB), detect=False)
            if not result or result[0][1] < 0.92:
                return False
            if result[0][0] != branch_name:
                last_text = text
                return False
            if result[0][1] < 0.98:
                return True
        if branch_name not in samples:
            # 仅保存已核对的完整蓝色字形，当前设备下次可以识别随程序字体缺少的字。
            x, top, width, height = cv2.boundingRect(text)
            if (
                2 <= x
                and x + width <= text.shape[1] - 2
                and 2 <= top
                and top + height <= text.shape[0] - 2
                and 18 * len(branch_name) <= width <= 27 * len(branch_name)
                and 16 <= height <= 32
            ):
                strokes = cv2.morphologyEx(blue, cv2.MORPH_TOPHAT, _STROKE_KERNEL)
                if len(samples) >= 128:
                    samples.pop(next(iter(samples)))
                samples[branch_name] = strokes[
                    top - 2 : top + height + 2, x - 2 : x + width + 2
                ].copy()
                solver._branch_text_samples = samples
        return True

    img = solver.recog.img
    if (
        branch_filter_state(img, profession) == (True, True)
        and np.count_nonzero(_branch_label_ink(img[y - 14 : y + 15, 1655:1792])) > 60
    ):
        return _wait(solver, selected)
    solver.tap((1720, y), interval=0.1)
    return _wait(solver, selected)


def select_visible_branch(solver, profession, branch_name):
    """在当前职业内选择分支。收起菜单后返回结果，供调用方恢复职业筛选。"""
    from arknights_mower.solvers.base_mixin import AgentSelectionNotReady

    if (
        not branch_name
        or branch_name == "全部"
        or branch_filter_state(solver.recog.img, profession) is None
    ):
        return False
    if not set_branch_menu_open(solver, profession, True):
        if (
            state := branch_filter_state(solver.recog.img, profession)
        ) is not None and not state[0]:
            return False
        raise AgentSelectionNotReady("未能确认分支菜单状态，返回房间重试")
    selected = _select_menu_row(solver, profession, branch_name)
    if not set_branch_menu_open(solver, profession, False):
        raise AgentSelectionNotReady("分支菜单尚未收起，返回房间重试")
    return selected and branch_filter_state(solver.recog.img, profession) == (
        False,
        True,
    )
