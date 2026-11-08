"""库存清单与明确重设事件保留正文、独立快照和实时载荷预算。"""

import json
import logging
from copy import deepcopy
from queue import Queue

import pytest

from arknights_mower.utils import log
from arknights_mower.utils.log_stream import LogStream


def record_with(message="仓库扫描：已识别2种物品\n龙门币：0\n固源岩：2", **extra):
    record = logging.LogRecord(
        log.logger.name,
        logging.INFO,
        "/project/arknights_mower/solvers/depotREC.py",
        12,
        message,
        (),
        None,
    )
    record.asctime = "2026-11-05 11:06:30,123"
    record.__dict__.update(extra)
    return record


def test_manufacturing_observation_retains_both_records_in_one_history_entry():
    stream = LogStream(history_limit=1)
    start = {
        "type": "facility-observation",
        "id": "manufacture-read",
        "room": "room_1_2",
        "label": "制造站 B102",
        "phase": "started",
        "anchor": True,
        "summary": "制造站 B102：产物为中级作战记录，正在读取心情",
        "agents": [],
    }
    end = {
        **start,
        "phase": "completed",
        "anchor": False,
        "summary": "制造站 B102：产物为中级作战记录，[[operator:酒神]]（心情23.381）",
        "agents": ["酒神"],
    }
    for event in (start, end):
        source = record_with(event["summary"], log_event=deepcopy(event))
        prepared = log.LiveQueueHandler(Queue()).prepare(source)
        source.log_event["agents"].append("芬")
        stream.publish(log._build_log_record(prepared, prepared.message))

    snapshot = json.loads(stream.subscribe().messages.get_nowait())
    assert [record["event"] for record in snapshot["records"]] == [start, end]
    assert snapshot["data"].splitlines() == [
        f"2026-11-05 11:06:30,123 INFO {event['summary']}" for event in (start, end)
    ]

    mismatched = record_with(end["summary"], log_event={**end, "summary": "心情完成"})
    fallback = log._build_log_record(mismatched, mismatched.getMessage())
    assert fallback["msg"] == end["summary"]
    assert "event" not in fallback


def test_mood_calculation_retains_progress_and_result_in_one_history_entry():
    stream = LogStream(history_limit=1)
    summaries = [
        ("started", "基建调度：正在根据已有读数推算干员的心情变化"),
        ("updated", "基建调度：已开始计算干员何时恢复到目标心情"),
        ("completed", "基建调度：心情计算用时 8.754 秒"),
    ]
    events = [
        {
            "type": "mood-calculation",
            "id": "mood-batch",
            "label": "基建调度",
            "phase": phase,
            "anchor": phase == "started",
            "summary": summary,
        }
        for phase, summary in summaries
    ]
    handler = log.LiveQueueHandler(Queue())
    for event in events:
        prepared = handler.prepare(record_with(event["summary"], log_event=event))
        stream.publish(log._build_log_record(prepared, prepared.message))

    snapshot = json.loads(stream.subscribe().messages.get_nowait())
    assert [record["event"] for record in snapshot["records"]] == events
    assert snapshot["data"].splitlines() == [
        f"2026-11-05 11:06:30,123 INFO {summary}" for _, summary in summaries
    ]

    invalid_event = {**events[-1], "phase": "waiting"}
    fallback = log._build_log_record(
        record_with(invalid_event["summary"], log_event=invalid_event),
        invalid_event["summary"],
    )
    assert fallback["msg"] == invalid_event["summary"]
    assert "event" not in fallback


