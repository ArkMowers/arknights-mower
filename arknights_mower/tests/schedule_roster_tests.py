"""Skland ownership checks shared by manual and startup schedule validation."""

import json
from unittest.mock import MagicMock

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
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": cid, "evolvePhase": 2, "level": 80} for cid in ids
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def roster_path(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(schedule_roster, "get_path", lambda _: path)
    return path


@pytest.fixture(autouse=True)
def remote_refresh(monkeypatch):
    from arknights_mower.utils import config

    monkeypatch.setattr(
        config,
        "conf",
        config.Conf(skland_info=[{"account": "offline", "password": "unused"}]),
    )
    refresh = MagicMock(
        side_effect=AssertionError("schedule validation requested Skland")
    )
    monkeypatch.setattr(
        "arknights_mower.solvers.cultivate_depot.cultivate.start", refresh
    )
    yield refresh
    refresh.assert_not_called()


def test_missing_cache_skips_ownership_check(roster_path):
    assert schedule_roster.validate_owned_operators(make_plan()) is None


def test_reports_main_backup_replacements_and_backup_tasks(roster_path, monkeypatch):
    write_roster(roster_path, "char_103_angel")

    message = schedule_roster.validate_owned_operators(make_plan())
    assert message.startswith("森空岛缓存中未持有以下排班干员：Lancet-2、年、芬、香草")
    assert "请确认已持有" in message
    assert "「养成规划」页面手动点击「刷新」后重新验证排班" in message
    assert "Current" not in message
    assert "Free" not in message
    assert "上述情况可能会导致 Mower 无法正常运行。" in message


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


def test_present_but_invalid_cache_reports_warning(roster_path):
    roster_path.write_text('{"data": {"characters": []}}', encoding="utf-8")
    message = schedule_roster.validate_owned_operators(make_plan())
    assert "缓存无效" in message
    assert "「养成规划」页面手动点击「刷新」" in message


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


def test_repeated_validation_preserves_cache_and_findings(roster_path):
    write_roster(roster_path, "char_103_angel")
    before = roster_path.read_bytes(), roster_path.stat().st_mtime_ns
    messages = [schedule_roster.validate_owned_operators(make_plan()) for _ in range(3)]
    assert all("未持有以下排班干员：Lancet-2、年、芬、香草" in msg for msg in messages)
    assert messages[0] == messages[1] == messages[2]
    assert (roster_path.read_bytes(), roster_path.stat().st_mtime_ns) == before


def test_unconfirmed_cache_miss_does_not_block(roster_path, monkeypatch):
    write_roster(roster_path, "char_103_angel")
    assert "未持有" in schedule_roster.validate_owned_operators(make_plan())


def test_read_only_cache_miss_warns_without_remote_refresh(roster_path, remote_refresh):
    write_roster(roster_path, "char_103_angel")
    message = schedule_roster.validate_owned_operators(make_plan())
    assert "森空岛缓存中未持有以下排班干员：Lancet-2、年、芬、香草" in message
    assert "「养成规划」" in message
    remote_refresh.assert_not_called()


def test_read_only_cache_checks_training_without_refresh(roster_path, remote_refresh):
    write_training_roster(roster_path, level=6)
    message = schedule_roster.validate_owned_operators(training_plan())
    assert "基础技能仅 6 级" in message
    remote_refresh.assert_not_called()


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
    plan = make_plan()
    plan["backup_plans"] = []

    result = Operators(plan).validate_backup_plans()
    assert result["success"]
    assert "能天使" in result["warnings"][0]
    assert "芬" in result["warnings"][0]


def training_plan(*, backup=False, task=False, replacement=False):
    config = PlanConfig("", "", "", workaholic="年,能天使,芬")
    slots = [Room("年", "", []), Room("能天使", "", [])]
    if replacement:
        slots[1] = Room("芬", "", ["能天使"])
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
        base = Plan({"train": [Room("年", "", []), Room("能天使", "", [])]}, config)
    return {"default_plan": base, "backup_plans": backups}


def write_training_roster(path, *, level=7, masteries=(3, 3, 2)):
    path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_2014_nian", "evolvePhase": 2, "level": 80},
                        {
                            "id": "char_103_angel",
                            "evolvePhase": 2,
                            "level": 80,
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
def test_training_slot_warns_for_unselectable_operators(
    roster_path, remote_refresh, source, level, masteries, reason
):
    write_training_roster(roster_path, level=level, masteries=masteries)
    result = Operators(training_plan(**source)).validate_backup_plans()
    remote_refresh.assert_not_called()
    assert result["success"]
    assert result["status"] == "passed"
    message = "\n".join(result["warnings"])
    assert "上述情况可能会导致 Mower 无法正常运行。" in message
    assert "训练位" in message
    assert "能天使" in message
    assert reason in message
    action = "升至 7 级后" if level < 7 else "更换干员后"
    assert action in message
    assert "「养成规划」页面手动点击「刷新」后重新验证排班" in message


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
    message = schedule_roster.validate_owned_operators(training_plan())
    assert "无法确认" in message
    assert "可能会导致 Mower 无法正常运行" not in message
    assert "同步干员数据" in message
    assert "「养成规划」页面手动点击「刷新」" in message


@pytest.mark.parametrize("placeholder", ["", "Current", "Free"])
def test_training_slot_placeholders_and_assistants_are_exempt(roster_path, placeholder):
    write_roster(roster_path, "char_2014_nian")
    plan = training_plan()
    plan["default_plan"].plan["train"][1].agent = placeholder
    assert schedule_roster.validate_owned_operators(plan) is None


def test_training_slot_uses_data_from_next_explicit_refresh(roster_path):
    write_training_roster(roster_path, level=6)
    assert "基础技能仅 6 级" in schedule_roster.validate_owned_operators(
        training_plan()
    )
    write_training_roster(roster_path)
    assert schedule_roster.validate_owned_operators(training_plan()) is None


def test_ownership_and_training_findings_do_not_refresh(roster_path, remote_refresh):
    write_training_roster(roster_path, level=6)
    plan = training_plan()
    plan["default_plan"].plan["train"][1].replacement = ["芬"]
    result = Operators(plan).validate_backup_plans()
    remote_refresh.assert_not_called()
    assert result["success"]
    assert "未持有以下排班干员：芬" in result["warnings"][0]
    assert "基础技能仅 6 级" in result["warnings"][0]


def test_training_slot_rechecks_mastery_after_explicit_cache_update(roster_path):
    write_roster(roster_path, "char_2014_nian")
    assert "未持有以下排班干员：能天使" in schedule_roster.validate_owned_operators(
        training_plan()
    )
    write_training_roster(roster_path, masteries=(3, 3, 3))
    assert "所有技能均已专三" in schedule_roster.validate_owned_operators(
        training_plan()
    )


def test_training_slot_checks_secondary_binding_replacements(roster_path, monkeypatch):
    write_training_roster(roster_path, level=6)
    plan = training_plan()
    slot = plan["default_plan"].plan["train"][1]
    slot.agent = "Current"
    slot.group_bindings = [{"group": "训练替班", "replacement": ["能天使"]}]
    assert "基础技能仅 6 级" in schedule_roster.validate_owned_operators(plan)


@pytest.mark.parametrize("unfinished_form", [False, True])
def test_training_slot_same_name_forms_use_owned_progress(
    roster_path, monkeypatch, unfinished_form
):
    characters = [{"id": "char_2014_nian", "evolvePhase": 2, "level": 80}]
    characters.extend(
        {
            "id": cid,
            "evolvePhase": 2,
            "level": 80,
            "mainSkillLevel": 7,
            "skills": [{"level": mastery}],
        }
        for cid, mastery in [
            ("char_002_amiya", 3),
            ("char_1001_amiya2", 2 if unfinished_form else 3),
        ]
    )
    roster_path.write_text(json.dumps({"data": {"characters": characters}}))
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


@pytest.mark.parametrize(
    "name,cid,phase,level,facility,warning",
    [
        ("夜刀", "char_502_nblade", 0, 29, "制造站", "精0 30级"),
        ("夜刀", "char_502_nblade", 0, 30, "制造站", None),
        ("芬", "char_123_fang", 0, 1, "制造站", None),
        ("能天使", "char_103_angel", 0, 1, "制造站", None),
        ("芬", "char_123_fang", 0, 55, "贸易站", "精1 1级"),
        ("芬", "char_123_fang", 1, 1, "贸易站", None),
        ("能天使", "char_103_angel", 1, 80, "贸易站", "精2 1级"),
        ("能天使", "char_103_angel", 2, 1, "贸易站", None),
        ("孑", "char_272_strong", 0, 1, "贸易站", None),
    ],
)
def test_building_skills_use_catalog_unlock_thresholds(
    roster_path, name, cid, phase, level, facility, warning, bundled_mastery_skills
):
    plan = {
        "default_plan": Plan(
            {"room_1_1": [Room(name, "", [], facility)]},
            PlanConfig("", "", "", workaholic=name),
        ),
        "backup_plans": [],
    }
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [{"id": cid, "evolvePhase": phase, "level": level}]
                }
            }
        )
    )
    result = Operators(plan).validate_backup_plans()
    assert result["success"], result
    if warning:
        assert warning in result["warnings"][0]
        assert "上述情况可能会导致 Mower 无法正常运行。" not in result["warnings"][0]
    else:
        assert result["warnings"] == []


