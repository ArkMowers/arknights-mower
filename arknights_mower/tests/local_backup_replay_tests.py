"""完整本地排班＋2026-09-27 00:42 日志缓存的调度回放。

plan 保留本地全部八张副表；日志不含当时完整 plan，二者不是同版本快照。
只替代设备点击，排班加载、条件求值、纠错和副表收敛使用实际代码。
"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, try_reorder

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.fixture
def replay(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 9, 27, 0, 42, 36)

        @classmethod
        def now(cls):
            return cls.current

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.experimental_dorm_logic = True
    config.conf.enable_mastery = False
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate_json(
            (FIXTURES / "local_backup_plan_20260927.json").read_text()
        ),
    )
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    state = json.loads((FIXTURES / "backup_log_state_20260927.json").read_text())
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(build_global_plan())
    assert solver.op_data.init_and_validate() is None
    assert len(solver.op_data.backup_plans) == 8
    assert solver.op_data.swap_plan(state["conditions"], refresh=True) is None
    for name, values in state["operators"].items():
        if name not in solver.op_data.operators:
            solver.op_data.add(Operator(name, ""))
        op = solver.op_data.operators[name]
        for key, value in values.items():
            if key == "time_stamp" and value is not None:
                value = datetime.fromisoformat(value)
            setattr(op, key, value)
    for saved in state["dorms"]:
        for bed in solver.op_data.dorm:
            if tuple(saved["position"]) == bed.position:
                bed.name = saved["name"]
                bed.time = (
                    datetime.fromisoformat(saved["time"]) if saved["time"] else None
                )
    solver.op_data.first_init = False
    solver.task, solver.tasks = None, []
    solver.find = MagicMock(return_value=True)
    solver.skip = MagicMock()
    solver.refresh_connecting = False
    solver._sync_run_order_tasks = MagicMock()
    solver.queue_product_switches = MagicMock()
    solver.log_state = state
    return solver


def execute(solver, task):
    base.datetime.current = max(base.datetime.now(), task.time)
    solver.tasks = [task]
    solver.task = task
    seen = []

    def arrange(plan, get_time):
        seen.append(copy.deepcopy(plan))
        solver.op_data = solver.op_data.project_arrangements([plan])
        plan.clear()

    solver.agent_arrange = MagicMock(side_effect=arrange)
    solver.infra_main()
    assert len(seen) == 1
    return seen[0]


def test_logged_automation_downshift_installs_fiammetta_in_new_dorm(replay):
    final = execute(
        replay,
        SchedulerTask(
            task_type=TaskTypes.SHIFT_OFF, task_plan=replay.log_state["shift_off"]
        ),
    )
    assert replay.op_data.plan_condition[4]
    assert final["dormitory_4"][3] == "菲亚梅塔"
    assert replay.op_data.operators["菲亚梅塔"].current_room == "dormitory_4"


@pytest.mark.parametrize("group", ["感知", "红松"])
@pytest.mark.parametrize(
    "kind", [TaskTypes.SHIFT_ON, TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER]
)
def test_full_plan_return_goes_directly_to_main_posts(replay, group, kind):
    data = replay.op_data
    names = [name for name in data.groups[group] if not data.operators[name].workaholic]
    rest = {}
    replay.get_resting_plan(names, [], rest, [])
    rest.update(try_reorder(data, rest) or {})
    assert any(room.startswith("dorm") for room in rest)
    execute(replay, SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=rest))
    backup_index = 3 if group == "感知" else 2
    assert replay.op_data.plan_condition[backup_index]
    assert not replay.agent_get_mood(read_rooms=False, return_plan=True)
    for bed in replay.op_data.dorm:
        if bed.name in names:
            # 只推进到回班，不把无关干员的心情缓存推进到过期。
            bed.time = base.datetime.now() + timedelta(minutes=5)
    # 从实际床位生成上班预约，而不是手写一份简化的回班名单。
    replay.tasks = []
    replay.plan_metadata()
    task = next(
        task
        for task in replay.tasks
        if task.type == TaskTypes.SHIFT_ON
        and any(name in names for occupants in task.plan.values() for name in occupants)
    )
    task.type = kind
    before = copy.deepcopy(task.plan)
    final = execute(replay, task)
    assert not replay.op_data.plan_condition[backup_index]
    expected_room = "room_3_2" if group == "感知" else "room_1_2"
    returning = ["槐琥", "迷迭香"] if group == "感知" else ["野鬃", "灰毫"]
    assert any(name in occupants for occupants in before.values() for name in returning)
    assert all(
        replay.op_data.operators[name].current_room == expected_room
        for name in returning
    )
    assert not any(
        name in occupants
        for room, occupants in final.items()
        if room != expected_room
        for name in returning
    )
    assert not any(t.meta_data == "副表内存收敛" and t.plan for t in replay.tasks)
    assert not replay.agent_get_mood(read_rooms=False, return_plan=True)


def test_full_plan_real_correction_after_recovery_skips_backup_posts(replay):
    names = replay.op_data.groups["感知"].copy()
    rest = {}
    replay.get_resting_plan(names, [], rest, [])
    rest.update(try_reorder(replay.op_data, rest) or {})
    execute(replay, SchedulerTask(task_type=TaskTypes.SHIFT_OFF, task_plan=rest))
    assert replay.op_data.plan_condition[3]
    for name in names:
        op = replay.op_data.operators[name]
        op.mood, op.time_stamp = op.upper_limit, base.datetime.now()
    for bed in replay.op_data.dorm:
        if bed.name in names:
            bed.time = base.datetime.now() - timedelta(seconds=1)
    # 基于日志缓存构造部分回班：槐琥已回副表岗位，其余组员仍在宿舍。
    # 整组正常休息不会触发纠错，不能把回满本身当作纠错触发条件。
    replay.op_data = replay.op_data.project_arrangements(
        [{"room_2_2": ["Current", "槐琥", "Current"]}]
    )
    replay.task, replay.tasks = None, []
    assert replay.agent_get_mood(read_rooms=False) == "self_correction"
    task = next(t for t in replay.tasks if t.type == TaskTypes.SELF_CORRECTION)
    assert task.plan["room_2_2"][2] == "迷迭香"
    final = execute(replay, task)
    assert final["room_3_2"][1:] == ["槐琥", "迷迭香"]
    assert final["room_2_2"][1:] == ["乌尔比安", "安哲拉"]
    assert not replay.op_data.plan_condition[3]
    assert not any(t.meta_data == "副表内存收敛" and t.plan for t in replay.tasks)
    assert not replay.agent_get_mood(read_rooms=False, return_plan=True)
