"""Pending complete recovery arrangements retain one exhausted-shift intent."""

import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, operators, scheduler_task  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
)


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 8, 10, 35)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    instance = object.__new__(base.BaseSchedulerSolver)
    members = {
        name: Operator(
            name,
            "central",
            index=index,
            current_room="central",
            current_index=index,
            operator_type="high",
            mood=0,
            time_stamp=Clock.now(),
        )
        for index, name in enumerate(("歌蕾蒂娅", "幽灵鲨"))
    }
    instance.op_data = SimpleNamespace(
        operators=members,
        exhaust_agent=["歌蕾蒂娅"],
        rest_in_full_group=[],
        groups={},
        run_order_rooms={},
        refresh_run_order_rooms=lambda: None,
        active_high_resting_count=lambda: 0,
    )
    instance.tasks, instance.task = [], None
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._emergency_frozen = MagicMock(return_value=False)
    instance.enter_room = MagicMock()
    instance.back = MagicMock()
    instance.get_agent_from_room = MagicMock(
        return_value=[{"time": None}, {"time": None}]
    )
    instance.get_resting_plan = MagicMock(
        side_effect=lambda candidates, replacements, plan, count: plan.update(
            {"central": ["陈"], "dormitory_1": ["歌蕾蒂娅"]}
        )
    )
    monkeypatch.setattr(base, "try_reorder", lambda data, plan: {})
    return instance


def pending_shift(solver, *, plan=None, task_type=TaskTypes.SHIFT_OFF):
    task = SchedulerTask(
        time=datetime(2026, 10, 8, 11),
        task_type=task_type,
        task_plan=plan or {"central": ["陈"], "dormitory_1": ["歌蕾蒂娅"]},
    )
    solver.tasks.append(task)
    return task


def generated_deadlines(solver):
    solver.run_order_solver()
    return [task for task in solver.tasks if task.type == TaskTypes.EXHAUST_OFF]


def bind_group(solver, *names):
    solver.op_data.groups["深海"] = list(names)
    for name in names:
        solver.op_data.operators[name].group = "深海"


def test_complete_pending_shift_prevents_regeneration_and_room_read(solver):
    pending = pending_shift(solver)
    original_time, original_plan = pending.time, pending.plan.copy()

    assert generated_deadlines(solver) == []
    assert solver.tasks == [pending]
    assert (pending.time, pending.plan) == (original_time, original_plan)
    solver.enter_room.assert_not_called()


def test_pending_shift_of_one_operator_does_not_block_independent_operator(solver):
    pending = pending_shift(solver)
    solver.op_data.exhaust_agent.append("幽灵鲨")

    deadlines = generated_deadlines(solver)

    assert len(deadlines) == 1
    assert deadlines[0].meta_data == "幽灵鲨"
    assert pending in solver.tasks


@pytest.mark.parametrize(
    "task_type",
    [
        TaskTypes.SHIFT_ON,
        TaskTypes.FIAMMETTA,
        TaskTypes.RUN_ORDER,
        TaskTypes.SELF_CORRECTION,
        TaskTypes.RELEASE_DORM,
    ],
)
def test_other_task_types_do_not_suppress_exhausted_recovery(solver, task_type):
    pending = pending_shift(solver, task_type=task_type)
    if task_type == TaskTypes.RELEASE_DORM:
        pending.strict_mood_limit = True

    assert len(generated_deadlines(solver)) == 1
    assert pending in solver.tasks


@pytest.mark.parametrize(
    "plan",
    [
        {"central": ["歌蕾蒂娅"], "dormitory_1": ["幽灵鲨"]},
        {"central": ["陈"], "dormitory_1": ["Current"]},
        {"central": ["歌蕾蒂娅"], "dormitory_1": ["歌蕾蒂娅"]},
    ],
)
def test_working_names_and_placeholders_do_not_prove_recovery(solver, plan):
    pending_shift(solver, plan=plan)

    assert len(generated_deadlines(solver)) == 1


