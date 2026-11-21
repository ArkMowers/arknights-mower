"""Zero-mood work configuration controls replacement exemptions per binding."""

# ruff: noqa: E402

import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils import config
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())


def roster(slots, workaholics):
    return Operators(
        {
            "default_plan": Plan(
                {"central": slots},
                PlanConfig("", "", "", workaholic=",".join(workaholics)),
            ),
            "backup_plans": [],
        }
    )


@pytest.mark.parametrize("group", ["", "常驻"])
def test_zero_mood_workers_need_no_replacements_or_beds(group, monkeypatch):
    from arknights_mower.utils import exhaust_replacement

    matching = MagicMock(side_effect=AssertionError("permanent staff never rotate"))
    monkeypatch.setattr(exhaust_replacement, "match_replacements", matching)
    data = roster(
        [Room("能天使", group, []), Room("银灰", group, [])], ["能天使", "银灰"]
    )
    assert data.init_and_validate() is None
    assert all(op.workaholic for op in data.operators.values())
    assert not data.dorm
    matching.assert_not_called()


def test_observed_zero_mood_does_not_exempt_ordinary_workers():
    data = roster([Room("能天使", "", ["红"])], [])
    assert data.init_and_validate() is None
    data.operators["能天使"].mood = 0
    data.plan["central"][0].replacement = []
    assert "能天使" in data.init_and_validate()


@pytest.mark.parametrize("missing", ["能天使", "银灰"])
def test_mixed_group_requires_every_members_replacements(missing):
    data = roster(
        [
            Room("能天使", "混合", [] if missing == "能天使" else ["红"]),
            Room("银灰", "混合", [] if missing == "银灰" else ["初雪"]),
        ],
        ["能天使"],
    )
    assert missing in data.init_and_validate()


def test_multi_group_exemption_is_checked_per_binding():
    shared = Room(
        "讯使",
        "常驻",
        [],
        group_bindings=[{"group": "轮休", "replacement": ["红"]}],
    )
    data = roster(
        [shared, Room("能天使", "常驻", []), Room("银灰", "轮休", [])],
        ["讯使", "能天使"],
    )
    assert data.init_and_validate() == "以下干员替换组缺失：银灰"
    shared.group_bindings[0]["replacement"] = []
    data = roster([shared, Room("银灰", "轮休", ["初雪"])], ["讯使"])
    assert data.init_and_validate() == "讯使的每个绑组都需要替班"


def test_all_zero_mood_multi_groups_validate_without_mood_driver():
    data = roster(
        [Room("讯使", "甲", [], group_bindings=[{"group": "乙", "replacement": []}])],
        ["讯使"],
    )
    assert data.init_and_validate() is None


def test_zero_mood_group_checks_only_supplied_replacement_candidates():
    data = roster(
        [Room("能天使", "常驻", []), Room("银灰", "常驻", ["红"])],
        ["能天使", "银灰"],
    )
    assert data.init_and_validate() is None
    data.plan["central"][0].replacement = ["红"]
    assert data.init_and_validate() == "常驻 分组无法排班,替换组数量不够"


@pytest.mark.parametrize("replacement", [["无效干员"], ["菲亚梅塔"], ["Free"]])
def test_optional_replacements_still_validate_supplied_names(replacement):
    data = roster([Room("能天使", "常驻", replacement)], ["能天使"])
    assert data.init_and_validate() is not None


def test_fiammetta_charging_targets_remain_required():
    data = roster([Room("能天使", "", [])], ["能天使", "菲亚梅塔"])
    data.plan["dormitory_1"] = [
        Room("菲亚梅塔", "", []),
        Room("杜林", "", []),
        *[Room("Free", "", []) for _ in range(3)],
    ]
    assert data.init_and_validate() == "菲亚梅塔替换缺失"