@pytest.mark.parametrize("source", ["main", "backup", "replacement", "binding", "task"])
@pytest.mark.parametrize(
    "name,cid,phase,expected",
    [
        ("清流", "char_385_finlpp", 1, True),
        ("极境", "char_401_elysm", 1, True),
        ("能天使", "char_103_angel", 1, True),
        ("清流", "char_385_finlpp", 2, False),
        ("梓兰", "char_278_orchid", 1, False),
    ],
)
def test_reception_checks_all_assignments_and_only_four_to_six_stars(
    roster_path, source, name, cid, phase, expected, bundled_mastery_skills
):
    conf = PlanConfig("", "", "")
    slot = Room(name, "", [])
    main = Plan({}, conf)
    backup = Plan({}, conf)
    if source == "main":
        main.plan["meeting"] = [slot]
    elif source == "backup":
        backup.plan["meeting"] = [slot]
    elif source in ("replacement", "binding"):
        slot.agent = "Current"
        if source == "replacement":
            slot.replacement = [name]
        else:
            slot.group_bindings = [{"group": "甲", "replacement": [name]}]
        main.plan["meeting"] = [slot]
    else:
        backup.task = {"meeting": [name]}
    plan = {"default_plan": main, "backup_plans": [backup]}
    roster_path.write_text(
        json.dumps(
            {"data": {"characters": [{"id": cid, "evolvePhase": phase, "level": 1}]}}
        )
    )
    warning = schedule_roster.validate_owned_operators(plan) or ""
    assert ("会客室干员" in warning) is expected
    assert "可能会导致 Mower 无法正常运行" not in warning
    if expected:
        assert name in warning
        assert "尚未精二" in warning
        assert "基建技能" not in warning


