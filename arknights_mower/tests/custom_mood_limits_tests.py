from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from arknights_mower.tests import (
    dorm_release_tests,
    ling_xi_rest_limit_tests,
    shift_off_mood_tests,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanConf
from arknights_mower.utils.operators import Operator, build_global_plan
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import TaskTypes, plan_mood_limit_releases

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data
legacy_solver = ling_xi_rest_limit_tests.solver
legacy_shift_solver = shift_off_mood_tests.solver


@pytest.fixture
def solver(legacy_solver):
    config.conf.experimental_dorm_logic = True
    legacy_solver.op_data.config.experimental_dorm_logic = True
    # 通用上限用不受令夕模式约束的工作组验证。
    data = legacy_solver.op_data
    old = data.plan["central"][0].agent
    op = data.operators.pop(old)
    op.name = "银灰"
    data.operators["银灰"] = op
    data.plan["central"][0].agent = "银灰"
    data.groups[op.group] = [
        "银灰" if name == old else name for name in data.groups[op.group]
    ]
    for bed in data.dorm:
        if bed.name == old:
            bed.name = "银灰"
    data.init_mood_limit()
    return legacy_solver


@pytest.fixture
def shift_solver(legacy_shift_solver):
    config.conf.experimental_dorm_logic = True
    legacy_shift_solver.op_data.config.experimental_dorm_logic = True
    return legacy_shift_solver


def bounds(lower=0, upper=24):
    return {"lower": lower, "upper": upper}


@pytest.mark.parametrize(
    "value",
    [
        bounds(-1, 12),
        bounds(12, 12),
        bounds(13, 12),
        bounds(0, 25),
        bounds(0, float("inf")),
    ],
)
@pytest.mark.parametrize("individual", [False, True])
def test_invalid_limits_are_rejected(value, individual):
    payload = (
        {"operator_mood_limits": {"银灰": value}}
        if individual
        else {"mood_limits": value}
    )
    with pytest.raises(ValidationError):
        PlanConf(**payload)


def test_plan_round_trip_builds_runtime_limits(monkeypatch):
    raw = {
        "plan1": {"meeting": {"plans": [{"agent": "银灰", "replacement": ["红"]}]}},
        "conf": {
            "ling_xi": 2,
            "mood_limits": bounds(2, 20),
            "operator_mood_limits": {"银灰": bounds(4, 16)},
        },
        "backup_plans": [{"conf": {"operator_mood_limits": {"红": bounds(1, 12)}}}],
    }
    plan = config.PlanModel(**raw)
    plan = config.PlanModel.model_validate_json(plan.model_dump_json())
    monkeypatch.setattr(config, "plan", plan)
    result = build_global_plan()
    assert result["default_plan"].config.mood_limits == bounds(2, 20)
    assert result["default_plan"].config.operator_mood_limits == {"银灰": bounds(4, 16)}
    assert result["backup_plans"][0].config.operator_mood_limits == {
        "红": bounds(1, 12)
    }
    assert PlanConf(ling_xi=1).mood_limits is None


def test_global_scope_and_individual_override(op_data):
    op_data.config.mood_limits = bounds(2, 20)
    op_data.config.operator_mood_limits = {"银灰": bounds(6, 14), "空爆": bounds(8, 12)}
    op_data.init_mood_limit()
    for name, expected in [("银灰", (6, 14)), ("红", (2, 20)), ("空爆", (0, 24))]:
        op = op_data.operators[name]
        assert (op.lower_limit, op.upper_limit) == expected
    assert not op_data.has_rest_mood_limit("空爆")
    assert not op_data.has_rest_mood_limit("红")
    # 后续读房补入的排班替班也使用同一配置。
    del op_data.operators["红"]
    op_data.add(Operator("红", ""))
    assert op_data.operators["红"].upper_limit == 20


def test_backup_limits_inherit_override_and_restore(op_data):
    main = op_data.global_plan["default_plan"].config
    main.mood_limits = bounds(2, 20)
    main.operator_mood_limits = {"银灰": bounds(4, 16)}
    op_data.global_plan["backup_plans"] = [
        Plan(
            {},
            PlanConfig(
                "",
                "",
                "",
                mood_limits=bounds(3, 18),
                operator_mood_limits={"红": bounds(5, 15)},
            ),
        ),
        Plan({}, PlanConfig("", "", "", operator_mood_limits={"银灰": bounds(7, 17)})),
    ]
    op_data.swap_plan([True, False], True)
    assert op_data.operators["银灰"].upper_limit == 16
    assert op_data.operators["红"].lower_limit == 5
    assert op_data.operators["杜林"].upper_limit == 18
    op_data.swap_plan([True, True], True)
    assert op_data.operators["银灰"].lower_limit == 7
    op_data.swap_plan([False, False], True)
    assert op_data.operators["银灰"].lower_limit == 4
    assert op_data.operators["红"].upper_limit == 20


def test_individual_limits_override_mode_while_mode_overrides_global(legacy_solver):
    data = legacy_solver.op_data
    data.config.experimental_dorm_logic = True
    name = data.plan["central"][0].agent
    assert data.operators[name].upper_limit == 12
    assert data.operators["絮雨"].lower_limit == 12
    data.config.mood_limits = bounds(1, 20)
    data.config.operator_mood_limits = {name: bounds(4, 16)}
    data.init_mood_limit()
    assert (data.operators[name].lower_limit, data.operators[name].upper_limit) == (
        4,
        16,
    )
    assert (data.operators["絮雨"].lower_limit, data.operators["絮雨"].upper_limit) == (
        12,
        24,
    )
    assert data.operators["斥罪"].upper_limit == 20
    data.config.mood_limits = None
    data.config.operator_mood_limits = {}
    data.init_mood_limit()
    assert data.operators[name].upper_limit == 12
    assert data.operators["絮雨"].lower_limit == 12


@pytest.mark.parametrize("free_room", [False, True])
def test_any_planned_operator_releases_at_cap_and_cannot_reenter(op_data, free_room):
    op_data.config.free_room = free_room
    op_data.config.operator_mood_limits = {"红": bounds(4, 16)}
    op_data.init_mood_limit()
    op = op_data.operators["红"]
    op.current_room, op.current_index = ROOM, 4
    op.mood = 17
    bed = op_data.dorm[0]
    bed.name = op.name
    bed.time = datetime.now() + timedelta(hours=2)
    tasks = plan_mood_limit_releases(op_data)
    assert len(tasks) == 1 and tasks[0].meta_data == "红"
    assert tasks[0].time <= datetime.now()
    assert tasks[0].mood_limit == 16
    assert op_data.assign_dorm("红") is None
    assert op_data.assign_dorm_group(["红"]) == []


def test_custom_limits_do_not_clear_fixed_dorm_staff(op_data):
    op_data.config.mood_limits = bounds(0, 12)
    op_data.init_mood_limit()
    op_data.operators["杜林"].current_room = ROOM
    op_data.operators["杜林"].current_index = 0
    assert all(t.meta_data != "杜林" for t in plan_mood_limit_releases(op_data))


def test_cap_change_rescales_cached_recovery_time(op_data):
    op_data.init_mood_limit()
    op = op_data.operators["红"]
    op.mood = 6
    op.current_room, op.current_index = ROOM, 4
    bed = op_data.dorm[0]
    bed.name = op.name
    bed.time = op.time_stamp + timedelta(hours=3)
    op_data.config.operator_mood_limits = {"红": bounds(0, 12)}
    op_data.init_mood_limit()
    assert bed.time == op.time_stamp + timedelta(hours=1)
    op_data.config.operator_mood_limits.clear()
    op_data.init_mood_limit()
    assert bed.time == op.time_stamp + timedelta(hours=3)


def test_read_countdown_targets_custom_cap(op_data):
    op_data.config.operator_mood_limits = {"红": bounds(2, 12)}
    op_data.init_mood_limit()
    op = op_data.operators["红"]
    op.mood = 6
    op.current_room, op.current_index = ROOM, 4
    op_data.refresh_dorm_time(
        ROOM, 4, {"agent": "红", "time": op.time_stamp + timedelta(hours=3)}
    )
    assert op_data.dorm[0].time == op.time_stamp + timedelta(hours=1)


def test_cap_change_without_valid_mood_requires_new_countdown(op_data):
    op_data.init_mood_limit()
    op_data.dorm[0].name = "红"
    op_data.operators["红"].time_stamp = None
    op_data.config.operator_mood_limits = {"红": bounds(0, 12)}
    op_data.init_mood_limit()
    assert op_data.dorm[0].time is None


def test_unlisted_override_starts_and_stops_with_effective_plan(op_data):
    op_data.config.operator_mood_limits = {"空爆": bounds(3, 14)}
    op_data.init_mood_limit()
    assert op_data.operators["空爆"].upper_limit == 24
    replacements = op_data.plan["meeting"][0].replacement
    replacements.append("空爆")
    op_data.init_mood_limit()
    assert op_data.operators["空爆"].upper_limit == 14
    replacements.remove("空爆")
    op_data.init_mood_limit()
    assert op_data.operators["空爆"].upper_limit == 24


def test_totter_automatic_bounds_remain_and_custom_range_can_override(op_data):
    op_data.plan["meeting"][0].agent = "铅踝"
    op_data.add(Operator("铅踝", "meeting", operator_type="high"))
    op_data.init_mood_limit()
    assert op_data.operators["铅踝"].lower_limit == 20
    op_data.config.mood_limits = bounds(0, 12)
    op_data.init_mood_limit()
    assert (
        op_data.operators["铅踝"].lower_limit,
        op_data.operators["铅踝"].upper_limit,
    ) == (0, 12)


def test_unknown_override_name_is_rejected(op_data):
    op_data.config.operator_mood_limits = {"不存在的干员": bounds(0, 12)}
    assert "干员名无效" in op_data.init_and_validate()


@pytest.mark.parametrize("lower,upper", [(0, 12), (8, 20), (0, 1), (0.25, 2)])
@pytest.mark.parametrize("above", [False, True])
def test_downshift_and_rescue_thresholds_use_custom_range(
    shift_solver, lower, upper, above
):
    solver = shift_solver
    data = solver.op_data
    data.config.operator_mood_limits = {"歌蕾蒂娅": bounds(lower, upper)}
    data.init_mood_limit()
    data.config.resting_threshold = 0.5
    config.conf.rescue_threshold = 0.5
    op = data.operators["歌蕾蒂娅"]
    threshold = lower + (upper - lower) * 0.5
    assert data.resting_mood_threshold(op) == threshold
    assert data.rescue_mood_threshold(op) == lower + (upper - lower) * 0.25
    for other in data.operators.values():
        other.mood = 24
    op.mood = threshold + (0.01 if above else 0)
    solver.resting()
    assert (op.name in {bed.name for bed in data.dorm}) is (not above)


def test_changed_cap_invalidates_old_release_task(solver):
    data = solver.op_data
    data.config.operator_mood_limits = {"絮雨": bounds(0, 16)}
    data.init_mood_limit()
    task = next(t for t in plan_mood_limit_releases(data) if t.meta_data == "絮雨")
    data.config.operator_mood_limits["絮雨"] = bounds(0, 20)
    data.init_mood_limit()
    task.time = ling_xi_rest_limit_tests.NOW
    solver.task, solver.tasks = task, [task]
    from unittest.mock import MagicMock

    solver.agent_arrange = MagicMock()
    solver.infra_main()
    solver.agent_arrange.assert_called_once_with({}, False)
    assert data.operators["絮雨"].is_resting()


def test_full_custom_replacement_is_excluded_from_free_selection(solver):
    data = solver.op_data
    data.config.operator_mood_limits = {"斥罪": bounds(0, 16)}
    data.init_mood_limit()
    op = data.operators["斥罪"]
    op.current_room, op.current_index = "", -1
    op.mood = 16
    assert op.name not in solver.get_free_list([])


@pytest.mark.parametrize("individual", [False, True])
def test_selection_distinguishes_individual_and_global_caps(solver, individual):
    from unittest.mock import MagicMock

    from arknights_mower.utils.scheduler_task import SchedulerTask

    class SelectionBoundary(Exception):
        pass

    data = solver.op_data
    data.config.mood_limits = bounds(0, 12)
    if individual:
        data.config.operator_mood_limits = {
            name: bounds(0, 12)
            for name in data.operators
            if data.is_planned_operator(name)
        }
    data.init_mood_limit()
    for op in data.operators.values():
        op.mood = 12
    data.get_current_room = MagicMock(side_effect=SelectionBoundary)
    solver.task = SchedulerTask()
    agents = ["冰酿", "闪灵", "絮雨", data.plan["central"][0].agent, "Free"]
    with pytest.raises(SelectionBoundary):
        solver.choose_agent(agents, "dormitory_1", preserve_dorm_occupants=True)
    assert agents == (
        ["冰酿", "闪灵", "Free", "Free", "Free"]
        if individual
        else ["冰酿", "闪灵", "絮雨", data.plan["central"][0].agent, "Free"]
    )


def test_completed_limited_group_keeps_return_after_last_release(solver):
    data = solver.op_data
    data.config.operator_mood_limits = {
        name: bounds(0, 12) for name in data.groups["感知"]
    }
    data.init_mood_limit()
    solver.plan_metadata()
    members = data.groups["感知"]
    for name in members:
        op = data.operators[name]
        op.mood = 12
        op.current_room, op.current_index = "", -1
    for bed in data.dorm:
        bed.reset()
    solver.plan_metadata()
    returns = [t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]
    assert any(
        set(members) <= {name for names in t.plan.values() for name in names}
        for t in returns
    )


@pytest.mark.parametrize("related", [False, True])
def test_completed_group_return_waits_only_for_related_arrangements(solver, related):
    from arknights_mower.utils.scheduler_task import SchedulerTask

    data = solver.op_data
    data.config.operator_mood_limits = {
        name: bounds(0, 12) for name in data.groups["感知"]
    }
    data.init_mood_limit()
    members = data.groups["感知"]
    for name in members:
        op = data.operators[name]
        op.mood = 12
        op.current_room, op.current_index = "", -1
    for bed in data.dorm:
        bed.reset()
    now = ling_xi_rest_limit_tests.NOW
    pending = SchedulerTask(
        time=now + timedelta(minutes=10),
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"contact": ["斥罪"]}
        if related
        else {"dormitory_1": ["冰酿", "Current", "Current", "Current", "Current"]},
    )
    solver.tasks = [pending]
    solver.plan_metadata()
    task = next(
        t
        for t in solver.tasks
        if t.type == TaskTypes.SHIFT_ON
        and set(members) <= {name for names in t.plan.values() for name in names}
    )
    expected = (
        pending.time + timedelta(seconds=1)
        if (related and data.experimental_dorm_logic)
        else now
    )
    assert task.time == expected


