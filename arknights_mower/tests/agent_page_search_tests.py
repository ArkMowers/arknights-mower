"""滑动后旧帧、漏识别及整页位置变化的回归测试。"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_mixin  # noqa: E402
from arknights_mower.solvers.base_mixin import (  # noqa: E402
    AgentSelectionNotReady,
    BaseMixin,
)
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
    solver.sleep = MagicMock(side_effect=lambda *args, **kwargs: solver.recog.update())
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
    with pytest.raises(AgentSelectionNotReady):
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
    with pytest.raises(AgentSelectionNotReady):
        solver.swipe_agent_page(before, ["砾"])
    assert solver.recog.update.call_count == 12
    assert solver.swipe_noinertia.call_count == 2
    solver.tap.assert_not_called()


def test_incomplete_last_frame_cannot_be_reported_as_end(monkeypatch):
    before = page()
    solver = reader(monkeypatch, [before] * 5 + [[]])
    with pytest.raises(AgentSelectionNotReady):
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


def test_pull_left_continues_until_actual_page_stops_moving():
    solver = BaseMixin()
    middle = page(offset=160)
    another = page(("砾", "苍苔", "克洛丝", "炎熔", "安赛尔", "香草"), 120)
    left = page()
    solver.wait_for_agent_page = MagicMock(side_effect=[middle, another, left, left])
    solver.swipe_noinertia = MagicMock()
    # 先连续回拉两次，仍需根据实际画面追加手势，不能按计数认定归零。
    assert solver.swipe_left(3, "ALL") == 0
    assert solver.swipe_noinertia.call_count == 5
    assert all(
        call.kwargs == {"interval": 0}
        for call in solver.swipe_noinertia.call_args_list[:2]
    )
    for call in solver.swipe_noinertia.call_args_list:
        start, movement = call.args
        assert start == (650, 540)
        assert 0 <= start[0] + movement[0] < 1920


def test_zero_counter_does_not_hide_clipped_first_column():
    solver = BaseMixin()
    clipped, left = page(offset=160), page()
    solver.wait_for_agent_page = MagicMock(side_effect=[clipped, left, left])
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(0, "ALL") == 0
    assert solver.swipe_noinertia.call_count == 2


def test_failed_pull_does_not_claim_list_is_at_left_edge():
    solver = BaseMixin()
    clipped = page(offset=160)
    solver.wait_for_agent_page = MagicMock(return_value=clipped)
    solver.swipe_noinertia = MagicMock()
    with pytest.raises(AgentSelectionNotReady):
        solver.swipe_left(3, "ALL")
    assert solver.swipe_noinertia.call_count == 3


@pytest.mark.parametrize("count,swipes", [(0, 1), (1, 1), (3, 3), (100, 9)])
def test_rewind_counter_only_batches_input_and_always_checks_end(count, swipes):
    solver = BaseMixin()
    solver.wait_for_agent_page = MagicMock(return_value=page())
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(count, "ALL") == 0
    assert solver.swipe_noinertia.call_count == swipes
    assert solver.wait_for_agent_page.call_count == 2


def test_stop_during_bulk_rewind_sends_no_more_input():
    solver = BaseMixin()
    solver.wait_for_agent_page = MagicMock()
    solver.swipe_noinertia = MagicMock(side_effect=[None, MowerExit])
    with pytest.raises(MowerExit):
        solver.swipe_left(8, "ALL")
    assert solver.swipe_noinertia.call_count == 2
    solver.wait_for_agent_page.assert_not_called()


def test_rewind_gestures_remain_bounded_when_every_page_changes():
    solver = BaseMixin()
    solver.wait_for_agent_page = MagicMock(
        side_effect=[page(offset=i * 15) for i in range(20)]
    )
    solver.swipe_noinertia = MagicMock()
    with pytest.raises(AgentSelectionNotReady):
        solver.swipe_left(100, "ALL")
    assert solver.swipe_noinertia.call_count == 12


def test_visible_correct_roster_is_not_read_from_later_columns(monkeypatch):
    # 用户截图中梅尔/迷迭香列被裁掉，第一张完整卡片位于 x≈790。
    clipped = page(("槐琥", "酒神", "结城理"), offset=160)
    solver = reader(monkeypatch, [clipped] * 6)
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(["迷迭香", "槐琥", "梅尔"], ordered=False)
    solver.tap.assert_not_called()


def test_zero_counter_does_not_hide_an_aligned_middle_page():
    solver = BaseMixin()
    middle = page(("槐琥", "酒神", "结城理"))
    left = page(("梅尔", "迷迭香", "槐琥"))
    solver.wait_for_agent_page = MagicMock(side_effect=[middle, left, left])
    solver.swipe_noinertia = MagicMock()
    assert solver.swipe_left(0, "ALL") == 0
    assert solver.swipe_noinertia.call_count == 2


def test_transient_clipping_waits_for_complete_roster_without_input(monkeypatch):
    targets = ["梅尔", "迷迭香", "槐琥"]
    clipped = page(("槐琥", "酒神", "结城理"), offset=160)
    complete = page(targets)
    solver = reader(monkeypatch, [clipped, complete, complete])
    assert solver.wait_for_arranged_agents(targets) == targets
    assert solver.recog.update.call_count == 3
    solver.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


@pytest.mark.parametrize("correct", [False, True])
def test_moving_roster_is_neither_accepted_nor_reported_wrong(monkeypatch, correct):
    targets = ["梅尔", "迷迭香", "槐琥"]
    names = targets if correct else ["槐琥", "酒神", "结城理"]
    solver = reader(
        monkeypatch, [page(names, offset) for offset in (20, 16, 12, 8, 4, 0)]
    )
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(targets)
    solver.tap.assert_not_called()


def test_position_must_settle_even_when_names_already_match(monkeypatch):
    targets = ["梅尔", "迷迭香", "槐琥"]
    solver = reader(monkeypatch, [page(targets, offset) for offset in (16, 8, 0, 0)])
    assert solver.wait_for_arranged_agents(targets) == targets
    assert solver.recog.update.call_count == 4


def test_clipped_last_frame_invalidates_wrong_roster(monkeypatch):
    targets = ["梅尔", "迷迭香", "槐琥"]
    wrong = page(("槐琥", "酒神", "结城理"))
    solver = reader(monkeypatch, [wrong] * 5 + [page(offset=160)])
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(targets)


def test_clipping_breaks_consecutive_matching_roster(monkeypatch):
    targets = ["梅尔", "迷迭香", "槐琥"]
    complete = page(targets)
    solver = reader(monkeypatch, [complete, page(offset=160), complete, complete])
    assert solver.wait_for_arranged_agents(targets) == targets
    assert solver.recog.update.call_count == 4


def test_missing_card_positions_cannot_confirm_selection(monkeypatch):
    targets = ["梅尔", "迷迭香", "槐琥"]
    solver = reader(monkeypatch, [[(name, None) for name in targets]] * 6)
    with pytest.raises(AgentSelectionNotReady):
        solver.wait_for_arranged_agents(targets)
    solver.tap.assert_not_called()


@pytest.mark.parametrize("train", [False, True])
def test_unchanged_name_pixels_reuse_matching_but_changed_names_are_reread(
    monkeypatch, train
):
    matcher = MagicMock(return_value=page())
    monkeypatch.setattr(base_mixin, "operator_list", matcher)
    monkeypatch.setattr(base_mixin, "operator_list_train", matcher)
    read = BaseMixin.agent_page_reader(train=train)
    first = np.zeros((1080, 1920, 3), dtype=np.uint8)
    unrelated_animation = first.copy()
    unrelated_animation[200:400, 800:900] = 255
    assert read(first) == read(unrelated_animation)
    assert matcher.call_count == 1
    changed_name = first.copy()
    changed_name[490, 800] = 255
    read(changed_name)
    assert matcher.call_count == 2


def test_name_cache_does_not_survive_a_new_wait(monkeypatch):
    matcher = MagicMock(return_value=page())
    monkeypatch.setattr(base_mixin, "operator_list", matcher)
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    BaseMixin.agent_page_reader()(img)
    BaseMixin.agent_page_reader()(img)
    assert matcher.call_count == 2
