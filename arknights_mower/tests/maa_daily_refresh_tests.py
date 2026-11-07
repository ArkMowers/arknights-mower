import time
from datetime import datetime
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import manual_tasks
from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

scheduler = recovery.scheduler


@pytest.fixture
def run(scheduler, monkeypatch):
    with monkeypatch.context() as environment:
        environment.setenv("TZ", "Asia/Shanghai")
        time.tzset()
        module, solver, clock = scheduler.module, scheduler.solver, scheduler.clock
        clock.current = datetime(2026, 11, 7, 3, 44, 59)
        monkeypatch.setattr(manual_tasks, "datetime", clock)
        monkeypatch.setattr(
            module.config,
            "conf",
            Conf(
                stage_plan_enable=False,
                maa_credit_fight=False,
                maa_mall_enable=False,
                visit_friend_enable=False,
                maa_mail=True,
                maa_rg_sleep_min="00:00",
                maa_rg_sleep_max="00:00",
            ),
        )
        monkeypatch.setattr(module.config, "stop_maa", Event())
        monkeypatch.setattr(module, "send_message", MagicMock())
        monkeypatch.setattr(module, "save_exception", MagicMock())
        solver.MAA = MagicMock()
        solver.MAA.running.return_value = False
        solver.MAA.append_task.return_value = 1
        solver.last_execution = {"maa": None}
        solver.stages = []
        solver.tasks = [SchedulerTask(datetime(2026, 11, 7, 6))]
        for name in (
            "back_to_index",
            "initialize_maa",
            "release_maa",
            "append_maa_task",
            "append_maa_theme_task",
            "rest_until_next_task",
            "maa_stop",
            "sleep",
            "scene_graph_navigation",
        ):
            monkeypatch.setattr(solver, name, MagicMock())
        yield scheduler
    time.tzset()


def configure(run, kind, manual=False):
    solver, conf = run.solver, run.module.config.conf
    kwargs = {}
    if kind == "long":
        conf.maa_rg_enable = 1
        conf.maa_long_task_type = "rogue"
        conf.maa_rg_theme = "Sami"
        solver.scene.return_value = run.module.Scene.TERMINAL_MAIN
        kwargs.update(tasks=[], long_task="rogue")
    elif kind == "single":
        kwargs.update(tasks=["Award"], one_time=True)
    if manual:
        solver.task = SchedulerTask(
            run.clock.now(),
            task_type=TaskTypes.ROGUELIKE if kind == "long" else TaskTypes.STAGE_PLAN,
        )
        solver.tasks.insert(0, solver.task)
        kwargs["manual"] = True
    return kwargs


@pytest.mark.parametrize("kind", ["daily", "long", "single"])
@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize(
    "instant, allowed",
    [
        (datetime(2026, 11, 7, 3, 44, 59), True),
        (datetime(2026, 11, 7, 3, 45), False),
        (datetime(2026, 11, 7, 3, 59, 59), False),
        (datetime(2026, 11, 7, 4), True),
    ],
)
def test_refresh_start_window(run, kind, manual, instant, allowed):
    run.clock.current = instant
    kwargs = configure(run, kind, manual)
    run.solver.maa_plan_solver(**kwargs)
    assert run.solver.MAA.start.call_count == int(allowed)
    if not allowed:
        run.solver.initialize_maa.assert_not_called()
        run.solver.back_to_index.assert_not_called()
        assert run.solver.last_execution["maa"] is None
        assert [
            task.time
            for task in run.solver.tasks
            if task.meta_data == "maa_daily_refresh"
        ] == [datetime(2026, 11, 7, 4)]
    run.io.assert_not_called()


@pytest.mark.parametrize("kind", ["daily", "long", "single"])
@pytest.mark.parametrize("phase", ["initialize", "append"])
def test_preparation_crossing_window_does_not_start(run, kind, phase):
    kwargs = configure(run, kind)

    def advance(*args):
        run.clock.current = datetime(2026, 11, 7, 3, 45)
        return 1

    target = (
        run.solver.initialize_maa
        if phase == "initialize"
        else run.solver.MAA.append_task
        if kind == "long"
        else run.solver.append_maa_task
    )
    target.side_effect = advance
    run.solver.maa_plan_solver(**kwargs)
    run.solver.MAA.start.assert_not_called()
    assert run.solver.last_execution["maa"] is None


@pytest.mark.parametrize("kind", ["daily", "long"])
def test_running_work_stops_before_captured_refresh(run, monkeypatch, kind):
    kwargs = configure(run, kind, manual=True)
    stop_at = datetime(
        2026, 11, 7, 3, 55 if kind == "daily" else 59, 0 if kind == "daily" else 31
    )
    running = iter([True, False])

    def tick():
        run.clock.current = stop_at
        return next(running)

    run.solver.MAA.running.side_effect = tick
    monkeypatch.setattr(run.module, "csleep", lambda _: None)
    assert run.solver.maa_plan_solver(**kwargs) is False
    run.solver.MAA.start.assert_called_once()
    run.solver.maa_stop.assert_called_once()
    assert run.solver.last_execution["maa"] is None
    assert run.solver.task.maa_refresh_until == datetime(2026, 11, 7, 4)


def test_run_cannot_roll_deadline_forward_after_refresh(run, monkeypatch):
    kwargs = configure(run, "long", manual=True)
    run.solver.MAA.running.side_effect = lambda: True

    def tick(_):
        run.clock.current = datetime(2026, 11, 7, 4, 0, 1)

    monkeypatch.setattr(run.module, "csleep", tick)
    assert run.solver.maa_plan_solver(**kwargs) is False
    run.solver.maa_stop.assert_called_once()
    assert not any(task.meta_data == "maa_daily_refresh" for task in run.solver.tasks)


