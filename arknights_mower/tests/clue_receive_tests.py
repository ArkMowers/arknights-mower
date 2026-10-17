from unittest.mock import MagicMock

import cv2
import pytest
from rapidocr_onnxruntime import RapidOCR

from arknights_mower.tests.clue_gift_tests import clue_workflow as clue_workflow
from arknights_mower.tests.clue_gift_tests import frame
from arknights_mower.tests.clue_gift_tests import gift_ui as gift_ui
from arknights_mower.utils import rapidocr
from arknights_mower.utils.image import loadres
from arknights_mower.utils.scene import Scene


@pytest.fixture
def receive_workflow(clue_workflow, monkeypatch):
    solver, state = clue_workflow
    # 原图缺 5 号；仅在离线输入中补齐卡片，构造完整线索板。
    receive = frame("clue_receive_credit_capped.jpg")
    card = loadres("clue/5")
    receive[660 : 660 + card.shape[0], 495 : 495 + card.shape[1]] = card
    state.snapshots[Scene.CLUE_RECEIVE] = receive
    state.received = 0
    state.pending = 2
    state.credit_capped = True
    state.cap_after = None
    state.cap_score = 0.99
    state.receive_opened = False
    state.receive_exits = 0
    state.exit_delayed = False

    previous_find = solver.find

    def find(resource, **kwargs):
        if resource == "clue/badge_new" and kwargs["scope"] == (
            (1815, 360),
            (1895, 410),
        ):
            return (1850, 385) if not state.receive_opened else None
        return previous_find(resource, **kwargs)

    solver.find = find
    previous_scene = solver.scene

    def scene():
        current = previous_scene()
        solver.recog.gray = cv2.cvtColor(solver.recog.img, cv2.COLOR_RGB2GRAY)
        return current

    solver.scene = scene
    previous_tap = solver.tap.side_effect

    def tap(point, **kwargs):
        if point == (1800, 430):
            state.receive_opened = True
            state.scene = Scene.CLUE_RECEIVE
        elif point == ((1580, 220), (1880, 255)):
            state.received += 1
            if state.cap_after == state.received:
                state.credit_capped = True
            if state.received == state.pending:
                receive[100:400, 1275:1920] = 0
        elif point == (1239, 144):
            state.receive_exits += 1
            if state.exit_delayed and state.receive_exits == 1:
                state.credit_capped = False
            else:
                state.scene = Scene.INFRA_CONFIDENTIAL
        else:
            previous_tap(point, **kwargs)

    solver.tap = MagicMock(side_effect=tap)
    solver.ctap = solver.tap
    solver._give_one_placed_clue = MagicMock(return_value=False)
    solver._read_clue_gift_capacity = MagicMock(return_value=(0, 10))

    def ocr(image, **kwargs):
        if image.shape[:2] == (75, 645):
            message = (
                "今日接受信用已达上限" if state.credit_capped else "接受线索可获得信用"
            )
            return [[[], message, state.cap_score]], None
        return [[[], "测试好友", 0.99]], None

    monkeypatch.setattr(rapidocr, "engine", MagicMock(side_effect=ocr))
    return solver, state


@pytest.mark.parametrize("leifeng", [False, True])
@pytest.mark.parametrize(
    "capped,cap_after,expected",
    [(True, None, 0), (False, None, 2), (False, 1, 1)],
)
def test_full_board_stops_receiving_only_after_daily_credit_cap(
    receive_workflow, caplog, leifeng, capped, cap_after, expected
):
    solver, state = receive_workflow
    solver.leifeng_mode = leifeng
    state.credit_capped = capped
    state.cap_after = cap_after

    solver.clue_new()

    assert state.received == expected
    assert state.receive_exits == 1
    solver._give_one_placed_clue.assert_called_once()
    solver._run_clue_shop.assert_called_once()
    assert (
        "线索板已填满，今日接受信用已达上限，暂不领取剩余好友线索" in caplog.text
    ) is (expected < 2)


def test_delayed_close_does_not_resume_receiving_after_credit_cap(receive_workflow):
    solver, state = receive_workflow
    state.exit_delayed = True

    solver.clue_new()

    assert state.received == 0
    assert state.receive_exits == 2
    solver._give_one_placed_clue.assert_called_once()
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize(
    "x,y",
    [
        (72, 228),
        (374, 334),
        (679, 198),
        (1003, 265),
        (495, 660),
        (805, 573),
        (154, 608),
    ],
)
def test_missing_any_board_card_keeps_receiving_at_credit_cap(receive_workflow, x, y):
    solver, state = receive_workflow
    state.snapshots[Scene.CLUE_RECEIVE][y - 16 : y + 232, x - 16 : x + 178] = 0

    solver.clue_new()

    assert state.received == 2
    assert state.receive_exits == 1
    solver._give_one_placed_clue.assert_called_once()


def test_low_confidence_cap_text_does_not_stop_receiving(receive_workflow):
    solver, state = receive_workflow
    state.cap_score = 0.5

    solver.clue_new()

    assert state.received == 2


def test_real_incomplete_board_keeps_receiving_at_credit_cap(receive_workflow):
    solver, state = receive_workflow
    state.snapshots[Scene.CLUE_RECEIVE][:] = frame("clue_receive_credit_capped.jpg")

    solver.clue_new()

    assert state.received == 2
    solver._run_clue_shop.assert_called_once()


def test_page_change_while_waiting_never_receives_on_another_page(receive_workflow):
    solver, state = receive_workflow

    def wait():
        if state.scene == Scene.CLUE_RECEIVE:
            state.scene = Scene.INFRA_CONFIDENTIAL

    solver.wait_product_complete.side_effect = wait

    solver.clue_new()

    assert state.received == 0
    assert state.receive_exits == 0
    solver._run_clue_shop.assert_called_once()


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("clue_receive_credit_capped.jpg", True),
        ("clue_live_receive_after.png", True),
        ("clue_live_credit_prompt.png", False),
    ],
)
def test_real_receive_credit_caption(receive_workflow, monkeypatch, filename, expected):
    solver, state = receive_workflow
    state.scene = Scene.CLUE_RECEIVE
    state.snapshots[Scene.CLUE_RECEIVE] = frame(filename)
    monkeypatch.setattr(rapidocr, "engine", RapidOCR())

    assert solver._clue_receive_credit_capped() is expected


@pytest.mark.parametrize(
    "result,expected",
    [
        (None, False),
        ([], False),
        ([[[], "信用已达上限", 0.99]], False),
        ([[[], "今日接受信用未达上限", 0.99]], False),
        ([[[], " 今日接受信用 已达上限 ", 0.99]], True),
    ],
)
def test_credit_cap_requires_complete_confirmed_caption(
    receive_workflow, result, expected
):
    solver, state = receive_workflow
    state.scene = Scene.CLUE_RECEIVE
    rapidocr.engine.return_value = (result, None)
    rapidocr.engine.side_effect = None

    assert solver._clue_receive_credit_capped() is expected


def test_credit_cap_is_not_read_on_other_pages(receive_workflow):
    solver, _ = receive_workflow

    assert solver._clue_receive_credit_capped() is False
    rapidocr.engine.assert_not_called()
