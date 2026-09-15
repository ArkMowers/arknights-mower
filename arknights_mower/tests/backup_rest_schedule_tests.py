"""副表切换后，回班任务必须使用新排班的耗尽配置和岗位。"""

import sys
from datetime import datetime
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