def test_window_uses_server_timezone(run, monkeypatch):
    with monkeypatch.context() as environment:
        environment.setenv("TZ", "UTC")
        time.tzset()
        run.clock.current = datetime(2026, 11, 6, 19, 45)
        run.solver.maa_plan_solver()
        run.solver.MAA.start.assert_not_called()
        assert any(
            task.meta_data == "maa_daily_refresh"
            and task.time == datetime(2026, 11, 6, 20)
            for task in run.solver.tasks
        )
    time.tzset()


def test_manual_interruption_observed_after_refresh_can_resume(run, monkeypatch):
    configure(run, "long", manual=True)
    solver = run.solver
    pending = solver.task
    solver.MAA.running.return_value = True

    def tick(_):
        run.clock.current = datetime(2026, 11, 7, 4, 0, 1)

    monkeypatch.setattr(run.module, "csleep", tick)
    assert manual_tasks.run_manual_task(solver, pending) is False
    assert not getattr(pending, "execution_failure", None)
    assert pending.manual_steps
    solver.MAA.running.return_value = False
    assert manual_tasks.run_manual_task(solver, pending)
    assert pending.manual_steps == []
    assert solver.MAA.start.call_count == 2


@pytest.mark.parametrize("restore", [False, True])
def test_retained_manual_work_releases_at_refresh_without_blocking_other_tasks(
    run, income_db, restore
):
    solver = run.solver
    run.clock.current = datetime(2026, 11, 7, 3, 45)
    configure(run, "daily", manual=True)
    original = solver.task
    original_time = original.time
    run.module.config.conf.stage_plan_runner = "maa"
    assert manual_tasks.run_manual_task(solver, original) is False
    if restore:
        from arknights_mower.solvers import record

        assert record.save_state_to_db({"tasks": solver.tasks})
        solver.tasks = record.load_state()["tasks"]
        original = next(
            task for task in solver.tasks if task.type == TaskTypes.STAGE_PLAN
        )
        solver.task = original
    snapshot = original.execution_failure["snapshot"]
    steps = list(original.manual_steps)
    unrelated = SchedulerTask(run.clock.now(), task_type=TaskTypes.SKLAND)
    solver.skland_plan_solver = MagicMock(return_value=True)
    solver.tasks.insert(0, unrelated)

    for minute in (46, 50, 59):
        run.clock.current = datetime(2026, 11, 7, 3, minute)
        solver._resume_failed_tasks()
        assert original.execution_failure["snapshot"] == snapshot
        assert original.manual_steps == steps
        assert solver.find_next_task() is unrelated
    solver.task = unrelated
    assert manual_tasks.run_manual_task(solver, unrelated)
    solver.skland_plan_solver.assert_called_once()
    solver.tasks.remove(unrelated)
    assert (
        len([task for task in solver.tasks if task.meta_data == "maa_daily_refresh"])
        == 1
    )

    run.clock.current = datetime(2026, 11, 7, 4)
    solver._resume_failed_tasks()
    assert not hasattr(original, "execution_failure")
    solver.task = original
    assert manual_tasks.run_manual_task(solver, original)
    solver.MAA.start.assert_called_once()
    assert original.manual_steps == []
    assert original.time == original_time
    run.io.assert_not_called()


def test_repeated_automatic_deferral_keeps_one_fixed_wakeup(run):
    for minute in (45, 46, 55, 59):
        run.clock.current = datetime(2026, 11, 7, 3, minute)
        assert run.solver.maa_plan_solver() is False
    wakeups = [
        task for task in run.solver.tasks if task.meta_data == "maa_daily_refresh"
    ]
    assert len(wakeups) == 1
    assert wakeups[0].time == datetime(2026, 11, 7, 4)
    run.solver.MAA.start.assert_not_called()


def test_shop_is_not_prepared_inside_window(run):
    run.clock.current = datetime(2026, 11, 7, 3, 45)
    run.solver.run_maa_event_shop(lambda: datetime(2026, 11, 7, 6))
    run.solver.initialize_maa.assert_not_called()
    run.solver.MAA.start.assert_not_called()


@pytest.mark.parametrize("phase", ["navigation", "initialize", "append"])
def test_shop_preparation_rechecks_start_window(run, monkeypatch, phase):
    from arknights_mower.solvers.event_shop import EventShopNavigation
    from arknights_mower.utils import maa_event_shop
    from arknights_mower.utils.config import weekly_plan_loader

    run.module.config.conf.maa_event_shop.enable = True
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", MagicMock())
    monkeypatch.setattr(maa_event_shop, "weekly_plan_uses_activity", lambda *a: True)
    monkeypatch.setattr(maa_event_shop, "select_shop", lambda *a: {})
    monkeypatch.setattr(EventShopNavigation, "run", MagicMock(return_value=True))

    def advance(*args):
        run.clock.current = datetime(2026, 11, 7, 3, 45)
        return 1

    target = {
        "navigation": EventShopNavigation.run,
        "initialize": run.solver.initialize_maa,
        "append": run.solver.MAA.append_task,
    }[phase]
    target.side_effect = advance
    run.solver.run_maa_event_shop(lambda: datetime(2026, 11, 7, 4))
    target.assert_called_once()
    run.solver.MAA.start.assert_not_called()
