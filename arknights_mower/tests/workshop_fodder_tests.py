"""Independent Deer fodder: saved limits survive automatic crafting and restore."""

import pytest

from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils import mastery_recommendation as rec
from arknights_mower.utils import workshop_automation as auto
from arknights_mower.utils import workshop_config as state
from arknights_mower.utils.config.conf import WorkshopDeerFodderItem
from arknights_mower.utils.workshop_fodder import deer_fodder_items


def custom_fodder():
    return WorkshopDeerFodderItem(
        item_names=["家具零件_碳"], children_lower_limit=50, self_upper_limit=120
    )


def test_options_are_usable_building_fodder_not_elite_crit_materials(next_skill):
    import server
    from arknights_mower.data import workshop_formula

    client = server.app.test_client()
    response = client.get("/item?kind=deer-fodder")
    assert response.status_code == 200
    assert "碳素组" in response.json
    assert "家具零件_碳" in response.json
    assert all(workshop_formula[name]["tab"] == "基建材料" for name in response.json)
    assert set(response.json) < set(client.get("/item").json)


def test_default_materials_are_retained_and_empty_selection_stays_empty(next_skill):
    assert len(deer_fodder_items()) == 1
    assert deer_fodder_items()[0]["item_names"] == [
        "碳素",
        "碳素组",
        "家具零件_碳素组",
    ]
    config.conf.workshop_deer_fodder = []
    assert deer_fodder_items() == []


def test_custom_fodder_is_used_by_auto_config_and_survives_backup_restore(
    next_skill, monkeypatch
):
    from arknights_mower.utils.config.conf import RIICPart

    config.conf.workshop_settings = [RIICPart.WorkShopSetting(operator="空爆")]
    config.conf.fodder_operators = ["九色鹿"]
    config.conf.workshop_deer_fodder = [custom_fodder()]
    data = rec.get_mastery_recommendations()
    data["operators"][1]["recommendations"][0]["chain_needed_materials"] = [
        {"name": "糖聚块", "count": 2}
    ]
    monkeypatch.setattr(rec, "get_mastery_recommendations", lambda: data)
    for _ in range(2):
        result = auto.update_workshop_config()
        deer = next(
            entry
            for entry in result["workshop_settings"]
            if entry["operator"] == "九色鹿"
        )
        assert custom_fodder().model_dump() in deer["items"]
        assert not any("碳素组" in item["item_names"] for item in deer["items"])
    config.conf.workshop_deer_fodder = [
        custom_fodder().model_copy(update={"self_upper_limit": 240})
    ]
    next_skill.plans.clear()
    auto.update_workshop_config()
    assert config.conf.workshop_settings[0].operator == "空爆"
    assert config.conf.workshop_deer_fodder[0].self_upper_limit == 240


def test_default_config_generator_uses_the_same_independent_fodder(next_skill):
    config.conf.workshop_deer_fodder = [custom_fodder()]
    settings = rec.compute_default_workshop_config(["九色鹿"], [], [])
    assert custom_fodder().model_dump() in settings[0]["items"]


@pytest.mark.parametrize("field", ["children_lower_limit", "self_upper_limit"])
@pytest.mark.parametrize("value", [-1, 1000000])
def test_invalid_fodder_limits_do_not_replace_saved_configuration(
    next_skill, field, value
):
    import server

    config.conf.workshop_deer_fodder = [custom_fodder()]
    payload = config.conf.model_dump()
    payload["workshop_deer_fodder"][0][field] = value
    response = server.app.test_client().post("/conf", json=payload)
    assert response.status_code >= 400
    assert config.conf.workshop_deer_fodder == [custom_fodder()]


def test_invalid_or_removed_recipes_are_not_added_to_generated_fodder(next_skill):
    config.conf.workshop_deer_fodder = [
        WorkshopDeerFodderItem(item_names=["糖聚块", "不存在", "碳素"])
    ]
    assert deer_fodder_items()[0]["item_names"] == ["碳素"]


def test_old_browser_config_save_does_not_reset_independent_fodder(next_skill):
    config.conf.workshop_deer_fodder = [custom_fodder()]
    req = config.conf.model_dump()
    req.pop("workshop_deer_fodder")
    state.save_user_config(req)
    assert config.conf.workshop_deer_fodder == [custom_fodder()]
