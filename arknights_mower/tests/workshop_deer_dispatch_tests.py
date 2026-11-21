"""Manual predecessors and Deer finish before later workers receive live quotas."""

from types import SimpleNamespace

from arknights_mower.utils import config, scheduler_task, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.scheduler_task import TaskTypes


def test_deer_dispatch_waits_for_predecessor_and_replans_from_main_outputs(monkeypatch):
    conf = config.Conf(workshop_auto_active=True)
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    low = WorkShopItem(item_names=["糖组"], children_lower_limit=0, self_upper_limit=1)
    t4 = WorkShopItem(item_names=["异铁块"], children_lower_limit=0, self_upper_limit=1)
    conf.workshop_settings = [
        RIICPart.WorkShopSetting(operator="瑕光", source="mastery", items=[low]),
        RIICPart.WorkShopSetting(operator="九色鹿", source="mastery", items=[low, t4]),
        RIICPart.WorkShopSetting(operator="空爆", source="mastery", items=[low]),
    ]
    stock = {
        "糖组": 0,
        "糖": 112,
        "异铁块": 0,
        "异铁组": 3,
        "全新装置": 3,
        "聚酸酯组": 3,
        "龙门币": 10000,
    }
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    data = SimpleNamespace(
        operators={
            name: SimpleNamespace(mood=24) for name in ("瑕光", "九色鹿", "空爆")
        }
    )
    tasks = []
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [task.meta_data for task in tasks] == ["瑕光"]
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [task.meta_data for task in tasks] == ["瑕光"]
    predecessor = tasks[0]
    data.operators["瑕光"].mood = 0
    scheduler_task.try_workshop_tasks(
        data, tasks, minimum_mood=0, completed_task=predecessor
    )
    assert [task.meta_data for task in tasks] == ["瑕光", "九色鹿"]
    scheduler_task.try_workshop_tasks(data, tasks)
    assert [task.meta_data for task in tasks] == ["瑕光", "九色鹿"]
    # Ignore random byproducts: only the confirmed T4 main output changes stock.
    stock.update({"异铁块": 1})
    data.operators["九色鹿"].mood = 0
    conf.workshop_generation += 1
    conf.workshop_settings = conf.workshop_settings[2:]
    scheduler_task.try_workshop_tasks(
        data, tasks, minimum_mood=0, completed_task=tasks[-1]
    )
    assert [task.meta_data for task in tasks if task.type == TaskTypes.WORKSHOP] == [
        "瑕光",
        "九色鹿",
        "空爆",
    ]


def test_unchanged_quota_does_not_requeue_completed_deer_before_later_worker(
    monkeypatch,
):
    conf = config.Conf(workshop_auto_active=True)
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    fodder = WorkShopItem(
        item_names=["糖组"], children_lower_limit=0, self_upper_limit=1
    )
    elite = WorkShopItem(
        item_names=["异铁块"], children_lower_limit=0, self_upper_limit=1
    )
    conf.workshop_settings = [
        RIICPart.WorkShopSetting(
            operator="九色鹿", source="mastery", items=[fodder, elite]
        ),
        RIICPart.WorkShopSetting(operator="空爆", source="mastery", items=[fodder]),
    ]
    stock = {
        "糖组": 0,
        "糖": 112,
        "异铁块": 0,
        "异铁组": 3,
        "全新装置": 3,
        "聚酸酯组": 3,
        "龙门币": 10000,
    }
    monkeypatch.setattr(scheduler_task, "get_inventory_counts", lambda: stock)
    data = SimpleNamespace(
        operators={name: SimpleNamespace(mood=24) for name in ("九色鹿", "空爆")}
    )
    tasks = []
    scheduler_task.try_workshop_tasks(data, tasks)
    first = tasks[0]
    scheduler_task.try_workshop_tasks(data, tasks, completed_task=first)
    assert [task.meta_data for task in tasks] == ["九色鹿", "空爆"]
    scheduler_task.try_workshop_tasks(data, tasks, completed_task=first)
    assert [task.meta_data for task in tasks] == ["九色鹿", "空爆"]
    # A new quota can admit Deer again; the old task cannot block that generation.
    tasks[:] = [first]
    conf.workshop_generation += 1
    scheduler_task.try_workshop_tasks(data, tasks, completed_task=first)
    assert [task.meta_data for task in tasks] == ["九色鹿", "九色鹿"]
