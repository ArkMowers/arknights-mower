from datetime import datetime
from unittest.mock import Mock

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


@pytest.mark.parametrize("x,y", [(930, 555), (1270, 750)])
def test_expiry_reads_only_chinese_side_of_badge(monkeypatch, x, y):
    engine = Mock(return_value=([("即将到期", 0.95)], None))
    monkeypatch.setattr(monthly_card.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(monthly_card.rapidocr, "engine", engine)

    assert monthly_card.expiry_visible(home_frame(x, y))
    image = engine.call_args.args[0]
    assert 175 <= image.shape[1] <= 205
    assert engine.call_args.kwargs == {
        "use_det": False,
        "use_cls": False,
        "use_rec": True,
    }


def test_similar_store_color_does_not_activate_ocr(monkeypatch):
    initialize = Mock()
    monkeypatch.setattr(monthly_card.rapidocr, "initialize_ocr", initialize)

    assert not monthly_card.expiry_visible(home_frame(badge=False))
    initialize.assert_not_called()


@pytest.mark.parametrize(
    "reading", [("即将到明", 0.98), ("即将到期", 0.50), ("活动即将到期", 0.99)]
)
def test_uncertain_text_never_confirms_an_expiry(monkeypatch, reading):
    monkeypatch.setattr(monthly_card.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(
        monthly_card.rapidocr, "engine", Mock(return_value=([reading], None))
    )

    assert not monthly_card.expiry_visible(home_frame())


def test_warning_reminder_is_deduplicated_across_scheduler_restart(
    income_db, monkeypatch
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
    assert scans.call_count == 1
    mail.assert_called_once_with(
        "请在游戏内查看月卡剩余时间。", subject="月卡即将到期", level="WARNING"
    )

    restarted = monthly_card.MonthlyCardReminder()
    restarted.observe(Scene.INDEX, recognizer)
    assert mail.call_count == 1
    now = now.replace(day=25)
    restarted.observe(Scene.INDEX, recognizer)
    assert mail.call_count == 2


def test_waits_for_another_home_visit_after_an_unreadable_badge(income_db, monkeypatch):
    scans = Mock(side_effect=[RuntimeError("OCR unavailable"), True])
    mail = Mock()
    monkeypatch.setattr(monthly_card, "expiry_visible", scans)
    monkeypatch.setattr(monthly_card, "send_message", mail)
    recognizer = Mock(img=home_frame())
    reminder = monthly_card.MonthlyCardReminder()

    reminder.observe(Scene.INDEX, recognizer)
    reminder.observe(Scene.INDEX, recognizer)
    assert scans.call_count == 1
    mail.assert_not_called()
    reminder.observe(Scene.INFRA_MAIN, recognizer)
    reminder.observe(Scene.INDEX, recognizer)
    mail.assert_called_once()
