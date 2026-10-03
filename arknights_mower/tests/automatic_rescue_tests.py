"""智能救急的临时驻员、实测退出和普通收取的离线契约。"""

import copy
import ctypes
import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import emergency
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import config, emergency_recovery
from arknights_mower.utils.emergency_recovery import (
    NativeProjection,
    history_rate,
    mood_context,
    recovery_target,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(emergency, "datetime", Clock)
    monkeypatch.setattr(emergency_recovery, "datetime", Clock)
    monkeypatch.setattr(emergency, "emergency_mood_history", lambda name: [])
    monkeypatch.setattr(emergency, "save_current_state", lambda: True)
    monkeypatch.setattr(emergency, "try_workshop_tasks", MagicMock())


def setup_startup(solver):
    solver._emergency_read_rooms = MagicMock()
    solver._read_initial_card_mood = MagicMock()
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver._emergency_schedule_staffing = MagicMock()
    solver.run_order_solver = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_collect = MagicMock()
    solver._emergency_startup_pending = True
    solver.op_data.config.resting_threshold = 0.65
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 8
    return solver


def make_episode(solver):
    data = solver.op_data
    solver.run_order_solver = MagicMock()
    solver.emergency_state = {
        "phase": "recovering",
        "backup_names": [],
        "frozen_conditions": [],
        "targets": {name: 16 for name in PRIMARY},
        "target_sources": {name: "fallback" for name in PRIMARY},
        "work_contexts": {
            name: mood_context(data, data.operators[name].room) for name in PRIMARY
        },
        "dorm_layout": {
            room: [slot.agent for slot in slots]
            for room, slots in data.plan.items()
            if room.startswith("dorm")
        },
        "next_read": NOW + timedelta(minutes=30),
    }
    solver.last_execution = {"todo": NOW}
    return solver.emergency_state


def test_default_off_and_rescue_line_is_above_zero(solver):
    assert not config.Conf().automatic_rescue_enable
    setup_startup(solver)
    assert solver.op_data.rescue_mood_threshold(
        solver.op_data.operators[PRIMARY[0]]
    ) == pytest.approx(11.7)
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_startup_pending


@pytest.mark.parametrize(
    "projection",
    [
        NativeProjection(NOW + timedelta(minutes=10), True),
        NativeProjection(None, False, "unknown"),
    ],
)
def test_native_opportunity_or_unknown_prevents_temporary_staffing(
    solver, monkeypatch, projection
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    monkeypatch.setattr(emergency, "native_opportunity", lambda *a, **k: projection)
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_not_called()


def test_measured_low_mood_plans_once_and_restart_only_reconciles(solver, monkeypatch):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    monkeypatch.setattr(
        emergency,
        "native_opportunity",
        lambda *a, **k: NativeProjection(None, True, "blocked"),
    )
    solver._emergency_startup()
    assert solver._emergency_active()
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_schedule_staffing.assert_called_once_with(initial=True)
    assert solver.emergency_state["phase"] == "staffing"


@pytest.mark.parametrize("field", ["phase", "targets"])
def test_invalid_persisted_episode_is_rejected_before_device_access(solver, field):
    setup_startup(solver)
    state = make_episode(solver)
    state[field] = "invalid"
    config.conf.automatic_rescue_enable = True
    with pytest.raises(emergency.MowerExit, match="缓存结构不完整"):
        solver._emergency_startup()
    solver._emergency_read_rooms.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


def test_card_estimates_do_not_establish_entry_or_ready(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        op.time_stamp = None
        solver.op_data.dorm_mood_estimates[name] = (0, NOW)
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_not_called()
    make_episode(solver)
    for name in PRIMARY:
        solver.op_data.dorm_mood_estimates[name] = (24, NOW)
    assert not solver._emergency_ready()


@pytest.mark.parametrize("empty_slot", [True, False])
def test_real_room_absence_invalidates_only_departed_resident_reading(
    solver, empty_slot
):
    missing = solver.op_data.operators[PRIMARY[0]]
    untouched = solver.op_data.operators[COVERS[0]]
    room = missing.current_room
    original_stamp = untouched.time_stamp
    solver.recog = SimpleNamespace(
        gray=np.zeros((1080, 1920), dtype=np.uint8), update=MagicMock()
    )
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.find = MagicMock(return_value=empty_slot)
    solver.read_screen = MagicMock(return_value="")
    solver.sleep = MagicMock()
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_read_rooms([room])
    assert missing.current_room == "" and missing.time_stamp is None
    assert untouched.time_stamp == original_stamp
    assert untouched.mood == 24
    make_episode(solver)
    assert not solver._emergency_ready()


def test_actual_targets_are_required_and_no_majority_exit(solver):
    state = make_episode(solver)
    solver.op_data.operators[PRIMARY[-1]].mood = 15
    assert not solver._emergency_ready()
    solver.op_data.operators[PRIMARY[-1]].mood = 16
    assert solver._emergency_ready()
    state["targets"][PRIMARY[-1]] = 25
    assert not solver._emergency_ready()


def test_history_separates_jumps_environment_and_platforms():
    def segment(hour, mood, event=None, key="work", before="room_1_1"):
        return (
            mood,
            (NOW + timedelta(hours=hour)).isoformat(),
            before,
            "room_1_1",
            event,
            key,
            0,
        )

    rows = [segment(i, 20 - 2 * i) for i in range(4)]
    assert history_rate(rows, "room_1_1", "work") == 2
    assert history_rate(rows, "room_1_1", "changed") is None
    for event in (
        "fiammetta_before",
        "fiammetta_after",
        "fiammetta_charge",
        "crafting",
    ):
        modified = [*rows[:2], segment(2, 23, event), rows[-1]]
        assert history_rate(modified, "room_1_1", "work") is None
    assert history_rate([segment(i, 24) for i in range(5)], "room_1_1", "work") is None


def test_context_ignores_inspection_timestamp_but_detects_roster_change(solver):
    data = solver.op_data
    room = data.operators[PRIMARY[0]].room
    data.facility_states[room] = {"product": "gold", "updated_at": "old"}
    before = mood_context(data, room)
    data.facility_states[room]["updated_at"] = "new"
    assert mood_context(data, room) == before
    data.operators[PRIMARY[0]]._current_room = ""
    assert mood_context(data, room) != before


def test_targets_use_individual_rates_and_preserve_infeasible_value(solver):
    data = solver.op_data
    normal = data.resting_mood_threshold(data.operators[PRIMARY[0]])
    assert recovery_target(data, PRIMARY[0]) == (normal + 1, "fallback")
    target, source = recovery_target(data, PRIMARY[0], 2, NOW + timedelta(hours=2), NOW)
    assert target == normal + 5 and source == "history"
    target, _ = recovery_target(data, PRIMARY[0], 10, NOW + timedelta(hours=2), NOW)
    assert target > 24
    data.operators[PRIMARY[0]].exhaust_require = True
    target, _ = recovery_target(data, PRIMARY[0], 4, NOW + timedelta(hours=1), NOW)
    assert target == 5


@pytest.mark.parametrize("last_collection", [None, NOW - timedelta(minutes=16)])
def test_collection_waits_for_mood_check_instead_of_waking_early(
    solver, last_collection
):
    make_episode(solver)
    solver.last_execution["todo"] = last_collection
    solver._emergency_collect = MagicMock()
    solver._emergency_tick()
    check = next(
        task for task in solver.tasks if task.meta_data == emergency.CHECK_META
    )
    assert check.time == NOW + timedelta(minutes=30)
    assert solver.emergency_state["next_read"] == NOW + timedelta(minutes=30)
    solver._emergency_collect.assert_not_called()


@pytest.mark.parametrize("observed", [False, True])
def test_due_mood_check_collects_even_with_paused_order_agents(solver, observed):
    state = make_episode(solver)
    state["next_read"] = NOW
    if observed:
        state["observed_at"] = NOW
    solver.op_data.add(Operator("但书", "", current_room="room_2_1", current_index=0))
    order = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    solver.tasks = [order]
    activity = []
    solver._emergency_collect = MagicMock(
        side_effect=lambda: activity.append("collect")
    )
    solver._emergency_read_rooms = MagicMock(
        side_effect=lambda rooms, **kwargs: activity.append("read")
    )
    solver._emergency_update_targets = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_tick()
    assert activity == (["collect"] if observed else ["collect", "read"])
    assert order not in solver.tasks
    solver._emergency_collect.assert_called_once()


def test_due_mood_check_collects_before_ready_handoff(solver):
    state = make_episode(solver)
    state["next_read"] = NOW
    state["observed_at"] = NOW
    activity = []
    solver._emergency_collect = MagicMock(
        side_effect=lambda: activity.append("collect")
    )
    solver._emergency_update_targets = MagicMock()
    solver._emergency_restore = MagicMock(
        side_effect=lambda: activity.append("restore") or True
    )
    solver._emergency_tick()
    assert activity == ["collect", "restore"]


def test_collection_reuses_todo_and_never_arranges_staff(solver, monkeypatch):
    make_episode(solver)
    solver.last_execution["todo"] = NOW - timedelta(minutes=16)
    solver.recog = SimpleNamespace(update=MagicMock(), img=object())
    solver.tap = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    solver.todo_list = MagicMock()
    solver.agent_arrange = MagicMock()
    monkeypatch.setattr(emergency.detector, "infra_notification", lambda img: (1, 2))
    solver._emergency_collect()
    solver.todo_list.assert_called_once()
    solver.agent_arrange.assert_not_called()


def test_occupied_order_agents_remove_tasks_without_touching_collection(solver):
    make_episode(solver)
    solver.op_data.add(Operator("但书", "", current_room="room_2_1", current_index=0))
    room = solver.op_data.operators[PRIMARY[0]].room
    order = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={room: ["但书"]}, meta_data=room
    )
    check = SchedulerTask(meta_data=emergency.CHECK_META)
    solver.tasks = [order, check]
    solver._emergency_filter_tasks()
    assert solver.tasks == [check]
    assert solver.last_execution["todo"] == NOW


def test_frozen_backup_and_ordinary_shift_are_rejected(solver):
    make_episode(solver)
    assert solver.backup_plan_solver() is False
    plan = {"room_1_1": [PRIMARY[0]]}
    solver.task = SchedulerTask(task_type=TaskTypes.SHIFT_ON, task_plan=plan)
    with pytest.raises(RuntimeError, match="暂停普通工作站"):
        solver.agent_arrange(plan)
    solver.enter_room.assert_not_called()


def test_history_above_rescue_line_does_not_trigger_entry(solver, monkeypatch):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 14
    history = MagicMock(side_effect=AssertionError("entry must not inspect rates"))
    monkeypatch.setattr(emergency, "history_rate", history)
    projection = MagicMock()
    monkeypatch.setattr(emergency, "native_opportunity", projection)

    solver._emergency_startup()

    history.assert_not_called()
    projection.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


@pytest.mark.parametrize("mood", [0, 8])
def test_real_blocked_startup_ignores_full_bed_timers_and_zero_rates(solver, mood):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in COVERS:
        data.operators[name].mood = 0
    for name in PRIMARY[:2]:
        data.operators[name].mood = mood
        data.operators[name].depletion_rate = 0
    for index, name in enumerate(PRIMARY[2:], 2):
        op = data.operators[name]
        op._current_room, op.current_index = "dormitory_1", index
        op.mood = op.upper_limit
        bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", index))
        bed.name, bed.time = name, None

    solver._emergency_startup()

    assert solver._emergency_active()
    solver._emergency_schedule_staffing.assert_called_once_with(initial=True)


@pytest.mark.parametrize("bound_group", [False, True])
def test_single_low_recovery_group_does_not_enter_even_when_blocked(
    solver, monkeypatch, bound_group
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 24
    members = PRIMARY[:2] if bound_group else PRIMARY[:1]
    for name in members:
        data.operators[name].mood = 0
        if bound_group:
            data.operators[name].group = "low_group"
    if bound_group:
        data.groups["low_group"] = list(members)
    projection = MagicMock(return_value=NativeProjection(None, True, "blocked"))
    monkeypatch.setattr(emergency, "native_opportunity", projection)

    solver._emergency_startup()

    projection.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_active()


def test_multiple_low_groups_with_current_native_capacity_do_not_enter(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY[2:]:
        solver.op_data.operators[name].mood = 24

    solver._emergency_startup()

    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_active()


def test_multiple_low_groups_competing_for_current_beds_enter(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    # Four independent low groups have available covers but only three native beds.
    solver._emergency_startup()

    assert solver._emergency_active()
    solver._emergency_schedule_staffing.assert_called_once_with(initial=True)


def test_low_resting_group_counts_when_waiting_group_cannot_get_beds(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    data.operators[PRIMARY[0]].mood = 0
    for name in PRIMARY[1:]:
        op = data.operators[name]
        op.group = "resting_group"
        op.mood = 8
        op._current_room = "dormitory_1"
        op.current_index = PRIMARY.index(name) + 1
        bed = next(
            bed
            for bed in data.dorm
            if bed.position == (op.current_room, op.current_index)
        )
        bed.name = name
        bed.time = NOW + timedelta(hours=2)
    data.groups["resting_group"] = list(PRIMARY[1:])

    solver._emergency_startup()

    assert solver._emergency_active()
    solver._emergency_schedule_staffing.assert_called_once_with(initial=True)


@pytest.mark.parametrize("reading", ["prediction", "missing", "at_line"])
def test_second_group_needs_measured_mood_below_its_own_line(
    solver, monkeypatch, reading
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY[2:]:
        data.operators[name].mood = 24
    second = data.operators[PRIMARY[1]]
    if reading == "prediction":
        second.mood_is_prediction = True
    elif reading == "missing":
        second.time_stamp = None
    else:
        second.mood = data.rescue_mood_threshold(second)
    projection = MagicMock()
    monkeypatch.setattr(emergency, "native_opportunity", projection)

    solver._emergency_startup()

    projection.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()


@pytest.mark.parametrize("reading", ["prediction", "missing", "at_line"])
def test_entry_requires_measured_mood_strictly_below_rescue_line(solver, reading):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        if reading == "prediction":
            op.mood_is_prediction = True
        elif reading == "missing":
            op.time_stamp = None
        else:
            op.mood = solver.op_data.rescue_mood_threshold(op)

    solver._emergency_startup()

    assert not solver._emergency_active()
    solver._emergency_schedule_staffing.assert_not_called()


def test_without_history_above_rescue_line_does_not_plan_temporary_staffing(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 12
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_not_called()


def test_partial_handoff_persists_plan_and_retry_does_not_replan_temporary_staffing(
    solver,
):
    state = make_episode(solver)
    plan = {"room_1_1": [PRIMARY[0]]}
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(side_effect=[plan.copy(), None])
    solver._emergency_read_rooms = MagicMock()
    previous_task = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    solver.task = previous_task

    def arrange(plan, get_time):
        assert solver.task is not previous_task
        assert solver.task.type == TaskTypes.NOT_SPECIFIC
        assert solver.task.plan is plan
        assert get_time
        return solver.agent_arrange.call_count > 1

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.run_order_solver = MagicMock()
    solver.plan_metadata = MagicMock()
    solver._emergency_schedule_staffing = MagicMock()
    assert not solver._emergency_restore()
    assert state["phase"] == "returning"
    assert state["handoff_plan"] == plan
    assert solver.task is previous_task
    assert solver._emergency_restore()
    assert solver.emergency_state is None
    assert solver.task is previous_task
    solver._emergency_schedule_staffing.assert_not_called()
    solver.backup_plan_solver.assert_called_once()


def partial_handoff(solver, monkeypatch, failure="deferred"):
    """物理安排首房成功后中断；交接与原生可行性判断使用实际实现。"""
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    state = make_episode(solver)
    data = solver.op_data
    for name in PRIMARY:
        op = data.operators[name]
        data.update_detail(name, 16, op.current_room, op.current_index, True)
    plan = {}
    for name, cover in zip(PRIMARY[:2], COVERS[:2]):
        op = data.operators[name]
        room = op.room
        op.current_room, op.current_index = "", -1
        data.operators[cover].current_room, data.operators[cover].current_index = (
            room,
            0,
        )
        plan[room] = [name]
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(side_effect=[copy.deepcopy(plan), None])
    solver._emergency_read_rooms = MagicMock()
    solver._read_initial_card_mood = MagicMock()
    solver._emergency_collect = MagicMock()
    # 此批次实测目标保持 16；这组回归不依赖历史不足时的较低目标。
    solver._emergency_update_targets = MagicMock()
    solver._emergency_schedule_staffing = MagicMock()
    solver._emergency_plan_beds = MagicMock(wraps=solver._emergency_plan_beds)
    attempts = []

    def arrange(pending, get_time):
        assert get_time
        assert solver.task.type == TaskTypes.NOT_SPECIFIC
        attempts.append(copy.deepcopy(pending))
        if len(attempts) == 1:
            room = data.operators[PRIMARY[0]].room
            solver.op_data = solver.op_data.project_arrangements(
                [{room: pending[room]}]
            )
            del pending[room]
            if failure == "error":
                raise RuntimeError("第二个房间安排失败")
            return False
        solver.op_data = solver.op_data.project_arrangements([pending])
        pending.clear()

    solver.agent_arrange = MagicMock(side_effect=arrange)
    if failure == "error":
        with pytest.raises(RuntimeError, match="第二个房间安排失败"):
            solver._emergency_restore()
    else:
        assert not solver._emergency_restore()
    assert state["phase"] == "returning" and state["handoff_plan"]
    completed = solver.op_data.operators[PRIMARY[0]]
    assert (completed.current_room, completed.current_index) == (
        completed.room,
        completed.index,
    )
    # 下一次真实房间观察读到已回岗主班消耗了 0.1 点心情。
    solver.op_data.update_detail(
        completed.name, 15.9, completed.current_room, completed.current_index, True
    )
    state["next_read"] = NOW
    return state, attempts


@pytest.mark.parametrize("failure", ["deferred", "error"])
@pytest.mark.parametrize("restarted", [False, True])
def test_returning_tick_continues_real_handoff_after_returned_primary_consumes_mood(
    solver, monkeypatch, failure, restarted
):
    state, attempts = partial_handoff(solver, monkeypatch, failure)
    if restarted:
        solver.emergency_state = copy.deepcopy(state)
        state = solver.emergency_state
        solver._emergency_startup_pending = True
        solver._emergency_startup()
    assert solver.op_data.operators[PRIMARY[0]].mood < state["targets"][PRIMARY[0]]

    solver._emergency_tick()

    assert len(attempts) == 2
    assert solver.emergency_state is None
    assert solver.op_data.operators[PRIMARY[0]].mood == 15.9
    assert state["targets"][PRIMARY[0]] == 16
    solver._emergency_schedule_staffing.assert_not_called()
    assert not solver._emergency_handoff


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_returning_tick_waits_for_specialized_compensation_before_handoff(
    solver, monkeypatch, kind
):
    state, attempts = partial_handoff(solver, monkeypatch)
    room = solver.op_data.operators[PRIMARY[1]].room
    compensation = SchedulerTask(task_type=kind, task_plan={room: [COVERS[1]]})
    compensation.emergency_original_roster = {room: [COVERS[1]]}
    solver.tasks = [compensation]

    solver._emergency_tick()
    assert len(attempts) == 1
    assert state["phase"] == "returning"
    assert compensation in solver.tasks

    solver.tasks.remove(compensation)
    state["next_read"] = NOW
    solver._emergency_tick()
    assert len(attempts) == 2
    assert solver.emergency_state is None


@pytest.mark.parametrize(
    "invalid",
    [
        "pending_measurement",
        "pending_prediction",
        "returned_prediction",
        "native_blocked",
    ],
)
def test_returning_rejects_stale_handoff_and_resumes_recovery(
    solver, monkeypatch, invalid
):
    state, attempts = partial_handoff(solver, monkeypatch)
    pending = solver.op_data.operators[PRIMARY[1]]
    if invalid == "pending_measurement":
        solver.op_data.update_detail(
            pending.name, 15.9, pending.current_room, pending.current_index, True
        )
    elif invalid == "pending_prediction":
        pending.mood_is_prediction = True
    elif invalid == "returned_prediction":
        solver.op_data.operators[PRIMARY[0]].mood_is_prediction = True
    else:
        for name in COVERS:
            solver.op_data.operators[name].mood = 0

    solver._emergency_tick()

    assert len(attempts) == 1
    assert state["phase"] == "recovering"
    assert not any(
        key in state for key in ("handoff_plan", "handoff_names", "handoff_conditions")
    )
    assert state["targets"][PRIMARY[0]] == 16
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_plan_beds.assert_called_once_with(state)
    if invalid == "pending_measurement":
        assert any(
            pending.name in row for task in solver.tasks for row in task.plan.values()
        )
    assert not solver._emergency_handoff


@pytest.mark.parametrize(
    "previous_type", [None, TaskTypes.NOT_SPECIFIC, TaskTypes.FIAMMETTA]
)
def test_handoff_uses_real_arrangement_with_its_own_task_context(solver, previous_type):
    make_episode(solver)
    plan = {"room_1_1": [PRIMARY[0]]}
    previous_task = (
        SchedulerTask(task_type=previous_type, meta_data=emergency.CHECK_META)
        if previous_type is not None
        else None
    )
    solver.task = previous_task
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(side_effect=[plan.copy(), None])
    solver._emergency_read_rooms = MagicMock()
    solver.enter_room = MagicMock()
    observed_tasks = []
    solver.turn_on_room_detail = MagicMock(
        side_effect=lambda room: observed_tasks.append(solver.task)
    )
    solver.back = MagicMock()
    solver.scene = MagicMock(return_value=Scene.INFRA_MAIN)
    solver.run_order_solver = MagicMock()
    solver.plan_metadata = MagicMock()

    assert solver._emergency_restore()
    assert solver.emergency_state is None
    assert solver.task is previous_task
    assert len(observed_tasks) == 1
    assert observed_tasks[0] is not previous_task
    assert observed_tasks[0].type == TaskTypes.NOT_SPECIFIC
    assert not solver._emergency_handoff
    solver.enter_room.assert_called_once_with("room_1_1")


@pytest.mark.parametrize(
    "error", [RuntimeError("arrangement failed"), emergency.MowerExit()]
)
def test_handoff_restores_previous_task_after_arrangement_error(solver, error):
    state = make_episode(solver)
    plan = {"room_1_1": [PRIMARY[0]]}
    previous_task = SchedulerTask(task_type=TaskTypes.WORKSHOP)
    solver.task = previous_task
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(return_value=plan.copy())
    solver.agent_arrange_room = MagicMock(side_effect=error)
    with pytest.raises(type(error)):
        solver._emergency_restore()
    assert solver.task is previous_task
    assert state["phase"] == "returning"
    assert state["handoff_plan"] == plan
    assert solver._emergency_frozen()


def test_exhausted_replacements_prevent_exit_until_native_matching_is_feasible(solver):
    make_episode(solver)
    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(return_value={})
    solver.agent_arrange = MagicMock()
    assert not solver._emergency_restore()
    solver.agent_arrange.assert_not_called()


def test_check_task_rearms_at_next_mood_read_after_consumed_check(solver):
    make_episode(solver)
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.CHECK_META)]
    solver.last_execution["todo"] = NOW
    consumed = solver.tasks.pop()
    solver.task = consumed
    solver._emergency_tick()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == NOW + timedelta(minutes=30)


def test_history_cycle_keeps_charge_dependent_operator_separate():
    rows = []
    for i in range(4):
        start = NOW + timedelta(hours=i * 3)
        rows += [
            (
                22,
                start.isoformat(),
                "dormitory_1",
                "central",
                "fiammetta_after",
                "gladiia",
                0,
            ),
            (
                8,
                (start + timedelta(hours=2)).isoformat(),
                "central",
                "dormitory_1",
                "fiammetta_before",
                "dorm",
                0,
            ),
        ]
    assert emergency_recovery.history_cycle(rows, "central", "gladiia") == 2
    assert emergency_recovery.history_cycle(rows, "central", "other") is None


def test_history_schema_migration_and_bounded_query_are_hermetic(tmp_path, monkeypatch):
    import sqlite3

    from arknights_mower.solvers import record

    directory = tmp_path / "db"
    directory.mkdir()
    path = directory / "data.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE agent_action (name TEXT, agent_current_room TEXT, current_room TEXT, is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT)"
        )
    monkeypatch.setattr(
        record, "get_path", lambda name: path if name.endswith("data.db") else directory
    )
    monkeypatch.setattr(record, "_tables_created", False)
    for i in range(205):
        record.save_agent_action(
            "歌蕾蒂娅",
            "central",
            "central",
            True,
            "sea",
            20,
            current_time=NOW - timedelta(minutes=205 - i),
            context_key="sea",
            current_index=0,
        )
    rows = record.emergency_mood_history("歌蕾蒂娅", NOW)
    assert len(rows) == 200
    assert rows[0][1] == str(NOW - timedelta(minutes=200))
    assert rows[-1][-2:] == ("sea", 0)


def test_exact_collection_deadline_collects_both_orders_and_products(solver):
    make_episode(solver)
    solver.last_execution["todo"] = NOW - timedelta(minutes=15)
    solver.find = lambda template: template
    solver.tap = MagicMock()
    solver.todo_list()
    assert [call.args[0] for call in solver.tap.call_args_list][:2] == [
        "infra_collect_bill",
        "infra_collect_factory",
    ]
    assert solver.last_execution["todo"] == NOW


def test_future_order_does_not_block_ready_handoff_but_started_compensation_does(
    solver,
):
    make_episode(solver)
    task = SchedulerTask(
        time=NOW + timedelta(hours=1),
        task_plan={"room_1_1": ["但书"]},
        task_type=TaskTypes.RUN_ORDER,
    )
    solver.tasks = [task]
    assert solver._emergency_ready()
    task.emergency_original_roster = {"room_1_1": [PRIMARY[0]]}
    assert not solver._emergency_ready()


def test_temporary_staffing_survives_filter_but_ordinary_working_plan_does_not(solver):
    make_episode(solver)
    staffing = SchedulerTask(task_plan={"room_1_1": [COVERS[0]]})
    staffing.emergency_staffing = True
    ordinary = SchedulerTask(task_plan={"room_1_2": [PRIMARY[1]]})
    dorm = SchedulerTask(task_plan={"dormitory_1": ["Current"] * 5})
    check = SchedulerTask(meta_data=emergency.CHECK_META)
    solver.tasks = [staffing, ordinary, dorm, check]
    solver._emergency_filter_tasks()
    assert solver.tasks == [staffing, dorm, check]


def test_restart_reuses_only_unfinished_room_plan_without_scanning(solver):
    native_schedule = solver._emergency_schedule_staffing
    setup_startup(solver)
    state = make_episode(solver)
    state["staffing_plan"] = {
        "room_1_1": [PRIMARY[0]],
        "room_1_2": [COVERS[1]],
    }
    solver._emergency_scan_workers = MagicMock()
    solver._emergency_update_targets = MagicMock()
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_startup()
    solver._emergency_schedule_staffing = native_schedule
    solver._emergency_tick()
    staffing = [t for t in solver.tasks if getattr(t, "emergency_staffing", False)]
    assert len(staffing) == 1
    assert staffing[0].plan == {"room_1_2": [COVERS[1]]}
    assert state["staffing_plan"] == {"room_1_2": [COVERS[1]]}
    solver._emergency_scan_workers.assert_not_called()


def test_completed_staffing_plan_reconciles_actual_roster_and_rearms_orders(solver):
    state = make_episode(solver)
    state["staffing_plan"] = {"room_1_1": [PRIMARY[0]]}
    solver._emergency_tick()
    assert state["staffing_plan"] == {}
    assert state["temporary_roster"]["room_1_1"] == [PRIMARY[0]]
    solver.run_order_solver.assert_called()
    assert state["phase"] == "recovering"


def test_existing_healthy_temporary_workers_are_not_rescanned(solver):
    make_episode(solver)
    solver.op_data.plan["room_1_1"][0].facility = "制造站"
    solver.op_data.operators[PRIMARY[0]]._current_room = ""
    solver.op_data.operators[COVERS[0]]._current_room = "room_1_1"
    solver.op_data.operators[COVERS[0]].current_index = 0
    solver._emergency_scan_workers = MagicMock()
    solver._emergency_schedule_staffing()
    solver._emergency_scan_workers.assert_not_called()
    assert not any(getattr(t, "emergency_staffing", False) for t in solver.tasks)


def test_low_temporary_worker_is_repaired_and_plan_is_saved_before_enqueue(solver):
    from arknights_mower.utils.emergency_staffing import StaffingCandidate

    state = make_episode(solver)
    data = solver.op_data
    data.config.resting_threshold = 0.65
    data.plan["room_1_1"][0].facility = "制造站"
    data.operators[PRIMARY[0]].mood = 8
    solver._emergency_scan_workers = MagicMock(
        return_value=[StaffingCandidate(COVERS[0], 24, ())]
    )
    snapshots = []
    solver._emergency_save = MagicMock(
        side_effect=lambda: snapshots.append(
            (dict(state.get("staffing_plan", {})), list(solver.tasks))
        )
    )
    solver._emergency_schedule_staffing()
    expected = {
        "room_1_1": [COVERS[0]],
        "dormitory_1": ["Current", "Current", PRIMARY[0], "Current", "Current"],
    }
    assert snapshots == [(expected, [])]
    assert solver.tasks[0].plan == expected
    assert solver.tasks[0].emergency_staffing
    room, facility, reserved = solver._emergency_scan_workers.call_args.args
    assert (room, facility) == ("room_1_1", "制造站")
    assert PRIMARY[0] in reserved


@pytest.mark.parametrize("name", ["但书", "龙舌兰", "佩佩", "可露希尔"])
def test_every_trade_order_agent_remains_available_for_run_orders(solver, name):
    make_episode(solver)
    solver.op_data.add(Operator(name, ""))
    room = "room_1_1"
    order = SchedulerTask(
        time=NOW + timedelta(minutes=10),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={room: [name]},
        meta_data=room,
    )
    solver.tasks = [order]
    assert solver._emergency_run_order_available(room, order.plan)
    solver._emergency_filter_tasks()
    assert solver.tasks == [order]
    solver.op_data.operators[name]._current_room = "room_2_1"
    assert not solver._emergency_run_order_available(room, order.plan)


def test_run_order_compensation_restores_actual_temporary_original(solver, monkeypatch):
    from arknights_mower.solvers import base_schedule

    make_episode(solver)
    room = "room_1_1"
    solver.op_data.operators[PRIMARY[0]]._current_room = ""
    solver.op_data.operators[COVERS[0]]._current_room = room
    solver.op_data.operators[COVERS[0]].current_index = 0
    solver.op_data.add(Operator("但书", ""))
    order = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={room: ["但书"]}, meta_data=room
    )
    solver.task = order
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.CHECK_META)]
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.agent_arrange_room = MagicMock(return_value={room: ["但书"]})
    solver.drone = MagicMock()
    solver.skip = MagicMock()
    config.conf.run_order_grandet_mode.enable = False
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *a: False
    )
    solver.agent_arrange(order.plan)
    compensation = next(t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER)
    assert order.emergency_original_roster == {room: [COVERS[0]]}
    assert compensation.plan == {room: [COVERS[0]]}
    assert compensation.emergency_original_roster == {room: [COVERS[0]]}
    assert compensation.plan[room] != [solver.op_data.plan[room][0].agent]


def test_flagged_temporary_staffing_can_arrange_while_regular_shift_is_frozen(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    make_episode(solver)
    plan = {"room_1_1": [COVERS[0]]}
    solver.task = SchedulerTask(task_plan=plan)
    solver.task.emergency_staffing = True
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver.agent_arrange_room = MagicMock(return_value={})
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *a: False
    )
    solver.agent_arrange(plan)
    solver.agent_arrange_room.assert_called_once_with(
        {}, "room_1_1", plan, get_time=False
    )


@pytest.mark.parametrize("mood", [None, 0, 15.9])
def test_selection_rechecks_card_mood_and_preserves_actual_readings(
    solver, monkeypatch, mood
):
    from arknights_mower.solvers import base_mixin

    make_episode(solver)
    name = COVERS[0]
    op = solver.op_data.operators[name]
    solver.op_data.config.resting_threshold = 0.65
    solver.op_data.dorm_mood_estimates[name] = (24, NOW)
    solver.task = SchedulerTask(task_plan={"room_1_1": [name]})
    solver.task.emergency_staffing = True
    solver.recog = SimpleNamespace(img=object())
    monkeypatch.setattr(base_mixin, "estimate_agent_mood", lambda *a: mood)
    with pytest.raises(base_mixin.AgentSelectionNotReady, match="心情不足或无法读取"):
        solver.observe_agent_moods([(name, ((0, 0), (1, 1)))], [name], None, False)
    assert (op.mood, op.time_stamp) == (24, NOW)
    if mood is None:
        assert name not in solver.op_data.dorm_mood_estimates
    else:
        assert solver.op_data.dorm_mood_estimates[name][0] == mood


def test_rejected_staffing_candidate_cancels_only_failed_room_and_requests_repair(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.solvers.base_mixin import AgentSelectionNotReady

    state = make_episode(solver)
    plan = {"room_1_1": [COVERS[0]], "room_1_2": [COVERS[1]]}
    state["staffing_plan"] = {room: names.copy() for room, names in plan.items()}
    solver.task = SchedulerTask(task_plan=plan)
    solver.task.emergency_staffing = True
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock(side_effect=AgentSelectionNotReady("心情不足"))
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_read_rooms = MagicMock()
    solver._emergency_save = MagicMock()
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    assert solver.agent_arrange_room({}, "room_1_1", plan) is False
    assert state["staffing_plan"] == {"room_1_2": [COVERS[1]]}
    assert plan == {"room_1_2": [COVERS[1]]}
    assert state["next_read"] == NOW
    solver.choose_agent.assert_called_once()
    solver._emergency_read_rooms.assert_called_once_with(["room_1_1"])
    solver._emergency_save.assert_called_once()


def test_known_skland_skills_skip_icon_recognition_and_missing_data_uses_fallback(
    solver, monkeypatch
):
    snapshot = {"account_uid": "test"}
    known, unknown, unowned, low_mood = COVERS
    skills = ({"skillIcon": "known"},)
    fallback = ({"skillIcon": "fallback"},)
    page = [(name, ((i, 0), (i + 1, 1))) for i, name in enumerate(COVERS)]
    solver._selection_profile_snapshot = object()
    solver.recog = SimpleNamespace(img=object(), w=1920, h=1080)
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.refresh_facility_state = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.profession_filter = MagicMock()
    solver.tap = MagicMock()
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock()
    solver.wait_for_agent_page = MagicMock(side_effect=[page, page])
    solver.same_agent_page = MagicMock(return_value=True)
    solver.swipe_agent_page = MagicMock(return_value=(1, None))
    solver.back_to_infrastructure = MagicMock()
    monkeypatch.setattr(emergency, "load_skill_snapshot", lambda: snapshot)
    monkeypatch.setattr(emergency, "owned_operator", lambda name, data: name != unowned)
    monkeypatch.setattr(
        emergency,
        "unlocked_skills",
        lambda name, facility, data: skills if name == known else None,
    )
    monkeypatch.setattr(
        emergency,
        "estimate_agent_mood",
        lambda image, scope: 0 if scope[0][0] == 3 else 24,
    )
    icons = MagicMock(return_value=fallback)
    monkeypatch.setattr(emergency, "card_skills", icons)
    candidates = solver._emergency_scan_workers("room_1_1", "制造站", set())
    assert [(candidate.name, candidate.skills) for candidate in candidates] == [
        (known, skills),
        (unknown, fallback),
    ]
    icons.assert_called_once_with(solver.recog.img, page[1][1], unknown, "制造站")
    solver.refresh_facility_state.assert_called_once_with("room_1_1")
    solver.back_to_infrastructure.assert_called_once()


def test_selection_scan_cancels_page_on_recognition_failure(solver, monkeypatch):
    solver._selection_profile_snapshot = object()
    solver.recog = SimpleNamespace(img=object(), w=1920, h=1080)
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.refresh_facility_state = MagicMock()
    solver.find = MagicMock(return_value=True)
    solver.profession_filter = MagicMock()
    solver.tap = MagicMock()
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock()
    solver.wait_for_agent_page = MagicMock(side_effect=RuntimeError("识别失败"))
    solver.back_to_infrastructure = MagicMock()
    monkeypatch.setattr(emergency, "load_skill_snapshot", lambda: None)
    with pytest.raises(RuntimeError, match="识别失败"):
        solver._emergency_scan_workers("room_1_1", "制造站", set())
    solver.back_to_infrastructure.assert_called_once()


def test_completed_primary_remains_reserved_during_another_group_departure(solver):
    from arknights_mower.utils.emergency_staffing import (
        StaffingCandidate,
        eligible_worker,
    )

    state = make_episode(solver)
    data = solver.op_data
    room = data.operators[PRIMARY[1]].room
    data.plan[room][0].facility = "制造站"
    data.operators[PRIMARY[1]].mood = 8
    completed = PRIMARY[0]
    assert data.operators[completed].mood >= state["targets"][completed]
    observations = []

    def scan(room, facility, reserved, **kwargs):
        observations.append(reserved)
        assert completed in reserved
        assert not eligible_worker(data, completed, 24, reserved)
        return [StaffingCandidate(COVERS[0], 24, ())]

    solver._emergency_scan_workers = scan
    solver._emergency_schedule_staffing(initial=True)
    assert observations
    assert solver.tasks[0].plan[room] == [COVERS[0]]
    projected = data.project_arrangements([solver.tasks[0].plan])
    assert projected.operators[PRIMARY[1]].is_resting()
    assert projected.operators[completed].current_room == data.operators[completed].room


def test_unchanged_initial_staffing_still_monitors_temporary_worker_mood(solver):
    from arknights_mower.utils.emergency_staffing import StaffingCandidate

    state = make_episode(solver)
    data = solver.op_data
    room = "room_1_1"
    data.plan[room][0].facility = "制造站"
    data.operators[PRIMARY[0]]._current_room = ""
    data.operators[COVERS[0]]._current_room = room
    data.operators[COVERS[0]].current_index = 0
    solver._emergency_scan_workers = MagicMock(
        return_value=[StaffingCandidate(COVERS[0], 24, ())]
    )
    solver._emergency_schedule_staffing(initial=True)
    assert not state.get("staffing_plan")
    assert state["temporary_roster"][room] == [COVERS[0]]
    assert not any(getattr(t, "emergency_staffing", False) for t in solver.tasks)
    state["next_read"] = NOW
    solver._emergency_read_rooms = MagicMock()
    solver._emergency_collect = MagicMock()
    solver._emergency_update_targets = MagicMock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_tick()
    assert room in solver._emergency_read_rooms.call_args.args[0]
    solver._emergency_scan_workers.assert_not_called()


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_staffing_reserves_original_worker_of_started_specialized_task(solver, kind):
    from arknights_mower.utils.emergency_staffing import (
        StaffingCandidate,
        eligible_worker,
    )

    make_episode(solver)
    room = "room_1_2"
    data = solver.op_data
    data.operators[PRIMARY[1]].mood = 8
    data.plan[room][0].facility = "制造站"
    data.add(Operator("但书", ""))
    original = COVERS[0]
    task = SchedulerTask(task_type=kind, task_plan={"room_1_1": ["但书"]})
    task.emergency_original_roster = {"room_1_1": [original]}
    solver.tasks = [task]

    def scan(room, facility, reserved, **kwargs):
        assert original in reserved
        assert not eligible_worker(data, original, 24, reserved)
        return [StaffingCandidate(COVERS[1], 24, ())]

    solver._emergency_scan_workers = MagicMock(side_effect=scan)

    solver._emergency_schedule_staffing(initial=True)

    solver._emergency_scan_workers.assert_called_once()
    staffing = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    assert staffing.plan[room] == [COVERS[1]]
    assert data.project_arrangements([staffing.plan]).operators[PRIMARY[1]].is_resting()
    assert task.emergency_original_roster == {"room_1_1": [original]}


@pytest.mark.parametrize("path", ["planner", "selection"])
@pytest.mark.parametrize("lower_manager", [False, True])
@pytest.mark.parametrize("resident_mood", [8, 24])
def test_emergency_preserves_configured_managers_and_priority_dynamic_residents(
    solver, monkeypatch, path, lower_manager, resident_mood
):
    from arknights_mower.solvers import record
    from arknights_mower.utils.resting_priority import RestingTier, resting_tier

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    state = make_episode(solver)
    room = "dormitory_1"
    incoming = PRIMARY[0]
    residents = ["冰酿", "闪灵", *COVERS[:3]]
    data = solver.op_data
    data.update_detail(incoming, 8, "", -1, True)
    for index, name in enumerate(residents):
        data.update_detail(name, 8 if index == 1 else resident_mood, room, index, True)
    data.config.ope_resting_priority = residents.copy()
    assert len(data.dorm) == 3
    assert {bed.position[1] for bed in data.dorm} == {2, 3, 4}
    assert all(bed.name for bed in data.dorm)
    assert resting_tier(data, incoming) == RestingTier.MAIN
    assert all(resting_tier(data, name) == RestingTier.PRIORITY for name in residents)
    if lower_manager:
        data.config.ope_resting_priority.remove(residents[0])
        data.operators[residents[0]].resting_priority = "low"
    allowed = False
    assert [
        bed.position for bed in data.dorm if data._slot_takable(bed, requester=incoming)
    ] == ([(room, 0)] if allowed else [])

    plan = emergency_recovery.emergency_dorm_plan(data, state, solver.tasks)
    if path == "planner":
        assert plan == (
            {room: [incoming, "Current", "Current", "Current", "Current"]}
            if allowed
            else {}
        )
    else:
        row = [
            residents[index] if name == "Current" else name
            for index, name in enumerate(plan.get(room, residents))
        ]
        solver.task = SchedulerTask(
            task_type=TaskTypes.FILL_DORM, task_plan={room: row}
        )
        solver.task.emergency_dorm = True
        solver.prepare_dorm_selection(row, room)
        assert row == ([incoming, *residents[1:]] if allowed else residents)

    assert data.get_current_room(room, True) == residents
    assert not data.operators[incoming].current_room


@pytest.mark.parametrize("manager_reading", ["full", "unfinished", "prediction"])
@pytest.mark.parametrize("explicit_priority", [False, True])
@pytest.mark.parametrize("manager_index", [0, 1])
def test_configured_manager_keeps_position_for_every_measurement_and_priority(
    solver, monkeypatch, manager_reading, explicit_priority, manager_index
):
    from arknights_mower.solvers import record
    from arknights_mower.utils.resting_priority import RestingTier, resting_tier

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    state = make_episode(solver)
    room = "dormitory_1"
    incoming = PRIMARY[0]
    residents = ["冰酿", "闪灵", *COVERS[:3]]
    manager = residents[manager_index]
    data = solver.op_data
    data.update_detail(incoming, 8, "", -1, True)
    for index, name in enumerate(residents):
        data.update_detail(name, 8, room, index, True)
    data.update_detail(
        manager,
        23 if manager_reading == "unfinished" else 24,
        room,
        manager_index,
        True,
    )
    data.operators[manager].mood_is_prediction = manager_reading == "prediction"
    data.config.ope_resting_priority = [
        name for name in residents if explicit_priority or name != manager
    ]
    assert resting_tier(data, incoming) == RestingTier.MAIN
    assert resting_tier(data, manager) == (
        RestingTier.PRIORITY if explicit_priority else RestingTier.MAIN
    )
    assert data.operators[manager].index == manager_index
    assert {bed.position[1] for bed in data.dorm} == {2, 3, 4}
    assert all(bed.name for bed in data.dorm)
    allowed = False
    assert [
        bed.position for bed in data.dorm if data._slot_takable(bed, requester=incoming)
    ] == ([(room, manager_index)] if allowed else [])

    plan = emergency_recovery.emergency_dorm_plan(data, state, solver.tasks)
    expected = ["Current"] * 5
    expected[manager_index] = incoming
    assert plan == ({room: expected} if allowed else {})
    row = [
        residents[index] if name == "Current" else name
        for index, name in enumerate(plan.get(room, residents))
    ]
    solver.task = SchedulerTask(task_type=TaskTypes.FILL_DORM, task_plan={room: row})
    solver.task.emergency_dorm = True

    solver.prepare_dorm_selection(row, room)

    expected = residents.copy()
    if allowed:
        expected[manager_index] = incoming
    assert row == expected
    assert data.get_current_room(room, True) == residents
    assert not data.operators[incoming].current_room


def staffing_deadline_episode(solver, monkeypatch, seconds):
    """实测清退时刻与设施扫描共用虚拟时钟，保留实际任务规划。"""
    from arknights_mower.solvers import base_schedule, record
    from arknights_mower.utils import operation_timing, operators, scheduler_task
    from arknights_mower.utils.emergency_staffing import StaffingCandidate

    clock = {"now": NOW}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    for module in (
        emergency,
        emergency_recovery,
        base_schedule,
        operators,
        scheduler_task,
    ):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    monkeypatch.setattr(emergency, "load_skill_snapshot", lambda: None)
    monkeypatch.setattr(operation_timing, "_dorm_durations", {})
    state = make_episode(solver)
    state["phase"] = "staffing"
    state["next_read"] = NOW
    data = solver.op_data
    for name in PRIMARY:
        op = data.operators[name]
        data.update_detail(name, 8, op.current_room, op.current_index, True)
        data.plan[op.room][op.index].facility = "制造站"
    limited = data.operators[PRIMARY[0]]
    data.config.operator_mood_limits = {limited.name: {"lower": 0, "upper": 12}}
    data.init_mood_limit()
    data.update_detail(limited.name, 10, "dormitory_1", 2, True)
    _, bed = data.get_dorm_by_name(limited.name)
    bed.time = NOW + timedelta(seconds=seconds)
    state["targets"][limited.name] = 10.5
    solver._emergency_read_rooms = MagicMock()
    solver._emergency_collect = MagicMock()
    solver.last_execution["todo"] = NOW
    solver._emergency_update_targets = MagicMock()
    scans, saves = [], []

    def scan(room, facility, reserved, **kwargs):
        index = next(
            i for i, name in enumerate(PRIMARY) if data.operators[name].room == room
        )
        assert COVERS[index] not in reserved
        scans.append(room)
        clock["now"] += timedelta(seconds=45)
        return [StaffingCandidate(COVERS[index], 24, ())]

    solver._emergency_scan_workers = MagicMock(side_effect=scan)
    solver._emergency_save = MagicMock(
        side_effect=lambda: saves.append(copy.deepcopy(state.get("staffing_plan", {})))
    )
    return state, clock, scans, saves, limited.name


def test_staffing_tick_yields_before_near_personal_limit_release(solver, monkeypatch):
    state, clock, scans, _, _ = staffing_deadline_episode(solver, monkeypatch, 120)

    solver._emergency_tick()

    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert not scans
    assert release.mood_limit_deadline == NOW + timedelta(seconds=120)
    assert release.time == NOW + timedelta(seconds=30)
    assert clock["now"] < release.time <= clock["now"] + timedelta(seconds=46)
    assert state["next_read"] <= clock["now"] + timedelta(minutes=1)
    assert solver._emergency_active()


@pytest.mark.parametrize("healthy_remaining", [False, True])
def test_staffing_discards_unexecutable_group_scan_and_retries_after_release(
    solver, monkeypatch, healthy_remaining
):
    state, clock, scans, saves, limited_name = staffing_deadline_episode(
        solver, monkeypatch, 180
    )
    solver._emergency_release_ready = MagicMock(return_value=False)
    healthy_room = solver.op_data.operators[PRIMARY[1]].room
    if healthy_remaining:
        solver.op_data.update_detail(PRIMARY[1], 8, "", -1, True)
        solver.op_data.update_detail(COVERS[1], 24, healthy_room, 0, True)

    solver._emergency_tick()

    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert len(scans) == 1
    assert release.mood_limit_deadline == NOW + timedelta(seconds=180)
    assert release.time == NOW + timedelta(seconds=90)
    assert clock["now"] < release.time <= clock["now"] + timedelta(seconds=46)
    assert not state.get("staffing_plan")
    assert not state.get("staffing_members")
    assert not any(getattr(task, "emergency_staffing", False) for task in solver.tasks)
    assert not any(saved for saved in saves)
    clock["now"] = NOW + timedelta(seconds=180)
    solver.op_data.update_detail(limited_name, 12, "", -1, True)
    solver.op_data.operators[limited_name].rest_mood_release_limit = 12
    solver.tasks.remove(release)
    state["next_read"] = clock["now"]

    solver._emergency_tick()

    staffing = next(
        task for task in solver.tasks if getattr(task, "emergency_staffing", False)
    )
    member = PRIMARY[2] if healthy_remaining else PRIMARY[1]
    room = solver.op_data.operators[member].room
    assert len(scans) == 2 and scans[-1] == room
    assert staffing.plan[room] == [COVERS[PRIMARY.index(member)]]
    assert state["staffing_members"] == [member]
    assert (
        solver.op_data.project_arrangements([staffing.plan])
        .operators[member]
        .is_resting()
    )
    assert state["staffing_plan"] in saves
    assert not state.get("staffing_remaining")
    assert not any(task.strict_mood_limit for task in solver.tasks)


def test_staffing_deadline_yield_moves_existing_check_to_prompt_continuation(
    solver, monkeypatch
):
    state, clock, scans, _, _ = staffing_deadline_episode(solver, monkeypatch, 120)
    check = SchedulerTask(
        time=NOW + timedelta(minutes=30), meta_data=emergency.CHECK_META
    )
    solver.tasks = [check]

    solver._emergency_tick()

    assert not scans
    assert check.time == state["next_read"] == clock["now"] + timedelta(minutes=1)
    assert [
        task for task in solver.tasks if task.meta_data == emergency.CHECK_META
    ] == [check]


def test_returning_ready_waits_for_due_strict_release(solver, monkeypatch):
    state, attempts = partial_handoff(solver, monkeypatch)
    release = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["", "Current", "Current", "Current", "Current"]},
    )
    release.strict_mood_limit = True
    solver.tasks = [release]

    assert not solver._emergency_ready()
    assert state["phase"] == "returning"
    assert len(attempts) == 1
    release.plan.clear()
    assert solver._emergency_ready()


