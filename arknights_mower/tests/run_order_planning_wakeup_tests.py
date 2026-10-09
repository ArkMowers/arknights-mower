"""[INV-SCHED-04] Final shift completion resumes normal trade-order planning."""

import copy
import socket
import subprocess
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import pytest
import requests

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import record
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def replay(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 9, 15, 46, 57)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base, "save_log", MagicMock())
    monkeypatch.setattr(base, "save_exception", MagicMock())
    monkeypatch.setattr(base, "send_message", MagicMock())
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    monkeypatch.setattr(config, "stop_mower", Event())

    def forbidden_io(*args, **kwargs):
        pytest.fail("Offline scheduling must not connect a device or external service")

    monkeypatch.setattr(base.Device, "create", forbidden_io)
    monkeypatch.setattr(socket, "socket", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_io)
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    config.conf.enable_mastery = False

    instance = object.__new__(base.BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room("歌蕾蒂娅", "", ["陈"])],
                "contact": [Room("黑键", "感知", ["红"])],
                "room_1_1": [Room("鸿雪", "", ["但书", "深巡"])],
                "dormitory_1": [
                    Room("塑心", "感知", ["隐德来希"]),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [
            Plan(
                {},
                PlanConfig("", "", ""),
                trigger=LogicExpression(
                    "op_data.operators['黑键'].is_resting()", "==", "True"
                ),
                task={
                    "dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]
                },
            )
        ],
    }
    assert instance.initialize_operators() is None
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    for op in instance.op_data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp, op.mood = Clock.now(), 24
    for index, name in ((2, "黑键"), (3, "陈"), (4, "红")):
        op = instance.op_data.operators[name]
        op.current_room, op.current_index = "dormitory_1", index
    black_key = instance.op_data.operators["黑键"]
    black_key.mood = 18
    instance.op_data.operators["冰酿"].current_room = ""
    dorm = instance.op_data.dorm[0]
    dorm.name, dorm.time = "黑键", Clock.now() + timedelta(hours=2)
    instance.tasks, instance.task = [], None
    instance.plan_metadata()
    instance.scene = MagicMock(return_value=base.Scene.INFRA_MAIN)
    instance.find = MagicMock(return_value=True)
    instance.recog = MagicMock()
    instance.check_current_focus = MagicMock()
    instance.back_to_infrastructure = MagicMock()
    instance.party_time = instance.free_clue = instance.credit_fight = None
    instance.enable_party = False
    instance.drone_room = None
    instance.reload_time = Clock.now()
    instance.planned = instance.todo_task = instance.collect_notification = False
    instance.error = instance.refresh_connecting = False
    instance.agent_get_mood = MagicMock(return_value=None)
    instance.plan_solver = MagicMock(side_effect=instance.skip)
    instance.get_run_order_time = MagicMock(
        return_value=Clock.now() + timedelta(hours=1)
    )
    monkeypatch.setattr(base.detector, "infra_notification", lambda image: None)
    instance.sleep = MagicMock()
    return instance, Clock


def simulate_room_io(solver, clock, failures=0, failure_kind="exception"):
    """Keep arrangement execution real; selection/readback is the device seam."""
    remaining = failures

    def arrange_room(previous, room, plan, **kwargs):
        nonlocal remaining
        original = solver.op_data.get_current_room(room, True)
        temporary_order = solver.task.type == TaskTypes.RUN_ORDER and any(
            name in base.TRADE_ORDER_AGENTS for name in plan[room]
        )
        if remaining:
            remaining -= 1
            if failure_kind == "exception":
                raise base.RoomArrangementDeferred(
                    room, RuntimeError("simulated dorm confirmation failure")
                )
            solver.task.time = clock.now() + timedelta(minutes=1)
            return False
        solver.op_data = solver.op_data.project_arrangements([{room: plan[room]}])
        plan.pop(room)
        return previous | {room: original} if temporary_order else previous

    solver.agent_arrange_room = MagicMock(side_effect=arrange_room)
    return solver.agent_arrange_room


def dispatch(solver, clock):
    # Real time advances between entries; handle_error's due query uses '<'.
    clock.current += timedelta(seconds=1)
    solver.run()
    assert not solver.error


def planning_tasks(solver, clock):
    return [
        task
        for task in solver.tasks
        if task.type == TaskTypes.NOT_SPECIFIC
        and not task.plan
        and not task.meta_data
        and task.time <= clock.now()
    ]


def start_deferred_shift(solver, clock, failures, failure_kind="exception"):
    assert solver.backup_plan_solver()
    shift = next(task for task in solver.tasks if task.type == TaskTypes.RE_ORDER)
    simulate_room_io(solver, clock, failures, failure_kind)
    dispatch(solver, clock)
    if failures:
        assert shift in solver.tasks and shift.time > clock.now()
        clock.current = shift.time + timedelta(seconds=1)
        dispatch(solver, clock)
        assert shift in solver.tasks
        assert not planning_tasks(solver, clock)
        assert not any(task.type == TaskTypes.RUN_ORDER for task in solver.tasks)
    return shift


