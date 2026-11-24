from datetime import datetime
from threading import Event, Thread
from unittest.mock import Mock, PropertyMock

import numpy as np
import pytest

from arknights_mower.solvers import monthly_card
from arknights_mower.utils.scene import Scene


def home_frame(x=1270, y=750, *, badge=True):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[y : y + 50, x : x + 150] = (218, 16, 76)
    if badge:
        frame[y + 5 : y + 45, x + 5 : x + 52] = (39, 9, 22)
        for dx in (61, 81, 101, 121):
            frame[y + 12 : y + 38, x + dx : x + dx + 11] = (250, 235, 241)
    return frame


def home_region(x=1270, y=750, *, badge=True):
    return home_frame(x, y, badge=badge)[530:850, 900:1500]


@pytest.fixture
def reminder_threads(monkeypatch):
    workers = []

    def make_thread(*args, **kwargs):
        worker = Thread(*args, **kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(monthly_card, "Thread", make_thread)
    monkeypatch.setattr(monthly_card.config, "stop_mower", Event())
    yield workers
    for worker in workers:
        worker.join(5)
        assert not worker.is_alive()


@pytest.mark.parametrize("x,y", [(930, 555), (1270, 750)])
def test_expiry_reads_only_chinese_side_of_badge(monkeypatch, x, y):
    engine = Mock(return_value=([("即将到期", 0.95)], None))
    monkeypatch.setattr(monthly_card.rapidocr, "engine", engine)

    assert monthly_card.expiry_visible(home_region(x, y))
    image = engine.call_args.args[0]
    assert 175 <= image.shape[1] <= 205
    assert engine.call_args.kwargs == {
        "use_det": False,
        "use_cls": False,
        "use_rec": True,
    }


def test_similar_store_color_does_not_activate_ocr(monkeypatch):
    engine = Mock()
    monkeypatch.setattr(monthly_card.rapidocr, "engine", engine)

    assert not monthly_card.expiry_visible(home_region(badge=False))
    engine.assert_not_called()


@pytest.mark.parametrize(
    "reading", [("即将到明", 0.98), ("即将到期", 0.50), ("活动即将到期", 0.99)]
)
def test_uncertain_text_never_confirms_an_expiry(monkeypatch, reading):
    monkeypatch.setattr(
        monthly_card.rapidocr, "engine", Mock(return_value=([reading], None))
    )

    assert not monthly_card.expiry_visible(home_region())


def test_warning_reminder_is_deduplicated_across_scheduler_restart(
    income_db, monkeypatch, reminder_threads
):
    scans = Mock(return_value=True)
    mail = Mock()
    now = datetime(2026, 11, 24, 12)
    monkeypatch.setattr(monthly_card, "expiry_visible", scans)
    monkeypatch.setattr(monthly_card, "send_message", mail)
    monkeypatch.setattr(monthly_card, "get_server_time", lambda: now)
    recognizer = Mock(img=home_frame())
    first = monthly_card.MonthlyCardReminder()

    first.observe(Scene.INFRA_MAIN, recognizer)
    scans.assert_not_called()
    first.observe(Scene.INDEX, recognizer)
    first.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    assert scans.call_count == 1
    mail.assert_called_once_with(
        "请在游戏内查看月卡剩余时间。", subject="月卡即将到期", level="WARNING"
    )

    restarted = monthly_card.MonthlyCardReminder()
    restarted.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    assert mail.call_count == 1
    now = now.replace(day=25)
    restarted.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    assert mail.call_count == 2


def test_waits_for_another_home_visit_after_an_unreadable_badge(
    income_db, monkeypatch, reminder_threads
):
    scans = Mock(side_effect=[RuntimeError("OCR unavailable"), True])
    mail = Mock()
    monkeypatch.setattr(monthly_card, "expiry_visible", scans)
    monkeypatch.setattr(monthly_card, "send_message", mail)
    recognizer = Mock(img=home_frame())
    reminder = monthly_card.MonthlyCardReminder()

    reminder.observe(Scene.INDEX, recognizer)
    reminder.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    assert scans.call_count == 1
    mail.assert_not_called()
    reminder.observe(Scene.INFRA_MAIN, recognizer)
    reminder.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    mail.assert_called_once()


def test_pending_scan_admits_no_second_scan_and_discards_stopped_result(
    income_db, monkeypatch, reminder_threads
):
    started, release = Event(), Event()

    def blocked_scan(region):
        started.set()
        return release.wait(5)

    original = monthly_card.MonthlyCardReminder()
    restarted = monthly_card.MonthlyCardReminder()
    recognizer = Mock(img=home_frame())
    mail = Mock()
    monkeypatch.setattr(monthly_card, "expiry_visible", blocked_scan)
    monkeypatch.setattr(monthly_card, "send_message", mail)

    original.observe(Scene.INDEX, recognizer)
    try:
        assert started.wait(2)
        original.observe(Scene.INFRA_MAIN, recognizer)
        original.observe(Scene.INDEX, recognizer)
        restarted.observe(Scene.INDEX, recognizer)
        assert len(reminder_threads) == 1
        monthly_card.config.stop_mower.set()
    finally:
        release.set()
        reminder_threads[0].join(5)
    mail.assert_not_called()

    monthly_card.config.stop_mower.clear()
    restarted.observe(Scene.INFRA_MAIN, recognizer)
    restarted.observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    mail.assert_called_once()


def test_cached_home_scene_without_a_frame_does_not_start_a_capture(reminder_threads):
    recognizer = Mock(capture_started_at=None)
    capture = PropertyMock(side_effect=AssertionError("unexpected capture"))
    type(recognizer).img = capture

    monthly_card.MonthlyCardReminder().observe(Scene.INDEX, recognizer)

    assert not reminder_threads
    capture.assert_not_called()


def test_stop_while_registering_reminder_preserves_same_day_retry(
    income_db, monkeypatch, reminder_threads
):
    from arknights_mower.solvers import record

    started, release = Event(), Event()
    original_claim = monthly_card.claim_monthly_card_reminder
    now = datetime(2026, 11, 24, 12)
    yesterday = now.replace(day=23).date()
    assert original_claim(yesterday)[0]

    def blocked_claim(today):
        started.set()
        assert release.wait(5)
        return original_claim(today)

    mail = Mock()
    monkeypatch.setattr(monthly_card, "expiry_visible", Mock(return_value=True))
    monkeypatch.setattr(monthly_card, "claim_monthly_card_reminder", blocked_claim)
    monkeypatch.setattr(monthly_card, "send_message", mail)
    monkeypatch.setattr(monthly_card, "get_server_time", lambda: now)
    recognizer = Mock(img=home_frame())

    monthly_card.MonthlyCardReminder().observe(Scene.INDEX, recognizer)
    try:
        assert started.wait(2)
        monthly_card.config.stop_mower.set()
    finally:
        release.set()
        reminder_threads[0].join(5)
    mail.assert_not_called()
    assert record._fetchall("SELECT game_day FROM monthly_card_reminder") == [
        (yesterday.isoformat(),)
    ]

    monthly_card.config.stop_mower.clear()
    monthly_card.MonthlyCardReminder().observe(Scene.INDEX, recognizer)
    reminder_threads[-1].join(5)
    mail.assert_called_once()


def test_revoking_a_cancelled_claim_preserves_a_newer_reminder(income_db):
    from arknights_mower.solvers import record

    day = datetime(2026, 11, 24).date()
    next_day = day.replace(day=25)
    claimed, previous = record.claim_monthly_card_reminder(day)
    assert claimed
    assert record.claim_monthly_card_reminder(next_day)[0]

    record.restore_monthly_card_reminder(day, previous)

    assert not record.claim_monthly_card_reminder(day)[0]
    assert not record.claim_monthly_card_reminder(next_day)[0]


def test_reminder_has_an_independent_short_shared_ocr_timeout(monkeypatch, tmp_path):
    shared = monthly_card.SharedOCREngine(directory=tmp_path)
    calls = []

    def recognize(client, image, **options):
        calls.append(client)
        return [("即将到期", 0.98)], None

    monkeypatch.setattr(monthly_card.rapidocr, "engine", shared)
    monkeypatch.setattr(monthly_card.SharedOCREngine, "__call__", recognize)

    assert monthly_card.expiry_visible(home_region())
    assert len(calls) == 1
    assert calls[0] is not shared
    assert calls[0].directory == shared.directory
    assert calls[0].timeout == 5
    assert shared.timeout == 60
