from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.tests import dorm_recovery_evidence_tests, dorm_recovery_tests
from arknights_mower.tests.dorm_recovery_tests import ROOM
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.recognize import RecognizeError, Recognizer

solver = dorm_recovery_tests.solver
full_dorm_with_wrong_recipient = (
    dorm_recovery_evidence_tests.full_dorm_with_wrong_recipient
)


@pytest.fixture
def room_panel(full_dorm_with_wrong_recipient):
    scheduler, names, taps = full_dorm_with_wrong_recipient
    gray_card = scheduler.recog.gray.copy()
    captures = []
    device = Mock(spec=["screencap", "check_current_focus", "control"])

    def capture():
        names_now = scheduler.physical.copy()
        captures.append(names_now)
        gray = gray_card.copy()
        for i, top in ((2, 323), (3, 532), (4, 741)):
            gray[top + 25, 1460:1462] = i, len(captures) - 1
        return None, np.repeat(gray[:, :, None], 3, axis=2), gray

    device.screencap.side_effect = capture
    device.check_current_focus.return_value = False
    device.control = object()
    scheduler.device = device
    scheduler.recog = Recognizer(device)
    scheduler._room_list_at_end = Mock(side_effect=lambda bottom: bottom)
    scheduler.detect_room = Mock(return_value=ROOM)
    del scheduler.scroll_room_operators

    def find(res, **kwargs):
        image = scheduler.recog.img
        if res == "infra_no_operator":
            return not captures[image[766, 1461, 0]][4]
        return res == "room_detail"

    scheduler.find.side_effect = find
    scheduler.read_operator_in_room.side_effect = lambda crop: captures[crop[0, 1]][
        crop[0, 0]
    ]
    ordinary_read = scheduler.get_agent_from_room.side_effect

    def observe(*args, **kwargs):
        scheduler.recog.update()
        _ = scheduler.recog.img
        return ordinary_read(*args, **kwargs)

    scheduler.get_agent_from_room.side_effect = observe
    return scheduler, names, taps, captures


@pytest.mark.parametrize("supplied", [False, True])
def test_full_correction_only_uses_the_adjacent_local_read(room_panel, supplied):
    scheduler, names, taps, captures = room_panel
    prior = scheduler.get_agent_from_room(ROOM) if supplied else None
    result = scheduler.ensure_dorm_recovery_order(
        ROOM, names, correction_observation=prior
    )
    first_vacancy = names[:4] + [""]
    second_vacancy = names[:3] + ["", ""]
    assert [r["agent"] for r in result] == second_vacancy
    assert captures == [names] * (2 if supplied else 1) + [
        first_vacancy,
        second_vacancy,
    ]
    assert taps == [4, 3] and scheduler.task.dorm_recovery_restore == [ROOM]
    assert scheduler.task.plan[ROOM] == names


def test_normal_dispatch_restores_both_beds_after_one_capture_each(room_panel):
    scheduler, names, taps, captures = room_panel
    checked = []
    remove = scheduler.tap.side_effect

    def remove_bed(point):
        checked.append((len(captures), captures[-1]))
        remove(point)

    scheduler.tap.side_effect = remove_bed
    dorm_recovery_tests.arrange(scheduler)
    assert taps == [4, 3] and checked == [(1, names), (2, names[:4] + [""])]
    assert scheduler.physical == names and scheduler.confirms == [names]
    assert scheduler.op_data.operators[names[2]].dorm_recovery_room == ROOM
    assert not scheduler.task.plan and not scheduler.task.dorm_recovery_restore


@pytest.mark.parametrize("supplied", [False, True])
def test_single_fourth_removal_only_reuses_the_local_read(room_panel, supplied):
    scheduler, names, taps, captures = room_panel
    scheduler.op_data.operators[names[2]].mood = 8
    prior = scheduler.get_agent_from_room(ROOM) if supplied else None
    result = scheduler.ensure_dorm_recovery_order(
        ROOM, names, correction_observation=prior
    )
    vacancy = [*names[:3], "", names[4]]
    assert taps == [3] and captures == [names] * (2 if supplied else 1) + [vacancy]
    assert [row["agent"] for row in result] == vacancy
    assert scheduler.task.plan[ROOM] == names
    assert scheduler.task.dorm_recovery_restore == [ROOM]