def test_unknown_progression_is_advisory_and_same_name_forms_share_progress(
    roster_path, bundled_mastery_skills
):
    plan = {
        "default_plan": Plan(
            {"central": [Room("阿米娅", "", [])]},
            PlanConfig("", "", "", workaholic="阿米娅"),
        ),
        "backup_plans": [],
    }
    roster_path.write_text(
        json.dumps({"data": {"characters": [{"id": "char_002_amiya"}]}})
    )
    result = Operators(plan).validate_backup_plans()
    assert result["success"]
    assert "无法确认" in result["warnings"][0]
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_002_amiya", "evolvePhase": 0, "level": 1},
                        {"id": "char_1001_amiya2", "evolvePhase": 2, "level": 1},
                    ]
                }
            }
        )
    )
    assert Operators(plan).validate_backup_plans()["warnings"] == []


def test_unavailable_skill_catalog_remains_advisory(roster_path, monkeypatch):
    from arknights_mower.utils import building_skills

    write_roster(roster_path, "char_103_angel", "char_123_fang")

    def unavailable():
        raise FileNotFoundError("building-skill catalog")

    monkeypatch.setattr(building_skills, "skill_index", unavailable)
    plan = make_plan()
    plan["backup_plans"] = []
    result = Operators(plan).validate_backup_plans()
    assert result["success"]
    assert "更新资源包" in result["warnings"][0]


@pytest.mark.parametrize("source", ["main", "backup", "replacement", "binding", "task"])
@pytest.mark.parametrize("facility,expected", [("制造站", False), ("贸易站", True)])
def test_only_assigned_facility_skills_warn_for_every_roster_source(
    roster_path, bundled_mastery_skills, source, facility, expected
):
    conf = PlanConfig("", "", "")
    main = Plan({"room_1_1": [Room("Current", "", [], facility)]}, conf)
    backup = Plan({}, conf)
    slot = Room("芬", "", [], facility)
    if source == "main":
        main.plan["room_1_1"] = [slot]
    elif source == "backup":
        # Backup facility metadata may be omitted and inherited from the main plan.
        slot.facility = ""
        backup.plan["room_1_1"] = [slot]
    elif source == "replacement":
        main.plan["room_1_1"][0].replacement = ["芬"]
    elif source == "binding":
        main.plan["room_1_1"][0].group_bindings = [
            {"group": "甲", "replacement": ["芬"]}
        ]
    else:
        backup.task = {"room_1_1": ["芬"]}
    plan = {"default_plan": main, "backup_plans": [backup]}
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_123_fang", "evolvePhase": 0, "level": 1}
                    ]
                }
            }
        )
    )
    warning = schedule_roster.validate_owned_operators(plan)
    if expected:
        assert "进驻设施（贸易站）" in warning
        assert "精1 1级" in warning
    else:
        assert warning is None


