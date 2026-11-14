from copy import deepcopy
from time import monotonic

import cv2

from arknights_mower.models import noto_sans, riic_base_digits, shop
from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.credit_shop import (
    select_value_product,
    value_purchase_deficit,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.datetime import get_server_time
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


class CreditShopIncomplete(Exception):
    """购物尚未完成，保留已发送操作及最后观测供原任务续行。"""

    def __init__(self, message, pending_reward=None, observation=None):
        super().__init__(message)
        self.pending_reward = deepcopy(pending_reward)
        self.observation = deepcopy(observation or {})
        self.continuation = {}


class CreditShop(SceneGraphSolver):
    REWARD_TIMEOUT = 10.0
    REWARD_POLL_INTERVAL = 0.25

    def run(self, *, on_demand=False, resume=None):
        self.on_demand = on_demand
        self.credit_deficit = None
        self.selected_product = None
        self.rejected_product = None
        self.purchase_rechecks = 0
        self.value_catalog = None
        self.pending_reward = deepcopy(resume)
        self.selected_balance = None
        self.selected_slot = None
        self.selected_game_day = None
        self.selected_catalog = None
        logger.info("Start: 信用商店购物")
        result = super().run()
        if result is not True:
            self._incomplete("信用商店流程尚未完成", self._shop_observation())
        return result

    def _select_product(self, product, balance):
        self.selected_product = product
        self.selected_balance = balance
        self.selected_slot = self.products.index(product)
        self.selected_game_day = get_server_time().date().isoformat()
        self.selected_catalog = self._catalog(self.products)
        self.tap(product["touch"])

    @staticmethod
    def _catalog(products):
        return [
            {key: product[key] for key in ("name", "price", "discount")}
            if product is not None
            else None
            for product in products
        ]

    def _shop_observation(self, scene=None):
        scene = self.scene() if scene is None else scene
        observation = {
            "scene": scene,
            "balance": None,
            "products": None,
            "collectable": False,
        }
        if scene == Scene.SHOP_CREDIT:
            observation["game_day"] = get_server_time().date().isoformat()
            observation["collectable"] = bool(self.find("shop_collect"))
            observation["balance"] = self.credit_remain()
            if observation["balance"] is not None and self.product_info():
                observation["products"] = deepcopy(self.products)
            elif observation["balance"] is None:
                self.products = []
        elif scene == Scene.SHOP_CREDIT_CONFIRM:
            observation["cart_available"] = bool(self.find("shop_cart"))
        return observation

    @staticmethod
    def _reward_complete(observation, reward):
        if (
            observation["scene"] != Scene.SHOP_CREDIT
            or observation["balance"] is None
            or observation["products"] is None
        ):
            return False
        if (
            reward.get("dismissed")
            and reward.get("game_day") is not None
            and observation.get("game_day") is not None
            and reward["game_day"] != observation["game_day"]
            and (
                observation["collectable"]
                or (
                    reward.get("catalog") is not None
                    and CreditShop._catalog(observation["products"])
                    != reward["catalog"]
                )
            )
        ):
            return True
        if reward["kind"] == "collect":
            return not observation["collectable"]
        slot = reward.get("slot")
        return slot is None or (
            0 <= slot < len(observation["products"])
            and observation["products"][slot] is None
        )

    @classmethod
    def can_resume(cls, recog, pending):
        reader = object.__new__(cls)
        reader.recog = recog
        observation = reader._shop_observation()
        if observation == pending["observation"]:
            return False
        reward = pending.get("reward")
        if reward is not None:
            if observation["scene"] == Scene.MATERIEL and not reward["dismissed"]:
                return True
            if reader._reward_complete(observation, reward):
                reward["dismissed"] = True
                return True
            return False
        return (
            observation["scene"] == Scene.SHOP_CREDIT
            and observation["balance"] is not None
            and observation["products"] is not None
        ) or (
            observation["scene"] == Scene.SHOP_CREDIT_CONFIRM
            and observation["cart_available"]
        )

    def _incomplete(self, message, observation):
        self.credit_deficit = None
        raise CreditShopIncomplete(
            message,
            pending_reward=getattr(self, "pending_reward", None),
            observation=observation,
        )

    def _finish_reward(self):
        deadline = monotonic() + self.REWARD_TIMEOUT
        observation = {}
        attempts = int(self.REWARD_TIMEOUT / self.REWARD_POLL_INTERVAL) + 1
        for _ in range(attempts):
            if config.stop_mower.is_set():
                raise MowerExit
            observation = self._shop_observation()
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            if observation["scene"] == Scene.MATERIEL:
                if not self.pending_reward["dismissed"]:
                    # 关闭输入只发送一次；尚未退页时继续观察同一操作结果。
                    self.pending_reward["dismissed"] = True
                    self.tap((960, 960))
                    continue
            elif self.pending_reward["dismissed"] and self._reward_complete(
                observation, self.pending_reward
            ):
                self.pending_reward = None
                return observation
            self.sleep(min(self.REWARD_POLL_INTERVAL, remaining))
        self._incomplete("信用商店物资领取尚未确认完成", observation)

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
        self._select_product(product, remain)

    def number(
        self,
        scope: tp.Scope,
        font: str = "noto",
        height: int | None = None,
        thres: int | None = 127,
    ) -> int | None:
        """基于模板匹配读取数字，无法确认完整数字时返回 None。

        Args:
            scope: 识别区域
            font: 数字字体
            height: 高度
        """
        img = cropimg(self.recog.gray, scope)
        if not img.size:
            return None

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

        value = None

        for x, y, w, h in rect:
            # 独立微点不参与数字拼接。
            if w <= 4 and h <= 4:
                continue
            digit = cropimg(img, ((x, y), (x + w, y + h)))
            if img.shape[0] < default_height:
                if h * 3 < img.shape[0] * 2:
                    return None
                # 卷数等较小区域使用同一字体，按实际字高与模板对齐。
                scale = default_height / h
                digit = cv2.resize(digit, None, fx=scale, fy=scale)
            digit = cv2.copyMakeBorder(
                digit, 10, 10, 10, 10, cv2.BORDER_CONSTANT, None, (0,)
            )
            best_score = 0.5
            best_digit = None
            for i in range(10):
                im = templates[i]
                if digit.shape[0] < im.shape[0] or digit.shape[1] < im.shape[1]:
                    continue
                result = cv2.matchTemplate(digit, im, cv2.TM_SQDIFF_NORMED)
                min_val = cv2.minMaxLoc(result)[0]
                if min_val < best_score:
                    best_score = min_val
                    best_digit = i
            if best_digit is None:
                # 不能丢弃无法识别的数字后，把剩余部分当成完整读数。
                return None
            value = (0 if value is None else value) * 10 + best_digit

        return value

    def credit_remain(self) -> int | None:
        credits = self.number(((1700, 39), (1800, 75)), "riic_base", thres=180)
        logger.debug(f"{credits=}")
        return credits

    def product_info(self) -> bool:
        self.products = []
        products = []
        for idx in range(10):
            pos = card_list[idx]
            x, y = va(pos, (30, 30))
            if self.recog.gray[y][x] > 110:
                products.append(None)
                continue
            touch_scope = (pos, va(pos, (card_w, card_h)))
            x, y = va(pos, (6, 60))
            discount = 0
            if self.recog.gray[y][x] < 150:
                discount_scope = sa(((27, 65), (66, 95)), pos)
                discount = self.number(discount_scope, "riic_base")
                if discount is None:
                    return False
            price_scope = sa(((15, 300), (340, 333)), pos)
            price = self.number(price_scope, thres=180)
            if price is None:
                return False

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
                volume = self.number(sa(((252, 14), (270, 40)), pos))
                if volume not in (1, 2):
                    return False
                if volume == 1:
                    item_name += "·卷1"
                else:
                    item_name += "·卷2"

            products.append(
                {
                    "name": item_name,
                    "touch": touch_scope,
                    "discount": discount,
                    "price": price,
                }
            )
        self.products = products
        logger.debug(self.products)
        return True

    def transition(self):
        observation = None
        if getattr(self, "pending_reward", None) is not None:
            observation = self._finish_reward()
        scene = self.scene() if observation is None else observation["scene"]
        if scene == Scene.SHOP_CREDIT:
            if pos := self.find("shop_collect"):
                self.tap(pos, interval=0)
                self.pending_reward = {
                    "kind": "collect",
                    "dismissed": False,
                    "game_day": get_server_time().date().isoformat(),
                }
                return
            observation = observation or self._shop_observation(scene)
            remain = observation["balance"]
            if remain is None or observation["products"] is None:
                self._incomplete("信用商店余额或商品信息未确认", observation)
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
            priority_names = config.conf.maa_mall_buy.split(",")
            blacklist = config.conf.maa_mall_blacklist.split(",")
            for product in self.products:
                if (
                    product
                    and product["name"] in priority_names
                    and self._can_afford(remain, product["price"])
                ):
                    self._select_product(product, remain)
                    return
            for product in self.products:
                if (
                    product
                    and product["name"] not in blacklist
                    and self._can_afford(remain, product["price"])
                ):
                    self._select_product(product, remain)
                    return
            if remain > 300 and config.conf.maa_mall_ignore_blacklist_when_full:
                for product in self.products:
                    if product and self._can_afford(remain, product["price"]):
                        self._select_product(product, remain)
                        return
            if self.on_demand:
                self.credit_deficit = max(
                    0,
                    sum(
                        product["price"]
                        for product in self.products
                        if product and product["name"] not in blacklist
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
                if not self.tap_element("shop_cart", interval=0):
                    self._incomplete(
                        "信用商店购买确认按钮未找到", self._shop_observation(scene)
                    )
                self.pending_reward = {
                    "kind": "purchase",
                    "dismissed": False,
                    "slot": getattr(self, "selected_slot", None),
                    "touch": (
                        self.selected_product["touch"]
                        if self.selected_product is not None
                        else None
                    ),
                    "before_balance": getattr(self, "selected_balance", None),
                    "game_day": getattr(self, "selected_game_day", None),
                    "catalog": getattr(self, "selected_catalog", None),
                    "price": (
                        self.selected_product["price"]
                        if self.selected_product is not None
                        else None
                    ),
                }
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.SHOP_CREDIT)
