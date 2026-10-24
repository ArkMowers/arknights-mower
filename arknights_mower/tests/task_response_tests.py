import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.views import task as task_view


@pytest.fixture
def endpoint(monkeypatch):
    scheduler = SimpleNamespace(tasks=[])
    main = ModuleType("arknights_mower.__main__")
    main.base_scheduler = scheduler
    monkeypatch.setitem(sys.modules, main.__name__, main)
    thread = SimpleNamespace(is_alive=Mock(return_value=True))
    monkeypatch.setattr(task_view, "mower_thread", thread)
    app = Flask(__name__)
    app.token = "task-test-token"
    app.register_blueprint(task_view.task_bp)
    return SimpleNamespace(
        client=app.test_client(), scheduler=scheduler, main=main, thread=thread
    )


def get_tasks(endpoint):
    response = endpoint.client.get("/task", headers={"token": "task-test-token"})
    assert response.status_code == 200
    return response.get_json()


@pytest.mark.parametrize(
    "at,expected_time",
    [
        (datetime(2026, 10, 24, 12, 34, 56), "2026-10-24T12:34:56"),
        (
            datetime(2026, 10, 24, 12, 34, 56, 123456, timezone(timedelta(hours=8))),
            "2026-10-24T12:34:56.123456+08:00",
        ),
    ],
)
def test_task_list_keeps_display_fields_and_iso_time(endpoint, at, expected_time):
    task = SchedulerTask(
        time=at,
        task_plan={"room_1_1": ["温蒂", "Current", "Free", "", None]},
        task_type=TaskTypes.SHIFT_OFF,
        meta_data="轮休组甲",
        adjusted=True,
        strict_mood_limit=True,
        mood_limit=12.5,
        initial_fia=True,
    )
    endpoint.scheduler.tasks = [task]

    assert get_tasks(endpoint) == [
        {
            "time": expected_time,
            "plan": {"room_1_1": ["温蒂", "Current", "Free", "", None]},
            "type": {
                "_value_": "shifit_off",
                "_name_": "SHIFT_OFF",
                "display_value": "下班",
                "priority": 2,
            },
            "meta_data": "轮休组甲",
            "adjusted": True,
            "strict_mood_limit": True,
            "mood_limit": 12.5,
            "initial_fia": True,
            "display_name": "下班",
        }
    ]
    assert task.time is at
    assert task.type is TaskTypes.SHIFT_OFF
    assert task.plan == {"room_1_1": ["温蒂", "Current", "Free", "", None]}


@pytest.mark.parametrize(
    "flag", ["emergency_recovery_release", "emergency_staffing", "emergency_dorm"]
)
def test_task_list_keeps_emergency_labels(endpoint, flag):
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    setattr(task, flag, True)
    endpoint.scheduler.tasks = [task]

    assert get_tasks(endpoint)[0][flag] is True


def test_task_list_keeps_workshop_generation_for_duplicate_detection(endpoint):
    task = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="九色鹿")
    task.workshop_generation = 7
    endpoint.scheduler.tasks = [task]

    result = get_tasks(endpoint)[0]
    assert result["type"]["display_value"] == "加工材料"
    assert result["meta_data"] == "九色鹿"
    assert result["workshop_generation"] == 7


def test_task_list_uses_pending_queue_without_serializing_runtime_state(endpoint):
    task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    task.exhaust_support = True
    task.execution_failure = {"reason": "未确认驻员"}
    task.group_shift_predecessors = [task]
    task.internal_handle = object()
    task.internal_rooms = {"dormitory_1"}
    before = vars(task).copy()
    endpoint.scheduler.tasks = [task]

    result = get_tasks(endpoint)
    assert len(result) == 1
    assert result[0]["display_name"] == "替班交接"
    assert not (
        {
            "exhaust_support",
            "execution_failure",
            "group_shift_predecessors",
            "internal_handle",
            "internal_rooms",
        }
        & result[0].keys()
    )
    assert result[0]["type"].keys() == {
        "_value_",
        "_name_",
        "display_value",
        "priority",
    }
    assert vars(task).keys() == before.keys()
    assert all(getattr(task, name) is value for name, value in before.items())


def test_response_plan_does_not_share_mutable_roster():
    task = SchedulerTask(task_plan={"room_1_1": ["温蒂"]})
    result = task_view._task_response(task)
    result["plan"]["room_1_1"].append("图耶")
    result["plan"]["dormitory_1"] = ["Free"]
    assert task.plan == {"room_1_1": ["温蒂"]}


@pytest.mark.parametrize(
    "state", ["missing_scheduler", "missing_thread", "stopped", "empty"]
)
def test_task_list_returns_empty_when_not_running(endpoint, monkeypatch, state):
    if state == "missing_scheduler":
        endpoint.main.base_scheduler = None
    elif state == "missing_thread":
        monkeypatch.setattr(task_view, "mower_thread", None)
    elif state == "stopped":
        endpoint.thread.is_alive.return_value = False
    assert get_tasks(endpoint) == []


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_task_requests_reject_invalid_token_before_reading_scheduler(
    endpoint, method, token
):
    headers = {} if token is None else {"token": token}
    response = getattr(endpoint.client, method)("/task", headers=headers)
    assert response.status_code == 403
    endpoint.thread.is_alive.assert_not_called()
