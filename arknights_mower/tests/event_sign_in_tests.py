"""Offline sign-in workflow with controlled cards and supplied entry crops."""

import gc
from datetime import date, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import event_sign_in as sign_in
from arknights_mower.solvers import event_sign_in_recognition as vision
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.solver import StrategyError

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"
ORIGINAL_STATES = ("claimed", "available", *("locked",) * 5)
CENTERS = (697, 875, 1051, 1228, 1404, 1581, 1757)


@pytest.fixture(autouse=True)
def release_synthetic_frame_cycles():
    yield
    gc.collect()


def fixture_image(name):
    data = np.fromfile(FIXTURES / name, dtype=np.uint8)
    return cv2.cvtColor(cv2.imdecode(data, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def panel_frame(states=ORIGINAL_STATES):
    """Render unlocked white points independently of each card's receipt marker."""
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[205:290, 670:1800] = (125, 125, 125)
    for x, state in zip(np.linspace(697, 1757, len(states)), states):
        center = (round(x), 248)
        color = (0, 0, 0) if state == "locked" else (255, 255, 255)
        cv2.circle(image, center, 14, (230, 230, 230), -1, cv2.LINE_AA)
        cv2.circle(image, center, 11, color, -1, cv2.LINE_AA)
    return image


@pytest.fixture(scope="module")
def local_ocr():
    return sign_in.rapidocr.create_engine(threads=2)


def test_supplied_entry_crop_contains_a_confident_sign_in_label(local_ocr):
    result, _ = local_ocr(fixture_image("entry.png"), use_cls=False)
    labels = [(text, score) for _, text, score in result or []]
    assert any("签到" in text and score >= 0.9 for text, score in labels)


def test_supplied_expanded_home_distinguishes_sign_in_from_login_activity(local_ocr):
    result, _ = local_ocr(fixture_image("entry_expanded.png"), use_cls=False)

    entries = sign_in.sign_in_entries(result)

    assert len(entries) == 1
    assert entries[0][0] == 0
    assert "签到" in entries[0][1]
    assert 100 <= entries[0][2][1] < 185


def test_supplied_login_activity_has_no_supported_sign_in_progress():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[205:290, 670:1800] = fixture_image("login_progress_region.png")

    assert sign_in.detect_progress(image) is None


def test_supplied_expanded_arrow_is_not_clicked_again():
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[265:410, 20:115] = fixture_image("entry_controls_expanded.png")

    assert sign_in.activity_expand_position(image) is None


@pytest.mark.parametrize("shift", [0, -81])
def test_downward_version_of_the_supplied_arrow_identifies_the_expand_button(shift):
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    band = fixture_image("entry_controls_expanded.png")
    button = cv2.flip(band[91:128, 4:92], 0)
    band[91:128, 4:92] = (130, 130, 130)
    band[91 + shift : 128 + shift, 4:92] = button
    image[265:410, 20:115] = band

    position = sign_in.activity_expand_position(image)

    assert position is not None
    assert 50 <= position[0] <= 85
    assert 360 + shift <= position[1] <= 388 + shift


def ocr_number(day, center, *, height=100, score=0.999):
    x, y = center
    x, y = x - 690, y - 370
    box = [
        [x - 25, y - height / 2],
        [x + 25, y - height / 2],
        [x + 25, y + height / 2],
        [x - 25, y + height / 2],
    ]
    return box, str(day), score


def ocr_entry(slot, label="前瞻签到", *, score=0.996):
    y = 46 + slot * 81
    return [[26, y], [138, y], [138, y + 29], [26, y + 29]], label, score


def test_duplicate_sign_in_labels_in_different_slots_remain_separate_activities():
    observed = [ocr_entry(2), ocr_entry(0), ocr_entry(1, "特别招募")]

    entries = sign_in.sign_in_entries(observed)

    assert [entry[0] for entry in entries] == [0, 2]
    assert [entry[1] for entry in entries] == ["前瞻签到", "前瞻签到"]
    assert entries[0][2][1] < entries[1][2][1]


@pytest.mark.parametrize(
    "label,score", [("限时登录", 0.99), ("登录签到", 0.99), ("前瞻签到", 0.89)]
)
def test_login_and_unconfirmed_activity_labels_are_not_sign_in_candidates(label, score):
    assert sign_in.sign_in_entries([ocr_entry(0, label, score=score)]) == []


@pytest.fixture
def activity(monkeypatch):
    stopped = Event()
    monkeypatch.setattr(config, "stop_mower", stopped)
    state = SimpleNamespace(
        now=0.0,
        phase="index",
        states=list(ORIGINAL_STATES),
        unlocked_days=None,
        unknown_days=set(),
        hide_claimed_numbers=False,
        no_response_days=set(),
        receipt_fail_days=set(),
        side="left",
        page_start=None,
        entry=True,
        entry_script=[],
        entry_reads=0,
        activities=None,
        active_slot=0,
        opened_slots=[],
        has_expander=False,
        expanded=True,
        expansion_stuck=False,
        collapse_on_close=False,
        claimed_events=[],
        close=True,
        close_success=True,
        pending=None,
        claim_started=None,
        claimed=[],
        inputs=[],
        swipes=[],
        sleeps=[],
        reward_delay=0,
        dismissal_delay=0,
        ticks=0,
        show_reward=True,
        mark_claimed=True,
        receipt_script=[],
        receipt_observations=[],
        reward_wait_ends=[],
        fingerprint=20,
        scroll_values=[],
        scroll_stuck=False,
        stall_on_swipes=set(),
        scroll_skip_anchor=False,
        scroll_step=None,
        same_card_art=False,
        distinct_header_art=False,
        day_script=[],
        day_reads=0,
        day_results=[],
        hide_before_scroll=False,
        missing_day=False,
        change_before_tap=False,
        panel_updates=0,
        invalid_layout=False,
        presentation=None,
        presentation_sequence=[],
        remaining_presentations=[],
        presentations_handled=[],
        presentation_stay=0,
        reward_after_presentation=0,
        receipt_before_material=False,
        wear_text="穿戴",
        wear_score=0.99,
        skip_text="SKIP",
        skip_score=0.99,
        wear_script=[],
        skip_script=[],
        wear_reads=0,
        skip_reads=0,
        finds=[],
    )
    solver = object.__new__(sign_in.EventSignInSolver)
    recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))
    patterns = {
        day: np.random.default_rng(day).integers(40, 220, (8, 8), dtype=np.uint8)
        for day in range(1, 16)
    }

    def render():
        if state.phase in ("panel", "delay"):
            recog.img = panel_frame(state.states)
            page_tint = min(state.fingerprint + min(visible()) * 10, 250)
            recog.img[370:500, 690:1790] = page_tint
            for day, (x, _) in visible().items():
                art_day = 1 if state.same_card_art else day
                art = cv2.resize(
                    patterns[art_day], (240, 350), interpolation=cv2.INTER_NEAREST
                )
                recog.img[500:850, x - 120 : x + 120] = art[:, :, None]
                if state.distinct_header_art:
                    header = cv2.resize(
                        patterns[day], (240, 150), interpolation=cv2.INTER_NEAREST
                    )
                    recog.img[350:500, x - 120 : x + 120] = header[:, :, None]
                if state.states[day - 1] == "claimed":
                    cv2.rectangle(
                        recog.img, (x - 45, 390), (x + 45, 470), (255, 255, 255), -1
                    )
            if state.invalid_layout:
                recog.img[225:272, 1728:1787] = (80, 80, 80)
        else:
            recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def update():
        if state.phase == "delay":
            state.ticks += 1
            if state.ticks > state.reward_delay:
                if state.presentation is not None:
                    state.phase, state.ticks = "presentation", 0
                elif state.show_reward:
                    state.phase = "reward"
                else:
                    state.phase = "panel"
        elif state.phase == "presentation_dismissal":
            state.ticks += 1
            if state.ticks > state.presentation_stay:
                if state.remaining_presentations:
                    state.presentation = state.remaining_presentations.pop(0)
                    state.phase, state.ticks = "presentation", 0
                else:
                    state.phase, state.ticks = "after_presentation", 0
        elif state.phase == "after_presentation":
            state.ticks += 1
            if state.ticks > state.reward_after_presentation:
                if state.show_reward:
                    state.phase = "reward"
                elif state.receipt_before_material:
                    state.states[state.pending - 1] = "claimed"
                    state.phase = "panel"
        elif state.phase == "dismissal":
            state.ticks += 1
            if state.ticks > state.dismissal_delay:
                if state.mark_claimed and state.pending not in state.receipt_fail_days:
                    state.states[state.pending - 1] = "claimed"
                if state.receipt_script:
                    state.states[state.pending - 1] = (
                        "claimed" if state.receipt_script.pop(0) else "available"
                    )
                state.phase = "panel"
        elif state.phase == "panel":
            state.panel_updates += 1
            if state.receipt_script and state.pending is not None:
                state.states[state.pending - 1] = (
                    "claimed" if state.receipt_script.pop(0) else "available"
                )
        render()

    def visible():
        start = state.page_start
        if start is None:
            start = 1 if state.side == "left" else max(1, len(state.states) - 3)
        return {
            day: (820 + offset * 280, 430)
            for offset, day in enumerate(
                range(start, min(start + 4, len(state.states) + 1))
            )
        }

    def engine(image, **options):
        if options.get("use_det") is False:
            assert options == {"use_det": False, "use_cls": False, "use_rec": True}
            return [], None
        assert options == {"use_det": True, "use_cls": False, "use_rec": True}
        if image.shape == (247, 180, 3):
            state.entry_reads += 1
            entry = ([[26, 46], [138, 46], [138, 75], [26, 75]], "前瞻签到", 0.996)
            if state.entry_script:
                return state.entry_script.pop(0), None
            if state.activities is not None:
                return [
                    ocr_entry(slot, event["label"])
                    for slot, event in enumerate(state.activities)
                    if state.expanded or slot < 2
                ], None
            return ([entry] if state.entry else []), None
        if image.shape == (195, 420, 3):
            state.wear_reads += 1
            observed = (
                state.wear_script.pop(0)
                if state.wear_script
                else (state.wear_text, state.wear_score)
            )
            if observed is None:
                return [], None
            label = (
                [[150, 100], [280, 100], [280, 145], [150, 145]],
                *observed,
            )
            return ([label] if state.presentation == "costume" else []), None
        if image.shape == (180, 240, 3):
            state.skip_reads += 1
            observed = (
                state.skip_script.pop(0)
                if state.skip_script
                else (state.skip_text, state.skip_score)
            )
            if observed is None:
                return [], None
            label = (
                [[110, 20], [205, 20], [205, 55], [110, 55]],
                *observed,
            )
            return ([label] if state.presentation == "costume_animation" else []), None
        assert image.shape == (130, 1100, 3)
        state.day_reads += 1
        result = [ocr_number(day, point) for day, point in visible().items()]
        if state.hide_claimed_numbers:
            result = [
                item for item in result if state.states[int(item[1]) - 1] != "claimed"
            ]
        if state.day_script:
            result = state.day_script.pop(0)
        if state.missing_day or (state.hide_before_scroll and not state.swipes):
            result = []
        if state.change_before_tap:
            state.states[1] = "claimed"
            render()
        state.day_results.append(result)
        return result, None

    def tap(point, interval=1):
        if stopped.is_set():
            raise MowerExit
        state.inputs.append((point, state.phase))
        if point == (67, 292):
            assert state.phase == "index"
            if not state.expansion_stuck:
                state.expanded = True
        elif state.activities is not None and state.phase == "index":
            slot = next(
                slot
                for slot in range(len(state.activities))
                if point == (172, 160 + 81 * slot)
            )
            assert "签到" in state.activities[slot]["label"]
            state.active_slot = slot
            state.opened_slots.append(slot)
            state.states = state.activities[slot]["states"]
            state.page_start = 1
            state.phase = "panel"
        elif point == (172, 160):
            assert state.phase == "index"
            state.phase = "panel"
        elif point == (1875, 152):
            assert state.phase == "panel"
            if state.close_success:
                state.phase = "index"
                if state.collapse_on_close:
                    state.expanded = False
        elif point == (960, 960):
            assert state.phase == "reward"
            state.claimed.append(state.pending)
            state.claimed_events.append((state.active_slot, state.pending))
            state.phase, state.ticks = "dismissal", 0
        elif point in ((960, 540), (450, 300), (1837, 37)):
            assert state.phase == "presentation", (
                "a presentation was dismissed repeatedly"
            )
            expected = {
                "operator": (960, 540),
                "operator_first": (960, 540),
                "costume": (450, 300),
                "costume_animation": (1837, 37),
            }[state.presentation]
            assert point == expected
            state.presentations_handled.append((state.pending, state.presentation))
            state.phase, state.ticks = "presentation_dismissal", 0
        else:
            assert state.phase == "panel", "reward input reached an unconfirmed page"
            day = next(day for day, position in visible().items() if position == point)
            assert state.states[day - 1] == "available"
            state.pending, state.phase, state.ticks = day, "delay", 0
            state.claim_started = state.now
            if day in state.no_response_days:
                state.phase = "panel"
            if state.presentation_sequence:
                state.presentation = state.presentation_sequence[0]
                state.remaining_presentations = list(state.presentation_sequence[1:])
        state.now += interval
        render()

    def sleep(interval):
        state.now += interval
        state.sleeps.append(interval)

    def swipe(start, movement, duration, interval):
        state.swipes.append((start, movement, duration))
        if not state.scroll_stuck and len(state.swipes) not in state.stall_on_swipes:
            direction = -1 if movement[0] > 0 else 1
            step = state.scroll_step or (4 if state.scroll_skip_anchor else 3)
            state.page_start = max(
                1, min(min(visible()) + direction * step, len(state.states) - 3)
            )
        if state.scroll_values:
            state.fingerprint = state.scroll_values.pop(0)
        state.now += interval
        render()

    def swipe_noinertia(start, movement, duration=20, interval=0.2, **options):
        swipe(start, movement, duration, interval)

    def back_to_index():
        state.phase = "index"
        render()

    recog.update = Mock(side_effect=update)
    recog.check_announcement = lambda: (
        (1875, 152) if state.close and state.phase in ("panel", "delay") else None
    )
    recog.detect_index_scene = lambda: state.phase == "index"
    solver.recog = recog
    solver.tap = Mock(side_effect=tap)
    solver.sleep = sleep
    solver.swipe = Mock(side_effect=swipe)
    solver.swipe_noinertia = Mock(side_effect=swipe_noinertia)
    solver.back_to_index = Mock(side_effect=back_to_index)

    def find(name, *args, **kwargs):
        state.finds.append(name)
        if name == "materiel_ico":
            return state.phase in ("reward", "dismissal")
        if state.phase in ("presentation", "presentation_dismissal"):
            if name == "recruit/agent_token":
                return state.presentation == "operator"
            if name == "recruit/agent_token_first":
                return state.presentation == "operator_first"
        return False

    solver.find = find
    original_wait_reward = solver._wait_reward

    def wait_reward(day, target):
        result = original_wait_reward(day, target)
        state.reward_wait_ends.append((day, state.now))
        return result

    solver._wait_reward = Mock(side_effect=wait_reward)

    def detect_progress(image):
        if (
            state.phase not in ("panel", "delay")
            or state.invalid_layout
            or not 7 <= len(state.states) <= 15
        ):
            return None
        unlocked = state.unlocked_days
        if unlocked is None:
            unlocked = max(
                (day for day, value in enumerate(state.states, 1) if value != "locked"),
                default=0,
            )
        return vision.Progress(
            total_days=len(state.states),
            unlocked_days=unlocked,
            points=tuple(
                (round(x), 248) for x in np.linspace(697, 1757, len(state.states))
            ),
            day_scope=((690, 370), (1790, 500)),
            card_scope=((690, 340), (1790, 850)),
            drag_y=510,
            scale=1.0,
        )

    def read_cards(image, progress, result):
        positions = vision.day_positions(result, progress)
        cards = []
        for day, point in visible().items():
            observed_day = next(
                (number for number, position in positions.items() if position == point),
                None,
            )
            if day in state.unknown_days:
                observed_day = None
            claimed = state.states[day - 1] == "claimed"
            if claimed and observed_day is None and positions:
                observed_day = day
            x, _ = point
            cards.append(
                vision.Card(
                    day=observed_day,
                    position=point,
                    claimed=claimed,
                    scope=((x - 120, 340), (x + 120, 850)),
                )
            )
            if day == state.pending:
                state.receipt_observations.append(claimed)
        return tuple(cards)

    monkeypatch.setattr(sign_in, "time", SimpleNamespace(monotonic=lambda: state.now))
    monkeypatch.setattr(sign_in.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(sign_in.rapidocr, "engine", engine)
    monkeypatch.setattr(sign_in, "detect_progress", detect_progress, raising=False)
    monkeypatch.setattr(sign_in, "read_cards", read_cards, raising=False)
    monkeypatch.setattr(
        sign_in,
        "activity_expand_position",
        lambda image: (67, 292) if state.has_expander and not state.expanded else None,
        raising=False,
    )
    actions = (
        recog.update,
        solver.tap,
        solver.swipe,
        solver.swipe_noinertia,
        solver.back_to_index,
        solver._wait_reward,
    )
    yield solver, state, stopped
    for action in actions:
        action.reset_mock(return_value=True, side_effect=True)
    recog.img = np.empty((0, 0, 3), dtype=np.uint8)
    solver.device = None


def set_available(state, *days):
    state.states = [
        "available" if day in days else "claimed"
        for day in range(1, len(state.states) + 1)
    ]


def daily_scheduler(monkeypatch, solver):
    from arknights_mower.solvers import base_schedule

    solver.run = Mock(wraps=solver.run)
    factory = Mock(return_value=solver)
    monkeypatch.setattr(sign_in, "EventSignInSolver", factory)
    monkeypatch.setattr(config, "conf", SimpleNamespace(event_sign_in_enable=True))
    monkeypatch.setattr(
        base_schedule, "get_server_time", lambda: datetime(2026, 10, 25, 12)
    )
    saved = Mock()
    monkeypatch.setattr(base_schedule, "save_current_state", saved)
    scheduler = object.__new__(base_schedule.BaseSchedulerSolver)
    scheduler.device = Mock()
    scheduler.recog = solver.recog
    scheduler.daily_event_sign_in = date(2026, 10, 24)
    scheduler.daily_event_sign_in_attempt = None
    return scheduler, factory, saved


def test_run_collects_earliest_days_and_rechecks_after_each_confirmation(activity):
    solver, state, _ = activity
    set_available(state, 1, 2, 5)

    assert solver.run() is True

    assert state.claimed == [1, 2, 5]
    assert solver.claimed_days == {1, 2, 5}
    assert [point for point, phase in state.inputs if phase == "panel"] == [
        (820, 430),
        (1100, 430),
        (1100, 430),
        (1875, 152),
    ]
    assert state.phase == "index"
    assert state.swipes == [((1660, 410), (-840, 0), 20)]


def test_white_unlocked_points_do_not_skip_any_unclaimed_card(activity):
    solver, state, _ = activity
    state.states = [*("available",) * 4, *("locked",) * 6]
    state.unlocked_days = 4
    before_points = panel_frame(state.states)[205:290, 670:1800].copy()

    assert solver.run() is True

    assert state.claimed == [1, 2, 3, 4]
    assert solver.claimed_days == {1, 2, 3, 4}
    assert np.array_equal(before_points, panel_frame(state.states)[205:290, 670:1800])


def test_claimed_card_is_skipped_when_its_numeral_is_covered_by_the_receipt_mark(
    activity,
):
    solver, state, _ = activity
    state.hide_claimed_numbers = True

    assert solver.run() is True

    assert state.claimed == [2]
    assert all(
        "1" not in [text for _, text, _ in result] for result in state.day_results
    )
    assert (820, 430) not in [
        point for point, phase in state.inputs if phase == "panel"
    ]


def test_claimed_current_day_without_yellow_point_still_collects_earlier_missed_days(
    activity,
):
    solver, state, _ = activity
    state.states = [*("available",) * 4, "claimed", "locked", "locked"]
    state.unlocked_days = 5
    state.side = "right"
    state.hide_claimed_numbers = True

    assert solver.run() is True

    assert state.claimed == [1, 2, 3, 4]
    assert solver.claimed_days == {1, 2, 3, 4}
    assert state.states == [*("claimed",) * 5, "locked", "locked"]
    assert state.phase == "index"


def test_anonymous_claimed_pages_can_be_scanned_to_the_end_without_card_clicks(
    activity,
):
    solver, state, _ = activity
    state.states = ["claimed"] * 10
    state.hide_claimed_numbers = True

    assert solver.run() is True

    assert state.claimed == []
    assert state.phase == "index"
    assert all(point in ((172, 160), (1875, 152)) for point, _ in state.inputs)
    assert len(state.swipes) <= 10


def test_anonymous_claimed_page_keeps_its_day_offset_after_one_ineffective_swipe(
    activity,
):
    solver, state, _ = activity
    state.states = ["claimed"] * 10
    state.hide_claimed_numbers = True
    state.stall_on_swipes = {5}

    assert solver.run() is True

    assert state.claimed == []
    assert state.phase == "index"
    assert len(state.swipes) == 6
    assert solver.swipe_noinertia.call_args_list[5].kwargs["retry"] is True


def test_identical_claimed_card_art_cannot_hide_an_unvisited_unclaimed_day(activity):
    solver, state, _ = activity
    state.states = [*("claimed",) * 5, "available", *("locked",) * 4]
    state.hide_claimed_numbers = True
    state.same_card_art = True
    state.scroll_step = 1

    assert solver.run() is False

    assert state.claimed == []
    assert state.states[5] == "available"
    assert solver.claimed_days == set()


def test_distinct_card_headers_resolve_a_repeated_reward_image_without_skipping_days(
    activity,
):
    solver, state, _ = activity
    state.states = [*("claimed",) * 5, "available", *("locked",) * 4]
    state.hide_claimed_numbers = True
    state.same_card_art = True
    state.distinct_header_art = True
    state.scroll_step = 1

    assert solver.run() is True

    assert state.claimed == [6]
    assert solver.claimed_days == {6}
    assert state.phase == "index"


def test_unresponsive_day_is_attempted_once_and_later_clear_cards_are_still_claimed(
    activity,
):
    solver, state, _ = activity
    state.states = [*("available",) * 3, *("locked",) * 4]
    state.no_response_days = {1}

    assert solver.run() is False

    assert state.claimed == [2, 3]
    assert solver.claimed_days == {2, 3}
    assert solver.attempted_days == {1, 2, 3}
    assert [point for point, phase in state.inputs if phase == "panel"].count(
        (820, 430)
    ) == 1
    assert state.phase == "panel"


def test_material_without_a_receipt_mark_does_not_finish_that_day_or_block_later_days(
    activity,
):
    solver, state, _ = activity
    state.states = [*("available",) * 3, *("locked",) * 4]
    state.receipt_fail_days = {1}

    assert solver.run() is False

    assert state.claimed == [1, 2, 3]
    assert solver.claimed_days == {2, 3}
    assert state.states[0] == "available"
    assert [point for point, phase in state.inputs if phase == "panel"].count(
        (820, 430)
    ) == 1


def test_unknown_card_stays_unconfirmed_while_later_identified_cards_are_claimed(
    activity,
):
    solver, state, _ = activity
    state.states = [*("available",) * 3, *("locked",) * 4]
    state.unknown_days = {1}

    assert solver.run() is False

    assert state.claimed == [2, 3]
    assert solver.claimed_days == {2, 3}
    assert state.states[0] == "available"
    assert (820, 430) not in [
        point for point, phase in state.inputs if phase == "panel"
    ]


def test_unreadable_future_day_does_not_block_finishing_or_the_next_activity(activity):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["claimed", "available", *("locked",) * 5]},
        {"label": "限时签到", "states": ["available", *("locked",) * 9]},
    ]
    state.unknown_days = {4}

    assert solver.run() is True

    assert state.opened_slots == [0, 1]
    assert state.claimed_events == [(0, 2), (1, 1)]
    assert state.phase == "index"


