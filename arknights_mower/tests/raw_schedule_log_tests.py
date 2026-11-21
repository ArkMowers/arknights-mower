"""计划、名单及库存结果保留完整可读 INFO，内部容器只进入 DEBUG。"""

import logging
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import backup_refresh_continuity_tests as backups
from arknights_mower.tests import dorm_admission_priority_tests as dorms
from arknights_mower.tests import mastery_choose_train_tests as training
from arknights_mower.tests import product_long_wait_tests as long_wait
from arknights_mower.tests import product_shift_dispatch_tests as products
from arknights_mower.tests import workshop_limits_tests as workshop
from arknights_mower.tests.resting_priority_tests import set_tier
from arknights_mower.utils import config, maa_stage_inventory
from arknights_mower.utils.resting_priority import RestingTier
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")
backup_solver = backups.solver
op_data = dorms.op_data
residents = dorms.residents
pending_return = products.pending_return
inventory = workshop.inventory
workshop_game = workshop.game
solver = long_wait.solver
shared_product_cycle = long_wait.shared_product_cycle
long_cycle = long_wait.long_cycle


def capture(caplog, monkeypatch):
    monkeypatch.setattr(base.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(base.logger, "propagate", False)
    monkeypatch.setattr(base.logger, "disabled", False)
    caplog.set_level(logging.DEBUG, logger=base.logger.name)
    caplog.clear()


def info(caplog, prefix):
    return [
        record
        for record in caplog.records
        if record.levelno == logging.INFO and prefix in record.getMessage()
    ]


def assert_plan(record, plan):
    snapshot = record.log_task
    assert [(room["id"], room["agents"]) for room in snapshot["rooms"]] == list(
        plan.items()
    )
    assert "SchedulerTask(" not in record.getMessage()
    for room in snapshot["rooms"]:
        assert f"{room['label']}：{'、'.join(room['agents'])}" in record.getMessage()
    return deepcopy(snapshot)


def test_restored_task_log_retains_title_time_arrangement_and_backup_snapshot(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(operators={}, plan_condition=[])
    task = SchedulerTask(
        time=datetime(2026, 11, 5, 12, 30, 1, 123456),
        task_plan={"dormitory_1": ["Current", "砾", "Free"]},
        task_type=TaskTypes.SELF_CORRECTION,
    )
    task.log_source_title = "原有纠错安排"
    task.log_backup_changes = [{"name": "深海下班", "active": True}]
    task.backup_shift_conditions = [True]
    task.execution_failure = {
        "rooms": ("dormitory_1",),
        "snapshot": {"observations": {}, "reservations": (), "room_observations": {}},
    }
    instance.tasks = [task]
    instance._discard_legacy_recovery_checks = MagicMock()
    instance._discard_legacy_run_order_waits = MagicMock()
    instance._refresh_derived_correction = MagicMock(return_value=True)
    instance._task_failure_snapshot = MagicMock(
        return_value={
            "observations": {},
            "reservations": (),
            "room_observations": {"dormitory_1": 2},
            "correction_groups": {},
        }
    )
    original = deepcopy(task.plan)
    deadline = task.time

    instance._resume_failed_tasks()

    assert instance.tasks == [task]
    assert task.time == deadline and task.plan == original
    assert not hasattr(task, "execution_failure")
    records = info(caplog, "恢复原任务")
    assert len(records) == 1
    snapshot = assert_plan(records[0], original)
    assert snapshot["title"] == "原有纠错安排"
    assert snapshot["backups"] == [{"name": "深海下班", "active": True}]
    assert str(deadline) in records[0].getMessage()
    task.plan["dormitory_1"][1] = "清流"
    task.log_backup_changes[0]["name"] = "后改名称"
    assert records[0].log_task == snapshot


@pytest.mark.parametrize(
    ("kind", "metadata", "expected"),
    [
        (TaskTypes.WORKSHOP, "蜜莓", "蜜莓"),
        (TaskTypes.SWITCH_PRODUCT, "room_2_1,lmd", "贸易站 B201 → 龙门商法"),
        (TaskTypes.SWITCH_PRODUCT, "room_2_1,orundum", "贸易站 B201 → 开采协力"),
        (TaskTypes.SWITCH_PRODUCT, "room_2_2,gold", "制造站 B202 → 赤金"),
        (TaskTypes.DEPOT, "复查仓库记录", "复查仓库记录"),
        (TaskTypes.NOT_SPECIFIC, "实际目标", "实际目标"),
    ],
)
def test_restored_task_without_staffing_keeps_its_actual_target(
    caplog, monkeypatch, kind, metadata, expected
):
    capture(caplog, monkeypatch)
    task = SchedulerTask(
        time=datetime(2026, 11, 5, 12, 30, 1, 123456),
        task_type=kind,
        meta_data=metadata,
    )
    task.execution_failure = {
        "rooms": (),
        "snapshot": {"observations": {}, "reservations": (), "room_observations": {}},
    }
    if kind == TaskTypes.NOT_SPECIFIC:
        task.log_source_title = "复查：实际目标"
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        operators={},
        facility_states={
            "room_2_1": {"facility": "trade"},
            "room_2_2": {"facility": "manufacture"},
        },
    )
    instance.tasks = [task]
    instance._discard_legacy_recovery_checks = MagicMock()
    instance._discard_legacy_run_order_waits = MagicMock()
    instance._refresh_derived_correction = MagicMock(return_value=True)
    instance._task_failure_snapshot = MagicMock(
        return_value={
            "observations": {},
            "reservations": (),
            "room_observations": {},
            "correction_groups": {},
            "new_observation": True,
        }
    )
    deadline = task.time

    instance._resume_failed_tasks()

    assert instance.tasks == [task]
    assert task.time == deadline and task.meta_data == metadata and task.plan == {}
    records = info(caplog, "恢复原任务")
    assert len(records) == 1
    assert expected in records[0].getMessage()
    assert str(deadline) in records[0].getMessage()
    assert "room_2_" not in records[0].getMessage()
    if kind == TaskTypes.SWITCH_PRODUCT:
        assert records[0].log_task["targets"] == [
            {"id": metadata.split(",")[0], "label": expected}
        ]
    if kind == TaskTypes.NOT_SPECIFIC:
        assert records[0].getMessage().count("实际目标") == 1
    if kind == TaskTypes.WORKSHOP:
        assert "[[operator:蜜莓]]" in records[0].getMessage()
        assert records[0].log_agents == ["蜜莓"]


@pytest.mark.parametrize("coalesced", [False, True])
def test_backup_final_plan_is_complete_and_coalesced_plan_is_not_duplicated(
    backup_solver, caplog, monkeypatch, coalesced
):
    instance = backup_solver
    instance.op_data.backup_plans[0].name = "感知下班"
    deadline = instance.tasks[1]
    instance.tasks, instance.task = [deadline], None
    pending = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"room_1_2": ["砾", "Current", "Free"]},
    )
    if coalesced:
        instance.tasks.append(pending)
    instance.queue_product_switches = MagicMock()
    instance._backup_transition_plan = MagicMock(return_value=deepcopy(pending.plan))
    capture(caplog, monkeypatch)
    generated = []

    assert instance.backup_plan_solver(generated_tasks=generated)

    task = next(task for task in generated if task.plan)
    records = info(caplog, "已生成任务")
    assert len(records) == 1
    assert task.log_source_title == "调整干员（副表：感知下班）"
    assert_plan(records[0], task.plan)
    assert str(task.time) in records[0].getMessage()
    if coalesced:
        assert any(
            record.levelno == logging.DEBUG
            and "副表收敛合并" in record.getMessage()
            and "{'room_1_2':" in record.getMessage()
            for record in caplog.records
        ), [
            record.getMessage()
            for record in caplog.records
            if "副表收敛" in record.getMessage()
        ]
        summaries = info(caplog, "副表收敛合并")
        assert len(summaries) == 1
        assert_plan(summaries[0], task.plan)
    assert deadline in instance.tasks


