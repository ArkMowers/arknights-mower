"""整轮换班复用选人规则，副表、纠错及补床在设备操作前收敛。"""

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import shift_backup_convergence_tests as backup
from arknights_mower.utils import config, operators, scheduler_task
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.operators import Operator, Operators, build_global_plan
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

solver = backup.solver
FIXTURES = Path(__file__).with_name("fixtures")


def apply(solver, task):
    solver._activate_shift_backup(task)
    solver.op_data = solver.op_data.project_arrangements([task.plan])
    task.backup_shift_active = False
    solver.tasks, solver.task = [], None


@pytest.mark.parametrize(
    "kind", [TaskTypes.SHIFT_ON, TaskTypes.SELF_CORRECTION, TaskTypes.RE_ORDER]
)
def test_return_releases_beds_for_next_group_before_idle_filling(solver, kind):
    task = backup.resting(solver)
    task.type = kind
    for name in solver.op_data.groups["红松"]:
        solver.op_data.operators[name].mood = 24
    for name in solver.op_data.groups["深海"]:
        solver.op_data.operators[name].mood = 1
    before = backup.positions(solver.op_data)
    solver._prepare_shift_cycle(task)
    assert backup.positions(solver.op_data) == before
    assert solver.tasks == [task]
    apply(solver, task)
    assert all(
        solver.op_data.operators[name].is_resting()
        for name in solver.op_data.groups["深海"]
    )
    assert all(
        solver.op_data.operators[name].is_working()
        for name in solver.op_data.groups["红松"]
    )
    assert not solver.agent_get_mood(read_rooms=False, return_plan=True)
    next_task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    solver._prepare_shift_cycle(next_task)
    assert not next_task.plan


def test_fill_entry_does_not_jump_ahead_of_due_return(solver):
    task = backup.resting(solver)
    solver.op_data = solver.op_data.project_arrangements(
        [{"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}]
    )
    assert solver._fill_empty_dorms() is False
    assert solver.tasks == [task]


@pytest.mark.parametrize(
    "priority", [TaskTypes.FIAMMETTA, TaskTypes.RUN_ORDER, TaskTypes.SWAP_SUPPORT]
)
def test_urgent_task_preserves_original_boundary(solver, monkeypatch, priority):
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    task = backup.resting(solver)
    deadline = SchedulerTask(task_type=priority, time=datetime.now())
    solver.tasks.append(deadline)
    before = copy.deepcopy(task.plan)
    solver.resting = MagicMock(side_effect=AssertionError("must not expand shift"))
    solver._prepare_shift_cycle(task)
    solver.resting.assert_not_called()
    assert deadline in solver.tasks
    if priority == TaskTypes.FIAMMETTA:
        assert task.plan == before


def test_failed_convergence_does_not_commit_positions_or_task(solver, monkeypatch):
    task = backup.downshift(solver)
    before = backup.positions(solver.op_data), copy.deepcopy(task.plan)

    def fail(*args, **kwargs):
        raise ValueError("inconsistent backup")

    monkeypatch.setattr(base.BaseSchedulerSolver, "_prepare_shift_backup", fail)
    with pytest.raises(ValueError, match="inconsistent backup"):
        solver._prepare_shift_cycle(task)
    assert (backup.positions(solver.op_data), task.plan) == before
    assert not hasattr(task, "backup_shift_conditions")


@pytest.fixture
def logged_solver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 9, 29, 17, 4, 1)

    for module in (base, operators, scheduler_task):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate_json(
            (FIXTURES / "shift_cycle_plan_20260929.json").read_text()
        ),
    )
    for key, value in config.plan.advanced_settings.items():
        if hasattr(config.conf, key):
            setattr(config.conf, key, value)
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(base, "_is_mastery_busy", lambda name: False)
    state = json.loads((FIXTURES / "shift_cycle_state_20260929.json").read_text())
    instance = object.__new__(base.BaseSchedulerSolver)
    instance.op_data = Operators(build_global_plan())
    assert instance.op_data.init_and_validate() is None
    assert instance.op_data.swap_plan(state["conditions"], refresh=True) is None
    for name, values in state["operators"].items():
        if name not in instance.op_data.operators:
            instance.op_data.add(Operator(name, ""))
        for key, value in values.items():
            if key == "time_stamp" and value:
                value = datetime.fromisoformat(value)
            if key == "dorm_recovery_fixed":
                value = tuple(tuple(item) for item in value)
            setattr(instance.op_data.operators[name], key, value)
    for bed in instance.op_data.dorm:
        saved = next(
            (b for b in state["dorms"] if tuple(b["position"]) == bed.position), None
        )
        if saved:
            bed.name = saved["name"]
            bed.time = datetime.fromisoformat(saved["time"]) if saved["time"] else None
    instance.op_data.first_init = False
    instance.task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan=state["shift_on"]
    )
    instance.tasks = [instance.task]
    instance._sync_run_order_tasks = MagicMock()
    instance.last_train_mood_read = Clock.now()
    return instance


