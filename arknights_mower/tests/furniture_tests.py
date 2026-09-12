"""家具分解的保留策略、列表遍历和异常停止，不连接游戏。"""

from datetime import datetime, timedelta
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
    result.recog.img[300:315, 800:830] = 255
    result.factory_scene.return_value = Scene.FACTORY_FORMULA
    result.tasks = []
    result.task = None
    return result


@pytest.fixture(autouse=True)
def known_furniture(monkeypatch):
    monkeypatch.setattr(
        furniture, "load_furniture_keep_counts", lambda: {"测试家具": 1}
    )
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda img, expected_count=1, expected_batch=None: ("测试家具", 3),
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
    monkeypatch.setattr(furniture, "keep_switch_visual_state", lambda img: expected)
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
    assert solver.recog.save_screencap.call_args_list == [call("furniture")] * 2
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
    with pytest.raises(furniture.FurnitureSafetyError, match="未进入预期界面"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert (
        sum(c.args[0] == (0.88 * 1920, 0.9 * 1080) for c in solver.tap.call_args_list)
        == 1
    )
    solver.back.assert_not_called()


@pytest.mark.parametrize("when", ["minus", "before_submit"])
def test_new_due_task_stops_batch_without_submitting(monkeypatch, solver, when):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": 3 if when == "minus" else 1}
    stock = 6 if when == "minus" else 3
    monkeypatch.setattr(furniture, "furniture_batch", lambda img: stock - 1)
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda img, *args: ("测试家具", stock),
    )

    def add_due_task(*args, **kwargs):
        solver.tasks.append(SimpleNamespace(time=datetime.now()))

    if when == "minus":

        def tap(point, **kwargs):
            if point == (
                1920 * furniture.MINUS_BUTTON[0],
                1080 * furniture.MINUS_BUTTON[1],
            ):
                add_due_task()

        solver.tap.side_effect = tap
    else:
        solver.recog.save_screencap.side_effect = add_due_task
    with pytest.raises(furniture.FurnitureDeadlineReached):
        runner.process((0.37, 0.21), stock)
    assert all(
        c.args[0] != (1920 * 0.88, 1080 * 0.9) for c in solver.tap.call_args_list
    )


def test_submission_connection_failure_is_terminal(monkeypatch, solver):
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD

    def tap(point, **kwargs):
        if point == (1920 * 0.88, 1080 * 0.9):
            raise ConnectionError("提交后连接中断")

    solver.tap.side_effect = tap
    with pytest.raises(furniture.FurnitureSafetyError, match="提交结果无法确认"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert (
        sum(c.args[0] == (1920 * 0.88, 1080 * 0.9) for c in solver.tap.call_args_list)
        == 1
    )


def test_due_task_stops_before_opening_furniture_page(solver):
    solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(seconds=30))]
    runner = furniture.FurnitureDismantler(solver)
    runner.run()
    solver.enter_room.assert_not_called()
    solver.tap.assert_not_called()
    solver.back_to_infrastructure.assert_called_once_with()


def test_total_budget_includes_navigation_and_exits_normally(monkeypatch, solver):
    elapsed = 0
    monkeypatch.setattr(furniture, "monotonic", lambda: elapsed)
    runner = furniture.FurnitureDismantler(solver)

    def open_formula():
        nonlocal elapsed
        elapsed = furniture.FURNITURE_RUN_SECONDS

    runner.open_formula = open_formula
    runner.process = MagicMock()
    runner.run()
    runner.process.assert_not_called()
    solver.swipe_noinertia.assert_not_called()
    solver.back_to_infrastructure.assert_called_once_with()


def test_exit_connection_failure_does_not_restart_scan(monkeypatch, solver):
    solver.tasks = [SimpleNamespace(time=datetime.now())]
    solver.back_to_infrastructure.side_effect = ConnectionError("返回失败")
    with pytest.raises(furniture.FurnitureSafetyError, match="不重新分解"):
        furniture.FurnitureDismantler(solver).run()
    solver.tap.assert_not_called()


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
        lambda img, expected_count=1, expected_batch=None: ("测试家具", stock),
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
    monkeypatch.setattr(furniture, "batch_image_changed", lambda *args: True)
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda img, expected_count=1, expected_batch=None: ("测试家具", 7),
    )
    monkeypatch.setattr(
        furniture, "furniture_batch", MagicMock(side_effect=[6, 5, 4, 3, 3])
    )
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
        lambda img: np.full((10, 10), next(levels, 50), np.uint8),
    )
    with pytest.raises(RuntimeError, match="位置发生变化"):
        runner.run()
    runner.process.assert_called_once_with((0.37, 0.21), 2)