def test_receipt_confirmation_requires_two_consecutive_card_observations(activity):
    solver, state, _ = activity
    state.receipt_script = [True, False, True, True]

    assert solver.run() is True

    assert state.claimed == [2]
    assert any(
        state.receipt_observations[index : index + 3] == [True, False, True]
        for index in range(len(state.receipt_observations) - 2)
    )
    assert state.receipt_observations[-2:] == [True, True]


@pytest.mark.parametrize("day", range(1, 16))
def test_scanning_returns_to_left_edge_then_checks_all_unlocked_days(activity, day):
    solver, state, _ = activity
    state.states = ["claimed"] * 15
    set_available(state, day)
    state.side = "right" if day <= 4 else "left"

    assert solver.run() is True

    assert state.claimed == [day]
    forward = ((1660, 410), (-840, 0), 20)
    if day <= 4:
        assert state.swipes[:4] == [((820, 410), (840, 0), 20)] * 4
        assert state.swipes[4:] == [forward] * 4
    else:
        assert state.swipes == [forward] * 4


def test_three_stationary_swipes_end_an_offscreen_search_without_claiming(activity):
    solver, state, _ = activity
    set_available(state, 5)
    state.scroll_stuck = True

    assert solver.run() is False

    assert state.claimed == []
    assert len(state.swipes) == 3
    assert solver.swipe_noinertia.call_args_list[0].kwargs.get("retry", False) is False
    assert all(
        call.kwargs["retry"] for call in solver.swipe_noinertia.call_args_list[1:]
    )


