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
        # 替代最终阵容读房：同房未换床住客也获得新计时。
        for bed in solver.op_data.all_dorms():
            if bed.position[0] == room and bed.name and bed.time is None:
                solver.op_data.refresh_dorm_time(
                    *bed.position,
                    {"agent": bed.name, "time": clock.now() + timedelta(hours=2)},
                )
        plan.pop(room)
        return previous | {room: original} if temporary_order else previous

    solver.agent_arrange_room = MagicMock(side_effect=arrange_room)
    return solver.agent_arrange_room


def dispatch(solver, clock, *, observe_failures=True):
    # Real time advances between entries; handle_error's due query uses '<'.
    clock.current += timedelta(seconds=1)
    if observe_failures:
        for task in solver.tasks:
            if failure := getattr(task, "execution_failure", None):
                # 模拟下一次成功实测；时钟流逝本身不释放失败任务。
                for name in failure["snapshot"]["observations"]:
                    solver.op_data.operators[name].time_stamp = clock.now()
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
    original_time = shift.time
    simulate_room_io(solver, clock, failures, failure_kind)
    dispatch(solver, clock)
    if failures:
        assert shift in solver.tasks
        if failure_kind == "exception":
            assert shift.time == original_time and shift.execution_failure
            return shift
        else:
            assert shift.time > clock.now()
        clock.current = max(clock.current, shift.time) + timedelta(seconds=1)
        dispatch(solver, clock, observe_failures=False)
        assert shift in solver.tasks
        assert not planning_tasks(solver, clock)
        assert not any(task.type == TaskTypes.RUN_ORDER for task in solver.tasks)
    return shift


def finish_pending_shift(solver, clock, shift, failures):
    for _ in range(failures + 3):
        if all(task is not shift for task in solver.tasks):
            return
        clock.current = max(clock.current, shift.time) + timedelta(seconds=1)
        dispatch(solver, clock)
    pytest.fail(
        "fresh observations did not finish the pending shift within its attempts"
    )


@pytest.mark.parametrize("failures", [0, 1, 3])
@pytest.mark.parametrize("failure_kind", ["exception", "deferred"])
def test_backup_completion_plans_orders_before_future_return(
    replay, failures, failure_kind
):
    solver, clock = replay
    shift = start_deferred_shift(solver, clock, failures, failure_kind)
    finish_pending_shift(solver, clock, shift, failures)
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
    finish_pending_shift(resumed, clock, resumed_shift, failures)
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
    finish_pending_shift(solver, clock, shift, 1)
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


def start_observed_correction(solver, clock, *, recovery_wait=False):
    solver.tasks = []
    solver.op_data.backup_plans = []
    solver.op_data.plan_condition = []
    solver.op_data.operators["冰酿"].current_room = "dormitory_1"
    solver.op_data.operators["冰酿"].current_index = 1
    primary = solver.op_data.operators["歌蕾蒂娅"]
    primary.current_room, primary.current_index = "", -1
    if recovery_wait:
        primary.group = "感知"
        solver.op_data.groups["感知"].append(primary.name)
        solver.op_data.operators["黑键"].rest_in_full = True
    else:
        op = solver.op_data.operators["黑键"]
        op.current_room, op.current_index = "contact", 0
        solver.op_data.dorm[0].name = ""
        solver.op_data.dorm[0].time = None
    solver.agent_get_mood = base.BaseSchedulerSolver.agent_get_mood.__get__(solver)
    solver._read_agent_mood = MagicMock()

    def read_recovery_rooms(rooms):
        for op in solver.op_data.operators.values():
            if op.current_room in rooms:
                op.time_stamp = clock.now()

    solver._read_recovery_rooms = MagicMock(side_effect=read_recovery_rooms)
    simulate_room_io(solver, clock)
    solver.infra_main()
    correction = next(
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    )
    assert correction.meta_data == ""
    solver.get_run_order_time.assert_not_called()
    return correction


def test_observed_correction_completion_keeps_order_planning(replay):
    solver, clock = replay
    correction = start_observed_correction(solver, clock)
    dispatch(solver, clock)
    assert correction not in solver.tasks
    orders = [task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER]
    assert len(orders) == 1
    assert orders[0].meta_data == "room_1_1"
    solver.get_run_order_time.assert_called_once_with("room_1_1")