@pytest.mark.parametrize("index", [3, 4])
@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "future",
        "invalidate",
        "replaced_image",
        "replaced_gray",
        "new_recognizer",
        "new_device",
        "rebound_during_focus",
        "invalidate_during_name",
        "focus",
        "title",
        "popup",
        "network",
        "upper",
        "missing_button",
        "wrong_name",
        "wrong_room",
        "new_task",
        "resume",
    ],
)
def test_rejected_first_frame_reads_the_bed_again(room_panel, change, index):
    scheduler, names, taps, captures = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    receipt = scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task)
    assert receipt is not None
    if change in ("expired", "future"):
        stamp = start + timedelta(seconds=-1.1 if change == "expired" else 5)
        scheduler.recog.capture_started_at = receipt.capture_started_at = stamp
    elif change == "invalidate":
        scheduler.recog.update()
    elif change == "replaced_image":
        scheduler.recog._img = scheduler.recog.img.copy()
    elif change == "replaced_gray":
        scheduler.recog._gray = scheduler.recog.gray.copy()
    elif change == "new_recognizer":
        scheduler.recog = Recognizer(scheduler.device)
        scheduler.recog._install_frame(
            (None, receipt.image, receipt.gray), receipt.capture_started_at
        )
    elif change == "new_device":
        scheduler.device = scheduler.recog.device = SimpleNamespace(
            screencap=scheduler.device.screencap,
            check_current_focus=scheduler.device.check_current_focus,
            control=scheduler.device.control,
        )
    elif change == "rebound_during_focus":

        def rebind():
            scheduler.device.control = object()
            return False

        scheduler.device.check_current_focus.side_effect = rebind
    elif change == "invalidate_during_name":
        read_name = scheduler.read_operator_in_room.side_effect

        def read(crop):
            name = read_name(crop)
            if len(captures) == 1:
                scheduler.recog.update()
            return name

        scheduler.read_operator_in_room.side_effect = read
    elif change == "focus":
        scheduler.recog.device.check_current_focus.side_effect = [True, False]
    elif change == "title":
        scheduler.detect_room.side_effect = ["dormitory_4", ROOM]
    elif change in ("popup", "network"):
        original = scheduler.find.side_effect
        scheduler.find.side_effect = lambda label, **kw: (
            True
            if len(captures) == 1
            and scheduler.recog._img is not None
            and label
            == {"popup": "double_confirm/main", "network": "connecting"}[change]
            else original(label, **kw)
        )
    elif change == "upper":
        scheduler._room_list_at_end.side_effect = lambda bottom: (
            len(captures) > 1 and bottom
        )
    elif change == "missing_button":
        top = 532 if index == 3 else 741
        scheduler.recog.gray[top + 64 : top + 132, 1804:1862] = 49
    elif change == "wrong_name":
        captures[0][index] = "红"
    elif change == "wrong_room":
        receipt.room = "dormitory_4"
    elif change == "new_task":
        scheduler.task = deepcopy(scheduler.task)
    else:
        scheduler.task.dorm_recovery_restore = [ROOM]
    assert scheduler._tap_dorm_remove_button(
        ROOM, index, names[index], read_frame=receipt
    )
    assert len(captures) == 2 and receipt.image is None
    assert taps == [index]


@pytest.mark.parametrize("index", [3, 4])
def test_changed_plan_cannot_remove_a_resident_for_the_old_plan(room_panel, index):
    scheduler, names, taps, captures = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    receipt = scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task)
    scheduler.task.plan[ROOM] = names[:4] + ["红"]
    with pytest.raises(RecognizeError, match="最终名单已变"):
        scheduler._tap_dorm_remove_button(ROOM, index, names[index], read_frame=receipt)
    assert captures == [names, names] and not taps
    assert receipt.image is None and not getattr(
        scheduler.task, "dorm_recovery_restore", ()
    )
    assert scheduler.task.plan[ROOM] == names[:4] + ["红"]


def test_lost_connection_before_first_tap_requires_a_new_room_read(room_panel):
    scheduler, names, taps, captures = room_panel
    original = scheduler.task
    scheduler.device.check_current_focus.side_effect = [False, DeviceRecoveryError()]
    with pytest.raises(DeviceRecoveryError):
        scheduler.ensure_dorm_recovery_order(ROOM, names)
    assert captures == [names] and not taps and original.plan[ROOM] == names
    assert not getattr(original, "dorm_recovery_restore", ())

    scheduler.device.check_current_focus.side_effect = None
    scheduler.ensure_dorm_recovery_order(ROOM, names)
    assert captures == [names, names, names[:4] + [""], names[:3] + ["", ""]]
    assert taps == [4, 3] and scheduler.task is original
    assert original.dorm_recovery_restore == [ROOM]


def test_focus_change_rejects_the_new_occupant_and_a_second_use(room_panel):
    scheduler, names, taps, captures = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    receipt = scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task)
    scheduler.physical[4] = "红"
    scheduler.recog.device.check_current_focus.side_effect = [True, False, False]
    for count in (2, 3):
        with pytest.raises(RecognizeError, match="住客已变化"):
            scheduler._tap_dorm_remove_button(ROOM, 4, names[4], read_frame=receipt)
        assert len(captures) == count
    assert not taps and not getattr(scheduler.task, "dorm_recovery_restore", ())


def test_second_click_reads_again_if_first_click_missed(room_panel):
    scheduler, names, taps, captures = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    receipt = scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task)
    scheduler.tap.side_effect = None
    assert scheduler._tap_dorm_remove_button(ROOM, 4, names[4], read_frame=receipt)
    assert not scheduler._tap_dorm_remove_button(
        ROOM, 3, names[3], expected_third=names[2], read_frame=receipt
    )
    assert scheduler.tap.call_count == 1 and captures == [names, names]
    assert scheduler.task.dorm_recovery_restore == [ROOM]


def test_second_click_rejects_even_an_unconsumed_full_room_frame(room_panel):
    scheduler, names, taps, captures = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    receipt = scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task)
    assert receipt is not None
    assert not scheduler._tap_dorm_remove_button(
        ROOM, 3, names[3], expected_third=names[2], read_frame=receipt
    )
    assert captures == [names, names] and not taps


@pytest.mark.parametrize(
    "change",
    ["earlier", "unknown", "duplicate", "partial", "another_room", "resume", "mock"],
)
def test_only_a_fresh_complete_five_bed_read_can_be_offered(room_panel, change):
    scheduler, names, _, _ = room_panel
    start = datetime.now()
    rows = scheduler.get_agent_from_room(ROOM)
    if change == "earlier":
        start = scheduler.recog.capture_started_at + timedelta(microseconds=1)
    elif change == "unknown":
        rows[3]["observed"] = False
    elif change == "duplicate":
        rows[2]["agent"] = rows[4]["agent"]
    elif change == "partial":
        rows.pop()
    elif change == "another_room":
        rows[4]["agent"] = "红"
    elif change == "resume":
        scheduler.task.dorm_recovery_restore = [ROOM]
    else:
        scheduler.recog = Mock()
    assert scheduler._dorm_removal_frame(ROOM, rows, start, scheduler.task) is None
