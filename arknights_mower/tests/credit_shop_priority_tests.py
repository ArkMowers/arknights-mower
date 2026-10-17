from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.shop import CreditShop
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scene import Scene


def product(slot, name, price, discount=0):
    return {
        "name": name,
        "price": price,
        "discount": discount,
        "touch": (slot, 100),
    }


@pytest.fixture
def shopping(monkeypatch, income_db):
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            credit_shop_by_value=True,
            visit_friend_enable=True,
            visit_friend_mode="mower",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            maa_mall_buy="招聘许可,技巧概要·卷2",
            maa_mall_blacklist="碳",
        ),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    state = SimpleNamespace(
        balance=0,
        daily=0,
        products=[],
        purchased=[],
        scene=Scene.SHOP_CREDIT,
        selected=None,
        rejected=False,
        observations=0,
    )
    shop = object.__new__(CreditShop)
    shop.recog = MagicMock()
    shop.check_current_focus = MagicMock()
    shop.scene = lambda: state.scene
    shop.credit_remain = lambda: state.balance

    def find(name):
        if name == "shop_collect" and state.daily:
            return (999, 999)
        if name == "shop_credit_not_enough":
            return state.rejected

    def product_info():
        state.observations += 1
        assert state.observations < 40, (
            "shopping must finish without repeating purchases"
        )
        shop.products = [
            p if p and p["touch"] not in state.purchased else None
            for p in state.products
        ]

    def tap(position):
        if position == (999, 999):
            state.balance += state.daily
            state.daily = 0
            return
        state.selected = next(p for p in state.products if p and p["touch"] == position)
        state.scene = Scene.SHOP_CREDIT_CONFIRM

    def confirm(name):
        assert name == "shop_cart"
        assert state.balance >= state.selected["price"]
        state.balance -= state.selected["price"]
        state.purchased.append(state.selected["touch"])
        state.scene = Scene.SHOP_CREDIT

    shop.find = find
    shop.product_info = product_info
    shop.tap = MagicMock(side_effect=tap)
    shop.tap_element = MagicMock(side_effect=confirm)
    shop.back = MagicMock(
        side_effect=lambda: setattr(state, "scene", Scene.SHOP_CREDIT)
    )
    return shop, state


@pytest.mark.parametrize("on_demand", [False, True])
def test_unaffordable_priority_blocks_affordable_normal_goods(shopping, on_demand):
    shop, state = shopping
    config.conf.credit_shop_value_threshold = 100
    state.balance = 120
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 100, 50)]

    shop.run(on_demand=on_demand)

    assert state.purchased == []
    assert state.balance == 120
    assert shop.credit_deficit == (40 if on_demand else None)
    shop.tap.assert_not_called()


def test_priority_uses_actual_price_before_item_or_discount_order(shopping):
    shop, state = shopping
    config.conf.maa_mall_buy = "技巧概要·卷2,招聘许可,源岩"
    config.conf.credit_shop_value_threshold = 100
    state.balance = 500
    state.products = [
        product(0, "糖", 200),
        product(1, "招聘许可", 160),
        product(2, "技巧概要·卷2", 100, 50),
        product(3, "源岩", 80),
        product(4, "招聘许可", 40, 75),
        None,
    ]

    shop.run()

    assert state.purchased == [(4, 100), (3, 100), (2, 100), (1, 100)]
    assert state.balance == 120
    assert shop.credit_deficit is None


def test_remaining_priority_still_blocks_normal_goods_after_purchase(shopping):
    shop, state = shopping
    state.balance = 120
    state.products = [
        product(0, "技巧概要·卷2", 100, 50),
        product(1, "招聘许可", 40, 75),
        product(2, "糖", 20),
    ]

    shop.run()

    assert state.purchased == [(1, 100)]
    assert state.balance == 80


@pytest.mark.parametrize("on_demand", [False, True])
def test_exact_balance_buys_priority_without_requiring_board_feature(
    shopping, on_demand
):
    shop, state = shopping
    state.balance = 160
    state.products = [product(0, "招聘许可", 160)]

    shop.run(on_demand=on_demand)

    assert state.purchased == [(0, 100)]
    assert state.balance == 0


def test_equal_prices_use_shop_order_and_buy_each_card_once(shopping):
    shop, state = shopping
    config.conf.maa_mall_buy = "源岩,招聘许可"
    state.balance = 240
    state.products = [
        product(0, "招聘许可", 80, 50),
        product(1, "源岩", 80),
        product(2, "招聘许可", 80, 50),
    ]

    shop.run()

    assert state.purchased == [(0, 100), (1, 100), (2, 100)]
    assert state.balance == 0


def test_priority_takes_precedence_over_blacklist(shopping):
    shop, state = shopping
    config.conf.maa_mall_blacklist = "招聘许可"
    state.balance = 160
    state.products = [product(0, "招聘许可", 160)]

    shop.run()

    assert state.purchased == [(0, 100)]


