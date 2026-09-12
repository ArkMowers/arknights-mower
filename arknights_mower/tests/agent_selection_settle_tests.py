"""选人画面延迟、缺帧及重排顺序的回归测试。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402

TARGET = ["多萝西", "淬羽赫默", "娜斯提"]
OLD = ["斯卡蒂", "幽灵鲨", "娜斯提"]


def reader(monkeypatch, frames):
    solver = BaseMixin()
    snapshots = iter(frames)
    solver.recog = SimpleNamespace(img=None)

    def update():
        solver.recog.img = next(snapshots)

    solver.recog.update = MagicMock(side_effect=update)
    solver.sleep = MagicMock()
    solver.find = MagicMock(return_value=False)
    solver.tap = MagicMock()
    monkeypatch.setattr(
        base_mixin,
        "operator_list",
        lambda img, **kwargs: [
            (
                n,
                (
                    (630 + (i // 2) * 215, 488 + (i % 2) * 421),
                    (818 + (i // 2) * 215, 520 + (i % 2) * 421),
                ),
            )
            for i, n in enumerate(img)
        ],
    )
    return solver


def test_waits_for_delayed_selection_without_tapping_again(monkeypatch):
    solver = reader(monkeypatch, [OLD, OLD, TARGET, OLD, TARGET, TARGET])
    assert solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 6
    solver.tap.assert_not_called()


@pytest.mark.parametrize("frame", [[], TARGET[:2], ["", "淬羽赫默", "娜斯提"]])
def test_incomplete_names_pause_without_reselecting(monkeypatch, frame):
    solver = reader(monkeypatch, [frame] * 6)
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 6
    solver.tap.assert_not_called()


def test_stable_wrong_roster_is_a_selection_error(monkeypatch):
    solver = reader(monkeypatch, [OLD] * 6)
    assert not solver.verify_agent(TARGET, "room_3_3")


def test_changing_names_pause_instead_of_triggering_reselection(monkeypatch):
    solver = reader(monkeypatch, [OLD, TARGET] * 3)
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    solver.tap.assert_not_called()


def test_connection_at_timeout_does_not_report_stable_wrong_roster(monkeypatch):
    solver = reader(monkeypatch, [OLD] * 6)
    solver.find.side_effect = [False] * 5 + [True]
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    solver.tap.assert_not_called()


def test_ocr_errors_wait_without_sorting_or_clearing(monkeypatch):
    solver = reader(monkeypatch, [OLD] * 6)
    monkeypatch.setattr(base_mixin, "operator_list", MagicMock(side_effect=ValueError))
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    solver.tap.assert_not_called()


def test_reorder_uses_actual_stable_card_order(monkeypatch):
    actual = list(reversed(TARGET))
    solver = reader(monkeypatch, [OLD, actual, actual])
    assert solver.wait_for_arranged_agents(TARGET, ordered=False) == actual


def test_final_verification_requires_requested_order(monkeypatch):
    solver = reader(monkeypatch, [list(reversed(TARGET))] * 6)
    assert not solver.verify_agent(TARGET, "room_3_3")


def test_stop_during_wait_propagates_without_retry(monkeypatch):
    solver = reader(monkeypatch, [OLD])
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 1


def test_connection_overlay_breaks_consecutive_match(monkeypatch):
    solver = reader(monkeypatch, [TARGET] * 4)
    solver.find.side_effect = [False, True, False, False]
    assert solver.verify_agent(TARGET, "room_3_3")
    assert solver.recog.update.call_count == 4


def sort_reader(frames):
    solver = BaseMixin()
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.detect_arrange_order = MagicMock(side_effect=frames)
    solver.tap = MagicMock()
    solver.sleep = MagicMock()
    return solver


def test_sort_does_not_accept_matching_frame_from_before_click():
    down, up = ("技能", False), ("技能", True)
    solver = sort_reader([down, down, down, up, up, up, down, down])
    solver.switch_arrange_order("技能", "room_1_1")
    assert solver.detect_arrange_order.call_count == 8
    assert solver.tap.call_count == 2


def test_sort_waits_for_delayed_click_without_repeating_it():
    mood, skill = ("心情", True), ("技能", False)
    solver = sort_reader([mood, mood, None, mood, skill, skill])
    solver.switch_arrange_order("技能", "room_1_1")
    solver.tap.assert_called_once_with((1210, 60), interval=0.5)


@pytest.mark.parametrize("frame", [None, ("技能", False)])
def test_sort_pauses_when_click_cannot_be_acknowledged(frame):
    solver = sort_reader([("技能", False)] + [frame] * 6)
    with pytest.raises(MowerExit):
        solver.switch_arrange_order("技能", "central")
    solver.tap.assert_called_once()


def test_unknown_initial_sort_does_not_tap():
    solver = sort_reader([None] * 6)
    with pytest.raises(MowerExit):
        solver.switch_arrange_order("技能", "central")
    solver.tap.assert_not_called()


def test_sort_accepts_string_direction_and_dorm_coordinates():
    solver = sort_reader([("技能", False)] + [("心情", True)] * 2)
    solver.switch_arrange_order("心情", "dormitory_1", "true")
    solver.tap.assert_called_once_with((1352, 60), interval=0.5)


def test_stop_during_sort_does_not_repeat_click():
    solver = sort_reader([("技能", False)] * 2)
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.switch_arrange_order("技能", "central")
    solver.tap.assert_called_once()
