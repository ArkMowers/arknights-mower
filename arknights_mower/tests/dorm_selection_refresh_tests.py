"""补位选人首屏发现新候选，保留预约、恢复优先级和搜索边界。"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import AgentSelectionPageChanged
from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils import resting_priority
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

pytestmark = pytest.mark.usefixtures("offline_maintenance")

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


def first_page(instance, monkeypatch, moods):
    page = [(name, ((i, 32), (i + 189, 64))) for i, name in enumerate(moods)]
    monkeypatch.setattr(
        base_mixin,
        "estimate_agent_mood",
        lambda image, scope: moods[page[scope[0][0]][0]],
    )
    scan = instance.scan_agent.side_effect
    observations = []

    def visible(names, **kwargs):
        observations.append(names.copy())
        selected, _ = scan(names, **kwargs)
        return selected, page

    instance.scan_agent.side_effect = visible
    return observations


def cached_idle(instance, monkeypatch):
    data = instance.op_data
    data.operators["红"].current_room = "meeting"
    data.add(Operator("陈", "", mood=10, time_stamp=datetime.now()))
    monkeypatch.setattr(resting_priority, "agent_list", [*data.operators, "伊芙利特"])


@pytest.mark.parametrize("pre_resolve", [False, True])
def test_new_low_idle_competes_with_cached_idle_on_first_page(
    solver, monkeypatch, pre_resolve
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    observations = first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})
    plan = instance.task.plan[ROOM]
    if pre_resolve:
        instance.preserve_resting_crafters(plan, ROOM)
        assert plan[-1] == "陈"

    instance.choose_agent(plan, ROOM)

    assert plan == selected
    assert plan[-1] == "伊芙利特"
    incoming = instance.op_data.operators["伊芙利特"]
    assert incoming.time_stamp is None
    assert incoming.mood == 24
    assert instance.op_data.dorm_mood_estimates["伊芙利特"][0] == 1
    assert observations.count([]) == 1
    instance.swipe_agent_page.assert_not_called()


@pytest.mark.parametrize("vacant", [False, True])
def test_planned_named_fill_rechecks_its_original_ordinary_candidate(
    solver, monkeypatch, vacant
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    if vacant:
        data.update_detail("空爆", 24, "", -1, True)
        selected.pop()
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    instance.task = tasks[0]
    plan = instance.task.plan[ROOM]
    assert plan[-1] == "陈"
    plan[:4] = selected[:4]
    first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "伊芙利特"


def test_previously_full_operator_uses_new_card_without_overwriting_measurement(
    solver, monkeypatch
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    data.add(Operator("伊芙利特", "", mood=24, time_stamp=datetime.now()))
    measured_at = data.operators["伊芙利特"].time_stamp
    first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "伊芙利特"
    assert data.operators["伊芙利特"].mood == 24
    assert data.operators["伊芙利特"].time_stamp == measured_at


def test_new_operator_outside_first_page_does_not_expand_observation(
    solver, monkeypatch
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    first_page(instance, monkeypatch, {"陈": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "陈"
    assert "伊芙利特" not in instance.op_data.operators
    assert "伊芙利特" not in instance.op_data.dorm_mood_estimates
    instance.swipe_agent_page.assert_not_called()


def test_cached_replacement_keeps_priority_over_new_lower_mood_idle(
    solver, monkeypatch
):
    instance, selected = solver
    data = instance.op_data
    data.operators["红"].mood = 10
    monkeypatch.setattr(resting_priority, "agent_list", [*data.operators, "伊芙利特"])
    first_page(instance, monkeypatch, {"伊芙利特": 1, "红": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "红"
    assert data.dorm_mood_estimates["伊芙利特"][0] == 1


@pytest.mark.parametrize(
    "blocked", ["blacklist", "workaholic", "reservation", "working"]
)
def test_first_page_preserves_shared_candidate_exclusions(solver, monkeypatch, blocked):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    if blocked == "blacklist":
        data.config.free_blacklist = ["伊芙利特"]
    elif blocked == "workaholic":
        data.config.workaholic = ["伊芙利特"]
    elif blocked == "reservation":
        instance.tasks = [SchedulerTask(task_plan={"meeting": ["伊芙利特"]})]
    else:
        data.add(Operator("伊芙利特", "", current_room="room_1_1", current_index=0))
    first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "陈"
    assert "伊芙利特" not in data.dorm_mood_estimates


@pytest.mark.parametrize("mood", [None, 24])
def test_unreadable_or_full_new_card_keeps_cached_recovery(solver, monkeypatch, mood):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    first_page(instance, monkeypatch, {"伊芙利特": mood, "陈": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "陈"
    assert "伊芙利特" not in instance.op_data.operators
    instance.swipe_agent_page.assert_not_called()


def test_new_low_card_does_not_displace_unfinished_resident(solver, monkeypatch):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    data.operators["空爆"].mood = 8
    instance.task.type = TaskTypes.NOT_SPECIFIC
    instance.task.meta_data = ""
    first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})
    plan = instance.task.plan[ROOM]

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "空爆"
    assert data.operators["空爆"].current_room == ROOM


@pytest.mark.parametrize(
    "protected", ["exhausted", "fiammetta", "recovery", "expected"]
)
def test_protected_selection_does_not_open_new_search(solver, monkeypatch, protected):
    instance, _ = solver
    cached_idle(instance, monkeypatch)
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    if protected == "exhausted":
        instance.op_data.idle_dorm_search_exhausted = True
    elif protected == "fiammetta":
        instance.task.type = TaskTypes.FIAMMETTA
    elif protected == "expected":
        instance.task.group_shift_expected = {(ROOM, 4): "陈"}
    first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})

    instance.choose_agent(plan, ROOM, preserve_dorm_occupants=protected == "recovery")

    assert plan[-1] == "陈"
    assert "伊芙利特" not in instance.op_data.dorm_mood_estimates


def test_page_exit_preserves_original_task_identity_and_named_plan(solver, monkeypatch):
    instance, _ = solver
    cached_idle(instance, monkeypatch)
    task = instance.task
    original_time = task.time
    plan = task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    original = plan.copy()
    instance.scan_agent = MagicMock(side_effect=AgentSelectionPageChanged("页面退出"))

    with pytest.raises(AgentSelectionPageChanged):
        instance.choose_agent(plan, ROOM)

    assert instance.task is task and task.time == original_time
    assert task.plan[ROOM] == original
    assert plan == original


@pytest.mark.parametrize("previous_mood", [None, 18])
def test_single_target_preparation_observes_new_candidate_before_confirmation(
    solver, monkeypatch, previous_mood
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    if previous_mood is not None:
        data.add(
            Operator("伊芙利特", "", mood=previous_mood, time_stamp=datetime.now())
        )
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "陈"
    observations = first_page(instance, monkeypatch, {"伊芙利特": 1, "陈": 10})
    instance.find = MagicMock(side_effect=lambda resource: resource == "confirm_blue")
    instance.get_agent_from_room = MagicMock(
        side_effect=lambda room, **kwargs: [
            {"agent": name} for name in kwargs.get("expected_agents", selected)
        ]
    )
    instance.back = MagicMock()
    instance.tap_confirm = MagicMock()

    assert instance.ensure_dorm_recovery_order(ROOM, plan)
    instance.choose_agent(plan, ROOM, preserve_dorm_occupants=True)

    assert plan == selected and plan[-1] == "伊芙利特"
    assert observations.count([]) == 1
    assert data.operators["伊芙利特"].dorm_recovery_room == (
        ROOM if previous_mood is not None else ""
    )
    if previous_mood is None:
        instance.tap_confirm.assert_not_called()
        instance.back.assert_called_once()
    else:
        instance.tap_confirm.assert_called_once()