def test_changed_image_without_card_progress_does_not_trigger_blind_next_page(activity):
    solver, state, _ = activity
    set_available(state, 5)
    state.scroll_stuck = True
    state.scroll_values = [90]

    assert solver.run() is False

    assert len(state.swipes) == 1
    assert state.claimed == []
    assert all(point in ((172, 160),) for point, _ in state.inputs)


def test_unreadable_day_list_finishes_with_a_bounded_number_of_gestures(activity):
    solver, state, _ = activity
    state.missing_day = True

    assert solver.run() is False

    assert len(state.swipes) <= 10
    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]


@pytest.mark.parametrize("days", [7, 10, 14, 15])
def test_reference_layout_simulates_claiming_every_day_across_overlapping_pages(
    activity, days
):
    solver, state, _ = activity
    state.states = ["available"] * days

    assert solver.run() is True

    assert state.claimed == list(range(1, days + 1))
    assert solver.claimed_days == set(range(1, days + 1))
    assert all(marker == "claimed" for marker in state.states)
    assert state.phase == "index"
    assert len(state.swipes) <= 4


def test_lost_overlap_anchor_stops_after_one_swipe_without_claiming(activity):
    solver, state, _ = activity
    state.states = ["claimed"] * 15
    set_available(state, 15)
    state.scroll_skip_anchor = True

    assert solver.run() is False

    assert len(state.swipes) == 1
    assert state.claimed == []
    assert state.inputs == [((172, 160), "index")]


