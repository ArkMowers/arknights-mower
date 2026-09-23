"""Skland ownership checks shared by manual and startup schedule validation."""

import json

import pytest

from arknights_mower.utils import schedule_roster
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room


def make_plan():
    config = PlanConfig("", "", "")
    return {
        "default_plan": Plan({"central": [Room("能天使", "", ["芬"])]}, config),
        "backup_plans": [
            Plan(
                {"room_1_1": [Room("年", "", ["香草"])]},
                config,
                task={"dormitory_1": ["Current", "Free", "Lancet-2", "年"]},
            )
        ],
    }


def write_roster(path, *ids):
    path.write_text(
        json.dumps({"data": {"characters": [{"id": cid} for cid in ids]}}),
        encoding="utf-8",
    )


@pytest.fixture
def roster_path(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    return path


def test_missing_cache_skips_ownership_check(roster_path):
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_reports_main_backup_replacements_and_backup_tasks(roster_path, monkeypatch):
    write_roster(roster_path, "char_103_angel")
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: True)

    message = schedule_roster.validate_owned_operators(make_plan())
    assert message == "森空岛中未持有以下排班干员：Lancet-2、年、芬、香草"
    assert "Current" not in message
    assert "Free" not in message


def test_owned_operators_pass_including_low_rarity_names(roster_path):
    write_roster(
        roster_path,
        "char_103_angel",
        "char_123_fang",
        "char_2014_nian",
        "char_240_wyvern",
        "char_285_medic2",
    )
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_present_but_invalid_cache_blocks_validation(roster_path):
    roster_path.write_text('{"data": {"characters": []}}', encoding="utf-8")
    assert "缓存无效" in schedule_roster.validate_owned_operators(make_plan())


def test_inventory_placeholder_skips_ownership_check(roster_path):
    roster_path.write_text(
        json.dumps({"code": 0, "data": {"items": [{"id": "31063", "count": "0"}]}}),
        encoding="utf-8",
    )
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_failed_inventory_response_does_not_skip_validation(roster_path):
    roster_path.write_text(
        json.dumps({"code": 10001, "data": {"items": []}}), encoding="utf-8"
    )
    assert "缓存无效" in schedule_roster.validate_owned_operators(make_plan())


def test_stale_cache_is_refreshed_before_rejecting(roster_path, monkeypatch):
    write_roster(roster_path, "char_103_angel")

    def refresh():
        write_roster(
            roster_path,
            "char_103_angel",
            "char_123_fang",
            "char_2014_nian",
            "char_240_wyvern",
            "char_285_medic2",
        )
        return True

    monkeypatch.setattr(schedule_roster, "_refresh_roster", refresh)
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_unconfirmed_cache_miss_does_not_block(roster_path, monkeypatch):
    write_roster(roster_path, "char_103_angel")
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: False)
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_unknown_operator_name_reports_resource_mismatch(roster_path):
    write_roster(roster_path, "char_103_angel")
    plan = make_plan()
    plan["backup_plans"][0].task["dormitory_1"].append("资源缺失干员")
    message = schedule_roster.validate_owned_operators(plan)
    assert "更新资源包" in message
    assert "资源缺失干员" in message


def test_malformed_resource_reports_error(roster_path, monkeypatch):
    from arknights_mower.utils import mastery_recommendation

    write_roster(roster_path, "char_103_angel")
    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        lambda: {"characters": {"char_103_angel": None}},
    )
    assert "更新资源包" in schedule_roster.validate_owned_operators(make_plan())


def test_outdated_training_resource_reports_error(roster_path, monkeypatch):
    from arknights_mower.utils import mastery_recommendation

    write_roster(roster_path, "char_103_angel")
    monkeypatch.setattr(
        mastery_recommendation,
        "get_skill_data",
        lambda: {"training": {"version": 2, "operators": {}}},
    )
    assert "更新资源包" in schedule_roster.validate_owned_operators(make_plan())


def test_precheck_runs_even_without_backup_plans(roster_path, monkeypatch):
    write_roster(roster_path, "char_2014_nian")
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: True)
    plan = make_plan()
    plan["backup_plans"] = []

    result = Operators(plan).validate_backup_plans()
    assert not result["success"]
    assert "能天使" in result["message"]
    assert "芬" in result["message"]
