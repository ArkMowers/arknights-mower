"""断线弹窗或无效滚动不能把房间读取困在固定像素 while 循环中。"""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", Mock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402
from arknights_mower.utils.recognize import RecognizeError  # noqa: E402


@pytest.fixture(autouse=True)
def scroll_clock(monkeypatch):
    now = 0

    def sleep(solver, seconds):
        nonlocal now
        now += seconds
        solver.recog.update()

    monkeypatch.setattr(base_schedule, "monotonic", lambda: now)
    monkeypatch.setattr(BaseSchedulerSolver, "sleep", sleep)


def boundary_color(point):
    value = 220 if point[1] in (343, 531) else 49
    return value, value, value


def solver():
    result = object.__new__(BaseSchedulerSolver)
    result.recog = Mock(w=1920, h=1080)
    result.find = Mock(side_effect=lambda name: name == "room_detail")
    result.get_color = Mock(return_value=(255, 255, 255))
    result.swipe = Mock()
    return result


@pytest.mark.parametrize("bottom", [False, True])
def test_unchanged_scroll_has_bounded_room_recovery(bottom):
    result = solver()
    with pytest.raises(RecognizeError, match="六次"):
        result.scroll_room_operators(bottom=bottom)
    assert result.swipe.call_count == 6
    result.swipe.assert_called_with(
        (1536, 746 if bottom else 260),
        (0, -486 if bottom else 486),
        duration=500,
        interval=0,
    )


@pytest.mark.parametrize("bottom", [False, True])
@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_first_downward_swipe_duration_and_unchanged_feedback(bottom, mode):
    from arknights_mower.utils.performance import PERFORMANCE_PRESETS

    result = solver()
    result._selection_profile_snapshot = PERFORMANCE_PRESETS[mode]
    result.get_color.side_effect = lambda point: (
        boundary_color(point) if result.swipe.call_count == 2 else (255, 255, 255)
    )
    assert result.scroll_room_operators(bottom=bottom) is bottom
    first_ms = 220 if bottom and mode in ("xhigh", "high") else 500
    assert [call.kwargs["duration"] for call in result.swipe.call_args_list] == [
        first_ms,
        500,
    ]


@pytest.mark.parametrize("dialog", ["confirm", "double_confirm/main"])
def test_popup_interrupts_scroll_before_another_gesture(dialog):
    result = solver()
    result.find.side_effect = lambda name: (
        name == "room_detail" or (result.swipe.call_count == 1 and name == dialog)
    )
    with pytest.raises(RecognizeError, match="确认弹窗"):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_called_once()


def test_left_room_is_not_read_as_scroll_boundary():
    result = solver()
    result.find.return_value = None
    result.find.side_effect = None
    result.get_color.return_value = (0, 0, 0)
    with pytest.raises(RecognizeError, match="离开房间"):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_not_called()


def test_last_gesture_result_is_checked_before_failure():
    result = solver()
    result.get_color.side_effect = lambda point: (
        boundary_color(point) if result.swipe.call_count == 6 else (255, 255, 255)
    )
    result.scroll_room_operators(bottom=True)
    assert result.swipe.call_count == 6


def test_already_at_boundary_does_not_swipe():
    result = solver()
    result.get_color.side_effect = boundary_color
    result.scroll_room_operators(bottom=False)
    result.swipe.assert_not_called()
    result.recog.update.assert_not_called()


def test_user_stop_is_not_converted_to_recovery(monkeypatch):
    result = solver()
    monkeypatch.setattr(base_schedule.config.stop_mower, "is_set", lambda: True)
    with pytest.raises(MowerExit):
        result.scroll_room_operators(bottom=True)
    result.swipe.assert_not_called()


