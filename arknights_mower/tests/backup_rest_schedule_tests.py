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
    PlanTriggerTiming,
    Room,
)
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


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
                trigger_timing="AFTER_PLANNING",
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


def test_shift_off_recomputes_emergency_return_after_backup_switch(solver):
    solver.task = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={"contact": ["红"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.tasks = [solver.task]
    solver.infra_main()
    assert solver.op_data.operators["歌蕾蒂娅"].exhaust_require
    assert return_task(solver).time == datetime(2026, 9, 11, 17, 5, 3)
    assert return_task(solver).plan["dormitory_1"][0] == "塑心"
    solver.agent_arrange.assert_called_once_with({"contact": ["红"]}, True)


def test_completed_shift_off_queues_new_plan_correction_before_backup_task(solver):
    backup = solver.op_data.backup_plans[0]
    backup.trigger_timing = PlanTriggerTiming.BEFORE_PLANNING
    backup.task = {"central": ["Current"]}
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={"contact": ["红"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]

    def queue_correction(*, force=False):
        assert force
        solver.tasks.append(
            SchedulerTask(
                task_plan={"contact": ["黑键"]},
                task_type=TaskTypes.SELF_CORRECTION,
            )
        )
        return "self_correction"

    solver.agent_get_mood = MagicMock(side_effect=queue_correction)
    solver.infra_main()

    correction = next(
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    )
    backup_task = next(task for task in solver.tasks if task.plan == backup.task)
    assert correction.time < backup_task.time
    assert current not in solver.tasks
    solver.agent_get_mood.assert_called_once_with(force=True)


def test_truthy_switch_without_generated_tasks_does_not_start_correction(solver):
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={"contact": ["红"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
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
    assert solver.backup_plan_solver() == bool(custom_task)
    assert return_task(solver).time == datetime(2026, 9, 11, 17, 5, 3)
    assert all(t is not old_task for t in solver.tasks)
    assert any(t is depot for t in solver.tasks)
    if custom_task:
        assert any(t.plan == custom_task for t in solver.tasks)


def test_unchanged_or_not_yet_eligible_backup_keeps_return(solver):
    solver.plan_metadata()
    original = return_task(solver)
    solver.backup_plan_solver(PlanTriggerTiming.BEFORE_PLANNING)
    assert return_task(solver) is original
    solver.backup_plan_solver()
    updated = return_task(solver)
    solver.backup_plan_solver()
    assert return_task(solver) is updated


def test_switch_without_existing_rest_schedule_does_not_create_one(solver):
    solver.backup_plan_solver()
    assert all(t.type != TaskTypes.SHIFT_ON for t in solver.tasks)


def enable_experimental_dorm_logic(solver):
    solver.op_data.config.experimental_dorm_logic = True
    solver.op_data.global_plan["default_plan"].config.experimental_dorm_logic = True
    for backup in solver.op_data.global_plan["backup_plans"]:
        backup.config.experimental_dorm_logic = True
    assert solver.op_data.swap_plan([False], refresh=True) is None


@pytest.fixture
def meeting_transition(solver):
    """alex 的切表场景：一人已在宿舍回满，另一人待命，独立副表仍开启。"""
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
            PlanConfig("", "", "", experimental_dorm_logic=True),
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
    config.conf.experimental_dorm_logic = True
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


def test_arrangement_projection_moves_timers_without_touching_live_state(
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
    assert (projected.dorm[0].name, projected.dorm[0].time) == before[1]
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

    dependent = next(t for t in solver.tasks if t.plan.get("central") == ["歌蕾蒂娅"])
    independent = next(t for t in solver.tasks if "meeting" in t.plan)
    assert dependent.time > migration.time
    assert independent.time < migration.time
    assert independent.plan == {"meeting": ["信仰搅拌机", "Current"]}


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

    release = next(t for t in solver.tasks if t.type == TaskTypes.RELEASE_DORM)
    assert release.plan == {
        "dormitory_1": ["Current", "Current", "Free", "Current", "Current"]
    }
    assert release.time > migration.time
    assert return_task(solver).plan == {"central": ["歌蕾蒂娅"]}
    assert return_task(solver).time < migration.time
    assert data.dorm[2].name == "九色鹿"


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
    enable_experimental_dorm_logic(solver)
    reorder = MagicMock(return_value={"dormitory_1": ["Current"] * 5})
    monkeypatch.setattr(base, "rebalance_plan_swap_dorms", reorder)

    assert solver.backup_plan_solver() is False

    reorder.assert_not_called()
    assert [task.type for task in solver.tasks] == [TaskTypes.NOT_SPECIFIC]


def test_experimental_backup_keeps_zero_mood_worker_on_shift(solver):
    solver.op_data.global_plan["default_plan"].config.workaholic = ["歌蕾蒂娅"]
    enable_experimental_dorm_logic(solver)
    worker = solver.op_data.operators["歌蕾蒂娅"]
    worker.mood = 0
    worker.time_stamp = datetime(2026, 9, 11, 16, 2, 21)

    assert worker.workaholic
    assert solver.backup_plan_solver() is False
    assert solver.op_data.plan_condition == [True]
    assert all("central" not in task.plan for task in solver.tasks)


def test_experimental_backup_bed_change_still_reorders(solver, monkeypatch):
    enable_experimental_dorm_logic(solver)
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


@pytest.mark.parametrize("append_empty_task", [False, True])
def test_backup_reorder_wakes_planning_even_with_existing_return(
    solver, monkeypatch, append_empty_task
):
    enable_experimental_dorm_logic(solver)
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

    assert solver.backup_plan_solver(
        append_empty_task=append_empty_task, generated_tasks=generated
    )

    assert any(t.type == TaskTypes.SHIFT_ON for t in solver.tasks)
    wakeups = [t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC]
    assert len(wakeups) == int(append_empty_task)
    if append_empty_task:
        assert wakeups[0].time == generated[0].time
        assert wakeups[0] in generated


@pytest.mark.parametrize("experimental", [False, True])
def test_backup_reorder_rebuilds_invalidated_run_order_on_next_planning_pass(
    solver, monkeypatch, experimental
):
    solver.global_plan["default_plan"].plan["room_1_1"] = [
        Room("鸿雪", "", ["但书", "深巡"])
    ]
    if experimental:
        enable_experimental_dorm_logic(solver)
    else:
        assert solver.op_data.swap_plan([False], refresh=True) is None
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
    solver.agent_arrange.side_effect = lambda plan, get_time: plan.clear()
    solver.skip = base.BaseSchedulerSolver.skip.__get__(solver)
    solver.infra_main()
    assert solver.planned  # 重排完成仍按原流程跳过本轮常规规划。

    wakeup = next(t for t in solver.tasks if t.type == TaskTypes.NOT_SPECIFIC)
    # 下一次 run() 重置 planned；消费空任务后进入正常规划，无需等待回班。
    solver.task, solver.planned = wakeup, False
    solver.infra_main()
    solver.agent_get_mood = MagicMock(return_value=None)
    solver.restart_after_mood_read = False
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


def test_plan_swap_dorm_reorder_adds_empty_followup_with_future_mastery(
    solver, monkeypatch
):
    mastery = SchedulerTask(
        time=datetime(2026, 9, 11, 20),
        task_type=TaskTypes.SKILL_UPGRADE,
    )
    solver.tasks = [mastery]
    monkeypatch.setattr(
        base,
        "rebalance_plan_swap_dorms",
        MagicMock(return_value={"dormitory_1": ["Current"] * 5}),
    )

    assert solver.backup_plan_solver() is True

    generated = [task for task in solver.tasks if task is not mastery]
    assert [task.type for task in generated] == [
        TaskTypes.RE_ORDER,
        TaskTypes.NOT_SPECIFIC,
    ]
    assert generated[0].time == generated[1].time == base.datetime.now()


def test_embedded_plan_swap_dorm_reorder_does_not_add_empty_followup(
    solver, monkeypatch
):
    monkeypatch.setattr(
        base,
        "rebalance_plan_swap_dorms",
        MagicMock(return_value={"dormitory_1": ["Current"] * 5}),
    )

    assert solver.backup_plan_solver(append_empty_task=False) is True

    assert [task.type for task in solver.tasks] == [TaskTypes.RE_ORDER]


def test_before_dorm_task_supersedes_same_dorm_and_preserves_other_dorms(solver):
    backup = solver.op_data.backup_plans[0]
    backup.trigger_timing = PlanTriggerTiming.BEFORE_DORM
    backup.task = {
        "dormitory_1": ["隐德来希", "Current", "Current", "Current", "Current"]
    }
    black_key = solver.op_data.operators["黑键"]
    black_key.current_room, black_key.current_index = "contact", 0
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={
            "contact": ["红"],
            "dormitory_1": ["塑心", "冰酿", "黑键", "Free", "Free"],
            "dormitory_2": ["Current"] * 5,
        },
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
    arranged = []

    def arrange_room(new_plan, room, plan, get_time=False):
        arranged.append(room)
        del plan[room]
        if room == "contact":
            black_key.current_room, black_key.current_index = "dormitory_1", 2
        return new_plan

    solver.agent_arrange_room = MagicMock(side_effect=arrange_room)
    solver.agent_arrange = base.BaseSchedulerSolver.agent_arrange.__get__(solver)
    solver.queue_product_switches = MagicMock()

    assert solver.agent_arrange(current.plan, get_time=True) is False
    assert arranged == ["contact"]
    assert current.plan == {"dormitory_2": ["Current"] * 5}
    generated = next(task for task in solver.tasks if task is not current)
    assert generated.plan == backup.task
    assert generated.time == current.time - timedelta(microseconds=1)
    assert solver.op_data.plan_condition == [True]


def test_before_dorm_deactivation_restores_main_plan_before_dorm(solver):
    backup = solver.op_data.backup_plans[0]
    backup.trigger_timing = PlanTriggerTiming.BEFORE_DORM
    backup.plan = {
        "dormitory_1": [
            Room("隐德来希", "", []),
            *[Room("Current", "", []) for _ in range(4)],
        ]
    }
    backup.task = {
        "dormitory_1": [
            "隐德来希",
            "Current",
            "Current",
            "Current",
            "Current",
        ]
    }
    solver.op_data.swap_plan([True], refresh=True)
    black_key = solver.op_data.operators["黑键"]
    black_key.current_room, black_key.current_index = "contact", 0
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={
            "contact": ["红"],
            "dormitory_1": ["隐德来希", "冰酿", "黑键", "Free", "Free"],
        },
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
    arranged = []

    def arrange_room(new_plan, room, plan, get_time=False):
        arranged.append(room)
        del plan[room]
        return new_plan

    solver.agent_arrange_room = MagicMock(side_effect=arrange_room)
    solver.agent_arrange = base.BaseSchedulerSolver.agent_arrange.__get__(solver)
    solver.queue_product_switches = MagicMock()

    assert solver.agent_arrange(current.plan, get_time=True) is False
    assert arranged == ["contact"]
    assert current.plan == {}
    generated = next(task for task in solver.tasks if task is not current)
    assert generated.plan == {
        "dormitory_1": [
            "塑心",
            "Current",
            "Current",
            "Current",
            "Current",
        ]
    }
    assert generated.time == current.time - timedelta(microseconds=1)
    assert solver.op_data.plan_condition == [False]


def test_infra_main_keeps_deferred_dorm_task(solver):
    current = SchedulerTask(
        task_plan={"dormitory_1": ["塑心", "冰酿", "黑键", "Free", "Free"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
    solver.agent_arrange.return_value = False
    solver.plan_metadata = MagicMock()

    solver.infra_main()

    assert current in solver.tasks
    assert current.plan
    solver.plan_metadata.assert_not_called()
    solver.skip.assert_called()


def test_infra_main_removes_fully_superseded_dorm_task(solver):
    current = SchedulerTask(
        task_plan={"dormitory_1": ["塑心", "冰酿", "黑键", "Free", "Free"]},
        task_type=TaskTypes.SHIFT_OFF,
    )
    generated = SchedulerTask(
        task_plan={
            "dormitory_1": ["隐德来希", "Current", "Current", "Current", "Current"]
        }
    )
    solver.task = current
    solver.tasks = [generated, current]

    def supersede_current(plan, get_time):
        plan.clear()
        return False

    solver.agent_arrange.side_effect = supersede_current
    solver.plan_metadata = MagicMock()

    solver.infra_main()

    assert current not in solver.tasks
    assert generated in solver.tasks
    solver.plan_metadata.assert_not_called()
    solver.skip.assert_called()


def test_before_dorm_timing_order_and_parser():
    assert Plan.set_timing_enum("before_work") is PlanTriggerTiming.BEFORE_WORK
    assert Plan.set_timing_enum("before_dorm") is PlanTriggerTiming.BEFORE_DORM
    assert (
        PlanTriggerTiming.BEGINNING.value
        < PlanTriggerTiming.BEFORE_WORK.value
        < PlanTriggerTiming.BEFORE_DORM.value
        < PlanTriggerTiming.BEFORE_PLANNING.value
    )


def test_exit_timing_defaults_to_entry_timing_and_can_be_independent():
    inherited = Plan({}, PlanConfig("", "", ""), trigger_timing="BEFORE_DORM")
    independent = Plan(
        {},
        PlanConfig("", "", ""),
        trigger_timing="BEFORE_DORM",
        exit_trigger_timing="BEFORE_WORK",
    )

    assert inherited.exit_trigger_timing is PlanTriggerTiming.BEFORE_DORM
    assert independent.trigger_timing is PlanTriggerTiming.BEFORE_DORM
    assert independent.exit_trigger_timing is PlanTriggerTiming.BEFORE_WORK


def test_backup_uses_independent_exit_timing(solver):
    backup = solver.op_data.backup_plans[0]
    backup.trigger_timing = PlanTriggerTiming.BEFORE_DORM
    backup.exit_trigger_timing = PlanTriggerTiming.BEFORE_WORK
    solver.op_data.plan_condition = [True]
    solver.op_data.operators["黑键"].is_resting = MagicMock(return_value=False)

    solver.backup_plan_solver(PlanTriggerTiming.BEGINNING)
    assert solver.op_data.plan_condition == [True]

    solver.backup_plan_solver(PlanTriggerTiming.BEFORE_WORK)
    assert solver.op_data.plan_condition == [False]


def test_before_work_exit_defers_current_room_before_entering_it(solver):
    backup = solver.op_data.backup_plans[0]
    backup.trigger_timing = PlanTriggerTiming.BEFORE_DORM
    backup.exit_trigger_timing = PlanTriggerTiming.BEFORE_WORK
    backup.task = {"contact": ["红"]}
    solver.op_data.plan_condition = [True]
    solver.op_data.operators["黑键"].is_resting = MagicMock(return_value=False)
    current = SchedulerTask(
        time=datetime(2026, 9, 11, 16),
        task_plan={
            "contact": ["红"],
            "dormitory_1": ["塑心", "冰酿", "黑键", "Free", "Free"],
        },
        task_type=TaskTypes.SHIFT_OFF,
    )
    solver.task = current
    solver.tasks = [current]
    solver.agent_arrange_room = MagicMock()
    solver.agent_arrange = base.BaseSchedulerSolver.agent_arrange.__get__(solver)
    solver.queue_product_switches = MagicMock()

    assert solver.agent_arrange(current.plan, get_time=True) is False

    solver.agent_arrange_room.assert_not_called()
    assert current.plan == {"dormitory_1": ["塑心", "冰酿", "黑键", "Free", "Free"]}
    generated = next(task for task in solver.tasks if task is not current)
    assert generated.plan == {"contact": ["黑键"]}
    assert generated.time == current.time - timedelta(microseconds=1)


def test_switch_preserves_shift_on_target_when_backup_modifies_room_plan(solver):
    solver.plan_metadata()
    old_task = return_task(solver)
    assert old_task.plan["contact"][0] == "黑键"
    assert old_task.time == datetime(2026, 9, 11, 16, 24, 21)

    # 模拟副表调整了工位（黑键与陈换位），并将歌蕾蒂娅设为用尽
    backup = solver.op_data.backup_plans[0]
    backup.plan = {
        "contact": [Room("陈", "", [])],
        "central": [Room("黑键", "感知", ["陈"])],
    }
    backup.config.exhaust_require = ["歌蕾蒂娅"]

    solver.backup_plan_solver()

    # 副表已生效且修改了 contact 和 central 的计划
    assert solver.op_data.plan["contact"][0].agent == "陈"
    assert solver.op_data.plan["central"][0].agent == "黑键"
    new_task = return_task(solver)
    # 回班任务的时间按副表配置消除急救推迟到 17:05
    assert new_task.time == datetime(2026, 9, 11, 17, 5, 3)
    # 回班工位依然保留下班时的快照（contact 的黑键），没有被副表改写为 central
    assert new_task.plan["contact"][0] == "黑键"
    assert "central" not in new_task.plan


def test_deactivation_restores_main_plan_targets_preventing_stickiness(solver):
    solver.plan_metadata()
    # 模拟副表生效
    backup = solver.op_data.backup_plans[0]
    backup.plan = {
        "contact": [Room("陈", "", [])],
        "central": [Room("黑键", "感知", ["陈"])],
    }
    backup.config.exhaust_require = ["歌蕾蒂娅"]
    solver.backup_plan_solver()
    assert solver.op_data.plan_condition == [True]

    # 模拟副表期间存在的某任务记录了副表工位 central
    task = return_task(solver)
    task.plan = {"central": ["黑键"]}

    # 条件变更，黑键离开宿舍，副表条件失效
    solver.op_data.operators["黑键"].is_resting = MagicMock(return_value=False)
    solver.backup_plan_solver()

    # 副表失效，恢复主表
    assert solver.op_data.plan_condition == [False]
    new_task = return_task(solver)
    # 不会发生工位粘滞，黑键回班工位正确恢复为主表工位 contact，而不是副表 central
    assert new_task.plan["contact"][0] == "黑键"
    assert "central" not in new_task.plan


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
