"""MAA 单次派发、实测退出和普通收取的离线契约。"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

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
from arknights_mower.utils.plan import Room
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
    solver._run_emergency_maa = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_collect = MagicMock()
    solver._emergency_startup_pending = True
    solver.op_data.config.resting_threshold = 0.65
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 8
    return solver


def make_episode(solver):
    data = solver.op_data
    solver.emergency_state = {
        "phase": "recovering",
        "dispatch": "completed",
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
    assert not config.Conf().maa_emergency_infrast_enable
    setup_startup(solver)
    assert solver.op_data.rescue_mood_threshold(
        solver.op_data.operators[PRIMARY[0]]
    ) == pytest.approx(11.7)
    solver._emergency_startup()
    solver._run_emergency_maa.assert_not_called()
    assert not solver._emergency_startup_pending


@pytest.mark.parametrize(
    "projection",
    [
        NativeProjection(NOW + timedelta(minutes=10), True),
        NativeProjection(None, False, "unknown"),
    ],
)
def test_native_opportunity_or_unknown_prevents_dispatch(
    solver, monkeypatch, projection
):
    setup_startup(solver)
    config.conf.maa_emergency_infrast_enable = True
    monkeypatch.setattr(emergency, "native_opportunity", lambda *a, **k: projection)
    solver._emergency_startup()
    solver._run_emergency_maa.assert_not_called()


def test_measured_low_mood_dispatches_once_and_restart_only_reconciles(
    solver, monkeypatch
):
    setup_startup(solver)
    config.conf.maa_emergency_infrast_enable = True
    monkeypatch.setattr(
        emergency,
        "native_opportunity",
        lambda *a, **k: NativeProjection(None, True, "blocked"),
    )
    solver._emergency_startup()
    assert solver._emergency_active()
    solver._emergency_startup()
    solver._run_emergency_maa.assert_called_once()
    assert solver.emergency_state["dispatch"] == "unknown"


@pytest.mark.parametrize("field", ["phase", "dispatch"])
def test_invalid_persisted_episode_cannot_dispatch_again(solver, field):
    setup_startup(solver)
    state = make_episode(solver)
    state[field] = "invalid"
    config.conf.maa_emergency_infrast_enable = True
    with pytest.raises(emergency.MowerExit, match="缓存结构不完整"):
        solver._emergency_startup()
    solver._emergency_read_rooms.assert_not_called()
    solver._run_emergency_maa.assert_not_called()


def test_card_estimates_do_not_establish_entry_or_ready(solver):
    setup_startup(solver)
    config.conf.maa_emergency_infrast_enable = True
    for name in PRIMARY:
        op = solver.op_data.operators[name]
        op.time_stamp = None
        solver.op_data.dorm_mood_estimates[name] = (0, NOW)
    solver._emergency_startup()
    solver._run_emergency_maa.assert_not_called()
    make_episode(solver)
    for name in PRIMARY:
        solver.op_data.dorm_mood_estimates[name] = (24, NOW)
    assert not solver._emergency_ready()


def test_observed_absence_invalidates_only_departed_resident_reading(solver):
    missing = solver.op_data.operators[PRIMARY[0]]
    untouched = solver.op_data.operators[COVERS[0]]
    room = missing.current_room
    original_stamp = untouched.time_stamp
    observed = [
        {"agent": op.name}
        for op in solver.op_data.operators.values()
        if op.current_room == room and op.name != missing.name
    ]
    solver.get_agent_from_room = MagicMock(return_value=observed)
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver._emergency_read_rooms([room])
    solver.get_agent_from_room.assert_called_once_with(room, None, force_mood=True)
    assert missing.current_room == "" and missing.time_stamp is None
    assert untouched.time_stamp == original_stamp
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


def test_collection_wakes_before_long_mood_check_with_paused_orders(solver):
    make_episode(solver)
    solver.last_execution["todo"] = NOW - timedelta(minutes=16)
    solver._emergency_tick()
    check = next(
        task for task in solver.tasks if task.meta_data == emergency.CHECK_META
    )
    assert check.time == NOW
    assert solver.emergency_state["next_read"] == NOW + timedelta(minutes=30)


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


@pytest.mark.parametrize("successful", [False, True])
def test_maa_parameters_and_callback_outcome(solver, successful):
    make_episode(solver)
    for slots in solver.op_data.plan.values():
        for slot in slots:
            slot.facility = "制造站"
    solver.op_data.plan["factory"] = [Room("特克诺", "", [], facility="加工站")]
    solver.op_data.plan["train"] = [Room("阿米娅", "", [])]
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 8
    asst = SimpleNamespace(
        append_task=MagicMock(return_value=1),
        start=MagicMock(return_value=True),
        running=MagicMock(return_value=False),
        stop=MagicMock(),
        run_successful=successful,
    )
    solver.initialize_maa = lambda: setattr(solver, "MAA", asst)
    solver.recog = SimpleNamespace(reset_after_external_control=MagicMock())
    solver._run_emergency_maa()
    params = asst.append_task.call_args.args[1]
    assert set(params["facility"]) == {"Mfg", "Processing"}
    assert params["threshold"] == 9 / 24
    assert not params["fiammetta_recovery_enabled"] and not params["replenish"]
    assert params["drones"] == "_NotUse"
    assert solver.emergency_state["dispatch"] == (
        "completed" if successful else "failed"
    )
    asst.stop.assert_called_once()
    solver.recog.reset_after_external_control.assert_called_once()


def test_history_predicts_rescue_line_before_pending_native_opportunity(
    solver, monkeypatch
):
    setup_startup(solver)
    config.conf.maa_emergency_infrast_enable = True
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 14
    monkeypatch.setattr(emergency, "history_rate", lambda *a: 2)
    seen = {}

    def projection(*args, **kwargs):
        seen.update(kwargs)
        return NativeProjection(None, True, "blocked")

    monkeypatch.setattr(emergency, "native_opportunity", projection)
    solver._emergency_startup()
    assert seen["deadlines"][PRIMARY[0]] == NOW + timedelta(hours=(14 - 11.7) / 2)
    solver._run_emergency_maa.assert_called_once()


def test_without_history_above_rescue_line_does_not_dispatch(solver):
    setup_startup(solver)
    config.conf.maa_emergency_infrast_enable = True
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 12
    solver._emergency_startup()
    solver._run_emergency_maa.assert_not_called()


def test_partial_handoff_persists_plan_and_retry_does_not_dispatch(solver):
    state = make_episode(solver)
    plan = {"room_1_1": [PRIMARY[0]]}
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(side_effect=[plan.copy(), None])
    solver._emergency_read_rooms = MagicMock()
    solver.agent_arrange = MagicMock(side_effect=[False, True])
    solver.run_order_solver = MagicMock()
    solver.plan_metadata = MagicMock()
    solver._run_emergency_maa = MagicMock()
    assert not solver._emergency_restore()
    assert state["phase"] == "returning"
    assert state["handoff_plan"] == plan
    assert solver._emergency_restore()
    assert solver.emergency_state is None
    solver._run_emergency_maa.assert_not_called()
    solver.backup_plan_solver.assert_called_once()


def test_exhausted_replacements_prevent_exit_until_native_matching_is_feasible(solver):
    make_episode(solver)
    for name in COVERS:
        solver.op_data.operators[name].mood = 0
    solver.backup_plan_solver = MagicMock(return_value=False)
    solver.agent_get_mood = MagicMock(return_value={})
    solver.agent_arrange = MagicMock()
    assert not solver._emergency_restore()
    solver.agent_arrange.assert_not_called()


def test_stop_confirmation_failure_blocks_mower_device_actions(solver, monkeypatch):
    make_episode(solver)
    for slots in solver.op_data.plan.values():
        for slot in slots:
            slot.facility = "制造站"
    asst = SimpleNamespace(
        append_task=MagicMock(return_value=1),
        start=MagicMock(return_value=False),
        running=lambda: True,
        stop=MagicMock(),
    )
    solver.initialize_maa = lambda: setattr(solver, "MAA", asst)
    solver.recog = SimpleNamespace(reset_after_external_control=MagicMock())
    counter = iter([0, 0, 601, 601, 620])
    monkeypatch.setattr(emergency, "monotonic", lambda: next(counter))
    monkeypatch.setattr(emergency, "csleep", lambda value: None)
    with pytest.raises(emergency.MowerExit, match="未确认停止"):
        solver._run_emergency_maa()
    solver.recog.reset_after_external_control.assert_not_called()


def test_check_task_rearms_collection_after_consumed_check(solver):
    make_episode(solver)
    solver.tasks = [SchedulerTask(time=NOW, meta_data=emergency.CHECK_META)]
    solver.last_execution["todo"] = NOW
    consumed = solver.tasks.pop()
    solver.task = consumed
    solver._emergency_tick()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == NOW + timedelta(minutes=15)


@pytest.mark.parametrize("failure", ["stop", "running"])
@pytest.mark.parametrize("save_fails", [False, True])
def test_stop_interface_errors_halt_even_if_state_save_fails(
    solver, failure, save_fails
):
    make_episode(solver)
    for slots in solver.op_data.plan.values():
        for slot in slots:
            slot.facility = "制造站"
    asst = SimpleNamespace(
        append_task=MagicMock(return_value=1),
        start=MagicMock(return_value=False),
        running=MagicMock(return_value=False),
        stop=MagicMock(),
    )
    getattr(asst, failure).side_effect = RuntimeError("interface unavailable")
    solver.initialize_maa = lambda: setattr(solver, "MAA", asst)
    solver.recog = SimpleNamespace(reset_after_external_control=MagicMock())
    if save_fails:
        solver._emergency_save = MagicMock(side_effect=RuntimeError("db unavailable"))
    with pytest.raises(emergency.MowerExit, match="未确认停止"):
        solver._run_emergency_maa()
    assert solver.MAA is asst
    solver.recog.reset_after_external_control.assert_not_called()


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