def test_custom_limits_toggle_restores_original_ranges_and_keeps_config(op_data):
    op_data.config.mood_limits = bounds(2, 20)
    op_data.config.operator_mood_limits = {"银灰": bounds(4, 16)}
    for enabled in (True, False, True):
        op_data.config.experimental_dorm_logic = enabled
        op_data.init_mood_limit()
        for name, custom in [("银灰", (4, 16)), ("红", (2, 20))]:
            op = op_data.operators[name]
            assert (op.lower_limit, op.upper_limit) == (custom if enabled else (0, 24))
            assert op_data.has_rest_mood_limit(name) is (enabled and name == "银灰")
        assert op_data.config.operator_mood_limits["银灰"] == bounds(4, 16)


def test_disabled_custom_limits_keep_ling_xi_automatic_rules(legacy_solver):
    data = legacy_solver.op_data
    data.config.experimental_dorm_logic = False
    data.config.mood_limits = bounds(1, 20)
    name = data.plan["central"][0].agent
    data.config.operator_mood_limits = {name: bounds(4, 16)}
    data.init_mood_limit()
    assert data.custom_mood_limits(name) is None
    assert data.operators[name].upper_limit == 12
    assert data.operators["絮雨"].lower_limit == 12
    assert data.has_rest_mood_limit(name)
    assert not data.has_rest_mood_limit("絮雨")


