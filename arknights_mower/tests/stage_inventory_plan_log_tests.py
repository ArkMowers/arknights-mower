"""最终刷取顺序只转换显示名称；关卡 ID、重复项和选择结果保持原样。"""

import json
from copy import deepcopy
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.log_display_payload_tests import record_with
from arknights_mower.tests.raw_schedule_log_tests import base, capture
from arknights_mower.utils import config, log, maa_stage_inventory
from arknights_mower.utils.log_stream import LogStream


@pytest.fixture
def planning(monkeypatch, caplog):
    capture(caplog, monkeypatch)
    monkeypatch.setattr(
        config,
        "conf",
        SimpleNamespace(
            maa_stage_inventory_enable=True,
            maa_stage_limit_rules=[
                {"stage": "OTHER", "items": [{"item_id": "30012", "limit": 5}]}
            ],
            maa_stage_ratio_rules=[],
        ),
    )
    stock = {"30012": 2}
    load = MagicMock(return_value=(stock, None))
    monkeypatch.setattr(maa_stage_inventory, "load_inventory_snapshot", load)
    return object.__new__(base.BaseSchedulerSolver), stock, load


def plan_record(caplog):
    records = [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "stage-inventory-plan"
    ]
    assert len(records) == 1
    return records[0]


@pytest.mark.parametrize(
    "original,selected,message",
    [
        (
            ["Annihilation", "PR-B-1"],
            ["Annihilation", "PR-B-1"],
            "接下来计划依次刷取当期剿灭 → PR-B-1",
        ),
        ([], [], "当前没有待刷关卡"),
        ([""], [""], "接下来计划依次刷取上次作战"),
        (["", "PR-B-1"], ["", "PR-B-1"], "接下来计划依次刷取上次作战 → PR-B-1"),
        (
            ["1-7", "1-7-HARD", "1-7"],
            ["1-7", "1-7-HARD", "1-7"],
            "接下来计划依次刷取1-7 → 1-7-HARD → 1-7",
        ),
        (
            ["PR-B-1", "Annihilation", "PR-A-1"],
            ["Annihilation", "PR-B-1", "PR-A-1"],
            "接下来计划依次刷取当期剿灭 → PR-B-1 → PR-A-1",
        ),
    ],
)
def test_footer_preserves_selected_ids_and_handles_empty_and_special_stages(
    planning, caplog, original, selected, message
):
    solver, stock, load = planning
    before = deepcopy((original, stock))

    result = solver.apply_maa_stage_inventory_rules(original)

    assert result == selected and (original, stock) == before
    load.assert_called_once_with()
    record = plan_record(caplog)
    assert record.getMessage() == message
    assert [item["code"] for item in record.log_event["stages"]] == result
    assert record.log_group == "weekly-plan-editor"
    assert not hasattr(record, "log_inventory")
    assert set(record.log_event) == {"type", "stages"}
    if result:
        suffix = " → ".join(item["label"] for item in record.log_event["stages"])
        assert message == "接下来计划依次刷取" + suffix
    for item in record.log_event["stages"]:
        if item["code"] in ("", "Annihilation"):
            assert item["drops"] == []
        elif item["code"] == "PR-B-1":
            assert item["drops"] == ["狙击芯片", "术师芯片"]
        elif item["code"] == "1-7":
            assert item["drops"] == ["固源岩"]


@pytest.mark.parametrize("disabled", [False, True])
def test_original_early_returns_do_not_add_reads_or_logs(planning, caplog, disabled):
    solver, _, load = planning
    config.conf.maa_stage_inventory_enable = not disabled
    config.conf.maa_stage_limit_rules = []
    original = ["", "PR-B-1", "Annihilation"]

    result = solver.apply_maa_stage_inventory_rules(original)

    assert result == (original if disabled else ["Annihilation", "", "PR-B-1"])
    assert original == ["", "PR-B-1", "Annihilation"]
    load.assert_not_called()
    assert not caplog.records


