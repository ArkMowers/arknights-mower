"""普通启动首次补床在选出当前任务前也能完成主班规划。"""

import sys
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import Mock

sys.modules.setdefault("arknights_mower.utils.skland", Mock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.tests import dorm_release_tests  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402

op_data = dorm_release_tests.op_data
ROOM = dorm_release_tests.ROOM


def test_first_cached_start_plans_primary_recovery_before_filling_bed(
    op_data, monkeypatch
):
    monkeypatch.setattr(base_schedule, "workshop_inventory_changed", Event())
    scheduler = base_schedule.BaseSchedulerSolver(device=Mock(), recog=Mock())
    scheduler.op_data = op_data
    op_data.operators["空爆"].current_room = "meeting"
    op_data.dorm[0].reset()
    appointment = SchedulerTask(
        datetime.now() + timedelta(hours=2), {}, TaskTypes.DEPOT
    )
    scheduler.tasks = [appointment]
    scheduler.resting = Mock(return_value={})
    scheduler._scan_card_moods = Mock()
    save_exception = Mock()
    monkeypatch.setattr(base_schedule, "save_exception", save_exception)

    # run() 首次选任务前调用此入口；不提前手工补 scheduler.task。
    assert scheduler._fill_empty_dorms()

    scheduler.resting.assert_called_once_with()
    save_exception.assert_not_called()
    assert scheduler.task is None
    assert scheduler.tasks[0] is appointment
    assert scheduler.tasks[1].type == TaskTypes.FILL_DORM
    assert scheduler.tasks[1].plan == {ROOM: ["Current"] * 4 + ["红"]}
    assert not op_data.dorm[0].name
