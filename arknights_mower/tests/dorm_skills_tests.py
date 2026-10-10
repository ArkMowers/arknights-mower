import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import dorm_skills
from arknights_mower.utils.res_version import (
    BUILDING_SKILL_DATA,
    BUILDING_SKILL_PACKAGE_PATH,
)


@pytest.fixture(autouse=True)
def reset_cache():
    dorm_skills.clear_dorm_skill_cache()
    yield
    dorm_skills.clear_dorm_skill_cache()


def test_builtin_descriptions_classify_single_recovery():
    for name in ("琴柳", "闪灵", "蜜莓", "Lancet-2"):
        assert dorm_skills.is_single_recovery_manager(name)
    for name in ("杜林", "菲亚梅塔", "红", "不存在的干员"):
        assert not dorm_skills.is_single_recovery_manager(name)


def test_matches_rich_text_and_only_requested_agents(monkeypatch):
    unread = MagicMock()
    unread.get.side_effect = AssertionError("不应匹配未配置干员的描述")
    monkeypatch.setattr(
        dorm_skills,
        "_skill_index",
        lambda: {
            "琴柳": [
                {
                    "des": "进驻宿舍时，使该宿舍内除自身以外<@cc.vup>心情未满</>的某个干员每小时恢复<@cc.vup>+0.7</>"
                }
            ],
            "杜林": [{"des": "进驻宿舍时，使该宿舍内所有干员的心情每小时恢复+0.2"}],
            "未配置": [unread],
        },
    )
    assert dorm_skills.is_single_recovery_manager("琴柳")
    assert not dorm_skills.is_single_recovery_manager("杜林")
    assert not dorm_skills.is_single_recovery_manager("缺失")


@pytest.mark.parametrize("overlay", [False, True])
def test_skill_file_loaded_once_until_resource_reload(tmp_path, monkeypatch, overlay):
    relative = BUILDING_SKILL_PACKAGE_PATH if overlay else BUILDING_SKILL_DATA
    skill_file = tmp_path / relative
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        json.dumps(
            [{"name": "琴柳", "child_skill": [{"des": dorm_skills._SINGLE_RECOVERY}]}]
        )
    )
    lookup = MagicMock(return_value=skill_file)
    monkeypatch.setattr(dorm_skills, "resource_pkg_path", lookup)
    assert dorm_skills.is_single_recovery_manager("琴柳")
    # 文件随后不可读也不影响已加载版本，不重复 I/O 或文本匹配。
    skill_file.unlink()
    for _ in range(10):
        assert dorm_skills.is_single_recovery_manager("琴柳")
        assert not dorm_skills.is_single_recovery_manager("杜林")
    assert lookup.call_count == 1
    skill_file.write_text("[]")
    dorm_skills.clear_dorm_skill_cache()
    assert not dorm_skills.is_single_recovery_manager("琴柳")
    assert lookup.call_count == 2


def test_packaged_app_includes_shared_skill_data_without_frontend_sources(monkeypatch):
    import build_assets

    monkeypatch.setattr(build_assets, "ensure_frontend_built", lambda: None)
    datas = build_assets.get_pyinstaller_common_datas()
    assert (
        str(build_assets.PROJECT_ROOT / BUILDING_SKILL_DATA),
        "arknights_mower/data",
    ) in datas
    assert not any("ui/src" in source for source, _ in datas)


@pytest.mark.parametrize("name", ["杜林", "夜莺", "赫拉格", "冰酿"])
def test_builtin_group_and_shared_recovery_managers(name):
    assert dorm_skills.is_group_recovery_manager(name)


@pytest.mark.parametrize("name", ["闪灵", "安赛尔", "和弦", "菲亚梅塔", "不存在的干员"])
def test_single_self_and_charge_recovery_do_not_qualify_as_group(name):
    assert not dorm_skills.is_group_recovery_manager(name)


