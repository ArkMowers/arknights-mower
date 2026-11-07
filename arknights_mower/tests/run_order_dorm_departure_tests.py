"""连续跑单前先补齐源宿舍，失败保留原跑单而不开始贸易站插拔。"""

import copy
import pickle
from datetime import timedelta

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests import dorm_recovery_tests
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.tests.run_order_restoration_tests import prepare_order
from arknights_mower.utils import resting_priority
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskScope,
    TaskTypes,
    task_view,
    try_add_release_dorm,
)

DORM = "dormitory_1"
TRADE = "room_1_1"
reordering_solver = dorm_recovery_tests.solver


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


@pytest.mark.parametrize(
    "upper,mood,resident_mood,allowed",
    [
        (24, 21, 10, False),
        (24, 19.3, 10, False),
        (24, 19.2, 10, True),
        (24, 5, 10, True),
        (12, 9.7, 10, False),
        (12, 9.6, 10, True),
        (24, 21, 24, True),
        (24, 21, None, True),
    ],
)
def test_completed_order_keeps_normal_replacement_takeover_threshold(
    orders, monkeypatch, upper, mood, resident_mood, allowed
):
    solver, first, _, events = orders
    solver.op_data.plan[TRADE][0].replacement.append("但书")

    solver.agent_arrange(first.plan)

    assert len(events) == 4
    assert solver.op_data.get_current_room(DORM, True)[2] == "红"
    assert solver.op_data.operators["但书"].current_room == ""
    data = solver.op_data
    if resident_mood is None:
        row = data.get_current_room(DORM, True)
        row[2] = ""
        data = data.project_arrangements([{DORM: row}])
    else:
        data.operators["红"].mood = resident_mood
        data.operators["红"].time_stamp = NOW
        data.operators["红"].mood_is_prediction = False
    data._projection_now = NOW
    operator = data.operators["但书"]
    operator.upper_limit, operator.mood, operator.time_stamp = upper, mood, NOW
    operator.mood_is_prediction = False
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
    future = SchedulerTask(
        time=NOW + timedelta(hours=1),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={TRADE: ["但书", "Current"]},
        meta_data=TRADE,
    )
    tasks = [future]
    try_add_release_dorm(
        {},
        None,
        data,
        tasks,
        reserved_slots={bed.position for bed in data.dorm if bed.position != (DORM, 2)},
    )

    assert any("但书" in task.plan.get(DORM, ()) for task in tasks) == allowed
    assert data.get_current_room(DORM, True)[2] == (
        "" if resident_mood is None else "红"
    )
    assert operator.current_room == ""
    assert not hasattr(first, "run_order_dorm_original")


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
    assert first.plan == original["plan"]
    assert first.time == original["time"]
    assert first.run_order_dorm_slots == {DORM: {2}}


def test_preparation_does_not_create_trade_confirmation_for_dormitory(orders):
    solver, first, _, _ = orders
    first.run_order_confirmation_pending = {"room": TRADE, "submitted": False}
    before = copy.deepcopy(first.run_order_confirmation_pending)

    solver._prepare_run_order_confirmation(DORM, ["红"])

    assert first.run_order_confirmation_pending == before


@pytest.mark.parametrize("unknown_index", [0, 2])
def test_unknown_source_ocr_cannot_confirm_preparation_or_release_order(
    orders, unknown_index
):
    solver, first, _, events = orders
    read = solver.get_agent_from_room.side_effect

    def unknown(room, *args, **kwargs):
        rows = read(room, *args, **kwargs)
        if room == DORM:
            rows[unknown_index] = {"agent": "", "observed": False}
        return rows

    solver.get_agent_from_room.side_effect = unknown
    original_time = first.time
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver.agent_arrange(first.plan)

    assert events == []
    assert first.time == original_time
    assert first.plan == {TRADE: ["但书", COVERS[1]]}
    assert solver.op_data.get_current_room(DORM, True)[2] == "但书"


