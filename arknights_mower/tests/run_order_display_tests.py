"""跑单原班恢复沿用任务身份，展示剩余安排。"""

from copy import deepcopy
from datetime import datetime

from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


def test_run_order_title_changes_only_after_switching_to_original_roster():
    task = SchedulerTask(
        time=datetime(2026, 11, 6, 21, 10, 8),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    assert task.display_name == "跑单"
    task.run_order_original_roster = {"room_1_1": ["图耶"]}
    task.run_order_restore_pending = True
    assert task.display_name == "跑单"

    task.prepare_run_order_restoration()
    before = deepcopy(vars(task))

    assert task.display_name == "恢复原班"
    displayed = task.format()
    assert displayed.type == "恢复原班"
    assert displayed.plan == {"room_1_1": ["图耶"]}
    assert displayed.time == datetime(2026, 11, 6, 21, 10, 8)
    assert vars(task) == before
    assert task.type is TaskTypes.RUN_ORDER


def test_restoration_title_does_not_depend_on_failure_or_remaining_roster():
    task = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
    task.run_order_restore_pending = True
    task.run_order_original_roster = {"room_1_1": ["图耶"]}
    task.prepare_run_order_restoration()
    task.execution_failure = {"reason": "干员确认结果仍未确定"}
    assert task.display_name == "恢复原班"
    del task.execution_failure
    task.plan.clear()
    assert task.display_name == "恢复原班"


def test_other_tasks_with_empty_metadata_keep_their_title():
    assert SchedulerTask(task_type=TaskTypes.RUN_ORDER).display_name == "跑单"
    assert SchedulerTask(task_type=TaskTypes.SELF_CORRECTION).display_name == "纠错"
