"""缓存候选耗尽时，Free 复用游戏选人页寻找未登记的空闲干员。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils import resting_priority, scheduler_task
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    plan_metadata,
    try_add_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


def allow_unregistered(monkeypatch, instance, names):
    monkeypatch.setattr(
        resting_priority, "agent_list", [*instance.op_data.operators, *names]
    )


def screen_only(instance, owned):
    scan = instance.scan_agent

    def select(names, **kwargs):
        return scan([name for name in owned if name in names], **kwargs)

    instance.scan_agent = MagicMock(side_effect=select)


def empty_bed(instance, selected):
    data = instance.op_data
    # 现有空闲替班都在工作，只能从游戏页面补床。
    data.update_detail("空爆", 24, "meeting", 0, True)
    data.operators["红"].current_room = "room_1_1"
    selected.pop()


@pytest.mark.parametrize("mood", [8, 24])
def test_empty_bed_uses_actual_owned_operator_and_registers_after_selection(
    solver, monkeypatch, mood
):
    instance, selected = solver
    data = instance.op_data
    empty_bed(instance, selected)
    # 名单中的陈并未持有，不能提前把他写进补床任务。
    allow_unregistered(monkeypatch, instance, ["陈", "伊芙利特"])
    screen_only(instance, ["伊芙利特"])
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert [task.plan for task in tasks] == [{ROOM: ["Current"] * 4 + ["Free"]}]
    assert "伊芙利特" not in data.operators
    instance.task = tasks[0]
    plan = selected.copy() + ["Free"]
    instance.choose_agent(plan, ROOM)
    assert plan == selected
    assert plan[-1] == "伊芙利特"
    assert "陈" not in data.operators
    assert data.operators["伊芙利特"].time_stamp is None
    data.update_detail("伊芙利特", mood, ROOM, 4, True)
    assert data.is_full_dorm_fallback("伊芙利特") == (mood == 24)
    if mood == 24:
        tasks = plan_metadata(data, [])
        try_add_release_dorm({}, None, data, tasks)
        assert tasks == []


def test_strict_cap_release_fills_with_unregistered_idle_operator(solver, monkeypatch):
    instance, selected = solver
    data = instance.op_data
    data.plan["meeting"][0].replacement.append("空爆")
    data.config.operator_mood_limits["空爆"] = {"lower": 0, "upper": 12}
    data.operators["空爆"].upper_limit = 12
    instance.task.strict_mood_limit = True
    data.operators["红"].current_room = "room_1_1"
    allow_unregistered(monkeypatch, instance, ["伊芙利特"])
    screen_only(instance, ["伊芙利特"])
    plan = instance.task.plan[ROOM]
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert plan[-1] == "伊芙利特"
    assert "空爆" not in selected


def test_multiple_empty_beds_choose_distinct_idle_operators(solver, monkeypatch):
    instance, selected = solver
    empty_bed(instance, selected)
    data = instance.op_data
    from arknights_mower.utils.plan import Room

    data.plan[ROOM][3] = Room("Free", "", [])
    data.update_detail("桃金娘", 24, "room_1_2", 0, True)
    selected.pop()
    allow_unregistered(monkeypatch, instance, ["伊芙利特", "妮芙"])
    # 游戏心情排序与图鉴顺序不同，应按屏幕顺序选。
    screen_only(instance, ["妮芙", "伊芙利特"])
    plan = selected.copy() + ["Free", "Free"]
    instance.task = SchedulerTask(task_plan={ROOM: plan})
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert plan[-2:] == ["妮芙", "伊芙利特"]


def test_unregistered_fallback_respects_exclusions_and_pending_tasks(
    solver, monkeypatch
):
    instance, _ = solver
    data = instance.op_data
    allow_unregistered(monkeypatch, instance, ["伊芙利特", "妮芙", "特米米", "深靛"])
    data.config.free_blacklist = ["妮芙"]
    data.config.workaholic = ["特米米"]
    instance.tasks = [SchedulerTask(task_plan={"meeting": ["深靛"]})]
    candidates = instance.get_free_list([], include_full=True)
    assert "伊芙利特" in candidates
    assert not {"妮芙", "特米米", "深靛"} & set(candidates)
    assert "伊芙利特" not in instance.get_free_list([])


def test_fallback_does_not_clear_full_resident_to_try_unregistered_operators(
    solver, monkeypatch
):
    instance, _ = solver
    allow_unregistered(monkeypatch, instance, ["伊芙利特"])
    plan = instance.task.plan[ROOM]
    instance.preserve_resting_crafters(plan, ROOM)
    assert plan[-1] == "空爆"


def test_missing_owned_candidate_stops_search_without_registering_catalogue(
    solver, monkeypatch
):
    instance, selected = solver
    empty_bed(instance, selected)
    allow_unregistered(monkeypatch, instance, ["陈"])
    screen_only(instance, [])
    plan = selected.copy() + ["Free"]
    instance.task = SchedulerTask(task_plan={ROOM: plan})
    with pytest.raises(Exception, match="列表已到末尾|足够的可用宿舍"):
        instance.choose_agent(plan, ROOM)
    assert "陈" not in instance.op_data.operators


@pytest.mark.parametrize("cached_mood", [None, 10, 21])
def test_daily_planner_refills_vacancy_even_without_low_mood_shift(
    solver, monkeypatch, cached_mood
):
    instance, selected = solver
    data = instance.op_data
    empty_bed(instance, selected)
    data.operators["银灰"].current_room = "meeting"
    cached_candidate = cached_mood is not None
    if cached_candidate:
        data.operators["红"].current_room = ""
        # 下班阈值之上和之下都统一生成补位，不能再产生会被跑单延期的重排。
        data.operators["红"].mood = cached_mood
    else:
        allow_unregistered(monkeypatch, instance, ["伊芙利特"])
        screen_only(instance, ["伊芙利特"])
    instance.task = None
    # 隔离设备读屏和无关的仓库读取；实际运行宿舍规划、任务生成和 Free 选人。
    instance.agent_get_mood = MagicMock(return_value={})
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: {})
    instance.plan_solver()
    assert len(instance.tasks) == 1
    assert instance.tasks[0].type == TaskTypes.FILL_DORM
    assert instance.tasks[0].plan == {
        ROOM: ["Current"] * 4 + ["红" if cached_candidate else "Free"]
    }
    instance.task = instance.tasks[0]
    plan = selected.copy() + [instance.task.plan[ROOM][-1]]
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert len(selected) == 5
    assert selected[-1] == ("红" if cached_candidate else "伊芙利特")


@pytest.mark.parametrize("order_delay", [-10, 30, 120])
@pytest.mark.parametrize("cached_mood", [None, 10, 21])
def test_daily_vacancy_fills_before_nearby_or_due_run_order(
    solver, monkeypatch, order_delay, cached_mood
):
    instance, selected = solver
    empty_bed(instance, selected)
    instance.op_data.operators["银灰"].current_room = "meeting"
    target = "伊芙利特" if cached_mood is None else "红"
    if cached_mood is None:
        allow_unregistered(monkeypatch, instance, [target])
    else:
        instance.op_data.operators[target].current_room = ""
        instance.op_data.operators[target].mood = cached_mood
    order = SchedulerTask(
        time=datetime.now() + timedelta(seconds=order_delay),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
    )
    instance.tasks = [order]
    instance.task = None
    instance.agent_get_mood = MagicMock(return_value={})
    instance.plan_solver()
    fill = next(task for task in instance.tasks if task.type == TaskTypes.FILL_DORM)
    assert fill.plan == {
        ROOM: ["Current"] * 4 + ["Free" if cached_mood is None else target]
    }
    original_order_time = order.time
    scheduler_task.scheduling(instance.tasks)
    assert instance.tasks[0] is fill
    assert order.time == original_order_time
    assert not scheduler_task.defer_dorm_before_run_order(fill, instance.tasks, ROOM)
    instance.task = fill
    plan = selected.copy() + [fill.plan[ROOM][-1]]
    if cached_mood is None:
        screen_only(instance, [target])
    instance.choose_agent(plan, ROOM)
    assert selected == plan
    assert len(selected) == 5
    assert selected[-1] == target


def test_unknown_vacancy_fill_is_reserved_once_without_deferral_event(
    solver, monkeypatch
):
    instance, selected = solver
    empty_bed(instance, selected)
    allow_unregistered(monkeypatch, instance, ["伊芙利特"])
    order = SchedulerTask(
        time=datetime.now() + timedelta(seconds=5), task_type=TaskTypes.RUN_ORDER
    )
    instance.tasks, instance.task = [order], None
    assert instance._fill_empty_dorms()
    assert not instance._fill_empty_dorms()
    assert len(instance.tasks) == 2
    fill = next(t for t in instance.tasks if t.type == TaskTypes.FILL_DORM)
    assert fill.plan[ROOM][-1] == "Free"


def test_full_dorm_keeps_nearby_order_guard(solver):
    instance, _ = solver
    instance.op_data.operators["银灰"].current_room = "meeting"
    instance.op_data.operators["红"].mood = 21
    order = SchedulerTask(
        time=datetime.now() + timedelta(seconds=30), task_type=TaskTypes.RUN_ORDER
    )
    instance.tasks, instance.task = [order], None
    instance.agent_get_mood = MagicMock(return_value={})
    instance.plan_solver()
    assert order in instance.tasks
    assert not any(
        task.type in (TaskTypes.FILL_DORM, TaskTypes.NOT_SPECIFIC)
        for task in instance.tasks
    )
    scheduler_task.scheduling(instance.tasks)
    assert instance.tasks[0] is order


def test_priority_vacancy_plan_does_not_include_ordinary_full_resident_release(solver):
    from arknights_mower.utils.operators import Dormitory, Operator
    from arknights_mower.utils.plan import Room

    instance, selected = solver
    data = instance.op_data
    empty_bed(instance, selected)
    data.plan[ROOM][3] = Room("Free", "", [])
    data.dorm.insert(
        0, Dormitory((ROOM, 3), "桃金娘", datetime.now() - timedelta(minutes=1))
    )
    data.operators["红"].current_room = ""
    data.operators["红"].mood = 10
    data.add(Operator("陈", "", mood=12, time_stamp=datetime.now()))
    data.plan["meeting"][0].replacement.append("陈")
    instance.tasks, instance.task = [], None
    assert instance._fill_empty_dorms()
    assert instance.tasks[0].type == TaskTypes.FILL_DORM
    assert instance.tasks[0].plan == {ROOM: ["Current"] * 4 + ["红"]}


@pytest.mark.parametrize(
    "blocked", ["disabled", "personal_cap", "reserved", "stale_empty", "initializing"]
)
def test_vacancy_priority_keeps_existing_admission_guards(solver, blocked):
    instance, selected = solver
    data = instance.op_data
    empty_bed(instance, selected)
    data.operators["红"].current_room = ""
    data.operators["红"].mood = 24
    instance.tasks, instance.task = [], None
    if blocked == "initializing":
        instance.defer_backup_plan_until_mood_read = True
    elif blocked == "disabled":
        data.config.free_room = False
    elif blocked == "personal_cap":
        data.config.operator_mood_limits["红"] = {"lower": 0, "upper": 12}
        data.operators["红"].upper_limit = 12
    elif blocked == "reserved":
        instance.tasks = [SchedulerTask(task_plan={ROOM: ["Current"] * 4 + ["红"]})]
    else:
        # 床位记录虽然空了，实际位置缓存仍有人，不能误当空床插队换人。
        data.operators["空爆"]._current_room = ROOM
        data.operators["空爆"].current_index = 4
    assert not instance._fill_empty_dorms()
