from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import depotREC as module
from arknights_mower.utils import depot


@pytest.fixture
def solver():
    return module.depotREC.__new__(module.depotREC)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1亿", 100000000),
        ("1.23亿", 123000000),
        ("1.01亿", 101000000),
        ("9999.9万", 99999000),
        ("12万", 120000),
        ("123456", 123456),
        ("1", 1),
        ("0", 0),
        ("１．２ 亿", 120000000),
    ],
)
def test_lmd_retains_amount_and_unit(solver, monkeypatch, text, expected):
    monkeypatch.setattr(
        module.rapidocr, "engine", Mock(return_value=([(text, 0.99)], None))
    )
    assert solver.读取龙门币数字(np.zeros((50, 180), dtype=np.uint8)) == expected


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        [("1亿", 0.5)],
        [("1亿extra", 0.99)],
        [("1.2.3亿", 0.99)],
        [("1亿2", 0.99)],
        [("-1亿", 0.99)],
        [("1", 0.99), ("亿", 0.99)],
        [("一亿", 0.99)],
        [("1.5", 0.99)],
    ],
)
def test_uncertain_lmd_is_not_a_partial_count(solver, monkeypatch, result):
    monkeypatch.setattr(module.rapidocr, "engine", Mock(return_value=(result, None)))
    assert solver.读取龙门币数字(np.zeros((50, 180), dtype=np.uint8)) is None


@pytest.mark.parametrize("name", ["龙门币", "赤金"])
def test_item_identity_selects_quantity_reader(solver, monkeypatch, name):
    monkeypatch.setattr(module, "提取特征点", lambda _: np.zeros(1))
    monkeypatch.setattr(module.vision_np, "knn1_predict", lambda *args: name)
    solver.读取龙门币数字 = Mock(return_value=100000000)
    solver.读取物品数字 = Mock(return_value=12)
    image = np.zeros((260, 260), dtype=np.uint8)
    model = dict(X=None, y=None, classes=None)
    expected = 100000000 if name == "龙门币" else 12
    assert solver.匹配物品一次(image, image, model) == [name, expected]
    reader = solver.读取龙门币数字 if name == "龙门币" else solver.读取物品数字
    np.testing.assert_array_equal(reader.call_args.args[0], image[160:210, 30:210])
    other = solver.读取物品数字 if name == "龙门币" else solver.读取龙门币数字
    other.assert_not_called()


def test_cloud_integer_count_does_not_lose_magnitude():
    payload = {
        "_mower_inventory_observed_at": 123,
        "data": {"items": [{"id": "4001", "count": "100000000"}]},
    }
    counts, _ = depot.cloud_inventory_snapshot(payload)
    assert counts["龙门币"] == 100000000


def test_lmd_initializes_shared_ocr_when_needed(solver, monkeypatch):
    engine = Mock(return_value=([("1亿", 0.99)], None))
    monkeypatch.setattr(module.rapidocr, "engine", None)
    initialize = Mock(
        side_effect=lambda: monkeypatch.setattr(module.rapidocr, "engine", engine)
    )
    monkeypatch.setattr(module.rapidocr, "initialize_ocr", initialize)
    assert solver.读取龙门币数字(np.zeros((50, 180), dtype=np.uint8)) == 100000000
    initialize.assert_called_once_with()
    assert engine.call_args.kwargs == dict(use_det=False, use_cls=False, use_rec=True)


def test_failed_ocr_leaves_lmd_unconfirmed(solver, monkeypatch):
    monkeypatch.setattr(
        module.rapidocr, "engine", Mock(side_effect=RuntimeError("OCR failed"))
    )
    assert solver.读取龙门币数字(np.zeros((50, 180), dtype=np.uint8)) is None