def test_mood_calculation_replays_plain_stages_with_the_same_operation(monkeypatch):
    queue = Queue()
    monkeypatch.setattr(log.logger, "handlers", [log.LiveQueueHandler(queue)])
    monkeypatch.setattr(log.logger, "disabled", False)
    stream = LogStream(history_limit=2)
    subscription = stream.subscribe()
    initial = json.loads(subscription.messages.get_nowait())
    parent = {"type": "mood-calculation", "id": "mood-batch"}
    start = {
        **parent,
        "label": "基建调度",
        "phase": "started",
        "anchor": True,
        "summary": "基建调度：正在计算心情",
    }
    finish = {
        **start,
        "phase": "completed",
        "anchor": False,
        "summary": "基建调度：心情计算用时 8.754 秒",
    }
    stage_one, unrelated, stage_two = (
        "正在根据已有读数推算干员的心情变化",
        "已收取贸易站订单",
        "正在计算干员恢复到目标心情的时间",
    )
    log.logger.info(start["summary"], extra={"log_event": start})
    with log.log_parent_context(parent):
        log.logger.info(stage_one)
    log.logger.info(unrelated)
    with log.log_parent_context(parent):
        log.logger.info(stage_two)
    log.logger.info(finish["summary"], extra={"log_event": finish})

    live = []
    messages = [start["summary"], stage_one, unrelated, stage_two, finish["summary"]]
    for seq, message in enumerate(messages, start=1):
        prepared = queue.get_nowait()
        prepared.asctime = "2026-11-05 11:06:30,123"
        stream.publish(log._build_log_record(prepared, prepared.getMessage()))
        frame = json.loads(subscription.messages.get_nowait())
        assert frame["stream_id"] == initial["stream_id"]
        assert frame["snapshot"] is False
        assert frame["evicted"] == []
        (record,) = frame["records"]
        assert (record["seq"], record["level"], record["msg"]) == (seq, "INFO", message)
        live.append(record)

    assert [record.get("event") for record in live] == [start, None, None, None, finish]
    assert [record.get("parent") for record in live] == [
        None,
        parent,
        None,
        parent,
        None,
    ]
    history = json.loads(stream.subscribe().messages.get_nowait())
    assert history["snapshot"] is True
    assert history["records"] == live
    assert history["data"].splitlines() == [
        f"2026-11-05 11:06:30,123 INFO {message}" for message in messages
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "depot-scan",
        "facility-observation",
        "mood-calculation",
        "production-switch",
        "order-read",
    ],
)
def test_operation_log_parent_preserves_identity_and_source(kind, monkeypatch):
    queue = Queue()
    monkeypatch.setattr(log.logger, "handlers", [log.LiveQueueHandler(queue)])
    monkeypatch.setattr(log.logger, "disabled", False)
    scope = {"type": kind, "id": "operation", "room": "discarded"}
    with log.log_parent_context(scope):
        scope["id"] = "mutated"
        log.logger.info("已进入仓库")
    log.logger.info("后续日志")

    scoped, following = queue.get_nowait(), queue.get_nowait()
    scoped.asctime = following.asctime = "2026-11-05 11:06:30,123"
    published = log._build_log_record(scoped, scoped.getMessage())
    assert published["parent"] == {"type": kind, "id": "operation"}
    assert published["msg"] == "已进入仓库"
    assert "parent" not in log._build_log_record(following, following.getMessage())


@pytest.mark.parametrize(
    "phase,summary",
    [
        ("started", "仓库扫描正在同步森空岛库存"),
        ("updated", "仓库扫描正在识别基础物品"),
        ("completed", "仓库扫描完成"),
        ("failed", "仓库扫描未能确认物品数量"),
        ("stopped", "仓库扫描已停止"),
    ],
)
def test_depot_scan_event_preserves_original_source_and_snapshot(phase, summary):
    stream = LogStream()
    event = {
        "type": "depot-scan",
        "id": "depot-attempt",
        "phase": phase,
        "anchor": phase == "started",
        "summary": summary,
    }
    source = record_with(summary, log_event={**event, "room": "discarded"})
    prepared = log.LiveQueueHandler(Queue()).prepare(source)
    source.log_event["summary"] = "已改动的事件正文"
    stream.publish(log._build_log_record(prepared, prepared.message))
    snapshot = json.loads(stream.subscribe().messages.get_nowait())
    assert snapshot["records"][0]["event"] == event
    assert snapshot["data"] == f"2026-11-05 11:06:30,123 INFO {summary}"


