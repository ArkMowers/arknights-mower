import json
from pathlib import Path

import pytest

from arknights_mower.utils import building_skills, mastery_recommendation
from arknights_mower.utils.selection_skill_rank import (
    selection_efficiency_rank,
    selection_skill_rank,
)

ROOT = Path(__file__).resolve().parents[2]
DOROTHY = "char_4048_doroth"
SILENCE = "char_108_silent"
WEEDY = "char_400_weedy"


@pytest.fixture
def box(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: path)
    monkeypatch.setattr(
        mastery_recommendation,
        "_find_skill_data",
        lambda: ROOT / "arknights_mower/data/skill_data.json",
    )
    monkeypatch.setattr(mastery_recommendation, "_skill_data_cache", None)
    monkeypatch.setattr(building_skills, "resource_pkg_path", lambda rel: ROOT / rel)
    building_skills.clear_building_skills()
    yield path
    building_skills.clear_building_skills()


def character(char_id, phase=2):
    return {"id": char_id, "evolvePhase": phase, "level": 1}


def write_roster(path, *characters):
    path.write_text(json.dumps({"data": {"characters": characters}}), encoding="utf-8")


def test_last_matching_slot_ties_and_prefix(box):
    write_roster(
        box,
        character(DOROTHY),
        character(SILENCE),
        character(WEEDY),
        character("char_242_otter"),
        character("char_501_durin"),
    )
    rank = selection_skill_rank
    assert rank("MANUFACTURE", "ALL", "多萝西", ()) == {False: (2, 3), True: (2, 3)}
    assert rank("MANUFACTURE", "ALL", "多萝西", ["梅尔", "杜林"]) == {
        False: (1, 2),
        True: (2, 3),
    }
    assert rank("MANUFACTURE", "SPECIAL", "多萝西", ["赫默"]) == {
        False: (1, 1),
        True: (2, 2),
    }
    for args in (
        ("MANUFACTURE", "ALL", "杜林", ()),
        ("MANUFACTURE", "CASTER", "多萝西", ()),
        ("TRADING", "ALL", "多萝西", ()),
        ("MANUFACTURE", "ALL", "多萝西", ["多萝西"]),
        ("MANUFACTURE", "ALL", "多萝西", ["赫默", "赫默"]),
        ("MANUFACTURE", "ALL", "多萝西", ["未持有"]),
    ):
        assert rank(*args) is None


def test_same_file_updated_and_different_account_path(box, monkeypatch):
    def rank():
        return selection_skill_rank("MANUFACTURE", "ALL", "赫默", ())

    assert rank() is None
    write_roster(box, character(SILENCE, 0), character(WEEDY))
    assert rank() == {False: (1, 1), True: (2, 2)}
    write_roster(box, character(SILENCE), character(DOROTHY), character(WEEDY))
    assert rank() == {False: (1, 2), True: (2, 3)}
    other = box.with_name("other-account.json")
    write_roster(other, character(SILENCE), character("char_242_otter"))
    monkeypatch.setattr(mastery_recommendation, "get_path", lambda _: other)
    assert rank() == {False: (2, 2), True: (1, 1)}
    other.unlink()
    assert rank() is None


@pytest.mark.parametrize(
    "other",
    [
        {"id": SILENCE, "level": 1},
        {"id": SILENCE, "evolvePhase": 2},
        {"id": SILENCE, "evolvePhase": 3, "level": 20},
        {"id": SILENCE, "evolvePhase": 1, "level": 0},
        character("char_unknown"),
        character(DOROTHY),
    ],
)
def test_incomplete_or_ambiguous_roster_abstains(box, other):
    write_roster(box, character(DOROTHY), other)
    assert selection_skill_rank("MANUFACTURE", "ALL", "多萝西", ()) is None


def test_unknown_active_amiya_form_also_protects_other_targets(box):
    write_roster(
        box,
        character("char_002_amiya"),
        character("char_1001_amiya2"),
        character("char_1037_amiya3"),
        character("char_306_leizi"),
        character(DOROTHY),
    )
    rank = selection_skill_rank
    assert rank("CONTROL", "ALL", "惊蛰", ()) == {False: (2, 2), True: (1, 1)}
    assert rank("CONTROL", "CASTER", "惊蛰", ()) is None
    assert rank("CONTROL", "MEDIC", "阿米娅", ()) is None
    assert rank("CONTROL", "CASTER", "惊蛰", ["阿米娅"]) == {
        False: (1, 1),
        True: (1, 1),
    }
    assert rank("MANUFACTURE", "SPECIAL", "多萝西", ()) == {False: (1, 1), True: (1, 1)}


def test_selected_legacy_resource_without_sort_ids_abstains(box, monkeypatch):
    write_roster(box, character(DOROTHY))
    assert selection_skill_rank("MANUFACTURE", "ALL", "多萝西", ()) == {
        False: (1, 1),
        True: (1, 1),
    }
    old = box.with_name("legacy-skill.json")
    rows = [
        {
            "name": "多萝西",
            "child_skill": [
                {k: v for k, v in skill.items() if k != "sortId"}
                for skill in building_skills.skill_index()["多萝西"]
            ],
        }
    ]
    old.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(building_skills, "resource_pkg_path", lambda _: old)
    building_skills.clear_building_skills()
    assert selection_skill_rank("MANUFACTURE", "ALL", "多萝西", ()) is None


