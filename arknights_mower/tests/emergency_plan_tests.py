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


def test_rescue_runner_and_fia_targets_are_independent(solver):
    from arknights_mower.tests.automatic_rescue_tests import configure_rescue
    from arknights_mower.utils import config
    from arknights_mower.utils.config.plan import Facility

    configure_rescue(solver)
    document = config.conf.automatic_rescue_plan
    document.plan1.room_1_1.plans[0].replacement = ["但书"]
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
    assert effective_rescue_plan(solver.op_data, document)["run_order_replacements"][
        "room_1_1"
    ] == [[]]


@pytest.mark.parametrize("mismatch", ["type", "level"])
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
    monkeypatch.setattr(
        emergency,
        "native_opportunity",
        lambda *args, **kwargs: NativeProjection(None, True, "blocked"),
    )
    solver._emergency_startup()
    assert not solver._emergency_active()
    solver._emergency_schedule_staffing.assert_not_called()
    assert "room_1_1" in caplog.text
    assert (
        "设施类型不一致" if mismatch == "type" else "等级/岗位数不一致"
    ) in caplog.text


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
