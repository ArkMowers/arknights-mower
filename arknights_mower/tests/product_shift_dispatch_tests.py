"""到期换班先收敛产物目标，避免执行即将失效的独立切换。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def pending_return(monkeypatch, offline_maintenance):
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("陈", "", ["红"])],
                    "room_1_2": [Room("Lancet-2", "", [], "制造站", "gold")],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", "", workaholic="Lancet-2", free_room=True),
                products={"room_1_2": "gold"},
            ),
            "backup_plans": [
                Plan(
                    {"room_1_2": [Room("Current", "", [], "制造站", "exp3")]},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression(
                        "op_data.operators['陈'].is_working()", "==", "False"
                    ),
                    products={"room_1_2": "exp3"},
                )
            ],
        }
    )
    assert solver.op_data.init_and_validate() is None
    assert solver.op_data.swap_plan([True], refresh=True) is None
    now = datetime.now()
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 24, now
    solver.op_data = solver.op_data.project_arrangements(
        [{"central": ["红"], "dormitory_1": ["Current", "Current", "陈"]}]
    )
    solver.op_data.first_init = False
    for bed in solver.op_data.dorm:
        if bed.name == "陈":
            bed.time = now - timedelta(seconds=1)
    solver.op_data.update_facility_state("room_1_2", "manufacture", "gold")
    solver.tasks, solver.task = [], None
    solver._sync_run_order_tasks = MagicMock()
    solver.last_train_mood_read = now
    solver.find = MagicMock(return_value=(1, 1))
    solver.skip = MagicMock()
    solver.refresh_connecting = False
    solver.queue_product_switches()
    product = solver.tasks[0]
    product.time = now - timedelta(minutes=5)
    returning = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON,
        task_plan={"central": ["陈"]},
        time=now - timedelta(minutes=2),
    )
    solver.tasks.append(returning)
    solver.task = product
    changes = []

    def switch(tasks, **kwargs):
        for task in tasks:
            room, target = task.meta_data.split(",")
            changes.append(("product", room, target))
            solver.op_data.update_facility_state(room, "manufacture", target)
            solver.tasks[:] = [
                pending for pending in solver.tasks if pending is not task
            ]

    def arrange(plan, *args, **kwargs):
        changes.append(("arrange", plan.copy()))
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    solver.switch_base_products = switch
    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.plan_metadata = MagicMock()
    return solver, product, returning, changes


@pytest.mark.parametrize("actual", ["gold", "exp3"])
def test_due_return_uses_final_product_without_round_trip(pending_return, actual):
    solver, product, returning, changes = pending_return
    solver.op_data.update_facility_state("room_1_2", "manufacture", actual)
    times = product.time, returning.time
    solver.infra_main()
    assert [item for item in changes if item[0] == "product"] == (
        [] if actual == "gold" else [("product", "room_1_2", "gold")]
    )
    assert changes[-1][0] == "arrange"
    assert solver.op_data.operators["陈"].is_working()
    assert solver.op_data.products["room_1_2"] == "gold"
    assert product not in solver.tasks
    assert (product.time, returning.time) == times
    solver.queue_product_switches()
    assert not any(task.type == TaskTypes.SWITCH_PRODUCT for task in solver.tasks)


def test_future_return_does_not_cancel_current_product(pending_return):
    solver, product, returning, changes = pending_return
    returning.time = datetime.now() + timedelta(hours=1)
    solver.infra_main()
    assert changes == [("product", "room_1_2", "exp3")]
    assert returning in solver.tasks
    assert solver.op_data.operators["陈"].is_resting()


def test_completed_product_keeps_failed_staffing_for_recovery(pending_return):
    solver, product, returning, changes = pending_return
    solver.op_data.update_facility_state("room_1_2", "manufacture", "exp3")
    original_time = returning.time
    solver.agent_arrange.side_effect = base.RecognizeError("换人结果未确认")
    solver.infra_main()
    assert changes == [("product", "room_1_2", "gold")]
    assert returning in solver.tasks
    assert returning.time == original_time
    assert returning.execution_failure
    assert returning.backup_shift_active
    assert returning.plan["central"] == ["陈"]
    assert solver.op_data.operators["陈"].is_resting()
    solver.queue_product_switches()
    assert not any(task.type == TaskTypes.SWITCH_PRODUCT for task in solver.tasks)
    assert solver.backup_plan_solver() is False
    assert solver.op_data.products["room_1_2"] == "gold"
    solver._resume_failed_tasks()
    assert returning.execution_failure
    assert returning.time == original_time


def test_urgent_order_still_precedes_product_and_return(pending_return):
    solver, product, returning, changes = pending_return
    order = SchedulerTask(
        time=datetime.now() - timedelta(minutes=10),
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_1_1",
    )
    solver.tasks.insert(0, order)
    solver.infra_main()
    assert changes == []
    assert product in solver.tasks
    assert returning in solver.tasks


def test_unconverged_staffing_retains_product_until_new_observation(pending_return):
    solver, product, returning, changes = pending_return
    original_times = product.time, returning.time
    solver._retain_failed_task(returning, "副表预演尚未收敛", list(returning.plan))
    solver.infra_main()
    assert changes == []
    assert product in solver.tasks and returning in solver.tasks
    assert product.execution_failure and returning.execution_failure
    for _ in range(5):
        solver._resume_failed_tasks()
        assert product.execution_failure and returning.execution_failure
    assert (product.time, returning.time) == original_times
    solver.op_data.operators["红"].time_stamp = datetime.now()
    solver._resume_failed_tasks()
    assert not getattr(product, "execution_failure", None)
    assert not getattr(returning, "execution_failure", None)
    solver.task = product
    solver.infra_main()
    assert not [item for item in changes if item[0] == "product"]
    assert solver.op_data.operators["陈"].is_working()


@pytest.mark.parametrize("failed", [False, True])
def test_unrelated_staffing_does_not_block_product_switch(pending_return, failed):
    solver, product, returning, changes = pending_return
    solver.op_data.backup_plans = []
    solver.op_data.plan_condition = []
    original_time = returning.time
    if failed:
        solver._retain_failed_task(returning, "恢复观测尚未完成", list(returning.plan))
    for _ in range(3):
        solver._resume_failed_tasks()
    solver.infra_main()
    assert changes == [("product", "room_1_2", "exp3")]
    assert product not in solver.tasks
    assert returning in solver.tasks and returning.time == original_time
    assert solver.op_data.operators["陈"].is_resting()
    assert bool(getattr(returning, "execution_failure", None)) is failed
