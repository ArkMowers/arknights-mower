import base64
import time
import weakref
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.utils import email, log
from arknights_mower.utils.config.conf import EmailPart

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRckAAAAASUVORK5CYII="
)


class NotificationConf(SimpleNamespace):
    pass


@pytest.fixture
def notification(monkeypatch):
    conf = NotificationConf(
        mail_enable=True,
        notification_level="INFO",
        mail_subject="[测试实例]",
        mail_attach_error_screenshot=False,
        account="sender@example.invalid",
        pass_code="test-password",
        recipient=["receiver@example.invalid"],
        custom_smtp_server=SimpleNamespace(enable=False),
        timezone_offset=0,
    )
    monkeypatch.setattr(email.config, "conf", conf)
    monkeypatch.setattr(email, "logger", MagicMock())
    thread = MagicMock()
    monkeypatch.setattr(email, "Thread", thread)
    get_store = MagicMock(return_value=None)
    monkeypatch.setattr(log, "get_screenshot_store", get_store)
    source = SimpleNamespace(_screenshot_owner=object())

    def send(body, **kwargs):
        if kwargs.get("archive_screenshots"):
            kwargs.setdefault("screenshot_source", source)
        email.send_message(body, **kwargs)
        return thread.call_args.kwargs["args"][0].msg

    return SimpleNamespace(
        conf=conf, send=send, thread=thread, get_store=get_store, source=source
    )


def html_body(message):
    part = next(
        part for part in message.walk() if part.get_content_type() == "text/html"
    )
    return part.get_payload(decode=True).decode("utf-8")


def image_parts(message):
    return [part for part in message.walk() if part.get_content_maintype() == "image"]


def captured_frame(notification, *, age=1, data=PNG):
    wall_ns = time.time_ns() - int(age * 10**9)
    monotonic_at = time.monotonic() - age
    return SimpleNamespace(
        data=data,
        captured_ns=wall_ns,
        queued_at=monotonic_at,
        capture_started_at=monotonic_at,
        capture_wall_ns=wall_ns,
        capture_owner=notification.source._screenshot_owner,
        configuration_ref=weakref.ref(notification.conf),
    )


def test_plain_notification_uses_template_and_preserves_subject_and_text(notification):
    message = notification.send(
        "首行 <标签> & 内容\n第二行", subject="任务提醒", level="WARNING"
    )
    body = html_body(message)
    assert message["Subject"] == "[测试实例]任务提醒"
    assert body.count("<html") == 1
    assert "Mower 通知" in body
    assert "WARNING" in body
    assert "首行 &lt;标签&gt; &amp; 内容<br>第二行" in body
    assert "cid:mower-screenshot" not in body


def test_error_screenshot_is_opt_in_by_default():
    assert EmailPart().mail_attach_error_screenshot is False


def test_screenshot_from_a_previous_configuration_is_not_sent(
    monkeypatch, notification
):
    notification.conf.mail_attach_error_screenshot = True
    previous = NotificationConf(**vars(notification.conf))
    frame = captured_frame(notification)
    frame.configuration_ref = weakref.ref(previous)
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    assert not image_parts(message)


def test_clock_rollback_does_not_make_an_old_screenshot_recent(notification):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification, age=40)
    frame.captured_ns = time.time_ns() - 20_000_000_000
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    assert not image_parts(message)


def test_delayed_screenshot_submission_does_not_make_an_old_capture_recent(
    notification,
):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification, age=40)
    frame.captured_ns = time.time_ns() - 1_000_000_000
    frame.queued_at = time.monotonic() - 1
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    assert not image_parts(message)


def test_rebound_device_does_not_send_its_previous_screenshot(notification):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification)
    notification.source._screenshot_owner = object()
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    assert not image_parts(message)


def test_closing_a_device_invalidates_its_screenshot_owner():
    import os
    from threading import RLock

    from arknights_mower.utils.device.device import Device

    device = object.__new__(Device)
    device.owner_pid = os.getpid()
    device._resource_lock = RLock()
    device._screenshot_owner = object()
    device._close_error = None
    device._pending_cleanup = []
    device._interrupt_error = None
    device.control = None
    device.client = None
    previous = device._screenshot_owner

    device.close()

    assert device._screenshot_owner is not previous


