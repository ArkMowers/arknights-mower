"""滑动后旧帧、漏识别及整页位置变化的回归测试。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import BaseMixin  # noqa: E402
from arknights_mower.utils.csleep import MowerExit  # noqa: E402


def page(names=("杜林", "芬", "克洛丝", "炎熔", "安赛尔", "香草"), offset=0):
    return tuple(
        (
            name,
            (
                (630 + (i // 2) * 215 + offset, 488 + (i % 2) * 421),
                (818 + (i // 2) * 215 + offset, 520 + (i % 2) * 421),
            ),
        )
        for i, name in enumerate(names)
    )


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
    solver.swipe_noinertia = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: img)
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: img)
    return solver


@pytest.mark.parametrize("train", [False, True])
def test_target_appearing_after_old_frame_is_selected_without_swiping(
    monkeypatch, train
):
    old = page()
    new = page(("杜林", "砾", "克洛丝", "炎熔", "安赛尔", "香草"))
    solver = reader(monkeypatch, [old, new, new])
    targets = ["砾"]
    selected, current = solver.scan_agent(targets, train=train)
    assert selected == ["砾"]
    assert targets == []
    assert current == new
    solver.tap.assert_called_once_with(new[1][1], interval=0.2)
    solver.swipe_noinertia.assert_not_called()


def test_missing_target_is_rechecked_before_returning_absent(monkeypatch):
    solver = reader(monkeypatch, [page(), page()])
    targets = ["苍苔"]
    assert solver.scan_agent(targets) == ([], page())
    assert targets == ["苍苔"]
    assert solver.recog.update.call_count == 2
    solver.tap.assert_not_called()


def test_names_at_moving_coordinates_cannot_be_clicked(monkeypatch):
    frames = [page(("砾", "苍苔"), offset) for offset in (100, 50, 0, 0)]
    solver = reader(monkeypatch, frames)
    assert solver.scan_agent(["砾"])[0] == ["砾"]
    solver.tap.assert_called_once_with(frames[-1][0][1], interval=0.2)
    assert solver.recog.update.call_count == 4


def test_second_target_is_relocated_after_first_click(monkeypatch):
    first = page(("砾", "苍苔", "杜林", "芬"))
    moved = page(("砾", "杜林", "苍苔", "芬"))
    solver = reader(monkeypatch, [first, first, moved, moved])
    assert solver.scan_agent(["砾", "苍苔"])[0] == ["砾", "苍苔"]
    assert [c.args[0] for c in solver.tap.call_args_list] == [first[0][1], moved[2][1]]


def test_free_slot_limit_does_not_overselect(monkeypatch):
    current = page(("砾", "苍苔"))
    solver = reader(monkeypatch, [current, current])
    free = ["砾", "苍苔"]
    assert solver.scan_agent(free, max_agent_count=1)[0] == ["砾"]
    assert free == ["苍苔"]
    solver.tap.assert_called_once()


@pytest.mark.parametrize("frame", [[], page(("", "苍苔"))])
def test_unreadable_page_pauses_without_tapping_or_swiping(monkeypatch, frame):
    solver = reader(monkeypatch, [frame] * 6)
    with pytest.raises(MowerExit):
        solver.scan_agent(["砾"])
    solver.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def test_connection_overlay_invalidates_previous_read(monkeypatch):
    solver = reader(monkeypatch, [page()] * 4)
    solver.find.side_effect = [False, True, False, False]
    assert solver.wait_for_agent_page() == page()
    assert solver.recog.update.call_count == 4


def test_matching_first_card_does_not_mean_end_of_list(monkeypatch):
    before = page()
    after = page(("杜林", "砾", "苍苔", "炎熔", "安赛尔", "香草"))
    solver = reader(monkeypatch, [after, after])
    assert solver.swipe_agent_page(before, ["砾"]) == 1
    solver.swipe_noinertia.assert_called_once()


def test_delayed_swipe_does_not_issue_another_page_swipe(monkeypatch):
    before = page()
    after = page(("砾", "苍苔", "克洛丝", "炎熔", "安赛尔", "香草"))
    solver = reader(monkeypatch, [before] * 4 + [after] * 2)
    assert solver.swipe_agent_page(before, ["砾"]) == 1
    assert solver.recog.update.call_count == 6
    solver.swipe_noinertia.assert_called_once()


def test_swipe_overlaps_two_columns(monkeypatch):
    before = page(tuple(str(i) for i in range(12)))
    after = page(tuple(str(i) for i in range(8, 20)))
    solver = reader(monkeypatch, [after, after])
    solver.swipe_agent_page(before, ["19"])
    solver.swipe_noinertia.assert_called_once_with((1490, 488), (-860, 0))


def test_failed_swipe_gets_only_one_short_confirmation(monkeypatch):
    before = page(tuple(str(i) for i in range(12)))
    after = page(tuple(str(i) for i in range(2, 14)))
    solver = reader(monkeypatch, [before] * 6 + [after, after])
    assert solver.swipe_agent_page(before, ["13"]) == 2
    assert [c.args[1] for c in solver.swipe_noinertia.call_args_list] == [
        (-860, 0),
        (-215, 0),
    ]


def test_unchanged_page_does_not_start_another_blind_search(monkeypatch):
    before = page()
    solver = reader(monkeypatch, [before] * 12)
    with pytest.raises(MowerExit):
        solver.swipe_agent_page(before, ["砾"])
    assert solver.recog.update.call_count == 12
    assert solver.swipe_noinertia.call_count == 2
    solver.tap.assert_not_called()


def test_incomplete_last_frame_cannot_be_reported_as_end(monkeypatch):
    before = page()
    solver = reader(monkeypatch, [before] * 5 + [[]])
    with pytest.raises(MowerExit):
        solver.swipe_agent_page(before, ["砾"])
    solver.swipe_noinertia.assert_called_once()


def test_stop_during_page_wait_does_not_send_more_input(monkeypatch):
    solver = reader(monkeypatch, [page()])
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.scan_agent(["砾"])
    solver.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def test_training_free_search_checks_next_page_when_first_page_has_no_target():
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

    solver = object.__new__(BaseSchedulerSolver)
    solver.profession_filter = MagicMock()
    solver.get_free_list = MagicMock(return_value=["砾"])
    solver.scan_agent = MagicMock(side_effect=[([], page()), (["砾"], page())])
    solver.swipe_agent_page = MagicMock(return_value=1)
    solver.swipe_left = MagicMock(return_value=0)
    solver.ctap = MagicMock()
    solver.verify_agent = MagicMock(return_value=True)
    solver.choose_train_ope("Free")
    solver.swipe_agent_page.assert_called_once_with(page(), ["Free"], train=True)
    solver.verify_agent.assert_called_once_with(["砾"], "train", train=True)
