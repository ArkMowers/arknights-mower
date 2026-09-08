"""Fixed mastery handoffs share run-order collision handling without being accelerated."""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule  # noqa: E402
from arknights_mower.utils import scheduler_task as scheduler  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def clock():
    now = datetime(2026, 9, 8, 18, 20)
    with (
        patch.object(scheduler.config.conf, "enable_mastery", True),
        patch.object(scheduler.config.conf.run_order_grandet_mode, "enable", False),
        patch.object(
            scheduler.NewsChecker, "get_update_time", return_value=(None, None)
        ),
        patch.object(scheduler, "datetime") as mock_clock,
    ):
        mock_clock.now.return_value = now
        yield mock_clock


def pair():
    at = datetime(2026, 9, 8, 18, 50)
    return (
        SchedulerTask(
            at - timedelta(minutes=1),
            {"room_1_1": ["但书"]},
            TaskTypes.RUN_ORDER,
            "room_1_1",
        ),
        SchedulerTask(
            at, task_type=TaskTypes.SWAP_SUPPORT, meta_data="学员 换入逻各斯"
        ),
    )


def make_solver(tasks):
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.tasks = tasks
    solver.recog = SimpleNamespace(gray=None, w=1920, h=1080)
    solver.digit_reader = MagicMock()
    solver.tap = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver._wait_drone_interface = MagicMock()
    solver.double_read_time = MagicMock()
    return solver
