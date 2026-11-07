from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils.scheduler_task import TaskTypes
from arknights_mower.utils.trading_order import TradingOrder


def test_get_buff_scores_no_deliverable():
    order = TradingOrder()
    # 纯黑图像
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    scores = order.get_buff_scores(img)
    assert scores is None


def test_get_buff_scores_with_deliverable_and_pepe():
    order = TradingOrder()
    # 白色高亮像素 (255, 255, 255)
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # 可交付标记区域 [675:700, 550:580]
    img[675:700, 550:580] = (255, 255, 255)
    # 佩佩区域 [224:257, 610:640]
    img[224:257, 610:640] = (255, 255, 255)

    scores = order.get_buff_scores(img)
    assert scores is not None
    assert "佩佩" in scores
    assert scores["佩佩"] > 40
    assert scores["但书"] < 5
    assert order.has_distinct_buff(scores) is True


def test_trading_order_is_stable_helper():
    order = TradingOrder()
    scores1 = {"佩佩": 5.0, "但书": 2.0}
    scores2 = {"佩佩": 6.0, "但书": 2.5}
    scores3 = {"佩佩": 15.0, "但书": 2.0}

    assert order.is_stable(scores1, scores2) is True
    assert order.is_stable(scores1, scores3) is False
    assert order.is_stable(None, scores2) is False


def test_accept_order_debounce_when_initial_frame_has_buff():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.order_reader = TradingOrder()
    solver.recog = MagicMock()
    solver.recog.w = 1920
    solver.recog.h = 1080
    solver.sleep = MagicMock()
    solver.tap = MagicMock()

    find_mock = MagicMock(side_effect=[(500, 700), (500, 700), None])
    solver.find = find_mock

    # 首帧即有明确 buff，无需额外 sleep 缓冲
    solver.order_reader.get_buff_scores = MagicMock(
        return_value={"佩佩": 85.0, "但书": 0.0}
    )
    solver.order_reader.save = MagicMock()

    solver.accept_order()

    solver.sleep.assert_not_called()
    solver.recog.save_screencap.assert_called_once_with("run_order")
    solver.order_reader.save.assert_called_once_with(solver.recog.img)
    solver.tap.assert_called_once()


@pytest.mark.parametrize(
    ("room", "label"), [("room_1_1", "B101"), ("room_bad", "room_bad")]
)
def test_accept_order_passes_known_room_and_device_to_order_recognition(room, label):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = SimpleNamespace(type=TaskTypes.RUN_ORDER, meta_data=room)
    solver.device = object()
    solver._cache_facility_state_from_current_page = MagicMock()
    solver.order_reader = TradingOrder()
    solver.order_reader.get_buff_scores = MagicMock(return_value={"佩佩": 85.0})
    solver.order_reader.save = MagicMock()
    solver.recog = MagicMock(w=1920, h=1080)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.find = MagicMock(side_effect=[(500, 700), (500, 700), None])

    solver.accept_order()

    solver.order_reader.save.assert_called_once_with(
        solver.recog.img, room=label, screenshot_source=solver.device
    )


def test_accept_order_accepts_drone_room_without_run_order_task():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = None
    solver.device = object()
    solver.order_reader = TradingOrder()
    solver.order_reader.get_buff_scores = MagicMock(return_value={"佩佩": 85.0})
    solver.order_reader.save = MagicMock()
    solver.recog = MagicMock(w=1920, h=1080)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.find = MagicMock(side_effect=[(500, 700), (500, 700), None])

    solver.accept_order(room="room_2_1")

    solver.order_reader.save.assert_called_once_with(
        solver.recog.img, room="B201", screenshot_source=solver.device
    )


def test_drone_passes_its_trade_room_to_order_collection():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = MagicMock()
    solver.op_data.is_orundum_trade_room.return_value = False
    solver.recog = MagicMock(w=1920, h=1080)
    solver.tap = MagicMock()
    solver._wait_drone_interface = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("lmd", True))
    solver.find = MagicMock(side_effect=[None, (500, 500)])
    solver._tap_drone_accelerate = MagicMock(return_value=(500, 500))
    solver.scene = MagicMock(return_value=None)
    solver.waiting_scene = []
    solver.accept_order = MagicMock()
    solver.drone_room = "room_1_1"

    solver.drone("room_2_1", not_return=True, skip_enter=True)

    solver.accept_order.assert_called_once_with(room="room_2_1")


