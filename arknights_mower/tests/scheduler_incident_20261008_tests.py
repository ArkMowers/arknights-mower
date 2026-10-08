"""Offline regressions for deferred exhausted shifts and scheduler idle waits."""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, operators, scheduler_task  # noqa: E402
from arknights_mower.utils.recognize import Recognizer, Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    scheduling,
)


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 8, 10, 34, 50)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    monkeypatch.setattr(config, "save_conf", MagicMock())
    monkeypatch.setattr(base, "refresh_resource_at_boundary", MagicMock())
    monkeypatch.setattr(base, "send_message", MagicMock())
    monkeypatch.setattr(base, "save_exception", MagicMock())
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    monkeypatch.setattr(base.logger, "info", MagicMock())
    monkeypatch.setattr(base.logger, "debug", MagicMock())
    monkeypatch.setattr(base.logger, "warning", MagicMock())
    return Clock


def repeated_exhaust(clock, monkeypatch, *, retain_deadline=False):
    name = "歌蕾蒂娅"
    operator = SimpleNamespace(
        name=name,
        room="central",
        current_room="central",
        current_index=0,
        group="",
        multi_group=False,
        workaholic=False,
        lower_limit=0,
        depletion_rate=0,
        current_mood=lambda: 0,
        is_resting=lambda: False,
        is_high=lambda: True,
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = SimpleNamespace(
        operators={name: operator},
        exhaust_agent=[name],
        rest_in_full_group=[],
        groups={},
        run_order_rooms={"room_2_1": []},
        refresh_run_order_rooms=lambda: None,
        active_high_resting_count=lambda: 0,
        print=lambda: "offline operator fixture",
    )
    for method in (
        "_emergency_frozen",
        "_emergency_active",
        "_refresh_deferred_product_reservations",
        "plan_run_order",
        "enter_room",
    ):
        setattr(solver, method, MagicMock(return_value=False))
    solver.find = MagicMock(return_value=True)
    solver.check_fia = MagicMock(return_value=(None, None))
    solver.get_agent_from_room = MagicMock(return_value=[{"time": None}])

    def back():
        clock.current += timedelta(seconds=1.1)

    solver.back = back
    arrangement = {"central": ["备用干员"], "dormitory_1": [name]}
    solver.get_resting_plan = lambda candidates, replacements, plan, count: plan.update(
        deepcopy(arrangement)
    )
    monkeypatch.setattr(base, "try_reorder", lambda data, plan: {})
    order = SchedulerTask(
        time=clock.now() + timedelta(minutes=2),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_2_1": ["但书"]},
        meta_data="room_2_1",
    )
    exhausted = SchedulerTask(
        time=clock.now(), task_type=TaskTypes.EXHAUST_OFF, meta_data=name
    )
    solver.tasks, solver.task = [exhausted, order], exhausted
    solver.infra_main()
    scheduling(solver.tasks, time_now=clock.now())
    if retain_deadline:
        solver.tasks.append(
            SchedulerTask(
                time=order.time + timedelta(seconds=1),
                task_type=TaskTypes.EXHAUST_OFF,
                meta_data=name,
            )
        )
    for _ in range(3):
        clock.current += timedelta(seconds=5)
        solver.run_order_solver()
        solver._plan_primary_recovery(scan_moods=False)
        pending = solver.find_next_task(task_type=TaskTypes.EXHAUST_OFF, meta_data=name)
        if pending is not None and pending.time <= clock.now():
            solver.task = pending
            solver.infra_main()
        scheduling(solver.tasks, time_now=clock.now())
    return [task for task in solver.tasks if task.type == TaskTypes.SHIFT_OFF]


def test_postponed_exhausted_shift_is_not_generated_again(clock, monkeypatch):
    pending = repeated_exhaust(clock, monkeypatch)
    assert len(pending) == 1, f"same operator has {len(pending)} postponed shifts"


def test_retained_exhausted_deadline_suppresses_duplicate_generation(
    clock, monkeypatch
):
    assert len(repeated_exhaust(clock, monkeypatch, retain_deadline=True)) == 1


def idle_recognizer(clock, monkeypatch, *, reset_after_idle=False):
    clock.current = datetime(2026, 10, 8, 10, 55, 38, 643000)
    config.conf.run_order_delay = 3
    config.conf.close_simulator_when_idle = False
    device = MagicMock()
    recog = Recognizer(device)
    recog.scene = recog.last_scene = Scene.INFRA_MAIN
    recog.last_scene_time = clock.now()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = recog

    def sleep(seconds):
        clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(base, "csleep", sleep)
    solver._idle_sleep(298.417708)
    assert not solver.sleeping
    assert clock.now() == datetime(2026, 10, 8, 11, 0, 37, 60708)
    if reset_after_idle:
        recog.reset_after_external_control()
    # The first fresh observation after the legitimate idle interval is unchanged.
    recog.scene = Scene.INFRA_MAIN
    recog.check_freeze(clock.now())
    return recog


def test_intentional_scheduler_sleep_does_not_trigger_game_exit(clock, monkeypatch):
    recog = idle_recognizer(clock, monkeypatch)
    recog.device.exit.assert_not_called()


def test_reset_at_idle_boundary_preserves_active_freeze_detection(clock, monkeypatch):
    recog = idle_recognizer(clock, monkeypatch, reset_after_idle=True)
    recog.device.exit.assert_not_called()
    recog.check_freeze(clock.now() + timedelta(seconds=271))
    recog.device.exit.assert_called_once()
