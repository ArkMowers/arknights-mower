from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import email


@pytest.mark.parametrize("encryption", ["tls", "starttls"])
@pytest.mark.parametrize(
    ("configured", "explicit", "expected"),
    [
        ([], None, ["sender@example.invalid"]),
        ([""], None, ["sender@example.invalid"]),
        ([" ", "\t\r\n"], None, ["sender@example.invalid"]),
        (["first@example.invalid"], None, ["first@example.invalid"]),
        (
            ["", "first@example.invalid", " \t", "second@example.invalid"],
            None,
            ["first@example.invalid", "second@example.invalid"],
        ),
        (
            ["configured@example.invalid"],
            ["explicit@example.invalid"],
            ["explicit@example.invalid"],
        ),
        ([""], ["explicit@example.invalid"], ["explicit@example.invalid"]),
        (["configured@example.invalid"], [], ["configured@example.invalid"]),
    ],
)
def test_send_selects_recipients_without_changing_configuration(
    monkeypatch, encryption, configured, explicit, expected
):
    original = configured.copy()
    conf = SimpleNamespace(
        account="sender@example.invalid",
        pass_code="test-password",
        recipient=configured,
        custom_smtp_server=SimpleNamespace(
            enable=True,
            server="smtp.example.invalid",
            ssl_port=587 if encryption == "starttls" else 465,
            encryption=encryption,
        ),
    )
    monkeypatch.setattr(email.config, "conf", conf)
    smtp = MagicMock()
    smtp_ssl = MagicMock()
    monkeypatch.setattr(email.smtplib, "SMTP", smtp)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", smtp_ssl)

    message = email.Email("test body", "test subject", None)
    message.send(explicit)

    constructor = smtp if encryption == "starttls" else smtp_ssl
    unused_constructor = smtp_ssl if encryption == "starttls" else smtp
    constructor.assert_called_once_with(
        "smtp.example.invalid", conf.custom_smtp_server.ssl_port, timeout=10
    )
    unused_constructor.assert_not_called()
    transport = constructor.return_value
    if encryption == "starttls":
        transport.starttls.assert_called_once_with()
    else:
        transport.starttls.assert_not_called()
    transport.login.assert_called_once_with(conf.account, conf.pass_code)
    transport.send_message.assert_called_once_with(message.msg, conf.account, expected)
    transport.quit.assert_called_once_with()
    assert conf.recipient == original
