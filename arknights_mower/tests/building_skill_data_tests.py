"""Shared building-skill data remains independent of the WebUI build tree."""

import json
from types import SimpleNamespace

from arknights_mower.utils import building_skills, dorm_skills, resource_pkg
from arknights_mower.utils.building_skill_data import write_building_skill_data
from arknights_mower.utils.res_version import (
    BUILDING_SKILL_DATA,
    BUILDING_SKILL_PACKAGE_PATH,
    content_hash,
    package_file_paths,
)


def test_generation_exports_identical_legacy_resource_entry(tmp_path):
    catalog = [{"name": "琴柳", "child_skill": []}]
    write_building_skill_data(catalog, tmp_path)
    source = tmp_path / BUILDING_SKILL_DATA
    exported = tmp_path / BUILDING_SKILL_PACKAGE_PATH
    assert json.loads(source.read_text("utf-8")) == catalog
    assert source.read_bytes() == exported.read_bytes()
    paths = package_file_paths(tmp_path)
    assert exported.relative_to(tmp_path) in paths
    assert source.relative_to(tmp_path) not in paths
    before = content_hash(tmp_path, paths)
    write_building_skill_data([], tmp_path)
    assert content_hash(tmp_path, package_file_paths(tmp_path)) != before


def test_both_backend_consumers_work_without_any_frontend_files(tmp_path, monkeypatch):
    source = tmp_path / BUILDING_SKILL_DATA
    source.parent.mkdir(parents=True)
    skills = [{"des": dorm_skills._SINGLE_RECOVERY}]
    source.write_text(json.dumps([{"name": "琴柳", "child_skill": skills}]))
    monkeypatch.setattr(resource_pkg, "__rootdir__", source.parent.parent)
    monkeypatch.setattr(resource_pkg, "_selection", lambda: SimpleNamespace(root=None))
    monkeypatch.setattr(
        resource_pkg,
        "_reload_callbacks",
        {
            "dorm": dorm_skills.clear_dorm_skill_cache,
            "building": building_skills.clear_building_skills,
        },
    )
    resource_pkg.reload_resource_caches()
    try:
        assert not (tmp_path / "ui").exists()
        assert dorm_skills.is_single_recovery_manager("琴柳")
        assert building_skills.skill_index() == {"琴柳": skills}
        source.write_text("[]")
        resource_pkg.reload_resource_caches()
        assert not dorm_skills.is_single_recovery_manager("琴柳")
        assert building_skills.skill_index() == {}
    finally:
        resource_pkg.reload_resource_caches()
