"""订单收取记录真实动作，未收取与中断不能宣告成功。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.business_log_groups_tests import live
from arknights_mower.tests.raw_schedule_log_tests import base, capture
from arknights_mower.utils.scheduler_task import TaskTypes
from arknights_mower.utils.trading_order import TradingOrder


@pytest.fixture
def collector():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.task = SimpleNamespace(type=TaskTypes.RUN_ORDER, meta_data="room_1_1")
    solver.op_data = SimpleNamespace(
        facility_states={"room_1_1": {"facility": "trade"}}
    )
    solver._cache_facility_state_from_current_page = MagicMock()
    solver.recog = SimpleNamespace(
        w=1920, h=1080, img=object(), update=MagicMock(), save_screencap=MagicMock()
    )
    solver.sleep = MagicMock()
    solver.device = object()
    solver.tap = MagicMock()
    solver.order_reader = MagicMock()
    solver.order_reader.has_distinct_buff.return_value = True
    return solver


def messages(caplog):
    return [
        record.getMessage() for record in caplog.records if record.levelname == "INFO"
    ]


def test_live_order_save_keeps_its_observations_in_the_collection_group(
    collector, caplog, monkeypatch, income_db
):
    capture(caplog, monkeypatch)
    order = TradingOrder()
    order.get_buff_scores = MagicMock(return_value={"佩佩": 85.0})
    collector.order_reader = order
    collector.find = MagicMock(side_effect=[True, True, None])

    collector.accept_order()

    entries = [live(record) for record in caplog.records if record.levelname == "INFO"]
    assert entries[0]["msg"] == "当前为 佩佩 订单, 订单价值为: 1000"
    assert entries[1]["msg"].startswith("储存订单信息至数据库 ")
    assert [entry["msg"] for entry in entries[2:]] == [
        "贸易站 B101：正在收取订单",
        "贸易站 B101：已收取订单",
    ]
    assert [entry.get("group") for entry in entries] == ["base-scheduler"] * 4

    caplog.clear()
    order.save(collector.recog.img, datetime(2026, 1, 1))
    historical = [
        live(record) for record in caplog.records if record.levelname == "INFO"
    ]
    assert [entry.get("group") for entry in historical] == [None, None]


@pytest.mark.parametrize("collect_only", [False, True])
def test_collection_announces_real_taps_once_and_confirms_only_after_marker_disappears(
    collector, caplog, monkeypatch, collect_only
):
    capture(caplog, monkeypatch)
    collector.task.run_order_collect_only = collect_only
    collector.find = MagicMock(side_effect=[True, True, True, None])
    collector.accept_order()
    assert messages(caplog) == ["贸易站 B101：正在收取订单", "贸易站 B101：已收取订单"]
    assert collector.tap.call_count == 2
    if collect_only:
        collector.order_reader.save.assert_not_called()
    else:
        collector.order_reader.save.assert_called_once_with(
            collector.recog.img,
            room="B101",
            screenshot_source=collector.device,
            log_group="base-scheduler",
        )


@pytest.mark.parametrize("collect_only", [False, True])
def test_no_deliverable_order_never_claims_collection(
    collector, caplog, monkeypatch, collect_only
):
    capture(caplog, monkeypatch)
    collector.task.run_order_collect_only = collect_only
    collector.find = MagicMock(return_value=None)
    collector.accept_order()
    assert messages(caplog) == ["贸易站 B101：未识别到可收取订单"]
    collector.tap.assert_not_called()
    collector.order_reader.save.assert_not_called()
    assert collector.sleep.call_count == 7


def test_collection_label_uses_the_newly_observed_facility_type(
    collector, caplog, monkeypatch
):
    capture(caplog, monkeypatch)
    collector.op_data.facility_states["room_1_1"]["facility"] = "manufacture"
    collector._cache_facility_state_from_current_page.side_effect = lambda *_: (
        collector.op_data.facility_states["room_1_1"].update(facility="trade")
    )
    collector.find = MagicMock(side_effect=[True, True, None])
    collector.accept_order()
    assert messages(caplog) == ["贸易站 B101：正在收取订单", "贸易站 B101：已收取订单"]


def test_interrupted_collection_never_claims_success(collector, caplog, monkeypatch):
    capture(caplog, monkeypatch)
    collector.find = MagicMock(return_value=True)
    collector.tap.side_effect = base.MowerExit
    with pytest.raises(base.MowerExit):
        collector.accept_order()
    assert messages(caplog) == ["贸易站 B101：正在收取订单"]
