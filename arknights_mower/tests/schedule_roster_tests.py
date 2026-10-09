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


def training_plan(*, backup=False, task=False, replacement=False):
    config = PlanConfig("", "", "")
    slots = [Room("年", "", []), Room("能天使", "", [])]
    if replacement:
        slots[1] = Room("Current", "", ["能天使"])
    base = Plan({"train": slots}, config)
    backups = []
    if backup or task:
        backups.append(
            Plan(
                {} if task else {"train": slots},
                config,
                task={"train": ["Current", "能天使"]} if task else None,
                name="训练副表",
            )
        )
        base = Plan({"train": [Room("", "", []), Room("", "", [])]}, config)
    return {"default_plan": base, "backup_plans": backups}


def write_training_roster(path, *, level=7, masteries=(3, 3, 2)):
    path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_2014_nian"},
                        {
                            "id": "char_103_angel",
                            "mainSkillLevel": level,
                            "skills": [{"level": value} for value in masteries],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "source", [{}, {"backup": True}, {"task": True}, {"replacement": True}]
)
@pytest.mark.parametrize(
    ("level", "masteries", "reason"),
    [(6, (0, 0, 0), "基础技能仅 6 级"), (7, (3, 3, 3), "所有技能均已专三")],
)
def test_training_slot_rejects_unselectable_operators(
    roster_path, monkeypatch, source, level, masteries, reason
):
    write_training_roster(roster_path, level=level, masteries=masteries)
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: False)
    result = Operators(training_plan(**source)).validate_backup_plans()
    assert result["status"] == "failed"
    assert "训练位" in result["message"]
    assert "能天使" in result["message"]
    assert reason in result["message"]


@pytest.mark.parametrize("masteries", [(0, 0, 0), (3, 3, 2), (3, 0, 3)])
def test_training_slot_accepts_seven_with_any_unfinished_skill(roster_path, masteries):
    write_training_roster(roster_path, masteries=masteries)
    assert schedule_roster.validate_owned_operators(training_plan()) is None


@pytest.mark.parametrize(
    ("level", "masteries"),
    [(None, (0,)), (True, (0,)), (7, ()), (7, (None,)), (7, (True,)), (7, (4,))],
)
def test_training_slot_unknown_skill_data_requests_sync(
    roster_path, monkeypatch, level, masteries
):
    write_training_roster(roster_path, level=level, masteries=masteries)
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: False)
    message = schedule_roster.validate_owned_operators(training_plan())
    assert "无法确认" in message
    assert "同步干员数据" in message


@pytest.mark.parametrize("placeholder", ["", "Current", "Free"])
def test_training_slot_placeholders_and_assistants_are_exempt(roster_path, placeholder):
    write_roster(roster_path, "char_2014_nian")
    plan = training_plan()
    plan["default_plan"].plan["train"][1].agent = placeholder
    assert schedule_roster.validate_owned_operators(plan) is None


def test_training_slot_refreshes_stale_skill_data_once(roster_path, monkeypatch):
    write_training_roster(roster_path, level=6)
    calls = []

    def refresh():
        calls.append(True)
        write_training_roster(roster_path)
        return True

    monkeypatch.setattr(schedule_roster, "_refresh_roster", refresh)
    assert schedule_roster.validate_owned_operators(training_plan()) is None
    assert calls == [True]


def test_training_slot_rechecks_mastery_after_ownership_refresh(
    roster_path, monkeypatch
):
    write_roster(roster_path, "char_2014_nian")

    def refresh():
        write_training_roster(roster_path, masteries=(3, 3, 3))
        return True

    monkeypatch.setattr(schedule_roster, "_refresh_roster", refresh)
    assert "所有技能均已专三" in schedule_roster.validate_owned_operators(
        training_plan()
    )


def test_training_slot_checks_secondary_binding_replacements(roster_path, monkeypatch):
    write_training_roster(roster_path, level=6)
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: False)
    plan = training_plan()
    slot = plan["default_plan"].plan["train"][1]
    slot.agent = "Current"
    slot.group_bindings = [{"group": "训练替班", "replacement": ["能天使"]}]
    assert "基础技能仅 6 级" in schedule_roster.validate_owned_operators(plan)


@pytest.mark.parametrize("unfinished_form", [False, True])
def test_training_slot_same_name_forms_use_owned_progress(
    roster_path, monkeypatch, unfinished_form
):
    characters = [{"id": "char_2014_nian"}]
    characters.extend(
        {
            "id": cid,
            "mainSkillLevel": 7,
            "skills": [{"level": mastery}],
        }
        for cid, mastery in [
            ("char_002_amiya", 3),
            ("char_1001_amiya2", 2 if unfinished_form else 3),
        ]
    )
    roster_path.write_text(json.dumps({"data": {"characters": characters}}))
    monkeypatch.setattr(schedule_roster, "_refresh_roster", lambda: False)
    plan = training_plan()
    plan["default_plan"].plan["train"][1].agent = "阿米娅"
    message = schedule_roster.validate_owned_operators(plan)
    if unfinished_form:
        assert message is None
    else:
        assert "所有技能均已专三" in message


@pytest.mark.parametrize("payload", [None, {"code": 0, "data": {"items": []}}])
def test_training_without_roster_retains_existing_compatibility(roster_path, payload):
    if payload is not None:
        roster_path.write_text(json.dumps(payload))
    assert schedule_roster.validate_owned_operators(training_plan()) is None