def test_transient_card_ocr_can_recover_before_any_swipe(activity):
    solver, state, _ = activity
    state.day_script = [
        [],
        [ocr_number("2O", (1100, 430))],
        [ocr_number(2, (1100, 430), score=0.4)],
    ]

    assert solver.run() is True

    assert state.claimed == [2]
    assert state.swipes == []
    assert state.day_reads >= 5


def test_earlier_card_that_recovers_before_clicking_is_claimed_before_the_old_target(
    activity,
):
    solver, state, _ = activity
    state.states = ["available", "available", *("locked",) * 5]
    partial = [ocr_number(day, (820 + (day - 1) * 280, 430)) for day in range(2, 5)]
    state.day_script = [partial] * 6

    assert solver.run() is True

    assert state.claimed == [1, 2]
    assert [point for point, phase in state.inputs if phase == "panel"] == [
        (820, 430),
        (1100, 430),
        (1875, 152),
    ]


def test_transient_card_ocr_after_a_swipe_recovers_without_a_second_gesture(activity):
    solver, state, _ = activity
    set_available(state, 5)
    before = [
        ocr_number(day, (820 + offset * 280, 430))
        for offset, day in enumerate(range(1, 5))
    ]
    state.day_script = [before, before, [], [ocr_number("1O", (1100, 430))], []]

    assert solver.run() is True

    assert state.claimed == [5]
    assert len(state.swipes) == 1