@pytest.mark.parametrize(
    "room,name,cid,phase,level",
    [
        ("contact", "巡林者", "char_503_rang", 0, 1),
        ("central", "阿米娅", "char_002_amiya", 0, 1),
        ("factory", "九色鹿", "char_4019_ncdeer", 0, 1),
        ("train", "艾丽妮", "char_4009_irene", 0, 1),
    ],
)
def test_unrelated_workshop_training_and_dorm_skills_do_not_warn(
    roster_path, bundled_mastery_skills, room, name, cid, phase, level
):
    plan = {
        "default_plan": Plan({room: [Room(name, "", [])]}, PlanConfig("", "", "")),
        "backup_plans": [],
    }
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [{"id": cid, "evolvePhase": phase, "level": level}]
                }
            }
        )
    )
    assert schedule_roster.validate_owned_operators(plan) is None


def test_operator_with_multiple_assignments_reports_only_the_locked_facility(
    roster_path, bundled_mastery_skills
):
    plan = {
        "default_plan": Plan(
            {
                "room_1_1": [Room("芬", "", [], "制造站")],
            },
            PlanConfig("", "", ""),
        ),
        "backup_plans": [Plan({}, PlanConfig("", "", ""), task={"room_1_2": ["芬"]})],
    }
    plan["default_plan"].plan["room_1_2"] = [Room("Current", "", [], "贸易站")]
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_123_fang", "evolvePhase": 0, "level": 1}
                    ]
                }
            }
        )
    )
    warning = schedule_roster.validate_owned_operators(plan)
    assert "进驻设施（贸易站）" in warning
    assert "制造站" not in warning


def test_explicit_dorm_assignment_checks_dorm_skills(
    roster_path, bundled_mastery_skills
):
    plan = {
        "default_plan": Plan(
            {"dormitory_3": [Room("阿米娅", "", [])]}, PlanConfig("", "", "")
        ),
        "backup_plans": [],
    }
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_002_amiya", "evolvePhase": 0, "level": 1}
                    ]
                }
            }
        )
    )
    warning = schedule_roster.validate_owned_operators(plan)
    assert "进驻设施（宿舍）" in warning
    assert "精2 1级" in warning


@pytest.mark.parametrize(
    "room,name,cid",
    [("factory", "九色鹿", "char_4019_ncdeer"), ("train", "艾丽妮", "char_4009_irene")],
)
def test_excluded_facilities_do_not_request_growth_data(
    roster_path, bundled_mastery_skills, room, name, cid
):
    plan = {
        "default_plan": Plan({room: [Room(name, "", [])]}, PlanConfig("", "", "")),
        "backup_plans": [],
    }
    roster_path.write_text(json.dumps({"data": {"characters": [{"id": cid}]}}))
    assert schedule_roster.validate_owned_operators(plan) is None


def test_reception_promotion_warning_does_not_duplicate_skill_warning(
    roster_path, bundled_mastery_skills
):
    plan = {
        "default_plan": Plan(
            {"meeting": [Room("极境", "", [])]},
            PlanConfig("", "", "", workaholic="极境"),
        ),
        "backup_plans": [],
    }
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_401_elysm", "evolvePhase": 1, "level": 1}
                    ]
                }
            }
        )
    )
    result = Operators(plan).validate_backup_plans()
    assert result["success"], result
    assert "会客室干员 极境 尚未精二" in result["warnings"][0]
    assert "基建技能" not in result["warnings"][0]


def test_reception_promotion_warning_preserves_other_facility_skill_checks(
    roster_path, bundled_mastery_skills
):
    conf = PlanConfig("", "", "")
    plan = {
        "default_plan": Plan({"meeting": [Room("行箸", "", [])]}, conf),
        "backup_plans": [Plan({"contact": [Room("行箸", "", [])]}, conf)],
    }
    roster_path.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [
                        {"id": "char_4172_xingzh", "evolvePhase": 1, "level": 1}
                    ]
                }
            }
        )
    )
    warning = schedule_roster.validate_owned_operators(plan)
    assert "会客室干员 行箸 尚未精二" in warning
    assert "进驻设施（人力办公室）" in warning
    assert "进驻设施（会客室）" not in warning
