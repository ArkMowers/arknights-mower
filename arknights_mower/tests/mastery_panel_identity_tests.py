"""Training identity uses frame evidence; terminal failures request archives."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import ImageFont

from arknights_mower.solvers import mastery, mastery_reader
from arknights_mower.utils import email, log, mastery_db, mastery_recommendation
from arknights_mower.utils.mastery_panel_model import FONT_SIZE, render_template
from arknights_mower.utils.scene import Scene


@pytest.fixture
def plan():
    return {
        "id": 1,
        "char_id": "char_128_plosis",
        "char_name": "白面鸮",
        "skill_index": 1,
        "skill_name": "二技能·脑啡肽",
        "target_level": 3,
        "status": "arranging",
    }


def panel_solver(text, pixels="[白面鸮]脑啡肽"):
    font = ImageFont.truetype(
        str(Path(__file__).parents[1] / "fonts/SourceHanSansCN-Medium-mastery.ttf"),
        FONT_SIZE,
        layout_engine=ImageFont.Layout.BASIC,
    )
    rendered = (
        render_template(pixels, font) if pixels else np.zeros((0, 0), dtype=np.uint8)
    )
    solver = MagicMock()
    solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.img[934 : 934 + rendered.shape[0], 240 : 240 + rendered.shape[1]] = (
        rendered[:, :, None]
    )
    solver.read_screen.return_value = text
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    solver.tasks = []
    return solver


@pytest.mark.parametrize("ocr_name", ["白面", "面鸮", "陌生人", ""])
def test_name_comes_from_templates_independently_of_ocr(ocr_name, plan):
    solver = panel_solver(f"[{ocr_name}]脑啡肽")
    panel = mastery_reader._read_panel_text(solver)
    assert (panel.operator_name, panel.skill_name) == ("白面鸮", "脑啡肽")
    solver.read_screen.assert_called_once()
    assert mastery_reader._plan_matches_room(
        plan, mastery_reader.RoomState("training", panel)
    )


@pytest.mark.parametrize(
    "name, skill",
    [
        ("八幡海铃", "颤栗之弦"),
        ("卡涅利安", "沙缚镣锁"),
        ("森蚺", "荆棘"),
        ("吽", "医疗模式"),
    ],
)
def test_full_name_templates_cover_other_operators(name, skill):
    panel = mastery_reader._read_panel_text(
        panel_solver(f"[] {skill}", f"[{name}]{skill}")
    )
    assert panel.operator_name == name


def test_blank_pixels_do_not_accept_a_valid_ocr_name():
    solver = panel_solver("[白面鸮]脑啡肽", pixels="")
    panel = mastery_reader._read_panel_text(solver)
    assert panel.operator_name == ""
    solver.read_screen.assert_not_called()


def test_unavailable_name_templates_preserve_unknown(monkeypatch):
    monkeypatch.setattr(mastery_reader, "recognize_operator", lambda *_: None)
    solver = panel_solver("[白面鸮]脑啡肽")
    assert mastery_reader._read_panel_text(solver).operator_name == ""
    solver.read_screen.assert_not_called()


@pytest.fixture
def confirmation(monkeypatch):
    start = datetime.now()
    times = iter(start + timedelta(seconds=i) for i in range(30))
    monkeypatch.setattr(mastery, "datetime", SimpleNamespace(now=lambda: next(times)))
    monkeypatch.setattr(
        mastery, "_read_train_countdown", lambda _: start + timedelta(hours=8)
    )
    update = MagicMock()
    send = MagicMock()
    monkeypatch.setattr(mastery_db, "update_plan_status", update)
    monkeypatch.setattr(email, "send_message", send)
    monkeypatch.setattr(mastery, "_schedule_swap_if_needed", lambda *_: None)
    monkeypatch.setattr(mastery, "_schedule_collect_checked", lambda *_: None)
    monkeypatch.setattr(mastery, "_arrange_support", lambda *_: None)
    return start + timedelta(seconds=5), update, send


def test_unknown_name_waits_then_confirms_fresh_read(monkeypatch, confirmation, plan):
    deadline, update, send = confirmation
    solver = panel_solver("[白面]脑啡肽")
    monkeypatch.setattr(
        mastery_reader, "recognize_operator", MagicMock(side_effect=[None, "白面鸮"])
    )
    assert mastery._confirm_training_started(solver, plan, deadline) == "started"
    assert [call.args[1] for call in update.call_args_list] == ["training"]
    solver.sleep.assert_any_call(1)
    assert all("与计划不符" not in call.args[0] for call in send.call_args_list)


def test_direct_name_template_confirms_training(confirmation, plan):
    deadline, update, _ = confirmation
    solver = panel_solver("[白面]脑啡肽")
    assert mastery._confirm_training_started(solver, plan, deadline) == "started"
    assert [call.args[1] for call in update.call_args_list] == ["training"]


@pytest.mark.parametrize("text", ["[白面]脑啡肽", "[白面鸮]"])
def test_unconfirmed_identity_times_out_without_false_mismatch(
    monkeypatch, confirmation, plan, text
):
    deadline, update, send = confirmation
    solver = panel_solver(text)
    monkeypatch.setattr(mastery_reader, "recognize_operator", lambda *_: None)
    assert mastery._confirm_training_started(solver, plan, deadline) == "timeout"
    update.assert_not_called()
    send.assert_not_called()
    solver.back.assert_not_called()


def test_real_other_occupant_still_fails(confirmation, plan):
    deadline, update, send = confirmation
    solver = panel_solver("[夜莺]圣域", "[夜莺]圣域")
    assert mastery._confirm_training_started(solver, plan, deadline) == "failed"
    assert update.call_args.args == (plan["id"], "failed")
    assert "实际占用：夜莺" in send.call_args.args[0]


@pytest.mark.parametrize("exit_kind", ["mismatch", "timeout"])
@pytest.mark.parametrize("notification_fails", [False, True])
def test_terminal_failure_reaches_archive_before_notification_and_exit(
    monkeypatch, plan, exit_kind, notification_fails
):
    store = MagicMock()
    store.mark_error.return_value = "mastery-archive"
    events = []
    store.mark_error.side_effect = lambda *_: (
        events.append("archive") or "mastery-archive"
    )
    monkeypatch.setattr(log, "get_screenshot_store", lambda: store)
    monkeypatch.setattr(log.config.log_queue, "put", MagicMock())
    monkeypatch.setattr(mastery_db, "update_plan_status", MagicMock())

    def make_email(*_, **__):
        events.append("notify")
        if notification_fails:
            raise RuntimeError("notification unavailable")
        return MagicMock()

    monkeypatch.setattr(email, "Email", make_email)
    monkeypatch.setattr(email, "Thread", MagicMock())
    monkeypatch.setattr(
        email.config,
        "conf",
        SimpleNamespace(mail_enable=True, notification_level="ERROR", mail_subject=""),
    )

    class ArchiveHandler(logging.Handler):
        def emit(self, record):
            log.filter.filter(record)
            log.basic_formatter.format(record)
            log.whlr.emit(record)

    logger = logging.Logger("mastery-archive-test")
    logger.addHandler(ArchiveHandler())
    monkeypatch.setattr(mastery, "logger", logger)
    monkeypatch.setattr(email, "logger", logger)
    solver = MagicMock()
    solver.back.side_effect = lambda: events.append("exit")

    def run_exit():
        if exit_kind == "mismatch":
            mastery._exit_failed(
                solver, plan, "训练室面板干员/技能与计划不符", step_level=1
            )
        else:
            mastery._exit_arranging_timeout(
                solver, plan, "TRAIN_MAIN", Scene.TRAIN_MAIN, 1
            )

    if notification_fails:
        with pytest.raises(RuntimeError, match="notification unavailable"):
            run_exit()
    else:
        run_exit()
        assert events[-1] == "exit"
    store.mark_error.assert_called_once()
    assert events[:2] == ["archive", "notify"]
    assert "白面鸮 二技能·脑啡肽 专1" in store.mark_error.call_args.args[1]
    assert any(
        "记录编号 mastery-archive" in call.args[0]
        for call in log.config.log_queue.put.call_args_list
    )


@pytest.fixture
def incident_solver():
    """Replay only the panel pixels from the supplied 2026-10-02 Capture Frame."""
    from PIL import Image

    image = np.asarray(
        Image.open(
            Path(__file__).parent / "fixtures/mastery_panel_ptilopsis_enkephalin.png"
        ).convert("RGB")
    )
    solver = panel_solver("[白面]脑啡肽", pixels="")
    (x0, y0), (x1, y1) = mastery_reader.PANEL_REGION
    assert image.shape == (y1 - y0, x1 - x0, 3)
    solver.recog.img[y0:y1, x0:x1] = image
    return solver


def test_real_incident_panel_replays_production_ocr(monkeypatch, incident_solver, plan):
    from unittest.mock import patch

    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import rapidocr

    with patch.object(rapidocr, "engine", None):
        rapidocr.initialize_ocr()
        incident_solver.read_screen.side_effect = lambda *args, **kwargs: (
            BaseMixin.read_screen(incident_solver, *args, **kwargs)
        )
        panel = mastery_reader._read_panel_text(incident_solver)

    assert (panel.operator_name, panel.skill_name) == ("白面鸮", "脑啡肽")
    assert mastery_reader._plan_matches_room(
        plan, mastery_reader.RoomState("training", panel)
    )


def test_real_incident_logged_ocr_confirms_training_once(
    monkeypatch, confirmation, incident_solver, plan
):
    deadline, update, send = confirmation
    recognize = MagicMock(wraps=mastery_reader.recognize_skill)
    monkeypatch.setattr(mastery_reader, "recognize_skill", recognize)

    assert (
        mastery._confirm_training_started(incident_solver, plan, deadline) == "started"
    )
    assert [call.args[1] for call in update.call_args_list] == ["training"]
    assert incident_solver.read_screen.call_count == 1
    recognize.assert_called_once()
    assert recognize.call_args.args[1] == "白面鸮"
    assert all("与计划不符" not in call.args[0] for call in send.call_args_list)


@pytest.mark.parametrize("evidence", ["missing_model", "stale_model", "blank_pixels"])
def test_real_incident_unconfirmed_evidence_keeps_bounded_wait(
    monkeypatch, confirmation, incident_solver, plan, evidence
):
    from copy import deepcopy

    if evidence == "missing_model":
        monkeypatch.setattr(mastery_reader, "recognize_operator", lambda *_: None)
    elif evidence == "stale_model":
        data = deepcopy(mastery_recommendation.get_skill_data())
        data["characters"]["char_128_plosis"]["skills"][0]["name"] += "更新"
        monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: data)
    else:
        incident_solver.recog.img[:] = 0
    deadline, update, send = confirmation

    assert (
        mastery._confirm_training_started(incident_solver, plan, deadline) == "timeout"
    )
    update.assert_not_called()
    send.assert_not_called()
    incident_solver.sleep.assert_any_call(1)
    incident_solver.back.assert_not_called()


def test_real_incident_template_result_does_not_cross_reads(
    monkeypatch, incident_solver
):
    recognize = MagicMock(wraps=mastery_reader.recognize_operator)
    monkeypatch.setattr(mastery_reader, "recognize_operator", recognize)
    assert mastery_reader._read_panel_text(incident_solver).operator_name == "白面鸮"

    incident_solver.recog.img[:] = 0
    assert mastery_reader._read_panel_text(incident_solver).operator_name == ""
    assert recognize.call_count == 2
