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
    assert paged.state.moves == [702, 702, 702, 234, -702, -702, -702, -702, -234]
    assert all(frame.shape == (1080, 1920, 3) for _, frame in frames)


def test_category_paging_uses_standard_drag_and_slower_boundary_checks(paged):
    solver = paged.solver
    original_swipe = solver.swipe_noinertia.side_effect

    def send_swipe(points, *, durations, up_wait, capture):
        (x0, y0), *_, (x1, y1) = points
        movement = (x1 - x0, y1 - y0)
        assert durations == [200, {702: 140, 234: 400}[abs(movement[0])], 200]
        assert up_wait == 400
        assert capture is True
        original_swipe(points[0], movement)
        return solver.recog.img

    solver.device = SimpleNamespace(swipe_ext=Mock(side_effect=send_swipe))
    solver.recog.set_frame = Mock()
    solver.sleep = Mock()
    solver.swipe_noinertia = module.SceneGraphSolver.swipe_noinertia.__get__(solver)

    assert [offset for offset, _ in solver._category_frames()] == [0, 702, 1404, 1500]
    assert solver.device.swipe_ext.call_count == 9


@pytest.mark.parametrize("ignored_at, direction", [(1000, 702), (702, -702)])
def test_missed_swipe_before_boundary_still_scans_all_columns(
    paged, ignored_at, direction
):
    solver, state = paged.solver, paged.state
    original_swipe = solver.swipe_noinertia.side_effect
    ignored = False
    solver.匹配物品一次 = Mock(return_value=("应急理智顶液", 1))

    def swipe(start, movement, **kwargs):
        nonlocal ignored
        if not ignored and state.offset == ignored_at and movement[0] == direction:
            ignored = True
            state.moves.append(movement[0])
            state.clock += 1
            return
        original_swipe(start, movement, **kwargs)

    solver.swipe_noinertia.side_effect = swipe

    assert solver.分类扫描({}) is False

    assert ignored
    assert state.offset == 1500
    assert solver.结果字典 == {"应急理智顶液": 42}


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


@pytest.mark.parametrize(
    "limit,moves", [(1, [702]), (4, [702, 234, -702, -702, -702, -702])]
)
def test_category_swipe_limit_includes_boundary_check(paged, limit, moves):
    paged.state.offset = 0
    paged.solver.recog.img = paged.state.render()
    paged.solver.CATEGORY_SWIPE_LIMIT = limit
    with pytest.raises(module._DepotScanIncomplete):
        list(paged.solver._category_frames())
    assert paged.state.moves == moves


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


def test_recorded_right_boundary_ignores_small_rendering_changes(monkeypatch):
    def frame(name):
        image = cv2.imread(str(FIXTURES / "depot" / name))
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    left = frame("consume_left_20261117.webp")
    right = frame("consume_right_before_20261117.webp")
    boundary = frame("consume_right_after_20261117.webp")
    solver = module.depotREC.__new__(module.depotREC)
    solver.recog = SimpleNamespace(img=left)
    solver._category_x = 1063
    solver._wait_for_depot_ready = Mock(return_value=True)
    solver._category_selected = Mock(return_value=True)
    moves = iter([left, left, right, boundary, boundary])

    def swipe(*_args, **_kwargs):
        solver.recog.img = next(moves)

    solver.swipe_noinertia = Mock(side_effect=swipe)
    monkeypatch.setattr(module, "monotonic", lambda: 0)

    pages = list(solver._category_frames())

    assert [offset for offset, _ in pages] == [0, 574]
    assert solver.swipe_noinertia.call_count == 5


@pytest.mark.parametrize("distance", [1, 24, 107, 234])
def test_recorded_content_movement_is_not_a_boundary(distance):
    frame = cv2.imread(str(FIXTURES / "depot/consume_right_before_20261117.webp"))
    shifted = frame.copy()
    shifted[140:950] = np.roll(frame[140:950], distance, axis=1)

    assert not module.depotREC._same_depot_view(frame, shifted)


def replay_consumable_pages(frame, captures):
    solver = module.depotREC.__new__(module.depotREC)
    solver.recog = SimpleNamespace(img=frame)
    solver._category_x = 1063
    solver._wait_for_depot_ready = Mock(return_value=True)
    solver._category_selected = Mock(return_value=True)
    frames = iter(captures)

    def swipe(*args, **kwargs):
        solver.recog.img = next(frames)

    solver.swipe_noinertia = Mock(side_effect=swipe)
    pages = list(solver._category_frames())
    swipes = [call.args[1][0] for call in solver.swipe_noinertia.call_args_list]
    return pages, swipes


def test_depot_paging_ignores_fixed_background_at_the_edge_of_the_overlap():
    image = cv2.imread(str(FIXTURES / "depot_consume_expiring_20261018.jpg"))
    frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    shifted = frame.copy()
    shifted[140:990] = np.roll(frame[140:990], -341, axis=1)
    shifted[140:990, :32] = frame[140:990, :32]

    pages, swipes = replay_consumable_pages(
        frame, [frame, frame, shifted, shifted, shifted]
    )

    assert [offset for offset, _ in pages] == [0, 341]
    assert swipes == [702, 234, -702, -702, -234]