def test_unreadable_post_swipe_page_finishes_after_bounded_boundary_checks(activity):
    solver, state, _ = activity
    set_available(state, 5)
    before = [
        ocr_number(day, (820 + offset * 280, 430))
        for offset, day in enumerate(range(1, 5))
    ]
    state.day_script = [before, before, *([[]] * 10)]

    assert solver.run() is False

    assert state.claimed == []
    assert len(state.swipes) <= 4


def test_missing_middle_numeral_is_reobserved_without_skipping_a_page(activity):
    solver, state, _ = activity
    state.day_script = [[ocr_number(1, (820, 430)), ocr_number(3, (1380, 430))]]

    assert solver.run() is True

    assert state.claimed == [2]
    assert state.swipes == []


def test_transient_entry_ocr_can_recover_before_declaring_no_activity(activity):
    solver, state, _ = activity
    state.entry_script = [[], [ocr_entry(0, score=0.5)], []]

    assert solver.run() is True

    assert state.claimed == [2]
    assert state.entry_reads >= 5


def test_persistent_low_confidence_sign_in_entry_remains_incomplete(activity):
    solver, state, _ = activity
    state.entry_script = [[ocr_entry(0, score=0.5)]] * 20

    assert solver.run() is False

    assert state.inputs == []
    assert state.entry_reads <= 8
    assert state.now < 5


def test_two_sign_in_activities_are_checked_top_to_bottom_even_with_the_same_label(
    activity,
):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["available", *("locked",) * 6]},
        {"label": "前瞻签到", "states": ["available", *("locked",) * 9]},
    ]

    assert solver.run() is True

    assert state.opened_slots == [0, 1]
    assert state.claimed_events == [(0, 1), (1, 1)]
    assert state.phase == "index"


def test_low_confidence_second_sign_in_recovers_before_accepting_the_first_alone(
    activity,
):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["claimed", *("locked",) * 6]},
        {"label": "限时签到", "states": ["available", *("locked",) * 6]},
    ]
    state.entry_script = [[ocr_entry(0), ocr_entry(1, "限时签到", score=0.5)]] * 3

    assert solver.run() is True

    assert state.opened_slots == [0, 1]
    assert state.claimed_events == [(1, 1)]
    assert state.entry_reads >= 7


def test_persistent_low_confidence_second_sign_in_does_not_complete_a_partial_list(
    activity,
):
    solver, state, _ = activity
    state.entry_script = [[ocr_entry(0), ocr_entry(1, "限时签到", score=0.5)]] * 20

    assert solver.run() is False

    assert state.opened_slots == []
    assert state.inputs == []
    assert state.entry_reads <= 8


def test_missing_second_entry_recovers_before_accepting_a_partial_activity_list(
    activity,
):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["claimed", *("locked",) * 6]},
        {"label": "限时签到", "states": ["available", *("locked",) * 6]},
    ]
    state.entry_script = [
        [ocr_entry(0), ocr_entry(1, "限时签到")],
        [ocr_entry(0)],
        [ocr_entry(0)],
    ]

    assert solver.run() is True

    assert state.opened_slots == [0, 1]
    assert state.claimed_events == [(1, 1)]


def test_previously_seen_second_entry_cannot_disappear_into_a_successful_partial_list(
    activity,
):
    solver, state, _ = activity
    state.entry_script = [
        [ocr_entry(0), ocr_entry(1, "限时签到")],
        *([[ocr_entry(0)]] * 20),
    ]

    assert solver.run() is False

    assert state.inputs == []
    assert state.entry_reads <= 8


def test_expansion_reveals_third_sign_in_and_login_activity_is_not_entered(activity):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["claimed", *("locked",) * 6]},
        {"label": "限时登录", "states": None},
        {"label": "限时签到", "states": ["available", *("locked",) * 14]},
    ]
    state.has_expander, state.expanded = True, False
    state.collapse_on_close = True

    assert solver.run() is True

    assert state.opened_slots == [0, 2]
    assert state.claimed_events == [(2, 1)]
    assert [point for point, _ in state.inputs].count((67, 292)) == 2
    assert state.phase == "index"


def test_activity_expansion_is_clicked_once_while_waiting_for_its_result(activity):
    solver, state, _ = activity
    state.has_expander, state.expanded, state.expansion_stuck = True, False, True

    assert solver.run() is False

    assert state.inputs == [((67, 292), "index")]
    assert state.claimed == []
    assert state.entry_reads <= 8
    assert state.now < 5


def test_unknown_activity_layout_does_not_prevent_the_next_sign_in_check(activity):
    solver, state, _ = activity
    state.activities = [
        {"label": "前瞻签到", "states": ["claimed"] * 6},
        {"label": "限时签到", "states": ["available", *("locked",) * 6]},
    ]

    assert solver.run() is False

    assert state.opened_slots == [0, 1]
    assert state.claimed_events == [(1, 1)]
    assert state.phase == "index"


def test_delayed_reward_and_dismissal_each_receive_only_one_input(activity):
    solver, state, _ = activity
    state.reward_delay, state.dismissal_delay = 5, 3

    assert solver.run() is True

    assert state.claimed == [2]
    assert state.inputs == [
        ((172, 160), "index"),
        ((1100, 430), "panel"),
        ((960, 960), "reward"),
        ((1875, 152), "panel"),
    ]
    assert state.panel_updates >= 2


@pytest.mark.parametrize("failure", ["no_reward", "no_receipt_marker"])
def test_unconfirmed_claim_returns_false_without_repeating_the_claim(activity, failure):
    solver, state, _ = activity
    state.show_reward = failure != "no_reward"
    state.mark_claimed = failure != "no_receipt_marker"

    assert solver.run() is False

    assert [point for point, phase in state.inputs if phase == "panel"] == [(1100, 430)]
    assert solver.claimed_days == set()
    assert state.now < 20
    assert state.phase != "index"


def test_receipt_observed_during_ocr_prevents_a_stale_reward_click(activity):
    solver, state, _ = activity
    state.change_before_tap = True

    assert solver.run() is True

    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]


def test_run_rejects_an_unsupported_layout_before_clicking_any_reward(activity):
    solver, state, _ = activity
    state.invalid_layout = True

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]
    assert state.claimed == []
    assert state.now < 10


