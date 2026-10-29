import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import config, graph, rapidocr
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.scene import Scene, SceneComment
from arknights_mower.utils.solver import BaseSolver, StrategyError

FIXTURES = Path(__file__).parent / "fixtures" / "clue"
ORIGINAL = "clue_access_record_20261029.jpg"
OTHER_FRAMES = sorted(
    path.name
    for path in FIXTURES.iterdir()
    if path.suffix in {".png", ".jpg"}
    and path.name not in {ORIGINAL, "clue_access_record_video.png"}
)
OTHER_NATIVE_FRAMES = sorted(
    path
    for path in FIXTURES.parent.rglob("*")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    and path.parent != FIXTURES
    and bytes2img(path.read_bytes()).shape[:2] == (1080, 1920)
)


@pytest.fixture(autouse=True)
def no_ocr(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Access Records recognition must not initialize or call OCR")

    monkeypatch.setattr(rapidocr, "engine", forbidden)
    monkeypatch.setattr(rapidocr, "initialize_ocr", forbidden)
    monkeypatch.setattr(config, "stop_mower", Event())


def frame(filename=ORIGINAL):
    image = bytes2img((FIXTURES / filename).read_bytes())
    if image.shape[:2] != (1080, 1920):
        image = cv2.resize(image, (1920, 1080), interpolation=cv2.INTER_AREA)
    return image


def observation(image):
    device = SimpleNamespace(check_current_focus=lambda: False)
    recognizer = Recognizer(device, (FIXTURES / ORIGINAL).read_bytes())
    recognizer._img = image
    recognizer._gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    recognizer._matcher = None
    return recognizer


@pytest.mark.parametrize("filename", [ORIGINAL, "clue_access_record_video.png"])
def test_access_record_has_its_own_global_scene_without_ocr(filename):
    recognizer = observation(frame(filename))

    assert recognizer.find("clue/access_record") is not None
    assert recognizer.get_scene() == Scene.CLUE_ACCESS_RECORD


@pytest.mark.parametrize("background", ["black", "blue", "noise", "room"])
def test_only_title_foreground_is_required(background):
    original = frame()
    if background == "noise":
        image = np.random.default_rng(29).integers(
            0, 180, original.shape, dtype=np.uint8
        )
    elif background == "room":
        image = frame("clue_live_room_details.png")
    else:
        image = np.empty_like(original)
        image[:] = (0, 0, 0) if background == "black" else (72, 95, 120)

    title = original[281:333, 845:1062]
    foreground = (title.min(axis=2) >= 190) & (
        title.max(axis=2).astype(np.int16) - title.min(axis=2) <= 40
    )
    image[281:333, 845:1062][foreground] = title[foreground]
    recognizer = observation(image)

    assert recognizer.get_scene() == Scene.CLUE_ACCESS_RECORD


@pytest.mark.parametrize("quality", [40, 75, 95])
def test_access_record_survives_jpeg_recompression(quality):
    _, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(frame(), cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )

    assert (
        observation(bytes2img(encoded.tobytes())).get_scene()
        == Scene.CLUE_ACCESS_RECORD
    )


@pytest.mark.parametrize(
    "variant",
    ["no_title", "white_block", "half_title", "mirrored", "misplaced"],
)
def test_incomplete_or_wrong_foreground_does_not_identify_access_record(variant):
    image = frame()
    title = image[281:333, 845:1062].copy()
    if variant == "half_title":
        image[281:333, 954:1062] = 0
    else:
        image[250:365, 800:1120] = 0
        if variant == "white_block":
            image[281:333, 845:1062] = 255
        elif variant == "mirrored":
            image[281:333, 845:1062] = title[:, ::-1]
        elif variant == "misplaced":
            image[281:333, 400:617] = title

    assert observation(image).find("clue/access_record") is None


def test_access_record_does_not_require_orange_mark():
    image = frame()
    image[160:205, 850:1100] = 0

    assert observation(image).get_scene() == Scene.CLUE_ACCESS_RECORD


@pytest.mark.parametrize("filename", OTHER_FRAMES)
def test_other_reception_and_reward_pages_are_not_access_records(filename):
    assert observation(frame(filename)).find("clue/access_record") is None


@pytest.mark.parametrize(
    "path",
    OTHER_NATIVE_FRAMES,
    ids=lambda path: path.relative_to(FIXTURES.parent).as_posix(),
)
def test_other_native_screenshots_are_not_access_records(path):
    image = bytes2img(path.read_bytes())

    assert observation(image).find("clue/access_record") is None


@pytest.mark.parametrize(
    "background_match", ["nav_bar", "infra_overview", "factory_tag"]
)
def test_access_record_overrides_background_scene_matches(background_match):
    recognizer = observation(frame())
    real_find = recognizer.find

    def find(resource, *args, **kwargs):
        if resource == "connecting":
            return None
        if resource == background_match:
            return ((0, 0), (10, 10))
        return real_find(resource, *args, **kwargs)

    recognizer.find = find

    assert recognizer.get_scene() == Scene.CLUE_ACCESS_RECORD


def test_connecting_keeps_priority_over_access_record():
    recognizer = observation(frame())
    real_find = recognizer.find
    recognizer.find = lambda resource, *args, **kwargs: (
        ((0, 0), (10, 10))
        if resource == "connecting"
        else real_find(resource, *args, **kwargs)
    )

    assert recognizer.get_scene() == Scene.CONNECTING


def test_access_record_scene_metadata_agrees_with_runtime_data():
    scenes = json.loads(
        (Path(__file__).parents[1] / "data" / "scene.json").read_text("utf-8")
    )

    assert Scene.CLUE_ACCESS_RECORD == 233
    assert scenes["233"]["label"] == "CLUE_ACCESS_RECORD"
    assert scenes["233"]["comment"] == SceneComment[233]


@pytest.mark.parametrize("closes", [False, True])
def test_navigation_dismisses_access_record_once_and_stops_if_unchanged(closes):
    solver = object.__new__(graph.SceneGraphSolver)
    state = SimpleNamespace(scene=Scene.CLUE_ACCESS_RECORD, clicks=[])
    solver.scene = lambda: state.scene
    solver.recog = SimpleNamespace(update=Mock())
    solver.sleep = Mock()

    def tap(position, *_args, **_kwargs):
        state.clicks.append(position)
        if len(state.clicks) > 1:
            pytest.fail("Navigation repeated Access Records dismissal")
        if closes:
            state.scene = Scene.CLUE_MESSAGE_BOARD

    solver.tap = tap
    solver.scene_graph_navigation(Scene.CLUE_MESSAGE_BOARD)

    assert state.clicks == [(960, 540)]
    assert state.scene == (
        Scene.CLUE_MESSAGE_BOARD if closes else Scene.CLUE_ACCESS_RECORD
    )
    assert solver.recog.update.call_count <= 6


def test_basic_home_navigation_closes_record_before_trying_background_navigation():
    solver = object.__new__(BaseSolver)
    state = SimpleNamespace(scene=Scene.CLUE_ACCESS_RECORD)
    solver.scene = lambda: state.scene
    solver.recog = SimpleNamespace(update=Mock())
    solver.sleep = Mock()
    solver.tap = Mock(
        side_effect=lambda *_: setattr(state, "scene", Scene.CLUE_MESSAGE_BOARD)
    )

    def get_navigation():
        assert state.scene == Scene.CLUE_MESSAGE_BOARD
        state.scene = Scene.INDEX
        return True

    solver.get_navigation = Mock(side_effect=get_navigation)
    solver.tap_nav_element = Mock()

    solver.back_to_index()

    solver.tap.assert_called_once_with((960, 540))
    solver.get_navigation.assert_called_once_with()
    solver.tap_nav_element.assert_called_once_with("index")


def reappearing_record_navigation(solver_type, interruption, brief_board):
    solver = object.__new__(solver_type)
    state = SimpleNamespace(clicks=[], reads=0, observed=[])
    after_click = iter(
        [interruption]
        + ([Scene.CLUE_MESSAGE_BOARD] if brief_board else [])
        + [Scene.CLUE_ACCESS_RECORD] * 10
    )

    def scene():
        state.reads += 1
        if state.reads > 16:
            pytest.fail("Navigation did not finish after Access Records reappeared")
        value = (
            next(after_click, Scene.CLUE_ACCESS_RECORD)
            if state.clicks
            else Scene.CLUE_ACCESS_RECORD
        )
        state.observed.append(value)
        return value

    def tap(position, *_args, **_kwargs):
        state.clicks.append(position)
        if len(state.clicks) > 1:
            pytest.fail("Navigation clicked the reappearing Access Records again")

    solver.scene = scene
    solver.tap = tap
    solver.recog = SimpleNamespace(update=Mock())
    solver.sleep = Mock()
    solver.get_navigation = Mock(
        side_effect=lambda: pytest.fail("Navigation used the covered background")
    )
    return solver, state


@pytest.mark.parametrize("interruption", [Scene.UNKNOWN, Scene.LOADING])
@pytest.mark.parametrize("brief_board", [False, True])
def test_graph_navigation_does_not_click_record_again_after_interrupted_observations(
    interruption, brief_board
):
    solver, state = reappearing_record_navigation(
        graph.SceneGraphSolver, interruption, brief_board
    )

    solver.scene_graph_navigation(Scene.CLUE_MESSAGE_BOARD)

    assert state.clicks == [(960, 540)]
    assert interruption in state.observed
    assert state.observed[-1] == Scene.CLUE_ACCESS_RECORD
    assert solver.recog.update.call_count <= 4
    if not brief_board:
        assert solver.recog.update.call_count == 4


@pytest.mark.parametrize("interruption", [Scene.UNKNOWN, Scene.LOADING])
@pytest.mark.parametrize("brief_board", [False, True])
def test_basic_home_navigation_does_not_click_record_again_after_interrupted_observations(
    interruption, brief_board
):
    solver, state = reappearing_record_navigation(BaseSolver, interruption, brief_board)

    with pytest.raises(StrategyError):
        solver.back_to_index()

    assert state.clicks == [(960, 540)]
    assert interruption in state.observed
    assert state.observed[-1] == Scene.CLUE_ACCESS_RECORD
    assert solver.recog.update.call_count <= 4
    if not brief_board:
        assert solver.recog.update.call_count == 4
    solver.get_navigation.assert_not_called()
