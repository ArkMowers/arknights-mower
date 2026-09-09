"""家具分解的保留策略、列表遍历和异常停止，不连接游戏。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from arknights_mower.solvers import furniture
from arknights_mower.utils.scene import Scene


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
    runner.process((0.37, 0.21))
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
        furniture.FurnitureDismantler(solver).process((0.37, 0.21))
    assert all(args.args[0][1] < 0.9 * 1080 for args in solver.tap.call_args_list)


def test_missing_result_never_retries_submission(monkeypatch, solver):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(RuntimeError, match="未进入预期界面"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21))
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
    fingerprints = [0, 50, 50, 100, 0, 0, 0, 0]
    monkeypatch.setattr(
        furniture,
        "list_fingerprint",
        lambda img: np.full((10, 10), fingerprints.pop(0), dtype=np.uint8),
    )
    runner = furniture.FurnitureDismantler(solver)
    runner.open_formula = MagicMock()
    runner.process = MagicMock()
    runner.run()
    assert runner.process.call_args_list == [
        call((0.75, 0.21)),
        call((0.37, 0.21)),
        call((0.37, 0.21)),
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
