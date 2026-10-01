"""集中恢复的普通空床补位保持可让床，正式恢复批次仍保床。"""

import pickle
from copy import deepcopy
from datetime import timedelta
from threading import Event
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers import record
from arknights_mower.tests.mass_mood_recovery_tests import (
    COVERS,
    NOW,
    PRIMARY,
    admit,
    set_moods,
)
from arknights_mower.tests.mass_mood_recovery_tests import (
    solver as solver,
)
from arknights_mower.utils import resting_priority
from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    try_add_release_dorm,
)


@pytest.fixture
def temporary_fill(solver, monkeypatch):
    monkeypatch.setattr(logger, "disabled", True)
    monkeypatch.setattr(record, "_conn", MagicMock())
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.rescue_needed()
    data.add(Operator("红", "", mood=5, time_stamp=NOW))
    data.main_rescue_priority.add("红")
    data.config.resting_priority_replacement.append("红")
    owner = data.operators[PRIMARY[0]]
    owner.replacement.append("红")
    data.plan[owner.room][owner.index].replacement.append("红")
    solver.task = SchedulerTask(
        NOW, {"dormitory_1": ["Current"] * 4 + ["Free"]}, TaskTypes.FILL_DORM
    )
    solver.task.simple_dorm_fill = True
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    for name in (
        "refresh_facility_state",
        "turn_on_room_detail",
        "wait_product_complete",
        "scroll_room_operators",
        "plan_metadata",
    ):
        setattr(solver, name, MagicMock())
    solver.find = MagicMock(
        side_effect=lambda resource, scope=None: (
            True
            if resource == "infra_no_operator" and scope[0][1] in (553, 532)
            else None
        )
    )
    solver.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    solver.read_accurate_mood = MagicMock(return_value=5)
    solver.read_operator_time = MagicMock(return_value=NOW + timedelta(hours=5))
    solver.get_agent_from_room("dormitory_1")
    return solver


def test_actual_rescue_fill_does_not_reserve_ordinary_bed(temporary_fill):
    data = temporary_fill.op_data
    resident = data.operators["红"]
    bed = data.get_dorm_by_name("红")[1]
    assert resident.temporary_dorm_fill
    data.rescue_needed()
    assert not data.is_rescue_recovering("红", NOW)
    assert data._slot_takable(bed, requester=PRIMARY[0])
    reserved = {
        index for index, candidate in enumerate(data.dorm) if candidate is not bed
    }
    assert data.assign_dorm(PRIMARY[0], used=reserved) is bed


def test_temporary_fill_state_isolated_in_projection_and_cleared_on_leave(
    temporary_fill,
):
    data = temporary_fill.op_data
    projected = data.project_arrangements([])
    assert projected.operators["红"].temporary_dorm_fill
    projected.operators["红"].current_room = ""
    assert not projected.operators["红"].temporary_dorm_fill
    assert data.operators["红"].temporary_dorm_fill
    cleared = data.project_arrangements(
        [{"dormitory_1": ["Current", "Current", "Free", "Free", "Free"]}]
    )
    assert not cleared.operators["红"].temporary_dorm_fill
    assert data.operators["红"].temporary_dorm_fill
    data.operators["红"].current_room = ""
    assert not data.operators["红"].temporary_dorm_fill


def test_explicit_dorm_projection_preserves_temporary_fill_without_promotion(
    temporary_fill,
):
    data = temporary_fill.op_data
    for names in (
        ["Current", "Current", "Current", "Current", "红"],
        ["Current", "Current", "红", "Free", "Free"],
    ):
        projected = data.project_arrangements([{"dormitory_1": names}])
        projected.rescue_needed()
        assert projected.operators["红"].temporary_dorm_fill
        assert not projected.is_rescue_recovering("红", NOW)
        assert projected._slot_takable(
            projected.get_dorm_by_name("红")[1], requester=PRIMARY[0]
        )
    assert data.operators["红"].temporary_dorm_fill
    assert data.operators["红"].current_index == 4


def test_formal_assignment_promotes_ordinary_fill_into_protected_batch(temporary_fill):
    data = temporary_fill.op_data
    temporary_fill.task = SchedulerTask(
        NOW, {"dormitory_1": ["Current"] * 4 + ["红"]}, TaskTypes.SHIFT_OFF
    )
    temporary_fill.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    temporary_fill.get_agent_from_room("dormitory_1")
    assert not data.operators["红"].temporary_dorm_fill
    data.rescue_needed()
    assert data.is_rescue_recovering("红", NOW)
    assert data._slot_takable(data.get_dorm_by_name("红")[1], requester=PRIMARY[0])