@pytest.mark.parametrize("release_seconds", [44, 45])
def test_returning_handoff_waits_when_arrangement_budget_reaches_strict_release(
    solver, monkeypatch, release_seconds
):
    state, attempts = partial_handoff(solver, monkeypatch)
    release = SchedulerTask(
        time=NOW + timedelta(seconds=release_seconds),
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["", "Current", "Current", "Current", "Current"]},
    )
    release.strict_mood_limit = True
    solver.tasks = [release]
    pending = copy.deepcopy(state["handoff_plan"])

    assert solver._emergency_ready()
    assert not solver._emergency_restore()
    assert len(attempts) == 1
    assert state["handoff_plan"] == pending
    assert state["phase"] == "returning"
    assert release in solver.tasks and release.plan
    assert not solver._emergency_handoff

    solver.tasks.remove(release)
    assert solver._emergency_restore()
    assert len(attempts) == 2
    assert solver.emergency_state is None


@pytest.mark.parametrize("restarted", [False, True])
@pytest.mark.parametrize("expired", [False, True])
def test_handoff_cancels_deferred_emergency_fill_before_primary_returns(
    solver, monkeypatch, restarted, expired
):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "save_agent_action", MagicMock())
    state = make_episode(solver)
    data = solver.op_data
    primary = PRIMARY[0]
    data.update_detail(primary, 8, "", -1, True)
    solver._emergency_plan_beds(state)
    pending = next(
        task for task in solver.tasks if getattr(task, "emergency_dorm", False)
    )
    assert primary in pending.plan["dormitory_1"]
    order = SchedulerTask(
        time=NOW + timedelta(seconds=30),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_2": ["但书"]},
        meta_data="room_1_2",
    )
    solver.tasks.append(order)
    emergency.protect_priority_tasks(solver.tasks, time_now=NOW)
    assert pending.time > NOW
    solver.tasks.remove(order)
    if expired:
        pending.time = NOW - timedelta(minutes=1)
    if restarted:
        solver.tasks = pickle.loads(pickle.dumps(solver.tasks))
        pending = next(task for task in solver.tasks if task.emergency_dorm)
    for name in PRIMARY:
        worker = data.operators[name]
        data.update_detail(
            name,
            16 if name == primary else 24,
            "" if name == primary else worker.room,
            -1 if name == primary else worker.index,
            True,
        )
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    arrangements = []

    def arrange_room(new_plan, room, plan, **kwargs):
        assert pending not in solver.tasks
        arrangements.append(copy.deepcopy({room: plan[room]}))
        solver.op_data = solver.op_data.project_arrangements([{room: plan[room]}])
        del plan[room]
        return new_plan

    solver.agent_arrange_room = arrange_room
    solver._emergency_read_rooms = MagicMock(return_value=True)
    solver.plan_metadata = MagicMock(wraps=solver.plan_metadata)
    assert solver._emergency_ready()
    assert solver._emergency_restore()
    assert solver.emergency_state is None
    assert pending not in solver.tasks
    assert solver.op_data.operators[primary].is_working()
    returned = copy.deepcopy(arrangements)
    # 已选中的旧任务引用也在真实派发入口按队列身份检查后放弃。
    pending.time = NOW - timedelta(minutes=1)
    solver.task = pending
    solver.find = MagicMock(return_value=(1, 1))
    solver.skip = MagicMock()
    assert solver.infra_main()
    assert solver.task is None
    assert solver.op_data.operators[primary].is_working()
    assert arrangements == returned
    solver.skip.assert_called_once()


