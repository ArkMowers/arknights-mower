"""普通跑单仅使用完整实测原班，失败后的重试仅恢复原班。"""

import copy
import pickle
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.automatic_rescue_tests import offline as offline
from arknights_mower.tests.emergency_compensation_tests import selection_harness
from arknights_mower.tests.mass_mood_recovery_tests import COVERS, NOW, PRIMARY
from arknights_mower.tests.mass_mood_recovery_tests import solver as solver
from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Room
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "room_1_1"
ORIGINAL = [COVERS[0], COVERS[1]]


def prepare_order(solver, monkeypatch, original=ORIGINAL, buffer=1, adjusted=True):
    place = selection_harness(solver, monkeypatch)
    place(original)
    config.conf.run_order_grandet_mode.enable = bool(buffer)
    config.conf.run_order_grandet_mode.buffer_time = buffer
    task = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.RUN_ORDER,
        task_plan={ROOM: ["但书", COVERS[1]]},
        meta_data=ROOM,
    )
    task.adjusted = adjusted
    solver.task = task
    solver.tasks = [task]
    solver.accept_order = MagicMock()
    solver.sleep = MagicMock()
    solver.record_selection_failure = MagicMock()
    solver.swipe_left.side_effect = lambda *a, **k: (
        (0, None) if k.get("return_page") else 0
    )
    solver.drone_room = "room_9_9"
    solver.find = MagicMock(
        side_effect=lambda name, *a, **k: None if name == "bill_accelerate" else True
    )
    return task, place


def assert_pending_restoration(task):
    assert task.type == TaskTypes.RUN_ORDER
    assert task.meta_data == ""
    assert task.plan == {ROOM: ORIGINAL}
    assert task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.run_order_restore_pending


@pytest.mark.parametrize("original", [["", ""], [COVERS[0], ""]])
def test_incomplete_observed_roster_prevents_temporary_selection(
    solver, monkeypatch, original
):
    task, _ = prepare_order(solver, monkeypatch, original)

    assert solver.agent_arrange(task.plan) is False

    assert solver.op_data.get_current_room(ROOM, True) == original
    solver.choose_agent.assert_not_called()
    solver.get_free_list.assert_not_called()
    solver.drone.assert_not_called()
    assert not getattr(task, "run_order_restore_pending", False)
    assert any(t.type == TaskTypes.NOT_SPECIFIC for t in solver.tasks)


def test_drone_failure_retries_only_original_roster(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch)
    solver.drone.side_effect = RuntimeError("无人机加速失败")

    with pytest.raises(RuntimeError, match="无人机加速失败"):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    assert task in solver.tasks
    solver.drone.reset_mock(side_effect=True)
    solver.choose_agent.reset_mock()
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.drone.assert_not_called()
    solver.get_free_list.assert_not_called()


