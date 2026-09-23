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


def test_unrelated_experimental_backup_switch_skips_dorm_reorder(solver, monkeypatch):
    enable_experimental_dorm_logic(solver)
    reorder = MagicMock(return_value={"dormitory_1": ["Current"] * 5})
    monkeypatch.setattr(base, "rebalance_plan_swap_dorms", reorder)

    assert solver.backup_plan_solver() is False

    reorder.assert_not_called()
    assert [task.type for task in solver.tasks] == [TaskTypes.NOT_SPECIFIC]


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
