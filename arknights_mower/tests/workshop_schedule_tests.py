"""Workshop schedule regressions."""

from unittest.mock import patch

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    facility,
    item,
    owned,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import config
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.utils.config.plan import PlanModel


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize(
    "room",
    ["central", "meeting", "contact", "train", "gaming_1", "room_1_1", "room_2_2"],
)
def test_all_other_facilities_block_primary_and_replacement_staff(
    backup, replacement, room
):
    slot = facility("Free", ["年"]) if replacement else facility("年", ["Current"])
    plan = (
        {"backup_plans": [{"plan": {room: slot}}]}
        if backup
        else {"plan1": {room: slot}}
    )
    assert workshop.scheduled_operators(PlanModel.model_validate(plan)) == {
        "年": [room]
    }


@pytest.mark.parametrize(
    "room", ["factory", "dormitory_1", "dormitory_2", "dormitory_3", "dormitory_4"]
)
def test_dorms_and_workshop_are_allowed_in_both_plans(room):
    plan = {
        "plan1": {room: facility("年", ["号角"])},
        "backup_plans": [{"plan": {room: facility("九色鹿", ["空爆"])}}],
    }
    assert workshop.scheduled_operators(PlanModel.model_validate(plan)) == {}
    plan["backup_plans"].append({"plan": {"central": facility("年")}})
    assert workshop.scheduled_operators(plan) == {"年": ["central"]}


def test_recommendation_uses_best_unscheduled_operator_and_deer_only_needs_ownership(
    game,
):
    meta, ids = game
    roster = owned(ids, "九色鹿", elite=0, level=1) + owned(ids, "年", "空爆", "号角")
    # Ownership is enough even when no unlocked probability rule is listed for deer.
    meta[ids["九色鹿"]]["groups"] = []
    plan = {
        "plan1": {"dormitory_1": facility("年", ["九色鹿"])},
        "backup_plans": [{"plan": {"central": facility("Free", ["年"])}}],
    }
    result = workshop.recommend_workshop_operators(roster, meta, plan=plan)
    assert set(result["defaults"]["fodder_operators"]) == {"九色鹿", "号角", "空爆"}
    assert result["defaults"]["t5_operators"] == ["空爆"]
    plan["backup_plans"][0]["plan"]["train"] = facility("九色鹿")
    result = workshop.recommend_workshop_operators(roster, meta, plan=plan)
    assert "九色鹿" not in result["defaults"]["fodder_operators"]
    assert result["nine_colored_deer"]["owned"] is True


def test_auto_config_respects_manual_selections_even_when_scheduled(game, monkeypatch):
    meta, ids = game
    available = workshop.available_operators(owned(ids, "号角", "空爆"), meta)
    groups = [("fodder_operators", ["号角", "空爆"], [item("炽合金块")])]
    before = workshop.allocate_workshop_items(groups, available=available)
    assert before[0]["items"] == [item("炽合金块")]
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate(
            {"backup_plans": [{"plan": {"meeting": facility("号角")}}]}
        ),
    )
    after = workshop.allocate_workshop_items(groups, available=available)
    assert after == before
    with patch.object(
        workshop,
        "available_operators",
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX"),
    ):
        result = workshop.allocate_workshop_items(groups)
        assert {entry["operator"] for entry in result} == {"号角", "空爆"}
        assert all(entry["items"] == [item("炽合金块")] for entry in result)


def test_manually_selected_scheduled_deer_keeps_material_and_fodder():
    result = workshop.allocate_workshop_items(
        [("fodder_operators", ["九色鹿"], [item("炽合金块")])],
        available={},
        fodder_items=[item("碳素")],
        plan={"plan1": {"train": facility("九色鹿")}},
    )
    assert result == [
        {
            "operator": "九色鹿",
            "enabled": True,
            "items": [item("碳素"), item("炽合金块")],
        }
    ]
