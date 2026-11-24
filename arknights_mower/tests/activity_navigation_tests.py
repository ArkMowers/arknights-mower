from types import SimpleNamespace
from unittest.mock import MagicMock, call

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


def test_rerun_currency_reuses_game_icon_in_terminal(activity, tmp_path, monkeypatch):
    stages, shop = activity
    token = "act46side_token_detector_rep_1"
    icon = "act46side_token_detector"
    stages[0]["drop"][0]["id"] = token
    shop.update(token_ids=[token], token_icon_ids=[icon])
    root = tmp_path / "cache/resource/template/items"
    root.mkdir(parents=True)
    template = np.random.default_rng(123).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    cv2.imwrite(str(root / f"{icon}.png"), template)
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver = SimpleNamespace(stage_meta=stages[0], recog=SimpleNamespace(img=frame))
    monkeypatch.setattr(nav.config.conf, "maa_path", str(tmp_path))
    navigator = nav.ActivityNavigation(solver)

    frame[300:364, 120:184] = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)
    assert navigator.token_entry() == (152, 332)


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


def test_changed_page_without_target_activity_does_not_open_stage(
    activity, monkeypatch
):
    solver = MagicMock()
    solver.stage_meta = activity[0][0]
    solver.open_activity_overview_until_ready.return_value = False
    navigator = nav.ActivityNavigation(solver, activity[1])
    monkeypatch.setattr(navigator, "enter_from_terminal", lambda: True)
    monkeypatch.setattr(navigator, "read", lambda: [[[], "其他活动", 0.99]])
    assert not navigator.open_stage("AB-1")
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


def test_shop_does_not_click_fixed_point_when_activity_entry_fails(
    activity, monkeypatch
):
    solver = MagicMock(stage_meta=activity[0][0])
    solver.open_activity_overview_until_ready.return_value = True
    solver.find_stage_image_and_enter.return_value = False
    navigator = nav.ActivityNavigation(solver, activity[1])
    monkeypatch.setattr(navigator, "enter_from_terminal", lambda **_: False)
    read = MagicMock()
    monkeypatch.setattr(navigator, "read", read)

    assert not navigator.open_shop((229, 826))
    assert solver.tap.call_args_list == [call((490, 1014), interval=0.2)]
    read.assert_not_called()


@pytest.mark.parametrize(
    "scores, expected",
    [((0.93, 0.82), (229, 926)), ((0.93, 0.91), None), ((0.82, 0.81), None)],
)
def test_terminal_currency_requires_a_unique_strong_template(
    activity, tmp_path, monkeypatch, scores, expected
):
    root = tmp_path / "resource/template/items"
    root.mkdir(parents=True)
    template = np.random.default_rng(123).integers(0, 100, (64, 64, 3), dtype=np.uint8)
    cv2.imwrite(str(root / "test_token.png"), template)
    cv2.imwrite(str(root / "alternate_token.png"), 255 - template)
    monkeypatch.setattr(nav.config.conf, "maa_path", str(tmp_path))

    primary, alternate = np.zeros((2, 811, 214), dtype=np.float32)
    primary[810, 213], alternate[284, 74] = scores
    empty = np.zeros((1, 1), dtype=np.float32)

    def match_template(_frame, scaled, _method):
        if scaled.shape[:2] != (32, 32):
            return empty
        return primary if scaled[0, 0, 0] < 128 else alternate

    monkeypatch.setattr(cv2, "matchTemplate", match_template)
    solver = SimpleNamespace(
        stage_meta=activity[0][0],
        recog=SimpleNamespace(img=np.zeros((1080, 1920, 3), dtype=np.uint8)),
    )
    shop = {**activity[1], "token_icon_ids": ["alternate_token"]}
    assert nav.ActivityNavigation(solver, shop).token_entry() == expected


@pytest.mark.parametrize(
    "capture_duration,ocr_duration,expected",
    [(12.0, 0.0, False), (2.0, 12.0, False), (2.0, 1.0, True)],
)
def test_activity_confirmation_shares_budget_between_capture_and_ocr(
    activity, tmp_path, monkeypatch, capture_duration, ocr_duration, expected
):
    from arknights_mower.utils import ocr_shared
    from arknights_mower.utils.device.io_budget import io_timeout

    clock = [0.0]
    monkeypatch.setattr(nav, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ocr_shared, "monotonic", lambda: clock[0])

    class Recognizer:
        def update(self):
            pass

        @property
        def img(self):
            duration = min(capture_duration, io_timeout(60))
            clock[0] += duration
            if duration < capture_duration:
                raise TimeoutError
            return np.zeros((8, 8), dtype=np.uint8)

    def read_response(_channel, deadline):
        duration = min(ocr_duration, deadline - clock[0])
        clock[0] += duration
        if duration < ocr_duration:
            raise TimeoutError
        return {
            "status": "ok",
            "result": ([[[], "测试活动", 0.99], [[], "作战结束时间", 0.99]], None),
        }

    ocr = ocr_shared.SharedOCREngine(directory=tmp_path)
    open_service = MagicMock(return_value=(MagicMock(), "token"))
    monkeypatch.setattr(ocr_shared, "open_service", open_service)
    monkeypatch.setattr(ocr_shared, "send_preamble", MagicMock())
    monkeypatch.setattr(ocr_shared, "send_json", MagicMock())
    monkeypatch.setattr(ocr_shared, "send", MagicMock())
    responses = iter(({"status": "authenticated"}, {"status": "ready"}))
    monkeypatch.setattr(
        ocr_shared,
        "read_json",
        lambda *args: next(responses, None) or read_response(*args),
    )
    monkeypatch.setattr(nav.rapidocr, "engine", ocr)

    solver = SimpleNamespace(stage_meta=activity[0][0], recog=Recognizer())
    navigator = nav.ActivityNavigation(solver, activity[1])

    assert navigator.confirm_activity_home() is expected
    assert clock[0] == (3.0 if expected else 5.0)
    if capture_duration < 5.0:
        open_service.assert_called_once_with(tmp_path, 5.0)
    else:
        open_service.assert_not_called()


def test_activity_confirmation_rejects_late_in_process_ocr_result(
    activity, monkeypatch
):
    clock = [0.0]
    monkeypatch.setattr(nav, "monotonic", lambda: clock[0])
    solver = MagicMock(stage_meta=activity[0][0])
    navigator = nav.ActivityNavigation(solver, activity[1])

    def read(*args, **kwargs):
        clock[0] += 12.0
        return [[[], "测试活动", 0.99], [[], "作战结束时间", 0.99]], None

    monkeypatch.setattr(nav.rapidocr, "engine", read)
    assert not navigator.confirm_activity_home()
    solver.recog.update.assert_called_once()
    solver.sleep.assert_not_called()


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
