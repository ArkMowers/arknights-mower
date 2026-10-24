"""整批换班后读取订单，已有关键任务保护原纠错的未完安排。"""

import copy
import socket
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests


@pytest.fixture
def staffed_order(monkeypatch):
    # 导入链中的森空岛身份请求不属于离线调度；替身随夹具恢复。
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.tests import run_order_product_tests as room_pages
    from arknights_mower.utils import operation_timing

    base = room_pages.base_schedule
    operators = room_pages.Operators
    scheduling = room_pages.scheduler_task
    config = room_pages.config

    class Clock(datetime):
        current = datetime(2026, 10, 19, 12)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    for module in (base, sys.modules[operators.__module__], scheduling, room_pages):
        monkeypatch.setattr(module, "datetime", Clock)

    def forbidden_io(*args, **kwargs):
        pytest.fail("离线订单调度不得连接设备、外部服务或启动进程")

    monkeypatch.setattr(base.Device, "create", forbidden_io)
    monkeypatch.setattr(socket, "socket", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_io)
    monkeypatch.setattr(scheduling.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(base, "save_log", MagicMock())
    monkeypatch.setattr(base, "save_exception", MagicMock())
    monkeypatch.setattr(base, "send_message", MagicMock())
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    monkeypatch.setattr(config, "stop_mower", Event())
    for name in ("_work_durations", "_dorm_durations"):
        monkeypatch.setattr(
            operation_timing, name, defaultdict(lambda: deque(maxlen=8))
        )
    solver = room_pages.solver.__wrapped__(monkeypatch)
    config.conf.run_order_delay = 3
    config.conf.run_order_grandet_mode.enable = True
    config.conf.run_order_grandet_mode.buffer_time = 30
    config.conf.run_order_grandet_mode.back_to_index = False
    solver.waiting_scene = []
    solver.drone_room = "room_9_9"
    solver.refresh_connecting = False
    solver.party_time = solver.free_clue = solver.credit_fight = None
    solver.enable_party = False
    solver.reload_time = Clock.now()
    occupants = {
        "room_1_1": [""],
        "room_2_2": [""],
        "dormitory_1": ["", "", "", "", ""],
    }
    states = {"room_1_1": "paused", "room_2_2": "paused"}
    room_pages.use_order_pages(solver, states)
    order_find = solver.find
    room_pages.use_mood_pages(solver, monkeypatch, occupants)
    for operator in solver.op_data.operators.values():
        operator.current_room, operator.current_index = "", -1
    events = []
    deadlines = {
        "room_1_1": Clock.now() + timedelta(hours=1),
        "room_2_2": Clock.now() + timedelta(hours=2),
    }
    durations = {"room_1_1": 20, "room_2_2": 60, "dormitory_1": 180}

    def enter_room(room):
        events.append(("enter", room, Clock.now()))
        solver._page.update(room=room, open=False)

    def find(resource, *args, **kwargs):
        if resource in ("control_central", "confirm_blue"):
            return True
        return order_find(resource)

    def read_time(*args, **kwargs):
        room = solver._page["room"]
        events.append(("read", room, Clock.now()))
        if states[room] in ("empty", "paused"):
            return None
        return max(0, (deadlines[room] - Clock.now()).total_seconds())

    def confirm(room, new_plan):
        chosen = solver.choose_agent.call_args.args[0]
        occupants[room] = [
            name if name not in ("Current", "Free") else "" for name in chosen
        ]
        if room in states:
            states[room] = "active" if all(occupants[room]) else "paused"
        Clock.current += timedelta(seconds=durations[room])
        events.append(("staffed", room, Clock.now()))

    def back(*args, **kwargs):
        solver._page.update(room=None, open=False)

    def sleep(seconds=1):
        Clock.current += timedelta(seconds=seconds)

    def accept_order():
        events.append(("collected", "room_1_1", Clock.now()))
        deadlines["room_1_1"] = Clock.now() + timedelta(hours=1)

    for name in (
        "turn_on_room_detail",
        "record_selection_success",
        "_track_idle_dorm_shift",
        "_finish_idle_dorm_shift",
    ):
        monkeypatch.setattr(solver, name, MagicMock(), raising=False)
    monkeypatch.setattr(
        solver, "ensure_dorm_recovery_order", MagicMock(return_value=False)
    )
    monkeypatch.setattr(
        solver, "_can_refresh_idle_dorm_search", MagicMock(return_value=False)
    )
    monkeypatch.setattr(solver, "prepare_dorm_selection", MagicMock(return_value=None))
    monkeypatch.setattr(solver, "enter_room", MagicMock(side_effect=enter_room))
    monkeypatch.setattr(solver, "find", MagicMock(side_effect=find))
    monkeypatch.setattr(solver, "scene", MagicMock(return_value=base.Scene.INFRA_MAIN))
    monkeypatch.setattr(solver, "choose_agent", MagicMock())
    monkeypatch.setattr(solver, "tap_confirm", MagicMock(side_effect=confirm))
    monkeypatch.setattr(solver, "back", MagicMock(side_effect=back))
    monkeypatch.setattr(solver, "sleep", MagicMock(side_effect=sleep))
    monkeypatch.setattr(solver, "accept_order", MagicMock(side_effect=accept_order))
    monkeypatch.setattr(
        solver,
        "get_order_remaining_time",
        MagicMock(
            side_effect=lambda: max(
                0, (deadlines["room_1_1"] - Clock.now()).total_seconds()
            )
        ),
    )
    solver.read_time.side_effect = read_time
    solver.recog.img = MagicMock()
    solver.recog.update = MagicMock()
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.plan_metadata = MagicMock()
    return SimpleNamespace(
        solver=solver,
        clock=Clock,
        events=events,
        deadlines=deadlines,
        durations=durations,
        occupants=occupants,
        states=states,
        base=base,
        scheduling=scheduling,
        config=config,
        task_type=room_pages.TaskTypes,
        task=room_pages.SchedulerTask,
        operators=operators,
    )


def correction(ui, rooms=None):
    plan = {
        "room_1_1": ["鸿雪"],
        "room_2_2": ["图耶"],
        "dormitory_1": ["杜林", "蜜莓", "Current", "Current", "Current"],
    }
    task = ui.task(
        time=ui.clock.now(),
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={
            room: row for room, row in plan.items() if rooms is None or room in rooms
        },
    )
    ui.solver.tasks.append(task)
    ui.solver.task = task
    return task


def reads(ui, room="room_1_1"):
    return [event for event in ui.events if event[:2] == ("read", room)]


def test_completed_staffing_reads_each_station_once_and_keeps_distant_run(
    staffed_order,
):
    ui = staffed_order
    task = correction(ui)
    original_time = task.time

    ui.solver.agent_arrange(task.plan)

    assert task.plan == {} and task.time == original_time
    assert len(reads(ui)) == 1
    assert ui.events.index(reads(ui)[0]) > next(
        index
        for index, event in enumerate(ui.events)
        if event[:2] == ("enter", "room_2_2")
    )
    orders = [task for task in ui.solver.tasks if task.type == ui.task_type.RUN_ORDER]
    assert {task.meta_data for task in orders} == {"room_1_1", "room_2_2"}
    assert not any(task.type == ui.task_type.REFRESH_TIME for task in ui.solver.tasks)
    ui.solver.run_order_solver()
    assert len(reads(ui)) == 1
    assert len(reads(ui, "room_2_2")) == 1


def test_known_order_yields_and_preserves_unfinished_correction(staffed_order):
    ui = staffed_order
    task = correction(ui, {"room_1_1", "dormitory_1"})
    original_time = task.time
    order = ui.task(
        time=ui.clock.now() + timedelta(seconds=90),
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_2_2": ["龙舌兰"]},
        meta_data="room_2_2",
    )
    ui.solver.tasks.append(order)
    assert ui.solver.agent_arrange(task.plan) is False
    remaining = copy.deepcopy(task.plan)
    assert remaining and task.time == original_time
    assert not reads(ui)
    for _ in range(3):
        assert ui.solver.agent_arrange(task.plan) is False
        assert task.plan == remaining and task.time == original_time
    ui.solver.tasks = [pending for pending in ui.solver.tasks if pending is not order]
    ui.solver.agent_arrange(task.plan)
    assert not task.plan and task.time == original_time
    assert len(reads(ui)) == 1


@pytest.mark.parametrize("old_minutes", [60, 10, -1])
def test_configured_refresh_operator_move_replaces_even_due_order(
    staffed_order, monkeypatch, old_minutes
):
    ui = staffed_order
    solver = ui.solver
    ui.occupants["room_1_1"] = ["鸿雪"]
    solver.get_agent_from_room("room_1_1")
    ui.states["room_1_1"] = "active"
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=old_minutes + 3)
    solver.plan_run_order("room_1_1")
    old_order = next(
        task for task in solver.tasks if task.type == ui.task_type.RUN_ORDER
    )
    assert len(reads(ui)) == 1
    solver.op_data.first_init = False
    moved = solver.op_data.operators["杜林"]
    moved.refresh_order_room = [True, ["room_1_1"]]
    monkeypatch.setattr(
        ui.operators, "current_room_changed_callback", solver.current_room_changed
    )
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=20)

    moved.current_room = "central"
    solver.plan_run_order("room_1_1")

    assert len(reads(ui)) == 2
    assert all(task is not old_order for task in solver.tasks)
    order = next(task for task in solver.tasks if task.type == ui.task_type.RUN_ORDER)
    assert order.time == ui.clock.now() + timedelta(minutes=17)


