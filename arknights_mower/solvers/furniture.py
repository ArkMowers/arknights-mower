"""加工站家具分解：只使用游戏的保留一件与 MAX，不安排干员。"""

import re
from time import monotonic

import cv2
import numpy as np

from arknights_mower.utils import rapidocr
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
        quantity = read_text(
            crop_relative(img, x - 0.005, y + 0.16, x + 0.09, y + 0.215)
        )
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

    def open_formula(self):
        solver = self.solver
        for _ in range(30):
            scene = solver.factory_scene()
            if scene == Scene.FACTORY_FORMULA:
                # 切换分类重置列表位置，兼容分解后列表自动重排或移除条目。
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

    def process(self, position):
        solver = self.solver
        self.tap(*position)
        self.wait_scene(Scene.FACTORY_DASHBOARD)
        if not keep_one_enabled(solver.recog.img):
            raise RuntimeError("至少保留1件未开启，停止家具分解")
        self.tap(0.96, 0.42)  # 最多（MAX）
        self.wait_scene(Scene.FACTORY_DASHBOARD)
        if not keep_one_enabled(solver.recog.img) or not solver.item_valid():
            raise RuntimeError("家具分解数量或保留状态异常，未提交加工")
        self.tap(0.88, 0.9, interval=2)
        # 提交只点一次，确认结果后才处理下一个家具。
        self.wait_scene(Scene.FACTORY_PRODUCT_COLLECT)
        solver.recog.save_screencap("furniture")
        solver.back()

    def run(self):
        solver = self.solver
        logger.info("开始分解所有重复家具，每种至少保留1件")
        self.open_formula()
        started = monotonic()
        processed = 0
        bottom_checks = 0
        while monotonic() - started < 30 * 60:
            self.wait_scene(Scene.FACTORY_FORMULA)
            cards = furniture_cards(solver.recog.img)
            candidate = next((pos for pos, count in cards if count > 1), None)
            if candidate is not None:
                self.process(candidate)
                processed += 1
                logger.info(f"已完成第{processed}批重复家具分解")
                self.open_formula()
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
                logger.info(f"重复家具分解完成，共加工{processed}批，每种保留1件")
                solver.back_to_infrastructure()
                return
        raise RuntimeError("家具分解超过30分钟，停止本轮处理")
