import hashlib
import json

import pytest

from arknights_mower.utils import maa_copilot as library
from arknights_mower.utils import maa_copilot_normalization as normalization
from arknights_mower.utils.config.conf import CopilotConf


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setattr(library, "get_path", lambda _: tmp_path / "library")
    monkeypatch.setattr(normalization.config.conf, "maa_path", str(tmp_path / "maa"))


def raw(**fields):
    return json.dumps(
        {"stage_name": "1-7", "actions": [], **fields}, ensure_ascii=False
    ).encode()


def stored(**fields):
    info = library.store_script(raw(**fields))
    return json.loads(library.script_path(info["id"]).read_text("utf-8"))


def test_primary_and_group_skills_use_mower_rarity_and_amiya_form():
    ops = [
        {"name": name, "skill": skill}
        for name, skill in [
            ("夜刀", 1),
            ("芬", 2),
            ("桃金娘", 3),
            ("棘刺", 3),
            ("阿米娅", 3),
            ("阿米娅-MEDIC", 3),
            ("芬", 1),
            ("桃金娘", 2),
        ]
    ]
    result = stored(opers=ops[:4], groups=[{"name": "替补", "opers": ops[4:]}])
    rows = result["opers"] + result["groups"][0]["opers"]
    assert [op["skill"] for op in rows] == [0, 0, 0, 3, 3, 0, 1, 2]
    assert [op.get("requirements") for op in rows] == [
        None,
        None,
        None,
        {"elite": 2},
        None,
        None,
        None,
        {"elite": 1},
    ]


def test_unresolved_foreign_name_keeps_skill_until_maa_resources_are_available(
    tmp_path,
):
    op = {"name": "First Snow", "skill": 3}
    info = library.store_script(raw(opers=[op]))
    source = library.script_path(info["id"])
    assert json.loads(source.read_bytes())["opers"] == [op]
    table = tmp_path / "maa/resource/battle_data.json"
    table.parent.mkdir(parents=True)
    table.write_text(
        json.dumps({"chars": {"char_example": {"name_en": "First Snow", "rarity": 5}}})
    )
    directory = tmp_path / "run"
    conf = CopilotConf(scripts=[{"id": info["id"]}])
    library.build_copilot_params(conf, directory)
    assert json.loads((directory / source.name).read_bytes())["opers"] == [
        {"name": "First Snow", "skill": 0}
    ]


def test_installed_battle_data_resolves_localized_names_and_unknowns(tmp_path):
    path = tmp_path / "maa/resource/battle_data.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "chars": {
                    "char_002_amiya": {
                        "name": "阿米娅",
                        "name_en": "Amiya",
                        "name_jp": "アーミヤ",
                        "rarity": 5,
                    },
                    "char_1001_amiya2": {"name_en": "Amiya-WARRIOR", "rarity": 5},
                }
            }
        )
    )
    ops = [
        {"name": name, "skill": 3}
        for name in ("aMiYa", "アーミヤ", "Amiya-WARRIOR", "未知")
    ]
    rows = stored(opers=ops)["opers"]
    assert [op["skill"] for op in rows] == [3, 3, 0, 3]
    assert "requirements" not in rows[3]
    assert rows[0]["requirements"] == rows[1]["requirements"] == {"elite": 2}


@pytest.mark.parametrize(
    "skill,level,module,elite,expected",
    [
        (0, 4, -1, 0, 0),
        (2, -1, -1, -1, 1),
        (0, 8, -1, -1, 2),
        (0, -1, 3, -1, 2),
        (0, 5, 0, 0, 1),
        (0, 7, -1, 0, 1),
        (0, 8, 0, 0, 2),
        (0, 10, 0, 1, 2),
        (0, 0, 1, 0, 2),
        (2, 0, -1, 2, 2),
    ],
)
def test_elite_minimum_preserves_other_requirements(
    skill, level, module, elite, expected
):
    requirements = {"skill_level": level, "module": module, "elite": elite, "level": 64}
    row = stored(
        opers=[{"name": "棘刺", "skill": skill, "requirements": requirements}]
    )["opers"][0]
    assert row["requirements"] == {**requirements, "elite": expected}


