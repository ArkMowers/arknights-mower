import sys
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.utils.config.conf import Conf  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask  # noqa: E402


@pytest.fixture
def solver(monkeypatch):
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.device = MagicMock()
    instance.recog = Recognizer(instance.device)
    instance.MAA = MagicMock()
    instance.MAA.get_version.return_value = "v6.17.3"
    instance.MAA.append_task.return_value = 1
    instance.MAA.running.return_value = False
    instance.tasks = [SchedulerTask(time=datetime.now() + timedelta(hours=1))]
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


@pytest.mark.parametrize("mode", ["daily", "single", "manual"])
def test_real_daily_queue_ends_with_theme_and_starts_once(solver, monkeypatch, mode):
    setup_plan(solver, monkeypatch)
    monkeypatch.setattr(
        solver,
        "append_maa_theme_task",
        base_schedule.BaseSchedulerSolver.append_maa_theme_task.__get__(solver),
    )
    monkeypatch.setattr(
        solver,
        "append_maa_task",
        base_schedule.BaseSchedulerSolver.append_maa_task.__get__(solver),
    )
    conf = base_schedule.config.conf
    conf.stage_plan_enable = False
    conf.maa_mall_enable = False
    conf.maa_credit_fight = False
    conf.visit_friend_enable = False
    conf.maa_mail = True
    solver._maa_daily_done = MagicMock(return_value=False)
    solver._remember_maa_daily_task = MagicMock()
    solver.find_next_task = MagicMock(return_value=solver.tasks[0])
    maa = solver.MAA
    order = MagicMock()
    order.attach_mock(maa.append_task, "append")
    order.attach_mock(maa.start, "start")
    assert (
        solver.maa_plan_solver(
            "All" if mode == "daily" else ["StartUp", "Award"],
            one_time=mode == "single",
            manual=mode == "manual",
        )
        is True
    )
    assert [entry.args[0] for entry in maa.append_task.call_args_list] == [
        "StartUp",
        "Award",
        "SwitchTheme",
    ]
    maa.start.assert_called_once()
    assert order.mock_calls[-2:] == [
        call.append("SwitchTheme", {"themes": ["夜间"]}),
        call.start(),
    ]


@pytest.mark.parametrize("version", ["v6.17.3", "6.17.4", "v6.18.0-beta.1"])
def test_supported_core_appends_without_starting_or_clearing_queue(solver, version):
    solver.MAA.get_version.return_value = version
    solver.append_maa_theme_task()
    assert solver.MAA.method_calls == [
        call.get_version(),
        call.append_task("SwitchTheme", {"themes": ["夜间"]}),
    ]


@pytest.mark.parametrize("version", ["v6.17.2", "v6.17.3-beta.1", "DEBUG VERSION", ""])
def test_old_or_unverifiable_core_skips_restore(solver, version):
    solver.MAA.get_version.return_value = version
    solver.append_maa_theme_task()
    solver.MAA.append_task.assert_not_called()
    solver.MAA.stop.assert_not_called()


@pytest.mark.parametrize("reason", ["disabled", "empty", "stopped", "mower_stopped"])
def test_skip_conditions_do_not_append_a_task(solver, reason):
    if reason == "disabled":
        base_schedule.config.conf.maa_restore_theme_enable = False
    elif reason == "empty":
        base_schedule.config.conf.maa_restore_theme = "  "
    elif reason == "stopped":
        base_schedule.config.stop_maa.set()
    else:
        base_schedule.config.stop_mower.set()
    solver.append_maa_theme_task()
    solver.MAA.append_task.assert_not_called()
    solver.MAA.start.assert_not_called()


@pytest.mark.parametrize("failure", ["append", "exception"])
def test_restore_submission_failure_keeps_daily_queue(solver, failure):
    if failure == "append":
        solver.MAA.append_task.return_value = 0
    else:
        solver.MAA.append_task.side_effect = RuntimeError("core error")
    solver.append_maa_theme_task()
    solver.MAA.stop.assert_not_called()
    solver.MAA.start.assert_not_called()


@pytest.mark.parametrize("reason", ["stop", "mower_stop", "schedule", "single_timeout"])
def test_daily_queue_with_theme_uses_existing_stop_boundary(
    solver, monkeypatch, reason
):
    setup_plan(solver, monkeypatch)
    solver.task = SchedulerTask(time=datetime.now())
    monkeypatch.setattr(
        solver,
        "append_maa_theme_task",
        base_schedule.BaseSchedulerSolver.append_maa_theme_task.__get__(solver),
    )
    maa = solver.MAA
    maa.running.side_effect = [True, True, False]
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
        elif reason == "mower_stop":
            base_schedule.config.stop_mower.set()
        elif reason == "schedule":
            solver.tasks[0].time = now
        else:
            now += timedelta(minutes=6)

    solver.sleep.side_effect = tick
    if reason == "mower_stop":
        with pytest.raises(MowerExit):
            solver.maa_plan_solver(manual=True)
    else:
        assert (
            solver.maa_plan_solver(manual=True, one_time=reason == "single_timeout")
            is False
        )
    maa.append_task.assert_called_once_with("SwitchTheme", {"themes": ["夜间"]})
    maa.start.assert_called_once()
    assert solver.maa_stop.call_count == (2 if reason == "mower_stop" else 1)
    assert solver.last_execution["maa"] is None
    assert solver.MAA is None