def test_zero_available_days_closes_without_touching_a_reward(activity):
    solver, state, _ = activity
    state.states = ["claimed", "claimed", *("locked",) * 5]

    assert solver.run() is True

    assert state.claimed == []
    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]


def test_no_event_entry_completes_without_opening_a_panel(activity):
    solver, state, _ = activity
    state.entry = False

    assert solver.run() is True

    assert state.inputs == []
    solver.back_to_index.assert_called_once_with()


def test_unconfirmed_home_screen_cannot_be_reported_as_no_event(activity):
    solver, state, _ = activity
    solver.recog.detect_index_scene = lambda: False

    assert solver.run() is False

    assert state.inputs == []


def test_close_requires_observed_return_to_the_home_screen(activity):
    solver, state, _ = activity
    set_available(state)
    state.close_success = False

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]


def test_budget_exhaustion_returns_false_before_opening_event(activity):
    solver, state, _ = activity
    solver.back_to_index.side_effect = lambda: setattr(state, "now", 181)

    assert solver.run() is False

    assert state.inputs == []


@pytest.mark.parametrize("failure", [MowerExit, RuntimeError])
def test_cancellation_and_device_errors_propagate(activity, failure):
    solver, state, stopped = activity
    if failure is MowerExit:
        stopped.set()
    else:
        solver.back_to_index.side_effect = failure("device unavailable")

    with pytest.raises(failure):
        solver.run()

    assert state.inputs == []


@pytest.mark.parametrize("failure", [MowerExit, RuntimeError])
def test_failure_during_reward_wait_propagates_without_further_input(activity, failure):
    solver, state, stopped = activity
    state.reward_delay = 5
    observe = solver.recog.update.side_effect

    def update():
        if state.phase == "delay":
            if failure is MowerExit:
                stopped.set()
            else:
                raise RuntimeError("capture unavailable")
        observe()

    solver.recog.update.side_effect = update

    with pytest.raises(failure):
        solver.run()

    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.claimed == []


@pytest.mark.parametrize("stage", ["initialize", "recognize"])
@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError, ConnectionError])
def test_ocr_service_failure_returns_an_unconfirmed_result(
    activity, monkeypatch, stage, failure
):
    solver, state, _ = activity
    name = "initialize_ocr" if stage == "initialize" else "engine"
    engine = Mock(side_effect=failure("OCR service unavailable"))
    monkeypatch.setattr(sign_in.rapidocr, name, engine)

    assert solver.run() is False

    engine.assert_called_once()
    assert state.inputs == []
    assert solver.claimed_days == set()


@pytest.mark.parametrize("stage", ["initialize", "recognize"])
def test_ocr_service_cancellation_still_propagates(activity, monkeypatch, stage):
    solver, state, _ = activity
    name = "initialize_ocr" if stage == "initialize" else "engine"
    monkeypatch.setattr(sign_in.rapidocr, name, Mock(side_effect=MowerExit))

    with pytest.raises(MowerExit):
        solver.run()

    assert state.inputs == []


def test_capture_failure_before_ocr_is_not_mistaken_for_a_service_failure(
    activity, monkeypatch
):
    solver, state, _ = activity
    previous = solver.recog

    class FailingCapture:
        @property
        def img(self):
            raise RuntimeError("capture backend unavailable")

        def __getattr__(self, name):
            return getattr(previous, name)

    solver.recog = FailingCapture()
    engine = Mock()
    monkeypatch.setattr(sign_in.rapidocr, "engine", engine)

    with pytest.raises(RuntimeError, match="capture backend unavailable"):
        solver.run()

    engine.assert_not_called()
    assert state.inputs == []


def test_navigation_strategy_failure_returns_false(activity):
    solver, state, _ = activity
    solver.back_to_index.side_effect = StrategyError("home navigation exhausted")

    assert solver.run() is False

    assert state.inputs == []


@pytest.mark.parametrize("stage", ["initialize", "recognize"])
@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError, ConnectionError])
def test_daily_dispatch_retains_due_date_and_does_not_replay_failed_real_ocr_run(
    activity, monkeypatch, stage, failure
):
    solver, state, _ = activity
    name = "initialize_ocr" if stage == "initialize" else "engine"
    engine = Mock(side_effect=failure("OCR service unavailable"))
    monkeypatch.setattr(sign_in.rapidocr, name, engine)
    scheduler, factory, saved = daily_scheduler(monkeypatch, solver)

    assert scheduler.event_sign_in_plan_solver() is False
    assert scheduler.daily_event_sign_in_attempt == date(2026, 10, 25)
    assert scheduler.daily_event_sign_in == date(2026, 10, 24)
    assert scheduler.event_sign_in_plan_solver() is False

    solver.run.assert_called_once_with()
    factory.assert_called_once_with(scheduler.device, scheduler.recog)
    engine.assert_called_once()
    saved.assert_called_once_with()
    assert scheduler.daily_event_sign_in == date(2026, 10, 24)
    assert state.inputs == []


@pytest.mark.parametrize("presentation", ["operator", "operator_first", "costume"])
def test_reward_presentation_precedes_material_confirmation(activity, presentation):
    solver, state, _ = activity
    state.presentation = presentation

    assert solver.run() is True

    presentation_point = (450, 300) if presentation == "costume" else (960, 540)
    assert state.inputs == [
        ((172, 160), "index"),
        ((1100, 430), "panel"),
        (presentation_point, "presentation"),
        ((960, 960), "reward"),
        ((1875, 152), "panel"),
    ]
    assert state.presentations_handled == [(2, presentation)]
    assert state.claimed == [2]


@pytest.mark.parametrize("presentation", ["operator", "costume"])
def test_a_presentation_that_remains_visible_is_dismissed_once(activity, presentation):
    solver, state, _ = activity
    state.presentation, state.presentation_stay = presentation, 5

    assert solver.run() is True

    assert state.presentations_handled == [(2, presentation)]
    assert state.claimed == [2]
    assert not any(phase == "presentation_dismissal" for _, phase in state.inputs)


@pytest.mark.parametrize("presentation", ["operator", "costume"])
def test_each_new_day_can_dismiss_its_own_reward_presentation(activity, presentation):
    solver, state, _ = activity
    set_available(state, 1, 2)
    state.presentation = presentation

    assert solver.run() is True

    assert state.presentations_handled == [(1, presentation), (2, presentation)]
    assert state.claimed == [1, 2]
    assert solver.claimed_days == {1, 2}


def test_costume_dismissal_clicks_blank_space_and_never_the_wear_button(activity):
    solver, state, _ = activity
    state.presentation = "costume"

    assert solver.run() is True

    assert ((450, 300), "presentation") in state.inputs
    assert all(
        not (1500 <= x <= 1920 and 840 <= y <= 1035) for (x, y), _ in state.inputs
    )


