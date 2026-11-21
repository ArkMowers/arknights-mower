"""关闭自动线索流程时，购物仍通过真实基建调度和购物循环执行。"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.clue_credit_tests import prepare_clue_dispatch, product
from arknights_mower.tests.clue_credit_tests import shopping as shopping
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def automatic_shop(shopping, monkeypatch):
    scheduler, shop, state = shopping
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            enable_party=0,
            maa_mall_mode="maa",
            visit_friend_mode="maa",
            maa_mall_enable=True,
            maa_mall_buy="招聘许可",
        ),
    )
    clock = prepare_clue_dispatch(scheduler, state, monkeypatch)
    scheduler.task = None
    scheduler.tasks = []
    scheduler.op_data = SimpleNamespace(run_order_rooms={})
    scheduler.planned = True
    scheduler.todo_task = False
    scheduler.collect_notification = True
    scheduler.enable_party = config.conf.enable_party == 1
    scheduler.last_clue = clock.now() - timedelta(hours=2)
    scheduler.drone_room = None
    scheduler.drone_time = None
    scheduler.reload_time = clock.now()
    scheduler.clue_new = MagicMock(side_effect=AssertionError("自动线索搜集已关闭"))
    shop.run = MagicMock(wraps=shop.run)
    state.daily = 160
    state.products = [product(price=160)]
    return scheduler, shop, state, clock


@pytest.mark.parametrize("shopping_enabled", [False, True])
@pytest.mark.parametrize("visits_enabled", [False, True])
def test_migrated_maa_shopping_runs_without_automatic_clues_or_pending_clue_tasks(
    automatic_shop, shopping_enabled, visits_enabled
):
    scheduler, shop, state, clock = automatic_shop
    config.conf.maa_mall_enable = shopping_enabled
    config.conf.visit_friend_enable = visits_enabled
    previous_check = scheduler.last_clue
    assert scheduler.tasks == []
    assert config.conf.maa_mall_mode == "mower"

    scheduler.infra_main()

    assert state.purchased == (["招聘许可"] if shopping_enabled else [])
    assert state.daily == (0 if shopping_enabled else 160)
    assert shop.run.call_count == int(shopping_enabled)
    assert scheduler.last_clue == (clock.now() if shopping_enabled else previous_check)
    assert scheduler.tasks == []
    assert config.conf.enable_party == 0
    assert scheduler.enable_party is False
    scheduler.clue_new.assert_not_called()
    scheduler.visit_friend_plan_solver.assert_not_called()

    scheduler.todo_task = False
    scheduler.infra_main()
    assert shop.run.call_count == int(shopping_enabled)


def test_shop_only_cycle_collects_board_credit_only_for_confirmed_shortage(
    automatic_shop,
):
    scheduler, shop, state, _ = automatic_shop
    state.daily = 0
    state.previous = 160

    scheduler.infra_main()

    assert state.visits == [False]
    assert state.purchased == ["招聘许可"]
    assert shop.run.call_count == 2
    assert state.current == 300
    scheduler.clue_new.assert_not_called()


def test_shop_only_admission_preserves_existing_task_gap(automatic_shop):
    scheduler, shop, state, clock = automatic_shop
    previous_check = scheduler.last_clue
    dependency = SchedulerTask(
        time=clock.now() + timedelta(minutes=2), task_type=TaskTypes.NOT_SPECIFIC
    )
    scheduler.tasks = [dependency]

    scheduler.infra_main()

    shop.run.assert_not_called()
    assert scheduler.last_clue == previous_check
    assert scheduler.tasks == [dependency]
    scheduler.tasks.clear()
    scheduler.todo_task = False
    scheduler.infra_main()
    assert state.purchased == ["招聘许可"]
    scheduler.clue_new.assert_not_called()


def test_shop_only_reset_exclusion_preserves_time_and_other_ready_work(automatic_shop):
    from arknights_mower.utils.datetime import get_server_time

    scheduler, shop, state, clock = automatic_shop
    previous_check = scheduler.last_clue
    state.now = state.now.replace(day=14, hour=3, minute=50)
    scheduler.drone_room = "room_1_1"
    scheduler.drone = MagicMock()
    scheduler.reload_time = None
    scheduler.reload = MagicMock()

    scheduler.infra_main()

    shop.run.assert_not_called()
    scheduler.clue_new.assert_not_called()
    assert scheduler.last_clue == previous_check
    scheduler.drone.assert_called_once_with("room_1_1")
    scheduler.reload.assert_called_once_with()
    state.now = state.now.replace(hour=4, minute=0)
    scheduler.daily_visit_friend_attempt = get_server_time().date()
    scheduler.todo_task = False
    scheduler.infra_main()
    assert state.purchased == ["招聘许可"]
    assert scheduler.last_clue == clock.now()