@pytest.mark.parametrize("phase", ["recovering", "returning"])
def test_handoff_filter_removes_only_episode_fill_and_retains_restoration_tasks(
    solver, phase
):
    state = make_episode(solver)
    state["phase"] = phase
    fill = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_1": ["Current", "Current", PRIMARY[0]]},
    )
    fill.emergency_dorm = True
    release = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={"dormitory_1": ["Current", "Current", ""]},
    )
    release.strict_mood_limit = True
    specialized = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER, task_plan={"room_1_2": [COVERS[1]]}
    )
    specialized.emergency_original_roster = {"room_1_2": [COVERS[1]]}
    ordinary = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "Free"]},
    )
    solver.tasks = pickle.loads(pickle.dumps([fill, release, specialized, ordinary]))
    queued_fill, queued_release, queued_specialized, queued_ordinary = solver.tasks

    solver._emergency_filter_tasks()

    assert solver.tasks == (
        [queued_release, queued_specialized, queued_ordinary]
        if phase == "returning"
        else [queued_fill, queued_release, queued_specialized, queued_ordinary]
    )


def test_target_projection_reuses_eval_capsule_and_isolates_mutable_state(
    solver, monkeypatch
):
    state = make_episode(solver)
    source = solver.op_data
    make_capsule = ctypes.pythonapi.PyCapsule_New
    make_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    make_capsule.restype = ctypes.py_object
    capsule = make_capsule(ctypes.c_void_p(42), None, None)
    source.eval_model.imported_functions["runtime_handle"] = capsule
    source.evaluate_expression("True == True")
    before_moods = {name: op.mood for name, op in source.operators.items()}
    before_beds = [(bed.name, bed.time) for bed in source.dorm]
    before_plan = repr(source.plan)
    probes = []

    def inspect_projection(probe, members):
        projected = probe.op_data
        probes.append(projected)
        assert projected is not source
        assert projected.eval_model is source.eval_model
        assert projected.eval_model.imported_functions["runtime_handle"] is capsule
        assert projected.plan is not source.plan
        assert projected.config is not source.config
        for name in members:
            assert projected.operators[name] is not source.operators[name]
            projected.operators[name].mood = 0
        assert projected.dorm[0] is not source.dorm[0]
        projected.dorm[0].name = ""
        return NativeProjection(NOW + timedelta(hours=1), True)

    monkeypatch.setattr(emergency, "history_rate", lambda *a: 2)
    monkeypatch.setattr(emergency, "native_opportunity", inspect_projection)
    solver._emergency_update_targets()

    assert len(probes) == len(state["targets"])
    assert all(value == "history" for value in state["target_sources"].values())
    assert before_moods == {name: op.mood for name, op in source.operators.items()}
    assert before_beds == [(bed.name, bed.time) for bed in source.dorm]
    assert before_plan == repr(source.plan)


