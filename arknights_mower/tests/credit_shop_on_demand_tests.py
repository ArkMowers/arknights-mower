import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

with pytest.MonkeyPatch.context() as import_context:
    import_context.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule

from arknights_mower.solvers import clue_credit
from arknights_mower.tests.credit_shop_priority_tests import product
from arknights_mower.tests.credit_shop_priority_tests import shopping as shopping
from arknights_mower.tests.credit_shop_value_tests import save_values
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit


@pytest.fixture
def on_demand_shopping(shopping, monkeypatch):
    shop, state = shopping
    config.conf.clue_credit_on_demand = True
    config.conf.credit_shop_value_threshold = 0.1
    config.conf.maa_mall_buy = "招聘许可"
    save_values({"招聘许可": 0, "糖": 20, "源岩": 6})
    state.now = datetime.fromisoformat("2026-10-15T12:00:00+08:00")
    state.previous = state.current = 300
    state.visits = []
    state.board_confirmed = True
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 200)]
    monkeypatch.setattr(
        clue_credit,
        "get_server_time",
        lambda: state.now.astimezone(timezone(timedelta(hours=4))),
    )
    monkeypatch.setattr(clue_credit, "CreditShop", lambda *_: shop)
    monkeypatch.setattr(base_schedule, "CreditShop", lambda *_: shop)
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.daily_visit_friend = date.min
    scheduler.daily_visit_friend_attempt = clue_credit.get_server_time().date()
    scheduler._party_time = None
    scheduler.device = MagicMock()
    scheduler.recog = shop.recog
    scheduler.scene_graph_navigation = MagicMock()

    def visit(*, collect_current):
        state.visits.append(collect_current)
        state.balance += state.previous
        state.previous = 0
        if collect_current:
            state.balance += state.current
            state.current = 0
        return state.board_confirmed

    scheduler._visit_clue_message_board = visit
    return scheduler, shop, state


def test_deficit_counts_priority_and_only_raw_qualified_ordinary_goods(
    on_demand_shopping,
):
    _, shop, state = on_demand_shopping
    config.conf.maa_mall_blacklist = "招聘许可,装置"
    save_values({"源岩": 4, "龙门币": 0.001, "装置": 100})
    state.balance = 50
    state.products += [
        product(2, "源岩", 80),  # 原始性价比恰好等于阈值，不计入。
        product(3, "龙门币", 100),
        product(4, "装置", 160),
        product(5, "未知材料", 100),
        product(6, "加急许可", 160),
        None,
    ]

    shop.run(on_demand=True)

    # 零估值且在黑名单中的优先商品仍计入，与糖合计 360；其他商品均排除。
    assert shop.credit_deficit == 310
    assert state.purchased == []


@pytest.mark.parametrize("balance,claims", [(150, []), (149, [False])])
def test_party_decision_uses_whole_target_deficit(on_demand_shopping, balance, claims):
    scheduler, shop, state = on_demand_shopping
    scheduler._party_time = state.now.replace(hour=22)
    state.balance = balance

    scheduler._run_clue_shop()

    assert state.visits == claims
    assert state.purchased == ([(0, 100), (1, 100)] if claims else [])
    assert state.balance == (89 if claims else 150)
    assert state.current == 300
    if not claims:
        assert shop.credit_deficit == 210


def test_normal_goods_also_use_total_not_first_item_shortage(on_demand_shopping):
    scheduler, _, state = on_demand_shopping
    config.conf.maa_mall_buy = ""
    scheduler._party_time = state.now.replace(hour=22)
    state.balance = 50
    state.products = [product(0, "糖", 200), product(1, "源岩", 80)]

    scheduler._run_clue_shop()

    # 首件只缺 150，但合计缺 230，不能等 210，须领取信用板。
    assert state.visits == [False]
    assert state.purchased == [(0, 100), (1, 100)]
    assert state.balance == 70


def test_claim_old_credit_then_wait_for_actual_party_income(on_demand_shopping):
    scheduler, shop, state = on_demand_shopping
    scheduler._party_time = state.now.replace(hour=22)
    state.previous = 150

    scheduler._run_clue_shop()

    assert state.visits == [False]
    assert state.balance == 150
    assert state.purchased == []
    assert state.current == 300
    assert shop.credit_deficit == 210

    state.now = state.now.replace(hour=22, minute=1)
    state.balance += 210
    scheduler._run_clue_shop()

    assert state.visits == [False]
    assert state.purchased == [(0, 100), (1, 100)]
    assert state.balance == 0
    assert state.current == 300


@pytest.mark.parametrize(
    "previous,current,claims",
    [(100, 300, [False, True]), (360, 300, [False]), (0, 0, [False, True])],
)
def test_board_phases_recheck_real_balance_and_are_bounded(
    on_demand_shopping, previous, current, claims
):
    scheduler, _, state = on_demand_shopping
    state.previous, state.current = previous, current

    scheduler._run_clue_shop()

    assert state.visits == claims
    assert state.purchased == ([(0, 100), (1, 100)] if previous + current else [])
    assert state.balance == (40 if previous == 100 else 0)