@pytest.mark.parametrize("priority", ["", "招聘许可"])
def test_no_remaining_priority_enters_value_shopping_without_blacklisted_overflow(
    shopping, priority
):
    shop, state = shopping
    config.conf.maa_mall_buy = priority
    config.conf.maa_mall_ignore_blacklist_when_full = True
    state.balance = 600
    state.products = [None, product(1, "糖", 200), product(2, "碳", 80, 50)]

    shop.run(on_demand=True)

    assert state.purchased == [(1, 100)]
    assert state.balance == 400
    assert shop.credit_deficit is None


def test_shop_daily_credit_is_available_only_after_collection(shopping):
    shop, state = shopping
    state.balance = 80
    state.daily = 80
    state.products = [product(0, "招聘许可", 160)]

    shop.run()

    assert shop.tap.call_args_list[0].args == ((999, 999),)
    assert state.purchased == [(0, 100)]
    assert state.balance == 0


@pytest.mark.parametrize("on_demand", [False, True])
def test_purchase_rejection_does_not_fall_back_or_request_credit(shopping, on_demand):
    shop, state = shopping
    state.balance = 160
    state.rejected = True
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 80)]

    shop.run(on_demand=on_demand)

    assert shop.tap.call_count == 1
    shop.tap_element.assert_not_called()
    assert state.purchased == []
    assert shop.credit_deficit is None


@pytest.mark.parametrize(
    "inactive",
    [
        {"credit_shop_by_value": False},
        {"visit_friend_enable": False},
        {"visit_friend_mode": "maa"},
        {"maa_mall_enable": False},
        {"maa_mall_mode": "maa"},
    ],
)
@pytest.mark.parametrize("on_demand", [False, True])
def test_inactive_value_feature_keeps_old_affordable_fallback(
    shopping, monkeypatch, inactive, on_demand
):
    shop, state = shopping
    monkeypatch.setattr(config, "conf", config.conf.updated(inactive))
    state.balance = 120
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 80)]

    shop.run(on_demand=on_demand)

    assert state.purchased == [(1, 100)]
    assert state.balance == 40
    assert shop.credit_deficit == (120 if on_demand else None)


def test_disabled_value_feature_keeps_old_priority_and_overflow_order(shopping):
    shop, state = shopping
    config.conf.credit_shop_by_value = False
    config.conf.maa_mall_ignore_blacklist_when_full = True
    state.balance = 800
    state.products = [
        product(0, "糖", 80),
        product(1, "招聘许可", 160),
        product(2, "技巧概要·卷2", 50, 75),
        product(3, "碳", 80),
    ]

    shop.run()

    assert state.purchased == [(1, 100), (2, 100), (0, 100), (3, 100)]
    assert state.balance == 430


@pytest.mark.parametrize(
    "name,listed_name", [("糖", "代糖"), ("源岩", "固源岩"), ("碳", "碳素")]
)
@pytest.mark.parametrize("on_demand", [False, True])
def test_ordinary_blacklist_matches_whole_names(shopping, name, listed_name, on_demand):
    shop, state = shopping
    config.conf.credit_shop_by_value = False
    config.conf.maa_mall_buy = ""
    config.conf.maa_mall_blacklist = f"加急许可,{listed_name},家具零件"
    state.balance = 250
    state.products = [
        product(0, name, 100),
        product(1, listed_name, 100),
        product(2, "聚酸酯", 200),
    ]

    shop.run(on_demand=on_demand)

    assert state.purchased == [(0, 100)]
    assert state.balance == 150
    assert shop.credit_deficit == (50 if on_demand else None)


@pytest.mark.parametrize(
    "name,listed_name", [("糖", "代糖"), ("源岩", "固源岩"), ("碳", "碳素")]
)
@pytest.mark.parametrize("on_demand", [False, True])
def test_ordinary_priority_matches_whole_names(shopping, name, listed_name, on_demand):
    shop, state = shopping
    config.conf.credit_shop_by_value = False
    config.conf.maa_mall_buy = f"招聘许可,{listed_name}"
    config.conf.maa_mall_blacklist = ""
    state.balance = 150
    state.products = [product(0, name, 100), product(1, listed_name, 100)]

    shop.run(on_demand=on_demand)

    assert state.purchased == [(1, 100)]
    assert state.balance == 50
    assert shop.credit_deficit == (50 if on_demand else None)


@pytest.mark.parametrize(
    "name,listed_name", [("糖", "代糖"), ("源岩", "固源岩"), ("碳", "碳素")]
)
def test_ordinary_deficit_blacklist_matches_whole_names(shopping, name, listed_name):
    shop, state = shopping
    config.conf.credit_shop_by_value = False
    config.conf.maa_mall_buy = ""
    config.conf.maa_mall_blacklist = listed_name
    state.balance = 50
    state.products = [
        product(0, name, 100),
        product(1, listed_name, 100),
        product(2, "聚酸酯", 200),
    ]

    shop.run(on_demand=True)

    assert state.purchased == []
    assert shop.credit_deficit == 250
