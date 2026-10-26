import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.news_checker import (  # noqa: E402
    MaintenanceInfo,
    NewsChecker,
)
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig  # noqa: E402


def operators():
    return Operators(
        {
            "default_plan": Plan({}, PlanConfig("", "", "")),
            "backup_plans": [],
        }
    )


def maintenance(*, hours=6, update_type="major", title="停机维护"):
    return SimpleNamespace(
        start=datetime.now() + timedelta(hours=hours),
        update_type=update_type,
        is_flash_update="闪断更新" in title,
        manual=False,
    )


def test_major_maintenance_remaining_hours_and_expression(monkeypatch):
    op_data = operators()
    monkeypatch.setattr(
        "arknights_mower.utils.operators.NewsChecker.get_maintenance",
        lambda: maintenance(hours=6),
    )

    assert op_data.major_maintenance_remaining_hours() == pytest.approx(6, abs=0.01)
    assert op_data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours() <= 12"
    )


@pytest.mark.parametrize(
    "info",
    [
        None,
        maintenance(update_type="hot"),
        maintenance(title="闪断更新"),
    ],
)
def test_non_major_or_flash_maintenance_does_not_trigger(monkeypatch, info):
    op_data = operators()
    monkeypatch.setattr(
        "arknights_mower.utils.operators.NewsChecker.get_maintenance", lambda: info
    )

    assert op_data.major_maintenance_remaining_hours() == float("inf")
    assert not op_data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours() <= 12"
    )


@pytest.mark.parametrize("hours", [0, -1])
def test_started_major_maintenance_does_not_trigger(monkeypatch, hours):
    op_data = operators()
    monkeypatch.setattr(
        "arknights_mower.utils.operators.NewsChecker.get_maintenance",
        lambda: maintenance(hours=hours),
    )

    assert op_data.major_maintenance_remaining_hours() == float("inf")
    assert not op_data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours() <= 0.5"
    )


@pytest.mark.parametrize(
    "comparison,expected",
    [
        ("<", False),
        ("<=", True),
        ("==", True),
        ("!=", False),
        (">=", True),
        (">", False),
    ],
)
@pytest.mark.parametrize("manual", [False, True])
def test_duration_comparisons_use_total_window_at_exact_boundary(
    monkeypatch, comparison, expected, manual
):
    now = datetime(2026, 10, 26, 10)
    info = MaintenanceInfo(
        now + timedelta(minutes=15),
        now + timedelta(hours=6, minutes=15),
        "major",
        "计划停止" if manual else "停机维护",
        "",
        "duration-window",
        manual=manual,
    )
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: info)
    data = operators()
    data._projection_now = now
    expression = f"op_data.major_maintenance_remaining_hours('{comparison}', 6) <= 0.5"
    assert data.evaluate_expression(expression) is expected
    data._projection_now += timedelta(minutes=14)
    assert data.evaluate_expression(expression) is expected


@pytest.mark.parametrize("comparison", ["<", "<=", "==", "!=", ">=", ">"])
@pytest.mark.parametrize("hours", [0, 6])
def test_zero_duration_matches_only_unrestricted_conditions(
    monkeypatch, comparison, hours
):
    now = datetime.now()
    info = MaintenanceInfo(
        now + timedelta(minutes=15),
        now + timedelta(minutes=15),
        "major",
        "计划停止",
        "",
        "no-restart",
        manual=True,
        restart_after_update=False,
    )
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: info)
    data = operators()
    assert data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours() <= 0.5"
    )
    assert not data.evaluate_expression(
        f"op_data.major_maintenance_remaining_hours('{comparison}', {hours}) <= 0.5"
    )


def test_duration_filter_stays_active_until_manual_preparation_finishes(monkeypatch):
    now = datetime.now()
    info = MaintenanceInfo(
        now - timedelta(hours=7),
        now - timedelta(hours=1),
        "major",
        "计划停止",
        "",
        "preparation-pending",
        manual=True,
        preparation_pending=True,
    )
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: info)
    data = operators()
    assert data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours('>=', 6) <= 0.5"
    )
    assert not data.evaluate_expression(
        "op_data.major_maintenance_remaining_hours('<', 6) <= 0.5"
    )


@pytest.mark.parametrize("info_kind", ["missing", "hot", "started"])
def test_duration_filter_never_activates_missing_flash_or_started_announcement(
    monkeypatch, info_kind
):
    now = datetime.now()
    start = (
        now - timedelta(minutes=1)
        if info_kind == "started"
        else now + timedelta(minutes=15)
    )
    info = MaintenanceInfo(
        start,
        start + timedelta(hours=7),
        "hot" if info_kind == "hot" else "major",
        "停机维护",
        "",
        "unavailable-window",
    )
    monkeypatch.setattr(
        NewsChecker,
        "get_major_maintenance",
        lambda *_: None if info_kind == "missing" else info,
    )
    assert not operators().evaluate_expression(
        "op_data.major_maintenance_remaining_hours('>=', 6) <= 0.5"
    )


