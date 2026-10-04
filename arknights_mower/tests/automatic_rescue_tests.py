"""自动救急的临时驻员、实测退出和普通收取的离线契约。"""

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


def configure_rescue(solver):
    from arknights_mower.utils.config.plan import PlanModel
    from arknights_mower.utils.emergency_plan import RESCUE_ROOMS

    covers = iter(COVERS)
    roster = {
        room: {"plans": [{"agent": next(covers)} for slot in row]}
        for room, row in solver.op_data.plan.items()
        if room in RESCUE_ROOMS and row
    }
    config.conf.automatic_rescue_plan = PlanModel(plan1=roster)
    return {
        room: [slot["agent"] for slot in facility["plans"]]
        for room, facility in roster.items()
    }


def setup_startup(solver):
    configure_rescue(solver)
    solver._read_agent_mood = MagicMock()
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
        "staffing_complete": True,
        "rescue_plan": configure_rescue(solver),
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
    solver._emergency_schedule_staffing.assert_not_called()
    assert solver.emergency_state["phase"] == "staffing"
    assert solver.emergency_state["observed_at"] == NOW


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
    assert recovery_target(data, PRIMARY[0]) == (normal, "fallback")
    target, source = recovery_target(data, PRIMARY[0], 2, NOW + timedelta(hours=2), NOW)
    assert target == normal + 5 and source == "history"
    target, _ = recovery_target(data, PRIMARY[0], 10, NOW + timedelta(hours=2), NOW)
    assert target > 24
    data.operators[PRIMARY[0]].exhaust_require = True
    target, _ = recovery_target(data, PRIMARY[0], 4, NOW + timedelta(hours=1), NOW)
    assert target == 5


@pytest.mark.parametrize("last_collection", [None, NOW - timedelta(minutes=16)])
def test_collection_does_not_create_an_independent_wakeup(solver, last_collection):
    make_episode(solver)
    solver.last_execution["todo"] = last_collection
    solver._emergency_collect = MagicMock()
    solver._emergency_tick()
    assert not solver.tasks
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
    assert activity == ([] if observed else ["collect", "read"])
    assert order not in solver.tasks
    assert solver._emergency_collect.call_count == (0 if observed else 1)


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
    assert activity == ["restore"]


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
    check = SchedulerTask(meta_data=emergency.RESUME_META)
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
    solver._emergency_schedule_staffing.assert_not_called()


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
    solver._emergency_schedule_staffing.assert_not_called()


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
    solver._emergency_schedule_staffing.assert_not_called()


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


@pytest.mark.parametrize("delay", [0, 10])
def test_startup_keeps_executable_native_return_before_rescue(solver, delay):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    owner = data.operators[PRIMARY[2]]
    owner.mood = 24
    cover = data.operators[COVERS[0]]
    cover._current_room, cover.current_index = owner.room, owner.index
    bed = data.dorm[0]
    owner._current_room, owner.current_index = bed.position
    bed.name, bed.time = owner.name, None
    task = SchedulerTask(
        time=NOW + timedelta(minutes=delay),
        task_type=TaskTypes.SHIFT_ON,
        task_plan={owner.room: [owner.name]},
    )
    solver.tasks = [task]

    solver._emergency_startup()

    assert solver._emergency_active() is (delay > 0)
    if delay == 0:
        solver._emergency_schedule_staffing.assert_not_called()
        assert task in solver.tasks
    else:
        solver._emergency_schedule_staffing.assert_not_called()


@pytest.mark.parametrize("delay,mood", [(0, 24), (10, 24), (0, 8)])
def test_startup_keeps_executable_fiammetta_before_rescue(solver, delay, mood):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=mood,
        time_stamp=NOW,
        operator_type="high",
        replacement=[PRIMARY[-1]],
    )
    task = SchedulerTask(
        time=NOW + timedelta(minutes=delay),
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"dormitory_1": [PRIMARY[-1], "菲亚梅塔"]},
        meta_data=PRIMARY[-1],
    )
    solver.tasks = [task]

    solver._emergency_startup()

    executable = delay == 0 and mood == 24
    assert solver._emergency_active() is (not executable)
    if executable:
        solver._emergency_schedule_staffing.assert_not_called()
        assert task in solver.tasks
    else:
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
        solver._read_agent_mood = MagicMock()
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
        SchedulerTask(task_type=previous_type, meta_data=emergency.RESUME_META)
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


