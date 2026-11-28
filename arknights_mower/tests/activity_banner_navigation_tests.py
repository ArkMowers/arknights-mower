from unittest.mock import MagicMock, call

import numpy as np
import pytest

from arknights_mower.solvers import activity_navigation, event_shop
from arknights_mower.utils.scene import Scene

SHOP = {
    "activity": "时间啊，向前！",
    "entry_names": ["残照终尽", "长冬初青", "世纪之春"],
    "activity_id": "act55side",
    "start_ts": 1793487600,
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
    solver.find_stage_image_and_enter.side_effect = (
        lambda *args, confirm_entry=None, **kwargs: (
            confirm_entry() if confirm_entry is not None else True
        )
    )
    solver.open_activity_overview_until_ready = MagicMock(return_value=False)
    solver.rank_activity_candidates = MagicMock(side_effect=AssertionError("AI called"))
    banners = [BANNER]
    monkeypatch.setattr(
        activity_navigation.ActivityNavigation, "token_entry", lambda _: None
    )

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (200, 1400):
            return banners, None
        if frame.shape[:2] == (1080, 1920):
            return [
                [[], "作战结束时间", 0.99],
                [[], "关闭时间：2026/11/29", 0.99],
                [[], "剩余10", 0.99],
                [[], SHOP["activity"], 0.99],
                [BANNER[0], "残照终尽", 0.99],
                [[], "TL-7", 0.99],
            ], None
        return [], None

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    return solver, banners


def test_shop_clicks_named_banner_and_confirms_shop_without_ai(navigation):
    solver, _ = navigation
    assert solver.run(SHOP)
    assert solver.tap.call_args_list == [
        call((270, 820), interval=0.2),
        call((1461, 255)),
    ]
    solver.open_activity_overview_until_ready.assert_not_called()
    solver.click_subtitle_if_needed.assert_not_called()
    solver.find_target_stage_after_entry.assert_not_called()
    solver.rank_activity_candidates.assert_not_called()
    assert solver.nav_steps == []


@pytest.mark.parametrize(
    "text",
    [
        "<时间啊，向前！>活动已开放",
        "《残照终尽》关卡已开放",
        "<长冬初青>EX关卡已开放",
        "＜世纪之春＞S关卡已开放",
        "长冬初青",
        '"长冬初青"内关卡已开放',
    ],
)
def test_shop_accepts_activity_and_chapter_banners(navigation, text):
    solver, banners = navigation
    banners[:] = [[BANNER[0], text, 0.99]]
    assert solver.run(SHOP)
    assert solver.tap.call_args_list == [
        call((270, 820), interval=0.2),
        call((1461, 255)),
    ]
    solver.open_activity_overview_until_ready.assert_not_called()


@pytest.mark.parametrize(
    "text,score",
    [
        ("<其他活动>关卡已开放", 0.99),
        ("<其他章节>关卡已开放", 0.99),
        ("<长冬初青>关卡已开放", 0.79),
        ("EX关卡已开放", 0.99),
    ],
)
def test_shop_rejects_unconfirmed_chapter_banners(navigation, text, score):
    solver, banners = navigation
    banners[:] = [[BANNER[0], text, score]]
    assert not solver.run(SHOP)
    solver.tap_and_detect_page_move.assert_not_called()
    solver.tap.assert_called_once_with((490, 1014), interval=0.2)


def test_duplicate_chapter_banners_do_not_click_shop(navigation):
    solver, banners = navigation
    banners[:] = [[BANNER[0], "<长冬初青>关卡已开放", 0.99]] * 2
    assert not solver.run(SHOP)
    solver.tap_and_detect_page_move.assert_not_called()
    solver.tap.assert_called_once_with((490, 1014), interval=0.2)


def test_chapter_banner_still_requires_confirmed_shop_page(navigation, monkeypatch):
    solver, banners = navigation
    banners[:] = [[BANNER[0], "<长冬初青>关卡已开放", 0.99]]
    monkeypatch.setattr(
        activity_navigation.ActivityNavigation, "confirm_shop", lambda _: False
    )
    assert not solver.run(SHOP)
    assert solver.tap.call_args_list == [
        call((270, 820), interval=0.2),
        call((1461, 255)),
    ]
    solver.recog.update.assert_called_once()


@pytest.mark.parametrize(
    "activity,ocr_title",
    [(SHOP["activity"], " 长 冬初青 "), (" 不义之财 复刻 ", "不 义之财　复刻")],
)
def test_activity_list_recognizes_chapter_title(
    navigation, monkeypatch, activity, ocr_title
):
    solver, _ = navigation
    solver.name = activity
    solver.stageType = "ACTIVITY"
    solver.stage_meta = {
        "zoneNameSecond": activity,
        "entryNames": SHOP["entry_names"],
    }
    monkeypatch.setattr(
        event_shop.NavigationSolver, "find_stage_banner_image", lambda *a, **k: None
    )
    monkeypatch.setattr(
        event_shop.rapidocr,
        "engine",
        lambda *a, **k: ([[BANNER[0], ocr_title, 0.99]], None),
    )
    assert solver.find_stage_banner(activity) == ((270, 70), (270, 70))


def test_activity_navigation_uses_only_its_own_chapter_names(navigation, monkeypatch):
    from arknights_mower.solvers import activity_navigation as stage_navigation

    solver, banners = navigation
    solver.name = "TL-7"
    solver.stage_meta = {"zoneNameSecond": SHOP["activity"]}
    monkeypatch.setattr(
        stage_navigation,
        "stage_data_full",
        [
            {
                "stageType": "ACTIVITY",
                "zoneNameSecond": SHOP["activity"],
                "subTitle": "长冬初青",
            },
            {
                "stageType": "ACTIVITY",
                "zoneNameSecond": "其他活动",
                "subTitle": "其他章节",
            },
        ],
    )
    banners[:] = [[BANNER[0], "<长冬初青>关卡已开放", 0.99]]
    assert solver.enter_activity_from_terminal()
    solver.tap_and_detect_page_move.reset_mock()
    banners[:] = [[BANNER[0], "<其他章节>关卡已开放", 0.99]]
    assert not solver.enter_activity_from_terminal()
    solver.tap_and_detect_page_move.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["other", "prefix", "low_score", "duplicate", "absent"]
)
def test_unconfirmed_banner_uses_list_entry_and_never_clicks_shop(navigation, fault):
    solver, banners = navigation
    if fault == "other":
        banners[:] = [[BANNER[0], "<其他活动>活动已开放", 0.99]]
    elif fault == "prefix":
        banners[:] = [[BANNER[0], "<其他章节>活动已开放", 0.99]]
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


