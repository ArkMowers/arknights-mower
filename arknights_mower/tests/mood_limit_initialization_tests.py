from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room


@pytest.fixture
def data(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    return Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("令", "感知", ["红"])],
                    "meeting": [Room("银灰", "感知", ["夜刀"])],
                    "dormitory_1": [
                        Room(name, "", [])
                        for name in ("杜林", "闪灵", "Free", "Free", "Free")
                    ],
                },
                PlanConfig(
                    "",
                    "",
                    "",
                    ling_xi=1,
                    mood_limits={"lower": 3, "upper": 20},
                    operator_mood_limits={"银灰": {"lower": 5, "upper": 18}},
                ),
            ),
            "backup_plans": [],
        }
    )


def limits(data, name):
    op = data.operators[name]
    return op.lower_limit, op.upper_limit


def test_initialization_applies_priority_without_per_operator_plan_scans(
    data, monkeypatch
):
    scan = Mock(side_effect=AssertionError("unexpected full plan scan"))
    monkeypatch.setattr(data, "is_planned_operator", scan)

    assert data.init_and_validate() is None

    assert limits(data, "令") == (0, 12)
    assert limits(data, "银灰") == (5, 18)
    assert limits(data, "红") == (3, 20)
    scan.assert_not_called()


def test_initialization_failure_retains_incrementally_applied_limits(data):
    data.plan["meeting"].append(Room("令", "", []))

    assert data.init_and_validate() == (
        "高效组干员不可重复 房间->meeting,central, 干员->令"
    )

    assert limits(data, "令") == (0, 12)
    assert limits(data, "银灰") == (5, 18)


def test_reinitialization_uses_changed_replacements_and_emergency_roster(data):
    assert data.init_and_validate() is None
    data.add(Operator("空爆", ""))
    assert limits(data, "空爆") == (0, 24)
    data.plan["central"][0].replacement[:] = ["空爆"]
    data.emergency_dorm_agents.add("红")

    assert data.init_and_validate(update=True) is None

    assert limits(data, "空爆") == (3, 20)
    assert limits(data, "红") == (3, 20)
    data.emergency_dorm_agents.clear()
    data.init_mood_limit()
    assert limits(data, "红") == (0, 24)


def test_dynamic_add_checks_current_plan_including_additional_bindings(data):
    assert data.init_and_validate() is None
    data.plan["meeting"][0].group_bindings.append(
        {"group": "其他", "replacement": ["夕"]}
    )
    data.config.ling_xi = 2

    data.add(Operator("夕", ""))

    assert limits(data, "夕") == (0, 12)
    data.plan["meeting"][0].group_bindings.clear()
    data.init_mood_limit()
    assert limits(data, "夕") == (0, 24)


def test_limit_refresh_converts_existing_countdown_without_full_plan_scans(
    data, monkeypatch
):
    assert data.init_and_validate() is None
    observed = datetime(2026, 10, 27, 8)
    op = data.operators["银灰"]
    op.current_room, op.current_index = "dormitory_1", 2
    op.mood, op.time_stamp = 6, observed
    bed = data.dorm[0]
    bed.name, bed.time = op.name, observed + timedelta(hours=3)
    data.config.operator_mood_limits[op.name] = {"lower": 4, "upper": 14}
    monkeypatch.setattr(
        data,
        "is_planned_operator",
        Mock(side_effect=AssertionError("unexpected full plan scan")),
    )

    data.init_mood_limit()

    assert limits(data, op.name) == (4, 14)
    assert bed.time == observed + timedelta(hours=2)
    assert (op.mood, op.time_stamp) == (6, observed)
