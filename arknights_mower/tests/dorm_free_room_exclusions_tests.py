"""不养闲人排除名单：回满保床、仍可上班，个人上限优先。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_empty_release_tests, dorm_release_tests
from arknights_mower.utils.scheduler_task import (
    TaskTypes,
    add_release_dorm,
    generate_plan_by_drom,
    plan_metadata,
    try_add_release_dorm,
)

op_data = dorm_release_tests.op_data
solver = dorm_empty_release_tests.solver
ROOM = dorm_release_tests.ROOM


@pytest.mark.parametrize("mood", [10, 24])
@pytest.mark.parametrize("overdue", [False, True])
def test_excluded_resident_is_never_idle_fill_capacity(op_data, mood, overdue):
    op_data.config.free_room_exclusions = ["空爆"]
    op_data.operators["空爆"].mood = mood
    op_data.dorm[0].time = datetime.now() + timedelta(minutes=-1 if overdue else 60)
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks == []
    assert not op_data._slot_takable(op_data.dorm[0], False, requester="银灰")
    assert not op_data._slot_takable(op_data.dorm[0], True, requester="红")


def test_excluded_resident_has_no_early_release_even_with_future_work(op_data):
    op_data.config.free_room_exclusions = ["空爆"]
    op_data.dorm[0].time = datetime.now() + timedelta(minutes=10)
    tasks = []
    add_release_dorm(tasks, op_data, "空爆")
    try_add_release_dorm(
        {"meeting": ["空爆"]}, datetime.now() + timedelta(hours=1), op_data, tasks
    )
    assert tasks == []
    assert not any(t.type == TaskTypes.RELEASE_DORM for t in plan_metadata(op_data, []))
    releases = {datetime.now(): ([op_data.dorm[0]], None)}
    assert generate_plan_by_drom({}, op_data, release_tasks=releases) == []
    assert op_data.dorm[0].name == "空爆"


@pytest.mark.parametrize("target", ["Free", "空爆", "红"])
def test_full_resident_survives_free_resolution_and_named_selection(solver, target):
    instance, selected = solver
    instance.op_data.config.free_room_exclusions = ["空爆"]
    agents = instance.task.plan[ROOM]
    agents[-1] = target
    instance.choose_agent(agents, ROOM)
    assert agents[-1] == "空爆"
    assert selected == agents


def test_exclusion_does_not_prevent_return_to_work(solver):
    instance, _ = solver
    data = instance.op_data
    data.config.free_room_exclusions = ["银灰"]
    data.operators["空爆"].current_room = ""
    data.operators["银灰"].current_room = ROOM
    data.operators["银灰"].current_index = 4
    data.dorm[0].name = "银灰"
    instance.tasks = plan_metadata(data, [])
    shift = next(t for t in instance.tasks if t.type == TaskTypes.SHIFT_ON)
    assert shift.plan["meeting"] == ["银灰"]
    instance.task = shift
    agents = ["Current"] * 4 + ["Free"]
    instance.preserve_resting_crafters(agents, ROOM)
    assert agents[4] != "银灰"


def test_cached_release_is_cancelled_after_exclusion_enabled(solver):
    instance, _ = solver
    instance.op_data.config.free_room_exclusions = ["空爆"]
    task = instance.task
    instance.tasks = [task]
    instance.find = MagicMock(return_value=True)
    instance.agent_arrange = MagicMock()
    instance.skip = MagicMock()
    instance.infra_main()
    assert task.plan == {}
    assert instance.tasks == []
    assert instance.op_data.operators["空爆"].current_room == ROOM


@pytest.mark.parametrize("mood", [10, 12, 24])
def test_custom_limit_release_still_takes_priority(solver, mood):
    instance, _ = solver
    data = instance.op_data
    data.config.free_room_exclusions = ["空爆"]
    data.plan["meeting"][0].replacement.append("空爆")
    data.config.operator_mood_limits = {"空爆": {"lower": 0, "upper": 12}}
    data.operators["空爆"].upper_limit = 12
    data.operators["空爆"].mood = mood
    data.dorm[0].time = datetime.now() - timedelta(minutes=1)
    tasks = plan_metadata(data, [])
    strict = next(t for t in tasks if t.strict_mood_limit)
    assert strict.meta_data == "空爆"
    instance.task = strict
    agents = strict.plan[ROOM].copy()
    instance.preserve_resting_crafters(agents, ROOM)
    assert agents[-1] != "空爆"


def test_disabling_feature_or_removing_name_restores_takeover(op_data):
    op_data.config.free_room_exclusions = ["空爆"]
    op_data.config.free_room_exclusions.clear()
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"
    op_data.config.free_room_exclusions = ["空爆"]
    op_data.config.experimental_dorm_logic = False
    tasks = []
    try_add_release_dorm({}, None, op_data, tasks)
    assert tasks[0].plan[ROOM][-1] == "红"
    op_data.config.experimental_dorm_logic = True
    op_data.config.free_room = False
    assert not op_data.is_free_room_excluded("空爆")
