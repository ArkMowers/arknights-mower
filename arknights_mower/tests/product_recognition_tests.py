from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import product_recognition
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.recognize import RecognizeError, Recognizer

FIXTURES = Path(__file__).parent / "fixtures/manufacture"


def solver_for(frame):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(
        img=frame, gray=cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), h=1080, w=1920
    )
    return solver


def card(number):
    crops = bytes2img((FIXTURES / "trade_strategy_cards.webp").read_bytes())
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[840:1040, 1400:1810] = crops[number * 200 : (number + 1) * 200]
    return frame


@pytest.mark.parametrize(
    ("filename", "product"),
    [("b303_room_20261123.jpg", "gold"), ("b102_check_in_exp_20261123.jpg", "exp3")],
)
def test_open_and_closed_manufacture_room_labels_skip_ocr(
    monkeypatch, filename, product
):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = Recognizer(None, (FIXTURES / filename).read_bytes())
    ocr = Mock(side_effect=AssertionError("unexpected OCR"))
    monkeypatch.setattr(base.rapidocr, "engine", ocr)
    assert solver._visible_manufacture_product() == product
    ocr.assert_not_called()


@pytest.mark.parametrize(
    "case", ["repeated_prefix", "suffix", "missing_template", "zoom"]
)
def test_room_label_falls_back_to_single_line_ocr(monkeypatch, case):
    filename = {
        "repeated_prefix": "b102_check_in_exp_20261123.jpg",
        "zoom": "b102_room_zoom_20261123.jpg",
    }.get(case, "b303_room_20261123.jpg")
    frame = bytes2img((FIXTURES / filename).read_bytes())
    if case == "suffix":
        frame[934:968, 314:385] = frame[934:968, 239:310].copy()
    elif case == "repeated_prefix":
        frame[934:968, 239:275] = frame[934:968, 275:311].copy()
    elif case == "missing_template":
        monkeypatch.setattr(
            product_recognition, "loadres", Mock(side_effect=FileNotFoundError)
        )
    text = {
        "suffix": "赤金赤金",
        "repeated_prefix": "级级作战记录",
        "zoom": "中级作战记录",
        "missing_template": "赤金",
    }[case]
    ocr = Mock(return_value=([[text, 1.0]], []))
    monkeypatch.setattr(base.rapidocr, "engine", ocr)
    result = solver_for(frame)._visible_manufacture_product()
    assert result == {"zoom": "exp3", "missing_template": "gold"}.get(case)
    assert ocr.call_count == 1
    assert ocr.call_args.kwargs == dict(use_det=False, use_cls=False, use_rec=True)


@pytest.mark.parametrize(
    "filename",
    [
        "b303_product_opening_20261123.jpg",
        "b303_product_settled_20261123.jpg",
        "adjusted_total.jpg",
    ],
)
def test_manufacture_detail_gold_without_ocr(filename):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = Recognizer(None, (FIXTURES / filename).read_bytes())
    solver._product_ocr_text = Mock(side_effect=AssertionError("unexpected OCR"))
    assert solver.read_manufacture_product() == "gold"
    solver._product_ocr_text.assert_not_called()


@pytest.mark.parametrize("partial", [False, True])
def test_manufacture_detail_requires_all_six_record_characters(partial):
    title = bytes2img((FIXTURES / "detail_exp3_20261018.webp").read_bytes())
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[330:430, 1540:1835] = title
    if partial:
        frame[365:402, 1570:1608] = frame[365:402, 1608:1646].copy()
    solver = solver_for(frame)
    solver._product_ocr_text = Mock(return_value="级级作战记录")
    if partial:
        with pytest.raises(RecognizeError, match="无法识别当前制造产物"):
            solver.read_manufacture_product()
        assert solver._product_ocr_text.call_count == 2
    else:
        assert solver.read_manufacture_product() == "exp3"
        solver._product_ocr_text.assert_not_called()


@pytest.mark.parametrize(
    ("material", "expected"),
    [("固源岩", "orirock"), ("装置", "orirock_device"), ("", None)],
)
def test_missing_title_keeps_detail_material_read(material, expected):
    frame = bytes2img((FIXTURES / "b303_product_settled_20261123.jpg").read_bytes())
    frame[364:405, 1640:1683] = 50
    solver = solver_for(frame)
    solver._product_ocr_text = Mock(side_effect=["源石碎片", material])
    if expected:
        assert solver.read_manufacture_product() == expected
    else:
        with pytest.raises(RecognizeError, match="源石碎片配方"):
            solver.read_manufacture_product()
    assert [call.args[0] for call in solver._product_ocr_text.call_args_list] == [
        ((1540, 330), (1835, 430)),
        ((430, 330), (650, 430)),
    ]


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, ("lmd", True)), (1, ("lmd", False)), (2, ("orundum", True))],
)
def test_open_and_locked_trade_cards_without_ocr(index, expected):
    solver = solver_for(card(index))
    solver._product_ocr_text = Mock(side_effect=AssertionError("unexpected OCR"))
    assert solver._read_trade_product_card() == expected
    solver._product_ocr_text.assert_not_called()


@pytest.mark.parametrize(
    ("index", "roi"),
    [
        (0, (slice(912, 957), slice(1606, 1694))),
        (1, (slice(978, 1007), slice(1544, 1564))),
        (2, (slice(956, 1003), slice(1652, 1694))),
    ],
)
def test_partial_trade_words_request_ocr(index, roi):
    frame = card(index)
    frame[roi] = 20
    solver = solver_for(frame)
    solver._product_ocr_text = Mock(return_value="")
    with pytest.raises(RecognizeError, match="订单类型"):
        solver._read_trade_product_card()
    solver._product_ocr_text.assert_called_once_with(((1400, 840), (1810, 1040)))


@pytest.mark.parametrize(("index", "other"), [(0, 2), (2, 0)])
def test_disagreeing_readable_trade_fields_cannot_authorize_a_switch(index, other):
    frame = card(index)
    frame[912:1003, 1606:1694] = card(other)[912:1003, 1606:1694]
    solver = solver_for(frame)
    solver._product_ocr_text = Mock(side_effect=AssertionError("conflicting card"))
    with pytest.raises(RecognizeError, match="底色不一致"):
        solver._read_trade_product_card()
    solver._product_ocr_text.assert_not_called()


def test_foreign_layout_can_recover_through_scaled_trade_ocr():
    frame = cv2.resize(card(0), (1280, 720))
    solver = solver_for(frame)
    solver.recog.w, solver.recog.h = 1280, 720
    solver._product_ocr_text = Mock(return_value="贸易站3级后可切换")
    assert solver._read_trade_product_card() == ("lmd", False)
    solver._product_ocr_text.assert_called_once_with(((933, 560), (1206, 693)))
