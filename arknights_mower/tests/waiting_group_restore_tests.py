"""恢复旧等待队列时，只合并尚未执行且责任相同的派生上班任务。"""

import copy
import pickle
import sys
from datetime import datetime, timedelta
from threading import Event
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import scheduler_task
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

NOW = datetime(2026, 10, 18, 2, 37, 34)


def waiting_shift(predecessor, *, seconds=0):
    task = SchedulerTask(
        time=NOW + timedelta(seconds=seconds),
        task_plan={"recycle": ["旅骨", "Current"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    task.group_shift_predecessors = (predecessor,)
    task.group_shift_waiting = set()
    task.return_windows = {"旅骨": (("dormitory_1", 4), NOW)}
    return task


def predecessor():
    task = SchedulerTask(
        time=NOW - timedelta(hours=1),
        task_plan={"dormitory_3": ["塑心", "蜜莓", "野鬃", "望", "重岳"]},
        task_type=TaskTypes.SHIFT_ON,
    )
    task.group_shift_expected = {("dormitory_1", 4): "旅骨"}
    task.execution_failure = {
        "rooms": ["dormitory_3"],
        "reason": "干员确认画面仍未稳定，返回房间重试",
    }
    return task


def test_restore_old_waiting_copies_keeps_earliest_original_and_predecessor():
    previous = predecessor()
    waiting = [waiting_shift(previous, seconds=index) for index in range(26791)]
    original = waiting[0]
    result = scheduler_task.merge_restored_waiting_shifts(waiting[::-1])
    assert len(result) == 1 and result[0] is original
    assert original.time == NOW
    assert original.group_shift_predecessors[0] is previous
    assert previous.execution_failure["rooms"] == ["dormitory_3"]
    again = scheduler_task.merge_restored_waiting_shifts(result)
    assert len(again) == 1 and again[0] is original


def test_pickle_roundtrip_keeps_same_predecessor_reference():
    previous = predecessor()
    earliest, duplicate = waiting_shift(previous), waiting_shift(previous, seconds=2)
    saved = pickle.loads(
        pickle.dumps({"tasks": [previous], "waiting": [duplicate, earliest]})
    )
    original = saved["waiting"][1]
    result = scheduler_task.merge_restored_waiting_shifts(saved["waiting"])
    assert len(result) == 1 and result[0] is original
    assert result[0].group_shift_predecessors[0] is saved["tasks"][0]
    restored_again = pickle.loads(
        pickle.dumps({"tasks": saved["tasks"], "waiting": result})
    )
    assert (
        restored_again["waiting"][0].group_shift_predecessors[0]
        is restored_again["tasks"][0]
    )


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("plan", {"recycle": ["见行者", "Current"]}),
        ("group_shift_waiting", {"另一组"}),
        ("group_shift_transitions", {"联动": True}),
        ("return_windows", {"旅骨": (("dormitory_2", 4), NOW)}),
        ("meta_data", "明确请求"),
        ("adjusted", True),
        ("strict_mood_limit", True),
        ("mood_limit", 20),
        ("initial_fia", True),
        ("type", TaskTypes.SHIFT_OFF),
    ],
)
def test_distinct_targets_or_execution_metadata_are_preserved(attribute, value):
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    setattr(second, attribute, value)
    result = scheduler_task.merge_restored_waiting_shifts([first, second])
    assert len(result) == 2 and result[0] is first and result[1] is second


def test_value_equal_but_distinct_predecessors_are_preserved():
    previous = predecessor()
    other = copy.deepcopy(previous)
    assert previous == other and previous is not other
    first, second = waiting_shift(previous), waiting_shift(other, seconds=2)
    result = scheduler_task.merge_restored_waiting_shifts([first, second])
    assert len(result) == 2 and result[0] is first and result[1] is second


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("group_shift_expected", {("recycle", 0): "旅骨"}),
        ("backup_shift_active", True),
        ("derived_correction_started", True),
        ("execution_retained", True),
        ("execution_failure", {"rooms": ["recycle"]}),
        ("arrangement_retry_count", 1),
        ("dorm_recovery_restore", ["dormitory_1"]),
        ("product_shift_locked", True),
        ("unknown_execution_state", {"reserved": "旅骨"}),
        ("adjusted", True),
        ("strict_mood_limit", True),
        ("initial_fia", True),
        ("mood_limit", 20),
    ],
)
def test_started_or_unrecognized_work_is_not_merged_even_with_same_metadata(
    attribute, value
):
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    for task in (first, second):
        setattr(task, attribute, copy.deepcopy(value))
    result = scheduler_task.merge_restored_waiting_shifts([first, second])
    assert len(result) == 2 and result[0] is first and result[1] is second


