"""训练期间的副表决定协助者是否仍被普通排班占用。"""

from copy import deepcopy

import pytest

from arknights_mower.tests.mastery_support_fixtures import facility
from arknights_mower.tests.mastery_support_fixtures import game as game
from arknights_mower.utils.mastery_support_data import schedule_context


def condition(left, right="True", operator="=="):
    return {"left": left, "operator": operator, "right": right}


def training_plan():
    return {
        "plan1": {"recycle": facility("望")},
        "backup_plans": [
            {
                "name": "望专精",
                "type": "global",
                "group_ids": ["default"],
                "trigger": condition("op_data.facility_is_training('train')"),
                "plan": {"recycle": facility("余")},
            }
        ],
    }


def test_training_backup_releases_assistant_without_mutating_source():
    plan = training_plan()
    original = deepcopy(plan)
    assert "望" not in schedule_context(plan)[0]
    assert plan == original


@pytest.mark.parametrize("room", ["train", "'train'"])
def test_assistant_location_activates_matching_backup(room):
    plan = training_plan()
    plan["backup_plans"][0]["trigger"] = condition(
        condition("op_data.facility_is_training('train')"),
        condition("op_data.operators['望'].current_room", room),
        "and",
    )
    assert "望" not in schedule_context(plan)[0]
    assert "余" in schedule_context(plan)[0]


@pytest.mark.parametrize(
    "slot",
    [
        facility("Current"),
        facility("余", ["望"]),
        {
            "plans": [
                {
                    "agent": "余",
                    "group_bindings": [{"group": "甲", "replacement": ["望"]}],
                }
            ]
        },
    ],
)
def test_retained_primary_or_replacement_stays_blocked(slot):
    plan = training_plan()
    plan["backup_plans"][0]["plan"]["recycle"] = slot
    assert schedule_context(plan)[0]["望"] == {"recycle"}


def test_uncertain_condition_does_not_release_assistant():
    plan = training_plan()
    plan["backup_plans"][0]["trigger"] = condition(
        "op_data.operators['令'].current_mood()", "12", ">"
    )
    assert "望" in schedule_context(plan)[0]


def test_later_backup_can_reintroduce_assistant():
    plan = training_plan()
    plan["backup_plans"].append(
        {"trigger": condition("True"), "plan": {"recycle": facility("望")}}
    )
    assert "望" in schedule_context(plan)[0]


def test_training_group_excludes_nontraining_assignment():
    plan = training_plan()
    plan["plan1"] = {"recycle": facility("余")}
    plan["backup_groups"] = [
        {
            "id": "training",
            "name": "专精",
            "exclusive_with": [],
            "trigger": condition("op_data.facility_is_training('train')"),
        }
    ]
    plan["backup_plans"] = [
        {
            "group_ids": ["training"],
            "type": "exclusive",
            "trigger": condition("op_data.operators['望'].current_room", "train"),
            "plan": {},
        },
        {
            "group_ids": ["training"],
            "type": "exclusive",
            "trigger": condition("op_data.operators['望'].current_room", "train", "!="),
            "plan": {"recycle": facility("望")},
        },
    ]
    assert "望" not in schedule_context(plan)[0]


def test_budget_exhaustion_keeps_original_exclusions(monkeypatch):
    from arknights_mower.utils import mastery_schedule
    from arknights_mower.utils.backup_validation import BackupValidationLimitExceeded

    def exhausted(*args, **kwargs):
        raise BackupValidationLimitExceeded("budget")

    monkeypatch.setattr(mastery_schedule, "possible_backup_conditions", exhausted)
    assert "望" in schedule_context(training_plan())[0]


def test_mutually_exclusive_alternative_can_still_reserve_assistant():
    plan = training_plan()
    plan["backup_plans"][0]["type"] = "exclusive"
    plan["backup_plans"].append(
        {
            "type": "exclusive",
            "trigger": condition("True"),
            "plan": {},
        }
    )
    assert "望" in schedule_context(plan)[0]


def test_normal_backup_validation_does_not_assume_training():
    from types import SimpleNamespace

    from arknights_mower.utils.backup_validation import possible_backup_conditions

    backups = [SimpleNamespace(trigger="op_data.facility_is_training('train') == True")]
    assert possible_backup_conditions(backups, 10) == [(False,), (True,)]
    assert possible_backup_conditions(backups, 10, training_support="望") == [(True,)]