def test_group_recovery_requires_dorm_skill_and_matches_rich_text(monkeypatch):
    unread = MagicMock()
    unread.get.side_effect = AssertionError("不应匹配未配置干员的描述")
    monkeypatch.setattr(
        dorm_skills,
        "_skill_index",
        lambda: {
            "群回": [
                {
                    "roomType": "宿舍",
                    "des": "除自身以外<@cc.vup>所有干员的心情</>每小时恢复+0.2",
                }
            ],
            "分摊": [
                {
                    "roomType": "宿舍",
                    "des": "使心情未满的<@cc.kw>宿舍成员</>，平均分配到总计每小时心情恢复+0.8的加成",
                }
            ],
            "中枢": [{"roomType": "中枢", "des": "所有干员的心情每小时恢复+0.05"}],
            "未知设施": [{"des": "所有干员的心情每小时恢复+0.2"}],
            "未配置": [unread],
        },
    )
    assert dorm_skills.is_group_recovery_manager("群回")
    assert dorm_skills.is_group_recovery_manager("分摊")
    assert not dorm_skills.is_group_recovery_manager("中枢")
    assert not dorm_skills.is_group_recovery_manager("未知设施")
    assert not dorm_skills.is_group_recovery_manager("缺失")


@pytest.mark.parametrize("overlay", [False, True])
def test_group_and_single_classification_share_file_cache_and_reload(
    tmp_path, monkeypatch, overlay
):
    relative = BUILDING_SKILL_PACKAGE_PATH if overlay else BUILDING_SKILL_DATA
    skill_file = tmp_path / relative
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        json.dumps(
            [
                {
                    "name": "群回",
                    "child_skill": [
                        {"roomType": "宿舍", "des": "所有干员的心情每小时恢复+0.2"}
                    ],
                },
                {
                    "name": "单回",
                    "child_skill": [
                        {"roomType": "宿舍", "des": dorm_skills._SINGLE_RECOVERY}
                    ],
                },
            ]
        )
    )
    lookup = MagicMock(return_value=skill_file)
    monkeypatch.setattr(dorm_skills, "resource_pkg_path", lookup)
    assert dorm_skills.is_group_recovery_manager("群回")
    assert dorm_skills.is_single_recovery_manager("单回")
    skill_file.unlink()
    for _ in range(10):
        assert dorm_skills.is_group_recovery_manager("群回")
        assert dorm_skills.is_single_recovery_manager("单回")
        assert not dorm_skills.is_group_recovery_manager("缺失")
    assert lookup.call_count == 1
    skill_file.write_text("[]")
    dorm_skills.clear_dorm_skill_cache()
    assert not dorm_skills.is_group_recovery_manager("群回")
    assert not dorm_skills.is_single_recovery_manager("单回")
    assert lookup.call_count == 2


@pytest.mark.parametrize(
    "name",
    [
        "罗德岛隐秘队",
        "聆音",
        "新约能天使",
        "小满",
        "寒檀",
        "隐现",
        "车尔尼",
        "蜜莓",
        "琴柳",
        "深靛",
        "杰克",
        "酸糖",
        "特米米",
        "波登可",
        "断罪者",
        "黑",
        "闪灵",
        "暴行",
        "初雪",
        "崖心",
        "临光",
        "古米",
        "慕斯",
        "流星",
        "末药",
        "泡普卡",
        "安赛尔",
        "卡缇",
        "米格鲁",
        "芙蓉",
        "Lancet-2",
    ],
)
def test_current_single_recovery_operators_are_recognized(name):
    assert dorm_skills.is_single_recovery_manager(name)


def test_indigo_description_without_self_exclusion_matches(monkeypatch):
    monkeypatch.setattr(
        dorm_skills,
        "_skill_index",
        lambda: {
            "深靛": [
                {
                    "des": "进驻宿舍时，使该宿舍内<@cc.vup>心情未满</>的某个干员每小时恢复+0.55"
                }
            ],
        },
    )
    assert dorm_skills.is_single_recovery_manager("深靛")