def test_recent_same_device_frame_published_during_notification_is_usable(
    monkeypatch, notification
):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification, age=0)
    frame.capture_started_at = 100.5
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)
    monkeypatch.setattr(email, "monotonic", lambda: 100.0)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    assert image_parts(message)[0].get_payload(decode=True) == PNG


def test_profile_change_during_image_selection_keeps_the_original_recipients(
    monkeypatch, notification
):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification)
    later = NotificationConf(**vars(notification.conf))
    later.account = "second-sender@example.invalid"
    later.pass_code = "second-password"
    later.recipient = ["second-recipient@example.invalid"]

    def switch_profile():
        monkeypatch.setattr(email.config, "conf", later)
        return SimpleNamespace(latest=lambda: frame)

    notification.get_store.side_effect = switch_profile
    smtp = MagicMock()
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", smtp)
    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )
    queued_email = notification.thread.call_args.kwargs["args"][0]
    queued_email.send()

    assert image_parts(message)[0].get_payload(decode=True) == PNG
    assert message["From"] == "sender@example.invalid"
    assert message["To"] == "receiver@example.invalid"
    smtp.return_value.login.assert_called_once_with(
        "sender@example.invalid", "test-password"
    )
    smtp.return_value.send_message.assert_called_once_with(
        message, "sender@example.invalid", ["receiver@example.invalid"]
    )


@pytest.mark.parametrize(
    ("threshold", "level", "sent"),
    [
        ("INFO", "INFO", True),
        ("INFO", "WARNING", True),
        ("INFO", "ERROR", True),
        ("WARNING", "INFO", False),
        ("WARNING", "WARNING", True),
        ("WARNING", "ERROR", True),
        ("ERROR", "INFO", False),
        ("ERROR", "WARNING", False),
        ("ERROR", "ERROR", True),
    ],
)
def test_notification_threshold_controls_delivery_before_screenshot_selection(
    notification, threshold, level, sent
):
    notification.conf.notification_level = threshold
    notification.conf.mail_attach_error_screenshot = True
    email.send_message(
        "一条通知",
        level=level,
        archive_screenshots=True,
        screenshot_source=notification.source,
    )
    assert bool(notification.thread.call_count) is sent
    if not sent:
        notification.get_store.assert_not_called()


def test_test_email_route_requires_token_and_uses_the_notification_template(
    monkeypatch,
):
    import server
    from arknights_mower.utils import config_profiles, managed_device

    conf = SimpleNamespace(
        mail_enable=False,
        mail_subject="[测试实例]",
        account="sender@example.invalid",
        pass_code="test-password",
        recipient=["receiver@example.invalid"],
        custom_smtp_server=SimpleNamespace(enable=False),
    )
    monkeypatch.setattr(email.config, "conf", conf)
    monkeypatch.setattr(server.app, "token", "email-token", raising=False)
    monkeypatch.setitem(server.app.config, "UPDATES_ENABLED", True)
    monkeypatch.setattr(managed_device, "operation_blocked", lambda *_: False)
    monkeypatch.setattr(config_profiles, "check_generation", lambda *_: None)
    sent = []
    original_email = email.Email
    monkeypatch.setattr(original_email, "send", lambda self: sent.append(self.msg))
    constructor = MagicMock(wraps=original_email)
    monkeypatch.setattr(email, "Email", constructor)
    client = server.app.test_client()

    for headers in ({}, {"token": "incorrect"}):
        assert client.get("/test-email", headers=headers).status_code == 403
    constructor.assert_not_called()
    assert sent == []

    response = client.get("/test-email", headers={"token": "email-token"})
    assert response.status_code == 200
    assert "邮件发送成功" in response.get_data(as_text=True)
    assert len(sent) == 1
    assert sent[0]["Subject"] == "[测试实例]测试邮件"
    assert "Mower 通知" in html_body(sent[0])
    assert "测试邮件" in html_body(sent[0])