def test_consumed_continuation_does_not_create_periodic_check(solver):
    make_episode(solver)
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.RESUME_META)]
    solver.last_execution["todo"] = NOW
    consumed = solver.tasks.pop()
    solver.task = consumed
    solver._emergency_tick()
    assert not solver.tasks


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
    check = SchedulerTask(meta_data=emergency.RESUME_META)
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
    state["staffing_complete"] = False
    state["rescue_plan"] = {
        solver.op_data.operators[name].room: [name] for name in PRIMARY
    }
    state["rescue_plan"]["room_1_2"] = [COVERS[1]]
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


def test_completed_staffing_plan_reconciles_actual_roster_and_rearms_orders(solver):
    state = make_episode(solver)
    state["staffing_plan"] = {"room_1_1": [PRIMARY[0]]}
    solver.op_data.operators[PRIMARY[1]].mood = 0
    solver._emergency_schedule_staffing = MagicMock(return_value=True)
    solver._emergency_plan_beds = MagicMock()
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
    solver._emergency_schedule_staffing()
    assert not any(getattr(t, "emergency_staffing", False) for t in solver.tasks)


@pytest.mark.parametrize("name", ["但书", "龙舌兰", "佩佩", "可露希尔"])
def test_configured_trade_order_agent_remains_available_for_run_orders(solver, name):
    state = make_episode(solver)
    state["run_order_replacements"] = {"room_1_1": [[name]]}
    solver._emergency_sync_reservations()
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
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.RESUME_META)]
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
    if mood is None:
        with pytest.raises(
            base_mixin.AgentSelectionNotReady, match="心情读数未知或无效"
        ):
            solver.observe_agent_moods([(name, ((0, 0), (1, 1)))], [name], None, False)
    else:
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


@pytest.mark.parametrize("stale_identity", [False, True])
@pytest.mark.parametrize("stale_completion", [False, True])
def test_unexecutable_due_release_does_not_prevent_rescue(
    solver, stale_identity, stale_completion
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 0
    for name, bed in zip(PRIMARY[2:], data.dorm[:2]):
        resident = data.operators[name]
        resident._current_room, resident.current_index = bed.position
        bed.name, bed.time = name, NOW if stale_completion else None
    room, index = data.dorm[0].position
    row = ["Current"] * len(data.plan[room])
    row[index] = "Free"
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={room: row},
        meta_data=PRIMARY[3] if stale_identity else PRIMARY[2],
    )
    solver.tasks = [task]
    before_plan = copy.deepcopy(task.plan)
    result = emergency_recovery.native_opportunity(
        solver, PRIMARY[:2], NOW, current_only=True
    )
    assert result.complete and result.opportunity is None
    assert task.plan == before_plan
    assert data.operators[PRIMARY[2]].mood == 0

    solver._emergency_startup()

    assert solver._emergency_active()
    solver._emergency_schedule_staffing.assert_not_called()


def test_current_fiammetta_charge_is_consumed_after_one_target(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 0
    for name in COVERS[:2]:
        data.operators[name].mood = 0
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.operators["冰酿"]._current_room, data.operators["冰酿"].current_index = "", -1
    data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=24,
        time_stamp=NOW,
        operator_type="high",
        replacement=PRIMARY[:2],
    )
    tasks = [
        SchedulerTask(
            time=NOW,
            task_type=TaskTypes.FIAMMETTA,
            task_plan={"dormitory_1": [target, "菲亚梅塔"]},
            meta_data=target,
        )
        for target in PRIMARY[:2]
    ]
    solver.tasks = tasks
    result = emergency_recovery.native_opportunity(
        solver, PRIMARY, NOW, current_only=True
    )
    assert result.complete and result.opportunity is None
    assert data.operators["菲亚梅塔"].mood == 24
    assert all(data.operators[name].mood == 0 for name in PRIMARY)
    assert solver.tasks == tasks

    solver._emergency_startup()

    assert solver._emergency_active()
    solver._emergency_schedule_staffing.assert_not_called()


