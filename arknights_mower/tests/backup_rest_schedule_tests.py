"""副表切换后，回班任务必须使用新排班的耗尽配置和岗位。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config, operators, scheduler_task  # noqa: E402
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.plan import (  # noqa: E402
    Plan,
    PlanConfig,
    Room,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402

pytestmark = pytest.mark.usefixtures("offline_maintenance")


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 9, 11, 16, 2, 21)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    config.conf.enable_mastery = False
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room("歌蕾蒂娅", "", ["陈"])],
                "contact": [Room("黑键", "感知", ["红"])],
                "dormitory_1": [
                    Room("塑心", "感知", ["隐德来希"]),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [
            Plan(
                {},
                PlanConfig("", "歌蕾蒂娅", ""),
                trigger=LogicExpression(
                    "op_data.operators['黑键'].is_resting()", "==", "True"
                ),
            )
        ],
    }
    assert instance.initialize_operators() is None
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    for op in instance.op_data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.time_stamp = Clock.now()
        op.mood = 24
    gladiia = instance.op_data.operators["歌蕾蒂娅"]
    gladiia.time_stamp = datetime(2026, 9, 11, 15, 35, 45, 810059)
    gladiia.mood = 3.1665609162721444
    gladiia.depletion_rate = 3.1050745754008617
    black_key = instance.op_data.operators["黑键"]
    black_key.current_room, black_key.current_index = "dormitory_1", 2
    black_key.mood = 18
    dorm = instance.op_data.dorm[0]
    dorm.name, dorm.time = "黑键", datetime(2026, 9, 11, 17, 13, 3)
    instance.tasks = []
    instance.task = None
    instance.find = MagicMock(return_value=True)
    instance.skip = MagicMock()
    instance.agent_arrange = MagicMock()  # 设备操作；在岗/休息状态已按下班结果设置。
    return instance


def return_task(solver):
    return next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)


@pytest.mark.parametrize("confirmed", [False, True])
def test_shift_off_recomputes_emergency_return_after_backup_switch(solver, confirmed):
    def arrange(plan, read_time):
        if not confirmed:
            return
        # 模拟换人后的读房结果；黑键的恢复床位和时间已在夹具中设置。
        for room, names in plan.items():
            for index, name in enumerate(names):
                if name in ("Current", "Free", ""):
                    continue
                occupant = solver.op_data.get_current_operator(room, index)
                if occupant is not None:
                    occupant.current_room, occupant.current_index = "", -1
                op = solver.op_data.operators[name]
                op.current_room, op.current_index = room, index

    solver.agent_arrange.side_effect = arrange
    solver.task = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={"contact": ["红"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.tasks = [solver.task]
    current = solver.task
    solver.infra_main()
    assert solver.op_data.operators["歌蕾蒂娅"].exhaust_require
    if not confirmed:
        assert current in solver.tasks
        assert current.group_shift_expected[("contact", 0)] == "红"
        assert not any(t.type == TaskTypes.SHIFT_ON for t in solver.tasks)
        return
    assert current.group_shift_expected == {}
    assert return_task(solver).time == datetime(2026, 9, 11, 17, 5, 3)
    assert return_task(solver).plan["dormitory_1"][0] == "塑心"
    solver.agent_arrange.assert_called_once()
    assert solver.agent_arrange.call_args.args[0]["contact"] == ["红"]
    assert "dormitory_1" in solver.agent_arrange.call_args.args[0]


def test_truthy_switch_without_generated_tasks_does_not_start_correction(solver):
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={"contact": ["红"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
    solver._prepare_shift_cycle = MagicMock()
    solver.backup_plan_solver = MagicMock(return_value=True)
    solver.agent_get_mood = MagicMock()

    solver.infra_main()

    solver.agent_get_mood.assert_not_called()


@pytest.mark.parametrize("custom_task", [None, {"central": ["Current"]}])
def test_switch_rebuilds_existing_return_and_preserves_other_tasks(solver, custom_task):
    solver.op_data.backup_plans[0].task = custom_task
    solver.plan_metadata()
    old_task = return_task(solver)
    assert old_task.time == datetime(2026, 9, 11, 16, 24, 21)
    depot = SchedulerTask(task_type=TaskTypes.DEPOT)
    solver.tasks.append(depot)
    assert solver.backup_plan_solver() is False
    assert return_task(solver).time == datetime(2026, 9, 11, 17, 5, 3)
    assert all(t is not old_task for t in solver.tasks)
    assert any(t is depot for t in solver.tasks)
    assert not any(t.plan == {"central": ["Current"]} for t in solver.tasks)


def test_switch_without_existing_rest_schedule_does_not_create_one(solver):
    solver.backup_plan_solver()
    assert all(t.type != TaskTypes.SHIFT_ON for t in solver.tasks)


@pytest.mark.parametrize("path", ["cached", "shift"])
@pytest.mark.parametrize("activating", [False, True])
def test_backup_commit_invalidates_dynamic_exhaust_deadlines(solver, path, activating):
    if not activating:
        assert solver.op_data.swap_plan([True], refresh=True) is None
        solver.op_data.operators["黑键"].current_room = "contact"
    unaffected = SchedulerTask(
        time=base.datetime.now() - timedelta(minutes=9),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="黑键",
    )
    deadlines = [
        SchedulerTask(
            time=base.datetime.now() + timedelta(minutes=minutes),
            task_type=TaskTypes.EXHAUST_OFF,
            meta_data=name,
        )
        for minutes, name in [(-9, "歌蕾蒂娅"), (30, "黑键,歌蕾蒂娅")]
    ]
    concrete = SchedulerTask(
        task_type=TaskTypes.EXHAUST_OFF,
        task_plan={"contact": ["红"]},
        meta_data="黑键",
    )
    depot = SchedulerTask(task_type=TaskTypes.DEPOT)
    support = SchedulerTask(
        task_type=TaskTypes.SWAP_SUPPORT,
        task_plan={"train": ["红"]},
    )
    solver.tasks = [*deadlines, unaffected, concrete, depot, support]
    before = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    if path == "cached":
        solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.backup_shift_conditions = [activating]
        solver.task = task
        solver.tasks.append(task)
        solver._activate_shift_backup(task)

    assert solver.op_data.plan_condition == [activating]
    assert all(not any(task is old for task in solver.tasks) for old in deadlines)
    assert all(
        any(task is kept for task in solver.tasks)
        for kept in (unaffected, concrete, depot, support)
    )
    assert {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    } == before
    assert any(task.type == TaskTypes.NOT_SPECIFIC for task in solver.tasks)


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_unchanged_backup_preserves_dynamic_exhaust_deadline(solver, path):
    assert solver.op_data.swap_plan([True], refresh=True) is None
    old = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="歌蕾蒂娅")
    solver.tasks = [old]
    if path == "cached":
        solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.backup_shift_conditions = [True]
        solver._activate_shift_backup(task)
    assert solver.tasks == [old]


@pytest.mark.parametrize("path", ["cached", "shift"])
def test_failed_backup_commit_preserves_dynamic_exhaust_deadline(solver, path):
    old = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="歌蕾蒂娅")
    solver.tasks = [old]
    swap = solver.op_data.swap_plan
    solver.op_data.swap_plan = MagicMock(
        side_effect=lambda conditions, refresh=False: (
            "invalid merged plan" if conditions == [True] else swap(conditions, refresh)
        )
    )
    if path == "cached":
        assert solver.backup_plan_solver() is False
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.backup_shift_conditions = [True]
        with pytest.raises(ValueError, match="最终排班生效失败"):
            solver._activate_shift_backup(task)
    assert solver.tasks == [old]
    assert solver.op_data.plan_condition == [False]


@pytest.mark.parametrize("change", ["room", "replacement", "group", "group_member"])
def test_backup_staffing_change_invalidates_corresponding_exhaust_task(solver, change):
    backup = solver.op_data.backup_plans[0]
    backup.config.exhaust_require = []
    if change == "room":
        backup.plan = {
            "central": [Room("陈", "", ["红"])],
            "meeting": [Room("歌蕾蒂娅", "", ["陈"])],
        }
    elif change == "replacement":
        backup.plan = {"central": [Room("歌蕾蒂娅", "", ["红"])]}
    elif change == "group":
        backup.plan = {"central": [Room("歌蕾蒂娅", "感知", ["陈"])]}
    else:
        backup.plan = {"dormitory_1": [Room("塑心", "", ["隐德来希"])]}
    affected_name = "黑键" if change == "group_member" else "歌蕾蒂娅"
    old = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data=affected_name)
    solver.tasks = [old]

    solver.backup_plan_solver()

    assert solver.op_data.plan_condition == [True]
    assert not any(task is old for task in solver.tasks)


def test_backup_projection_preserves_exhaust_deadline_until_commit(solver):
    old = SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="歌蕾蒂娅")
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={"contact": ["红"]})
    solver.tasks = [old, task]

    solver._prepare_shift_backup(task)

    assert task.backup_shift_conditions == [True]
    assert solver.op_data.plan_condition == [False]
    assert solver.tasks == [old, task]


def test_changed_exhaust_deadline_rebuilds_from_new_schedule_and_readback(solver):
    old = SchedulerTask(
        time=base.datetime.now() - timedelta(minutes=9),
        task_type=TaskTypes.EXHAUST_OFF,
        meta_data="歌蕾蒂娅",
    )
    solver.tasks = [old]
    solver.backup_plan_solver()
    assert solver.op_data.operators["歌蕾蒂娅"].exhaust_require
    assert not any(task is old for task in solver.tasks)
    solver.tasks = [
        task for task in solver.tasks if task.type != TaskTypes.NOT_SPECIFIC
    ]
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[
            {"agent": "歌蕾蒂娅", "time": base.datetime.now() + timedelta(minutes=40)}
        ]
    )

    solver.run_order_solver()

    rebuilt = [task for task in solver.tasks if task.type == TaskTypes.EXHAUST_OFF]
    assert len(rebuilt) == 1
    assert rebuilt[0].meta_data == "歌蕾蒂娅"
    assert rebuilt[0].time == base.datetime.now() + timedelta(minutes=10)
    assert rebuilt[0].time != old.time
    solver.get_agent_from_room.assert_called_once_with("central", [0])


def reset_default_plan(solver):
    assert solver.op_data.swap_plan([False], refresh=True) is None


@pytest.fixture
def meeting_transition(solver):
    """会客室切表场景：一人已在宿舍回满，另一人待命，独立副表仍开启。"""
    solver.global_plan = {
        "default_plan": Plan(
            {
                "meeting": [
                    Room("信仰搅拌机", "", ["陈"]),
                    Room("跃跃", "", ["见行者"]),
                ],
                "central": [Room("歌蕾蒂娅", "", ["红"])],
                "room_2_1": [Room("野鬃", "", ["结城理"])],
                "dormitory_1": [
                    Room("塑心", "", []),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [
            Plan(
                {},
                PlanConfig("", "", ""),
                trigger=LogicExpression("True", "==", "True"),
            ),
            Plan(
                {
                    "meeting": [
                        Room("埃癸斯", "", ["信仰搅拌机"]),
                        Room("虎狼丸", "", ["跃跃"]),
                    ],
                },
                PlanConfig("", "", ""),
                trigger=LogicExpression(
                    "op_data.operators['结城理'].is_working()", "==", "True"
                ),
            ),
        ],
    }
    assert solver.initialize_operators() is None
    data = solver.op_data
    assert data.swap_plan([True, True], refresh=True) is None
    actual = {
        "meeting": ["埃癸斯", "虎狼丸"],
        "central": ["红"],
        "room_2_1": ["野鬃"],
        "dormitory_1": ["塑心", "冰酿", "信仰搅拌机", "歌蕾蒂娅", "Free"],
    }
    for op in data.operators.values():
        op.current_room, op.current_index = "", -1
        op.mood, op.time_stamp, op.depletion_rate = 24, base.datetime.now(), 0
    for room, names in actual.items():
        for index, name in enumerate(names):
            if name != "Free":
                data.operators[name].current_room = room
                data.operators[name].current_index = index
    data.dorm[0].name = "信仰搅拌机"
    data.dorm[0].time = base.datetime.now() - timedelta(hours=1)
    data.dorm[1].name = "歌蕾蒂娅"
    data.dorm[1].time = base.datetime.now() + timedelta(hours=2)
    data.operators["歌蕾蒂娅"].mood = 12
    solver.tasks = [
        SchedulerTask(
            time=data.dorm[1].time,
            task_type=TaskTypes.SHIFT_ON,
            task_plan={"central": ["歌蕾蒂娅"]},
        )
    ]
    return solver


def test_backup_deactivation_uses_pending_final_arrangement(meeting_transition):
    solver = meeting_transition
    assert solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True, False]
    # 重算多次、以及跑单把最终安排延期后，都不能再制造会客室中间态。
    correction = next(t for t in solver.tasks if "meeting" in t.plan)
    correction.time += timedelta(minutes=5)
    for _ in range(2):
        solver.plan_metadata()
        meeting_tasks = [t for t in solver.tasks if "meeting" in t.plan]
        assert meeting_tasks == [correction]
        assert correction.plan == {"meeting": ["信仰搅拌机", "跃跃"]}
        assert return_task(solver).plan == {"central": ["歌蕾蒂娅"]}
        assert return_task(solver).time == base.datetime.now() + timedelta(
            hours=2, minutes=-8
        )
    # 计划中的回班不应提前清空真实床位，也不能触发真实位置变更回调。
    assert solver.op_data.dorm[0].name == "信仰搅拌机"
    assert solver.op_data.operators["信仰搅拌机"].current_room == "dormitory_1"


def test_cancelled_arrangement_restores_return_planning(meeting_transition):
    solver = meeting_transition
    assert solver.backup_plan_solver()
    solver.tasks = [t for t in solver.tasks if t.type != TaskTypes.SELF_CORRECTION]
    solver.plan_metadata()
    assert any(
        t.type == TaskTypes.SHIFT_ON
        and t.plan.get("meeting") == ["信仰搅拌机", "Current"]
        for t in solver.tasks
    )


def test_arrangement_projection_invalidates_moved_timer_without_touching_live_state(
    meeting_transition, monkeypatch
):
    data = meeting_transition.op_data
    before = [(bed.name, bed.time) for bed in data.dorm]
    callback = MagicMock()
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", callback)
    data.operators["信仰搅拌机"].refresh_drained = True
    projected = data.project_arrangements(
        [
            {
                "meeting": ["信仰搅拌机", "Current"],
                "dormitory_1": ["Current", "Current", "歌蕾蒂娅", "Free", "Current"],
            }
        ]
    )

    assert projected.get_current_operator("meeting", 0).name == "信仰搅拌机"
    assert projected.get_current_operator("meeting", 1).name == "虎狼丸"
    assert projected.operators["埃癸斯"].current_room == ""
    assert projected.dorm[0].name == before[1][0]
    assert projected.dorm[0].time is None
    assert projected.dorm[1].name == ""
    assert projected.dorm[1].time is None
    assert [(bed.name, bed.time) for bed in data.dorm] == before
    assert data.operators["信仰搅拌机"].current_room == "dormitory_1"
    callback.assert_not_called()


@pytest.mark.parametrize("task_type", [TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER])
def test_pending_migration_precedes_dependent_return(meeting_transition, task_type):
    solver = meeting_transition
    assert solver.op_data.swap_plan([True, False], refresh=True) is None
    migration = SchedulerTask(
        time=base.datetime.now() + timedelta(hours=3),
        task_type=task_type,
        task_plan={
            "dormitory_1": ["Current", "Current", "Current", "Free", "歌蕾蒂娅"]
        },
    )
    solver.tasks.append(migration)
    solver.plan_metadata()

    # 换位后恢复时间未知，不能把旧床位的时间套在新床位上。
    assert not any(t.plan.get("central") == ["歌蕾蒂娅"] for t in solver.tasks)
    independent = next(t for t in solver.tasks if "meeting" in t.plan)
    assert independent.time < migration.time
    assert independent.plan == {"meeting": ["信仰搅拌机", "Current"]}
    assert migration in solver.tasks
    solver.op_data = solver.op_data.project_arrangements([migration.plan])
    solver.tasks.remove(migration)
    _, bed = solver.op_data.get_dorm_by_name("歌蕾蒂娅")
    assert bed.time is None
    solver.op_data.refresh_dorm_time(
        *bed.position,
        {"agent": bed.name, "time": migration.time + timedelta(hours=2)},
    )
    solver.plan_metadata()
    dependent = next(t for t in solver.tasks if t.plan.get("central") == ["歌蕾蒂娅"])
    assert dependent.time > migration.time


def test_pending_migration_release_uses_destination_and_preserves_other_returns(
    meeting_transition,
):
    solver = meeting_transition
    data = solver.op_data
    assert data.swap_plan([True, False], refresh=True) is None
    data.config.free_room = True
    data.add(operators.Operator("九色鹿", ""))
    deer = data.operators["九色鹿"]
    deer.current_room, deer.current_index = data.dorm[2].position
    deer.mood, deer.time_stamp = 12, base.datetime.now()
    data.dorm[2].name, data.dorm[2].time = (
        "九色鹿",
        base.datetime.now() + timedelta(hours=1),
    )
    migration = SchedulerTask(
        time=base.datetime.now() + timedelta(hours=3),
        task_type=TaskTypes.RE_ORDER,
        task_plan={
            "meeting": ["信仰搅拌机", "跃跃"],
            "dormitory_1": ["Current", "Current", "九色鹿", "Current", "Free"],
        },
    )
    solver.tasks.append(migration)
    solver.plan_metadata()

    assert not any(t.type == TaskTypes.RELEASE_DORM for t in solver.tasks)
    assert return_task(solver).plan == {"central": ["歌蕾蒂娅"]}
    assert return_task(solver).time < migration.time
    assert data.dorm[2].name == "九色鹿"
    solver.op_data = data.project_arrangements([migration.plan])
    solver.tasks.remove(migration)
    _, bed = solver.op_data.get_dorm_by_name("九色鹿")
    assert bed.time is None
    solver.op_data.refresh_dorm_time(
        *bed.position,
        {"agent": bed.name, "time": migration.time + timedelta(hours=1)},
    )
    solver.plan_metadata()
    release = next(t for t in solver.tasks if t.type == TaskTypes.RELEASE_DORM)
    assert release.meta_data == "九色鹿"
    assert release.plan == {
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"]
    }


@pytest.mark.parametrize(
    "task_type",
    [TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER, TaskTypes.NOT_SPECIFIC],
)
def test_completed_arrangement_rebuilds_from_observed_beds(
    meeting_transition, task_type
):
    solver = meeting_transition
    assert solver.op_data.swap_plan([True, False], refresh=True) is None
    current = SchedulerTask(
        time=base.datetime.now(),
        task_type=task_type,
        task_plan={
            "meeting": ["信仰搅拌机", "跃跃"],
            "dormitory_1": ["Current"] * 3 + ["歌蕾蒂娅", "Current"],
        },
    )
    solver.task = current
    solver.tasks.append(current)

    def arrange(plan, read_time):
        assert read_time
        # 替代设备读屏：第一人回班；另一休息者的完成时间已重新测量。
        data = solver.op_data
        data.dorm[0].reset()
        data.operators["信仰搅拌机"].current_room = "meeting"
        data.operators["信仰搅拌机"].current_index = 0
        data.operators["跃跃"].current_room = "meeting"
        data.operators["跃跃"].current_index = 1
        data.dorm[1].time = base.datetime.now() + timedelta(hours=4)
        plan.clear()

    solver.agent_arrange.side_effect = arrange
    solver.infra_main()

    assert current not in solver.tasks
    assert all("meeting" not in t.plan for t in solver.tasks)
    assert return_task(solver).time == base.datetime.now() + timedelta(
        hours=4, minutes=-8
    )


def test_unrelated_experimental_backup_switch_skips_dorm_reorder(solver, monkeypatch):
    reset_default_plan(solver)
    reorder = MagicMock(return_value={"dormitory_1": ["Current"] * 5})
    monkeypatch.setattr(base, "rebalance_plan_swap_dorms", reorder)

    assert solver.backup_plan_solver() is False

    reorder.assert_not_called()
    assert [task.type for task in solver.tasks] == [TaskTypes.NOT_SPECIFIC]


def test_unified_backup_keeps_zero_mood_worker_on_shift(solver):
    solver.op_data.global_plan["default_plan"].config.workaholic = ["歌蕾蒂娅"]
    reset_default_plan(solver)
    worker = solver.op_data.operators["歌蕾蒂娅"]
    worker.mood = 0
    worker.time_stamp = datetime(2026, 9, 11, 16, 2, 21)

    assert worker.workaholic
    assert solver.backup_plan_solver() is False
    assert solver.op_data.plan_condition == [True]
    assert all("central" not in task.plan for task in solver.tasks)


def test_unified_backup_bed_change_still_reorders(solver, monkeypatch):
    reset_default_plan(solver)
    solver.op_data.backup_plans[0].plan["dormitory_1"] = [
        Room("Current", "", []),
        Room("Current", "", []),
        Room("夜莺", "", []),
        Room("Free", "", []),
        Room("Free", "", []),
    ]
    reorder = MagicMock(
        return_value={
            "dormitory_1": ["夜莺", "Current", "Current", "Current", "Current"]
        }
    )
    monkeypatch.setattr(base, "rebalance_plan_swap_dorms", reorder)

    assert solver.backup_plan_solver() is True

    reorder.assert_called_once()
    assert [task.type for task in solver.tasks] == [
        TaskTypes.RE_ORDER,
        TaskTypes.NOT_SPECIFIC,
    ]


def test_backup_reorder_wakes_planning_even_with_existing_return(solver, monkeypatch):
    reset_default_plan(solver)
    solver.plan_metadata()
    monkeypatch.setattr(
        base, "dorm_rebalance_signature", lambda data: tuple(data.plan_condition)
    )
    monkeypatch.setattr(
        base,
        "rebalance_plan_swap_dorms",
        MagicMock(
            return_value={
                "dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]
            }
        ),
    )
    generated = []

    assert solver.backup_plan_solver(generated_tasks=generated)

    assert any(t.type == TaskTypes.SHIFT_ON for t in solver.tasks)
    wakeups = [t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC]
    assert len(wakeups) == int(True)
    assert wakeups[0].time == generated[0].time
    assert wakeups[0] in generated


def test_backup_reorder_rebuilds_invalidated_run_order_on_next_planning_pass(
    solver, monkeypatch
):
    solver.global_plan["default_plan"].plan["room_1_1"] = [
        Room("鸿雪", "", ["但书", "深巡"])
    ]
    reset_default_plan(solver)
    # 原版常规规划要求宿舍满员；让两种模式在相同可用状态下比较。
    for index, name in ((3, "陈"), (4, "红")):
        solver.op_data.operators[name].current_room = "dormitory_1"
        solver.op_data.operators[name].current_index = index
    solver.plan_metadata()
    # 时间较远的跑单仍沿用原版规则：换班时删除，常规规划负责重建。
    old_order = SchedulerTask(
        time=base.datetime.now() + timedelta(minutes=30),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    solver.tasks.append(old_order)
    solver.refresh_run_order_time("room_1_1")
    assert old_order not in solver.tasks
    assert all(t.type != TaskTypes.REFRESH_TIME for t in solver.tasks)

    solver.op_data.backup_plans[0].config.dorm_order = ["dormitory_1"]
    monkeypatch.setattr(
        base, "dorm_rebalance_signature", lambda data: tuple(data.plan_condition)
    )
    monkeypatch.setattr(
        base,
        "rebalance_plan_swap_dorms",
        MagicMock(
            return_value={
                "dormitory_1": ["Current", "冰酿", "Current", "Current", "Current"]
            }
        ),
    )
    assert solver.backup_plan_solver()
    solver.task = next(t for t in solver.tasks if t.type == TaskTypes.RE_ORDER)

    def arrange(plan, get_time):
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()

    solver.agent_arrange.side_effect = arrange
    solver.skip = base.BaseSchedulerSolver.skip.__get__(solver)
    solver.infra_main()
    assert solver.planned  # 重排完成仍按原流程跳过本轮常规规划。

    wakeup = next(t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC)
    # 下一次 run() 重置 planned；消费空任务后进入正常规划，无需等待回班。
    solver.task, solver.planned = wakeup, False
    solver.infra_main()
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.plan_solver = MagicMock()
    solver.op_data.operators["歌蕾蒂娅"].mood = 24
    solver.op_data.operators["歌蕾蒂娅"].time_stamp = base.datetime.now()
    solver.get_run_order_time = MagicMock(
        return_value=base.datetime.now() + timedelta(hours=1)
    )
    solver.infra_main()

    orders = [t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER]
    assert len(orders) == 1
    assert orders[0].meta_data == "room_1_1"
    assert orders[0].time == solver.get_run_order_time.return_value
    solver.get_run_order_time.assert_called_once_with("room_1_1")


def test_switch_preserves_shift_on_target_when_backup_modifies_room_plan(solver):
    solver.plan_metadata()
    old_task = return_task(solver)
    assert old_task.plan["contact"][0] == "黑键"
    assert old_task.time == datetime(2026, 9, 11, 16, 24, 21)

    # 模拟副表调整了工位（黑键与陈换位），并将歌蕾蒂娅设为用尽
    backup = solver.op_data.backup_plans[0]
    backup.plan = {
        "contact": [Room("陈", "", ["砾"])],
        "central": [Room("黑键", "感知", ["红"])],
        "meeting": [Room("歌蕾蒂娅", "", ["陈"])],
    }
    backup.config.exhaust_require = ["歌蕾蒂娅"]

    solver.backup_plan_solver()

    # 副表已生效且修改了 contact 和 central 的计划
    assert solver.op_data.plan["contact"][0].agent == "陈"
    assert solver.op_data.plan["central"][0].agent == "黑键"
    # The final correction now includes the returning operator directly.
    merged = [task for task in solver.tasks if task.plan]
    assert len(merged) == 1
    assert merged[0].plan == {"central": ["黑键"], "contact": ["陈"]}
    assert not any(task.type == TaskTypes.SHIFT_ON for task in solver.tasks)


def test_deactivation_restores_main_plan_targets_preventing_stickiness(solver):
    solver.plan_metadata()
    # 模拟副表生效
    backup = solver.op_data.backup_plans[0]
    backup.plan = {
        "contact": [Room("陈", "", ["砾"])],
        "central": [Room("黑键", "感知", ["红"])],
        "meeting": [Room("歌蕾蒂娅", "", ["陈"])],
    }
    backup.config.exhaust_require = ["歌蕾蒂娅"]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]

    # Complete the pending arrangement before evaluating the next real state.
    transition = next(task.plan for task in solver.tasks if task.plan)
    solver.op_data = solver.op_data.project_arrangements([transition])
    solver.tasks.clear()
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [False]
    merged = [task for task in solver.tasks if task.plan]
    assert len(merged) == 1
    assert merged[0].plan["contact"] == ["黑键"]
    assert "黑键" not in merged[0].plan.get("central", [])


def test_shift_on_slot_collision_falls_back_gracefully(solver):
    # 快照将黑键指定到 contact 0 号位
    existing_targets = {"黑键": ("contact", 0)}
    # 生效排班中陈为 contact 0 号位
    solver.op_data.plan["contact"][0] = Room("陈", "", [])
    solver.op_data.operators["陈"].room = "contact"
    solver.op_data.operators["陈"].index = 0
    solver.op_data.operators["陈"].operator_type = "high"
    solver.op_data.operators["陈"].current_room = "dormitory_1"
    solver.op_data.operators["陈"].current_index = 1
    # 黑键在生效排班中为 central 0 号位
    solver.op_data.operators["黑键"].room = "central"
    solver.op_data.operators["黑键"].index = 0

    # 同一批次陈与黑键同时安排回班
    batch_dorms = {
        datetime(2026, 9, 11, 17): (
            [
                solver.op_data.dorm[0],  # 黑键
                operators.Dormitory(
                    ("dormitory_1", 1), "陈", datetime(2026, 9, 11, 17)
                ),
            ],
            False,
        )
    }
    tasks = scheduler_task.generate_plan_by_drom(
        batch_dorms, solver.op_data, existing_targets=existing_targets
    )
    assert len(tasks) == 1
    plan = tasks[0].plan
    all_assigned = [agent for agents in plan.values() for agent in agents]
    assert "黑键" in all_assigned
    assert "陈" in all_assigned


def test_active_fiammetta_blocks_every_backup_trigger(solver):
    reset_default_plan(solver)
    data = solver.op_data
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    data.evaluate_expression = MagicMock(wraps=data.evaluate_expression)
    original = list(data.plan_condition)
    generated = []
    assert solver.backup_plan_solver(generated_tasks=generated) is False
    assert data.plan_condition == original
    assert generated == []
    assert solver.tasks == []
    data.evaluate_expression.assert_not_called()


@pytest.mark.parametrize("phase", ["trigger", "charge", "restore"])
def test_due_fiammetta_blocks_backup_between_tasks_and_after_restart(solver, phase):
    reset_default_plan(solver)
    plans = {
        "trigger": {},
        "charge": {"dormitory_1": ["歌蕾蒂娅", "菲亚梅塔"]},
        "restore": {"central": ["歌蕾蒂娅"]},
    }
    task = SchedulerTask(
        time=base.datetime.now(), task_type=TaskTypes.FIAMMETTA, task_plan=plans[phase]
    )
    solver.tasks = [task]
    solver.task = None
    data = solver.op_data
    data.evaluate_expression = MagicMock(wraps=data.evaluate_expression)
    assert solver.backup_plan_solver() is False
    assert data.plan_condition == [False]
    assert solver.tasks == [task]
    data.evaluate_expression.assert_not_called()

    # 完成回岗后恢复正常判断；未来的下一次充能不能长期阻止副表。
    task.time = base.datetime.now() + timedelta(hours=1)
    solver.backup_plan_solver()
    assert data.plan_condition == [True]
    assert data.evaluate_expression.called


def test_gladiia_temporary_charge_does_not_activate_rest_backup(solver):
    reset_default_plan(solver)
    data = solver.op_data
    data.backup_plans[0].trigger = LogicExpression(
        "op_data.operators['歌蕾蒂娅'].is_resting()", "==", "True"
    )
    gladiia = data.operators["歌蕾蒂娅"]
    gladiia.current_room, gladiia.current_index = "dormitory_1", 3
    restore = SchedulerTask(
        time=base.datetime.now(),
        task_type=TaskTypes.FIAMMETTA,
        task_plan={"central": ["歌蕾蒂娅"]},
    )
    solver.task = None
    solver.tasks = [restore]
    assert solver.backup_plan_solver() is False
    assert data.plan_condition == [False]
    gladiia.current_room, gladiia.current_index = "central", 0
    solver.tasks = []
    solver.backup_plan_solver()
    assert data.plan_condition == [False]
    # 真正下班时仍按原条件正常触发。
    gladiia.current_room, gladiia.current_index = "dormitory_1", 3
    solver.backup_plan_solver()
    assert data.plan_condition == [True]
