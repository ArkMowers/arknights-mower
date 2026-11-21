"""副表名称快照按完整名称传输，异常数据保留日志原文。"""

import logging
from queue import Queue

import pytest

from arknights_mower.utils import log


def make_record(backups):
    record = logging.LogRecord(
        log.logger.name,
        logging.INFO,
        __file__,
        12,
        "已激活的副表：深海下班；已停用的副表：深海提前下班",
        (),
        None,
    )
    record.asctime = "2026-11-05 00:12:26"
    record.log_backups = backups
    return record


def test_backup_names_are_detached_before_the_async_consumer():
    original = [
        {"name": "深海下班", "active": True},
        {"name": "深海提前下班", "active": False},
    ]
    record = make_record(original)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    original[0]["name"] = "后续改名"
    original.append({"name": "其他副表", "active": True})

    result = log._build_log_record(prepared, prepared.getMessage())

    assert result["backups"] == [
        {"name": "深海下班", "active": True},
        {"name": "深海提前下班", "active": False},
    ]
    assert result["msg"] == record.getMessage()


@pytest.mark.parametrize(
    "backups",
    [
        None,
        [],
        {},
        [{"name": "", "active": True}],
        [{"name": "深海下班", "active": "true"}],
        [{"name": "长" * 129, "active": True}],
        [{"name": "深海下班", "active": True}] * 129,
    ],
)
def test_invalid_backup_metadata_keeps_the_complete_text(backups):
    record = make_record(backups)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    assert "log_backups" not in prepared.__dict__
    assert "backups" not in log._build_log_record(prepared, prepared.getMessage())
    assert prepared.getMessage() == record.getMessage()


def test_backup_names_share_the_existing_task_and_message_budget():
    record = make_record([{"name": "深海下班", "active": True}])
    record.msg = "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 100)
    record.log_task = {"header": "任" * 70}
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    result = log._build_log_record(prepared, prepared.getMessage())
    assert result["task"] == record.log_task
    assert "backups" not in result
    assert result["msg"] == record.getMessage()