@pytest.mark.parametrize("path", ["immediate", "blocked", "pending"])
def test_native_projection_reuses_eval_capsule_across_search_branches(solver, path):
    source = solver.op_data
    make_capsule = ctypes.pythonapi.PyCapsule_New
    make_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    make_capsule.restype = ctypes.py_object
    capsule = make_capsule(ctypes.c_void_p(42), None, None)
    source.eval_model.imported_functions["runtime_handle"] = capsule
    source.evaluate_expression("True == True")
    name = PRIMARY[0]
    if path != "immediate":
        for cover in COVERS:
            source.operators[cover].mood = 0
    if path == "pending":
        primary = source.operators[name]
        primary.depletion_rate = 1
        solver.tasks.append(
            SchedulerTask(
                time=NOW + timedelta(minutes=10),
                task_type=TaskTypes.SHIFT_OFF,
                task_plan={
                    primary.room: [COVERS[0]],
                    "dormitory_1": ["Current", "Current", name, "Current", "Current"],
                },
            )
        )
    before_operators = {
        n: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for n, op in source.operators.items()
    }
    before_beds = [(bed.name, bed.time) for bed in source.dorm]
    before_plan = repr(source.plan)
    before_tasks = [(task.time, copy.deepcopy(task.plan)) for task in solver.tasks]

    result = emergency_recovery.native_opportunity(solver, [name], NOW)

    assert result.complete
    assert (
        result.opportunity
        == {
            "immediate": NOW,
            "blocked": None,
            "pending": NOW + timedelta(minutes=10),
        }[path]
    )
    assert before_operators == {
        n: (op.current_room, op.current_index, op.mood, op.time_stamp)
        for n, op in source.operators.items()
    }
    assert before_beds == [(bed.name, bed.time) for bed in source.dorm]
    assert before_plan == repr(source.plan)
    assert before_tasks == [(task.time, task.plan) for task in solver.tasks]
    assert source.eval_model.imported_functions["runtime_handle"] is capsule
    solver.enter_room.assert_not_called()
