"""排班校验覆盖与副表演算相同的合并配置错误，且不修改实际驻员。"""

import ast
import copy
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import (
    BaseSchedulerSolver,
    _merge_plan_overlay,
)
from arknights_mower.utils import backup_validation, config, operators, schedule_roster
from arknights_mower.utils.config.plan import parse_plan_document
from arknights_mower.utils.config.plan_advanced import apply_advanced_settings
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators, build_global_plan
from arknights_mower.utils.plan import RIGHT_SIDE_ROOM_CAPACITY, Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    dorm_rebalance_signature,
)

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


def facility_backup():
    conf = PlanConfig("", "", "")
    slots = [
        Room("乌尔比安", "", ["苍苔"], "制造站", "gold"),
        Room("幽灵鲨", "", ["夜烟"], "制造站", "gold"),
    ]
    return {
        "default_plan": Plan({"room_1_3": slots}, conf, products={"room_1_3": "gold"}),
        "backup_plans": [
            Plan(
                {"room_1_3": copy.deepcopy(slots)},
                conf,
                name="深海强制上班",
                task={"room_1_3": ["乌尔比安", "幽灵鲨"]},
                products={"room_1_3": "gold"},
            )
        ],
    }


def trade_schedule(level, primary="lmd", backup="lmd", *, declared=True):
    conf = PlanConfig("", "", "")
    slots = [
        Room(agent, "", [cover], "贸易站", primary)
        for agent, cover in [("能天使", "芬"), ("银灰", "初雪"), ("陈", "红")][:level]
    ]
    return {
        "default_plan": Plan({"room_1_1": slots}, conf, products={"room_1_1": primary}),
        "backup_plans": [
            Plan(
                {"room_1_1": copy.deepcopy(slots)} if declared else {},
                conf,
                name="订单切换",
                products={"room_1_1": backup},
            )
        ],
    }


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("declared", [False, True])
def test_non_three_level_trade_backup_fails_before_combination_analysis(
    monkeypatch, level, enabled, declared
):
    config.conf.product_switching.enable = enabled
    plan = trade_schedule(level, backup="orundum", declared=declared)
    data = initialize(plan)
    analyze = MagicMock(side_effect=AssertionError("invalid order reached analysis"))
    monkeypatch.setattr(backup_validation, "possible_backup_conditions", analyze)
    before = data.plan, data.config, data.operators, data.dorm, data.products
    result = data.validate_backup_plans(max_seconds=0)
    assert result["status"] == "failed"
    assert all(
        text in result["message"]
        for text in ("订单切换", "room_1_1", "3级", "开采协力")
    )
    assert data.plan_condition == [False]
    assert all(
        current is original
        for current, original in zip(
            (data.plan, data.config, data.operators, data.dorm, data.products), before
        )
    )
    analyze.assert_not_called()


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("enabled", [False, True])
def test_non_three_level_trade_primary_reports_validation_error(level, enabled):
    config.conf.product_switching.enable = enabled
    plan = trade_schedule(level, primary="orundum", backup="orundum")
    plan["backup_plans"] = []
    data = Operators(plan)
    error = data.init_and_validate()
    assert all(text in error for text in ("主表", "room_1_1", "3级", "开采协力"))
    result = data.validate_backup_plans()
    assert result["status"] == "failed"
    assert "主表" in result["message"]


@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("enabled", [False, True])
def test_fixed_lmd_trade_target_remains_valid(level, enabled):
    config.conf.product_switching.enable = enabled
    data = initialize(trade_schedule(level))
    assert data.validate_backup_plans()["success"]


@pytest.mark.parametrize("primary,backup", [("lmd", "orundum"), ("orundum", "lmd")])
def test_three_level_trade_order_switch_passes_validation(primary, backup):
    config.conf.product_switching.enable = True
    data = initialize(trade_schedule(3, primary=primary, backup=backup))
    assert data.validate_backup_plans()["success"]
    assert data.swap_plan([True], refresh=True) is None
    assert data.products["room_1_1"] == backup


@pytest.mark.parametrize("level", [1, 2])
def test_non_three_level_trade_activation_preserves_live_state(level):
    config.conf.product_switching.enable = True
    plan = trade_schedule(level)
    data = initialize(plan)
    before = data.plan, data.config, data.operators, data.dorm, data.products
    plan["backup_plans"][0].products["room_1_1"] = "orundum"
    error = data.swap_plan([True], refresh=True)
    assert "3级" in error
    assert data.plan_condition == [False]
    assert all(
        current is original
        for current, original in zip(
            (data.plan, data.config, data.operators, data.dorm, data.products), before
        )
    )