def test_efficiency_uses_whole_tie_group_and_product_applicability(box):
    write_roster(
        box,
        *(
            character(cid)
            for cid in (
                DOROTHY,
                "char_328_cammou",
                "char_190_clour",
                "char_381_bubble",
                "char_369_bena",
                "char_237_gravel",
            )
        ),
    )
    rank = selection_efficiency_rank
    for name in ("卡达", "红云", "泡泡"):
        assert rank("MANUFACTURE", "ALL", name, (), product="exp3") == {
            False: (2, 4),
            True: (2, 4),
        }
    assert rank("MANUFACTURE", "ALL", "泡泡", ["红云"], product="exp3") == {
        False: (2, 3),
        True: (2, 3),
    }
    assert rank("MANUFACTURE", "ALL", "贝娜", (), product="exp3") == {
        False: (5, 5),
        True: (1, 1),
    }
    assert rank("MANUFACTURE", "SPECIAL", "砾", (), product="exp3") is None
    assert rank("MANUFACTURE", "SPECIAL", "砾", (), product="gold") == {
        False: (1, 1),
        True: (3, 3),
    }
    assert rank("MANUFACTURE", "SPECIAL", "砾", (), product="orirock") is None


def test_lmd_order_uses_trade_skills_with_empty_targets(box):
    write_roster(
        box,
        character("char_103_angel"),
        character("char_455_nothin"),
        character("char_478_kirara"),
        character("char_1033_swire2"),
    )
    rank = selection_efficiency_rank
    assert rank("TRADING", "ALL", "能天使", (), product="lmd") == {
        False: (1, 1),
        True: (4, 4),
    }
    # 琳琅诗怀雅的两项贸易技能分别为 20 和 0。
    assert rank("TRADING", "SPECIAL", "琳琅诗怀雅", (), product="lmd") == {
        False: (1, 1),
        True: (3, 3),
    }
    assert rank("TRADING", "SPECIAL", "乌有", (), product="lmd") == {
        False: (3, 3),
        True: (1, 1),
    }
    for product in ("orundum", "gold", "exp3", "", None):
        assert rank("TRADING", "ALL", "能天使", (), product=product) is None


def test_lmd_efficiency_reaches_wind_chimes_after_two_retained_slots(box):
    guards = {
        "玫兰莎",
        "缠丸",
        "慕斯",
        "石英",
        "摩根",
        "拉普兰德",
        "铎铃",
        "柏喙",
        "龙舌兰",
        "雷狼龙S空爆",
        "贝洛内",
        "银灰",
        "赫德雷",
        "佩佩",
        "锏",
        "维娜·维多利亚",
        "月见夜",
    }
    retained = ["绮良", "鸿雪"]
    roster = guards.union(retained)
    operators = json.loads(
        (ROOT / "arknights_mower/data/riic/operators.json").read_text("utf8")
    )
    growth = {3: (1, 55), 4: (2, 70), 5: (2, 80), 6: (2, 90)}
    characters = []
    for operator in operators["operators"]:
        if operator["name"] in roster:
            phase, level = growth[operator["rarity"]]
            characters.append(
                {"id": operator["charId"], "evolvePhase": phase, "level": level}
            )
    assert len(characters) == len(roster)
    write_roster(box, *characters)
    assert selection_skill_rank("TRADING", "WARRIOR", "铎铃", retained) == {
        False: (9, 9),
        True: (9, 9),
    }
    assert selection_efficiency_rank(
        "TRADING", "WARRIOR", "铎铃", retained, product="lmd"
    ) == {
        False: (12, 17),
        True: (1, 6),
    }


@pytest.mark.parametrize("missing", ["targets", "efficiency"])
def test_skill_only_resource_abstains_on_efficiency_without_losing_skill_rank(
    box, monkeypatch, missing
):
    write_roster(box, character(DOROTHY), character(WEEDY))
    assert selection_efficiency_rank(
        "MANUFACTURE", "SPECIAL", "多萝西", (), product="gold"
    ) == {False: (1, 1), True: (2, 2)}
    catalog = building_skills.skill_index()
    rows = []
    for name in ("多萝西", "温蒂"):
        skills = [s.copy() for s in catalog[name]]
        if name == "温蒂":
            for s in skills:
                s.pop(missing, None)
        rows.append({"name": name, "child_skill": skills})
    old = box.with_name("skill-only.json")
    old.write_text(json.dumps(rows), encoding="utf8")
    monkeypatch.setattr(building_skills, "resource_pkg_path", lambda _: old)
    building_skills.clear_building_skills()
    assert (
        selection_efficiency_rank(
            "MANUFACTURE", "SPECIAL", "多萝西", (), product="gold"
        )
        is None
    )
    assert selection_efficiency_rank(
        "MANUFACTURE", "SPECIAL", "多萝西", ["温蒂"], product="gold"
    ) == {False: (1, 1), True: (1, 1)}
    assert selection_skill_rank("MANUFACTURE", "SPECIAL", "多萝西", ()) == {
        False: (1, 1),
        True: (2, 2),
    }
