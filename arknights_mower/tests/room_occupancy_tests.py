"""用实机图里的床位、姓名、心情条、倒计时和人数栏重放进驻详情。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from PIL import Image

from arknights_mower.solvers import base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import selection_order
from arknights_mower.utils.image import loadres
from arknights_mower.utils.recognize import RecognizeError, Recognizer

DORM = "dormitory_3"
FULL = ("隐德来希", "蜜莓", "絮雨", "国度", "伊芙利特")
COMPACT = (*FULL[:3], "", "")
SPARSE = (FULL[0], "", FULL[2], "", FULL[4])
LAST_TWO = ("", "", FULL[2], "", FULL[4])
PAIR = (*FULL[:2], "虎狼丸", "能天使", "")
B102 = "room_1_2"
B302 = "room_3_2"
B203 = "room_2_3"
WORK = ("酒神", "野鬃", "灰毫")
# 前十八帧取自 followup-occupancy，最后两帧是 followup-transfer 的同一次读房。
CASES = {
    "compact-three-top": (DORM, COMPACT),
    "compact-three-bottom": (DORM, COMPACT),
    "remove-bed-4-top": (DORM, SPARSE),
    "remove-bed-4-bottom": (DORM, SPARSE),
    "remove-bed-1-top": (DORM, LAST_TWO),
    "remove-bed-1-bottom": (DORM, LAST_TWO),
    "remove-bed-3-bottom": (DORM, ("", "", "", "", FULL[4])),
    "remove-bed-5-bottom": (DORM, ("",) * 5),
    "handover-top": (DORM, FULL),
    "b102-initial": (B102, WORK),
    "b102-empty1": (B102, (WORK[0], "", WORK[2])),
    "b102-empty2": (B102, (WORK[0], "", "")),
    "b102-empty3": (B102, ("",) * 3),
    "m302-initial": (B302, ("斯卡蒂", "幽灵鲨")),
    "m302-empty1": (B302, ("", "幽灵鲨")),
    "m302-empty2": (B302, ("", "")),
    "m203-initial": (B203, ("Lancet-2",)),
    "m203-empty1": (B203, ("",)),
    "clear-hi-off-pair_top": (DORM, PAIR),
    "clear-hi-off-pair_bottom": (DORM, PAIR),
}
STAMP = datetime(2026, 11, 25, 13)


@pytest.fixture(scope="module")
def atlas():
    path = Path(__file__).parent / "fixtures/selection/room_occupancy_20261125.webp"
    with Image.open(path) as img:
        return np.array(img.convert("L"))


@pytest.fixture
def frame(atlas):
    def get(tag):
        tile = list(CASES).index(tag)
        x, y = tile % 4 * 345, tile // 4 * 888
        gray = np.zeros((1080, 1920), np.uint8)
        gray[110:941, 1460:1805] = atlas[y : y + 831, x : x + 345]
        gray[1003:1060, 1595:] = atlas[y + 831 : y + 888, x : x + 325]
        return gray

    return get


@pytest.mark.parametrize("tag", CASES)
def test_recorded_occupancy_and_capacity(frame, tag):
    _, names = CASES[tag]
    gray = frame(tag)
    count = sum(bool(n) for n in names)
    assert selection_order.read_room_occupancy(gray) == (count, len(names))
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    for capacity in (1, 2, 3, 5):
        expected = count if capacity == len(names) else None
        assert selection_order.room_occupancy(rgb, capacity) == expected


@pytest.mark.parametrize("band", [(-62, -3), (15, 95), (146, 169), (177, 210)])
def test_partial_footer_or_disagreeing_people_and_digits_is_unknown(frame, band):
    gray = frame("b102-empty1")
    caption = loadres("room/occupancy_two", gray=True)[:, :137]
    _, _, _, (x, y) = cv2.minMaxLoc(
        cv2.matchTemplate(gray[1003:1060, 1650:], caption, cv2.TM_CCOEFF_NORMED)
    )
    x += 1650
    y += 1003
    gray[y : y + 45, x + band[0] : x + band[1]] = 120
    assert selection_order.read_room_occupancy(gray) is None

    other = frame("b102-empty2")
    other[y : y + 45, x + 146 : x + 174] = frame("b102-empty1")[
        y : y + 45, x + 146 : x + 174
    ]
    assert selection_order.read_room_occupancy(other) is None


def test_people_require_visible_heads_and_bodies(frame):
    gray = frame("b102-empty1")
    gray[1025:1033, 1650:1677] = 255
    assert selection_order.room_occupancy(gray, 3) is None


@pytest.mark.parametrize("capacity", [None, 0, 4, 3.0, True])
def test_invalid_capacity_does_not_confirm_the_footer(frame, capacity):
    assert selection_order.room_occupancy(frame("b102-initial"), capacity) is None


def test_missing_resources_and_incomplete_frame_are_unknown(frame, monkeypatch):
    monkeypatch.setattr(
        selection_order,
        "_occupancy_templates",
        selection_order._occupancy_templates.__wrapped__,
    )
    monkeypatch.setattr(selection_order, "loadres", Mock(side_effect=FileNotFoundError))
    assert selection_order.room_occupancy(frame("b102-initial"), 3) is None
    assert selection_order.read_room_occupancy(frame("m302-initial")[:-10]) is None
    assert selection_order.read_room_occupancy(Mock()) is None


@pytest.fixture
def room_reader(frame):
    def make(tag, *, planned=None):
        room, expected = CASES[tag]
        s = object.__new__(BaseSchedulerSolver)
        s.task, s.tasks = None, []
        s._can_refresh_idle_dorm_search = Mock(return_value=False)
        s._execution_group_transitions = Mock(return_value={})
        s.refresh_facility_state = Mock(return_value=False)
        s.turn_on_room_detail = Mock()
        s.wait_product_complete = Mock()
        s._reconcile_room_observation = Mock()
        s.detect_room = Mock(return_value=room)
        s.op_data = Mock()
        s.op_data.plan = {
            room: [SimpleNamespace(agent="Current")] * (planned or len(expected))
        }
        s.op_data.mood_calculation_enabled = False
        s.op_data.update_detail.return_value = None
        s.op_data.get_dorm_by_name.return_value = (None, None)
        s.op_data.all_dorms.return_value = []
        s.op_data.operators = {}
        for name in {n for _, names in CASES.values() for n in names if n}:
            index = expected.index(name) if name in expected else -1
            op = Mock(current_room=room, current_index=index, mood=18, depletion_rate=1)
            op.need_to_refresh.return_value = False
            op.current_mood.return_value = 18
            s.op_data.operators[name] = op

        recog = object.__new__(Recognizer)
        s.recog = recog
        recog.w, recog.h = 1920, 1080
        recog.capture_started_at = STAMP

        def install(gray):
            recog._gray = gray
            recog._img = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
            recog.capture_started_at += timedelta(seconds=1)

        install(frame(tag))
        s.get_color = lambda point: recog.img[point[1], point[0]]
        s.find = Mock(
            side_effect=lambda res, **kw: (
                recog.find(res, **kw)
                if res == "infra_no_operator"
                else res == "room_detail"
            )
        )
        s.read_screen = Mock(wraps=s.read_screen)
        s.read_operator_time = Mock(side_effect=AssertionError("本帧应该可以读完"))
        s.sleep = Mock()
        recog.update = Mock()

        def swipe(start, movement, **kwargs):
            target = "bottom" if movement[1] < 0 else "top"
            next_tag = tag.replace("top", target).replace("bottom", target)
            install(frame(next_tag))

        s.swipe = Mock(side_effect=swipe)
        return s, install

    return make


def full_icon_searches(s):
    return sum(call.args[0] == "infra_no_operator" for call in s.find.call_args_list)


def name_reads(s):
    return sum(
        call.kwargs.get("type") == "name" for call in s.read_screen.call_args_list
    )


@pytest.mark.parametrize("tag", [t for t, (room, _) in CASES.items() if room != DORM])
def test_small_facilities_keep_physical_slots_without_extra_room_title_read(
    room_reader, tag
):
    s, _ = room_reader(tag)
    room, expected = CASES[tag]
    result = s.get_agent_from_room(room, strict_observation=True)
    assert tuple(r["agent"] for r in result) == expected
    assert name_reads(s) == sum(bool(n) for n in expected)
    assert full_icon_searches(s) == 0
    s.detect_room.assert_not_called()
    s.swipe.assert_not_called()


@pytest.mark.parametrize(
    ("tag", "swipes"),
    [
        ("compact-three-top", 0),
        ("compact-three-bottom", 1),
        ("remove-bed-4-top", 1),
        ("remove-bed-4-bottom", 1),
        ("remove-bed-1-top", 1),
        ("remove-bed-1-bottom", 0),
        ("remove-bed-3-bottom", 0),
        ("remove-bed-5-bottom", 0),
        ("clear-hi-off-pair_top", 0),
        ("clear-hi-off-pair_bottom", 1),
    ],
)
def test_only_skip_scroll_after_all_visible_names_are_identified(
    room_reader, tag, swipes
):
    s, _ = room_reader(tag)
    result = s.get_agent_from_room(DORM, strict_observation=True)
    expected = CASES[tag][1]
    assert tuple(r["agent"] for r in result) == expected
    assert s.swipe.call_count == swipes
    assert name_reads(s) == sum(bool(n) for n in expected)
    assert full_icon_searches(s) == 5 * swipes
    assert s.detect_room.call_count == 1 + swipes


@pytest.mark.parametrize(
    ("tag", "other"), [("b102-empty2", "b102-initial"), ("b102-empty1", "b102-empty3")]
)
def test_consistent_but_wrong_footer_cannot_change_visible_slots(
    room_reader, frame, tag, other
):
    s, _ = room_reader(tag)
    s.recog.gray[1003:1060, 1595:] = frame(other)[1003:1060, 1595:]
    observed = s.get_agent_from_room(B102, strict_observation=True)
    assert tuple(r["agent"] for r in observed) == CASES[tag][1]
    assert full_icon_searches(s) == 3
    assert name_reads(s) == sum(bool(n) for n in CASES[tag][1])


@pytest.mark.parametrize("masked", ["footer", "empty_icon", "name"])
def test_occlusion_falls_back_to_observed_slots(room_reader, masked):
    s, _ = room_reader("b102-empty1")
    region = {
        "footer": np.s_[1003:1060, 1595:],
        "empty_icon": np.s_[377:466, 1537:1609],
        "name": np.s_[578:633, 1460:1785],
    }[masked]
    s.recog.gray[region] = 0
    rows = s.get_agent_from_room(B102)
    assert full_icon_searches(s) >= 3
    assert rows[0]["agent"] == WORK[0]
    assert rows[1].get("observed", True) == (masked != "empty_icon")
    assert rows[2].get("observed", True) == (masked != "name")
    assert rows[2]["agent"] == ("" if masked == "name" else WORK[2])


def test_repeated_name_is_rejected_before_any_cache_write(room_reader):
    s, _ = room_reader("b102-initial")
    s.recog.gray[369:424, 1460:1785] = s.recog.gray[160:215, 1460:1785]
    with pytest.raises(RecognizeError, match="重复|两个岗位"):
        s.get_agent_from_room(B102)
    s.op_data.update_detail.assert_not_called()
    s._reconcile_room_observation.assert_not_called()


@pytest.mark.parametrize("duplicate_in", ["work", "dorm"])
def test_slot_by_slot_fallback_rejects_a_second_slot_for_the_same_resident(
    room_reader, frame, duplicate_in
):
    if duplicate_in == "work":
        s, install = room_reader("b102-initial")
        gray = frame("b102-initial")
        gray[1003:1060, 1595:] = 0
        gray[369:424, 1460:1785] = gray[160:215, 1460:1785]
        install(gray)
        room = B102
    else:
        s, install = room_reader("remove-bed-4-top")

        def lower(*args, **kwargs):
            gray = frame("remove-bed-4-bottom")
            gray[766:821, 1460:1785] = frame("remove-bed-4-top")[160:215, 1460:1785]
            install(gray)

        s.swipe.side_effect = lower
        room = DORM
    with pytest.raises(RecognizeError, match="重复|两个岗位"):
        s.get_agent_from_room(room)
    writes = [c.args[0] for c in s.op_data.update_detail.call_args_list]
    assert len(writes) == len(set(writes))
    s._reconcile_room_observation.assert_not_called()


@pytest.mark.parametrize("footer", ["hidden", "plausible_single_slot"])
def test_visible_extra_work_slots_survive_a_short_plan_and_a_bad_footer(
    room_reader, frame, footer
):
    s, install = room_reader("b102-empty1", planned=1)
    gray = frame("b102-empty1")
    gray[1003:1060, 1595:] = (
        0 if footer == "hidden" else frame("m203-initial")[1003:1060, 1595:]
    )
    install(gray)
    rows = s.get_agent_from_room(B102, strict_observation=True)
    assert tuple(r["agent"] for r in rows) == CASES["b102-empty1"][1]
    assert full_icon_searches(s) == 3
    s.swipe.assert_not_called()


def test_work_room_does_not_scroll_for_slots_beyond_its_capacity(room_reader):
    s, _ = room_reader("b102-initial", planned=6)
    s.scroll_room_operators = Mock(side_effect=AssertionError("工作间最多三岗"))
    rows = s.get_agent_from_room(B102, strict_observation=True)
    assert tuple(r["agent"] for r in rows) == WORK
    s.swipe.assert_not_called()


def test_card_alignment_is_required_before_using_the_count(room_reader):
    s, _ = room_reader("b102-empty1")
    # 局部遮住第三张卡的上边缘，姓名仍然完整。
    s.recog.gray[552:554, 1795:1805] = 120
    rows = s.get_agent_from_room(B102, strict_observation=True)
    assert tuple(row["agent"] for row in rows) == CASES["b102-empty1"][1]
    assert full_icon_searches(s) == 3


@pytest.mark.parametrize("masked", [False, True])
def test_extra_card_on_timer_retry_invalidates_a_short_room_observation(
    room_reader, frame, masked
):
    s, install = room_reader("m203-initial")
    original = frame("m203-initial")
    if masked:
        original[1003:1060, 1595:] = 0
    install(original)
    s.read_accurate_mood = Mock(return_value=12)
    real_read = s.read_screen._mock_wraps
    s.read_screen.side_effect = lambda img, **kw: (
        "?" if kw["type"] == "time" else real_read(img, **kw)
    )

    def retry(*args, **kwargs):
        gray = frame("b102-initial")
        gray[135:326, 1460:1805] = original[135:326, 1460:1805]
        gray[1003:1060, 1595:] = original[1003:1060, 1595:]
        install(gray)
        return STAMP + timedelta(hours=1)

    s.read_operator_time.side_effect = retry
    with pytest.raises(RecognizeError, match="换帧"):
        s.get_agent_from_room(B203, [0])
    s.op_data.update_detail.assert_not_called()
    s._reconcile_room_observation.assert_not_called()


@pytest.mark.parametrize(("tag", "planned"), [("b102-empty1", 1), ("m302-empty1", 3)])
def test_mismatched_plan_reads_actual_slots_without_inventing_vacancies(
    room_reader, tag, planned
):
    s, _ = room_reader(tag, planned=planned)
    room, names = CASES[tag]
    result = s.get_agent_from_room(room)
    assert tuple(row["agent"] for row in result[: len(names)]) == names
    assert full_icon_searches(s) >= max(planned, len(names))
    if planned > len(names):
        assert result[-1]["observed"] is False


@pytest.mark.parametrize(
    "changed", ["same", "other_slot", "covered", "same_buffer", "same_time"]
)
def test_timer_retry_rechecks_whole_counted_roster_before_write(
    room_reader, frame, changed
):
    s, install = room_reader("b102-empty2")
    expected_deadline = STAMP + timedelta(hours=1)
    original_read = s.read_screen._mock_wraps
    s.read_screen.side_effect = lambda img, **kw: (
        "?" if kw["type"] == "time" else original_read(img, **kw)
    )

    def retry(room, index, cord):
        assert (room, index, cord) == (B102, 0, ((1650, 270), (1780, 305)))
        tag = "b102-empty2" if changed in ("same", "covered") else "b102-empty1"
        new = frame(tag)
        if changed == "covered":
            new[1003:1060, 1595:] = 0
        if changed in ("same_buffer", "same_time"):
            s.recog.gray[:] = new
            new = s.recog.gray
        old_stamp = s.recog.capture_started_at
        install(new)
        if changed == "same_time":
            s.recog.capture_started_at = old_stamp
        return expected_deadline

    s.read_operator_time.side_effect = retry
    if changed == "same":
        rows = s.get_agent_from_room(B102, [0])
        assert rows[0]["time"] == expected_deadline
        assert tuple(r["agent"] for r in rows) == CASES["b102-empty2"][1]
    else:
        with pytest.raises(RecognizeError, match="换帧"):
            s.get_agent_from_room(B102, [0])
        s._reconcile_room_observation.assert_not_called()
        s.op_data.update_detail.assert_not_called()
        s.op_data.refresh_dorm_time.assert_not_called()
    assert s.read_operator_time.call_count == 1


@pytest.mark.parametrize(
    "changed",
    ["same", "previous_name", "previous_vacancy", "current_name", "wrong_room"],
)
def test_fallback_timer_retry_checks_previous_slots_and_current_resident(
    room_reader, frame, changed
):
    s, install = room_reader("b102-empty1")
    s.recog.gray[1003:1060, 1595:] = 0
    s.read_accurate_mood = Mock(return_value=13)
    deadline = STAMP + timedelta(hours=1)

    def retry(room, index, cord):
        assert index == 2
        gray = frame("b102-initial" if changed == "previous_vacancy" else "b102-empty1")
        if changed == "previous_name":
            gray[160:215, 1460:1785] = frame("m302-initial")[160:215, 1460:1785]
        if changed == "current_name":
            gray[578:633, 1460:1785] = frame("m302-initial")[160:215, 1460:1785]
        if changed == "wrong_room":
            s.detect_room.return_value = B302
        gray[1003:1060, 1595:] = 0
        install(gray)
        return deadline

    s.read_operator_time.side_effect = retry
    if changed == "same":
        rows = s.get_agent_from_room(B102, [2])
        assert tuple(row["agent"] for row in rows) == CASES["b102-empty1"][1]
        assert rows[2]["time"] == deadline
    else:
        with pytest.raises(RecognizeError, match="换帧"):
            s.get_agent_from_room(B102, [2])
        assert [c.args[3] for c in s.op_data.update_detail.call_args_list] == [0]
        s._reconcile_room_observation.assert_not_called()
    s.read_operator_time.assert_called_once()


def test_rechecking_a_timer_reuses_the_panel_verified_on_that_capture(
    room_reader, frame
):
    s, install = room_reader("b102-empty2")

    def refresh(room, *, after_roster, **kw):
        after_roster.update(
            facility="manufacture",
            frame=s.recog._img,
            captured_at=s.recog.capture_started_at,
        )

    s.refresh_facility_state.side_effect = refresh
    s._work_room_panel = Mock(return_value="open")
    s._read_room_facility_product = Mock(return_value=False)
    real_read = s.read_screen._mock_wraps
    s.read_screen.side_effect = lambda img, **kw: (
        "?" if kw["type"] == "time" else real_read(img, **kw)
    )

    def retry(*args, **kwargs):
        install(frame("b102-empty2"))
        return STAMP + timedelta(hours=1)

    s.read_operator_time.side_effect = retry
    rows = s.get_agent_from_room(B102, [0], facility_observation={})
    assert tuple(row["agent"] for row in rows) == CASES["b102-empty2"][1]
    s._work_room_panel.assert_called_once_with(B102)
    s.detect_room.assert_not_called()


def test_fallback_reuses_positively_read_names_only_on_the_capture_that_supplied_them(
    room_reader, frame
):
    s, install = room_reader("b102-initial")
    # 第三人的姓名残缺，左边仍有字迹。前两人的姓名各识别一次。
    s.recog.gray[578:633, 1460:1785] = 0
    s.recog.gray[600:607, 1473:1478] = 255
    real_read = s.read_screen._mock_wraps
    names = []

    def read(img, **kw):
        value = real_read(img, **kw)
        if kw["type"] == "name":
            names.append(value)
        return value

    s.read_screen.side_effect = read
    result = s.get_agent_from_room(B102)
    assert result[2]["observed"] is False
    assert names.count(WORK[0]) == names.count(WORK[1]) == 1

    old = s.recog.gray.copy()
    install(old)

    def replace_after_failed_read(img, **kw):
        value = real_read(img, **kw)
        if kw["type"] == "name" and not value:
            new = frame("b102-empty1")
            new[160:215, 1460:1785] = frame("m302-initial")[160:215, 1460:1785]
            install(new)
        return value

    s.read_screen.side_effect = replace_after_failed_read
    result = s.get_agent_from_room(B102)
    assert [r["agent"] for r in result] == ["斯卡蒂", "", WORK[2]]


def test_panel_refresh_after_names_were_read_rejects_old_vacancy(room_reader, frame):
    s, install = room_reader("b102-empty2")

    def refresh(room, *, after_roster, **kw):
        after_roster.update(
            facility="manufacture",
            frame=s.recog._img,
            captured_at=s.recog.capture_started_at,
        )

    s.refresh_facility_state.side_effect = refresh
    check = s._check_room_roster_frame

    def check_after_sample(room, observation, *, sampled=False):
        if s.read_screen.called and not s._work_room_panel.called:
            s.recog._img = s.recog._img.copy()
        check(room, observation, sampled=sampled)

    s._check_room_roster_frame = check_after_sample

    def fresh_panel(room):
        install(frame("b102-empty1"))
        return "open"

    s._work_room_panel = Mock(side_effect=fresh_panel)
    with pytest.raises(RecognizeError, match="换帧"):
        s.get_agent_from_room(B102, facility_observation={})
    s._work_room_panel.assert_called_once()
    s.op_data.update_detail.assert_not_called()
    s._reconcile_room_observation.assert_not_called()


def test_training_room_keeps_its_two_slot_reader(room_reader, monkeypatch):
    s, _ = room_reader("m302-initial")
    names = CASES["m302-initial"][1]
    observation = [
        {"agent": n, "mood": 18, "sample_mood": 18, "update_time": False} for n in names
    ]
    training = Mock(return_value=observation)
    monkeypatch.setattr(BaseSchedulerSolver, "_observe_training_room", training)
    forbidden = Mock(side_effect=AssertionError("训练室应使用专用读法"))
    monkeypatch.setattr(base_schedule, "room_occupancy", forbidden)
    monkeypatch.setattr(base_schedule, "read_room_occupancy", forbidden)
    result = s.get_agent_from_room("train")
    assert tuple(row["agent"] for row in result) == names
    training.assert_called_once()
    forbidden.assert_not_called()


def test_panel_verification_that_replaces_the_capture_precedes_counting(
    room_reader, frame
):
    s, install = room_reader("b102-empty2")
    for i, name in enumerate(WORK):
        s.op_data.operators[name].current_index = i

    def refresh(room, *, after_roster, **kw):
        after_roster.update(
            facility="manufacture",
            frame=s.recog._img,
            captured_at=s.recog.capture_started_at,
        )

    s.refresh_facility_state.side_effect = refresh
    s.turn_on_room_detail.side_effect = lambda room: install(frame("b102-empty3"))

    def verify(room):
        install(frame("b102-initial"))
        return "open"

    s._work_room_panel = Mock(side_effect=verify)
    s._read_room_facility_product = Mock(return_value=False)
    result = s.get_agent_from_room(B102, facility_observation={})
    assert tuple(r["agent"] for r in result) == WORK
    assert s._work_room_panel.call_count == 1
    s.detect_room.assert_not_called()


@pytest.fixture(scope="module")
def local_ocr():
    from arknights_mower.utils import rapidocr

    return rapidocr.create_engine(0.8, threads=2)


@pytest.mark.parametrize(
    ("bottom", "i", "name", "width", "seconds"),
    [
        (False, 3, "能天使", 293, 34 * 60 + 36),
        (True, 2, "虎狼丸", 164, 3 * 3600 + 45 * 60 + 29),
    ],
)
def test_edge_card_name_mood_and_raw_countdown_follow_same_offset(
    room_reader, frame, local_ocr, monkeypatch, bottom, i, name, width, seconds
):
    from arknights_mower.utils import rapidocr

    monkeypatch.setattr(rapidocr, "engine", local_ocr)
    s, install = room_reader(
        "remove-bed-1-bottom" if bottom else "clear-hi-off-pair_top"
    )
    if bottom:
        # 把实际读到虎狼丸倒计时的第 3 床原图放入仅住第 3、5 床的画面。
        gray = s.recog.gray.copy()
        gray[323:514, 1460:1785] = frame("clear-hi-off-pair_bottom")[323:514, 1460:1785]
        install(gray)
    captured_at = s.recog.capture_started_at
    rows = s.get_agent_from_room(DORM, [i], read_dorm_evidence=True)
    assert rows[i]["agent"] == name
    assert rows[i]["measured_mood"] == pytest.approx(width * 24 / 310)
    assert rows[i]["recovery_seconds"] == seconds
    assert rows[i]["time"] == captured_at + timedelta(seconds=seconds)
    s.swipe.assert_not_called()
    s.read_operator_time.assert_not_called()
