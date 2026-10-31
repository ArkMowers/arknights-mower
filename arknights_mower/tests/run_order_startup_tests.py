"""启动订单检查只发布临近跑单，实际驻员心情供首次全设施扫描复用。"""

import copy
import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as admission

staffed_order = admission.staffed_order


def prepare(ui):
    solver = ui.solver
    solver._startup_run_order_check_pending = True
    solver._startup_mood_observations = {}
    solver._state_restore_complete = True
    ui.occupants.update({"room_1_1": ["孑"], "room_2_2": ["图耶"]})
    ui.states.update({"room_1_1": "active", "room_2_2": "active"})
    return solver


def orders(ui):
    return [task for task in ui.solver.tasks if task.type == ui.task_type.RUN_ORDER]


@pytest.mark.parametrize(
    "delay,minutes,urgent",
    [(3, 10, True), (3, 10.1, False), (8, 16, True), (8, 16.1, False)],
)
def test_startup_checks_all_stations_once_and_publishes_only_urgent(
    staffed_order, delay, minutes, urgent
):
    ui = staffed_order
    solver = prepare(ui)
    ui.config.conf.run_order_delay = delay
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=minutes + delay)
    solver._check_startup_run_orders()
    assert {task.meta_data for task in orders(ui)} == (
        {"room_1_1"} if urgent else set()
    )
    assert len(admission.reads(ui)) == len(admission.reads(ui, "room_2_2")) == 1
    assert not any(task.type == ui.task_type.REFRESH_TIME for task in solver.tasks)
    restored = pickle.loads(pickle.dumps(solver.tasks))
    assert {task.meta_data for task in restored} == ({"room_1_1"} if urgent else set())
    solver.tasks.clear()
    solver._check_startup_run_orders()
    assert len(admission.reads(ui)) == 1


@pytest.mark.parametrize("retained", [False, True])
def test_existing_order_including_restoration_consumes_startup_check(
    staffed_order, retained
):
    ui = staffed_order
    solver = prepare(ui)
    task = ui.task(task_type=ui.task_type.RUN_ORDER, task_plan={"room_1_1": ["鸿雪"]})
    if retained:
        task.run_order_restore_pending = True
        task.execution_retained = True
    solver.tasks.append(task)
    solver._check_startup_run_orders()
    solver.tasks.clear()
    solver._check_startup_run_orders()
    assert not admission.reads(ui)


@pytest.mark.parametrize("maintenance", ["entry", "replacement"])
def test_maintenance_does_not_start_ordinary_order_checks(staffed_order, maintenance):
    ui = staffed_order
    solver = prepare(ui)
    if maintenance == "entry":
        solver.maintenance_entry_pending = True
    else:
        task = ui.task(task_type=ui.task_type.SELF_CORRECTION)
        task.maintenance_replacement_run = True
        solver.tasks.append(task)
    solver._check_startup_run_orders()
    assert not admission.reads(ui) and not orders(ui)


@pytest.mark.parametrize("state", ["paused", "unreadable"])
def test_incomplete_startup_order_does_not_create_refresh_or_block_other_stations(
    staffed_order, state
):
    ui = staffed_order
    solver = prepare(ui)
    if state == "paused":
        ui.states["room_1_1"] = "paused"
    else:
        read = solver.read_time.side_effect

        def unreadable(*args, **kwargs):
            if solver._page["room"] == "room_1_1":
                raise ui.base.RecognizeError("订单未核实")
            return read(*args, **kwargs)

        solver.read_time.side_effect = unreadable
    solver._check_startup_run_orders()
    assert not solver.tasks
    assert len(admission.reads(ui, "room_2_2")) == 1
    assert "room_1_1" in solver._startup_mood_observations
    assert [call.args[0] for call in solver.get_agent_from_room.call_args_list].count(
        "room_1_1"
    ) == 1


@pytest.mark.parametrize("shortage", [False, True])
def test_shared_drone_adjustment_uses_temporary_tasks_and_returns_to_main(
    staffed_order, shortage
):
    ui = staffed_order
    solver = prepare(ui)
    solver.drone_room = "room_1_1"
    ui.deadlines.update(
        {room: ui.clock.now() + timedelta(minutes=8) for room in ui.states}
    )
    solver.recog.gray = MagicMock()
    solver.digit_reader = MagicMock()
    solver.digit_reader.get_drone.return_value = 20 if shortage else 100
    solver.double_read_time = MagicMock(
        return_value=ui.clock.now() + timedelta(minutes=3)
    )

    def adjust(room, *, adjust_time, order_tasks):
        assert not solver.tasks
        assert len(pickle.loads(pickle.dumps(solver.tasks))) == 0
        solver.enter_room(room)
        return solver.adjust_order_time(True, room, order_tasks=order_tasks)

    solver.drone = MagicMock(side_effect=adjust)
    solver._check_startup_run_orders()
    assert solver.drone.call_count == 1
    assert len(orders(ui)) == 2
    first = next(task for task in orders(ui) if task.meta_data == "room_1_1")
    assert first.time == ui.clock.now() + timedelta(minutes=5 if shortage else 0)
    assert solver.scene_graph_navigation.call_args.args[0] == ui.base.Scene.INFRA_MAIN
    assert not solver._page["open"]


