"""保留换班的派发与启动恢复使用同一个前置任务对象。"""

import copy
import pickle
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskScope, TaskTypes


@pytest.fixture
def scheduling_case(monkeypatch, offline_maintenance):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    forbidden = MagicMock(side_effect=AssertionError("unexpected external I/O"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    from arknights_mower.solvers import base_schedule as base

    class Clock(datetime):
        current = datetime(2026, 10, 27, 1, 3, 46)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.replace(tzinfo=tz)

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("陈", "", ["红"])],
                    "room_1_2": [
                        Room("阿罗玛", "", ["苍苔"]),
                        Room("槐琥", "", ["温米"]),
                        Room("砾", "", ["克洛丝"]),
                    ],
                    "room_3_3": [
                        Room("乌尔比安", "", ["安哲拉"]),
                        Room("跃跃", "", ["芙蓉"]),
                        Room("九色鹿", "", ["炎熔"]),
                    ],
                    "recycle": [Room("旅骨", "", ["星源"]), Room("芬", "", ["翎羽"])],
                    "dormitory_3": [
                        Room("杜林", "", []),
                        Room("蜜莓", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                    "dormitory_4": [
                        Room("安赛尔", "", []),
                        Room("嘉维尔", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", ""),
            ),
            "backup_plans": [
                Plan(
                    {"central": [Room("Current", "", [])]},
                    PlanConfig("", "", ""),
                    trigger=LogicExpression("True", "==", "False"),
                )
            ],
        }
    )
    assert data.init_and_validate() is None
    for op in data.operators.values():
        op._current_room, op.current_index = (
            (op.room, op.index) if op.is_high() else ("", -1)
        )
        op.mood, op.time_stamp = 12, Clock.current
    data.first_init = False
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = data
    solver.tasks, solver.task, solver.waiting_group_shifts = [], None, []
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.refresh_connecting = False
    solver.planned = True
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver.back_to_infrastructure = MagicMock()
    solver.recog, solver.device = MagicMock(), MagicMock()

    def arrange(plan, *args, **kwargs):
        solver.op_data = solver.op_data.project_arrangements([plan])
        return True

    solver.agent_arrange = MagicMock(side_effect=arrange)
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", lambda: (None, None)
    )
    return SimpleNamespace(solver=solver, base=base, clock=Clock, io=forbidden)


def retained_pair(case, scene):
    """保留现场任务类型和时间，安排使用通过校验的最小排班。"""
    solver = case.solver
    if scene == "night":
        previous = SchedulerTask(
            datetime(2026, 10, 27, 0, 5, 4, 85196),
            {
                "dormitory_3": ["杜林", "蜜莓", "乌尔比安", "跃跃", "九色鹿"],
                "dormitory_4": ["Current", "Current", "Current", "Current", "Free"],
            },
            TaskTypes.RE_ORDER,
        )
        following = SchedulerTask(
            case.clock.now(),
            {"room_1_2": ["阿罗玛", "槐琥", "Current"]},
            TaskTypes.SELF_CORRECTION,
        )
        solver.op_data = solver.op_data.project_arrangements(
            [{"room_1_2": ["苍苔", "温米", "砾"]}]
        )
    else:
        case.clock.current = datetime(2026, 10, 27, 13, 46, 33)
        previous = SchedulerTask(
            datetime(2026, 10, 27, 13, 43, 30, 264445),
            {
                "dormitory_3": ["Current", "Current", "阿罗玛", "Current", "Current"],
            },
            TaskTypes.SHIFT_OFF,
        )
        following = SchedulerTask(
            case.clock.now(),
            {"recycle": ["旅骨", "Current"]},
            TaskTypes.SELF_CORRECTION,
        )
        following.exhaust_support = True
        following.coordination_request_names = ("阿罗玛",)
        solver.op_data = solver.op_data.project_arrangements(
            [{"recycle": ["阿罗玛", "芬"], "room_1_2": ["苍苔", "温米", "砾"]}]
        )
    previous.backup_shift_active = True
    previous.backup_shift_conditions = list(solver.op_data.plan_condition)
    solver.tasks = [previous, following]
    solver.task = following
    solver._retain_failed_task(previous, "确认结果未核实", tuple(previous.plan))
    return previous, following


@pytest.mark.parametrize("scene", ["night", "afternoon"])
def test_retained_incident_dispatch_does_not_create_timed_retry(scheduling_case, scene):
    case = scheduling_case
    previous, following = retained_pair(case, scene)
    previous_state = previous.time, copy.deepcopy(previous.plan)
    original_time = following.time
    reserved = retained_task_reservations(case.solver.op_data, [previous])
    case.solver.infra_main()
    for _ in range(3):
        case.clock.current += timedelta(minutes=1)
        case.solver._resume_failed_tasks()
        if any(
            task is following
            for task in scheduler_task.task_view(
                case.solver.tasks, TaskScope.DISPATCH, case.solver.op_data
            )
        ):
            case.solver.task = following
            case.solver.infra_main()
    assert (previous.time, previous.plan) == previous_state
    assert any(task is previous for task in case.solver.tasks)
    assert previous.execution_failure and previous.backup_shift_active
    assert following.time == original_time
    assert retained_task_reservations(case.solver.op_data, [previous]) == reserved
    if scene == "night":
        assert not any(task is following for task in case.solver.tasks)
        case.solver.agent_arrange.assert_called_once()
    else:
        assert not any(task is following for task in case.solver.tasks)
        assert all(
            not call.args[0] for call in case.solver.agent_arrange.call_args_list
        )
    case.io.assert_not_called()


@pytest.mark.parametrize(
    "predecessor_field", ["group_shift_predecessors", "product_shift_predecessors"]
)
@pytest.mark.parametrize("waiting", [False, True])
def test_real_startup_rebinds_predecessors_to_restored_task(
    scheduling_case, monkeypatch, predecessor_field, waiting
):
    from arknights_mower import __main__ as mower
    from arknights_mower.utils import crash_recovery

    class Restored(BaseException):
        pass

    case = scheduling_case
    previous, following = retained_pair(case, "afternoon")
    if predecessor_field == "product_shift_predecessors":
        # 额外构造同岗位冲突，验证依赖引用；这不是现场完整安排的回放。
        previous.plan["recycle"] = ["旅骨", "Current"]
        case.solver._retain_failed_task(
            previous, "确认结果未核实", tuple(previous.plan)
        )
        following.exhaust_support = False
        case.solver.infra_main()
        assert following.product_shift_predecessors == (previous,)
    else:
        following.group_shift_predecessors = (previous,)
    if waiting:
        following.group_shift_waiting = set()
    tasks = [previous] if waiting else [previous, following]
    waiting_tasks = [following] if waiting else []
    saved = pickle.loads(
        pickle.dumps(
            {
                "tasks": tasks,
                "waiting_group_shifts": waiting_tasks,
                "operators": {},
                "dorm": [],
                "party_time": None,
                "daily_visit_friend": case.clock.now().date(),
                "daily_report": case.clock.now().date(),
                "daily_skland": case.clock.now().date(),
                "daily_mail": case.clock.now().date(),
                "task_count": 1,
            }
        )
    )
    operators = MagicMock(operators={}, backup_plans=case.solver.op_data.backup_plans)
    operators.validate_backup_plans.return_value = {"success": True}
    restored = object.__new__(case.base.BaseSchedulerSolver)
    restored.tasks, restored.op_data = [], operators
    restored.initialize_operators = lambda: None
    restored._pending_group_transitions = lambda: {}
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    monkeypatch.setattr(mower, "base_scheduler", None)
    monkeypatch.setattr(mower, "initialize", lambda *args, **kwargs: restored)
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        mower, "_apply_version_update_resting_threshold", lambda *args: None
    )

    def after_restoration():
        raise Restored

    monkeypatch.setattr(mower, "refresh_resource_at_boundary", after_restoration)
    with pytest.raises(Restored):
        mower.simulate(saved)
    new_previous = restored.tasks[0]
    new_following = restored.waiting_group_shifts[0] if waiting else restored.tasks[1]
    assert getattr(new_following, predecessor_field)[0] is new_previous
    assert (new_previous.time, new_previous.plan) == (previous.time, previous.plan)
    assert new_previous.execution_failure == previous.execution_failure
    assert new_following.time == following.time
    if predecessor_field == "product_shift_predecessors" and not waiting:
        solver = case.solver
        solver.tasks = restored.tasks
        original_plan = copy.deepcopy(new_previous.plan)
        for _ in range(3):
            case.clock.current += timedelta(minutes=1)
            solver._resume_failed_tasks()
            assert new_following.execution_failure
        solver.op_data.room_observations["recycle"] = 1
        solver._resume_failed_tasks()
        assert not getattr(new_previous, "execution_failure", None)
        assert new_previous.backup_shift_active
        assert new_following.execution_failure
        assert new_previous.plan == original_plan
        solver.task = new_previous
        solver.infra_main()
        assert not any(task is new_previous for task in solver.tasks)
        solver._resume_failed_tasks()
        assert not getattr(new_following, "execution_failure", None)
        assert new_following.time == following.time
        solver.task = new_following
        solver.infra_main()
        assert not any(task is new_following for task in solver.tasks)
        solver._resume_failed_tasks()
        assert not any(task is new_following for task in solver.tasks)