def test_recycle_task_without_primary_facility_passes_startup_and_activation():
    plan = two_backups()
    plan["backup_plans"] = [
        Plan(
            {},
            plan["default_plan"].config,
            name="回收站临时换人",
            task={"recycle": ["芬", "香草"]},
        )
    ]
    data = initialize(plan)
    result = data.validate_backup_plans()
    assert result["success"], result
    assert data.swap_plan([True], refresh=True) is None
    assert data.plan_condition == [True]
    assert "recycle" not in data.plan
    assert data.backup_plans[0].task == {"recycle": ["芬", "香草"]}


@pytest.mark.parametrize("room,capacity", RIGHT_SIDE_ROOM_CAPACITY.items())
@pytest.mark.parametrize("count", [None, 0, 1])
@pytest.mark.parametrize("mode", ["roster", "task", "both"])
def test_right_side_backups_reach_final_arrangement(room, capacity, count, mode):
    plan = two_backups()
    conf = plan["default_plan"].config
    if count is not None:
        plan["default_plan"].plan[room] = [Room("月见夜", "", ["史都华德"])][:count]
    names = ["香草", "翎羽"][:capacity]
    slots = [
        Room(name, "", [replacement])
        for name, replacement in zip(names, ["克洛丝", "斑点"])
    ]
    plan["backup_plans"] = [
        Plan(
            {room: slots} if mode != "task" else {},
            conf,
            name="右侧驻员",
            task={room: names} if mode != "roster" else {},
        )
    ]
    data = initialize(plan)
    result = data.validate_backup_plans()
    assert result["success"], result
    previous = copy.deepcopy(data.plan)
    original = repr(plan["default_plan"].plan)
    previous_layout = dorm_rebalance_signature(data)
    assert data.swap_plan([True], refresh=True) is None
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    transition = solver._backup_transition_plan(
        previous, [False], [True], [], previous_layout
    )
    assert transition[room] == names
    assert repr(plan["default_plan"].plan) == original
    if mode != "task":
        assert [slot.agent for slot in data.plan[room]] == names
    else:
        assert repr(data.plan) == repr(previous)

    active_plan = copy.deepcopy(data.plan)
    assert data.swap_plan([False], refresh=True) is None
    transition = solver._backup_transition_plan(
        active_plan, [True], [False], [], previous_layout
    )
    if count == 1:
        assert transition[room] == ["月见夜"]
    else:
        assert room not in transition


@pytest.mark.parametrize("room,capacity", RIGHT_SIDE_ROOM_CAPACITY.items())
def test_empty_right_side_backup_preserves_staff_and_has_no_transition(room, capacity):
    plan = two_backups()
    conf = plan["default_plan"].config
    plan["default_plan"].plan[room] = [Room("香草", "", ["克洛丝"])]
    plan["backup_plans"] = [Plan({room: []}, conf, task={room: []})]
    data = initialize(plan)
    previous = copy.deepcopy(data.plan)
    layout = dorm_rebalance_signature(data)
    assert data.swap_plan([True], refresh=True) is None
    assert [slot.agent for slot in data.plan[room]] == ["香草"]
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks, solver.task = data, [], None
    assert solver._backup_transition_plan(previous, [False], [True], [], layout) == {}


def test_right_side_task_overlay_extends_existing_partial_target():
    from types import SimpleNamespace

    plan = {"recycle": ["芬"]}
    _merge_plan_overlay(
        plan, {"recycle": ["Current", "香草"]}, SimpleNamespace(plan={})
    )
    assert plan == {"recycle": ["芬", "香草"]}


@pytest.mark.parametrize("room", ["meeting", "train", "recycle"])
def test_right_side_roster_current_keeps_first_slot_and_adds_second(room):
    plan = two_backups()
    conf = plan["default_plan"].config
    plan["default_plan"].plan[room] = [Room("香草", "", ["克洛丝"])]
    plan["backup_plans"] = [
        Plan(
            {room: [Room("Current", "", []), Room("翎羽", "", ["斑点"])]},
            conf,
        )
    ]
    data = initialize(plan)
    assert data.validate_backup_plans()["success"]
    assert data.swap_plan([True], refresh=True) is None
    assert [slot.agent for slot in data.plan[room]] == ["香草", "翎羽"]


