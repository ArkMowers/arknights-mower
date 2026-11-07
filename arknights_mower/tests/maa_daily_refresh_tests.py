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
@pytest.mark.parametrize(
    "instant,allowed",
    [(datetime(2026, 11, 7, 3, 45), False), (datetime(2026, 11, 7, 4), True)],
)
def test_preparation_rechecks_current_window(run, kind, phase, instant, allowed):
    kwargs = configure(run, kind)

    def advance(*args):
        run.clock.current = instant
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
    assert run.solver.MAA.start.call_count == int(allowed)
    if not allowed:
        assert run.solver.last_execution["maa"] is None


@pytest.mark.parametrize("kind", ["daily", "long"])
@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize(
    "observed",
    [
        datetime(2026, 11, 7, 3, 45),
        datetime(2026, 11, 7, 3, 55),
        datetime(2026, 11, 7, 3, 59, 45),
        datetime(2026, 11, 7, 4, 0, 1),
    ],
)
def test_running_work_is_not_interrupted_by_refresh(
    run, monkeypatch, kind, manual, observed
):
    kwargs = configure(run, kind, manual=manual)
    running = iter([True, False])

    def tick():
        run.clock.current = observed
        return next(running)

    run.solver.MAA.running.side_effect = tick
    monkeypatch.setattr(run.module, "csleep", lambda _: None)
    assert run.solver.maa_plan_solver(**kwargs)
    run.solver.MAA.start.assert_called_once()
    run.solver.maa_stop.assert_not_called()
    if kind == "daily":
        assert run.solver.last_execution["maa"] == observed
    run.io.assert_not_called()


@pytest.mark.parametrize("kind", ["daily", "long", "single"])
def test_original_task_deadlines_still_interrupt_running_work(run, monkeypatch, kind):
    kwargs = configure(run, kind, manual=True)
    running = iter([True, False])

    def tick():
        run.clock.current = datetime(2026, 11, 7, 3, 55)
        return next(running)

    run.solver.tasks[-1].time = datetime(2026, 11, 7, 3, 55, 20)
    run.solver.MAA.running.side_effect = tick
    monkeypatch.setattr(run.module, "csleep", lambda _: None)
    run.solver.maa_plan_solver(**kwargs)
    run.solver.maa_stop.assert_called_once()
    assert run.solver.last_execution["maa"] is None


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
@pytest.mark.parametrize(
    "instant,allowed",
    [(datetime(2026, 11, 7, 3, 45), False), (datetime(2026, 11, 7, 4), True)],
)
def test_shop_preparation_rechecks_start_window(
    run, monkeypatch, phase, instant, allowed
):
    from arknights_mower.solvers.event_shop import EventShopNavigation
    from arknights_mower.utils import maa_event_shop
    from arknights_mower.utils.config import weekly_plan_loader

    run.module.config.conf.maa_event_shop.enable = True
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", MagicMock())
    monkeypatch.setattr(maa_event_shop, "weekly_plan_uses_activity", lambda *a: True)
    monkeypatch.setattr(maa_event_shop, "select_shop", lambda *a: {})
    monkeypatch.setattr(EventShopNavigation, "run", MagicMock(return_value=True))

    def advance(*args):
        run.clock.current = instant
        return 1

    target = {
        "navigation": EventShopNavigation.run,
        "initialize": run.solver.initialize_maa,
        "append": run.solver.MAA.append_task,
    }[phase]
    target.side_effect = advance
    run.solver.run_maa_event_shop(lambda: datetime(2026, 11, 7, 6))
    target.assert_called_once()
    assert run.solver.MAA.start.call_count == int(allowed)


