"""排班校验覆盖与副表演算相同的合并配置错误，且不修改实际驻员。"""

import copy
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config, operators, schedule_roster
from arknights_mower.utils.config.plan import parse_plan_document
from arknights_mower.utils.config.plan_advanced import apply_advanced_settings
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators, build_global_plan
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

FIXTURE = Path(__file__).with_name("fixtures") / "backup_validation_plan_20261002.json"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(schedule_roster, "validate_owned_operators", lambda _: None)
    monkeypatch.setattr(operators.logger, "debug", lambda *args, **kwargs: None)


@pytest.fixture
def image_plan(monkeypatch):
    document = parse_plan_document(json.loads(FIXTURE.read_text(encoding="utf-8")))
    monkeypatch.setattr(config, "plan", document)
    monkeypatch.setattr(
        config, "conf", apply_advanced_settings(config.conf, document.advanced_settings)
    )
    return build_global_plan()


def initialize(plan):
    data = Operators(plan)
    assert data.init_and_validate() is None
    return data


def two_backups():
    conf = PlanConfig("", "", "")
    return {
        "default_plan": Plan(
            {"central": [Room("能天使", "", ["芬"]), Room("银灰", "", ["初雪"])]},
            conf,
        ),
        "backup_plans": [
            Plan({"central": [Room("八幡海铃", "", ["红"])]}, conf, name="主力变更"),
            Plan(
                {
                    "central": [
                        Room("Current", "", []),
                        Room("银灰", "", ["八幡海铃"]),
                    ]
                },
                conf,
                name="替班变更",
            ),
        ],
    }


def test_image_plan_rejects_the_same_error_as_shift_projection(image_plan):
    data = initialize(image_plan)
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    data.operators["渡桥"].current_room = "dormitory_2"
    data.operators["玛恩纳"].current_room = "dormitory_3"
    data.party_time = datetime.now()
    data.first_init = False
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = data
    solver.tasks = []
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={})
    with pytest.raises(ValueError, match="上下班副表推演失败") as failure:
        solver._prepare_shift_backup(task)
    result = data.validate_backup_plans()
    assert not result["success"]
    assert "深海强制上班" in result["message"]
    assert "渡桥下班" in result["message"]
    assert str(failure.value).removeprefix("上下班副表推演失败：") in result["message"]


def test_corrected_image_plan_skips_mutually_exclusive_combinations(image_plan):
    image_plan["backup_plans"][3].plan["central"][4].replacement = ["清道夫"]
    result = initialize(image_plan).validate_backup_plans()
    assert result == {"success": True, "message": "验证成功，共验证 32 次"}


@pytest.mark.parametrize("reverse", [False, True])
def test_primary_replacement_conflict_across_disjoint_backups(reverse):
    plan = two_backups()
    if reverse:
        plan["backup_plans"].reverse()
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert "主力变更" in result["message"]
    assert "替班变更" in result["message"]
    assert "替换组不可用高效组干员" in result["message"]


def test_mutually_exclusive_backups_do_not_report_an_impossible_conflict():
    plan = two_backups()
    plan["backup_plans"][0].trigger = LogicExpression(
        "op_data.operators['能天使'].is_working()", "==", "True"
    )
    plan["backup_plans"][1].trigger = LogicExpression(
        "op_data.operators['能天使'].is_working()", "==", "False"
    )
    result = initialize(plan).validate_backup_plans()
    assert result == {"success": True, "message": "验证成功，共验证 2 次"}


def test_twenty_mutually_exclusive_backups_are_supported():
    plan = two_backups()
    template = plan["backup_plans"][0]
    plan["backup_plans"] = [
        Plan(
            copy.deepcopy(template.plan),
            PlanConfig("", "", ""),
            LogicExpression(
                "op_data.operators['能天使'].current_room", "==", repr(f"room_{index}")
            ),
            name=f"房间条件{index}",
        )
        for index in range(20)
    ]
    result = initialize(plan).validate_backup_plans()
    assert result == {"success": True, "message": "验证成功，共验证 21 次"}


def many_backup_solver(count, *, oscillating=False):
    conf = PlanConfig("", "", "")
    main = {
        "central": [Room("能天使", "", ["红"])],
        "meeting": [Room("芬", "", ["香草"])],
        "dormitory_1": [Room("杜林", "", []), Room("桃金娘", "", [])]
        + [Room("Free", "", []) for _ in range(3)],
    }
    backups = [
        Plan(
            {"central": [Room("讯使", "", ["翎羽"])]}
            if oscillating
            else {"meeting": [Room("讯使", "", ["翎羽"])]},
            conf,
            LogicExpression(
                "op_data.operators['能天使'].is_working()",
                "==",
                "True" if oscillating else "False",
            ),
            name=f"联动副表{index}",
        )
        for index in range(count)
    ]
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = initialize(
        {"default_plan": Plan(main, conf), "backup_plans": backups}
    )
    for op in solver.op_data.operators.values():
        op._current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 5, datetime.now()
    solver.op_data.first_init = False
    solver.tasks = []
    return solver