@pytest.mark.parametrize(
    "changed_room,changed_name", [("room_2_2", "图耶"), ("dormitory_1", "杜林")]
)
def test_later_room_refresh_operator_updates_already_read_station(
    staffed_order, monkeypatch, changed_room, changed_name
):
    ui = staffed_order
    solver = ui.solver
    solver.op_data.first_init = False
    solver.op_data.operators[changed_name].refresh_order_room = [True, ["room_1_1"]]
    monkeypatch.setattr(
        ui.operators, "current_room_changed_callback", solver.current_room_changed
    )
    confirm = solver.tap_confirm.side_effect

    def change_production(room, new_plan):
        confirm(room, new_plan)
        if room == changed_room:
            ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=20)

    solver.tap_confirm.side_effect = change_production
    task = correction(ui)

    solver.agent_arrange(task.plan)

    assert task.plan == {}
    assert len(reads(ui)) == 1
    order = next(
        task
        for task in solver.tasks
        if task.type == ui.task_type.RUN_ORDER and task.meta_data == "room_1_1"
    )
    assert order.time == ui.deadlines["room_1_1"] - timedelta(minutes=3)
    assert not any(task.type == ui.task_type.REFRESH_TIME for task in solver.tasks)


def test_vacancy_dependent_refresh_resumes_after_confirmed_staffing(staffed_order):
    ui = staffed_order
    solver = ui.solver
    task = correction(ui, {"room_1_1"})
    ui.states["room_1_1"] = "paused"
    solver.plan_run_order("room_1_1")
    waiting = next(
        task for task in solver.tasks if task.type == ui.task_type.REFRESH_TIME
    )
    original_time = waiting.time
    assert waiting.execution_failure
    for _ in range(3):
        solver._resume_failed_tasks()
        solver.plan_run_order("room_1_1")
    assert len(reads(ui)) == 1
    assert waiting.time == original_time
    ui.states["room_1_1"] = "active"

    solver.agent_arrange(task.plan)

    assert len(reads(ui)) == 2
    assert all(queued is not waiting for queued in solver.tasks)
    assert any(task.type == ui.task_type.RUN_ORDER for task in solver.tasks)
    assert waiting.time == original_time


