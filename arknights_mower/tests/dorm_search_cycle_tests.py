"""空闲者搜索跨宿舍共享，实际轮休／协助位释放和超时才开放新一轮。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.tests import (
    dorm_empty_release_tests,
    exhausted_working_timer_tests,
)
from arknights_mower.tests.dorm_unregistered_idle_tests import (
    allow_unregistered,
    empty_bed,
    screen_only,
)
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
room_reader = exhausted_working_timer_tests.room_reader
ROOM = dorm_empty_release_tests.ROOM


def test_timeout_reopens_release_and_clears_checks_without_changing_beds(solver):
    instance, _ = solver
    data = instance.op_data
    resident = data.operators["空爆"]
    resident.dorm_mood_fallback = ROOM
    peer = data.operators["红"]
    peer.idle_rest_check = (24, peer.mood, peer.time_stamp)
    bed_time = data.dorm[0].time
    stopped = datetime.now() - timedelta(hours=1, seconds=1)
    data.stop_idle_dorm_search(stopped)
    # 重复实读全满不能重新计时。
    data.stop_idle_dorm_search()
    assert data.idle_dorm_search_stopped_at == stopped

    tasks = plan_metadata(data, [])

    assert not data.idle_dorm_search_exhausted
    assert data.idle_dorm_search_stopped_at is None
    assert resident.dorm_mood_fallback == ""
    assert peer.idle_rest_check is None
    assert data.dorm[0].time == bed_time
    assert resident.current_room == ROOM
    assert any(t.type == TaskTypes.RELEASE_DORM for t in tasks)
    # 后续规划不反复清空刚写入的全满保护。
    resident.dorm_mood_fallback = ROOM
    plan_metadata(data, tasks)
    assert resident.dorm_mood_fallback == ROOM


def test_timeout_boundary_and_legacy_mode(op_data):
    now = datetime.now()
    op_data.stop_idle_dorm_search(now)
    assert not op_data.refresh_idle_dorm_search(now=now + timedelta(minutes=59))
    op_data.config.experimental_dorm_logic = False
    assert not op_data.refresh_idle_dorm_search(now=now + timedelta(hours=3))
    op_data.config.experimental_dorm_logic = True
    assert op_data.refresh_idle_dorm_search(now=now + timedelta(minutes=60))
    assert not op_data.refresh_idle_dorm_search(now=now + timedelta(hours=4))


def group_arrangement(instance, task_type=TaskTypes.SHIFT_OFF):
    data = instance.op_data
    for index, name in enumerate(("银灰", "红")):
        op = data.operators[name]
        op.group = "轮休组"
        op.room = "meeting"
        op.operator_type = "high"
        op.current_room = "meeting"
        op.current_index = index
    data.run_order_rooms = {}
    task = SchedulerTask(
        task_type=task_type,
        task_plan={"dormitory_2": ["银灰"], "dormitory_3": ["红"]},
    )
    instance.task = task
    instance.tasks = [task]
    return task


@pytest.mark.parametrize("task_type", [TaskTypes.SHIFT_OFF, TaskTypes.SELF_CORRECTION])
def test_group_refresh_waits_for_all_rooms_and_does_not_repeat(solver, task_type):
    instance, _ = solver
    data = instance.op_data
    task = group_arrangement(instance, task_type)
    data.stop_idle_dorm_search()
    fail_once = True

    def arrange(new_plan, room, plan, **kwargs):
        nonlocal fail_once
        if room == "dormitory_3" and fail_once:
            fail_once = False
            raise RuntimeError("模拟第二间宿舍换人失败")
        name = plan[room][0]
        data.operators[name].current_room = room
        del plan[room]
        return new_plan

    instance.agent_arrange_room = MagicMock(side_effect=arrange)
    with pytest.raises(RuntimeError):
        instance.agent_arrange(task.plan)
    assert data.idle_dorm_search_exhausted
    assert data.operators["银灰"].is_resting()
    assert data.operators["红"].is_working()

    instance.agent_arrange(task.plan)
    assert not data.idle_dorm_search_exhausted
    data.stop_idle_dorm_search()
    # 同任务收尾、重复纠错已经到位的两个人，都不刷新。
    instance._finish_idle_dorm_shift()
    assert data.idle_dorm_search_exhausted
    instance.task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION,
        task_plan={"dormitory_2": ["银灰"], "dormitory_3": ["红"]},
    )
    instance.agent_arrange(instance.task.plan)
    assert data.idle_dorm_search_exhausted


@pytest.mark.parametrize("case", ["single", "fia", "initial", "legacy"])
def test_non_group_or_temporary_arrangement_does_not_refresh(solver, case):
    instance, _ = solver
    data = instance.op_data
    task = group_arrangement(instance)
    if case == "single":
        del task.plan["dormitory_3"]
    elif case == "fia":
        task.type = TaskTypes.FIAMMETTA
    elif case == "initial":
        instance._initial_mood_probe_active = True
    else:
        data.config.experimental_dorm_logic = False
    data.stop_idle_dorm_search()
    instance._track_idle_dorm_shift(task.plan)
    for name in ("银灰", "红"):
        data.operators[name].current_room = "dormitory_2"
    instance._finish_idle_dorm_shift()
    assert data.idle_dorm_search_exhausted


def test_exhausted_search_still_fills_an_empty_bed(solver, monkeypatch):
    instance, selected = solver
    empty_bed(instance, selected)
    data = instance.op_data
    data.stop_idle_dorm_search()
    allow_unregistered(monkeypatch, instance, ["伊芙利特"])
    screen_only(instance, ["伊芙利特"])
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert len(tasks) == 1
    instance.task = tasks[0]
    plan = selected.copy() + ["Free"]
    instance.choose_agent(plan, ROOM)
    assert len(selected) == 5
    assert selected[-1] == "伊芙利特"
    assert data.idle_dorm_search_exhausted


def test_stop_is_shared_across_rooms_and_reset_restores_unknown_search(
    solver, monkeypatch
):
    instance, _ = solver
    data = instance.op_data
    allow_unregistered(monkeypatch, instance, ["伊芙利特"])
    data.add(Operator("陈", "", current_room="dormitory_2", current_index=4))
    for room, name in ((ROOM, "空爆"), ("dormitory_2", "陈")):
        instance.task = SchedulerTask(task_type=TaskTypes.RELEASE_DORM, meta_data=name)
        assert instance.dorm_mood_fallback_candidates(["Free"], room)
    data.stop_idle_dorm_search()
    for room, name in ((ROOM, "空爆"), ("dormitory_2", "陈")):
        instance.task = SchedulerTask(task_type=TaskTypes.RELEASE_DORM, meta_data=name)
        assert not instance.dorm_mood_fallback_candidates(["Free"], room)
    data.refresh_idle_dorm_search(reason="专精协助位干员已释放")
    assert instance.dorm_mood_fallback_candidates(["Free"], "dormitory_2")


@pytest.mark.parametrize("case", ["released", "unchanged", "initial", "fia"])
def test_actual_training_read_reopens_once_without_workshop_configuration(
    op_data, room_reader, case
):
    data = op_data
    old = data.operators["空爆"]
    old.current_room, old.current_index = "train", 0
    incoming = "空爆" if case == "unchanged" else "红"
    instance, _, _ = room_reader(room="train", name=incoming, mood=8)
    instance.op_data = data
    if case == "initial":
        instance.defer_backup_plan_until_mood_read = True
    elif case == "fia":
        instance.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    data.stop_idle_dorm_search()

    instance.get_agent_from_room("train", [0])

    assert data.idle_dorm_search_exhausted == (case != "released")
    if case == "released":
        assert old.current_room == ""
        data.stop_idle_dorm_search()
        instance.get_agent_from_room("train", [0])
        assert data.idle_dorm_search_exhausted


def test_restart_preserves_search_deadline_and_full_resident_protection(
    solver, monkeypatch
):
    import copy
    import pickle
    from threading import Event

    from arknights_mower import __main__ as main
    from arknights_mower.solvers.record import current_state

    instance, _ = solver
    data = instance.op_data
    stopped = datetime.now() - timedelta(hours=1)
    data.stop_idle_dorm_search(stopped)
    data.operators["空爆"].dorm_mood_fallback = ROOM
    peer = data.operators["红"]
    peer.idle_rest_check = (24, peer.mood, peer.time_stamp)
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(instance, attr, 0)
    monkeypatch.setattr(main, "base_scheduler", instance)
    saved = pickle.loads(pickle.dumps(current_state()))
    assert saved["idle_dorm_search_stopped_at"] == stopped

    fresh = copy.deepcopy(data)
    fresh.refresh_idle_dorm_search(reason="模拟重启前的新对象")
    restarted = object.__new__(BaseSchedulerSolver)
    restarted.op_data = fresh
    restarted.initialize_operators = MagicMock(return_value=None)
    fresh.validate_backup_plans = MagicMock(return_value={"success": True})
    monkeypatch.setattr(main, "initialize", MagicMock(return_value=restarted))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.config.conf, "close_simulator_when_idle", False)

    class ReachedScheduling(BaseException):
        pass

    monkeypatch.setattr(
        main, "refresh_resource_at_boundary", MagicMock(side_effect=ReachedScheduling)
    )
    with pytest.raises(ReachedScheduling):
        main.simulate(saved)
    assert fresh.idle_dorm_search_exhausted
    assert fresh.idle_dorm_search_stopped_at == stopped
    assert fresh.is_full_dorm_fallback("空爆")
    assert fresh.idle_rest_checked("红")
    assert not fresh.refresh_idle_dorm_search(now=stopped + timedelta(minutes=59))
    assert fresh.refresh_idle_dorm_search(now=stopped + timedelta(minutes=60))
