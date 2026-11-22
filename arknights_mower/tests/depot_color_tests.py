"""Offline depot identity checks using bundled icons and recorded item slots."""

import lzma
import pickle
import socket
import subprocess
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import depotREC as module
from arknights_mower.utils.image import loadimg

ROOT = Path(module.__rootdir__).parent
FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture(autouse=True)
def offline_io(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(module, "resource_ui_path", lambda _: None, raising=False)
    if hasattr(module, "_color_templates"):
        module._color_templates.cache_clear()
    yield
    forbidden.assert_not_called()
    if hasattr(module, "_color_templates"):
        module._color_templates.cache_clear()


@pytest.fixture
def solver():
    solver = module.depotREC.__new__(module.depotREC)
    solver.物品数字 = module.导入_数字模板()
    solver.结果字典 = {}
    solver._seen_names = set()
    solver._unconfirmed_names = set()
    return solver


@pytest.fixture
def models():
    result = {}
    for name in ("CONSUME", "NORMAL"):
        with lzma.open(ROOT / "arknights_mower/models" / f"{name}.pkl") as stream:
            result[name] = pickle.load(stream)
    return result


def icon(name, shift=4):
    image = loadimg(ROOT / "ui/public/depot" / f"{name}.webp")
    image = cv2.resize(image, (213, 213))
    return cv2.warpAffine(image, np.float32([[1, 0, shift], [0, 1, shift]]), (213, 213))


@pytest.fixture
def quantity_one(solver):
    # The first recorded slot is one expiring sanity potion.
    frame = loadimg(FIXTURES / "depot/consume_left_20261117.webp")
    return solver.切图主程序(frame[140:1000])[0][1]


@pytest.mark.parametrize(
    "name,category",
    [
        ("中坚高级干员调用凭证", "CONSUME"),
        ("寻访凭证", "NORMAL"),
        ("中坚寻访凭证", "NORMAL"),
        ("十连寻访凭证", "NORMAL"),
        ("十连中坚寻访凭证", "NORMAL"),
    ],
)
@pytest.mark.parametrize("shift", [0, 2, 4, -4])
def test_shifted_colored_vouchers_keep_their_identity_and_quantity(
    solver, models, quantity_one, name, category, shift
):
    assert solver.匹配物品一次(icon(name, shift), quantity_one, models[category]) == [
        name,
        1,
    ]


@pytest.mark.parametrize(
    "category,names",
    [
        ("CONSUME", ["感谢庆典干员凭证", "中坚高级干员调用凭证"]),
        ("NORMAL", ["寻访凭证", "中坚寻访凭证", "十连寻访凭证", "十连中坚寻访凭证"]),
    ],
)
def test_category_scan_does_not_merge_different_voucher_kinds(
    solver, models, quantity_one, monkeypatch, category, names
):
    items = [
        (icon(name, 0 if name == "感谢庆典干员凭证" else 4), quantity_one, str(i))
        for i, name in enumerate(names)
    ]
    monkeypatch.setattr(solver, "切图主程序", lambda *args: items)
    monkeypatch.setattr(
        solver,
        "_category_frames",
        lambda: iter([(0, np.zeros((1080, 1920, 3), dtype=np.uint8))]),
    )

    solver.分类扫描(models[category])

    assert solver.结果字典 == dict.fromkeys(names, 1)


def test_recorded_training_invitation_is_not_downgraded(solver, models):
    frame = loadimg(FIXTURES / "depot_consume_expiring_20261018.jpg")
    item, gray, _ = solver.切图主程序(frame[140:1000])[16]

    assert solver.匹配物品一次(item, gray, models["CONSUME"]) == [
        "资深干员特训邀请函",
        1,
    ]


def test_recorded_ordinary_and_kernel_permits_keep_separate_counts(
    solver, models, monkeypatch
):
    # Two slots from the same recorded basic-item page: ordinary 1, kernel 14.
    slots = loadimg(FIXTURES / "depot/headhunting_permits_20261118.png")
    frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    frame[154:700, 1228:1488] = slots
    monkeypatch.setattr(solver, "_category_frames", lambda: iter([(0, frame)]))

    solver.分类扫描(models["NORMAL"])

    assert solver.结果字典 == {"寻访凭证": 1, "中坚寻访凭证": 14}


def test_recorded_medicine_stacks_with_different_expiries_still_sum(
    solver, models, monkeypatch
):
    frame = loadimg(FIXTURES / "depot/consume_false_sort_20261116.jpg")
    # The two stacks in this column expire in six and thirteen days: 4 + 1.
    items = solver.切图主程序(frame[140:1000], [748])[:2]
    monkeypatch.setattr(solver, "切图主程序", lambda *args: items)
    monkeypatch.setattr(solver, "_category_frames", lambda: iter([(0, frame)]))

    solver.分类扫描(models["CONSUME"])

    assert solver.结果字典 == {"应急理智加强剂": 5}
    assert solver._unconfirmed_names == set()


@pytest.mark.parametrize("predicted", ["周年庆典干员凭证", "感谢庆典干员凭证"])
def test_identical_anniversary_icons_keep_the_model_label(predicted):
    assert (
        module._refine_item_color(
            icon("感谢庆典干员凭证", 0),
            predicted,
            ("周年庆典干员凭证", "感谢庆典干员凭证"),
        )
        == predicted
    )


@pytest.mark.parametrize("layout", ["public", "dist"])
def test_builtin_source_and_packaged_layouts_use_colored_icons(
    tmp_path, monkeypatch, layout
):
    directory = tmp_path / "ui" / layout / "depot"
    directory.mkdir(parents=True)
    for name in ("寻访凭证", "中坚寻访凭证"):
        (directory / f"{name}.webp").write_bytes(
            (ROOT / "ui/public/depot" / f"{name}.webp").read_bytes()
        )
    monkeypatch.setattr(module, "__rootdir__", tmp_path / "arknights_mower")
    if layout == "dist":
        import build_assets

        monkeypatch.setattr(build_assets, "PROJECT_ROOT", tmp_path)
        collected = build_assets._collect_ui_dist_datas()
        assert {Path(source).name for source, _ in collected} == {
            "寻访凭证.webp",
            "中坚寻访凭证.webp",
        }
        assert all(destination == "./ui/dist/depot" for _, destination in collected)

    assert (
        module._refine_item_color(
            icon("寻访凭证"), "中坚寻访凭证", ("寻访凭证", "中坚寻访凭证")
        )
        == "寻访凭证"
    )


def test_selected_resource_icons_do_not_fall_back_to_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "resource_ui_path", lambda _: tmp_path)
    assert (
        module._refine_item_color(
            icon("寻访凭证"), "中坚寻访凭证", ("寻访凭证", "中坚寻访凭证")
        )
        == "中坚寻访凭证"
    )


