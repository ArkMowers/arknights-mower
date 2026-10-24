"""换班中途只检查临近跑单，换班完毕后正式读取远期时间。"""

import pickle
from datetime import timedelta

import pytest

from arknights_mower.tests import run_order_staffing_admission_tests as admission

staffed_order = admission.staffed_order


def orders(ui, room):
    return [
        task
        for task in ui.solver.tasks
        if task.type == ui.task_type.RUN_ORDER and task.meta_data == room
    ]


def test_final_read_uses_completed_staffing_and_preserves_existing_order(staffed_order):
    ui = staffed_order
    solver = ui.solver
    ui.occupants["room_2_2"] = ["图耶"]
    solver.get_agent_from_room("room_2_2")
    ui.states["room_2_2"] = "active"
    solver.plan_run_order("room_2_2")
    existing = orders(ui, "room_2_2")[0]
    existing_time = existing.time
    confirm = solver.tap_confirm.side_effect
    probes = []

    def boost(room, new_plan):
        if room == "dormitory_1":
            assert not orders(ui, "room_1_1")
            assert len(admission.reads(ui)) == 1
            probes.extend(
                t for t in solver.tasks if t.type == ui.task_type.REFRESH_TIME
            )
        confirm(room, new_plan)
        if room == "dormitory_1":
            ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=20)

    solver.tap_confirm.side_effect = boost
    task = admission.correction(ui, {"room_1_1", "dormitory_1"})
    original_time = task.time
    solver.agent_arrange(task.plan)

    assert task.plan == {} and task.time == original_time
    assert len(admission.reads(ui)) == 2
    assert orders(ui, "room_1_1")[0].time == ui.deadlines["room_1_1"] - timedelta(
        minutes=3
    )
    assert probes and all(t not in solver.tasks for t in probes)
    assert orders(ui, "room_2_2") == [existing] and existing.time == existing_time
    assert len(admission.reads(ui, "room_2_2")) == 1
    staffed = next(e for e in ui.events if e[:2] == ("staffed", "dormitory_1"))
    assert ui.events.index(admission.reads(ui)[-1]) > ui.events.index(staffed)


def test_intermediate_probe_rechecks_after_later_staffing_and_yields(staffed_order):
    ui = staffed_order
    confirm = ui.solver.tap_confirm.side_effect

    def boost(room, new_plan):
        if room == "room_2_2":
            assert not orders(ui, "room_1_1")
        confirm(room, new_plan)
        if room == "room_2_2":
            ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=4)

    ui.solver.tap_confirm.side_effect = boost
    task = admission.correction(ui)
    original_time = task.time

    assert ui.solver.agent_arrange(task.plan) is False

    assert len(admission.reads(ui)) == 2
    assert orders(ui, "room_1_1")[0].time == ui.deadlines["room_1_1"] - timedelta(
        minutes=3
    )
    assert task.time == original_time and set(task.plan) == {"dormitory_1"}
    assert not any(event[:2] == ("staffed", "dormitory_1") for event in ui.events)


@pytest.mark.parametrize("restart", [False, True])
def test_far_probe_keeps_refresh_responsibility_across_critical_yield(
    staffed_order, restart
):
    ui = staffed_order
    other = ui.task(
        time=ui.clock.now() + timedelta(seconds=100),
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_2_2": ["龙舌兰"]},
        meta_data="room_2_2",
    )
    ui.solver.tasks.append(other)
    task = admission.correction(ui, {"room_1_1", "dormitory_1"})
    original_time = task.time
    assert ui.solver.agent_arrange(task.plan) is False
    assert not orders(ui, "room_1_1")
    refresh = next(t for t in ui.solver.tasks if t.type == ui.task_type.REFRESH_TIME)
    refresh_time = refresh.time
    for _ in range(3):
        assert ui.solver.agent_arrange(task.plan) is False
    assert len(admission.reads(ui)) == 1
    if restart:
        ui.solver.tasks = pickle.loads(pickle.dumps(ui.solver.tasks))
        task = next(
            t for t in ui.solver.tasks if t.type == ui.task_type.SELF_CORRECTION
        )
        refresh = next(
            t for t in ui.solver.tasks if t.type == ui.task_type.REFRESH_TIME
        )
    ui.solver.tasks.remove(orders(ui, "room_2_2")[0])
    ui.solver.task = task
    confirm = ui.solver.tap_confirm.side_effect

    def boost(room, new_plan):
        confirm(room, new_plan)
        ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=20)

    ui.solver.tap_confirm.side_effect = boost
    ui.solver.agent_arrange(task.plan)

    assert task.plan == {} and task.time == original_time
    assert len(admission.reads(ui)) == 2
    assert refresh not in ui.solver.tasks and refresh.time == refresh_time
    assert orders(ui, "room_1_1")[0].time == ui.deadlines["room_1_1"] - timedelta(
        minutes=3
    )


def test_failed_final_read_keeps_one_refresh_and_does_not_repeat_staffing(
    staffed_order,
):
    ui = staffed_order
    read = ui.solver.read_time.side_effect
    attempts = []

    def fail_final_read(*args, **kwargs):
        if ui.solver._page["room"] == "room_1_1":
            attempts.append(ui.clock.now())
            if len(attempts) > 1:
                raise ui.base.RecognizeError("订单数字未确认")
        return read(*args, **kwargs)

    ui.solver.read_time.side_effect = fail_final_read
    task = admission.correction(ui, {"room_1_1", "dormitory_1"})
    original_time = task.time
    ui.solver.agent_arrange(task.plan)

    assert task.plan == {} and task.time == original_time
    assert any(event[:2] == ("staffed", "dormitory_1") for event in ui.events)
    assert not orders(ui, "room_1_1")
    refreshes = [t for t in ui.solver.tasks if t.type == ui.task_type.REFRESH_TIME]
    assert len(refreshes) == 1
    refresh = refreshes[0]
    refresh_time = refresh.time
    for _ in range(3):
        ui.solver._resume_failed_tasks()
        ui.solver.plan_run_order("room_1_1")
    assert len(attempts) == 2
    assert refresh.time == refresh_time and refresh.execution_failure
    assert refresh in ui.solver.tasks


@pytest.mark.parametrize(
    "protection", ["strict_mood_limit", "dorm_recovery_restore", "special"]
)
def test_noninterruptible_arrangement_waits_until_completion_to_read(
    staffed_order, protection
):
    ui = staffed_order
    task = admission.correction(ui, {"room_2_2"})
    if protection == "special":
        task.type = ui.task_type.SWAP_SUPPORT
    else:
        setattr(
            task,
            protection,
            True if protection == "strict_mood_limit" else ["dormitory_1"],
        )
    ui.states["room_1_1"] = "active"
    ui.deadlines["room_1_1"] = ui.clock.now() + timedelta(minutes=3)
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_1_1")
    ui.solver.tasks.append(refresh)

    assert ui.solver._read_arrangement_order_times("room_1_1") is False
    assert not admission.reads(ui) and refresh in ui.solver.tasks

    task.plan.clear()
    ui.solver._read_arrangement_order_times("room_1_1")
    assert len(admission.reads(ui)) == 1
    assert all(t is not refresh for t in ui.solver.tasks)
    assert len(orders(ui, "room_1_1")) == 1
