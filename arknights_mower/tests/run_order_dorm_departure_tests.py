"""连续跑单前先补齐源宿舍，失败保留原跑单而不开始贸易站插拔。"""

import copy
import pickle
from datetime import timedelta

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.run_order_restoration_tests import prepare_order
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
)

DORM = "dormitory_1"
TRADE = "room_1_1"


@pytest.fixture
def orders(solver, monkeypatch):
    first, _ = prepare_order(solver, monkeypatch)
    data = solver.op_data
    for name in ("龙舌兰", "红", "空爆"):
        data.add(Operator(name, "", mood=10, time_stamp=NOW))
    dorm_row = ["冰酿", "闪灵", "但书", "龙舌兰", COVERS[2]]
    solver.op_data = data.project_arrangements([{DORM: dorm_row}])
    second = SchedulerTask(
        time=NOW + timedelta(seconds=1),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_2": ["龙舌兰"]},
        meta_data="room_1_2",
        adjusted=True,
    )
    solver.tasks.append(second)
    events, chosen = [], {}
    fillers = iter(("红", "空爆"))

    def choose(row, room, **kwargs):
        for index, name in enumerate(row):
            if name == "Free":
                row[index] = next(fillers)
        chosen[room] = row.copy()

    def confirm(room, new_plan):
        events.append((room, chosen[room].copy()))
        solver.op_data = solver.op_data.project_arrangements([{room: chosen[room]}])

    solver.choose_agent.side_effect = choose
    solver.tap_confirm.side_effect = confirm
    solver.drone.side_effect = lambda *a, **k: events.append(("order", []))
    return solver, first, second, events


def test_consecutive_orders_replace_each_dorm_occupant_before_insertion(orders):
    solver, first, second, events = orders
    original_times = first.time, second.time

    solver.agent_arrange(first.plan)

    assert events[:4] == [
        (DORM, ["冰酿", "闪灵", "红", "龙舌兰", COVERS[2]]),
        (TRADE, ["但书", COVERS[1]]),
        ("order", []),
        (TRADE, [COVERS[0], COVERS[1]]),
    ]
    assert first.plan == {}
    assert all(solver.op_data.get_current_room(DORM, True))
    solver.tasks.remove(first)
    solver.task = second

    solver.agent_arrange(second.plan)

    assert events[4:] == [
        (DORM, ["冰酿", "闪灵", "红", "空爆", COVERS[2]]),
        ("room_1_2", ["龙舌兰"]),
        ("order", []),
        ("room_1_2", [PRIMARY[1]]),
    ]
    assert all(solver.op_data.get_current_room(DORM, True))
    assert (first.time, second.time) == original_times
    assert second.plan == {}
    assert not hasattr(first, "run_order_original_roster")
    assert not hasattr(second, "run_order_original_roster")


def test_dorm_preparation_failure_preserves_order_and_resumes_after_restart(orders):
    solver, first, _, events = orders
    original_time = first.time
    trade_plan = copy.deepcopy(first.plan)
    choose = solver.choose_agent.side_effect

    def unavailable(*args, **kwargs):
        raise base_schedule.AgentSelectionNotReady("未找到可替换的 Free 干员")

    solver.choose_agent.side_effect = unavailable
    with pytest.raises(base_schedule.RoomArrangementDeferred) as failure:
        solver.agent_arrange(first.plan)

    assert failure.value.room == DORM
    assert events == []
    assert first.time == original_time
    assert first.plan[TRADE] == trade_plan[TRADE]
    assert first.plan == trade_plan
    assert first.run_order_dorm_slots == {DORM: {2}}
    assert not hasattr(first, "run_order_original_roster")
    assert solver.op_data.get_current_room(DORM, True)[2] == "但书"

    solver._retain_failed_task(first, str(failure.value), [DORM])
    unrelated = SchedulerTask(time=NOW, task_type=TaskTypes.DEPOT)
    solver.tasks.append(unrelated)
    remaining = copy.deepcopy(first.plan)
    for _ in range(3):
        solver._resume_failed_tasks()
        dispatchable = task_view(solver.tasks, TaskScope.DISPATCH, solver.op_data)
        assert first not in dispatchable
        assert unrelated in dispatchable
        assert first.plan == remaining and first.time == original_time

    restored = pickle.loads(pickle.dumps(first))
    solver.task = restored
    solver.tasks[0] = restored
    solver.op_data.operators["但书"].time_stamp = NOW + timedelta(seconds=1)
    solver._resume_failed_tasks()
    assert not getattr(restored, "execution_failure", None)
    solver.choose_agent.side_effect = choose
    solver.agent_arrange(restored.plan)

    assert events[0][0] == DORM
    assert events[1][0] == TRADE
    assert restored.plan == {} and restored.time == original_time
    assert not hasattr(restored, "run_order_dorm_slots")
    assert first.plan[TRADE] == trade_plan[TRADE]
    assert all(solver.op_data.get_current_room(DORM, True))


def test_new_occupant_observation_does_not_evict_unrelated_resident(orders):
    solver, first, _, events = orders
    original = solver.get_agent_from_room.side_effect

    def observe(room, *args, **kwargs):
        if room == DORM:
            solver.op_data = solver.op_data.project_arrangements(
                [{DORM: ["冰酿", "闪灵", "红", "龙舌兰", COVERS[2]]}]
            )
        return original(room, *args, **kwargs)

    solver.get_agent_from_room.side_effect = observe
    solver.agent_arrange(first.plan)

    assert events[0][0] == TRADE
    assert not any(room == DORM for room, _ in events)
    assert solver.op_data.get_current_room(DORM, True)[2] == "红"


def test_saved_source_bed_is_filled_even_if_departing_operator_is_already_idle(orders):
    solver, first, _, events = orders
    first.run_order_dorm_slots = {DORM: {2}}
    solver.op_data = solver.op_data.project_arrangements(
        [{DORM: ["冰酿", "闪灵", "", "龙舌兰", COVERS[2]]}]
    )
    assert solver.op_data.operators["但书"].current_room == ""

    solver.agent_arrange(first.plan)

    assert events[0] == (DORM, ["冰酿", "闪灵", "红", "龙舌兰", COVERS[2]])
    assert events[1][0] == TRADE
    assert not hasattr(first, "run_order_dorm_slots")


def test_incomplete_source_observation_preserves_order_without_insertion(orders):
    solver, first, _, events = orders
    read = solver.get_agent_from_room.side_effect
    solver.get_agent_from_room.side_effect = lambda room, *a, **k: (
        [] if room == DORM else read(room, *a, **k)
    )
    original = copy.deepcopy(first.__dict__)

    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver.agent_arrange(first.plan)

    assert events == []
    assert first.__dict__ == original


def test_preparation_does_not_create_trade_confirmation_for_dormitory(orders):
    solver, first, _, _ = orders
    first.run_order_confirmation_pending = {"room": TRADE, "submitted": False}
    before = copy.deepcopy(first.run_order_confirmation_pending)

    solver._prepare_run_order_confirmation(DORM, ["红"])

    assert first.run_order_confirmation_pending == before
