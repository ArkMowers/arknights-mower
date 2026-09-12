"""MAA 日常接黑流树海时，旧首页计时不能触发强制退出游戏。"""

import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402


@pytest.fixture
def recog(monkeypatch):
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(maa_rg_enable=1, maa_rg_theme="BlackFlow", run_order_delay=5),
    )
    return Recognizer(MagicMock())


def stale_home(recog):
    recog.scene = Scene.INDEX
    recog.last_scene = Scene.INDEX
    recog.last_scene_time = datetime.now() - timedelta(hours=1)


def test_external_control_resets_watchdog_and_cached_frame(recog):
    stale_home(recog)
    recog._screencap = b"old frame"
    recog.loading_time = 6
    recog.reset_after_external_control()
    assert recog.scene == Scene.UNDEFINED
    assert recog._screencap is None
    assert recog.loading_time == 0
    recog.scene = Scene.INDEX  # 接管时重新识别后仍然是首页。
    assert recog.get_scene() == Scene.INDEX
    recog.device.exit.assert_not_called()


def test_real_freeze_invalidates_old_scene_instead_of_reporting_home(recog):
    stale_home(recog)
    assert recog.get_scene() == Scene.UNDEFINED
    recog.device.exit.assert_called_once()


def test_watchdog_still_detects_a_new_freeze_after_handoff(recog):
    recog.reset_after_external_control()
    recog.scene = Scene.INDEX
    recog.get_scene()
    recog.check_freeze(datetime.now() + timedelta(minutes=10))
    recog.device.exit.assert_called_once()
    assert recog.scene == Scene.UNDEFINED


def test_regular_screenshot_updates_do_not_disable_watchdog(recog):
    stale_home(recog)
    recog.update()
    recog.scene = Scene.INDEX
    assert recog.get_scene() == Scene.UNDEFINED
    recog.device.exit.assert_called_once()


def test_handoff_respects_mower_stop(recog):
    base_schedule.config.stop_mower.set()
    with pytest.raises(MowerExit):
        recog.reset_after_external_control()


@pytest.mark.parametrize("daily", [True, False])
@pytest.mark.parametrize("long_result", ["schedule_stop", "ended"])
def test_blackflow_starts_without_closing_game_and_returns_fresh_state(
    recog, monkeypatch, daily, long_result
):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.recog = recog
    solver.device = recog.device
    solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=2))]
    solver.last_execution = {"maa": None if daily else datetime.now()}
    solver.credit_fight = 1
    maa = MagicMock()
    solver.MAA = maa
    monkeypatch.setattr(recog, "save_screencap", MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    solver.append_maa_task = MagicMock()
    solver.sleep = MagicMock()

    def initialize():
        solver.MAA = maa
        if daily and solver.initialize_maa.call_count == 2:
            assert recog.last_scene is None
        # 日常结束/MAA 连接准备耗时之后，旧首页计时已过期。
        stale_home(recog)

    solver.initialize_maa = MagicMock(side_effect=initialize)

    def home():
        # 对照日志：back_to_index 识别到首页，再执行 check_freeze。
        recog.scene = Scene.INDEX
        assert recog.get_scene() == Scene.INDEX
        solver.device.exit.assert_not_called()

    solver.back_to_index = MagicMock(side_effect=home)
    daily_results = [False] if daily else []
    if long_result == "schedule_stop":
        maa.running.side_effect = daily_results + [True]

        def tick(_):
            stale_home(recog)
            solver.tasks[0].time = datetime.now() + timedelta(seconds=20)

        monkeypatch.setattr(base_schedule, "csleep", tick)
    else:
        maa.running.side_effect = daily_results + [True, False]
        monkeypatch.setattr(base_schedule, "csleep", lambda _: stale_home(recog))

    def idle():
        assert recog.last_scene is None
        assert recog.scene == Scene.UNDEFINED

    solver.rest_until_next_task = MagicMock(side_effect=idle)
    solver.maa_plan_solver()
    solver.device.exit.assert_not_called()
    solver.rest_until_next_task.assert_called_once()
    maa.append_task.assert_called_once()
    kind, params = maa.append_task.call_args.args
    assert kind == "Roguelike"
    assert params["theme"] == "BlackFlow"
    assert params["mode"] == base_schedule.config.conf.rogue.mode
