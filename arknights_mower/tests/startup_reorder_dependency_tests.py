"""启动观测生成的宿舍迁移不能挡住其所需的初始化回班。"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import record
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import TaskTypes

pytestmark = pytest.mark.usefixtures("offline_maintenance")


def test_observed_startup_migration_keeps_its_cover_and_completes_return(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 1, 8, 12)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(record, "save_agent_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    config.conf.enable_mastery = False
    config.conf.test_mood_calculation = False
    config.conf.group_rest_in_full_on_mood_gap = False
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room("芬", "甲", ["克洛丝"])],
                "contact": [Room("翎羽", "甲", ["香草"])],
                "meeting": [
                    Room(
                        "香草",
                        "丙",
                        ["安德切尔"],
                        group_bindings=[
                            {"group": "甲", "replacement": ["安德切尔"]},
                            {"group": "丁", "replacement": ["安德切尔"]},
                        ],
                    )
                ],
                "room_1_1": [Room("玫兰莎", "丙", ["米格鲁"])],
                "room_1_2": [Room("梓兰", "丁", ["黑角"])],
                "dormitory_1": [
                    Room(
                        "杜林",
                        "丙",
                        ["香草"],
                        group_bindings=[
                            {"group": "甲", "replacement": ["香草", "巡林者"]}
                        ],
                    ),
                    Room("闪灵", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
                "dormitory_2": [
                    Room("流明", "", []),
                    Room("冰酿", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            PlanConfig("", "", "", free_room=True),
        ),
        "backup_plans": [
            Plan(
                {},
                PlanConfig("", "", "", free_room=True, ope_resting_priority="空爆"),
                trigger=LogicExpression("True", "==", "True"),
            )
        ],
    }
    assert solver.initialize_operators() is None
    solver.tasks, solver.waiting_group_shifts, solver.task = [], [], None
    solver._initial_staffing_pending = True
    solver.op_data.first_init = False
    solver.last_train_mood_read = Clock.now()
    solver.enter_room = Mock(side_effect=AssertionError("不应触发设备读房"))
    observed = {
        # 第二个中枢位置未托管，但在岗的巡林者仍不能被取作宿管替班。
        "central": [("克洛丝", 12), ("巡林者", 12)],
        "contact": [],
        "meeting": [("安德切尔", 12)],
        "room_1_1": [("玫兰莎", 24)],
        "room_1_2": [("梓兰", 24)],
        "dormitory_1": [
            ("香草", 12),
            ("闪灵", 24),
            ("芬", 23),
            ("空爆", 10),
            ("芙蓉", 10),
        ],
        "dormitory_2": [
            ("流明", 24),
            ("冰酿", 24),
            ("泡泡", 10),
            ("黑角", 10),
            ("泡普卡", 10),
        ],
    }
    for room, row in observed.items():
        for index, (name, mood) in enumerate(row):
            if name not in solver.op_data.operators:
                solver.op_data.add(Operator(name, ""))
            solver.op_data.update_detail(name, mood, room, index, update_time=True)
        solver._reconcile_room_observation(room, [{"agent": name} for name, _ in row])
    solver.op_data.update_detail("米格鲁", 24, "", -1, update_time=True)
    assert not solver.op_data.group_shift_state
    assert not solver.op_data.is_group_shift_anchor(solver.op_data.operators["香草"])
    assert solver.op_data.get_dorm_by_name("香草")[1].position == ("dormitory_1", 0)
    original_positions = {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    }

    assert solver.backup_plan_solver()
    migration = next(task for task in solver.tasks if task.type == TaskTypes.RE_ORDER)
    assert migration.plan.get("dormitory_1", ["Current"] * 5)[0] == "Current"
    assert not any("香草" in row for row in migration.plan.values())
    assert solver.op_data.get_current_operator("dormitory_1", 0).name == "香草"
    assert solver.agent_get_mood(force=True, read_rooms=False) == "self_correction"
    correction = next(
        task for task in solver.tasks if task.type == TaskTypes.SELF_CORRECTION
    )
    assert correction.initial_staffing
    assert correction.plan["central"] == ["芬"]
    assert correction.plan["contact"] == ["翎羽"]
    migration_time = migration.time
    solver.task = migration
    solver._prepare_group_shift(migration)
    solver._prepare_shift_cycle(migration)
    assert {
        name: (op.current_room, op.current_index)
        for name, op in solver.op_data.operators.items()
    } == original_positions
    assert not solver.waiting_group_shifts
    assert migration.time == migration_time

    solver._activate_shift_backup(migration)
    solver._prepare_group_shift(migration, remember_targets=True)
    projected = solver.op_data.project_arrangements([migration.plan])
    for room in migration.plan:
        names = projected.get_current_room(room, True)
        for index, name in enumerate(names):
            if name:
                solver.op_data.update_detail(
                    name,
                    solver.op_data.operators[name].mood,
                    room,
                    index,
                    update_time=True,
                )
        solver._reconcile_room_observation(room, [{"agent": name} for name in names])
    assert solver.op_data.get_current_operator("central", 0).name == "芬"
    assert solver.op_data.get_current_operator("contact", 0).name == "翎羽"
    solver.tasks.remove(migration)
    assert solver._complete_group_shift(migration)
    assert not solver.waiting_group_shifts
    assert all(task is not migration for task in solver.tasks)
    assert migration.time == migration_time
    solver.enter_room.assert_not_called()
