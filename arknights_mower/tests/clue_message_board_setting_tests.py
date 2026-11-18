"""信息板领取可单独关闭，线索、商店信用和购物仍沿用各自入口。"""

from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.clue_credit import ClueCreditMixin
from arknights_mower.tests.clue_credit_tests import shopping as shopping
from arknights_mower.tests.clue_gift_tests import clue_workflow as clue_workflow
from arknights_mower.tests.clue_gift_tests import gift_ui as gift_ui
from arknights_mower.tests.credit_shop_auto_dispatch_tests import (
    automatic_shop as automatic_shop,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf


def test_information_board_defaults_on_and_preserves_saved_false():
    conf = Conf()
    assert conf.clue_message_board_enable is True
    assert "clue_message_board_enable" not in conf.model_dump(exclude_unset=True)
    updated = conf.updated({"clue_message_board_enable": False})
    restored = Conf.model_validate_json(updated.model_dump_json(exclude_unset=True))
    assert restored.clue_message_board_enable is False
    assert restored.should_defer_clue_credit is False
    assert restored.should_use_credit_shop_value is True
    assert restored.updated({"enable_party": 0}).clue_message_board_enable is False
    assert restored.updated(
        {"clue_message_board_enable": True}
    ).should_defer_clue_credit


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("weekday", [2, 6])
def test_clue_workflow_skips_disabled_board_and_keeps_later_steps(
    clue_workflow, monkeypatch, enabled, weekday
):
    from arknights_mower.solvers import base_schedule

    solver, state = clue_workflow
    monkeypatch.setattr(config, "conf", Conf(clue_message_board_enable=enabled))
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: weekday)
    solver._clue_credit_enabled.return_value = enabled
    state.count = state.after_fast = 9

    solver.clue_new()

    solver._open_clue_message_board.assert_not_called()
    assert solver._collect_clue_message_board.call_count == int(
        enabled and weekday == 6
    )
    solver._run_clue_shop.assert_called_once()
    solver.read_party_time.assert_called_once()
    solver.backup_plan_solver.assert_called_once()
    assert state.sent == []


@pytest.mark.parametrize("visits", [False, True])
@pytest.mark.parametrize("daily_credit", [0, 160])
def test_disabled_information_board_keeps_real_automatic_shop(
    automatic_shop, visits, daily_credit
):
    solver, shop, state, clock = automatic_shop
    config.conf.clue_message_board_enable = False
    config.conf.visit_friend_enable = visits
    solver.daily_visit_friend_attempt = None
    state.daily = daily_credit
    state.previous = state.current = 300
    state.now = state.now.replace(day=14, hour=3, minute=50)
    solver.reload_time = clock.now()

    solver.infra_main()

    assert state.visits == []
    assert state.purchased == (["招聘许可"] if daily_credit else [])
    assert state.daily == 0
    assert state.previous == state.current == 300
    assert shop.run.call_count == 1
    assert solver.last_clue == clock.now()
    solver.clue_new.assert_not_called()
    solver.visit_friend_plan_solver.assert_not_called()


def test_disabling_board_blocks_new_claims_in_a_saved_on_demand_shop(automatic_shop):
    solver, shop, state, _ = automatic_shop
    config.conf.clue_message_board_enable = False
    state.daily = 0
    state.previous = state.current = 300

    solver._run_clue_shop(
        resume={"on_demand": True, "stage": 1, "settlement_checked": True}
    )

    shop.run.assert_called_once_with(on_demand=True)
    assert state.visits == []
    assert state.previous == state.current == 300


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("_open_clue_message_board", {}),
        ("_collect_clue_message_board", {"collect_current": True}),
        ("_visit_clue_message_board", {"collect_current": False}),
    ],
)
def test_disabled_board_helpers_never_enter_or_click(monkeypatch, method, kwargs):
    monkeypatch.setattr(config, "conf", Conf(clue_message_board_enable=False))
    solver = ClueCreditMixin()
    solver.recog = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    solver.enter_room = MagicMock()
    solver.tap = MagicMock()

    assert getattr(solver, method)(**kwargs) is False

    solver.recog.update.assert_not_called()
    solver.scene_graph_navigation.assert_not_called()
    solver.enter_room.assert_not_called()
    solver.tap.assert_not_called()