@pytest.mark.parametrize("available", [False, True])
def test_target_update_reuses_group_opportunity_only_within_one_update(
    solver, monkeypatch, available
):
    data = solver.op_data
    members = PRIMARY[:2]
    for name in members:
        op = data.operators[name]
        op.group = "恢复组"
        data.global_plan["default_plan"].plan[op.room][op.index].group = op.group
    data.groups["恢复组"] = members.copy()
    state = make_episode(solver)
    state["targets"] = {name: 16 for name in PRIMARY[:3]}
    rates = {PRIMARY[0]: 1, PRIMARY[1]: 3, PRIMARY[2]: None}
    monkeypatch.setattr(emergency, "emergency_mood_history", lambda name: [name])
    monkeypatch.setattr(emergency, "history_rate", lambda rows, *args: rates[rows[0]])
    cycles = {PRIMARY[0]: 1, PRIMARY[1]: 2, PRIMARY[2]: None}
    monkeypatch.setattr(emergency, "history_cycle", lambda rows, *args: cycles[rows[0]])
    first = NOW + timedelta(hours=1) if available else None
    projection = MagicMock(return_value=NativeProjection(first, True))
    monkeypatch.setattr(emergency, "native_opportunity", projection)

    solver._emergency_update_targets()

    assert projection.call_count == 1
    assert set(projection.call_args.args[1]) == set(members)
    expected = {
        PRIMARY[0]: first,
        PRIMARY[1]: NOW + timedelta(hours=2) if available else None,
        PRIMARY[2]: first,
    }
    for name in PRIMARY[:3]:
        assert (
            state["targets"][name]
            == recovery_target(data, name, rates[name], expected[name], NOW)[0]
        )
    second = NOW + timedelta(hours=2)
    projection.return_value = NativeProjection(second, True)

    solver._emergency_update_targets()

    assert projection.call_count == 2
    for name in PRIMARY[:3]:
        assert (
            state["targets"][name]
            == recovery_target(data, name, rates[name], second, NOW)[0]
        )
    assert state["targets"][PRIMARY[0]] != state["targets"][PRIMARY[1]]


@pytest.mark.parametrize("phase", ["staffing", "recovering", "returning"])
def test_rescue_run_order_checks_do_not_read_exhausted_primaries(solver, phase):
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    state = make_episode(solver)
    state["phase"] = phase
    solver.op_data.exhaust_agent = [PRIMARY[0]]
    solver.op_data.operators[PRIMARY[0]].mood = 0
    solver._sync_run_order_tasks = MagicMock()
    solver.op_data.run_order_rooms = {}
    solver.check_fia = MagicMock(return_value=(None, None))
    BaseSchedulerSolver.run_order_solver(solver)
    solver.enter_room.assert_not_called()
    assert not any(t.type == TaskTypes.EXHAUST_OFF for t in solver.tasks)


def test_completed_staffing_continues_next_group_before_mood_check(solver):
    state = make_episode(solver)
    state["staffing_plan"] = {"room_1_1": [PRIMARY[0]]}
    solver._emergency_read_rooms = MagicMock()
    solver.op_data.operators[PRIMARY[1]].mood = 0
    solver._emergency_schedule_staffing = MagicMock(return_value=True)
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_tick()
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_read_rooms.assert_not_called()
    assert state["next_read"] == NOW + timedelta(minutes=30)