def test_unconfirmed_final_ocr_keeps_roster_until_confirmed_without_reselection(orders):
    solver, first, _, events = orders
    read = solver.get_agent_from_room.side_effect
    reads = 0

    def unknown_final(room, *args, **kwargs):
        nonlocal reads
        rows = read(room, *args, **kwargs)
        if room == DORM:
            reads += 1
            if reads >= 3:
                rows[2] = {"agent": "", "observed": False}
        return rows

    solver.get_agent_from_room.side_effect = unknown_final
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver.agent_arrange(first.plan)
    assert len(events) == 1 and events[0][0] == DORM
    assert first.run_order_dorm_plan[DORM][2] == "红"
    solver.get_agent_from_room.side_effect = read

    solver.agent_arrange(first.plan)

    assert sum(room == DORM for room, _ in events) == 1
    assert events[1][0] == TRADE
    assert not getattr(first, "run_order_dorm_plan", {})


def test_confirmed_vacancy_at_cached_source_position_still_requires_filling(orders):
    solver, first, _, events = orders
    read = solver.get_agent_from_room.side_effect
    observed = False

    def vacancy(room, *args, **kwargs):
        nonlocal observed
        if room == DORM and not observed:
            observed = True
            row = solver.op_data.get_current_room(DORM, True)
            row[2] = ""
            solver.op_data = solver.op_data.project_arrangements([{DORM: row}])
        return read(room, *args, **kwargs)

    solver.get_agent_from_room.side_effect = vacancy
    solver.agent_arrange(first.plan)

    assert events[0][0] == DORM and events[0][1][2] == "红"
    assert events[1][0] == TRADE


def test_partial_reordering_keeps_full_roster_through_saved_retry(orders):
    solver, first, _, events = orders
    original_time = first.time
    final = ["冰酿", "闪灵", "红", COVERS[2], "龙舌兰"]
    cleared = ["冰酿", "闪灵", "红", "", ""]
    attempted = False

    def reorder(room, agents, **kwargs):
        nonlocal attempted
        if room != DORM or attempted:
            return False
        attempted = True
        agents[:] = final
        solver.task.dorm_recovery_restore = [DORM]
        solver.op_data = solver.op_data.project_arrangements([{DORM: cleared}])
        events.append(("temporary_clear", cleared))
        raise base_schedule.RoomArrangementDeferred(
            DORM, base_schedule.AgentSelectionNotReady("补回其余恢复住客失败")
        )

    solver.ensure_dorm_recovery_order.side_effect = reorder
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver.agent_arrange(first.plan)
    names, slots = retained_task_reservations(solver.op_data, [first])
    assert {COVERS[2], "龙舌兰"} <= names
    assert {(DORM, 3), (DORM, 4)} <= slots
    restored = pickle.loads(pickle.dumps(first))
    solver.task, solver.tasks[0] = restored, restored

    solver.agent_arrange(restored.plan)

    assert events[1] == (DORM, final)
    assert events[2][0] == TRADE
    assert solver.op_data.get_current_room(DORM, True) == final
    assert restored.time == original_time and restored.plan == {}
    assert not getattr(restored, "dorm_recovery_restore", ())


