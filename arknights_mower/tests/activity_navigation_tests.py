from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import activity_navigation as nav
from arknights_mower.utils.scene import Scene


@pytest.fixture
def activity(monkeypatch):
    stages = [
        {
            "id": "AB-1",
            "stageType": "ACTIVITY",
            "zoneNameSecond": "测试活动",
            "subTitle": "普通章节",
            "endTs": {"endTs": 9999999999},
            "drop": [{"type": "ACTIVITY_ITEM", "id": "test_token"}],
        }
    ]
    shop = {
        "activity": "测试活动",
        "entry_names": ["普通章节", "额外章节", "特别章节"],
        "chapters": {"normal": "普通章节", "ex": "额外章节", "s": "特别章节"},
        "x": 1000,
        "y": 200,
        "confirm_text": "测试商店",
    }
    monkeypatch.setattr(nav, "stage_data_full", stages)
    monkeypatch.setattr(nav, "activity_shop", lambda _: shop)
    return stages, shop


@pytest.mark.parametrize(
    "target,title", [("AB-EX-1", "额外章节"), ("AB-S-1", "特别章节")]
)
def test_stage_resolution_uses_the_activity_chapter_mapping(activity, target, title):
    meta = nav.resolve_activity_stage(target)
    assert meta["zoneNameSecond"] == "测试活动"
    assert meta["subTitle"] == title
    assert meta["id"] == target
    assert "drop" not in meta


def test_unrelated_and_ambiguous_activity_prefixes_are_not_guessed(activity):
    stages, _ = activity
    stages.append({"id": None, "stageType": "ACTIVITY"})
    assert nav.resolve_activity_stage("CD-EX-1") is None
    stages.append({**stages[0], "zoneNameSecond": "另一个活动"})
    assert nav.resolve_activity_stage("AB-EX-1") is None


@pytest.mark.parametrize(
    "point,expected",
    [((120, 300), (152, 332)), ((650, 800), (682, 832)), ((1100, 300), None)],
)
def test_currency_template_is_found_at_different_positions(
    activity, tmp_path, monkeypatch, point, expected
):
    root = tmp_path / "resource/template/items"
    root.mkdir(parents=True)
    template = np.random.default_rng(123).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    cv2.imwrite(str(root / "test_token.png"), cv2.cvtColor(template, cv2.COLOR_RGB2BGR))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    x, y = point
    frame[y : y + 64, x : x + 64] = template
    solver = SimpleNamespace(
        stage_meta=activity[0][0], recog=SimpleNamespace(img=frame)
    )
    monkeypatch.setattr(nav.config.conf, "maa_path", str(tmp_path))
    assert nav.ActivityNavigation(solver).token_entry() == expected


def test_missing_currency_does_not_match_unrelated_image(
    activity, tmp_path, monkeypatch
):
    monkeypatch.setattr(nav.config.conf, "maa_path", str(tmp_path))
    solver = SimpleNamespace(
        stage_meta=activity[0][0],
        recog=SimpleNamespace(img=np.zeros((1080, 1920, 3), np.uint8)),
    )
    assert nav.ActivityNavigation(solver).token_entry() is None


def test_token_entry_is_used_without_reading_changing_banner_text(
    activity, monkeypatch
):
    solver = SimpleNamespace(
        stage_meta=activity[0][0],
        scene=lambda: Scene.TERMINAL_MAIN,
        tap_and_detect_page_move=MagicMock(return_value=True),
        collect_terminal_ocr_candidates=MagicMock(
            side_effect=AssertionError("OCR used")
        ),
    )
    monkeypatch.setattr(nav.ActivityNavigation, "token_entry", lambda _: (333, 444))
    assert nav.ActivityNavigation(solver).enter_from_terminal()
    solver.tap_and_detect_page_move.assert_called_once_with(
        (333, 444), "测试活动", record_step=False
    )


def test_changed_page_without_target_activity_does_not_click_shop(
    activity, monkeypatch
):
    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    solver.open_activity_overview_until_ready.return_value = False
    navigator = nav.ActivityNavigation(solver, activity[1])
    monkeypatch.setattr(navigator, "enter_from_terminal", lambda: True)
    monkeypatch.setattr(navigator, "read", lambda: [[[], "其他活动", 0.99]])
    assert not navigator.open_shop()
    assert solver.tap.call_args_list == [(((490, 1014),), {"interval": 0.2})]