def test_startup_urgent_order_yields_and_resumes_same_arrangement(staffed_order):
    ui = staffed_order
    solver = prepare(ui)
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=3)
    original = admission.correction(ui)
    original_time, original_plan = original.time, copy.deepcopy(original.plan)
    solver.infra_main()
    assert solver.task is None
    assert any(task is original for task in solver.tasks)
    assert original.time == original_time and original.plan == original_plan
    assert not any(event[0] == "staffed" for event in ui.events)
    solver.task = next(task for task in orders(ui) if task.meta_data == "room_1_1")
    solver.infra_main()
    assert not orders(ui)
    assert original.time == original_time and original.plan == original_plan
    solver.task = original
    solver.infra_main()
    assert original.plan == {} and original.time == original_time


@pytest.mark.parametrize("changed", [False, True])
def test_initial_mood_scan_reuses_only_unchanged_strict_startup_observation(
    staffed_order, monkeypatch, changed
):
    ui = staffed_order
    solver = prepare(ui)
    solver.defer_backup_plan_until_mood_read = True
    monkeypatch.setattr(ui.config.conf, "test_mood_calculation", True)
    read_room = solver.get_agent_from_room.side_effect

    def low_mood(room, *args, **kwargs):
        result = read_room(room, *args, **kwargs)
        if room == "room_1_1":
            solver.op_data.operators["孑"].mood = 3
            result[0]["mood"] = 3
        return result

    solver.get_agent_from_room.side_effect = low_mood
    solver._check_startup_run_orders()
    assert solver.get_agent_from_room.call_args_list[0].kwargs == {
        "force_mood": True,
        "strict_observation": True,
    }
    operator = solver.op_data.operators["孑"]
    if changed:
        operator.current_room = ""
    monkeypatch.setattr(ui.base, "base_room_list", ["room_1_1", "room_2_2"])
    solver.get_agent_from_room.reset_mock()
    solver._read_agent_mood()
    scanned = [call.args[0] for call in solver.get_agent_from_room.call_args_list]
    assert scanned == (["room_1_1"] if changed else [])
    if not changed:
        assert operator.mood == 3 and "孑" in solver._initial_mood_room_observations
    if not changed:
        solver._read_agent_mood()
        assert not solver.get_agent_from_room.call_args_list


def test_startup_future_order_waits_once_without_retiming_unfinished_correction(
    staffed_order, monkeypatch
):
    ui = staffed_order
    solver = prepare(ui)
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=4)
    solver._check_startup_run_orders()
    task = admission.correction(ui)
    original_time = task.time
    assert solver.agent_arrange(task.plan) is False
    remaining = copy.deepcopy(task.plan)
    order = next(
        queued for queued in solver.tasks if queued.type == ui.task_type.RUN_ORDER
    )
    assert order.time == original_time + timedelta(minutes=1)
    assert order.time > ui.clock.now()
    for _ in range(3):
        ui.scheduling.scheduling(solver.tasks, op_data=solver.op_data)
        assert task.time == original_time and task.plan == remaining
        assert len(admission.reads(ui)) == 1
    waited = []

    def idle_sleep(seconds):
        waited.append(seconds)
        assert len(waited) <= 2, "到期订单不能反复等待或阻塞原纠错续行"
        ui.clock.current += timedelta(seconds=seconds)

    transition = solver.transition
    transitions = []

    def bounded_transition():
        transitions.append(ui.clock.now())
        assert len(transitions) <= 12, "已到期订单应结束本轮场景执行"
        return transition()

    monkeypatch.setattr(solver, "_idle_sleep", idle_sleep)
    monkeypatch.setattr(solver, "transition", bounded_transition)
    monkeypatch.setattr(solver, "_fill_empty_dorms", MagicMock())
    monkeypatch.setattr(solver, "handle_error", MagicMock(return_value=True))
    monkeypatch.setattr(solver, "check_current_focus", MagicMock())

    solver.run()

    assert waited == [60]
    assert solver.accept_order.call_count == 1
    assert task.time == original_time and task.plan == remaining
    assert len(admission.reads(ui)) == 1


def test_incomplete_strict_mood_is_not_reused_and_does_not_block_other_station(
    staffed_order,
):
    ui = staffed_order
    solver = prepare(ui)
    read_room = solver.get_agent_from_room.side_effect

    def incomplete(room, *args, **kwargs):
        if room == "room_1_1":
            raise ui.base.RecognizeError("槽位心情未核实")
        return read_room(room, *args, **kwargs)

    solver.get_agent_from_room.side_effect = incomplete
    solver._check_startup_run_orders()
    assert "room_1_1" not in solver._startup_mood_observations
    assert not admission.reads(ui)
    assert len(admission.reads(ui, "room_2_2")) == 1
    assert not solver.tasks


def test_stale_startup_mood_does_not_bypass_normal_refresh(staffed_order, monkeypatch):
    ui = staffed_order
    solver = prepare(ui)
    solver.defer_backup_plan_until_mood_read = True
    solver._check_startup_run_orders()
    ui.clock.current += timedelta(hours=3)
    monkeypatch.setattr(ui.base, "base_room_list", ["room_1_1", "room_2_2"])
    solver.get_agent_from_room.reset_mock()
    solver._read_agent_mood()
    assert {call.args[0] for call in solver.get_agent_from_room.call_args_list} == {
        "room_1_1",
        "room_2_2",
    }
