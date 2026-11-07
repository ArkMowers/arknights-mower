"""运行入口的启动记录不冒充基建业务，具体业务仍可显式指定分组。"""

import logging
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower import __main__ as main
from arknights_mower.utils import config, log, recycling_report


def test_startup_records_have_no_base_group_before_device_preparation(
    monkeypatch, caplog
):
    stopped = Event()
    stopped.set()
    monkeypatch.setattr(config, "stop_mower", stopped)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", ())
    monkeypatch.setattr(main.NewsChecker, "get_effective_maintenance", lambda: None)
    monkeypatch.setattr(recycling_report, "start_recycling_reports", Mock())
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
    initialize = Mock()
    monkeypatch.setattr(main, "initialize", initialize)
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.INFO, logger=log.logger.name)

    assert main._main({}) is None

    records = [r for r in caplog.records if r.pathname == main.__file__]
    assert [r.getMessage() for r in records] == [
        "开始运行Mower",
        f"正在使用全局配置空间: {main.path.global_space}",
    ]
    for record in records:
        logging.Formatter("%(asctime)s").format(record)
        assert "group" not in log._build_log_record(record, record.getMessage())
    initialize.assert_not_called()


@pytest.mark.parametrize("threshold", [False, True])
def test_scheduled_base_threshold_keeps_its_specific_business_group(
    monkeypatch, caplog, threshold
):
    now = datetime(2026, 11, 5, 12)
    info = SimpleNamespace(
        start=now + timedelta(hours=2),
        update_type="major" if threshold else "minor",
        announcement_id="offline-maintenance",
        manual=False,
    )
    timer = Mock()
    monkeypatch.setattr(main, "Timer", timer)
    monkeypatch.setattr(main, "_maintenance_timer", None)
    monkeypatch.setattr(main, "_maintenance_timer_key", None)
    monkeypatch.setattr(config.conf, "version_update_threshold_advance_hours", 1)
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.INFO, logger=log.logger.name)

    main._arm_maintenance_timer(info, now=now)

    timer.assert_called_once()
    assert timer.call_args.args[0] == (3600 if threshold else 7200)
    timer.return_value.start.assert_called_once_with()
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert (
        "启用版本维护心情阈值" if threshold else "响应服务器维护"
    ) in record.getMessage()
    logging.Formatter("%(asctime)s").format(record)
    assert log._build_log_record(record, record.getMessage()).get("group") == (
        "base-scheduler" if threshold else None
    )
