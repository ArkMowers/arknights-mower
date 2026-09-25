"""未知替班入宿读满后，按游戏心情排序换一次；最低者也满就停止。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    add_release_dorm,
    plan_metadata,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


@pytest.fixture
def fallback_solver(solver):
    instance, selected = solver
    data = instance.op_data
    # 首名替班已入宿并读到24；其余两个替班缓存未知。
    data.plan["meeting"][0].replacement.extend(["空爆", "陈"])
    data.add(Operator("陈", ""))
    data.operators["红"].time_stamp = None
    data.config.resting_priority_replacement = ["红"]
    return instance, selected


def select_lowest(instance, selected):
    scan = instance.scan_agent.side_effect
    observed = []

    def game_order(names, max_agent_count=None, **kwargs):
        if max_agent_count is not None:
            # 游戏实测陈的心情更低，即使红的缓存排序、宿舍层级在前。
            observed.append(set(names))
            assert {"红", "陈"} <= set(names)
            names.sort(key=lambda name: name != "陈")
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = game_order
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == "陈"
    assert selected == plan
    assert observed
    assert instance.op_data.operators["陈"].dorm_mood_fallback == ROOM
    return plan


def finish_read(instance, mood):
    data = instance.op_data
    data.update_detail("空爆", 24, "", -1, True)
    data.update_detail("陈", mood, ROOM, 4, True)
    data.dorm[0].name = "陈"
    data.dorm[0].time = datetime.now() + timedelta(minutes=30 if mood < 24 else -1)
    return data


@pytest.mark.parametrize("mood", [24, 10])
def test_game_lowest_full_is_retained_but_unfinished_still_recovers(
    fallback_solver, mood
):
    instance, selected = fallback_solver
    select_lowest(instance, selected)
    data = finish_read(instance, mood)
    assert data.is_full_dorm_fallback("陈") == (mood == 24)
    releases = [t for t in plan_metadata(data, []) if t.meta_data == "陈"]
    assert bool(releases) == (mood < 24)
    if mood == 24:
        for _ in range(3):
            tasks = plan_metadata(data, [])
            try_add_release_dorm({}, None, data, tasks)
            add_release_dorm(tasks, data, "陈")
            assert tasks == []
        agents = instance.task.plan[ROOM].copy()
        agents[-1] = "Free"
        instance.preserve_resting_crafters(agents, ROOM)
        assert agents[-1] == "陈"


def test_retained_full_resident_yields_to_known_tired_operator(fallback_solver):
    instance, selected = fallback_solver
    select_lowest(instance, selected)
    data = finish_read(instance, 24)
    data.operators["红"].mood = 10
    data.operators["红"].time_stamp = datetime.now()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"
    agents = ["Current"] * 4 + ["Free"]
    instance.preserve_resting_crafters(agents, ROOM)
    assert agents[-1] == "红"


def test_strict_limit_wins_over_retaining_full_fallback(fallback_solver):
    instance, selected = fallback_solver
    select_lowest(instance, selected)
    data = finish_read(instance, 24)
    data.config.operator_mood_limits = {"陈": {"lower": 0, "upper": 12}}
    data.operators["陈"].upper_limit = 12
    assert not data.is_full_dorm_fallback("陈")
    task = next(t for t in plan_metadata(data, []) if t.strict_mood_limit)
    assert task.meta_data == "陈"
    instance.task = task
    assert "陈" not in instance.dorm_mood_fallback_candidates(task.plan[ROOM], ROOM)


def test_cached_release_is_cancelled_and_work_clears_retention(fallback_solver):
    instance, selected = fallback_solver
    select_lowest(instance, selected)
    data = finish_read(instance, 24)
    instance.task.meta_data = "陈"
    instance.task.plan[ROOM][-1] = "Free"
    instance.tasks = [instance.task]
    instance.find = MagicMock(return_value=True)
    instance.agent_arrange = MagicMock()
    instance.skip = MagicMock()
    instance.infra_main()
    assert instance.tasks == []
    assert data.operators["陈"].current_room == ROOM
    data.update_detail("陈", 24, "meeting", 0, True)
    assert data.operators["陈"].dorm_mood_fallback == ""


def test_fallback_filters_reserved_blacklisted_working_and_capped(fallback_solver):
    instance, _ = fallback_solver
    data = instance.op_data
    args = instance.task.plan[ROOM]
    assert set(instance.dorm_mood_fallback_candidates(args, ROOM)) == {
        "红",
        "陈",
        "空爆",
    }
    data.config.free_blacklist = ["红"]
    data.operators["陈"].current_room = "meeting"
    assert instance.dorm_mood_fallback_candidates(args, ROOM) == []
    data.operators["陈"].current_room = ""
    data.operators["陈"].time_stamp = datetime.now()
    data.config.operator_mood_limits = {"陈": {"lower": 0, "upper": 12}}
    data.operators["陈"].upper_limit = 12
    assert instance.dorm_mood_fallback_candidates(args, ROOM) == []


@pytest.mark.parametrize("other_limit,expected_blocked", [(20, True), (24, False)])
def test_limit_twenty_clears_lowest_and_only_blocks_reached_limits(
    fallback_solver, other_limit, expected_blocked
):
    instance, selected = fallback_solver
    data = instance.op_data
    for name in ("空爆", "陈", "红"):
        upper = other_limit if name == "红" else 20
        data.config.operator_mood_limits[name] = {"lower": 0, "upper": upper}
        data.operators[name].upper_limit = upper
    instance.task.strict_mood_limit = True
    # 先从真实心情排序里选陈；陈也已到20，只能清出，不能保留。
    select_lowest(instance, selected)
    data = finish_read(instance, 20)
    assert not data.is_full_dorm_fallback("陈")
    assert data.idle_rest_checked("红") == expected_blocked
    strict = next(t for t in plan_metadata(data, []) if t.strict_mood_limit)
    assert strict.meta_data == "陈"
    instance.task = strict
    agents = strict.plan[ROOM].copy()
    instance.preserve_resting_crafters(agents, ROOM)
    assert agents[-1] == ("" if expected_blocked else "Free")
    if expected_blocked:
        data.update_detail("陈", 20, "", -1, True)
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []
        # 后续真实工作/心情读取或提高上限，候选可重新参与。
        data.update_detail("红", 10, "", -1, True)
        assert not data.idle_rest_checked("红")
        assert "红" in instance.get_free_list([])


def test_changed_idle_observation_invalidates_all_full_result(fallback_solver):
    instance, selected = fallback_solver
    select_lowest(instance, selected)
    data = instance.op_data
    data.operators["红"].time_stamp = datetime.now()
    data.operators["红"].mood = 8
    finish_read(instance, 24)
    assert not data.idle_rest_checked("红")
    assert "红" in instance.get_free_list([])


def test_global_limit_only_applies_to_planned_operators(fallback_solver):
    instance, selected = fallback_solver
    data = instance.op_data
    data.config.mood_limits = {"lower": 0, "upper": 20}
    for op in data.operators.values():
        data.apply_custom_mood_limits(op)
    data.add(Operator("伊芙利特", ""))
    assert data.operators["伊芙利特"].upper_limit == 24
    assert not data.has_rest_mood_limit("伊芙利特")
    instance.task.strict_mood_limit = True
    select_lowest(instance, selected)
    data = finish_read(instance, 20)
    assert data.idle_rest_checked("红")
    assert data.is_full_dorm_fallback("陈")
    data.operators["红"].upper_limit = 24
    data.config.operator_mood_limits["红"] = {"lower": 0, "upper": 24}
    assert not data.idle_rest_checked("红")
    assert "红" in instance.get_free_list([])


@pytest.mark.parametrize("other_available", [False, True])
def test_current_resident_can_be_the_lowest_and_stay(fallback_solver, other_available):
    instance, selected = fallback_solver
    data = instance.op_data
    if not other_available:
        data.config.free_blacklist = ["红", "陈"]
    scan = instance.scan_agent.side_effect
    compared = []

    def game_order(names, max_agent_count=None, **kwargs):
        if max_agent_count is not None:
            assert "空爆" in names
            compared.append(set(names))
            names.sort(key=lambda name: name != "空爆")
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = game_order
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert bool(compared) == other_available
    assert selected == plan
    assert plan[-1] == "空爆"
    data.update_detail("空爆", 24, ROOM, 4, True)
    assert data.is_full_dorm_fallback("空爆")
    for _ in range(3):
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []
    if other_available:
        assert data.idle_rest_checked("红")
        assert data.idle_rest_checked("陈")


def test_current_resident_still_respects_upper_limit_and_reservations(fallback_solver):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    instance, _ = fallback_solver
    data = instance.op_data
    args = instance.task.plan[ROOM]
    assert "空爆" in instance.dorm_mood_fallback_candidates(args, ROOM)
    instance.tasks = [
        SchedulerTask(task_plan={"meeting": ["空爆"]}, task_type=TaskTypes.SHIFT_ON)
    ]
    assert "空爆" not in instance.dorm_mood_fallback_candidates(args, ROOM)
    instance.tasks = []
    data.config.operator_mood_limits["空爆"] = {"lower": 0, "upper": 20}
    data.operators["空爆"].upper_limit = 20
    instance.task.strict_mood_limit = True
    assert "空爆" not in instance.dorm_mood_fallback_candidates(args, ROOM)


def test_global_cap_all_above_twenty_keeps_lowest_and_stays_full(fallback_solver):
    instance, selected = fallback_solver
    data = instance.op_data
    data.config.mood_limits = {"lower": 0, "upper": 20}
    for op in data.operators.values():
        data.apply_custom_mood_limits(op)
    for name, mood in (("空爆", 24), ("红", 23), ("陈", 21)):
        data.operators[name].mood = mood
        data.operators[name].time_stamp = datetime.now()
        assert not data.has_rest_mood_limit(name)
    assert data.operators["红"].upper_limit == 20
    select_lowest(instance, selected)
    data = finish_read(instance, 21)
    assert data.is_full_dorm_fallback("陈")
    read_at = data.operators["陈"].time_stamp
    data.correct_dorm()
    assert data.operators["陈"].mood == 21
    assert data.operators["陈"].time_stamp == read_at
    for _ in range(3):
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []
    assert data.operators["陈"].current_room == ROOM


def test_global_cap_empty_bed_uses_lowest_even_above_cap(fallback_solver):
    instance, _ = fallback_solver
    data = instance.op_data
    data.config.mood_limits = {"lower": 0, "upper": 20}
    for op in data.operators.values():
        data.apply_custom_mood_limits(op)
    for name, mood in (("空爆", 24), ("红", 23), ("陈", 21)):
        data.update_detail(name, mood, "", -1, True)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "陈"
    assert data.operators["陈"].upper_limit == 20
    assert instance.get_free_list([], include_full=True)[0] == "陈"
    data.update_detail("陈", 21, ROOM, 4, True)
    assert data.is_full_dorm_fallback("陈")
    assert not any(task.strict_mood_limit for task in plan_metadata(data, []))
