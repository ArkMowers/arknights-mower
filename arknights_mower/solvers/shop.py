from __future__ import annotations

from ..data import shop_items
from ..ocr import ocr_rectify, ocrhandle
from ..utils import segment
from ..utils.device import Device
from ..utils.image import scope2slice
from ..utils.log import logger
from ..utils.recognize import RecognizeError, Scene
from ..utils.solver import BaseSolver, Recognizer


class ShopSolver(BaseSolver):
    """
    自动使用信用点购买物资
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

    def run(self, priority: list[str] = None) -> None:
        """
        :param priority: list[str], 使用信用点购买东西的优先级, 若无指定则默认购买第一件可购买的物品
        """
        self.priority = priority
        self.buying = None
        logger.info('Start: 商店')
        logger.info('购买期望：%s' % priority if priority else '无，购买到信用点用完为止')
        super().run()

    def transition(self) -> bool:
        if self.scene() == Scene.INDEX:
            self.tap_element('index_shop')
        elif self.scene() == Scene.SHOP_OTHERS:
            self.tap_element('shop_credit_2')
        elif self.scene() == Scene.SHOP_CREDIT:
            collect = self.find('shop_collect')
            if collect is not None:
                self.tap(collect)
            else:
                return self.shop_credit()
        elif self.scene() == Scene.SHOP_CREDIT_CONFIRM:
            if self.find('shop_credit_not_enough') is None:
                self.tap_element('shop_cart')
            elif len(self.priority) > 0:
                # 移除优先级中买不起的物品
                self.priority.remove(self.buying) 
                logger.info('信用点不足，放弃购买%s，看看别的...' % self.buying)
                self.back()
            else:
                return True
        elif self.scene() == Scene.SHOP_ASSIST:
            self.back()
        elif self.scene() == Scene.MATERIEL:
            self.tap_element('materiel_ico')
        elif self.scene() == Scene.LOADING:
            self.sleep(3)
        elif self.scene() == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_shop')
        elif self.scene() != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')

    def shop_credit(self) -> bool:
        """ 购买物品逻辑 """
        segments = segment.credit(self.recog.img)
        valid = []
        for seg in segments:
            if self.find('shop_sold', scope=seg) is None:
                scope = (seg[0], (seg[1][0], seg[0][1] + (seg[1][1]-seg[0][1])//4))
                img = self.recog.img[scope2slice(scope)]
                ocr = ocrhandle.predict(img)
                if len(ocr) == 0:
                    raise RecognizeError
                ocr = ocr[0]
                if ocr[1] not in shop_items:
                    ocr[1] = ocr_rectify(img, ocr, shop_items, '物品名称')
                valid.append((seg, ocr[1]))
        logger.info(f'商店内可购买的物品：{[x[1] for x in valid]}')
        if len(valid) == 0:
            return True
        priority = self.priority
        if priority is not None:
            valid.sort(
                key=lambda x: 9999 if x[1] not in priority else priority.index(x[1]))
            if valid[0][1] not in priority:
                return True
        logger.info(f'实际购买顺序：{[x[1] for x in valid]}')
        self.buying = valid[0][1]
        self.tap(valid[0][0], interval=3)