@pytest.mark.parametrize("failures", [0, 1, 3])
@pytest.mark.parametrize("failure_kind", ["exception", "deferred"])
def test_backup_completion_plans_orders_before_future_return(
    replay, failures, failure_kind
):
    solver, clock = replay
    shift = start_deferred_shift(solver, clock, failures, failure_kind)
    for _ in range(failures):
        clock.current = shift.time + timedelta(seconds=1)
        dispatch(solver, clock)
    assert shift not in solver.tasks
    assert any(task.type == TaskTypes.SHIFT_ON for task in solver.tasks)
    assert len(planning_tasks(solver, clock)) == 1, (
        "Completed retry must wake planning before the outer loop selects future sleep"
    )
    dispatch(solver, clock)
    orders = [task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER]
    assert len(orders) == 1
    assert orders[0].meta_data == "room_1_1"
    solver.get_run_order_time.assert_called_once_with("room_1_1")


@pytest.mark.parametrize("failures", [1, 3])
def test_saved_shift_continues_planning_in_a_new_scheduler(
    replay, failures, monkeypatch, tmp_path
):
    solver, clock = replay
    shift = start_deferred_shift(solver, clock, failures)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda path: tmp_path if path == "@app/tmp" else tmp_path / "record.db",
    )
    monkeypatch.setattr(record, "_tables_created", False)
    assert record.save_state_to_db(
        {
            "tasks": solver.tasks,
            "operators": solver.op_data.operators,
            "dorm": solver.op_data.all_dorms(),
            "group_shift_state": solver.op_data.group_shift_state,
        }
    )
    saved = record.load_state()
    resumed = object.__new__(base.BaseSchedulerSolver)
    resumed.__dict__.update(solver.__dict__)
    resumed.global_plan = copy.deepcopy(solver.global_plan)
    assert resumed.initialize_operators() is None
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    assert (
        resumed.op_data.swap_plan(solver.op_data.plan_condition, refresh=True) is None
    )
    resumed.op_data.operators = saved["operators"]
    resumed.op_data.restore_dorm_state(saved["dorm"])
    resumed.op_data.restore_group_shift_state(saved["group_shift_state"])
    resumed.tasks, resumed.task = saved["tasks"], None
    resumed.plan_solver = MagicMock(side_effect=resumed.skip)
    resumed_shift = next(t for t in resumed.tasks if t.type == TaskTypes.RE_ORDER)
    assert resumed_shift is not shift
    assert resumed_shift.time == shift.time
    simulate_room_io(resumed, clock, failures - 1)
    for _ in range(failures):
        clock.current = resumed_shift.time + timedelta(seconds=1)
        dispatch(resumed, clock)
    assert resumed_shift not in resumed.tasks
    assert len(planning_tasks(resumed, clock)) == 1
    dispatch(resumed, clock)
    assert len([t for t in resumed.tasks if t.type == TaskTypes.RUN_ORDER]) == 1
    resumed.get_run_order_time.assert_called_once_with("room_1_1")


def test_backup_correction_reuses_existing_planning_task(replay):
    solver, clock = replay
    solver.op_data.operators["冰酿"].current_room = "dormitory_1"
    solver.op_data.backup_plans[0].plan = {}
    solver.op_data.backup_plans[0].task = {"central": ["隐德来希"]}
    assert solver.backup_plan_solver()
    correction = next(
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    )
    simulate_room_io(solver, clock)
    dispatch(solver, clock)
    assert correction not in solver.tasks
    assert len(planning_tasks(solver, clock)) == 1
    dispatch(solver, clock)
    assert len([t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER]) == 1


def test_planning_preserves_existing_order_and_original_roster_task(replay):
    solver, clock = replay
    shift = start_deferred_shift(solver, clock, 1)
    order = SchedulerTask(
        clock.now() + timedelta(minutes=30),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    restoration = SchedulerTask(
        clock.now() + timedelta(minutes=10),
        {"room_1_1": ["鸿雪"]},
        TaskTypes.RUN_ORDER,
    )
    restoration.emergency_original_roster = copy.deepcopy(restoration.plan)
    solver.tasks.extend([order, restoration])
    dispatch(solver, clock)
    assert shift not in solver.tasks
    dispatch(solver, clock)
    assert [t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER] == [
        restoration,
        order,
    ]
    solver.get_run_order_time.assert_not_called()
    assert restoration.plan == {"room_1_1": ["鸿雪"]}
    assert solver.agent_arrange_room.call_count == 2
    # Dispatch the retained tasks through the real executor too. Countdown and
    # order confirmation remain device I/O, and the existing inline return runs.
    config.conf.run_order_grandet_mode.buffer_time = 1
    solver.drone_room = "room_3_3"
    solver.find = MagicMock(
        side_effect=lambda name, **kwargs: True if name == "control_central" else None
    )
    solver.get_order_remaining_time = MagicMock(return_value=5)
    solver.accept_order = MagicMock()
    solver.drone = MagicMock()
    solver.agent_arrange = MagicMock(wraps=solver.agent_arrange)
    clock.current = restoration.time + timedelta(seconds=1)
    dispatch(solver, clock)
    assert restoration not in solver.tasks
    assert order in solver.tasks
    solver.agent_arrange.assert_called_once()
    clock.current = order.time + timedelta(seconds=1)
    dispatch(solver, clock)
    assert order not in solver.tasks
    assert solver.agent_arrange.call_count == 2
    dispatch(solver, clock)
    assert solver.agent_arrange.call_count == 2
    solver.accept_order.assert_called_once()
    solver.drone.assert_not_called()
