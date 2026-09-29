"""任务丢失后，用尽回满干员仍根据宿舍实况完成本轮休息。"""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, operators, resting_correction, scheduler_task
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import TaskTypes

NOW = datetime(2026, 9, 29, 12)
DORM = "dormitory_1"


@pytest.fixture
def solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    for module in (base, operators, resting_correction, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    monkeypatch.setattr(operators.Operators, "current_room_changed_callback", None)
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.tasks, instance.task = [], None
    instance.global_plan = {
        "default_plan": Plan(
            {
                "contact": [Room("阿罗玛", "", ["引星棘刺", "赫默"])],
                DORM: [Room("冰酿", "", []), Room("闪灵", "", [])]
                + [Room("Free", "", []) for _ in range(3)],
            },
            PlanConfig("阿罗玛", "阿罗玛", ""),
        ),
        "backup_plans": [],
    }
    assert instance.initialize_operators() is None
    operators.Operators.current_room_changed_callback = None
    instance.op_data = instance.op_data.project_arrangements(
        [{"contact": ["Free"], DORM: ["冰酿", "闪灵", "阿罗玛", "Free", "Free"]}]
    )
    for op in instance.op_data.operators.values():
        op.mood, op.time_stamp = 10, NOW
    # 替班已占用；原上班任务仍在时，本轮休息等待到回满。
    for name in ("引星棘刺", "赫默"):
        instance.op_data.operators[name].current_room = "meeting"
    _, bed = instance.op_data.get_dorm_by_name("阿罗玛")
    bed.name, bed.time = "阿罗玛", NOW + timedelta(hours=2)
    instance.tasks, instance.task = [], None
    instance.find_next_task = MagicMock(return_value=None)
    instance.enter_room = MagicMock(
        side_effect=AssertionError("unexpected device read")
    )
    instance.plan_metadata()
    assert any(t.type == TaskTypes.SHIFT_ON for t in instance.tasks)
    return instance


def lose_tasks(solver, restart):
    if restart:
        saved_ops = deepcopy(solver.op_data.operators)
        saved_dorms = deepcopy(solver.op_data.all_dorms())
        assert solver.initialize_operators() is None
        operators.Operators.current_room_changed_callback = None
        for name, saved in saved_ops.items():
            op = solver.op_data.operators[name]
            for attr in (
                "mood",
                "time_stamp",
                "depletion_rate",
                "current_room",
                "current_index",
            ):
                setattr(op, attr, getattr(saved, attr))
        solver.op_data.restore_dorm_state(saved_dorms)
    solver.tasks = []


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("deadline", [False, True])
def test_lost_return_task_does_not_recall_unfinished_warmup(solver, restart, deadline):
    lose_tasks(solver, restart)
    _, bed = solver.op_data.get_dorm_by_name("阿罗玛")
    if not deadline:
        bed.time = None
    for _ in range(3):
        assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
    # 顺带读到时间后复用正常规划重建预约，不依赖旧任务对象。
    bed.time = NOW + timedelta(hours=2)
    solver.plan_metadata()
    returns = [t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]
    assert len(returns) == 1
    assert returns[0].time == bed.time
    assert returns[0].plan["contact"] == ["阿罗玛"]
    assert solver.op_data.operators["阿罗玛"].is_resting()
    solver.enter_room.assert_not_called()


def test_lost_return_task_uses_available_cover(solver):
    lose_tasks(solver, True)
    solver.op_data.operators["赫默"].current_room = ""
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {
        "contact": ["赫默"]
    }


@pytest.mark.parametrize("upper", [12, 20, 24])
def test_normal_planning_rebuilds_only_one_return_at_effective_limit(
    solver, monkeypatch, upper
):
    lose_tasks(solver, True)
    data = solver.op_data
    op = data.operators["阿罗玛"]
    op.upper_limit = upper
    _, bed = data.get_dorm_by_name(op.name)
    bed.time = None
    # 游戏倒计时到 24，复用读房时的换算得到实际设置上限的回满时间。
    data.refresh_dorm_time(
        DORM, 2, {"agent": op.name, "time": NOW + timedelta(hours=7)}
    )
    expected = NOW + timedelta(hours=(upper - op.mood) / 2)
    assert bed.time == expected
    solver._read_agent_mood = MagicMock()
    solver.resting = MagicMock(return_value={})
    solver._fill_empty_dorms = MagicMock()
    solver.backup_plan_solver = MagicMock()
    monkeypatch.setattr(base, "try_reorder", lambda *args: None)
    monkeypatch.setattr(base, "try_workshop_tasks", lambda *args: None)
    monkeypatch.setattr(base, "try_add_release_dorm", lambda *args: None)
    for _ in range(3):
        # 与正常规划入口一致：先纠错，再复用 plan_solver 重建派生任务。
        assert solver.agent_get_mood(skip_dorm=True) is None
        solver.plan_solver()
        returns = [t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]
        assert len(returns) == 1
        assert returns[0].time == expected
        assert returns[0].plan["contact"] == [op.name]
        assert not any(t.type == TaskTypes.SELF_CORRECTION for t in solver.tasks)


@pytest.mark.parametrize("upper", [12, 20, 24])
def test_completed_warmup_can_return_after_restart(solver, upper):
    lose_tasks(solver, True)
    op = solver.op_data.operators["阿罗玛"]
    op.upper_limit = upper
    op.mood = upper
    _, bed = solver.op_data.get_dorm_by_name(op.name)
    bed.time = NOW
    assert solver.agent_get_mood(
        skip_dorm=True, read_rooms=False, return_plan=True
    ) == {"contact": ["阿罗玛"]}


@pytest.mark.parametrize("setting", ["exhaust", "full"])
def test_other_correction_rules_are_unchanged(solver, setting):
    lose_tasks(solver, False)
    op = solver.op_data.operators["阿罗玛"]
    if setting == "exhaust":
        op.exhaust_require = False
    else:
        op.rest_in_full = False
    assert solver.agent_get_mood(
        skip_dorm=True, read_rooms=False, return_plan=True
    ) == {"contact": ["阿罗玛"]}
