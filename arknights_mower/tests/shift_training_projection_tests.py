"""换班预演保留受专精保护的训练室驻员，避免误入宿舍候选。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import mastery_reader
from arknights_mower.tests import shift_backup_convergence_tests as backup
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = backup.solver


@pytest.fixture
def training_solver(solver, monkeypatch):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(config.conf, "assistant_follows_schedule", False)
    monkeypatch.setattr(base, "_training_room_scan_disabled", False)
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    monkeypatch.setattr(mastery_db, "is_operator_busy", lambda name: False)
    solver._notify_train_correction_skipped = MagicMock()
    for index, name in enumerate(("艾丽妮", "克莱门莎")):
        solver.op_data.add(
            Operator(
                name,
                "",
                current_room="train",
                current_index=index,
                mood=17,
                time_stamp=datetime.now(),
            )
        )
    for name in ("望", "余"):
        solver.op_data.add(Operator(name, "", time_stamp=datetime.now()))
    return solver


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize(
    "follow,enabled", [(False, True), (True, True), (False, False)]
)
def test_backup_training_actions_match_protection_before_dorm_filling(
    training_solver, monkeypatch, configured, follow, enabled
):
    s = training_solver
    config.conf.assistant_follows_schedule = follow
    config.conf.enable_mastery = enabled
    monkeypatch.setattr(
        mastery_db, "get_active_plan", lambda: {"id": 1, "char_name": "克莱门莎"}
    )
    room_state = mastery_reader.RoomState("training")
    s.train_room_state = room_state
    if configured:
        # 训练室未配入排班时也必须保留实际驻员。
        for plan in (s.op_data.plan, s.op_data.global_plan["default_plan"].plan):
            plan["train"] = [Room("望", "", ["褐果"]), Room("余", "", ["真言"])]
    s.op_data.backup_plans[0].plan = {}
    s.op_data.backup_plans[0].task = {"train": ["望", "余"]}
    s.op_data.backup_plans[0].trigger = LogicExpression("True", "==", "True")
    for op in s.op_data.operators.values():
        if op.current_room != "train":
            op.mood = 24
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    s.task, s.tasks = task, [task]
    before = backup.positions(s.op_data)

    s._prepare_shift_cycle(task)

    assert backup.positions(s.op_data) == before
    assert s.train_room_state is room_state
    final = s.op_data.project_arrangements([task.plan])
    assert "dormitory_1" in task.plan
    if enabled:
        assert final.get_train_support() == "艾丽妮"
        assert final.operators["克莱门莎"].current_room == "train"
        assert "艾丽妮" not in task.plan.get("dormitory_1", [])
        assert "train" not in task.plan
    else:
        assert "艾丽妮" in task.plan["dormitory_1"]
        if configured:
            assert final.get_train_support() == "望"
            if enabled:
                assert final.operators["克莱门莎"].current_room == "train"
            else:
                assert final.operators["克莱门莎"].current_room != "train"
    s._notify_train_correction_skipped.assert_not_called()


@pytest.mark.parametrize("source", ["protected", "database", "queue", "observed"])
@pytest.mark.parametrize("follow", [False, True])
def test_initial_intent_is_filtered_before_backup_condition_evaluation(
    training_solver, monkeypatch, source, follow
):
    s = training_solver
    config.conf.assistant_follows_schedule = follow
    if source != "protected":
        s.op_data.operators["艾丽妮"].name = "褐果"
        s.op_data.operators["褐果"] = s.op_data.operators.pop("艾丽妮")
    if source == "database":
        monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"id": 1})
    elif source == "queue":
        s.tasks.append(SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE))
    elif source == "observed":
        s.train_room_state = mastery_reader.RoomState("training")
    s.op_data.backup_plans[0].trigger = LogicExpression(
        "op_data.operators['克莱门莎'].current_room", "==", "'train'"
    )
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    s.tasks.append(task)
    before = backup.positions(s.op_data)
    room_state = getattr(s, "train_room_state", None)

    s._prepare_shift_backup(task)

    assert task.backup_shift_conditions == [True]
    assert backup.positions(s.op_data) == before
    assert getattr(s, "train_room_state", None) is room_state
    assert "train" not in task.plan
    s._notify_train_correction_skipped.assert_not_called()


def test_cycle_without_backup_filters_training_intent(training_solver):
    s = training_solver
    s.op_data.backup_plans = []
    s.op_data.plan_condition = []
    for op in s.op_data.operators.values():
        if op.current_room != "train":
            op.mood = 24
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF, task_plan={"train": ["望", "余"]}
    )
    before = backup.positions(s.op_data)

    s._prepare_shift_cycle(task)

    assert backup.positions(s.op_data) == before
    assert "艾丽妮" not in task.plan.get("dormitory_1", [])
    assert "train" not in task.plan
    s._notify_train_correction_skipped.assert_not_called()