def test_repeated_read_and_ordinary_reorder_preserve_temporary_fill(temporary_fill):
    data = temporary_fill.op_data
    for task in [temporary_fill.task, None]:
        temporary_fill.task = task
        temporary_fill.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
        temporary_fill.get_agent_from_room("dormitory_1")
        assert data.operators["红"].temporary_dorm_fill
    temporary_fill.task = SchedulerTask(
        NOW, {"dormitory_1": ["Current"] * 4 + ["红"]}, TaskTypes.RE_ORDER
    )
    temporary_fill.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    temporary_fill.get_agent_from_room("dormitory_1")
    data.rescue_needed()
    assert not data.is_rescue_recovering("红", NOW)


def test_formal_low_priority_batch_keeps_bed_until_upper_limit(solver):
    data = solver.op_data
    set_moods(data, [0] * 4)
    data.operators[COVERS[0]].mood = 5
    data = admit(data, [COVERS[0]], [5])
    data.rescue_needed()
    bed = data.get_dorm_by_name(COVERS[0])[1]
    assert data.is_rescue_recovering(COVERS[0], NOW)
    assert data._slot_takable(bed, requester=PRIMARY[0])
    data.operators[COVERS[0]].mood = data.operators[COVERS[0]].upper_limit
    data.rescue_needed()
    assert not data.is_rescue_recovering(COVERS[0], NOW)
    assert data._slot_takable(bed, requester=PRIMARY[0])


@pytest.mark.parametrize("admission", ["ordinary", "formal", "legacy"])
def test_restart_preserves_dorm_admission_identity(solver, monkeypatch, admission):
    from arknights_mower import __main__ as main

    data = solver.op_data
    set_moods(data, [0] * 4)
    data.operators[COVERS[0]].mood = 5
    solver.op_data = data = admit(data, COVERS[:1], [5])
    resident = data.operators[COVERS[0]]
    resident.temporary_dorm_fill = admission == "ordinary"
    for attr in (
        "daily_visit_friend",
        "daily_report",
        "daily_skland",
        "daily_mail",
        "task_count",
    ):
        setattr(solver, attr, 0)
    monkeypatch.setattr(main, "base_scheduler", solver)
    saved = pickle.loads(pickle.dumps(record.current_state()))
    if admission == "legacy":
        del saved["operators"][resident.name].temporary_dorm_fill
    fresh = Operators(deepcopy(data.global_plan))
    assert fresh.init_and_validate() is None
    fresh.validate_backup_plans = MagicMock(return_value={"success": True})
    restarted = object.__new__(type(solver))
    restarted.op_data = fresh
    restarted.initialize_operators = MagicMock(return_value=None)
    monkeypatch.setattr(main, "initialize", MagicMock(return_value=restarted))
    monkeypatch.setattr(main.config, "stop_mower", Event())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", MagicMock())

    class ReachedScheduling(BaseException):
        pass

    monkeypatch.setattr(
        main, "refresh_resource_at_boundary", MagicMock(side_effect=ReachedScheduling)
    )
    with pytest.raises(ReachedScheduling):
        main.simulate(saved)
    restored = fresh.operators[resident.name]
    bed = fresh.get_dorm_by_name(resident.name)[1]
    ordinary = admission == "ordinary"
    assert restored.temporary_dorm_fill is ordinary
    assert fresh.is_rescue_recovering(restored.name, NOW) is not ordinary
    assert fresh._slot_takable(bed, requester=PRIMARY[0])
    assert (restored.current_room, restored.current_index) == (
        resident.current_room,
        resident.current_index,
    )
    assert (restored.mood, restored.time_stamp, restored.depletion_rate) == (
        resident.mood,
        resident.time_stamp,
        resident.depletion_rate,
    )
    assert bed.time == data.get_dorm_by_name(resident.name)[1].time


@pytest.fixture
def ordinary_readback(temporary_fill, monkeypatch):
    instance = temporary_fill
    data = instance.op_data
    data.update_detail("红", 5, "", -1, True)
    set_moods(data, [24] * 4)
    data.rescue_mode = False
    data.rescue_armed = True
    data.rescue_completed.clear()
    assert not data.rescue_needed()
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
    instance.task = None
    instance.tasks = [
        SchedulerTask(
            NOW + timedelta(hours=6),
            {"dormitory_1": ["Current", "Current", "Free", "Free", "Current"]},
        )
    ]
    return instance


