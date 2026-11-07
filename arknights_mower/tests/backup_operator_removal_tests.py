import copy

import pytest
from pydantic import ValidationError

from arknights_mower.utils.config.plan import BackupPlanConf, PlanModel
from arknights_mower.utils.plan import PlanConfig

FIELDS = [
    "rest_in_full",
    "exhaust_require",
    "resting_priority",
    "resting_priority_replacement",
    "free_room_exclusions",
    "resting_standby",
    "workaholic",
    "free_blacklist",
    "refresh_trading",
    "refresh_drained",
    "ope_resting_priority",
]


def make_config(field, names="", removed=""):
    values = dict(rest_in_full="", exhaust_require="", resting_priority="")
    values["refresh_trading_config" if field == "refresh_trading" else field] = names
    if removed:
        values["removed_operators"] = {field: removed}
    return PlanConfig(**values)


@pytest.mark.parametrize("field", FIELDS)
def test_backup_removes_inherited_entries_without_mutating_sources(field):
    main = make_config(field, "陈,红")
    backup = make_config(field, "初雪,陈", "陈")
    before = copy.deepcopy((vars(main), vars(backup)))
    merged = main.merge_config(backup)
    attr = "refresh_trading_config" if field == "refresh_trading" else field
    assert getattr(merged, attr) == ["红", "初雪"]
    assert (vars(main), vars(backup)) == before


@pytest.mark.parametrize("field", FIELDS)
def test_backup_order_allows_later_readdition_and_deactivation(field):
    main = make_config(field, "陈,红")
    removal = make_config(field, removed="陈,不存在")
    addition = make_config(field, "陈")
    attr = "refresh_trading_config" if field == "refresh_trading" else field
    assert getattr(main.merge_config(removal).merge_config(addition), attr) == [
        "红",
        "陈",
    ]
    assert getattr(main.merge_config(addition).merge_config(removal), attr) == ["红"]
    assert getattr(main.merge_config(addition), attr) == ["陈", "红"]


def test_legacy_backup_remains_additive_and_removal_roundtrips():
    raw = {
        "plan1": {},
        "backup_plans": [
            {"plan": {}, "task": {}, "trigger": {}, "conf": {"rest_in_full": "陈"}}
        ],
    }
    model = PlanModel.model_validate(raw)
    assert model.backup_plans[0].conf.removed_operators == {}
    model.backup_plans[0].conf.removed_operators = {"rest_in_full": "红"}
    restored = PlanModel.model_validate_json(model.model_dump_json())
    assert restored.backup_plans[0].conf.removed_operators == {"rest_in_full": "红"}
    assert make_config("rest_in_full", "红").merge_config(
        make_config("rest_in_full", "陈")
    ).rest_in_full == ["红", "陈"]


def test_unsupported_removal_field_is_rejected():
    with pytest.raises(ValidationError):
        BackupPlanConf(removed_operators={"dorm_order": "dormitory_1"})


def test_refresh_trading_removal_matches_operator_with_room_configuration():
    main = make_config("refresh_trading", "陈(room_1_1),陈,陈洁,红")
    merged = main.merge_config(make_config("refresh_trading", removed="陈"))
    assert merged.refresh_trading_config == ["陈洁", "红"]


@pytest.mark.parametrize("field", FIELDS)
def test_backup_can_remove_entire_list(field):
    attr = "refresh_trading_config" if field == "refresh_trading" else field
    assert (
        getattr(
            make_config(field, "陈").merge_config(make_config(field, removed="陈")),
            attr,
        )
        == []
    )


def test_runtime_builder_keeps_removals_and_switching_restores_main(monkeypatch):
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import Operators, build_global_plan

    model = PlanModel.model_validate(
        {
            "plan1": {},
            "conf": {"rest_in_full": "陈", "exhaust_require": "红"},
            "backup_plans": [
                {
                    "plan": {},
                    "task": {},
                    "trigger": {},
                    "conf": {
                        "rest_in_full": "初雪",
                        "removed_operators": {
                            "rest_in_full": "陈",
                            "exhaust_require": "红",
                        },
                    },
                },
                {"plan": {}, "task": {}, "trigger": {}, "conf": {"rest_in_full": "陈"}},
            ],
        }
    )
    monkeypatch.setattr(config, "plan", model)
    monkeypatch.setattr(config, "conf", config.Conf())
    global_plan, source = build_global_plan(include_source=True)
    data = Operators(global_plan)
    before = model.model_dump()
    for flags, full, exhausted in [
        ([True, False], ["初雪"], []),
        ([True, True], ["初雪", "陈"], []),
        ([False, True], ["陈"], ["红"]),
        ([False, False], ["陈"], ["红"]),
    ]:
        data.swap_plan(flags)
        assert [name for name in data.config.rest_in_full if name] == full
        assert [name for name in data.config.exhaust_require if name] == exhausted
    assert source["backup_plans"][0]["conf"]["removed_operators"] == {
        "rest_in_full": "陈",
        "exhaust_require": "红",
    }
    assert model.model_dump() == before
