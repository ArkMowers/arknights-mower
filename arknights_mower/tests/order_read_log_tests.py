"""订单读取摘要由实际读屏驱动；本轮关联不改变刷新责任。"""

from copy import deepcopy
from datetime import timedelta

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as existing
from arknights_mower.tests.raw_schedule_log_tests import capture
from arknights_mower.utils import log

staffed_order = existing.staffed_order


def records(caplog):
    return [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "order-read"
    ]


@pytest.fixture
def reading(staffed_order, caplog, monkeypatch):
    ui = staffed_order
    ui.occupants.update({"room_1_1": ["孑"], "room_2_2": ["图耶"]})
    ui.states.update({"room_1_1": "active", "room_2_2": "active"})
    for room in ui.states:
        ui.solver.get_agent_from_room(room)
        ui.solver.op_data.update_facility_state(room, "trade", "lmd")
    ui.solver.tasks = []
    ui.solver.task = None
    ui.solver._cache_facility_state_from_current_page.return_value = None
    ui.events.clear()
    capture(caplog, monkeypatch)
    return ui


def queue(ui):
    ui.solver._refresh_orders_after_product_switch()
    return {
        task.meta_data: task
        for task in ui.solver.tasks
        if task.type == ui.task_type.REFRESH_TIME
    }


def statuses(record):
    return {item["room"]: item["status"] for item in record.log_event["rooms"]}


def test_queue_does_not_preannounce_and_real_reads_finish_only_after_both_rooms(
    reading, caplog
):
    ui = reading
    refreshes = queue(ui)
    original_times = {room: task.time for room, task in refreshes.items()}
    assert records(caplog) == [] and ui.events == []
    read_time = ui.solver.read_time.side_effect
    observed_phases = []

    def read(*args, **kwargs):
        observed_phases.append(
            [record.log_event["phase"] for record in records(caplog)]
        )
        return read_time(*args, **kwargs)

    ui.solver.read_time.side_effect = read
    ui.solver._read_pending_order_times("room_1_1")

    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "completed",
    ]
    assert observed_phases == [["started"], ["started", "updated"]]
    assert (
        logs[0].getMessage()
        == "产物切换和驻员安排已完成，正在读取贸易站 B101、贸易站 B202 的订单倒计时"
    )
    assert len({record.log_event["id"] for record in logs}) == 1
    assert statuses(logs[1]) == {"room_1_1": "read", "room_2_2": "pending"}
    assert statuses(logs[-1]) == {"room_1_1": "read", "room_2_2": "read"}
    assert all(
        task not in ui.solver.tasks and task.time == original_times[room]
        for room, task in refreshes.items()
    )
    assert [event[1] for event in ui.events if event[0] == "read"] == [
        "room_1_1",
        "room_2_2",
    ]
    assert ui.solver._order_read_log_cohorts == {}
    assert not hasattr(ui.solver, "_active_order_read_log")
    assert not hasattr(ui.solver, "_order_read_log_request")
    assert statuses(logs[0]) == {"room_1_1": "pending", "room_2_2": "pending"}


def test_ordinary_same_room_read_cannot_consume_the_queued_switch_cohort(
    reading, caplog
):
    ui = reading
    refreshes = queue(ui)
    cohort = next(iter(ui.solver._order_read_log_cohorts.values()))
    original = deepcopy(cohort["rooms"])

    ui.solver.get_run_order_time("room_1_1")

    ordinary = records(caplog)
    assert [record.log_event["phase"] for record in ordinary] == [
        "started",
        "completed",
    ]
    assert all(record.log_event["after_switch"] is False for record in ordinary)
    assert ordinary[0].getMessage() == "正在读取贸易站 B101 的订单倒计时"
    assert cohort["rooms"] == original and cohort["id"] is None
    assert all(task in ui.solver.tasks for task in refreshes.values())

    ui.solver.plan_run_order("room_1_1")

    marked = records(caplog)[2:]
    assert [record.log_event["phase"] for record in marked] == ["started", "updated"]
    assert all(record.log_event["after_switch"] for record in marked)
    assert marked[0].log_event["id"] != ordinary[0].log_event["id"]


def test_second_room_pause_is_confirmed_separately_from_a_numeric_countdown(
    reading, caplog
):
    ui = reading
    queue(ui)
    ui.states["room_2_2"] = "paused"

    ui.solver._read_pending_order_times("room_1_1")

    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "completed",
    ]
    assert statuses(logs[-1]) == {"room_1_1": "read", "room_2_2": "paused"}
    assert (
        logs[-1].getMessage()
        == "已读取贸易站 B101 的订单倒计时；贸易站 B202 的订单暂停获取"
    )
    assert not any(
        task.type == ui.task_type.RUN_ORDER and task.meta_data == "room_2_2"
        for task in ui.solver.tasks
    )


@pytest.mark.parametrize("interrupted", [False, True])
def test_second_room_failure_retains_its_original_refresh_and_does_not_complete_the_batch(
    reading, caplog, interrupted
):
    ui = reading
    refreshes = queue(ui)
    original_time = refreshes["room_2_2"].time
    read_time = ui.solver.read_time.side_effect

    def read(*args, **kwargs):
        if ui.solver._page["room"] == "room_2_2":
            if interrupted:
                raise ui.base.MowerExit()
            return None
        return read_time(*args, **kwargs)

    ui.solver.read_time.side_effect = read
    if interrupted:
        with pytest.raises(ui.base.MowerExit):
            ui.solver._read_pending_order_times("room_1_1")
    else:
        ui.solver._read_pending_order_times("room_1_1")

    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "failed",
    ]
    assert statuses(logs[-1]) == {"room_1_1": "read", "room_2_2": "pending"}
    failure = logs[-1]
    assert failure.getMessage().startswith(
        "已读取贸易站 B101 的订单倒计时；贸易站 B202 的订单倒计时读取未完成："
    )
    assert (
        log._display_snapshots(failure, failure.getMessage())["event"]
        == failure.log_event
    )
    if interrupted:
        assert failure.log_event["detail"] == "操作已中断"
    assert refreshes["room_2_2"] in ui.solver.tasks
    assert refreshes["room_2_2"].time == original_time
    assert not any(
        task.type == ui.task_type.RUN_ORDER and task.meta_data == "room_2_2"
        for task in ui.solver.tasks
    )


