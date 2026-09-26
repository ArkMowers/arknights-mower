"""同宿舍批量清退：不跨任务、逐人复核、失败可重试，最终只安排一次。"""

import copy
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_empty_release_tests
from arknights_mower.utils import config
from arknights_mower.utils.operators import Dormitory
from arknights_mower.utils.plan import Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    merge_release_dorm,
)

solver = dorm_empty_release_tests.solver
op_data = dorm_empty_release_tests.op_data
ROOM = dorm_empty_release_tests.ROOM


@pytest.fixture
def batch_solver(solver):
    instance, selected = solver
    data = instance.op_data
    data.plan[ROOM][3] = Room("Free", "", [])
    data.dorm.insert(
        0, Dormitory((ROOM, 3), "桃金娘", datetime.now() - timedelta(minutes=3))
    )
    data.dorm[1].time = datetime.now() - timedelta(minutes=2)
    start = datetime.now() - timedelta(seconds=2)
    tasks = []
    for i, name in ((3, "桃金娘"), (4, "空爆")):
        plan = ["Current"] * 5
        plan[i] = "Free"
        tasks.append(
            SchedulerTask(
                time=start,
                task_plan={ROOM: plan},
                task_type=TaskTypes.RELEASE_DORM,
                meta_data=name,
            )
        )
    instance.task, instance.tasks = tasks[0], tasks
    return instance, selected


def run_batch(instance, action=None):
    plans = []

    def arrange(plan, get_time):
        plans.append(copy.deepcopy(plan))
        return action(plan) if action else None

    instance.agent_arrange = MagicMock(side_effect=arrange)
    result, get_time = instance.arrange_release_dorm()
    assert get_time
    instance.agent_arrange.assert_called_once()
    return plans[0], result


def test_same_room_release_executes_one_arrangement(batch_solver):
    instance, _ = batch_solver
    instance.find = MagicMock(return_value=True)
    instance.agent_arrange = MagicMock()
    instance.backup_plan_solver = MagicMock(return_value=False)
    instance.plan_metadata = MagicMock()
    instance.skip = MagicMock()
    instance.infra_main()
    instance.agent_arrange.assert_called_once_with(
        {ROOM: ["Current"] * 3 + ["Free", "Free"]}, True
    )
    assert instance.tasks == []


@pytest.mark.parametrize("change", ["moved", "protected", "retained", "unknown"])
def test_batch_ignores_invalid_person_without_cancelling_other(batch_solver, change):
    instance, _ = batch_solver
    data = instance.op_data
    if change == "moved":
        data.operators["空爆"].current_room = "meeting"
    elif change == "protected":
        data.config.free_room_exclusions = ["空爆"]
    elif change == "retained":
        data.operators["空爆"].dorm_mood_fallback = ROOM
    else:
        instance.tasks[1].meta_data = "不存在的干员"
    plan, _ = run_batch(instance)
    assert plan == {ROOM: ["Current"] * 3 + ["Free", "Current"]}
    assert instance.tasks == [instance.task]


@pytest.mark.parametrize(
    "barrier", [TaskTypes.RUN_ORDER, TaskTypes.SHIFT_ON, TaskTypes.FIAMMETTA]
)
def test_batch_does_not_cross_another_task(batch_solver, barrier):
    instance, _ = batch_solver
    middle = SchedulerTask(time=instance.task.time, task_type=barrier)
    instance.tasks.insert(1, middle)
    plan, _ = run_batch(instance)
    assert len(instance.tasks) == 3
    assert plan[ROOM].count("Free") == 1


@pytest.mark.parametrize(
    "boundary", ["strict", "workshop", "other_room", "future", "legacy"]
)
def test_batch_preserves_special_release_boundaries(
    batch_solver, boundary, monkeypatch
):
    instance, _ = batch_solver
    second = instance.tasks[1]
    if boundary == "strict":
        second.strict_mood_limit = True
    elif boundary == "workshop":
        monkeypatch.setattr(
            config,
            "conf",
            SimpleNamespace(workshop_settings=[SimpleNamespace(operator="空爆")]),
        )
    elif boundary == "other_room":
        second.plan = {"dormitory_2": second.plan[ROOM]}
    elif boundary == "legacy":
        instance.op_data.config.experimental_dorm_logic = False
    else:
        second.time = datetime.now() + timedelta(minutes=2)
    plan, _ = run_batch(instance)
    assert len(instance.tasks) == 2
    assert plan[ROOM].count("Free") == 1


@pytest.mark.parametrize("already_full", [True, False])
def test_original_ten_minute_alignment_only_batches_finished_recovery(
    batch_solver, already_full, monkeypatch
):
    instance, _ = batch_solver
    now = datetime.now()
    clock = MagicMock()
    clock.now.return_value = now
    monkeypatch.setattr("arknights_mower.solvers.base_schedule.datetime", clock)
    first, second = instance.tasks
    first.time, second.time = now - timedelta(minutes=5), now
    merge_release_dorm(instance.tasks, 10)
    instance.task = instance.tasks[0]
    assert instance.tasks[1].time == now + timedelta(seconds=1)
    if not already_full:
        _, bed = instance.op_data.get_dorm_by_name(instance.tasks[1].meta_data)
        bed.time = now + timedelta(minutes=1)
    plan, _ = run_batch(instance)
    assert plan[ROOM].count("Free") == (2 if already_full else 1)
    assert len(instance.tasks) == (1 if already_full else 2)