def test_assistant_candidates_use_training_schedule(game, monkeypatch):
    from arknights_mower.tests.mastery_support_fixtures import owned
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_support_data import candidates
    from arknights_mower.utils.mastery_support_types import TrainingInputs

    metadata, ids = game
    monkeypatch.setattr(config, "plan", training_plan())
    options, _ = candidates(
        ids["能天使"],
        TrainingInputs(
            roster=[owned(ids["能天使"]), owned(ids["望"])],
            metadata=metadata,
        ),
    )
    assert "望" in options


def test_real_backup_selection_switches_with_assistant_location(monkeypatch):
    from arknights_mower.utils import mastery_db
    from arknights_mower.utils.logic_expression import get_logic_exp
    from arknights_mower.utils.operators import Operator, Operators
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    groups = [
        {
            "id": "training",
            "name": "专精",
            "exclusive_with": [],
            "trigger": condition("op_data.facility_is_training('train')"),
        }
    ]
    backups = [
        Plan(
            {"recycle": [Room(name, "", [])]},
            PlanConfig("", "", ""),
            name=label,
            group_ids=["training"],
            backup_type="exclusive",
            trigger=get_logic_exp(
                condition(
                    condition("op_data.operators['令'].is_working()", "True", "!="),
                    condition(
                        "op_data.operators['望'].current_room", "train", comparison
                    ),
                    "and",
                )
            ),
        )
        for name, label, comparison in [
            ("余", "望协助", "=="),
            ("望", "望不协助", "!="),
        ]
    ]
    operators = Operators(
        {
            "default_plan": Plan(
                {"recycle": [Room("国度", "", [])]}, PlanConfig("", "", "")
            ),
            "backup_plans": backups,
            "backup_groups": groups,
        }
    )
    operators.add(Operator("令", "central", current_room="dormitory_1"))
    operators.add(Operator("望", "", current_room="train", current_index=0))
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: {"status": "training"})
    for room, expected, occupant in [
        ("train", [True, False], "余"),
        ("", [False, True], "望"),
        ("train", [True, False], "余"),
    ]:
        operators.operators["望"].current_room = room
        selection = operators.evaluate_backup_selection()
        assert selection.conditions == expected
        assert (
            operators.swap_plan(selection.conditions, backup_group=selection.group_id)
            is None
        )
        assert operators.plan["recycle"][0].agent == occupant
    monkeypatch.setattr(mastery_db, "get_active_plan", lambda: None)
    assert operators.evaluate_backup_selection().conditions == [False, False]


@pytest.mark.parametrize("released", [False, True])
def test_runtime_handoff_rechecks_effective_training_schedule(monkeypatch, released):
    from unittest.mock import MagicMock

    from arknights_mower.solvers import mastery_reader, mastery_support_swap
    from arknights_mower.tests.mastery_support_fixtures import swap_case
    from arknights_mower.utils import config
    from arknights_mower.utils.mastery_support_types import SupportPlanError
    from arknights_mower.utils.scene import Scene

    schedule = training_plan()
    if not released:
        schedule["backup_plans"][0]["plan"]["recycle"] = facility("Current")
    monkeypatch.setattr(config, "plan", schedule)
    plan, panel, solver, _ = swap_case()
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    monkeypatch.setattr(mastery_reader, "read_main_panel", lambda s: panel)
    monkeypatch.setattr(
        mastery_reader, "_read_slots_checked", lambda s: ("望", "学员", None, True)
    )
    record = MagicMock()
    monkeypatch.setattr(mastery_support_swap, "record_work", record)
    if released:
        assert mastery_support_swap.place_support(solver, plan, 2, "望") is panel
        solver.choose_train.assert_called_once_with(["望", "Current"])
        record.assert_called_once_with(plan, 2, "望", panel.countdown)
    else:
        with pytest.raises(SupportPlanError, match="非训练室排班"):
            mastery_support_swap.place_support(solver, plan, 2, "望")
        solver.choose_train.assert_not_called()
        record.assert_not_called()