def test_recovery_wait_reads_orders_without_recreating_correction(replay):
    solver, clock = replay
    correction = start_observed_correction(solver, clock, recovery_wait=True)
    original_time = correction.time
    dispatch(solver, clock)
    assert solver.waiting_group_shifts == [correction]
    assert correction not in solver.tasks
    waiting_plan = copy.deepcopy(correction.plan)
    refresh = [
        task
        for task in solver.tasks
        if task.type == TaskTypes.REFRESH_TIME and task.meta_data == "room_1_1"
    ]
    assert len(refresh) == 1
    assert refresh[0].time <= clock.now()
    recovery_checks = [
        task for task in solver.tasks if getattr(task, "recovery_observation_rooms", ())
    ]
    assert recovery_checks and all(task.time > clock.now() for task in recovery_checks)
    dispatch(solver, clock, observe_failures=False)
    orders = [task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER]
    assert len(orders) == 1
    solver.get_run_order_time.assert_called_once_with("room_1_1")
    assert solver.waiting_group_shifts == [correction]
    assert correction.plan == waiting_plan
    assert correction.time == original_time
    assert not any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
    assert solver.agent_get_mood(skip_dorm=True, read_rooms=False) is None
    solver._queue_missing_run_order_reads()
    assert [task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER] == orders
    assert not any(
        task.type == TaskTypes.REFRESH_TIME and task.meta_data == "room_1_1"
        for task in solver.tasks
    )
    assert all(task in solver.tasks for task in recovery_checks)
    for _ in range(3):
        solver._queue_missing_run_order_reads()
        assert solver.agent_get_mood(skip_dorm=True, read_rooms=False) is None
        assert solver.waiting_group_shifts == [correction]
        assert correction.plan == waiting_plan
        assert correction.time == original_time
        assert [
            task for task in solver.tasks if task.type == TaskTypes.RUN_ORDER
        ] == orders
        assert not any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
    solver.get_run_order_time.assert_called_once_with("room_1_1")
    independent = solver.op_data.operators["鸿雪"]
    independent.current_room, independent.current_index = "", -1
    plan = solver.agent_get_mood(skip_dorm=True, read_rooms=False, return_plan=True)
    assert plan == {"room_1_1": ["鸿雪"]}
    independent.current_room, independent.current_index = "room_1_1", 0
    clock.current += timedelta(minutes=1)
    recovered = solver.op_data.operators["黑键"]
    recovered.mood = 24
    recovered.time_stamp = clock.now()
    solver.op_data.get_dorm_by_name("黑键")[1].time = clock.now()
    solver._resume_waiting_group_shifts()
    assert correction not in solver.waiting_group_shifts
    assert any(task is correction for task in solver.tasks)
    assert correction.time == original_time
    assert correction.plan["central"] == waiting_plan["central"]
    assert correction.plan["contact"] == waiting_plan["contact"]
    dispatch(solver, clock, observe_failures=False)
    assert correction not in solver.tasks
    assert solver.op_data.operators["歌蕾蒂娅"].current_room == "central"
    assert solver.op_data.operators["黑键"].current_room == "contact"
    solver.get_run_order_time.assert_called_once_with("room_1_1")


@pytest.mark.parametrize("kind", ["order", "refresh", "original", "restoration"])
def test_recovery_wait_preserves_existing_order_responsibility(replay, kind):
    solver, clock = replay
    correction = start_observed_correction(solver, clock, recovery_wait=True)
    pending = SchedulerTask(
        clock.now() + timedelta(minutes=30),
        {} if kind == "refresh" else {"room_1_1": ["鸿雪"]},
        TaskTypes.REFRESH_TIME if kind == "refresh" else TaskTypes.RUN_ORDER,
        meta_data="room_1_1" if kind in ("order", "refresh") else "",
    )
    if kind == "original":
        pending.emergency_original_roster = {"room_1_1": ["鸿雪"]}
    elif kind == "restoration":
        pending.run_order_original_roster = {"room_1_1": ["鸿雪"]}
        pending.run_order_restore_pending = True
    solver.tasks.append(pending)
    original = copy.deepcopy(vars(pending))
    dispatch(solver, clock)
    assert solver.waiting_group_shifts == [correction]
    assert pending in solver.tasks
    assert vars(pending) == original
    assert [
        task
        for task in solver.tasks
        if task.type == TaskTypes.RUN_ORDER
        or task.type == TaskTypes.REFRESH_TIME
        and task.meta_data
    ] == [pending]
    solver.get_run_order_time.assert_not_called()
