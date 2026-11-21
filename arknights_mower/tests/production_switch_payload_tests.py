"""生产切换事件沿既有日志通道校验、快照并共享长度预算。"""

import json
from copy import deepcopy
from queue import Queue

import pytest

from arknights_mower.tests.log_display_payload_tests import record_with
from arknights_mower.utils import log
from arknights_mower.utils.log_stream import LogStream


def event_for(phase="started"):
    return {
        "type": "production-switch",
        "id": "one-operation",
        "room": "room_1_2",
        "label": "制造站 B102",
        "facility": "manufacture",
        "product": "赤金",
        "previous": "中级作战记录",
        "phase": phase,
        "anchor": phase == "started",
        **(
            {
                "detail": "无人机数量不足，当前生产效率为 200%，预计 26 秒后可满足加速计划"
            }
            if phase == "waiting"
            else {}
        ),
    }


@pytest.mark.parametrize("phase", ["started", "waiting", "completed", "failed"])
def test_production_event_is_snapshotted_through_queue_and_history(phase):
    event = event_for(phase)
    if phase == "failed":
        event["detail"] = "产物切换校验失败"
    expected = deepcopy(event)
    record = record_with("原始切换日志", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event.clear()
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == expected and delivered["msg"] == "原始切换日志"
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"].clear()
    assert (
        json.loads(stream.subscribe().messages.get_nowait())["records"][0]["event"]
        == expected
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", ""),
        ("id", "i" * 129),
        ("room", []),
        ("room", "r" * 129),
        ("label", None),
        ("label", "l" * 129),
        ("product", ""),
        ("product", "p" * 257),
        ("previous", None),
        ("previous", ""),
        ("previous", "p" * 257),
        ("facility", "power"),
        ("facility", {}),
        ("phase", []),
        ("phase", "success"),
        ("anchor", 1),
        ("anchor", False),
        ("detail", "waiting outside waiting phase"),
    ],
)
def test_invalid_production_event_preserves_only_the_source_text(key, value):
    event = event_for()
    event[key] = value
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


@pytest.mark.parametrize("detail", [None, "", [], "d" * 2049])
def test_waiting_detail_is_required_and_bounded(detail):
    event = event_for("waiting")
    event["detail"] = detail
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


def test_optional_previous_and_shared_payload_budget():
    event = event_for("waiting")
    event.pop("previous")
    assert (
        log._display_snapshots(record_with(log_event=event), "原文")["event"] == event
    )
    message = "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 1)
    assert "event" not in log._display_snapshots(record_with(log_event=event), message)
