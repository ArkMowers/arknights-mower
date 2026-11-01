from unittest.mock import MagicMock, call

import numpy as np
import pytest

from arknights_mower.solvers import event_shop
from arknights_mower.utils.scene import Scene

SHOP = {
    "activity": "时间啊，向前！",
    "x": 1461,
    "y": 255,
    "confirm_text": "炮火所掩埋的",
}
BANNER = [
    [[140, 50], [400, 50], [400, 90], [140, 90]],
    "<时间啊，向前！>活动已开放",
    0.99,
]


@pytest.fixture
def navigation(monkeypatch):
    solver = object.__new__(event_shop.EventShopNavigation)
    solver.recog = MagicMock()
    solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.scene = lambda: Scene.TERMINAL_MAIN
    for name in (
        "scene_graph_navigation",
        "sleep",
        "tap",
        "wait_for_scene_stable",
        "find_stage_image_and_enter",
        "click_subtitle_if_needed",
        "find_target_stage_after_entry",
    ):
        monkeypatch.setattr(solver, name, MagicMock(return_value=True))
    solver.tap_and_detect_page_move = MagicMock(return_value=True)
    solver.open_activity_overview_until_ready = MagicMock(return_value=False)
    solver.rank_activity_candidates = MagicMock(side_effect=AssertionError("AI called"))
    banners = [BANNER]

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (200, 1400):
            return banners, None
        if frame.shape[:2] == (1080, 1920):
            return [[[], SHOP["confirm_text"], 0.99]], None
        return [], None

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    return solver, banners


def test_shop_clicks_named_banner_and_confirms_title_without_ai(navigation):
    solver, _ = navigation
    assert solver.run(SHOP)
    solver.tap_and_detect_page_move.assert_called_once_with(
        (270, 820), BANNER[1], record_step=False
    )
    solver.tap.assert_called_once_with((1461, 255))
    solver.open_activity_overview_until_ready.assert_not_called()
    solver.click_subtitle_if_needed.assert_not_called()
    solver.find_target_stage_after_entry.assert_not_called()
    solver.rank_activity_candidates.assert_not_called()
    assert solver.nav_steps == []


@pytest.mark.parametrize(
    "fault", ["other", "prefix", "low_score", "duplicate", "absent"]
)
def test_unconfirmed_banner_uses_list_entry_and_never_clicks_shop(navigation, fault):
    solver, banners = navigation
    if fault == "other":
        banners[:] = [[BANNER[0], "<其他活动>活动已开放", 0.99]]
    elif fault == "prefix":
        banners[:] = [[BANNER[0], "<时间啊，向前！复刻>活动已开放", 0.99]]
    elif fault == "low_score":
        banners[:] = [[BANNER[0], BANNER[1], 0.79]]
    elif fault == "duplicate":
        banners.append(BANNER)
    else:
        banners.clear()
    assert not solver.run(SHOP)
    solver.tap_and_detect_page_move.assert_not_called()
    solver.tap.assert_called_once_with((490, 1014), interval=0.2)
    solver.open_activity_overview_until_ready.assert_called_once_with(max_taps=8)


def test_banner_click_without_page_change_falls_back_to_activity_list(navigation):
    solver, _ = navigation
    solver.tap_and_detect_page_move.return_value = False
    solver.open_activity_overview_until_ready.return_value = True
    assert solver.run(SHOP)
    assert solver.tap.call_args_list == [
        call((490, 1014), interval=0.2),
        call((1461, 255)),
    ]
    solver.find_stage_image_and_enter.assert_called_once_with(
        SHOP["activity"], max_swipes=10
    )


def test_wrong_shop_title_is_not_accepted_after_banner_entry(navigation):
    solver, _ = navigation
    assert not solver.run({**SHOP, "confirm_text": "其他兑换处"})
    assert solver.recog.update.call_count == 3
    assert solver.sleep.call_count == 2


def test_ordinary_activity_navigation_reuses_banner_before_ai(navigation):
    solver, _ = navigation
    solver.name = "TL-7"
    solver.stageType = "ACTIVITY"
    solver.stage_meta = {"zoneNameSecond": SHOP["activity"], "endTs": 9999999999}
    solver._suppress_nav_recording = False
    solver.should_use_llm_navigation = MagicMock(
        side_effect=AssertionError("AI selected")
    )
    assert solver.try_quick_entry_from_main()
    solver.tap_and_detect_page_move.assert_called_once_with(
        (270, 820), BANNER[1], record_step=False
    )
    solver.click_subtitle_if_needed.assert_called_once()
    solver.find_target_stage_after_entry.assert_called_once_with("TL-7", max_swipes=3)
    assert not solver._suppress_nav_recording


def test_shop_title_is_confirmed_from_fresh_frames_after_transition(
    navigation, monkeypatch
):
    solver, _ = navigation
    original = event_shop.rapidocr.engine
    shop_reads = []

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (1080, 1920):
            shop_reads.append(None)
            if len(shop_reads) == 1:
                return [], None
        return original(frame, **kwargs)

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert solver.run(SHOP)
    assert len(shop_reads) == 2
    assert solver.recog.update.call_count == 2
    solver.sleep.assert_called_once_with(0.2)
