"""生效宿舍顺序改变时重分已有单回住客，其他切表保留原位。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch, offline_maintenance):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("芬", "", ["克洛丝"])],
                    "meeting": [Room("香草", "", ["空爆"])],
                    "dormitory_1": [
                        Room(n, "", [])
                        for n in ["杜林", "闪灵", "Free", "Free", "Free"]
                    ],
                    "dormitory_2": [
                        Room(n, "", [])
                        for n in ["流明", "蜜莓", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", "", dorm_order="dormitory_1,dormitory_2"),
            ),
            "backup_plans": [
                Plan(
                    {},
                    PlanConfig("", "", "", dorm_order="dormitory_2,dormitory_1"),
                    trigger=LogicExpression("True", "==", "True"),
                ),
            ],
        }
    )
    assert instance.op_data.init_and_validate() is None
    now = datetime.now()
    for op in instance.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, now
    for name, cover, work, dorm, mood in [
        ("芬", "克洛丝", "central", "dormitory_1", 5),
        ("香草", "空爆", "meeting", "dormitory_2", 12),
    ]:
        op = instance.op_data.operators[name]
        op._current_room, op.current_index, op.mood = dorm, 2, mood
        op.dorm_recovery_room, op.dorm_recovery_index = dorm, 2
        substitute = instance.op_data.operators[cover]
        substitute._current_room, substitute.current_index = work, 0
        bed = next(b for b in instance.op_data.dorm if b.position == (dorm, 2))
        bed.name, bed.time = name, now + timedelta(hours=2)
    instance.tasks, instance.task = [], None
    instance.queue_product_switches = MagicMock()
    return instance


@pytest.mark.parametrize("same_order", [False, True])
@pytest.mark.parametrize("reserved", [False, True])
@pytest.mark.parametrize("leaving", [False, True])
def test_backup_dorm_order_reallocates_existing_single_targets(
    solver, same_order, reserved, leaving
):
    data = solver.op_data
    config.conf.dorm_isolation = [["芬", "香草"]]
    if same_order:
        data.backup_plans[0].config.dorm_order = data.config.dorm_order.copy()
    original_room = "dormitory_1"
    if leaving:
        assert data.swap_plan([True], refresh=True) is None
        data.backup_plans[0].trigger = LogicExpression("False", "==", "True")
        if not same_order:
            original_room = "dormitory_2"
            for bed in data.dorm:
                if bed.name in ("芬", "香草"):
                    bed.name = "香草" if bed.name == "芬" else "芬"
                    op = data.operators[bed.name]
                    op._current_room = op.dorm_recovery_room = bed.position[0]
    if reserved:
        solver.tasks.append(
            SchedulerTask(
                time=datetime.now() + timedelta(hours=1),
                task_type=TaskTypes.RE_ORDER,
                task_plan={
                    original_room: ["Current", "Current", "芬", "Current", "Current"]
                },
            )
        )
    solver.backup_plan_solver()
    generated = [task.plan for task in solver.tasks if task.type != TaskTypes.SHIFT_ON]
    final = solver.op_data.project_arrangements(generated)
    expected = (
        original_room
        if same_order or reserved
        else ("dormitory_1" if leaving else "dormitory_2")
    )
    assert final.operators["芬"].current_room == expected
    assert final.operators["香草"].current_room != expected
    assert final.get_current_operator("dormitory_1", 0).name == "杜林"
    assert final.get_current_operator("dormitory_2", 0).name == "流明"
    assert data.operators["芬"].current_room == original_room
    assert data.operators["芬"].dorm_recovery_room == original_room


@pytest.mark.parametrize("path", ["cached", "shift", "product"])
def test_changed_dorm_order_keeps_isolated_residents_apart(solver, path):
    config.conf.dorm_isolation = [["芬", "香草"]]
    solver.op_data.backup_plans[0].config.dorm_order = [
        "dormitory_2",
        "dormitory_2_low",
        "dormitory_1",
        "dormitory_3",
        "dormitory_4",
    ]
    before = [(bed.name, bed.time) for bed in solver.op_data.dorm]
    if path == "cached":
        solver.backup_plan_solver()
    else:
        task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
        task.product_shift_locked = path == "product"
        solver.tasks = [task]
        solver.task = task
        solver._prepare_shift_cycle(task)
        arranged = copy.deepcopy(task.plan)
        solver._prepare_shift_cycle(task)
        assert task.plan == arranged
        assert solver.op_data.plan_condition == [False]
        assert [(bed.name, bed.time) for bed in solver.op_data.dorm] == before
    final = solver.op_data.project_arrangements([task.plan for task in solver.tasks])
    assert final.operators["芬"].current_room == "dormitory_2"
    assert final.operators["香草"].current_room == "dormitory_1"
    assert final.operators["香草"].current_index == 2