def test_independent_deferred_slots_keep_the_new_tasks_full_arrangement(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        operators={}, get_current_operator=lambda *_: None
    )
    task = SchedulerTask(
        time=datetime(2026, 11, 5, 12, 30, 1, 123456),
        task_plan={
            "room_2_2": ["砾", "Current", "Free"],
            "dormitory_1": ["杜林", "Current", "Free"],
        },
        task_type=TaskTypes.SELF_CORRECTION,
    )
    instance.tasks = [task]
    deadline = task.time

    instance._reserve_deferred_product_shift(task, {("room_2_2", 0), ("room_2_2", 2)})

    independent = instance.tasks[1]
    assert task.time == deadline
    assert task.plan == {"room_2_2": ["砾", "Current", "Free"]}
    records = info(caplog, "已生成可先执行的任务")
    assert len(records) == 1
    assert_plan(records[0], independent.plan)
    assert str(independent.time) in records[0].getMessage()


def test_dorm_admission_log_describes_the_task_instead_of_completed_recovery(
    residents, caplog, monkeypatch
):
    set_tier(residents, "红", RestingTier.PRIORITY, 20).operator_type = "low"
    tasks = []
    capture(caplog, monkeypatch)

    try_add_release_dorm({}, None, residents, tasks)

    assert len(tasks) == 1
    records = info(caplog, "任务")
    assert len(records) == 1
    assert_plan(records[0], tasks[0].plan)
    assert str(tasks[0].time) in records[0].getMessage()
    assert "恢复完成" not in records[0].getMessage()