@pytest.mark.parametrize(
    "frame", ["room_empty_bottom_20261020.jpg", "room_empty_bottom_again_20261020.jpg"]
)
@pytest.mark.parametrize("starts_at_bottom", [False, True])
def test_recorded_empty_slots_stop_at_first_bottom_frame(frame, starts_at_bottom):
    from pathlib import Path

    import numpy as np
    from PIL import Image

    result = solver()
    image = np.array(Image.open(Path(__file__).parent / "fixtures/selection" / frame))
    top = np.array(
        Image.open(
            Path(__file__).parent / "fixtures/selection/room_empty_top_20261020.jpg"
        )
    )
    result.get_color.side_effect = lambda point: (
        image if starts_at_bottom or result.swipe.call_count else top
    )[point[1], point[0]]
    result.scroll_room_operators(bottom=True)
    assert result.swipe.call_count == (0 if starts_at_bottom else 1)
    assert result.recog.update.call_count == result.swipe.call_count


def test_delayed_bottom_feedback_requires_aligned_cards_before_reading():
    result = solver()
    samples = []

    def color(point):
        frame = result.recog.update.call_count
        if point == (1800, 925):
            samples.append(frame)
        if frame < 2:
            return (255, 255, 255)
        if frame == 2:
            return (49, 49, 49)
        return boundary_color(point)

    result.get_color.side_effect = color
    result.scroll_room_operators(bottom=True)
    assert samples == [0, 1, 2, 3]
    result.swipe.assert_called_once()


@pytest.fixture
def five_slot_room():
    def make(start_bottom, *, empty=(), unclear=(), timer_replacement=None):
        s = solver()
        names = ["黑键", "能天使", "绮良", "琴柳", "鸿雪"]
        colors = {}
        captured = []
        written = []
        ready = datetime(2026, 11, 23, 15)
        bottom = start_bottom
        s.detect_room = Mock(return_value="central")
        s.task, s.tasks = None, []
        s._can_refresh_idle_dorm_search = Mock(return_value=False)
        s.refresh_facility_state = s.turn_on_room_detail = s.wait_product_complete = (
            Mock()
        )
        s.op_data = Mock()
        s.op_data.plan = {"central": [None] * 5}
        s.op_data.mood_calculation_enabled = False
        s.op_data.room_observations = {}
        s.op_data.operators = {
            name: Mock(
                current_room="central", current_index=i, mood=15, depletion_rate=1
            )
            for i, name in enumerate(names)
        }

        def write(name, mood, room, index, update, **_):
            written.append((name, mood, index, update))
            # 第一个岗位的实读可以触发原本未指定的第五岗读时。
            return 4 if index == 0 else None

        s.op_data.update_detail.side_effect = write
        ys = (135, 344, 553, 532, 741)
        mood_y = (219, 428, 637, 615, 823)
        time_y = (270, 480, 690, 668, 877)
        for end in (False, True):
            img = np.zeros((1080, 1920, 3), dtype=np.uint8)
            top = 532 if end else 344
            img[top - 1, 1800] = 220
            for i in range(3, 5) if end else range(3):
                img[ys[i] + 25, 1460] = i + 1
                img[mood_y[i], 1470] = i + 11
                img[time_y[i], 1650] = i + 1
            colors[end] = img

        def capture():
            captured.append(bottom)
            s.recog.img = colors[bottom]
            s.recog.gray = s.recog.img[:, :, 0]
            s.recog.capture_started_at = ready + timedelta(seconds=len(captured))

        capture()
        s.recog.update.side_effect = capture

        def swipe(start, movement, **_):
            nonlocal bottom
            bottom = movement[1] < 0

        s.swipe.side_effect = swipe
        s.get_color.side_effect = lambda point: s.recog.img[point[1], point[0]]
        s.find.side_effect = lambda res, scope=None: (
            res == "room_detail"
            or res == "infra_no_operator"
            and ys.index(scope[0][1]) in empty
        )
        unread = set(unclear)

        def read(img, *, type, cord=None):
            if type == "name":
                index = int(img[0, 0]) - 1
                assert index in range(5)
                if ("name", index) in unread:
                    unread.remove(("name", index))
                    return ""
                return names[index]
            (x, y), _ = cord
            index = int(img[y, x, 0]) - 1
            assert index in range(5)
            if ("time", index) in unread:
                unread.remove(("time", index))
                return "?"
            return f"01:00:0{index}"

        def live_time(room, index, cord):
            assert bottom == (index >= 3)
            s.recog.update()
            if timer_replacement:
                names[index] = timer_replacement
            return ready + timedelta(hours=2)

        s.read_screen = Mock(side_effect=read)
        s.read_operator_time = Mock(side_effect=live_time)
        s.read_accurate_mood = lambda img: int(img[0, 0])
        return s, captured, written, names, ready

    return make