@pytest.mark.parametrize(
    "change",
    [
        {"id": " "},
        {"id": "a" * 129},
        {"phase": "waiting"},
        {"anchor": False},
        {"anchor": 1},
        {"summary": "与正文不符"},
        {"summary": "仓库扫描\n正在同步森空岛库存"},
        {"summary": "物" * 1025},
    ],
)
def test_invalid_depot_scan_event_preserves_source_text(change):
    summary = "仓库扫描正在同步森空岛库存"
    message = (
        summary
        if change.get("summary") == "与正文不符"
        else change.get("summary", summary)
    )
    source = record_with(
        message,
        log_event={
            "type": "depot-scan",
            "id": "depot-attempt",
            "phase": "started",
            "anchor": True,
            "summary": summary,
            **change,
        },
    )
    prepared = log.LiveQueueHandler(Queue()).prepare(source)
    published = log._build_log_record(prepared, prepared.message)
    assert published["msg"] == message
    assert "event" not in published


def test_inventory_is_snapshotted_before_enqueue_and_history_keeps_the_original():
    inventory = {
        "items": [{"name": "龙门币", "count": 0}, {"name": "固源岩", "count": 2}]
    }
    original = deepcopy(inventory)
    record = record_with(log_inventory=inventory)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    inventory["items"][0]["count"] = 999
    inventory["items"].reverse()
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["inventory"] == original
    assert delivered["msg"] == record.getMessage()
    assert delivered["level"] == "INFO"
    stream = LogStream()
    stream.publish(delivered)
    delivered["inventory"]["items"][0]["count"] = 100
    history = json.loads(stream.subscribe().messages.get_nowait())
    assert history["records"][0]["inventory"] == original


def test_reset_event_is_explicit_and_its_source_message_and_agents_are_unchanged():
    event = {"type": "operator-reset-idle"}
    record = record_with(
        "重设 [[operator:砾]] 至空闲",
        log_event=event,
        log_agents=["砾"],
        log_room="dormitory_1",
    )
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event["type"] = "changed"
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == {"type": "operator-reset-idle"}
    assert delivered["agents"] == ["砾"]
    assert delivered["room"] == "dormitory_1"
    assert delivered["msg"] == record.getMessage()


