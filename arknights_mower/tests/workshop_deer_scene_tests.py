"""九色鹿因果读取与加工页面变化共用同一帧证据。"""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests.workshop_deer_cycle_tests import deer as deer
from arknights_mower.tests.workshop_deer_cycle_tests import game as game
from arknights_mower.tests.workshop_deer_cycle_tests import inventory as inventory
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import WorkShopItem
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.image import loadimg


@pytest.fixture
def deer_scene(deer):
    solver, state, base, _, _ = deer
    config.conf.workshop_auto_active = False
    config.conf.workshop_settings[0].items = [
        WorkShopItem(
            item_names=["固源岩组"], children_lower_limit=0, self_upper_limit=1
        )
    ]
    root = Path(__file__).parent / "fixtures" / "workshop"
    dashboard = loadimg(str(root / "deer_dashboard_20261103.jpg"), True)
    formula = loadimg(str(root / "deer_formula_transition_20261103.jpg"), True)
    solver.recog.gray = dashboard
    reader = DigitReader()
    solver.digit_reader = MagicMock(wraps=reader)
    return solver, state, base, dashboard, formula


def test_delayed_formula_open_does_not_reread_counter_or_repeat_click(deer_scene):
    solver, state, base, dashboard, formula = deer_scene
    original_tap = solver.tap
    state.open_pending = False
    state.pending_frames = 0
    opened = []
    open_point = (864, 702)

    def tap(point, **kwargs):
        if point == open_point:
            opened.append(point)
            state.open_pending = True
            return
        original_tap(point, **kwargs)

    def update():
        if state.open_pending:
            state.pending_frames += 1
            if state.pending_frames >= 2:
                state.open_pending = False
                state.scene = base.Scene.FACTORY_FORMULA
        solver.recog.gray = (
            formula if state.scene == base.Scene.FACTORY_FORMULA else dashboard
        )

    solver.tap = tap
    solver.recog.update.side_effect = update

    solver.generate_product("九色鹿")

    base.save_exception.assert_not_called()
    assert state.crafts == [("固源岩组", 1)]
    assert opened == [open_point]
    assert all(
        call.args[0] is dashboard
        for call in solver.digit_reader.get_deer_causality.call_args_list
    )


def test_unreadable_counter_keeps_three_observation_bound(deer_scene, caplog):
    solver, state, base, _, _ = deer_scene
    solver.recog.gray = np.zeros((1080, 1920), dtype=np.uint8)

    solver.generate_product("九色鹿")

    base.save_exception.assert_not_called()
    assert state.crafts == []
    assert solver.digit_reader.get_deer_causality.call_count == 3
    assert solver.sleep.call_count == 2
    assert "九色鹿因果数字模板匹配失败" in caplog.text


def test_counter_retry_returns_changed_page_to_workflow(deer_scene, caplog):
    solver, state, base, dashboard, formula = deer_scene
    unreadable = np.zeros((1080, 1920), dtype=np.uint8)
    solver.recog.gray = unreadable
    state.redirect = True

    def update():
        if state.redirect:
            state.redirect = False
            state.scene = base.Scene.FACTORY_FORMULA
        solver.recog.gray = (
            formula if state.scene == base.Scene.FACTORY_FORMULA else dashboard
        )

    solver.recog.update.side_effect = update

    solver.generate_product("九色鹿")

    base.save_exception.assert_not_called()
    assert state.crafts == [("固源岩组", 1)]
    readings = solver.digit_reader.get_deer_causality.call_args_list
    assert readings[0].args[0] is unreadable
    assert all(call.args[0] is dashboard for call in readings[1:])
    assert "九色鹿因果数字模板匹配失败" not in caplog.text


@pytest.mark.parametrize("failure", ["cancel", "deadline"])
def test_formula_open_preserves_cancellation_and_existing_budget(
    deer_scene, monkeypatch, failure
):
    solver, state, base, _, _ = deer_scene
    original_tap = solver.tap
    opened = []

    def tap(point, **kwargs):
        if point == (864, 702):
            opened.append(point)
            return
        original_tap(point, **kwargs)

    solver.tap = tap
    if failure == "cancel":

        def update():
            if opened:
                raise base.MowerExit

        solver.recog.update.side_effect = update
        with pytest.raises(base.MowerExit):
            solver.generate_product("九色鹿")
        base.save_exception.assert_not_called()
    else:
        now = base.datetime.now()
        times = iter([now, now, now, now + timedelta(minutes=6)])
        monkeypatch.setattr(base, "datetime", SimpleNamespace(now=lambda: next(times)))

        assert solver.generate_product("九色鹿") is False

        base.save_exception.assert_called_once()
        assert "循环运行时间超过 5 分钟" in str(base.save_exception.call_args.args[0])
    assert opened == [(864, 702)]
    assert state.crafts == []


@pytest.mark.parametrize("recovery_scene", ["FACTORY_ROOM", "INFRA_MAIN", "UNKNOWN"])
def test_navigation_recovery_can_open_formula_again(deer_scene, recovery_scene):
    solver, state, base, dashboard, formula = deer_scene
    original_tap = solver.tap
    opened = []
    state.left_dashboard = False

    def enter(*args, **kwargs):
        state.left_dashboard = False
        state.scene = base.Scene.FACTORY_DASHBOARD

    def tap(point, *args, **kwargs):
        if point == (864, 702):
            opened.append(point)
            if len(opened) == 1:
                state.left_dashboard = True
                return
        elif point == (192, 1026):
            enter()
            return
        original_tap(point, **kwargs)

    def update():
        if state.left_dashboard:
            state.scene = getattr(base.Scene, recovery_scene)
        solver.recog.gray = (
            formula if state.scene == base.Scene.FACTORY_FORMULA else dashboard
        )

    solver.tap = tap
    solver.enter_room.side_effect = enter
    solver.recog.update.side_effect = update

    solver.generate_product("九色鹿")

    base.save_exception.assert_not_called()
    assert state.crafts == [("固源岩组", 1)]
    assert opened == [(864, 702), (864, 702)]


@pytest.mark.parametrize("cancel_on", ["read", "refresh"])
def test_counter_observation_propagates_cancellation(deer_scene, cancel_on):
    solver, state, base, _, _ = deer_scene
    if cancel_on == "read":
        solver.digit_reader.get_deer_causality.side_effect = base.MowerExit
    else:
        solver.digit_reader.get_deer_causality.return_value = None
        solver.recog.update.side_effect = base.MowerExit

    with pytest.raises(base.MowerExit):
        solver.generate_product("九色鹿")

    assert state.crafts == []
    base.save_exception.assert_not_called()
