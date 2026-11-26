"""补位选人首屏发现新候选，保留预约、恢复优先级和搜索边界。"""

from datetime import datetime, timedelta
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
    data.add(
        Operator("陈", "", mood=10, time_stamp=datetime.now() - timedelta(seconds=1))
    )
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

    assert plan == selected and plan[-1] == ("伊芙利特" if vacant else "陈")


@pytest.mark.parametrize("other_measured", [False, True])
@pytest.mark.parametrize(
    ("visible_priority", "expected"),
    [("lower", "红"), ("equal", "红"), ("higher", "伊芙利特")],
)
def test_first_page_competes_with_estimated_named_takeover(
    solver, monkeypatch, visible_priority, expected, other_measured
):
    instance, selected = solver
    data = instance.op_data
    data.config.resting_priority_replacement = ["红"]
    data.config.resting_standby = ["空爆"]
    data.operators["空爆"].mood = 0
    data.operators["红"].time_stamp = None
    data.dorm_mood_estimates["红"] = (22, datetime.now())
    if other_measured:
        data.add(Operator("陈", "", mood=10, time_stamp=datetime.now()))
    if visible_priority == "equal":
        data.plan["meeting"][0].replacement.append("伊芙利特")
        data.config.resting_priority_replacement.append("伊芙利特")
    elif visible_priority == "higher":
        data.config.ope_resting_priority = ["伊芙利特"]
    monkeypatch.setattr(resting_priority, "agent_list", [*data.operators, "伊芙利特"])
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    instance.task = tasks[0]
    plan = instance.task.plan[ROOM]
    assert plan[-1] == "红"
    plan[:4] = selected[:4]
    observations = first_page(instance, monkeypatch, {"伊芙利特": 1})

    instance.choose_agent(plan, ROOM)

    assert observations.count([]) == 1
    assert plan == selected and selected[-1] == expected


@pytest.mark.parametrize("higher_visible", [False, True])
def test_named_takeover_rechecks_resident_after_queueing(
    solver, monkeypatch, higher_visible
):
    instance, selected = solver
    data = instance.op_data
    data.config.resting_priority_replacement = ["红", "陈"]
    data.plan["meeting"][0].replacement.append("陈")
    data.operators["红"].mood = 12
    data.operators["空爆"].mood = 0
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    instance.task = tasks[0]
    plan = instance.task.plan[ROOM]
    assert plan[-1] == "红"
    plan[:4] = selected[:4]

    data.update_detail("空爆", 0, "", -1, True)
    data.add(Operator("陈", ""))
    data.update_detail("陈", 15, ROOM, 4, True)
    assert data.dorm[0].name == "陈"
    if higher_visible:
        data.config.ope_resting_priority = ["伊芙利特"]
    monkeypatch.setattr(resting_priority, "agent_list", [*data.operators, "伊芙利特"])
    first_page(instance, monkeypatch, {"伊芙利特": 1})

    instance.choose_agent(plan, ROOM, fast_mode=False)

    assert plan == selected
    assert selected[-1] == ("伊芙利特" if higher_visible else "陈")


def test_previously_full_operator_uses_new_card_without_overwriting_measurement(
    solver, monkeypatch
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    measured_at = datetime.now() - timedelta(seconds=1)
    data.add(Operator("伊芙利特", "", mood=24, time_stamp=measured_at))
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
@pytest.mark.parametrize("priority_target", [False, True])
def test_recovery_preparation_observes_candidates_with_tier_appropriate_confirmation(
    solver, monkeypatch, previous_mood, priority_target
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    if priority_target:
        data.config.ope_resting_priority = ["陈"]
    if previous_mood is not None:
        data.add(
            Operator(
                "伊芙利特",
                "",
                mood=previous_mood,
                time_stamp=datetime.now() - timedelta(seconds=1),
            )
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

    recovery_ordered = instance.ensure_dorm_recovery_order(ROOM, plan)
    if priority_target:
        assert recovery_ordered == [
            {"agent": name} for name in ("杜林", "闪灵", "爱丽丝", "桃金娘", "陈")
        ]
    else:
        assert recovery_ordered is False
    instance.choose_agent(plan, ROOM, preserve_dorm_occupants=bool(recovery_ordered))

    target = "陈" if priority_target else "伊芙利特"
    assert plan == selected and plan[-1] == target
    assert observations.count([]) == 1
    # 夹具只回读姓名；即使临时选人成功，也没有证明实际恢复速度。
    assert not data.operators[target].dorm_recovery_room
    if priority_target:
        instance.tap_confirm.assert_called_once()
    else:
        instance.tap_confirm.assert_not_called()
    instance.back.assert_not_called()


def test_planned_trade_operator_replaced_when_selection_card_crosses_entry_limit(
    solver, monkeypatch
):
    instance, selected = solver
    cached_idle(instance, monkeypatch)
    data = instance.op_data
    data.add(
        Operator("但书", "", mood=2, time_stamp=datetime.now() - timedelta(seconds=1))
    )
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "但书"
    first_page(instance, monkeypatch, {"但书": 21, "陈": 10})

    instance.choose_agent(plan, ROOM)

    assert plan == selected and plan[-1] == "陈"
    assert data.dorm_mood_estimates["但书"][0] == 21
