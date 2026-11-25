from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import navigation
from arknights_mower.utils.stage_map_labels import read_map_stage_labels


def map_frame(*labels):
    frame = np.full((1080, 1920, 3), 127, np.uint8)
    for index, name in enumerate(labels):
        path = Path(__file__).parent / "fixtures/stage_map" / f"{name}.png"
        tile = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        x = 100 + index * 360
        h, w = tile.shape[:2]
        frame[400 : 400 + h, x : x + w] = tile
    return frame


@pytest.mark.parametrize("code", ["OS-7", "OS-9", "OS-10", "OS-EX-8"])
def test_reads_full_label_at_its_visible_position(code):
    frame = map_frame("OS-9" if code == "OS-7" else "OS-7", code)
    x, y = dict(read_map_stage_labels(frame))[code]
    assert 460 < x < 680 and 400 < y < 490


@pytest.mark.parametrize("target", ["OS-1", "0S-7", "OS-1O", "OS-8", "OS-S-8"])
def test_similar_or_absent_code_never_selects_a_label(target):
    assert target not in dict(
        read_map_stage_labels(map_frame("OS-7", "OS-10", "OS-EX-8"))
    )


def test_duplicate_or_partially_hidden_label_is_inconclusive():
    assert [code for code, _ in read_map_stage_labels(map_frame("OS-9", "OS-9"))] == [
        "OS-9",
        "OS-9",
    ]
    frame = map_frame("OS-7")
    frame[435:475, 205:245] = 127
    assert not read_map_stage_labels(frame)


@pytest.mark.parametrize("using_template", [True, False])
def test_template_precedes_ocr_and_both_record_the_selected_point(using_template):
    solver = object.__new__(navigation.NavigationSolver)
    solver.recog = SimpleNamespace(
        img=map_frame("OS-7") if using_template else map_frame()
    )
    solver._suppress_nav_recording = False
    solver.wait_for_scene_stable = MagicMock()
    solver.collect_terminal_ocr_candidates = MagicMock(
        return_value=[{"text": "OS-7", "center": (300, 600)}]
    )
    solver.tap = MagicMock()
    solver.record_nav_step = MagicMock()
    solver.persist_nav_steps = MagicMock()
    assert solver.find_target_stage_after_entry("OS-7", max_swipes=0)
    if using_template:
        solver.collect_terminal_ocr_candidates.assert_not_called()
        point = dict(read_map_stage_labels(solver.recog.img))["OS-7"]
    else:
        solver.collect_terminal_ocr_candidates.assert_called_once()
        point = (300, 600)
    solver.tap.assert_called_once_with(point, interval=0.2)
    solver.record_nav_step.assert_called_once_with(
        "tap", pos=point, text="OS-7", success=True
    )
    solver.persist_nav_steps.assert_called_once()


def test_open_chapter_accepts_another_visible_code_before_map_ocr():
    from arknights_mower.solvers.activity_navigation import ActivityNavigation

    solver = MagicMock()
    solver.stage_meta = {}
    for name in ("is_stage_code", "stage_pattern_stem", "normalize_stage_text"):
        setattr(
            solver, name, getattr(navigation.NavigationSolver, name).__get__(solver)
        )
    solver.recog.img = map_frame("OS-EX-8")
    solver.tap_and_detect_page_move.return_value = True
    navigator = ActivityNavigation(solver, shop={})
    navigator.read = MagicMock(side_effect=[[[[(20, 30)] * 4, "变革之路", 1.0]]])
    assert navigator.open_chapter("变革之路", "OS-EX-1")
    navigator.read.assert_called_once()
    solver.tap_and_detect_page_move.assert_called_once_with(
        (20, 30), "变革之路", record_step=False
    )


def test_duplicate_template_and_ocr_matches_do_not_click():
    solver = object.__new__(navigation.NavigationSolver)
    solver.recog = SimpleNamespace(img=map_frame("OS-7", "OS-7"))
    solver.wait_for_scene_stable = MagicMock()
    solver.collect_terminal_ocr_candidates = MagicMock(
        return_value=[{"text": "OS-7", "center": (x, 500)} for x in (250, 850)]
    )
    solver.swipe_noinertia = MagicMock()
    solver.record_nav_step = MagicMock()
    solver.tap = MagicMock()
    assert not solver.find_target_stage_after_entry("OS-7", max_swipes=0)
    solver.tap.assert_not_called()


@pytest.mark.parametrize(
    "target,visible,vector",
    [("OS-10", "OS-7", (-800, 0)), ("OS-7", "OS-10", (800, 0))],
)
def test_swipes_toward_target_when_ocr_misreads_visible_chapter(
    target, visible, vector
):
    solver = object.__new__(navigation.NavigationSolver)
    solver.recog = SimpleNamespace(img=map_frame(visible))
    solver._suppress_nav_recording = True
    solver.wait_for_scene_stable = MagicMock()
    solver.collect_terminal_ocr_candidates = MagicMock(
        return_value=[{"text": visible.replace("O", "0"), "center": (200, 440)}]
    )
    solver.swipe_noinertia = MagicMock(
        side_effect=lambda *args: setattr(solver.recog, "img", map_frame(target))
    )
    solver.tap = MagicMock()
    solver.record_nav_step = MagicMock()
    assert solver.find_target_stage_after_entry(target, max_swipes=1)
    assert solver.swipe_noinertia.call_args.args[1] == vector
    solver.collect_terminal_ocr_candidates.assert_called_once()
    solver.tap.assert_called_once_with(
        dict(read_map_stage_labels(solver.recog.img))[target], interval=0.2
    )


def test_ocr_cannot_overrule_a_conflicting_code_on_the_same_plate():
    solver = object.__new__(navigation.NavigationSolver)
    solver.recog = SimpleNamespace(img=map_frame("OS-7"))
    point = dict(read_map_stage_labels(solver.recog.img))["OS-7"]
    solver.wait_for_scene_stable = MagicMock()
    solver.collect_terminal_ocr_candidates = MagicMock(
        return_value=[{"text": "0S-7", "center": point}]
    )
    solver.swipe_noinertia = MagicMock()
    solver.record_nav_step = MagicMock()
    solver.tap = MagicMock()
    assert not solver.find_target_stage_after_entry("0S-7", max_swipes=0)
    solver.tap.assert_not_called()