def test_duration_conditions_select_distinct_backups_and_keep_threshold_wakeup(
    monkeypatch,
):
    now = datetime(2026, 10, 26, 10)
    info = MaintenanceInfo(
        now + timedelta(hours=1),
        now + timedelta(hours=7),
        "major",
        "停机维护",
        "",
        "six-hours",
    )
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: info)
    plans = [
        Plan(
            {},
            PlanConfig("", "", ""),
            LogicExpression(
                f"op_data.major_maintenance_remaining_hours('{comparison}', 6)",
                "<=",
                "0.5",
            ),
        )
        for comparison in (">=", "<")
    ]
    data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": plans}
    )
    data._projection_now = now
    assert data.evaluate_backup_selection().conditions == [False, False]
    assert data.next_major_maintenance_check(now) == now + timedelta(minutes=30)
    assert all(plan.uses_major_maintenance_condition for plan in plans)
    data._projection_now += timedelta(minutes=30)
    assert data.evaluate_backup_selection().conditions == [True, False]
    info = MaintenanceInfo(
        info.start,
        info.start + timedelta(hours=5),
        "major",
        "停机维护",
        "",
        "five-hours",
    )
    assert data.evaluate_backup_selection().conditions == [False, True]


def test_nested_duration_condition_selects_group_at_its_advance_threshold(monkeypatch):
    now = datetime.now()
    info = MaintenanceInfo(
        now + timedelta(hours=1),
        now + timedelta(hours=7),
        "major",
        "停机维护",
        "",
        "group-window",
    )
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: info)
    data = operators()
    data.backup_groups = [
        {
            "id": "long-stop",
            "trigger": {
                "function": "all",
                "args": [
                    "True",
                    {
                        "left": "op_data.major_maintenance_remaining_hours('>=', 6)",
                        "operator": "<=",
                        "right": "0.5",
                    },
                ],
            },
        }
    ]
    data.backup_plans = [
        Plan({}, PlanConfig("", "", ""), "True", group_ids=["long-stop"])
    ]
    data._projection_now = now
    assert data.evaluate_backup_selection().conditions == [False]
    assert data.next_major_maintenance_check(now) == now + timedelta(minutes=30)
    data._projection_now += timedelta(minutes=30)
    selected = data.evaluate_backup_selection()
    assert selected.group_id == "long-stop"
    assert selected.conditions == [True]


@pytest.mark.parametrize(
    "comparison,hours",
    [
        ("unknown", 6),
        (">=", -1),
        (">=", float("inf")),
        (">=", True),
        (None, 6),
        (">=", None),
    ],
)
def test_invalid_duration_conditions_are_rejected_without_a_maintenance(
    monkeypatch, comparison, hours
):
    monkeypatch.setattr(NewsChecker, "get_major_maintenance", lambda *_: None)
    with pytest.raises(ValueError, match="停止时长条件"):
        operators().major_maintenance_remaining_hours(comparison, hours)


def test_group_mood_supports_min_max_and_excludes_zero_mood_workers():
    op_data = operators()
    op_data.groups = {"鸿雪组": ["鸿雪", "图耶", "爱丽丝", "焰影苇草"]}
    op_data.config.workaholic = ["鸿雪", "图耶"]
    for name, mood in [("鸿雪", 0), ("图耶", 24), ("爱丽丝", 7.25), ("焰影苇草", 18.5)]:
        op_data.add(Operator(name, "room_1_1", mood=mood, operator_type="high"))

    assert op_data.group_min_mood("鸿雪组") == 7.25
    assert op_data.group_max_mood("鸿雪组") == 18.5
    assert op_data.evaluate_expression("op_data.group_min_mood('鸿雪组') < 8")
    assert op_data.evaluate_expression("op_data.group_max_mood('鸿雪组') < 19")


def test_group_min_mood_rejects_unknown_group():
    with pytest.raises(ValueError, match="不存在的绑组"):
        operators().group_min_mood("不存在")


def test_group_mood_rejects_group_with_only_zero_mood_workers():
    op_data = operators()
    op_data.groups = {"零心情组": ["鸿雪"]}
    op_data.config.workaholic = ["鸿雪"]
    op_data.add(Operator("鸿雪", "room_1_1", mood=24, operator_type="high"))

    with pytest.raises(ValueError, match="没有可统计心情"):
        op_data.group_max_mood("零心情组")
