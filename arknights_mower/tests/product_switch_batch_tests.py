"""批量切产物先读数、逐站完成，并为整批操作保留关键任务窗口。"""

import socket
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests


@pytest.fixture
def batch(monkeypatch, offline_maintenance):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule as base
    from arknights_mower.utils import config, scheduler_task

    def forbidden_io(*args, **kwargs):
        pytest.fail("离线切产物回归不得连接设备、外部服务或启动进程")

    monkeypatch.setattr(base.Device, "create", forbidden_io)
    monkeypatch.setattr(socket, "socket", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_io)
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))

    class Clock(datetime):
        current = datetime(2026, 10, 28, 12)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = SimpleNamespace()
    solver.tasks = []
    solver.task = None
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()
    solver._change_trade_product = MagicMock()
    return SimpleNamespace(
        base=base, scheduling=scheduler_task, config=config, clock=Clock, solver=solver
    )


def switches(ui, count=2):
    tasks = [
        ui.scheduling.SchedulerTask(
            task_type=ui.scheduling.TaskTypes.SWITCH_PRODUCT,
            meta_data=f"room_{index}_2,gold",
        )
        for index in range(1, count + 1)
    ]
    ui.solver.tasks = tasks[:]
    ui.solver.task = tasks[0]
    return tasks