@pytest.mark.parametrize("bottom", [False, True])
def test_five_slots_read_names_moods_and_times_from_two_frames(five_slot_room, bottom):
    s, captured, written, names, ready = five_slot_room(bottom, empty=(1,))
    result = s.get_agent_from_room("central", [0, 2, 3], force_mood=True)
    assert captured == [bottom, not bottom]
    assert s.swipe.call_count == 1
    assert [row["agent"] for row in result] == [names[0], "", *names[2:]]
    assert [row["mood"] for row in result] == [11, -1, 13, 14, 15]
    assert written == [(names[i], 11 + i, i, True) for i in (0, 2, 3, 4)]
    for i in (0, 2, 3, 4):
        sequence = 1 if (i >= 3) == bottom else 2
        assert result[i]["time"] == ready + timedelta(hours=1, seconds=sequence + i)
    s.read_operator_time.assert_not_called()


@pytest.mark.parametrize("field", ["name", "time"])
def test_fuzzy_lower_sample_returns_to_correct_slot_once(five_slot_room, field):
    s, captured, written, names, ready = five_slot_room(True, unclear=[(field, 3)])
    result = s.get_agent_from_room("central", [3], force_mood=True)
    assert captured[:3] == [True, False, True]
    assert s.swipe.call_count == 2
    assert [row["agent"] for row in result] == names
    assert [slot for _, _, slot, _ in written] == list(range(5))
    if field == "time":
        assert result[3]["time"] == ready + timedelta(hours=2)
        s.read_operator_time.assert_called_once_with(
            "central", 3, ((1650, 668), (1780, 703))
        )
    else:
        s.read_operator_time.assert_not_called()


def test_changed_resident_in_live_timer_retry_prevents_full_confirmation(
    five_slot_room,
):
    s, _, written, _, _ = five_slot_room(
        True, unclear=[("time", 3)], timer_replacement="年"
    )
    with pytest.raises(RecognizeError, match="第 4 岗"):
        s.get_agent_from_room("central", [3], force_mood=True)
    assert [index for _, _, index, _ in written] == [0, 1, 2]
    assert not s.op_data.room_observations
    assert not s.op_data.refresh_dorm_time.called


def test_live_countdown_retry_uses_the_successful_capture_time(five_slot_room):
    s, captured, _, _, ready = five_slot_room(True, unclear=[("time", 3)])
    s.read_operator_time = BaseSchedulerSolver.read_operator_time.__get__(s)

    def read_time(cord, limit):
        s.recog.update()
        return 90

    s.read_time = read_time
    result = s.get_agent_from_room("central", [3], force_mood=True)
    assert captured == [True, False, True, True]
    assert result[3]["time"] == ready + timedelta(seconds=4 + 90)