def test_original_roster_restoration_does_not_read_or_reinsert_order(
    staffed_order, monkeypatch
):
    ui = staffed_order
    ui.occupants["room_1_1"] = ["但书"]
    ui.solver.get_agent_from_room("room_1_1")
    ui.solver.op_data.first_init = False
    ui.solver.op_data.operators["鸿雪"].refresh_order_room = [True, ["room_1_1"]]
    monkeypatch.setattr(
        ui.operators, "current_room_changed_callback", ui.solver.current_room_changed
    )
    restore = ui.task(
        time=ui.clock.now(),
        task_plan={"room_1_1": ["鸿雪"]},
        task_type=ui.task_type.RUN_ORDER,
    )
    restore.run_order_original_roster = copy.deepcopy(restore.plan)
    restore.run_order_restore_pending = True
    ui.solver.tasks, ui.solver.task = [restore], restore

    ui.solver.agent_arrange(restore.plan)

    assert ui.occupants["room_1_1"] == ["鸿雪"]
    assert not reads(ui)
    assert not getattr(restore, "run_order_restore_pending", False)
    ui.solver.accept_order.assert_not_called()
    assert [call.args[0] for call in ui.solver.choose_agent.call_args_list] == [
        ["鸿雪"]
    ]


def test_unobserved_short_order_is_read_only_after_completed_batch(staffed_order):
    ui = staffed_order
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=4)
    task = correction(ui)
    original_time = task.time
    ui.solver.agent_arrange(task.plan)
    assert not task.plan and task.time == original_time
    assert len(reads(ui)) == 1
    last_staffing = max(
        index for index, event in enumerate(ui.events) if event[0] == "staffed"
    )
    assert ui.events.index(reads(ui)[0]) > last_staffing
    assert any(queued.type == ui.task_type.RUN_ORDER for queued in ui.solver.tasks)


