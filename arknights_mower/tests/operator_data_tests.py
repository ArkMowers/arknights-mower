"""Shared game profiles preserve resource selection and existing operator views."""

import json
import shutil
from copy import deepcopy
from types import SimpleNamespace

import pytest

from arknights_mower import data
from arknights_mower.utils import resource_pkg
from arknights_mower.utils.operator_data import (
    OPERATOR_CATALOG_DATA,
    compile_operator_catalog,
    operator_views,
    write_operator_catalog,
)
from arknights_mower.utils.res_version import is_package_file, package_file_paths
from auto_get_res_new import Arknights数据处理器


def game_tables():
    characters = {
        "char_one": {
            "name": "测试干员",
            "rarity": "TIER_6",
            "profession": "WARRIOR",
            "subProfessionId": "lord",
            "itemObtainApproach": "GACHA",
            "isSpChar": True,
        },
        "char_two": {
            "name": "短名",
            "rarity": 0,
            "profession": "MEDIC",
            "itemObtainApproach": "RECRUIT",
        },
        "npc_skip": {"name": "非干员", "itemObtainApproach": "GACHA"},
        "char_unavailable": {"name": "不可获取", "isNotObtainable": True},
    }
    building = {
        "buffs": {
            "first": {
                "buffName": "基础技能",
                "description": "效率<@cc.vup>+10%</>",
                "roomType": "FUTURE_ROOM",
                "skillIcon": "first_icon",
            },
            "last": {
                "buffName": "升级技能",
                "description": "效率<@cc.vup>+20%</>",
                "roomType": "FUTURE_ROOM",
                "skillIcon": "last_icon",
            },
        },
        "chars": {
            "char_one": {
                "buffChar": [
                    {
                        "buffData": [
                            {"buffId": "first", "cond": {"phase": 0, "level": 1}},
                            {
                                "buffId": "last",
                                "cond": {"phase": "PHASE_2", "level": 30},
                            },
                        ]
                    }
                ]
            }
        },
    }
    return characters, building


def test_generator_builds_one_catalog_and_matching_legacy_exports(
    tmp_path, monkeypatch
):
    from PIL import Image

    monkeypatch.chdir(tmp_path)
    characters, building = game_tables()
    characters.pop("npc_skip")
    characters["char_unavailable"]["itemObtainApproach"] = None
    for char_id in ("char_one", "char_two"):
        path = tmp_path / f"ArknightsGameResource/avatar/{char_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (96, 96), "red").save(path)
    (tmp_path / "ui/public/avatar").mkdir(parents=True)
    version = tmp_path / "ArknightsGameResource/version"
    version.write_text("confirmed-game-snapshot\n", encoding="utf-8")
    processor = Arknights数据处理器.__new__(Arknights数据处理器)
    processor.干员表, processor.基建表 = characters, building
    processor.添加干员()

    catalog = json.loads((tmp_path / OPERATOR_CATALOG_DATA).read_text("utf-8"))
    assert catalog["sourceVersion"] == "confirmed-game-snapshot"
    assert catalog["operatorCount"] == 2
    assert catalog["skillCount"] == 1
    assert catalog["skillStageCount"] == 2
    operator = catalog["operators"][0]
    assert operator["rarity"] == 6
    assert operator["isAlter"] is True
    assert "skills" not in operator
    assert operator["skillSlots"][0] == [
        {
            "buffId": "first",
            "name": "基础技能",
            "roomType": "FUTURE_ROOM",
            "skillIcon": "first_icon",
            "description": "效率+10%",
            "unlockPhase": 0,
            "unlockLevel": 1,
        },
        {
            "buffId": "last",
            "name": "升级技能",
            "roomType": "FUTURE_ROOM",
            "skillIcon": "last_icon",
            "description": "效率+20%",
            "unlockPhase": 2,
            "unlockLevel": 30,
        },
    ]
    assert json.loads(
        (tmp_path / "arknights_mower/data/agent.json").read_text("utf-8")
    ) == ["短名", "测试干员"]
    assert json.loads(
        (tmp_path / "arknights_mower/data/agent_profession.json").read_text("utf-8")
    ) == {"测试干员": "WARRIOR", "短名": "MEDIC"}


def test_catalog_order_preserves_existing_calculator_order_and_appends_new_operators():
    characters, building = game_tables()
    catalog = compile_operator_catalog(
        characters, building, "snapshot", order=["char_two"]
    )
    assert [operator["charId"] for operator in catalog["operators"]] == [
        "char_two",
        "char_one",
    ]
    assert operator_views(catalog) == (
        ["短名", "测试干员"],
        {"测试干员": "WARRIOR", "短名": "MEDIC"},
    )


def test_generated_slots_order_upgrades_by_unlock_condition():
    characters, building = game_tables()
    building["chars"]["char_one"]["buffChar"][0]["buffData"].reverse()
    catalog = compile_operator_catalog(characters, building, "snapshot")
    assert [skill["buffId"] for skill in catalog["operators"][0]["skillSlots"][0]] == [
        "first",
        "last",
    ]


