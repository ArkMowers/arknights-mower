"""加工入队使用真实心情和任务预约，避免宿舍换班前借走干员。"""

from datetime import datetime

import pytest

from arknights_mower.tests import workshop_queue_tests
from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.config.conf import WorkShopItem
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

queue = workshop_queue_tests.queue


def test_prediction_blocks_operator_whose_cached_mood_is_full(queue):
    data, tasks = queue
    data.operators["年"].current_mood = lambda: 20

    scheduler_task.try_workshop_tasks(data, tasks)

    assert [task.meta_data for task in tasks] == ["泥岩"]


def test_dorm_admission_reservation_blocks_workshop_borrowing(queue):
    data, tasks = queue
    admission = SchedulerTask(
        datetime.now(), {"dormitory_1": ["年"]}, TaskTypes.FILL_DORM
    )
    tasks.append(admission)

    scheduler_task.try_workshop_tasks(data, tasks)

    assert tasks[0] is admission
    assert [task.meta_data for task in tasks if task.type == TaskTypes.WORKSHOP] == [
        "泥岩"
    ]


def test_protected_recovery_cannot_be_interrupted_even_near_full(queue):
    data, tasks = queue
    data.operators["年"].mood = 23
    data.is_rescue_recovering = lambda name: name == "年"

    scheduler_task.try_workshop_tasks(data, tasks)

    assert [task.meta_data for task in tasks] == ["泥岩"]


def test_legacy_unscoped_setting_with_only_forbidden_recipe_is_not_queued(
    queue, caplog
):
    data, tasks = queue
    setting = config.conf.workshop_settings[0].model_copy(
        update={
            "operator": "莱伊",
            "items": [WorkShopItem(item_names=["糖聚块"], upper_limit=10)],
        }
    )
    config.conf.workshop_settings = [setting]
    data.operators["莱伊"] = data.operators["年"]

    scheduler_task.try_workshop_tasks(data, tasks)

    assert tasks == []
    assert setting.items[0].item_names == ["糖聚块"]
    assert "莱伊加工跳过：没有符合干员材料范围" in caplog.text


@pytest.mark.parametrize("reason", ["mood", "unknown", "reserved", "recovery"])
def test_automatic_crafting_reports_operator_block_reason(queue, caplog, reason):
    data, tasks = queue
    if reason == "mood":
        data.operators["年"].current_mood = lambda: 20
        expected = "年加工跳过：心情不足（当前 20.0，需大于 22）"
    elif reason == "unknown":
        data.operators["年"].current_mood = lambda: -1
        expected = "年加工跳过：心情尚未读取"
    elif reason == "reserved":
        tasks.append(
            SchedulerTask(task_plan={"meeting": ["年"]}, task_type=TaskTypes.SHIFT_ON)
        )
        expected = "年加工跳过：已被上班任务预约"
    else:
        data.is_rescue_recovering = lambda name: name == "年"
        expected = "年加工跳过：正在集中恢复"
    scheduler_task.try_workshop_tasks(data, tasks)
    assert expected in caplog.text
    assert [t.meta_data for t in tasks if t.type == TaskTypes.WORKSHOP] == ["泥岩"]
    assert "请检查合成数量" not in caplog.text