def test_partial_recovery_group_does_not_suppress_deadline(solver):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    pending_shift(solver)

    assert len(generated_deadlines(solver)) == 1


def test_separate_partial_arrangements_do_not_prove_one_complete_group(solver):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    pending_shift(solver)
    pending_shift(
        solver,
        plan={"central": ["Current", "红"], "dormitory_2": ["幽灵鲨"]},
    )

    assert len(generated_deadlines(solver)) == 1


def test_complete_recovery_group_suppresses_deadline(solver):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    pending_shift(
        solver,
        plan={"central": ["陈", "红"], "dormitory_1": ["歌蕾蒂娅", "幽灵鲨"]},
    )

    assert generated_deadlines(solver) == []


@pytest.mark.parametrize("member_role", ["dormitory", "workaholic", "multi_group"])
def test_non_recovery_group_members_do_not_require_independent_beds(
    solver, member_role
):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    member = solver.op_data.operators["幽灵鲨"]
    if member_role == "dormitory":
        member.room = "dormitory_1"
    elif member_role == "workaholic":
        member.workaholic = True
    else:
        member.group_bindings = [
            {"group": "深海", "replacement": ["红"]},
            {"group": "其他组", "replacement": ["陈"]},
        ]
    pending_shift(solver)

    assert generated_deadlines(solver) == []


@pytest.mark.parametrize("retains_member", [True, False])
def test_already_resting_group_member_requires_retained_bed(solver, retains_member):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    member = solver.op_data.operators["幽灵鲨"]
    member.current_room, member.current_index = "dormitory_2", 1
    plan = {"central": ["陈"], "dormitory_1": ["歌蕾蒂娅"]}
    if not retains_member:
        plan["dormitory_2"] = ["Current", "Free"]
    pending_shift(solver, plan=plan)

    assert len(generated_deadlines(solver)) == (0 if retains_member else 1)


@pytest.mark.parametrize("retained_target", ["Current", "幽灵鲨"])
def test_explicitly_retained_same_dorm_member_completes_pending_recovery(
    solver, retained_target
):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    member = solver.op_data.operators["幽灵鲨"]
    member.current_room, member.current_index = "dormitory_1", 1
    pending_shift(
        solver,
        plan={"central": ["陈"], "dormitory_1": ["歌蕾蒂娅", retained_target]},
    )

    assert generated_deadlines(solver) == []


def test_group_member_explicitly_returning_to_work_does_not_complete_rest(solver):
    bind_group(solver, "歌蕾蒂娅", "幽灵鲨")
    member = solver.op_data.operators["幽灵鲨"]
    member.current_room, member.current_index = "dormitory_2", 1
    pending_shift(
        solver,
        plan={"central": ["陈", "幽灵鲨"], "dormitory_1": ["歌蕾蒂娅"]},
    )

    assert len(generated_deadlines(solver)) == 1


def test_consumed_or_cancelled_arrangement_reopens_deadline_admission(solver):
    consumed = pending_shift(solver)
    solver.task = consumed
    solver.tasks.remove(consumed)

    assert len(generated_deadlines(solver)) == 1


def test_due_concrete_arrangement_still_suppresses_regeneration(solver):
    pending = pending_shift(solver)
    pending.time = datetime(2026, 10, 8, 10, 34)

    assert generated_deadlines(solver) == []
    assert solver.tasks == [pending]


def test_existing_dynamic_deadline_does_not_duplicate_pending_arrangement(solver):
    pending = pending_shift(solver)
    solver.task = SchedulerTask(
        time=datetime(2026, 10, 8, 10, 35),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="歌蕾蒂娅",
    )
    solver.tasks.insert(0, solver.task)

    solver.overtake_room()

    assert solver.tasks == [solver.task, pending]
    solver.get_resting_plan.assert_not_called()
