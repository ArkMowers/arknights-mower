"""家具资源保留整套所需数量，与账号是否集齐套装无关。"""

import copy
import json
from pathlib import Path

import pytest

from arknights_mower.utils.furniture_data import (
    build_furniture_data,
    furniture_keep_counts,
)
from arknights_mower.utils.res_version import (
    RES_PACKAGE_DATA,
    content_hash,
    package_file_paths,
)


def source():
    return {
        "customData": {
            "furnitures": {
                "chair": {
                    "name": "椅子",
                    "themeId": "room",
                    "quantity": 2,
                    "canBeDestroy": True,
                },
                "lamp": {
                    "name": "吊灯",
                    "themeId": "room",
                    "quantity": 6,
                    "canBeDestroy": True,
                },
                "unknown": {
                    "name": "未知数量",
                    "themeId": "",
                    "quantity": 0,
                    "canBeDestroy": True,
                },
                "locked": {
                    "name": "不可分解",
                    "themeId": "",
                    "quantity": 1,
                    "canBeDestroy": False,
                },
            },
            "themes": {
                "room": {
                    "name": "房间",
                    "quickSetup": [{"furnitureId": "chair"}] * 4
                    + [{"furnitureId": "lamp"}],
                }
            },
        }
    }


def test_keep_larger_of_quantity_and_set_layout_even_with_incomplete_inventory():
    data = build_furniture_data(source())
    assert data["themes"]["room"]["counts"] == {"chair": 4, "lamp": 1}
    assert furniture_keep_counts(data) == {"椅子": 4, "吊灯": 6}


def test_ambiguous_names_are_never_auto_dismantled():
    data = build_furniture_data(source())
    data["furnitures"]["copy"] = {**data["furnitures"]["chair"], "name": "椅 子"}
    assert "椅子" not in furniture_keep_counts(data)


def test_shared_furniture_uses_largest_theme_requirement():
    data = build_furniture_data(source())
    data["themes"]["other"] = {"name": "另一主题", "counts": {"chair": 5}}
    assert furniture_keep_counts(data)["椅子"] == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", -1),
        ("quantity", True),
        ("quantity", "2"),
        ("themeId", "missing"),
        ("canBeDestroy", 1),
        ("name", " "),
    ],
)
def test_invalid_metadata_is_rejected(field, value):
    data = build_furniture_data(source())
    data["furnitures"]["chair"][field] = value
    with pytest.raises(ValueError):
        furniture_keep_counts(data)


def test_missing_theme_member_is_rejected():
    data = build_furniture_data(source())
    data["themes"]["room"]["counts"]["missing"] = 2
    with pytest.raises(ValueError):
        furniture_keep_counts(data)


def test_bundled_data_contains_multi_piece_sets_and_is_hashed(tmp_path):
    root = Path(__file__).resolve().parents[2]
    rel = "arknights_mower/data/furniture.json"
    data = json.loads((root / rel).read_text())
    counts = furniture_keep_counts(data)
    assert counts["瓷色壁灯"] == 2
    assert counts["柔和顶灯"] == 5
    assert counts["复古吊灯"] == 6
    assert "管道置物架" not in counts
    assert rel in RES_PACKAGE_DATA
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps(data))
    paths = package_file_paths(tmp_path)
    before = content_hash(tmp_path, paths)
    changed = copy.deepcopy(data)
    changed["furnitures"][next(iter(changed["furnitures"]))]["quantity"] = 100
    dest.write_text(json.dumps(changed))
    assert content_hash(tmp_path, paths) != before