def test_existing_restoration_is_excluded_from_the_new_read_cohort(reading, caplog):
    ui = reading
    restoring = ui.task(
        time=ui.clock.now() + timedelta(hours=3),
        task_type=ui.task_type.RUN_ORDER,
        meta_data="room_2_2",
    )
    restoring.run_order_original_roster = {"room_2_2": ["图耶"]}
    restoring.run_order_restore_pending = True
    ui.solver.tasks.append(restoring)
    original_time = restoring.time

    refreshes = queue(ui)

    assert list(refreshes) == ["room_1_1"]
    assert records(caplog) == []
    ui.solver._read_pending_order_times("room_1_1")
    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == ["started", "completed"]
    assert [item["room"] for item in logs[0].log_event["rooms"]] == ["room_1_1"]
    assert restoring in ui.solver.tasks and restoring.time == original_time


def test_skipped_second_room_closes_the_partial_attempt_without_changing_refresh(
    reading, caplog
):
    ui = reading
    refreshes = queue(ui)
    ui.solver.plan_run_order("room_1_1")
    restoring = ui.task(
        time=ui.clock.now() + timedelta(hours=3),
        task_type=ui.task_type.RUN_ORDER,
        meta_data="room_2_2",
    )
    restoring.run_order_original_roster = {"room_2_2": ["图耶"]}
    restoring.run_order_restore_pending = True
    ui.solver.tasks.append(restoring)
    original_time = refreshes["room_2_2"].time
    before_reads = ui.solver.read_time.call_count

    ui.solver._read_pending_order_times("room_2_2")

    assert ui.solver.read_time.call_count == before_reads
    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "failed",
    ]
    assert (
        refreshes["room_2_2"] in ui.solver.tasks
        and refreshes["room_2_2"].time == original_time
    )
    assert restoring in ui.solver.tasks


def test_anchor_precedes_cache_detail_and_freezes_the_cohort_labels(reading, caplog):
    ui = reading
    queue(ui)
    seen = []

    def cache(room, facility, *, defer_log=False):
        assert defer_log
        seen.append(room)
        if room == "room_1_1":
            ui.solver.op_data.update_facility_state(room, "trade", "lmd")
        else:
            ui.solver.op_data.facility_states[room]["facility"] = "manufacture"
        return "龙门商法", f"读取{room}的订单类型"

    ui.solver.op_data.update_facility_state("room_2_2", "trade", "lmd")
    ui.solver._cache_facility_state_from_current_page.side_effect = cache
    ui.solver.plan_run_order("room_1_1")
    initial = deepcopy(records(caplog)[0].log_event["rooms"])
    ui.solver.plan_run_order("room_2_2")
    logs = records(caplog)
    assert seen == ["room_1_1", "room_2_2"]
    assert [(item["room"], item["label"]) for item in logs[-1].log_event["rooms"]] == [
        (item["room"], item["label"]) for item in initial
    ]
    messages = [record.getMessage() for record in caplog.records]
    assert messages.index(logs[0].getMessage()) < messages.index(
        "读取room_1_1的订单类型"
    )
    parent = {"type": "order-read", "id": logs[0].log_event["id"]}
    assert all(record.log_parent == parent for record in logs)
    for record in caplog.records:
        if record.getMessage() in {f"读取{room}的订单类型" for room in seen}:
            assert record.log_parent == parent
    log.logger.info("继续调度")
    assert not hasattr(caplog.records[-1], "log_parent")


def test_invalidating_an_unread_refresh_retires_only_its_display_attempt(
    reading, caplog
):
    ui = reading
    refreshes = queue(ui)
    ui.solver.plan_run_order("room_1_1")
    original_time = refreshes["room_2_2"].time
    before_reads = ui.solver.read_time.call_count

    ui.solver._invalidate_order_estimates({"room_2_2"})

    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "failed",
    ]
    assert (
        logs[-1].getMessage()
        == "已读取贸易站 B101 的订单倒计时；贸易站 B202 的订单倒计时读取未完成"
    )
    assert ui.solver._order_read_log_cohorts == {}
    assert (
        all(task is not refreshes["room_2_2"] for task in ui.solver.tasks)
        and refreshes["room_2_2"].time == original_time
    )
    assert ui.solver.read_time.call_count == before_reads


def test_cohort_capacity_closes_old_display_progress_without_consuming_tasks(
    reading, caplog
):
    ui = reading
    refreshes = queue(ui)
    ui.solver.plan_run_order("room_1_1")
    old_id = records(caplog)[0].log_event["id"]
    original_time = refreshes["room_2_2"].time
    for _ in range(32):
        refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_1_1")
        ui.solver.tasks.append(refresh)
        ui.solver._remember_order_read_log_cohort({"room_1_1": refresh})
    assert len(ui.solver._order_read_log_cohorts) == 32
    logs = records(caplog)
    assert [record.log_event["phase"] for record in logs] == [
        "started",
        "updated",
        "failed",
    ]
    assert logs[-1].log_event["id"] == old_id
    assert (
        refreshes["room_2_2"] in ui.solver.tasks
        and refreshes["room_2_2"].time == original_time
    )
