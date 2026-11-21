"""延后普通清退前补齐下一单，读取责任不能随大型任务一起推迟。"""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as admission

staffed_order = admission.staffed_order


@pytest.fixture
def pending_orders(staffed_order, monkeypatch):
    from arknights_mower.solvers import manual_tasks

    ui = staffed_order
    solver = ui.solver
    monkeypatch.setattr(manual_tasks, "datetime", ui.clock)
    ui.config.conf.maa_rg_enable = True
    for room, name in (("room_1_1", "鸿雪"), ("room_2_2", "图耶")):
        ui.occupants[room] = [name]
        solver.get_agent_from_room(room)
        ui.states[room] = "active"
    ui.release = ui.task(
        time=ui.clock.now() - timedelta(minutes=5),
        task_type=ui.task_type.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current"] * 4 + ["Free"]},
    )
    ui.later = ui.task(
        time=ui.clock.now() + timedelta(hours=3),
        task_type=ui.task_type.FIAMMETTA,
    )
    solver.tasks = [ui.release, ui.later]
    solver.back_to_infrastructure = MagicMock()
    solver.maa_plan_solver = MagicMock(
        side_effect=lambda tasks: ui.events.append(("maa", tasks, ui.clock.now()))
    )
    ui.manual = manual_tasks
    return ui


def orders(ui):
    return {
        task.meta_data: task
        for task in ui.solver.tasks
        if task.type == ui.task_type.RUN_ORDER
    }


def test_missing_next_orders_are_read_before_maa_without_releasing_dorm(pending_orders):
    ui = pending_orders
    release_time = ui.release.time
    release_plan = ui.release.plan.copy()

    assert ui.manual.run_long_task_if_dorm_pending(ui.solver)

    assert set(orders(ui)) == {"room_1_1", "room_2_2"}
    for room, task in orders(ui).items():
        assert task.time == ui.deadlines[room] - timedelta(minutes=3)
        assert len(admission.reads(ui, room)) == 1
        assert ui.events.index(admission.reads(ui, room)[0]) < next(
            i for i, event in enumerate(ui.events) if event[0] == "maa"
        )
    assert ui.release in ui.solver.tasks
    assert ui.release.time == release_time and ui.release.plan == release_plan
    ui.solver.tap_confirm.assert_not_called()
    assert not any(t.type == ui.task_type.REFRESH_TIME for t in ui.solver.tasks)

    assert ui.manual.run_long_task_if_dorm_pending(ui.solver)
    assert len(admission.reads(ui)) == len(admission.reads(ui, "room_2_2")) == 1


def test_existing_order_is_kept_while_only_missing_station_is_read(pending_orders):
    ui = pending_orders
    ui.solver.plan_run_order("room_2_2")
    existing = orders(ui)["room_2_2"]
    existing_time = existing.time

    assert ui.manual.run_long_task_if_dorm_pending(ui.solver)

    assert orders(ui)["room_2_2"] is existing
    assert existing.time == existing_time
    assert len(admission.reads(ui)) == len(admission.reads(ui, "room_2_2")) == 1


@pytest.mark.parametrize("minutes", [3, 10])
def test_newly_read_near_order_prevents_maa_start(pending_orders, minutes):
    ui = pending_orders
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=minutes)

    assert not ui.manual.run_long_task_if_dorm_pending(ui.solver)

    assert orders(ui)["room_1_1"].time == ui.deadlines["room_1_1"] - timedelta(
        minutes=3
    )
    ui.solver.maa_plan_solver.assert_not_called()


def test_near_shift_runs_before_reading_orders(pending_orders):
    ui = pending_orders
    shift = ui.task(
        time=ui.clock.now() + timedelta(seconds=30),
        task_type=ui.task_type.SHIFT_OFF,
        task_plan={"room_1_1": ["但书"]},
    )
    ui.solver.tasks.append(shift)

    assert not ui.manual.run_long_task_if_dorm_pending(ui.solver)

    assert not admission.reads(ui)
    assert ui.solver.tasks == [ui.release, ui.later, shift]
    ui.solver.maa_plan_solver.assert_not_called()


def test_failed_read_retains_one_request_and_does_not_start_or_repeat(pending_orders):
    ui = pending_orders
    read = ui.solver.read_time.side_effect
    attempts = []

    def fail(*args, **kwargs):
        if ui.solver._page["room"] == "room_1_1":
            attempts.append(ui.clock.now())
            raise ui.base.RecognizeError("订单数字未确认")
        return read(*args, **kwargs)

    ui.solver.read_time.side_effect = fail
    assert not ui.manual.run_long_task_if_dorm_pending(ui.solver)
    refresh = next(t for t in ui.solver.tasks if t.type == ui.task_type.REFRESH_TIME)
    original_time = refresh.time
    for _ in range(3):
        assert not ui.manual.run_long_task_if_dorm_pending(ui.solver)

    assert attempts == [original_time]
    assert refresh.execution_failure and refresh.time == original_time
    assert [t for t in ui.solver.tasks if t.type == ui.task_type.REFRESH_TIME] == [
        refresh
    ]
    assert set(orders(ui)) == {"room_2_2"}
    ui.solver.maa_plan_solver.assert_not_called()


@pytest.mark.parametrize(
    "flag", ["defer_backup_plan_until_mood_read", "_initial_staffing_pending"]
)
def test_startup_observations_cannot_be_bypassed_by_long_task(pending_orders, flag):
    ui = pending_orders
    setattr(ui.solver, flag, True)
    assert not ui.manual.run_long_task_if_dorm_pending(ui.solver)
    assert not admission.reads(ui)
    ui.solver.maa_plan_solver.assert_not_called()


def test_completed_run_order_with_due_release_gets_successor_before_maa(pending_orders):
    ui = pending_orders
    solver = ui.solver
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(seconds=30)
    completed = solver._new_run_order_task("room_1_1", ui.clock.now())
    solver.tasks.insert(0, completed)
    solver.task = completed
    solver.planned = solver.todo_task = solver.collect_notification = False

    solver.infra_main()

    assert completed not in solver.tasks
    assert solver.op_data.get_current_room("room_1_1", True) == ["鸿雪"]
    solver.accept_order.assert_called_once()
    assert not orders(ui)
    assert ui.release in solver.tasks
    solver.infra_main()
    assert solver.planned and not orders(ui)
    assert ui.manual.run_long_task_if_dorm_pending(solver)
    assert "room_1_1" in orders(ui)
    assert orders(ui)["room_1_1"].time == ui.deadlines["room_1_1"] - timedelta(
        minutes=3
    )


def test_maa_stops_for_newly_read_order(pending_orders, monkeypatch):
    from arknights_mower.tests import long_task_dorm_tests

    ui = pending_orders
    ui.now = ui.clock.now()
    del ui.solver.maa_plan_solver
    solver = long_task_dorm_tests.maa_solver.__wrapped__(ui, monkeypatch)

    def tick(_):
        assert "room_1_1" in orders(ui)
        ui.clock.current = orders(ui)["room_1_1"].time - timedelta(seconds=25)

    monkeypatch.setattr(ui.base, "csleep", tick)

    assert ui.manual.run_long_task_if_dorm_pending(solver)

    solver.MAA.start.assert_called_once()
    solver.maa_stop.assert_called_once()
    assert ui.clock.now() < orders(ui)["room_1_1"].time
