"""Replay depot frames captured from alexsun on 2026-10-18, without a device."""

import socket
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from arknights_mower.utils.recognize import Recognizer, Scene

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    "filename",
    ["depot_all_20261018.jpg", "depot_consume_expiring_20261018.jpg"],
)
def test_depot_scene_with_expiring_items(filename):
    device = Mock()
    recognizer = Recognizer(device, screencap=(FIXTURES / filename).read_bytes())
    recognizer.check_freeze = Mock()

    assert recognizer.find("depot") is not None
    assert recognizer.get_scene() == Scene.DEPOT
    device.assert_not_called()
    assert device.mock_calls == []


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
