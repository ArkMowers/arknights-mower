"""加工入队核验心情和任务预约，避免宿舍换班前借走干员。"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests import workshop_queue_tests
from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.config.conf import WorkShopItem
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.utils.workshop_limits import (
    workshop_candidate_mood,
    workshop_operator_block_reason,
)

queue = workshop_queue_tests.queue


def test_prediction_blocks_operator_whose_cached_mood_is_full(queue):
    data, tasks = queue
    data.operators["年"].current_mood = lambda: 20

    scheduler_task.try_workshop_tasks(data, tasks)

    assert [task.meta_data for task in tasks] == ["泥岩"]


def test_calculated_workshop_mood_uses_model_for_operator_missing_from_cache():
    calculated = Mock(return_value=17)
    data = SimpleNamespace(
        operators={},
        mood_calculation_enabled=True,
        calculated_mood=calculated,
    )

    assert workshop_candidate_mood(data, "演算干员") == 17
    calculated.assert_called_once_with("演算干员")


def test_calculated_workshop_admission_accepts_model_value_without_operator_object():
    data = SimpleNamespace(
        operators={},
        mood_calculation_enabled=True,
        calculated_mood=Mock(return_value=24),
    )

    assert (
        workshop_operator_block_reason(
            data, "演算干员", minimum_mood=22, require_known_mood=True
        )
        is None
    )


def test_calculated_workshop_mood_does_not_fall_back_to_stale_operator_or_card():
    data = SimpleNamespace(
        operators={"演算干员": SimpleNamespace(mood=24, current_mood=lambda: -1)},
        mood_calculation_enabled=True,
        calculated_mood=Mock(return_value=None),
        dorm_mood_estimates={"演算干员": (24, datetime.now())},
    )

    assert workshop_candidate_mood(data, "演算干员") is None


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


def test_ordinary_resident_is_not_blanket_protected_from_crafting(queue):
    data, tasks = queue
    data.operators["年"].mood = 23

    scheduler_task.try_workshop_tasks(data, tasks)

    assert [task.meta_data for task in tasks] == ["年", "泥岩"]


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


@pytest.mark.parametrize("reason", ["mood", "unknown", "reserved"])
def test_automatic_crafting_reports_operator_block_reason(queue, caplog, reason):
    data, tasks = queue
    if reason == "mood":
        data.operators["年"].current_mood = lambda: 20
        expected = "年加工跳过：心情不足（当前 20.0，需大于 22）"
    elif reason == "unknown":
        data.operators["年"].current_mood = lambda: -1
        expected = "年加工跳过：缺少可用心情读数或卡牌预估"
    else:
        tasks.append(
            SchedulerTask(task_plan={"meeting": ["年"]}, task_type=TaskTypes.SHIFT_ON)
        )
        expected = "年加工跳过：已被上班任务预约"
    scheduler_task.try_workshop_tasks(data, tasks)
    assert expected in caplog.text
    assert [t.meta_data for t in tasks if t.type == TaskTypes.WORKSHOP] == ["泥岩"]
    assert "请检查合成数量" not in caplog.text