def test_identical_wait_groups_and_transitions_allow_merge():
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    for task in (first, second):
        task.group_shift_waiting = {"联动"}
        task.group_shift_transitions = {"联动": False}
    result = scheduler_task.merge_restored_waiting_shifts([second, first])
    assert len(result) == 1 and result[0] is first


def test_same_recovery_window_preserves_earliest_start():
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    second.return_windows["旅骨"] = (("dormitory_1", 4), NOW + timedelta(seconds=2))
    result = scheduler_task.merge_restored_waiting_shifts([second, first])
    assert len(result) == 1 and result[0] is first
    assert first.return_windows["旅骨"][1] == NOW


def test_different_recovery_window_identity_is_not_merged():
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    first.return_windows["旅骨"] = ((("旅骨", 21),), NOW)
    second.return_windows["旅骨"] = ((("旅骨", 23),), NOW + timedelta(seconds=2))
    result = scheduler_task.merge_restored_waiting_shifts([first, second])
    assert len(result) == 2 and result[0] is first and result[1] is second


def test_earlier_task_with_later_window_start_is_not_merged():
    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    first.return_windows["旅骨"] = (("dormitory_1", 4), NOW + timedelta(seconds=3))
    result = scheduler_task.merge_restored_waiting_shifts([first, second])
    assert len(result) == 2 and result[0] is first and result[1] is second


def test_unrelated_waiting_work_preserves_order_and_identity():
    previous = predecessor()
    ordinary = SchedulerTask(task_type=TaskTypes.CLUE_PARTY, time=NOW)
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    result = scheduler_task.merge_restored_waiting_shifts([ordinary, second, first])
    assert len(result) == 2 and result[0] is ordinary and result[1] is first


@pytest.fixture
def mower_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower import __main__ as mower

    return mower


def test_simulate_restoration_coalesces_waiting_before_dispatch(
    monkeypatch, mower_module
):
    mower = mower_module
    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils import config, crash_recovery

    class Restored(BaseException):
        pass

    previous = predecessor()
    first, second = waiting_shift(previous), waiting_shift(previous, seconds=2)
    saved = pickle.loads(
        pickle.dumps(
            {
                "tasks": [previous],
                "waiting_group_shifts": [second, first],
                "operators": {},
                "dorm": [],
                "party_time": None,
                "daily_visit_friend": NOW.date(),
                "daily_report": NOW.date(),
                "daily_skland": NOW.date(),
                "daily_mail": NOW.date(),
                "task_count": 51,
            }
        )
    )
    operators = MagicMock(operators={}, backup_plans=[])
    operators.validate_backup_plans.return_value = {"success": True}
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = operators
    instance.initialize_operators = lambda: None
    instance._pending_group_transitions = lambda: {}
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    monkeypatch.setattr(mower, "base_scheduler", None)
    monkeypatch.setattr(mower, "initialize", lambda *a, **kw: instance)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        mower, "_apply_version_update_resting_threshold", lambda *a: None
    )

    def after_restoration():
        raise Restored

    monkeypatch.setattr(mower, "refresh_resource_at_boundary", after_restoration)
    with pytest.raises(Restored):
        mower.simulate(saved)
    assert len(instance.waiting_group_shifts) == 1
    restored = instance.waiting_group_shifts[0]
    assert restored is saved["waiting_group_shifts"][1]
    assert restored.time == NOW
    assert instance.tasks[0].time == saved["tasks"][0].time
    assert instance.tasks[0].execution_failure == saved["tasks"][0].execution_failure
    assert restored.group_shift_predecessors[0] is instance.tasks[0]