def test_run_order_internal_records_are_debug_and_info_names_every_facility(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    rooms = {f"room_{i}_1": {"internal": i} for i in (1, 2, 3)}
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        run_order_rooms=rooms,
        facility_states={room: {"facility": "trade"} for room in rooms},
    )
    monkeypatch.setattr(base, "scheduling", MagicMock(return_value=None))

    assert instance._adjust_run_orders([])

    summaries = info(caplog, "跑单设施")
    assert len(summaries) == 1
    assert "贸易站 B101、贸易站 B201、贸易站 B301" in summaries[0].getMessage()
    assert not any("internal" in record.getMessage() for record in info(caplog, ""))
    assert any(
        record.levelno == logging.DEBUG and "internal" in record.getMessage()
        for record in caplog.records
    )
    assert instance.op_data.run_order_rooms is rooms


@pytest.mark.parametrize(
    ("before", "after", "desired", "position"),
    [
        (["褐果", "桃金娘"], ["夜莺", "桃金娘"], ["夜莺", "Current"], "协助位"),
        (["褐果", "桃金娘"], ["褐果", "夜莺"], ["Current", "夜莺"], "训练位"),
    ],
)
def test_training_pending_selection_keeps_real_names_and_slot_positions(
    caplog, monkeypatch, before, after, desired, position
):
    capture(caplog, monkeypatch)
    instance = training.make_solver(
        [
            base.Scene.INFRA_DETAILS,
            base.Scene.INFRA_DETAILS,
            base.Scene.INFRA_ARRANGE_ORDER,
            base.Scene.INFRA_DETAILS,
        ],
        [
            [{"agent": name} for name in before],
            [{"agent": name} for name in after],
        ],
    )

    base.BaseSchedulerSolver.choose_train(instance, desired)

    if position == "协助位":
        instance.choose_agent.assert_called_once_with(["夜莺"], "train", True)
        instance.choose_train_ope.assert_not_called()
    else:
        instance.choose_train_ope.assert_called_once_with("夜莺")
        instance.choose_agent.assert_not_called()
    records = info(caplog, "正在安排")
    assert len(records) == 1
    assert records[0].getMessage() == f"正在安排 [[operator:夜莺]] 进驻训练室{position}"
    assert records[0].log_room == "train" and records[0].log_agents == ["夜莺"]
    assert records[0].log_event == {
        "type": "training-selection",
        "positions": [{"agent": "夜莺", "index": 0 if position == "协助位" else 1}],
    }
    assert not any("['select']" in record.getMessage() for record in info(caplog, ""))


