"""令夕上限独立离宿，不等待同组或不养闲人。"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import (  # noqa: E402
    config,
    operators,
    resting_correction,
    scheduler_task,
)
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    merge_release_dorm,
    scheduling,
)

NOW = datetime(2026, 9, 24, 6, 0)


@pytest.fixture(params=[(False, 1), (True, 1), (False, 2), (True, 2)])
def solver(request, monkeypatch):
    experimental, mode = request.param

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    for module in (base, operators, scheduler_task, resting_correction):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    config.conf.experimental_dorm_logic = experimental
    limited = "令" if mode == 1 else "夕"
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room(limited, "感知", ["Mon3tr"])],
                "contact": [Room("絮雨", "感知", ["斥罪"])],
                "dormitory_1": [Room("冰酿", "", []), Room("闪灵", "", [])]
                + [Room("Free", "", []) for _ in range(3)],
            },
            PlanConfig(
                "絮雨", "", "", ling_xi=mode, experimental_dorm_logic=experimental
            ),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    instance.op_data = instance.op_data.project_arrangements(
        [
            {
                "central": ["Mon3tr"],
                "contact": ["斥罪"],
                "dormitory_1": ["冰酿", "闪灵", "絮雨", limited, "Free"],
            }
        ]
    )
    for op in instance.op_data.operators.values():
        op.mood, op.time_stamp = 6, NOW
    for bed in instance.op_data.dorm:
        if bed.name:
            bed.time = NOW + timedelta(minutes=30 if bed.name == limited else 240)
    instance.tasks, instance.task = [], None
    instance.find = MagicMock(return_value=True)
    instance.skip = MagicMock()
    instance.backup_plan_solver = MagicMock(return_value=False)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    return instance


def limited_name(solver):
    return solver.op_data.plan["central"][0].agent


def release(solver):
    return next(t for t in solver.tasks if t.strict_mood_limit)


@pytest.mark.parametrize("free_room", [False, True])
def test_limit_has_independent_release_even_while_group_waits_for_full(
    solver, free_room
):
    data = solver.op_data
    data.config.free_room = free_room
    solver.plan_metadata()
    task = release(solver)
    assert task.type == TaskTypes.RELEASE_DORM
    assert task.meta_data == limited_name(solver)
    assert task.time == NOW + timedelta(minutes=30)
    assert task.plan == {"dormitory_1": ["Current"] * 3 + ["Free", "Current"]}
    group_return = next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)
    assert group_return.time > task.time
    assert limited_name(solver) in group_return.plan["central"]
    assert "絮雨" in group_return.plan["contact"]
    assert data.operators[limited_name(solver)].is_resting()
    solver.plan_metadata()
    assert sum(t.strict_mood_limit for t in solver.tasks) == 1


@pytest.mark.parametrize("mood", [12, 20.8, 24])
def test_observed_limit_or_overdue_timer_releases_immediately(solver, mood):
    solver.op_data.operators[limited_name(solver)].mood = mood
    solver.plan_metadata()
    assert release(solver).time == NOW


def test_overdue_timer_with_old_mood_is_not_lost(solver):
    _, bed = solver.op_data.get_dorm_by_name(limited_name(solver))
    bed.time = NOW - timedelta(minutes=5)
    solver.plan_metadata()
    assert release(solver).time == NOW


def test_unknown_mood_without_timer_does_not_release(solver):
    op = solver.op_data.operators[limited_name(solver)]
    op.mood, op.time_stamp = 24, None
    _, bed = solver.op_data.get_dorm_by_name(op.name)
    bed.time = None
    solver.plan_metadata()
    assert not any(t.strict_mood_limit for t in solver.tasks)


def test_departed_operator_waits_without_recalling_group_or_refilling(solver):
    name = limited_name(solver)
    solver.op_data.operators[name].mood = 20.8
    solver.plan_metadata()
    task = release(solver)
    solver.task = task
    # 用实际选人准备逻辑验证 Free 不会被主班保床恢复成令/夕。
    solver.get_free_list = MagicMock(return_value=[])
    agents = task.plan["dormitory_1"].copy()
    solver.preserve_resting_crafters(agents, "dormitory_1")
    assert agents[3] == "Free"
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    assert solver.op_data.operators[name].current_room == ""
    assert solver.op_data.operators["絮雨"].is_resting()
    solver.task, solver.tasks = None, []
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert all(room.startswith("dorm") for room in correction)
    assert not any(name in names or "絮雨" in names for names in correction.values())
    solver.plan_metadata()
    assert not any(t.strict_mood_limit for t in solver.tasks)
    group_return = next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)
    assert group_return.plan["central"] == [name]
    solver.enter_room.assert_not_called()


def test_full_low_operator_is_not_selected_as_free_filler(solver):
    op = solver.op_data.operators[limited_name(solver)]
    op.operator_type = "low"
    op.current_room, op.current_index = "", -1
    op.mood = 20.8
    assert op.name not in solver.get_free_list([])


def test_equal_mode_removes_old_limit_and_release(solver):
    data = solver.op_data
    data.config.ling_xi = 3
    data.init_mood_limit()
    assert data.operators[limited_name(solver)].upper_limit == 24
    solver.plan_metadata()
    assert not any(t.strict_mood_limit for t in solver.tasks)


def test_strict_release_is_not_delayed_by_merging_or_run_order(solver):
    solver.op_data.operators[limited_name(solver)].mood = 12
    solver.plan_metadata()
    task = release(solver)
    order = SchedulerTask(
        NOW + timedelta(seconds=10), {"room_1_1": ["但书"]}, TaskTypes.RUN_ORDER
    )
    tasks = [task, order]
    merge_release_dorm(tasks, 10)
    scheduling(tasks, time_now=NOW)
    assert task.time == NOW
    assert not task.deferred_by_run_order


def test_rebuild_uses_confirmed_new_bed(solver):
    name = limited_name(solver)
    solver.plan_metadata()
    old = release(solver)
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["Current", "Current", "Current", "Free", name]}]
    )
    solver.plan_metadata()
    if solver.op_data.experimental_dorm_logic:
        # 换床后的旧倒计时失效；实际读房取得新时间后才重建上限任务。
        assert not any(t.strict_mood_limit for t in solver.tasks)
        _, bed = solver.op_data.get_dorm_by_name(name)
        assert bed.time is None
        solver.op_data.refresh_dorm_time(
            *bed.position,
            {"agent": name, "time": NOW + timedelta(hours=3)},
        )
        solver.plan_metadata()
    task = release(solver)
    assert task is not old
    assert task.plan["dormitory_1"] == ["Current"] * 4 + ["Free"]
    # 当前心情 6、上限 12：读到回满 24 需三小时，换算到上限需一小时。
    assert task.time == (
        NOW + timedelta(hours=1) if solver.op_data.experimental_dorm_logic else old.time
    )


@pytest.mark.parametrize("stale", [False, True])
def test_release_execution_reads_remaining_beds_and_ignores_stale_mode(solver, stale):
    name = limited_name(solver)
    solver.op_data.operators[name].mood = 12
    solver.plan_metadata()
    task = release(solver)
    solver.task, solver.tasks = task, [task]
    if stale:
        solver.op_data.config.ling_xi = 3
        solver.op_data.init_mood_limit()

    def arrange(plan, get_time):
        assert get_time is (not stale)
        solver.op_data = solver.op_data.project_arrangements([plan])

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    assert solver.op_data.operators[name].is_resting() is stale
    assert not any(t.strict_mood_limit for t in solver.tasks)
    solver.agent_arrange.assert_called_once()


@pytest.mark.parametrize("mood", [12, 20.8, 11.9])
def test_group_downshift_skips_only_completed_ling_xi_bed(solver, mood):
    data = solver.op_data
    name = limited_name(solver)
    solver.op_data = data.project_arrangements(
        [
            {
                "central": [name],
                "contact": ["絮雨"],
                "dormitory_1": ["Current", "Current", "Free", "Free", "Free"],
            }
        ]
    )
    data = solver.op_data
    data.operators[name].mood = mood
    plan = {}
    solver.get_resting_plan([name, "絮雨"], [], plan, 0)
    assert plan["central"] == ["Mon3tr"]
    assert plan["contact"] == ["斥罪"]
    assert any(b.name == name for b in data.dorm) is (mood < 12)
    assert any(b.name == "絮雨" for b in data.dorm)
    if mood >= 12:
        assert data.assign_dorm(name) is None


def test_dorm_cover_also_rejects_completed_ling_xi(solver):
    data = solver.op_data
    name = limited_name(solver)
    data.operators[name].mood = 12
    resident = data.operators["冰酿"]
    resident.replacement = [name, "Mon3tr"]
    assert data.replacement_candidates(resident) == ["Mon3tr"]
    data.operators["絮雨"].replacement = [name, "Mon3tr"]
    assert name in data.replacement_candidates(data.operators["絮雨"])


def test_selection_rejects_explicit_completed_ling_xi_even_when_preserving(solver):
    class SelectionBoundary(Exception):
        pass

    name = limited_name(solver)
    solver.op_data.operators[name].mood = 12
    solver.op_data.get_current_room = MagicMock(side_effect=SelectionBoundary)
    solver.task = SchedulerTask()
    agents = ["冰酿", "闪灵", "絮雨", name, "Free"]
    with pytest.raises(SelectionBoundary):
        solver.choose_agent(agents, "dormitory_1", preserve_dorm_occupants=True)
    assert name not in agents
    assert agents[3] == "Free"