def test_selected_resource_icons_supply_color_correction(tmp_path, monkeypatch):
    for name in ("寻访凭证", "中坚寻访凭证"):
        (tmp_path / f"{name}.webp").write_bytes(
            (ROOT / "ui/public/depot" / f"{name}.webp").read_bytes()
        )
    monkeypatch.setattr(module, "resource_ui_path", lambda _: tmp_path)
    assert (
        module._refine_item_color(
            icon("寻访凭证"), "中坚寻访凭证", ("寻访凭证", "中坚寻访凭证")
        )
        == "寻访凭证"
    )


def test_unmatched_color_does_not_override_the_model():
    assert (
        module._refine_item_color(
            np.zeros((213, 213, 3), dtype=np.uint8),
            "中坚寻访凭证",
            ("寻访凭证", "中坚寻访凭证"),
        )
        == "中坚寻访凭证"
    )


@pytest.mark.parametrize(
    "item_rgb,original_rgb,expected,near_threshold",
    [
        ((69, 14, 0), (0, 255, 0), "candidate", True),  # 0.980031
        ((64, 13, 0), (0, 255, 0), "original", True),  # 0.979987
        ((255, 0, 0), (57, 13, 0), "candidate", True),  # gap 0.025035
        ((255, 0, 0), (79, 18, 0), "original", True),  # gap 0.024989
        ((255, 0, 0), (0, 255, 0), "candidate", False),
    ],
)
def test_color_decision_at_both_thresholds(
    tmp_path, monkeypatch, item_rgb, original_rgb, expected, near_threshold
):
    for name, color in (("candidate", (255, 0, 0)), ("original", original_rgb)):
        image = np.full((213, 213, 3), color[::-1], dtype=np.uint8)
        cv2.imencode(".webp", image, [cv2.IMWRITE_WEBP_QUALITY, 101])[1].tofile(
            tmp_path / f"{name}.webp"
        )
    monkeypatch.setattr(module, "resource_ui_path", lambda _: tmp_path)
    match = Mock(wraps=cv2.matchTemplate)
    monkeypatch.setattr(cv2, "matchTemplate", match)
    item = np.full((213, 213, 3), item_rgb, dtype=np.uint8)

    assert (
        module._refine_item_color(item, "original", ("original", "candidate"))
        == expected
    )
    masked_calls = [call for call in match.call_args_list if "mask" in call.kwargs]
    assert len(masked_calls) == (2 if near_threshold else 0)


def test_partly_black_search_retains_masked_opencv_scores(monkeypatch):
    names = ("寻访凭证", "中坚寻访凭证")
    item = np.zeros((213, 213, 3), dtype=np.uint8)
    item[32:181, 32] = 255
    region = item[32:181, 32:181]
    scores = []
    for name in names:
        template = icon(name, 0)[40:173, 40:173]
        result = cv2.matchTemplate(
            region, template, cv2.TM_CCORR_NORMED, mask=module._COLOR_ICON_MASK
        )
        score = cv2.minMaxLoc(result)[1]
        if np.isfinite(score):
            scores.append((score, name))
    scores.sort(reverse=True)
    expected = names[0]
    if (
        len(scores) == 2
        and scores[0][0] >= 0.98
        and scores[0][0] - scores[1][0] >= 0.025
    ):
        expected = scores[0][1]

    match = Mock(wraps=cv2.matchTemplate)
    monkeypatch.setattr(cv2, "matchTemplate", match)
    assert module._refine_item_color(item, names[0], names) == expected
    assert sum("mask" in call.kwargs for call in match.call_args_list) == len(names)