def test_unconfirmed_terminal_entry_falls_back_to_activity_list(
    navigation, monkeypatch
):
    solver, _ = navigation
    solver.open_activity_overview_until_ready.return_value = True
    original = event_shop.rapidocr.engine
    clock = [0.0]
    monkeypatch.setattr(activity_navigation, "monotonic", lambda: clock[0])
    solver.sleep.side_effect = lambda _: clock.__setitem__(0, 5.0)

    def ocr(frame, **kwargs):
        if (
            frame.shape[:2] == (1080, 1920)
            and not solver.find_stage_image_and_enter.called
        ):
            return [], None
        return original(frame, **kwargs)

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert solver.run(SHOP)
    assert solver.tap.call_args_list == [
        call((270, 820), interval=0.2),
        call((490, 1014), interval=0.2),
        call((1461, 255)),
    ]
    solver.find_stage_image_and_enter.assert_called_once()


def test_activity_page_is_not_accepted_as_shop(navigation, monkeypatch):
    solver, _ = navigation
    original = event_shop.rapidocr.engine

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (1080, 1920) and solver.tap.call_args == call(
            (1461, 255)
        ):
            return [[[], SHOP["activity"], 0.99]], None
        return original(frame, **kwargs)

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert not solver.run(SHOP)
    assert solver.recog.update.call_count == 4
    assert solver.sleep.call_count == 2