def test_complete_observed_replacement_is_restored_while_primary_keeps_resting(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch)
    primary = solver.op_data.operators[PRIMARY[0]]
    primary._current_room, primary.current_index = "dormitory_1", 2

    solver.agent_arrange(task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert (primary.current_room, primary.current_index) == ("dormitory_1", 2)
    assert task.plan == {}
    assert not getattr(task, "run_order_restore_pending", False)
    assert not hasattr(task, "run_order_original_roster")
    solver.get_free_list.assert_not_called()


@pytest.mark.parametrize("failure", ["countdown", "wait", "collect", "restore"])
def test_post_insertion_failure_keeps_compensation_and_retries_only_restore(
    solver, monkeypatch, failure
):
    task, place = prepare_order(solver, monkeypatch, adjusted=False)
    error = RuntimeError("跑单后续操作失败")
    solver.get_order_remaining_time.side_effect = (
        [60, error] if failure == "countdown" else None
    )
    if failure == "wait":
        solver.sleep.side_effect = error
    elif failure == "collect":
        solver.accept_order.side_effect = error
    elif failure == "restore":
        confirm = solver.tap_confirm.side_effect

        def fail_restore(room, new_plan):
            if solver.choose_agent.call_args.args[0] == ORIGINAL:
                raise error
            return confirm(room, new_plan)

        solver.tap_confirm.side_effect = fail_restore

    with pytest.raises(RuntimeError, match="跑单后续操作失败"):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    assert solver.op_data.get_current_room(ROOM, True) == ["但书", COVERS[1]]
    solver.get_order_remaining_time.reset_mock(side_effect=True)
    solver.sleep.reset_mock(side_effect=True)
    solver.accept_order.reset_mock(side_effect=True)
    solver.tap_confirm.side_effect = lambda room, new_plan: place(
        solver.choose_agent.call_args.args[0]
    )
    solver.choose_agent.reset_mock()
    solver.agent_arrange(task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.get_order_remaining_time.assert_not_called()
    solver.drone.assert_not_called()
    solver.sleep.assert_not_called()
    solver.accept_order.assert_not_called()
    solver.get_free_list.assert_not_called()


def test_incomplete_server_wait_keeps_compensation_for_next_dispatch(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch, adjusted=False)
    solver.waiting_scene = [Scene.INFRA_MAIN]
    solver.waiting_solver = MagicMock(return_value=False)

    assert solver.agent_arrange(task.plan) is False

    assert_pending_restoration(task)
    assert solver.op_data.get_current_room(ROOM, True) == ["但书", COVERS[1]]
    solver.accept_order.assert_not_called()


def test_selection_uncertainty_cannot_erase_original_roster(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch)
    solver.wait_for_arranged_agents.side_effect = base_schedule.AgentSelectionNotReady(
        "干员名单仍在变化"
    )

    with pytest.raises(base_schedule.AgentSelectionNotReady):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    assert solver.choose_agent.call_count == 1
    solver.wait_for_arranged_agents.side_effect = lambda names, **kwargs: names
    solver.choose_agent.reset_mock()
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.drone.assert_not_called()


def test_nonbuffer_restore_reuses_task_without_order_room_metadata(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)

    assert solver.agent_arrange(task.plan) is False

    assert_pending_restoration(task)
    assert [t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER] == [task]
    solver.drone.assert_called_once()
    solver.drone.reset_mock()
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert task.plan == {}
    solver.drone.assert_not_called()


@pytest.mark.parametrize("stage", ["selection", "confirmation"])
def test_first_insertion_failure_never_repeats_trade_operator_selection(
    solver, monkeypatch, stage
):
    task, place = prepare_order(solver, monkeypatch)
    failure = RuntimeError("首次换入失败")
    if stage == "selection":
        solver.choose_agent.side_effect = failure
    else:
        solver.tap_confirm.side_effect = failure

    with pytest.raises(RuntimeError, match="首次换入失败"):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    solver.choose_agent.assert_called_once()
    solver.drone.assert_not_called()
    solver.choose_agent.reset_mock(side_effect=True)
    solver.tap_confirm.side_effect = lambda room, new_plan: place(
        solver.choose_agent.call_args.args[0]
    )
    solver.agent_arrange(task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    assert not getattr(task, "run_order_restore_pending", False)
    solver.drone.assert_not_called()


@pytest.mark.parametrize(
    "cleanup", ["overdue", "unrelated_overdue", "disabled_room", "product_switch"]
)
def test_pending_restoration_survives_queue_reconciliation(
    solver, monkeypatch, cleanup
):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    assert_pending_restoration(task)
    if cleanup == "overdue":
        task.time = NOW - timedelta(days=2)
    elif cleanup == "unrelated_overdue":
        task.time = NOW - timedelta(minutes=1)
        solver.tasks.append(
            SchedulerTask(
                time=NOW - timedelta(minutes=30), task_type=TaskTypes.SHIFT_OFF
            )
        )
    if cleanup in ("overdue", "unrelated_overdue"):
        solver.error = False
        solver.handle_error(force=True)
    elif cleanup == "disabled_room":
        solver.tasks.append(
            SchedulerTask(task_type=TaskTypes.REFRESH_TIME, meta_data=ROOM)
        )
        solver._sync_run_order_tasks()
    else:
        solver.op_data.run_order_rooms[ROOM] = []
        solver._refresh_orders_after_product_switch()

    assert task in solver.tasks
    assert_pending_restoration(task)
    solver.task = task
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL


def test_repeated_restore_verification_failure_is_bounded_and_retryable(
    solver, monkeypatch
):
    task, place = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    solver.choose_agent.reset_mock()
    solver.tap_confirm.side_effect = lambda *args: None

    with pytest.raises(Exception, match="检测到安排干员未成功"):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    assert 1 <= solver.choose_agent.call_count <= 4
    solver.choose_agent.reset_mock()
    solver.tap_confirm.side_effect = lambda room, new_plan: place(
        solver.choose_agent.call_args.args[0]
    )
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert not getattr(task, "run_order_restore_pending", False)
    solver.get_free_list.assert_not_called()


def test_shared_proviso_cannot_start_another_room_during_pending_restore(
    solver, monkeypatch
):
    original, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(original.plan)
    assert_pending_restoration(original)
    second = SchedulerTask(
        time=NOW,
        task_type=TaskTypes.RUN_ORDER,
        task_plan={"room_1_2": ["但书"]},
        meta_data="room_1_2",
    )
    solver.tasks.append(second)
    solver.task = second
    solver.choose_agent.reset_mock()
    solver.drone.reset_mock()

    assert solver.agent_arrange(second.plan) is False

    assert second.time == NOW + timedelta(minutes=1)
    assert second.plan == {"room_1_2": ["但书"]}
    assert_pending_restoration(original)
    assert solver.op_data.operators["但书"].current_room == ROOM
    solver.choose_agent.assert_not_called()
    solver.drone.assert_not_called()


def test_pending_restore_blocks_new_generation_for_same_room(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    solver.op_data.run_order_rooms[ROOM] = NOW
    solver.op_data.run_order_replacements = MagicMock(return_value=[["但书"], []])

    solver.plan_run_order(ROOM)

    assert [t for t in solver.tasks if t.type == TaskTypes.RUN_ORDER] == [task]
    assert_pending_restoration(task)


def test_restore_waits_for_original_worker_in_foreign_working_facility(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    worker = solver.op_data.operators[ORIGINAL[0]]
    worker._current_room, worker.current_index = "room_1_2", 0
    solver.choose_agent.reset_mock()

    assert solver.agent_arrange(task.plan) is False

    assert_pending_restoration(task)
    assert worker.current_room == "room_1_2"
    assert task.time == NOW + timedelta(minutes=1)
    solver.choose_agent.assert_not_called()
    worker._current_room, worker.current_index = "", -1
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL


@pytest.mark.parametrize("queued_order", [False, True])
@pytest.mark.parametrize("saved_plan", ["restoration", "insertion", "empty"])
@pytest.mark.parametrize("release_read_failure", [False, True])
def test_blocked_restoration_dispatches_source_room_release(
    solver, monkeypatch, queued_order, saved_plan, release_read_failure
):
    monkeypatch.setattr(
        scheduler_task.NewsChecker,
        "get_update_time",
        MagicMock(return_value=(None, None)),
    )
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    solver.op_data.plan[ROOM][1] = Room("图耶", "", [COVERS[1]])
    solver.op_data.global_plan["default_plan"].plan[ROOM] = copy.deepcopy(
        solver.op_data.plan[ROOM]
    )
    for bed, name in zip(solver.op_data.dorm, ["芙蓉", "梓兰", "安赛尔"]):
        room, index = bed.position
        solver.op_data.add(
            Operator(
                name,
                "",
                current_room=room,
                current_index=index,
                mood=12,
                time_stamp=NOW,
            )
        )
        bed.name, bed.time = name, NOW + timedelta(hours=1)
    monkeypatch.setattr(
        base_schedule,
        "defer_dorm_before_priority_task",
        scheduler_task.defer_dorm_before_priority_task,
    )
    if saved_plan != "restoration":
        task.meta_data = ROOM
        task.plan = {ROOM: ["但书", COVERS[1]]} if saved_plan == "insertion" else {}
        task = pickle.loads(pickle.dumps(task))
        solver.tasks = [task]
    worker = solver.op_data.operators[ORIGINAL[0]]
    source_room = "room_1_2"
    primary = solver.op_data.operators[PRIMARY[1]]
    primary._current_room, primary.current_index = "", -1
    worker._current_room, worker.current_index = source_room, 0
    release = SchedulerTask(
        time=NOW,
        task_plan={source_room: [primary.name]},
        task_type=TaskTypes.SELF_CORRECTION,
    )
    solver.tasks.append(release)
    if queued_order:
        solver.tasks.append(
            SchedulerTask(
                time=NOW,
                task_plan={"room_1_3": ["但书"]},
                task_type=TaskTypes.RUN_ORDER,
                meta_data="room_1_3",
            )
        )
    current_time = [NOW]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current_time[0]

    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    solver._product_switching_enabled = MagicMock(return_value=True)
    solver.refresh_connecting = True
    solver.choose_agent.reset_mock()
    solver.drone.reset_mock()
    failed_read = False
    read_error = base_schedule.AgentSelectionNotReady("源站选人名单暂未稳定")
    choose = solver.choose_agent.side_effect

    def choose_with_retry(names, room, **kwargs):
        nonlocal failed_read
        if release_read_failure and room == source_room and not failed_read:
            failed_read = True
            raise read_error
        return choose(names, room, **kwargs)

    solver.choose_agent.side_effect = choose_with_retry

    def confirm(room, new_plan):
        row = solver.choose_agent.call_args.args[0]
        for operator in solver.op_data.operators.values():
            if operator.current_room == room:
                operator._current_room, operator.current_index = "", -1
        for index, name in enumerate(row):
            operator = solver.op_data.operators[name]
            operator._current_room, operator.current_index = room, index

    solver.tap_confirm.side_effect = confirm
    trace = []
    for _ in range(6):
        scheduler_task.scheduling(
            solver.tasks, time_now=current_time[0], op_data=solver.op_data
        )
        selected = solver.tasks[0]
        current_time[0] = max(current_time[0], selected.time)
        solver.task = selected
        solver.infra_main()
        assert [
            call.args[0] for call in base_schedule.save_exception.call_args_list
        ] == ([read_error] if failed_read else [])
        trace.append((selected.type, task.time, release.time))
        if release not in solver.tasks and not getattr(
            task, "run_order_restore_pending", False
        ):
            break

    assert release not in solver.tasks, trace
    assert task not in solver.tasks, trace
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert solver.op_data.get_current_room(source_room, True) == [primary.name]
    assert failed_read == release_read_failure
    assert not hasattr(release, "arrangement_retry_count")
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.drone.assert_not_called()


def test_restoration_confirm_does_not_repeat_order_buffer_wait(solver, monkeypatch):
    task, _ = prepare_order(solver, monkeypatch, buffer=0)
    solver.agent_arrange(task.plan)
    assert_pending_restoration(task)
    config.conf.run_order_grandet_mode.enable = True
    config.conf.run_order_grandet_mode.buffer_time = 15
    solver.op_data.run_order_rooms[ROOM] = NOW
    solver.find = MagicMock(return_value=None)
    solver.sleep.reset_mock()

    base_schedule.BaseSchedulerSolver.tap_confirm(solver, ROOM, {ROOM: ORIGINAL})

    solver.sleep.assert_not_called()


def test_unreadable_countdown_before_selection_never_claims_compensation(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch, adjusted=False)
    solver.get_order_remaining_time.return_value = 0
    solver.reset_room_time = MagicMock()

    solver.agent_arrange(task.plan)

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert not getattr(task, "run_order_restore_pending", False)
    solver.choose_agent.assert_not_called()
    solver.drone.assert_not_called()
    solver.get_free_list.assert_not_called()


@pytest.mark.parametrize("observed", [["Free", "Free"], ["Current", COVERS[1]]])
def test_roster_placeholders_never_become_a_temporary_restore_target(
    solver, monkeypatch, observed
):
    task, _ = prepare_order(solver, monkeypatch, original=["", ""])
    solver.get_agent_from_room.return_value = [{"agent": name} for name in observed]
    solver.get_agent_from_room.side_effect = None

    assert solver.agent_arrange(task.plan) is False

    solver.choose_agent.assert_not_called()
    solver.drone.assert_not_called()
    solver.get_free_list.assert_not_called()
    assert not getattr(task, "run_order_restore_pending", False)


def test_actual_roster_verification_failure_keeps_first_original_snapshot(
    solver, monkeypatch
):
    task, _ = prepare_order(solver, monkeypatch)

    def read(room, *args, **kwargs):
        actual = solver.op_data.get_current_room(room, True)
        if "但书" in actual:
            actual = [PRIMARY[0], COVERS[1]]
        return [{"agent": name} for name in actual]

    solver.get_agent_from_room.side_effect = read

    with pytest.raises(Exception, match="检测到安排干员未成功"):
        solver.agent_arrange(task.plan)

    assert_pending_restoration(task)
    assert solver.choose_agent.call_count == 1
    solver.drone.assert_not_called()
    solver.get_agent_from_room.side_effect = lambda room, *a, **k: [
        {"agent": name} for name in solver.op_data.get_current_room(room, True)
    ]
    solver.choose_agent.reset_mock()
    solver.agent_arrange(task.plan)
    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.get_free_list.assert_not_called()


@pytest.mark.parametrize(
    "failure_type", [base_schedule.MowerExit, base_schedule.DeviceRecoveryError]
)
@pytest.mark.parametrize("stage", ["selection", "confirmation", "drone"])
def test_terminal_device_failure_retains_compensation_without_local_retry(
    solver, monkeypatch, failure_type, stage
):
    task, _ = prepare_order(solver, monkeypatch)
    failure = failure_type("设备恢复预算耗尽")
    if stage == "selection":
        solver.choose_agent.side_effect = failure
    elif stage == "confirmation":
        solver.tap_confirm.side_effect = failure
    else:
        solver.drone.side_effect = failure

    with pytest.raises(failure_type) as raised:
        solver.agent_arrange(task.plan)

    assert raised.value is failure
    assert_pending_restoration(task)
    assert task in solver.tasks
    assert solver.choose_agent.call_count == 1
    if stage == "selection":
        solver.tap_confirm.assert_not_called()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("checkpoint", ["before_confirmation", "during_wait"])
def test_saved_pending_task_normalizes_to_restoration_before_reentry(
    solver, monkeypatch, checkpoint
):
    task, place = prepare_order(solver, monkeypatch)
    task.run_order_original_roster = {ROOM: ORIGINAL.copy()}
    task.run_order_restore_pending = True
    if checkpoint == "during_wait":
        place(["但书", COVERS[1]])
        task.plan.clear()
    restored = pickle.loads(pickle.dumps(task))
    solver.task = restored
    solver.tasks = [restored]

    solver.agent_arrange(restored.plan)

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert all(
        "但书" not in call.args[0] for call in solver.choose_agent.call_args_list
    )
    solver.drone.assert_not_called()
    assert not getattr(restored, "run_order_restore_pending", False)


@pytest.mark.parametrize("back_to_index", [False, True])
def test_dispatcher_restores_saved_empty_pending_plan_before_consumption(
    solver, monkeypatch, back_to_index
):
    task, place = prepare_order(solver, monkeypatch)
    place(["但书", COVERS[1]])
    task.plan.clear()
    task.run_order_original_roster = {ROOM: ORIGINAL.copy()}
    task.run_order_restore_pending = True
    task = pickle.loads(pickle.dumps(task))
    solver.task = task
    solver.tasks = [task]
    solver._product_switching_enabled = MagicMock(return_value=True)
    solver.refresh_connecting = False
    config.conf.run_order_grandet_mode.back_to_index = back_to_index
    solver.back_to_index = MagicMock()

    solver.infra_main()

    assert solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert not getattr(task, "run_order_restore_pending", False)
    solver.drone.assert_not_called()
    solver.back_to_index.assert_not_called()