@pytest.mark.parametrize("calibrated", [False, True])
def test_logged_return_and_automation_rest_converge_in_one_plan(
    logged_solver, calibrated
):
    """16:34 缓存＋同日排班＋17:04 回班意图；不是完整设备读屏回放。"""
    solver = logged_solver
    if calibrated:
        # 充能前最后一次实测速度；验证保留速度后直接退出满心情副表。
        solver.op_data.operators["歌蕾蒂娅"].depletion_rate = 3.29993792234696
    original = backup.positions(solver.op_data)
    task = solver.task
    solver._prepare_shift_cycle(task)
    assert backup.positions(solver.op_data) == original
    final = copy.deepcopy(task.plan)
    apply(solver, task)
    assert all(
        solver.op_data.operators[n].is_resting()
        for n in ["森蚺", "温蒂", "清流", "鸿雪", "图耶", "承曦格雷伊"]
    )
    assert solver.op_data.operators["埃癸斯"].current_room == "room_2_3"
    assert all(
        "埃癸斯" not in names
        for room, names in final.items()
        if room.startswith("dorm")
    )
    assert solver.op_data.plan_condition[5]
    assert solver.op_data.plan_condition[1] is (not calibrated)
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert not correction
    next_task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    solver._prepare_shift_cycle(next_task)
    assert not next_task.plan


def test_no_backups_still_rotates_after_return(solver):
    task = backup.resting(solver)
    solver.op_data.backup_plans = []
    solver.op_data.plan_condition = []
    for name in solver.op_data.groups["红松"]:
        solver.op_data.operators[name].mood = 24
    for name in solver.op_data.groups["深海"]:
        solver.op_data.operators[name].mood = 1
    solver._prepare_shift_cycle(task)
    apply(solver, task)
    assert all(
        solver.op_data.operators[n].is_resting() for n in solver.op_data.groups["深海"]
    )


def test_queued_fill_is_recomputed_and_future_special_task_is_retained(solver):
    task = backup.resting(solver)
    for name in solver.op_data.groups["红松"]:
        solver.op_data.operators[name].mood = 24
    for name in solver.op_data.groups["深海"]:
        solver.op_data.operators[name].mood = 1
    old_fill = SchedulerTask(
        task_type=TaskTypes.FILL_DORM,
        task_plan={"dormitory_1": ["Current", "Current", "酒神", "食铁兽", "陈"]},
    )
    later = SchedulerTask(
        task_type=TaskTypes.RUN_ORDER,
        time=datetime.now() + timedelta(hours=1),
        task_plan={"room_1_2": ["但书", "Current"]},
    )
    solver.tasks += [old_fill, later]
    solver._prepare_shift_cycle(task)
    assert solver.tasks == [task, later]
    apply(solver, task)
    assert all(
        solver.op_data.operators[n].is_resting() for n in solver.op_data.groups["深海"]
    )


def test_repeated_projection_rejects_without_committing(solver, monkeypatch):
    solver.op_data.backup_plans = []
    solver.op_data.plan_condition = []
    task = SchedulerTask(
        task_type=TaskTypes.SHIFT_ON, task_plan={"central": ["薇薇安娜"]}
    )
    before = copy.deepcopy(task.plan), backup.positions(solver.op_data)

    def alternating(self, **kwargs):
        current = self.op_data.get_current_operator("central", 0).name
        return {"central": ["陈" if current == "薇薇安娜" else "薇薇安娜"]}

    monkeypatch.setattr(base.BaseSchedulerSolver, "resting", alternating)
    with pytest.raises(ValueError, match="完整换班预演出现循环"):
        solver._prepare_shift_cycle(task)
    assert (task.plan, backup.positions(solver.op_data)) == before


