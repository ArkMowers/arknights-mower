"""Backup group selection, saved plans and structurally possible validation states."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from arknights_mower.utils import config
from arknights_mower.utils.backup_validation import possible_backup_conditions
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operators, build_global_plan


def condition(value):
    return {"left": value, "operator": "==", "right": "True"}


def model():
    return PlanModel.model_validate(
        {
            "backup_groups": [
                {"id": name, "name": name, "trigger": condition("True")}
                for name in ["a", "b"]
            ],
            "backup_plans": [
                {
                    "name": name,
                    "group_ids": [group],
                    "type": kind,
                    "trigger": condition("True"),
                }
                for name, group, kind in [
                    ("shared", "default", "global"),
                    ("fallback", "default", "exclusive"),
                    ("a-global", "a", "global"),
                    ("a-first", "a", "exclusive"),
                    ("a-second", "a", "exclusive"),
                    ("b-global", "b", "global"),
                ]
            ],
        }
    )


def test_old_plan_roundtrip_and_invalid_references():
    old = PlanModel.model_validate({"backup_plans": [{"name": "old"}]})
    saved = old.model_dump()
    assert saved["backup_groups"][0]["id"] == "default"
    assert saved["backup_plans"][0]["group_ids"] == ["default"]
    assert saved["backup_plans"][0]["type"] == "global"
    assert PlanModel.model_validate(saved).model_dump() == saved
    for change in [
        {"backup_groups": [{"id": "a", "name": "a"}] * 2},
        {"backup_plans": [{"group_ids": ["missing"]}]},
        {"backup_plans": [{"type": "invalid"}]},
    ]:
        with pytest.raises(ValidationError):
            PlanModel.model_validate(change)


def test_runtime_retains_group_and_exclusive_then_falls_back(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    data = Operators(build_global_plan(plan_model=model()))
    selected = data.evaluate_backup_selection()
    assert selected.group_id == "a"
    assert selected.conditions == [False, False, True, True, False, False]
    assert data.backup_group == "default"
    data.swap_plan([False, False, True, False, True, False], backup_group="a")
    assert data.evaluate_backup_selection().conditions[4]
    data.swap_plan([False, False, False, False, False, True], backup_group="b")
    assert data.evaluate_backup_selection().group_id == "b"
    data.backup_groups[-1]["trigger"] = condition("False")
    assert data.evaluate_backup_selection().group_id == "a"
    data.backup_groups[1]["trigger"] = condition("False")
    selected = data.evaluate_backup_selection()
    assert selected.group_id == "default"
    assert selected.conditions == [True, True, False, False, False, False]


def test_empty_active_group_is_not_inferred_from_backup_flags(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    saved = model()
    saved.backup_plans = []
    data = Operators(build_global_plan(plan_model=saved))
    data.swap_plan([], backup_group="b")
    assert data.evaluate_backup_selection().group_id == "b"
    projected = data.project_arrangements([])
    projected.backup_group = "a"
    assert data.backup_group == "b"


def test_validation_includes_retained_exclusive_without_default_globals(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    data = Operators(build_global_plan(plan_model=model()))
    states = possible_backup_conditions(
        data.backup_plans, 20, groups=data.backup_groups
    )
    assert set(states) == {
        (False, False, True, True, False, False),
        (False, False, True, False, True, False),
        (False, False, False, False, False, True),
    }


@pytest.mark.parametrize("count", [19, 30])
def test_many_independent_groups_do_not_form_cross_group_cartesian_product(count):
    groups = [
        {"id": f"g{i}", "name": str(i), "trigger": condition(f"unknown{i}")}
        for i in range(count)
    ]
    backups = [
        SimpleNamespace(group_ids=[group["id"]], backup_type="global", trigger="True")
        for group in groups
    ]
    states = possible_backup_conditions(backups, 64, groups=groups)
    assert len(states) == count + 1
    assert max(map(sum, states)) == 1


def test_multiple_memberships_and_default_have_identical_gating(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    saved = model()
    saved.backup_plans[0].group_ids = ["a", "b"]
    data = Operators(build_global_plan(plan_model=saved))
    assert data.evaluate_backup_selection().conditions[0]
    data.swap_plan([False] * 6, backup_group="b")
    assert data.evaluate_backup_selection().conditions[0]
    for group in data.backup_groups:
        group["trigger"] = condition("False")
    assert not data.evaluate_backup_selection().conditions[0]
    for invalid in [[], ["a", "a"], ["a", "missing"]]:
        raw = saved.model_dump()
        raw["backup_plans"][0]["group_ids"] = invalid
        with pytest.raises(ValidationError):
            PlanModel.model_validate(raw)