@pytest.mark.parametrize("target", ["Current", "Free", "", "安哲拉"])
def test_backup_task_overflow_fails_before_combination_analysis(monkeypatch, target):
    plan = facility_backup()
    plan["backup_plans"][0].task["room_1_3"].append(target)
    data = initialize(plan)
    before = copy.deepcopy(data.plan)
    analyze = MagicMock(side_effect=AssertionError("invalid task reached analysis"))
    monkeypatch.setattr(backup_validation, "possible_backup_conditions", analyze)
    result = data.validate_backup_plans(max_seconds=0)
    assert result["status"] == "failed"
    assert "深海强制上班" in result["message"]
    assert "room_1_3" in result["message"]
    assert "2 个岗位" in result["message"]
    assert data.plan_condition == [False]
    assert [slot.agent for slot in data.plan["room_1_3"]] == [
        slot.agent for slot in before["room_1_3"]
    ]
    assert plan["backup_plans"][0].task["room_1_3"][-1] == target
    analyze.assert_not_called()


@pytest.mark.parametrize("count", [1, 3])
def test_backup_facility_slot_count_cannot_change_level(count):
    plan = facility_backup()
    slots = plan["backup_plans"][0].plan["room_1_3"]
    if count == 1:
        slots.pop()
    else:
        slots.append(Room("Current", "", [], "制造站", "gold"))
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert f"岗位数 2 → {count}" in result["message"]
    assert "切设施功能尚未实现" in result["message"]


@pytest.mark.parametrize("agent", ["Current", "乌尔比安"])
def test_backup_facility_type_cannot_change_even_with_same_slots(agent):
    plan = facility_backup()
    slot = plan["backup_plans"][0].plan["room_1_3"][0]
    slot.agent = agent
    slot.facility = "贸易站"
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert "制造站 → 贸易站" in result["message"]


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("product", ["gold", "exp3"])
def test_backup_product_change_requires_enabled_switching(enabled, product):
    config.conf.product_switching.enable = enabled
    plan = facility_backup()
    plan["backup_plans"][0].products["room_1_3"] = product
    result = initialize(plan).validate_backup_plans()
    assert result["success"] is (enabled or product == "gold")
    if not result["success"]:
        assert "gold → exp3" in result["message"]
        assert "未开启自动切换产物与订单" in result["message"]


def test_backup_all_current_facility_still_has_to_preserve_level():
    plan = facility_backup()
    plan["backup_plans"][0].plan["room_1_3"] = [
        Room("Current", "", [], "制造站", "gold")
    ] * 3
    result = initialize(plan).validate_backup_plans()
    assert not result["success"]
    assert "改变设施等级" in result["message"]


@pytest.mark.parametrize("change", ["level", "type", "task", "product"])
def test_runtime_backup_activation_rejects_conflicts_without_mutation(change):
    plan = facility_backup()
    data = initialize(plan)
    before = data.plan, data.config, data.operators, data.dorm, data.products
    operator = data.operators["乌尔比安"]
    operator.current_room = "room_1_3"
    operator.mood = 7
    backup = plan["backup_plans"][0]
    if change == "level":
        backup.plan["room_1_3"].pop()
    elif change == "type":
        backup.plan["room_1_3"][0].facility = "贸易站"
    elif change == "task":
        backup.task["room_1_3"].append("Current")
    else:
        backup.products["room_1_3"] = "exp3"
        config.conf.product_switching.enable = False
    error = data.swap_plan([True], refresh=True)
    assert "深海强制上班" in error
    assert data.plan_condition == [False]
    assert all(
        current is original
        for current, original in zip(
            (data.plan, data.config, data.operators, data.dorm, data.products), before
        )
    )
    assert operator.current_room == "room_1_3"
    assert operator.mood == 7