@pytest.mark.parametrize(
    "enabled,missing,expected",
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_initial_card_scan_covers_configured_rescue_workers(
    solver, monkeypatch, enabled, missing, expected
):
    from arknights_mower.utils.config.plan import PlanModel

    config.conf.automatic_rescue_enable = enabled
    name = "红"
    config.conf.automatic_rescue_plan = PlanModel(
        plan1={"room_1_1": {"plans": [{"agent": name}]}}
    )
    if not missing:
        solver.op_data.dorm_mood_estimates[name] = (24, datetime.now())
    solver._scan_card_moods = MagicMock()
    solver._read_initial_card_mood()
    assert solver._scan_card_moods.called is expected


def test_rescue_task_report_labels_staffing_and_concrete_dorm_rotation(solver):
    from arknights_mower.solvers.base_schedule import task_template

    task = SchedulerTask(time=NOW, task_plan={"room_1_1": [COVERS[0]]})
    task.emergency_staffing = True
    check = SchedulerTask(time=NOW, task_plan={"dormitory_1": [PRIMARY[0]]})
    check.emergency_recovery_release = True
    report = task_template.render(
        tasks=[task.format(), check.format()], base_scheduler=solver
    )
    assert "自动救急换班" in report
    assert "自动救急离宿待命" not in report
    assert "自动救急" in report
    assert "自动救急心情复查" not in report
    assert COVERS[0] in report
    assert emergency.RESUME_META not in report
    assert task.type == TaskTypes.NOT_SPECIFIC


def test_idle_rescue_ticks_do_not_repeat_planning_or_workshop_checks(
    solver, monkeypatch
):
    make_episode(solver)
    workshop = MagicMock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", workshop)
    solver._emergency_schedule_staffing = MagicMock()
    solver._emergency_read_rooms = MagicMock()
    for _ in range(3):
        solver._emergency_tick()
    workshop.assert_not_called()
    solver.run_order_solver.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    solver._emergency_read_rooms.assert_not_called()
    checks = [task for task in solver.tasks if task.meta_data == emergency.RESUME_META]
    assert not checks
    assert not solver.tasks


@pytest.mark.parametrize(
    "task_type", [TaskTypes.WORKSHOP, TaskTypes.FIAMMETTA, TaskTypes.SWAP_SUPPORT]
)
def test_completed_specialized_task_replans_from_local_readback(
    solver, monkeypatch, task_type
):
    make_episode(solver)
    solver.op_data.operators[PRIMARY[0]].mood = 0
    solver._emergency_schedule_staffing = MagicMock(return_value=True)
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_read_rooms = MagicMock()
    workshop = MagicMock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", workshop)
    solver._emergency_tick(completed_task=SchedulerTask(task_type=task_type))
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_read_rooms.assert_not_called()
    workshop.assert_called_once()
    solver._emergency_tick()
    workshop.assert_called_once()


def test_unknown_staffing_room_does_not_complete_pending_arrangement(solver):
    state = make_episode(solver)
    state["staffing_plan"] = {"room_1_1": [COVERS[0]]}
    solver.op_data.get_current_room = MagicMock(return_value=None)
    assert solver._emergency_reconcile_staffing() is False
    assert state["staffing_plan"] == {"room_1_1": [COVERS[0]]}


def test_startup_observation_is_consumed_by_single_dispatch_path(solver, monkeypatch):
    setup_startup(solver)
    solver.last_execution = {"todo": NOW}
    config.conf.automatic_rescue_enable = True
    monkeypatch.setattr(
        emergency,
        "native_opportunity",
        lambda *args, **kwargs: NativeProjection(None, True, "blocked"),
    )
    solver._emergency_update_targets = MagicMock()
    solver._open_emergency_beds = MagicMock()
    solver._emergency_startup()
    solver._emergency_schedule_staffing.assert_not_called()
    solver._emergency_update_targets.assert_not_called()
    solver._open_emergency_beds.assert_not_called()
    solver._emergency_read_rooms.reset_mock()
    solver._emergency_ready = MagicMock(return_value=False)
    solver._emergency_plan_beds = MagicMock()
    solver._emergency_tick()
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_update_targets.assert_called_once()
    solver._open_emergency_beds.assert_called_once()
    solver._emergency_read_rooms.assert_not_called()
    solver._emergency_tick()
    solver._emergency_schedule_staffing.assert_called_once()


def test_normal_planner_hands_rescue_all_planning_ownership(solver, monkeypatch):
    from arknights_mower.solvers import base_schedule

    make_episode(solver)
    solver._emergency_tick = MagicMock()
    solver.agent_get_mood = MagicMock()
    workshop = MagicMock()
    monkeypatch.setattr(base_schedule, "try_workshop_tasks", workshop)
    solver.plan_solver()
    solver._emergency_tick.assert_called_once()
    workshop.assert_not_called()
    solver.agent_get_mood.assert_not_called()


def test_pending_rescue_staffing_precedes_due_observation_and_specialized_planning(
    solver, monkeypatch
):
    state = make_episode(solver)
    state["next_read"] = NOW
    task = SchedulerTask(time=NOW, task_plan={"room_1_1": [COVERS[0]]})
    task.emergency_staffing = True
    solver.tasks = [task]
    solver._emergency_observe_recovery = MagicMock()
    workshop = MagicMock()
    monkeypatch.setattr(emergency, "try_workshop_tasks", workshop)
    solver._emergency_tick()
    solver._emergency_observe_recovery.assert_not_called()
    solver.run_order_solver.assert_not_called()
    workshop.assert_not_called()
    assert any(t is task for t in solver.tasks)
    assert state["next_read"] > task.time


def test_regular_recovery_observes_only_unfinished_primary_dorms(solver):
    state = make_episode(solver)
    state["temporary_roster"] = {"room_1_1": [COVERS[0]]}
    unfinished = solver.op_data.operators[PRIMARY[0]]
    unfinished._current_room, unfinished.current_index = "dormitory_1", 2
    unfinished.mood = 8
    unfinished.time_stamp = NOW - timedelta(hours=3)
    state["targets"][PRIMARY[1]] = 16
    solver._emergency_read_rooms = MagicMock(return_value=True)
    solver._emergency_collect = MagicMock()
    assert solver._emergency_observe_recovery()
    solver._emergency_read_rooms.assert_called_once_with(
        {"dormitory_1"}, yield_to_releases=True
    )


def test_fresh_initial_observation_goes_directly_to_staffing(solver):
    state = make_episode(solver)
    state["phase"] = "staffing"
    state["next_read"] = NOW
    state["observed_at"] = NOW
    solver.op_data.operators[PRIMARY[0]].mood = 0
    solver._emergency_collect = MagicMock()
    solver._emergency_read_rooms = MagicMock()
    solver._emergency_update_targets = MagicMock()
    solver._emergency_plan_beds = MagicMock()

    def queue():
        task = SchedulerTask(time=NOW, task_plan={"room_1_1": [COVERS[0]]})
        task.emergency_staffing = True
        solver.tasks.append(task)
        state["phase"] = "recovering"
        return True

    solver._emergency_schedule_staffing = MagicMock(side_effect=queue)
    solver._emergency_tick()
    solver._emergency_schedule_staffing.assert_called_once()
    solver._emergency_collect.assert_not_called()
    solver._emergency_read_rooms.assert_not_called()
    solver.run_order_solver.assert_not_called()


def test_dorm_filling_queues_one_task_after_staffing(solver, monkeypatch):
    state = make_episode(solver)
    state["dorm_layout"] = {}
    expected = {"dormitory_1": ["Current", "Current", PRIMARY[0], "Current", "Current"]}
    monkeypatch.setattr(
        emergency, "emergency_dorm_plan", lambda *a, **kw: copy.deepcopy(expected)
    )
    solver._emergency_plan_beds(state)
    solver._emergency_plan_beds(state)
    assert len(solver.tasks) == 1
    assert solver.tasks[0].emergency_dorm
    assert solver.tasks[0].plan == expected


def test_early_exit_keeps_unfinished_group_resting_with_normal_replacements(solver):
    state = make_episode(solver)
    data = solver.op_data
    for name in PRIMARY[:2]:
        data.operators[name].group = "一起休息"
        data.global_plan["default_plan"].plan[data.operators[name].room][
            0
        ].group = "一起休息"
    data.groups["一起休息"] = PRIMARY[:2]
    data.operators[PRIMARY[0]].mood = 8
    data.operators[PRIMARY[1]].mood = 18
    # 救急工作驻员已到位，主班离岗。
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    plan = solver._emergency_resting_handoff({})
    assert plan is not None
    projected = solver.op_data.project_arrangements([plan])
    assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])
    assert all(projected.operators[name].is_working() for name in PRIMARY[2:])
    assert plan["room_1_1"] == [COVERS[0]]
    assert plan["room_1_2"] == [COVERS[1]]
    assert solver._emergency_handoff_feasible(plan)
    assert solver._emergency_ready()
    assert not solver.op_data.operators[PRIMARY[0]].is_resting()


