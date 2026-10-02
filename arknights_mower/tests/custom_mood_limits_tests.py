from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from arknights_mower.solvers import emergency
from arknights_mower.tests import (
    dorm_release_tests,
    ling_xi_rest_limit_tests,
    shift_off_mood_tests,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import PlanConf
from arknights_mower.utils.emergency_recovery import mood_context
from arknights_mower.utils.operators import Operator, build_global_plan
from arknights_mower.utils.plan import Plan, PlanConfig
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    plan_mood_limit_releases,
)

ROOM = dorm_release_tests.ROOM
op_data = dorm_release_tests.op_data
legacy_solver = ling_xi_rest_limit_tests.solver
legacy_shift_solver = shift_off_mood_tests.solver


@pytest.fixture
def solver(legacy_solver):
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
    return legacy_shift_solver


def bounds(lower=0, upper=24):
    return {"lower": lower, "upper": upper}


@pytest.fixture
def emergency_solver(solver, monkeypatch):
    now = ling_xi_rest_limit_tests.NOW

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(emergency, "datetime", Clock)
    monkeypatch.setattr(emergency, "save_current_state", lambda: True)
    data = solver.op_data
    data.config.ling_xi = 3
    data.config.operator_mood_limits = {"银灰": bounds(0, 12)}
    data.init_mood_limit()
    limited = data.operators["银灰"]
    data.update_detail("银灰", 10, limited.current_room, limited.current_index, True)
    _, bed = data.get_dorm_by_name("银灰")
    bed.time = now + timedelta(minutes=10)
    solver.emergency_state = {
        "phase": "recovering",
        "backup_names": [],
        "frozen_conditions": [],
        "targets": {"银灰": 12, "絮雨": 24},
        "target_sources": {"银灰": "fallback", "絮雨": "fallback"},
        "work_contexts": {
            name: mood_context(data, data.operators[name].room)
            for name in ("银灰", "絮雨")
        },
        "dorm_layout": {
            room: [slot.agent for slot in slots]
            for room, slots in data.plan.items()
            if room.startswith("dorm")
        },
        "next_read": now + timedelta(minutes=30),
    }
    return solver


def test_emergency_plans_personal_limit_before_next_read_without_ordinary_shifts(
    emergency_solver,
):
    solver = emergency_solver
    solver.plan_metadata()
    assert len(solver.tasks) == 1
    release = solver.tasks[0]
    assert release.type == TaskTypes.RELEASE_DORM
    assert release.strict_mood_limit and release.mood_limit == 12
    assert release.meta_data == "银灰"
    assert release.time == ling_xi_rest_limit_tests.NOW + timedelta(minutes=10)
    assert release.time < solver.emergency_state["next_read"]
    assert release.release_dorm_targets() == {"银灰": (ROOM, 3)}
    solver.plan_metadata()
    assert len(solver.tasks) == 1
    assert solver.tasks[0].time == release.time
    assert not solver._emergency_ready()


def test_emergency_releases_completed_primary_without_exiting_or_clearing_new_resident(
    emergency_solver,
):
    solver = emergency_solver
    data = solver.op_data
    data.update_detail("银灰", 12, ROOM, 3, True)
    solver.plan_metadata()
    release = solver.tasks[0]
    assert release.time == ling_xi_rest_limit_tests.NOW
    assert release.strict_mood_limit and release.meta_data == "银灰"
    assert not solver._emergency_ready()
    assert solver.prepare_release_dorm(release)
    solver.op_data = data.project_arrangements(
        [{ROOM: ["Current", "Current", "Current", "斥罪", "Current"]}]
    )
    assert not solver.prepare_release_dorm(release)
    assert release.plan == {}
    assert solver.op_data.get_current_operator(ROOM, 3).name == "斥罪"
    solver.plan_metadata()
    assert not solver.tasks
    assert solver.emergency_state["phase"] == "recovering"
    assert not solver._emergency_ready()


def test_emergency_nonreading_tick_keeps_personal_limit_deadline(emergency_solver):
    solver = emergency_solver
    solver.emergency_state["phase"] = "staffing"
    staffing = SchedulerTask(task_plan={"central": ["Mon3tr"]})
    staffing.emergency_staffing = True
    solver.tasks = [staffing]
    solver._emergency_read_rooms = MagicMock(
        side_effect=AssertionError("unexpected mood read")
    )
    solver._emergency_collect = MagicMock(
        side_effect=AssertionError("unexpected collection")
    )

    solver._emergency_tick()
    solver._emergency_tick()

    releases = [task for task in solver.tasks if task.strict_mood_limit]
    assert len(releases) == 1
    assert releases[0].time == ling_xi_rest_limit_tests.NOW + timedelta(minutes=10)
    assert releases[0].release_dorm_targets() == {"银灰": (ROOM, 3)}
    assert solver.emergency_state["phase"] == "staffing"
    assert staffing in solver.tasks
    assert all(task.type != TaskTypes.SHIFT_ON for task in solver.tasks)