@pytest.mark.parametrize("from_list", [False, True])
def test_shop_rejects_other_activity_even_if_fixed_point_would_open_a_shop(
    navigation, monkeypatch, from_list
):
    solver, banners = navigation
    if from_list:
        banners.clear()
        solver.open_activity_overview_until_ready.return_value = True
        monkeypatch.setattr(
            solver,
            "find_stage_image_and_enter",
            event_shop.NavigationSolver.find_stage_image_and_enter.__get__(solver),
        )
        monkeypatch.setattr(solver, "find_stage_banner", lambda _: ((270, 70),) * 2)
    original = event_shop.rapidocr.engine
    clock = [0.0]
    monkeypatch.setattr(activity_navigation, "monotonic", lambda: clock[0])
    solver.sleep.side_effect = lambda _: clock.__setitem__(0, clock[0] + 5.0)

    def ocr(frame, **kwargs):
        if frame.shape[:2] != (1080, 1920):
            return original(frame, **kwargs)
        if call((1461, 255)) in solver.tap.call_args_list:
            return [[[], "关闭时间", 0.99], [[], "剩余10", 0.99]], None
        return [[[], "其他活动", 0.99], [[], "作战结束时间", 0.99]], None

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert not solver.run(SHOP)
    assert call((1461, 255)) not in solver.tap.call_args_list


def test_ordinary_activity_navigation_reuses_banner_before_ai(navigation):
    solver, _ = navigation
    solver.name = "TL-7"
    solver.stageType = "ACTIVITY"
    solver.stage_meta = {
        "zoneNameSecond": SHOP["activity"],
        "subTitle": "残照终尽",
        "endTs": 9999999999,
    }
    solver._suppress_nav_recording = False
    solver.should_use_llm_navigation = MagicMock(
        side_effect=AssertionError("AI selected")
    )
    assert solver.try_quick_entry_from_main()
    assert solver.tap_and_detect_page_move.call_args_list == [
        call((270, 820), BANNER[1], record_step=False),
        call((270, 70), "残照终尽", record_step=False),
    ]
    solver.click_subtitle_if_needed.assert_not_called()
    solver.find_target_stage_after_entry.assert_called_once_with("TL-7", max_swipes=6)
    assert not solver._suppress_nav_recording


def test_shop_is_confirmed_from_fresh_frames_after_fixed_click(navigation, monkeypatch):
    solver, _ = navigation
    original = event_shop.rapidocr.engine
    shop_reads = []

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (1080, 1920) and solver.tap.call_args == call(
            (1461, 255)
        ):
            shop_reads.append(None)
            if len(shop_reads) == 1:
                return [], None
        return original(frame, **kwargs)

    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert solver.run(SHOP)
    assert len(shop_reads) == 2
    assert solver.recog.update.call_count == 3
    solver.sleep.assert_called_once_with(0.2)


@pytest.mark.parametrize("from_list", [False, True])
def test_shop_waits_for_activity_controls_while_background_keeps_animating(
    navigation, monkeypatch, from_list
):
    solver, banners = navigation
    solver.wait_for_scene_stable.return_value = False
    entry_point = (270, 820)
    if from_list:
        banners.clear()
        entry_point = (270, 70)
        solver.open_activity_overview_until_ready.return_value = True
        monkeypatch.setattr(
            solver,
            "find_stage_image_and_enter",
            event_shop.NavigationSolver.find_stage_image_and_enter.__get__(solver),
        )
        monkeypatch.setattr(solver, "find_stage_banner", lambda _: (entry_point,) * 2)
    original = event_shop.rapidocr.engine
    names = [[[], "残照终尽", 0.99]]
    activity_frames = iter([[], names, [*names, [[], "作战结束时间", 0.99]]])

    def on_tap(point, **kwargs):
        if point == (1461, 255):
            assert next(activity_frames, None) is None

    def ocr(frame, **kwargs):
        if frame.shape[:2] == (1080, 1920) and solver.tap.call_args == call(
            entry_point, interval=0.2
        ):
            return next(activity_frames), None
        return original(frame, **kwargs)

    solver.tap.side_effect = on_tap
    monkeypatch.setattr(event_shop.rapidocr, "engine", ocr)
    assert solver.run(SHOP)
    assert solver.tap.call_args == call((1461, 255))
    assert solver.sleep.call_args_list == [call(0.2), call(0.2)]
    solver.tap_and_detect_page_move.assert_not_called()
    if not from_list:
        solver.wait_for_scene_stable.assert_called_once_with(
            timeout_seconds=5, interval_seconds=0.2
        )
