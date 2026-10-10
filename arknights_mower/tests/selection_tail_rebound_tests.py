"""末页抬手后的回弹不能沿用按住期间的卡片坐标。"""

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import AgentSelectionNotReady, BaseMixin
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import Recognizer

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


def image(name):
    return cv2.cvtColor(cv2.imread(str(FIXTURES / name)), cv2.COLOR_BGR2RGB)


def page(offset=0, train=False):
    rows = ((479, 506), (895, 922)) if train else ((488, 520), (909, 941))
    cards = tuple(
        (
            name,
            (
                (621 + i // 2 * 216 + offset, rows[i % 2][0]),
                (810 + i // 2 * 216 + offset, rows[i % 2][1]),
            ),
        )
        for i, name in enumerate(
            ("钼铅", "霜华", "杏仁", "雪雉", "维荻", "THRM-EX", "歌蕾蒂娅", "旅骨")
        )
    )
    if offset:
        cards = (
            ("空构", ((630, rows[0][0]), (818, rows[0][1]))),
            ("罗宾", ((630, rows[1][0]), (818, rows[1][1]))),
        ) + cards
    return cards


def target_scope(cards):
    return next(scope for name, scope in cards if name == "歌蕾蒂娅")


def solver_for(monkeypatch, mode, train=False, frames=None):
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "performance_mode", mode)
    held = (
        image("tail_held_20261010.jpg")
        if not train
        else np.full((1080, 1920, 3), 220, dtype=np.uint8)
    )
    fresh = np.zeros((1080, 1920, 3), dtype=np.uint8)
    settled = page(270, train)
    snapshots = iter(frames or [settled] * 5)
    current = {"page": page(train=train)}

    def capture():
        current["page"] = next(snapshots)
        frame = fresh.copy()
        frame[490, 700] = target_scope(current["page"])[0][0] % 255
        frame[480, 700] = frame[490, 700]
        return None, frame, frame[:, :, 0]

    solver = BaseMixin()
    solver.device = SimpleNamespace(screencap=MagicMock(side_effect=capture))
    solver.recog = Recognizer(solver.device)
    solver.recog.set_frame((None, held, held[:, :, 0]))
    solver.find = MagicMock(
        side_effect=lambda *_: bool(solver.recog.img.size) and False
    )
    solver.sleep = MagicMock(side_effect=lambda *_: solver.recog.update())
    solver.tap = MagicMock(side_effect=lambda *_, **__: solver.recog.update())
    solver.swipe_noinertia = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda *_, **__: current["page"])
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda *_: current["page"])
    monkeypatch.setattr(base_mixin, "agent_card_selected", lambda *_, **__: False)
    return solver, settled


@pytest.mark.parametrize("mode", ["xhigh", "high"])
@pytest.mark.parametrize(
    "train,full_scan", [(False, True), (False, False), (True, True)]
)
def test_tail_scan_relocates_target_after_release(monkeypatch, mode, train, full_scan):
    solver, settled = solver_for(monkeypatch, mode, train)
    observed = solver.observe_agent_page((), train=train, full_scan=full_scan)
    targets = ["歌蕾蒂娅"]

    selected, actual = solver.scan_agent(
        targets, train=train, full_scan=full_scan, observation=observed
    )

    assert selected == ["歌蕾蒂娅"] and targets == []
    assert actual == settled
    assert solver.device.screencap.call_count == 2
    solver.tap.assert_called_once_with(target_scope(settled), interval=0)
    solver.swipe_noinertia.assert_not_called()
    assert observed.image is None


@pytest.mark.parametrize("mode,captures", [("medium", 2), ("low", 3)])
def test_slow_tail_wait_does_not_count_held_frame_as_stable(
    monkeypatch, mode, captures
):
    solver, _ = solver_for(monkeypatch, mode, frames=[page()] * 3)
    observed = solver.observe_agent_page(())
    assert solver.wait_for_agent_page(observation=observed) == page()
    assert solver.device.screencap.call_count == captures


