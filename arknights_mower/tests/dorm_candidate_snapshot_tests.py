from collections import Counter
from datetime import datetime, timedelta

import pytest

from arknights_mower.tests.dorm_release_tests import op_data as op_data
from arknights_mower.utils import dorm_candidates as candidates
from arknights_mower.utils import resting_priority
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Room


def test_candidate_scan_shares_replacement_union_and_unknown_mood_queries(
    op_data, monkeypatch
):
    data = op_data
    now = datetime.now()
    data.plan["meeting"][0].group_bindings = [{"group": "其他", "replacement": ["年"]}]
    data.plan["dormitory_1"][0] = Room("菲亚梅塔", "", ["九色鹿"])
    monkeypatch.setattr(
        candidates, "unregistered_idle_candidates", lambda *args: ["年", "九色鹿"]
    )
    data.dorm_mood_estimates = {name: (8, now) for name in ("年", "九色鹿")}
    mood_calls = Counter()
    tier_calls = Counter()
    original_mood = candidates.dorm_candidate_mood
    original_tier = resting_priority.resting_tier
    snapshots = []

    def count_mood(data, name, *args, **kwargs):
        mood_calls[name] += 1
        return original_mood(data, name, *args, **kwargs)

    def inspect_tier(data, name, now=None, *, replacement_names=None):
        assert replacement_names is not None
        tier_calls[name] += 1
        snapshots.append(replacement_names)
        return original_tier(data, name, now, replacement_names=replacement_names)

    monkeypatch.setattr(candidates, "dorm_candidate_mood", count_mood)
    monkeypatch.setattr(candidates, "resting_tier", inspect_tier)
    monkeypatch.setattr(resting_priority, "resting_tier", inspect_tier)

    result = candidates.dorm_candidates(data, now=now)

    assert result.estimated_recovering == ["年", "九色鹿"]
    assert all(names is snapshots[0] for names in snapshots)
    assert snapshots[0] == {"红", "年"}
    assert mood_calls["年"] == mood_calls["九色鹿"] == 1
    assert tier_calls["年"] == tier_calls["九色鹿"] == 1


def test_next_candidate_scan_reads_changed_plan_priority_cards_and_positions(
    op_data, monkeypatch
):
    data = op_data
    now = datetime.now()
    for name in ("年", "九色鹿"):
        data.add(Operator(name, ""))
        data.operators[name].time_stamp = None
        data.dorm_mood_estimates[name] = (8, now)
    monkeypatch.setattr(candidates, "unregistered_idle_candidates", lambda *args: [])
    data.plan["meeting"][0].replacement.append("年")

    first = candidates.dorm_candidates(data, now=now)
    assert first.estimated_recovering == ["年", "九色鹿"]

    data.plan["meeting"][0].replacement.remove("年")
    data.config.ope_resting_priority.append("九色鹿")
    second = candidates.dorm_candidates(data, now=now)
    assert second.estimated_recovering == ["九色鹿", "年"]

    data.dorm_mood_estimates["九色鹿"] = (24, now)
    third = candidates.dorm_candidates(data, now=now)
    assert third.estimated_recovering == ["年"]
    assert "九色鹿" in third.filling
    assert "九色鹿" not in third.unknown

    data.operators["年"].current_room, data.operators["年"].current_index = "meeting", 0
    fourth = candidates.dorm_candidates(data, now=now + timedelta(hours=1))
    assert fourth.estimated_recovering == []
    assert "年" not in fourth.filling
    assert "九色鹿" in fourth.unknown


@pytest.mark.parametrize("tier", list(resting_priority.RestingTier))
def test_optional_replacement_snapshot_preserves_tier_precedence(op_data, tier):
    from arknights_mower.tests.resting_priority_tests import set_tier

    set_tier(op_data, "年", tier)
    if tier == resting_priority.RestingTier.EXCLUDED:
        op_data.config.free_blacklist.append("年")
    replacements = {
        name
        for slots in op_data.plan.values()
        for slot in slots
        if slot.agent != "菲亚梅塔"
        for name in slot.all_replacements
    }
    assert resting_priority.resting_tier(op_data, "年") == tier
    assert (
        resting_priority.resting_tier(op_data, "年", replacement_names=replacements)
        == tier
    )


def test_candidate_snapshot_preserves_calculated_mood_and_projection_clock(
    op_data, monkeypatch
):
    data = op_data
    observed = datetime(2026, 10, 27, 8)
    for name in ("年", "九色鹿"):
        data.add(Operator(name, ""))
        op = data.operators[name]
        op.mood, op.time_stamp = 6, observed
    data.operators["年"].upper_limit = 12
    data.config.ope_resting_priority.append("年")
    monkeypatch.setattr(candidates, "unregistered_idle_candidates", lambda *args: [])
    monkeypatch.setattr(
        Operators, "mood_calculation_enabled", property(lambda self: True)
    )

    def calculated_mood(self, name, now=None):
        if name == "年":
            return 8 if now < observed + timedelta(hours=1) else 12
        return 10 if name == "九色鹿" else None

    monkeypatch.setattr(Operators, "calculated_mood", calculated_mood)
    data._projection_now = observed
    before = candidates.dorm_candidates(data)
    assert [name for name in before.filling if name in ("年", "九色鹿")] == [
        "年",
        "九色鹿",
    ]

    data._projection_now = observed + timedelta(hours=1)
    after = candidates.dorm_candidates(data)
    assert [name for name in after.filling if name in ("年", "九色鹿")] == [
        "九色鹿",
        "年",
    ]
    assert "年" in after.full
    assert "年" not in after.recovering
    assert (
        resting_priority.resting_tier(
            data, "年", data._projection_now, replacement_names=set()
        )
        == resting_priority.RestingTier.IDLE
    )
    assert data.operators["年"].mood == 6
    assert data.operators["年"].time_stamp == observed
