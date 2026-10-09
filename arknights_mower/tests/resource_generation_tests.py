"""Offline regressions for upstream building-skill resource generation."""

import json

import pytest

from auto_get_res_new import Arknights数据处理器


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