@pytest.mark.parametrize("level", ["WARNING", "ERROR"])
def test_recent_visual_error_can_embed_the_existing_screenshot(notification, level):
    notification.conf.mail_attach_error_screenshot = True
    notification.conf.timezone_offset = -3
    frame = captured_frame(notification, age=2)
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send("训练室安排超时", level=level, archive_screenshots=True)
    body = html_body(message)
    images = image_parts(message)
    assert 'src="cid:mower-screenshot"' in body
    assert "截图时间：" in body
    captured = datetime.fromtimestamp(frame.capture_wall_ns / 10**9) - timedelta(
        hours=3
    )
    assert captured.strftime("%Y-%m-%d %H:%M:%S") in body
    assert len(images) == 1
    assert images[0]["Content-ID"] == "<mower-screenshot>"
    assert images[0].get_content_disposition() == "inline"
    assert images[0].get_payload(decode=True) == PNG


def test_encoded_jpeg_is_reused_without_reencoding(notification):
    notification.conf.mail_attach_error_screenshot = True
    jpeg = email.img2bytes(np.zeros((4, 4, 3), dtype=np.uint8)).tobytes()
    frame = captured_frame(notification, data=jpeg)
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )

    image = image_parts(message)[0]
    assert image.get_content_type() == "image/jpeg"
    assert image.get_filename() == "screenshot.jpg"
    assert image.get_payload(decode=True) == jpeg


def test_existing_image_attachment_is_retained_with_an_inline_error_image(
    monkeypatch, notification
):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification)
    notification.get_store.return_value = SimpleNamespace(latest=lambda: frame)
    monkeypatch.setattr(
        email, "img2bytes", lambda _: SimpleNamespace(tobytes=lambda: PNG)
    )

    message = notification.send(
        "训练室安排超时",
        level="ERROR",
        archive_screenshots=True,
        attach_image=object(),
    )
    images = image_parts(message)
    assert len(images) == 2
    assert {part.get_content_disposition() for part in images} == {
        "inline",
        "attachment",
    }
    assert all(part.get_payload(decode=True) == PNG for part in images)


@pytest.mark.parametrize("switch_during_capture", [False, True])
def test_real_device_capture_preserves_its_configuration_identity(
    tmp_path, monkeypatch, notification, switch_during_capture
):
    from arknights_mower.utils import config
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.screenshot import ScreenshotStore

    notification.conf.mail_attach_error_screenshot = True
    notification.conf.screenshot_interval = 0
    notification.conf.performance_mode = "manual"
    later = NotificationConf(**vars(notification.conf))
    image = np.zeros((8, 8, 3), dtype=np.uint8)

    def capture():
        if switch_during_capture:
            monkeypatch.setattr(config, "conf", later)
        return SimpleNamespace(unwrap=lambda: image)

    device = object.__new__(Device)
    device._screenshot_owner = object()
    device.session_control = SimpleNamespace(capture=capture)
    monkeypatch.setattr(config, "screenshot_time", datetime.min)
    monkeypatch.setattr(config, "screenshot_avg", None)
    monkeypatch.setattr(config, "screenshot_count", 0)
    store = ScreenshotStore(
        tmp_path, lambda: 0, logger=MagicMock(), encoder=lambda _: PNG
    )
    monkeypatch.setattr(log, "_store", lambda: store)
    notification.get_store.return_value = store
    store.start()
    try:
        device.screencap()
        with store._ready:
            assert store._ready.wait_for(lambda: store._latest is not None, timeout=3)
        frame = store.latest()
        assert frame.capture_started_at <= frame.queued_at
        assert frame.capture_wall_ns is not None
        message = notification.send(
            "训练室安排超时",
            level="ERROR",
            archive_screenshots=True,
            screenshot_source=device,
        )
        assert bool(image_parts(message)) is not switch_during_capture
    finally:
        assert store.close()["remaining_threads"] == []


def test_maa_stop_sends_the_real_drop_table_through_the_shared_template(
    monkeypatch, notification
):
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(base_schedule, "send_message", email.send_message)
    monkeypatch.setattr(base_schedule, "battle_inventory_active", MagicMock())
    monkeypatch.setattr(
        base_schedule,
        "stage_drop",
        {
            "details": [[{"itemName": "源岩", "quantity": 2}]],
            "summary": [{"itemName": "源岩", "quantity": 2}],
        },
    )
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.MAA = MagicMock()
    solver.drop_send = False

    solver.maa_stop()

    message = notification.thread.call_args.kwargs["args"][0].msg
    body = html_body(message)
    assert message["Subject"] == "[测试实例]MAA停止"
    assert body.count("<html") == 1
    assert "源岩" in body and "合计" in body
    assert "&lt;table" not in body
    assert solver.drop_send is True
    solver.MAA.stop.assert_called_once_with()