def test_emergency_reading_tick_replans_limit_after_new_observation(emergency_solver):
    solver = emergency_solver
    state = solver.emergency_state
    state["phase"] = "returning"
    state["next_read"] = ling_xi_rest_limit_tests.NOW
    solver.plan_metadata()
    assert solver.tasks[0].time > ling_xi_rest_limit_tests.NOW

    def observe(rooms):
        assert ROOM in rooms
        solver.op_data.update_detail("银灰", 12, ROOM, 3, True)

    solver._emergency_read_rooms = MagicMock(side_effect=observe)
    solver._emergency_collect = MagicMock()

    solver._emergency_tick()

    release = next(task for task in solver.tasks if task.strict_mood_limit)
    assert release.time == ling_xi_rest_limit_tests.NOW
    assert release.release_dorm_targets() == {"银灰": (ROOM, 3)}
    assert state["phase"] == "returning"
    assert not solver._emergency_ready()
    assert all(task.type != TaskTypes.SHIFT_ON for task in solver.tasks)


def test_emergency_bed_planning_preserves_resident_awaiting_personal_limit_release(
    emergency_solver,
):
    solver = emergency_solver
    solver.plan_metadata()
    release = solver.tasks[0]
    assert solver.emergency_state["targets"]["银灰"] == release.mood_limit == 12
    assert solver.op_data.operators["银灰"].mood == 10

    solver._open_emergency_beds()
    solver._emergency_plan_beds(solver.emergency_state)

    arrangements = [
        task.plan for task in solver.tasks if getattr(task, "emergency_dorm", False)
    ]
    assert "银灰" not in {
        name for plan in arrangements for names in plan.values() for name in names
    }
    solver.op_data = solver.op_data.project_arrangements(arrangements)
    assert solver.prepare_release_dorm(release)
    assert release.release_dorm_targets() == {"银灰": (ROOM, 3)}
    assert not solver._emergency_ready()


def test_emergency_does_not_readmit_completed_limit_cycle_or_fabricate_target_mood(
    emergency_solver,
):
    solver = emergency_solver
    data = solver.op_data
    data.update_detail("银灰", 11.8, "", -1, True)
    limited = data.operators["银灰"]
    limited.rest_mood_release_limit = limited.upper_limit
    other = data.operators["絮雨"]
    data.update_detail(other.name, 24, other.current_room, other.current_index, True)
    assert data.rest_mood_complete(limited.name)
    assert not solver._emergency_ready()

    solver._open_emergency_beds()
    solver._emergency_plan_beds(solver.emergency_state)

    assert limited.name not in {
        name for task in solver.tasks for names in task.plan.values() for name in names
    }
    assert limited.current_room == ""
    assert limited.mood == 11.8
    assert solver.emergency_state["targets"][limited.name] == 12
    assert not solver._emergency_ready()


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


@pytest.mark.parametrize("exhaust", [False, True])
@pytest.mark.parametrize("individual", [False, True])
def test_rest_in_full_returns_at_configured_upper_limit(op_data, exhaust, individual):
    data = op_data
    if individual:
        data.config.operator_mood_limits = {"银灰": bounds(2, 12)}
    else:
        data.config.mood_limits = bounds(2, 12)
    data.init_mood_limit()
    op = data.operators["银灰"]
    op.rest_in_full, op.exhaust_require = True, exhaust
    op.mood, op.time_stamp = 6, datetime.now()
    data.operators["空爆"].current_room = ""
    op.current_room, op.current_index = ROOM, 4
    bed = data.dorm[0]
    bed.name, bed.time = op.name, None
    data.refresh_dorm_time(
        ROOM, 4, {"agent": op.name, "time": op.time_stamp + timedelta(hours=3)}
    )
    assert bed.time == op.time_stamp + timedelta(hours=1)
    tasks = plan_metadata(data, [])
    returning = next(t for t in tasks if t.type == TaskTypes.SHIFT_ON)
    # 保留原回满准备提前量；用尽＋回满不提前回岗。
    assert returning.time == bed.time - timedelta(minutes=0 if exhaust else 8)
    if individual:
        release = next(t for t in tasks if t.strict_mood_limit)
        assert release.time == bed.time
    data.config.operator_mood_limits["银灰"] = bounds(2, 18)
    data.init_mood_limit()
    assert bed.time == op.time_stamp + timedelta(hours=2)


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
    expected = pending.time + timedelta(seconds=1) if related else now
    assert task.time == expected


@pytest.mark.parametrize("mode", [1, 2, 3])
def test_mode_changes_override_saved_custom_ranges(legacy_solver, mode):
    data = legacy_solver.op_data
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
