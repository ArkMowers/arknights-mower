"""雷锋模式或自有库满时，补送已经摆上板的同编号自有线索。"""

import re

import cv2
import numpy as np

from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import cropimg, loadres
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene

BOARD_CLUE_ORIGINS = {
    1: (497, 228),
    2: (799, 334),
    3: (1104, 198),
    4: (1428, 257),
    5: (920, 660),
    6: (1230, 573),
    7: (579, 608),
}


def clue_card_number(image):
    """匹配真实线索卡片；空槽位的数字不能建立可赠送的依据。"""
    scores = []
    for number in range(1, 8):
        template = loadres(f"clue/{number}")
        if any(a < b for a, b in zip(image.shape[:2], template.shape[:2])):
            return None
        score = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED).max()
        scores.append((float(score), number))
    scores.sort(reverse=True)
    if scores[0][0] >= 0.7 and scores[0][0] - scores[1][0] >= 0.1:
        return scores[0][1]
    return None


class ClueGiftMixin:
    def _read_placed_clue_numbers(self):
        """读取确实已摆放的编号；取帧后已离开线索板时返回 None。"""
        self.wait_product_complete()
        self.recog.update()
        if self.scene() != Scene.INFRA_CONFIDENTIAL:
            return None
        placed = set()
        for number, (x, y) in BOARD_CLUE_ORIGINS.items():
            # 卡片位置存在数像素偏移，在各自槽位内留出模板搜索余量。
            card = cropimg(self.recog.img, ((x - 16, y - 16), (x + 178, y + 232)))
            if clue_card_number(card) == number:
                placed.add(number)
        return frozenset(placed)

    def _read_clue_gift_capacity(self):
        if self.scene() != Scene.CLUE_GIVE_AWAY:
            return None
        if rapidocr.engine is None:
            rapidocr.initialize_ocr()
        result = rapidocr.engine(
            cropimg(self.recog.img, ((420, 16), (616, 76))),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )[0]
        if not result or len(result) != 1 or result[0][1] < 0.9:
            return None
        text = "".join(result[0][0].split())
        match = re.fullmatch(r"自有库(\d{1,2})/(\d{1,2})", text)
        if match is None:
            return None
        count, limit = map(int, match.groups())
        if 0 <= count <= limit <= 99 and limit > 0:
            return count, limit
        return None

    def _clue_missing_filter(self):
        if self.scene() != Scene.CLUE_GIVE_AWAY:
            return None
        left = np.all(self.get_color((1050, 38)) > 220)
        right = np.all(self.get_color((1078, 38)) > 220)
        if left != right:
            return bool(right)
        return None

    def _set_clue_missing_filter(self, enabled):
        current = self._clue_missing_filter()
        if current is None:
            return False
        if current == enabled:
            return True
        self.tap((1064, 38))
        for _ in range(3):
            self.recog.update()
            if self._clue_missing_filter() == enabled:
                return True
            self.sleep(0.5)
        return False

    def _first_clue_recipient(self):
        """只选择有传递奖励标签及橙色赠送按钮的可见好友。"""
        if self.scene() != Scene.CLUE_GIVE_AWAY:
            return None
        for row in range(4):
            label = ((1450, 228 + row * 222), (1580, 278 + row * 222))
            if not self.find("clue/label_give_away", scope=label):
                continue
            button = cropimg(
                self.recog.img,
                ((1768, 110 + row * 222), (1835, 284 + row * 222)),
            )
            hsv = cv2.cvtColor(button, cv2.COLOR_RGB2HSV)
            orange = (hsv[..., 0] <= 30) & (hsv[..., 1] >= 170) & (hsv[..., 2] >= 150)
            if orange.mean() >= 0.5:
                return (1790, 200 + row * 222)
        return None

    def _give_one_placed_clue(self, placed):
        """快速送出后按需补送一张；未知画面或结果不重发。"""
        if not placed:
            return False
        self.wait_product_complete()
        self.recog.update()
        capacity = self._read_clue_gift_capacity()
        if capacity is not None:
            self.clue_count = capacity[0]
        if (
            capacity is None
            or capacity[0] == 0
            or (not self.leifeng_mode and capacity[0] < capacity[1])
        ):
            return False
        original_filter = self._clue_missing_filter()
        if original_filter is None:
            return False
        completed = self._select_and_give_placed_clue(placed, capacity)
        # 正常结束时恢复用户筛选；停止或设备异常直接向外传播，不追加点击。
        self._set_clue_missing_filter(original_filter)
        return completed

    def _select_and_give_placed_clue(self, placed, capacity):
        for number in sorted(placed):
            if self.scene() != Scene.CLUE_GIVE_AWAY:
                return False
            self.tap((130 + (number - 1) * 77, 130))
            self.recog.update()
            if self.scene() != Scene.CLUE_GIVE_AWAY:
                return False
            card_scope = ((30, 208), (192, 424))
            if clue_card_number(cropimg(self.recog.img, card_scope)) != number:
                continue
            # 赠送页只列出可传递的自有线索，不从接收库选择。
            self.tap(card_scope)
            self.recog.update()
            if not self._set_clue_missing_filter(True):
                return False
            recipient = self._first_clue_recipient()
            if recipient is None:
                if not self._set_clue_missing_filter(False):
                    return False
                recipient = self._first_clue_recipient()
            if recipient is None:
                return False
            # 选人期间若库存发生变化，不再依据旧读数赠送。
            if self._read_clue_gift_capacity() != capacity:
                return False
            logger.info("向好友补送一张板上已有的 %s 号自有线索", number)
            self.tap(recipient)
            for _ in range(4):
                self.recog.update()
                after = self._read_clue_gift_capacity()
                if after == (capacity[0] - 1, capacity[1]):
                    self.clue_count = after[0]
                    return True
                self.sleep(0.5)
            logger.warning(
                "未确认线索赠送后的库存减少，本次不再赠送",
                extra={"archive_screenshots": True},
            )
            return False
        return False