@pytest.mark.parametrize("stale_staffing_wait", [False, True])
def test_released_candidate_observation_resumes_same_failed_preparation(
    orders, stale_staffing_wait
):
    solver, first, _, events = orders
    first.run_order_staffing_wait = stale_staffing_wait
    data = solver.op_data
    for name in ("红", "空爆"):
        data.operators[name].current_room = "room_9_9"
    choose = solver.choose_agent.side_effect

    def unavailable(*args, **kwargs):
        raise base_schedule.AgentSelectionNotReady("没有空闲补位候选")

    solver.choose_agent.side_effect = unavailable
    with pytest.raises(base_schedule.RoomArrangementDeferred) as failure:
        solver.agent_arrange(first.plan)
    assert not getattr(first, "run_order_staffing_wait", False)
    solver._retain_failed_task(first, str(failure.value), [DORM])
    original_time = first.time
    source_revision = copy.deepcopy(data.room_observations)
    unrelated = SchedulerTask(time=NOW, task_type=TaskTypes.DEPOT)
    solver.tasks.append(unrelated)
    for _ in range(3):
        solver._resume_failed_tasks()
        assert first not in task_view(solver.tasks, TaskScope.DISPATCH, data)
        assert unrelated in task_view(solver.tasks, TaskScope.DISPATCH, data)
    data.operators["空爆"].time_stamp = NOW + timedelta(seconds=1)
    solver._resume_failed_tasks()
    assert first.execution_failure
    data.operators["红"].current_room = ""
    data.operators["红"].current_index = -1
    data.operators["红"].time_stamp = NOW + timedelta(seconds=1)
    assert data.room_observations == source_revision

    solver._resume_failed_tasks()

    assert not getattr(first, "execution_failure", None)
    assert first in task_view(solver.tasks, TaskScope.DISPATCH, data)
    solver.choose_agent.side_effect = choose
    solver.agent_arrange(first.plan)
    assert events[0][0] == DORM and events[1][0] == TRADE
    assert first.time == original_time and first.plan == {}


def test_final_preparation_read_enters_dorm_before_room_detail_wait(orders):
    solver, first, _, events = orders
    page = {"room": None}
    waits = []
    read = solver.get_agent_from_room.side_effect
    find = solver.find.side_effect
    detail = base_schedule.BaseSchedulerSolver.turn_on_room_detail.__get__(solver)

    def observe(room, *args, **kwargs):
        detail(room)
        assert page["room"] == room
        return read(room, *args, **kwargs)

    def locate(name, *args, **kwargs):
        if name == "room_detail":
            return bool(page["room"])
        if name == "control_central":
            return not page["room"]
        if name in ("connecting", "arrange_check_in", "arrange_check_in_small"):
            return None
        return find(name, *args, **kwargs)

    solver.enter_room.side_effect = lambda room: page.update(room=room)
    solver.back.side_effect = lambda *args: page.update(room=None)
    solver.scene.side_effect = lambda: (
        Scene.INFRA_DETAILS if page["room"] else Scene.INFRA_MAIN
    )
    solver.find.side_effect = locate
    solver.get_color = lambda *args: np.array([255, 255, 255])
    solver.sleep.side_effect = lambda interval=1: waits.append(interval)
    solver.get_agent_from_room.side_effect = observe

    assert solver._prepare_run_order_dorm_departures(first.plan)

    assert events == [(DORM, ["冰酿", "闪灵", "红", "龙舌兰", COVERS[2]])]
    assert waits == []
    assert page["room"] is None
    assert not getattr(first, "run_order_dorm_plan", {})


@pytest.mark.parametrize("returning", [False, True])
def test_saved_preparation_ignores_stale_trade_staffing_wait(orders, returning):
    solver, first, _, events = orders
    data = solver.op_data
    choose = solver.choose_agent.side_effect
    for name in ("红", "空爆"):
        data.operators[name].current_room = "room_9_9"

    def unavailable(*args, **kwargs):
        raise base_schedule.AgentSelectionNotReady("没有空闲补位候选")

    solver.choose_agent.side_effect = unavailable
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver.agent_arrange(first.plan)
    # 兼容旧版保存的未完成补床和残留贸易缺员标志。
    first.run_order_staffing_wait = True
    solver._retain_failed_task(first, "预补床缺少候选", [DORM])
    restored = pickle.loads(pickle.dumps(first))
    solver.task, solver.tasks[0] = restored, restored
    original_time = restored.time
    reservation_args = {"returning_names": ("红",)} if returning else {}
    names, slots = retained_task_reservations(data, [restored], **reservation_args)
    assert {"龙舌兰", COVERS[2]} <= names
    assert {(DORM, 3), (DORM, 4)} <= slots
    unrelated = SchedulerTask(time=NOW, task_type=TaskTypes.DEPOT)
    solver.tasks.append(unrelated)
    for _ in range(3):
        solver._resume_failed_tasks()
        ready = task_view(solver.tasks, TaskScope.DISPATCH, data)
        assert restored not in ready and unrelated in ready
    source_observations = copy.deepcopy(data.room_observations)
    data.operators["红"].current_room = ""
    data.operators["红"].current_index = -1
    data.operators["红"].time_stamp = NOW + timedelta(seconds=1)

    solver._resume_failed_tasks()

    assert data.room_observations == source_observations
    assert not getattr(restored, "execution_failure", None)
    assert restored in task_view(solver.tasks, TaskScope.DISPATCH, data)
    assert solver.task is restored and restored.time == original_time
    solver.choose_agent.side_effect = choose
    solver.agent_arrange(restored.plan)
    assert events[0][0] == DORM and events[1][0] == TRADE
    assert restored.plan == {} and restored.time == original_time
    assert not getattr(restored, "run_order_staffing_wait", False)


