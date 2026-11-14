"""回班快照保留工作目标，附带宿舍换位不改变工作主班的回班岗位。"""

import copy
from datetime import datetime, timedelta

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.group_recovery import split_recovery_return
from arknights_mower.utils.operators import Dormitory, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    generate_plan_by_drom,
    plan_metadata,
)


@pytest.fixture
def recovering_primary(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf(enable_mastery=False))
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "meeting": [Room("银灰", "", ["红"])],
                    "contact": [Room("讯使", "", ["芬"])],
                    "dormitory_1": [
                        Room(name, "", [])
                        for name in ["杜林", "闪灵", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", "", free_room=False),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    now = datetime(2026, 11, 8, 12)
    for op in data.operators.values():
        op.mood, op.time_stamp = 24, now
        op._current_room, op.current_index = op.room, op.index
    primary = data.operators["银灰"]
    primary._current_room, primary.current_index = "dormitory_1", 2
    primary.mood = 21
    data.operators["红"]._current_room, data.operators["红"].current_index = (
        "meeting",
        0,
    )
    bed = next(b for b in data.dorm if b.position == ("dormitory_1", 2))
    bed.name, bed.time = primary.name, now + timedelta(hours=1)
    return data, bed, now


@pytest.mark.parametrize("target", [("dormitory_1", 4), ("contact", 0)])
def test_return_generator_rejects_incidental_dorm_target(recovering_primary, target):
    data, bed, now = recovering_primary
    before = copy.deepcopy(data.dorm)
    tasks = generate_plan_by_drom(
        {bed.time: ([bed], False)},
        data,
        existing_targets={"银灰": target},
        now=now,
    )
    expected = "meeting" if target[0].startswith("dorm") else "contact"
    assert [task.plan for task in tasks] == [{expected: ["银灰"]}]
    assert tasks[0].time == bed.time - timedelta(minutes=8)
    assert [(b.name, b.position, b.time) for b in data.dorm] == [
        (b.name, b.position, b.time) for b in before
    ]
    assert data.operators["银灰"].current_room == "dormitory_1"


@pytest.mark.parametrize("work_first", [False, True])
@pytest.mark.parametrize("saved_work", [False, True])
def test_metadata_rebuild_keeps_work_target_despite_dorm_moves(
    recovering_primary, work_first, saved_work
):
    data, bed, now = recovering_primary
    data.plan_condition = [True]
    dorm = {"dormitory_1": ["Current"] * 4 + ["银灰"]}
    work = {"contact": ["银灰"]} if saved_work else {}
    plan = {**work, **dorm} if work_first else {**dorm, **work}
    tasks = [
        SchedulerTask(
            time=bed.time - timedelta(minutes=8),
            task_type=TaskTypes.SHIFT_ON,
            task_plan=plan,
        )
    ]
    expected_room = "contact" if saved_work else "meeting"
    for _ in range(3):
        tasks = plan_metadata(data, tasks, now=now)
        returns = [task for task in tasks if task.type == TaskTypes.SHIFT_ON]
        assert [task.plan for task in returns] == [{expected_room: ["银灰"]}]
        assert returns[0].time == bed.time - timedelta(minutes=8)
        assert data.operators["银灰"].current_room == "dormitory_1"
        assert bed.name == "银灰"
    confirmed = data.project_arrangements([returns[0].plan])
    assert confirmed.operators["银灰"].current_room == expected_room
    rebuilt = plan_metadata(confirmed, [], now=bed.time)
    assert all("银灰" not in row for task in rebuilt for row in task.plan.values())


def test_configured_dorm_primary_keeps_its_dorm_return_target(recovering_primary):
    data, _, now = recovering_primary
    manager = data.operators["杜林"]
    manager._current_room, manager.current_index = "", -1
    bed = Dormitory(("dormitory_1", 2), manager.name, now + timedelta(hours=1))
    tasks = generate_plan_by_drom(
        {bed.time: ([bed], False)},
        data,
        existing_targets={manager.name: ("dormitory_1", 0)},
        now=now,
    )
    assert tasks[0].plan["dormitory_1"][0] == manager.name


def test_displaced_dorm_cover_waits_for_its_recovering_source_group(recovering_primary):
    data, bed, now = recovering_primary
    data.operators["银灰"].group = data.operators["闪灵"].group = "回班"
    data.groups["回班"] = ["银灰", "闪灵"]
    data.operators["闪灵"]._current_room = ""
    data.operators["红"]._current_room, data.operators["红"].current_index = (
        "dormitory_1",
        1,
    )
    data.operators["讯使"]._current_room, data.operators["讯使"].current_index = (
        "dormitory_1",
        3,
    )
    task = SchedulerTask(
        time=now,
        task_type=TaskTypes.SHIFT_ON,
        task_plan={
            "meeting": ["银灰"],
            "contact": ["讯使"],
            "dormitory_1": ["Current", "闪灵", "Current", "Current", "红"],
        },
    )
    independent = []
    split_recovery_return(data, task, independent, {"银灰"})
    assert [sibling.plan for sibling in independent] == [{"contact": ["讯使"]}]
    assert task.plan == {
        "meeting": ["银灰"],
        "dormitory_1": ["Current", "闪灵", "Current", "Current", "红"],
    }
    assert task.time == now
    assert bed.name == "银灰"