@pytest.mark.parametrize("run_start_seconds", [100, 110])
def test_remaining_work_room_uses_same_margin_as_dispatch(
    staffed_order, run_start_seconds
):
    ui = staffed_order
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(
        minutes=3, seconds=run_start_seconds
    )
    # 已有正式跑单仍按原有下一房安排预算决定是否让行。
    ui.occupants["room_1_1"] = ["鸿雪"]
    ui.states["room_1_1"] = "active"
    ui.solver.get_agent_from_room("room_1_1")
    ui.solver.plan_run_order("room_1_1")
    task = correction(ui, {"room_1_1", "room_2_2"})
    original_time = task.time

    assert ui.solver.agent_arrange(task.plan) is not False

    assert task.plan == {} and task.time == original_time
    assert len(reads(ui)) == 1
    assert not reads(ui, "room_2_2")
    order = next(
        queued
        for queued in ui.solver.tasks
        if queued.type == ui.task_type.RUN_ORDER and queued.meta_data == "room_1_1"
    )
    assert order.time == original_time + timedelta(seconds=run_start_seconds)
    assert ui.clock.now() < order.time
    refresh = next(
        queued for queued in ui.solver.tasks if queued.type == ui.task_type.REFRESH_TIME
    )
    refresh_time = refresh.time
    for _ in range(3):
        ui.solver._read_arrangement_order_times("room_2_2")
    assert not reads(ui, "room_2_2")
    assert refresh in ui.solver.tasks and refresh.time == refresh_time

    order.time = ui.clock.now() + timedelta(hours=1)
    ui.solver._read_arrangement_order_times("room_2_2")

    assert len(reads(ui, "room_2_2")) == 1
    assert refresh not in ui.solver.tasks
    assert task.time == original_time


def test_failed_final_read_keeps_independent_refresh_after_all_staffing(
    staffed_order,
):
    ui = staffed_order
    solver = ui.solver
    read_time = solver.read_time.side_effect
    attempts = []

    def unreadable_first_room(*args, **kwargs):
        if solver._page["room"] == "room_1_1":
            attempts.append(ui.clock.now())
            raise ui.base.RecognizeError("订单数字未确认")
        return read_time(*args, **kwargs)

    solver.read_time.side_effect = unreadable_first_room
    task = correction(ui)

    solver.agent_arrange(task.plan)

    assert task.plan == {}
    assert not getattr(task, "execution_failure", None)
    waiting = next(
        queued for queued in solver.tasks if queued.type == ui.task_type.REFRESH_TIME
    )
    original_time = waiting.time
    assert waiting.meta_data == "room_1_1" and waiting.execution_failure
    assert ui.occupants["room_1_1"] == ["鸿雪"]
    assert ui.occupants["room_2_2"] == ["图耶"]
    assert any(event[:2] == ("staffed", "dormitory_1") for event in ui.events)
    for _ in range(3):
        solver._resume_failed_tasks()
        solver.plan_run_order("room_1_1")
    assert len(attempts) == 1
    assert waiting.time == original_time


def test_due_first_order_is_read_before_other_pending_refresh(staffed_order):
    ui = staffed_order
    solver = ui.solver
    ui.occupants["room_2_2"] = ["图耶"]
    solver.get_agent_from_room("room_2_2")
    ui.states["room_2_2"] = "active"
    other = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_2_2")
    solver.tasks.append(other)
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(seconds=90)
    task = correction(ui, {"room_1_1", "dormitory_1"})

    assert solver.agent_arrange(task.plan) is not False

    assert len(reads(ui)) == 1
    assert len(reads(ui, "room_2_2")) == 1
    assert all(queued is not other for queued in solver.tasks)
    assert task.plan == {}


