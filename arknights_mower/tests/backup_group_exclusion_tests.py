import copy
import itertools
import pickle

import pytest
from pydantic import ValidationError

from arknights_mower.utils import config
from arknights_mower.utils.backup_validation import possible_backup_conditions
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operators, build_global_plan


def group(key, excluded=(), trigger=True):
    return {
        "id": key,
        "name": key,
        "trigger": {"left": str(trigger)},
        "exclusive_with": list(excluded),
    }


def backup(name, memberships, kind="exclusive", trigger=True):
    return {
        "name": name,
        "group_ids": memberships,
        "type": kind,
        "trigger": {"left": str(trigger)},
    }


def load(groups, backups):
    return Operators(
        build_global_plan(
            plan_model=PlanModel.model_validate(
                {"backup_groups": groups, "backup_plans": backups}
            )
        )
    )


@pytest.fixture(autouse=True)
def isolated_conf(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())


def test_parallel_exclusive_selection_isolated_projection_and_saved_state():
    data = load(
        [group("trade"), group("factory")],
        [
            backup("trade-a", ["trade"]),
            backup("trade-b", ["trade"]),
            backup("factory-a", ["factory"]),
            backup("overlay", ["trade", "factory"], "global"),
        ],
    )
    selection = data.evaluate_backup_selection()
    assert selection.group_ids == ("trade", "factory")
    assert selection.conditions == [True, False, True, True]
    assert data.backup_group == "default"
    assert data.swap_plan(selection.conditions, backup_group=selection.group_id) is None
    projected = data.project_arrangements([])
    projected.swap_plan([False, True, True, True], backup_group=selection.group_id)
    assert data.plan_condition == [True, False, True, True]
    assert projected.evaluate_backup_selection().conditions == [False, True, True, True]
    assert pickle.loads(pickle.dumps(selection.group_id)) == selection.group_id
    assert data.evaluate_backup_selection() == selection


def test_priority_chain_excluded_group_does_not_block_later_group():
    data = load(
        [
            group("maintenance", ["trade"]),
            group("trade", ["factory"]),
            group("factory"),
        ],
        [backup(key, [key]) for key in ["maintenance", "trade", "factory"]],
    )
    selected = data.evaluate_backup_selection()
    assert selected.group_ids == ("maintenance", "factory")
    assert selected.conditions == [True, False, True]
    data.backup_groups[1], data.backup_groups[2] = (
        data.backup_groups[2],
        data.backup_groups[1],
    )
    assert data.evaluate_backup_selection().conditions == [False, True, False]


def test_shared_exclusive_reserves_every_active_membership():
    data = load(
        [group("a"), group("b")],
        [backup("shared", ["a", "b"]), backup("a", ["a"]), backup("b", ["b"])],
    )
    assert data.evaluate_backup_selection().conditions == [True, False, False]
    data.swap_plan([False, True, True], backup_group=("a", "b"))
    assert data.evaluate_backup_selection().conditions == [False, True, True]
    data.backup_plans[1].trigger = "False"
    assert data.evaluate_backup_selection().conditions == [False, False, True]


def test_fallback_only_when_no_custom_group_selected():
    data = load(
        [group("a", trigger=False), group("b", trigger=False)],
        [backup("fallback", ["default"]), backup("a", ["a"])],
    )
    assert data.evaluate_backup_selection().conditions == [True, False]
    data.backup_groups[1]["trigger"] = {"left": "True"}
    data.backup_plans[1].trigger = "False"
    assert data.evaluate_backup_selection().group_id == "a"
    assert data.evaluate_backup_selection().conditions == [False, False]


