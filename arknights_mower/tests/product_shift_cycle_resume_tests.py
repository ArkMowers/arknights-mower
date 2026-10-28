"""切产物等待恢复时保留完整换班及共享替班安排。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import shift_backup_convergence_tests as backup
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = backup.solver


@pytest.fixture
def product_waiting_cycle(solver, monkeypatch):
    monkeypatch.setattr(config.conf.product_switching, "enable", True)
    plans = copy.deepcopy(solver.op_data.global_plan)
    for plan, product in (
        (plans["default_plan"], "gold"),
        (plans["backup_plans"][0], "exp3"),
    ):
        plan.products = {"room_2_2": product}
        for slot in plan.plan["room_2_2"]:
            slot.facility = "制造站"
            slot.product = product
    solver.op_data = Operators(plans)
    assert solver.op_data.init_and_validate() is None
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, datetime.now()
    solver.op_data.first_init = False
    task = backup.resting(solver)
    for name in solver.op_data.groups["红松"]:
        solver.op_data.operators[name].mood = 24
    for name in solver.op_data.groups["深海"]:
        solver.op_data.operators[name].mood = 1
    solver.op_data.update_facility_state("room_2_2", "manufacture", "exp3")
    solver.plan_metadata = MagicMock()
    solver.agent_arrange = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    return solver, task


@pytest.mark.parametrize("serialized", [False, True])
def test_product_wait_resume_preserves_complete_rotation(
    product_waiting_cycle, serialized
):
    import jsonpickle

    solver, task = product_waiting_cycle
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    original = copy.deepcopy(task.plan)
    transitions = dict(task.group_shift_transitions)
    assert transitions == {"红松": False, "深海": True}
    assert task.backup_shift_intent != original
    original_time = task.time
    positions = backup.positions(solver.op_data)
    deadline = task.time + timedelta(minutes=2)
    solver.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred("等待制造完成", ready_at=deadline)
    )
    with pytest.raises(base.ProductSwitchDeferred):
        solver._switch_products_before_arrangement(task)
    assert task.product_shift_locked
    assert task.plan == original and task.time == original_time
    if serialized:
        task = jsonpickle.decode(jsonpickle.encode(task))
        solver.task, solver.tasks = task, [task]
    for _ in range(3):
        solver._prepare_group_shift(task)
        solver._prepare_shift_cycle(task)
        assert task.plan == original
        assert task.group_shift_transitions == transitions
        assert task.time == original_time
        assert solver.tasks == [task]
        assert backup.positions(solver.op_data) == positions
    solver.switch_base_products.side_effect = lambda tasks, **kwargs: (
        solver.op_data.update_facility_state("room_2_2", "manufacture", "gold")
    )
    solver._switch_products_before_arrangement(task)
    solver._activate_shift_backup(task)
    solver._prepare_group_shift(task, remember_targets=True)
    final = solver.op_data.project_arrangements([task.plan])
    assert all(final.operators[name].is_working() for name in final.groups["红松"])
    assert all(final.operators[name].is_resting() for name in final.groups["深海"])
    assert task.group_shift_transitions == transitions
    assert task.time == original_time


@pytest.mark.parametrize("failed_arrangement", [False, True])
def test_dispatch_resumes_product_wait_with_merged_departure(
    product_waiting_cycle, failed_arrangement
):
    solver, task = product_waiting_cycle
    task.time = datetime.now() - timedelta(minutes=3)
    ready_at = datetime.now() - timedelta(seconds=1)
    original_positions = backup.positions(solver.op_data)
    solver.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred("等待制造完成", ready_at=ready_at)
    )
    solver.infra_main()
    assert task in solver.tasks and task.product_shift_locked
    assert task.time == ready_at
    assert task.group_shift_transitions == {"红松": False, "深海": True}
    original_plan = copy.deepcopy(task.plan)
    assert backup.positions(solver.op_data) == original_positions
    solver.agent_arrange.assert_not_called()

    def arrange(plan, *args, **kwargs):
        if failed_arrangement:
            raise base.RecognizeError("驻员读取未确认")
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    solver.agent_arrange.side_effect = arrange
    solver.switch_base_products.side_effect = lambda tasks, **kwargs: (
        solver.op_data.update_facility_state("room_2_2", "manufacture", "gold")
    )
    solver.task = task
    solver.infra_main()
    assert task.time == ready_at
    if failed_arrangement:
        assert task in solver.tasks and task.execution_failure
        assert task.plan == original_plan
        assert backup.positions(solver.op_data) == original_positions
        assert solver.op_data.group_is_resting("红松")
        assert not solver.op_data.group_is_resting("深海")
    else:
        assert task not in solver.tasks
        assert not solver.op_data.group_is_resting("红松")
        assert solver.op_data.group_is_resting("深海")
        assert all(
            solver.op_data.operators[n].is_resting()
            for n in solver.op_data.groups["深海"]
        )


def test_product_wait_preserves_rotation_until_dependency_releases(
    product_waiting_cycle,
):
    solver, task = product_waiting_cycle
    task.time = datetime.now() - timedelta(minutes=3)
    predecessor = SchedulerTask(task_type=TaskTypes.RE_ORDER)
    predecessor.time = task.time
    solver.tasks.append(predecessor)
    solver.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "等待生产前置操作", dependencies=(predecessor,)
        )
    )
    original_time = task.time
    solver.infra_main()
    assert task.product_shift_locked and task.execution_failure
    assert task.product_shift_predecessors == (predecessor,)
    original_plan = copy.deepcopy(task.plan)
    assert task.group_shift_transitions == {"红松": False, "深海": True}
    for _ in range(3):
        solver._resume_failed_tasks()
        assert task.execution_failure and task.plan == original_plan
        assert task.time == original_time
    solver.tasks.remove(predecessor)
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert task.plan == original_plan and task.time == original_time
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    assert task.plan == original_plan
    assert task.group_shift_transitions == {"红松": False, "深海": True}


def test_shared_cover_survives_complete_rotation_product_wait(solver, monkeypatch):
    monkeypatch.setattr(config.conf.product_switching, "enable", True)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [
                        Room("森蚺", "自动化", ["夕"]),
                        Room("令", "感知", ["年"]),
                    ],
                    "meeting": [
                        Room("信仰搅拌机", "", ["塞雷娅"]),
                        Room(
                            "跃跃",
                            "感知",
                            ["黍"],
                            group_bindings=[
                                {"group": "自动化", "replacement": ["虎狼丸"]}
                            ],
                        ),
                    ],
                    "room_1_2": [Room("Lancet-2", "", [], "制造站", "gold")],
                    "dormitory_1": [
                        Room("冰酿", "", []),
                        Room("闪灵", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", "", workaholic="Lancet-2"),
                products={"room_1_2": "gold"},
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", ""),
                    trigger=backup.LogicExpression(
                        "op_data.operators['令'].is_working()", "==", "False"
                    ),
                    products={"room_1_2": "exp3"},
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    assert data.swap_plan([True], refresh=True) is None
    for op in data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 24, datetime.now()
    solver.op_data = data.project_arrangements(
        [
            {
                "central": ["森蚺", "年"],
                "meeting": ["信仰搅拌机", "黍"],
                "dormitory_1": ["冰酿", "闪灵", "令", "虎狼丸", "Free"],
            }
        ]
    )
    solver.op_data.first_init = False
    solver.op_data.commit_group_shifts({"感知": True, "自动化": False})
    solver.op_data.operators["森蚺"].mood = 1
    solver.op_data.operators["虎狼丸"].mood = 14
    solver.op_data.update_facility_state("room_1_2", "manufacture", "exp3")
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"central": ["Current", "令"]}
    )
    solver.tasks, solver.task = [task], task
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    expected_plan = copy.deepcopy(task.plan)
    expected_time = task.time
    assert task.group_shift_transitions == {"自动化": True, "感知": False}
    assert task.plan["meeting"][1] == "虎狼丸"
    assert "森蚺" in task.plan["dormitory_1"]
    solver.switch_base_products = MagicMock(
        side_effect=base.ProductSwitchDeferred(
            "等待制造完成", ready_at=task.time + timedelta(minutes=2)
        )
    )
    with pytest.raises(base.ProductSwitchDeferred):
        solver._switch_products_before_arrangement(task)
    assert task.product_shift_locked
    solver._prepare_group_shift(task)
    solver._prepare_shift_cycle(task)
    assert task.plan == expected_plan
    assert task.time == expected_time
    solver._prepare_group_shift(task, remember_targets=True)
    assert task.plan["meeting"][1] == "虎狼丸"
    assert all(
        "虎狼丸" not in row
        for room, row in task.plan.items()
        if room.startswith("dorm")
    )