@pytest.mark.parametrize("kind", ["normal", "ex", "s"])
def test_chapter_map_requires_the_target_stage_pattern(activity, monkeypatch, kind):
    from arknights_mower.solvers.navigation import NavigationSolver

    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    for name in ("is_stage_code", "stage_pattern_stem", "normalize_stage_text"):
        setattr(solver, name, getattr(NavigationSolver, name).__get__(solver))
    solver.tap_and_detect_page_move.return_value = True
    navigator = nav.ActivityNavigation(solver, activity[1])
    title = activity[1]["chapters"][kind]
    target = {"normal": "AB-1", "ex": "AB-EX-1", "s": "AB-S-1"}[kind]
    box = [[100, 200], [300, 200], [300, 240], [100, 240]]
    reads = iter([[[box, "　".join(title), 0.99]], [[[], target, 0.99]]])
    monkeypatch.setattr(navigator, "read", lambda: next(reads))
    assert navigator.open_chapter(title, target)
    solver.tap_and_detect_page_move.assert_called_once_with(
        (200, 220), title, record_step=False
    )


def test_locked_s_chapter_never_selects_a_stage(activity, monkeypatch):
    solver = MagicMock()
    solver.stage_meta = {**activity[0][0], "subTitle": "特别章节"}
    solver.tap_and_detect_page_move.return_value = False
    navigator = nav.ActivityNavigation(solver, activity[1])
    monkeypatch.setattr(navigator, "open_page", lambda: True)
    monkeypatch.setattr(
        navigator,
        "read",
        lambda: [[[[100, 200], [300, 200], [300, 240], [100, 240]], "特别章节", 0.99]],
    )
    assert not navigator.open_stage("AB-S-1")
    solver.find_target_stage_after_entry.assert_not_called()


def test_chapter_animation_does_not_confirm_the_wrong_map(activity, monkeypatch):
    from arknights_mower.solvers.navigation import NavigationSolver

    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    for name in ("is_stage_code", "stage_pattern_stem", "normalize_stage_text"):
        setattr(solver, name, getattr(NavigationSolver, name).__get__(solver))
    solver.tap_and_detect_page_move.return_value = True
    navigator = nav.ActivityNavigation(solver, activity[1])
    box = [[100, 200], [300, 200], [300, 240], [100, 240]]
    reads = iter([[[box, "特别章节", 0.99]]] + [[[[], "AB-EX-1", 0.99]]] * 3)
    monkeypatch.setattr(navigator, "read", lambda: next(reads))
    assert not navigator.open_chapter("特别章节", "AB-S-1")
    assert solver.sleep.call_count == 2


def test_shop_click_uses_detected_currency_location_without_coordinates(
    activity, monkeypatch
):
    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    shop = {
        key: value
        for key, value in activity[1].items()
        if key not in {"x", "y", "confirm_text"}
    }
    navigator = nav.ActivityNavigation(solver, shop)
    monkeypatch.setattr(navigator, "open_page", lambda: True)
    monkeypatch.setattr(navigator, "shop_entry", lambda: (1300, 350))
    monkeypatch.setattr(navigator, "confirm_shop", lambda: True)
    assert navigator.open_shop()
    solver.tap.assert_called_once_with((1300, 350))


@pytest.mark.parametrize(
    "texts,expected",
    [
        (["关闭时间：2026/11/29", "剩余10"], True),
        (["兑换截止", "售罄"], True),
        (["作战结束时间", "剩余13天"], False),
        (["关闭时间", "剩余20天"], False),
    ],
)
def test_shop_requires_both_deadline_and_commodity_markers(
    activity, monkeypatch, texts, expected
):
    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    navigator = nav.ActivityNavigation(solver, activity[1])
    monkeypatch.setattr(navigator, "read", lambda: [[[], text, 0.99] for text in texts])
    assert navigator.confirm_shop() is expected
