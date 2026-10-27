"""MAA 日常接黑流树海时，旧首页计时不能触发强制退出游戏。"""

import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils import solver as solver_module  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402


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
@pytest.mark.parametrize("long_result", ["schedule_stop", "stop_requested", "ended"])
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
    logger = MagicMock()
    monkeypatch.setattr(base_schedule, "logger", logger)
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
    if long_result in {"schedule_stop", "stop_requested"}:
        maa.running.side_effect = daily_results + [True]

        def tick(_):
            stale_home(recog)
            if long_result == "schedule_stop":
                solver.tasks[0].time = datetime.now() + timedelta(seconds=20)
            else:
                base_schedule.config.stop_maa.set()

        monkeypatch.setattr(base_schedule, "csleep", tick)
    else:
        maa.running.side_effect = daily_results + [True, False]
        monkeypatch.setattr(base_schedule, "csleep", lambda _: stale_home(recog))

    def idle():
        assert recog.last_scene is None
        assert recog.scene == Scene.UNDEFINED

    solver.rest_until_next_task = MagicMock(side_effect=idle)
    solver.maa_plan_solver()
    logger.error.assert_not_called()
    logger.exception.assert_not_called()
    assert not any(
        call.kwargs.get("level") == "ERROR"
        for call in base_schedule.send_message.call_args_list
    )
    solver.device.exit.assert_not_called()
    solver.rest_until_next_task.assert_called_once()
    maa.append_task.assert_called_once()
    kind, params = maa.append_task.call_args.args
    assert kind == "Roguelike"
    assert params["theme"] == "BlackFlow"
    assert params["mode"] == base_schedule.config.conf.rogue.mode


@pytest.fixture
def daily_handoff(recog, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 27, 12)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(base_schedule.config, "conf", Conf())
    events = []
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.recog, solver.device = recog, recog.device
    solver.tasks = [SchedulerTask(Clock.now() + timedelta(minutes=6))]
    solver.last_execution = {"maa": None}
    solver.credit_fight = 1
    solver.task_count = 0
    engine = MagicMock()
    engine.running.side_effect = lambda: not engine.stop.called
    solver.MAA = engine

    def record(name):
        events.append((name, Clock.now()))

    def advance(seconds):
        record(("sleep", seconds))
        if base_schedule.config.stop_mower.is_set():
            raise MowerExit
        Clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(solver_module, "csleep", advance)
    engine.stop.side_effect = lambda: record("maa_stop")
    solver.device.exit.side_effect = lambda: record("exit")
    solver.device.check_current_focus.side_effect = lambda: record("launch") or True
    solver.device.return_home.side_effect = lambda: record("android_home")
    solver.back_to_index = MagicMock(side_effect=lambda: record("game_home"))
    solver.initialize_maa = MagicMock()
    solver.append_maa_task = MagicMock()
    solver.check_current_focus = MagicMock()
    for name in (
        "_refresh_workshop_inventory",
        "_refresh_observed_recovery_tasks",
        "_schedule_maintenance_backup_check",
        "_stop_after_round",
    ):
        setattr(solver, name, MagicMock())

    def idle(seconds, **kwargs):
        record(("idle", seconds))
        Clock.current += timedelta(seconds=seconds)

    solver._idle_sleep = MagicMock(side_effect=idle)
    monkeypatch.setattr(recog, "save_screencap", MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "task_template", MagicMock())
    monkeypatch.setattr(base_schedule, "protect_priority_tasks", MagicMock())
    logger = MagicMock()
    monkeypatch.setattr(base_schedule, "logger", logger)
    restart = MagicMock(side_effect=lambda **kwargs: record("close_simulator") or True)
    monkeypatch.setattr(base_schedule, "restart_simulator", restart)
    return SimpleNamespace(
        solver=solver, clock=Clock, events=events, engine=engine, logger=logger
    )


def configure_idle_action(action):
    conf = base_schedule.config.conf
    conf.return_home_when_idle = action == "home"
    conf.exit_game_when_idle = action == "exit"
    conf.close_simulator_when_idle = action == "close"


@pytest.mark.parametrize("action", ["idle", "home", "exit", "close"])
@pytest.mark.parametrize("remaining", [115, 300, 301])
def test_daily_stop_waits_before_following_actual_idle_action(
    daily_handoff, action, remaining
):
    solver, clock = daily_handoff.solver, daily_handoff.clock
    configure_idle_action(action)
    one_time = remaining != 115
    start = clock.now()
    stop_at = start + timedelta(seconds=305 if one_time else 65)
    expected_deadline = stop_at + timedelta(seconds=180 + remaining)
    solver.tasks[0].time = expected_deadline
    pending = solver.tasks[0]

    assert solver.maa_plan_solver(tasks=["Fight"], one_time=one_time)

    events = daily_handoff.events
    assert ("maa_stop", stop_at) in events
    assert (("sleep", 180), stop_at) in events
    handoff = stop_at + timedelta(seconds=180)
    assert (("idle", remaining), handoff) in events
    if action == "close" and remaining > 300:
        assert ("close_simulator", handoff) in events
        solver.device.exit.assert_not_called()
        solver.device.check_current_focus.assert_not_called()
        solver.back_to_index.assert_called_once()
    elif action == "exit" and remaining > 300:
        assert ("exit", handoff) in events
        solver.device.exit.assert_called_once()
        solver.device.check_current_focus.assert_not_called()
        solver.back_to_index.assert_called_once()
    else:
        assert events.count(("exit", handoff)) == 1
        assert events.index(("exit", handoff)) < events.index(("launch", handoff))
        assert events.index(("launch", handoff)) < events.index(("game_home", handoff))
        assert solver.back_to_index.call_count == 2
    if action == "home":
        assert events.index(("game_home", handoff)) < events.index(
            ("android_home", handoff)
        )
    else:
        solver.device.return_home.assert_not_called()
    assert solver.tasks == [pending]
    assert pending.time == expected_deadline
    assert solver.last_execution["maa"] is None
    assert clock.now() == expected_deadline
    daily_handoff.engine.close.assert_called_once()
    daily_handoff.logger.exception.assert_not_called()


def test_mower_stop_during_daily_grace_wait_does_not_restart_game(
    daily_handoff, monkeypatch
):
    solver = daily_handoff.solver

    def stop_during_wait(seconds):
        if seconds == 180:
            base_schedule.config.stop_mower.set()
            raise MowerExit
        daily_handoff.clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(solver_module, "csleep", stop_during_wait)
    with pytest.raises(MowerExit):
        solver.maa_plan_solver(tasks=["Fight"])
    solver.device.exit.assert_not_called()
    solver.device.check_current_focus.assert_not_called()
    solver.back_to_index.assert_called_once()
    solver._idle_sleep.assert_not_called()
    daily_handoff.engine.close.assert_called_once()
