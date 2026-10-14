from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.solvers import shop as shop_module
from arknights_mower.tests.credit_shop_priority_tests import product
from arknights_mower.tests.credit_shop_priority_tests import shopping as shopping
from arknights_mower.utils import config
from arknights_mower.utils.credit_shop import product_sanity_value
from arknights_mower.utils.growth_value import price_catalog


@pytest.mark.parametrize(
    "name,item_id,price,quantity",
    [
        ("龙门币", "4001", 100, 1800),
        ("龙门币", "4001", 200, 3600),
        ("家具零件", "3401", 160, 20),
        ("家具零件", "3401", 200, 25),
        ("招聘许可", "7001", 160, 1),
        ("加急许可", "7002", 160, 1),
        ("赤金", "3003", 160, 6),
        ("基础作战记录", "2001", 100, 9),
        ("初级作战记录", "2002", 200, 9),
        ("技巧概要·卷1", "3301", 160, 5),
        ("技巧概要·卷2", "3302", 200, 3),
        ("碳", "3112", 160, 5),
        ("碳素", "3113", 200, 3),
        ("源岩", "30011", 80, 2),
        ("代糖", "30021", 100, 2),
        ("酯原料", "30031", 100, 2),
        ("异铁碎片", "30041", 120, 2),
        ("双酮", "30051", 120, 2),
        ("破损装置", "30061", 80, 1),
        ("固源岩", "30012", 200, 3),
        ("糖", "30022", 200, 2),
        ("聚酸酯", "30032", 200, 2),
        ("异铁", "30042", 240, 2),
        ("酮凝集", "30052", 240, 2),
        ("装置", "30062", 160, 1),
    ],
)
@pytest.mark.parametrize("discount", [0, 50, 75])
def test_known_pack_uses_whole_quantity_and_supplied_unit_value(
    name, item_id, price, quantity, discount
):
    catalog = {"items": {item_id: {"value": 2.5}}}
    offer = product(0, name, price * (100 - discount) // 100, discount)
    assert product_sanity_value(offer, catalog) == quantity * 2.5


@pytest.mark.parametrize("discount,quantity", [(50, 1800), (75, 3600)])
def test_same_name_and_sale_price_do_not_confuse_pack_size(discount, quantity):
    catalog = {"items": {"4001": {"value": 0.0036}}}
    assert product_sanity_value(
        product(0, "龙门币", 50, discount), catalog
    ) == pytest.approx(quantity * 0.0036)


@pytest.mark.parametrize("price,discount,quantity", [(5, 95, 1800), (2, 99, 3600)])
def test_rare_discounts_still_use_full_pack_value(price, discount, quantity):
    catalog = {"items": {"4001": {"value": 0.0036}}}
    assert product_sanity_value(
        product(0, "龙门币", price, discount), catalog
    ) == pytest.approx(quantity * 0.0036)


@pytest.mark.parametrize(
    "offer",
    [
        product(0, "未知材料", 100),
        product(0, None, 100),
        product(0, "糖", 0),
        product(0, "糖", 80),
        product(0, "糖", 200, 100),
        product(0, "糖", 200, -1),
        product(0, "糖", 100, None),
    ],
)
def test_unknown_or_inconsistent_pack_is_not_valued(offer):
    assert product_sanity_value(offer, {"items": {"30022": {"value": 10}}}) is None


@pytest.mark.parametrize("value", [None, -1, float("nan"), float("inf"), True])
def test_invalid_unit_value_is_not_used(value):
    catalog = {"items": {"30022": {"value": value}}}
    assert product_sanity_value(product(0, "糖", 200), catalog) is None


def save_values(values):
    ids = record.get_recycling_valuation()["item_ids"]
    imported = {
        "prices": {name: value for name, value in values.items() if name != "龙门币"},
        "item_ids": {name: ids[name] for name in values},
    }
    if "龙门币" in values:
        imported["lmd_sanity"] = values["龙门币"]
    return record.update_recycling_valuation(imported=imported)


@pytest.fixture
def value_shopping(shopping):
    config.conf.maa_mall_buy = ""
    config.conf.credit_shop_value_threshold = 0.15
    return shopping


def test_highest_raw_ratio_is_bought_before_overflow_bargain(value_shopping):
    shop, state = value_shopping
    save_values({"糖": 50, "龙门币": 20 / 1800})
    config.conf.credit_shop_value_threshold = 0.3
    state.balance = 400
    state.products = [product(0, "龙门币", 100), product(1, "糖", 200)]

    shop.run()

    assert state.purchased == [(1, 100)]
    assert state.balance == 200


def test_raw_best_unaffordable_does_not_buy_cheaper_runner_up(value_shopping):
    shop, state = value_shopping
    save_values({"糖": 10, "源岩": 3.5})
    config.conf.credit_shop_value_threshold = 0.05
    state.balance = 100
    state.products = [product(0, "源岩", 80), product(1, "糖", 200)]

    shop.run(on_demand=True)

    assert state.purchased == []
    assert state.balance == 100
    assert shop.credit_deficit == 180


def test_overflow_reorders_candidates_and_still_pays_full_price(value_shopping):
    shop, state = value_shopping
    save_values({"糖": 10, "龙门币": 0.005})
    state.balance = 390
    state.products = [product(0, "糖", 200), product(1, "龙门币", 100)]

    shop.run()

    assert state.purchased == [(1, 100)]
    assert state.balance == 290


@pytest.mark.parametrize(
    "credit,purchases,remaining",
    [
        (500, [(0, 100)], 300),
        (600, [(0, 100), (1, 100)], 300),
    ],
)
def test_zero_effective_cost_ties_use_raw_ratio_and_recompute_after_buying(
    value_shopping, credit, purchases, remaining
):
    shop, state = value_shopping
    save_values({"糖": 10, "龙门币": 0.005})
    state.balance = credit
    state.products = [product(1, "龙门币", 100), product(0, "糖", 200)]

    shop.run()

    assert state.purchased == purchases
    assert state.balance == remaining


@pytest.mark.parametrize(
    "credit,threshold,purchases,remaining",
    [
        (200, 0.1, [], 200),
        (200, 0.099, [(0, 100)], 0),
        (350, 20 / 150, [], 350),
        (350, 0.13, [(0, 100)], 150),
    ],
)
def test_strict_threshold_and_exact_cash_for_raw_and_effective_values(
    value_shopping, credit, threshold, purchases, remaining
):
    shop, state = value_shopping
    save_values({"糖": 10})
    config.conf.credit_shop_value_threshold = threshold
    state.balance = credit
    state.products = [product(0, "糖", 200)]

    shop.run()

    assert state.purchased == purchases
    assert state.balance == remaining


def test_blacklist_and_zero_values_are_excluded_even_when_overflowing(value_shopping):
    shop, state = value_shopping
    config.conf.maa_mall_blacklist = "招聘许可,碳"
    config.conf.maa_mall_ignore_blacklist_when_full = True
    state.balance = 1000
    state.products = [
        product(0, "招聘许可", 160),
        product(1, "碳", 160),
        product(2, "家具零件", 200),
        product(3, "加急许可", 160),
    ]

    shop.run(on_demand=True)

    assert state.purchased == []
    assert state.balance == 1000
    assert shop.credit_deficit is None


def test_all_priority_cards_precede_higher_value_ordinary_goods(shopping):
    shop, state = shopping
    save_values({"糖": 100, "招聘许可": 0, "技巧概要·卷2": 0})
    state.balance = 500
    state.products = [
        product(0, "糖", 200),
        product(1, "招聘许可", 160),
        product(2, "技巧概要·卷2", 50, 75),
    ]

    shop.run()

    assert state.purchased == [(2, 100), (1, 100), (0, 100)]
    assert state.balance == 90


def test_saved_prices_override_bundled_values_and_refresh_each_shop_run(value_shopping):
    shop, state = value_shopping
    config.conf.credit_shop_value_threshold = 0.01
    state.products = [product(0, "糖", 200), product(1, "源岩", 80)]
    save_values({"糖": 30, "源岩": 1})
    state.balance = 200
    shop.run()
    assert state.purchased == [(0, 100)]
    first_catalog = deepcopy(shop.value_catalog)

    save_values({"糖": 1, "源岩": 30})
    state.balance, state.purchased = 200, []
    shop.run()
    assert state.purchased == [(1, 100)]
    assert shop.value_catalog["items"]["30011"]["value"] == 30
    assert first_catalog["items"]["30011"]["value"] == 1


def test_one_saved_price_snapshot_per_run(value_shopping, monkeypatch):
    shop, state = value_shopping
    save_values({"糖": 30, "源岩": 30})
    catalog_reader = MagicMock(wraps=price_catalog)
    monkeypatch.setattr(shop_module, "price_catalog", catalog_reader)
    state.balance = 300
    state.products = [product(0, "糖", 200), product(1, "源岩", 80)]
    shop.run()
    assert state.purchased == [(1, 100), (0, 100)]
    catalog_reader.assert_called_once_with()


def test_inactive_feature_never_reads_value_table(shopping, monkeypatch):
    shop, state = shopping
    config.conf.credit_shop_by_value = False
    catalog_reader = MagicMock(
        side_effect=AssertionError("legacy flow must not load values")
    )
    monkeypatch.setattr(shop_module, "price_catalog", catalog_reader)
    state.balance = 120
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 80)]
    shop.run()
    assert state.purchased == [(1, 100)]
    catalog_reader.assert_not_called()


def test_unknown_price_or_missing_value_is_skipped_without_spending(
    value_shopping, monkeypatch
):
    shop, state = value_shopping
    monkeypatch.setattr(shop_module, "price_catalog", lambda: {"items": {}})
    state.balance = 500
    state.products = [product(0, "糖", 200), product(1, "未知材料", 100)]
    shop.run()
    assert state.purchased == []
    assert state.balance == 500


def test_sample_shop_spends_870_using_three_power_threshold(value_shopping):
    shop, state = value_shopping
    config.conf.credit_shop_value_threshold = 0.036
    config.conf.maa_mall_blacklist = ""
    state.balance = 870
    state.products = [
        product(0, "固源岩", 50, 75),
        product(1, "加急许可", 80, 50),
        product(2, "初级作战记录", 100, 50),
        product(3, "源岩", 40, 50),
        product(4, "装置", 80, 50),
        product(5, "碳", 80, 50),
        product(6, "招聘许可", 160),
        product(7, "家具零件", 200),
        product(8, "糖", 200),
        product(9, "装置", 160),
    ]
    shop.run()
    assert state.purchased == [(i, 100) for i in [6, 0, 2, 4, 3, 9, 8, 5]]
    assert state.balance == 0