def test_ratio_footer_uses_the_actual_selected_sequence_and_main_activity_drops(
    planning, caplog, monkeypatch
):
    solver, stock, _ = planning
    config.conf.maa_stage_ratio_rules = [
        {
            "name": "材料",
            "members": [
                {"stage": "PR-A-1", "item_id": "a", "ratio": 1},
                {"stage": "TEST-ACT", "item_id": "30012", "ratio": 1},
            ],
        }
    ]
    stock["a"] = 10
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
            },
            {
                "id": "Annihilation",
                "drop": [{"id": "30012", "type": "MATERIAL", "dropType": "NORMAL"}],
            },
        ],
    )

    assert solver.apply_maa_stage_inventory_rules(
        ["PR-A-1", "Annihilation", "TEST-ACT"]
    ) == ["Annihilation", "TEST-ACT"]

    record = plan_record(caplog)
    assert record.getMessage() == "接下来计划依次刷取当期剿灭 → TEST-ACT"
    assert record.log_event["stages"] == [
        {"code": "Annihilation", "label": "当期剿灭", "drops": []},
        {"code": "TEST-ACT", "label": "TEST-ACT", "drops": ["糖"]},
    ]


def plan_event():
    return {
        "type": "stage-inventory-plan",
        "stages": [
            {"code": "Annihilation", "label": "当期剿灭", "drops": []},
            {"code": "", "label": "上次作战", "drops": []},
            {"code": "1-7", "label": "1-7", "drops": ["固源岩"]},
            {"code": "1-7-HARD", "label": "1-7-HARD", "drops": []},
            {"code": "1-7", "label": "1-7", "drops": ["固源岩"]},
        ],
    }


def test_ordered_stage_metadata_survives_queue_and_stream_as_a_deep_snapshot():
    event = plan_event()
    expected = deepcopy(event)
    message = "接下来计划依次刷取当期剿灭 → 上次作战 → 1-7 → 1-7-HARD → 1-7"
    record = record_with(message, log_event=event)
    prepared = log.LiveQueueHandler(Queue()).prepare(record)
    event["stages"][2]["drops"].clear()
    event["stages"].reverse()
    prepared.asctime = record.asctime
    delivered = log._build_log_record(prepared, prepared.getMessage())
    assert delivered["event"] == expected and delivered["msg"] == message
    stream = LogStream()
    stream.publish(delivered)
    delivered["event"]["stages"].clear()
    assert (
        json.loads(stream.subscribe().messages.get_nowait())["records"][0]["event"]
        == expected
    )


@pytest.mark.parametrize(
    "stages",
    [
        None,
        {},
        [None],
        [{"code": [], "label": "错误", "drops": []}],
        [{"code": "s" * 65, "label": "s" * 65, "drops": []}],
        [{"code": "1-7", "label": "", "drops": []}],
        [{"code": "1-7", "label": "1-7-HARD", "drops": []}],
        [{"code": "", "label": "上次作战", "drops": ["固源岩"]}],
        [{"code": "Annihilation", "label": "剿灭", "drops": []}],
        [{"code": "Annihilation", "label": "当期剿灭", "drops": ["固源岩"]}],
        [{"code": "1-7", "label": "1-7", "drops": None}],
        [{"code": "1-7", "label": "1-7", "drops": [""]}],
        [{"code": "1-7", "label": "1-7", "drops": [None]}],
        [{"code": "1-7", "label": "1-7", "drops": ["x" * 257]}],
        [{"code": "1-7", "label": "1-7", "drops": ["x"] * 65}],
        [{"code": "1-7", "label": "1-7", "drops": []}] * 129,
    ],
)
def test_invalid_stage_plan_falls_back_to_the_original_text(stages):
    event = {"type": "stage-inventory-plan", "stages": stages}
    assert "event" not in log._display_snapshots(record_with(log_event=event), "原文")


def test_empty_plan_repeated_stages_and_existing_shared_budget():
    for stages in ([], [{"code": "1-7", "label": "1-7", "drops": []}] * 128):
        event = {"type": "stage-inventory-plan", "stages": stages}
        assert (
            log._display_snapshots(record_with(log_event=event), "原文")["event"]
            == event
        )
    event = plan_event()
    assert "event" not in log._display_snapshots(
        record_with(log_event=event), "文" * (log.LIVE_LOG_MESSAGE_LIMIT - 1)
    )
    assert "event" not in log._display_snapshots(
        record_with(log_event=event),
        "原文",
        {"task": "文" * log.LIVE_LOG_MESSAGE_LIMIT},
    )