@pytest.mark.parametrize("mode", [1, 2, 3])
def test_mode_changes_override_saved_custom_ranges(legacy_solver, mode):
    data = legacy_solver.op_data
    data.config.experimental_dorm_logic = True
    name = data.plan["central"][0].agent
    data.config.mood_limits = bounds(1, 20)
    data.config.operator_mood_limits = {name: bounds(4, 16), "絮雨": bounds(3, 18)}
    data.config.ling_xi = mode
    data.init_mood_limit()
    assert (data.operators[name].lower_limit, data.operators[name].upper_limit) == (
        4,
        16,
    )
    assert (data.operators["絮雨"].lower_limit, data.operators["絮雨"].upper_limit) == (
        3,
        18,
    )
    # 移除个人设置后，模式恢复并覆盖仍启用的全体范围。
    data.config.operator_mood_limits = {}
    data.init_mood_limit()
    expected = (
        (0, 24)
        if mode == 3
        else ((0, 12) if name == {1: "令", 2: "夕"}[mode] else (12, 24))
    )
    assert (
        data.operators[name].lower_limit,
        data.operators[name].upper_limit,
    ) == expected
    assert (data.operators["絮雨"].lower_limit, data.operators["絮雨"].upper_limit) == (
        0 if mode == 3 else 12,
        24,
    )