def test_facility_idle_keeps_its_attempt_and_snapshot_through_log_delivery():
    parent = {
        "type": "facility-arrangement",
        "id": "arrangement-1",
        "room": "dormitory_1",
    }
    event = {
        "type": "facility-idle",
        "id": parent["id"],
        "room": parent["room"],
        "agents": ["砾"],
    }
    record = record_with(
        "已确认 [[operator:砾]] 转为空闲", log_event=event, log_parent=parent
    )
    original_parent, original_event = deepcopy(parent), deepcopy(event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    parent["id"] = "changed"
    event["agents"].append("夜莺")
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    stream = LogStream()
    stream.publish(delivered)
    delivered["parent"]["room"] = "dormitory_2"
    delivered["event"]["agents"].append("芬")
    (retained,) = json.loads(stream.subscribe().messages.get_nowait())["records"]
    assert retained["parent"] == original_parent
    assert retained["event"] == original_event
    assert retained["msg"] == record.getMessage()


@pytest.mark.parametrize("phase", [None, "started", "completed", "failed", "stopped"])
def test_recruitment_slot_event_and_parent_keep_their_original_scope(phase):
    scope = {"type": "recruitment-slot", "id": "recruit-2", "slot": 2}
    event = {**scope, "phase": phase} if phase is not None else scope
    record = record_with(
        "2号招募位：准备领取干员",
        log_event={**event, "extra": True},
        log_parent={**scope, "extra": True},
    )
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    record.log_event["id"] = "changed"
    record.log_parent["slot"] = 3
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    stream = LogStream()
    stream.publish(delivered)
    delivered["parent"]["slot"] = 4
    delivered["event"]["id"] = "changed again"

    (retained,) = json.loads(stream.subscribe().messages.get_nowait())["records"]
    assert retained["parent"] == scope
    assert retained["event"] == event
    assert retained["msg"] == record.getMessage()


@pytest.mark.parametrize(
    ("slot", "identifier"),
    [
        (0, "scope"),
        (5, "scope"),
        (True, "scope"),
        ("2", "scope"),
        (2, " "),
        (2, "x" * 129),
    ],
)
def test_recruitment_slot_discards_invalid_metadata_without_losing_source(
    slot, identifier
):
    scope = {"type": "recruitment-slot", "id": identifier, "slot": slot}
    record = record_with("2号招募位：准备领取干员", log_event=scope, log_parent=scope)

    delivered = log._build_log_record(record, record.getMessage())

    assert delivered["msg"] == record.getMessage()
    assert "event" not in delivered
    assert "parent" not in delivered


@pytest.mark.parametrize("phase", [None, "", "queued", True])
def test_recruitment_slot_rejects_unknown_phase_without_losing_scope(phase):
    scope = {"type": "recruitment-slot", "id": "recruit-2", "slot": 2}
    record = record_with(
        "2号招募位：检查完成",
        log_event={**scope, "phase": phase},
        log_parent=scope,
    )

    delivered = log._build_log_record(record, record.getMessage())

    assert delivered["msg"] == record.getMessage()
    assert delivered["parent"] == scope
    assert "event" not in delivered


@pytest.mark.parametrize("matches", [True, False])
def test_facility_summary_preserves_the_original_action_only(matches):
    message = "正在 贸易站 B101 安排 [[operator:但书]] 跑单"
    event = {
        "type": "facility-arrangement",
        "id": "run-order",
        "phase": "started",
        "anchor": True,
        "room": "room_1_1",
        "label": "贸易站 B101",
        "agents": ["但书"],
        "summary": message if matches else "其他操作",
    }
    record = record_with(message, log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["msg"] == message
    assert delivered["event"]["id"] == event["id"]
    assert delivered["event"].get("summary") == (message if matches else None)


@pytest.mark.parametrize("agents", [[], ["Current"], ["砾", "砾"], ["砾"] * 6])
def test_facility_idle_discards_invalid_agents_but_keeps_original_message(agents):
    event = {
        "type": "facility-idle",
        "id": "attempt",
        "room": "dormitory_1",
        "agents": agents,
    }
    message = "已确认 [[operator:砾]] 转为空闲"
    delivered = log._build_log_record(record_with(message, log_event=event), message)
    assert "event" not in delivered
    assert delivered["msg"] == message


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "workshop-result",
            "changes": [
                {"name": "切削原液", "delta": 3},
                {"name": "龙门币", "delta": -900},
            ],
        },
        {
            "type": "facility-arrangement",
            "id": "a" * 32,
            "phase": "started",
            "room": "dormitory_1",
            "label": "宿舍1",
            "agents": ["杜林", "红"],
        },
        {
            "type": "facility-arrangement",
            "id": "training",
            "phase": "started",
            "room": "train",
            "label": "训练室",
            "agents": ["夜莺"],
            "positions": [{"agent": "夜莺", "index": 0}],
        },
        {"type": "training-selection", "positions": [{"agent": "夜莺", "index": 1}]},
        {
            "type": "stage-inventory-limit",
            "stage": {"code": "1-7", "drops": ["固源岩"]},
        },
        {"type": "operation-drops", "items": [{"name": "采购凭证", "count": 3}]},
        {
            "type": "base-report",
            "date": "2026-11-05",
            "items": [
                {"name": "赤金制造价值", "value": 0, "unit": "龙门币", "item": "赤金"},
                {"name": "龙门币订单数", "value": None, "unit": "笔", "item": "龙门币"},
            ],
        },
    ],
)
def test_display_events_survive_queue_and_history_as_snapshots(event):
    original = deepcopy(event)
    record = record_with("完整正文", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event.clear()
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == original
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"].clear()
    history = json.loads(stream.subscribe().messages.get_nowait())
    assert history["records"][0]["event"] == original
    assert history["records"][0]["msg"] == "完整正文"


@pytest.mark.parametrize(
    "phase,anchor",
    [("started", True), ("updated", False), ("completed", False), ("failed", False)],
)
def test_facility_anchor_survives_queue_and_history_as_a_snapshot(phase, anchor):
    event = {
        "type": "facility-arrangement",
        "id": "actual-room-entry",
        "phase": phase,
        "anchor": anchor,
        "room": "meeting",
        "label": "会客室",
        "agents": ["陈"],
    }
    test_display_events_survive_queue_and_history_as_snapshots(event)


def test_facility_update_keeps_training_positions_as_a_snapshot():
    event = {
        "type": "facility-arrangement",
        "id": "training",
        "phase": "updated",
        "anchor": False,
        "room": "train",
        "label": "训练室",
        "agents": ["夜莺", "闪灵"],
        "positions": [{"agent": "夜莺", "index": 0}, {"agent": "闪灵", "index": 1}],
    }
    test_display_events_survive_queue_and_history_as_snapshots(event)


def test_facility_update_without_anchor_falls_back_to_original_text():
    record = record_with(
        "原始设施记录",
        log_event={
            "type": "facility-arrangement",
            "id": "actual-room-entry",
            "phase": "updated",
            "room": "recycle",
            "label": "回收站",
            "agents": ["行铃", "旅骨"],
        },
    )
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_event" not in prepared.__dict__
    assert "event" not in log._build_log_record(record, record.getMessage())
    assert prepared.getMessage() == "原始设施记录"


@pytest.mark.parametrize(
    "phase,anchor",
    [
        ("started", None),
        ("started", 1),
        ("started", "true"),
        ("started", []),
        ("started", False),
        ("updated", True),
        ("updated", None),
        ("updated", 0),
        ("completed", True),
        ("failed", True),
    ],
)
def test_invalid_facility_anchor_falls_back_to_original_text(phase, anchor):
    record = record_with(
        "原始设施记录",
        log_event={
            "type": "facility-arrangement",
            "id": "actual-room-entry",
            "phase": phase,
            "anchor": anchor,
            "room": "meeting",
            "label": "会客室",
            "agents": ["陈"],
        },
    )
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_event" not in prepared.__dict__
    assert "event" not in log._build_log_record(record, record.getMessage())
    assert prepared.getMessage() == "原始设施记录"


@pytest.mark.parametrize(
    "change",
    [
        {"name": "固源岩", "delta": True},
        {"name": "固源岩", "delta": 0},
        {"name": "固源岩", "delta": 1.5},
        {"name": "固源岩", "delta": 9_007_199_254_740_992},
        {"name": "", "delta": 1},
    ],
)
def test_invalid_workshop_changes_fall_back_to_original_text(change):
    record = record_with(
        "原始加工结果", log_event={"type": "workshop-result", "changes": [change]}
    )
    assert "event" not in log._build_log_record(record, record.getMessage())


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", ""),
        ("id", "x" * 129),
        ("phase", "unknown"),
        ("room", []),
        ("label", ""),
        ("agents", ["红"] * 6),
    ],
)
def test_invalid_facility_event_preserves_original_text(field, value):
    event = {
        "type": "facility-arrangement",
        "id": "a" * 32,
        "phase": "started",
        "room": "dormitory_1",
        "label": "宿舍1",
        "agents": ["红"],
    }
    event[field] = value
    record = record_with("原始安排", log_event=event)
    assert "event" not in log._build_log_record(record, record.getMessage())


