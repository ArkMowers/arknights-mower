import sys
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.device = MagicMock()
    instance.recog = Recognizer(instance.device)
    instance.MAA = MagicMock()
    instance.MAA.get_version.return_value = "v6.17.3"
    instance.MAA.append_task.return_value = 1
    instance.MAA.running.return_value = False
    instance.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=1))]
    monkeypatch.setattr(
        base_schedule.config,
        "conf",
        Conf(maa_restore_theme_enable=True, maa_restore_theme=" 夜间 "),
    )
    monkeypatch.setattr(base_schedule.config, "stop_maa", threading.Event())
    monkeypatch.setattr(base_schedule.config, "stop_mower", threading.Event())
    return instance


def test_config_defaults_and_roundtrip():
    defaults = Conf()
    assert defaults.maa_restore_theme_enable is False
    assert defaults.maa_restore_theme == ""
    restored = Conf(
        **Conf(maa_restore_theme_enable=True, maa_restore_theme="夜间").model_dump()
    )
    assert restored.maa_restore_theme_enable is True
    assert restored.maa_restore_theme == "夜间"


@pytest.mark.parametrize("version", ["v6.17.3", "6.17.4", "v6.18.0-beta.1"])
def test_supported_core_clears_queue_and_restores_one_theme(solver, version):
    solver.MAA.get_version.return_value = version
    solver.recog.scene = solver.recog.last_scene = Scene.INDEX
    solver.recog.last_scene_time = datetime.now() - timedelta(hours=1)
    solver.restore_maa_theme()
    assert solver.MAA.method_calls == [
        call.get_version(),
        call.stop(),
        call.append_task("SwitchTheme", {"themes": ["夜间"]}),
        call.start(),
        call.running(),
        call.stop(),
    ]
    assert solver.recog.last_scene is None
    solver.recog.scene = Scene.INDEX
    assert solver.recog.get_scene() == Scene.INDEX
    solver.device.exit.assert_not_called()


@pytest.mark.parametrize("version", ["v6.17.2", "v6.17.3-beta.1", "DEBUG VERSION", ""])
def test_old_or_unverifiable_core_skips_restore(solver, version):
    solver.MAA.get_version.return_value = version
    solver.restore_maa_theme()
    solver.MAA.append_task.assert_not_called()
    solver.MAA.stop.assert_not_called()


@pytest.mark.parametrize(
    "reason", ["disabled", "empty", "stopped", "mower_stopped", "urgent"]
)
def test_skip_conditions_do_not_start_a_task(solver, reason):
    if reason == "disabled":
        base_schedule.config.conf.maa_restore_theme_enable = False
    elif reason == "empty":
        base_schedule.config.conf.maa_restore_theme = "  "
    elif reason == "stopped":
        base_schedule.config.stop_maa.set()
    elif reason == "mower_stopped":
        base_schedule.config.stop_mower.set()
    else:
        solver.tasks[0].time = datetime.now() + timedelta(seconds=8)
    solver.restore_maa_theme()
    solver.MAA.append_task.assert_not_called()
    solver.MAA.start.assert_not_called()


@pytest.mark.parametrize("failure", ["append", "start", "exception"])
def test_restore_failure_is_contained(solver, failure):
    if failure == "append":
        solver.MAA.append_task.return_value = 0
    elif failure == "start":
        solver.MAA.start.return_value = False
    else:
        solver.MAA.running.side_effect = RuntimeError("core error")
    solver.restore_maa_theme()
    assert solver.MAA.stop.call_count == (1 if failure == "append" else 2)


@pytest.mark.parametrize("reason", ["stop", "schedule", "timeout", "exit"])
def test_restore_can_be_interrupted(solver, monkeypatch, reason):
    solver.MAA.running.return_value = True
    now = datetime.now()

    class Clock:
        @staticmethod
        def now():
            return now

    monkeypatch.setattr(base_schedule, "datetime", Clock)

    def tick(_):
        nonlocal now
        if reason == "stop":
            base_schedule.config.stop_maa.set()
        elif reason == "schedule":
            solver.tasks[0].time = now
        elif reason == "timeout":
            now += timedelta(seconds=121)
        else:
            raise MowerExit

    monkeypatch.setattr(base_schedule, "csleep", tick)
    if reason == "exit":
        with pytest.raises(MowerExit):
            solver.restore_maa_theme()
    else:
        solver.restore_maa_theme()
    assert solver.MAA.stop.call_count == 2
    assert solver.recog.last_scene is None


def setup_plan(solver, monkeypatch):
    solver.last_execution = {"maa": None}
    solver.credit_fight = 1
    solver.recog = MagicMock()
    for name in [
        "back_to_index",
        "append_maa_task",
        "initialize_maa",
        "restore_maa_theme",
        "rest_until_next_task",
        "sleep",
        "maa_stop",
    ]:
        monkeypatch.setattr(solver, name, MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())


@pytest.mark.parametrize("one_time", [False, True])
def test_daily_and_single_run_restore_after_work_before_idle(
    solver, monkeypatch, one_time
):
    setup_plan(solver, monkeypatch)
    solver.find_next_task = MagicMock(return_value=solver.tasks[0])
    order = MagicMock()
    order.attach_mock(solver.append_maa_task, "append")
    order.attach_mock(solver.MAA.start, "start")
    order.attach_mock(solver.restore_maa_theme, "restore")
    order.attach_mock(solver.rest_until_next_task, "idle")
    solver.maa_plan_solver(one_time=one_time)
    assert order.mock_calls == [
        call.append("StartUp"),
        call.append("Fight"),
        call.append("Mall"),
        call.append("Award"),
        call.start(),
        call.restore(),
        call.idle(),
    ]


@pytest.mark.parametrize("reason", ["not_due", "hard_stop", "error"])
def test_no_restore_without_completed_daily_work(solver, monkeypatch, reason):
    setup_plan(solver, monkeypatch)
    if reason == "not_due":
        solver.last_execution["maa"] = datetime.now()
    elif reason == "hard_stop":
        solver.MAA.running.side_effect = [True, False]
        solver.tasks[0].time = datetime.now() + timedelta(minutes=2)
    else:
        solver.initialize_maa.side_effect = RuntimeError("connection failed")
        solver._idle_sleep = MagicMock()
        monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    solver.maa_plan_solver()
    solver.restore_maa_theme.assert_not_called()


@pytest.mark.parametrize("ended_early", [False, True])
def test_long_task_restores_after_scheduled_stop_but_not_error(
    solver, monkeypatch, ended_early
):
    setup_plan(solver, monkeypatch)
    base_schedule.config.conf.maa_rg_enable = 1
    base_schedule.config.conf.maa_rg_theme = "BlackFlow"
    maa = solver.MAA
    maa.running.side_effect = [False, False] if ended_early else [False, True]
    solver.initialize_maa.side_effect = lambda: setattr(solver, "MAA", maa)
    monkeypatch.setattr(
        base_schedule,
        "csleep",
        lambda _: setattr(
            solver.tasks[0], "time", datetime.now() + timedelta(seconds=25)
        ),
    )
    order = MagicMock()
    order.attach_mock(maa.append_task, "append")
    order.attach_mock(solver.maa_stop, "stop")
    order.attach_mock(solver.restore_maa_theme, "restore")
    order.attach_mock(solver.rest_until_next_task, "idle")
    solver.maa_plan_solver()
    assert order.mock_calls[0].args[0] == "Roguelike"
    assert order.mock_calls[1:] == (
        [call.idle()] if ended_early else [call.stop(), call.restore(), call.idle()]
    )
