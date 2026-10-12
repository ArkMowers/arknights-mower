"""Local operation scheduling consumes confirmed inventory without cloud refresh."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import maa_stage_inventory  # noqa: E402


@pytest.fixture
def scheduler(monkeypatch):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.device = MagicMock()
    solver.recog = MagicMock()
    solver.tasks = [
        SimpleNamespace(time=datetime.now() + timedelta(hours=2), meta_data="")
    ]
    solver.local_operation_followup_time = None
    solver.last_execution = {"maa": None}
    solver.back_to_index = MagicMock()
    solver.maybe_switch_expired_activity_plan = MagicMock()
    solver.check_current_focus = MagicMock()
    monkeypatch.setattr(base_schedule, "get_server_weekday", lambda: 0)
    monkeypatch.setattr(base_schedule, "scheduling", MagicMock())
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    return solver


@pytest.mark.parametrize(
    ("stop_reason", "should_break"),
    [("stopped_by_inventory", False), ("inventory_unconfirmed", True)],
)
def test_inventory_result_never_renavigates_same_stage(
    scheduler, monkeypatch, stop_reason, should_break
):
    navigation = MagicMock()
    operation = MagicMock()
    operation.return_value.run.return_value = {
        "simulated_current_ap": 96,
        "executed_runs": 4,
        "remaining_runs": 6,
        "sanity_drain": False,
        "stopped_by_deadline": False,
        stop_reason: True,
    }
    monkeypatch.setattr(base_schedule, "NavigationSolver", navigation)
    monkeypatch.setattr(base_schedule, "OperationSolver", operation)

    result = scheduler.run_local_operation_stage(
        "1-7", datetime.now() + timedelta(hours=1), 120, 6, 10, "threshold", 100
    )

    assert result["simulated_current_ap"] == 96
    assert result["executed_any"] is True
    assert result["should_break"] is should_break
    assert result.get("inventory_unconfirmed", False) is should_break
    navigation.return_value.run.assert_called_once_with("1-7")
    operation.return_value.run.assert_called_once()


@pytest.mark.parametrize(
    ("fallback", "fallback_cost", "unconfirmed"),
    [(False, 6, False), (True, 6, False), (True, None, False), (True, 6, True)],
)
def test_local_plan_reselects_after_drops_and_continues_daily_tasks(
    scheduler, monkeypatch, fallback, fallback_cost, unconfirmed
):
    inventory = {"30012": 9}
    # Both stages drop the same item: completing one also caps the other.
    planned = ["1-7", "S2-1"] + (["CE-6"] if fallback else [])
    conf = SimpleNamespace(
        maa_gap=4,
        maa_stage_inventory_enable=True,
        maa_stage_limit_rules=[
            {"stage": stage, "items": [{"item_id": "30012", "limit": 10}]}
            for stage in ("1-7", "S2-1")
        ],
        maa_stage_ratio_rules=[],
        maa_weekly_plan=[SimpleNamespace(stage=planned, sanity_threshold=100)],
    )
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(
        maa_stage_inventory, "load_inventory_snapshot", lambda: (inventory, None)
    )
    player = MagicMock()
    player.return_value.get_first_available_snapshot.return_value = SimpleNamespace(
        current_ap=120
    )
    monkeypatch.setattr(base_schedule, "PlayerInfoClient", player)
    refresh = MagicMock()
    monkeypatch.setattr(base_schedule, "cultivateDepotSolver", refresh)
    mission = MagicMock()
    monkeypatch.setattr(base_schedule, "MissionSolver", mission)
    scheduler.mower_stage_ap_cost = MagicMock(
        side_effect=lambda stage: fallback_cost if stage == "CE-6" else 6
    )
    scheduler.upsert_local_operation_followup = MagicMock()
    scheduler.clear_local_operation_followups = MagicMock()

    def run_stage(**kwargs):
        inventory["30012"] = 10
        return {
            "simulated_current_ap": kwargs["simulated_current_ap"]
            - (kwargs["ap_cost"] or 0),
            "executed_any": not unconfirmed,
            "should_break": unconfirmed or kwargs["stage"] == "CE-6",
            "inventory_unconfirmed": unconfirmed,
        }

    scheduler.run_local_operation_stage = MagicMock(side_effect=run_stage)
    scheduler.mower_plan_solver()

    assert [
        call.kwargs["stage"]
        for call in scheduler.run_local_operation_stage.call_args_list
    ] == (["1-7", "CE-6"] if fallback and not unconfirmed else ["1-7"])
    mission.return_value.run.assert_called_once()
    player.return_value.get_first_available_snapshot.assert_called_once()
    refresh.assert_not_called()
    scheduler.device.exit.assert_not_called()
    assert scheduler.last_execution["maa"] is not None
    if not fallback or fallback_cost is None or unconfirmed:
        scheduler.upsert_local_operation_followup.assert_not_called()
        scheduler.clear_local_operation_followups.assert_called_once()
    if fallback_cost is None:
        fallback_call = scheduler.run_local_operation_stage.call_args.kwargs
        assert fallback_call["mode"] == "fallback"
        assert fallback_call["threshold"] is None
        assert fallback_call["target_total_runs"] is None


def test_local_reselection_excludes_attempted_stage_before_ratio_choice(
    scheduler, monkeypatch
):
    conf = SimpleNamespace(
        maa_stage_inventory_enable=True,
        maa_stage_limit_rules=[],
        maa_stage_ratio_rules=[
            {
                "members": [
                    {"stage": "1-7", "item_id": "30012", "ratio": 1},
                    {"stage": "CE-6", "item_id": "4001", "ratio": 1},
                ]
            }
        ],
        maa_weekly_plan=[SimpleNamespace(stage=["1-7", "CE-6"])],
    )
    monkeypatch.setattr(base_schedule.config, "conf", conf)
    monkeypatch.setattr(
        maa_stage_inventory,
        "load_inventory_snapshot",
        lambda: ({"30012": 0, "4001": 5}, None),
    )
    assert scheduler.mower_stage_plan() == ["1-7"]
    assert scheduler.mower_stage_plan(excluded_stages={"1-7"}) == ["CE-6"]


def test_initially_full_plan_clears_old_followup_and_continues_daily_tasks(
    scheduler, monkeypatch
):
    followup = SimpleNamespace(
        time=datetime.now() + timedelta(minutes=1),
        meta_data=base_schedule.FOLLOWUP_TASK_META,
    )
    scheduler.tasks.append(followup)
    scheduler.local_operation_followup_time = followup.time
    scheduler.mower_stage_plan = MagicMock(return_value=[])
    monkeypatch.setattr(base_schedule.config, "conf", SimpleNamespace(maa_gap=4))
    player = MagicMock()
    monkeypatch.setattr(base_schedule, "PlayerInfoClient", player)
    mission = MagicMock()
    monkeypatch.setattr(base_schedule, "MissionSolver", mission)

    scheduler.mower_plan_solver()

    assert followup not in scheduler.tasks
    assert scheduler.local_operation_followup_time is None
    player.assert_not_called()
    mission.return_value.run.assert_called_once()
    scheduler.device.exit.assert_not_called()