@pytest.mark.parametrize("retry_distance", [0, 107])
def test_stationary_consumables_with_background_change_still_check_the_next_page(
    retry_distance,
):
    image = cv2.imread(str(FIXTURES / "depot_consume_expiring_20261018.jpg"))
    frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    changed = frame.copy()
    changed[600:680, 1700:1820] = 137
    advanced = changed.copy()
    advanced[140:990] = np.roll(changed[140:990], -retry_distance, axis=1)
    advanced[970:, 1560:] = changed[970:, 1560:]
    pages, swipes = replay_consumable_pages(
        frame, [frame, frame, changed, advanced, advanced, advanced]
    )

    if retry_distance:
        assert [offset for offset, _ in pages] == [0, retry_distance]
        assert swipes == [702, 234, -702, -234, -702, -234]
    else:
        assert [offset for offset, _ in pages] == [0]
        assert swipes == [702, 234, -702, -234]


def test_single_consumable_with_background_change_confirms_the_boundary():
    image = cv2.imread(str(FIXTURES / "depot_consume_expiring_20261018.jpg"))
    frame = np.full_like(image, 255)
    frame[165:387, 15:230] = cv2.cvtColor(image[165:387, 79:294], cv2.COLOR_BGR2RGB)
    changed = frame.copy()
    changed[600:680, 1700:1820] = 137

    pages, swipes = replay_consumable_pages(frame, [frame, frame, changed, changed])

    assert [offset for offset, _ in pages] == [0]
    assert swipes == [702, 234, -702, -234]


def repeated_stack_pages(
    label_y, background_change, distinct_columns, *, template_change=False
):
    image = cv2.imread(str(FIXTURES / "depot_consume_expiring_20261018.jpg"))
    cell = np.full((1080, 234, 3), 255, dtype=np.uint8)
    row = 571 if label_y == 983 else 0
    cell[165 + row : 388 + row, 15:230] = cv2.cvtColor(
        image[165:388, 79:294], cv2.COLOR_BGR2RGB
    )
    label_background = (45, 45, 45) if label_y == 356 else (163, 199, 119)
    cv2.rectangle(cell, (150, label_y - 26), (207, label_y + 5), label_background, -1)
    shelf = np.tile(cell, (1, 10, 1))
    templates = FIXTURES.parent.parent / "resources" / "depot_num"
    digits = {
        value: cv2.imread(str(templates / f"digit_{value}.png"), cv2.IMREAD_GRAYSCALE)
        for value in (6, 8)
    }
    for column in range(10):
        digit = digits[8 if column in distinct_columns else 6]
        height, width = digit.shape
        right = column * 234 + 198
        area = shelf[label_y - height : label_y, right - width : right]
        np.maximum(area, digit[:, :, None], out=area)
    frame = shelf[:, :1920].copy()
    shifted = shelf[:, 234:2154].copy()
    if background_change:
        shifted[600:680, 1700:1820] = 137
    if template_change:
        # 降低 234 和 702 像素候选的得分，让 468 像素成为唯一最高分。
        shifted[440:456, 1010:1032] = 155
        shifted[440:456, 250:272] = 155
    return frame, shifted


@pytest.mark.parametrize(
    "label_y", [356, 412, 983], ids=["quantity", "expiration", "bottom-expiration"]
)
@pytest.mark.parametrize("background_change", [False, True])
def test_slow_swipe_reads_repeated_icons_with_different_labels(
    label_y, background_change
):
    frame, shifted = repeated_stack_pages(label_y, background_change, (5, 8))
    pages, swipes = replay_consumable_pages(
        frame, [frame, frame, frame, shifted, shifted, shifted]
    )

    assert [offset for offset, _ in pages] == [0, 234]
    assert np.array_equal(pages[-1][1], shifted)
    assert swipes == [702, 234, -702, -234, -702, -234]


@pytest.mark.parametrize("template_change", [False, True])
def test_repeated_icons_use_labels_outside_the_displacement_template(template_change):
    frame, shifted = repeated_stack_pages(
        356, False, (1,), template_change=template_change
    )
    pages, _ = replay_consumable_pages(
        frame, [frame, frame, frame, shifted, shifted, shifted]
    )

    assert [offset for offset, _ in pages] == [0, 234]


@pytest.mark.parametrize("template_change", [False, True])
def test_repeated_icons_without_a_unique_displacement_stop_the_scan(template_change):
    frame, shifted = repeated_stack_pages(
        356, False, (8,), template_change=template_change
    )

    with pytest.raises(module._DepotScanIncomplete):
        replay_consumable_pages(frame, [frame, frame, frame, shifted, shifted, shifted])


@pytest.mark.parametrize("appearing", [False, True])
def test_changed_visible_item_does_not_confirm_a_boundary(appearing):
    image = cv2.imread(str(FIXTURES / "depot_consume_expiring_20261018.jpg"))
    frame = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    missing_item = frame.copy()
    missing_item[168:375, 75:300] = 255
    before, after = (missing_item, frame) if appearing else (frame, missing_item)

    assert not module.depotREC._same_depot_view(before, after)


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
