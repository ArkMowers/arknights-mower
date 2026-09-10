"""加工站家具分解：按资源保留完整一套，不安排干员。"""

import re
from time import monotonic

import cv2
import numpy as np

from arknights_mower.utils import rapidocr
from arknights_mower.utils.furniture_data import (
    load_furniture_keep_counts,
    normalize_name,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.workshop_ui import (
    CONFIRM_OPERATOR,
    FORMULA_TABS,
    OPEN_FORMULA,
    OPEN_WORKSHOP,
    scale_point,
)

NAME_SCOPE = ((0.36, 0.265), (0.59, 0.31))
BATCH_SCOPE = ((0.78, 0.475), (0.95, 0.568))
CARDS_SCOPE = ((0.2, 0.1), (0.98, 1))
KEEP_SWITCH_SCOPE = ((0.75, 0.68), (0.99, 0.83))
LIST_SCOPE = ((0.21, 0.13), (0.97, 0.97))
MAX_BUTTON = (0.96, 0.42)
MINUS_BUTTON = (0.84, 0.68)
SUBMIT_BUTTON = (0.88, 0.9)
MIN_TEXT_CONFIDENCE = 0.9
LIST_CHANGE_THRESHOLD = 1.5  # 缩小后的灰度差，仍使用 0..255 尺度。
CARD_ROW_TOLERANCE = 0.04  # 容纳同排 OCR 框的几像素偏移，远小于约 0.25 的行距。


def crop_relative(img, scope):
    (left, top), (right, bottom) = scope
    height, width = img.shape[:2]
    return img[
        round(top * height) : round(bottom * height),
        round(left * width) : round(right * width),
    ]


def read_text(img, *, min_confidence=0):
    result, _ = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)
    if min_confidence and (
        not result or any(score < min_confidence for _, score in result)
    ):
        raise ValueError("家具文字识别置信度不足")
    return normalize_name("".join(text for text, _ in result or []))


def read_confident_text(img):
    return read_text(img, min_confidence=MIN_TEXT_CONFIDENCE)


def glyph_image(mask, padding=6, *, reject_clipped=False):
    x, y, width, height = cv2.boundingRect(mask)
    if (
        not width
        or not height
        or (reject_clipped and (x == 0 or x + width == mask.shape[1]))
    ):
        raise ValueError("家具文字为空或被裁切")
    return cv2.copyMakeBorder(
        mask[y : y + height, x : x + width],
        padding,
        padding,
        padding,
        padding,
        cv2.BORDER_CONSTANT,
        value=0,
    )


def furniture_name(img):
    # 名称长短差异很大，先定位文字，避免「桌子」等短名称被大块留白干扰。
    name_img = crop_relative(img, NAME_SCOPE)
    result, _ = rapidocr.engine(
        name_img,
        use_det=True,
        use_cls=False,
        use_rec=True,
    )
    if not result:
        raise ValueError("家具名称无法可靠确认")
    name = (
        normalize_name(result[0][1])
        if len(result) == 1 and result[0][2] >= MIN_TEXT_CONFIDENCE
        else None
    )
    # 引号可能被拆框或在高置信度结果中漏读，重新识别完整白色字形。
    points = [point for box, _, _ in result for point in box]
    left = max(0, int(min(point[0] for point in points)) - 12)
    right = min(name_img.shape[1], int(max(point[0] for point in points)) + 12)
    mask = cv2.inRange(name_img[:, left:right], (200, 200, 200), (255, 255, 255))
    try:
        candidate = read_confident_text(glyph_image(mask))
    except ValueError as error:
        if name is None:
            raise ValueError("家具名称无法可靠确认") from error
    else:
        # 对已确认的单框名称只恢复完整外围引号；多框结果使用整行重识别。
        if name is None or candidate in {f"“{name}”", f'"{name}"'}:
            name = candidate
    if name is None:
        raise ValueError("家具名称无法可靠确认")
    return name


def furniture_details(img, expected_count=1, expected_batch=None):
    name = furniture_name(img)
    # 数量右对齐：分子为库存，分母随加工份数改变，MAX 后可能是 12/11。
    batch_digits = len(str(expected_batch)) if expected_batch is not None else 1
    left = 0.476 - 0.010 * (len(str(expected_count)) + batch_digits - 2)
    stock = read_confident_text(crop_relative(img, ((left, 0.414), (0.511, 0.443))))
    if not (match := re.fullmatch(r"(\d+)[/／](\d+)", stock)):
        raise ValueError("无法确认家具库存")
    owned, consumed = map(int, match.groups())
    if consumed < 1 or (expected_batch is not None and consumed != expected_batch):
        raise ValueError("家具消耗数量与加工份数不一致")
    return name, owned