def test_tail_scan_waits_through_multiple_rebound_positions(monkeypatch):
    solver, settled = solver_for(
        monkeypatch, "xhigh", frames=[page(90), page(180), page(270), page(270)]
    )
    observed = solver.observe_agent_page(())
    assert solver.scan_agent(["歌蕾蒂娅"], observation=observed)[0] == ["歌蕾蒂娅"]
    assert solver.device.screencap.call_count == 4
    solver.tap.assert_called_once_with(target_scope(settled), interval=0)


def test_unsettled_tail_never_clicks_or_replays_swipe(monkeypatch):
    solver, _ = solver_for(
        monkeypatch, "xhigh", frames=[page(i * 10) for i in range(6)]
    )
    observed = solver.observe_agent_page(())
    targets = ["歌蕾蒂娅"]
    with pytest.raises(AgentSelectionNotReady):
        solver.scan_agent(targets, observation=observed)
    assert targets == ["歌蕾蒂娅"]
    solver.tap.assert_not_called()
    solver.swipe_noinertia.assert_not_called()


def test_stop_during_tail_wait_propagates_without_clicking(monkeypatch):
    solver, _ = solver_for(monkeypatch, "xhigh")
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        solver.scan_agent(["歌蕾蒂娅"], observation=solver.observe_agent_page(()))
    solver.tap.assert_not_called()


def test_original_frames_distinguish_partial_right_card_from_end_gap():
    tail = image("tail_held_20261010.jpg")
    tail_page = base_mixin.operator_list(tail, full_scan=False)
    assert "歌蕾蒂娅" in [name for name, _ in tail_page]
    assert BaseMixin.agent_page_has_right_gap(tail, tail_page)
    # 全部职业扫描区域之外的半张卡片仍证明列表填满右侧。
    ordinary = image("page_held_20261010.jpg")
    ordinary_page = base_mixin.operator_list(ordinary, full_scan=False)
    assert not BaseMixin.agent_page_has_right_gap(ordinary, ordinary_page)


@pytest.mark.parametrize("mode", ["xhigh", "high"])
def test_original_ordinary_page_retains_single_held_capture(monkeypatch, mode):
    solver, _ = solver_for(monkeypatch, mode)
    ordinary = image("page_held_20261010.jpg")
    solver.recog.set_frame((None, ordinary, ordinary[:, :, 0]))
    observed = solver.observe_agent_page(())
    assert solver.scan_agent(["歌蕾蒂娅"], observation=observed)[0] == ["歌蕾蒂娅"]
    solver.device.screencap.assert_not_called()
    solver.tap.assert_called_once_with(target_scope(page()), interval=0)


def test_unknown_tail_reading_never_supplies_old_target(monkeypatch):
    absent = tuple(
        ("砾" if name == "歌蕾蒂娅" else name, scope) for name, scope in page(270)
    )
    solver, _ = solver_for(monkeypatch, "xhigh", frames=[absent] * 2)
    targets = ["歌蕾蒂娅"]
    # 取帧标记不参与名字识别；新画面中的目标已经离开。
    solver.device.screencap.side_effect = lambda: (
        None,
        np.zeros((1080, 1920, 3), dtype=np.uint8),
        None,
    )
    readings = iter([page(), absent, absent])
    monkeypatch.setattr(base_mixin, "operator_list", lambda *_, **__: next(readings))
    selected, actual = solver.scan_agent(
        targets, observation=solver.observe_agent_page(())
    )
    assert selected == [] and actual == absent and targets == ["歌蕾蒂娅"]
    solver.tap.assert_not_called()


@pytest.mark.parametrize("train", [False, True])
def test_right_gap_requires_both_name_rows_to_be_blank(train):
    frame = np.full((1080, 1920, 3), 220, dtype=np.uint8)
    rows = ((479, 506), (895, 922)) if train else ((488, 520), (909, 941))
    frame[rows[1][1] - 8 : rows[1][1], 1600:1790] = 0
    assert not BaseMixin.agent_page_has_right_gap(frame, page(train=train), train=train)
