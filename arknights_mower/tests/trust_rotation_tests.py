"""Offline contracts for daily Trust Rotation; no device or network access."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from arknights_mower.solvers import trust_rotation as trust
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit


def card(value, x=570, y=120, **flags):
    return trust.TrustCard(
        value,
        ((x, y), (x + 184, y + 394)),
        flags.get("selected", False),
        flags.get("assistant", False),
        flags.get("activity", False),
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("200%", 200),
        ("信赖 100％", 100),
        ("0%", 0),
        ("M 199 %", 199),
        ("201%", None),
        ("1200%", None),
        ("?%", None),
        ("200", None),
        ("%69", None),
        ("", None),
    ],
)
def test_trust_requires_explicit_bounded_percent(text, expected):
    assert trust.parse_trust(text) == expected


@pytest.mark.parametrize(
    "current,candidate,prefer,expected",
    [
        (99, 0, True, False),
        (100, 20, True, True),
        (120, 20, True, True),
        (120, 110, True, False),
        (199, 101, True, False),
        (200, 150, True, True),
        (120, 20, False, False),
        (199, 20, False, False),
        (200, 0, False, True),
        (200, 200, True, False),
        (None, 0, False, True),
        (None, 200, False, False),
    ],
)
def test_threshold_retention_and_fallback(current, candidate, prefer, expected):
    assert trust.should_replace(current, candidate, prefer, 100) is expected


def test_candidate_rosters_exclude_only_their_own_kind():
    assistant, activity, free = card(0, assistant=True), card(1, activity=True), card(2)
    selected = card(0, selected=True)
    assert trust.rank_candidates(
        [free, activity, assistant, selected], "assistant"
    ) == [activity, free]
    assert trust.rank_candidates([free, activity, assistant, selected], "activity") == [
        assistant,
        free,
    ]


def test_lowest_trust_is_first_and_full_trust_never_clears_a_slot():
    values = [card(110), card(200), card(20), card(0)]
    assert [
        item.trust for item in trust.rank_candidates(values, "assistant", True, 100)
    ] == [0, 20, 110]


def solver():
    result = trust.TrustRotationSolver.__new__(trust.TrustRotationSolver)
    result.deadline = float("inf")
    result.prefer, result.threshold = True, 100
    result.recog = SimpleNamespace(
        img=np.zeros((1080, 1920, 3), dtype=np.uint8), find=Mock(return_value=None)
    )
    result.tap, result.swipe = Mock(), Mock()
    result._require = Mock()
    result._prepare_selection = Mock()
    result.assistant_names = {}
    return result


@pytest.fixture
def connecting_inspection(monkeypatch):
    obj = solver()
    del obj.tap, obj._require
    state = SimpleNamespace(
        now=0.0,
        page=1,
        connecting=0,
        persistent=False,
        cancel=False,
        changed_page=False,
        observations=0,
        inputs=[],
        reads=[],
    )
    stopped = Event()
    monkeypatch.setattr(config, "stop_mower", stopped)
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(trust, "monotonic", lambda: state.now)
    monkeypatch.setattr(trust.rapidocr, "initialize_ocr", Mock())

    def observe(interval):
        state.now += interval
        if state.connecting:
            state.observations += 1
            if state.cancel and state.observations == 2:
                stopped.set()
            if not state.persistent:
                state.connecting -= 1
                if not state.connecting and state.changed_page:
                    state.page = 4
        obj.recog.img.fill(state.page)

    def tap(point):
        assert not state.connecting, "input reached a connecting screen"
        state.inputs.append(point)
        if point == (95, 625):
            state.page, state.connecting = 2, 3
        elif point == obj.ASSISTANT_POINTS[0]:
            state.page = 3
        elif point == (65, 55):
            state.page = 2

    def ocr(image, **kwargs):
        state.reads.append((state.connecting, state.now))
        labels = {1: "基建副手", 2: "罗德岛基建副手", 3: "确认", 4: "其他页面"}
        return [([], labels[int(image[0, 0, 0])], 1.0)], None

    obj.recog.img.fill(1)
    obj.recog.find = lambda *args: bool(state.connecting)
    obj.device = SimpleNamespace(tap=Mock(side_effect=tap))
    obj.sleep = observe
    obj.ASSISTANT_POINTS = obj.ASSISTANT_POINTS[:1]
    for name in (
        "discard_pending_selection",
        "back_to_infrastructure",
        "_enter_control_center",
        "_return_from_assistants",
        "_activity_rooms",
    ):
        setattr(obj, name, Mock())
    obj._assistant_trust = Mock(return_value=1)
    obj._name = Mock(return_value="芬")
    monkeypatch.setattr(trust.rapidocr, "engine", ocr)
    return obj, state


def test_inspection_waits_for_connecting_before_opening_assistant(
    connecting_inspection,
):
    obj, state = connecting_inspection
    obj.run(seconds=20)
    assert state.observations == 3
    assert state.inputs == [(95, 625), (635, 350), (65, 55)]
    assert all(not connecting for connecting, _ in state.reads)
    assert obj.assistant_names == {0: "芬"}
    obj._activity_rooms.assert_called_once()


def test_inspection_rechecks_page_after_connecting_clears(connecting_inspection):
    obj, state = connecting_inspection
    state.changed_page = True
    with pytest.raises(trust.TrustReadingError, match="未确认罗德岛基建副手页面"):
        obj.run(seconds=20)
    assert state.inputs == [(95, 625)]
    obj._name.assert_not_called()


def test_connecting_after_page_read_never_receives_stale_input(connecting_inspection):
    obj, state = connecting_inspection

    def read_trust(index):
        state.connecting, state.changed_page = 3, True
        return 1

    obj._assistant_trust.side_effect = read_trust
    with pytest.raises(trust.TrustReadingError, match="联网"):
        obj.run(seconds=20)
    assert state.inputs == [(95, 625)]
    obj._name.assert_not_called()


def test_connecting_never_reads_names_from_an_unverified_page(
    connecting_inspection, monkeypatch
):
    obj, state = connecting_inspection
    del obj._name
    obj.deadline = 20
    state.connecting, state.changed_page = 3, True
    matcher = Mock(return_value="芬")
    monkeypatch.setattr(trust, "match_operator_name", matcher)
    with pytest.raises(trust.TrustReadingError, match="联网"):
        obj._name(obj.SELECTOR_NAME)
    matcher.assert_not_called()
    assert state.inputs == []


def test_connecting_uses_original_inspection_deadline(connecting_inspection):
    obj, state = connecting_inspection
    state.persistent = True
    with pytest.raises(trust.TrustReadingError, match="时间预算"):
        obj.run(seconds=3.5)
    assert state.now == obj.deadline == 3.5
    assert state.inputs == [(95, 625)]
    assert len(state.reads) == 1
    obj._name.assert_not_called()


def test_connecting_stop_cancels_before_selection_readback(connecting_inspection):
    obj, state = connecting_inspection
    state.persistent, state.cancel = True, True
    with pytest.raises(MowerExit):
        obj.run(seconds=20)
    assert state.now == 2
    assert state.inputs == [(95, 625)]
    assert len(state.reads) == 1
    obj._name.assert_not_called()


@pytest.fixture(scope="module")
def local_trust_ocr():
    return trust.rapidocr.create_engine(threads=1)


@pytest.fixture
def activity_69_frame():
    image = cv2.imread(
        str(Path(__file__).parent / "fixtures" / "trust_activity_b106_69.jpg")
    )
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def test_logged_activity_trust_is_read_in_its_upright_orientation(
    activity_69_frame, local_trust_ocr, monkeypatch
):
    obj = solver()
    obj.recog.img = activity_69_frame
    monkeypatch.setattr(trust.rapidocr, "engine", local_trust_ocr)
    scope = ((1480, 705), (1660, 775))
    assert obj._assignment_trust(scope, ((1430, 245), (1705, 775))) == 69
    assert obj._trust(scope) == 69
    obj.tap.assert_not_called()


@pytest.mark.parametrize("prefer_low", [False, True])
def test_logged_activity_trust_allows_inspecting_all_remaining_rooms(
    activity_69_frame, local_trust_ocr, prefer_low, monkeypatch
):
    obj = solver()
    obj.prefer = prefer_low
    obj.recog.img = activity_69_frame
    monkeypatch.setattr(trust.rapidocr, "engine", local_trust_ocr)
    read_ocr = obj._ocr

    def observe(scope):
        if scope == ((360, 360), (1900, 1020)):
            return [
                (
                    [[x, y], [x + 90, y], [x + 90, y + 35], [x, y + 35]],
                    "活动室",
                    0.99,
                )
                for y in (50, 210, 370, 530)
                for x in (680, 1160)
            ]
        # Each simulated room replays the original occupied 69% panel.
        return read_ocr(scope)

    obj._ocr = observe
    obj._assignment_trust = Mock(wraps=obj._assignment_trust)
    obj._replace = Mock(side_effect=AssertionError("Retain the 69% incumbent"))
    obj._activity_rooms()

    assert obj._assignment_trust.call_count == 8
    obj._replace.assert_not_called()
    assert [call.args[0] for call in obj.tap.call_args_list] == [
        (1140, 465),
        (65, 55),
        (1620, 465),
        (65, 55),
        (1140, 625),
        (65, 55),
        (1620, 625),
        (65, 55),
        (1140, 785),
        (65, 55),
        (1620, 785),
        (65, 55),
        (1140, 945),
        (65, 55),
        (1620, 945),
        (65, 55),
    ]


@pytest.fixture
def name_frame(request):
    sample, name, value = request.param
    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures" / f"trust_name_{sample}.png")
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[155:215, 20:350] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return frame, name, value


@pytest.mark.parametrize(
    "name_frame",
    [("recon", "罗德岛隐秘队", 100), ("clemensa", "克莱门莎", 62)],
    indirect=True,
)
def test_logged_assistant_name_is_read_as_a_complete_line(name_frame):
    obj = solver()
    obj.recog.img, expected, _ = name_frame
    assert obj._name(obj.SELECTOR_NAME) == expected
    obj.tap.assert_not_called()


def test_activity_name_readback_uses_the_verified_text_region():
    obj = solver()
    crop = cv2.imread(
        str(Path(__file__).parent / "fixtures" / "trust_name_activity.png")
    )
    obj.recog.img[640:710, 1420:1750] = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    assert obj._name(obj.ACTIVITY_NAME, activity=True) == "旅骨"
    obj.tap.assert_not_called()


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("00-selector.png", "结城理"),
        ("01-selector.png", "矩"),
        ("02-selector.png", "响石"),
        ("03-selector.png", "风絮"),
        ("04-selector.png", "罗德岛隐秘队"),
        ("05-activity.png", "克莱门莎"),
        ("06-activity.png", "旅骨"),
        ("07-activity.png", "德·托莱多"),
        ("08-activity.png", "时隙"),
        ("09-activity.png", "岳羽由加莉"),
        ("10-activity.png", "机械师"),
        ("11-activity.png", "虎狼丸"),
        ("12-activity.png", "埃癸斯"),
        ("selector_amiya.png", "阿米娅"),
        ("selector_stainless.png", "白铁"),
        ("selector_zheya.png", "折桠"),
        ("selector_confess.png", "CONFESS-47"),
        ("selector_terra.png", "泰拉大陆调查团"),
        ("selector_uofficial.png", "U-Official"),
        ("selector_kaltsit.png", "凯尔希·思衡托"),
        ("selector_christine.png", "Miss.Christine"),
        ("selector_vina.png", "维娜·维多利亚"),
        ("activity_terra.png", "泰拉大陆调查团"),
    ],
)
def test_existing_templates_read_real_name_fields_without_ocr(
    filename, expected, monkeypatch
):
    obj = solver()
    crop = cv2.imread(str(Path(__file__).parent / "fixtures/trust_names" / filename))
    activity = "activity" in filename
    y, x = (640, 1420) if activity else (155, 20)
    obj.recog.img[y : y + crop.shape[0], x : x + crop.shape[1]] = cv2.cvtColor(
        crop, cv2.COLOR_BGR2RGB
    )
    monkeypatch.setattr(trust.rapidocr, "engine", Mock(side_effect=AssertionError))
    scope = obj.ACTIVITY_NAME if activity else obj.SELECTOR_NAME
    before = obj.recog.img.copy()
    assert obj._name(scope, activity=activity) == expected
    np.testing.assert_array_equal(obj.recog.img, before)
    obj.tap.assert_not_called()


@pytest.mark.parametrize("damage", ["blank", "clipped", "oversized", "weak"])
def test_incomplete_name_fields_cannot_authorize_selection(damage):
    obj = solver()
    image = np.full((45, 330, 3), 255, dtype=np.uint8)
    if damage == "clipped":
        image[0:30, 10:30] = 0
    elif damage == "oversized":
        image[5:35, 5:325] = 0
    elif damage == "weak":
        image[20:23, 20:23] = 0
    obj.recog.img[160:205, 20:350] = image
    with pytest.raises(trust.TrustReadingError):
        obj._name(obj.SELECTOR_NAME)
    obj.tap.assert_not_called()


def test_activity_replacement_verifies_real_selector_and_room_name_crops(monkeypatch):
    obj = solver()
    fixtures = Path(__file__).parent / "fixtures"
    selector = cv2.imread(str(fixtures / "trust_name_clemensa.png"))
    activity = cv2.imread(str(fixtures / "trust_names/05-activity.png"))
    obj.recog.img[155:215, 20:350] = cv2.cvtColor(selector, cv2.COLOR_BGR2RGB)
    obj._cards = Mock(
        side_effect=[
            [card(200, selected=True)],
            [card(0)],
            [card(0, selected=True)],
        ]
    )
    obj._trust = Mock(return_value=0)

    def tap(point):
        if point == (1575, 1025):
            obj.recog.img.fill(0)
            obj.recog.img[640:710, 1420:1750] = cv2.cvtColor(
                activity, cv2.COLOR_BGR2RGB
            )

    obj.tap.side_effect = tap
    monkeypatch.setattr(trust.rapidocr, "engine", Mock(side_effect=AssertionError))
    assert obj._replace("activity", 200) == "replaced"
    assert [call.args[0] for call in obj.tap.call_args_list] == [
        ((570, 120), (754, 514)),
        (1575, 1025),
    ]


@pytest.mark.parametrize(
    "name_frame",
    [("recon", "罗德岛隐秘队", 100), ("clemensa", "克莱门莎", 62)],
    indirect=True,
)
def test_logged_incumbent_does_not_block_activity_inspection(name_frame, monkeypatch):
    obj = solver()
    obj.recog.img, expected, value = name_frame
    monkeypatch.setattr(config, "conf", Conf())
    for name in (
        "discard_pending_selection",
        "back_to_infrastructure",
        "_enter_control_center",
        "_leave_selection",
        "_return_from_assistants",
        "_activity_rooms",
    ):
        setattr(obj, name, Mock())
    obj._assistant_trust = Mock(
        side_effect=[value, None, None, None, None, value, None]
    )
    obj._replace = Mock(return_value="full")
    obj.run()
    assert obj.assistant_names == {0: expected}
    obj._replace.assert_called_once_with("assistant", None, index=1)
    obj._activity_rooms.assert_called_once()


@pytest.mark.parametrize("result", ["", "未收录姓名"])
def test_unverified_name_never_authorizes_selection(result, monkeypatch):
    obj = solver()
    monkeypatch.setattr(trust, "match_operator_name", Mock(return_value=result))
    with pytest.raises(trust.TrustReadingError):
        obj._name(obj.SELECTOR_NAME)
    obj.tap.assert_not_called()


@pytest.mark.parametrize("expired_before", [False, True])
def test_name_templates_obey_inspection_deadline(monkeypatch, expired_before):
    obj = solver()

    def recognize(*args, **kwargs):
        obj.deadline = 0
        return "芬"

    matcher = Mock(side_effect=recognize)
    monkeypatch.setattr(trust, "match_operator_name", matcher)
    if expired_before:
        obj.deadline = 0
    with pytest.raises(trust.TrustReadingError, match="时间预算"):
        obj._name(obj.SELECTOR_NAME)
    assert matcher.call_count == (0 if expired_before else 1)
    obj.tap.assert_not_called()


@pytest.mark.parametrize("kind", ["assistant", "activity"])
def test_full_roster_stops_before_selection_or_confirmation(kind):
    obj = solver()
    obj._prepare_selection = Mock()
    obj._cards = Mock(return_value=[card(99, selected=True), card(200)])
    assert obj._replace(kind, 99) == "full"
    obj.tap.assert_not_called()
    obj.swipe.assert_not_called()


def test_cross_kind_low_trust_prevents_incorrect_saturation():
    obj = solver()
    obj._prepare_selection = Mock()
    other = card(5, activity=True)
    obj._cards = Mock(return_value=[card(200), other])
    obj._name = Mock(return_value="芬")
    assert obj._find_candidate("assistant") == (other, "芬")


def test_assistant_roster_without_badges_never_moves_another_assistant():
    obj = solver()
    occupied, candidate = card(0, 789), card(5, 1006)
    obj.assistant_names = {0: "芬", 1: "白铁"}
    obj._cards = Mock(return_value=[occupied, candidate])
    obj._name = Mock(side_effect=["白铁", "裂响"])
    assert obj._find_candidate("assistant") == (candidate, "裂响")
    assert [call.args[0] for call in obj.tap.call_args_list] == [
        occupied.scope,
        candidate.scope,
    ]
    assert (1575, 1025) not in [call.args[0] for call in obj.tap.call_args_list]


def test_activity_badges_exclude_occupants_of_unvisited_rooms():
    obj = solver()
    other, candidate = card(0, activity=True), card(5, 789)
    obj._cards = Mock(return_value=[other, candidate])
    obj._name = Mock(return_value="裂响")
    assert obj._find_candidate("activity") == (candidate, "裂响")
    obj.tap.assert_called_once_with(candidate.scope)


def test_unreadable_candidate_is_skipped_without_confirmation():
    obj = solver()
    unknown, candidate = card(0), card(5, 789)
    obj._cards = Mock(return_value=[unknown, candidate])
    obj._name = Mock(side_effect=[trust.TrustReadingError("unknown"), "裂响"])
    assert obj._find_candidate("assistant") == (candidate, "裂响")
    assert [call.args[0] for call in obj.tap.call_args_list] == [
        unknown.scope,
        candidate.scope,
    ]


def test_confirmed_replacement_updates_only_its_assistant_membership():
    obj = solver()
    occupied = card(0, 789)
    candidate = card(5, 1006)
    obj.assistant_names = {0: "芬", 1: "白铁"}
    obj._cards = Mock(
        side_effect=[
            [card(120, selected=True)],
            [occupied, candidate],
            [card(5, 1006, selected=True)],
        ]
    )
    obj._name = Mock(side_effect=["白铁", "裂响", "裂响", "裂响"])
    obj._trust = Mock(return_value=5)
    obj._leave_selection = Mock()
    assert obj._replace("assistant", 120) == "replaced"
    assert obj.assistant_names == {0: "裂响", 1: "白铁"}
    clicks = [call.args[0] for call in obj.tap.call_args_list]
    assert clicks.index((1575, 1025)) > clicks.index(candidate.scope)
    assert clicks.count((1575, 1025)) == 1


def test_expired_budget_rejects_inputs_and_scene_navigation(monkeypatch):
    obj = solver()
    obj.deadline = 0
    monkeypatch.setattr(config, "stop_mower", SimpleNamespace(is_set=lambda: False))
    with pytest.raises(trust.TrustReadingError):
        trust.TrustRotationSolver.tap(obj, (500, 500))
    with pytest.raises(trust.TrustReadingError):
        obj.scene()


def test_empty_card_cross_is_distinct_from_unknown_trust():
    image = np.full((375, 190, 3), 100, dtype=np.uint8)
    image[100:170, 90:100] = 255
    image[130:140, 60:130] = 255
    assert trust.empty_assignment(image)
    assert not trust.empty_assignment(np.full_like(image, 100))
    obj = solver()
    obj.recog.img = image
    obj._text = Mock(return_value="")
    assert obj._assignment_trust(((0, 0), (190, 375)), ((0, 0), (190, 375))) is None
    obj.recog.img = np.full_like(image, 100)
    with pytest.raises(trust.TrustReadingError):
        obj._assignment_trust(((0, 0), (190, 375)), ((0, 0), (190, 375)))


@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_real_sort_arrow_direction(direction):
    image = cv2.imread(
        str(Path(__file__).parent / "fixtures" / f"trust_sort_{direction}.png")
    )
    ascending = trust.trust_order_ascending(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    assert bool(ascending) == (direction == "ascending")


def test_unknown_sort_arrow_does_not_establish_ascending_order():
    assert trust.trust_order_ascending(np.zeros((19, 38, 3), dtype=np.uint8)) is None


@pytest.mark.parametrize("active", [False, True])
def test_real_skill_priority_state(active):
    state = "active" if active else "inactive"
    image = cv2.imread(
        str(Path(__file__).parent / "fixtures" / f"trust_skill_priority_{state}.png")
    )
    assert trust.skill_priority_active(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)) == active


def test_active_skill_priority_is_disabled_before_trust_selection(monkeypatch):
    obj = solver()
    obj._text = Mock(return_value="ALL")
    states = iter([True, False])
    monkeypatch.setattr(trust, "skill_priority_active", lambda _: next(states))
    monkeypatch.setattr(trust, "trust_order_ascending", lambda _: True)
    trust.TrustRotationSolver._prepare_selection(obj)
    assert [call.args[0] for call in obj.tap.call_args_list] == [
        (1140, 55),
        (1850, 135),
    ]


def test_scroll_reset_reaches_start_beyond_two_swipes(monkeypatch):
    obj = solver()
    obj._text = Mock(return_value="ALL")
    monkeypatch.setattr(trust, "trust_order_ascending", lambda _: True)

    def swipe(*args, **kwargs):
        obj.recog.img[:] = min(obj.swipe.call_count, 4) * 20

    obj.swipe.side_effect = swipe
    trust.TrustRotationSolver._prepare_selection(obj)
    assert obj.swipe.call_count == 5


@pytest.mark.parametrize("expanded", [False, True])
def test_profession_filter_is_verified_before_reset(expanded, monkeypatch):
    obj = solver()
    obj._text = Mock(return_value="ALL" if expanded else "")
    monkeypatch.setattr(trust, "trust_order_ascending", lambda _: True)
    trust.TrustRotationSolver._prepare_selection(obj)
    clicks = [call.args[0] for call in obj.tap.call_args_list]
    assert clicks == ([(1850, 135)] if expanded else [(1850, 55), (1850, 135)])
    assert any(call.args[0] == "ALL" for call in obj._require.call_args_list)


def test_aborted_pending_selection_is_discarded_without_confirming():
    obj = solver()
    obj._text = Mock(side_effect=["确认", "当前使用者信息"])
    obj.discard_pending_selection()
    assert [call.args[0] for call in obj.tap.call_args_list] == [(65, 55), (65, 55)]


def test_threshold_fallback_retains_incumbent_without_confirming():
    obj = solver()
    obj._find_candidate = Mock(return_value=(card(110), "芬"))
    obj._cards = Mock(return_value=[card(120, selected=True)])
    obj._leave_selection = Mock()
    assert obj._replace("activity", 120) == "retained"
    obj._leave_selection.assert_called_once()
    obj.tap.assert_not_called()


@pytest.mark.parametrize(
    "actual",
    [
        [],
        [card(200, selected=True)],
        [card(120, selected=True), card(120, selected=True)],
    ],
)
def test_unverified_current_selection_rejects_input(actual):
    obj = solver()
    obj._find_candidate = Mock(return_value=card(20))
    obj._cards = Mock(return_value=actual)
    with pytest.raises(trust.TrustReadingError):
        obj._replace("activity", 120)
    obj.tap.assert_not_called()


def test_missing_trust_is_unknown_not_zero():
    obj = solver()
    obj._text = Mock(return_value="无法识别")
    with pytest.raises(trust.TrustReadingError):
        obj._trust(((0, 0), (100, 100)))


@pytest.mark.parametrize("selected_user_tab", [False, True])
def test_user_tab_is_clicked_at_most_once(selected_user_tab):
    obj = solver()
    obj._ocr = Mock(
        return_value=[([[680, 50], [780, 50], [780, 90], [680, 90]], "活动室", 0.99)]
    )
    obj._text = Mock(return_value="当前使用者信息" if selected_user_tab else "设施信息")
    obj._assignment_trust = Mock(return_value=20)
    obj._activity_rooms()
    clicks = [call.args[0] for call in obj.tap.call_args_list]
    assert clicks.count((95, 410)) == (0 if selected_user_tab else 1)


def test_unbuilt_rooms_receive_no_clicks():
    obj = solver()
    obj._ocr = Mock(return_value=[])
    obj._activity_rooms()
    obj.tap.assert_not_called()


def test_eight_built_positions_are_checked_and_no_working_roster_is_mutated():
    obj = solver()
    ordinary = {"白铁": {"current_room": "room_1_1", "mood": 20}}
    obj.op_data = SimpleNamespace(operators=ordinary)
    obj._ocr = Mock(
        return_value=[
            ([[x, y], [x + 90, y], [x + 90, y + 35], [x, y + 35]], "活动室", 0.99)
            for y in (50, 210, 370, 530)
            for x in (680, 1160)
        ]
    )
    obj._text = Mock(return_value="当前使用者信息")
    obj._assignment_trust = Mock(return_value=20)
    obj._activity_rooms()
    assert obj.tap.call_count == 16
    assert ordinary == {"白铁": {"current_room": "room_1_1", "mood": 20}}


def test_full_activity_candidates_skip_remaining_built_rooms():
    obj = solver()
    obj._ocr = Mock(
        return_value=[
            ([[680, y], [780, y], [780, y + 35], [680, y + 35]], "活动室", 0.99)
            for y in (50, 210, 370)
        ]
    )
    obj._text = Mock(return_value="当前使用者信息")
    obj._assignment_trust = Mock(return_value=200)
    obj._replace = Mock(return_value="full")
    obj._leave_selection = Mock()
    obj._activity_rooms()
    obj._replace.assert_called_once_with("activity", 200)
    obj._leave_selection.assert_called_once()


@pytest.fixture
def daily(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "conf", Conf(trust_rotation_enable=True))
    path = tmp_path / "trust_rotation.json"
    monkeypatch.setattr(trust, "get_path", lambda _: path)
    mocked = Mock()
    monkeypatch.setattr(trust, "TrustRotationSolver", Mock(return_value=mocked))
    return path, mocked


def test_daily_interval_commits_only_completed_inspections(daily):
    path, mocked = daily
    next_task = datetime.now() + timedelta(hours=1)
    assert trust.run_trust_rotation(None, None, next_task)
    assert "completed_at" in json.loads(path.read_text())
    assert not trust.run_trust_rotation(None, None, next_task)
    mocked.run.assert_called_once_with(seconds=480)


def test_failed_daily_inspection_remains_due(daily):
    path, mocked = daily
    mocked.run.side_effect = trust.TrustReadingError("unknown")
    assert not trust.run_trust_rotation(None, None, datetime.now() + timedelta(hours=1))
    assert not path.exists()


def test_daily_stop_propagates_without_completion(daily):
    path, mocked = daily
    mocked.run.side_effect = MowerExit
    with pytest.raises(MowerExit):
        trust.run_trust_rotation(None, None, datetime.now() + timedelta(hours=1))
    assert not path.exists()


def test_disabled_daily_inspection_has_no_device_inputs(daily):
    path, mocked = daily
    config.conf.trust_rotation_enable = False
    assert not trust.run_trust_rotation(None, None, datetime.now() + timedelta(hours=1))
    mocked.run.assert_not_called()
    assert not path.exists()


def test_due_inspection_preserves_next_task_margin(daily):
    path, mocked = daily
    assert not trust.run_trust_rotation(
        None, None, datetime.now() + timedelta(seconds=30)
    )
    mocked.run.assert_not_called()
    assert not path.exists()


@pytest.mark.parametrize(
    "values",
    [
        {"trust_rotation_threshold": 0},
        {"trust_rotation_threshold": 201},
        {"trust_rotation_interval": 0},
        {"trust_rotation_interval": float("inf")},
    ],
)
def test_config_rejects_unbounded_or_invalid_limits(values):
    with pytest.raises(ValidationError):
        Conf(**values)


def test_default_config_is_opt_in():
    conf = Conf()
    assert not conf.trust_rotation_enable
    assert not conf.trust_rotation_prefer_low
    assert conf.trust_rotation_threshold == 100
    assert conf.trust_rotation_interval == 24
