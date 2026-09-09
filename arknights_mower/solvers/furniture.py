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


def crop_relative(img, left, top, right, bottom):
    height, width = img.shape[:2]
    return img[
        round(top * height) : round(bottom * height),
        round(left * width) : round(right * width),
    ]


def read_text(img):
    result, _ = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)
    return re.sub(r"\s+", "", "".join(item[0] for item in result or []))


def read_precise_text(img):
    result, _ = rapidocr.engine(img, use_det=False, use_cls=False, use_rec=True)
    if not result or any(score < 0.9 for _, score in result):
        raise ValueError("家具详情识别置信度不足")
    return normalize_name("".join(text for text, _ in result))


def furniture_details(img, expected_count=1, expected_batch=None):
    # 名称长短差异很大，先定位文字，避免「桌子」等短名称被大块留白干扰。
    name_img = crop_relative(img, 0.36, 0.265, 0.59, 0.31)
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
        if len(result) == 1 and result[0][2] >= 0.9
        else None
    )
    # 引号可能被拆框或在高置信度结果中漏读，重新识别完整白色字形。
    points = [point for box, _, _ in result for point in box]
    left = max(0, int(min(point[0] for point in points)) - 12)
    right = min(name_img.shape[1], int(max(point[0] for point in points)) + 12)
    mask = cv2.inRange(name_img[:, left:right], (200, 200, 200), (255, 255, 255))
    x, y, width, height = cv2.boundingRect(mask)
    if width and height:
        text_img = cv2.copyMakeBorder(
            mask[y : y + height, x : x + width],
            6,
            6,
            6,
            6,
            cv2.BORDER_CONSTANT,
            value=0,
        )
        try:
            candidate = read_precise_text(text_img)
        except ValueError:
            if name is None:
                raise
        else:
            # 对已有可靠结果仅接受 OCR 实际读出的完整外围引号，不改写正文。
            if name is None or candidate in {f"“{name}”", f'"{name}"'}:
                name = candidate
    if name is None:
        raise ValueError("家具名称无法可靠确认")
    # 数量右对齐：分子为库存，分母随加工份数改变，MAX 后可能是 12/11。
    batch_digits = len(str(expected_batch)) if expected_batch is not None else 1
    left = 0.476 - 0.010 * (len(str(expected_count)) + batch_digits - 2)
    stock = read_precise_text(crop_relative(img, left, 0.414, 0.511, 0.443))
    if not (match := re.fullmatch(r"(\d+)[/／](\d+)", stock)):
        raise ValueError("无法确认家具库存")
    owned, consumed = map(int, match.groups())
    if consumed < 1 or (expected_batch is not None and consumed != expected_batch):
        raise ValueError("家具消耗数量与加工份数不一致")
    return name, owned


def furniture_batch(img):
    # 加工份数为黄色大字；先提取文字，避免宽裁剪的留白影响 OCR。
    region = crop_relative(img, 0.78, 0.475, 0.95, 0.568)
    mask = cv2.inRange(
        cv2.cvtColor(region, cv2.COLOR_RGB2HSV), (20, 140, 140), (40, 255, 255)
    )
    x, y, width, height = cv2.boundingRect(mask)
    if not width or not height or x == 0 or x + width == mask.shape[1]:
        raise ValueError("家具加工份数为空或被裁切")
    number = cv2.copyMakeBorder(
        mask[y : y + height, x : x + width],
        12,
        12,
        12,
        12,
        cv2.BORDER_CONSTANT,
        value=0,
    )
    text = read_precise_text(number)
    if not re.fullmatch(r"\d+", text):
        raise ValueError("无法确认家具加工份数")
    return int(text)


