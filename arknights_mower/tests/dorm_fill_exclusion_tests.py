"""黑名单和零心情工作身份优先于心情、补满和保床。"""

from datetime import datetime

import pytest

from arknights_mower.tests import (
    dorm_empty_release_tests,
    dorm_mood_fallback_tests,
    initial_dorm_mood_tests,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.resting_priority import has_resting_mood
from arknights_mower.utils.scheduler_task import try_add_release_dorm

op_data = dorm_empty_release_tests.op_data
solver = dorm_empty_release_tests.solver
fallback_solver = dorm_mood_fallback_tests.fallback_solver
initial_solver = initial_dorm_mood_tests.solver
ROOM = dorm_empty_release_tests.ROOM


def exclude(data, name, kind):
    if kind == "blacklist":
        data.config.free_blacklist.append(name)
    else:
        data.operators[name].workaholic = True
    # 即使同时配置高优身份，也不能覆盖排除条件。
    data.config.ope_resting_priority.append(name)


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
@pytest.mark.parametrize("mood", [0, 24, None])
def test_empty_bed_filters_excluded_before_mood_sort_and_full_fallback(
    solver, kind, mood
):
    instance, selected = solver
    data = instance.op_data
    data.add(Operator("陈", "", mood=24 if mood is None else mood))
    data.operators["陈"].time_stamp = None if mood is None else datetime.now()
    exclude(data, "陈", kind)
    data.operators["红"].mood = 10 if mood == 0 else 24
    data.update_detail("空爆", 24, "meeting", 0, True)
    selected.pop()
    data.dorm[0].name, data.dorm[0].time = "", None
    assert "陈" not in instance.get_free_list([])
    assert "陈" not in instance.get_free_list([], include_full=True)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"
    instance.task = tasks[0]
    plan = [slot.agent for slot in data.plan[ROOM]][:4] + ["红"]
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert "陈" not in selected


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
def test_game_lowest_excluded_operator_is_never_a_selection_candidate(
    fallback_solver, kind
):
    instance, selected = fallback_solver
    data = instance.op_data
    # 陈21、红23、原住者24；最低者被排除后只能从合格者中比较。
    exclude(data, "陈", kind)
    args = instance.task.plan[ROOM]
    assert set(instance.dorm_mood_fallback_candidates(args, ROOM)) == {"红", "空爆"}
    scan = instance.scan_agent.side_effect
    compared = []

    def select(names, max_agent_count=None, **kwargs):
        if max_agent_count is not None:
            assert "陈" not in names
            compared.append(names.copy())
        return scan(names, max_agent_count=max_agent_count, **kwargs)

    instance.scan_agent.side_effect = select
    instance.choose_agent(args, ROOM)
    assert compared
    assert args[-1] == "红"
    assert "陈" not in selected


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
def test_queued_named_fill_rechecks_exclusion_at_execution(solver, kind):
    instance, selected = solver
    data = instance.op_data
    data.add(Operator("陈", "", mood=0, time_stamp=datetime.now()))
    data.operators["红"].mood = 10
    plan = instance.task.plan[ROOM]
    plan[-1] = "陈"
    exclude(data, "陈", kind)
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == "红"
    assert "陈" not in selected


def test_zero_mood_operator_without_workaholic_setting_can_rest(solver):
    instance, selected = solver
    instance.op_data.operators["红"].mood = 0
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == "红"
    assert selected == plan


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
def test_fixed_dorm_staff_are_not_automatic_fill_candidates(solver, kind):
    instance, selected = solver
    plan = instance.task.plan[ROOM]
    staff = plan[0]
    exclude(instance.op_data, staff, kind)
    instance.choose_agent(plan, ROOM)
    assert plan[0] == staff
    assert selected == plan


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
@pytest.mark.parametrize("alternative", [False, True])
def test_excluded_resident_cannot_be_retained_by_full_or_exemption_flags(
    solver, kind, alternative
):
    instance, selected = solver
    data = instance.op_data
    data.operators["空爆"].dorm_mood_fallback = ROOM
    data.config.free_room_exclusions = ["空爆"]
    exclude(data, "空爆", kind)
    if not alternative:
        exclude(data, "红", kind)
    assert not data.skip_idle_dorm_release("空爆")
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert plan[-1] == ("红" if alternative else "")
    assert "空爆" not in selected


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
@pytest.mark.parametrize("name", ["银灰", "红"])
def test_initial_main_and_priority_replacement_reading_respects_exclusions(
    initial_solver, kind, name
):
    exclude(initial_solver.op_data, name, kind)
    assert initial_solver._read_initial_dorm_mood()
    assert name not in {n for _, names in initial_solver.arranged for n in names}
    assert not has_resting_mood(initial_solver.op_data.operators[name])


@pytest.mark.parametrize("kind", ["blacklist", "workaholic"])
def test_initial_free_only_batch_does_not_reselect_excluded_free_resident(
    initial_solver, kind
):
    for name in initial_solver.missing[1:]:
        initial_solver.op_data.operators[name].time_stamp = datetime.now()
    exclude(initial_solver.op_data, "安赛尔", kind)
    assert initial_solver._read_initial_dorm_mood()
    assert len(initial_solver.arranged) == 1
    names = initial_solver.arranged[0][1]
    assert names[:2] == ["芬", "香草"]
    assert "安赛尔" not in names
