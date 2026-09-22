"""Skland ownership checks shared by manual and startup schedule validation."""

import json

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


def test_missing_cache_skips_ownership_check(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_roster, "get_path", lambda _: tmp_path / "missing.json"
    )
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_reports_main_backup_replacements_and_backup_tasks(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    write_roster(path, "char_103_angel")

    message = schedule_roster.validate_owned_operators(make_plan())
    assert message == "森空岛缓存中未持有以下排班干员：Lancet-2、年、芬、香草"
    assert "Current" not in message
    assert "Free" not in message


def test_owned_operators_pass_including_low_rarity_names(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    write_roster(
        path,
        "char_103_angel",
        "char_123_fang",
        "char_2014_nian",
        "char_240_wyvern",
        "char_285_medic2",
    )
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_present_but_invalid_cache_blocks_validation(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    path.write_text('{"data": {"characters": []}}', encoding="utf-8")
    assert "缓存无效" in schedule_roster.validate_owned_operators(make_plan())


def test_precheck_runs_even_without_backup_plans(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    write_roster(path, "char_2014_nian")
    plan = make_plan()
    plan["backup_plans"] = []

    result = Operators(plan).validate_backup_plans()
    assert not result["success"]
    assert "能天使" in result["message"]
    assert "芬" in result["message"]