@pytest.mark.parametrize(
    "protection",
    [
        "current",
        "execution_retained",
        "run_order_original_roster",
        "run_order_restore_pending",
        "emergency_original_roster",
        "maintenance_replacement_run",
        "maintenance_advance_before_backup",
    ],
)
def test_staffing_refresh_preserves_started_or_maintenance_order(
    staffed_order, protection
):
    ui = staffed_order
    order = ui.task(
        time=ui.clock.now() - timedelta(minutes=1),
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    if protection == "current":
        ui.solver.task = order
    else:
        setattr(
            order,
            protection,
            {"room_1_1": ["鸿雪"]} if "roster" in protection else True,
        )
    ui.solver.tasks = [order]
    before = copy.deepcopy(vars(order))

    ui.solver.refresh_run_order_time("room_1_1")

    assert ui.solver.tasks == [order]
    assert vars(order) == before
    assert not reads(ui)


@pytest.mark.parametrize("retained", [False, True])
def test_retained_ordinary_departure_keeps_request_after_member_is_resting(
    staffed_order, retained
):
    ui = staffed_order
    operator = ui.solver.op_data.operators["鸿雪"]
    operator.current_room, operator.current_index = "dormitory_1", 2
    operator.mood = 4
    task = ui.task(
        time=ui.clock.now(),
        task_type=ui.task_type.SHIFT_OFF,
        task_plan={"room_2_2": ["图耶"]},
    )
    task.ordinary_coordination = True
    task.coordination_request_names = ["鸿雪"]
    if retained:
        task.execution_retained = True
    ui.solver.tasks = [task]
    original = copy.deepcopy(vars(task))

    assert ui.solver._prepare_ordinary_departure(task) is retained

    assert vars(task) == original


def test_failed_final_read_checks_order_deadline_before_next_refresh(staffed_order):
    from arknights_mower.utils.plan import Room

    ui = staffed_order
    solver = ui.solver
    solver.op_data.plan["room_3_3"] = [Room("孑", "", ["佩佩"])]
    solver.op_data.products["room_3_3"] = "lmd"
    solver.op_data.refresh_run_order_rooms()
    ui.states.update({"room_2_2": "active", "room_3_3": "active"})
    ui.deadlines["room_3_3"] = ui.clock.now() + timedelta(hours=4)
    task = correction(ui, {"dormitory_1"})
    task.plan.clear()
    original_time, remaining = task.time, copy.deepcopy(task.plan)
    order = ui.task(
        time=ui.clock.now() + timedelta(seconds=75),
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    failed = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_2_2")
    other = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_3_3")
    solver.tasks.extend([order, failed, other])
    failed_time = failed.time
    read_time = solver.read_time.side_effect
    attempts = []

    def fail_after_order_deadline(*args, **kwargs):
        if solver._page["room"] == "room_2_2":
            attempts.append(ui.clock.now())
            ui.clock.current += timedelta(seconds=90)
            raise ui.base.RecognizeError("订单数字未确认")
        return read_time(*args, **kwargs)

    solver.read_time.side_effect = fail_after_order_deadline

    solver._read_arrangement_order_times("room_2_2")

    assert order.time < ui.clock.now()
    assert any(queued is order for queued in solver.tasks)
    assert any(queued is failed for queued in solver.tasks)
    assert failed.time == failed_time and failed.execution_failure
    assert any(queued is other for queued in solver.tasks)
    assert not reads(ui, "room_3_3")
    assert task.time == original_time and task.plan == remaining

    order.time = ui.clock.now() + timedelta(hours=1)
    ui.clock.current = max(ui.clock.now(), other.time)
    solver._read_arrangement_order_times("room_3_3")

    assert len(attempts) == 1
    assert len(reads(ui, "room_3_3")) == 1
    assert all(queued is not other for queued in solver.tasks)
    assert failed.time == failed_time and failed.execution_failure
    assert task.time == original_time and task.plan == remaining
    assert task.plan == {} and task.time == original_time
    assert len(reads(ui, "room_3_3")) == 1
    assert all(queued is not other for queued in solver.tasks)