def furniture_cards(img):
    """按行、从左到右读取完整卡片；数量单独识别，避免漏掉暗色卡片。"""
    height, width = img.shape[:2]
    result, _ = rapidocr.engine(
        crop_relative(img, 0.2, 0.1, 0.98, 1),
        use_det=True,
        use_cls=False,
        use_rec=True,
    )
    cards = []
    found_title = False
    for box, text, _ in result or []:
        if text.replace(" ", "") != "家具零件":
            continue
        found_title = True
        x = min(point[0] for point in box) / width + 0.2
        y = min(point[1] for point in box) / height + 0.1
        # 列表底部可能仅露出标题，留到下次滚动后处理。
        if y + 0.215 > 0.98:
            continue
        quantity_img = crop_relative(img, x - 0.005, y + 0.16, x + 0.09, y + 0.215)
        quantity = read_text(quantity_img)
        match = re.fullmatch(r"(\d+)[/／]1", quantity)
        if not match:
            # 大块留白可能被 OCR 误读为汉字，提取白色数量字形后再严格识别。
            mask = cv2.inRange(quantity_img, (200, 200, 200), (255, 255, 255))
            tx, ty, tw, th = cv2.boundingRect(mask)
            if tw and th:
                number = cv2.copyMakeBorder(
                    mask[ty : ty + th, tx : tx + tw],
                    6,
                    6,
                    6,
                    6,
                    cv2.BORDER_CONSTANT,
                    value=0,
                )
                quantity = read_precise_text(number)
                match = re.fullmatch(r"(\d+)[/／]1", quantity)
        if not match:
            raise ValueError(f"无法读取家具数量：{quantity!r}")
        # 点击配方标题；家具素材缩略图不是选择配方的按钮。
        cards.append(((x + 0.03, y + 0.015), int(match[1])))
    if not found_title:
        raise ValueError("未识别到家具列表，停止分解")
    # 同一行两列的 OCR 边框可能相差几像素。
    cards.sort(key=lambda card: card[0][1])
    rows = []
    for card in cards:
        if not rows or card[0][1] - rows[-1][0][0][1] > 0.04:
            rows.append([])
        rows[-1].append(card)
    return [card for row in rows for card in sorted(row, key=lambda c: c[0][0])]


def keep_one_enabled(img):
    """只在家具详情有保留开关时返回状态；未知界面不提交加工。"""
    result, _ = rapidocr.engine(
        crop_relative(img, 0.75, 0.68, 0.99, 0.83),
        use_det=True,
        use_cls=False,
        use_rec=True,
    )
    entries = {text.replace(" ", "").upper(): box for box, text, _ in result or []}
    if "至少保留1件" not in entries:
        raise ValueError("未识别到家具的至少保留1件开关")
    for state in ("ON", "OFF"):
        if state in entries:
            return state == "ON"
    raise ValueError("无法确认家具保留开关状态")


def list_fingerprint(img):
    # 排除顶部资源数字及左侧菜单；缩小后允许轻微截图噪声。
    return cv2.resize(
        cv2.cvtColor(crop_relative(img, 0.21, 0.13, 0.97, 0.97), cv2.COLOR_RGB2GRAY),
        (320, 180),
    )


class FurnitureDismantler:
    def __init__(self, solver):
        self.solver = solver
        self.keep_counts = load_furniture_keep_counts()

    def tap(self, x, y, interval=0.5):
        self.solver.tap(
            (x * self.solver.recog.w, y * self.solver.recog.h), interval=interval
        )

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
            if np.mean(cv2.absdiff(previous, current)) < 1.5:
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
                    self.tap(0.1, 0.57)
                    self.tap(0.1, 0.71)
                self.wait_scene(Scene.FACTORY_FORMULA)
                return
            elif scene == Scene.INFRA_MAIN:
                solver.enter_room("factory")
            elif scene == Scene.FACTORY_ROOM:
                self.tap(0.1, 0.95)
            elif scene == Scene.FACTORY_DASHBOARD:
                self.tap(0.45, 0.65)
            elif scene == Scene.FACTORY_PRODUCT_COLLECT:
                solver.back()
            elif scene == Scene.CONNECTING:
                solver.sleep()
            elif solver.find("arrange_check_in") or solver.find(
                "arrange_check_in_small"
            ):
                self.tap(0.25, 0.95)
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
        self.tap(0.96, 0.42)  # 最多（MAX）
        self.wait_scene(Scene.FACTORY_DASHBOARD)
        maximum = furniture_batch(solver.recog.img)
        if not 0 < maximum < stock:
            raise RuntimeError("家具 MAX 份数异常，未提交加工")
        target = min(maximum, stock - keep)
        for _ in range(maximum - target):
            self.tap(0.84, 0.68, interval=0.2)
        # 验证实际份数，防止减号漏点或界面变化损坏整套家具。
        if furniture_batch(solver.recog.img) != target or furniture_details(
            solver.recog.img, expected_count, target
        ) != (name, stock):
            raise RuntimeError("无法确认保留完整套装，未提交加工")
        if not keep_one_enabled(solver.recog.img) or not solver.item_valid():
            raise RuntimeError("家具分解数量或保留状态异常，未提交加工")
        self.tap(0.88, 0.9, interval=2)
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
            unchanged = np.mean(cv2.absdiff(previous, current)) < 1.5
            bottom_checks = bottom_checks + 1 if unchanged else 0
            if bottom_checks >= 2:
                logger.info(f"重复家具分解完成，共加工{processed}批，已保留完整套装")
                solver.back_to_infrastructure()
                return
        raise RuntimeError("家具分解超过30分钟，停止本轮处理")