def test_nonproduction_partial_overlay_remains_supported():
    plan = two_backups()
    plan["backup_plans"] = plan["backup_plans"][:1]
    result = initialize(plan).validate_backup_plans()
    assert result["success"]


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
    assert result == {
        "success": True,
        "status": "passed",
        "message": "验证成功，共验证 13 次",
    }


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
    assert result == {
        "success": True,
        "status": "passed",
        "message": "验证成功，共验证 3 次",
    }


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
    assert result == {
        "success": True,
        "status": "passed",
        "message": "验证成功，共验证 2 次",
    }


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
    assert result == {
        "success": True,
        "status": "passed",
        "message": "验证成功，共验证 3 次",
    }


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


@pytest.mark.parametrize("count", [0, 8])
def test_identical_effective_schedules_are_validated_once(monkeypatch, count):
    plan = two_backups()
    plan["backup_plans"] = [
        copy.deepcopy(plan["backup_plans"][0]) for _ in range(count)
    ]
    data = Operators(plan)
    original = Operators.init_and_validate
    calls = []

    def check(self, update=False):
        calls.append(tuple(self.plan_condition))
        return original(self, update)

    monkeypatch.setattr(Operators, "init_and_validate", check)
    assert data.validate_backup_plans()["success"]
    assert len(calls) == (2 if count else 1)
    assert len(set(calls)) == len(calls)


@pytest.mark.parametrize("valid", [False, True])
def test_manual_route_checks_baseline_only_once(monkeypatch, valid):
    plan = two_backups()
    plan["backup_plans"] = []
    if not valid:
        plan["default_plan"].plan["central"][0].replacement = []
    original = Operators.init_and_validate
    check = MagicMock(side_effect=lambda self, update=False: original(self, update))
    monkeypatch.setattr(
        Operators, "init_and_validate", lambda self, update=False: check(self, update)
    )
    server = Path(__file__).resolve().parents[2] / "server.py"
    route = next(
        node
        for node in ast.parse(server.read_text()).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "validate_backup_plans_route"
    )
    route.decorator_list = []
    namespace = {
        "build_global_plan": lambda: plan,
        "Operators": Operators,
        "request": MagicMock(get_json=MagicMock(return_value={})),
        "logger": MagicMock(),
    }
    exec(
        compile(ast.Module(body=[route], type_ignores=[]), str(server), "exec"),
        namespace,
    )
    result = namespace["validate_backup_plans_route"]()
    assert result["success"] is valid
    assert result["status"] == ("passed" if valid else "failed")
    check.assert_called_once()


def test_validation_reuse_does_not_survive_a_configuration_edit():
    plan = two_backups()
    plan["backup_plans"][1].plan["central"][1].replacement = ["初雪"]
    data = Operators(plan)
    assert data.validate_backup_plans()["success"]
    plan["backup_plans"][1].plan["central"][1].replacement = ["八幡海铃"]
    assert data.validate_backup_plans()["status"] == "failed"


def test_same_staffing_with_different_zero_mood_configuration_is_rechecked():
    plan = {
        "default_plan": Plan(
            {"central": [Room("能天使", "", [])]},
            PlanConfig("", "", "", workaholic="能天使"),
        ),
        "backup_plans": [
            Plan({}, PlanConfig("", "", "", removed_operators={"workaholic": "能天使"}))
        ],
    }
    data = initialize(plan)
    result = data.validate_backup_plans()
    assert result["status"] == "failed"
    assert "能天使" in result["message"]
    assert "替换组缺失" in result["message"]
    assert data.swap_plan([True], refresh=True) == "以下干员替换组缺失：能天使"


def test_same_staffing_does_not_reuse_maintenance_permission(monkeypatch):
    plan = two_backups()
    slot = {"central": [Room("但书", "", ["红"])]}
    plan["backup_plans"] = [
        Plan(slot, PlanConfig("", "", ""), name="普通副表"),
        Plan(
            copy.deepcopy(slot),
            PlanConfig("", "", ""),
            LogicExpression("op_data.major_maintenance_remaining_hours()", "<=", "0.5"),
            name="维护副表",
        ),
    ]
    monkeypatch.setattr(
        backup_validation,
        "possible_backup_conditions",
        lambda *args, **kwargs: [(False, True), (True, False)],
    )
    result = Operators(plan).validate_backup_plans()
    assert result["status"] == "failed"
    assert "普通副表" in result["message"]
    assert "高效组不可用" in result["message"]


