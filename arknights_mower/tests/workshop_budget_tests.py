"""合成共用保守心情预算，批次之间不打开进驻详情。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.calculated_mood_tests import NOW, enable, sync_model
from arknights_mower.tests.calculated_mood_tests import solver as solver
from arknights_mower.tests.mass_mood_recovery_tests import base_schedule as base
from arknights_mower.utils import config, workshop_automation, workshop_mood
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scene import Scene


@pytest.mark.parametrize("card", [None, 5.9])
@pytest.mark.parametrize("calculated", [False, True])
def test_recipe_changes_share_budget_without_batch_room_readback(
    solver, monkeypatch, calculated, card
):
    data = enable(solver, monkeypatch)
    config.conf.test_mood_calculation = calculated
    config.conf.enable_mastery = False
    config.conf.workshop_auto_active = False
    setting = RIICPart.WorkShopSetting(
        operator="空爆",
        items=[
            WorkShopItem(
                item_names=[name], self_upper_limit=limit, children_lower_limit=0
            )
            for name, limit in [("糖组", 1), ("技巧概要·卷3", 3)]
        ],
    )
    config.conf.workshop_settings = [setting]
    data.add(
        Operator(
            "空爆", "", current_room="factory", current_index=0, mood=6, time_stamp=NOW
        )
    )
    data.mood_model.observe("空爆", 6, NOW - timedelta(microseconds=1))
    sync_model(data, NOW)
    if card is not None:
        data.dorm_mood_estimates["空爆"] = (card, datetime.now())
    snapshot = SimpleNamespace(settings=[setting], is_current=lambda: True)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_mood, "operator_mood_rules", lambda *a, **kw: ([], True)
    )
    stock = {"糖组": 0, "糖": 4, "技巧概要·卷3": 0, "技巧概要·卷2": 9}
    monkeypatch.setattr(base, "get_inventory_counts", lambda: dict(stock))
    deltas = []

    def apply(delta):
        deltas.append(delta)
        for name, count in delta.items():
            stock[name] = stock.get(name, 0) + count

    monkeypatch.setattr(base, "apply_workshop_inventory", apply)
    monkeypatch.setattr(base, "save_current_state", lambda: True)
    errors = MagicMock()
    monkeypatch.setattr(base, "save_exception", errors)
    solver.recog = MagicMock(w=1920, h=1080)
    solver.factory_scene = MagicMock(
        side_effect=[
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_FORMULA,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_PRODUCT_COLLECT,
            Scene.FACTORY_PRODUCT_COLLECT,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_FORMULA,
            Scene.FACTORY_DASHBOARD,
            Scene.FACTORY_PRODUCT_COLLECT,
        ]
    )
    for method in [
        "tap",
        "back",
        "back_to_infrastructure",
        "swipe_noinertia",
        "turn_on_room_detail",
        "get_agent_from_room",
    ]:
        setattr(solver, method, MagicMock())
    solver.find = lambda name: False
    solver.item_valid = lambda: True
    solver.item_list = MagicMock(
        side_effect=[
            [("糖组", ((10, 10), (20, 20)), True)],
            [("技巧概要·卷3", ((10, 10), (20, 20)), True)],
        ]
    )

    assert solver.generate_product("空爆", snapshot=snapshot) is not False

    errors.assert_not_called()
    assert stock == {
        "糖组": 1,
        "糖": 0,
        "技巧概要·卷3": 1 if card else 2,
        "技巧概要·卷2": 6 if card else 3,
        "龙门币": -200,
    }
    assert len(deltas) == 2
    solver.get_agent_from_room.assert_not_called()
    solver.turn_on_room_detail.assert_not_called()
    produce = (1920 * 0.88, 1080 * 0.88)
    assert sum(call.args[0] == produce for call in solver.tap.call_args_list) == 2
    if calculated:
        assert data.calculated_mood("空爆", NOW) == (1 if card else 0)
        assert data.operators["空爆"].mood == 6
        assert len(data.mood_model.events) == 2
        assert data.mood_model.pending_events == {}
    else:
        assert data.operators["空爆"].mood == (1 if card else 0)
        assert data.operators["空爆"].mood_is_prediction
