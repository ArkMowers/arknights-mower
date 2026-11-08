"""任务列表在认证后只读返回完整设施名称和任务展示快照。"""

import copy
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.views import task as route


@pytest.fixture
def task_route(monkeypatch):
    main = ModuleType("arknights_mower.__main__")
    monkeypatch.setitem(sys.modules, main.__name__, main)
    worker = Mock(is_alive=Mock(return_value=True))
    monkeypatch.setattr(route, "mower_thread", worker)
    app = Flask(__name__)
    app.token = "task-presentation-token"
    app.register_blueprint(route.task_bp)
    return SimpleNamespace(main=main, worker=worker, client=app.test_client())


@pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_task_rejects_credentials_before_scheduler_access(task_route, method, token):
    accessed = Mock(side_effect=AssertionError("认证前不得读取任务"))
    task_route.main.__getattr__ = accessed
    response = task_route.client.open(
        "/task",
        method=method,
        headers={} if token is None else {"token": token},
        data="invalid json",
        content_type="application/json",
    )
    assert response.status_code == 403
    accessed.assert_not_called()
    task_route.worker.is_alive.assert_not_called()


def test_authenticated_task_list_has_read_only_facility_presentation(task_route):
    when = datetime(2026, 11, 4, 16, 5, 19)
    refresh = SchedulerTask(
        time=when, task_type=TaskTypes.REFRESH_TIME, meta_data="room_2_1"
    )
    staffed = SchedulerTask(
        time=when,
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_2_1": ["Current", "但书", "龙舌兰"]},
    )
    data = SimpleNamespace(
        operators={},
        facility_states={"room_2_1": {"facility": "trade"}},
        plan={},
    )
    scheduler = SimpleNamespace(tasks=[refresh, staffed], op_data=data)
    task_route.main.base_scheduler = scheduler
    before = copy.deepcopy(vars(scheduler))
    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )
    assert response.status_code == 200
    first, second = response.json
    assert first["display_name"] == "刷新跑单时间"
    assert first["meta_data"] == "room_2_1"
    assert first["presentation"]["targets"] == [
        {"id": "room_2_1", "label": "贸易站 B201"}
    ]
    assert second["plan"] == {"room_2_1": ["Current", "但书", "龙舌兰"]}
    assert second["presentation"]["rooms"] == [
        {
            "id": "room_2_1",
            "label": "贸易站 B201",
            "agents": ["Current", "但书", "龙舌兰"],
        }
    ]
    assert first["time"] == "2026-11-04T16:05:19"
    assert vars(data) == vars(before["op_data"])
    assert [vars(task) for task in scheduler.tasks] == [
        vars(task) for task in before["tasks"]
    ]


def test_stopped_task_list_remains_empty(task_route):
    task_route.main.base_scheduler = None
    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )
    assert response.status_code == 200
    assert response.json == []


def test_restoration_list_displays_remaining_roster_without_changing_task(task_route):
    task = SchedulerTask(
        time=datetime(2026, 11, 6, 21, 10, 8),
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_1": ["但书"]},
        meta_data="room_1_1",
    )
    task.run_order_original_roster = {"room_1_1": ["图耶"]}
    task.run_order_restore_pending = True
    task.prepare_run_order_restoration()
    task.log_source_title = "跑单"
    data = SimpleNamespace(
        operators={}, facility_states={"room_1_1": {"facility": "trade"}}, plan={}
    )
    task_route.main.base_scheduler = SimpleNamespace(tasks=[task], op_data=data)
    before = copy.deepcopy(vars(task))

    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )

    assert response.status_code == 200
    item = response.json[0]
    assert item["display_name"] == item["presentation"]["title"] == "恢复原班"
    assert item["plan"] == {"room_1_1": ["图耶"]}
    assert item["presentation"]["rooms"] == [
        {"id": "room_1_1", "label": "贸易站 B101", "agents": ["图耶"]}
    ]
    assert item["time"] == "2026-11-06T21:10:08"
    assert vars(task) == before
    assert task.type is TaskTypes.RUN_ORDER


