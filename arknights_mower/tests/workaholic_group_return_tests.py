"""副表启用零心情工作后，原休息成员仍随已确认的绑组一起回班。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    rebalance_plan_swap_dorms,
)

GROUP = "深海队"
WORKERS = ["乌尔比安", "斯卡蒂", "安哲拉", "幽灵鲨"]
MEMBERS = ["歌蕾蒂娅", "伊内丝", "深巡", *WORKERS]

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda _: False)
    config.conf.enable_mastery = False
    # 取用户排班中的绑组、回满要求、零心情副表及四个实际床位。
    layout = {
        "central": [Room("歌蕾蒂娅", GROUP, ["玛恩纳"])],
        "meeting": [Room("伊内丝", GROUP, ["塞雷娅"])],
        "room_1_1": [Room("深巡", GROUP, ["古米"])],
        "room_2_1": [
            Room("乌尔比安", GROUP, ["娜斯提"]),
            Room("斯卡蒂", GROUP, ["多萝西"]),
        ],
        "room_2_2": [Room("安哲拉", GROUP, ["赫默"])],
        "room_3_2": [Room("幽灵鲨", GROUP, ["白面鸮"])],
    }
    for index, managers in enumerate(
        [
            ("流明", "琴柳"),
            ("撷英调香师", "杜林"),
            ("闪灵", "夜莺"),
            ("絮雨", "车尔尼"),
        ],
        1,
    ):
        layout[f"dormitory_{index}"] = [
            *(Room(name, "", []) for name in managers),
            *(Room("Free", "", []) for _ in range(3)),
        ]
    data = Operators(
        {
            "default_plan": Plan(
                layout,
                PlanConfig(
                    rest_in_full="歌蕾蒂娅",
                    exhaust_require="",
                    resting_priority=",".join(WORKERS),
                ),
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", "", workaholic=",".join(WORKERS)),
                    trigger=LogicExpression(
                        "op_data.operators['歌蕾蒂娅'].current_mood() >= 18",
                        "and",
                        "op_data.operators['乌尔比安'].current_mood() >= 8",
                    ),
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    now = datetime.now()
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, now
    for name in MEMBERS:
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        cover = data.operators[op.replacement[0]]
        cover._current_room, cover.current_index = op.room, op.index
    for name, position, mood, hours in [
        ("歌蕾蒂娅", ("dormitory_1", 2), 18.89, 1.7),
        ("深巡", ("dormitory_2", 2), 22.29, 0.5),
        ("乌尔比安", ("dormitory_3", 2), 17.57, 2.2),
        ("安哲拉", ("dormitory_4", 4), 18.65, 1.5),
    ]:
        op = data.operators[name]
        op._current_room, op.current_index, op.mood = *position, mood
        bed = next(bed for bed in data.dorm if bed.position == position)
        bed.name, bed.time = name, now + timedelta(hours=hours)
    data.commit_group_shifts({GROUP: True})
    data.first_init = False
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data, instance.tasks, instance.task = data, [], None
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(side_effect=AssertionError("device access"))
    instance._sync_run_order_tasks = MagicMock()
    return instance


def test_backup_zero_mood_keeps_existing_group_recovery_and_correction(solver):
    data = solver.op_data
    previous = copy.deepcopy(data.dorm)
    assert data.swap_plan([True], refresh=True) is None
    assert all(not data.is_group_shift_anchor(data.operators[name]) for name in WORKERS)
    before = {bed.name: (bed.position, bed.time) for bed in previous if bed.name}
    migration = rebalance_plan_swap_dorms(data, previous)
    assert migration == {}
    assert {
        bed.name: (bed.position, bed.time) for bed in data.dorm if bed.name
    } == before
    for _ in range(2):
        correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
        assert not (
            set(MEMBERS)
            & {
                name
                for room, row in correction.items()
                if not room.startswith("dorm")
                for name in row
            }
        )
    assert data.group_is_resting(GROUP)
    solver.enter_room.assert_not_called()


def test_group_return_keeps_deadline_then_confirms_all_members(solver):
    data = solver.op_data
    assert data.swap_plan([True], refresh=True) is None
    tasks = plan_metadata(data, [])
    task = next(task for task in tasks if task.type == TaskTypes.SHIFT_ON)
    deadline = data.get_dorm_by_name("歌蕾蒂娅")[1].time
    assert task.time == deadline
    assert set(MEMBERS) <= {name for row in task.plan.values() for name in row}
    for _ in range(2):
        tasks = plan_metadata(data, tasks)
        returns = [item for item in tasks if item.type == TaskTypes.SHIFT_ON]
        assert len(returns) == 1 and returns[0].time == deadline
    # 原有回班安排到期后，用实测满心情释放整组，不另加重试任务。
    data.operators["歌蕾蒂娅"].mood = 24
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    expected = dict(task.group_shift_expected)
    assert set(MEMBERS) <= set(expected.values())
    for (room, index), name in expected.items():
        current = data.get_current_operator(room, index)
        if current is not None:
            current._current_room, current.current_index = "", -1
        op = data.operators[name]
        op._current_room, op.current_index = room, index
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting(GROUP)
    assert all(data.operators[name].is_working() for name in MEMBERS)
    assert not task.group_shift_expected
    solver.enter_room.assert_not_called()


def test_unrelated_backup_cycle_does_not_recall_zero_mood_group(solver):
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    assert solver.backup_plan_solver() is False
    assert solver.op_data.plan_condition == [True]
    for task in solver.tasks:
        assert (
            not (
                set(MEMBERS)
                & {
                    name
                    for room, row in task.plan.items()
                    if not room.startswith("dorm")
                    for name in row
                }
            )
            or task.type == TaskTypes.SHIFT_ON
        )
    assert solver.op_data.group_is_resting(GROUP)


@pytest.mark.parametrize("role", ["ungrouped", "all_zero", "working_group"])
def test_zero_mood_workers_outside_resting_mixed_group_return_normally(solver, role):
    data = solver.op_data
    if role == "ungrouped":
        data.global_plan["default_plan"].plan["room_2_1"][0].group = ""
    elif role == "all_zero":
        data.backup_plans[0].config.workaholic = MEMBERS.copy()
    else:
        data.commit_group_shifts({GROUP: False})
    previous = copy.deepcopy(data.dorm)
    assert data.swap_plan([True], refresh=True) is None
    migration = rebalance_plan_swap_dorms(data, previous)
    assert not any(bed.name == "乌尔比安" for bed in data.dorm)
    assert not data.workaholic_follows_resting_group(data.operators["乌尔比安"])
    assert migration


def test_repeated_correction_preserves_original_return_and_unrelated_dispatch(solver):
    data = solver.op_data
    assert data.swap_plan([True], refresh=True) is None
    tasks = plan_metadata(data, [])
    returning = next(task for task in tasks if task.type == TaskTypes.SHIFT_ON)
    ready = SchedulerTask(task_type=TaskTypes.RECRUIT)
    solver.tasks = [returning, ready]
    original = returning.time, copy.deepcopy(returning.plan)
    for _ in range(2):
        solver.agent_get_mood(read_rooms=False)
        solver.tasks.sort(key=lambda item: item.time)
        assert base.BaseSchedulerSolver.find_next_task(solver) is ready
        assert len(solver.tasks) == 2
        assert returning in solver.tasks
        assert (returning.time, returning.plan) == original
    assert not getattr(solver, "waiting_group_shifts", [])


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("restore", [False, True])
def test_backup_refresh_preserves_confirmed_resting_state(solver, initial, restore):
    import jsonpickle

    data = solver.op_data
    if restore:
        data.restore_group_shift_state(
            jsonpickle.decode(jsonpickle.encode(data.group_shift_state))
        )
    data.first_init = initial
    assert data.swap_plan([True], refresh=True) is None
    data.commit_group_shifts({})
    assert data.group_shift_state[GROUP] is True
    assert data.workaholic_follows_resting_group(data.operators["乌尔比安"])


def test_all_zero_transition_requires_complete_group_confirmation(solver):
    data = solver.op_data
    data.backup_plans[0].config.workaholic = MEMBERS.copy()
    previous = copy.deepcopy(data.dorm)
    assert data.swap_plan([True], refresh=True) is None
    data.commit_group_shifts({})
    assert data.group_shift_state[GROUP] is True
    one = {"room_2_1": ["乌尔比安", "Current"]}
    assert data.arrangement_group_transitions(one) == {}
    plan = rebalance_plan_swap_dorms(data, previous)
    assert set(MEMBERS) <= {
        name
        for room, row in plan.items()
        if not room.startswith("dorm")
        for name in row
    }
    assert data.arrangement_group_transitions(plan) == {GROUP: False}
    assert data.group_shift_state[GROUP] is True
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.RE_ORDER)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    expected = dict(task.group_shift_expected)
    assert set(MEMBERS) <= set(expected.values())
    # 计划与部分已完成房间都不能先把组标成上班。
    assert data.group_shift_state[GROUP] is True
    for (room, index), name in expected.items():
        current = data.get_current_operator(room, index)
        if current is not None:
            current._current_room, current.current_index = "", -1
        data.operators[name]._current_room, data.operators[name].current_index = (
            room,
            index,
        )
    assert solver._complete_group_shift(task)
    assert data.group_shift_state[GROUP] is False


def test_all_zero_correction_completes_the_original_resting_group(solver):
    from arknights_mower.utils.resting_correction import prefer_resting_replacements

    data = solver.op_data
    data.backup_plans[0].config.workaholic = MEMBERS.copy()
    assert data.swap_plan([True], refresh=True) is None
    plan = {"room_2_1": ["乌尔比安", "Current"]}
    prefer_resting_replacements(data, plan, lambda _: False)
    assert set(MEMBERS) <= {name for row in plan.values() for name in row}
    assert data.group_shift_state[GROUP] is True


def test_initial_all_zero_group_stays_working_without_a_resting_transition(solver):
    data = solver.op_data
    data.backup_plans[0].config.workaholic = MEMBERS.copy()
    data.group_shift_state = {}
    assert data.swap_plan([True], refresh=True) is None
    data.commit_group_shifts({})
    assert data.group_shift_state[GROUP] is False
    assert not any(
        data.workaholic_follows_resting_group(data.operators[name]) for name in MEMBERS
    )


@pytest.fixture
def dorm_group_solver(solver, request):
    shared = getattr(request, "param", False)
    layout = {
        "contact": [Room("芬", "甲", ["香草"])],
        "meeting": [Room("桃金娘", "甲", ["清道夫"])],
        "recycle": [Room("梓兰", "乙", ["史都华德"])],
        "dormitory_1": [
            Room(
                "杜林",
                "甲",
                ["夜莺"],
                group_bindings=[{"group": "乙", "replacement": ["夜莺"]}]
                if shared
                else [],
            ),
            Room("流明", "", []),
            *(Room("Free", "", []) for _ in range(3)),
        ],
    }
    data = Operators(
        {
            "default_plan": Plan(layout, PlanConfig("", "", "")),
            "backup_plans": [Plan({}, PlanConfig("", "", "", workaholic="芬,桃金娘"))],
        }
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.time_stamp, op.mood = datetime.now(), 24
    for name in ("芬", "桃金娘", "杜林", "梓兰"):
        op = data.operators[name]
        op._current_room, op.current_index = "", -1
        cover = data.operators[op.replacement[0]]
        cover._current_room, cover.current_index = op.room, op.index
    data.commit_group_shifts({"甲": True, "乙": True})
    data.first_init = False
    assert data.swap_plan([True], refresh=True) is None
    solver.op_data = data
    return solver


def test_all_zero_return_restores_fixed_dorm_member_before_confirmation(
    dorm_group_solver,
):
    from arknights_mower.utils.resting_correction import (
        correct_group_dorms,
        prefer_resting_replacements,
    )

    solver = dorm_group_solver
    data = solver.op_data
    plan = {"contact": ["芬"]}
    prefer_resting_replacements(data, plan, lambda _: False)
    assert plan["dormitory_1"][0] == "杜林"
    correct_group_dorms(data, plan, lambda _: False)
    assert plan["dormitory_1"][0] == "杜林"
    assert data.arrangement_group_transitions(plan) == {"甲": False}
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.RE_ORDER)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.group_shift_expected["dormitory_1", 0] == "杜林"
    assert data.group_is_resting("甲")
    for (room, index), name in task.group_shift_expected.items():
        current = data.get_current_operator(room, index)
        if current:
            current._current_room, current.current_index = "", -1
        data.operators[name]._current_room, data.operators[name].current_index = (
            room,
            index,
        )
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")


@pytest.mark.parametrize("target", ["Current", None])
def test_all_zero_return_accepts_observed_exact_primary_only(dorm_group_solver, target):
    solver = dorm_group_solver
    data = solver.op_data
    plan = {
        "contact": ["芬"],
        "dormitory_1": ["杜林", "Current", "Current", "Current", "Current"],
    }
    if target:
        plan["meeting"] = [target]
    assert data.arrangement_group_transitions(plan) == {}
    worker = data.operators["桃金娘"]
    worker._current_room, worker.current_index = worker.room, worker.index
    assert data.arrangement_group_transitions({}) == {}
    assert data.arrangement_group_transitions(plan) == {"甲": False}
    conflicting = copy.deepcopy(plan)
    conflicting["meeting"] = ["清道夫"]
    assert data.arrangement_group_transitions(conflicting) == {}
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.RE_ORDER)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert set(task.group_shift_expected.values()) >= {"芬", "桃金娘", "杜林"}
    assert data.group_is_resting("甲")
    for (room, index), name in task.group_shift_expected.items():
        current = data.get_current_operator(room, index)
        if current:
            current._current_room, current.current_index = "", -1
        data.operators[name]._current_room, data.operators[name].current_index = (
            room,
            index,
        )
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")


@pytest.mark.parametrize("dorm_group_solver", [True], indirect=True)
def test_all_zero_return_preserves_shared_dorm_other_resting_binding(dorm_group_solver):
    from arknights_mower.utils.resting_correction import (
        correct_group_dorms,
        prefer_resting_replacements,
    )

    solver = dorm_group_solver
    data = solver.op_data
    plan = {"contact": ["芬"]}
    prefer_resting_replacements(data, plan, lambda _: False)
    correct_group_dorms(data, plan, lambda _: False)
    assert plan.get("dormitory_1", ["Current"])[0] != "杜林"
    assert data.arrangement_group_transitions(plan) == {"甲": False}
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.RE_ORDER)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan.get("dormitory_1", ["Current"])[0] != "杜林"
    assert "杜林" not in task.group_shift_expected.values()
    assert data.group_is_resting("乙")
    worker = data.operators["芬"]
    worker._current_room, worker.current_index = "dormitory_1", 2
    bed = next(bed for bed in data.dorm if bed.position == ("dormitory_1", 2))
    bed.name, bed.time = "芬", datetime.now() + timedelta(hours=1)
    migration = rebalance_plan_swap_dorms(data, copy.deepcopy(data.dorm))
    assert migration["contact"] == ["芬"]
    assert migration.get("dormitory_1", ["Current"])[0] != "杜林"
    assert data.arrangement_group_transitions(migration) == {"甲": False}
    assert data.group_is_resting("乙")


@pytest.mark.parametrize(
    "source", ["correction", "native", "retained", "suspended", "partial"]
)
def test_training_protection_blocks_partial_zero_group_and_releases_original_task(
    dorm_group_solver, monkeypatch, source
):
    from arknights_mower.utils.resting_correction import prefer_resting_replacements

    solver = dorm_group_solver
    data = solver.op_data
    # 合法主班在切表前已绑定训练室；两名工作主班现均由替班在岗。
    layout = data.global_plan["default_plan"].plan
    layout["train"] = layout.pop("meeting")
    data.plan_condition = [False]
    assert data.swap_plan([True], refresh=True) is None
    cover = data.operators["清道夫"]
    cover._current_room, cover.current_index = "train", 0
    protected = [True]
    config.conf.enable_mastery = True
    monkeypatch.setattr(solver, "_train_scheduling_protected", lambda: protected[0])
    monkeypatch.setattr(solver, "_train_mastery_active", lambda: protected[0])
    monkeypatch.setattr(solver, "_train_protected", lambda: False)
    plan = {"contact": ["芬"]}
    if source == "correction":
        prefer_resting_replacements(data, plan, lambda name: name == "桃金娘")
        solver._suppress_train_correction(plan)
    elif source == "native":
        plan.update(
            train=["桃金娘"],
            dormitory_1=["杜林", "Current", "Current", "Current", "Current"],
        )
    task = SchedulerTask(task_plan=plan, task_type=TaskTypes.RE_ORDER)
    if source == "retained":
        task.execution_retained = True
    solver.task, solver.tasks = task, [task]
    if source == "partial":
        protected[0] = False
        solver._prepare_group_shift(task, remember_targets=True)
        data.operators["香草"]._current_room, data.operators["香草"].current_index = (
            "",
            -1,
        )
        data.operators["芬"]._current_room, data.operators["芬"].current_index = (
            "contact",
            0,
        )
        del task.plan["contact"]
        del task.plan["train"]
        task.training_skipped_slots = {0}
        task.execution_retained = True
        protected[0] = True
    original_expected = copy.deepcopy(getattr(task, "group_shift_expected", {}))
    original_transitions = copy.deepcopy(getattr(task, "group_shift_transitions", {}))
    deadline, original = task.time, copy.deepcopy(task.plan)
    if source == "suspended":
        solver._suspend_group_shift(task, {"乙"})
        assert task not in solver.tasks
        assert solver.waiting_group_shifts == [task]
        solver._resume_waiting_group_shifts()
        assert task not in solver.tasks
        data.commit_group_shifts({"乙": False})
        # 当前执行的其他组任务不能接收这个等待任务的训练依赖失败。
        other = SchedulerTask(task_type=TaskTypes.RE_ORDER)
        solver.task = other
        solver._resume_waiting_group_shifts()
        assert not getattr(other, "execution_failure", None)
        assert task.execution_failure["rooms"] == ("train",)
        assert task.execution_failure["dependency"]
        assert solver.tasks == [task]
        assert not solver.waiting_group_shifts
        assert not hasattr(task, "group_shift_waiting")
        assert task.time == deadline and task.plan == original
        solver._resume_waiting_group_shifts()
        assert solver.tasks == [task]
        solver.task = task
    for _ in range(2):
        with pytest.raises(base.ProductSwitchDeferred) as blocked:
            solver._prepare_group_shift(task, remember_targets=True)
        assert blocked.value.ready_at is None
        assert blocked.value.rooms == ("train",)
        solver._retain_failed_task(
            task, str(blocked.value), blocked.value.rooms, dependency=True
        )
        assert task.time == deadline and task.plan == original
        assert data.group_is_resting("甲")
        assert getattr(task, "group_shift_expected", {}) == original_expected
        assert getattr(task, "group_shift_transitions", {}) == original_transitions
    ready = SchedulerTask(task_type=TaskTypes.RECRUIT)
    solver.tasks.append(ready)
    assert base.BaseSchedulerSolver.find_next_task(solver) is ready
    solver._resume_failed_tasks()
    assert task.execution_failure
    # 真实训练观测变化后释放原任务，完整组回班仍需最终实测确认。
    protected[0] = False
    data.room_observations = {"train": datetime.now()}
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert task.time == deadline
    solver._prepare_group_shift(task, remember_targets=True)
    if source == "partial":
        assert "contact" not in task.plan
    assert task.group_shift_transitions == {"甲": False}
    assert set(task.group_shift_expected.values()) >= {"芬", "桃金娘", "杜林"}
    assert data.group_is_resting("甲")
    for (room, index), name in task.group_shift_expected.items():
        current = data.get_current_operator(room, index)
        if current:
            current._current_room, current.current_index = "", -1
        data.operators[name]._current_room, data.operators[name].current_index = (
            room,
            index,
        )
    assert solver._complete_group_shift(task)
    assert not data.group_is_resting("甲")
