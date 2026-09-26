"""埃癸斯从会客室休息后接替发电站，旧回班不能把他再次拉走。"""

from datetime import datetime, timedelta

import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def solver(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    instance = object.__new__(BaseSchedulerSolver)
    instance.op_data = Operators(
        {
            "default_plan": Plan(
                {
                    "meeting": [
                        Room("埃癸斯", "", ["信仰搅拌机"]),
                        Room("虎狼丸", "", ["跃跃"]),
                    ],
                    "room_3_3": [Room("Lancet-2", "", ["澄闪"])],
                    "dormitory_1": [
                        Room("杜林", "", []),
                        Room("桃金娘", "", []),
                        *[Room("Free", "", []) for _ in range(3)],
                    ],
                },
                PlanConfig("", "", "", experimental_dorm_logic=True),
            ),
            "backup_plans": [],
        }
    )
    assert instance.op_data.init_and_validate() is None
    instance.op_data.first_init = False
    instance.tasks = []
    instance.task = None
    monkeypatch.setattr(
        Operators, "current_room_changed_callback", instance.current_room_changed
    )
    return instance


def shift_on(plan):
    return SchedulerTask(
        time=datetime.now() + timedelta(hours=1),
        task_type=TaskTypes.SHIFT_ON,
        task_plan=plan,
    )


@pytest.mark.parametrize("previous_room", ["", "dormitory_1"])
@pytest.mark.parametrize("first_init", [False, True])
def test_observed_start_of_work_cancels_all_old_returns(
    solver, previous_room, first_init
):
    data = solver.op_data
    op = data.operators["埃癸斯"]
    op._current_room, op.current_index = previous_room, 2 if previous_room else -1
    data.first_init = first_init
    stale = shift_on({"meeting": ["埃癸斯", "Current"]})
    stale_with_cleanup = shift_on(
        {
            "meeting": ["埃癸斯", "Current"],
            "dormitory_1": ["Current", "Current", "Free", "Current", "Current"],
        }
    )
    solver.tasks = [stale, stale_with_cleanup]
    # 埃癸斯没有刷新跑单或用尽的设置，也必须收到实际上岗通知。
    assert not op.refresh_order_room[0] and not op.refresh_drained
    data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert solver.tasks == []
    assert op.is_working()


def test_merged_returns_keep_other_people_and_execution_time(solver):
    task = shift_on({"meeting": ["埃癸斯", "虎狼丸"]})
    when = task.time
    solver.tasks = [task]
    solver.op_data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert solver.tasks == [task]
    assert task.plan == {"meeting": ["Current", "虎狼丸"]}
    assert task.time == when


def test_current_and_non_return_tasks_are_not_changed_mid_execution(solver):
    active = shift_on({"meeting": ["埃癸斯", "虎狼丸"]})
    special = [
        SchedulerTask(task_type=kind, task_plan={"meeting": ["埃癸斯", "Current"]})
        for kind in (TaskTypes.FIAMMETTA, TaskTypes.SHIFT_OFF, TaskTypes.RE_ORDER)
    ]
    stale = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.task = active
    solver.tasks = [active, *special, stale]
    solver.op_data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert solver.tasks == [active, *special]
    assert active.plan == {"meeting": ["埃癸斯", "虎狼丸"]}
    assert all(task.plan == {"meeting": ["埃癸斯", "Current"]} for task in special)


@pytest.mark.parametrize("next_room", ["", "dormitory_1", "dormitory_2"])
def test_rest_and_idle_changes_keep_the_return(solver, next_room):
    solver.op_data.operators["埃癸斯"]._current_room = "meeting"
    task = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.tasks = [task]
    solver.op_data.operators["埃癸斯"].current_room = next_room
    assert solver.tasks == [task]


def test_legacy_mode_keeps_its_original_return_behavior(solver):
    solver.op_data.config.experimental_dorm_logic = False
    task = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.tasks = [task]
    solver.op_data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert solver.tasks == [task]


def test_projection_and_plan_reconstruction_do_not_cancel_real_returns(solver):
    task = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.tasks = [task]
    projected = solver.op_data.project_arrangements([{"room_3_3": ["埃癸斯"]}])
    assert projected.operators["埃癸斯"].is_working()
    # 新建或恢复影子对象并不代表游戏已安排成功。
    Operator("埃癸斯", "meeting", current_room="room_3_3")
    assert solver.tasks == [task]


def test_replacement_identity_after_backup_switch_still_cancels_old_return(solver):
    data = solver.op_data
    task = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.tasks = [task]
    # 会客室副表退出后，他恢复为发电站替班；旧任务仍记录会客室工位。
    plan = data.global_plan["default_plan"].plan
    plan["meeting"] = [
        Room("信仰搅拌机", "", ["陈"]),
        Room("跃跃", "", ["见行者"]),
    ]
    plan["room_3_3"] = [Room("Lancet-2", "自动化", ["埃癸斯"])]
    assert data.swap_plan([], refresh=True) is None
    assert not data.operators["埃癸斯"].is_high()
    assert solver.tasks == [task]
    data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert solver.tasks == []


def test_reading_an_already_working_operator_does_not_cancel_future_cycle(solver):
    data = solver.op_data
    data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    task = shift_on({"meeting": ["埃癸斯", "Current"]})
    solver.tasks = [task]
    data.update_detail("埃癸斯", 17, "room_3_3", 0, True)
    assert solver.tasks == [task]


def test_return_is_recreated_only_after_a_new_rest_cycle(solver):
    data = solver.op_data
    data.update_detail("埃癸斯", 10, "dormitory_1", 2, True)
    data.dorm[0].time = datetime.now() + timedelta(hours=1)
    solver.plan_metadata()
    assert any(task.plan.get("meeting", [""])[0] == "埃癸斯" for task in solver.tasks)
    data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    assert not any(task.type == TaskTypes.SHIFT_ON for task in solver.tasks)
    solver.plan_metadata()
    assert not any(task.type == TaskTypes.SHIFT_ON for task in solver.tasks)
    data.update_detail("埃癸斯", 8, "dormitory_1", 2, True)
    data.dorm[0].time = datetime.now() + timedelta(hours=2)
    solver.plan_metadata()
    assert any(task.plan.get("meeting", [""])[0] == "埃癸斯" for task in solver.tasks)


@pytest.mark.parametrize("merged", [False, True])
def test_product_deferred_return_releases_only_obsolete_locks(solver, merged):
    task = shift_on({"meeting": ["埃癸斯", "虎狼丸" if merged else "Current"]})
    solver.tasks = [task]
    slots = {("meeting", 0), ("meeting", 1)} if merged else {("meeting", 0)}
    solver._reserve_deferred_product_shift(task, slots)
    solver._refresh_deferred_product_reservations()
    assert "埃癸斯" in solver.op_data.reserved_product_replacements
    solver.op_data.update_detail("埃癸斯", 18, "room_3_3", 0, True)
    if merged:
        assert solver.tasks == [task]
        assert task.product_lock_slots == {("meeting", 1)}
        assert task.product_lock_names == {"虎狼丸"}
    else:
        assert solver.tasks == []
    assert "埃癸斯" not in solver.op_data.reserved_product_replacements