@pytest.mark.parametrize("count", [1, 20])
def test_many_backups_converge_on_shift_off_and_shift_on(count):
    solver = many_backup_solver(count)
    data = solver.op_data
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_OFF,
        task_plan={"central": ["红"], "dormitory_1": ["Current", "Current", "能天使"]},
    )
    solver._prepare_shift_backup(task)
    assert task.backup_shift_conditions == [True] * count
    assert task.plan["meeting"] == ["讯使"]
    assert data.plan_condition == [False] * count
    assert data.operators["能天使"].current_room == "central"
    assert data.swap_plan(task.backup_shift_conditions, refresh=True) is None
    solver.op_data = data.project_arrangements([task.plan])
    returning = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"central": ["能天使"]}
    )
    solver._prepare_shift_backup(returning)
    assert returning.backup_shift_conditions == [False] * count
    assert returning.plan["meeting"] == ["芬"]
    assert solver.op_data.plan_condition == [True] * count
    assert solver.op_data.operators["能天使"].current_room == "dormitory_1"


def test_twenty_backups_detect_activation_oscillation_and_preserve_the_task():
    solver = many_backup_solver(20, oscillating=True)
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={})
    with pytest.raises(ValueError, match="副表推演出现循环"):
        solver._prepare_shift_backup(task)
    assert task.plan == {}
    assert solver.op_data.plan_condition == [False] * 20
    assert solver.op_data.operators["能天使"].current_room == "central"


def test_three_way_group_and_bed_conflict_is_not_reduced_to_pairs():
    conf = PlanConfig("", "", "")

    def current():
        return Room("Current", "", [])

    plan = {
        "default_plan": Plan(
            {
                "central": [Room("芬", "同组", ["香草"]), Room("讯使", "", ["翎羽"])],
                "dormitory_1": [
                    Room("杜林", "", []),
                    Room("桃金娘", "", []),
                    *[Room("Free", "", []) for _ in range(3)],
                ],
            },
            conf,
        ),
        "backup_plans": [
            Plan(
                {
                    "dormitory_1": [
                        current(),
                        current(),
                        current(),
                        Room("蜜莓", "", []),
                    ]
                },
                conf,
                name="占床甲",
            ),
            Plan(
                {"central": [current(), Room("讯使", "同组", ["翎羽"])]},
                conf,
                name="增加组员",
            ),
            Plan(
                {
                    "dormitory_1": [
                        current(),
                        current(),
                        current(),
                        current(),
                        Room("波登可", "", []),
                    ]
                },
                conf,
                name="占床乙",
            ),
        ],
    }
    for flags in ([True, True, False], [True, False, True], [False, True, True]):
        assert Operators(plan).swap_plan(flags, refresh=True) is None
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert all(name in result["message"] for name in ("占床甲", "增加组员", "占床乙"))
    assert "所需宿舍数2大于当前有效宿舍数1" in result["message"]


def test_later_backup_overrides_a_shared_slot_without_duplicate_primary_error():
    plan = two_backups()
    plan["backup_plans"][1].plan = {"central": [Room("德克萨斯", "", ["翎羽"])]}
    result = initialize(plan).validate_backup_plans()
    assert result == {"success": True, "message": "验证成功，共验证 4 次"}


@pytest.mark.parametrize("valid", [False, True])
def test_validation_preserves_active_plan_and_actual_operator_state(valid):
    plan = two_backups()
    if valid:
        plan["backup_plans"][1].plan["central"][1].replacement = ["初雪"]
    data = initialize(plan)
    assert data.swap_plan([True, False], refresh=True) is None
    data.first_init = False
    op = data.operators["八幡海铃"]
    op.current_room, op.current_index = "central", 0
    op.mood, op.time_stamp = 7, datetime.now()
    before = copy.deepcopy(data.__dict__, {id(data.eval_model): data.eval_model})
    callback = MagicMock()
    Operators.current_room_changed_callback = callback
    result = data.validate_backup_plans()
    assert result["success"] is valid
    assert data.plan_condition == before["plan_condition"]
    assert repr(data.plan) == repr(before["plan"])
    assert data.operators["八幡海铃"] is op
    assert vars(op) == vars(before["operators"]["八幡海铃"])
    assert data.config is before["config"] or vars(data.config) == vars(
        before["config"]
    )
    assert data.first_init is False
    callback.assert_not_called()


def test_no_backups_still_validates_the_main_plan():
    plan = two_backups()
    plan["backup_plans"] = []
    plan["default_plan"].plan["central"][1].replacement = ["能天使"]
    result = Operators(plan).validate_backup_plans()
    assert not result["success"]
    assert "基础验证失败" in result["message"]


def test_main_dorm_layout_uses_initial_validation_rules():
    plan = two_backups()
    plan["default_plan"].plan["dormitory_1"] = [
        Room("杜林", "", []),
        Room("桃金娘", "", []),
        Room("Free", "", []),
        Room("蜜莓", "", []),
        Room("Free", "", []),
    ]
    result = Operators(plan).validate_backup_plans()
    assert not result["success"]
    assert "Free必须连续且安排在宿管后" in result["message"]


def test_large_combination_space_never_reports_partial_validation_as_success(
    monkeypatch,
):
    plan = two_backups()
    monkeypatch.setattr(operators, "MAX_BACKUP_VALIDATION_COMBINATIONS", 2)
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert "验证未完成" in result["message"]
