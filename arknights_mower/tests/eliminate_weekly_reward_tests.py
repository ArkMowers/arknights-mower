from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import pytest

from arknights_mower.solvers import operation
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene

FIXTURE = Path(__file__).parent / "fixtures" / "eliminate"
REWARD_SCOPE = ((163, 980), (315, 1031))


def observation():
    return Recognizer(
        SimpleNamespace(check_current_focus=lambda: False),
        (FIXTURE / "eliminate_weekly_reward_full.webp").read_bytes(),
    )


def eliminate_solver(recog):
    solver = object.__new__(operation.OperationSolver)
    solver.recog = recog
    solver.stage_id = "annihilation"
    solver.current_batch_repeat_count = 1
    solver.sanity_drain = False
    solver.annihilation_reward_full = False
    solver.annihilation_agency_locked = False
    solver.tap = MagicMock()
    solver.tap_element = MagicMock()
    solver._finish_batch = MagicMock()
    solver._mark_battle_started = MagicMock()
    return solver


def test_weekly_reward_is_read_on_annihilation_page():
    recog = observation()

    assert recog.get_scene() == Scene.OPERATOR_ELIMINATE
    assert recog.find("ope_agency_lock") is None
    assert recog.find("1800") == REWARD_SCOPE
    assert eliminate_solver(recog).number(REWARD_SCOPE, 43) == 1800


def test_full_weekly_reward_stops_annihilation_without_tapping():
    solver = eliminate_solver(observation())

    assert solver.transition() is True

    assert solver.annihilation_reward_full is True
    assert solver.sanity_drain is False
    solver._finish_batch.assert_called_once_with(False)
    solver.tap.assert_not_called()
    solver.tap_element.assert_not_called()


def lock_proxy_command(solver):
    # 没有代理指挥锁定时的截图：只替换锁图标的匹配结果，其余仍按真实画面识别。
    real_find = solver.find

    def find(res, *args, **kwargs):
        if res == "ope_agency_lock":
            return ((1565, 856), (1632, 923))
        return real_find(res, *args, **kwargs)

    solver.find = find


def test_locked_proxy_command_skips_annihilation_without_tapping():
    solver = eliminate_solver(observation())
    lock_proxy_command(solver)

    assert solver.transition() is True

    assert solver.annihilation_agency_locked is True
    assert solver.annihilation_reward_full is False
    assert solver.sanity_drain is False
    solver._finish_batch.assert_called_once_with(False)
    solver.tap.assert_not_called()
    solver.tap_element.assert_not_called()


@pytest.mark.parametrize("locked", [False, True])
def test_annihilation_skip_reaches_operation_result(monkeypatch, locked):
    solver = eliminate_solver(observation())
    if locked:
        lock_proxy_command(solver)
    del solver._finish_batch, solver._mark_battle_started
    solver._inventory_limit_reached = lambda: False
    monkeypatch.setattr(operation, "battle_inventory_active", Event())
    monkeypatch.setattr(
        operation.SceneGraphSolver, "run", lambda self: self.transition()
    )

    result = solver.run(
        next_task_time=datetime.now() + timedelta(hours=1),
        stage_id="Annihilation",
        target_total_runs=2,
        simulated_current_ap=120,
        ap_cost=25,
        stage_duration_seconds=60,
    )

    assert result["annihilation_reward_full"] is not locked
    assert result["annihilation_agency_locked"] is locked
    assert result["sanity_drain"] is False
    assert result["executed_runs"] == 0
    assert result["simulated_current_ap"] == 120
    solver.tap.assert_not_called()
    solver.tap_element.assert_not_called()


def test_template_match_without_full_reading_keeps_annihilation_running():
    solver = eliminate_solver(observation())
    # 没有模板命中但读数不足 1800 的实机画面，这里保留真实模板命中，只替换读数。
    solver.number = MagicMock(return_value=1600)

    solver.transition()

    solver.number.assert_called_once_with(REWARD_SCOPE, 43)
    assert solver.annihilation_reward_full is False
    assert solver.sanity_drain is False
    solver._finish_batch.assert_not_called()
    solver.tap_element.assert_called_once_with("ope_start", interval=2)


def test_one_digit_difference_fails_template_check():
    recog = observation()
    # 把第二位的 8 换成第三位的 0，构造只差一位的“1000/1800”。
    recog.img[980:1031, 190:227] = recog.img[980:1031, 230:267].copy()
    recog._gray = cv2.cvtColor(recog.img, cv2.COLOR_RGB2GRAY)
    solver = eliminate_solver(recog)

    assert recog.find("1800") is None
    assert solver.number(REWARD_SCOPE, 43) == 1000

    solver.transition()

    assert solver.annihilation_reward_full is False
    assert solver.sanity_drain is False
    solver._finish_batch.assert_not_called()
    solver.tap_element.assert_called_once_with("ope_start", interval=2)