def test_stale_trade_staffing_wait_cannot_discard_unfinished_dorm_preparation(
    orders, monkeypatch
):
    solver, first, _, _ = orders
    first.run_order_staffing_wait = True
    first.run_order_dorm_plan = {DORM: ["冰酿", "闪灵", "Free", "龙舌兰", COVERS[2]]}
    first.execution_retained = True
    solver.op_data.run_order_rooms = {}
    monkeypatch.setattr(solver.op_data, "refresh_run_order_rooms", lambda: None)

    solver._sync_run_order_tasks()

    assert first in solver.tasks


def test_real_single_recovery_clear_resumes_full_preparation_roster(
    reordering_solver, monkeypatch
):
    solver = reordering_solver
    final = ["杜林", "琴柳", "红", "银灰", "陈"]
    solver.op_data.add(Operator("但书", "", mood=5))
    solver.physical = ["杜林", "琴柳", "红", "但书", "银灰"]
    read = solver.get_agent_from_room.side_effect

    def observe(room=DORM, *args, **kwargs):
        kwargs.pop("strict_observation", None)
        return read(room, *args, **kwargs)

    solver.get_agent_from_room.side_effect = observe
    solver.get_agent_from_room(DORM)
    task = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={TRADE: ["但书"]}, meta_data=TRADE
    )
    solver.task, solver.tasks = task, [task]

    def prepared(agents, room, **kwargs):
        # 给定合法最终阵容，保留生产单回排序、清房与补回流程。
        agents[:] = final
        return []

    monkeypatch.setattr(solver, "prepare_dorm_selection", prepared)
    confirm = solver.tap_confirm.side_effect
    failed = False

    def fail_after_clear(room, new_plan):
        nonlocal failed
        if solver.confirms and not failed:
            failed = True
            raise base_schedule.RoomArrangementDeferred(
                DORM, RuntimeError("最终补回失败")
            )
        confirm(room, new_plan)

    solver.tap_confirm.side_effect = fail_after_clear
    with pytest.raises(base_schedule.RoomArrangementDeferred):
        solver._prepare_run_order_dorm_departures(task.plan)

    assert len(solver.confirms) == 1 and solver.physical[-1] == ""
    assert task.run_order_dorm_plan == {DORM: final}
    names, _ = retained_task_reservations(solver.op_data, [task])
    assert {"红", "陈"} <= names
    restored = pickle.loads(pickle.dumps(task))
    solver.task, solver.tasks = restored, [restored]

    assert solver._prepare_run_order_dorm_departures(restored.plan)

    assert solver.physical == final
    assert len(solver.confirms) == 2
    assert not getattr(restored, "run_order_dorm_plan", {})
    assert not getattr(restored, "dorm_recovery_restore", ())
    assert restored.plan == {TRADE: ["但书"]}
    assert restored.time == task.time
