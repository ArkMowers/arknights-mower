"""训练列表阴影末列保留完整姓名，不从缺失的卡片推断身份。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import character_recognize as recognition

FIXTURES = Path(__file__).parent / "fixtures" / "selection"
CHESTNUT_SCOPE = ((1699, 895), (1874, 922))


def archived_frame(label="settled"):
    bands = cv2.cvtColor(
        cv2.imread(str(FIXTURES / f"training_chestnut_{label}_bands_20261012.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[479:506, 545:1920] = bands[:27]
    frame[895:922, 545:1920] = bands[27:]
    return frame


def test_settled_tail_keeps_chestnut_and_other_card_positions():
    frame = archived_frame()
    original = frame.copy()
    page = recognition.operator_list_train(frame)
    assert page == (
        ("夜莺", ((612, 479), (787, 506))),
        ("阿米娅", ((612, 895), (787, 922))),
        ("", ((832, 479), (1007, 506))),
        ("流明", ((829, 895), (1004, 922))),
        ("闪灵", ((1046, 479), (1221, 506))),
        ("", ((1049, 895), (1224, 922))),
        ("华法琳", ((1264, 479), (1439, 506))),
        ("赫默", ((1264, 895), (1439, 922))),
        ("蜜莓", ((1481, 479), (1656, 506))),
        ("苏苏洛", ((1481, 895), (1656, 922))),
        ("调香师", ((1699, 479), (1874, 506))),
        ("褐果", CHESTNUT_SCOPE),
    )
    np.testing.assert_array_equal(frame, original)


def test_shadowed_upper_row_uses_complete_lower_card_geometry():
    frame = archived_frame()
    frame[479:506], frame[895:922] = frame[895:922].copy(), frame[479:506].copy()
    page = recognition.operator_list_train(frame)
    assert ("褐果", ((1699, 479), (1874, 506))) in page
    assert len(page) == 12


def test_held_tail_preserves_existing_name_scopes():
    page = recognition.operator_list_train(archived_frame("held"))
    assert [name for name, _ in page] == [
        "闪灵",
        "",
        "华法琳",
        "赫默",
        "蜜莓",
        "苏苏洛",
        "调香师",
        "褐果",
    ]
    assert page[-1] == ("褐果", ((1342, 895), (1517, 922)))


def test_missing_right_edges_in_both_rows_do_not_invent_column():
    frame = archived_frame()
    frame[479:506, 1876:] = frame[895:922, 1876:]
    assert "褐果" not in [name for name, _ in recognition.operator_list_train(frame)]


def test_misaligned_lower_card_does_not_borrow_other_column():
    frame = archived_frame()
    frame[895:922, 1670:] = np.roll(frame[895:922, 1670:], 12, axis=1)
    assert "褐果" not in [name for name, _ in recognition.operator_list_train(frame)]


@pytest.mark.parametrize("offset", [-3, 3])
def test_aligned_lower_card_keeps_its_own_displacement(offset):
    frame = archived_frame()
    frame[895:922, 1670:] = np.roll(frame[895:922, 1670:], offset, axis=1)
    page = recognition.operator_list_train(frame)
    assert page[-1] == ("褐果", ((1699 + offset, 895), (1874 + offset, 922)))


def test_clipped_column_does_not_infer_name_from_visible_text():
    frame = archived_frame()
    for top in (479, 895):
        frame[top : top + 27, 545:] = np.roll(frame[top : top + 27, 545:], 80, axis=1)
    assert "褐果" not in [name for name, _ in recognition.operator_list_train(frame)]


def test_geometry_without_name_stays_unknown():
    frame = archived_frame()
    frame[895:922, 1699:1874] = 20
    page = recognition.operator_list_train(frame)
    assert page[-1] == ("", CHESTNUT_SCOPE)
    assert "褐果" not in [name for name, _ in page]


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
def test_scan_selects_chestnut_from_settled_tail(monkeypatch, mode):
    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=archived_frame(), update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.wait_for_next_observation = MagicMock()
    solver.tap = MagicMock()
    targets = ["褐果"]

    selected, _ = solver.scan_agent(
        targets, max_agent_count=1, train=True, respect_train_selection=True
    )

    assert selected == ["褐果"]
    assert targets == []
    solver.tap.assert_called_once_with(
        CHESTNUT_SCOPE, interval=0.2 if mode == "medium" else 0
    )


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
def test_held_scan_selects_relocated_chestnut_after_release(monkeypatch, mode):
    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import config
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config.conf, "performance_mode", mode)
    held, settled = archived_frame("held"), archived_frame()
    solver = BaseMixin()
    solver.device = SimpleNamespace(
        screencap=MagicMock(return_value=(None, settled, settled[:, :, 0]))
    )
    solver.recog = Recognizer(solver.device)
    solver.recog.set_frame((None, held, held[:, :, 0]))
    solver.find = MagicMock(
        side_effect=lambda *_: bool(solver.recog.img.size) and False
    )
    solver.wait_for_next_observation = MagicMock(
        side_effect=lambda *_: solver.recog.update()
    )
    solver.tap = MagicMock()
    solver.swipe_noinertia = MagicMock()
    targets = ["褐果"]

    selected, _ = solver.scan_agent(
        targets, train=True, observation=solver.observe_agent_page((), train=True)
    )

    assert selected == ["褐果"]
    assert targets == []
    assert solver.device.screencap.call_count == 2
    solver.tap.assert_called_once_with(
        CHESTNUT_SCOPE, interval=0.2 if mode == "medium" else 0
    )
    solver.swipe_noinertia.assert_not_called()