def test_inventory_stage_selection_preserves_result_order_and_readable_candidates(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {"stage": "1-7", "items": [{"item_id": "30012", "limit": 5}]}
            ],
            maa_stage_ratio_rules=[
                {
                    "name": "测试比例",
                    "members": [
                        {"stage": "PR-A-1", "item_id": "a", "ratio": 1},
                        {"stage": "PR-B-1", "item_id": "b", "ratio": 1},
                    ],
                }
            ],
        ),
    )
    stock = {"30012": 5, "a": 10, "b": 2}
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: (stock, 123)
    )
    instance = object.__new__(base.BaseSchedulerSolver)
    original = ["1-7", "PR-A-1", "PR-B-1", "Annihilation"]

    assert instance.apply_maa_stage_inventory_rules(original) == [
        "Annihilation",
        "PR-B-1",
    ]

    messages = [record.getMessage() for record in info(caplog, "")]
    assert "固源岩库存已达到设定上限，本轮跳过1-7" in messages
    skipped = info(caplog, "本轮跳过1-7")[0]
    assert skipped.log_event == {
        "type": "stage-inventory-limit",
        "stage": {"code": "1-7", "drops": ["固源岩"]},
    }
    assert (
        "比例规则「测试比例」的刷取比例相同（1:1），优先刷取库存相对不足的材料，本轮选择 PR-B-1"
        in messages
    )
    assert "接下来计划依次刷取当期剿灭 → PR-B-1" in messages
    assert not any("[" in message or "{" in message for message in messages)
    assert original == ["1-7", "PR-A-1", "PR-B-1", "Annihilation"]
    assert stock == {"30012": 5, "a": 10, "b": 2}


@pytest.mark.parametrize(
    "operator,stock,expected",
    [
        ("and", {"30012": 5, "30022": 7}, "固源岩、糖"),
        ("and", {"30012": 5, "30022": 2}, None),
        ("or", {"30012": 5, "30022": 2}, "固源岩"),
        ("or", {"30012": 1, "30022": 7}, "糖"),
    ],
)
def test_stage_limit_log_names_only_materials_that_reached_the_real_rule(
    caplog, monkeypatch, operator, stock, expected
):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {
                    "stage": "1-7",
                    "operator": operator,
                    "items": [
                        {"item_id": "30012", "limit": 5},
                        {"item_id": "30022", "limit": 7},
                    ],
                }
            ],
            maa_stage_ratio_rules=[],
        ),
    )
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: (stock, None)
    )
    before = deepcopy(stock)
    instance = object.__new__(base.BaseSchedulerSolver)

    assert instance.apply_maa_stage_inventory_rules(["1-7"]) == (
        [] if expected is not None else ["1-7"]
    )

    if expected is None:
        assert info(caplog, "本轮跳过") == []
    else:
        assert info(caplog, "本轮跳过1-7")[0].getMessage() == (
            f"{expected}库存已达到设定上限，本轮跳过1-7"
        )
    assert stock == before


def test_stage_limit_log_distinguishes_limit_materials_and_main_activity_drops(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {"stage": "TEST-ACT", "items": [{"item_id": "30012", "limit": 5}]}
            ],
            maa_stage_ratio_rules=[],
        ),
    )
    monkeypatch.setattr(
        base,
        "stage_data_full",
        [
            {
                "id": "TEST-ACT",
                "drop": [
                    {"id": "30022", "type": "MATERIAL", "dropType": "NORMAL"},
                    {"id": "30012", "type": "MATERIAL", "dropType": "SPECIAL"},
                ],
            }
        ],
    )
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: ({"30012": 5}, None)
    )
    instance = object.__new__(base.BaseSchedulerSolver)

    assert instance.apply_maa_stage_inventory_rules(["TEST-ACT"]) == []

    result = info(caplog, "本轮跳过TEST-ACT")[0]
    assert result.getMessage() == "固源岩库存已达到设定上限，本轮跳过TEST-ACT"
    assert result.log_event == {
        "type": "stage-inventory-limit",
        "stage": {"code": "TEST-ACT", "drops": ["糖"]},
    }


def test_stage_limit_log_keeps_each_stage_and_uses_unknown_material_fallback(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {"stage": "1-7", "items": [{"item_id": "30012", "limit": 5}]},
                {
                    "stage": "UNKNOWN-STAGE",
                    "items": [{"item_id": "unknown", "limit": 3}],
                },
            ],
            maa_stage_ratio_rules=[],
        ),
    )
    monkeypatch.setattr(
        maa_stage_inventory,
        "load_inventory_snapshot",
        lambda: ({"30012": 5, "unknown": 3}, None),
    )
    instance = object.__new__(base.BaseSchedulerSolver)

    assert instance.apply_maa_stage_inventory_rules(["1-7", "UNKNOWN-STAGE"]) == []

    skipped = info(caplog, "本轮跳过")
    assert [record.getMessage() for record in skipped] == [
        "固源岩库存已达到设定上限，本轮跳过1-7",
        "对应材料库存已达到设定上限，本轮跳过UNKNOWN-STAGE",
    ]
    assert [record.log_event["stage"] for record in skipped] == [
        {"code": "1-7", "drops": ["固源岩"]},
        {"code": "UNKNOWN-STAGE", "drops": []},
    ]


