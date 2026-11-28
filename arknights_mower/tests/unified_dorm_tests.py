"""Retired settings cannot select another policy or survive config round trips."""

import copy
import json

import pytest

from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan import PlanModel, migrate_legacy_dorm_order
from arknights_mower.utils.config.plan_advanced import (
    apply_advanced_settings,
    export_advanced_settings,
)

RETIRED = (
    "experimental_dorm_logic",
    "refresh_backup_plan_after_mood",
    "workshop_low_priority_rest",
)


@pytest.mark.parametrize("enabled", [None, False, True])
def test_retired_modes_are_ignored_and_not_serialized(enabled):
    old = {key: enabled for key in RETIRED} if enabled is not None else {}
    conf = Conf(**old)
    assert conf.model_dump() == Conf().model_dump()
    assert not set(RETIRED) & export_advanced_settings(conf).keys()
    assert apply_advanced_settings(conf, {**old, "free_room": True}).free_room
    plan = PlanModel(
        plan1={},
        conf={"mood_limits": {"lower": 0, "upper": 20}, "rest_in_full": "阿罗玛"},
        advanced_settings={**old, "free_room": True},
        backup_plans=[
            {
                "conf": {},
                "plan": {},
                "task": {},
                "trigger": {},
                "trigger_timing": "BEFORE_DORM",
                "exit_trigger_timing": "BEFORE_WORK",
            }
        ],
    )
    saved = plan.model_dump()
    assert saved["advanced_settings"] == {"free_room": True}
    assert saved["conf"]["mood_limits"]["upper"] == 20
    assert saved["conf"]["rest_in_full"] == "阿罗玛"
    assert "trigger_timing" not in saved["backup_plans"][0]
    assert "exit_trigger_timing" not in saved["backup_plans"][0]
    assert PlanModel.model_validate_json(plan.model_dump_json()).model_dump() == saved


@pytest.mark.parametrize("source", ["global", "advanced", "plan"])
def test_old_order_migrates_with_plan_then_import_then_local_precedence(source):
    raw = {"plan1": {}}
    if source in ("advanced", "plan"):
        raw["advanced_settings"] = {
            "dorm_order": "dormitory_3_2,dormitory_3_3,dormitory_2_2"
        }
    if source == "plan":
        raw["conf"] = {"dorm_order": "dormitory_4,dormitory_1,dormitory_2,dormitory_3"}
    original = copy.deepcopy(raw)
    plan = PlanModel(**raw)
    migrate_legacy_dorm_order(plan, raw, "dormitory_2_2,dormitory_1_2")
    assert raw == original
    assert (
        plan.conf.dorm_order.split(",")[0]
        == {"global": "dormitory_2", "advanced": "dormitory_3", "plan": "dormitory_4"}[
            source
        ]
    )
    assert len(set(plan.conf.dorm_order.split(","))) == 4
    assert "dorm_order" not in (plan.advanced_settings or {})
    assert not migrate_legacy_dorm_order(plan, json.loads(plan.model_dump_json()), "")


@pytest.mark.parametrize("advanced", [False, True])
def test_empty_per_plan_default_does_not_hide_old_global_order(advanced):
    raw = {"plan1": {}, "conf": {"dorm_order": ""}}
    if advanced:
        raw["advanced_settings"] = {"dorm_order": "dormitory_3_2"}
    plan = PlanModel(**raw)
    assert migrate_legacy_dorm_order(plan, raw, "dormitory_2_2")
    assert plan.conf.dorm_order.startswith("dormitory_3" if advanced else "dormitory_2")
