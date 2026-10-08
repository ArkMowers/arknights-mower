"""救急排班与正常排班隔离，副表覆盖和重名提示的契约。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import emergency
from arknights_mower.tests.automatic_rescue_tests import setup_startup
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.emergency_plan import (
    configured_rescue_names,
    effective_rescue_plan,
    rescue_plan_for,
)
from arknights_mower.utils.emergency_recovery import NativeProjection


def schedule(*names):
    return PlanModel(plan1={"room_1_1": {"plans": [{"agent": n} for n in names]}})


def test_rescue_without_replacements_accepts_normal_primary(solver):
    setup_startup(solver)
    roster = {
        room: [slot.agent for slot in row]
        for room, row in solver.op_data.plan.items()
        if room.startswith("room")
    }
    assert rescue_plan_for(solver.op_data, roster) == roster


def test_rescue_backups_apply_in_order_without_mutating_normal_plan():
    document = schedule("红", "初雪")
    document = PlanModel(
        **{
            **document.model_dump(),
            "backup_plans": [
                {
                    "name": "启用",
                    "conf": {},
                    "task": {},
                    "trigger": {"left": "1", "operator": "==", "right": "1"},
                    "plan": {
                        "room_1_1": {"plans": [{"agent": "Current"}, {"agent": "砾"}]}
                    },
                },
                {
                    "name": "停用",
                    "conf": {},
                    "task": {},
                    "trigger": {"left": "1", "operator": "==", "right": "0"},
                    "plan": {"room_1_1": {"plans": [{"agent": "斑点"}]}},
                },
            ],
        }
    )
    data = SimpleNamespace(
        plan={"room_1_1": [object(), object()]},
        evaluate_expression=lambda expression: expression == "(1 == 1)",
    )
    before = document.model_dump()
    assert effective_rescue_plan(data, document)["rescue_plan"] == {
        "room_1_1": ["红", "砾"]
    }
    assert document.model_dump() == before
    assert configured_rescue_names(document) == {"红", "初雪", "砾", "斑点"}


@pytest.mark.parametrize(
    "roster",
    [
        {},
        {"room_1_1": ["红", "红"]},
        {"room_1_1": ["不存在"]},
        {"room_1_1": ["红", "初雪"]},
    ],
)
def test_incomplete_or_duplicate_roster_is_rejected(roster):
    with pytest.raises(ValueError):
        rescue_plan_for(SimpleNamespace(plan={"room_1_1": [object()]}), roster)


def test_primary_overlap_warns_and_stays_out_of_recovery_targets(solver, monkeypatch):
    setup_startup(solver)
    config.conf.automatic_rescue_enable = True
    row = config.conf.automatic_rescue_plan.plan1.room_1_1
    row.plans[0].agent = PRIMARY[0]
    logger = MagicMock()
    monkeypatch.setattr(emergency, "logger", logger)
    monkeypatch.setattr(
        emergency, "native_opportunity", lambda *a, **k: NativeProjection(None, True)
    )
    monkeypatch.setattr(emergency, "save_current_state", lambda: True)
    solver._emergency_startup()
    assert solver._emergency_active()
    assert solver.emergency_state["rescue_plan"]["room_1_1"] == [PRIMARY[0]]
    assert PRIMARY[0] not in solver.emergency_state["targets"]
    assert set(solver.emergency_state["targets"]) == set(PRIMARY[1:])
    logger.warning.assert_called_once()
    assert PRIMARY[0] in logger.warning.call_args.args[1]


def test_configuration_instances_keep_rescue_rosters_isolated():
    first, second = config.Conf(), config.Conf()
    first.automatic_rescue_plan = schedule(COVERS[0])
    assert not configured_rescue_names(second.automatic_rescue_plan)


@pytest.mark.parametrize("backup", [False, True])
def test_recycle_rescue_roster_and_initial_sampling(backup):
    facility = {"plans": [{"agent": "芬"}, {"agent": "香草"}]}
    primary = {"central": {"plans": [{"agent": "杜林"}]}}
    backups = []
    if backup:
        backups = [
            {
                "name": "回收站副表",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {"recycle": facility},
            }
        ]
    else:
        primary["recycle"] = facility
    document = PlanModel(plan1=primary, backup_plans=backups)
    data = SimpleNamespace(
        plan={"central": [object()], "recycle": [object(), object()]},
        evaluate_expression=lambda expression: True,
    )
    before = document.model_dump()

    assert configured_rescue_names(document) == {"杜林", "芬", "香草"}
    assert effective_rescue_plan(data, document)["rescue_plan"] == {
        "central": ["杜林"],
        "recycle": ["芬", "香草"],
    }
    assert document.model_dump() == before


@pytest.mark.parametrize(
    "names, error",
    [
        (["芬", "香草", "红"], "岗位数量"),
        (["芬", "芬"], "重复"),
        (["芬", "不存在"], "无效"),
        (["芬"], "等级/岗位数"),
        (None, "缺少"),
    ],
)
def test_recycle_rescue_roster_rejects_invalid_staffing(names, error):
    data = SimpleNamespace(plan={"recycle": [object(), object()]})
    roster = {} if names is None else {"recycle": names}
    with pytest.raises(ValueError, match=error):
        rescue_plan_for(data, roster)


def test_rescue_dorms_preserve_slot_indexes_and_override_fia_position(solver):
    from arknights_mower.utils.plan import Room

    setup_startup(solver)
    data = solver.op_data
    data.plan["dormitory_1"][4] = Room("菲亚梅塔", "", [])
    document = config.conf.automatic_rescue_plan.model_copy(deep=True)
    from arknights_mower.utils.config.plan import Facility

    document.plan1.dormitory_1 = Facility(
        plans=[{"agent": "杜林"}, {"agent": "Free"}, {"agent": "菲亚梅塔"}]
    )
    dorms = effective_rescue_plan(data, document)["dorm_layout"]
    assert dorms["dormitory_1"] == ["杜林", "Free", "菲亚梅塔", "Free", "Free"]
    document.plan1.dormitory_1 = Facility(plans=[{"agent": "杜林"}])
    dorms = effective_rescue_plan(data, document)["dorm_layout"]
    assert dorms["dormitory_1"] == ["杜林", "Free", "Free", "Free", "Free"]


def test_rescue_manager_defaults_to_free_and_cannot_duplicate_working_staff(solver):
    from arknights_mower.utils.config.plan import Facility

    setup_startup(solver)
    document = config.conf.automatic_rescue_plan
    dorms = effective_rescue_plan(solver.op_data, document)["dorm_layout"]
    assert dorms["dormitory_1"] == ["Free"] * 5
    document.plan1.dormitory_1 = Facility(plans=[{"agent": COVERS[0]}])
    with pytest.raises(ValueError, match="重复"):
        effective_rescue_plan(solver.op_data, document)


def test_independent_managers_are_added_and_restored_only_with_capacity(solver):
    from arknights_mower.tests.automatic_rescue_tests import make_episode

    state = make_episode(solver)
    state["dorm_layout"] = {"dormitory_1": ["杜林", "闪灵", "Free", "Free", "Free"]}
    state["targets"] = {}
    solver._open_emergency_beds()
    assert [slot.agent for slot in solver.op_data.plan["dormitory_1"]] == state[
        "dorm_layout"
    ]["dormitory_1"]
    assert "杜林" in solver.op_data.operators
    state["targets"] = {name: 24 for name in PRIMARY}
    for name in PRIMARY:
        solver.op_data.operators[name].mood = 0
    solver._open_emergency_beds()
    assert [slot.agent for slot in solver.op_data.plan["dormitory_1"]] == [
        "杜林",
        "Free",
        "Free",
        "Free",
        "Free",
    ]


def test_fia_charge_room_tracks_measured_rescue_position(solver):
    from arknights_mower.tests.automatic_rescue_tests import make_episode
    from arknights_mower.utils.operators import Operator

    state = make_episode(solver)
    fia = Operator(
        "菲亚梅塔",
        "dormitory_1",
        index=4,
        replacement=[PRIMARY[0]],
        current_room="dormitory_1",
        current_index=4,
    )
    solver.op_data.add(fia)
    state["dorm_layout"] = {"dormitory_1": ["Free", "Free", "菲亚梅塔", "Free", "Free"]}
    solver._open_emergency_beds()
    assert fia.index == 4
    fia.current_index = 2
    solver._open_emergency_beds()
    assert (fia.room, fia.index, fia.replacement) == ("dormitory_1", 2, [PRIMARY[0]])


@pytest.mark.parametrize("additional", [False, True])
def test_rescue_runner_and_fia_targets_are_independent(solver, additional):
    from arknights_mower.tests.automatic_rescue_tests import configure_rescue
    from arknights_mower.utils import config
    from arknights_mower.utils.config.plan import Facility, GroupBinding

    configure_rescue(solver)
    document = config.conf.automatic_rescue_plan
    slot = document.plan1.room_1_1.plans[0]
    if additional:
        slot.replacement = ["红"]
        slot.group_bindings = [GroupBinding(group="附加", replacement=["但书"])]
    else:
        slot.replacement = ["但书"]
    document.plan1.dormitory_1 = Facility(
        plans=[
            {"agent": "Free"},
            {"agent": "Free"},
            {"agent": "菲亚梅塔", "replacement": [PRIMARY[0]]},
        ]
    )
    result = effective_rescue_plan(solver.op_data, document)
    assert result["run_order_replacements"]["room_1_1"] == [["但书"]]
    assert result["fia_targets"] == [PRIMARY[0]]
    document.plan1.room_1_1.plans[0].replacement = ["红"]
    slot.group_bindings = []
    assert effective_rescue_plan(solver.op_data, document)["run_order_replacements"][
        "room_1_1"
    ] == [[]]


@pytest.mark.parametrize("mismatch", ["type", "level", "product"])
def test_facility_mismatch_prevents_rescue_entry(solver, monkeypatch, caplog, mismatch):
    from arknights_mower.utils.config.plan import Plans

    setup_startup(solver)
    monkeypatch.setattr(emergency, "save_current_state", lambda: True)
    config.conf.automatic_rescue_enable = True
    solver.op_data.plan["room_1_1"][0].facility = "贸易站"
    rescue = config.conf.automatic_rescue_plan.plan1.room_1_1
    rescue.name = "制造站" if mismatch == "type" else "贸易站"
    if mismatch == "level":
        rescue.plans.append(Plans(agent="红"))
    if mismatch == "product":
        solver.op_data.products["room_1_1"] = "lmd"
        rescue.product = "orundum"
    monkeypatch.setattr(
        emergency,
        "native_opportunity",
        lambda *args, **kwargs: NativeProjection(None, True, "blocked"),
    )
    solver._emergency_startup()
    assert not solver._emergency_active()
    solver._emergency_schedule_staffing.assert_not_called()
    assert "room_1_1" in caplog.text
    assert {
        "type": "设施类型不一致",
        "level": "等级/岗位数不一致",
        "product": "产物不一致",
    }[mismatch] in caplog.text


def test_effective_rescue_backup_must_match_normal_facility():
    from arknights_mower.utils.plan import Room

    data = SimpleNamespace(
        plan={"room_1_1": [Room("阿米娅", "", [], "制造站")]},
        evaluate_expression=lambda expression: True,
    )
    document = PlanModel(
        plan1={"room_1_1": {"name": "贸易站", "plans": [{"agent": "红"}]}},
        backup_plans=[
            {
                "name": "制造站",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {"room_1_1": {"name": "制造站", "plans": [{"agent": "砾"}]}},
            }
        ],
    )
    assert effective_rescue_plan(data, document)["rescue_plan"] == {"room_1_1": ["砾"]}
    data.evaluate_expression = lambda expression: False
    with pytest.raises(ValueError, match="设施类型不一致"):
        effective_rescue_plan(data, document)


def test_normal_schedule_advanced_export_excludes_rescue_configuration():
    from arknights_mower.utils.config.plan_advanced import (
        apply_advanced_settings,
        export_advanced_settings,
    )

    conf = config.Conf(automatic_rescue_enable=True)
    original = conf.automatic_rescue_plan.model_dump()
    advanced = export_advanced_settings(conf)
    assert "automatic_rescue_enable" not in advanced
    assert "automatic_rescue_plan" not in advanced
    restored = apply_advanced_settings(conf, {"rescue_threshold": 0.8})
    assert restored.automatic_rescue_enable
    assert restored.automatic_rescue_plan.model_dump() == original


@pytest.mark.parametrize("active", [False, True])
def test_both_effective_backup_plans_control_product_with_unchanged_facility(
    active, monkeypatch
):
    monkeypatch.setattr(config.conf.product_switching, "enable", True)
    from arknights_mower.utils.logic_expression import LogicExpression
    from arknights_mower.utils.operators import Operators
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    data = Operators(
        {
            "default_plan": Plan(
                {"room_1_1": [Room("阿米娅", "", [], "制造站")]},
                PlanConfig("", "", ""),
                products={"room_1_1": "gold"},
            ),
            "backup_plans": [
                Plan(
                    {"room_1_1": [Room("红", "", [], "制造站")]},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression("1", "==", "1"),
                    products={"room_1_1": "exp3"},
                )
            ],
        }
    )
    assert data.swap_plan([active]) is None
    data.evaluate_expression = lambda expression: active
    document = PlanModel(
        plan1={
            "room_1_1": {
                "name": "制造站",
                "product": "gold",
                "plans": [{"agent": "砾"}],
            }
        },
        backup_plans=[
            {
                "name": "制造",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {
                    "room_1_1": {
                        "name": "制造站",
                        "product": "exp3",
                        "plans": [{"agent": "初雪"}],
                    }
                },
            }
        ],
    )
    result = effective_rescue_plan(data, document)
    assert result["rescue_plan"] == {"room_1_1": ["初雪" if active else "砾"]}
    if active:
        document.backup_plans[0].plan.room_1_1.product = "gold"
        with pytest.raises(ValueError, match="产物不一致.*中级作战记录.*赤金"):
            effective_rescue_plan(data, document)
    else:
        document.backup_plans[0].plan.room_1_1.product = "exp3"
        assert effective_rescue_plan(data, document) == result


def test_backup_capacity_is_checked_after_conditions_and_overlay():
    from arknights_mower.utils.plan import Room

    data = SimpleNamespace(
        plan={"room_1_1": [Room("红", "", [], "制造站"), Room("砾", "", [], "制造站")]},
        products={"room_1_1": "gold"},
        evaluate_expression=lambda expression: True,
    )
    document = PlanModel(
        plan1={
            "room_1_1": {
                "name": "制造站",
                "product": "gold",
                "plans": [{"agent": "初雪"}],
            }
        },
        backup_plans=[
            {
                "name": "二级",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {
                    "room_1_1": {
                        "name": "制造站",
                        "plans": [{"agent": "Current"}, {"agent": "斑点"}],
                    }
                },
            }
        ],
    )
    assert effective_rescue_plan(data, document)["rescue_plan"] == {
        "room_1_1": ["初雪", "斑点"]
    }
    data.evaluate_expression = lambda expression: False
    with pytest.raises(ValueError, match="等级/岗位数不一致"):
        effective_rescue_plan(data, document)


def test_product_only_backup_keeps_rescue_roster_and_last_active_product():
    from arknights_mower.utils.plan import Room

    data = SimpleNamespace(
        plan={"room_1_1": [Room("红", "", [], "制造站", product="gold")]},
        products={"room_1_1": "exp3"},
        evaluate_expression=lambda expression: expression == "(1 == 1)",
    )
    document = PlanModel(
        plan1={
            "room_1_1": {
                "name": "制造站",
                "product": "gold",
                "plans": [{"agent": "初雪"}],
            }
        },
        backup_plans=[
            {
                "name": "产物",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {"room_1_1": {"product": "exp3", "plans": []}},
            },
            {
                "name": "未启用",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "0"},
                "plan": {"room_1_1": {"product": "orirock", "plans": []}},
            },
        ],
    )
    assert effective_rescue_plan(data, document)["rescue_plan"] == {
        "room_1_1": ["初雪"]
    }


@pytest.mark.parametrize("active", [False, True])
def test_rescue_fixed_rooms_apply_backups_and_keep_empty_training_slot(active):
    from arknights_mower.utils.plan import Room

    data = SimpleNamespace(
        plan={"central": [Room("阿米娅", "", [])]},
        evaluate_expression=lambda expression: active,
    )
    document = PlanModel(
        plan1={
            "central": {"plans": [{"agent": "红"}]},
            "factory": {"plans": [{"agent": "砾"}]},
            "train": {"plans": [{"agent": "初雪"}, {"agent": ""}]},
        },
        backup_plans=[
            {
                "name": "专项驻员",
                "conf": {},
                "task": {},
                "trigger": {"left": "1", "operator": "==", "right": "1"},
                "plan": {
                    "factory": {"plans": [{"agent": "斑点"}]},
                    "train": {"plans": [{"agent": "Current"}, {"agent": "阿米娅"}]},
                },
            }
        ],
    )
    result = effective_rescue_plan(data, document)["rescue_plan"]
    assert result["factory"] == ["斑点" if active else "砾"]
    assert result["train"] == ["初雪", "阿米娅" if active else ""]
    assert {"初雪", "砾", "斑点", "阿米娅"} <= configured_rescue_names(document)
    assert "factory" not in data.plan


@pytest.mark.parametrize(
    "room,names",
    [
        ("factory", ["红", "初雪"]),
        ("train", ["红", "初雪", "砾"]),
        ("train", ["红", "红"]),
    ],
)
def test_rescue_fixed_rooms_reject_over_capacity_and_duplicate_workers(room, names):
    with pytest.raises(ValueError):
        rescue_plan_for(
            SimpleNamespace(plan={"central": [object()]}),
            {"central": ["阿米娅"], room: names},
        )


def test_rescue_recovery_settings_append_and_dorm_order_overrides(solver):
    from arknights_mower.utils.plan import PlanConfig

    setup_startup(solver)
    document = config.conf.automatic_rescue_plan.model_copy(deep=True)
    document.conf.workaholic = "年"
    document.conf.free_blacklist = "杜林"
    document.conf.dorm_order = "dormitory_3,dormitory_1,dormitory_2,dormitory_4"
    normal = solver.op_data.config
    normal.workaholic = ["清流"]
    normal.free_blacklist = ["初雪"]
    result = effective_rescue_plan(solver.op_data, document)
    overlay = PlanConfig("", "", "", **result["worker_config"])
    combined = normal.merge_config(overlay)
    assert set(combined.workaholic) >= {"清流", "年"}
    assert set(combined.free_blacklist) >= {"初雪", "杜林"}
    assert combined.dorm_order[0] == "dormitory_3"
    assert normal.workaholic == ["清流"]
    assert normal.free_blacklist == ["初雪"]
