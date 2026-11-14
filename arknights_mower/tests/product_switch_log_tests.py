"""生产切换原行状态只使用实际读取结果，不参与资源计划和调度。"""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import product_switch_batch_tests as existing
from arknights_mower.tests.raw_schedule_log_tests import capture
from arknights_mower.utils import log

batch = existing.batch
switches = existing.switches


def events(caplog):
    return [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "production-switch"
    ]


@pytest.fixture
def production(batch, caplog, monkeypatch):
    ui = batch
    ui.clock.current = ui.clock(2026, 10, 28, 12)
    capture(caplog, monkeypatch)
    ui.products = {"room_1_2": "exp3", "room_2_2": "exp3"}
    ui.entered = []
    ui.available = 3
    ui.idle = False
    ui.solver.op_data = SimpleNamespace(facility_states={}, plan={})

    def cache(room, facility, product):
        ui.solver.op_data.facility_states[room] = {
            "facility": facility,
            "product": product,
        }

    def enter(room):
        ui.current_room = room
        ui.entered.append(room)

    ui.solver.op_data.update_facility_state = cache
    ui.solver._open_manufacture_product_detail = MagicMock(side_effect=enter)
    ui.solver.read_manufacture_product = MagicMock(
        side_effect=lambda: ui.products[ui.current_room]
    )
    ui.solver._manufacture_is_idle = MagicMock(side_effect=lambda: ui.idle)
    ui.solver._read_manufacture_speed = MagicMock(return_value=2.0)
    ui.solver._read_manufacture_total_seconds = MagicMock(return_value=741)
    ui.solver._tap_drone_accelerate = MagicMock()
    ui.solver._tap_product_point = MagicMock()
    ui.solver.recog.gray = None
    ui.solver.recog.w = 1920
    ui.solver.recog.h = 1080
    ui.solver.digit_reader = SimpleNamespace(get_drone=lambda *args: ui.available)
    ui.solver._execute_manufacture_acceleration = MagicMock(return_value=0)
    ui.solver._select_manufacture_product = MagicMock(
        side_effect=lambda target, **kwargs: ui.products.__setitem__(
            ui.current_room, target
        )
    )
    return ui


def test_real_survey_wait_and_readback_share_one_operation_without_changing_task(
    production, caplog
):
    ui = production
    tasks = switches(ui, 1)
    task = tasks[0]
    original_time = task.time
    with pytest.raises(ui.base.ProductSwitchDeferred) as wait:
        ui.solver.switch_base_products(tasks)

    records = events(caplog)
    assert [record.log_event["phase"] for record in records] == ["started", "waiting"]
    assert records[0].getMessage() == "正在切换制造站 B102 的产物 中级作战记录 → 赤金"
    assert records[1].getMessage() == "等待切换制造站 B102 的产物"
    reason = "无人机数量不足，当前生产效率为 200%，预计 26 秒后可满足加速计划"
    assert records[1].log_event["detail"] == reason
    parent = {"type": "production-switch", "id": records[0].log_event["id"]}
    assert all(record.log_parent == parent for record in records)
    waiting_detail = [
        record for record in caplog.records if record.getMessage() == reason
    ]
    assert len(waiting_detail) == 1
    assert waiting_detail[0].log_parent == parent
    assert not hasattr(waiting_detail[0], "log_event")
    assert any(
        getattr(record, "log_parent", None) == parent
        and record.getMessage().startswith("B102计划")
        for record in caplog.records
    )
    assert any(
        not hasattr(record, "log_parent")
        and record.getMessage().startswith("制造站批量切产物计划")
        for record in caplog.records
    )
    assert records[0].log_event["anchor"] is True
    assert records[1].log_event["anchor"] is False
    assert records[0].log_event["label"] == "制造站 B102"
    assert ui.entered == ["room_1_2", "room_1_2"]
    assert wait.value.ready_at == ui.clock.now() + timedelta(seconds=26)
    assert ui.solver.tasks == tasks and task.time == original_time
    ui.solver._execute_manufacture_acceleration.assert_not_called()
    ui.solver._select_manufacture_product.assert_not_called()
    ui.solver.sleep.assert_not_called()
    snapshot = deepcopy(records[0].log_event)

    ui.clock.current = wait.value.ready_at
    ui.available = 100
    ui.idle = True
    ui.solver.switch_base_products(tasks)

    records = events(caplog)
    assert [record.log_event["phase"] for record in records] == [
        "started",
        "waiting",
        "started",
        "completed",
    ]
    assert len({record.log_event["id"] for record in records}) == 1
    assert all(record.log_parent == parent for record in records)
    assert "detail" not in records[-2].log_event
    assert "detail" not in records[-1].log_event
    assert ui.products["room_1_2"] == "gold"
    assert ui.solver.tasks == [] and task.time == original_time
    assert ui.solver._product_switch_log_states == {}
    assert records[0].log_event == snapshot
    assert not hasattr(ui.solver, "_active_product_switch_logs")


