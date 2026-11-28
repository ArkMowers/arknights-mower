"""救急任务与设施明细沿实时日志保留显式归属及原始正文。"""

import asyncio
import json
from copy import deepcopy
from queue import Queue
from threading import Thread

import pytest

from arknights_mower.tests.log_display_payload_tests import record_with
from arknights_mower.utils import log
from arknights_mower.utils.log_stream import LogStream


def staffing_event(phase="queued"):
    return {
        "type": "rescue-staffing",
        "id": "task-one",
        "phase": phase,
        "anchor": phase == "queued",
        "rooms": [
            {
                "room": "room_1_1",
                "label": "贸易站 B101",
                "agents": ["Current", "陈", ""],
                "status": "completed" if phase == "completed" else "pending",
            }
        ],
    }


def parent_scope(task="task-one"):
    return {
        "type": "rescue-staffing",
        "id": task,
        "room": "room_1_1",
        "attempt": "facility-one",
    }


@pytest.mark.parametrize("phase", ["queued", "started", "completed", "failed"])
def test_task_and_parent_snapshots_survive_queue_delivery_and_history(phase):
    event = staffing_event(phase)
    if phase == "failed":
        event["detail"] = "进驻确认未完成"
    parent = parent_scope()
    expected_event, expected_parent = deepcopy(event), dict(parent)
    record = record_with("原始日志", log_event=event, log_parent=parent)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event["rooms"][0]["agents"].reverse()
    parent["id"] = "later-task"
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["msg"] == "原始日志"
    assert delivered["event"] == expected_event
    assert delivered["parent"] == expected_parent
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"]["rooms"].clear()
    delivered["parent"]["id"] = "another-task"
    history = json.loads(stream.subscribe().messages.get_nowait())["records"][0]
    assert history["event"] == expected_event
    assert history["parent"] == expected_parent


@pytest.mark.parametrize(
    "change",
    [
        {"id": ""},
        {"id": "i" * 129},
        {"phase": "waiting"},
        {"anchor": 1},
        {"anchor": False},
        {"rooms": []},
        {"rooms": [None]},
        {"rooms": [staffing_event()["rooms"][0]] * 2},
        {"detail": "不能把失败原因附到排队事件"},
    ],
)
def test_invalid_task_metadata_keeps_plain_source(change):
    event = {**staffing_event(), **change}
    result = log._build_log_record(record_with("原文", log_event=event), "原文")
    assert "event" not in result and result["msg"] == "原文"


@pytest.mark.parametrize(
    "change",
    [
        {"room": " "},
        {"label": "l" * 129},
        {"agents": ["陈"] * 6},
        {"agents": [None]},
        {"agents": ["a" * 257]},
        {"status": "skipped"},
    ],
)
def test_invalid_room_metadata_does_not_trim_the_original_plan(change):
    event = staffing_event()
    event["rooms"][0].update(change)
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


def test_completion_requires_every_room_confirmed_and_bounds_remain_explicit():
    event = staffing_event("completed")
    event["rooms"][0]["status"] = "unconfirmed"
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")
    event = staffing_event()
    event["rooms"] = [
        {**event["rooms"][0], "room": f"room-{index}"} for index in range(33)
    ]
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")
    event = staffing_event("failed")
    event["detail"] = "错" * 2049
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


@pytest.mark.parametrize(
    "parent",
    [
        {"type": "rescue-staffing", "id": "task-one", "room": "room_1_1"},
        {"type": "rescue-staffing", "id": "task-one", "attempt": "facility-one"},
        {**parent_scope(), "attempt": ""},
        {**parent_scope(), "room": "r" * 129},
        {**parent_scope(), "id": []},
        {**parent_scope(), "type": "other-operation"},
    ],
)
def test_invalid_parent_never_attaches_an_ordinary_record(parent):
    assert "parent" not in log._display_snapshots(
        record_with(log_parent=parent), "原文"
    )


def test_root_parent_and_event_share_the_complete_live_budget():
    event = staffing_event()
    parent = {"type": "rescue-staffing", "id": "task-one", "unknown": "discard"}
    kept = {"type": "rescue-staffing", "id": "task-one"}
    size = len(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    parent_size = len(json.dumps(kept, ensure_ascii=False, separators=(",", ":")))
    source = "文" * (log.LIVE_LOG_MESSAGE_LIMIT - size - parent_size)
    record = record_with(log_event=event, log_parent=parent)
    assert log._display_snapshots(record, source) == {"event": event, "parent": kept}
    assert log._display_snapshots(record, source + "文") == {"event": event}


def test_parent_context_is_captured_at_source_and_restored_after_failure(monkeypatch):
    queue = Queue()
    monkeypatch.setattr(log.logger, "handlers", [log.LiveQueueHandler(queue)])
    monkeypatch.setattr(log.logger, "disabled", False)
    outer = parent_scope()
    with log.log_parent_context(outer):
        log.logger.info("outer-first")
        outer["id"] = "mutated-input"
        with pytest.raises(RuntimeError):
            with log.log_parent_context(parent_scope("inner-task")):
                log.logger.info("inner")
                raise RuntimeError("interrupt")
        log.logger.info("outer-restored")
        worker = Thread(target=lambda: log.logger.info("different-thread"))
        worker.start()
        worker.join(timeout=2)
        assert not worker.is_alive()
        log.logger.info("explicit", extra={"log_parent": parent_scope("explicit-task")})
        log.logger.info("parent-event", extra={"log_parent": None})
    log.logger.info("outside")
    records = {record.getMessage(): record for record in list(queue.queue)}
    assert records["outer-first"].log_parent == parent_scope()
    assert records["outer-restored"].log_parent == parent_scope()
    assert records["inner"].log_parent == parent_scope("inner-task")
    assert records["explicit"].log_parent == parent_scope("explicit-task")
    assert not hasattr(records["different-thread"], "log_parent")
    assert not hasattr(records["parent-event"], "log_parent")
    assert not hasattr(records["outside"], "log_parent")


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_outer_context_is_released_for_errors_and_cancellation(monkeypatch, error):
    queue = Queue()
    monkeypatch.setattr(log.logger, "handlers", [log.LiveQueueHandler(queue)])
    monkeypatch.setattr(log.logger, "disabled", False)
    with pytest.raises(error):
        with log.log_parent_context(parent_scope()):
            log.logger.info("before-cancellation")
            raise error()
    log.logger.info("after-cancellation")
    assert queue.get_nowait().log_parent == parent_scope()
    assert not hasattr(queue.get_nowait(), "log_parent")


def test_async_scopes_keep_each_tasks_owner_across_yields(monkeypatch):
    queue = Queue()
    monkeypatch.setattr(log.logger, "handlers", [log.LiveQueueHandler(queue)])
    monkeypatch.setattr(log.logger, "disabled", False)

    async def write(owner):
        with log.log_parent_context(parent_scope(owner)):
            log.logger.info(owner + "-before")
            await asyncio.sleep(0)
            log.logger.info(owner + "-after")

    async def run():
        await asyncio.gather(write("one"), write("two"))

    asyncio.run(run())
    records = list(queue.queue)
    assert len(records) == 4
    assert all(
        record.getMessage().startswith(record.log_parent["id"]) for record in records
    )
