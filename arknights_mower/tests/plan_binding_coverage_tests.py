"""Every schedule-wide operator query includes additional binding replacements."""

# ruff: noqa: E402

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule, mastery, record
from arknights_mower.tests import multi_group_shift_tests
from arknights_mower.tests.mastery_support_fixtures import game as game
from arknights_mower.tests.mastery_support_fixtures import owned
from arknights_mower.tests.schedule_roster_tests import (
    make_plan,
    write_roster,
)
from arknights_mower.tests.schedule_roster_tests import (
    roster_path as roster_path,
)
from arknights_mower.utils import (
    config,
    mastery_db,
    mastery_support_data,
    schedule_roster,
)
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.mastery_support_types import TrainingInputs
from arknights_mower.utils.plan import Plan, PlanConfig, Room, all_replacements
from arknights_mower.utils.resting_priority import RestingTier, resting_tier
from arknights_mower.utils.scheduler_task import TaskTypes
from arknights_mower.utils.workshop_data import scheduled_operators

solver = multi_group_shift_tests.solver


def schedule(room, name, backup):
    table = {
        room: {
            "plans": [
                {
                    "agent": "芬",
                    "group": "甲",
                    "replacement": ["红"],
                    "group_bindings": [
                        {"group": "乙", "replacement": [name, "Free", "Current", ""]},
                        {"group": "丙", "replacement": [name]},
                    ],
                }
            ]
        }
    }
    return {
        "plan1": {} if backup else table,
        "backup_plans": [{"plan": table, "conf": {}, "task": {}, "trigger": {}}]
        if backup
        else [],
    }


def test_all_replacements_deduplicates_without_merging_binding_identity():
    slot = Room(
        "讯使",
        "甲",
        ["红", "黑角"],
        group_bindings=[
            {"group": "乙", "replacement": ["黑角", "砾"]},
            {"group": "丙", "replacement": ["砾", "Free"]},
        ],
    )
    before = deepcopy(vars(slot))
    assert slot.all_replacements == ["红", "黑角", "砾", "Free"]
    collected = all_replacements(slot.replacement, slot.group_bindings)
    collected.clear()
    assert vars(slot) == before
    assert [b["replacement"] for b in slot.bindings] == [
        ["红", "黑角"],
        ["黑角", "砾"],
        ["砾", "Free"],
    ]


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("model", [False, True])
@pytest.mark.parametrize(
    "room", ["central", "meeting", "dormitory_1", "factory", "train"]
)
def test_mastery_and_workshop_collect_additional_replacements(backup, model, room):
    raw = schedule(room, "阿斯卡纶", backup)
    plan = PlanModel(**raw) if model else raw
    before = deepcopy(plan)
    blocked, central = mastery_support_data.schedule_context(plan)
    expected = {} if room == "train" else {n: {room} for n in ("芬", "红", "阿斯卡纶")}
    assert blocked == expected
    assert central == (5 if room == "central" else 0)
    assert bool(mastery_support_data.trainee_schedule_conflict("阿斯卡纶", plan)) is (
        room != "train"
    )
    workshop = scheduled_operators(plan)
    assert workshop == (
        {}
        if room in ("dormitory_1", "factory")
        else {n: [room] for n in ("芬", "红", "阿斯卡纶")}
    )
    assert plan == before


@pytest.mark.parametrize("backup", [False, True])
def test_additional_replacement_is_excluded_from_training_assistants(game, backup):
    metadata, ids = game
    inputs = TrainingInputs(
        roster=[owned(ids[name]) for name in ("能天使", "艾丽妮", "逻各斯")],
        metadata=metadata,
        schedule=mastery_support_data.schedule_context(
            schedule("meeting", "艾丽妮", backup)
        ),
    )
    candidates, _ = mastery_support_data.candidates(ids["能天使"], inputs=inputs)
    assert "艾丽妮" not in candidates
    assert "逻各斯" in candidates


