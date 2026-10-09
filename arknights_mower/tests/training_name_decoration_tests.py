"""训练室姓名识别隔离黄白装饰，保留实际文字与未知姓名门槛。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import character_recognize as recognition

FIXTURES = Path(__file__).parent / "fixtures" / "selection"


def focused_name_frame(name, row=0):
    source = cv2.cvtColor(
        cv2.imread(str(FIXTURES / "training_ulpianus_first_20261009.jpg")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.full_like(source, 255)
    strip = np.zeros((27, 175, 3), np.uint8)
    # 原始特别关注图案与姓名分别绘制，覆盖标记和长姓名重叠的情况。
    strip[:, :48] = source[895:922, 801:849]
    template = recognition.OP_TRAIN[name]
    ys, xs = np.where(template > 0)
    glyphs = template[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = glyphs.shape
    right = max(165, min(width, strip.shape[1]))
    visible = glyphs[:26, -right:]
    section = strip[1 : 1 + min(height, 26), right - visible.shape[1] : right]
    section[visible > 0] = 255
    top = (479, 895)[row]
    frame[top : top + 27, 801:976] = strip
    return frame


@pytest.mark.parametrize("row", [0, 1])
@pytest.mark.parametrize(
    "name",
    [
        "山",
        "芬",
        "凛冬",
        "玛恩纳",
        "乌尔比安",
        "麒麟R夜刀",
        "火龙S黑角",
        "罗德岛隐秘队",
        "泰拉大陆调查团",
        "维娜·维多利亚",
        "W",
        "Lancet-2",
        "U-Official",
        "THRM-EX",
        "德·托莱多",
        "寒芒克洛丝",
        "凯尔希·思衡托",
        "阿米娅",
        "阿",
    ],
)
def test_special_focus_preserves_different_full_names(name, row):
    frame = focused_name_frame(name, row)
    original = frame.copy()
    assert [actual for actual, _ in recognition.operator_list_train(frame)] == [name]
    np.testing.assert_array_equal(frame, original)


def test_special_focus_supports_every_training_name_template(subtests):
    for name in recognition.OP_TRAIN:
        with subtests.test(name=name):
            frame = focused_name_frame(name)
            assert [actual for actual, _ in recognition.operator_list_train(frame)] == [
                name
            ]


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
@pytest.mark.parametrize("row", [0, 1])
@pytest.mark.parametrize("name", ["山", "火龙S黑角", "Lancet-2", "维娜·维多利亚"])
def test_training_scan_selects_other_special_focus_operators(
    monkeypatch, mode, row, name
):
    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "performance_mode", mode)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(
        img=focused_name_frame(name, row), update=MagicMock()
    )
    solver.find = MagicMock(return_value=False)
    solver.wait_for_next_observation = MagicMock()
    solver.tap = MagicMock()
    targets = [name]

    selected, _ = solver.scan_agent(
        targets, max_agent_count=1, train=True, respect_train_selection=True
    )

    assert selected == [name]
    assert targets == []
    top = (479, 895)[row]
    solver.tap.assert_called_once_with(
        ((799, top), (974, top + 27)), interval=0.2 if mode == "medium" else 0
    )


@pytest.mark.parametrize(
    "filename, expected",
    [
        (
            "training_ulpianus_first_20261009.jpg",
            [
                "玛恩纳",
                "怒潮凛冬",
                "山",
                "乌尔比安",
                "断罪者",
                "拉普兰德",
                "海沫",
                "刻刀",
                "骋风",
            ],
        ),
        (
            "training_ulpianus_scrolled_20261009.jpg",
            ["山", "乌尔比安", "断罪者", "拉普兰德", "海沫", "刻刀", "骋风", "慕斯"],
        ),
    ],
)
def test_archive_pages_recognize_ulpianus_without_changing_other_names(
    filename, expected
):
    frame = cv2.cvtColor(cv2.imread(str(FIXTURES / filename)), cv2.COLOR_BGR2RGB)
    original = frame.copy()
    assert [name for name, _ in recognition.operator_list_train(frame)] == expected
    np.testing.assert_array_equal(frame, original)


@pytest.mark.parametrize("mode", ["medium", "high", "xhigh"])
@pytest.mark.parametrize(
    "filename, scope",
    [
        ("training_ulpianus_first_20261009.jpg", ((801, 895), (976, 922))),
        ("training_ulpianus_scrolled_20261009.jpg", ((673, 895), (848, 922))),
    ],
)
def test_real_training_scan_selects_ulpianus_without_more_search(
    monkeypatch, mode, filename, scope
):
    from arknights_mower.solvers.base_mixin import BaseMixin
    from arknights_mower.utils import config

    monkeypatch.setattr(config.conf, "performance_mode", mode)
    frame = cv2.cvtColor(cv2.imread(str(FIXTURES / filename)), cv2.COLOR_BGR2RGB)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.wait_for_next_observation = MagicMock()
    solver.tap = MagicMock()
    targets = ["乌尔比安"]

    selected, _ = solver.scan_agent(
        targets, max_agent_count=1, train=True, respect_train_selection=True
    )

    assert selected == ["乌尔比安"]
    assert targets == []
    solver.tap.assert_called_once_with(scope, interval=0.2 if mode == "medium" else 0)


@pytest.mark.parametrize("row", [0, 1])
def test_decoration_is_isolated_in_both_training_rows(row):
    source = cv2.cvtColor(
        cv2.imread(str(FIXTURES / "training_ulpianus_first_20261009.jpg")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.full_like(source, 255)
    top = (479, 895)[row]
    frame[top : top + 27, 801:976] = source[895:922, 801:976]
    result = recognition.operator_list_train(frame)
    assert result == (("乌尔比安", ((799, top), (974, top + 27))),)


@pytest.mark.parametrize("name", ["泰拉大陆调查团", "罗德岛隐秘队", "Lancet-2"])
@pytest.mark.parametrize("decorated", [False, True])
def test_long_names_are_not_truncated(name, decorated):
    frame = np.full((1080, 1920, 3), 255, np.uint8)
    strip = np.zeros((27, 175, 3), np.uint8)
    template = recognition.OP_TRAIN[name]
    ys, xs = np.where(template > 0)
    glyphs = template[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = glyphs.shape
    strip[1 : height + 1, 165 - width : 165] = glyphs[:, :, None]
    if decorated:
        # 长姓名的首字位于固定截断范围内，仍从实际起点参与匹配。
        strip[1:25, :2] = (255, 210, 0)
    frame[479:506, 801:976] = strip
    assert [actual for actual, _ in recognition.operator_list_train(frame)] == [name]


def test_unknown_decorated_name_stays_unknown():
    frame = np.full((1080, 1920, 3), 255, np.uint8)
    strip = np.zeros((27, 175, 3), np.uint8)
    cv2.fillConvexPoly(strip, np.array([[0, 0], [45, 26], [0, 26]]), (255, 210, 0))
    strip[3:25, 60:165:2] = 255
    frame[479:506, 801:976] = strip
    assert [name for name, _ in recognition.operator_list_train(frame)] == [""]
