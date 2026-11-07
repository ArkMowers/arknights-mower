"""运行入口和邮件故障日志不包含设备、配置目录或邮件凭据。"""

import logging
import smtplib
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower import __main__ as main
from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.utils import email, log, path
from arknights_mower.utils.device.application import DeviceControl


@pytest.fixture
def captured_log(monkeypatch, caplog):
    monkeypatch.setattr(log.logger, "handlers", [caplog.handler])
    monkeypatch.setattr(log.logger, "propagate", False)
    caplog.set_level(logging.DEBUG, logger=log.logger.name)
    return caplog


@pytest.mark.parametrize("serial", ["192.0.2.41:16416", "USB-PRIVATE-726154"])
def test_device_initialization_keeps_identity_out_of_logs(captured_log, serial):
    control = DeviceControl(lambda: SimpleNamespace(adb=serial), ManualAdapter())
    try:
        result = control.start()
        assert result.ok and result.serial == serial
        assert "设备初始化完成" in captured_log.text
        assert serial not in captured_log.text
    finally:
        control.close()


def test_startup_keeps_configuration_directory_out_of_logs(monkeypatch, captured_log):
    location = r"C:\Users\private-synthetic-user\private-instance-726154"
    stopped = Event()
    stopped.set()
    monkeypatch.setattr(path, "global_space", location)
    monkeypatch.setattr(main.config, "stop_mower", stopped)

    assert main.simulate(None) is None
    assert "配置空间" in captured_log.text
    assert location not in captured_log.text
    assert "private-synthetic-user" not in captured_log.text
    assert "private-instance-726154" not in captured_log.text


@pytest.mark.parametrize("failure_kind", ["recipient", "authentication", "network"])
def test_mail_failures_keep_safe_type_and_code_without_exception_payload(
    monkeypatch, captured_log, failure_kind
):
    sender = "private-sender-726154@example.invalid"
    recipient = "private-recipient-726154@example.invalid"
    password = "synthetic-mail-password-726154"
    conf = SimpleNamespace(
        mail_enable=True,
        notification_level="INFO",
        mail_subject="",
        account=sender,
        pass_code=password,
        recipient=[recipient],
        custom_smtp_server=SimpleNamespace(enable=False),
    )
    failures = {
        "recipient": smtplib.SMTPRecipientsRefused(
            {recipient: (550, f"unknown recipient {recipient}".encode())}
        ),
        "authentication": smtplib.SMTPAuthenticationError(
            535, f"credentials {sender} {password}".encode()
        ),
        "network": OSError(111, f"cannot reach {sender} using {password}"),
    }
    failure = failures[failure_kind]
    send = Mock(side_effect=failure)
    monkeypatch.setattr(email.config, "conf", conf)
    monkeypatch.setattr(email.Email, "send", send)
    monkeypatch.setattr(email, "sleep", Mock())
    monkeypatch.setattr(
        email,
        "Thread",
        lambda *, target, args: SimpleNamespace(start=lambda: target(*args)),
    )

    email.send_message("普通通知", subject="离线测试")

    assert send.call_count == 3
    assert type(failure).__name__ in captured_log.text
    for value in (sender, recipient, password):
        assert value not in captured_log.text
    assert all(record.exc_info is None for record in captured_log.records)
    if failure_kind == "recipient":
        assert "550" in captured_log.text
    elif failure_kind == "authentication":
        assert "535" in captured_log.text
    elif failure_kind == "network":
        assert "111" in captured_log.text