@pytest.mark.parametrize("elite,skill_level", [(-1, 0), (0, -1), (-1, -1)])
def test_no_requirement_sentinels_survive_import_and_legacy_execution(
    tmp_path, elite, skill_level
):
    oper = {"name": "芬", "requirements": {"elite": elite, "skill_level": skill_level}}
    assert stored(opers=[oper])["opers"] == [oper]
    payload = raw(opers=[oper])
    key = hashlib.sha256(payload).hexdigest()
    source = library.script_path(key)
    source.write_bytes(payload)
    conf = CopilotConf(scripts=[{"id": key}])
    params = library.build_copilot_params(conf, tmp_path / "run")
    assert params["copilot_list"][0]["filename"] == str(source)
    assert source.read_bytes() == payload


@pytest.mark.parametrize("use_maa", [True, False])
def test_role_resolves_same_name_and_leaves_ambiguous_form_unchanged(tmp_path, use_maa):
    if use_maa:
        path = tmp_path / "maa/resource/battle_data.json"
        path.parent.mkdir(parents=True)
        chars = {
            key: {"name": "阿米娅", "name_en": "Amiya", "profession": role, "rarity": 5}
            for key, role in (
                ("char_1037_amiya3", "MEDIC"),
                ("char_002_amiya", "CASTER"),
            )
        }
        path.write_text(json.dumps({"chars": chars}))
    name = "AMIYA" if use_maa else "阿米娅"
    common = {"name": name, "skill": 3}
    ops = [
        common,
        {**common, "role": "MeDiC"},
        {**common, "role": "CASTER"},
        {**common, "role": "sniper"},
    ]
    rows = stored(groups=[{"name": "替补", "opers": ops}])["groups"][0]["opers"]
    assert rows == [
        common,
        {**ops[1], "skill": 0},
        {**ops[2], "requirements": {"elite": 2}},
        ops[3],
    ]


@pytest.mark.parametrize(
    "alias,core_role",
    [
        ("Guard", "warrior"),
        ("vanguard", "pioneer"),
        ("defender", "tank"),
        ("supporter", "support"),
        ("specialist", "special"),
    ],
)
def test_protocol_role_names_reach_formation_and_actions(tmp_path, alias, core_role):
    path = tmp_path / "maa/resource/battle_data.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "chars": {
                    "char_002_amiya": {
                        "name": "阿米娅",
                        "profession": "CASTER",
                        "rarity": 5,
                    },
                    "char_1001_amiya2": {
                        "name": "阿米娅",
                        "profession": "WARRIOR",
                        "rarity": 5,
                    },
                }
            }
        )
    )
    op = {"name": "阿米娅", "role": alias, "skill": 3}
    action = {"type": "Deploy", "name": "阿米娅", "role": alias, "location": [1, 2]}
    result = stored(opers=[op], actions=[action])
    assert result["opers"] == [
        {**op, "role": core_role, "skill": 0 if core_role == "warrior" else 3}
    ]
    assert result["actions"] == [{**action, "role": core_role}]


@pytest.mark.parametrize("android", [False, True])
def test_new_operator_survives_older_resources_and_uses_updated_cache_at_execution(
    tmp_path, monkeypatch, android
):
    target = tmp_path / "maa"
    path = target / "resource/battle_data.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"chars": {}}')
    monkeypatch.setenv("MOWER_ANDROID", "1" if android else "0")
    shared = tmp_path / "shared"
    monkeypatch.setattr(normalization, "storage_root", lambda target: shared)
    op = {"name": "冻河", "skill": 3, "requirements": {"elite": -1, "skill_level": -1}}
    info = library.store_script(raw(opers=[op]))
    source = library.script_path(info["id"])
    assert json.loads(source.read_bytes())["opers"] == [op]
    cache = (target if android else shared) / "cache/resource/battle_data.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "chars": {
                    "char_4244_tocka": {
                        "name": "冻河",
                        "profession": "SUPPORT",
                        "rarity": 6,
                    }
                }
            }
        )
    )
    directory = tmp_path / "run"
    conf = CopilotConf(scripts=[{"id": info["id"]}])
    params = library.build_copilot_params(conf, directory)
    assert params["copilot_list"][0]["filename"] == str(directory / source.name)
    assert json.loads((directory / source.name).read_bytes())["opers"] == [
        {**op, "requirements": {"elite": 2, "skill_level": -1}}
    ]
    assert json.loads(source.read_bytes())["opers"] == [op]


