"""更新重启保留重要任务及心情缓存，普通安排由立即空任务重建。"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests.process_crash_recovery_tests import (
    configure_simulate,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    notice as _notice,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    observed_scheduler as _observed_scheduler,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    offline as _offline,
)
from arknights_mower.utils import crash_recovery, instance_supervisor
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    replan_update_tasks,
)

offline = _offline
notice = _notice
observed_scheduler = _observed_scheduler


def test_update_keeps_important_tasks_and_replaces_ordinary_work_without_mutation():
    now = datetime.now()
    important = [
        SchedulerTask(
            time=now + timedelta(minutes=index - 3),
            task_plan={"train": ["测试干员"]},
            task_type=kind,
            meta_data="saved appointment",
        )
        for index, kind in enumerate(
            [
                TaskTypes.RUN_ORDER,
                TaskTypes.SKILL_UPGRADE,
                TaskTypes.SWAP_SUPPORT,
                TaskTypes.FIAMMETTA,
                TaskTypes.WORKSHOP,
                TaskTypes.RECRUIT,
                TaskTypes.SKLAND,
                TaskTypes.CLUE,
                TaskTypes.FURNITURE,
                TaskTypes.DEPOT,
            ]
        )
    ]
    ordinary = [
        SchedulerTask(task_type=kind)
        for kind in (
            TaskTypes.SHIFT_ON,
            TaskTypes.SHIFT_OFF,
            TaskTypes.EXHAUST_OFF,
            TaskTypes.SELF_CORRECTION,
            TaskTypes.RE_ORDER,
            TaskTypes.FILL_DORM,
            TaskTypes.RELEASE_DORM,
            TaskTypes.NOT_SPECIFIC,
        )
    ]
    cache = {"测试干员": object()}
    saved = {"operators": cache, "tasks": important + ordinary, "dorm": [object()]}
    old_times = [task.time for task in important]
    prepared = replan_update_tasks(saved)
    assert prepared["operators"] is cache and prepared["dorm"] is saved["dorm"]
    assert prepared["tasks"][:-1] == important
    assert all(
        actual is expected for actual, expected in zip(prepared["tasks"], important)
    )
    assert [task.time for task in important] == old_times
    assert prepared["tasks"][-1].type == TaskTypes.NOT_SPECIFIC
    assert now <= prepared["tasks"][-1].time <= datetime.now()
    assert saved["tasks"] == important + ordinary
    repeated = replan_update_tasks(prepared)
    assert repeated["tasks"][:-1] == important
    assert len(repeated["tasks"]) == len(important) + 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_failure", {"reason": "unconfirmed"}),
        ("execution_retained", True),
        ("group_shift_expected", {"测试干员": "room_1_1"}),
        ("group_shift_waiting", {"恢复组"}),
        ("return_windows", {"恢复组": ("原岗位", datetime(2026, 10, 25, 12))}),
        ("backup_shift_active", True),
        ("strict_mood_limit", True),
        ("emergency_original_roster", {"room_1_1": ["测试干员"]}),
        ("run_order_restore_pending", True),
        ("replacement_check", {"target": "测试干员"}),
        ("product_shift_locked", True),
    ],
)
def test_update_retains_unfinished_arrangements(field, value):
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    setattr(task, field, value)
    ordinary = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    saved = {"tasks": [ordinary, task]}
    prepared = replan_update_tasks(saved)
    assert len(prepared["tasks"]) == 2
    assert prepared["tasks"][0] is task
    assert prepared["tasks"][1].type == TaskTypes.NOT_SPECIFIC
    assert saved["tasks"] == [ordinary, task]


def test_update_retains_predecessors_of_specialized_and_suspended_tasks():
    predecessor = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task = SchedulerTask(task_type=TaskTypes.RUN_ORDER)
    task.group_shift_predecessors = (predecessor,)
    waiting_predecessor = SchedulerTask(task_type=TaskTypes.RE_ORDER)
    waiting = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    waiting.group_shift_predecessors = (waiting_predecessor,)
    saved = {
        "tasks": [predecessor, task, waiting_predecessor],
        "waiting_group_shifts": [waiting],
    }
    prepared = replan_update_tasks(saved)
    assert prepared["tasks"][:-1] == saved["tasks"]
    assert all(a is b for a, b in zip(prepared["tasks"], saved["tasks"]))
    assert prepared["waiting_group_shifts"] is saved["waiting_group_shifts"]
    assert task.group_shift_predecessors == (predecessor,)


@pytest.mark.parametrize("headers", [{}, {"token": "invalid"}])
@pytest.mark.parametrize("method", ["get", "post"])
def test_update_start_requires_token_before_loading_cache(
    offline, monkeypatch, headers, method
):
    load = Mock(side_effect=AssertionError("unauthorized snapshot access"))
    monkeypatch.setattr(offline.server, "load_state", load)
    response = getattr(offline.server.app.test_client(), method)(
        "/start/3", headers=headers
    )
    assert response.status_code == 403
    load.assert_not_called()
    offline.io.assert_not_called()


def test_update_post_retains_explicit_preparation_validation(offline, monkeypatch):
    load = Mock(side_effect=AssertionError("unconfirmed preparation"))
    monkeypatch.setattr(offline.server, "load_state", load)
    response = offline.server.app.test_client().post(
        "/start/3", headers={"token": "crash-test"}, json={}
    )
    assert response.status_code == 400
    assert response.json["error"] == "invalid_preparation_consent"
    load.assert_not_called()
    offline.io.assert_not_called()


@pytest.mark.parametrize("checkpoint_failure", [False, True])
def test_update_route_checkpoints_retained_tasks_and_keeps_mode_on_failure(
    offline, notice, observed_scheduler, monkeypatch, tmp_path, checkpoint_failure
):
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    deadline = datetime.now() + timedelta(hours=2)
    important = SchedulerTask(time=deadline, task_type=TaskTypes.SWAP_SUPPORT)
    important.plan_key = "saved mastery"
    observed_scheduler.tasks = [important, SchedulerTask(task_type=TaskTypes.SHIFT_ON)]
    assert offline.record.save_current_state()
    original = offline.record.load_state(strict=True)
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(instance_supervisor, "task_intent", Mock())
    response = offline.server.app.test_client().get(
        "/start/3", headers={"token": "crash-test"}
    )
    assert response.get_data(as_text=True) == "true"
    saved = create.call_args.kwargs["args"][0]
    assert [task.type for task in saved["tasks"]] == [
        TaskTypes.SWAP_SUPPORT,
        TaskTypes.NOT_SPECIFIC,
    ]
    assert saved["tasks"][0].time == deadline
    assert saved["tasks"][0].plan_key == "saved mastery"
    assert saved["operators"].keys() == original["operators"].keys()
    for name, operator in original["operators"].items():
        for field in ("mood", "time_stamp", "current_room", "current_index"):
            assert getattr(saved["operators"][name], field) == getattr(operator, field)
    assert crash_recovery.pending_start_type() == "3"
    configure_simulate(offline, monkeypatch, observed_scheduler)
    if checkpoint_failure:
        monkeypatch.setattr(offline.record, "save_current_state", lambda: False)
        with pytest.raises(RuntimeError, match="更新重规划后的状态暂未保存"):
            offline.main.simulate(saved)
        assert crash_recovery.pending_start_type() == "3"
        assert [
            task.type for task in offline.record.load_state(strict=True)["tasks"]
        ] == [
            TaskTypes.SWAP_SUPPORT,
            TaskTypes.SHIFT_ON,
        ]
        crash_recovery.activate("update startup failed")
        assert offline.server._retry_after_process_crash()
        retried = create.call_args.kwargs["args"][0]
        assert [task.type for task in retried["tasks"]] == [
            TaskTypes.SWAP_SUPPORT,
            TaskTypes.NOT_SPECIFIC,
        ]
        assert retried["tasks"][0].time == deadline
        assert crash_recovery.pending_start_type() == "3"
    else:

        def dispatch():
            assert crash_recovery.pending_start_type() is None
            checkpoint = offline.record.load_state(strict=True)
            assert [task.type for task in checkpoint["tasks"]] == [
                TaskTypes.SWAP_SUPPORT,
                TaskTypes.NOT_SPECIFIC,
            ]
            assert checkpoint["tasks"][0].time == deadline
            raise MowerExit

        monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", dispatch)
        offline.main.simulate(saved)
        crash_recovery.activate("later independent failure")
        assert crash_recovery.status()["start_type"] == "0"
    offline.io.assert_not_called()
