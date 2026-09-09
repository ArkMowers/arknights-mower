"""实机 OCR 回归：仅保留名称、库存和份数像素，不含账号信息。"""

from pathlib import Path

import cv2
import pytest
from rapidocr_onnxruntime import RapidOCR

from arknights_mower.solvers import furniture


@pytest.fixture(scope="module")
def ocr():
    return RapidOCR()


@pytest.mark.parametrize(
    "fixture,name,stock,batch",
    [
        ("stock_3_2", "洗衣间地毯", 3, 2),
        ("stock_4_3", "长桌", 4, 3),
        ("quoted_name", "“全是兔兔”糖果机", 1, None),
        ("rabbit_name", "兔兔拍立得相机", 1, None),
        ("short_quoted_name", "“食为天”", 1, None),
    ],
)
def test_real_panel_ocr(monkeypatch, ocr, fixture, name, stock, batch):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    assert furniture.furniture_details(img, stock, batch) == (name, stock)
    if batch is not None:
        assert furniture.furniture_batch(img) == batch