def test_early_exit_rejects_missing_normal_cover_and_insufficient_beds(solver):
    state = make_episode(solver)
    data = solver.op_data
    for name in PRIMARY:
        data.operators[name].mood = 8
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    assert solver._emergency_resting_handoff({}) is None
    assert not solver._emergency_ready()
    for name in PRIMARY[1:]:
        solver.op_data.operators[name].mood = 24
    solver.op_data.operators[COVERS[0]].mood = 0
    assert solver._emergency_resting_handoff({}) is None
    assert not solver._emergency_ready()


def test_early_handoff_finishes_without_recalling_unfinished_group(solver):
    state = make_episode(solver)
    data = solver.op_data
    data.operators[PRIMARY[0]].mood = 8
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    plan = solver._emergency_resting_handoff({})
    solver.op_data = solver.op_data.project_arrangements([plan])
    state.update(phase="returning", handoff_plan=plan, handoff_observing=True)
    solver._emergency_read_rooms = MagicMock(return_value=True)
    solver._emergency_save = MagicMock()
    solver.plan_metadata = MagicMock()
    solver.run_order_solver = MagicMock()
    solver._suppress_train_correction = MagicMock()
    assert solver._emergency_finish_handoff()
    assert solver.emergency_state is None
    assert solver.op_data.operators[PRIMARY[0]].is_resting()
    assert solver.op_data.get_current_operator("room_1_1", 0).name == COVERS[0]
    solver.plan_metadata.assert_called_once()


