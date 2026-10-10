"""Recycling prompts use the base footer and shared reward navigation."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, call

import cv2
import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene

FIXTURES = Path(__file__).parent / "fixtures/infra"
NOW = datetime(2026, 10, 10, 13, 0)
RECYCLE = ((245, 986), (323, 1064))


def recognizer(name):
    return Recognizer(Mock(), (FIXTURES / name).read_bytes())


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return NOW

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    result = object.__new__(base_schedule.BaseSchedulerSolver)
    result.recog = recognizer("recycle_todo.png")
    result.last_execution = {"todo": None}
    result.todo_task = False
    result.tap = Mock()
    return result


@pytest.mark.parametrize(
    "name,scene",
    [
        ("base_main.png", Scene.INFRA_MAIN),
        ("recycle_todo.png", Scene.INFRA_TODOLIST),
        ("recycle_reward.png", Scene.MATERIEL),
    ],
)
def test_supplied_screenshot_scenes(name, scene):
    assert recognizer(name).get_scene() == scene


def test_recycling_prompt_collects_once(solver):
    assert solver.recog.find("infra_collect_recycle") == RECYCLE
    solver.todo_list()
    solver.tap.assert_called_once_with(RECYCLE)
    assert solver.last_execution["todo"] == NOW
    assert not solver.todo_task


@pytest.mark.parametrize("last", [None, NOW - timedelta(minutes=15)])
def test_first_and_due_collection(solver, last):
    solver.last_execution["todo"] = last
    solver.todo_list()
    solver.tap.assert_called_once_with(RECYCLE)
    assert solver.last_execution["todo"] == NOW


@pytest.mark.parametrize(
    "last",
    [
        NOW - timedelta(minutes=15) + timedelta(seconds=1),
        NOW,
        NOW + timedelta(minutes=1),
    ],
)
def test_cooldown_closes_todo_without_collecting(solver, last):
    solver.last_execution["todo"] = last
    solver.todo_list()
    solver.tap.assert_called_once_with((1840, 140))
    assert solver.last_execution["todo"] == last
    assert solver.todo_task


def test_other_collection_types_keep_one_tap_each(solver):
    solver.find = Mock(side_effect=lambda resource: resource)
    solver.todo_list()
    assert solver.tap.call_args_list == [
        call("infra_collect_bill"),
        call("infra_collect_factory"),
        call("infra_collect_trust"),
        call("infra_collect_recycle"),
    ]


def test_changed_quantity_keeps_prompt_recognition():
    result = recognizer("recycle_todo.png")
    result._img[986:1010, 292:315] = (39, 166, 210)
    cv2.putText(
        result._img,
        "23",
        (292, 1008),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )
    result._gray = cv2.cvtColor(result._img, cv2.COLOR_RGB2GRAY)
    assert result.find("infra_collect_recycle") == RECYCLE


def test_prompt_moves_with_other_footer_entries():
    result = recognizer("recycle_todo.png")
    result._gray[986:1064, 800:878] = result.gray[986:1064, 245:323]
    result._gray[980:1080, 240:480] = 44
    assert result.find("infra_collect_recycle") == ((800, 986), (878, 1064))


def test_missing_collection_badge_does_not_collect(solver):
    solver.recog._gray[980:1018, 289:460] = 44
    assert solver.recog.find("infra_collect_recycle") is None
    solver.todo_list()
    solver.tap.assert_called_once_with((1840, 140))


def test_prompt_outside_footer_does_not_match():
    result = recognizer("recycle_todo.png")
    result._gray[500:578, 245:323] = result.gray[986:1064, 245:323]
    result._gray[980:1080, 240:480] = 44
    assert result.find("infra_collect_recycle") is None


@pytest.mark.parametrize("resource", ["bill", "factory", "trust"])
def test_other_collection_icon_does_not_match_recycling(resource):
    result = recognizer("recycle_todo.png")
    result._gray[980:1080, 240:480] = 44
    template = loadres(f"infra_collect_{resource}", True)
    height, width = template.shape
    result._gray[986 : 986 + height, 245 : 245 + width] = template
    assert result.find("infra_collect_recycle") is None


@pytest.mark.parametrize("name", ["base_main.png", "recycle_reward.png"])
def test_non_todo_screens_have_no_recycling_prompt(name):
    assert recognizer(name).find("infra_collect_recycle") is None


def test_collection_reward_returns_through_existing_scene_graph(solver, monkeypatch):
    from arknights_mower.utils import solver as base_solver

    monkeypatch.setattr(base_solver, "csleep", lambda _: None)
    frames = [
        recognizer(name)
        for name in [
            "recycle_todo.png",
            "recycle_reward.png",
            "recycle_todo.png",
            "base_main.png",
        ]
    ]
    captures = [(frame.screencap, frame.img, frame.gray) for frame in frames]
    position = 0

    def advance(point):
        nonlocal position
        assert point == [(284, 1025), (960, 960), (1840, 140)][position]
        position += 1

    solver.device = Mock()
    solver.recog.device = solver.device
    solver.device.tap.side_effect = advance
    solver.device.screencap.side_effect = lambda: captures[position]
    solver.tap = base_solver.BaseSolver.tap.__get__(solver)
    solver.todo_list()
    assert solver.scene() == Scene.MATERIEL
    solver.transition()
    assert solver.scene() == Scene.INFRA_MAIN
    assert position == 3
    assert solver.last_execution["todo"] == NOW
    solver.device.exit.assert_not_called()
    solver.device.send_keyevent.assert_not_called()