@pytest.mark.parametrize("room", ["central", "meeting", "train", "recycle"])
def test_backup_slot_copy_preserves_source_bindings_and_config(room):
    plan = two_backups()
    backup = plan["backup_plans"][0]
    backup.plan = {room: [Room("八幡海铃", "甲", ["红"])]}
    backup.plan[room][0].group_bindings = [{"group": "乙", "replacement": ["黑角"]}]
    data = Operators(plan)
    merged, conf = data.merge_plan(0, data.config)
    merged[room][0].group_bindings[0]["replacement"].append("砾")
    conf.workaholic.append("能天使")
    assert backup.plan[room][0].group_bindings[0]["replacement"] == ["黑角"]
    assert "能天使" not in backup.config.workaholic
    assert "能天使" not in data.config.workaholic


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
    assert result["status"] == "incomplete"
    assert "验证未完成" in result["message"]
    assert "允许启动" in result["message"]


@pytest.mark.parametrize("same_room", [False, True])
def test_product_specific_backups_skip_only_same_room_exclusion(same_room):
    plan = two_backups()
    plan["backup_plans"][0].trigger = LogicExpression(
        "op_data.facility_product('room_1_1')", "==", "gold"
    )
    second_room = "room_1_1" if same_room else "room_1_2"
    plan["backup_plans"][1].trigger = LogicExpression(
        f"op_data.facility_product('{second_room}')", "==", "exp3"
    )
    result = initialize(plan).validate_backup_plans()
    assert result["success"] is same_room
    assert result["status"] == ("passed" if same_room else "failed")
    if same_room:
        assert result["message"] == "验证成功，共验证 3 次"
    else:
        assert "替换组不可用高效组干员" in result["message"]


def test_analysis_budget_returns_an_incomplete_warning_without_mutating_state(
    monkeypatch,
):
    data = initialize(two_backups())
    op = data.operators["能天使"]
    op.mood = 7
    monkeypatch.setattr(backup_validation, "MAX_CONDITION_STATES", 2)
    result = data.validate_backup_plans()
    assert result["success"] is False
    assert result["status"] == "incomplete"
    assert "状态数量超过分析上限" in result["message"]
    assert "允许启动" in result["message"]
    assert data.plan_condition == [False, False]
    assert data.operators["能天使"] is op
    assert op.mood == 7


@pytest.mark.parametrize("failure", ["baseline", "ownership"])
@pytest.mark.parametrize("max_seconds", [None, 0])
def test_configuration_errors_still_block_when_combination_budget_is_exhausted(
    monkeypatch, failure, max_seconds
):
    plan = two_backups()
    monkeypatch.setattr(operators, "MAX_BACKUP_VALIDATION_COMBINATIONS", 0)
    if failure == "baseline":
        plan["default_plan"].plan["central"][1].replacement = ["能天使"]
    else:
        monkeypatch.setattr(
            schedule_roster, "validate_owned_operators", lambda _: "缺少已持有干员"
        )
    result = Operators(plan).validate_backup_plans(max_seconds=max_seconds)
    assert result["success"] is False
    assert result["status"] == "failed"
    assert "验证未完成" not in result["message"]


def test_unexpected_analysis_error_is_not_an_incomplete_warning(monkeypatch):
    monkeypatch.setattr(
        backup_validation,
        "possible_backup_conditions",
        MagicMock(side_effect=ValueError("unexpected analysis failure")),
    )
    with pytest.raises(ValueError, match="unexpected analysis failure"):
        initialize(two_backups()).validate_backup_plans()


def test_runtime_still_rejects_active_conflict_after_incomplete_validation(monkeypatch):
    plan = two_backups()
    for backup, name in zip(plan["backup_plans"], ("能天使", "银灰")):
        backup.trigger = LogicExpression(
            f"op_data.operators['{name}'].is_working()", "==", "True"
        )
    data = initialize(plan)
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, datetime.now()
    data.first_init = False
    monkeypatch.setattr(operators, "MAX_BACKUP_VALIDATION_COMBINATIONS", 2)
    assert data.validate_backup_plans()["status"] == "incomplete"
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data, solver.tasks = data, []
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan={})
    with pytest.raises(ValueError, match="上下班副表推演失败.*替换组不可用高效组干员"):
        solver._prepare_shift_backup(task)
    assert task.plan == {}
    assert data.plan_condition == [False, False]
    assert data.operators["能天使"].current_room == "central"