def test_early_handoff_matches_shared_covers_across_remaining_groups(solver):
    state = make_episode(solver)
    data = solver.op_data
    data.operators[PRIMARY[0]].replacement = COVERS[:2]
    data.operators[PRIMARY[1]].replacement = [COVERS[0]]
    for name in PRIMARY[:2]:
        data.operators[name].mood = 8
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    plan = solver._emergency_resting_handoff({})
    assert plan["room_1_1"] == [COVERS[1]]
    assert plan["room_1_2"] == [COVERS[0]]
    projected = solver.op_data.project_arrangements([plan])
    assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])


def test_absent_rescue_run_orders_do_not_inherit_normal_runners(solver):
    state = make_episode(solver)
    state["run_order_replacements"] = {}
    solver.op_data.plan["room_1_1"][0].replacement = ["但书"]
    solver.op_data.add(Operator("但书", ""))
    solver._emergency_sync_reservations()
    assert solver.op_data.run_order_replacements("room_1_1") == []
    assert not solver._emergency_run_order_available("room_1_1")
    solver.emergency_state = None
    solver._emergency_sync_reservations()
    assert solver.op_data.run_order_replacements("room_1_1") == [["但书"]]


def test_initial_full_fia_without_cached_task_precedes_rescue_evaluation(solver):
    setup_startup(solver)
    solver.check_fia = lambda: ([PRIMARY[-1]], "dormitory_1")
    config.conf.automatic_rescue_enable = True
    solver.op_data.operators["菲亚梅塔"] = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=0,
        current_room="dormitory_1",
        current_index=0,
        mood=24,
        time_stamp=NOW,
        replacement=[PRIMARY[-1]],
    )
    solver._emergency_startup()
    assert solver._emergency_startup_pending
    task = next(task for task in solver.tasks if getattr(task, "initial_fia", False))
    assert task.type == TaskTypes.FIAMMETTA
    solver.backup_plan_solver.assert_not_called()
    solver._emergency_schedule_staffing.assert_not_called()
    solver._emergency_startup()
    solver._read_agent_mood.assert_called_once()
    assert solver._emergency_startup_pending


@pytest.mark.parametrize("normal_cover_available", [False, True])
def test_startup_checks_normal_coverage_for_low_primaries_already_resting(
    solver, normal_cover_available
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY[2:]:
        data.operators[name].mood = 24
    data.operators[COVERS[0]].mood = 24 if normal_cover_available else 0
    solver.op_data = data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", *PRIMARY[:2], "Free"]}]
    )

    solver._emergency_startup()

    assert solver._emergency_active() is (not normal_cover_available)
    if normal_cover_available:
        handoff = next(
            task for task in solver.tasks if task.meta_data == "初始化正常轮休交接"
        )
        projected = solver.op_data.project_arrangements([handoff.plan])
        assert all(projected.operators[name].is_resting() for name in PRIMARY[:2])
        assert projected.get_current_operator("room_1_1", 0).name == COVERS[0]
        assert projected.get_current_operator("room_1_2", 0).name == COVERS[1]
    solver.enter_room.assert_not_called()


def test_measured_targets_do_not_exit_when_normal_replacements_are_exhausted(solver):
    make_episode(solver)
    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    assert not solver._emergency_ready()


def test_early_exit_rejects_shared_cover_required_by_two_resting_groups(solver):
    state = make_episode(solver)
    data = solver.op_data
    for name in PRIMARY[:2]:
        data.operators[name].mood = 8
        data.plan[data.operators[name].room][0].replacement = [COVERS[0]]
        data.global_plan["default_plan"].plan[data.operators[name].room][
            0
        ].replacement = [COVERS[0]]
        data.operators[name].replacement = [COVERS[0]]
    solver.op_data = data.project_arrangements([state["rescue_plan"]])
    assert not solver._emergency_ready()


def test_unknown_normal_primary_does_not_establish_startup_handoff_failure(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY[2:]:
        data.operators[name].mood = 24
    data.operators[PRIMARY[-1]].time_stamp = None
    solver.op_data = data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", *PRIMARY[:2], "Free"]}]
    )
    solver._emergency_startup()
    assert not solver._emergency_active()
    assert not any(task.meta_data == "初始化正常轮休交接" for task in solver.tasks)


