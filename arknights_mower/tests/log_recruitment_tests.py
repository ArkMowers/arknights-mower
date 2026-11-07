"""公招标签随实时日志传输，独立快照且共用已有长度预算。"""

import json
import logging
from copy import deepcopy
from queue import Queue

import pytest

from arknights_mower.utils import log


def record_with(recruitment=None, message="1号招募位：识别标签：治疗、费用回复"):
    record = logging.LogRecord(
        log.logger.name,
        logging.INFO,
        "/project/arknights_mower/solvers/recruit.py",
        12,
        message,
        (),
        None,
    )
    record.asctime = "2026-11-04 19:30:00"
    if recruitment is not None:
        record.log_recruitment = recruitment
    return record


@pytest.mark.parametrize(
    ("event", "rarity"), [("tags", None), ("start", 4), ("rare", 6)]
)
def test_queue_snapshots_recruitment_before_the_producer_mutates_it(event, rarity):
    queue = Queue()
    handler = log.LiveQueueHandler(queue)
    source = logging.getLogger(f"arknights_mower.tests.recruitment_snapshot.{event}")
    old_handlers, old_level, old_propagate = (
        source.handlers,
        source.level,
        source.propagate,
    )
    source.handlers = [handler]
    source.setLevel(logging.INFO)
    source.propagate = False
    metadata = {"event": event, "tags": ["治疗", "费用回复"], "rarity": rarity}
    original = {"event": event, "tags": ["治疗", "费用回复"], "rarity": rarity}
    message = "1号招募位：识别标签：治疗、费用回复"
    try:
        source.info(message, extra={"log_recruitment": metadata})
        metadata["tags"][0] = "修改后的标签"
        metadata["tags"].append("额外标签")
        metadata["event"] = "rare"
        metadata["rarity"] = 1
        queued = queue.get_nowait()
        queued.asctime = "2026-11-04 19:30:00"
        delivered = log._build_log_record(queued, queued.getMessage())
    finally:
        source.handlers, source.level, source.propagate = (
            old_handlers,
            old_level,
            old_propagate,
        )
        handler.close()

    assert queued.log_recruitment == original
    assert delivered["recruitment"] == original
    assert delivered["msg"] == message
    assert delivered["level"] == "INFO"


@pytest.mark.parametrize(
    "metadata",
    [
        "治疗",
        [],
        {},
        {"event": "other", "tags": ["治疗"], "rarity": None},
        {"event": "tags", "tags": [], "rarity": None},
        {"event": "tags", "tags": ["治疗"] * 6, "rarity": None},
        {"event": "tags", "tags": "治疗", "rarity": None},
        {"event": "tags", "tags": [None], "rarity": None},
        {"event": "tags", "tags": [""], "rarity": None},
        {"event": "tags", "tags": ["  "], "rarity": None},
        {"event": "tags", "tags": ["标" * 33], "rarity": None},
        {"event": "start", "tags": ["治疗"], "rarity": 0},
        {"event": "start", "tags": ["治疗"], "rarity": 7},
        {"event": "start", "tags": ["治疗"], "rarity": True},
        {"event": "start", "tags": ["治疗"], "rarity": 4.0},
        {"event": "start", "tags": ["治疗"], "rarity": "4"},
    ],
)
def test_invalid_recruitment_uses_unchanged_text_fallback(metadata):
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()
    assert record.log_recruitment is metadata


def test_recruitment_has_a_bounded_shape_and_keeps_valid_boundary_tags():
    metadata = {
        "event": "rare",
        "tags": ["标" * 32] * 5,
        "rarity": 6,
        "discarded": "过量的额外字段" * log.LIVE_LOG_MESSAGE_LIMIT,
    }
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    delivered = log._build_log_record(prepared, prepared.getMessage())

    assert delivered["recruitment"] == {
        "event": "rare",
        "tags": ["标" * 32] * 5,
        "rarity": 6,
    }
    assert len(json.dumps(delivered["recruitment"], ensure_ascii=False)) < 1024
    assert "discarded" not in prepared.log_recruitment
    assert "discarded" in record.log_recruitment


def test_recruitment_shares_the_message_budget_without_truncating_tags():
    metadata = {"event": "tags", "tags": ["治疗"], "rarity": None}
    record = record_with(metadata, "文" * log.LIVE_LOG_MESSAGE_LIMIT)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()


