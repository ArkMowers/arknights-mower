"""订单读取事件逐房校验结果，沿用日志预算与深拷贝边界。"""

import json
from copy import deepcopy
from queue import Queue

import pytest

from arknights_mower.tests.log_display_payload_tests import record_with
from arknights_mower.utils import log
from arknights_mower.utils.log_stream import LogStream


def event_for(phase="started"):
    statuses = {
        "started": ["pending", "pending"],
        "updated": ["read", "pending"],
        "completed": ["read", "paused"],
        "failed": ["read", "pending"],
    }[phase]
    return {
        "type": "order-read",
        "id": "read-cohort",
        "phase": phase,
        "anchor": phase == "started",
        "after_switch": True,
        "rooms": [
            {"room": room, "label": label, "status": status}
            for room, label, status in zip(
                ["room_1_1", "room_2_1"], ["贸易站 B101", "贸易站 B201"], statuses
            )
        ],
    }


@pytest.mark.parametrize("phase", ["started", "updated", "completed", "failed"])
def test_order_read_metadata_is_snapshotted_through_queue_and_history(phase):
    event = event_for(phase)
    if phase == "failed":
        event["detail"] = "操作已中断"
    expected = deepcopy(event)
    record = record_with("完整订单读取原文", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event["rooms"][0]["label"] = "后改名称"
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == expected and delivered["msg"] == "完整订单读取原文"
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"]["rooms"].clear()
    assert (
        json.loads(stream.subscribe().messages.get_nowait())["records"][0]["event"]
        == expected
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", ""),
        ("id", "i" * 129),
        ("phase", []),
        ("phase", "paused"),
        ("anchor", 1),
        ("anchor", False),
        ("after_switch", None),
        ("after_switch", 1),
        ("rooms", []),
        ("rooms", [None]),
        ("rooms", [event_for()["rooms"][0]] * 33),
        ("rooms", event_for()["rooms"] * 2),
        ("detail", "not failed"),
    ],
)
def test_invalid_order_read_event_falls_back_to_source_text(key, value):
    event = event_for()
    event[key] = value
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


@pytest.mark.parametrize(
    "key,value",
    [
        ("room", []),
        ("room", "r" * 129),
        ("label", ""),
        ("label", "l" * 129),
        ("status", None),
        ("status", []),
        ("status", "success"),
    ],
)
def test_invalid_room_result_is_rejected(key, value):
    event = event_for()
    event["rooms"][0][key] = value
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


@pytest.mark.parametrize("phase", ["started", "updated", "completed"])
def test_phase_cannot_claim_a_result_that_disagrees_with_pending_rooms(phase):
    event = event_for(phase)
    for item in event["rooms"]:
        item["status"] = "pending" if phase == "completed" else "read"
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


@pytest.mark.parametrize("detail", [None, "", [], "x" * 2049])
def test_failed_reason_has_a_bound_and_empty_is_omitted_instead(detail):
    event = event_for("failed")
    event["detail"] = detail
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


def test_order_read_uses_the_shared_message_and_metadata_budget():
    event = event_for()
    message = "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 1)
    assert "event" not in log._display_snapshots(record_with(log_event=event), message)
    assert "event" not in log._display_snapshots(
        record_with(log_event=event),
        "原文",
        {"task": "文" * log.LIVE_LOG_MESSAGE_LIMIT},
    )