def test_shared_catalog_stays_out_of_legacy_resource_archives(tmp_path):
    catalog = compile_operator_catalog(*game_tables(), "snapshot")
    write_operator_catalog(catalog, tmp_path)
    paths = {path.as_posix() for path in package_file_paths(tmp_path)}
    assert paths == {
        "arknights_mower/data/agent.json",
        "arknights_mower/data/agent_profession.json",
    }
    assert not is_package_file(OPERATOR_CATALOG_DATA)


def test_selected_legacy_package_does_not_borrow_bundled_catalog(tmp_path, monkeypatch):
    selected = tmp_path / "selected"
    folder = selected / "arknights_mower/data"
    folder.mkdir(parents=True)
    (folder / "agent.json").write_text('["旧干员"]', encoding="utf-8")
    (folder / "agent_profession.json").write_text(
        '{"旧干员":"MEDIC"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        resource_pkg, "_selection", lambda: SimpleNamespace(root=selected)
    )
    assert data._agent_views() == (["旧干员"], {"旧干员": "MEDIC"})
    stray = folder / "riic/operators.json"
    stray.parent.mkdir()
    stray.write_text('{"schemaVersion":99}', encoding="utf-8")
    assert data._agent_views() == (["旧干员"], {"旧干员": "MEDIC"})


def test_bundled_catalog_supplies_profiles_and_invalid_data_does_not_use_exports(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(resource_pkg, "_selection", lambda: SimpleNamespace(root=None))
    monkeypatch.setattr(resource_pkg, "__rootdir__", tmp_path / "arknights_mower")
    catalog = compile_operator_catalog(*game_tables(), "snapshot")
    write_operator_catalog(catalog, tmp_path)
    folder = tmp_path / "arknights_mower/data"
    (folder / "agent.json").write_text('["旧导出"]', encoding="utf-8")
    assert data._agent_views() == (
        ["短名", "测试干员"],
        {"测试干员": "WARRIOR", "短名": "MEDIC"},
    )

    (tmp_path / OPERATOR_CATALOG_DATA).write_text(
        '{"schemaVersion":99}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="共享干员目录"):
        data._agent_views()


def test_catalog_reload_updates_existing_references_and_rejects_invalid_data(
    tmp_path, monkeypatch
):
    catalog = compile_operator_catalog(*game_tables(), "snapshot")
    write_operator_catalog(catalog, tmp_path)
    monkeypatch.setattr(resource_pkg, "_selection", lambda: SimpleNamespace(root=None))
    monkeypatch.setattr(resource_pkg, "__rootdir__", tmp_path / "arknights_mower")
    original = {
        name: deepcopy(getattr(data, name))
        for name in (
            "_stage_data_base",
            "agent_list",
            "agent_profession",
            "workshop_formula",
            "stage_order",
            "recruit_agent",
            "recruit_result",
            "key_mapping",
            "recruit_tag",
            "agent_with_tags",
            "result_template_list",
        )
    }
    names, professions = data.agent_list, data.agent_profession
    monkeypatch.setattr(
        data,
        "_read_resource_json",
        lambda name, expected: [] if expected is list else {},
    )
    try:
        data.reload_resource_data()
        assert data.agent_list is names
        assert data.agent_profession is professions
        assert names == ["短名", "测试干员"]
        assert professions == {"测试干员": "WARRIOR", "短名": "MEDIC"}
        (tmp_path / OPERATOR_CATALOG_DATA).write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="共享干员目录"):
            data.reload_resource_data()
        assert names == ["短名", "测试干员"]
    finally:
        for name, value in original.items():
            target = getattr(data, name)
            if isinstance(target, list):
                target[:] = value
            else:
                target.clear()
                target.update(value)


@pytest.mark.parametrize(
    ("name", "invalid"),
    [("agent.json", {"错误姓名": "WARRIOR"}), ("agent_profession.json", [])],
)
def test_external_profile_type_error_preserves_loaded_resource_data(
    tmp_path, monkeypatch, name, invalid
):
    selected = tmp_path / "selected"
    folder = selected / "arknights_mower/data"
    folder.mkdir(parents=True)
    for source in data._data_path("agent.json").parent.glob("*.json"):
        shutil.copyfile(source, folder / source.name)
    (folder / name).write_text(json.dumps(invalid), encoding="utf-8")
    containers = {
        name: getattr(data, name)
        for name in (
            "_stage_data_base",
            "agent_list",
            "agent_profession",
            "workshop_formula",
            "stage_order",
            "recruit_agent",
            "recruit_result",
            "key_mapping",
            "recruit_tag",
            "agent_with_tags",
            "result_template_list",
        )
    }
    original = deepcopy(containers)
    monkeypatch.setattr(
        resource_pkg, "_selection", lambda: SimpleNamespace(root=selected)
    )
    try:
        with pytest.raises(ValueError, match=f"资源数据 {name} 类型错误"):
            data.reload_resource_data()
        for key, container in containers.items():
            assert getattr(data, key) is container
            assert container == original[key]
    finally:
        for key, container in containers.items():
            if isinstance(container, list):
                container[:] = original[key]
            else:
                container.clear()
                container.update(original[key])
