"""家具分解的保留策略、列表遍历和异常停止，不连接游戏。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from arknights_mower.solvers import furniture
from arknights_mower.utils.scene import Scene

REAL_FURNITURE_DETAILS = furniture.furniture_details
REAL_FURNITURE_BATCH = furniture.furniture_batch


@pytest.fixture
def solver():
    result = MagicMock()
    result.recog = SimpleNamespace(
        w=1920,
        h=1080,
        img=np.zeros((1080, 1920, 3), dtype=np.uint8),
        save_screencap=MagicMock(),
    )
    result.factory_scene.return_value = Scene.FACTORY_FORMULA
    return result


@pytest.fixture(autouse=True)
def known_furniture(monkeypatch):
    monkeypatch.setattr(
        furniture, "load_furniture_keep_counts", lambda: {"测试家具": 1}
    )
    monkeypatch.setattr(
        furniture, "furniture_details", lambda img, expected_count=1: ("测试家具", 3)
    )
    monkeypatch.setattr(furniture, "furniture_batch", lambda img: 2)


def title(x, y, text="家具零件"):
    return [[[x, y], [x + 100, y], [x + 100, y + 30], [x, y + 30]], text, 1]


def test_cards_follow_row_order_skip_singles_and_ignore_clipped_bottom(monkeypatch):
    # OCR 返回顺序不保证两列按行排列；最后一个只露出标题。
    ocr = MagicMock(
        side_effect=[
            ([title(1000, 39), title(260, 42), title(260, 310), title(260, 850)], 0),
            ([["1/1", 1]], 0),
            ([["7/1", 1]], 0),
            ([["2/1", 1]], 0),
        ]
    )
    monkeypatch.setattr(furniture.rapidocr, "engine", ocr)
    cards = furniture.furniture_cards(np.zeros((1080, 1920, 3), np.uint8))
    assert [count for _, count in cards] == [7, 1, 2]
    assert cards[0][0][0] < cards[1][0][0]
    assert ocr.call_count == 4


@pytest.mark.parametrize("quantity", ["", "? / 1", "2/2", "21"])
def test_unreadable_counts_stop_instead_of_silently_skipping(monkeypatch, quantity):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(side_effect=[([title(260, 42)], 0), ([[quantity, 1]], 0)]),
    )
    with pytest.raises(ValueError, match="无法读取家具数量"):
        furniture.furniture_cards(np.zeros((1080, 1920, 3), np.uint8))


def test_missing_list_is_not_reported_as_finished(monkeypatch, solver):
    monkeypatch.setattr(furniture.rapidocr, "engine", lambda *a, **kw: (None, 0))
    with pytest.raises(ValueError, match="未识别到家具列表"):
        furniture.furniture_cards(solver.recog.img)


@pytest.mark.parametrize(
    "text,expected", [("\u30001/1", 1), ("12/1", 12), ("100/1", 100)]
)
def test_quantity_accepts_ocr_whitespace_and_multiple_digits(
    monkeypatch, solver, text, expected
):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(side_effect=[([title(260, 42)], 0), ([[text, 1]], 0)]),
    )
    assert furniture.furniture_cards(solver.recog.img)[0][1] == expected


@pytest.mark.parametrize("state,expected", [("ON", True), ("OFF", False)])
def test_keep_one_reads_labeled_switch(monkeypatch, solver, state, expected):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        lambda *a, **kw: ([title(20, 20, "至少保留1件"), title(200, 20, state)], 0),
    )
    assert furniture.keep_one_enabled(solver.recog.img) is expected


def test_on_text_without_furniture_switch_is_rejected(monkeypatch, solver):
    monkeypatch.setattr(
        furniture.rapidocr, "engine", lambda *a, **kw: ([title(200, 20, "ON")], 0)
    )
    with pytest.raises(ValueError, match="未识别到家具"):
        furniture.keep_one_enabled(solver.recog.img)


def test_process_uses_max_once_and_confirms_result_without_operator_access(
    monkeypatch, solver
):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.side_effect = [
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_DASHBOARD,
        Scene.CONNECTING,
        Scene.FACTORY_PRODUCT_COLLECT,
    ]
    runner = furniture.FurnitureDismantler(solver)
    runner.process((0.37, 0.21), 3)
    assert solver.tap.call_args_list == [
        call((0.37 * 1920, 0.21 * 1080), interval=0.5),
        call((0.96 * 1920, 0.42 * 1080), interval=0.5),
        call((0.88 * 1920, 0.9 * 1080), interval=2),
    ]
    solver.back.assert_called_once()
    solver.recog.save_screencap.assert_called_once_with("furniture")
    solver.agent_arrange.assert_not_called()
    assert "op_data" not in solver._mock_children


@pytest.mark.parametrize("keep,valid", [(False, True), (True, False)])
def test_unsafe_or_disabled_recipe_never_submits(monkeypatch, solver, keep, valid):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: keep)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    solver.item_valid.return_value = valid
    with pytest.raises(RuntimeError):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert all(args.args[0][1] < 0.9 * 1080 for args in solver.tap.call_args_list)


def test_missing_result_never_retries_submission(monkeypatch, solver):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(RuntimeError, match="未进入预期界面"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert (
        sum(c.args[0] == (0.88 * 1920, 0.9 * 1080) for c in solver.tap.call_args_list)
        == 1
    )
    solver.back.assert_not_called()


def test_scan_resets_after_reordering_then_scrolls_until_bottom(monkeypatch, solver):
    scans = MagicMock(
        side_effect=[
            [((0.37, 0.21), 1), ((0.75, 0.21), 3)],
            # 成功后返回列表顶端；剩余重复家具因列表重排而上移。
            [((0.37, 0.21), 2)],
            [((0.37, 0.21), 1)],
            [((0.37, 0.21), 1)],
            # 下一页还有重复家具，不能仅凭同名「家具零件」判定到底。
            [((0.37, 0.21), 4)],
            [((0.37, 0.21), 1)],
            [((0.37, 0.21), 1)],
        ]
    )
    monkeypatch.setattr(furniture, "furniture_cards", scans)
    fingerprints = [0, 0, 0, 0, 50, 50, 50, 100, 100, 0, 0, 0, 0, 0, 0]
    monkeypatch.setattr(
        furniture,
        "list_fingerprint",
        lambda img: np.full((10, 10), fingerprints.pop(0), dtype=np.uint8),
    )
    runner = furniture.FurnitureDismantler(solver)
    runner.open_formula = MagicMock()
    runner.process = MagicMock(return_value=True)
    runner.run()
    assert runner.process.call_args_list == [
        call((0.75, 0.21), 3),
        call((0.37, 0.21), 2),
        call((0.37, 0.21), 4),
    ]
    assert runner.open_formula.call_count == 4
    assert solver.swipe_noinertia.call_count == 4
    solver.back_to_infrastructure.assert_called_once()


def test_open_formula_from_room_never_arranges_staff(solver):
    solver.factory_scene.side_effect = [
        Scene.FACTORY_ROOM,
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_FORMULA,
        Scene.FACTORY_FORMULA,
    ]
    furniture.FurnitureDismantler(solver).open_formula()
    solver.agent_arrange.assert_not_called()
    assert solver.tap.call_args_list[-2:] == [
        call((192, 1080 * 0.57), interval=0.5),
        call((192, 1080 * 0.71), interval=0.5),
    ]


@pytest.mark.parametrize("keep,stock", [(2, 2), (4, 2), (6, 5), (None, 8)])
def test_incomplete_sets_and_unknown_names_never_touch_max(
    monkeypatch, solver, keep, stock
):
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": keep} if keep else {}
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda img, expected_count=1: ("测试家具", stock),
    )
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    assert runner.process((0.37, 0.21), stock) is False
    assert solver.tap.call_count == 1


def test_inventory_mismatch_never_touches_max(solver):
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    assert furniture.FurnitureDismantler(solver).process((0.37, 0.21), 4) is False
    assert solver.tap.call_count == 1


def test_set_surplus_reduces_max_and_checks_final_batch(monkeypatch, solver):
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": 4}
    monkeypatch.setattr(
        furniture, "furniture_details", lambda img, expected_count=1: ("测试家具", 7)
    )
    monkeypatch.setattr(furniture, "furniture_batch", MagicMock(side_effect=[6, 3]))
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.side_effect = [
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_PRODUCT_COLLECT,
    ]
    assert runner.process((0.37, 0.21), 7)
    assert (
        solver.tap.call_args_list.count(call((0.84 * 1920, 0.68 * 1080), interval=0.2))
        == 3
    )
    assert solver.tap.call_args_list[-1] == call((0.88 * 1920, 0.9 * 1080), interval=2)


@pytest.mark.parametrize("maximum,final", [(0, 0), (3, 3), (2, 2)])
def test_bad_max_or_missed_minus_never_submits(monkeypatch, solver, maximum, final):
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": 2}
    monkeypatch.setattr(
        furniture, "furniture_batch", MagicMock(side_effect=[maximum, final])
    )
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(RuntimeError):
        runner.process((0.37, 0.21), 3)
    assert call((0.88 * 1920, 0.9 * 1080), interval=2) not in solver.tap.call_args_list


def test_protected_first_card_does_not_hide_later_cards_or_pages(monkeypatch, solver):
    runner = furniture.FurnitureDismantler(solver)
    runner.open_formula = MagicMock()
    runner.process = MagicMock(return_value=False)
    monkeypatch.setattr(
        furniture,
        "furniture_cards",
        MagicMock(
            side_effect=[
                [((0.37, 0.21), 2), ((0.75, 0.21), 3)],
                [((0.37, 0.4), 4)],
                [((0.37, 0.4), 4)],
            ]
        ),
    )
    levels = iter([0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 50])
    monkeypatch.setattr(
        furniture,
        "list_fingerprint",
        lambda img: np.full((10, 10), next(levels), np.uint8),
    )
    runner.run()
    assert runner.process.call_args_list[:3] == [
        call((0.37, 0.21), 2),
        call((0.75, 0.21), 3),
        call((0.37, 0.4), 4),
    ]
    assert runner.open_formula.call_args_list[1:] == [call(reset=False)] * 4
    assert solver.swipe_noinertia.call_count == 3
    solver.back_to_infrastructure.assert_called_once()


def test_returning_to_wrong_page_stops_before_next_selection(monkeypatch, solver):
    runner = furniture.FurnitureDismantler(solver)
    runner.open_formula = MagicMock()
    runner.process = MagicMock(return_value=False)
    monkeypatch.setattr(
        furniture, "furniture_cards", lambda img: [((0.37, 0.21), 2), ((0.75, 0.21), 3)]
    )
    levels = iter([0, 50])
    monkeypatch.setattr(
        furniture,
        "list_fingerprint",
        lambda img: np.full((10, 10), next(levels), np.uint8),
    )
    with pytest.raises(RuntimeError, match="位置发生变化"):
        runner.run()
    runner.process.assert_called_once_with((0.37, 0.21), 2)


@pytest.mark.parametrize("text,score", [("3/1", 0.8), ("3/2", 1), ("?", 1)])
def test_details_reject_uncertain_stock(monkeypatch, solver, text, score):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(side_effect=[([["测试家具", 1]], 0), ([[text, score]], 0)]),
    )
    with pytest.raises(ValueError):
        REAL_FURNITURE_DETAILS(solver.recog.img)


@pytest.mark.parametrize("stock", [2, 12, 100, 999])
def test_detail_stock_parser_accepts_multiple_digits(monkeypatch, solver, stock):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(side_effect=[([["测试家具", 1]], 0), ([[f"{stock}/1", 1]], 0)]),
    )
    assert REAL_FURNITURE_DETAILS(solver.recog.img, stock) == ("测试家具", stock)


def test_selected_furniture_changing_before_submit_stops(monkeypatch, solver):
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        MagicMock(side_effect=[("测试家具", 3), ("另一家具", 3)]),
    )
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(RuntimeError, match="无法确认保留完整套装"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert call((0.88 * 1920, 0.9 * 1080), interval=2) not in solver.tap.call_args_list


def test_empty_or_clipped_batch_is_rejected(solver):
    with pytest.raises(ValueError, match="为空或被裁切"):
        REAL_FURNITURE_BATCH(solver.recog.img)
    solver.recog.img[:] = [255, 220, 0]
    with pytest.raises(ValueError, match="为空或被裁切"):
        REAL_FURNITURE_BATCH(solver.recog.img)