@pytest.mark.parametrize("max_seconds, analysis_seconds", [(5, 0), (5, 4), (None, 0)])
def test_elapsed_budget_stops_combinations_and_manual_validation_is_untimed(
    monkeypatch, max_seconds, analysis_seconds
):
    plan = two_backups()
    plan["backup_plans"] = [copy.deepcopy(plan["backup_plans"][0]) for _ in range(4)]
    for backup, name in zip(plan["backup_plans"], ("能天使", "银灰", "芬", "初雪")):
        backup.config = PlanConfig(
            "", "", "", operator_mood_limits={name: {"lower": 1, "upper": 24}}
        )
    data = initialize(plan)
    op = data.operators["能天使"]
    op.mood = 7
    before = copy.deepcopy(data.__dict__, {id(data.eval_model): data.eval_model})
    clock = [100.0]
    checked = []
    monkeypatch.setattr(operators, "monotonic", lambda: clock[0])
    monkeypatch.setattr(backup_validation, "monotonic", lambda: clock[0])
    analysis = backup_validation.possible_backup_conditions

    def slow_analysis(*args, **kwargs):
        combinations = analysis(*args, **kwargs)
        clock[0] += analysis_seconds
        return combinations

    monkeypatch.setattr(backup_validation, "possible_backup_conditions", slow_analysis)
    original = Operators.init_and_validate

    def slow_check(self, update=False):
        error = original(self, update)
        if update:
            checked.append(self.plan_condition)
            clock[0] += 2
        return error

    monkeypatch.setattr(Operators, "init_and_validate", slow_check)
    result = data.validate_backup_plans(max_seconds=max_seconds)
    if max_seconds is None:
        assert result == {
            "success": True,
            "status": "passed",
            "message": "验证成功，共验证 16 次",
        }
        assert len(checked) == 15
    else:
        assert result["status"] == "incomplete"
        assert result["success"] is False
        assert "耗时预算" in result["message"]
        expected_checks = 1 if analysis_seconds else 3
        assert f"已验证 {expected_checks + 1} 次" in result["message"]
        assert "允许启动" in result["message"]
        assert len(checked) == expected_checks
    assert clock[0] >= 105
    assert data.plan_condition == before["plan_condition"]
    assert repr(data.plan) == repr(before["plan"])
    assert data.operators["能天使"] is op
    assert vars(op) == vars(before["operators"]["能天使"])


def test_condition_analysis_uses_the_same_deadline_as_combinations(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(operators, "monotonic", lambda: clock[0])
    monkeypatch.setattr(backup_validation, "monotonic", lambda: clock[0])
    parse = backup_validation.ast.parse

    def slow_parse(*args, **kwargs):
        tree = parse(*args, **kwargs)
        clock[0] += 5
        return tree

    monkeypatch.setattr(backup_validation.ast, "parse", slow_parse)
    plan = two_backups()
    plan["backup_plans"][0].trigger = LogicExpression("True", "==", "True")
    data = initialize(plan)
    result = data.validate_backup_plans(max_seconds=5)
    assert result["status"] == "incomplete"
    assert "已验证 1 次" in result["message"]


def test_error_from_current_combination_blocks_even_if_the_deadline_has_elapsed(
    monkeypatch,
):
    clock = [100.0]
    monkeypatch.setattr(operators, "monotonic", lambda: clock[0])
    monkeypatch.setattr(backup_validation, "monotonic", lambda: clock[0])
    original = Operators.init_and_validate

    def slow_conflict(self, update=False):
        error = original(self, update)
        if update and all(self.plan_condition):
            clock[0] += 5
        return error

    monkeypatch.setattr(Operators, "init_and_validate", slow_conflict)
    result = initialize(two_backups()).validate_backup_plans(max_seconds=5)
    assert clock[0] == 105
    assert result["status"] == "failed"
    assert "替换组不可用高效组干员" in result["message"]


def test_valid_plan_passes_within_the_startup_budget(monkeypatch):
    monkeypatch.setattr(operators, "monotonic", lambda: 100.0)
    monkeypatch.setattr(backup_validation, "monotonic", lambda: 104.9)
    plan = two_backups()
    plan["backup_plans"][1].plan["central"][1].replacement = ["初雪"]
    assert initialize(plan).validate_backup_plans(max_seconds=5) == {
        "success": True,
        "status": "passed",
        "message": "验证成功，共验证 3 次",
    }