def test_return_animation_can_settle_without_changing_list(monkeypatch, solver):
    runner = furniture.FurnitureDismantler(solver)
    levels = iter([50, 0])
    monkeypatch.setattr(
        furniture,
        "list_fingerprint",
        lambda img: np.full((10, 10), next(levels), np.uint8),
    )
    runner.wait_list_position(np.zeros((10, 10), np.uint8))
    solver.sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize("text,score", [("3/1", 0.8), ("3/?", 1), ("?", 1)])
def test_details_reject_uncertain_stock(monkeypatch, solver, text, score):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "测试家具")], 0),
                ([["测试家具", 1]], 0),
                ([[text, score]], 0),
            ]
        ),
    )
    with pytest.raises(ValueError):
        REAL_FURNITURE_DETAILS(solver.recog.img)


@pytest.mark.parametrize("stock", [2, 12, 100, 999])
def test_detail_stock_parser_accepts_multiple_digits(monkeypatch, solver, stock):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "测试家具")], 0),
                ([["测试家具", 1]], 0),
                ([[f"{stock}/1", 1]], 0),
            ]
        ),
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


@pytest.mark.parametrize("name", ["桌子", "货物垫板", "街头涂鸦"])
def test_names_are_detected_before_recognition(monkeypatch, solver, name):
    engine = MagicMock(
        side_effect=[([title(10, 10, name)], 0), ([[name, 1]], 0), ([["2/1", 1]], 0)]
    )
    monkeypatch.setattr(furniture.rapidocr, "engine", engine)
    assert REAL_FURNITURE_DETAILS(solver.recog.img, 2) == (name, 2)
    assert engine.call_args_list[0].kwargs["use_det"] is True


@pytest.mark.parametrize(
    "candidate,score,expected",
    [("“桌子”", 1, "“桌子”"), ("另一张桌子", 1, None), ("“桌子”", 0.8, None)],
)
def test_name_retry_only_restores_confident_quotes(
    monkeypatch, solver, candidate, score, expected
):
    furniture.crop_relative(solver.recog.img, ((0.36, 0.265), (0.59, 0.31)))[
        10:20, 10:40
    ] = 255
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "桌子")], 0),
                ([[candidate, score]], 0),
                ([["2/1", 1]], 0),
            ]
        ),
    )
    if expected is None:
        with pytest.raises(ValueError):
            REAL_FURNITURE_DETAILS(solver.recog.img, 2)
    else:
        assert REAL_FURNITURE_DETAILS(solver.recog.img, 2) == (expected, 2)


@pytest.mark.parametrize(
    "result",
    [
        None,
        [title(0, 0, "桌子"), title(50, 0, "另一名称")],
        [[[[0, 0]] * 4, "桌子", 0.8]],
    ],
)
def test_uncertain_name_detection_never_uses_partial_text(monkeypatch, solver, result):
    engine = MagicMock(return_value=(result, 0))
    monkeypatch.setattr(furniture.rapidocr, "engine", engine)
    with pytest.raises(ValueError, match="家具名称无法可靠确认"):
        REAL_FURNITURE_DETAILS(solver.recog.img, 2)
    assert engine.call_count == (2 if result else 1)


def test_multi_digit_stock_is_used_in_both_detail_checks(monkeypatch, solver):
    details = MagicMock(return_value=("测试家具", 12))
    monkeypatch.setattr(furniture, "furniture_details", details)
    monkeypatch.setattr(furniture, "furniture_batch", lambda img: 11)
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.side_effect = [
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_PRODUCT_COLLECT,
    ]
    assert furniture.FurnitureDismantler(solver).process((0.37, 0.21), 12)
    assert [c.args[1:] for c in details.call_args_list] == [(12,), (12, 11)]


def test_trademark_ocr_name_reaches_safe_batch_processing(monkeypatch, solver):
    import json
    from pathlib import Path

    from arknights_mower.utils.furniture_data import (
        FURNITURE_DATA_PATH,
        furniture_keep_counts,
    )

    data = json.loads(
        (Path(__file__).resolve().parents[2] / FURNITURE_DATA_PATH).read_text(
            encoding="utf-8"
        )
    )
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = furniture_keep_counts(data)
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda img, expected_count=1, expected_batch=None: ("便携TM计算器", 2),
    )
    monkeypatch.setattr(furniture, "furniture_batch", lambda img: 1)
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.side_effect = [
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_DASHBOARD,
        Scene.FACTORY_PRODUCT_COLLECT,
    ]
    assert runner.process((0.37, 0.21), 2)
    assert solver.tap.call_args_list[-1] == call((0.88 * 1920, 0.9 * 1080), interval=2)