def test_empty_inventory_selection_has_an_explicit_empty_result(caplog, monkeypatch):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {"stage": "1-7", "items": [{"item_id": "30012", "limit": 5}]}
            ],
            maa_stage_ratio_rules=[],
        ),
    )
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: ({"30012": 5}, 123)
    )
    instance = object.__new__(base.BaseSchedulerSolver)

    assert instance.apply_maa_stage_inventory_rules(["1-7"]) == []

    result = info(caplog, "当前没有待刷关卡")[0]
    assert result.getMessage() == "当前没有待刷关卡"
    assert result.log_event == {"type": "stage-inventory-plan", "stages": []}


def test_confirmed_workshop_delta_keeps_every_signed_change(
    workshop_game, inventory, caplog, monkeypatch
):
    instance, state, module = workshop_game
    state.remaining = 3
    instance.op_data.operators["蜜莓"].mood = 12
    before = inventory.get_inventory_counts()
    capture(caplog, monkeypatch)

    instance.generate_product("蜜莓")

    module.save_exception.assert_not_called()
    assert state.crafts == [("切削原液", 3)]
    (selected,) = info(caplog, "满足条件，开始加工")
    (batch,) = info(caplog, "本批最多")
    assert selected.getMessage() == "检测到切削原液满足条件，开始加工"
    assert batch.getMessage().startswith("[[operator:蜜莓]]加工切削原液：库存")
    assert batch.log_agents == ["蜜莓"]
    for record in (selected, batch):
        assert record.log_room == "factory"
        assert record.log_event == {
            "type": "workshop-material",
            "name": "切削原液",
            "item": "切削原液",
        }
    after = inventory.get_inventory_counts()
    records = info(caplog, "库存变化")
    assert len(records) == 1
    message = records[0].getMessage()
    assert "[[operator:蜜莓]]加工切削原液完成3次" in message
    assert "{" not in message
    for name in before.keys() | after.keys():
        change = after.get(name, 0) - before.get(name, 0)
        if change:
            assert f"{name}{change:+d}" in message
    assert records[0].log_room == "factory"
    assert records[0].log_agents == ["蜜莓"]
    assert records[0].log_event == {
        "type": "workshop-result",
        "product": {"name": "切削原液", "item": "切削原液"},
        "changes": [
            {"name": "化合切削液", "delta": -3},
            {"name": "晶体元件", "delta": -3},
            {"name": "RMA70-12", "delta": -3},
            {"name": "切削原液", "delta": 3},
            {"name": "龙门币", "delta": -900},
        ],
    }


def test_product_target_planning_does_not_preannounce_the_actual_switch(
    pending_return, caplog, monkeypatch
):
    instance, product, returning, changes = pending_return
    instance.op_data.update_facility_state("room_1_2", "manufacture", "exp3")
    original_plan = deepcopy(returning.plan)
    deadline = returning.time
    observations = []
    switch = instance.switch_base_products

    def observe_switch(*args, **kwargs):
        assert not info(caplog, "正在切换")
        observations.append(instance.op_data.facility_product("room_1_2"))
        assert instance.op_data.facility_product("room_1_2") == "exp3"
        return switch(*args, **kwargs)

    instance.switch_base_products = observe_switch
    capture(caplog, monkeypatch)

    instance._switch_products_before_arrangement(returning)

    assert observations == ["exp3"]
    assert changes == [("product", "room_1_2", "gold")]
    assert returning.plan == original_plan and returning.time == deadline
    assert product not in instance.tasks