def test_shared_drone_budget_is_not_a_single_station_estimate(production, caplog):
    ui = production
    tasks = switches(ui, 2)
    with pytest.raises(ui.base.ProductSwitchDeferred) as wait:
        ui.solver.switch_base_products(tasks)
    waiting = [
        record for record in events(caplog) if record.log_event["phase"] == "waiting"
    ]
    assert len(waiting) == 2
    assert wait.value.ready_at > ui.clock.now() + timedelta(seconds=26)
    for record in waiting:
        assert "整批加速计划" in record.log_event["detail"]
        assert "当前生产效率" not in record.log_event["detail"]
    assert ui.solver.tasks == tasks
    ui.solver._execute_manufacture_acceleration.assert_not_called()


def test_failed_readback_does_not_publish_completion_and_retry_has_a_new_id(
    production, caplog
):
    ui = production
    ui.available = 100
    ui.idle = True
    tasks = switches(ui, 1)
    ui.solver._select_manufacture_product.side_effect = None
    with pytest.raises(ui.base.ProductSwitchFailed):
        ui.solver.switch_base_products(tasks)
    records = events(caplog)
    assert [record.log_event["phase"] for record in records] == ["started", "failed"]
    assert "校验失败" in records[-1].log_event["detail"]
    first_id = records[0].log_event["id"]
    assert ui.solver._product_switch_log_states == {}
    with pytest.raises(ui.base.ProductSwitchFailed):
        ui.solver.switch_base_products(tasks)
    assert events(caplog)[-2].log_event["id"] != first_id
    assert not any(
        record.log_event["phase"] == "completed" for record in events(caplog)
    )


def test_unknown_previous_is_omitted_and_display_state_is_bounded(production, caplog):
    ui = production
    tasks = switches(ui, 1)
    ui.solver.op_data.facility_states["room_1_2"] = {"facility": "manufacture"}
    for _ in range(40):
        task = ui.scheduling.SchedulerTask(
            task_type=tasks[0].type, meta_data=tasks[0].meta_data
        )
        ui.solver._active_product_switch_logs = ui.solver._product_switch_log_context(
            [task], False
        )
        ui.solver._start_product_switch_log("room_1_2", "gold")
    records = events(caplog)
    assert all("previous" not in record.log_event for record in records)
    assert records[-1].getMessage() == "正在将制造站 B102 的产物切换为赤金"
    assert "尚未确认" not in records[-1].getMessage()
    assert len(ui.solver._product_switch_log_states) == 32
    assert all(
        state["owner"] is not None
        for state in ui.solver._product_switch_log_states.values()
    )
    assert not any(record.log_event["phase"] == "completed" for record in records)
    retired = [record for record in records if record.log_event["phase"] == "failed"]
    assert len(retired) == 8
    assert all("detail" not in record.log_event for record in retired)
    assert tasks == ui.solver.tasks


