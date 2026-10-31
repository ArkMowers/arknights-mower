"""范围筛选保留特征顺序、浮点边界和识别坐标。"""

from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.utils import matcher, recognize
from arknights_mower.utils.scene import Scene


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (((10, 20), (20, 30)), [0, 2, 3]),
        (((10.00000001, 20), (20, 30)), [2, 3]),
        (((10, 20), (19.99999999, 30)), [0, 2]),
        (((10, 20.00000001), (20, 30)), [2, 3]),
        (((10, 20), (20, 29.99999999)), [0, 2]),
        (((0, 0), (40, 40)), [0, 1, 2, 3, 4]),
        (((30, 30), (40, 40)), []),
        (((20, 30), (20, 30)), [3]),
        (((20, 30), (10, 20)), []),
    ],
)
def test_scope_keeps_boundaries_and_descriptor_order(monkeypatch, scope, expected):
    coordinates = [(10, 20), (9, 25), (15, 25), (20, 30), (21, 25)]
    points = [cv2.KeyPoint(float(x), float(y), 1) for x, y in coordinates]
    descriptors = np.repeat(np.arange(5, dtype=np.uint8)[:, None], 32, axis=1)
    monkeypatch.setattr(matcher, "keypoints", lambda _: (points, descriptors))
    index = Mock(knnMatch=Mock(return_value=[]))
    monkeypatch.setattr(matcher, "flann", index)
    subject = matcher.Matcher(np.zeros((40, 40), dtype=np.uint8))
    assert subject.match(np.zeros((8, 8), dtype=np.uint8), scope=scope) is None
    if len(expected) < 2:
        index.knnMatch.assert_not_called()
    else:
        np.testing.assert_array_equal(
            index.knnMatch.call_args.args[1], descriptors[expected]
        )
    np.testing.assert_array_equal(subject.des, descriptors)
    assert [point.pt for point in subject.kp] == coordinates


def test_scope_preserves_keypoint_mapping_and_absolute_coordinates():
    template = np.random.default_rng(40).integers(0, 256, (80, 90), dtype=np.uint8)
    origin = np.zeros((320, 320), dtype=np.uint8)
    origin[50:130, 60:150] = template
    origin[180:260, 170:260] = template
    subject = matcher.Matcher(origin)
    for seed in (1, 18, 123):
        cv2.setRNGSeed(seed)
        assert subject.match(template, scope=((165, 175), (265, 265))) == [
            [170, 180],
            [260, 260],
        ]
        assert subject.match(template, scope=((55, 45), (155, 135))) == [
            [60, 50],
            [150, 130],
        ]


def test_unscoped_query_keeps_original_descriptors(monkeypatch):
    origin = np.random.default_rng(4).integers(0, 256, (80, 90), dtype=np.uint8)
    subject = matcher.Matcher(origin)
    index = Mock(knnMatch=Mock(return_value=[]))
    monkeypatch.setattr(matcher, "flann", index)
    convert = Mock(
        side_effect=AssertionError("unscoped query must not convert coordinates")
    )
    monkeypatch.setattr(matcher.cv2, "KeyPoint_convert", convert)
    assert subject.match(origin) is None
    assert index.knnMatch.call_args.args[1] is subject.des


@pytest.mark.parametrize("seed", [1, 18, 123])
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("depot_all_20261018.jpg", Scene.DEPOT),
        ("depot_consume_expiring_20261018.jpg", Scene.DEPOT),
        ("infra/base_main.png", Scene.INFRA_MAIN),
        ("clue/clue_live_room_details.png", Scene.INFRA_DETAILS),
        ("login/startup_logo_bright_20261016.jpg", Scene.LOADING),
    ],
)
def test_scene_replay_preserves_observed_page(seed, filename, expected):
    cv2.setRNGSeed(seed)
    device = Mock()
    device.check_current_focus.return_value = False
    data = (Path(__file__).parent / "fixtures" / filename).read_bytes()
    reader = recognize.Recognizer(device, data)
    assert reader.get_scene() == expected
    device.check_current_focus.assert_not_called()
    device.screencap.assert_not_called()