@pytest.mark.parametrize("presentation", ["operator", "costume"])
def test_early_receipt_marker_without_material_confirmation_cannot_complete(
    activity, presentation
):
    solver, state, _ = activity
    state.presentation = presentation
    state.show_reward = False
    state.receipt_before_material = True

    assert solver.run() is False

    assert state.presentations_handled == [(2, presentation)]
    assert state.states[1] == "claimed"
    assert state.claimed == []
    assert solver.claimed_days == set()
    assert all(point != (1875, 152) for point, _ in state.inputs)


def test_recognized_presentation_allows_bounded_time_for_the_following_material(
    activity,
):
    solver, state, _ = activity
    state.presentation = "costume"
    state.reward_delay, state.reward_after_presentation = 18, 16

    assert solver.run() is True

    assert state.claimed == [2]
    assert 17 < state.now < 30


@pytest.mark.parametrize(
    "text,score", [("时装展示", 0.99), ("穿戴", 0.89), ("购买", 0.99)]
)
def test_unconfirmed_costume_page_is_not_clicked_or_given_extra_time(
    activity, text, score
):
    solver, state, _ = activity
    state.presentation = "costume"
    state.wear_text, state.wear_score = text, score

    assert solver.run() is False

    assert state.presentations_handled == []
    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.reward_wait_ends[-1][1] - state.claim_started <= 15.5


@pytest.mark.parametrize("failure", [MowerExit, RuntimeError])
@pytest.mark.parametrize("presentation", ["operator", "costume"])
def test_presentation_capture_failure_propagates_without_a_dismissal(
    activity, failure, presentation
):
    solver, state, stopped = activity
    state.presentation = presentation
    observe = solver.recog.update.side_effect

    def update():
        observe()
        if state.phase == "presentation":
            if failure is MowerExit:
                stopped.set()
            else:
                raise RuntimeError("capture backend unavailable")

    solver.recog.update.side_effect = update

    with pytest.raises(failure):
        solver.run()

    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.presentations_handled == []


@pytest.mark.parametrize("phase", ["animation", "ready"])
def test_operator_presentation_reuses_the_real_token_crop_without_recruitment(phase):
    crop = cv2.imdecode(
        np.fromfile(
            FIXTURES.parent / f"recruit_result_lava_{phase}_20261002.png",
            dtype=np.uint8,
        ),
        cv2.IMREAD_GRAYSCALE,
    )
    frame = np.zeros((1080, 1920), dtype=np.uint8)
    frame[730:860, 750:1920] = crop
    recognizer = Recognizer(Mock())
    recognizer._gray = frame
    recognizer._img = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    solver = object.__new__(sign_in.EventSignInSolver)
    solver.recog = recognizer
    solver.deadline = float("inf")
    solver._ocr = Mock(
        side_effect=AssertionError("operator reward must not use costume OCR")
    )

    assert solver._reward_presentation() == ("干员", (960, 540))

    solver._ocr.assert_not_called()


@pytest.mark.parametrize("text", ["SKIP", " S K I P ", "skip", "跳过"])
def test_costume_without_a_wear_button_uses_its_localized_skip_label(activity, text):
    solver, state, _ = activity
    state.presentation = "costume_animation"
    state.skip_text = text
    state.wear_text = ""

    assert solver.run() is True

    assert state.inputs == [
        ((172, 160), "index"),
        ((1100, 430), "panel"),
        ((1837, 37), "presentation"),
        ((960, 960), "reward"),
        ((1875, 152), "panel"),
    ]
    assert state.presentations_handled == [(2, "costume_animation")]
    assert state.claimed == [2]
    assert "skip" not in state.finds


def test_costume_skip_can_be_followed_by_a_separate_static_presentation(activity):
    solver, state, _ = activity
    state.presentation_sequence = ["costume_animation", "costume"]
    state.presentation_stay = 3

    assert solver.run() is True

    assert state.presentations_handled == [(2, "costume_animation"), (2, "costume")]
    assert state.inputs == [
        ((172, 160), "index"),
        ((1100, 430), "panel"),
        ((1837, 37), "presentation"),
        ((450, 300), "presentation"),
        ((960, 960), "reward"),
        ((1875, 152), "panel"),
    ]
    assert "skip" not in state.finds


@pytest.mark.parametrize(
    "text,score", [("SKIP", 0.89), ("SKIPPER", 0.99), ("返回", 0.99)]
)
def test_unconfirmed_skip_label_does_not_receive_a_click_or_extra_time(
    activity, text, score
):
    solver, state, _ = activity
    state.presentation = "costume_animation"
    state.skip_text, state.skip_score = text, score

    assert solver.run() is False

    assert state.presentations_handled == []
    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.reward_wait_ends[-1][1] - state.claim_started <= 15.5


def test_each_day_can_skip_and_dismiss_its_own_costume_presentation(activity):
    solver, state, _ = activity
    set_available(state, 1, 2)
    state.presentation_sequence = ["costume_animation", "costume"]

    assert solver.run() is True

    assert state.presentations_handled == [
        (1, "costume_animation"),
        (1, "costume"),
        (2, "costume_animation"),
        (2, "costume"),
    ]
    assert state.claimed == [1, 2]


@pytest.mark.parametrize("presentation", ["operator", "costume_animation", "costume"])
def test_unchanged_presentation_cannot_extend_its_own_wait_repeatedly(
    activity, presentation
):
    solver, state, _ = activity
    state.presentation = presentation
    state.presentation_stay = 1000

    assert solver.run() is False

    assert state.presentations_handled == [(2, presentation)]
    assert state.claimed == []
    assert state.reward_wait_ends[-1][1] - state.claim_started <= 15.5


def test_all_three_presentation_stages_can_precede_one_material_confirmation(activity):
    solver, state, _ = activity
    state.presentation_sequence = ["operator", "costume_animation", "costume"]

    assert solver.run() is True

    assert state.presentations_handled == [
        (2, "operator"),
        (2, "costume_animation"),
        (2, "costume"),
    ]
    assert state.claimed == [2]
    assert "skip" not in state.finds


@pytest.mark.parametrize("presentation", ["costume_animation", "costume"])
def test_transient_empty_wrong_and_low_confidence_ocr_can_recover_on_the_same_page(
    activity, presentation
):
    solver, state, _ = activity
    state.presentation = presentation
    if presentation == "costume_animation":
        state.skip_script = [None, ("SK1P", 0.99), ("SKIP", 0.4), ("SKIP", 0.99)]
    else:
        state.wear_script = [None, ("穿载", 0.99), ("穿戴", 0.4), ("穿戴", 0.99)]

    assert solver.run() is True

    reads = (
        state.skip_reads if presentation == "costume_animation" else state.wear_reads
    )
    assert reads >= 4
    assert state.presentations_handled == [(2, presentation)]
    assert state.claimed == [2]
    assert [point for point, phase in state.inputs if phase == "panel"] == [
        (1100, 430),
        (1875, 152),
    ]
    assert state.now < 12