@pytest.mark.parametrize("stock,batch", [(3, 2), (4, 3), (12, 11), (100, 99)])
def test_detail_consumption_tracks_selected_batch(monkeypatch, solver, stock, batch):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "桌子")], 0),
                ([["桌子", 1]], 0),
                ([[f"{stock}/{batch}", 1]], 0),
            ]
        ),
    )
    assert REAL_FURNITURE_DETAILS(solver.recog.img, stock, batch) == ("桌子", stock)


def test_recipe_can_open_with_a_remembered_batch(monkeypatch, solver):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "桌子")], 0),
                ([["桌子", 1]], 0),
                ([["3/2", 1]], 0),
            ]
        ),
    )
    assert REAL_FURNITURE_DETAILS(solver.recog.img, 3) == ("桌子", 3)


@pytest.mark.parametrize("consumed", [0, 1, 3])
def test_detail_rejects_consumption_different_from_target(
    monkeypatch, solver, consumed
):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "桌子")], 0),
                ([["桌子", 1]], 0),
                ([[f"3/{consumed}", 1]], 0),
            ]
        ),
    )
    with pytest.raises(ValueError, match="消耗数量与加工份数不一致"):
        REAL_FURNITURE_DETAILS(solver.recog.img, 3, 2)


@pytest.mark.parametrize(
    "owned,read_stock,keep,cap,expected",
    [
        (6, 8, 5, 99, 1),
        (4, 8, 5, 99, None),
        (6, 6, 5, 99, 1),
        (150, 150, 5, 99, 95),
        (150, 150, 100, 99, None),
    ],
)
def test_real_batch_model_preserves_set_despite_high_stock_or_cap(
    monkeypatch, solver, owned, read_stock, keep, cap, expected
):
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": keep}
    monkeypatch.setattr(
        furniture, "furniture_details", lambda *a: ("测试家具", read_stock)
    )
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    actual = [min(owned - 1, cap)]
    submitted = []

    def render():
        region = furniture.crop_relative(solver.recog.img, furniture.BATCH_SCOPE)
        region[:] = 0
        furniture.cv2.putText(
            region,
            str(actual[0]),
            (30, 75),
            furniture.cv2.FONT_HERSHEY_SIMPLEX,
            2,
            (255, 220, 0),
            3,
        )

    render()

    def tap(point, **kwargs):
        if point == (0.84 * 1920, 0.68 * 1080):
            actual[0] = max(1, actual[0] - 1)
            render()
        if point == (0.88 * 1920, 0.9 * 1080):
            submitted.append(actual[0])
            assert owned - actual[0] >= keep

    solver.tap.side_effect = tap
    monkeypatch.setattr(furniture, "furniture_batch", lambda img: actual[0])
    solver.factory_scene.side_effect = [Scene.FACTORY_DASHBOARD] * 2 + [
        Scene.FACTORY_PRODUCT_COLLECT
    ]
    assert runner.process((0.37, 0.21), read_stock) is (expected is not None)
    assert submitted == ([] if expected is None else [expected])


def test_conflicting_keep_switch_states_never_count_as_enabled(monkeypatch, solver):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        lambda *a, **k: (
            [title(20, 20, "至少保留1件"), title(200, 20, "ON"), title(300, 20, "OFF")],
            0,
        ),
    )
    with pytest.raises(ValueError, match="开关状态"):
        furniture.keep_one_enabled(solver.recog.img)


@pytest.mark.parametrize("retry_text,score", [("2/1", 1), ("2/1", 0.8), ("2/2", 1)])
def test_quantity_retry_uses_visible_glyphs_and_rejects_uncertainty(
    monkeypatch, solver, retry_text, score
):
    solver.recog.img[335:350, 665:715] = 255
    engine = MagicMock(
        side_effect=[
            ([title(260, 42)], 0),
            ([["時2/1", 1]], 0),
            ([[retry_text, score]], 0),
        ]
    )
    monkeypatch.setattr(furniture.rapidocr, "engine", engine)
    if retry_text == "2/1" and score >= 0.9:
        assert furniture.furniture_cards(solver.recog.img)[0][1] == 2
    else:
        with pytest.raises(ValueError):
            furniture.furniture_cards(solver.recog.img)
    assert engine.call_count == 3
    assert np.any(engine.call_args.args[0])


def test_low_confidence_keep_switch_never_enables_processing(monkeypatch, solver):
    state = title(200, 20, "ON")
    state[2] = 0.4
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        lambda *a, **k: ([title(20, 20, "至少保留1件"), state], 0),
    )
    with pytest.raises(ValueError, match="保留开关识别置信度不足"):
        furniture.keep_one_enabled(solver.recog.img)


