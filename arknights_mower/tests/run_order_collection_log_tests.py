"""订单收取记录真实动作，未收取与中断不能宣告成功。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.raw_schedule_log_tests import base, capture
from arknights_mower.utils.scheduler_task import TaskTypes


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
            collector.recog.img, room="B101", screenshot_source=collector.device
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