def test_unknown_game_selected_fill_is_left_for_one_actual_read(solver, monkeypatch):
    solver.op_data.backup_plans = []
    solver.op_data.plan_condition = []
    solver.resting = MagicMock(return_value={})
    solver.agent_get_mood = MagicMock(return_value={})

    def fill(plan, time, data, tasks, **kwargs):
        tasks.append(
            SchedulerTask(
                task_type=TaskTypes.FILL_DORM,
                task_plan={
                    "dormitory_1": ["Current", "Current", "Free", "Free", "Free"]
                },
            )
        )

    monkeypatch.setattr(base, "try_add_release_dorm", fill)
    task = SchedulerTask(task_type=TaskTypes.SHIFT_OFF)
    solver._prepare_shift_cycle(task)
    assert task.plan == {"dormitory_1": ["Current", "Current", "Free", "Free", "Free"]}
    assert all(not bed.name for bed in solver.op_data.dorm)


def test_empty_exhaust_trigger_and_planning_wakeup_are_not_consumed(solver):
    task = backup.resting(solver)
    triggers = [
        SchedulerTask(task_type=TaskTypes.EXHAUST_OFF, meta_data="乌尔比安"),
        SchedulerTask(),
    ]
    solver.tasks.extend(triggers)
    solver._prepare_shift_cycle(task)
    assert all(any(t is trigger for t in solver.tasks) for trigger in triggers)


def test_projection_reuses_eval_rules_without_copying_runtime_builtins(solver):
    class RuntimeBuiltin:
        def __deepcopy__(self, memo):
            raise TypeError("runtime builtin cannot be copied")

    # eval 注入的内建对象可能包含平台扩展句柄，不能随心情缓存深拷贝。
    solver.op_data.eval_model.imported_functions["__builtins__"] = {
        "runtime_handle": RuntimeBuiltin()
    }
    task = backup.resting(solver)
    before = backup.positions(solver.op_data)
    solver._prepare_shift_cycle(task)
    assert backup.positions(solver.op_data) == before
    assert task.plan
    apply(solver, task)
    assert not solver.agent_get_mood(read_rooms=False, return_plan=True)


def test_vacancy_check_does_not_start_work_correction_without_rotation(solver):
    for op in solver.op_data.operators.values():
        op.mood = 24
    # 独立工作纠错留给原巡检流程，不能因为空床额外生成换班。
    solver.op_data.operators["薇薇安娜"]._current_room = ""
    solver.agent_get_mood = MagicMock(
        side_effect=AssertionError("unexpected correction")
    )
    before = backup.positions(solver.op_data)
    assert solver._fill_empty_dorms()
    assert all(task.type == TaskTypes.FILL_DORM for task in solver.tasks)
    assert backup.positions(solver.op_data) == before
    solver.agent_get_mood.assert_not_called()


@pytest.mark.parametrize("free_room", [False, True])
def test_vacancy_check_converges_eligible_rotation_before_idle_filling(
    solver, free_room
):
    solver.op_data.config.free_room = free_room
    solver._scan_card_moods = MagicMock()
    for op in solver.op_data.operators.values():
        op.mood = 24
    for name in solver.op_data.groups["红松"]:
        solver.op_data.operators[name].mood = 1
    before = backup.positions(solver.op_data)
    assert solver._fill_empty_dorms() is False
    assert backup.positions(solver.op_data) == before
    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    assert task.type == TaskTypes.SHIFT_OFF
    solver._prepare_shift_cycle(task)
    assert backup.positions(solver.op_data) == before
    assert task.backup_shift_conditions == [True]
    apply(solver, task)
    assert all(
        solver.op_data.operators[name].is_resting()
        for name in solver.op_data.groups["红松"]
    )
    assert not solver.agent_get_mood(read_rooms=False, return_plan=True)
