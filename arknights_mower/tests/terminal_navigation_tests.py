from pathlib import Path
from unittest.mock import Mock, call

import cv2
import numpy as np
import pytest

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import RecognizeError, Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver

FIXTURES = Path(__file__).parent / "fixtures" / "terminal"


@pytest.fixture
def terminal_solver():
    device = Mock()
    frame = (FIXTURES / "seven_tabs_20261118.jpg").read_bytes()
    solver = object.__new__(BaseSolver)
    solver.device = device
    solver.recog = Recognizer(device, frame)
    solver.sleep = Mock()
    return solver


@pytest.mark.parametrize(
    "method", ["get_scene", "get_ra_scene", "get_sf_scene", "get_sss_scene"]
)
def test_terminal_scene_uses_visible_home_tab_without_full_search(
    terminal_solver, method
):
    reader = terminal_solver.recog
    reader.find = Mock(wraps=reader.find)
    cv2.setRNGSeed(18)

    assert getattr(reader, method)() == Scene.TERMINAL_MAIN
    assert call("terminal_main") not in reader.find.call_args_list
    terminal_solver.device.screencap.assert_not_called()


def test_shifted_terminal_tab_still_confirms_the_scene(terminal_solver):
    reader = terminal_solver.recog
    frame = reader.gray.copy()
    height, width = loadres("terminal_main", True).shape
    frame[754 : 754 + height, 320 : 320 + width] = frame[
        959 : 959 + height, 90 : 90 + width
    ]
    frame[959 : 959 + height, 90 : 90 + width] = 0
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))
    reader.find = Mock(wraps=reader.find)

    assert reader.get_sss_scene() == Scene.TERMINAL_MAIN
    reader.find.assert_any_call("terminal_main")
    assert reader.find("terminal_main") == ((320, 754), (320 + width, 754 + height))


def test_terminal_coordinates_still_return_the_best_full_screen_match(terminal_solver):
    reader = terminal_solver.recog
    frame = reader.gray.copy()
    template = loadres("terminal_main", True)
    height, width = template.shape
    frame[754 : 754 + height, 320 : 320 + width] = template
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))

    assert reader.get_sss_scene() == Scene.TERMINAL_MAIN
    assert reader.find("terminal_main") == ((320, 754), (320 + width, 754 + height))


def test_connecting_overlay_takes_priority_over_visible_terminal_tab(terminal_solver):
    reader = terminal_solver.recog
    frame = reader.gray.copy()
    connecting = loadres("connecting", True)
    height, width = connecting.shape
    frame[978 : 978 + height, 1087 : 1087 + width] = connecting
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))

    assert reader.get_scene() == Scene.CONNECTING


def test_partially_obscured_terminal_tab_uses_full_screen_threshold(terminal_solver):
    reader = terminal_solver.recog
    frame = reader.gray.copy()
    template = loadres("terminal_main", True)
    height, width = template.shape
    tab = frame[959 : 959 + height, 90 : 90 + width]
    tab[:, :16] = np.median(template)
    assert 0.9 < cv2.matchTemplate(tab, template, cv2.TM_CCOEFF_NORMED)[0, 0] < 0.98
    reader.set_frame((None, cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB), frame))
    reader.find = Mock(wraps=reader.find)

    assert reader.get_sss_scene() == Scene.TERMINAL_MAIN
    reader.find.assert_any_call("terminal_main")


@pytest.mark.parametrize(
    ("name", "center_x"),
    [
        ("main_theme", 407),
        ("collection", 682),
        ("regular", 957),
        ("longterm", 1232),
        ("contract", 1505),
    ],
)
def test_navigates_to_visible_tab_after_garrison_was_added(
    terminal_solver, name, center_x
):
    terminal_solver.tap_terminal_button(name)

    terminal_solver.device.tap.assert_called_once()
    x, y = terminal_solver.device.tap.call_args.args[0]
    assert abs(x - center_x) <= 10
    assert 980 <= y <= 1030


def test_tab_matches_when_garrison_is_selected(terminal_solver):
    bottom = cv2.imread(str(FIXTURES / "garrison_bottom_20261118.png"))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[960:1050] = bottom
    _, packet = cv2.imencode(".png", frame)
    terminal_solver.recog = Recognizer(terminal_solver.device, packet.tobytes())

    terminal_solver.tap_terminal_button("main")

    terminal_solver.device.tap.assert_called_once_with((133, 1006))


@pytest.mark.parametrize(("name", "center_x"), [("regular", 1125), ("longterm", 1445)])
def test_navigates_to_tab_at_the_previous_layout_position(
    terminal_solver, name, center_x
):
    frame = np.full((1080, 1920, 3), 205, dtype=np.uint8)
    current = terminal_solver.recog.img
    for current_x, previous_x in [(407, 485), (682, 800), (957, 1125), (1232, 1445)]:
        frame[960:1050, previous_x - 64 : previous_x + 64] = current[
            960:1050, current_x - 64 : current_x + 64, ::-1
        ]
    _, packet = cv2.imencode(".png", frame)
    terminal_solver.recog = Recognizer(terminal_solver.device, packet.tobytes())

    terminal_solver.tap_terminal_button(name)

    terminal_solver.device.tap.assert_called_once()
    x, _ = terminal_solver.device.tap.call_args.args[0]
    assert abs(x - center_x) <= 10


@pytest.mark.parametrize(("task", "center_x"), [("sss", 957), ("reclamation", 1232)])
def test_large_task_uses_detected_tab_from_terminal_home(
    terminal_solver, task, center_x
):
    assert terminal_solver.scene() == Scene.TERMINAL_MAIN
    terminal_solver.device.tap.side_effect = MowerExit

    with pytest.raises(MowerExit):
        if task == "sss":
            terminal_solver.to_sss(1, 1)
        else:
            terminal_solver.to_reclamation("Tales", 0)

    terminal_solver.device.tap.assert_called_once()
    x, _ = terminal_solver.device.tap.call_args.args[0]
    assert abs(x - center_x) <= 10


def test_unrecognized_tab_does_not_tap(terminal_solver):
    _, packet = cv2.imencode(".png", np.zeros((1080, 1920), dtype=np.uint8))
    terminal_solver.recog = Recognizer(terminal_solver.device, packet.tobytes())

    with pytest.raises(RecognizeError):
        terminal_solver.tap_terminal_button("regular")

    terminal_solver.device.tap.assert_not_called()


@pytest.mark.parametrize(
    ("marker", "x", "y"),
    [
        ("main_theme", 283, 945),
        ("main_theme", 335, 945),
        ("collection", 1005, 943),
        ("collection", 611, 943),
    ],
)
def test_recognizes_selected_tab_at_both_positions(marker, x, y):
    template = loadres(marker, gray=True)
    frame = np.full((1080, 1920), int(np.median(template)), dtype=np.uint8)
    h, w = template.shape
    frame[y : y + h, x : x + w] = template
    _, packet = cv2.imencode(".png", frame)
    recognizer = Recognizer(Mock(), packet.tobytes())

    assert recognizer.find(marker) == ((x, y), (x + w, y + h))
