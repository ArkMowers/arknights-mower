import traceback

from ..ocr import ocrhandle, ocr_rectify
from ..utils import config
from ..utils import segment
from ..utils.log import logger
from ..utils.recognize import Scene, RecognizeError
from ..utils.solver import BaseSolver, StrategyError
from ..data.item import shop_items


class ShopSolver(BaseSolver):
    """
    自动使用信用点购买物资
    """

    def __init__(self, adb=None, recog=None):
        super(ShopSolver, self).__init__(adb, recog)

    def run(self, priority=config.SHOP_PRIORITY):
        """
        :param priority: list[str], 使用信用点购买东西的优先级, 若无指定则默认购买第一件可购买的物品
        """
        logger.info('Start: 商店')

        retry_times = config.MAX_RETRYTIME
        while retry_times > 0:
            try:
                if self.scene() == Scene.INDEX:
                    self.tap_element('index_shop')
                elif self.scene() == Scene.SHOP_OTHERS:
                    self.tap_element('shop_credit_2')
                elif self.scene() == Scene.SHOP_CREDIT:
                    collect = self.recog.find('shop_collect')
                    if collect is not None:
                        self.tap(collect)
                    else:
                        segments = segment.credit(self.recog.img)
                        valid = []
                        for seg in segments:
                            if self.recog.find('shop_sold', scope=seg) is None:
                                img = self.recog.img[seg[0][1]:seg[0][1]+(seg[1][1]-seg[0][1])//4, seg[0][0]:seg[1][0]]
                                ocr = ocrhandle.predict(img)[0]
                                if ocr[1] not in shop_items:
                                    ocr[1] = ocr_rectify(img, ocr, shop_items, '物品名称')
                                valid.append((seg, ocr[1]))
                        logger.info(f'商店内可购买的物品：{[x[1] for x in valid]}')
                        if len(valid) == 0:
                            break
                        if priority is not None:
                            valid.sort(
                                key=lambda x: 9999 if x[1] not in priority else priority.index(x[1]))
                            if valid[0][1] not in priority:
                                break
                        self.tap(valid[0][0], interval=3)
                elif self.scene() == Scene.SHOP_CREDIT_CONFIRM:
                    if self.recog.find('shop_credit_not_enough') is None:
                        self.tap_element('shop_cart')
                    else:
                        break
                elif self.scene() == Scene.MATERIEL:
                    self.tap_element('materiel_ico')
                elif self.scene() == Scene.LOADING:
                    self.sleep(3)
                elif self.get_navigation():
                    self.tap_element('nav_shop')
                elif self.scene() != Scene.UNKNOWN:
                    self.back_to_index()
                else:
                    raise RecognizeError
            except RecognizeError as e:
                logger.warning(f'识别出了点小差错 qwq: {e}')
                retry_times -= 1
                self.sleep(3)
                continue
            except StrategyError as e:
                logger.error(e)
                logger.debug(traceback.format_exc())
                return
            except Exception as e:
                raise e
            retry_times = config.MAX_RETRYTIME