def furniture_batch(img):
    # 加工份数为黄色大字；先提取文字，避免宽裁剪的留白影响 OCR。
    region = crop_relative(img, BATCH_SCOPE)
    mask = cv2.inRange(
        cv2.cvtColor(region, cv2.COLOR_RGB2HSV), (20, 140, 140), (40, 255, 255)
    )
    text = read_confident_text(glyph_image(mask, 12, reject_clipped=True))
    if not re.fullmatch(r"\d+", text):
        raise ValueError("无法确认家具加工份数")
    return int(text)


def card_quantity(img):
    quantity = read_text(img)
    if not (match := re.fullmatch(r"(\d+)[/／]1", quantity)):
        # 留白误读时提取白色字形重试，仍须严格匹配消耗一个家具的配方。
        mask = cv2.inRange(img, (200, 200, 200), (255, 255, 255))
        try:
            quantity = read_confident_text(glyph_image(mask))
        except ValueError as error:
            raise ValueError(f"无法读取家具数量：{quantity!r}") from error
        match = re.fullmatch(r"(\d+)[/／]1", quantity)
    if not match:
        raise ValueError(f"无法读取家具数量：{quantity!r}")
    return int(match[1])


def furniture_cards(img):
    """按行、从左到右读取完整卡片；数量单独识别，避免漏掉暗色卡片。"""
    height, width = img.shape[:2]
    result, _ = rapidocr.engine(
        crop_relative(img, CARDS_SCOPE),
        use_det=True,
        use_cls=False,
        use_rec=True,
    )
    cards = []
    found_title = False
    for box, text, _ in result or []:
        if normalize_name(text) != "家具零件":
            continue
        found_title = True
        x = min(point[0] for point in box) / width + 0.2
        y = min(point[1] for point in box) / height + 0.1
        # 列表底部可能仅露出标题，留到下次滚动后处理。
        if y + 0.215 > 0.98:
            continue
        quantity_img = crop_relative(
            img, ((x - 0.005, y + 0.16), (x + 0.09, y + 0.215))
        )
        count = card_quantity(quantity_img)
        # 点击配方标题；家具素材缩略图不是选择配方的按钮。
        cards.append(((x + 0.03, y + 0.015), count))
    if not found_title:
        raise ValueError("未识别到家具列表，停止分解")
    # 同一行两列的 OCR 边框可能相差几像素。
    cards.sort(key=lambda card: card[0][1])
    rows = []
    row_top = None
    for card in cards:
        if row_top is None or card[0][1] - row_top > CARD_ROW_TOLERANCE:
            rows.append([])
            row_top = card[0][1]
        rows[-1].append(card)
    return [card for row in rows for card in sorted(row, key=lambda c: c[0][0])]


def keep_one_enabled(img):
    """只在家具详情有保留开关时返回状态；未知界面不提交加工。"""
    result, _ = rapidocr.engine(
        crop_relative(img, KEEP_SWITCH_SCOPE),
        use_det=True,
        use_cls=False,
        use_rec=True,
    )
    entries = {}
    for box, text, score in result or []:
        text = normalize_name(text).upper()
        if text in {"ON", "OFF", "至少保留1件"} and score < MIN_TEXT_CONFIDENCE:
            raise ValueError("家具保留开关识别置信度不足")
        entries[text] = box
    if "至少保留1件" not in entries:
        raise ValueError("未识别到家具的至少保留1件开关")
    states = entries.keys() & {"ON", "OFF"}
    if len(states) == 1:
        return "ON" in states
    raise ValueError("无法确认家具保留开关状态")


def list_fingerprint(img):
    # 排除顶部资源数字及左侧菜单；缩小后允许轻微截图噪声。
    return cv2.resize(
        cv2.cvtColor(crop_relative(img, LIST_SCOPE), cv2.COLOR_RGB2GRAY),
        (320, 180),
    )


def same_list(previous, current):
    return np.mean(cv2.absdiff(previous, current)) < LIST_CHANGE_THRESHOLD