def test_task_and_recruitment_cannot_each_consume_the_same_remaining_budget():
    metadata = {"event": "start", "tags": ["治疗"], "rarity": 4}
    record = record_with(metadata, "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 100))
    record.log_task = {"header": "任" * 60}
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert prepared.log_task == record.log_task
    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert delivered["task"] == record.log_task
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()


def test_archive_notice_is_counted_when_building_the_final_record():
    metadata = {"event": "tags", "tags": ["治疗"], "rarity": None}
    record = record_with(metadata, "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 100))
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert prepared.log_recruitment == metadata

    delivered = log._build_log_record(prepared, prepared.getMessage(), "归" * 100)

    assert "recruitment" not in delivered
    assert delivered["msg"] == record.getMessage() + "归" * 100


def test_plain_records_omit_recruitment():
    record = record_with()
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    assert "recruitment" not in log._build_log_record(prepared, prepared.getMessage())


def test_queue_detaches_every_rare_combination_and_omits_unknown_fields():
    metadata = {
        "event": "rare",
        "rarity": 5,
        "combinations": [
            {"tags": ["先锋干员", "支援"], "rarity": 5},
            {"tags": ["治疗", "费用回复"], "rarity": 4},
        ],
    }
    original = deepcopy(metadata)
    metadata["discarded"] = "额外内容" * log.LIVE_LOG_MESSAGE_LIMIT
    metadata["combinations"][0]["discarded"] = metadata["discarded"]
    record = record_with(
        metadata, "1号招募位：发现稀有标签：先锋干员、支援；治疗、费用回复"
    )
    queue = Queue()
    handler = log.LiveQueueHandler(queue)

    handler.handle(record)
    metadata["combinations"][0]["tags"][0] = "修改后的标签"
    metadata["combinations"][1]["tags"].append("额外标签")
    metadata["combinations"][0]["rarity"] = 1
    metadata["combinations"].pop()
    prepared = queue.get_nowait()
    handler.close()
    delivered = log._build_log_record(prepared, prepared.getMessage())

    assert prepared.log_recruitment == original
    assert delivered["recruitment"] == original
    assert delivered["msg"] == record.getMessage()
    assert "tags" not in delivered["recruitment"]


@pytest.mark.parametrize(
    "combination",
    [
        None,
        {},
        {"tags": [], "rarity": 5},
        {"tags": "先锋干员", "rarity": 5},
        {"tags": ["先锋干员"] * 4, "rarity": 5},
        {"tags": ["标" * 33], "rarity": 5},
        {"tags": [None], "rarity": 5},
        {"tags": ["  "], "rarity": 5},
        {"tags": ["先锋干员"], "rarity": None},
        {"tags": ["先锋干员"], "rarity": True},
        {"tags": ["先锋干员"], "rarity": 5.0},
        {"tags": ["先锋干员"], "rarity": "5"},
        {"tags": ["先锋干员"], "rarity": 0},
        {"tags": ["先锋干员"], "rarity": 7},
    ],
)
def test_invalid_rare_combination_falls_back_as_one_complete_text_record(combination):
    metadata = {"event": "rare", "rarity": 5, "combinations": [combination]}
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()


@pytest.mark.parametrize(
    "metadata",
    [
        {"event": "rare", "rarity": 5, "combinations": []},
        {"event": "rare", "rarity": 5, "combinations": {}},
        {"event": "rare", "rarity": 5, "combinations": "先锋干员、支援"},
        {
            "event": "rare",
            "rarity": 5,
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}] * 26,
        },
        {
            "event": "start",
            "rarity": 5,
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}],
        },
        {
            "event": "tags",
            "rarity": None,
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}],
        },
        {
            "event": "rare",
            "rarity": None,
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}],
        },
        {
            "event": "rare",
            "rarity": 5,
            "tags": ["先锋干员"],
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}],
        },
        {
            "event": "rare",
            "rarity": 5,
            "tags": None,
            "combinations": [{"tags": ["先锋干员"], "rarity": 5}],
        },
    ],
)
def test_invalid_or_mixed_combination_shapes_do_not_override_text(metadata):
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()


def test_all_twenty_five_combinations_fit_without_dropping_tags():
    metadata = {
        "event": "rare",
        "rarity": 6,
        "combinations": [{"tags": ["标" * 32] * 3, "rarity": 6} for _ in range(25)],
    }
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    delivered = log._build_log_record(prepared, prepared.getMessage())

    assert delivered["recruitment"] == metadata
    assert 1024 < len(json.dumps(metadata, ensure_ascii=False)) <= 4096


def test_encoded_combinations_over_4096_characters_fall_back_without_partial_data():
    metadata = {
        "event": "rare",
        "rarity": 6,
        "combinations": [{"tags": ['"' * 32] * 3, "rarity": 6} for _ in range(25)],
    }
    record = record_with(metadata)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()


def test_rare_combinations_share_the_remaining_budget_with_task_and_text():
    metadata = {
        "event": "rare",
        "rarity": 5,
        "combinations": [
            {"tags": ["先锋干员", "支援"], "rarity": 5},
            {"tags": ["治疗", "费用回复"], "rarity": 4},
        ],
    }
    record = record_with(metadata, "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 500))
    assert log.LiveQueueHandler(Queue()).prepare(record).log_recruitment == metadata
    record.log_task = {"header": "任" * 400}
    prepared = log.LiveQueueHandler(Queue()).prepare(record)

    assert prepared.log_task == record.log_task
    assert "log_recruitment" not in prepared.__dict__
    for source in (record, prepared):
        delivered = log._build_log_record(source, source.getMessage())
        assert delivered["task"] == record.log_task
        assert "recruitment" not in delivered
        assert delivered["msg"] == record.getMessage()
