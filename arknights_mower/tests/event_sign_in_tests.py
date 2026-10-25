"""Offline activity sign-in decisions using crops from the supplied game images."""

from datetime import date, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import event_sign_in as sign_in
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import Recognizer
from arknights_mower.utils.solver import StrategyError

FIXTURES = Path(__file__).parent / "fixtures/event_sign_in"
ORIGINAL_STATES = ("claimed", "available", *("locked",) * 5)
CENTERS = (697, 875, 1051, 1228, 1404, 1581, 1757)


def fixture_image(name):
    data = np.fromfile(FIXTURES / name, dtype=np.uint8)
    return cv2.cvtColor(cv2.imdecode(data, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def panel_frame(states=ORIGINAL_STATES, *, available_color=(220, 153, 3)):
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    image[205:290, 670:1800] = fixture_image("progress.png")
    colors = {"claimed": (255, 255, 255), "locked": (0, 0, 0)}
    for x, original, state in zip(CENTERS, ORIGINAL_STATES, states):
        if state != original or state == "available":
            color = colors.get(state, available_color)
            cv2.circle(image, (x, 248), 11, color, -1, cv2.LINE_AA)
    return image


@pytest.fixture(scope="module")
def local_ocr():
    return sign_in.rapidocr.create_engine(threads=2)


def test_supplied_progress_crop_identifies_only_day_two():
    assert sign_in.progress_states(panel_frame()) == ORIGINAL_STATES


@pytest.mark.parametrize("color", [(20, 110, 240), (170, 35, 210), (25, 190, 100)])
def test_available_marker_accepts_other_event_colors(color):
    assert (
        sign_in.progress_states(panel_frame(available_color=color)) == ORIGINAL_STATES
    )


@pytest.mark.parametrize(
    "name,expected", [("days_left.png", [2, 3, 4]), ("days_right.png", [4, 5, 6, 7])]
)
def test_supplied_day_crops_have_unambiguous_large_numerals(local_ocr, name, expected):
    result, _ = local_ocr(fixture_image(name), use_cls=False)
    positions = sign_in.day_positions(result)
    assert sorted(positions) == expected
    assert all(380 <= y <= 490 for _, y in positions.values())
    assert all(700 < x < 1780 for x, _ in positions.values())


def test_supplied_entry_crop_contains_a_confident_sign_in_label(local_ocr):
    result, _ = local_ocr(fixture_image("entry.png"), use_cls=False)
    labels = [(text, score) for _, text, score in result or []]
    assert any("签到" in text and score >= 0.9 for text, score in labels)


@pytest.mark.parametrize(
    "kind", ["six_days", "eight_days", "shifted", "wrong_frame", "grey_bar"]
)
def test_unsupported_layout_is_rejected(kind):
    image = panel_frame()
    if kind == "six_days":
        image[225:272, 1728:1787] = (80, 80, 80)
    elif kind == "eight_days":
        cv2.circle(image, (960, 248), 11, (0, 0, 0), -1, cv2.LINE_AA)
    elif kind == "shifted":
        image[205:290, 680:1810] = image[205:290, 670:1800].copy()
        image[205:290, 670:680] = 0
    elif kind == "wrong_frame":
        image = image[:720, :1280]
    else:
        image[205:290, 670:1800] = (85, 85, 85)
    assert sign_in.progress_states(image) is None


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


def test_small_low_confidence_duplicate_and_nonconsecutive_days_cannot_select_rewards():
    valid = ocr_number(2, (1100, 430))
    assert sign_in.day_positions([valid, ocr_number(1, (1350, 430), height=20)]) == {
        2: (1100, 430)
    }
    assert sign_in.day_positions([ocr_number(2, (1100, 430), score=0.89)]) == {}
    assert sign_in.day_positions([valid, ocr_number(2, (1380, 430))]) == {}
    assert sign_in.day_positions([valid, ocr_number(4, (1380, 430))]) == {}


@pytest.fixture
def activity(monkeypatch):
    stopped = Event()
    monkeypatch.setattr(config, "stop_mower", stopped)
    state = SimpleNamespace(
        now=0.0,
        phase="index",
        states=list(ORIGINAL_STATES),
        side="left",
        entry=True,
        close=True,
        close_success=True,
        pending=None,
        claimed=[],
        inputs=[],
        swipes=[],
        sleeps=[],
        reward_delay=0,
        dismissal_delay=0,
        ticks=0,
        show_reward=True,
        mark_claimed=True,
        fingerprint=20,
        scroll_values=[],
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
        white_before_material=False,
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
    left = {1: (820, 430), 2: (1100, 430), 3: (1380, 430), 4: (1660, 430)}
    right = {4: (820, 430), 5: (1100, 430), 6: (1380, 430), 7: (1660, 430)}
    solver = object.__new__(sign_in.EventSignInSolver)
    recog = SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8))

    def render():
        if state.phase in ("panel", "delay"):
            recog.img = panel_frame(state.states)
            recog.img[370:500, 690:1790] = state.fingerprint
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
                elif state.white_before_material:
                    state.states[state.pending - 1] = "claimed"
                    state.phase = "panel"
        elif state.phase == "dismissal":
            state.ticks += 1
            if state.ticks > state.dismissal_delay:
                if state.mark_claimed:
                    state.states[state.pending - 1] = "claimed"
                state.phase = "panel"
        elif state.phase == "panel":
            state.panel_updates += 1
        render()

    def visible():
        return left if state.side == "left" else right

    def engine(image, **options):
        assert options == {"use_det": True, "use_cls": False, "use_rec": True}
        if image.shape == (165, 180, 3):
            entry = ([[26, 46], [138, 46], [138, 75], [26, 75]], "前瞻签到", 0.996)
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
        result = [ocr_number(day, point) for day, point in visible().items()]
        if state.missing_day or (state.hide_before_scroll and not state.swipes):
            result = []
        if state.change_before_tap:
            state.states[1] = "claimed"
            render()
        return result, None

    def tap(point, interval=1):
        if stopped.is_set():
            raise MowerExit
        state.inputs.append((point, state.phase))
        if point == (172, 160):
            assert state.phase == "index"
            state.phase = "panel"
        elif point == (1875, 152):
            assert state.phase == "panel"
            if state.close_success:
                state.phase = "index"
        elif point == (960, 960):
            assert state.phase == "reward"
            state.claimed.append(state.pending)
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
        state.side = "left" if movement[0] > 0 else "right"
        if state.scroll_values:
            state.fingerprint = state.scroll_values.pop(0)
        state.now += interval
        render()

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
    solver.back_to_index = Mock(side_effect=back_to_index)

    def find(name):
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
    monkeypatch.setattr(sign_in, "time", SimpleNamespace(monotonic=lambda: state.now))
    monkeypatch.setattr(sign_in.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(sign_in.rapidocr, "engine", engine)
    return solver, state, stopped


def set_available(state, *days):
    state.states = ["available" if day in days else "claimed" for day in range(1, 8)]


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
    assert len(state.swipes) == 3


@pytest.mark.parametrize("day", range(1, 8))
def test_missing_day_seeks_correct_edge_until_three_unchanged_swipes(activity, day):
    solver, state, _ = activity
    set_available(state, day)
    state.side = "right" if day <= 4 else "left"
    state.hide_before_scroll = True

    assert solver.run() is True

    assert state.claimed == [day]
    assert len(state.swipes) == 3
    expected = (
        ((800, 510), (900, 0), 500) if day <= 4 else ((1700, 510), (-900, 0), 500)
    )
    assert state.swipes == [expected] * 3


def test_a_changed_scroll_frame_resets_the_stationary_counter(activity):
    solver, state, _ = activity
    set_available(state, 5)
    state.scroll_values = [20, 20, 40, 40, 40, 40]

    assert solver.run() is True

    assert state.claimed == [5]
    assert len(state.swipes) == 6


def test_scroll_stops_after_twelve_changes_without_claiming(activity):
    solver, state, _ = activity
    set_available(state, 5)
    state.scroll_values = list(range(30, 151, 10))

    assert solver.run() is False

    assert len(state.swipes) == 12
    assert state.claimed == []
    assert all(point in ((172, 160),) for point, _ in state.inputs)


def test_day_still_missing_at_the_edge_is_not_clicked(activity):
    solver, state, _ = activity
    state.missing_day = True

    assert solver.run() is False

    assert len(state.swipes) == 3
    assert state.inputs == [((172, 160), "index")]


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


@pytest.mark.parametrize("failure", ["no_reward", "no_white_marker"])
def test_unconfirmed_claim_returns_false_without_repeating_the_claim(activity, failure):
    solver, state, _ = activity
    state.show_reward = failure != "no_reward"
    state.mark_claimed = failure != "no_white_marker"

    assert solver.run() is False

    assert [point for point, phase in state.inputs if phase == "panel"] == [(1100, 430)]
    assert solver.claimed_days == set()
    assert state.now < 20
    assert state.phase != "index"


def test_state_change_after_ocr_prevents_a_stale_reward_click(activity):
    solver, state, _ = activity
    state.change_before_tap = True

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index")]


def test_run_rejects_an_unsupported_layout_before_clicking_any_reward(activity):
    solver, state, _ = activity
    state.invalid_layout = True

    assert solver.run() is False

    assert state.inputs == [((172, 160), "index")]
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
def test_early_white_marker_without_material_confirmation_cannot_complete(
    activity, presentation
):
    solver, state, _ = activity
    state.presentation = presentation
    state.show_reward = False
    state.white_before_material = True

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
    assert state.now < 17


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
    assert state.now < 17


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
    assert state.now < 18


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
    assert state.now < 17


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


def test_late_presentation_cannot_extend_past_the_global_deadline(activity):
    solver, state, _ = activity
    state.presentation = "costume_animation"
    state.presentation_stay = 1000
    back_to_index = solver.back_to_index.side_effect

    def late_navigation():
        back_to_index()
        state.now = 165

    solver.back_to_index.side_effect = late_navigation

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


@pytest.mark.parametrize("action", ["tap", "swipe", "back"])
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
        else:
            sign_in.EventSignInSolver.back(solver, interval=0)

    assert solver.device.mock_calls == []


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
