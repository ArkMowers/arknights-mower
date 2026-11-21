from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from arknights_mower.tests.shift_off_mood_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.plan_advanced import (
    apply_advanced_settings,
    export_advanced_settings,
)
from arknights_mower.utils.operators import build_global_plan


@pytest.mark.parametrize("value", [0.35, 0.65, 1])
def test_configuration_round_trip_and_plan_settings(value):
    conf = Conf(resting_threshold=0.35, group_resting_thresholds={"感知": value})
    restored = Conf.model_validate_json(conf.model_dump_json())
    assert restored.group_resting_thresholds == {"感知": value}
    settings = export_advanced_settings(restored)
    imported = apply_advanced_settings(Conf(), settings)
    assert imported.group_resting_thresholds == {"感知": value}
    assert imported.resting_threshold == 0.35
    assert Conf().group_resting_thresholds == {}


@pytest.mark.parametrize("value", [0.34, -1, 1.01, float("inf"), float("nan")])
def test_invalid_group_and_global_threshold_rejected(value):
    with pytest.raises(ValidationError):
        Conf(group_resting_thresholds={"感知": value})
    with pytest.raises(ValidationError):
        Conf(resting_threshold=value)


@pytest.mark.parametrize("group", ["", "   "])
def test_empty_group_rejected(group):
    with pytest.raises(ValidationError):
        Conf(group_resting_thresholds={group: 0.5})


def test_runtime_build_retains_thresholds_for_main_and_backup():
    conf = Conf(group_resting_thresholds={"感知": 0.35})
    model = config.PlanModel(backup_plans=[{"name": "副表", "plan": {}}])
    result = build_global_plan(plan_model=model, conf_model=conf)
    for plan in [result["default_plan"], *result["backup_plans"]]:
        assert plan.config.group_resting_thresholds == {"感知": 0.35}
        plan.config.group_resting_thresholds["感知"] = 0.8
    assert conf.group_resting_thresholds == {"感知": 0.35}


@pytest.mark.parametrize(
    ("thresholds", "central", "working_room", "resting_names"),
    [
        (
            {"感知": 0.35, "深海": 0.65},
            ["Current", "夕"],
            "room_2_1",
            {"歌蕾蒂娅", "幽灵鲨"},
        ),
        (
            {"感知": 0.65, "深海": 0.35},
            ["Mon3tr", "Current"],
            "room_1_1",
            {"令", "黑键"},
        ),
    ],
)
def test_ordinary_shift_uses_each_group_threshold(
    solver, thresholds, central, working_room, resting_names
):
    data = solver.op_data
    data.config.group_resting_thresholds = thresholds
    for name in ("令", "歌蕾蒂娅"):
        data.operators[name].mood = 10
    plan = solver.resting()
    assert plan["central"] == central
    assert plan[working_room] == ["伺夜"]
    assert {bed.name for bed in data.dorm if bed.name} == resting_names


def test_threshold_fallback_mood_range_and_rescue_line(solver):
    data = solver.op_data
    data.config.group_resting_thresholds = {"感知": 0.35}
    config.conf.rescue_threshold = 0.5
    op = data.operators["令"]
    op.lower_limit, op.upper_limit = 8, 20
    data.config.operator_mood_limits = {op.name: {"lower": 8, "upper": 20}}
    assert data.resting_mood_threshold(op) == pytest.approx(12.2)
    assert data.rescue_mood_threshold(op) == pytest.approx(10.1)
    assert data.resting_mood_threshold(data.operators["歌蕾蒂娅"]) == 12
    assert (
        data.resting_threshold_for(SimpleNamespace(group="", multi_group=False)) == 0.5
    )
    assert (
        data.resting_threshold_for(SimpleNamespace(group="感知", multi_group=True))
        == 0.5
    )
    data.config.group_resting_thresholds = {}
    assert data.resting_mood_threshold(op) == 14


def test_maintenance_overrides_groups_and_restores_saved_settings(solver, monkeypatch):
    from datetime import datetime

    from arknights_mower.__main__ import _apply_version_update_resting_threshold
    from arknights_mower.utils.plan import Plan, PlanConfig

    monkeypatch.setattr(config.conf, "group_resting_thresholds", {"感知": 0.35})
    monkeypatch.setattr(config.conf, "resting_threshold", 0.65)
    info = SimpleNamespace(update_type="major", start=datetime(2026, 10, 28, 10))
    now = datetime(2026, 10, 28, 9)
    op = solver.op_data.operators["令"]
    solver.global_plan["backup_plans"].append(Plan({}, PlanConfig("", "", "")))
    assert _apply_version_update_resting_threshold(info, solver, now)
    assert solver.op_data.resting_threshold_for(op) == 0.8
    assert not _apply_version_update_resting_threshold(info, solver, now)
    assert solver.op_data.swap_plan([True]) is None
    assert solver.op_data.resting_threshold_for(op) == 0.8
    assert config.conf.group_resting_thresholds == {"感知": 0.35}
    assert _apply_version_update_resting_threshold(None, solver, now)
    assert solver.op_data.resting_threshold_for(op) == 0.35
    assert solver.op_data.swap_plan([False]) is None
    assert solver.op_data.resting_threshold_for(op) == 0.35
    assert solver.global_plan["default_plan"].config.group_resting_thresholds == {
        "感知": 0.35
    }
