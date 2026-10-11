"""Offline contracts for daily Trust Rotation; no device or network access."""

import json
from datetime import datetime, timedelta
from pathlib import Path
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
    result.recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
    result.tap, result.swipe = Mock(), Mock()
    result._require = Mock()
    result._prepare_selection = Mock()
    result.assistant_names = {}
    return result


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