def test_clipped_name_cannot_match_a_shorter_known_name(monkeypatch, solver):
    region = furniture.crop_relative(solver.recog.img, furniture.NAME_SCOPE)
    region[:, -2:] = 255
    engine = MagicMock(return_value=([title(10, 10, "复古吊扇")], 0))
    monkeypatch.setattr(furniture.rapidocr, "engine", engine)
    with pytest.raises(ValueError, match="无法可靠确认"):
        furniture.furniture_name(solver.recog.img)
    engine.assert_called_once()


def test_two_valid_resource_names_disagree_so_neither_is_accepted(monkeypatch, solver):
    monkeypatch.setattr(
        furniture.rapidocr,
        "engine",
        MagicMock(
            side_effect=[
                ([title(10, 10, "复古吊扇")], 0),
                ([["复古吊灯", 1]], 0),
            ]
        ),
    )
    with pytest.raises(ValueError, match="两次识别冲突"):
        furniture.furniture_name(solver.recog.img)


def test_ocr_countdown_cannot_mask_an_ineffective_minus(monkeypatch, solver):
    region = furniture.crop_relative(solver.recog.img, furniture.BATCH_SCOPE)
    furniture.cv2.putText(
        region, "2", (30, 75), furniture.cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 220, 0), 3
    )
    runner = furniture.FurnitureDismantler(solver)
    runner.keep_counts = {"测试家具": 2}
    reader = MagicMock(side_effect=[2, 1, 1])
    monkeypatch.setattr(furniture, "furniture_batch", reader)
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(furniture.FurnitureSafetyError, match="减号未产生"):
        runner.process((0.37, 0.21), 3)
    # The misleading second OCR result is never used after unchanged glyphs.
    reader.assert_called_once()
    assert call((0.88 * 1920, 0.9 * 1080), interval=2) not in solver.tap.call_args_list


@pytest.mark.parametrize("change", ["none", "noise", "shift", "decrement"])
def test_batch_glyph_comparison_rejects_noise_and_translation(solver, change):
    before = solver.recog.img.copy()
    region = furniture.crop_relative(before, furniture.BATCH_SCOPE)
    furniture.cv2.putText(
        region, "2", (30, 75), furniture.cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 220, 0), 3
    )
    after = before.copy()
    target = furniture.crop_relative(after, furniture.BATCH_SCOPE)
    if change == "noise":
        target[5, 5] = (255, 220, 0)
    elif change == "shift":
        target[:] = np.roll(target, 1, axis=1)
    elif change == "decrement":
        target[:] = 0
        furniture.cv2.putText(
            target,
            "1",
            (30, 75),
            furniture.cv2.FONT_HERSHEY_SIMPLEX,
            2,
            (255, 220, 0),
            3,
        )
    assert furniture.batch_image_changed(before, after) is (change == "decrement")


def test_final_verification_reads_a_fresh_frame(monkeypatch, solver):
    changed = False

    def sleep(interval=1):
        nonlocal changed
        if interval == 0.3:
            changed = True

    solver.sleep.side_effect = sleep
    monkeypatch.setattr(
        furniture,
        "furniture_details",
        lambda *args: ("另一家具" if changed else "测试家具", 3),
    )
    monkeypatch.setattr(furniture, "keep_one_enabled", lambda img: True)
    solver.factory_scene.return_value = Scene.FACTORY_DASHBOARD
    with pytest.raises(furniture.FurnitureSafetyError, match="无法确认保留"):
        furniture.FurnitureDismantler(solver).process((0.37, 0.21), 3)
    assert changed
    assert call((0.88 * 1920, 0.9 * 1080), interval=2) not in solver.tap.call_args_list


@pytest.mark.parametrize("score", [0.8, float("nan"), float("inf")])
def test_low_or_invalid_quantity_confidence_requires_glyph_retry(monkeypatch, score):
    img = np.zeros((35, 100, 3), dtype=np.uint8)
    img[10:25, 20:65] = 255
    engine = MagicMock(side_effect=[([["99/1", score]], 0), ([["2/1", 1]], 0)])
    monkeypatch.setattr(furniture.rapidocr, "engine", engine)
    assert furniture.card_quantity(img) == 2
    assert engine.call_count == 2


@pytest.mark.parametrize("score", [0.8, float("nan"), float("inf")])
def test_uncertain_recipe_title_cannot_authorize_a_click(monkeypatch, solver, score):
    row = title(260, 42)
    row[2] = score
    monkeypatch.setattr(furniture.rapidocr, "engine", lambda *a, **k: ([row], 0))
    with pytest.raises(ValueError, match="位置识别置信度不足"):
        furniture.furniture_cards(solver.recog.img)
