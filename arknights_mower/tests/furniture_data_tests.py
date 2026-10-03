"""家具资源保留整套所需数量，与账号是否集齐套装无关。"""

import copy
import json
from pathlib import Path

import pytest

from arknights_mower.utils.furniture_data import (
    FURNITURE_DATA_PATH,
    build_furniture_data,
    furniture_keep_counts,
    normalize_name,
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
    rel = FURNITURE_DATA_PATH
    data = json.loads((root / rel).read_text(encoding="utf-8"))
    counts = furniture_keep_counts(data)
    assert counts["瓷色壁灯"] == 2
    assert counts["柔和顶灯"] == 5
    assert counts["复古吊灯"] == 6
    assert "管道置物架" not in counts
    assert counts[normalize_name("便携TM计算器")] == 1
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


@pytest.mark.parametrize(
    "ocr_name", ["便携TM计算器", "便携ＴＭ计算器", "便携 TM 计算器"]
)
def test_trademark_and_ocr_text_resolve_to_same_furniture(ocr_name):
    assert normalize_name(ocr_name) == normalize_name("便携™计算器")


def test_compatibility_normalization_keeps_ambiguity_check():
    data = build_furniture_data(source())
    data["furnitures"]["chair"]["name"] = "便携™计算器"
    data["furnitures"]["lamp"]["name"] = "便携TM计算器"
    assert normalize_name("便携™计算器") not in furniture_keep_counts(data)


def test_normalization_does_not_remove_distinguishing_name_characters():
    assert normalize_name("简易便椅（左）") != normalize_name("简易便椅（右）")


def test_generation_validates_before_touching_previous_file(tmp_path):
    from arknights_mower.utils.furniture_data import write_furniture_data

    path = tmp_path / "家具.json"
    path.write_bytes(b"previous")
    invalid = source()
    invalid["customData"]["furnitures"]["chair"]["quantity"] = -1
    with pytest.raises(ValueError):
        write_furniture_data(path, invalid)
    assert path.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [path]


def test_generation_writes_utf8_and_keeps_old_file_on_replace_failure(
    tmp_path, monkeypatch
):
    from arknights_mower.utils import update_runtime
    from arknights_mower.utils.furniture_data import write_furniture_data

    path = tmp_path / "家具.json"
    write_furniture_data(path, source())
    previous = path.read_bytes()
    assert json.loads(previous.decode("utf-8")) == build_furniture_data(source())

    def fail(*args):
        raise OSError("simulated locked file")

    monkeypatch.setattr(update_runtime, "replace_with_retry", fail)
    with pytest.raises(OSError):
        write_furniture_data(path, source())
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("复古吊灯", "复古吊扇", True),
        ("便携TM计算器", "便携TM计算器", True),
        ("吊灯", "大吊灯", True),
        ("大吊灯", "吊灯", True),
        ("吊灯", "壁纸", False),
        ("吊灯", "大号吊灯", False),
    ],
)
def test_conservative_name_distance(left, right, expected):
    from arknights_mower.utils.furniture_data import names_one_edit_apart

    assert names_one_edit_apart(left, right) is expected


def test_confusable_resource_names_only_raise_keep_counts():
    from arknights_mower.utils.furniture_data import conservative_keep_counts

    counts = {
        "复古吊灯": 6,
        "复古吊扇": 1,
        "简约高脚椅": 3,
        "简易高脚椅": 2,
        "便携TM计算器": 1,
    }
    protected = conservative_keep_counts(counts)
    assert protected == {**counts, "复古吊扇": 6, "简易高脚椅": 3}
    assert counts["复古吊扇"] == 1
    assert "复古吊" not in protected