def test_coordinate_actions_and_click_keep_the_preferred_target_only():
    actions = [
        {
            "type": kind,
            "name": "桃金娘",
            "role": "先锋",
            "location": [1, 2],
            "doc": "说明",
        }
        for kind in (
            "Skill",
            "Retreat",
            "BulletTime",
            "SkillUsage",
            "Deploy",
            "SetUnitLocation",
        )
    ]
    actions.extend(
        [
            {"type": "Click", "rect": [1, 2, 30, 40], "location": [3, 4]},
            {"type": "Click", "location": [5, 6]},
            {"type": "Skill", "name": "桃金娘"},
        ]
    )
    result = stored(actions=actions)["actions"]
    assert result[:4] == [
        {"type": a["type"], "location": [1, 2], "doc": "说明"} for a in actions[:4]
    ]
    assert result[4:6] == actions[4:6]
    assert result[6:] == [{"type": "Click", "rect": [1, 2, 30, 40]}, *actions[7:]]


@pytest.mark.parametrize(
    "fields",
    [
        {"opers": [{"name": "桃金娘", "skill": True}]},
        {"opers": [{"name": "棘刺", "skill": 4}]},
        {"opers": [{"name": "棘刺", "requirements": []}]},
        {"opers": [{"name": "棘刺", "requirements": {"skill_level": "7"}}]},
        {"groups": [{"name": "替补", "opers": [None]}]},
        {"groups": [{"opers": []}]},
        {"actions": [{"type": "Skill", "name": "棘刺", "location": [0]}]},
        {"actions": [{"type": "Click", "rect": [1, 2, 0, 3]}]},
        {"actions": [{"type": "Click"}]},
    ],
)
def test_invalid_nested_fields_are_rejected_before_writing(fields, tmp_path):
    with pytest.raises(ValueError):
        library.store_script(raw(**fields))
    assert not (tmp_path / "library").exists()


def test_existing_file_runs_corrected_with_original_id_and_library_quota(
    tmp_path, monkeypatch
):
    old = raw(opers=[{"name": "棘刺", "skill": 3, "requirements": {"elite": 0}}])
    key = hashlib.sha256(old).hexdigest()
    path = library.script_path(key)
    path.parent.mkdir()
    path.write_bytes(old)
    conf = CopilotConf(scripts=[{"id": key, "is_raid": True}])
    monkeypatch.setattr(library, "MAX_TOTAL_BYTES", len(old))
    assert library.store_script(old)["id"] == key
    directory = tmp_path / "run"
    params = library.build_copilot_params(conf, directory)
    assert params["copilot_list"] == [
        {"filename": str(directory / path.name), "is_raid": True}
    ]
    assert json.loads((directory / path.name).read_bytes())["opers"][0][
        "requirements"
    ] == {"elite": 2}
    assert path.read_bytes() == old
    assert [item["id"] for item in library.list_scripts()] == [key]


def test_invalid_legacy_group_remains_visible_for_removal(tmp_path):
    old = raw(groups=[{"name": "替补", "opers": [None]}])
    key = hashlib.sha256(old).hexdigest()
    path = library.script_path(key)
    path.parent.mkdir()
    path.write_bytes(old)
    assert library.list_scripts()[0]["id"] == key
    with pytest.raises(ValueError, match=r"groups\[0\]\.opers"):
        library.build_copilot_params(
            CopilotConf(scripts=[{"id": key}]), tmp_path / "run"
        )
    assert not (tmp_path / "run").exists()