@pytest.mark.parametrize("presentation", ["costume_animation", "costume"])
def test_persistent_empty_presentation_ocr_stops_without_another_claim(
    activity, presentation
):
    solver, state, _ = activity
    state.presentation = presentation
    state.skip_script = [None] * 100
    state.wear_script = [None] * 100

    assert solver.run() is False

    assert state.presentations_handled == []
    assert state.claimed == []
    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.reward_wait_ends[-1][1] - state.claim_started <= 15.5


@pytest.mark.parametrize("presentation", ["costume_animation", "costume"])
@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError])
def test_daily_dispatch_does_not_replay_a_claim_after_presentation_ocr_service_failure(
    activity, monkeypatch, presentation, failure
):
    solver, state, _ = activity
    state.presentation = presentation
    original_engine = sign_in.rapidocr.engine
    failed_requests = []
    shape = (180, 240, 3) if presentation == "costume_animation" else (195, 420, 3)

    def engine(image, **options):
        if image.shape == shape and state.phase == "presentation":
            failed_requests.append(state.pending)
            raise failure("presentation OCR service unavailable")
        return original_engine(image, **options)

    monkeypatch.setattr(sign_in.rapidocr, "engine", engine)
    scheduler, factory, saved = daily_scheduler(monkeypatch, solver)

    assert scheduler.event_sign_in_plan_solver() is False
    assert scheduler.event_sign_in_plan_solver() is False

    solver.run.assert_called_once_with()
    factory.assert_called_once_with(scheduler.device, scheduler.recog)
    saved.assert_called_once_with()
    assert failed_requests == [2]
    assert scheduler.daily_event_sign_in == date(2026, 10, 24)
    assert scheduler.daily_event_sign_in_attempt == date(2026, 10, 25)
    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")]
    assert state.claimed == []


def test_late_presentation_cannot_extend_past_the_global_deadline(
    activity, monkeypatch
):
    solver, state, _ = activity
    state.presentation = "costume_animation"
    state.presentation_stay = 1000
    back_to_index = solver.back_to_index.side_effect

    def late_navigation():
        back_to_index()
        state.now = 165

    solver.back_to_index.side_effect = late_navigation
    monkeypatch.setattr(
        sign_in.SceneGraphSolver,
        "sleep",
        lambda self, interval=1: setattr(state, "now", state.now + interval),
    )
    solver.sleep = sign_in.EventSignInSolver.sleep.__get__(solver)

    assert solver.run() is False

    assert state.presentations_handled == [(2, "costume_animation")]
    assert state.claimed == []
    assert state.now == 180


@pytest.mark.parametrize("stage", ["card", "operator", "material", "close"])
def test_slow_capture_cannot_send_input_after_the_operation_budget(
    activity, monkeypatch, stage
):
    solver, state, _ = activity
    tap = solver.tap.side_effect
    solver.device = Mock()
    solver.device.tap.side_effect = lambda point: tap(point, interval=0)
    solver.tap = sign_in.EventSignInSolver.tap.__get__(solver)

    if stage in ("operator", "material"):
        state.presentation = "operator" if stage == "operator" else None
        find = solver.find

        def delayed_find(name):
            result = find(name)
            if result and name == (
                "recruit/agent_token" if stage == "operator" else "materiel_ico"
            ):
                state.now = 181
            return result

        monkeypatch.setattr(solver, "find", delayed_find)
    elif stage == "card":
        panel_states = solver._panel_states

        def delayed_panel_states():
            result = panel_states()
            if state.panel_updates >= 2:
                state.now = 181
            return result

        monkeypatch.setattr(solver, "_panel_states", delayed_panel_states)
    else:
        set_available(state)
        check_announcement = solver.recog.check_announcement
        observations = 0

        def delayed_close_position():
            nonlocal observations
            position = check_announcement()
            if position is not None:
                observations += 1
                if observations >= 2:
                    state.now = 181
            return position

        monkeypatch.setattr(solver.recog, "check_announcement", delayed_close_position)

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index")] + (
        [((1100, 430), "panel")] if stage in ("operator", "material") else []
    )
    assert state.claimed == []
    assert solver.claimed_days == set()


@pytest.mark.parametrize("action", ["tap", "swipe", "swipe_noinertia", "back"])
def test_expired_navigation_budget_blocks_the_device_input(activity, action):
    solver, state, _ = activity
    solver.deadline = 180
    state.now = 181
    solver.device = Mock()

    with pytest.raises(sign_in.RecognizeError, match="活动签到操作超时"):
        if action == "tap":
            sign_in.EventSignInSolver.tap(solver, (100, 100), interval=0)
        elif action == "swipe":
            sign_in.EventSignInSolver.swipe(solver, (100, 100), (100, 0), interval=0)
        elif action == "swipe_noinertia":
            sign_in.EventSignInSolver.swipe_noinertia(
                solver, (100, 100), (100, 0), interval=0
            )
        else:
            sign_in.EventSignInSolver.back(solver, interval=0)

    assert solver.device.mock_calls == []


def test_reward_paging_reuses_the_operator_selection_gesture_path_and_timing(activity):
    solver, _, _ = activity
    solver.deadline = 180
    solver.device = Mock()

    sign_in.EventSignInSolver.swipe_noinertia(
        solver, (1660, 410), (-840, 0), interval=0
    )

    solver.device.swipe_ext.assert_called_once_with(
        [(1660, 410), (1660, 510), (820, 510), (820, 410)],
        durations=[200, 168, 200],
        up_wait=400,
    )


@pytest.mark.parametrize("stage", ["material", "operator", "claimed"])
def test_late_reward_observation_cannot_advance_or_complete_its_stage(
    activity, monkeypatch, stage
):
    solver, state, _ = activity
    if stage == "claimed":
        panel_states = solver._panel_states
        confirmations = 0

        def late_claimed_state():
            nonlocal confirmations
            result = panel_states()
            if result is not None and state.claimed:
                confirmations += 1
                if confirmations == 2:
                    state.now += 16
            return result

        monkeypatch.setattr(solver, "_panel_states", late_claimed_state)
    else:
        state.presentation = "operator" if stage == "operator" else None
        find = solver.find

        def late_reward_page(name):
            result = find(name)
            if result and name == (
                "recruit/agent_token" if stage == "operator" else "materiel_ico"
            ):
                state.now += 16
            return result

        monkeypatch.setattr(solver, "find", late_reward_page)

    assert solver.run() is False

    assert state.now < 35
    assert state.inputs == [((172, 160), "index"), ((1100, 430), "panel")] + (
        [((960, 960), "reward")] if stage == "claimed" else []
    )
    assert state.presentations_handled == []
    assert solver.claimed_days == set()


def test_late_home_confirmation_cannot_complete_after_the_operation_budget(
    activity, monkeypatch
):
    solver, state, _ = activity
    set_available(state)
    detect_index = solver.recog.detect_index_scene

    def late_home_confirmation():
        confirmed = detect_index()
        if len(state.inputs) == 2:
            state.now = 181
        return confirmed

    monkeypatch.setattr(solver.recog, "detect_index_scene", late_home_confirmation)

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index"), ((1875, 152), "panel")]
    assert state.claimed == []