@pytest.mark.parametrize(
    "kind", [TaskTypes.FILL_DORM, TaskTypes.NOT_SPECIFIC, TaskTypes.RELEASE_DORM]
)
def test_ordinary_admission_before_rescue_keeps_yielding_after_actual_readback(
    ordinary_readback, kind
):
    instance = ordinary_readback
    data = instance.op_data
    if kind != TaskTypes.FILL_DORM:
        data.config.free_room = True
        data.add(
            Operator(
                "空爆",
                "",
                mood=24,
                time_stamp=NOW,
                current_room="dormitory_1",
                current_index=4,
            )
        )
        data.dorm[2].name, data.dorm[2].time = "空爆", NOW - timedelta(minutes=1)
    if kind == TaskTypes.RELEASE_DORM:
        task = SchedulerTask(
            NOW, {"dormitory_1": ["Current"] * 4 + ["Free"]}, kind, "空爆"
        )
    else:
        count = len(instance.tasks)
        try_add_release_dorm({}, None, data, instance.tasks)
        assert len(instance.tasks) == count + 1
        task = instance.tasks[-1]
        assert task.type == kind
    assert not getattr(task, "simple_dorm_fill", False)
    instance.task = task
    if kind != TaskTypes.FILL_DORM:
        data.update_detail("空爆", 24, "", -1, True)
    # 游戏选人已经把 Free 解析成实际姓名，读房再记录入住身份。
    task.plan["dormitory_1"][4] = "红"
    instance.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    instance.get_agent_from_room("dormitory_1")
    assert data.operators["红"].temporary_dorm_fill
    set_moods(data, [0] * 4)
    assert data.rescue_needed()
    for current in (data, data.project_arrangements([task.plan])):
        assert current.operators["红"].temporary_dorm_fill
        assert not current.is_rescue_recovering("红", NOW)
        assert current._slot_takable(
            current.get_dorm_by_name("红")[1], requester=PRIMARY[0]
        )


def test_ordinary_fill_cross_bed_readback_preserves_formal_recovery(temporary_fill):
    instance = temporary_fill
    data = instance.op_data
    data.operators["红"].temporary_dorm_fill = False
    instance.task = SchedulerTask(
        NOW,
        {"dormitory_1": ["Current", "Current", "红", "Current", "Free"]},
        TaskTypes.FILL_DORM,
    )
    instance.find = MagicMock(
        side_effect=lambda resource, scope=None: (
            True
            if resource == "infra_no_operator" and scope[0][1] in (532, 741)
            else None
        )
    )
    instance.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    instance.get_agent_from_room("dormitory_1")
    assert data.operators["红"].current_index == 2
    for current in (data, data.project_arrangements([instance.task.plan])):
        assert not current.operators["红"].temporary_dorm_fill
        assert current.is_rescue_recovering("红", NOW)
        assert current._slot_takable(
            current.get_dorm_by_name("红")[1], requester=PRIMARY[0]
        )


@pytest.mark.parametrize("known", [True, False])
def test_shift_cycle_retains_ordinary_fill_source_through_actual_readback(
    ordinary_readback, known
):
    instance = ordinary_readback
    data = instance.op_data
    if not known:
        data.operators["红"].time_stamp = None
    task = SchedulerTask(NOW, task_type=TaskTypes.SHIFT_OFF)
    instance.tasks.append(task)
    instance.task = task
    instance._prepare_shift_cycle(task)
    assert data.operators["红"].current_room == ""
    assert not data.operators["红"].temporary_dorm_fill
    expected = "红" if known else "Free"
    assert task.plan["dormitory_1"][4] == expected
    assert task.dorm_fill_plan["dormitory_1"][4] == expected
    task.plan["dormitory_1"][4] = "红"
    instance.read_screen = MagicMock(side_effect=["冰酿", "闪灵", "红"])
    instance.get_agent_from_room("dormitory_1")
    assert data.operators["红"].temporary_dorm_fill
    set_moods(data, [0] * 4)
    assert data.rescue_needed()
    for current in (data, data.project_arrangements([task.plan])):
        assert current.operators["红"].temporary_dorm_fill
        assert not current.is_rescue_recovering("红", NOW)
        assert current._slot_takable(
            current.get_dorm_by_name("红")[1], requester=PRIMARY[0]
        )
