from __future__ import annotations

import os

import cv2
import numpy as np

from ..data import shop_items
from ..ocr import ocr_rectify, ocrhandle
from ..utils import segment, rapidocr
from ..utils.device import Device
from ..utils.digit_reader import DigitReader
from ..utils.image import scope2slice, loadimg
from ..utils.log import logger
from ..utils.path import get_path
from ..utils.recognize import RecognizeError, Scene
from ..utils.solver import BaseSolver, Recognizer
from .. import __rootdir__


class ShopSolver(BaseSolver):
    """
    自动使用信用点购买物资
    """

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)
        self.item_list = {}
        rapidocr.initialize_ocr()
        self.sold_template = loadimg(f"{__rootdir__}/resources/sold_out.png")
        self.credit_icon = loadimg(f"{__rootdir__}/resources/credit_icon.png")
        self.spent_credit = loadimg(f"{__rootdir__}/resources/spent_credit.png")

        self.item_credit_icon = loadimg(f"{__rootdir__}/resources/item_credit_icon.png")
        self.sold_credit_icon = loadimg(f"{__rootdir__}/resources/sold_credit_icon.png")

        self.digitReader = DigitReader()
        self.discount = {}
        self.discount_sold = {}
        for item in os.listdir(f"{__rootdir__}//resources/shop_discount"):
            self.discount[item.replace(".png", "")] = loadimg(f"{__rootdir__}/resources/shop_discount/{item}")
        for item in os.listdir(f"{__rootdir__}//resources/shop_discount"):
            self.discount_sold[item.replace(".png", "")] = loadimg(f"{__rootdir__}/resources/shop_discount_sold/{item}")

        self.sold_price_number = {}
        for item in os.listdir(f"{__rootdir__}//resources/sold_price_number"):
            self.sold_price_number[item.replace(".png", "")] = loadimg(
                f"{__rootdir__}/resources/sold_price_number/{item}")

        self.left_credit_template = {}
        for item in os.listdir(f"{__rootdir__}//resources/recruit_ticket"):
            self.left_credit_template[item.replace(".png", "")] = loadimg(
                f"{__rootdir__}/resources/recruit_ticket/{item}")

        self.shop_data = {}

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
        if (scene := self.scene()) == Scene.INDEX:
            self.tap_element('index_shop')
        elif scene == Scene.SHOP_OTHERS:
            self.tap_element('shop_credit_2')
        elif scene == Scene.SHOP_UNLOCK_SCHEDULE:
            return self.get_spent_credits()
        elif scene == Scene.SHOP_CREDIT:
            collect = self.find('shop_collect')
            if collect is not None:
                self.tap(collect)
            else:
                return self.shop_credit()
        elif scene == Scene.SHOP_CREDIT_CONFIRM:
            if self.find('shop_credit_not_enough') is None:
                self.tap_element('shop_cart')
            elif len(self.priority) > 0:
                # 移除优先级中买不起的物品
                self.priority.remove(self.buying)
                logger.info('信用点不足，放弃购买%s，看看别的...' % self.buying)
                self.back()
            else:
                return True
        elif scene == Scene.SHOP_ASSIST:
            self.back()
        elif scene == Scene.MATERIEL:
            self.tap_element('materiel_ico', scope=((860, 60), (1072, 217)))
        elif scene == Scene.LOADING:
            self.sleep(3)
        elif scene == Scene.CONNECTING:
            self.sleep(3)
        elif self.get_navigation():
            self.tap_element('nav_shop')
        elif scene != Scene.UNKNOWN:
            self.back_to_index()
        else:
            raise RecognizeError('Unknown scene')

    def shop_credit(self) -> bool:
        segments = segment.credit(self.recog.img)
        self.shop_data["credit"] = self.get_credits()
        for i in range(len(segments)):
            scope = (
                segments[i][0], (segments[i][1][0], segments[i][0][1] + (segments[i][1][1] - segments[i][0][1]) // 5))
            ocr = ocrhandle.predict(self.recog.img[scope2slice(scope)])
            # cv2.imshow("ocr",self.recog.img[scope2slice(scope)])
            # cv2.waitKey()
            if len(ocr) == 0:
                raise RecognizeError
            ocr = ocr[0]

            if ocr[1] not in list(shop_items.keys()):
                rapid_res = rapidocr.engine(self.recog.img[scope2slice(scope)], use_det=False, use_cls=False, use_rec=True)[0][0][0]
                if rapid_res in list(shop_items.keys()):
                    ocr[1] = rapid_res
                else:
                    ocr[1] = ocr_rectify(self.recog.img[scope2slice(scope)], ocr, shop_items, '物品名称')

            shop_sold, discount = self.get_discount(
                self.recog.img[segments[i][0][1]:segments[i][1][1], segments[i][0][0]:segments[i][1][0]])

            item_name = ocr[1]
            if item_name == '龙门币':
                price = self.get_item_price(
                    self.recog.img[segments[i][0][1]:segments[i][1][1], segments[i][0][0]:segments[i][1][0]], shop_sold)
                price = round(price / (1 - discount * 0.01), 0)
                if price == 200:
                    item_name = "龙门币(大)"
                elif price == 100:
                    item_name = "龙门币(小)"
            elif item_name == '家具零件':
                price = self.get_item_price(
                    self.recog.img[segments[i][0][1]:segments[i][1][1], segments[i][0][0]:segments[i][1][0]], shop_sold)
                price = round(price / (1 - discount * 0.01), 0)
                if price == 200:
                    item_name = "家具零件(大)"
                elif price == 160:
                    item_name = "家具零件(小)"
            self.item_list[i] = {
                'index': i,
                'name': item_name,
                'discount': discount,
                'shop_sold': shop_sold,
                'position': segments[i],
                'price': round(float(shop_items[item_name]) / (1 - discount * 0.01), 0)
            }
        self.shop_data["item"] = sorted(self.item_list.values(), key=lambda x: x['price'], reverse=True)
        logger.info("购买顺序:{}".format([f"{item['index'] + 1}:{item['name']}" for item in self.shop_data["item"]]))
        return True

    def get_discount(self, item_img: np.ndarray):
        if self.is_sold(item_img):
            for key in self.discount:
                res = cv2.matchTemplate(item_img,
                                        self.discount_sold[key], cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                if max_val > 0.85:
                    return True, int(key)
            return True, 0
        else:
            for key in self.discount:
                res = cv2.matchTemplate(item_img,
                                        self.discount[key], cv2.TM_CCOEFF_NORMED)

                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                if max_val > 0.8:
                    return False, int(key)
            return False, 0

    def is_sold(self, item_img: np.ndarray):
        res = cv2.matchTemplate(item_img,
                                self.sold_template, cv2.TM_CCOEFF_NORMED)

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val > 0.8:
            return True

    def get_credits(self):
        res = cv2.matchTemplate(self.recog.img, self.credit_icon, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        h, w = self.credit_icon.shape[:-1]
        p0 = [max_loc[0] + w, max_loc[1]]
        p1 = [p0[0] + 120, p0[1] + 50]

        res = self.digitReader.get_recruit_ticket(self.recog.img[p0[1]:p1[1], p0[0]:p1[0]])
        cv2.putText(self.recog.img,
                    "{}".format(self.digitReader.get_recruit_ticket(self.recog.img[p0[1]:p1[1], p0[0]:p1[0]])),
                    (p0[0], p0[1]), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return res

    def get_spent_credits(self):
        res = cv2.matchTemplate(self.recog.img, self.spent_credit, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        h, w = self.spent_credit.shape[:-1]
        p0 = [max_loc[0] + w, max_loc[1]]
        p1 = [p0[0] + 200, p0[1] + 60]
        self.shop_data["spent_credits"] = self.digitReader.get_credict_number(self.recog.img[p0[1]:p1[1], p0[0]:p1[0]])
        return True

    def get_item_price(self, item_img: np.ndarray, is_sold: False):
        if is_sold:
            res = cv2.matchTemplate(item_img, self.sold_credit_icon, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            h, w = self.item_credit_icon.shape[:-1]
            p0 = [max_loc[0] + w, max_loc[1]]
            p1 = [p0[0] + 140, p0[1] + 40]

            return self.get_sold_number(item_img[p0[1]:p1[1], p0[0]:p1[0]])
        else:
            res = cv2.matchTemplate(item_img, self.item_credit_icon, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            h, w = self.item_credit_icon.shape[:-1]
            p0 = [max_loc[0] + w, max_loc[1]]
            p1 = [p0[0] + 140, p0[1] + 40]
            return self.digitReader.get_credict_number(item_img[p0[1]:p1[1], p0[0]:p1[0]])

    def get_sold_number(self, digit_part: np.ndarray):
        result = {}
        for j in self.sold_price_number.keys():
            res = cv2.matchTemplate(
                digit_part,
                self.sold_price_number[j],
                cv2.TM_CCOEFF_NORMED,
            )
            threshold = 0.9
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        l = [str(result[k]) for k in sorted(result)]

        return int("".join(l))

    def get_left_credit(self, digit_part):
        result = {}
        digit_part = cv2.cvtColor(digit_part, cv2.COLOR_RGB2GRAY)

        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.left_credit_template[j],
                cv2.TM_CCORR_NORMED,
            )
            threshold = 0.94
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        l = [str(result[k]) for k in sorted(result)]
        return int("".join(l))
    # def shop_credit(self) -> bool:
    #     """ 购买物品逻辑 """
    #     segments = segment.credit(self.recog.img)
    #     valid = []
    #     for seg in segments:
    #         if self.find('shop_sold', scope=seg) is None:
    #             scope = (seg[0], (seg[1][0], seg[0][1] + (seg[1][1]-seg[0][1])//4))
    #             img = self.recog.img[scope2slice(scope)]
    #             ocr = ocrhandle.predict(img)
    #             if len(ocr) == 0:
    #                 raise RecognizeError
    #             ocr = ocr[0]
    #             if ocr[1] not in shop_items:
    #                 ocr[1] = ocr_rectify(img, ocr, shop_items, '物品名称')
    #             valid.append((seg, ocr[1]))
    #     logger.info(f'商店内可购买的物品：{[x[1] for x in valid]}')
    #     if len(valid) == 0:
    #         return True
    #     priority = self.priority
    #     if priority is not None:
    #         valid.sort(
    #             key=lambda x: 9999 if x[1] not in priority else priority.index(x[1]))
    #         if valid[0][1] not in priority:
    #             return True
    #     logger.info(f'实际购买顺序：{[x[1] for x in valid]}')
    #     self.buying = valid[0][1]
    #     self.tap(valid[0][0], interval=3)
