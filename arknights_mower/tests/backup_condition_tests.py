import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.utils.operators import Operators  # noqa: E402
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


def test_started_major_maintenance_has_zero_remaining_hours(monkeypatch):
    op_data = operators()
    monkeypatch.setattr(
        "arknights_mower.utils.operators.NewsChecker.get_maintenance",
        lambda: maintenance(hours=-1),
    )

    assert op_data.major_maintenance_remaining_hours() == 0


def test_group_mood_supports_min_max_and_excludes_zero_mood_workers():
    op_data = operators()
    op_data.groups = {"鸿雪组": ["鸿雪", "图耶", "爱丽丝", "焰影苇草"]}
    op_data.operators = {
        "鸿雪": SimpleNamespace(current_mood=lambda: 0, workaholic=True),
        "图耶": SimpleNamespace(current_mood=lambda: 24, workaholic=True),
        "爱丽丝": SimpleNamespace(current_mood=lambda: 7.25, workaholic=False),
        "焰影苇草": SimpleNamespace(current_mood=lambda: 18.5, workaholic=False),
    }

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
    op_data.operators = {
        "鸿雪": SimpleNamespace(current_mood=lambda: 24, workaholic=True)
    }

    with pytest.raises(ValueError, match="没有可统计心情"):
        op_data.group_max_mood("零心情组")