def order(ui, seconds):
    task = ui.scheduling.SchedulerTask(
        time=ui.clock.now() + timedelta(seconds=seconds),
        task_type=ui.scheduling.TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    ui.solver.tasks.append(task)
    return task


def observe(ui, waits):
    events = []

    def survey(room, target):
        events.append(("survey", room))
        wait, rate = waits[room]
        return {
            "room": room,
            "facility": "manufacture",
            "current_product": "exp3",
            "target_product": target,
            "needs_switch": True,
            "drone_count": 2,
            "available_drones": 100,
            "current_remaining": 360 + wait,
            "total_seconds": 360 + wait,
            "wait_seconds": wait,
            "production_rate": rate,
            "observed_at": ui.clock.now(),
        }

    ui.solver._survey_manufacture_switch = MagicMock(side_effect=survey)
    ui.solver._execute_manufacture_acceleration = MagicMock(
        side_effect=lambda item: events.append(("accelerate", item["room"])) or 0
    )
    ui.solver._change_manufacture_product = MagicMock(
        side_effect=lambda item, **kwargs: events.append(("change", item["room"]))
    )
    return events


def test_surveys_all_then_finishes_smallest_remainder_station_first(batch):
    ui = batch
    tasks = switches(ui)
    events = observe(ui, {"room_1_2": (120, 4), "room_2_2": (60, 1)})
    ui.solver.switch_base_products(tasks)
    assert events == [
        ("survey", "room_1_2"),
        ("survey", "room_2_2"),
        ("accelerate", "room_2_2"),
        ("change", "room_2_2"),
        ("accelerate", "room_1_2"),
        ("change", "room_1_2"),
    ]
    assert ui.solver.tasks == []


@pytest.mark.parametrize("count, minutes", [(1, 3), (2, 5), (3, 7)])
def test_switch_budget_counts_complete_batch(batch, count, minutes):
    ui = batch
    tasks = switches(ui, count)
    deadline = order(ui, minutes * 60)
    ui.scheduling.protect_priority_tasks(ui.solver.tasks, time_now=ui.clock.now())
    assert ui.solver.tasks[0] is deadline
    assert all(task.time > deadline.time for task in tasks)


def test_two_stations_fit_five_minutes_plus_existing_margin(batch):
    ui = batch
    tasks = switches(ui)
    deadline = order(ui, 5 * 60 + 15)
    ui.scheduling.protect_priority_tasks(ui.solver.tasks, time_now=ui.clock.now())
    assert ui.solver.tasks == [*tasks, deadline]
    assert all(task.time == ui.clock.now() for task in tasks)


@pytest.mark.parametrize("dispatch", [False, True])
def test_runtime_rechecks_after_survey_before_any_acceleration(batch, dispatch):
    ui = batch
    tasks = switches(ui)
    deadline = order(ui, 6 * 60)
    events = observe(ui, {"room_1_2": (20, 1), "room_2_2": (30, 1)})
    survey = ui.solver._survey_manufacture_switch.side_effect

    def slow_survey(room, target):
        result = survey(room, target)
        ui.clock.current += timedelta(seconds=40)
        return result

    ui.solver._survey_manufacture_switch.side_effect = slow_survey
    original = [task.time for task in tasks]
    if dispatch:
        ui.solver.op_data = SimpleNamespace(operators={}, run_order_rooms={})
        ui.solver.find = MagicMock(return_value=(1, 1))
        ui.solver.skip = MagicMock()
        ui.solver.refresh_connecting = False
        ui.solver.infra_main()
        assert ui.solver.tasks == [deadline, *tasks]
        assert all(task.retains_execution for task in tasks)
        assert ui.solver._product_batch_active is False
    else:
        with pytest.raises(ui.base.ProductSwitchPriorityDeferred):
            ui.solver.switch_base_products(tasks)
        assert ui.solver.tasks == [*tasks, deadline]
    assert events == [("survey", "room_1_2"), ("survey", "room_2_2")]
    assert [task.time for task in tasks] == original


def test_known_shift_product_budget_is_added_to_staffing(batch):
    ui = batch
    task = ui.scheduling.SchedulerTask(
        task_type=ui.scheduling.TaskTypes.SHIFT_OFF,
        task_plan={"room_1_2": ["Lancet-2"]},
    )
    ordinary = ui.scheduling.estimate_task_duration(task)
    task.pending_product_targets = {"room_1_2": "gold", "room_2_2": "exp3"}
    assert ui.scheduling.estimate_task_duration(task) == ordinary + timedelta(minutes=5)


@pytest.mark.parametrize("buffer_seconds", [0, 2, 60])
def test_observed_long_wait_increases_budget_before_any_side_effect(
    batch, buffer_seconds
):
    ui = batch
    ui.config.conf.product_switching.waiting_seconds = buffer_seconds
    ui.config.conf.run_order_delay = 5
    tasks = switches(ui, 1)
    order(ui, 5 * 60)
    events = observe(ui, {"room_1_2": (120, 0.5)})
    with pytest.raises(ui.base.ProductSwitchPriorityDeferred):
        ui.solver.switch_base_products(tasks)
    assert events == [("survey", "room_1_2")]
    assert ui.scheduling.estimate_task_duration(tasks[0]) == timedelta(
        minutes=6, seconds=buffer_seconds
    )


def test_drone_shortage_releases_dispatch_without_page_wait(batch):
    ui = batch
    tasks = switches(ui, 1)
    shift = ui.scheduling.SchedulerTask(
        task_type=ui.scheduling.TaskTypes.SHIFT_OFF,
        task_plan={"room_1_2": ["Current"]},
    )
    ui.solver.task = shift
    ui.solver.tasks.append(shift)
    order(ui, 5 * 60)
    observe(ui, {"room_1_2": (60, 2)})
    survey = ui.solver._survey_manufacture_switch.side_effect

    def scarce_drones(room, target):
        result = survey(room, target)
        result.update(drone_count=8, available_drones=3, current_remaining=1500)
        return result

    ui.solver._survey_manufacture_switch.side_effect = scarce_drones
    ready_at = ui.clock.now() + timedelta(seconds=90)
    ui.solver._estimate_product_switch_ready_at = MagicMock(return_value=ready_at)
    with pytest.raises(ui.base.ProductSwitchDeferred) as deferred:
        ui.solver.switch_base_products(tasks, before_arrangement=True)
    assert deferred.value.ready_at == ready_at
    assert shift in ui.solver.tasks
    ui.solver.sleep.assert_not_called()
    ui.solver._execute_manufacture_acceleration.assert_not_called()
    ui.solver._change_manufacture_product.assert_not_called()


def test_retained_batch_keeps_original_times_and_resumes_after_priority(batch):
    ui = batch
    tasks = switches(ui)
    original = [task.time for task in tasks]
    for task in tasks:
        task.execution_retained = True
    deadline = order(ui, 4 * 60)
    other = ui.scheduling.SchedulerTask(time=ui.clock.now() - timedelta(minutes=1))
    ui.solver.tasks.insert(0, other)
    events = observe(ui, {"room_1_2": (20, 1), "room_2_2": (30, 1)})
    for seconds in (0, 30, 60):
        ui.clock.current = original[0] + timedelta(seconds=seconds)
        ui.scheduling.protect_priority_tasks(ui.solver.tasks, time_now=ui.clock.now())
        assert ui.solver.tasks == [other, deadline, *tasks]
        assert [task.time for task in tasks] == original
        assert events == []
    ui.solver.tasks.remove(other)
    ui.solver.tasks.remove(deadline)
    ui.clock.current = deadline.time + timedelta(minutes=3)
    ui.solver.switch_base_products(tasks)
    assert ui.solver.tasks == []
    assert [task.time for task in tasks] == original
    assert events[-1] == ("change", "room_2_2")


def test_future_and_failed_switches_do_not_join_due_batch(batch):
    ui = batch
    tasks = switches(ui, 3)
    tasks[1].time += timedelta(minutes=20)
    tasks[2].execution_failure = {"reason": "等待新观测"}
    deadline = order(ui, 4 * 60)
    ui.scheduling.protect_priority_tasks(ui.solver.tasks, time_now=ui.clock.now())
    assert ui.solver.tasks[0] is tasks[0]
    assert ui.solver.tasks.index(tasks[1]) > ui.solver.tasks.index(deadline)
    assert ui.solver.tasks[-1] is tasks[2]