@pytest.mark.parametrize(
    "balance,remaining,purchases", [(100, 100, []), (390, 190, [(0, 100)])]
)
def test_overflow_only_goods_do_not_request_more_credit(
    on_demand_shopping, balance, remaining, purchases
):
    scheduler, _, state = on_demand_shopping
    config.conf.maa_mall_buy = ""
    config.conf.credit_shop_value_threshold = 0.15
    save_values({"糖": 10})
    state.balance = balance
    state.products = [product(0, "糖", 200)]

    scheduler._run_clue_shop()

    assert state.visits == []
    assert state.purchased == purchases
    assert state.balance == remaining


def test_blacklisted_zero_value_priority_can_request_board_credit(on_demand_shopping):
    scheduler, _, state = on_demand_shopping
    config.conf.maa_mall_blacklist = "招聘许可"
    config.conf.credit_shop_value_threshold = 100
    state.products = [product(0, "招聘许可", 160)]

    scheduler._run_clue_shop()

    assert state.visits == [False]
    assert state.purchased == [(0, 100)]
    assert state.balance == 140


def test_shop_daily_credit_is_spent_before_waiting_for_party(on_demand_shopping):
    scheduler, _, state = on_demand_shopping
    scheduler._party_time = state.now.replace(hour=22)
    state.daily = 160

    scheduler._run_clue_shop()

    assert state.purchased == [(0, 100)]
    assert state.balance == 0
    assert state.visits == []


@pytest.mark.parametrize(
    "end,claims",
    [
        ("2026-10-16T03:44:59+08:00", []),
        ("2026-10-16T03:45:00+08:00", [False]),
        ("2026-10-16T12:00:00+08:00", [False]),
        ("2026-10-15T11:00:00+08:00", [False]),
        (None, [False]),
    ],
)
def test_value_shopping_preserves_party_deadline(on_demand_shopping, end, claims):
    scheduler, _, state = on_demand_shopping
    scheduler._party_time = datetime.fromisoformat(end) if end else None
    state.balance = 150

    scheduler._run_clue_shop()

    assert state.visits == claims
    assert state.purchased == ([(0, 100), (1, 100)] if claims else [])


def test_on_demand_disabled_uses_only_actual_shop_balance(on_demand_shopping):
    scheduler, shop, state = on_demand_shopping
    config.conf.clue_credit_on_demand = False
    scheduler._party_time = state.now.replace(hour=22)
    state.balance = 120
    state.products = [product(0, "招聘许可", 160), product(1, "糖", 100, 50)]

    scheduler._run_clue_shop()

    assert state.balance == 120
    assert state.purchased == state.visits == []
    assert shop.credit_deficit is None


def test_value_disabled_keeps_all_nonblacklisted_goods_in_deficit(on_demand_shopping):
    scheduler, _, state = on_demand_shopping
    config.conf.credit_shop_by_value = False
    scheduler._party_time = state.now.replace(hour=22)
    state.balance = 50
    # 低于阈值的龙门币在旧购物流程中仍计入，总缺口 210。
    state.products = [product(0, "招聘许可", 160), product(1, "龙门币", 100)]
    save_values({"龙门币": 0.001})

    scheduler._run_clue_shop()

    assert state.visits == state.purchased == []


@pytest.mark.parametrize("corrected", [False, True])
def test_purchase_rejection_requires_confirmed_value_shortage(
    on_demand_shopping, corrected
):
    scheduler, shop, state = on_demand_shopping
    state.balance = 120
    state.products = [product(0, "招聘许可", 160)]
    readings = 0

    def balance():
        nonlocal readings
        readings += 1
        return state.balance if corrected and readings > 1 else 200

    shop.credit_remain = balance
    shop.find = lambda name: name == "shop_credit_not_enough" and state.balance < 160

    scheduler._run_clue_shop()

    assert state.visits == ([False] if corrected else [])
    assert state.purchased == ([(0, 100)] if corrected else [])
    assert readings <= 5


def test_unconfirmed_board_still_rechecks_cash_without_claiming_current(
    on_demand_shopping,
):
    scheduler, _, state = on_demand_shopping
    state.previous = 160
    state.board_confirmed = False

    scheduler._run_clue_shop()

    assert state.visits == [False]
    assert state.purchased == [(0, 100)]
    assert state.current == 300


def test_today_visit_still_required_before_value_shopping(on_demand_shopping):
    scheduler, shop, state = on_demand_shopping
    scheduler.daily_visit_friend_attempt = None

    scheduler._run_clue_shop()

    assert state.visits == state.purchased == []
    shop.tap.assert_not_called()


def test_stopping_mower_prevents_credit_actions(on_demand_shopping):
    scheduler, shop, state = on_demand_shopping
    config.stop_mower.set()

    with pytest.raises(MowerExit):
        scheduler._run_clue_shop()

    assert state.visits == []
    shop.tap.assert_not_called()
