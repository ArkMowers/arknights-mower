import lzma
import pickle
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import depotREC as module
from arknights_mower.utils.image import bytes2img

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.fixture
def pixel_solver(monkeypatch):
    monkeypatch.setattr(
        module.rapidocr, "engine", module.rapidocr.create_engine(threads=2)
    )
    solver = module.depotREC.__new__(module.depotREC)
    solver.物品数字 = module.导入_数字模板()
    solver.结果字典 = {}
    return solver


@pytest.fixture
def normal_model():
    with lzma.open(Path(module.__rootdir__) / "models" / "NORMAL.pkl", "rb") as stream:
        return pickle.load(stream)


def test_recorded_depot_scan_does_not_read_lmd_icon_as_digit(
    pixel_solver, normal_model
):
    frame = bytes2img((FIXTURES / "depot_basic_lmd_20261031.jpg").read_bytes())
    pixel_solver.recog = SimpleNamespace(img=frame)

    pixel_solver.分类扫描(normal_model)

    assert pixel_solver.结果字典["龙门币"] == 7214000


def test_earlier_recorded_lmd_item_retains_complete_amount(pixel_solver, normal_model):
    frame = bytes2img((FIXTURES / "depot_all_20261018.jpg").read_bytes())
    item, gray, _ = pixel_solver.切图主程序(frame[140:1000])[4]

    assert pixel_solver.匹配物品一次(item, gray, normal_model) == ["龙门币", 7512000]


@pytest.mark.parametrize(
    "text,expected", [("1721.4万", 17214000), ("9999.9万", 99999000)]
)
def test_constructed_wide_amount_preserves_true_leading_digits(
    pixel_solver, text, expected
):
    # Constructed bands reuse game glyphs; they are not recorded game amounts.
    gray = bytes2img(
        (FIXTURES / "depot_basic_lmd_20261031.jpg").read_bytes(), gray=True
    )
    glyphs = {
        "1": gray[600:650, 407:421],
        "2": gray[600:650, 386:402],
        "4": gray[600:650, 434:451],
        "7": gray[600:650, 368:384],
        "9": gray[600:650, 1597:1613],
        ".": gray[600:650, 426:430],
        "万": gray[600:650, 454:483],
    }
    band = np.zeros((50, 180), dtype=np.uint8)
    x = 165 - sum(glyphs[char].shape[1] for char in text) - 3 * (len(text) - 1)
    for char in text:
        glyph = glyphs[char]
        band[:, x : x + glyph.shape[1]] = glyph
        x += glyph.shape[1] + 3

    assert pixel_solver.读取龙门币数字(band) == expected