@pytest.mark.parametrize("target", ["lmd", "orundum"])
def test_trade_target_planning_does_not_preannounce_the_actual_switch(
    caplog, monkeypatch, target
):
    capture(caplog, monkeypatch)
    room = "room_2_1"
    current = "orundum" if target == "lmd" else "lmd"
    projected = {room: [SimpleNamespace(facility="贸易站")]}
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        products={room: current},
        facility_states={room: {"facility": "trade", "product": current}},
    )
    instance.tasks = []
    instance._product_switching_enabled = MagicMock(return_value=True)
    instance._products_after_arrangement = MagicMock(
        side_effect=[({room: current}, projected), ({room: target}, projected)]
    )

    def switch(tasks, **kwargs):
        assert len(tasks) == 1
        assert tasks[0].meta_data == f"{room},{target}"
        assert kwargs == {"before_arrangement": True}
        instance.op_data.facility_states[room]["product"] = target

    instance.switch_base_products = MagicMock(side_effect=switch)
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={room: ["砾", "Current", "Free"]},
    )
    original, deadline = deepcopy(task.plan), task.time

    instance._switch_products_before_arrangement(task)

    instance.switch_base_products.assert_called_once()
    assert task.plan == original and task.time == deadline
    assert not info(caplog, "正在切换")


def test_long_wait_log_keeps_the_existing_independent_return_and_deadline(
    long_cycle, caplog, monkeypatch
):
    instance, task = long_cycle
    deadline = task.time
    actual_positions = {
        name: (operator.current_room, operator.current_index)
        for name, operator in instance.op_data.operators.items()
    }
    capture(caplog, monkeypatch)

    long_wait.defer(instance, task, 16)

    early = task.product_wait_return_task
    assert instance.tasks == [task, early]
    assert task.time == deadline
    records = info(caplog, "已生成可先执行的任务")
    assert len(records) == 1
    assert_plan(records[0], early.plan)
    assert str(early.time) in records[0].getMessage()
    assert {
        name: (operator.current_room, operator.current_index)
        for name, operator in instance.op_data.operators.items()
    } == actual_positions


def test_group_confirmation_keeps_multiple_directions_and_single_member_identity(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    state = {"深海": False, "独立": True}
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = SimpleNamespace(
        operators={},
        group_is_resting=state.get,
        commit_group_shifts=state.update,
        shift_group_members=lambda group: (
            ["歌蕾蒂娅", "幽灵鲨"] if group == "深海" else ["令"]
        ),
    )
    instance._queue_ordinary_coordination_admission = MagicMock()
    instance._resume_waiting_group_shifts = MagicMock()
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.group_shift_transitions = {"深海": True, "独立": False}
    task.group_shift_expected = {}
    instance.tasks = [task]

    assert instance._complete_group_shift(task)

    assert state == {"深海": True, "独立": False}
    records = info(caplog, "绑组换班确认完成")
    assert len(records) == 1
    assert records[0].getMessage() == (
        "绑组换班确认完成：深海下班；[[operator:令]]上班"
    )
    assert records[0].log_agents == ["令"]
    assert "休息" not in records[0].getMessage()


@pytest.mark.parametrize("candidates", [[], ["砾", "清流"]])
def test_fia_fallback_log_is_a_candidate_list_without_selecting_an_extra_target(
    caplog, monkeypatch, candidates
):
    capture(caplog, monkeypatch)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.check_fia = MagicMock(return_value=(["令"], "dormitory_1"))
    instance._refresh_fia_candidate_moods = MagicMock()
    instance._fia_targets_all_full = MagicMock(return_value=True)
    instance._emergency_fia_fallback = MagicMock(return_value=candidates)
    instance.task = None
    instance.tasks = []

    instance.plan_fia()

    assert instance.tasks == []
    records = info(caplog, "按心情选择正常主班")
    assert len(records) == 1
    assert records[0].log_agents == candidates
    assert (
        records[0]
        .getMessage()
        .endswith(
            "、".join(f"[[operator:{name}]]" for name in candidates) or "暂无候选"
        )
    )


def test_unanchored_drone_estimate_keeps_deadline_without_orphan_progress(
    caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(config, "conf", config.Conf())
    instance = object.__new__(base.BaseSchedulerSolver)
    observed_at = datetime(2026, 11, 5, 12)
    observed = [
        {
            "current_remaining": 200,
            "production_rate": 2.0,
            "current_product": "gold",
            "observed_at": observed_at,
        }
    ]
    original = deepcopy(observed)

    deadline = instance._estimate_product_switch_ready_at(observed, 0)

    seconds = (deadline - observed_at).total_seconds()
    assert 0 < seconds <= 100
    assert observed == original
    assert not info(caplog, "无人机足够")
    assert not info(caplog, "无人机数量不足")
    assert any(
        record.levelno == logging.DEBUG and "[2.0]" in record.getMessage()
        for record in caplog.records
    )
