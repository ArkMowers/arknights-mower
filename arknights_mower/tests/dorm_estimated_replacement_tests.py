"""低心情卡片候选仍能替换满员兜底住客，实读与恢复计时保持独立。"""

import copy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.tests.dorm_unregistered_idle_tests import (
    allow_unregistered,
    screen_only,
)
from arknights_mower.utils import scheduler_task
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


def estimated_candidate(instance, monkeypatch, *, registered=True, stopped=True):
    data = instance.op_data
    resident = data.operators["空爆"]
    resident.dorm_mood_fallback = ROOM
    if registered:
        name = "红"
        data.operators[name].time_stamp = None
    else:
        name = "伊芙利特"
        data.operators["红"].current_room = "room_1_1"
        allow_unregistered(monkeypatch, instance, [name])
    data.dorm_mood_estimates[name] = (5, datetime.now())
    if stopped:
        data.stop_idle_dorm_search()
    return name


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("registered", [True, False])
@pytest.mark.parametrize("stopped", [True, False])
def test_low_card_waits_for_normal_release_before_replacing_full_resident(
    solver, monkeypatch, registered, stopped, free_room
):
    instance, selected = solver
    data = instance.op_data
    data.config.free_room = free_room
    name = estimated_candidate(
        instance, monkeypatch, registered=registered, stopped=stopped
    )
    before = copy.deepcopy({key: vars(op) for key, op in data.operators.items()})
    bed_time = data.dorm[0].time
    instance.task = None
    instance.agent_get_mood = MagicMock(return_value={})
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: {})

    instance.plan_solver()

    assert instance.tasks == []
    instance._scan_card_moods.assert_not_called()
    assert {key: vars(op) for key, op in data.operators.items()} == before
    assert data.dorm[0].time == bed_time
    # 卡片预估不解除满员兜底；正常清退另行满足自己的准入条件。
    data.operators["空爆"].dorm_mood_fallback = ""
    task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={ROOM: ["Current"] * 4 + ["Free"]},
        meta_data="空爆",
    )
    assert instance.prepare_release_dorm(task)
    instance.task = task
    screen_only(instance, [name])
    plan = selected[:4] + ["Free"]
    instance.choose_agent(plan, ROOM)
    assert plan == selected
    assert selected[-1] == name
    assert data.operators[name].time_stamp is None
    data.update_detail("空爆", 24, "", -1, True)
    data.update_detail(name, 8, ROOM, 4, True)
    assert not data.is_full_dorm_fallback(name)


@pytest.mark.parametrize(
    "reason",
    ["expired", "future", "full", "blacklist", "reserved", "working", "strict"],
)
def test_ineligible_card_does_not_override_full_resident_retention(
    solver, monkeypatch, reason
):
    instance, _ = solver
    data = instance.op_data
    name = estimated_candidate(instance, monkeypatch)
    now = datetime.now()
    if reason == "expired":
        data.dorm_mood_estimates[name] = (5, now - timedelta(hours=1))
    elif reason == "future":
        data.dorm_mood_estimates[name] = (5, now + timedelta(seconds=1))
    elif reason == "full":
        data.dorm_mood_estimates[name] = (24, now)
    elif reason == "blacklist":
        data.config.free_blacklist = [name]
    elif reason == "reserved":
        instance.tasks = [scheduler_task.SchedulerTask(task_plan={"meeting": [name]})]
    elif reason == "working":
        data.operators[name].current_room = "meeting"
    else:
        data.config.operator_mood_limits[name] = {"lower": 0, "upper": 12}
        data.operators[name].upper_limit = 12
    before = instance.tasks.copy()

    try_add_release_dorm({}, None, data, instance.tasks)

    assert instance.tasks == before
    candidates = instance.get_dorm_candidates(["Free"], room=ROOM)
    assert not instance.dorm_mood_fallback_candidates(["Free"], ROOM, candidates)


def test_low_card_does_not_displace_unfinished_resident(solver, monkeypatch):
    instance, _ = solver
    data = instance.op_data
    estimated_candidate(instance, monkeypatch)
    data.operators["空爆"].mood = 8
    data.dorm[0].time = datetime.now() + timedelta(hours=3)
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks == []
    agents = ["Current"] * 4 + ["Free"]
    instance.prepare_dorm_selection(agents, ROOM)
    assert agents[-1] == "空爆"


@pytest.mark.parametrize("registered", [True, False])
@pytest.mark.parametrize("stopped", [True, False])
def test_dorm_three_execution_does_not_skip_low_card_replacement(
    solver, monkeypatch, caplog, registered, stopped
):
    instance, selected = solver
    data = instance.op_data
    room = "dormitory_3"
    data.plan[room] = data.plan.pop(ROOM)
    for bed in data.dorm:
        bed.position = (room, bed.position[1])
    for op in data.operators.values():
        if op.room == ROOM:
            op.room = room
        if op.current_room == ROOM:
            op.current_room = room
    name = estimated_candidate(
        instance, monkeypatch, registered=registered, stopped=stopped
    )
    data.operators["空爆"].dorm_mood_fallback = room
    instance.task = None
    try_add_release_dorm({}, None, data, instance.tasks)
    assert instance.tasks == []
    data.operators["空爆"].dorm_mood_fallback = ""
    instance.task = SchedulerTask(
        task_type=TaskTypes.RELEASE_DORM,
        task_plan={room: ["Current"] * 4 + ["Free"]},
        meta_data="空爆",
    )
    instance.tasks = [instance.task]
    assert instance.prepare_release_dorm(instance.task)
    screen_only(instance, [name])
    instance.enter_room = MagicMock()
    instance.back = MagicMock()
    instance.turn_on_room_detail = MagicMock()
    instance.refresh_current_room = MagicMock()
    instance.find = MagicMock(
        side_effect=lambda name, *args, **kwargs: name == "confirm_blue"
    )
    instance.scene = MagicMock(return_value=0)
    instance.ensure_dorm_recovery_order = MagicMock(return_value=False)
    instance.tap_confirm = MagicMock()
    instance.get_agent_from_room = MagicMock(
        side_effect=lambda *args, **kwargs: [{"agent": name} for name in selected]
    )

    instance.agent_arrange_room({}, room, instance.task.plan, get_time=True)

    instance.tap_confirm.assert_called_once()
    assert selected[-1] == name
    assert f"任务与当前房间相同，跳过安排{room}人员" not in caplog.text
    assert room not in instance.task.plan