@pytest.mark.parametrize("cached", [False, True])
def test_missing_recovery_bed_timer_checked_before_admission(five_slot_room, cached):
    s, _, written, names, ready = five_slot_room(
        True, unclear=[("time", 3)], timer_replacement="年"
    )
    room = "dormitory_1"
    s.detect_room.return_value = room
    s._execution_group_transitions = lambda: {}
    s.op_data.plan[room] = [SimpleNamespace(agent=name) for name in names]
    bed = SimpleNamespace(
        position=(room, 3), name=names[3], time=ready if cached else None
    )
    s.op_data.operators[names[3]].current_room = room
    s.op_data.all_dorms.return_value = [bed]
    s.op_data.is_recovery_dorm.return_value = True
    s.op_data.get_dorm_by_name.side_effect = lambda name: (
        (0, bed) if name == bed.name else (None, None)
    )
    s._reconcile_room_observation = Mock()
    write = s.op_data.update_detail.side_effect

    def update(*args, **kwargs):
        write(*args, **kwargs)
        return 3 if args[3] == 3 and not cached else None

    s.op_data.update_detail.side_effect = update
    if cached:
        result = s.get_agent_from_room(room, force_mood=True)
        assert result[3]["time"] == ready
        s.read_operator_time.assert_not_called()
    else:
        with pytest.raises(RecognizeError, match="第 4 岗"):
            s.get_agent_from_room(room, force_mood=True)
        assert [index for _, _, index, _ in written] == [0, 1, 2]
        s.op_data.refresh_dorm_time.assert_not_called()