@pytest.mark.parametrize(
    "event",
    [
        {"type": "training-selection", "positions": [{"agent": "夜莺", "index": True}]},
        {
            "type": "training-selection",
            "positions": [{"agent": "夜莺", "index": 0}, {"agent": "红", "index": 0}],
        },
        {"type": "training-selection", "positions": [{"agent": "夜莺", "index": 2}]},
        {
            "type": "stage-inventory-limit",
            "stage": {"code": "1-7", "drops": ["固源岩"] * 65},
        },
        {"type": "operation-drops", "items": [{"name": "固源岩", "count": True}]},
        {"type": "operation-drops", "items": [{"name": "固源岩", "count": 0}]},
        {
            "type": "base-report",
            "date": "2026-11-05",
            "items": [{"name": "赤金", "unit": "个", "item": "赤金"}],
        },
        {
            "type": "base-report",
            "date": "2026-11-05",
            "items": [{"name": "赤金", "value": -1, "unit": "个", "item": "赤金"}],
        },
        {
            "type": "base-report",
            "date": "2026-11-05",
            "items": [{"name": "赤金", "value": True, "unit": "个", "item": "赤金"}],
        },
    ],
)
def test_invalid_display_events_keep_the_source_without_raising(event):
    record = record_with("完整原文", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_event" not in prepared.__dict__
    delivered = log._build_log_record(record, record.getMessage())
    assert "event" not in delivered
    assert delivered["msg"] == "完整原文"


def test_oversized_display_event_does_not_trim_individual_report_fields():
    record = record_with(
        "完整基报",
        log_event={
            "type": "base-report",
            "date": "2026-11-05",
            "items": [
                {"name": "名" * 256, "value": 1, "unit": "个", "item": "物" * 256}
            ]
            * 64,
        },
    )
    delivered = log._build_log_record(record, record.getMessage())
    assert "event" not in delivered
    assert delivered["msg"] == "完整基报"


@pytest.mark.parametrize(
    "inventory",
    [
        [],
        {},
        {"items": []},
        {"items": "固源岩"},
        {"items": [{"name": "", "count": 1}]},
        {"items": [{"name": "固源岩", "count": True}]},
        {"items": [{"name": "固源岩", "count": -1}]},
        {"items": [{"name": "固源岩", "count": 1.5}]},
        {"items": [{"name": "固源岩", "count": "3"}]},
        {"items": [{"name": "固源岩", "count": 9_007_199_254_740_992}]},
        {"items": [{"name": "物" * 257, "count": 1}]},
        {"items": [{"name": "固源岩", "count": 1}] * 513},
    ],
)
def test_invalid_inventory_falls_back_to_the_unchanged_source(inventory):
    record = record_with(log_inventory=inventory)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_inventory" not in prepared.__dict__
    delivered = log._build_log_record(record, record.getMessage())
    assert "inventory" not in delivered
    assert delivered["msg"] == record.getMessage()


@pytest.mark.parametrize("event", [None, [], {}, {"type": []}, {"type": "unknown"}])
def test_unknown_events_do_not_authorize_grouping(event):
    record = record_with("普通消息", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_event" not in prepared.__dict__
    assert "event" not in log._build_log_record(record, record.getMessage())


def test_inventory_and_event_share_the_existing_total_budget_with_other_fields():
    message = "文" * 200
    task = {"header": "计" * (log.LIVE_LOG_MESSAGE_LIMIT - 300)}
    inventory = {"items": [{"name": "固源岩", "count": 1}] * 8}
    record = record_with(
        message,
        log_task=task,
        log_inventory=inventory,
        log_event={"type": "operator-reset-idle"},
    )
    delivered = log._build_log_record(record, message)
    assert delivered["task"] == task
    assert "inventory" not in delivered
    size = len(message) + sum(
        len(json.dumps(delivered[key], ensure_ascii=False, separators=(",", ":")))
        for key in ("task", "inventory", "event")
        if key in delivered
    )
    assert size <= log.LIVE_LOG_MESSAGE_LIMIT
    assert delivered["msg"] == message
