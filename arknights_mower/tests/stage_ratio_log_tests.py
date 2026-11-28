"""比例选关单行说明沿用真实候选比例，悬浮掉落来自关卡表。"""

import json
import logging
from copy import deepcopy
from queue import Queue
from types import SimpleNamespace

import pytest

from arknights_mower.tests.log_display_payload_tests import record_with
from arknights_mower.tests.raw_schedule_log_tests import base, capture
from arknights_mower.utils import config, log, maa_stage_inventory
from arknights_mower.utils.log_stream import LogStream


@pytest.fixture
def choosing(monkeypatch, caplog):
    capture(caplog, monkeypatch)
    stock = {"30022": 10, "30012": 2}
    rule = {
        "name": "芯片储备",
        "members": [
            {"stage": "PR-A-1", "item_id": "30022", "ratio": 1.0},
            {"stage": "PR-B-1", "item_id": "30012", "ratio": 1.0},
        ],
    }
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[],
            maa_stage_ratio_rules=[rule],
        ),
    )
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: (stock, None)
    )
    return object.__new__(base.BaseSchedulerSolver), rule, stock


def ratio_record(caplog):
    values = [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "stage-inventory-ratio"
    ]
    assert len(values) == 1
    return values[0]


def test_ratio_info_is_one_line_and_keeps_complete_candidate_counts_at_debug(
    choosing, caplog
):
    solver, rule, stock = choosing
    original = ["PR-A-1", "PR-B-1", "Annihilation"]
    before = deepcopy((original, rule, stock))

    assert solver.apply_maa_stage_inventory_rules(original) == [
        "Annihilation",
        "PR-B-1",
    ]

    record = ratio_record(caplog)
    assert (
        record.getMessage()
        == "比例规则「芯片储备」的刷取比例相同（1:1），优先刷取库存相对不足的材料，本轮选择 PR-B-1"
    )
    assert record.log_event == {
        "type": "stage-inventory-ratio",
        "stage": {"code": "PR-B-1", "drops": ["狙击芯片", "术师芯片"]},
    }
    assert not hasattr(record, "log_inventory")
    assert "\n" not in record.getMessage()
    debug = next(
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG and "库存比例选关" in record.getMessage()
    )
    assert debug.args[2] == [
        {"stage": "PR-A-1", "count": 10, "ratio": 1.0, "score": 10.0},
        {"stage": "PR-B-1", "count": 2, "ratio": 1.0, "score": 2.0},
    ]
    assert (original, rule, stock) == before


@pytest.mark.parametrize("name", ["", "   "])
def test_unnamed_ratio_does_not_show_empty_quotes(choosing, caplog, name):
    solver, rule, _ = choosing
    rule["name"] = name
    solver.apply_maa_stage_inventory_rules(["PR-A-1", "PR-B-1"])
    assert ratio_record(caplog).getMessage().startswith("比例规则的刷取比例相同（1:1）")


def test_unequal_ratios_keep_candidate_order_and_decimal_precision(choosing, caplog):
    solver, rule, stock = choosing
    rule["name"] = "PR-B-1 芯片储备"
    rule["members"][0]["ratio"] = 1.23456789012345
    rule["members"][1]["ratio"] = 0.5
    before = deepcopy((rule, stock))
    original = ["PR-B-1", "Annihilation", "PR-A-1"]

    assert solver.apply_maa_stage_inventory_rules(original) == [
        "Annihilation",
        "PR-B-1",
    ]

    message = ratio_record(caplog).getMessage()
    assert "的刷取比例为 1.23456789012345:0.5，" in message
    assert "相同" not in message
    assert message.count("PR-B-1") == 2 and message.endswith("PR-B-1")
    assert (rule, stock) == before
    assert original == ["PR-B-1", "Annihilation", "PR-A-1"]


def test_equal_non_unit_ratios_are_not_normalized_to_one(choosing, caplog):
    solver, rule, _ = choosing
    for member in rule["members"]:
        member["ratio"] = 2.0
    solver.apply_maa_stage_inventory_rules(["PR-A-1", "PR-B-1"])
    assert "相同（2:2）" in ratio_record(caplog).getMessage()


def test_activity_main_drop_is_not_inferred_from_the_ratio_binding(
    choosing, caplog, monkeypatch
):
    solver, rule, _ = choosing
    rule["members"][1]["stage"] = "TEST-ACT"
    monkeypatch.setattr(
        base,
        "stage_data_full",
        [
            {
                "id": "TEST-ACT",
                "drop": [
                    {"id": "30022", "type": "MATERIAL", "dropType": "NORMAL"},
                    {"id": "30012", "type": "MATERIAL", "dropType": "SPECIAL"},
                ],
            }
        ],
    )

    assert solver.apply_maa_stage_inventory_rules(["PR-A-1", "TEST-ACT"]) == [
        "TEST-ACT"
    ]

    assert ratio_record(caplog).log_event == {
        "type": "stage-inventory-ratio",
        "stage": {"code": "TEST-ACT", "drops": ["糖"]},
    }


def ratio_event():
    return {
        "type": "stage-inventory-ratio",
        "stage": {"code": "PR-B-1", "drops": ["狙击芯片", "术师芯片"]},
    }


def test_ratio_event_uses_queue_and_stream_snapshots_without_inventory_metadata():
    event = ratio_event()
    expected = deepcopy(event)
    record = record_with("比例规则本轮选择 PR-B-1", log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event["stage"]["drops"].clear()
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == expected
    assert delivered["msg"] == "比例规则本轮选择 PR-B-1"
    assert "inventory" not in delivered
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"]["stage"]["drops"].clear()
    assert (
        json.loads(stream.subscribe().messages.get_nowait())["records"][0]["event"]
        == expected
    )


@pytest.mark.parametrize(
    "stage",
    [
        None,
        [],
        {"code": "", "drops": []},
        {"code": "s" * 65, "drops": []},
        {"code": "PR-B-1", "drops": None},
        {"code": "PR-B-1", "drops": ["x"] * 65},
        {"code": "PR-B-1", "drops": [""]},
        {"code": "PR-B-1", "drops": ["x" * 257]},
        {"code": "PR-B-1", "drops": [None]},
    ],
)
def test_invalid_ratio_stage_payload_falls_back_to_original_text(stage):
    event = {"type": "stage-inventory-ratio", "stage": stage}
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


def test_unknown_drop_stays_empty_and_ratio_metadata_shares_the_message_budget():
    event = {"type": "stage-inventory-ratio", "stage": {"code": "UNKNOWN", "drops": []}}
    assert (
        log._display_snapshots(record_with(log_event=event), "原文")["event"] == event
    )
    assert "event" not in log._display_snapshots(
        record_with(log_event=event), "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 1)
    )
    event["type"] = "stage-inventory-other"
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")
