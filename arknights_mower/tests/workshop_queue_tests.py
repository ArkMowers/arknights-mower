"""Delayed workshop tasks must not be regenerated on every planning pass."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config.conf, "workshop_auto_active", False)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    settings = [
        RIICPart.WorkShopSetting(
            operator=name,
            items=[WorkShopItem(item_names=["双极纳米片"], upper_limit=10)],
        )
        for name in ("年", "泥岩")
    ]
    monkeypatch.setattr(config.conf, "workshop_settings", settings)
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: {"糖": 100})
    from arknights_mower.utils import workshop_limits, workshop_recommendation

    monkeypatch.setattr(workshop_limits, "batch_limit", lambda *args: 1)
    monkeypatch.setattr(
        workshop_recommendation, "prioritize_workshop_settings", lambda items: items
    )
    data = SimpleNamespace(
        operators={item.operator: SimpleNamespace(mood=24) for item in settings}
    )
    return data, []


def test_repeated_planning_after_run_order_delay_keeps_one_task_per_operator(queue):
    data, tasks = queue
    scheduler_task.try_workshop_tasks(data, tasks)
    original = list(tasks)
    for _ in range(5):
        # 跑单把加工延至五分钟之后，plan_solver 会再次进入加工任务生成。
        for task in tasks:
            task.time = datetime.now() + timedelta(minutes=8)
        scheduler_task.try_workshop_tasks(data, tasks)
    assert len(tasks) == 2
    assert all(task is expected for task, expected in zip(tasks, original))


def test_real_run_order_scheduler_does_not_cause_repeated_workshop_batches(
    queue, monkeypatch
):
    data, tasks = queue
    names = [
        "谬因",
        "蜜莓",
        "缇缇",
        "凯尔希·思衡托",
        "空爆",
        "苏苏洛",
        "莱伊",
        "锡兰",
        "陨星",
    ]
    template = config.conf.workshop_settings[0]
    for name in names:
        config.conf.workshop_settings.append(
            template.model_copy(update={"operator": name})
        )
        data.operators[name] = SimpleNamespace(mood=24)
    now = datetime.now()
    tasks.append(
        SchedulerTask(
            time=now + timedelta(minutes=8),
            task_type=TaskTypes.RUN_ORDER,
            task_plan={"room_2_1": ["但书"]},
            meta_data="room_2_1",
        )
    )
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    for _ in range(3):
        # 与 plan_solver 相同的五分钟入口，以及真实的跑单推迟逻辑。
        assert scheduler_task.find_next_task(tasks, now + timedelta(minutes=5)) is None
        scheduler_task.try_workshop_tasks(data, tasks)
        scheduler_task.scheduling(tasks, time_now=now)
        pending = [task for task in tasks if task.type == TaskTypes.WORKSHOP]
        assert len(pending) == 11
        assert all(task.time > now + timedelta(minutes=5) for task in pending)


def test_pending_task_only_blocks_same_operator_and_completion_allows_next_run(queue):
    data, tasks = queue
    scheduler_task.try_workshop_tasks(data, tasks)
    remaining = tasks.pop()
    tasks[:] = [remaining]
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [task.meta_data for task in tasks] == ["泥岩", "年"]
    assert tasks[0] is remaining


def test_duplicate_settings_do_not_create_duplicate_tasks(queue):
    data, tasks = queue
    config.conf.workshop_settings *= 2
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [task.meta_data for task in tasks] == ["年", "泥岩"]


@pytest.mark.parametrize("stale", [False, True])
def test_only_current_generation_blocks_new_automatic_work(queue, stale):
    data, tasks = queue
    config.conf.workshop_auto_active = True
    config.conf.workshop_generation = 10
    old = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="年")
    old.workshop_generation = 9 if stale else 10
    tasks.append(old)
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [t.meta_data for t in tasks] == (
        ["年", "年", "泥岩"] if stale else ["年", "泥岩"]
    )


def test_non_workshop_task_for_same_operator_does_not_block(queue):
    data, tasks = queue
    tasks.append(SchedulerTask(task_type=TaskTypes.RELEASE_DORM, meta_data="年"))
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [t.meta_data for t in tasks if t.type == TaskTypes.WORKSHOP] == [
        "年",
        "泥岩",
    ]