@pytest.mark.parametrize("failed", [False, True])
def test_retry_keeps_individual_tasks_and_rechecks_identity(batch_solver, failed):
    instance, _ = batch_solver
    originals = [(t, t.meta_data, copy.deepcopy(t.plan)) for t in instance.tasks]

    def stop(plan):
        # 点击前失败，或因跑单延期；名单在选人过程中可能已被解析。
        plan[ROOM][-1] = "红"
        if failed:
            raise RuntimeError("选人失败")
        instance.task.time = datetime.now() + timedelta(minutes=10)
        return False

    if failed:
        with pytest.raises(RuntimeError, match="选人失败"):
            run_batch(instance, stop)
    else:
        _, result = run_batch(instance, stop)
        assert result is False
        assert instance.tasks[0].time == instance.tasks[1].time
    for task, name, plan in originals:
        assert task in instance.tasks
        assert task.meta_data == name
        assert task.plan == plan
    instance.op_data.config.free_room_exclusions = ["空爆"]
    plan, _ = run_batch(instance)
    assert plan == {ROOM: ["Current"] * 3 + ["Free", "Current"]}


@pytest.mark.parametrize("tired", [False, True])
def test_batch_fills_beds_without_duplicate_people_or_empty_beds(batch_solver, tired):
    instance, selected = batch_solver
    expected = selected.copy()
    if tired:
        instance.op_data.operators["红"].mood = 10

    def arrange(plan):
        plan[ROOM][:3] = expected[:3]
        instance.choose_agent(plan[ROOM], ROOM)

    run_batch(instance, arrange)
    assert len(set(selected)) == len(selected) == 5
    if tired:
        assert "红" in selected
        assert len({"桃金娘", "空爆"} & set(selected)) == 1
    else:
        assert selected == expected
        assert all(
            instance.op_data.is_full_dorm_fallback(name) for name in expected[3:]
        )


def test_arrange_room_resolves_selection_once_before_recovery_order(solver):
    instance, selected = solver
    instance.op_data.operators["红"].mood = 10
    instance.enter_room = MagicMock()
    instance.back = MagicMock()
    instance.turn_on_room_detail = MagicMock()
    instance.refresh_current_room = MagicMock()
    instance.find = MagicMock(
        side_effect=lambda name, *args, **kwargs: name == "confirm_blue"
    )
    instance.scene = MagicMock(return_value=0)
    instance.tap_confirm = MagicMock()
    instance.get_agent_from_room = MagicMock(
        side_effect=lambda *args: [{"agent": name} for name in selected]
    )
    resolve = instance.prepare_dorm_selection
    instance.prepare_dorm_selection = MagicMock(wraps=resolve)
    seen = []
    instance.ensure_dorm_recovery_order = MagicMock(
        side_effect=lambda room, agents, **kwargs: seen.append(agents.copy()) or False
    )
    instance.agent_arrange_room({}, ROOM, instance.task.plan, get_time=True)
    instance.prepare_dorm_selection.assert_called_once()
    assert seen == [selected]
    assert selected[-1] == "红"
    instance.tap_confirm.assert_called_once()


def test_global_cap_batch_compares_all_residents_and_keeps_full_beds(batch_solver):
    instance, selected = batch_solver
    data = instance.op_data
    data.operators["桃金娘"].operator_type = "low"
    data.operators["桃金娘"].room = ""
    data.plan["meeting"][0].replacement.extend(["桃金娘", "空爆"])
    data.config.mood_limits = {"lower": 0, "upper": 20}
    for name, mood in (("红", 21), ("桃金娘", 23), ("空爆", 24)):
        data.apply_custom_mood_limits(data.operators[name])
        data.operators[name].mood = mood
    fixed = selected[:3]

    def arrange(plan):
        plan[ROOM][:3] = fixed
        instance.choose_agent(plan[ROOM], ROOM)

    run_batch(instance, arrange)
    assert len(selected) == 5
    assert set(selected[3:]) == {"红", "桃金娘"}
    for index, name in enumerate(selected[3:], 3):
        data.update_detail(name, 24, ROOM, index, True)
        assert data.is_full_dorm_fallback(name)


def test_planner_and_selection_share_mood_gap_and_exclusion_rules(solver):
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.scheduler_task import try_add_release_dorm

    instance, _ = solver
    data = instance.op_data
    data.add(Operator("陈", "", mood=12, time_stamp=datetime.now()))
    data.plan["meeting"][0].replacement.append("陈")
    red = data.operators["红"]
    red.mood, red.upper_limit = 10, 12
    data.operators["陈"].lower_limit = 10
    # 相同层级，陈缺12点、红缺2点；不能用原始心情或下限比例决定补床顺序。
    assert instance.get_free_list([]) == ["陈", "红"]
    tasks = []
    try_add_release_dorm({}, None, data, tasks)
    assert tasks[0].plan[ROOM][-1] == "陈"
    # 已排好任务后才加入黑名单，最终解析也必须重新应用相同过滤规则。
    data.config.free_blacklist = ["陈"]
    instance.task = tasks[0]
    agents = tasks[0].plan[ROOM]
    instance.prepare_dorm_selection(agents, ROOM)
    assert agents[-1] == "红"
