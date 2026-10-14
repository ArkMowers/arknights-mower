import cv2

from arknights_mower.models import noto_sans, riic_base_digits, shop
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.credit_shop import (
    select_value_product,
    value_purchase_deficit,
)
from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.growth_value import price_catalog
from arknights_mower.utils.image import cropimg, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.vector import sa, va

card_w, card_h = 352, 354
top, left = 222, 25
gap = 28

card_list = []
for i in range(2):
    for j in range(5):
        card_list.append((left + j * (card_w + gap), top + i * (card_h + gap)))


class CreditShop(SceneGraphSolver):
    def run(self, *, on_demand=False):
        self.on_demand = on_demand
        self.credit_deficit = None
        self.selected_product = None
        self.rejected_product = None
        self.purchase_rechecks = 0
        self.value_catalog = None
        logger.info("Start: 信用商店购物")
        super().run()

    def _can_afford(self, remain, price):
        return remain >= price if self.on_demand else remain > price

    def _shop_by_value(self, remain):
        """先买空优先商品，再按性价比购买；只使用本次读取的实际余额。"""
        priority_names = config.conf.maa_mall_buy.split(",")
        priorities = [
            product
            for product in self.products
            if product and product["name"] in priority_names
        ]
        if priorities:
            product = min(priorities, key=lambda item: item["price"])
        else:
            if self.value_catalog is None:
                self.value_catalog = price_catalog()
            product = select_value_product(
                self.products,
                self.value_catalog,
                remain,
                config.conf.credit_shop_value_threshold,
                config.conf.maa_mall_blacklist.split(","),
            )
            if product is None:
                return True
        if remain < product["price"]:
            if self.on_demand:
                if self.value_catalog is None:
                    self.value_catalog = price_catalog()
                self.credit_deficit = value_purchase_deficit(
                    self.products,
                    self.value_catalog,
                    remain,
                    config.conf.credit_shop_value_threshold,
                    priority_names,
                    config.conf.maa_mall_blacklist.split(","),
                )
            logger.info(
                "待购商品 %s 需 %s 信用，当前余额 %s，结束本轮购物",
                product["name"],
                product["price"],
                remain,
            )
            return True
        self.selected_product = product
        self.tap(product["touch"])

    def number(
        self,
        scope: tp.Scope,
        font: str = "noto",
        height: int | None = None,
        thres: int | None = 127,
    ):
        """基于模板匹配的数字识别

        Args:
            scope: 识别区域
            font: 数字字体
            height: 高度
        """
        img = cropimg(self.recog.gray, scope)

        if font == "riic_base":
            templates = riic_base_digits
            default_height = 28
        else:
            templates = noto_sans
            default_height = 29

        if height and height != default_height:
            scale = default_height / height
            img = cv2.resize(img, None, None, scale, scale)
        img = thres2(img, thres)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rect = [cv2.boundingRect(c) for c in contours]
        rect.sort(key=lambda c: c[0])

        value = 0

        for x, y, w, h in rect:
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            score = []
            for i in range(10):
                im = templates[i]
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                score.append(min_val)
            value = value * 10 + score.index(min(score))

        return value

    def credit_remain(self):
        credits = self.number(((1700, 39), (1800, 75)), "riic_base", thres=180)
        logger.debug(f"{credits=}")
        return credits

    def product_info(self):
        self.products = []
        for idx in range(10):
            pos = card_list[idx]
            x, y = va(pos, (30, 30))
            if self.recog.gray[y][x] > 110:
                self.products.append(None)
                continue
            touch_scope = (pos, va(pos, (card_w, card_h)))
            x, y = va(pos, (6, 60))
            discount = 0
            if self.recog.gray[y][x] < 150:
                discount_scope = sa(((27, 65), (66, 95)), pos)
                discount = self.number(discount_scope, "riic_base")
            price_scope = sa(((15, 300), (340, 333)), pos)
            price = self.number(price_scope, thres=180)

            score = 1
            item_name = None
            name_scope = sa(((60, 11), (320, 45)), pos)
            target = cropimg(self.recog.gray, name_scope)
            target = cv2.copyMakeBorder(
                target, 10, 10, 30, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            target = thres2(target, 127)
            for name, img in shop.items():
                result = cv2.matchTemplate(target, img, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if min_val < score:
                    score = min_val
                    item_name = name
            if item_name == "技巧概要":
                if self.number(sa(((252, 14), (270, 40)), pos)) == 1:
                    item_name += "·卷1"
                else:
                    item_name += "·卷2"

            self.products.append(
                {
                    "name": item_name,
                    "touch": touch_scope,
                    "discount": discount,
                    "price": price,
                }
            )
        logger.debug(self.products)

    def transition(self):
        if (scene := self.scene()) == Scene.SHOP_CREDIT:
            if pos := self.find("shop_collect"):
                self.tap(pos)
                return
            remain = self.credit_remain()
            self.product_info()
            if self.on_demand and self.rejected_product is not None:
                rejected = next(
                    (
                        product
                        for product in self.products
                        if product
                        and product["touch"] == self.rejected_product["touch"]
                    ),
                    None,
                )
                if rejected is not None and remain >= rejected["price"]:
                    logger.warning("余额与信用不足提示矛盾，结束本次购物，不触发领板")
                    return True
                self.rejected_product = None
            if config.conf.should_use_credit_shop_value:
                return self._shop_by_value(remain)
            for product in self.products:
                if (
                    product
                    and product["name"] in config.conf.maa_mall_buy
                    and self._can_afford(remain, product["price"])
                ):
                    self.selected_product = product
                    self.tap(product["touch"])
                    return
            for product in self.products:
                if (
                    product
                    and product["name"] not in config.conf.maa_mall_blacklist
                    and self._can_afford(remain, product["price"])
                ):
                    self.selected_product = product
                    self.tap(product["touch"])
                    return
            if remain > 300 and config.conf.maa_mall_ignore_blacklist_when_full:
                for product in self.products:
                    if product and self._can_afford(remain, product["price"]):
                        self.selected_product = product
                        self.tap(product["touch"])
                        return
            if self.on_demand:
                self.credit_deficit = max(
                    0,
                    sum(
                        product["price"]
                        for product in self.products
                        if product
                        and product["name"] not in config.conf.maa_mall_blacklist
                    )
                    - remain,
                )
            return True
        elif scene == Scene.SHOP_CREDIT_CONFIRM:
            if self.find("shop_credit_not_enough"):
                self.back()
                if (
                    self.on_demand
                    and self.selected_product is not None
                    and not self.purchase_rechecks
                ):
                    # 只复核一次实际余额；矛盾观测不能作为领取信用的依据。
                    self.purchase_rechecks += 1
                    self.rejected_product = self.selected_product
                    return
                return True
            else:
                self.tap_element("shop_cart")
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.SHOP_CREDIT)
