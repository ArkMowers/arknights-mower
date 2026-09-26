"""初始化漏读心情按 Free 数选择宿舍，少量只换 Free，多量整间轮读。"""

import copy
from datetime import datetime
from math import ceil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import (
    dorm_empty_release_tests,
    dorm_recovery_tests,
    dorm_release_tests,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.resting_priority import has_resting_mood
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

op_data = dorm_release_tests.op_data
selection_solver = dorm_empty_release_tests.solver
room_solver = dorm_recovery_tests.solver
ROOM = "dormitory_2"
ORIGINAL = ["芬", "香草", "翎羽", "克洛丝", "安赛尔"]


@pytest.fixture
def solver(op_data):
    data = op_data
    data.plan[ROOM] = [
        Room(name, "", []) for name in ["芬", "香草", "Free", "Free", "Free"]
    ]
    for index, name in enumerate(ORIGINAL):
        data.add(Operator(name, ROOM if index < 2 else "", index=index))
        op = data.operators[name]
        op.current_room, op.current_index = ROOM, index
        op.mood, op.time_stamp = 24, datetime.now()
    for room, names in (
        ("room_1_1", ["陈", "煌", "能天使"]),
        ("room_1_2", ["德克萨斯", "拉普兰德"]),
    ):
        data.plan[room] = [Room(name, "", []) for name in names]
        for index, name in enumerate(names):
            data.add(Operator(name, room, index=index, operator_type="high"))
    data.operators["银灰"].time_stamp = None
    data.operators["红"].time_stamp = None
    data.config.resting_priority_replacement = ["红"]
    data.plan["meeting"][0].replacement.append("白雪")
    data.add(Operator("白雪", ""))
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = data
    instance.task = None
    instance.tasks = []
    instance.enter_room = MagicMock()
    instance.back = MagicMock()
    instance.translate_room = lambda room: room
    instance.get_agent_from_room = MagicMock()
    instance.no_pending_task = MagicMock(return_value=True)
    instance.arranged = []

    def arrange(new_plan, room, plan, *, get_time, mood_probe):
        assert get_time and mood_probe
        data = instance.op_data
        names = plan[room].copy()
        instance.arranged.append((room, names))
        for op in data.operators.values():
            if op.current_room == room and op.name not in names:
                op.current_room, op.current_index = "", -1
        for index, name in enumerate(names):
            if name:
                data.update_detail(name, 8, room, index, True)
        del plan[room]
        return new_plan

    instance.agent_arrange_room = MagicMock(side_effect=arrange)
    instance.missing = [
        op.name
        for op in data.operators.values()
        if not has_resting_mood(op) and op.name != "白雪"
    ]
    assert len(instance.missing) == 7
    return instance


@pytest.mark.parametrize("count", [1, 3, 4, 5, 6, 7])
def test_free_count_boundary_and_full_room_batches_without_restore(solver, count):
    targets = solver.missing[:count]
    for name in solver.missing[count:]:
        solver.op_data.operators[name].time_stamp = datetime.now()
    assert solver._read_initial_dorm_mood()
    assert solver.task is None
    assert solver.tasks == []
    assert len(solver.arranged) == (1 if count <= 3 else ceil(count / 5))
    assert all(room == ROOM for room, _ in solver.arranged)
    if count <= 3:
        expected = ORIGINAL.copy()
        expected[2 : 2 + count] = targets
        assert solver.arranged[0][1] == expected
    else:
        for index, (_, names) in enumerate(solver.arranged):
            batch = targets[index * 5 : (index + 1) * 5]
            assert names == batch + [""] * (5 - len(batch))
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert solver._initial_mood_probe_layout[ROOM] == solver.arranged[-1][1]
    assert all(has_resting_mood(solver.op_data.operators[name]) for name in targets)
    assert not has_resting_mood(solver.op_data.operators["白雪"])
    count_before = len(solver.arranged)
    assert solver._read_initial_dorm_mood()
    assert len(solver.arranged) == count_before


def test_deferred_batch_continues_from_remaining_unknowns(solver):
    solver.no_pending_task.side_effect = [True, True, False]
    assert not solver._read_initial_dorm_mood()
    assert len(solver.arranged) == 1
    read_names = {name for name in solver.arranged[0][1] if name}
    solver.no_pending_task.side_effect = None
    assert solver._read_initial_dorm_mood()
    assert len(solver.arranged) == 2
    assert all(
        has_resting_mood(solver.op_data.operators[name]) for name in solver.missing
    )
    # 下轮只补余下两人；上一批读数已经保留，不重新逐个试读。
    assert set(solver.arranged[-1][1][2:4]) == set(solver.missing) - read_names


def test_busy_and_working_operators_are_not_moved_for_sampling(solver, monkeypatch):
    monkeypatch.setattr(
        "arknights_mower.solvers.base_schedule.busy_resting_names", lambda: {"红"}
    )
    solver.op_data.operators["银灰"].current_room = "train"
    assert solver._read_initial_dorm_mood()
    selected = {name for _, names in solver.arranged for name in names}
    assert "红" not in selected
    assert "银灰" not in selected
    assert not has_resting_mood(solver.op_data.operators["红"])


@pytest.mark.parametrize("reason", ["legacy", "no_dorm", "imminent"])
def test_no_sampling_when_disabled_or_room_or_time_is_unavailable(solver, reason):
    if reason == "legacy":
        solver.op_data.config.experimental_dorm_logic = False
    elif reason == "no_dorm":
        solver.op_data.plan = {
            room: slots
            for room, slots in solver.op_data.plan.items()
            if not room.startswith("dorm")
        }
    else:
        solver.no_pending_task.return_value = False
    assert solver._read_initial_dorm_mood() == (reason != "imminent")
    solver.agent_arrange_room.assert_not_called()
    solver.enter_room.assert_not_called()


def test_failed_arrangement_restores_task_context_and_does_not_claim_completion(solver):
    solver.agent_arrange_room.side_effect = RuntimeError("read failed")
    with pytest.raises(RuntimeError, match="read failed"):
        solver._read_initial_dorm_mood()
    assert solver.task is None
    assert not has_resting_mood(solver.op_data.operators[solver.missing[0]])


def test_room_sampling_does_not_fill_empty_slots_or_reorder_vip(room_solver):
    room_solver.op_data.config.experimental_dorm_logic = True
    room_solver.preserve_resting_crafters = MagicMock()
    room_solver.ensure_dorm_recovery_order = MagicMock()
    room = dorm_recovery_tests.ROOM
    plan = {room: ["陈", "", "", "", ""]}
    room_solver.agent_arrange_room({}, room, plan, get_time=True, mood_probe=True)
    assert plan == {}
    assert room_solver.physical == ["陈", "", "", "", ""]
    room_solver.preserve_resting_crafters.assert_not_called()
    room_solver.ensure_dorm_recovery_order.assert_not_called()
    kwargs = room_solver.choose_agent.call_args.kwargs
    assert kwargs["mood_probe"] and kwargs["preserve_dorm_occupants"]
    assert not kwargs["fast_mode"]


def test_exact_sampling_selection_keeps_requested_full_operator(selection_solver):
    instance, selected = selection_solver
    data = instance.op_data
    data.config.operator_mood_limits["空爆"] = {"lower": 0, "upper": 12}
    data.operators["空爆"].upper_limit = 12
    agents = ["空爆", "", "", "", ""]
    instance.choose_agent(
        agents,
        dorm_empty_release_tests.ROOM,
        fast_mode=False,
        preserve_dorm_occupants=True,
        mood_probe=True,
    )
    assert selected == ["空爆"]


def test_zero_free_slots_still_uses_whole_dorm_capacity(solver):
    for room, slots in solver.op_data.plan.items():
        if room.startswith("dorm"):
            for slot in slots:
                if slot.agent == "Free":
                    slot.agent = "空爆"
    assert solver._read_initial_dorm_mood()
    assert len(solver.arranged) == 2
    assert all(len(names) == 5 for _, names in solver.arranged)
    assert all(
        has_resting_mood(solver.op_data.operators[name]) for name in solver.missing
    )


def test_missing_reading_is_not_treated_as_success(solver):
    def no_read(new_plan, room, plan, **kwargs):
        del plan[room]

    solver.agent_arrange_room.side_effect = no_read
    with pytest.raises(RuntimeError, match="仍未读到心情"):
        solver._read_initial_dorm_mood()
    assert solver.task is None


def test_sampling_keeps_original_residents_beds_and_tasks_even_between_batches(solver):
    original = solver.op_data
    locations = {
        name: (op.current_room, op.current_index)
        for name, op in original.operators.items()
    }
    beds = copy.deepcopy([vars(bed) for bed in original.all_dorms()])
    pending = SchedulerTask(task_plan={ROOM: ["Current"] * 4 + ["Free"]})
    solver.tasks = [pending]
    arrange = solver.agent_arrange_room.side_effect

    def sample(*args, **kwargs):
        result = arrange(*args, **kwargs)
        assert solver.op_data is not original
        assert {
            name: (op.current_room, op.current_index)
            for name, op in original.operators.items()
        } == locations
        assert [vars(bed) for bed in original.all_dorms()] == beds
        # 模拟读房清理旧清退任务，只能影响采样副本的队列。
        solver.tasks.clear()
        assert not solver.backup_plan_solver()
        return result

    solver.agent_arrange_room.side_effect = sample
    assert solver._read_initial_dorm_mood()
    assert solver.op_data is original
    assert solver.tasks == [pending]
    assert original.get_current_room(ROOM, True) == ORIGINAL
    assert all(original.operators[name].mood == 8 for name in solver.missing)


def test_failed_sampling_keeps_original_cache_and_completed_readings(solver):
    original = solver.op_data
    arrange = solver.agent_arrange_room.side_effect

    def fail_after_read(*args, **kwargs):
        arrange(*args, **kwargs)
        raise RuntimeError("interrupted after reading")

    solver.agent_arrange_room.side_effect = fail_after_read
    with pytest.raises(RuntimeError, match="interrupted"):
        solver._read_initial_dorm_mood()
    assert solver.op_data is original
    assert original.get_current_room(ROOM, True) == ORIGINAL
    assert not solver._initial_mood_probe_active
    assert all(
        has_resting_mood(original.operators[name]) for name in solver.missing[:5]
    )
    solver.agent_arrange_room.side_effect = arrange
    assert solver._read_initial_dorm_mood()
    assert all(has_resting_mood(original.operators[name]) for name in solver.missing)


def test_first_backup_uses_original_residents_and_new_mood(solver):
    data = solver.op_data
    data.plan_condition = [False]
    data.backup_plans = [
        SimpleNamespace(
            trigger="op_data.operators['芬'].current_room != dormitory_2 or op_data.operators['银灰'].current_mood() > 10",
            products={},
        )
    ]
    solver.defer_backup_plan_until_mood_read = True
    data.evaluate_expression = MagicMock(wraps=data.evaluate_expression)
    assert solver._read_initial_dorm_mood()
    assert not solver.backup_plan_solver()
    data.evaluate_expression.assert_not_called()
    solver.defer_backup_plan_until_mood_read = False
    assert not solver.backup_plan_solver()
    data.evaluate_expression.assert_called_once()
    assert data.plan_condition == [False]
    assert data.operators["芬"].current_room == ROOM
    assert data.operators["银灰"].mood == 8


def test_finish_hands_actual_positions_to_normal_correction(solver):
    assert solver._read_initial_dorm_mood()
    actual = solver.arranged[-1][1]
    solver._finish_initial_dorm_mood([])
    assert solver.op_data.get_current_room(ROOM, True) == actual
    task = solver.tasks[0]
    assert task.type == TaskTypes.SELF_CORRECTION
    assert task.plan[ROOM][:2] == ORIGINAL[:2]
    assert task.backup_shift_active
    assert not solver.backup_plan_solver()
    assert solver._initial_mood_probe_layout == {}


def test_finish_preserves_explicit_backup_arrangements_and_other_tasks(solver):
    assert solver._read_initial_dorm_mood()
    backup = SchedulerTask(
        task_plan={ROOM: ["香草", "芬", "Current", "Current", "Current"]}
    )
    unrelated = SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [unrelated, backup]
    solver.agent_get_mood = MagicMock(return_value={ROOM: ORIGINAL.copy()})
    solver._finish_initial_dorm_mood([backup])
    assert solver.tasks[0].plan[ROOM] == ["香草", "芬", *ORIGINAL[2:]]
    assert solver.tasks[1:] == [unrelated]


def test_finish_failure_keeps_original_cache_for_retry(solver):
    assert solver._read_initial_dorm_mood()
    original = solver.op_data
    solver.agent_get_mood = MagicMock(side_effect=RuntimeError("correction failed"))
    with pytest.raises(RuntimeError, match="correction failed"):
        solver._finish_initial_dorm_mood([])
    assert solver.op_data is original
    assert solver.defer_backup_plan_until_mood_read
    assert solver._initial_mood_probe_layout


@pytest.mark.parametrize("stage", ["scanning", "sampling"])
def test_initialization_blocks_all_backup_entry_points(solver, stage):
    solver.defer_backup_plan_until_mood_read = stage == "scanning"
    solver._initial_mood_probe_active = stage == "sampling"
    data = solver.op_data
    data.evaluate_expression = MagicMock(
        side_effect=AssertionError("must not evaluate")
    )
    data.swap_plan = MagicMock(side_effect=AssertionError("must not switch"))
    task = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    task.backup_shift_conditions = [True]
    assert not solver.backup_plan_solver()
    solver._prepare_shift_backup(task)
    solver._activate_shift_backup(task)
    assert solver._products_after_arrangement({}) == (data.products, data.plan)
    solver._cancel_pending_shift_on = MagicMock()
    solver.current_room_changed(data.operators["银灰"], started_working=True)
    solver._cancel_pending_shift_on.assert_not_called()


def test_saved_state_during_probe_uses_original_cache(solver, monkeypatch):
    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    monkeypatch.setattr(main, "base_scheduler", solver)
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(solver, attr, 0)
    original = solver.op_data
    tasks = solver.tasks
    arrange = solver.agent_arrange_room.side_effect
    snapshots = []

    def sample(*args, **kwargs):
        result = arrange(*args, **kwargs)
        state = current_state()
        assert state["operators"] is original.operators
        assert state["tasks"] is tasks
        assert state["dorm"] is original.dorm
        assert state["initial_mood_pending"]
        snapshots.append(state)
        return result

    solver.agent_arrange_room.side_effect = sample
    assert solver._read_initial_dorm_mood()
    assert snapshots
    assert snapshots[-1]["operators"]["芬"].current_room == ROOM


def test_next_initial_scan_does_not_overwrite_original_sampled_room(
    solver, monkeypatch
):
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(base_schedule, "_training_room_scan_disabled", True)
    assert solver._read_initial_dorm_mood()
    solver.defer_backup_plan_until_mood_read = True
    solver.enter_room.reset_mock()
    for op in solver.op_data.operators.values():
        op.need_to_refresh = lambda: False
    solver.op_data.operators["芬"].need_to_refresh = lambda: True
    solver._read_agent_mood()
    solver.enter_room.assert_not_called()
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
