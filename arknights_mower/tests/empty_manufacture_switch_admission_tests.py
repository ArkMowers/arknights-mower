import socket
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
import requests

EMPTY_ROOM = "room_1_2"
OTHER_ROOM = "room_3_2"
WORKERS = {EMPTY_ROOM: "鸿雪", OTHER_ROOM: "槐琥"}
TARGET = "exp3"


@pytest.fixture
def base_schedule(monkeypatch, offline_maintenance):
    def forbidden_io(*args, **kwargs):
        pytest.fail("离线切产物回归不得连接设备、外部服务或启动进程")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_io)
    with monkeypatch.context() as imports:
        imports.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
        from arknights_mower.solvers import base_schedule as base
        from arknights_mower.utils import config, operators, scheduler_task
        from arknights_mower.utils.plan import Plan, PlanConfig, Room

    monkeypatch.setattr(base.Device, "create", forbidden_io)
    monkeypatch.setattr(socket, "socket", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)

    class Clock(datetime):
        current = datetime(2026, 11, 26, 12)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(operators, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = operators.Operators(
        {
            "default_plan": Plan(
                {
                    EMPTY_ROOM: [
                        Room(WORKERS[EMPTY_ROOM], "", ["图耶"], "制造站", TARGET)
                    ],
                    OTHER_ROOM: [
                        Room(WORKERS[OTHER_ROOM], "", ["砾"], "制造站", TARGET)
                    ],
                },
                PlanConfig("", "", ""),
                products={EMPTY_ROOM: TARGET, OTHER_ROOM: TARGET},
            ),
            "backup_plans": [],
        }
    )
    assert solver.op_data.init_and_validate() is None
    solver.tasks, solver.task = [], None
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.refresh_connecting = False
    solver.find = Mock(return_value=True)
    solver.recog = SimpleNamespace(update=Mock())
    events = []
    paused_rooms = set()

    def observe_roster(room, name=""):
        if name:
            worker = solver.op_data.operators[name]
            worker.current_room, worker.current_index = room, 0
            worker.time_stamp = Clock.now()
            paused_rooms.discard(room)
        else:
            paused_rooms.add(room)
        solver._reconcile_room_observation(
            room, [{"agent": name, "mood": 24 if name else -1}]
        )

    def add_switch(room, *, overdue_minutes=1):
        solver.op_data.update_facility_state(room, "manufacture", "gold")
        switch = scheduler_task.SchedulerTask(
            time=Clock.now() - timedelta(minutes=overdue_minutes),
            task_type=scheduler_task.TaskTypes.SWITCH_PRODUCT,
            meta_data=base.product_task_meta(room, TARGET),
        )
        solver.tasks.append(switch)
        return switch

    def dispatch():
        solver._resume_failed_tasks()
        scheduler_task.scheduling(solver.tasks, op_data=solver.op_data)
        task = solver.find_next_task()
        solver.task = task
        if task is None or task.time > Clock.now():
            return None
        solver.infra_main()
        return task

    def survey(room, target):
        events.append(("survey", room))
        if room in paused_rooms:
            raise base.RecognizeError("制造暂停，无法加速当前制造队列")
        return {
            "room": room,
            "facility": "manufacture",
            "current_product": "gold",
            "target_product": target,
            "needs_switch": True,
            "available_drones": 100,
            "drone_count": 2,
            "wait_seconds": 0,
            "total_seconds": 360,
            "current_remaining": 360,
            "production_rate": 1.0,
            "observed_at": Clock.now(),
        }

    def accelerate(observation):
        events.append(("accelerate", observation["room"]))
        return 0

    def change(observation, **kwargs):
        room = observation["room"]
        events.append(("change", room))
        solver.op_data.update_facility_state(
            room, "manufacture", observation["target_product"]
        )

    def arrange(plan, *args, **kwargs):
        for room, (name,) in plan.items():
            events.append(("staffing", room))
            observe_roster(room, name)
        return True

    solver._survey_manufacture_switch = Mock(side_effect=survey)
    solver._execute_manufacture_acceleration = Mock(side_effect=accelerate)
    solver._change_manufacture_product = Mock(side_effect=change)
    solver.agent_arrange = Mock(side_effect=arrange)
    observe_roster(OTHER_ROOM, WORKERS[OTHER_ROOM])
    solver.op_data.update_facility_state(OTHER_ROOM, "manufacture", TARGET)
    return SimpleNamespace(
        solver=solver,
        clock=Clock,
        tasks=scheduler_task,
        events=events,
        paused_rooms=paused_rooms,
        observe_roster=observe_roster,
        add_switch=add_switch,
        dispatch=dispatch,
    )


def assert_switch_retained(solver, switch, original_time):
    matching = [
        task
        for task in solver.tasks
        if task.type == switch.type and task.meta_data == switch.meta_data
    ]
    assert len(matching) == 1 and matching[0] is switch
    assert switch.time == original_time


def test_startup_correction_staffs_confirmed_empty_room_before_switch(base_schedule):
    ui = base_schedule
    ui.observe_roster(EMPTY_ROOM)
    switch = ui.add_switch(EMPTY_ROOM)
    original_time = switch.time
    ui.solver._initial_staffing_pending = True
    ui.solver.task = switch

    ui.solver.infra_main()
    assert ("survey", EMPTY_ROOM) not in ui.events
    assert_switch_retained(ui.solver, switch, original_time)
    if not ui.events:
        ui.dispatch()
    assert ui.events == [("staffing", EMPTY_ROOM)]
    assert_switch_retained(ui.solver, switch, original_time)

    ui.dispatch()
    assert ui.events[-1] == ("change", EMPTY_ROOM)
    assert all(task is not switch for task in ui.solver.tasks)
    assert switch.time == original_time


def test_due_batch_leaves_confirmed_empty_room_for_staffing(base_schedule):
    ui = base_schedule
    ui.observe_roster(EMPTY_ROOM)
    other = ui.add_switch(OTHER_ROOM, overdue_minutes=2)
    switch = ui.add_switch(EMPTY_ROOM)
    original_time = switch.time
    ui.solver.tasks.append(
        ui.tasks.SchedulerTask(
            task_type=ui.tasks.TaskTypes.SELF_CORRECTION,
            task_plan={EMPTY_ROOM: [WORKERS[EMPTY_ROOM]]},
        )
    )

    ui.dispatch()

    assert ("survey", EMPTY_ROOM) not in ui.events
    assert_switch_retained(ui.solver, switch, original_time)
    for _ in range(3):
        ui.dispatch()
    assert ("staffing", EMPTY_ROOM) in ui.events
    assert ("change", OTHER_ROOM) in ui.events
    assert all(task is not other for task in ui.solver.tasks)
    assert ui.events.index(("staffing", EMPTY_ROOM)) < ui.events.index(
        ("survey", EMPTY_ROOM)
    )


def test_survey_only_switch_yields_to_staffing_and_keeps_original_task(base_schedule):
    ui = base_schedule
    ui.observe_roster(EMPTY_ROOM, WORKERS[EMPTY_ROOM])
    switch = ui.add_switch(EMPTY_ROOM)
    original_time = switch.time
    priority = ui.tasks.SchedulerTask(
        time=ui.clock.now() + timedelta(minutes=2),
        task_type=ui.tasks.TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    survey = ui.solver._survey_manufacture_switch.side_effect

    def survey_with_priority(room, target):
        observation = survey(room, target)
        ui.solver.tasks.append(priority)
        return observation

    ui.solver._survey_manufacture_switch.side_effect = survey_with_priority
    ui.dispatch()
    assert ui.events == [("survey", EMPTY_ROOM)]
    assert_switch_retained(ui.solver, switch, original_time)
    ui.solver._survey_manufacture_switch.side_effect = survey
    ui.solver.tasks.remove(priority)

    ui.observe_roster(EMPTY_ROOM)
    ui.solver.tasks.append(
        ui.tasks.SchedulerTask(
            task_type=ui.tasks.TaskTypes.SELF_CORRECTION,
            task_plan={EMPTY_ROOM: [WORKERS[EMPTY_ROOM]]},
        )
    )
    ui.dispatch()
    assert ui.events == [("survey", EMPTY_ROOM), ("staffing", EMPTY_ROOM)]
    assert_switch_retained(ui.solver, switch, original_time)

    ui.solver.queue_product_switches()
    assert_switch_retained(ui.solver, switch, original_time)


def test_overdue_paused_switch_waits_through_repeated_vacancy_observations(
    base_schedule,
):
    ui = base_schedule
    switch = ui.add_switch(EMPTY_ROOM)
    original_time = switch.time
    ui.paused_rooms.add(EMPTY_ROOM)
    ui.dispatch()
    assert ui.events == [("survey", EMPTY_ROOM)]
    assert_switch_retained(ui.solver, switch, original_time)

    assert switch.execution_failure
    ui.clock.current += timedelta(minutes=20)
    ui.dispatch()
    assert ui.events == [("survey", EMPTY_ROOM)]
    assert_switch_retained(ui.solver, switch, original_time)

    ui.observe_roster(EMPTY_ROOM)
    for _ in range(2):
        ui.clock.current += timedelta(minutes=20)
        ui.observe_roster(EMPTY_ROOM)
        ui.dispatch()
        assert_switch_retained(ui.solver, switch, original_time)

    assert ui.events == [("survey", EMPTY_ROOM)]
    ui.observe_roster(EMPTY_ROOM, WORKERS[EMPTY_ROOM])
    ui.dispatch()

    assert ui.events.count(("survey", EMPTY_ROOM)) == 2
    assert ui.events[-1] == ("change", EMPTY_ROOM)
    assert all(task is not switch for task in ui.solver.tasks)
    assert switch.time == original_time


@pytest.fixture
def backup_switch_waiting_for_staffing(base_schedule):
    from arknights_mower.utils.logic_expression import LogicExpression
    from arknights_mower.utils.operators import Operators
    from arknights_mower.utils.plan import Plan

    ui = base_schedule
    solver = ui.solver
    primary = solver.op_data.global_plan["default_plan"]
    primary.plan[EMPTY_ROOM][0].product = "gold"
    primary.products[EMPTY_ROOM] = "gold"
    backup = Plan(
        {},
        primary.config,
        trigger=LogicExpression("op_data.party_time", "is not", "None"),
        task={EMPTY_ROOM: [WORKERS[EMPTY_ROOM]]},
        products={EMPTY_ROOM: TARGET},
    )
    solver.op_data = Operators({"default_plan": primary, "backup_plans": [backup]})
    assert solver.op_data.init_and_validate() is None
    ui.observe_roster(OTHER_ROOM, WORKERS[OTHER_ROOM])
    solver.op_data.update_facility_state(OTHER_ROOM, "manufacture", TARGET)
    solver.op_data.update_facility_state(EMPTY_ROOM, "manufacture", "gold")
    solver.set_detected_party_time(ui.clock.now() + timedelta(hours=1))

    assert solver.backup_plan_solver() is False
    assert solver.op_data.plan_condition == [False]
    (switch,) = solver.tasks
    original_time = switch.time
    assert switch.type == ui.tasks.TaskTypes.SWITCH_PRODUCT
    assert switch.pending_backup_product_switch
    assert switch.pending_product_targets == {EMPTY_ROOM: TARGET}

    ui.observe_roster(EMPTY_ROOM)
    assert solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]
    assert solver.op_data.products[EMPTY_ROOM] == TARGET
    assert_switch_retained(solver, switch, original_time)
    assert switch.execution_failure["manufacture_staffing_wait"] == EMPTY_ROOM
    return ui, switch, original_time


def test_backup_activation_does_not_wait_for_empty_factory_switch(
    backup_switch_waiting_for_staffing,
):
    ui, switch, original_time = backup_switch_waiting_for_staffing
    solver = ui.solver
    ui.clock.current += timedelta(minutes=1)
    assert solver.backup_plan_solver() is False
    solver.queue_product_switches()
    assert solver.op_data.plan_condition == [True]
    assert_switch_retained(solver, switch, original_time)

    independent = ui.add_switch(OTHER_ROOM, overdue_minutes=2)
    ui.dispatch()
    assert ui.events == [
        ("survey", OTHER_ROOM),
        ("accelerate", OTHER_ROOM),
        ("change", OTHER_ROOM),
    ]
    assert all(task is not independent for task in solver.tasks)
    assert solver.op_data.get_current_operator(EMPTY_ROOM, 0) is None
    assert_switch_retained(solver, switch, original_time)

    ui.events.clear()
    ui.dispatch()
    assert ui.events == [("staffing", EMPTY_ROOM)]
    assert (
        solver.op_data.get_current_operator(EMPTY_ROOM, 0).name == WORKERS[EMPTY_ROOM]
    )
    assert_switch_retained(solver, switch, original_time)

    solver.switch_base_products = Mock(wraps=solver.switch_base_products)
    dispatched = ui.dispatch()
    if dispatched is not switch:
        assert dispatched is not None
        assert dispatched.type == ui.tasks.TaskTypes.NOT_SPECIFIC
        assert not dispatched.plan
        assert all(task is not dispatched for task in solver.tasks)
        assert ui.events == [("staffing", EMPTY_ROOM)]
        assert_switch_retained(solver, switch, original_time)
        assert solver.find_next_task(task_type=switch.type) is switch
        assert ui.dispatch() is switch

    assert ui.events == [
        ("staffing", EMPTY_ROOM),
        ("survey", EMPTY_ROOM),
        ("accelerate", EMPTY_ROOM),
        ("change", EMPTY_ROOM),
    ]
    solver.switch_base_products.assert_called_once()
    (batch,) = solver.switch_base_products.call_args.args
    assert len(batch) == 1 and batch[0] is switch
    assert all(task is not switch for task in solver.tasks)
    assert switch.time == original_time


def test_reverted_backup_discards_switch_waiting_for_empty_factory_staffing(
    backup_switch_waiting_for_staffing,
):
    ui, switch, _ = backup_switch_waiting_for_staffing
    solver = ui.solver
    solver.set_detected_party_time(None)
    solver.backup_plan_solver()
    solver.queue_product_switches()

    assert solver.op_data.plan_condition == [False]
    assert solver.op_data.products[EMPTY_ROOM] == "gold"
    assert not any(task.type == switch.type for task in solver.tasks)
    assert ui.events == []


def test_empty_factory_does_not_replace_a_retained_product_failure(base_schedule):
    ui = base_schedule
    switch = ui.add_switch(EMPTY_ROOM)
    original_time = switch.time
    ui.observe_roster(EMPTY_ROOM)
    ui.solver._retain_failed_task(
        switch, "等待原切换依赖", [OTHER_ROOM], dependency=True
    )
    failure = switch.execution_failure

    ui.dispatch()
    ui.observe_roster(EMPTY_ROOM, WORKERS[EMPTY_ROOM])
    ui.dispatch()

    assert ui.events == []
    assert_switch_retained(ui.solver, switch, original_time)
    assert switch.execution_failure is failure
