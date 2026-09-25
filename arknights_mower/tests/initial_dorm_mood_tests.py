"""初始化漏读心情按 Free 数选择宿舍，少量只换 Free，多量整间轮读。"""

from datetime import datetime
from math import ceil
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
    assert solver.op_data.get_current_room(ROOM, True) == solver.arranged[-1][1]
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