@pytest.mark.parametrize("backup", [False, True])
def test_additional_replacement_cannot_start_training(monkeypatch, backup):
    monkeypatch.setattr(
        config, "plan", PlanModel(**schedule("meeting", "异客", backup))
    )
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(mastery_db, "should_notify", lambda *args: False)
    update = MagicMock()
    monkeypatch.setattr(mastery_db, "update_plan_status", update)
    solver = MagicMock()
    mastery._start_new_training(
        solver,
        {
            "id": 1,
            "char_id": "test",
            "char_name": "异客",
            "skill_index": 1,
            "skill_name": "聚焦指令",
            "target_level": 3,
        },
    )
    update.assert_not_called()
    assert solver.mock_calls == []


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("active", [False, True])
def test_manual_training_stop_uses_additional_replacements(monkeypatch, backup, active):
    monkeypatch.setattr(
        config, "plan", PlanModel(**schedule("meeting", "异客", backup))
    )
    stop = Event()
    monkeypatch.setattr(config, "stop_mower", stop)
    monkeypatch.setattr(base_schedule, "send_message", MagicMock())
    save = MagicMock()
    monkeypatch.setattr(record, "save_current_state", save)
    room = SimpleNamespace(
        state="training",
        read_failed=False,
        panel=SimpleNamespace(countdown_state="active" if active else "unknown"),
    )
    solver = MagicMock()
    if active:
        with pytest.raises(base_schedule.MowerExit):
            base_schedule._stop_if_scheduled_trainee(solver, "异客", room)
        save.assert_called_once()
    else:
        base_schedule._stop_if_scheduled_trainee(solver, "异客", room)
        save.assert_not_called()
    assert stop.is_set() is active


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("owned_extra", [False, True])
def test_ownership_validation_includes_additional_bindings(
    roster_path, monkeypatch, backup, owned_extra
):
    plan = make_plan()
    table = plan["backup_plans"][0] if backup else plan["default_plan"]
    slot = next(iter(table.plan.values()))[0]
    slot.group_bindings = [{"group": "附加", "replacement": ["黑角", "黑角"]}]
    ids = [
        "char_103_angel",
        "char_123_fang",
        "char_2014_nian",
        "char_240_wyvern",
        "char_285_medic2",
    ]
    if owned_extra:
        ids.append("char_500_noirc")
    write_roster(roster_path, *ids)
    refresh = MagicMock(return_value=True)
    monkeypatch.setattr(schedule_roster, "_refresh_roster", refresh)
    result = schedule_roster.validate_owned_operators(plan)
    assert result == (None if owned_extra else "森空岛中未持有以下排班干员：黑角")
    assert refresh.call_count == (0 if owned_extra else 1)


@pytest.mark.parametrize("priority", [False, True])
def test_additional_replacement_gets_replacement_rest_priority(solver, priority):
    if priority:
        solver.op_data.config.resting_priority_replacement = ["黑角"]
    assert resting_tier(solver.op_data, "黑角") == (
        RestingTier.PRIORITY_REPLACEMENT if priority else RestingTier.REPLACEMENT
    )
    assert resting_tier(solver.op_data, "夜刀") == RestingTier.IDLE


@pytest.mark.parametrize("reserved", [False, True])
def test_rescue_standby_retains_normal_additional_replacement_identity(
    solver, reserved
):
    solver.emergency_state = {
        "phase": "recovering",
        "standby_workers": ["黑角", "夜刀"],
        "ready_members": ["黑角"] if reserved else [],
    }
    solver._emergency_sync_reservations()
    assert solver.op_data.emergency_reserved_agents == (
        {"黑角", "夜刀"} if reserved else {"夜刀"}
    )


@pytest.mark.parametrize("backup", [False, True])
def test_run_order_detection_and_task_use_additional_trade_replacement(solver, backup):
    main = solver.global_plan["default_plan"]
    slots = main.plan.pop("contact")
    slots[0].facility, slots[0].product = "贸易站", "lmd"
    main.plan["room_1_1"] = slots
    main.products = {"room_1_1": "lmd"}
    if backup:
        slots = deepcopy(slots)
        solver.global_plan["backup_plans"] = [
            Plan(
                {"room_1_1": slots},
                PlanConfig("", "", ""),
                trigger=LogicExpression("True", "==", "True"),
            )
        ]
    slots[0].group_bindings[0]["replacement"].append("但书")
    assert solver.initialize_operators() is None
    if backup:
        assert solver.op_data.swap_plan([True], refresh=True) is None
    solver.get_run_order_time = MagicMock(
        return_value=datetime.now() + timedelta(minutes=10)
    )
    solver.queue_product_switches = MagicMock()
    assert solver.op_data.is_run_order_room("room_1_1")
    solver.plan_run_order("room_1_1")
    task = next(t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER)
    assert task.plan == {"room_1_1": ["但书"]}
    assert solver.op_data.plan["room_1_1"][0].replacement == ["红"]