@pytest.mark.parametrize("target,previous", [("orundum", "lmd"), ("lmd", "orundum")])
def test_actual_trade_readback_uses_order_type_and_its_strategy_names(
    production, caplog, target, previous
):
    ui = production
    room = "room_1_1"
    ui.products[room] = previous
    task = ui.scheduling.SchedulerTask(
        task_type=ui.scheduling.TaskTypes.SWITCH_PRODUCT, meta_data=f"{room},{target}"
    )
    ui.solver.tasks = [task]
    ui.solver._open_trade_product_detail = MagicMock(
        side_effect=lambda current: setattr(ui, "current_room", current)
    )
    ui.solver._read_trade_product_card = MagicMock(
        side_effect=lambda: (ui.products[room], True)
    )
    ui.solver._change_trade_product = (
        ui.base.BaseSchedulerSolver._change_trade_product.__get__(ui.solver)
    )
    ui.solver._wait_product_resource = MagicMock()
    ui.solver._close_trade_product_select = MagicMock()

    def tap(point):
        if point == ui.base.TRADE_PRODUCTS[target].option:
            ui.products[room] = target

    ui.solver._tap_product_point.side_effect = tap
    ui.solver.switch_base_products([task])

    records = events(caplog)
    assert [record.log_event["phase"] for record in records] == ["started", "completed"]
    before = ui.base.TRADE_PRODUCTS[previous].strategy_name
    after = ui.base.TRADE_PRODUCTS[target].strategy_name
    assert (
        records[0].getMessage() == f"正在切换贸易站 B101 的订单类型 {before} → {after}"
    )
    assert records[0].log_event["facility"] == "trade"
    assert records[-1].log_event["product"] == after
    assert ui.products[room] == target and ui.solver.tasks == []


def test_new_target_closes_the_previous_operation_without_completing_it(
    production, caplog
):
    ui = production
    tasks = switches(ui, 1)
    with pytest.raises(ui.base.ProductSwitchDeferred):
        ui.solver.switch_base_products(tasks)
    previous_id = events(caplog)[0].log_event["id"]
    tasks[0].meta_data = "room_1_2,orirock"
    with pytest.raises(ui.base.ProductSwitchDeferred):
        ui.solver.switch_base_products(tasks)
    records = events(caplog)
    closed = next(record for record in records if record.log_event["phase"] == "failed")
    assert closed.log_event["id"] == previous_id
    assert "切换目标已变更" in closed.getMessage()
    assert records[-1].log_event["id"] != previous_id
    assert not any(record.log_event["phase"] == "completed" for record in records)


@pytest.mark.parametrize("kind", ["mower", "keyboard"])
def test_empty_interruption_reason_still_closes_the_transmitted_parent(
    production, caplog, kind
):
    ui = production
    ui.available = 100
    ui.idle = True
    tasks = switches(ui, 1)
    error = ui.base.MowerExit() if kind == "mower" else KeyboardInterrupt()
    ui.solver._select_manufacture_product.side_effect = error
    with pytest.raises(type(error)):
        ui.solver.switch_base_products(tasks)
    records = events(caplog)
    assert [record.log_event["phase"] for record in records] == ["started", "failed"]
    failure = records[-1]
    assert failure.log_event["detail"] == "操作已中断"
    assert (
        log._display_snapshots(failure, failure.getMessage())["event"]
        == failure.log_event
    )
    assert ui.solver.tasks == tasks
    assert ui.solver._product_switch_log_states == {}


def test_disabled_switching_closes_display_progress_before_existing_queue_cleanup(
    production, caplog
):
    ui = production
    tasks = switches(ui, 1)
    with pytest.raises(ui.base.ProductSwitchDeferred):
        ui.solver.switch_base_products(tasks)
    initial_id = events(caplog)[0].log_event["id"]
    ui.config.conf.product_switching.enable = False
    ui.solver._discard_product_switches()
    records = events(caplog)
    assert records[-1].log_event["id"] == initial_id
    assert records[-1].log_event["phase"] == "failed"
    assert records[-1].log_event["detail"] == "产物切换已停用"
    assert ui.solver._product_switch_log_states == {}
    assert ui.solver.tasks == []
    assert not any(record.log_event["phase"] == "completed" for record in records)


def test_nested_context_is_restored_and_only_missing_previous_is_enriched(
    production, caplog
):
    ui = production
    tasks = switches(ui, 1)
    enclosing = {"outer": object()}
    ui.solver._active_product_switch_logs = enclosing
    with pytest.raises(ui.base.ProductSwitchDeferred):
        ui.solver.switch_base_products(tasks)
    assert ui.solver._active_product_switch_logs is enclosing
    context = ui.solver._product_switch_log_context(tasks, False)
    ui.solver._active_product_switch_logs = context
    state = context["room_1_2"]
    original_id = state["event"]["id"]
    ui.solver._start_product_switch_log("room_1_2", "gold", "orirock")
    assert state["event"]["previous"] == "中级作战记录"
    state["event"].pop("previous")
    ui.solver._start_product_switch_log("room_1_2", "gold", "exp3")
    assert state["event"]["previous"] == "中级作战记录"
    assert state["event"]["id"] == original_id
