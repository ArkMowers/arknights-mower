"""Replay depot frames captured from alexsun on 2026-10-18, without a device."""

import socket
import subprocess
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import config
from arknights_mower.utils.recognize import Recognizer, Scene

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(config, "stop_mower", Event())
    yield
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    "filename",
    [
        "depot_all_20261018.jpg",
        "depot_consume_expiring_20261018.jpg",
        "depot/consume_false_sort_20261116.jpg",
        "depot/consume_left_20261117.webp",
        "depot/consume_right_before_20261117.webp",
    ],
)
def test_depot_scene_with_expiring_items(filename):
    device = Mock()
    recognizer = Recognizer(device, screencap=(FIXTURES / filename).read_bytes())
    recognizer.check_freeze = Mock()

    assert recognizer.find("depot") is not None
    assert recognizer.get_scene() == Scene.DEPOT
    device.assert_not_called()
    assert device.mock_calls == []


def test_confirmed_vault_precedes_operator_selection_features():
    recognizer = Recognizer(
        Mock(),
        screencap=(FIXTURES / "depot/consume_false_sort_20261116.jpg").read_bytes(),
    )

    recognizer.find = Mock(wraps=recognizer.find)

    assert recognizer.get_scene() == Scene.DEPOT
    assert not any(
        call.args[0] in {"arrange_order_options", "arrange_order_options_scene"}
        for call in recognizer.find.call_args_list
    )


def test_vault_button_confirms_depot_without_lower_left_background():
    image = cv2.imread(str(FIXTURES / "depot/consume_false_sort_20261116.jpg"))
    image[950:, :300] = 0
    recognizer = Recognizer(Mock(), screencap=cv2.imencode(".png", image)[1].tobytes())

    assert recognizer.find("depot") is not None
    assert recognizer.get_scene() == Scene.DEPOT


@pytest.mark.parametrize(
    "filename",
    [
        "depot/dorm_selection_20261117.webp",
        "selection/trade_single_cleared_20261021.jpg",
        "selection/trade_single_selected_20261021.jpg",
        "selection/manufacturing_right_edge_20261010.png",
    ],
)
@pytest.mark.parametrize("changed_filter", [False, True])
def test_operator_selection_keeps_its_scene(filename, changed_filter):
    image = cv2.imread(str(FIXTURES / filename))
    if changed_filter:
        image[30:95, 1580:1780] = 0
    recognizer = Recognizer(Mock(), screencap=cv2.imencode(".png", image)[1].tobytes())

    assert recognizer.find("depot") is None
    assert recognizer.find("arrange_order_options_scene", threshold=0.9) is not None
    assert recognizer.get_scene() == Scene.INFRA_ARRANGE_ORDER


def test_incomplete_vault_title_cannot_confirm_depot():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    original = cv2.imread(str(FIXTURES / "depot/consume_false_sort_20261116.jpg"))
    image[980:1045, 1575:1770] = original[980:1045, 1575:1770]
    recognizer = Recognizer(Mock(), screencap=cv2.imencode(".png", image)[1].tobytes())

    assert recognizer.find("depot") is None


@pytest.mark.parametrize(
    "filename",
    [
        "infra/base_main.png",
        "login/startup_logo_bright_20261016.jpg",
        "login/startup_logo_fading_20261016.jpg",
    ],
)
def test_other_scenes_do_not_match_depot(filename):
    recognizer = Recognizer(Mock(), screencap=(FIXTURES / filename).read_bytes())

    assert recognizer.find("depot") is None
