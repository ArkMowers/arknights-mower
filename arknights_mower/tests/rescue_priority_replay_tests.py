"""日志中的救急床位不足在统一层级下可安排整组，使用脱敏离线房态。"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.resting_priority import RestingTier, resting_tier

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture
def logged_solver(monkeypatch):
    state = json.loads((FIXTURES / "rescue_priority_state_20261002.json").read_text())
    now = datetime.fromisoformat(state["now"])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    for module in (base_schedule, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate_json(
            (FIXTURES / "rescue_priority_plan_20261002.json").read_text()
        ),
    )
    config.conf.enable_mastery = False
    for key, value in config.plan.advanced_settings.items():
        setattr(config.conf, key, value)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    data = Operators(build_global_plan())
    assert data.init_and_validate() is None
    assert data.swap_plan(state["conditions"], refresh=True) is None
    for name, values in state["operators"].items():
        if name not in data.operators:
            data.add(Operator(name, ""))
        op = data.operators[name]
        for key, value in values.items():
            if key == "time_stamp" and value:
                value = datetime.fromisoformat(value)
            if key == "dorm_recovery_fixed":
                value = tuple(value)
            setattr(op, key, value)
    for bed in data.dorm:
        saved = next(b for b in state["dorms"] if tuple(b["position"]) == bed.position)
        bed.name = saved["name"]
        bed.time = datetime.fromisoformat(saved["time"]) if saved["time"] else None
    data.shadow_copy = data.operators.copy()
    assert data.init_and_validate(True) is None
    data.first_init = False
    instance = object.__new__(base_schedule.BaseSchedulerSolver)
    instance.op_data, instance.tasks, instance.task = data, [], None
    instance.check_fia = MagicMock(return_value=(None, None))
    instance._refresh_deferred_product_reservations = MagicMock()
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    return instance


@pytest.mark.parametrize("group", ["感知", "自动化", "红松", "深海"])
def test_logged_group_can_leave_work_after_lower_priority_beds_yield(
    logged_solver, group
):
    solver = logged_solver
    data = solver.op_data
    assert sum(data.is_effective_free_slot(bed) for bed in data.dorm) == 7
    for name in ("苏苏洛", "空爆", "凯尔希·思衡托"):
        assert resting_tier(data, name) == RestingTier.IDLE
    members = data.groups[group]
    plan, replacements = {}, []
    solver.get_resting_plan(
        members, replacements, plan, data.active_high_resting_count()
    )
    assert plan
    assert len(replacements) == len(set(replacements))
    assert {
        plan[data.operators[name].room][data.operators[name].index]
        for name in members
        if plan[data.operators[name].room][data.operators[name].index] != "Free"
    } == set(replacements)
    admitted = {bed.name for bed in data.dorm if bed.name in members}
    optional = data.standby_candidates(members)
    required = {
        name
        for name in members
        if not data.operators[name].workaholic
        and not data.operators[name].room.startswith("dorm")
        and not data.rest_mood_complete(name)
        and name not in optional
    }
    assert required <= admitted
    solver.enter_room.assert_not_called()
