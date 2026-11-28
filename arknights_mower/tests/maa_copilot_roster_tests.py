import pytest

from arknights_mower.utils import maa_copilot_roster as check


@pytest.fixture
def roster(monkeypatch):
    records = {}
    grow = {}
    monkeypatch.setattr(check, "get_cultivate_characters", lambda: records)
    monkeypatch.setattr(
        check, "get_skill_data", lambda: {"growth": {"characters": grow}}
    )

    def add(name, *, cid=None, owned=True, **values):
        cid = cid or name
        grow[cid] = {
            "name": name,
            "modules": [{"id": "mX", "type": "GUARD-X"}],
            "profession": "WARRIOR",
        }
        if owned:
            records[cid] = {
                "evolvePhase": 2,
                "level": 30,
                "mainSkillLevel": 7,
                "skills": [{"level": 0}, {"level": 0}, {"level": 3}],
                "equips": [{"id": "mX", "level": 1}],
                **values,
            }
        return grow[cid]

    add("无关干员")
    return add


def assess(*ops, groups=()):
    return check.check_copilot_roster(
        {
            "opers": [{"name": o} if isinstance(o, str) else o for o in ops],
            "groups": [
                {
                    "name": f"组{i}",
                    "opers": [
                        {"name": o} if isinstance(o, str) else o for o in members
                    ],
                }
                for i, members in enumerate(groups)
            ],
        }
    )


def oper(name, *, skill=0, **requirements):
    return {"name": name, "skill": skill, "requirements": requirements}


def test_captain_import_points_out_only_the_missing_levels(roster):
    roster("塔露拉")
    result = assess(oper("塔露拉", skill=3, elite=2, level=60, skill_level=10))
    assert result["status"] == "shortfall" and result["can_borrow"]
    assert result["gaps"] == [
        {
            "slot": "塔露拉",
            "candidates": [{"name": "塔露拉", "reasons": ["精二 30 级，要求 60 级"]}],
        }
    ]


def test_higher_promotion_satisfies_previous_phases_level(roster):
    roster("塔露拉", level=1)
    assert assess(oper("塔露拉", elite=1, level=60))["status"] == "ready"


def test_candidate_missing_raised_skill_and_module(roster):
    roster("塔露拉", equips=[{"id": "mX", "level": 0}])
    result = assess(oper("塔露拉", skill=2, skill_level=10, module=1))
    assert result["gaps"][0]["candidates"][0]["reasons"] == [
        "技能 2 为 7 级，要求 10 级",
        "未解锁 X 模组",
    ]


def test_ignores_potential_and_module_level_in_ordinary_formation(roster):
    roster("塔露拉")
    assert (
        assess(oper("塔露拉", module=1, module_level=3, potential=6))["status"]
        == "ready"
    )


def test_reassigns_candidates_to_distinct_positions(roster):
    roster("甲")
    roster("乙")
    roster("丙", owned=False)
    assert assess(groups=[["甲", "乙"], ["甲", "丙"]])["status"] == "ready"


def test_multiple_missing_slots_cannot_be_filled_by_one_support(roster):
    roster("甲", owned=False)
    roster("乙", owned=False)
    result = assess("甲", "乙")
    assert not result["can_borrow"]
    assert [g["slot"] for g in result["gaps"]] == ["甲", "乙"]


def test_does_not_offer_duplicate_operator_as_support(roster):
    roster("甲")
    result = assess("甲", "甲")
    assert result["status"] == "shortfall" and not result["can_borrow"]
    assert result["gaps"][0]["candidates"][0]["reasons"] == ["该干员已被其他位置占用"]


def test_alternative_support_can_reassign_another_slot(roster):
    roster("甲")
    roster("乙", owned=False)
    result = assess(groups=[["甲", "乙"], ["甲"]])
    assert result["status"] == "shortfall" and result["can_borrow"]


def test_different_professions_of_same_operator_cannot_fill_two_slots(roster):
    base = roster("阿米娅", cid="amiya")
    base.update(profession="CASTER", progression_owner="amiya")
    form = roster("阿米娅", cid="guard")
    form.update(progression_owner="amiya")
    assert assess("阿米娅-WARRIOR")["status"] == "ready"
    result = assess("阿米娅", {"name": "阿米娅", "role": "warrior"})
    assert result["status"] == "shortfall" and not result["can_borrow"]


def test_unknown_member_does_not_hide_a_satisfied_group(roster):
    roster("甲")
    assert assess(groups=[["甲", "未收录名称"]])["status"] == "ready"
    assert assess("未收录名称")["status"] == "unknown"


def test_missing_required_skill_snapshot_is_not_reported_as_unowned(roster):
    roster("甲", skills=[])
    assert assess(oper("甲", skill=3, skill_level=10))["status"] == "unknown"


def test_missing_snapshot_is_optional(monkeypatch):
    monkeypatch.setattr(check, "get_cultivate_characters", lambda: None)
    assert assess("塔露拉")["status"] == "unknown"
    assert assess()["status"] == "ready"


def test_unknown_slot_preserves_independently_confirmed_gap(roster):
    roster("塔露拉")
    result = assess(oper("塔露拉", elite=2, level=60), "未收录名称")
    assert result["status"] == "unknown" and not result["can_borrow"]
    assert result["gaps"] == [
        {
            "slot": "塔露拉",
            "candidates": [{"name": "塔露拉", "reasons": ["精二 30 级，要求 60 级"]}],
        }
    ]


@pytest.mark.parametrize(
    "count,missing,status,can_borrow",
    [
        (12, 0, "ready", False),
        (12, 1, "shortfall", True),
        (13, 0, "shortfall", True),
        (13, 1, "shortfall", True),
        (13, 2, "shortfall", False),
        (14, 0, "shortfall", False),
        (14, 1, "shortfall", False),
        (15, 2, "shortfall", False),
    ],
)
def test_formation_capacity_and_missing_operators(
    roster, count, missing, status, can_borrow
):
    names = [f"干员{i}" for i in range(count)]
    for i, name in enumerate(names):
        roster(name, owned=i >= missing)
    result = assess(*names)
    assert result["status"] == status
    assert result["can_borrow"] is can_borrow
    assert len(result["gaps"]) == missing
    if count > 12:
        assert f"需要 {count} 个编队位置" in result["message"]


@pytest.mark.parametrize("count,status", [(13, "unknown"), (14, "shortfall")])
def test_capacity_is_reported_even_without_roster(monkeypatch, count, status):
    monkeypatch.setattr(check, "get_cultivate_characters", lambda: None)
    result = assess(*(f"干员{i}" for i in range(count)))
    assert result["status"] == status and not result["can_borrow"]
    assert f"需要 {count} 个编队位置" in result["message"]
    assert "刷新森空岛" in result["message"]


def test_empty_group_and_alternatives_do_not_consume_extra_slots(roster):
    names = [f"干员{i}" for i in range(13)]
    for name in names:
        roster(name)
    result = assess(*names[:11], groups=[names[11:], []])
    assert result["status"] == "ready"
