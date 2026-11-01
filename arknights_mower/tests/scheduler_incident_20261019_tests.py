"""用户提供的完整排班与日志中的个人离宿、临时换组过程。"""

import copy
import json
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.usefixtures("offline_maintenance")

NOW = datetime(2026, 10, 19, 18, 20, 43)


@pytest.fixture
def incident(monkeypatch, request):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule, record
    from arknights_mower.utils import config, group_recovery, operators, scheduler_task
    from arknights_mower.utils.config.plan import PlanModel
    from arknights_mower.utils.config.plan_advanced import apply_advanced_settings

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    for module in (base_schedule, operators, scheduler_task, group_recovery):
        monkeypatch.setattr(module, "datetime", Clock)
    raw = json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath(getattr(request, "param", "scheduler_incident_20261019_plan.json"))
        .read_text(encoding="utf-8")
    )
    conf = apply_advanced_settings(
        config.Conf(enable_mastery=False), raw["advanced_settings"]
    )
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(record, "save_agent_action", lambda *a, **kw: None)
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    data = operators.Operators(
        operators.build_global_plan(
            plan_model=PlanModel.model_validate(raw), conf_model=conf
        )
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op.current_room, op.current_index = op.room, op.index
        op.mood, op.time_stamp = 24, NOW
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data = data
    solver.task, solver.tasks = None, []
    return solver, base_schedule


def test_personal_release_keeps_food_beast_in_recovery(incident, monkeypatch):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, base = incident
    data = solver.op_data
    assert (data.operators["令"].lower_limit, data.operators["令"].upper_limit) == (
        0,
        12,
    )
    assert (
        data.operators["食铁兽"].lower_limit,
        data.operators["食铁兽"].upper_limit,
    ) == (12, 24)
    for name, room, index, mood, minutes in [
        ("令", "dormitory_2", 2, 11.46, 4),
        ("食铁兽", "dormitory_3", 4, 14.01, 125),
    ]:
        op = data.operators[name]
        op.current_room, op.current_index = room, index
        op.mood = mood
        _, bed = data.get_dorm_by_name(name)
        bed.name, bed.time = name, NOW + timedelta(minutes=minutes)
    data.group_shift_state["结城理"] = True
    data.group_recovery_full_members["结城理"] = ["令", "食铁兽"]
    returning = SchedulerTask(
        NOW + timedelta(minutes=125),
        {"room_2_2": ["Current", "食铁兽", "结城理"]},
        TaskTypes.SHIFT_ON,
    )
    task = SchedulerTask(
        NOW,
        {"dormitory_2": ["Current", "Current", "Free", "Current", "Current"]},
        TaskTypes.RELEASE_DORM,
        "令",
    )
    task.strict_mood_limit, task.mood_limit = True, 12
    solver.task, solver.tasks = task, [task, returning]

    class BeforeInput(Exception):
        pass

    def before_input(*args, **kwargs):
        assert set(task.plan) == {"dormitory_2"}
        assert returning.plan["room_2_2"][1] == "食铁兽"
        raise BeforeInput

    monkeypatch.setattr(base, "defer_dorm_before_priority_task", before_input)
    with pytest.raises(BeforeInput):
        solver.arrange_release_dorm()
    assert returning in solver.tasks
    assert returning.time == NOW + timedelta(minutes=125)
    assert data.operators["食铁兽"].current_room == "dormitory_3"


def test_actual_return_then_backup_round_trip_does_not_restore_old_wait(incident):
    from arknights_mower.utils.group_recovery import group_recovery_deadline

    solver, _ = incident
    data = solver.op_data
    op = data.operators["食铁兽"]
    op.current_room, op.current_index = "dormitory_3", 4
    data.group_shift_state["结城理"] = True
    data.group_recovery_full_members["结城理"] = [op.name]
    data.group_recovery_return_time["结城理"] = NOW
    data.update_detail(op.name, 14.09, op.room, op.index, True)
    conditions = [backup.name == "自动化下班" for backup in data.backup_plans]
    assert any(conditions)
    assert data.swap_plan(conditions, refresh=True) is None
    op = data.operators["食铁兽"]
    assert op.group == "自动化" and op.workaholic
    op.current_room, op.current_index = "", -1
    assert data.swap_plan([False] * len(conditions), refresh=True) is None
    op = data.operators["食铁兽"]
    assert op.group == "结城理" and not op.workaholic and not op.rest_in_full
    saved = pickle.loads(pickle.dumps(data.group_recovery_full_members))
    data.restore_group_shift_state(
        data.group_shift_state, saved, data.group_recovery_return_time
    )
    for _ in range(3):
        required, _ = group_recovery_deadline(data, op.group, now=NOW)
        assert op.name not in required
        assert solver.tasks == []


@pytest.mark.parametrize(
    "incident", ["scheduler_incident_20261020_plan.json"], indirect=True
)
def test_waiting_group_does_not_rebuild_cancelled_shared_dorm_correction(
    incident, monkeypatch
):
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    solver, base = incident
    data = solver.op_data
    data.first_init = False
    data.swap_plan([True, False, True, False], refresh=True)
    # 自动化继续休息，感知仍在岗；塑心应由隐德来希接替固定岗位。
    data.commit_group_shifts(
        {"自动化": True, "感知": False, "深海": False, "红松": False}
    )
    for name in ("流明", "塑心"):
        data.operators[name]._current_room, data.operators[name].current_index = "", -1
    data.operators["隐德来希"]._current_room = "dormitory_3"
    data.operators["隐德来希"].current_index = 0
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    for name, room, index in [
        ("森蚺", "dormitory_2", 4),
        ("图耶", "dormitory_3", 2),
        ("承曦格雷伊", "dormitory_3", 4),
        ("清流", "dormitory_2", 2),
    ]:
        op = data.operators[name]
        op._current_room, op.current_index = room, index
        op.mood, op.time_stamp = 12, NOW
    waiting = SchedulerTask(
        NOW,
        {
            "central": ["Current", "Current", "森蚺", "Current", "Current"],
            "room_2_1": ["图耶"],
            "room_1_3": ["承曦格雷伊"],
            "room_3_2": ["清流", "温蒂"],
            "dormitory_2": ["流明", "Current", "Current", "Current", "Current"],
        },
        TaskTypes.SHIFT_ON,
    )
    waiting.group_shift_waiting = {"自动化"}
    waiting.group_shift_predecessors = ()
    solver.waiting_group_shifts = [waiting]
    first = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert first.get("dormitory_3", ["Current"])[0] != "塑心"
    original = copy.deepcopy(waiting.plan)
    original_time = waiting.time
    assert first
    task = SchedulerTask(NOW, first, TaskTypes.SELF_CORRECTION)
    solver.task, solver.tasks = task, [task]
    solver._prepare_group_shift(task, remember_targets=True)
    selected = []
    order_reads = []

    def read_order_time(room):
        assert task.plan == {}
        order_reads.append(room)
        return NOW + timedelta(hours=1)

    def arrange_room(new_plan, room, plan, **kwargs):
        row = plan.pop(room)
        selected.append(room)
        projected = data.project_arrangements([{room: row}])
        data.operators, data.dorm = projected.operators, projected.dorm
        for name in row:
            if name in data.operators:
                data.operators[name].mood, data.operators[name].time_stamp = 24, NOW
        return new_plan

    monkeypatch.setattr(solver, "agent_arrange_room", arrange_room)
    monkeypatch.setattr(solver, "get_run_order_time", read_order_time)
    solver.agent_arrange(task.plan)
    assert selected
    assert "dormitory_3" not in selected
    assert sorted(order_reads) == ["room_1_1", "room_3_1"]
    assert sorted(
        (pending.meta_data, pending.time)
        for pending in solver.tasks
        if pending.type == TaskTypes.RUN_ORDER
    ) == [
        ("room_1_1", NOW + timedelta(hours=1)),
        ("room_3_1", NOW + timedelta(hours=1)),
    ]
    solver.task, solver.tasks = None, []
    for _ in range(3):
        assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
        assert solver.tasks == []
        assert solver.waiting_group_shifts == [waiting]
        assert waiting.plan == original and waiting.time == original_time
    # 真正观察到组员回岗后，固定宿管仍按正常组回班规则返回。
    observed = data.project_arrangements([waiting.plan])
    data.operators, data.dorm = observed.operators, observed.dorm
    data.commit_group_shifts({"自动化": False})
    solver.waiting_group_shifts = []
    returning = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert returning["dormitory_3"][0] == "塑心"