class FurnitureDismantler:
    def __init__(self, solver):
        self.solver = solver
        self.keep_counts = load_furniture_keep_counts()

    def tap(self, x, y, interval=0.5):
        self.solver.tap(scale_point(self.solver.recog, (x, y)), interval=interval)

    def wait_scene(self, expected):
        for _ in range(20):
            if self.solver.factory_scene() == expected:
                return
            self.solver.sleep()
        raise RuntimeError(f"家具分解未进入预期界面：{expected}")

    def wait_list_position(self, previous):
        # 场景标记可能先于切换动画恢复；短暂重截图后仍须匹配原列表位置。
        for attempt in range(4):
            current = list_fingerprint(self.solver.recog.img)
            if same_list(previous, current):
                return
            if attempt < 3:
                self.solver.sleep(0.5)
        raise RuntimeError("返回家具列表后位置发生变化，停止以避免选错配方")

    def open_formula(self, reset=True):
        solver = self.solver
        for _ in range(30):
            scene = solver.factory_scene()
            if scene == Scene.FACTORY_FORMULA:
                # 切换分类重置列表位置，兼容分解后列表自动重排或移除条目。
                if reset:
                    self.tap(*FORMULA_TABS["芯片"])
                    self.tap(*FORMULA_TABS["家具"])
                self.wait_scene(Scene.FACTORY_FORMULA)
                return
            elif scene == Scene.INFRA_MAIN:
                solver.enter_room("factory")
            elif scene == Scene.FACTORY_ROOM:
                self.tap(*OPEN_WORKSHOP)
            elif scene == Scene.FACTORY_DASHBOARD:
                self.tap(*OPEN_FORMULA)
            elif scene == Scene.FACTORY_PRODUCT_COLLECT:
                solver.back()
            elif scene == Scene.CONNECTING:
                solver.sleep()
            elif solver.find("arrange_check_in") or solver.find(
                "arrange_check_in_small"
            ):
                self.tap(*CONFIRM_OPERATOR)
            else:
                solver.sleep()
        raise RuntimeError("未能打开加工站家具页面")

    def process(self, position, expected_count):
        solver = self.solver
        self.tap(*position)
        self.wait_scene(Scene.FACTORY_DASHBOARD)
        try:
            name, stock = furniture_details(solver.recog.img, expected_count)
        except ValueError as error:
            logger.warning(f"跳过无法识别的家具：{error}")
            return False
        keep = self.keep_counts.get(name)
        if keep is None or stock != expected_count:
            logger.warning(f"跳过{name}：套装信息或库存无法可靠确认")
            return False
        if stock <= keep:
            logger.info(f"跳过{name}：现有{stock}件，完整一套需要{keep}件")
            return False
        if not keep_one_enabled(solver.recog.img):
            raise RuntimeError("至少保留1件未开启，停止家具分解")
        self.tap(*MAX_BUTTON)  # 最多（MAX）
        self.wait_scene(Scene.FACTORY_DASHBOARD)
        maximum = furniture_batch(solver.recog.img)
        if not 0 < maximum < stock:
            raise RuntimeError("家具 MAX 份数异常，未提交加工")
        # ON 的 MAX 至多为真实库存 - 1。无论库存是否被 OCR 稳定高读，
        # 至少再减少 keep - 1 份，才能独立保证真实剩余量不少于 keep。
        # MAX 若受单次加工上限限制，只会多留家具，不能因此减少保护数量。
        target = min(maximum - (keep - 1), stock - keep)
        if target <= 0:
            logger.info(f"跳过{name}：MAX 份数不足以确认完整套装之外的余量")
            return False
        for _ in range(maximum - target):
            self.tap(*MINUS_BUTTON, interval=0.2)
        # 验证实际份数，防止减号漏点或界面变化损坏整套家具。
        if furniture_batch(solver.recog.img) != target or furniture_details(
            solver.recog.img, expected_count, target
        ) != (name, stock):
            raise RuntimeError("无法确认保留完整套装，未提交加工")
        if not keep_one_enabled(solver.recog.img) or not solver.item_valid():
            raise RuntimeError("家具分解数量或保留状态异常，未提交加工")
        solver.recog.save_screencap("furniture")
        self.tap(*SUBMIT_BUTTON, interval=2)
        # 提交只点一次，确认结果后才处理下一个家具。
        self.wait_scene(Scene.FACTORY_PRODUCT_COLLECT)
        solver.recog.save_screencap("furniture")
        solver.back()
        logger.info(f"{name}分解{target}件，至少保留{keep}件组成完整一套")
        return True

    def run(self):
        solver = self.solver
        logger.info("开始分解重复家具，每种保留完整一套所需数量")
        self.open_formula()
        started = monotonic()
        processed = 0
        bottom_checks = 0
        while monotonic() - started < 30 * 60:
            self.wait_scene(Scene.FACTORY_FORMULA)
            cards = furniture_cards(solver.recog.img)
            completed = False
            page = list_fingerprint(solver.recog.img)
            for position, count in cards:
                if count <= 1:
                    continue
                completed = self.process(position, count)
                # 跳过的家具没有消耗，保持当前列表位置继续下一项。
                self.open_formula(reset=completed)
                if not completed:
                    self.wait_list_position(page)
                if completed:
                    processed += 1
                    logger.info(f"已完成第{processed}批重复家具分解")
                    break
            if completed:
                bottom_checks = 0
                continue
            previous = list_fingerprint(solver.recog.img)
            solver.swipe_noinertia(
                (solver.recog.w * 0.5, solver.recog.h * 0.88),
                (0, -solver.recog.h * 0.5),
                interval=1,
            )
            self.wait_scene(Scene.FACTORY_FORMULA)
            current = list_fingerprint(solver.recog.img)
            unchanged = same_list(previous, current)
            bottom_checks = bottom_checks + 1 if unchanged else 0
            if bottom_checks >= 2:
                logger.info(f"重复家具分解完成，共加工{processed}批，已保留完整套装")
                solver.back_to_infrastructure()
                return
        raise RuntimeError("家具分解超过30分钟，停止本轮处理")