def test_entry_reallocates_residents_and_clears_full_occupants(solver):
    state = make_episode(solver)
    data = solver.op_data
    state["targets"] = {name: 16 for name in PRIMARY[:2]}
    # 原恢复者在最后一床；满心情候补占住前床。
    data = data.project_arrangements(
        [
            {
                data.operators[PRIMARY[1]].room: [""],
                "dormitory_1": ["冰酿", "闪灵", COVERS[0], "", PRIMARY[0]],
            }
        ]
    )
    solver.op_data = data
    for name in PRIMARY[:2]:
        data.operators[name].mood = 8
    data.operators[PRIMARY[0]].group = "恢复组"
    data.operators[PRIMARY[1]].group = "恢复组"
    before = data.get_current_room("dormitory_1", True)
    plan = emergency_recovery.emergency_dorm_plan(data, state, reallocate=True)
    row = plan["dormitory_1"]
    assert set(row[2:4]) == set(PRIMARY[:2])
    assert row[4] == ""
    assert COVERS[0] not in row
    assert data.get_current_room("dormitory_1", True) == before


def test_entry_dorm_plan_is_retried_until_observed_and_then_releases_rebuilt(solver):
    state = make_episode(solver)
    state["dorm_replan_pending"] = True
    state["targets"] = {PRIMARY[0]: 16}
    data = solver.op_data
    solver.op_data = data.project_arrangements(
        [
            {
                "dormitory_1": ["冰酿", "闪灵", "", "", PRIMARY[0]],
            }
        ]
    )
    solver.op_data.operators[PRIMARY[0]].mood = 8
    solver._emergency_plan_beds(state)
    first = solver.tasks.pop()
    assert state["dorm_replan_pending"]
    solver._emergency_replan_releases()
    assert not any(
        getattr(t, "emergency_recovery_release", False) for t in solver.tasks
    )
    solver.emergency_state = state = pickle.loads(pickle.dumps(state))
    solver._emergency_plan_beds(state)
    assert solver.tasks.pop().plan == first.plan
    solver.op_data = solver.op_data.project_arrangements([first.plan])
    solver._emergency_plan_beds(state)
    assert not state["dorm_replan_pending"]
    assert "dorm_replan_plan" not in state
    assert not solver.tasks
    bed = solver.op_data.get_dorm_by_name(PRIMARY[0])[1]
    bed.time = NOW + timedelta(hours=4)
    solver._emergency_replan_releases()
    release = next(t for t in solver.tasks if t.emergency_recovery_release)
    assert release.plan[bed.position[0]][bed.position[1]] == "Free"
    assert release.time == NOW + timedelta(hours=2)


def test_entry_reallocation_preserves_reserved_bed(solver):
    state = make_episode(solver)
    data = solver.op_data
    solver.op_data = data.project_arrangements(
        [
            {
                data.operators[PRIMARY[1]].room: [""],
                "dormitory_1": ["冰酿", "闪灵", COVERS[0], "", PRIMARY[0]],
            }
        ]
    )
    data = solver.op_data
    for name in PRIMARY[:2]:
        data.operators[name].mood = 8
    task = SchedulerTask(
        task_plan={
            "dormitory_1": ["Current", "Current", COVERS[0], "Current", "Current"]
        }
    )
    plan = emergency_recovery.emergency_dorm_plan(data, state, [task], reallocate=True)
    assert plan["dormitory_1"][2] == "Current"
    assert set(plan["dormitory_1"][3:]) == set(PRIMARY[:2])


