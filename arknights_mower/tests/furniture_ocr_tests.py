"""生产 OCR 配置下的实机文字带与去账号面板回归。"""

from pathlib import Path

import cv2
import pytest

from arknights_mower.solvers import furniture
from arknights_mower.utils.image import bytes2img


@pytest.fixture(scope="module", params=("local", "shared"))
def ocr(request, tmp_path_factory):
    from unittest.mock import patch

    if request.param == "shared":
        from arknights_mower.tests.ocr_test_support import service
        from arknights_mower.utils import ocr_service, ocr_shared

        directory = tmp_path_factory.mktemp("furniture-shared-ocr")
        with service(directory, factory=ocr_service._engine):
            yield ocr_shared.SharedOCREngine(directory=directory)
    else:
        with patch.object(furniture.rapidocr, "engine", None):
            furniture.rapidocr.engine = furniture.rapidocr.create_engine()
            yield furniture.rapidocr.engine


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
        ("calculator_tm", "便携TM计算器", 7, None),
        ("order_terminal", "自助点餐机", 3, None),
    ],
)
def test_real_panel_ocr(monkeypatch, ocr, fixture, name, stock, batch):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = bytes2img(path.read_bytes())
    assert furniture.furniture_details(img, stock, batch) == (name, stock)
    if batch is not None:
        assert furniture.furniture_batch(img) == batch


def test_real_list_quantities_and_row_order(monkeypatch, ocr):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture/list_quantity.png"
    img = bytes2img(path.read_bytes())
    cards = furniture.furniture_cards(img)
    assert [count for _, count in cards] == [1, 1, 1, 1]
    assert cards[0][0][0] < cards[1][0][0]
    assert cards[2][0][0] < cards[3][0][0]


@pytest.mark.parametrize(
    "fixture,name,stock,batch,enabled",
    [
        ("panel_on", "简约高脚椅", 4, 1, True),
        ("panel_off", "桌子", 2, 2, False),
    ],
)
def test_full_panel_geometry_and_keep_switch(
    monkeypatch, ocr, fixture, name, stock, batch, enabled
):
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = bytes2img(path.read_bytes())
    assert furniture.furniture_details(img, stock, batch) == (name, stock)
    assert furniture.furniture_batch(img) == batch
    assert furniture.keep_one_enabled(img) is enabled


@pytest.mark.parametrize("fixture,state", [("panel_on", "OFF"), ("panel_off", "ON")])
def test_wrong_switch_ocr_cannot_override_slider_pixels(monkeypatch, fixture, state):
    from arknights_mower.tests.furniture_tests import title

    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = bytes2img(path.read_bytes())
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        lambda *args, **kwargs: (
            [title(20, 20, "至少保留1件"), title(200, 20, state)],
            0,
        ),
    )
    with pytest.raises(ValueError, match="文字与画面冲突"):
        furniture.keep_one_enabled(img)


@pytest.mark.parametrize("width", [960, 1280, 1920, 2560])
@pytest.mark.parametrize("fixture,enabled", [("panel_on", True), ("panel_off", False)])
def test_visual_switch_state_scales_with_game_frame(width, fixture, enabled):
    path = Path(__file__).parent / "fixtures/furniture" / f"{fixture}.png"
    img = bytes2img(path.read_bytes())
    img = cv2.resize(img, (width, round(width * 9 / 16)))
    assert furniture.keep_switch_visual_state(img) is enabled
