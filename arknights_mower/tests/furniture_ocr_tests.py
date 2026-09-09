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
        ("stock_17_16", "专业键盘架", 17, 16),
        ("quoted_name", "“全是兔兔”糖果机", 1, None),
        ("rabbit_name", "兔兔拍立得相机", 1, None),
        ("short_quoted_name", "“食为天”", 1, None),
        ("missing_quotes", "“梅雨时山水”", 2, None),
        ("missing_quotes_bed", "“新绿季浅睡”", 2, None),
    ],
)
def test_real_panel_ocr(monkeypatch, ocr, fixture, name, stock, batch):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    assert furniture.furniture_details(img, stock, batch) == (name, stock)
    if batch is not None:
        assert furniture.furniture_batch(img) == batch


def test_real_list_quantity_ignores_hallucinated_blank_text(monkeypatch, ocr):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture/list_quantity.png"
    img = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    cards = furniture.furniture_cards(img)
    assert [count for _, count in cards] == [1, 1, 1, 1]
    assert cards[0][0][0] < cards[1][0][0]
    assert cards[2][0][0] < cards[3][0][0]
