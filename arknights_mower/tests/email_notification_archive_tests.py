"""Error notifications log; only explicit visual failures request archives."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import email, log


@pytest.fixture
def notification(monkeypatch):
    records = []
    store = MagicMock()
    store.mark_error.return_value = "notification-archive"
    live_log = MagicMock()
    monkeypatch.setattr(log, "get_screenshot_store", lambda: store)
    monkeypatch.setattr(log.config.log_queue, "put", live_log)
    transport = MagicMock()
    thread = MagicMock()
    monkeypatch.setattr(email, "Email", transport)
    monkeypatch.setattr(email, "Thread", thread)

    class ForwardToArchive(logging.Handler):
        def emit(self, record):
            records.append(record)
            log.filter.filter(record)
            log.basic_formatter.format(record)
            log.whlr.emit(record)

    logger = logging.Logger("notification-archive-test")
    logger.addHandler(ForwardToArchive())
    monkeypatch.setattr(email, "logger", logger)
    return SimpleNamespace(
        records=records,
        store=store,
        live_log=live_log,
        transport=transport,
        thread=thread,
    )


@pytest.mark.parametrize("mail_enable", [False, True])
@pytest.mark.parametrize("threshold", ["INFO", "WARNING", "ERROR"])
@pytest.mark.parametrize("visual", [False, True])
def test_error_notification_always_logs_and_only_visual_failure_archives(
    monkeypatch, notification, mail_enable, threshold, visual
):
    monkeypatch.setattr(
        email.config,
        "conf",
        SimpleNamespace(
            mail_enable=mail_enable, notification_level=threshold, mail_subject="通知："
        ),
    )
    email.send_message(
        "训练室面板与计划不符",
        subject="白面鸮",
        level="ERROR",
        archive_screenshots=visual,
    )
    if visual:
        notification.store.mark_error.assert_called_once()
        assert (
            "白面鸮：训练室面板与计划不符"
            in notification.store.mark_error.call_args.args[1]
        )
        assert (
            "记录编号 notification-archive" in notification.live_log.call_args.args[0]
        )
    else:
        notification.store.mark_error.assert_not_called()
        assert "记录编号" not in notification.live_log.call_args.args[0]
    assert len(notification.records) == 1
    record = notification.records[0]
    assert record.pathname.endswith("utils/email.py")
    assert record.archive_screenshots is visual
    assert "白面鸮：训练室面板与计划不符" in notification.live_log.call_args.args[0]
    if mail_enable:
        notification.transport.assert_called_once_with(
            "训练室面板与计划不符", "通知：白面鸮", None
        )
        notification.thread.return_value.start.assert_called_once()
    else:
        notification.transport.assert_not_called()
        notification.thread.assert_not_called()


@pytest.mark.parametrize("level", ["INFO", "WARNING"])
def test_ordinary_notification_does_not_request_an_error_archive(
    monkeypatch, notification, level
):
    monkeypatch.setattr(
        email.config,
        "conf",
        SimpleNamespace(mail_enable=True, notification_level="ERROR", mail_subject=""),
    )
    email.send_message("普通通知", level=level)
    notification.store.mark_error.assert_not_called()
    notification.transport.assert_not_called()
    notification.thread.assert_not_called()


def test_disabled_error_mail_needs_no_account_settings(monkeypatch, notification):
    monkeypatch.setattr(email.config, "conf", SimpleNamespace(mail_enable=False))
    email.send_message("无账号时的运行错误", level="ERROR")
    notification.store.mark_error.assert_not_called()
    assert len(notification.records) == 1
    notification.transport.assert_not_called()


def test_archive_request_precedes_mail_construction_failure(monkeypatch, notification):
    monkeypatch.setattr(
        email.config,
        "conf",
        SimpleNamespace(mail_enable=True, notification_level="ERROR", mail_subject=""),
    )
    notification.transport.side_effect = RuntimeError("mail construction failed")
    with pytest.raises(RuntimeError, match="mail construction failed"):
        email.send_message("故障现场", level="ERROR", archive_screenshots=True)
    notification.store.mark_error.assert_called_once()
    notification.thread.assert_not_called()