def test_accept_order_debounce_when_scores_stabilize():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.order_reader = TradingOrder()
    solver.recog = MagicMock()
    solver.recog.w = 1920
    solver.recog.h = 1080
    solver.sleep = MagicMock()
    solver.tap = MagicMock()

    find_mock = MagicMock(side_effect=[(500, 700), (500, 700), None])
    solver.find = find_mock

    # 模拟普通订单：两次采样均低于 40，但相邻两次差值极小（已稳定），1 次 sleep 后跳出
    scores_frame1 = {
        "佩佩": 5.0,
        "但书": 2.0,
        "可露希尔": 0.0,
        "龙舌兰": 0.0,
        "源石": 0.0,
    }
    scores_frame2 = {
        "佩佩": 5.2,
        "但书": 2.1,
        "可露希尔": 0.0,
        "龙舌兰": 0.0,
        "源石": 0.0,
    }
    solver.order_reader.get_buff_scores = MagicMock(
        side_effect=[scores_frame1, scores_frame2]
    )
    solver.order_reader.save = MagicMock()

    solver.accept_order()

    solver.sleep.assert_called_once_with(0.15)
    solver.recog.save_screencap.assert_called_once_with("run_order")
    solver.order_reader.save.assert_called_once_with(solver.recog.img)
    solver.tap.assert_called_once()


def test_accept_order_debounce_when_initially_none_then_buff_ready():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.order_reader = TradingOrder()
    solver.recog = MagicMock()
    solver.recog.w = 1920
    solver.recog.h = 1080
    solver.sleep = MagicMock()
    solver.tap = MagicMock()

    find_mock = MagicMock(side_effect=[(500, 700), (500, 700), None])
    solver.find = find_mock

    # 模拟第一帧交付按钮尚未亮起 (None)，第二帧佩佩高亮显形 (>40)
    scores_frame2 = {
        "佩佩": 90.0,
        "但书": 0.0,
        "可露希尔": 0.0,
        "龙舌兰": 0.0,
        "源石": 0.0,
    }
    solver.order_reader.get_buff_scores = MagicMock(side_effect=[None, scores_frame2])
    solver.order_reader.save = MagicMock()

    solver.accept_order()

    solver.sleep.assert_called_once_with(0.15)
    solver.recog.save_screencap.assert_called_once_with("run_order")
    solver.order_reader.save.assert_called_once_with(solver.recog.img)
    solver.tap.assert_called_once()


def test_trading_order_save_buff_and_price(monkeypatch):
    order = TradingOrder()
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    img[675:700, 550:580] = (255, 255, 255)
    img[224:257, 610:640] = (255, 255, 255)  # 佩佩

    # 屏蔽数据库写入与日志
    monkeypatch.setattr("arknights_mower.solvers.record._conn", MagicMock())

    order.save(img)
    assert order.buff == "佩佩"
    assert order.price == 1000


def test_previous_order_miss_keeps_db_record_and_warning_without_archive():
    order = TradingOrder()
    order.get_buff_scores = MagicMock(return_value={"佩佩": 1.0, "但书": 0.0})
    order.templates = {1000: np.zeros((5, 5), dtype=np.uint8)}
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)

    with (
        patch("arknights_mower.solvers.record._conn"),
        patch("arknights_mower.utils.trading_order.save_log") as save_log,
        patch("arknights_mower.utils.trading_order.send_message") as send_message,
        patch.object(base.logger, "error") as error,
    ):
        order.save(img)
        order.save(img, time=datetime.now())

    error.assert_not_called()
    save_log.assert_called_once_with("检测到上一个订单漏单！", level="ERROR")
    send_message.assert_called_once_with(
        "检测到上一个订单漏单！", subject="贸易站漏单提醒", level="WARNING"
    )


def test_previous_order_miss_includes_known_room_and_visual_source():
    order = TradingOrder()
    order.get_buff_scores = MagicMock(return_value={"佩佩": 1.0, "但书": 0.0})
    order.templates = {1000: np.zeros((5, 5), dtype=np.uint8)}
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    source = object()

    with (
        patch("arknights_mower.solvers.record._conn"),
        patch("arknights_mower.utils.trading_order.save_log"),
        patch("arknights_mower.utils.trading_order.send_message") as notify,
    ):
        order.save(image, room="B101", screenshot_source=source)

    notify.assert_called_once_with(
        "检测到上一个订单漏单：B101。",
        subject="贸易站漏单提醒",
        level="WARNING",
        archive_screenshots=True,
        screenshot_source=source,
    )