def test_legacy_migration_and_symmetric_roundtrip_do_not_mutate_input():
    raw = {"backup_groups": [{"id": key, "name": key} for key in ["a", "b"]]}
    original = copy.deepcopy(raw)
    saved = PlanModel.model_validate(raw).model_dump()
    assert raw == original
    assert [entry["exclusive_with"] for entry in saved["backup_groups"]] == [
        [],
        ["b"],
        ["a"],
    ]
    assert PlanModel.model_validate(saved).model_dump() == saved
    explicit = PlanModel.model_validate(
        {"backup_groups": [group("a", ["b"]), group("b"), group("c")]}
    )
    assert [entry.exclusive_with for entry in explicit.backup_groups] == [
        [],
        ["b"],
        ["a"],
        [],
    ]


@pytest.mark.parametrize(
    "groups",
    [
        [group("a", ["missing"])],
        [group("a", ["a"])],
        [group("a", ["b", "b"]), group("b")],
        [group("default", ["a"]), group("a")],
        [group("a", ["default"])],
        [{**group("a"), "exclusive_with": None}],
    ],
)
def test_invalid_exclusions_are_rejected(groups):
    with pytest.raises(ValidationError):
        PlanModel.model_validate({"backup_groups": groups})


@pytest.mark.parametrize("eligibility", itertools.product([False, True], repeat=3))
@pytest.mark.parametrize("edges", [[], [("a", "b")], [("a", "b"), ("b", "c")]])
def test_validation_matches_runtime_for_priorities_shared_slots_and_retention(
    eligibility, edges
):
    groups = [
        group(key, [right for left, right in edges if left == key], enabled)
        for key, enabled in zip(["a", "b", "c"], eligibility)
    ]
    data = load(
        groups,
        [
            backup("a", ["a"]),
            backup("ab", ["a", "b"]),
            backup("b", ["b"]),
            backup("c", ["c"]),
            backup("shared-overlay", ["a", "b", "c"], "global"),
        ],
    )
    expected = set()
    for current in itertools.product([False, True], repeat=5):
        data.plan_condition = list(current)
        expected.add(tuple(data.evaluate_backup_selection().conditions))
    actual = set(
        possible_backup_conditions(data.backup_plans, 64, groups=data.backup_groups)
    )
    assert actual == expected


def test_many_parallel_constant_groups_do_not_enumerate_all_raw_flags():
    data = load(
        [group(str(index)) for index in range(12)],
        [backup(str(index), [str(index)]) for index in range(12)],
    )
    assert possible_backup_conditions(
        data.backup_plans, 2, groups=data.backup_groups
    ) == [(True,) * 12]


def test_concurrent_group_conditions_cannot_create_an_impossible_combination():
    groups = [group("a"), group("b")]
    groups[0]["trigger"] = {"left": "op_data.operators['芬'].is_working()"}
    groups[1]["trigger"] = {"left": "not op_data.operators['芬'].is_working()"}
    data = load(groups, [backup("a", ["a"], "global"), backup("b", ["b"], "global")])
    assert set(
        possible_backup_conditions(data.backup_plans, 4, groups=data.backup_groups)
    ) == {(True, False), (False, True)}


def test_new_groups_default_true_without_enabling_legacy_or_explicit_empty_groups():
    data = load(
        [
            {"id": "new", "name": "New", "exclusive_with": []},
            {"id": "legacy", "name": "Legacy"},
            {"id": "empty", "name": "Empty", "exclusive_with": [], "trigger": {}},
        ],
        [backup(key, [key]) for key in ["new", "legacy", "empty"]],
    )
    assert data.evaluate_backup_selection().group_id == "new"
    assert data.evaluate_backup_selection().conditions == [True, False, False]
    from arknights_mower.utils.config.plan import BackupGroup

    assert BackupGroup(id="new", name="New").trigger.left == "True"
    model = PlanModel(
        backup_groups=[BackupGroup(id="a", name="A"), BackupGroup(id="b", name="B")]
    )
    assert [item.trigger.left for item in model.backup_groups[1:]] == ["True", "True"]
    assert [item.exclusive_with for item in model.backup_groups[1:]] == [[], []]
