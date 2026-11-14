"""Offline regressions for upstream building-skill resource generation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from auto_get_res_new import Arknights数据处理器


def test_mastery_generation_includes_patch_forms_in_training_metadata(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    processor = Arknights数据处理器.__new__(Arknights数据处理器)
    forms = {
        "char_002_amiya": ("CASTER", "corecaster", "精神爆发"),
        "char_1001_amiya2": ("WARRIOR", "artsfghter", "影霄·绝影"),
        "char_1037_amiya3": ("MEDIC", "incantationmedic", "哀恸共情"),
    }
    characters = {
        cid: {
            "name": "阿米娅",
            "profession": profession,
            "subProfessionId": branch,
            "phases": [],
            "skills": [
                {
                    "skillId": cid,
                    "levelUpCostCond": [{"levelUpCost": [], "lvlUpTime": 28800}],
                }
            ],
        }
        for cid, (profession, branch, _) in forms.items()
    }
    processor.干员表 = {"char_002_amiya": characters.pop("char_002_amiya")}
    processor.干员形态表 = {"patchChars": characters}
    processor.基建表 = {"buffs": {}, "chars": {}}
    processor.物品表 = {"items": {}}
    processor.技能表 = {
        cid: {"levels": [{"name": skill}]} for cid, (_, _, skill) in forms.items()
    }
    processor.游戏变量 = {
        "characterExpMap": [],
        "characterUpgradeCostMap": [],
        "evolveGoldCost": [],
    }
    monkeypatch.setattr(processor, "加载json", lambda _: {})

    processor.提取专精数据()

    data = json.loads((tmp_path / "arknights_mower/data/skill_data.json").read_text())
    for cid, (profession, branch, skill) in forms.items():
        assert data["characters"][cid]["skills"][0]["name"] == skill
        assert data["training"]["operators"][cid] == {
            "name": "阿米娅",
            "profession": profession,
            "subProfessionId": branch,
            "groupId": None,
            "nationId": None,
            "teamId": None,
            "groups": [],
        }


@pytest.mark.parametrize(
    ("room", "expected"),
    [("RECYCLE", "回收站"), ("TRAINING", "训练室"), ("FUTURE_ROOM", "FUTURE_ROOM")],
)
@pytest.mark.parametrize("phase", [2, "PHASE_2"])
def test_building_skill_generation_preserves_new_and_unknown_facilities(
    tmp_path, monkeypatch, room, expected, phase
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "ui/src/pages/basement_skill/skill.json"
    output.parent.mkdir(parents=True)
    processor = Arknights数据处理器.__new__(Arknights数据处理器)
    processor.所有buff = []
    processor.干员表 = {"char_test": {"name": "测试干员"}}
    processor.基建表 = {
        "buffs": {
            "test_buff": {
                "buffName": "测试技能",
                "description": "使用<$recycle.power>回收材料",
                "roomType": room,
                "buffCategory": "OUTPUT",
                "skillIcon": "test_icon",
                "buffColor": "#FFFFFF",
                "textColor": "#000000",
            }
        },
        "chars": {
            "char_test": {
                "buffChar": [
                    {
                        "buffData": [
                            {
                                "buffId": "test_buff",
                                "cond": {"phase": phase, "level": 1},
                            }
                        ]
                    }
                ]
            }
        },
    }
    processor.获得干员基建描述()
    records = json.loads(output.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["name"] == "测试干员"
    assert records[0]["span"] == 1
    skill = records[0]["child_skill"][0]
    assert skill["roomType"] == expected
    assert skill["phase_level"] == "精2 1级"
    assert skill["skillname"] == "测试技能"
    assert skill["skillIcon"] == "test_icon"
    assert skill["buffer_des"] == ["recycle_power"]
    assert processor.所有buff == ["recycle_power"]


def test_metadata_generator_import_does_not_require_skimage():
    script = """
import importlib.abc
import sys

class NoSkimage(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] == "skimage":
            raise ModuleNotFoundError("skimage is absent from runtime dependencies", name=fullname)

sys.meta_path.insert(0, NoSkimage())
from auto_get_res_new import Arknights数据处理器
assert callable(Arknights数据处理器.获得干员基建描述)
assert "skimage" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("broken", [False, True])
def test_avatar_failure_blocks_metadata_publication(tmp_path, monkeypatch, broken):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ui/public/avatar").mkdir(parents=True)
    (tmp_path / "arknights_mower/data").mkdir(parents=True)
    source = tmp_path / "ArknightsGameResource/avatar/char_new.png"
    if broken:
        source.parent.mkdir(parents=True)
        source.write_bytes(b"invalid PNG")
    # A previous build's image cannot conceal an unreadable current source.
    (tmp_path / "ui/public/avatar/旅骨.webp").write_bytes(b"old-image")
    processor = Arknights数据处理器.__new__(Arknights数据处理器)
    processor.干员表 = {
        "char_new": {
            "name": "旅骨",
            "profession": "MEDIC",
            "itemObtainApproach": "GACHA",
        }
    }
    with pytest.raises(RuntimeError, match="旅骨.*char_new"):
        processor.添加干员()
    assert not (tmp_path / "arknights_mower/data/agent.json").exists()


def test_avatar_generation_preserves_complete_operator_metadata(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.chdir(tmp_path)
    (tmp_path / "ui/public/avatar").mkdir(parents=True)
    (tmp_path / "arknights_mower/data").mkdir(parents=True)
    source = tmp_path / "ArknightsGameResource/avatar/char_new.png"
    source.parent.mkdir(parents=True)
    Image.new("RGBA", (180, 180), (255, 0, 0, 255)).save(source)
    processor = Arknights数据处理器.__new__(Arknights数据处理器)
    processor.干员表 = {
        "char_new": {
            "name": "旅骨",
            "profession": "MEDIC",
            "itemObtainApproach": "GACHA",
        },
        "npc_skip": {"itemObtainApproach": None},
    }
    processor.添加干员()
    with Image.open(tmp_path / "ui/public/avatar/旅骨.webp") as avatar:
        assert avatar.format == "WEBP"
        assert avatar.size == (96, 96)
        avatar.load()
    assert json.loads((tmp_path / "arknights_mower/data/agent.json").read_text()) == [
        "旅骨"
    ]
    assert json.loads(
        (tmp_path / "arknights_mower/data/agent_profession.json").read_text()
    ) == {"旅骨": "MEDIC"}