@pytest.mark.parametrize("bottom", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("record", [False, True])
def test_dorm_evidence_keeps_measured_bar_and_raw_timer_from_same_frame(
    five_slot_room, bottom, enabled, record
):
    s, captured, _, names, ready = five_slot_room(bottom, unclear=[("time", 3)])
    room = "dormitory_1"
    s.detect_room.return_value = room
    s._execution_group_transitions = lambda: {}
    s._reconcile_room_observation = Mock()
    s.op_data.plan[room] = [SimpleNamespace(agent=name) for name in names]
    s.op_data.mood_calculation_enabled = enabled
    s.op_data.update_detail.side_effect = None
    s.op_data.update_detail.return_value = None
    deadline = ready + timedelta(minutes=20)
    beds = {
        name: SimpleNamespace(position=(room, i), name=name, time=deadline)
        for i, name in enumerate(names)
    }
    s.op_data.all_dorms.return_value = list(beds.values())
    s.op_data.get_dorm_by_name.side_effect = lambda name: (0, beds[name])
    for op in s.op_data.operators.values():
        op.current_room = room
        op.need_to_refresh.return_value = False
        op.current_mood.return_value = 22

    result = s.get_agent_from_room(
        room, read_dorm_evidence=True, record_dorm_evidence=record
    )

    assert captured == [bottom, not bottom]
    assert [row["measured_mood"] for row in result] == [11, 12, 13, 14, 15]
    assert [row.get("mood_sampled", False) for row in result] == [enabled or record] * 5
    assert [row["recovery_seconds"] for row in result] == [3600, 3601, 3602, None, 3604]
    assert [row["mood"] for row in result] == (
        [11, 12, 13, 14, 15] if enabled or record else [22] * 5
    )
    assert all(row["time"] == deadline for row in result)
    s.read_operator_time.assert_not_called()


@pytest.mark.parametrize("readable", [True, False])
def test_full_width_with_visible_timer_is_not_recorded_as_a_full_departure(
    five_slot_room, readable
):
    room = "dormitory_1"
    s, _, _, names, ready = five_slot_room(
        False, unclear=[] if readable else [("time", 0)]
    )
    s.detect_room.return_value = room
    s._execution_group_transitions = lambda: {}
    s._reconcile_room_observation = Mock()
    s.op_data.plan[room] = [SimpleNamespace(agent=name) for name in names]
    s.op_data.update_detail.side_effect = None
    s.op_data.update_detail.return_value = None
    beds = {
        n: SimpleNamespace(position=(room, i), name=n, time=ready)
        for i, n in enumerate(names)
    }
    s.op_data.all_dorms.return_value = list(beds.values())
    s.op_data.get_dorm_by_name.side_effect = lambda name: (0, beds[name])
    for op in s.op_data.operators.values():
        op.current_room = room
        op.need_to_refresh.return_value = False
        op.current_mood.return_value = 22
    s.recog.img[270, 1652] = 255
    s.read_accurate_mood = lambda _: 24
    first = s.get_agent_from_room(room, record_dorm_evidence=True)[0]
    assert first["recovery_seconds"] == (3600 if readable else None)
    assert first.get("measured_mood") == (24 if readable else None)
    assert not first.get("mood_sampled")
    assert first["mood"] == 22
    assert s.op_data.update_detail.call_args_list[0].args[-1] is False


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("evidence", [False, True])
@pytest.mark.parametrize("cold", [False, True])
@pytest.mark.parametrize("finished", [False, True])
def test_last_second_of_full_width_bar_preserves_sample_and_bed_deadline(
    five_slot_room, enabled, evidence, cold, finished
):
    from pathlib import Path

    from PIL import Image

    from arknights_mower.utils.operators import Dormitory, Operators

    room = "dormitory_3"
    s, _, _, names, ready = five_slot_room(False, empty=(1, 2, 3, 4))
    names[0] = "蓝毒"
    s.detect_room.return_value = room
    s._execution_group_transitions = lambda: {}
    s._reconcile_room_observation = Mock()
    s.op_data.plan[room] = [SimpleNamespace(agent="Free")] * 5
    s.op_data.mood_calculation_enabled = enabled
    old_mood = 24 if cold else 22
    old_stamp = None if cold else ready - timedelta(hours=1)
    op = s.op_data.operators.pop("黑键")
    op.current_room, op.mood, op.time_stamp = room, old_mood, old_stamp
    op.upper_limit, op.mood_is_prediction = 24, False
    op.current_mood.return_value = old_mood
    s.op_data.operators[names[0]] = op
    bed = Dormitory((room, 0))
    bed.name = names[0]
    if not cold:
        bed.time = ready
    s.op_data.dorm, s.op_data.group_dorm, s.op_data.true_exhaust_room = [bed], [], []
    s.op_data.all_dorms.return_value = [bed]
    s.op_data.get_dorm_by_name.return_value = (0, bed)
    s.op_data.is_recovery_dorm.return_value = True
    s.op_data.is_dynamic_dorm_position.return_value = True

    def write(name, mood, room, index, update):
        if update:
            op.mood, op.time_stamp = mood, ready
        return index

    s.op_data.update_detail.side_effect = write
    s.op_data.refresh_dorm_time.side_effect = lambda *args: Operators.refresh_dorm_time(
        s.op_data, *args
    )
    # 同一张床的连续两帧：蓝毒 23/24、还剩一秒，随后 24/24、倒计时消失。
    path = (
        Path(__file__).parent
        / "fixtures/selection/blue_poison_full_countdown_20261125.png"
    )
    with Image.open(path) as source:
        cards = np.asarray(source).reshape(2, 86, 310)
    s.recog.img[219:305, 1470:1780] = cards[int(finished), :, :, None]
    s.read_accurate_mood = BaseSchedulerSolver.read_accurate_mood.__get__(s)
    read = s.read_screen.side_effect

    def read_card(img, *, type, cord=None):
        if type == "time":
            assert not finished
            assert np.array_equal(img[270:305, 1650:1780, 0], cards[0, 51:, 180:])
            return "00:00:01"
        return read(img, type=type, cord=cord)

    s.read_screen.side_effect = read_card
    first = s.get_agent_from_room(
        room, [0], force_mood=not enabled, read_dorm_evidence=evidence
    )[0]
    if finished:
        assert op.mood == first["mood"] == 24 and op.time_stamp == ready
        assert first.get("recovery_seconds") is None
    else:
        assert (op.mood, op.time_stamp) == (old_mood, old_stamp)
        assert not first.get("mood_sampled")
        assert first["mood"] < 24
        assert first["time"] == bed.time == ready + timedelta(seconds=2)
        if evidence:
            assert (first["measured_mood"], first["recovery_seconds"]) == (24, 1)
    s.read_operator_time.assert_not_called()


def test_wrong_room_at_lower_start_does_not_apply_any_slot(five_slot_room):
    s, captured, written, _, _ = five_slot_room(True)
    s.detect_room.return_value = "dormitory_1"
    with pytest.raises(RecognizeError, match="未确认房间"):
        s.get_agent_from_room("central", force_mood=True)
    assert captured == [True, True]
    s.swipe.assert_not_called()
    assert not written


def test_stale_lower_frame_from_previous_room_is_refreshed_before_sampling(
    five_slot_room,
):
    s, captured, written, names, _ = five_slot_room(True)
    s.detect_room.side_effect = lambda: (
        "central" if len(captured) > 1 else "dormitory_1"
    )
    result = s.get_agent_from_room("central", force_mood=True)
    assert captured == [True, True, False]
    assert s.swipe.call_count == 1
    assert [row["agent"] for row in result] == names
    assert len(written) == 5


def test_stop_while_applying_saved_frame_preserves_pending_slots(
    five_slot_room, monkeypatch
):
    s, _, written, _, _ = five_slot_room(True)
    monkeypatch.setattr(
        base_schedule.config.stop_mower, "is_set", lambda: len(written) == 3
    )
    with pytest.raises(MowerExit):
        s.get_agent_from_room("central", force_mood=True)
    assert [index for _, _, index, _ in written] == [0, 1, 2]
    assert not s.op_data.room_observations


def test_popup_on_the_way_to_top_preserves_unapplied_lower_slots(five_slot_room):
    s, _, written, _, _ = five_slot_room(True)
    find = s.find.side_effect
    s.find.side_effect = lambda res, scope=None: (
        s.swipe.called and res == "confirm" or find(res, scope)
    )
    with pytest.raises(RecognizeError, match="确认弹窗"):
        s.get_agent_from_room("central", force_mood=True)
    assert not written
    assert not s.op_data.room_observations


@pytest.fixture(scope="module")
def central_end_frames():
    from pathlib import Path

    from PIL import Image

    # 正式复测中的上端、三次 +4 像素、精确下端，保留原识别区域和卡片边线。
    path = (
        Path(__file__).parent
        / "fixtures/selection/central_bottom_offsets_20261123.webp"
    )
    with Image.open(path) as source:
        return np.array(source).reshape(5, 941, 555, 3)


@pytest.mark.parametrize(
    "condition",
    [
        "aligned",
        "with_times",
        "empty_fourth",
        "wrong_anchor",
        "empty_anchor",
        "changing",
        "same_capture",
        "wrong_room",
        "wrong_spacing",
        "popup",
        "unclear_name",
        "unclear_time",
    ],
)
def test_near_bottom_requires_independent_aligned_frames_and_third_resident(
    five_slot_room, central_end_frames, condition, monkeypatch
):
    s, _, written, _, ready = five_slot_room(False)
    expected = ["薇薇安娜", "焰尾", "森蚺", "维什戴尔", "八幡海铃"]
    s.op_data.operators = dict(zip(expected, s.op_data.operators.values()))
    s.op_data.update_detail.side_effect = lambda name, mood, room, index, update: (
        written.append((name, mood, index, update))
    )
    seen = []
    empty_scopes = []

    def capture():
        index = min(len(seen), 4)
        seen.append(index)
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        img[:941, 1250:1805] = central_end_frames[index]
        partial = 1 <= index <= 3
        if partial:
            if condition == "wrong_anchor":
                img[352:407, 1460:1785] = 0
            if condition == "changing":
                img[130:940] = np.roll(img[130:940], index - 1, axis=0)
            if condition == "wrong_spacing":
                img[744, 1800] = 0
            if condition == "unclear_name":
                img[561:616, 1460:1785] = 0
            if condition == "unclear_time":
                img[672:707, 1650:1780] = 0
        s.recog.img = img

        s.recog.gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        stamp = 1 if partial and condition == "same_capture" else index
        s.recog.capture_started_at = ready + timedelta(seconds=stamp)

    def find(res, scope=None):
        if res == "infra_no_operator":
            top = scope[0][1]
            empty_scopes.append((seen[-1], top))
            return (
                condition == "empty_anchor"
                and top == 553
                and seen[-1] == 0
                or condition == "empty_fourth"
                and top == 536
            )
        if res == "confirm" and condition == "popup" and seen[-1] == 2:
            return True
        return res == "room_detail"

    capture()
    s.recog.update.side_effect = capture
    s.detect_room.side_effect = lambda: (
        "dormitory_1" if condition == "wrong_room" and 1 <= seen[-1] <= 3 else "central"
    )
    s.find.side_effect = find
    s.read_screen = Mock(wraps=BaseSchedulerSolver.read_screen.__get__(s))
    s.read_accurate_mood = BaseSchedulerSolver.read_accurate_mood.__get__(s)
    if condition == "popup":
        with pytest.raises(RecognizeError, match="确认弹窗"):
            s.get_agent_from_room("central", force_mood=True)
        assert [entry[2] for entry in written] == [0, 1, 2]
        assert not s.op_data.room_observations
        return
    needs_time = condition in ("with_times", "unclear_time")
    if needs_time:
        from arknights_mower.utils import rapidocr

        monkeypatch.setattr(rapidocr, "engine", rapidocr.create_engine(0.8, threads=2))
    rows = s.get_agent_from_room(
        "central", [3, 4] if needs_time else None, force_mood=True
    )
    if condition == "empty_anchor":
        expected[2] = ""
    if condition == "empty_fourth":
        expected[3] = ""
    assert [row["agent"] for row in rows] == expected
    assert [row["mood"] for row in rows[3:]] == pytest.approx(
        [-1 if condition == "empty_fourth" else 17.574193548, 20.129032258]
    )
    assert [n for n, *_ in written] == [n for n in expected if n]
    used_offset = condition in ("aligned", "empty_fourth", "with_times")
    assert seen[-1] == (2 if used_offset else 4)
    if used_offset:
        assert empty_scopes[-2:] == [(2, 536), (2, 745)]
    read_times = [
        call for call in s.read_screen.call_args_list if call.kwargs["type"] == "time"
    ]
    assert len(read_times) == (2 if needs_time else 0)
    if condition == "with_times":
        captured_at = ready + timedelta(seconds=2)
        assert rows[3]["time"] == captured_at + timedelta(
            hours=27, minutes=3, seconds=2
        )
        assert rows[4]["time"] == captured_at + timedelta(hours=31, seconds=47)
    if condition == "unclear_time":
        s.read_operator_time.assert_called_once_with(
            "central", 3, ((1650, 668), (1780, 703))
        )
        assert rows[3]["time"] == ready + timedelta(hours=2)
    else:
        s.read_operator_time.assert_not_called()


def test_release_reads_full_bars_without_requesting_extra_countdowns(five_slot_room):
    s, captured, _, names, ready = five_slot_room(False)
    room = "dormitory_1"
    s.detect_room.return_value = room
    s._execution_group_transitions = lambda: {}
    s._reconcile_room_observation = Mock()
    s.op_data.plan[room] = [SimpleNamespace(agent=n) for n in names]
    s.op_data.update_detail.side_effect = None
    s.op_data.update_detail.return_value = None
    beds = {
        n: SimpleNamespace(position=(room, i), name=n, time=ready + timedelta(hours=1))
        for i, n in enumerate(names)
    }
    s.op_data.all_dorms.return_value = list(beds.values())
    s.op_data.get_dorm_by_name.side_effect = lambda n: (0, beds[n])
    for op in s.op_data.operators.values():
        op.current_room = room
        op.need_to_refresh.return_value = False
        op.current_mood.return_value = 22
    s._release_dorm_readings = {}
    s.recog.img[270, 1652] = 255
    s.read_accurate_mood = lambda _: 24
    readings = s.get_agent_from_room(room)
    assert captured == [False, True]
    assert [r.get("measured_mood") for r in readings] == [None, 24, 24, 24, 24]
    assert not any(c.kwargs["type"] == "time" for c in s.read_screen.call_args_list)
    s.read_operator_time.assert_not_called()