@pytest.mark.parametrize("individual", [False, True])
def test_late_registered_ling_replacement_obeys_priority(op_data, individual):
    op_data.config.ling_xi = 1
    op_data.config.mood_limits = bounds(3, 20)
    op_data.config.operator_mood_limits = {"令": bounds(5, 18)} if individual else {}
    op_data.plan["meeting"][0].replacement.append("令")
    op_data.add(Operator("令", ""))
    op = op_data.operators["令"]
    assert (op.lower_limit, op.upper_limit) == ((5, 18) if individual else (0, 12))


def test_same_numeric_cap_is_strict_only_when_individually_configured(op_data):
    op_data.config.mood_limits = bounds(0, 20)
    op_data.init_mood_limit()
    op = op_data.operators["红"]
    op.current_room, op.current_index = ROOM, 4
    op.mood = 21
    op_data.dorm[0].name = "红"
    op_data.dorm[0].time = datetime.now() - timedelta(minutes=1)
    assert plan_mood_limit_releases(op_data) == []
    assert not op_data.rest_mood_complete("红")
    op_data.config.operator_mood_limits["红"] = bounds(0, 20)
    op_data.init_mood_limit()
    releases = plan_mood_limit_releases(op_data)
    assert len(releases) == 1 and releases[0].meta_data == "红"
    assert op_data.rest_mood_complete("红")
    op_data.config.operator_mood_limits.clear()
    op_data.init_mood_limit()
    assert op.upper_limit == 20
    assert plan_mood_limit_releases(op_data) == []
