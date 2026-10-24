"""材料规划复用真实输入，状态查询仍使用当前心情与任务。"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config, growth, growth_workshop
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils import workshop_automation as auto


@pytest.fixture
def planning(next_skill, monkeypatch):
    auto.clear_workshop_plan_cache()
    goals = []
    monkeypatch.setattr(growth, "load_goals", lambda: goals)
    compute = MagicMock(wraps=growth_workshop.growth_workshop_config)
    monkeypatch.setattr(growth_workshop, "growth_workshop_config", compute)
    stock = {"技巧概要·卷2": 300, "技巧概要·卷3": 0, "龙门币": 100000}
    yield SimpleNamespace(stock=stock, compute=compute, goals=goals)
    auto.clear_workshop_plan_cache()


def calculate(planning, **operators):
    return auto.calculate_workshop_plan(
        config.conf, local_stock=planning.stock, **operators
    )


def quota(result):
    return result.settings[0]["items"][0]["self_upper_limit"]


def test_repeated_plan_reads_reuse_calculation_without_sharing_results(planning):
    first = calculate(planning)
    assert first.recipe == "技巧概要·卷3" and quota(first) == 7
    second = calculate(planning)
    assert second == first and second is not first
    first.settings.clear()
    second.focus["char_name"] = "changed by caller"
    third = calculate(planning)
    assert quota(third) == 7 and third.focus["char_name"] != "changed by caller"
    planning.compute.assert_called_once()


def test_current_inventory_and_plan_order_each_recalculate(planning, next_skill):
    assert quota(calculate(planning)) == 7
    planning.stock["技巧概要·卷3"] = 7
    assert quota(calculate(planning)) == 12
    planning.stock["技巧概要·卷3"] = 0
    next_skill.plans[1]["priority"] = 3
    assert quota(calculate(planning)) == 5
    assert planning.compute.call_count == 3


def test_unsupplied_inventory_is_read_again_before_cache_lookup(planning, monkeypatch):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "get_inventory_counts", lambda: dict(planning.stock))
    assert quota(auto.calculate_workshop_plan(config.conf)) == 7
    planning.stock["技巧概要·卷3"] = 7
    assert quota(auto.calculate_workshop_plan(config.conf)) == 12


def test_changed_box_invalidates_even_with_same_size_and_mtime(planning, next_skill):
    assert quota(calculate(planning)) == 7
    path = next_skill.cultivate
    before = path.stat()
    content = path.read_text("utf-8")
    assert '"level": 0' in content
    path.write_text(content.replace('"level": 0', '"level": 3'), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_size == before.st_size
    result = calculate(planning)
    assert result.settings == [] and result.focus is None
    assert planning.compute.call_count == 2


def test_changed_selection_and_order_invalidate(planning):
    first = calculate(planning)
    changed = calculate(planning, book_operators=["空爆"])
    assert changed.settings != first.settings
    config.conf.growth_crafting_order = ["skill:char_a:0", "skill:char_b:0"]
    assert quota(calculate(planning)) == 5
    assert planning.compute.call_count == 3


@pytest.mark.parametrize(
    "field,value",
    [("workshop_min_bonus", 90), ("workshop_protect_t2_device_rock", True)],
)
def test_saved_material_and_operator_policy_recalculate(planning, field, value):
    calculate(planning)
    setattr(config.conf, field, value)
    calculate(planning)
    assert planning.compute.call_count == 2


def test_resource_reload_recalculates_after_in_place_catalog_refresh(
    planning, monkeypatch
):
    from arknights_mower.utils import resource_pkg

    assert quota(calculate(planning)) == 7
    original = rec.get_skill_data()
    updated = json.loads(json.dumps(original))
    updated["characters"]["char_b"]["skills"][0]["levels"][0]["materials"][0][
        "count"
    ] = 9
    monkeypatch.setattr(rec, "_load_skill_data", lambda: updated)
    callbacks = {
        name: callback
        for name, callback in resource_pkg._reload_callbacks.items()
        if callback in (rec.reload_resource_data, auto.clear_workshop_plan_cache)
    }
    monkeypatch.setattr(resource_pkg, "_reload_callbacks", callbacks)
    resource_pkg.reload_resource_caches()
    assert rec.get_skill_data() is original
    assert quota(calculate(planning)) == 9
    assert planning.compute.call_count == 2


def test_failed_input_read_never_returns_previous_success(planning, next_skill):
    calculate(planning)
    next_skill.cultivate.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        calculate(planning)
    next_skill.cultivate.unlink()
    with pytest.raises(ValueError, match="读取仓库"):
        calculate(planning)


def test_failed_calculation_can_retry_same_inputs(planning):
    planning.compute.side_effect = ValueError("temporary failure")
    with pytest.raises(ValueError, match="temporary failure"):
        calculate(planning)
    planning.compute.side_effect = None
    assert quota(calculate(planning)) == 7
    assert planning.compute.call_count == 2


def test_goal_edits_and_module_release_time_are_observed(
    planning, next_skill, monkeypatch
):
    source = rec.get_skill_data()
    source["growth"] = {
        "characters": {
            "char_b": {
                "phases": [{"max_level": 50}, {"max_level": 80}, {"max_level": 90}],
                "modules": [
                    {
                        "id": "module_b",
                        "elite": 2,
                        "level": 1,
                        "release_at": 100,
                        "materials": [{"id": "3303", "count": 2}],
                    }
                ],
            }
        }
    }
    monkeypatch.setattr(auto, "time", lambda: 101)
    monkeypatch.setattr(growth, "time", lambda: 101)
    assert quota(calculate(planning)) == 7
    next_skill.plans.clear()
    planning.goals.append({"char_id": "char_b", "module_id": "module_b"})
    assert quota(calculate(planning)) == 2
    monkeypatch.setattr(auto, "time", lambda: 99)
    monkeypatch.setattr(growth, "time", lambda: 99)
    with pytest.raises(ValueError):
        calculate(planning)
    monkeypatch.setattr(auto, "time", lambda: 100)
    monkeypatch.setattr(growth, "time", lambda: 100)
    assert quota(calculate(planning)) == 2


def test_file_timestamp_refresh_and_resource_replacement_recalculate(
    planning, next_skill, monkeypatch
):
    assert quota(calculate(planning)) == 7
    path = next_skill.cultivate
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    assert quota(calculate(planning)) == 7
    assert planning.compute.call_count == 2

    source = rec.get_skill_data()
    updated = json.loads(json.dumps(source))
    updated["characters"]["char_b"]["skills"][0]["levels"][0]["materials"][0][
        "count"
    ] = 9
    monkeypatch.setattr(rec, "_load_skill_data", lambda: updated)
    # 即使规划缓存的刷新回调先完成，随后替换的资源子表也使旧结果失效。
    auto.clear_workshop_plan_cache()
    calculate(planning)
    rec.reload_resource_data()
    assert quota(calculate(planning)) == 9