def setup_plan(solver, monkeypatch):
    solver.last_execution = {"maa": None}
    solver.credit_fight = 1
    solver.recog = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.TERMINAL_MAIN)
    for name in [
        "back_to_index",
        "scene_graph_navigation",
        "append_maa_task",
        "initialize_maa",
        "append_maa_theme_task",
        "rest_until_next_task",
        "sleep",
        "maa_stop",
    ]:
        monkeypatch.setattr(solver, name, MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())


@pytest.mark.parametrize("one_time", [False, True])
def test_daily_and_single_run_queue_theme_before_start(solver, monkeypatch, one_time):
    setup_plan(solver, monkeypatch)
    solver.find_next_task = MagicMock(return_value=solver.tasks[0])
    order = MagicMock()
    order.attach_mock(solver.append_maa_task, "append")
    order.attach_mock(solver.MAA.start, "start")
    order.attach_mock(solver.append_maa_theme_task, "restore")
    order.attach_mock(solver.rest_until_next_task, "idle")
    solver.maa_plan_solver(one_time=one_time)
    assert order.mock_calls == [
        call.append("StartUp"),
        call.append("Fight"),
        call.append("Mall"),
        call.append("Award"),
        call.restore(),
        call.start(),
        call.idle(),
    ]


@pytest.mark.parametrize("reason", ["not_due", "urgent", "error"])
def test_no_theme_queue_when_daily_run_is_skipped_or_initialization_fails(
    solver, monkeypatch, reason
):
    setup_plan(solver, monkeypatch)
    if reason == "not_due":
        solver.last_execution["maa"] = datetime.now()
    elif reason == "urgent":
        solver.MAA.running.side_effect = [True, False]
        solver.tasks[0].time = datetime.now() + timedelta(minutes=2)
    else:
        solver.initialize_maa.side_effect = RuntimeError("connection failed")
        solver._idle_sleep = MagicMock()
        monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    solver.maa_plan_solver()
    solver.append_maa_theme_task.assert_not_called()


@pytest.mark.parametrize("ended_early", [False, True])
def test_long_task_never_restores_theme_after_stop_or_core_completion(
    solver, monkeypatch, ended_early
):
    setup_plan(solver, monkeypatch)
    base_schedule.config.conf.maa_rg_enable = 1
    base_schedule.config.conf.maa_rg_theme = "BlackFlow"
    maa = solver.MAA
    maa.running.side_effect = [False] if ended_early else [True]
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
    order.attach_mock(solver.append_maa_theme_task, "restore")
    order.attach_mock(solver.rest_until_next_task, "idle")
    solver.maa_plan_solver([])
    assert order.mock_calls[0].args[0] == "Roguelike"
    assert order.mock_calls[1:] == (
        [call.idle()] if ended_early else [call.stop(), call.idle()]
    )
    solver.append_maa_theme_task.assert_not_called()


@pytest.mark.parametrize(
    "kind,executor", [("ra", "ReclamationAlgorithm"), ("sf", "SecretFront")]
)
def test_native_large_task_does_not_inherit_daily_theme_restore(
    solver, monkeypatch, kind, executor
):
    setup_plan(solver, monkeypatch)
    maa = solver.MAA
    solver.initialize_maa.side_effect = lambda: setattr(solver, "MAA", maa)
    native = MagicMock()
    monkeypatch.setattr(base_schedule, executor, MagicMock(return_value=native))
    solver.task = SchedulerTask(time=datetime.now())
    solver.maa_plan_solver([], manual=True, long_task=kind)
    native.run.assert_called_once()
    solver.append_maa_theme_task.assert_not_called()


def test_daily_theme_precedes_following_large_task_without_restore_after_it(
    solver, monkeypatch
):
    setup_plan(solver, monkeypatch)
    monkeypatch.setattr(
        solver,
        "append_maa_theme_task",
        base_schedule.BaseSchedulerSolver.append_maa_theme_task.__get__(solver),
    )
    base_schedule.config.conf.maa_rg_enable = 1
    base_schedule.config.conf.maa_rg_theme = "BlackFlow"
    maa = solver.MAA
    solver.initialize_maa.side_effect = lambda: setattr(solver, "MAA", maa)
    solver.maa_plan_solver()
    assert [entry.args[0] for entry in maa.append_task.call_args_list] == [
        "SwitchTheme",
        "Roguelike",
    ]
    assert maa.start.call_count == 2
