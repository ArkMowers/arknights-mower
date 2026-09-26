import json
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import dorm_skills


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
    relative = "ui/src/pages/basement_skill/skill.json"
    skill_file = tmp_path / relative
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        json.dumps(
            [{"name": "琴柳", "child_skill": [{"des": dorm_skills._SINGLE_RECOVERY}]}]
        )
    )
    monkeypatch.setattr(dorm_skills, "__rootdir__", tmp_path / "arknights_mower")
    lookup = MagicMock(return_value=skill_file if overlay else None)
    monkeypatch.setattr(dorm_skills, "resource_ui_path", lookup)
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


def test_packaged_app_includes_backend_skill_source(monkeypatch):
    import build_assets

    monkeypatch.setattr(build_assets, "ensure_frontend_built", lambda: None)
    datas = build_assets.get_pyinstaller_common_datas()
    assert (
        str(build_assets.PROJECT_ROOT / "ui/src/pages/basement_skill/skill.json"),
        "ui/src/pages/basement_skill",
    ) in datas