@pytest.mark.parametrize("resting", [False, True])
@pytest.mark.parametrize("estimate", [8, None])
def test_startup_card_moods_admit_rescue_without_changing_observations(
    solver, resting, estimate
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    if resting:
        solver.op_data = data = data.project_arrangements(
            [{"dormitory_1": ["冰酿", "闪灵", *PRIMARY[:2], ""]}]
        )
    for name in PRIMARY:
        data.operators[name].time_stamp = None
        if estimate is not None:
            data.dorm_mood_estimates[name] = (estimate, NOW)
    for name in COVERS:
        data.operators[name].mood = 0
    solver._emergency_startup()
    assert solver._emergency_active() is (estimate is not None)
    assert all(data.operators[name].time_stamp is None for name in PRIMARY)
    solver.enter_room.assert_not_called()


def test_card_estimates_do_not_confirm_recovery_exit(solver):
    make_episode(solver)
    for name in PRIMARY:
        solver.op_data.operators[name].time_stamp = None
        solver.op_data.dorm_mood_estimates[name] = (24, NOW)
    assert solver._emergency_resting_handoff({}) is None
    assert not solver._emergency_ready()


@pytest.mark.parametrize("normal_cover_available", [False, True])
def test_startup_known_resting_groups_use_card_only_missing_primary(
    solver, normal_cover_available
):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    data = solver.op_data
    for name in PRIMARY[2:]:
        data.operators[name].mood = 24
        data.operators[name].time_stamp = None
        data.dorm_mood_estimates[name] = (24, NOW)
    data.operators[COVERS[0]].mood = 24 if normal_cover_available else 0
    solver.op_data = data.project_arrangements(
        [{"dormitory_1": ["冰酿", "闪灵", *PRIMARY[:2], ""]}]
    )
    solver._emergency_startup()
    assert solver._emergency_active() is (not normal_cover_available)
    assert all(
        solver.op_data.operators[name].time_stamp is None for name in PRIMARY[2:]
    )


def test_expired_card_moods_do_not_establish_rescue_contention(solver):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    for name in PRIMARY:
        solver.op_data.operators[name].time_stamp = None
        solver.op_data.dorm_mood_estimates[name] = (0, NOW - timedelta(hours=1))
    solver._emergency_startup()
    assert not solver._emergency_active()


@pytest.mark.parametrize("configured_mood", [20, 24])
def test_rescue_fia_fallback_uses_lowest_uncapped_primary(solver, configured_mood):
    state = make_episode(solver)
    data = solver.op_data
    state["fia_targets"] = [PRIMARY[0]]
    state["dorm_layout"] = {"dormitory_1": ["菲亚梅塔", "Free", "Free", "Free", "Free"]}
    data.plan["dormitory_1"][0].agent = "菲亚梅塔"
    data.add(
        Operator(
            "菲亚梅塔",
            "dormitory_1",
            index=0,
            current_room="dormitory_1",
            current_index=0,
        )
    )
    for name, mood in zip(PRIMARY, [configured_mood, 1, 5, 8]):
        data.operators[name].mood = mood
    data.config.operator_mood_limits[PRIMARY[1]] = {"lower": 0, "upper": 12}
    data.operators[PRIMARY[1]].upper_limit = 12
    solver.check_fia = lambda: ([PRIMARY[0]], "dormitory_1")
    solver._refresh_fia_candidate_moods = MagicMock()
    solver.task = SchedulerTask(time=NOW, task_type=TaskTypes.FIAMMETTA)
    solver.plan_fia()
    task = next(t for t in solver.tasks if t.type == TaskTypes.FIAMMETTA and t.plan)
    assert task.meta_data == (PRIMARY[2] if configured_mood == 24 else PRIMARY[0])
    assert task.emergency_fia_fallback is (configured_mood == 24)
    solver._emergency_filter_tasks()
    assert task in solver.tasks


def test_rescue_fia_fallback_respects_unknown_reserved_and_normal_mode(solver):
    state = make_episode(solver)
    data = solver.op_data
    data.operators[PRIMARY[0]].mood = 24
    data.operators[PRIMARY[1]].time_stamp = None
    solver.tasks.append(SchedulerTask(task_plan={"room_1_3": [PRIMARY[2]]}))
    data.operators[PRIMARY[3]].mood = 8
    assert solver._emergency_fia_fallback([PRIMARY[0]]) == [PRIMARY[3]]
    assert solver._emergency_fia_fallback([]) is None
    state["phase"] = "done"
    assert solver._emergency_fia_fallback([PRIMARY[0]]) is None


@pytest.mark.parametrize("upper", [12, 24])
def test_full_rest_target_uses_personal_upper_limit_despite_history(solver, upper):
    op = solver.op_data.operators[PRIMARY[0]]
    op.rest_in_full, op.upper_limit = True, upper
    assert recovery_target(solver.op_data, op.name) == (upper, "rest_in_full")
    assert recovery_target(
        solver.op_data, op.name, 1, NOW + timedelta(minutes=15), NOW
    ) == (upper, "rest_in_full")


def test_handoff_rejects_below_full_normal_worker_even_with_lower_episode_target(
    solver,
):
    state = make_episode(solver)
    op = solver.op_data.operators[PRIMARY[0]]
    op.rest_in_full = True
    op.mood = state["targets"][op.name]
    assert not solver._emergency_handoff_feasible({}, check_rotation=False)
    op.mood = 24
    assert solver._emergency_handoff_feasible({}, check_rotation=False)