@pytest.mark.parametrize("legacy_plan", [None, {"room_2_1": None}, {"room_2_1": [{}]}])
def test_legacy_plan_without_a_valid_projection_keeps_the_queue_readable(
    task_route, legacy_plan
):
    legacy = SchedulerTask(task_plan=legacy_plan, task_type=TaskTypes.NOT_SPECIFIC)
    staffed = SchedulerTask(
        task_plan={"room_2_1": ["但书"]}, task_type=TaskTypes.NOT_SPECIFIC
    )
    task_route.main.base_scheduler = SimpleNamespace(tasks=[legacy, staffed])

    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )

    assert response.status_code == 200
    first, second = response.json
    assert first["plan"] == legacy_plan
    assert "presentation" not in first
    assert second["presentation"]["rooms"] == [
        {"id": "room_2_1", "label": "B201", "agents": ["但书"]}
    ]


def test_task_list_remains_readable_when_a_room_read_adds_an_operator(task_route):
    class ObservedOperator:
        current_index = 0

        @property
        def current_room(self):
            operators["斑点"] = SimpleNamespace(current_room="", current_index=-1)
            return "room_2_1"

    operators = {"但书": ObservedOperator()}
    task = SchedulerTask(
        task_plan={"room_2_1": ["龙舌兰"]}, task_type=TaskTypes.NOT_SPECIFIC
    )
    task_route.main.base_scheduler = SimpleNamespace(
        tasks=[task], op_data=SimpleNamespace(operators=operators, plan={})
    )

    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )

    assert response.status_code == 200
    assert response.json[0]["presentation"]["title"] == "但书下班"
    assert "斑点" in operators


def test_task_list_keeps_group_members_in_operator_snapshot(task_route):
    class JoiningOperators(dict):
        def copy(self):
            snapshot = super().copy()
            self["斑点"] = SimpleNamespace(multi_group=False)
            data.groups["贸易组"].append("斑点")
            return snapshot

    class StaffingData(SimpleNamespace):
        shift_group_members = Operators.shift_group_members

    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    task.group_shift_transitions = {"贸易组": True}
    data = StaffingData(
        operators=JoiningOperators({"但书": SimpleNamespace(multi_group=False)}),
        groups={"贸易组": ["但书"]},
        group_shift_state={"贸易组": False},
        plan={},
    )
    task_route.main.base_scheduler = SimpleNamespace(tasks=[task], op_data=data)

    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )

    assert response.status_code == 200
    assert response.json[0]["presentation"]["actions"] == [
        {"kind": "operator", "subject": "但书", "action": "下班"}
    ]
    assert data.groups["贸易组"] == ["但书", "斑点"]


def test_authenticated_dorm_adjustment_lists_rest_before_idle_without_committing(
    task_route,
):
    when = datetime(2026, 11, 5, 14, 58, 48, 543528)
    task = SchedulerTask(
        time=when,
        task_plan={"dormitory_2": ["Current", "Current", "Current", "桑葚", "Current"]},
        task_type=TaskTypes.NOT_SPECIFIC,
    )
    residents = ["杜林", "闪灵", "爱丽丝", "砾", "斑点"]
    operators = {
        name: SimpleNamespace(
            name=name, room="", current_room="dormitory_2", current_index=index
        )
        for index, name in enumerate(residents)
    }
    operators["桑葚"] = SimpleNamespace(
        name="桑葚", room="", current_room="", current_index=-1
    )
    data = SimpleNamespace(operators=operators, plan={}, facility_states={})
    scheduler = SimpleNamespace(tasks=[task], op_data=data)
    task_route.main.base_scheduler = scheduler
    before = copy.deepcopy(vars(scheduler))

    response = task_route.client.get(
        "/task", headers={"token": "task-presentation-token"}
    )

    assert response.status_code == 200
    assert response.json[0]["presentation"]["title"] == "桑葚休息；砾转为空闲"
    assert response.json[0]["presentation"]["actions"] == [
        {"kind": "operator", "subject": "桑葚", "action": "休息"},
        {"kind": "operator", "subject": "砾", "action": "转为空闲"},
    ]
    assert response.json[0]["plan"] == task.plan
    assert response.json[0]["time"] == "2026-11-05T14:58:48.543528"
    assert vars(data) == vars(before["op_data"])
    assert [vars(queued) for queued in scheduler.tasks] == [
        vars(queued) for queued in before["tasks"]
    ]
