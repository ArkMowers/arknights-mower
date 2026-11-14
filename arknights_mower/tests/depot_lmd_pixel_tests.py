import lzma
import pickle
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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
    solver = module.depotREC.__new__(module.depotREC)
    solver.物品数字 = module.导入_数字模板()
    solver.结果字典 = {}
    solver._seen_names = set()
    solver._unconfirmed_names = set()
    solver._category_frames = Mock(side_effect=lambda: iter([(0, solver.recog.img)]))
    return solver


@pytest.fixture
def normal_model():
    with lzma.open(Path(module.__rootdir__) / "models" / "NORMAL.pkl", "rb") as stream:
        return pickle.load(stream)


def test_recorded_depot_scan_skips_lmd_but_keeps_scan_only_items(
    pixel_solver, normal_model
):
    frame = bytes2img((FIXTURES / "depot_basic_lmd_20261031.jpg").read_bytes())
    pixel_solver.recog = SimpleNamespace(img=frame)

    pixel_solver.分类扫描(normal_model)

    assert "龙门币" not in pixel_solver.结果字典
    assert "合成玉" in pixel_solver.结果字典


def test_earlier_recorded_lmd_item_has_no_scanned_quantity(pixel_solver, normal_model):
    frame = bytes2img((FIXTURES / "depot_all_20261018.jpg").read_bytes())
    item, gray, _ = pixel_solver.切图主程序(frame[140:1000])[4]

    assert pixel_solver.匹配物品一次(item, gray, normal_model) == ["龙门币", None]
