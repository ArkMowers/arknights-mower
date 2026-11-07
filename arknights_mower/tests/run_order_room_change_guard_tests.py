import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


def test_drained_operator_does_not_touch_trading_tasks(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)

    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = MagicMock()
    solver.op_data.first_init = False
    solver.op_data.run_order_rooms = {"room_2_1": MagicMock()}
    solver.op_data.operators = {}

    task_time = datetime.now() + timedelta(minutes=60)
    order_task = SchedulerTask(
        time=task_time,
        task_type=TaskTypes.RUN_ORDER,
        meta_data="room_2_1",
    )
    solver.tasks = [order_task]

    refresh_trading_mock = MagicMock()
    solver.refresh_run_order_time = refresh_trading_mock
    refresh_drained_mock = MagicMock()
    solver.refresh_drained_time = refresh_drained_mock

    # 槐琥: refresh_drained = True, refresh_order_room = [False, []]
    op_huaihu = Operator(
        name="槐琥",
        room="room_1_2",
        refresh_drained=True,
        refresh_order_room=[False, []],
    )
    solver.op_data.operators["槐琥"] = op_huaihu

    solver.current_room_changed(op_huaihu)

    # 验证: 不应该刷新任何贸易站任务
    refresh_trading_mock.assert_not_called()
    assert order_task in solver.tasks
    # 应该正常调用 refresh_drained_time
    refresh_drained_mock.assert_called_once()


def test_trading_refresh_operator_refreshes_designated_room(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)

    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = MagicMock()
    solver.op_data.first_init = False
    solver.op_data.run_order_rooms = {"room_1_1": MagicMock(), "room_2_1": MagicMock()}
    solver.op_data.operators = {}

    refresh_trading_mock = MagicMock()
    solver.refresh_run_order_time = refresh_trading_mock
    refresh_drained_mock = MagicMock()
    solver.refresh_drained_time = refresh_drained_mock

    # 佩佩: 刷新指定贸易站 room_1_1
    op_pepe = Operator(
        name="佩佩",
        room="room_1_1",
        refresh_drained=False,
        refresh_order_room=[True, ["room_1_1"]],
    )
    solver.op_data.operators["佩佩"] = op_pepe

    solver.current_room_changed(op_pepe)

    refresh_trading_mock.assert_called_once_with("room_1_1")
    refresh_drained_mock.assert_not_called()


def test_global_trading_refresh_operator_refreshes_all_trading_rooms(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)

    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = MagicMock()
    solver.op_data.first_init = False
    solver.op_data.run_order_rooms = {"room_1_1": MagicMock(), "room_2_1": MagicMock()}
    solver.op_data.operators = {}

    refresh_trading_mock = MagicMock()
    solver.refresh_run_order_time = refresh_trading_mock

    # 全局跑单刷新干员
    op_global = Operator(
        name="迷迭香",
        room="room_1_1",
        refresh_drained=False,
        refresh_order_room=[True, []],
    )
    solver.op_data.operators["迷迭香"] = op_global

    solver.current_room_changed(op_global)

    assert refresh_trading_mock.call_count == 2
    refresh_trading_mock.assert_any_call("room_1_1")
    refresh_trading_mock.assert_any_call("room_2_1")