@pytest.mark.parametrize(
    ("template_name", "context", "expected"),
    [
        (
            "task_template",
            {
                "tasks": [
                    SimpleNamespace(
                        time=datetime(2026, 11, 6, 14, 30),
                        plan={"room_1_1": ["阿米娅"]},
                        type="",
                        emergency_recovery_release=False,
                        emergency_staffing=False,
                        emergency_dorm=False,
                    )
                ],
                "base_scheduler": SimpleNamespace(translate_room=lambda _: "贸易站"),
            },
            ("14:30:00", "贸易站", "阿米娅"),
        ),
        (
            "maa_template",
            {
                "stage_drop": {
                    "details": [[{"itemName": "源岩", "quantity": 2}]],
                    "summary": [{"itemName": "源岩", "quantity": 2}],
                }
            },
            ("源岩", "合计", "2"),
        ),
        (
            "recruit_template",
            {
                "recruit_results": {
                    1: {"tags": ["资深干员"], "result": [{"name": "阿米娅"}]}
                },
                "recruit_get_agent": {2: "杜宾"},
                "permit_count": 5,
            },
            ("资深干员", "阿米娅", "杜宾", "5"),
        ),
        (
            "recruit_rarity",
            {"recruit_results": [{"tag": "<输出>", "result": [{"name": "银灰"}]}]},
            ("&lt;输出&gt;", "银灰"),
        ),
        (
            "report_template",
            {
                "report_data": {
                    "赤金": 12,
                    "龙门币订单": 345,
                    "龙门币订单数": 6,
                    "作战录像": 7,
                    "合成玉": 8,
                }
            },
            ("赤金", "345", "合成玉"),
        ),
    ],
)
def test_existing_summary_templates_keep_their_data_in_one_mail_document(
    notification, template_name, context, expected
):
    fragment = getattr(email, template_name).render(**context)
    message = notification.send(fragment, subject="任务汇总", body_is_html=True)
    body = html_body(message)
    assert body.count("<html") == 1
    assert body.count("</html>") == 1
    assert "<table" in body and "&lt;table" not in body
    for value in expected:
        assert value in body


@pytest.mark.parametrize(
    ("enabled", "level", "visual"),
    [
        (False, "ERROR", True),
        (True, "ERROR", False),
        (True, "INFO", True),
    ],
)
def test_non_opted_in_or_nonvisual_notifications_do_not_access_screenshots(
    notification, enabled, level, visual
):
    notification.conf.mail_attach_error_screenshot = enabled
    message = notification.send("一条通知", level=level, archive_screenshots=visual)
    assert not image_parts(message)
    assert "cid:mower-screenshot" not in html_body(message)
    notification.get_store.assert_not_called()


@pytest.mark.parametrize(
    "case", ["missing", "stale", "future", "oversized", "invalid", "error"]
)
def test_unusable_screenshot_does_not_block_the_text_notification(notification, case):
    notification.conf.mail_attach_error_screenshot = True
    frame = captured_frame(notification)
    if case == "missing":
        frame = None
    elif case == "stale":
        frame.capture_started_at = time.monotonic() - 31
    elif case == "future":
        frame.capture_started_at = time.monotonic() + 60
    elif case == "oversized":
        frame.data = b"x" * (1024 * 1024 + 1)
    elif case == "invalid":
        frame.data = b"not an image"
    store = MagicMock()
    if case == "error":
        store.latest.side_effect = OSError("screenshot unavailable")
    else:
        store.latest.return_value = frame
    notification.get_store.return_value = store

    message = notification.send(
        "训练室安排超时", level="ERROR", archive_screenshots=True
    )
    assert "训练室安排超时" in html_body(message)
    assert not image_parts(message)
    assert "cid:mower-screenshot" not in html_body(message)