@pytest.mark.parametrize("manual", [False, True])
@pytest.mark.parametrize("restore", [False, True])
def test_deferred_shop_resumes_saved_step_without_daily_gap(
    run, monkeypatch, income_db, manual, restore
):
    from arknights_mower.solvers import record
    from arknights_mower.solvers.event_shop import EventShopNavigation
    from arknights_mower.utils import maa_event_shop
    from arknights_mower.utils.config import weekly_plan_loader

    solver = run.solver
    run.module.config.conf.maa_event_shop.enable = True
    run.module.config.conf.maa_gap = 24
    monkeypatch.setattr(weekly_plan_loader, "get_weekly_plan_manager", MagicMock())
    monkeypatch.setattr(maa_event_shop, "weekly_plan_uses_activity", lambda *a: True)
    monkeypatch.setattr(maa_event_shop, "select_shop", lambda *a: {})
    monkeypatch.setattr(EventShopNavigation, "run", MagicMock(return_value=True))
    solver.skland_plan_solver = MagicMock(return_value=True)

    def daily_completed():
        run.clock.current = datetime(2026, 11, 7, 3, 45)
        return False

    solver.MAA.running.side_effect = daily_completed
    if manual:
        original = SchedulerTask(run.clock.now(), task_type=TaskTypes.DAILY)
        original.manual_steps = ["maa_daily", TaskTypes.SKLAND.display_value]
        solver.task = original
        solver.tasks.insert(0, original)
        assert manual_tasks.run_manual_task(solver, original) is False
    else:
        assert solver.maa_plan_solver() is False
        original = next(task for task in solver.tasks if task.type == TaskTypes.DAILY)
    original_time = original.time
    assert original.manual_steps[0] == "maa_event_shop"
    assert solver.last_execution["maa"] is None
    assert original.maa_refresh_until == datetime(2026, 11, 7, 4)
    daily_submissions = solver.append_maa_task.call_count

    if restore:
        assert record.save_state_to_db({"tasks": solver.tasks})
        solver.tasks = record.load_state()["tasks"]
        original = next(task for task in solver.tasks if task.type == TaskTypes.DAILY)
    for minute in (46, 50, 59):
        run.clock.current = datetime(2026, 11, 7, 3, minute)
        solver._resume_failed_tasks()
        assert original.execution_failure
        assert original.manual_steps[0] == "maa_event_shop"
    assert (
        len([task for task in solver.tasks if task.meta_data == "maa_daily_refresh"])
        == 1
    )

    run.clock.current = datetime(2026, 11, 7, 4)
    solver._resume_failed_tasks()
    solver.task = original
    solver.MAA.running.side_effect = None
    solver.last_execution["maa"] = datetime(2026, 11, 7, 3, 45)
    assert manual_tasks.run_manual_task(solver, original)
    solver.MAA.append_task.assert_called_once()
    assert solver.MAA.append_task.call_args.args[0] == "Custom"
    assert solver.append_maa_task.call_count == daily_submissions
    assert solver.MAA.start.call_count == 2
    assert solver.last_execution["maa"] == datetime(2026, 11, 7, 4)
    assert original.manual_steps == []
    assert original.time == original_time
    assert solver.skland_plan_solver.call_count == int(manual)
    run.io.assert_not_called()


@pytest.mark.parametrize("kind", ["daily", "long", "shop"])
def test_refresh_deferral_crossing_four_uses_original_refresh(run, monkeypatch, kind):
    from arknights_mower.utils.news_checker import NewsChecker

    solver = run.solver
    run.clock.current = datetime(2026, 11, 7, 3, 59, 59, 999999)
    configure(run, kind, manual=True)
    if kind in ("daily", "shop"):
        solver.task.type = TaskTypes.DAILY
        solver.task.manual_steps = ["maa_event_shop" if kind == "shop" else "maa_daily"]
    original = solver.task
    original_time = original.time
    calculate = NewsChecker.get_daily_reset

    def crossing(cls, now=None):
        refresh = calculate(now)
        run.clock.current = datetime(2026, 11, 7, 4)
        return refresh

    monkeypatch.setattr(NewsChecker, "get_daily_reset", classmethod(crossing))
    assert manual_tasks.run_manual_task(solver, original) is False
    assert not getattr(original, "execution_failure", None)
    assert all(task.time <= datetime(2026, 11, 7, 6) for task in solver.tasks)
    assert manual_tasks.run_manual_task(solver, original)
    assert solver.MAA.start.call_count == int(kind != "shop")
    assert original.manual_steps == []
    assert original.time == original_time


def test_refresh_releases_wait_recorded_while_clock_crosses_deadline(run, monkeypatch):
    solver = run.solver
    run.clock.current = datetime(2026, 11, 7, 3, 59, 59, 999999)
    configure(run, "daily", manual=True)
    original = solver.task
    original.type = TaskTypes.DAILY
    original.manual_steps = ["maa_daily"]
    snapshot = manual_tasks.manual_task_snapshot

    def crossing(scheduler, task):
        run.clock.current = datetime(2026, 11, 7, 4)
        return snapshot(scheduler, task)

    monkeypatch.setattr(manual_tasks, "manual_task_snapshot", crossing)
    assert manual_tasks.run_manual_task(solver, original) is False
    solver._resume_failed_tasks()
    assert not getattr(original, "execution_failure", None)
    assert manual_tasks.run_manual_task(solver, original)
    solver.MAA.start.assert_called_once()
    assert original.manual_steps == []
