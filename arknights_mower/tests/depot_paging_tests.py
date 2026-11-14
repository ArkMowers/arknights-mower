"""Offline coverage of depot category boundaries and overlapping horizontal pages."""

import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import depotREC as module

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.fixture
def paged(monkeypatch):
    rng = np.random.default_rng(72)
    world = rng.integers(0, 256, size=(810, 3420, 1), dtype=np.uint8)
    state = SimpleNamespace(offset=1000, clock=0, moves=[], corrupt=False)
    solver = module.depotREC.__new__(module.depotREC)
    solver._category_x = 1063
    solver._seen_names = set()
    solver._unconfirmed_names = set()
    solver.结果字典 = {}

    def render():
        image = np.full((1080, 1920, 3), 230, dtype=np.uint8)
        image[140:950] = world[:, state.offset : state.offset + 1920]
        return image

    solver.recog = SimpleNamespace(img=render())
    state.render = render

    def swipe(start, movement, **kwargs):
        state.moves.append(movement[0])
        state.clock += 1
        state.offset = min(1500, max(0, state.offset - movement[0]))
        solver.recog.img = render()
        if state.corrupt and movement[0] < 0:
            solver.recog.img[140:950] = 0

    solver.swipe_noinertia = Mock(side_effect=swipe)
    solver._wait_for_depot_ready = Mock(return_value=True)
    solver._category_selected = Mock(return_value=True)
    monkeypatch.setattr(module, "monotonic", lambda: state.clock)
    return SimpleNamespace(solver=solver, state=state)


def test_category_scan_returns_to_start_and_confirms_the_final_boundary(paged):
    frames = list(paged.solver._category_frames())

    assert [offset for offset, _ in frames] == [0, 702, 1404, 1500]
    assert paged.state.moves == [702, 702, 702, -702, -702, -702, -702]
    assert all(frame.shape == (1080, 1920, 3) for _, frame in frames)


def test_overlapping_and_short_final_pages_count_each_grid_column_once(paged):
    paged.solver.匹配物品一次 = Mock(return_value=("应急理智顶液", 1))

    assert paged.solver.分类扫描({}) is False

    # A 1500px offset exposes columns 0..13; there are three slots per column.
    assert paged.solver.结果字典 == {"应急理智顶液": 42}
    assert paged.solver.匹配物品一次.call_count == 42


def test_unmatched_page_movement_does_not_claim_complete_coverage(paged):
    paged.state.corrupt = True
    with pytest.raises(module._DepotScanIncomplete):
        list(paged.solver._category_frames())


@pytest.mark.parametrize("initial_offset", [0, 1000])
def test_category_swipe_limit_bounds_start_and_end_search(paged, initial_offset):
    paged.state.offset = initial_offset
    paged.solver.recog.img = paged.state.render()
    paged.solver.CATEGORY_SWIPE_LIMIT = 1
    with pytest.raises(module._DepotScanIncomplete):
        list(paged.solver._category_frames())
    assert len(paged.state.moves) <= 2


def test_category_timeout_stops_without_yielding_a_complete_scan(paged):
    paged.solver.CATEGORY_SCAN_TIMEOUT = 0.5
    with pytest.raises(module._DepotScanIncomplete):
        list(paged.solver._category_frames())
    assert paged.state.moves == [702]


@pytest.mark.parametrize("failure", ["scene", "category"])
def test_lost_depot_or_selected_category_interrupts_paging(paged, failure):
    if failure == "scene":
        paged.solver._wait_for_depot_ready.return_value = False
    else:
        paged.solver._category_selected.return_value = False
    with pytest.raises(module._DepotScanIncomplete):
        list(paged.solver._category_frames())


@pytest.mark.parametrize(
    "filename,selected",
    [
        ("depot_all_20261018.jpg", 835),
        ("depot_consume_expiring_20261018.jpg", 1063),
        ("depot_basic_lmd_20261031.jpg", 1298),
    ],
)
def test_recorded_category_highlight_precedes_absence_inference(filename, selected):
    solver = module.depotREC.__new__(module.depotREC)
    solver.recog = SimpleNamespace(
        gray=cv2.imread(str(FIXTURES / filename), cv2.IMREAD_GRAYSCALE)
    )
    for x in (835, 1063, 1298):
        assert bool(solver._category_selected(x)) is (x == selected)


def test_ambiguous_uniform_content_cannot_establish_movement():
    frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    with pytest.raises(module._DepotScanIncomplete):
        module.depotREC._depot_scroll_distance(frame, frame)


def test_zero_scope_follows_installed_category_models_and_excludes_cloud_items(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(module.SceneGraphSolver, "__init__", lambda *a, **k: None)
    monkeypatch.setattr(
        module, "resource_pkg_path", lambda path: Path(module.__rootdir__).parent / path
    )
    monkeypatch.setattr(module, "get_path", lambda _: tmp_path / "depotresult.csv")

    solver = module.depotREC()

    assert {"技术调查补给", "罗德岛迎春红包"} <= solver._category_scopes[1063]
    assert {"合成玉", "可露希尔珍藏券I"} <= solver._category_scopes[1298]
    assert not {"龙门币", "赤金", "固源岩组"} & (
        solver._category_scopes[1063] | solver._category_scopes[1298]
    )
