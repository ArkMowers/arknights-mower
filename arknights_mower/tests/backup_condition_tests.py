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
