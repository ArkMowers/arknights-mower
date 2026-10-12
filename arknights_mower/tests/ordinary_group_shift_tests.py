"""普通绑组的完整目标和共享依赖不依赖完整换班预演或定时重试。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import multi_group_shift_tests as shared
from arknights_mower.tests import shift_backup_convergence_tests as cycle
from arknights_mower.tests.multi_group_shift_tests import SHARED
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

cycle_solver = cycle.solver
shared_solver = shared.solver


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    s = object.__new__(base.BaseSchedulerSolver)
    s.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "room_3_2": [Room("白面鸮", "轮休", ["香草"])],
                    "room_3_3": [
                        Room("清流", "", ["杰西卡"]),
                        Room("娜斯提", "轮休", ["杰西卡"]),
                    ],
                    "factory": [Room("赫默", "轮休", ["芳汀"])],
                    "train": [
                        Room("星源", "轮休", ["乌尔比安"]),
                        Room("塞雷娅", "轮休", ["铃兰"]),
                    ],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                    "dormitory_2": [
                        Room("塑心", "", []),
                        Room("冰酿", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert s.op_data.init_and_validate() is None
    s.op_data.first_init = False
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 24, datetime.now()
    for name in ("白面鸮", "娜斯提"):
        s.op_data.operators[name].mood = 0
    s.tasks, s.task = [], None
    s.total_agent = [op for op in s.op_data.operators.values() if op.is_high()]
    s._refresh_deferred_product_reservations = MagicMock()
    s.check_fia = MagicMock(return_value=([], None))
    s.find_next_task = MagicMock(return_value=None)
    return s


@pytest.mark.parametrize("position", ["idle", "target", "unrelated"])
@pytest.mark.parametrize("prefilled", [False, True])
def test_existing_cover_counts_only_at_its_exact_target(solver, position, prefilled):
    s = solver
    cover = s.op_data.operators["芳汀"]
    if position == "target":
        owner = s.op_data.operators["赫默"]
        owner._current_room, owner.current_index = "", -1
        cover._current_room, cover.current_index = "factory", 0
    elif position == "unrelated":
        cover._current_room, cover.current_index = "room_3_2", 0
    plan = {"factory": ["芳汀"]} if prefilled else {}
    original = deepcopy(plan)
    replacements = ["芳汀"] if prefilled else []
    admitted = s.get_resting_plan(
        s.op_data.groups["轮休"].copy(), replacements, plan, 0
    )
    if position == "unrelated":
        assert not admitted and plan == original
    else:
        assert admitted
        assert plan["factory"] == ["芳汀"]
        assert plan["room_3_3"][1] == "杰西卡"


@pytest.mark.parametrize("returning", [(), ("赫默", "星源", "塞雷娅", "清流")])
def test_slot_correction_does_not_suppress_low_mood_group(solver, returning):
    plan = solver.resting(returning=returning)
    assert plan["room_3_3"][1] == "杰西卡"
    assert plan["factory"] == ["芳汀"]
    assert plan["train"] == ["乌尔比安", "铃兰"]


def test_correction_cycle_releases_cover_and_departs_whole_low_mood_group(solver):
    s = solver
    for name in ("清流", "赫默", "星源", "塞雷娅"):
        s.op_data.operators[name]._current_room = ""
        s.op_data.operators[name].current_index = -1
    s.op_data.operators["杰西卡"]._current_room = "room_3_3"
    s.op_data.operators["杰西卡"].current_index = 0
    s.op_data.operators["芳汀"]._current_room = "factory"
    s.op_data.operators["芳汀"].current_index = 0
    s.op_data.operators["乌尔比安"]._current_room = "train"
    s.op_data.operators["乌尔比安"].current_index = 1
    s.op_data.commit_group_shifts({"轮休": False})
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={
            "room_3_3": ["清流", "Current"],
            "factory": ["赫默"],
            "train": ["星源", "塞雷娅"],
        },
    )
    s.task, s.tasks = task, [task]
    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    assert task.plan["room_3_3"] == ["清流", "杰西卡"]
    assert task.plan["factory"] == ["芳汀"]
    assert task.plan["train"] == ["乌尔比安", "铃兰"]
    assert task.group_shift_transitions == {"轮休": True}
    assert not s.op_data.group_is_resting("轮休")


@pytest.mark.parametrize("urgent", [False, True])
@pytest.mark.parametrize("duplicate_destination", [False, True])
def test_partial_return_has_complete_ordinary_targets_before_confirmation(
    cycle_solver, urgent, duplicate_destination
):
    s = cycle_solver
    s.op_data.backup_plans, s.op_data.plan_condition = [], []
    down = cycle.downshift(s)
    s.op_data = s.op_data.project_arrangements([down.plan])
    data = s.op_data
    members = data.shift_group_members("红松")
    assert all(not data.operators[name].multi_group for name in members)
    assert all(data.operators[name].is_resting() for name in members)
    for name in members:
        data.operators[name].mood = 10
    for bed in data.all_dorms():
        if bed.name in members:
            bed.time = datetime.now() + timedelta(hours=3)
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={"central": ["薇薇安娜"]}
    )
    if duplicate_destination:
        task.plan["dormitory_1"] = ["Current", "Current", "Current", "野鬃", "Current"]
    s.task, s.tasks = task, [task]
    if urgent:
        s.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    s._prepare_group_shift(task)
    s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    confirmed = dict(data.group_shift_state)
    s.op_data = data.project_arrangements([task.plan])
    s.op_data.group_shift_state = confirmed
    assert s._complete_group_shift(task)
    assert all(s.op_data.operators[name].is_working() for name in members)
    assert not s.op_data.group_is_resting("红松")


def test_unrelated_pending_confirmation_does_not_delay_group(cycle_solver):
    s = cycle_solver
    pending = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"central": ["薇薇安娜"]}
    )
    pending.group_shift_expected = {("central", 0): "薇薇安娜"}
    pending.group_shift_transitions = {"红松": False}
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"room_2_2": ["苍苔", "引星棘刺"]},
    )
    s.task, s.tasks = task, [pending, task]
    before = task.time
    s._prepare_group_shift(task, remember_targets=True)
    assert task.time == before
    assert task.group_shift_transitions == {"深海": True}
    assert s._pending_group_transitions() == {"红松": False, "深海": True}


@pytest.mark.parametrize("urgent", [False, True])
def test_partial_departure_completes_matching_and_beds(cycle_solver, urgent):
    s = cycle_solver
    s.op_data.backup_plans, s.op_data.plan_condition = [], []
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={
            "central": ["陈"],
            "dormitory_1": ["Current", "Current", "薇薇安娜", "Current", "Current"],
        },
    )
    s.task, s.tasks = task, [task]
    if urgent:
        s.tasks.append(SchedulerTask(task_type=TaskTypes.FIAMMETTA))
    s.op_data.commit_group_shifts({})
    original_state = dict(s.op_data.group_shift_state)
    s._prepare_group_shift(task)
    assert s.op_data.group_shift_state == original_state
    s._prepare_shift_cycle(task)
    s._prepare_group_shift(task, remember_targets=True)
    assert task.plan["room_1_2"] == ["酒神", "食铁兽"]
    for name in s.op_data.shift_group_members("红松"):
        assert name in task.plan["dormitory_1"]
    confirmed = dict(s.op_data.group_shift_state)
    s.op_data = s.op_data.project_arrangements([task.plan])
    s.op_data.group_shift_state = confirmed
    assert s._complete_group_shift(task)
    assert s.op_data.group_is_resting("红松")


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("failed", [False, True])
def test_shared_confirmation_dependency_resumes_without_clock_delay(
    shared_solver, restart, failed, monkeypatch
):
    import pickle

    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    s = shared_solver
    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈", "Current"]}
    )
    second = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["Current", "初雪"]}
    )
    # Both bindings have a common cover; only the started task's confirmation blocks.
    s.op_data.operators[SHARED].group_bindings[1]["replacement"] = ["红"]
    s.task, s.tasks = first, [first, second]
    s._prepare_group_shift(first, remember_targets=True)
    before = second.time
    with pytest.raises(base.GroupShiftBlocked) as error:
        s._prepare_group_shift(second, remember_targets=True)
    assert error.value.predecessors == (first,)
    assert error.value.groups == set()
    s._suspend_group_shift(
        second, error.value.groups, predecessors=error.value.predecessors
    )
    if restart:
        for attr in (
            "daily_visit_friend",
            "daily_report",
            "daily_skland",
            "daily_mail",
            "task_count",
        ):
            setattr(s, attr, None)
        monkeypatch.setattr(main, "base_scheduler", s)
        snapshot = pickle.loads(pickle.dumps(current_state()))
        s.tasks, s.waiting_group_shifts = (
            snapshot["tasks"],
            snapshot["waiting_group_shifts"],
        )
        first, second = s.tasks[0], s.waiting_group_shifts[0]
        assert second.group_shift_predecessors[0] is first
    s.task = first
    for _ in range(2):
        s._resume_waiting_group_shifts()
        assert second not in s.tasks
        assert second.time == before
    if failed:
        assert not s._complete_group_shift(first)
        s._resume_waiting_group_shifts()
        assert second not in s.tasks
        assert first.execution_failure
    confirmed = dict(s.op_data.group_shift_state)
    observed = dict(first.plan)
    s.op_data = s.op_data.project_arrangements([observed])
    s.op_data.group_shift_state = confirmed
    assert s._complete_group_shift(first)
    assert second in s.tasks and not s.waiting_group_shifts
    assert second.time == before
    assert second.group_shift_transitions == {"乙": True}
    assert s.op_data.group_is_resting("甲")
    assert not s.op_data.group_is_resting("乙")
    s._resume_waiting_group_shifts()
    assert sum(task is second for task in s.tasks) == 1
    s._prepare_group_shift(second, remember_targets=True)
    assert second.group_shift_expected["meeting", 1] == "初雪"


def test_true_group_return_suppresses_immediate_departure(solver):
    assert solver.resting(returning_groups={"轮休"}) == {}


def test_dispatch_suspends_confirmation_dependency_without_changing_time(
    shared_solver, monkeypatch
):
    s = shared_solver
    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈", "Current"]}
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["Current", "初雪"]}
    )
    s.task, s.tasks = first, [first, task]
    s._prepare_group_shift(first, remember_targets=True)
    before = task.time
    s.task = task
    s.find = MagicMock(return_value=(1, 1))
    s.refresh_connecting = False
    s.agent_arrange = MagicMock()
    s.skip = MagicMock()
    monkeypatch.setattr(base, "protect_priority_tasks", lambda tasks, **kwargs: None)
    s.infra_main()
    assert s.waiting_group_shifts == [task]
    assert task.group_shift_predecessors == (first,)
    assert task not in s.tasks and first in s.tasks
    assert task.time == before
    s.agent_arrange.assert_not_called()


def test_distinct_shared_slots_do_not_make_transitive_dependencies(shared_solver):
    s = shared_solver
    slots = s.global_plan["default_plan"].plan
    slots["dormitory_2"] = [
        Room("杜林", "", []),
        Room("夜莺", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    slots["central"] = [Room("能天使", "丙", ["夜刀"])]
    slots["factory"] = [
        Room(
            "清道夫",
            "乙",
            ["砾"],
            group_bindings=[{"group": "丙", "replacement": ["砾"]}],
        )
    ]
    assert s.initialize_operators() is None
    for op in s.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
    first = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"meeting": ["陈", "Current"]}
    )
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"central": ["夜刀"]})
    s.task, s.tasks = first, [first, task]
    s._prepare_group_shift(first, remember_targets=True)
    before = task.time
    s.task = task
    s._prepare_group_shift(task, remember_targets=True)
    assert task.plan["factory"] == ["砾"]
    assert task.time == before
    assert task.group_shift_transitions == {"丙": True}
