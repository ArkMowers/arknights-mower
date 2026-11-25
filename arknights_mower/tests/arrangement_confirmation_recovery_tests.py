"""确认结果未知时只补一次完整实读，不重新选人或跳过原任务阶段。"""

import copy
import pickle
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.tests import dorm_recovery_tests, training_submission_tests
from arknights_mower.utils import config, mastery_db
from arknights_mower.utils.scheduler_task import (
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

base = dorm_recovery_tests.base_schedule
dorm_solver = dorm_recovery_tests.solver
solver = training_submission_tests.solver
scheduler = training_submission_tests.scheduler
training_reader = training_submission_tests.training_reader
training_dispatch = training_submission_tests.training_dispatch
mastery_reader = training_submission_tests.mastery_reader
real_read_room_state = mastery_reader.read_room_state
ROOM = dorm_recovery_tests.ROOM
REASON = "干员确认联网等待超时，返回房间重试"


@pytest.fixture
def recovery(dorm_solver, monkeypatch):
    solver = dorm_solver
    task = solver.task
    task.arrangement_retry_room = ROOM
    task.arrangement_retry_count = 1
    solver._retain_failed_task(task, REASON, [ROOM])
    solver.physical = dorm_recovery_tests.FINAL.copy()
    observe = solver.get_agent_from_room.side_effect

    def read(room, *args, **kwargs):
        if kwargs.pop("strict_observation", False):
            assert persisted[-1].confirmation_recovery_rooms[room] == "consumed"
        rows = observe(room, *args, **kwargs)
        solver._reconcile_room_observation(room, rows)
        return rows

    solver.get_agent_from_room.side_effect = read
    solver.get_agent_from_room.reset_mock()
    solver.back_to_infrastructure = Mock()
    solver._refresh_observed_recovery_tasks = Mock()
    solver._sync_run_order_tasks = Mock()
    solver.planned = solver.todo_task = solver.collect_notification = True
    solver.handle_error = Mock(return_value=True)
    monkeypatch.setattr(base, "sync_replacement_checks", Mock())
    persisted = []

    def save():
        persisted.append(pickle.loads(pickle.dumps(solver.tasks[0])))
        return True

    save_state = Mock(side_effect=save)
    monkeypatch.setattr(base, "save_current_state", save_state)
    return solver, task, save_state, persisted


@pytest.mark.parametrize(
    "kind, scheduled_at, reason",
    [
        (
            TaskTypes.RE_ORDER,
            "2026-10-27T00:05:04.085196",
            "干员确认画面仍未稳定，返回房间重试",
        ),
        (TaskTypes.SHIFT_OFF, "2026-10-27T13:43:30.264445", REASON),
    ],
)
def test_infra_main_observes_retained_confirmation_without_staffing(
    recovery, kind, scheduled_at, reason
):
    solver, task, save, persisted = recovery
    task.type, task.time = kind, datetime.fromisoformat(scheduled_at)
    task.execution_failure["reason"] = reason
    original_plan, original_time = copy.deepcopy(task.plan), task.time
    task.backup_shift_active = True
    task.dorm_recovery_restore = [ROOM]
    task.group_shift_expected = {(ROOM, 3): "银灰"}

    assert solver.infra_main() is True

    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert not getattr(task, "execution_failure", None)
    assert task.plan == original_plan and task.time == original_time
    assert task.backup_shift_active and task.dorm_recovery_restore == [ROOM]
    assert task.group_shift_expected == {(ROOM, 3): "银灰"}
    assert any(pending is task for pending in solver.tasks)
    assert persisted[0].confirmation_recovery_rooms[ROOM] == "consumed"
    assert persisted[0].execution_failure
    assert save.call_count == 1


@pytest.mark.parametrize(
    "mode", ["unknown", "short", "exception", "no_revision", "duplicate"]
)
def test_failed_or_partial_read_never_reopens_or_repeats(recovery, mode):
    solver, task, save, _ = recovery
    original_plan, original_time = copy.deepcopy(task.plan), task.time
    failure = task.execution_failure
    task.plan[ROOM][2], task.plan[ROOM][4] = "Free", "Current"
    original_plan = copy.deepcopy(task.plan)

    def read(*args, **kwargs):
        solver.op_data.operators["银灰"].time_stamp = datetime.now() + timedelta(
            seconds=1
        )
        if mode == "exception":
            raise base.RecognizeError("房间名单未核实")
        rows = [{"agent": name} for name in solver.physical]
        if mode == "unknown":
            rows[2] = {"agent": "", "observed": False}
        if mode == "short":
            rows.pop()
        if mode == "duplicate":
            rows[2] = rows[3].copy()
            solver.op_data.room_observations[ROOM] = 1
        return rows

    solver.get_agent_from_room.side_effect = read
    assert solver._observe_failed_arrangement_confirmation() is True
    for _ in range(4):
        solver._resume_failed_tasks()
        assert solver._observe_failed_arrangement_confirmation() is False
        assert task.execution_failure is failure
    solver.get_agent_from_room.assert_called_once()
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert task.plan == original_plan and task.time == original_time
    assert save.call_count == 1


@pytest.mark.parametrize("outcome", [False, "exception"])
def test_permission_is_not_used_without_a_successful_save(recovery, outcome):
    solver, task, save, _ = recovery
    if outcome == "exception":
        save.side_effect = RuntimeError("保存失败")
    else:
        save.side_effect = None
        save.return_value = False
    solver._observe_failed_arrangement_confirmation()
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.enter_room.assert_not_called()
    solver.get_agent_from_room.assert_not_called()
    assert save.call_count == 1
    assert task.execution_failure


def test_consumed_permission_survives_restart_and_repeated_failure(recovery):
    solver, task, save, persisted = recovery
    solver._observe_failed_arrangement_confirmation()
    restored = persisted[0]
    solver.tasks, solver.task = [restored], restored
    solver._retain_failed_task(restored, REASON, [ROOM])
    for _ in range(4):
        assert solver._observe_failed_arrangement_confirmation() is False
        solver.scene.return_value = base.Scene.LOGIN_START
        assert solver._observe_failed_arrangement_confirmation() is False
        solver.scene.return_value = base.Scene.INFRA_MAIN
    assert restored.execution_failure
    solver.get_agent_from_room.assert_called_once()
    assert save.call_count == 1


def test_saved_failure_without_permission_field_gets_one_read(recovery):
    solver, task, _, _ = recovery
    task.__dict__.pop("confirmation_recovery_rooms", None)
    solver.tasks = [pickle.loads(pickle.dumps(task))]
    solver.task = solver.tasks[0]
    assert solver._observe_failed_arrangement_confirmation() is True
    assert solver.tasks[0].confirmation_recovery_rooms[ROOM] == "consumed"
    assert not getattr(solver.tasks[0], "execution_failure", None)


@pytest.mark.parametrize(
    "kind",
    [
        TaskTypes.RUN_ORDER,
        TaskTypes.FIAMMETTA,
        TaskTypes.SWAP_SUPPORT,
        TaskTypes.SKILL_UPGRADE,
    ],
)
def test_specialized_compensation_keeps_its_existing_recovery(recovery, kind):
    solver, task, save, _ = recovery
    task.type = kind
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()
    assert task.execution_failure


@pytest.mark.parametrize("kind", [TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA])
def test_due_priority_work_precedes_the_observation(recovery, kind):
    solver, task, save, _ = recovery
    priority = SchedulerTask(time=datetime.now(), task_type=kind)
    solver.tasks.append(priority)
    solver.task = priority
    assert solver._observe_failed_arrangement_confirmation() is False
    assert task.execution_failure
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()
    solver.tasks.remove(priority)
    solver.task = task
    assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once()


def test_waiting_for_login_does_not_consume_the_observation(recovery):
    solver, task, save, _ = recovery
    solver.scene.return_value = base.Scene.LOGIN_START
    assert solver._observe_failed_arrangement_confirmation() is False
    save.assert_not_called()
    solver.scene.return_value = base.Scene.INFRA_MAIN
    assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once()


def test_existing_related_observation_is_not_swallowed_by_recovery(recovery):
    solver, task, save, _ = recovery
    solver.op_data.room_observations[ROOM] = 1
    solver._resume_failed_tasks()
    assert not getattr(task, "execution_failure", None)
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_not_called()
    save.assert_not_called()


@pytest.mark.parametrize("near_order_window", [False, True])
def test_two_close_orders_only_delay_observation_inside_their_window(
    recovery, monkeypatch, near_order_window
):
    solver, task, save, _ = recovery

    class Clock(datetime):
        @classmethod
        def now(cls):
            return (
                datetime(2026, 10, 27, 14, 49)
                if near_order_window
                else datetime(2026, 10, 27, 13, 51, 37)
            )

    monkeypatch.setattr(base, "datetime", Clock)
    orders = [
        SchedulerTask(
            time=datetime(2026, 10, 27, 14, 50, 6),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_2_1",
        ),
        SchedulerTask(
            time=datetime(2026, 10, 27, 14, 54, 10),
            task_type=TaskTypes.RUN_ORDER,
            meta_data="room_1_1",
        ),
    ]
    solver.tasks.extend(orders)
    original_time, original_plan = task.time, copy.deepcopy(task.plan)
    assert solver._observe_failed_arrangement_confirmation() is not near_order_window
    if near_order_window:
        for _ in range(3):
            assert solver._observe_failed_arrangement_confirmation() is False
        solver.get_agent_from_room.assert_not_called()
        save.assert_not_called()
        assert task.execution_failure
        # 已完成的跑单退出队列后，同一原任务取得尚未消费的实读机会。
        solver.tasks[:] = [pending for pending in solver.tasks if pending not in orders]
        assert solver._observe_failed_arrangement_confirmation() is True
    solver.get_agent_from_room.assert_called_once_with(ROOM, strict_observation=True)
    assert save.call_count == 1
    assert task.time == original_time and task.plan == original_plan


def test_complete_observation_preserves_and_then_executes_single_recovery(recovery):
    solver, task, _, _ = recovery
    task.dorm_recovery_restore = [ROOM]
    original_plan = copy.deepcopy(task.plan)
    assert solver._observe_failed_arrangement_confirmation() is True
    assert task.plan == original_plan and task.dorm_recovery_restore == [ROOM]
    solver.choose_agent.assert_not_called()
    solver.tap_confirm.assert_not_called()

    solver.agent_arrange_room({}, ROOM, task.plan)

    assert solver.confirms == [
        ["杜林", "琴柳", "黑角", "银灰", ""],
        dorm_recovery_tests.FINAL,
    ]
    assert not task.plan and task.dorm_recovery_restore == []
    assert solver.op_data.operators["银灰"].dorm_recovery_room == ROOM


def test_cancelled_observation_stays_consumed_without_more_navigation(recovery):
    solver, task, save, _ = recovery
    solver.get_agent_from_room.side_effect = base.MowerExit
    with pytest.raises(base.MowerExit):
        solver._observe_failed_arrangement_confirmation()
    assert task.execution_failure
    assert task.confirmation_recovery_rooms[ROOM] == "consumed"
    solver.back_to_infrastructure.assert_not_called()
    assert save.call_count == 1
    assert solver._observe_failed_arrangement_confirmation() is False


def test_other_room_failures_use_the_existing_observation_policy(recovery):
    solver, task, save, _ = recovery
    task.execution_failure["reason"] = "房间姓名未识别"
    assert solver._observe_failed_arrangement_confirmation() is False
    save.assert_not_called()
    solver.get_agent_from_room.assert_not_called()


@pytest.fixture
def pending_trainee(training_dispatch, training_reader, monkeypatch):
    instance, task, depot = training_dispatch
    task.type = TaskTypes.RE_ORDER
    task.plan = {
        "train": ["虎狼丸", "迷迭香"],
        ROOM: ["杜林", "桃金娘", "深巡", "酒神", "食铁兽"],
    }
    monkeypatch.setattr(config.conf, "enable_crafting", True)
    monkeypatch.setattr(config.conf, "enable_mastery", True)
    monkeypatch.setattr(mastery_db, "get_reconcile_plans", lambda: [])
    monkeypatch.setattr(mastery_reader, "read_room_state", real_read_room_state)
    panel = Mock(return_value=mastery_reader.RoomPanel(idle_marker=True))
    monkeypatch.setattr(mastery_reader, "read_main_panel", panel)
    monkeypatch.setattr(base, "save_current_state", lambda: True)

    def show(scene):
        instance.scene.return_value = scene

    instance.train_scene = Mock(return_value=base.Scene.TRAIN_MAIN)
    instance.enter_room.side_effect = lambda room: show(base.Scene.INFRA_DETAILS)
    instance.back_to_infrastructure.side_effect = lambda: show(base.Scene.INFRA_MAIN)
    instance.back = Mock(side_effect=lambda interval=1: show(base.Scene.INFRA_MAIN))
    instance.recog.w, instance.recog.h = 1920, 1080
    instance.tap = Mock(side_effect=lambda pos: show(base.Scene.INFRA_ARRANGE_ORDER))
    instance._require_training_selection = Mock()
    instance.choose_train_ope = Mock()
    occupants = {
        "train": ["虎狼丸", "冻河"],
        ROOM: ["杜林", "桃金娘", "流星", "酒神", "食铁兽"],
    }
    instance.choose_agent = Mock()

    def confirm(room, new_plan=None, *, training_slot=None):
        if room == ROOM:
            occupants[ROOM] = instance.choose_agent.call_args.args[0].copy()
        show(base.Scene.INFRA_DETAILS)

    instance.tap_confirm = Mock(side_effect=confirm)
    training_reader.task, training_reader.tasks = task, instance.tasks
    training_reader.find_next_task.return_value = None
    training_reader.recog.gray[344:] = 1
    training_reader.find.side_effect = None
    training_reader.find.return_value = None
    training_reader.read_screen.side_effect = lambda crop, **kw: occupants["train"][
        crop[0, 0]
    ]
    training_reader.selection_transition_timing = lambda: (0.25, 2)
    training_reader.get_agent_from_room("train", strict_observation=True)

    def read(room, *args, **kwargs):
        if room == ROOM:
            return [{"agent": name} for name in occupants[ROOM]]
        return training_reader.get_agent_from_room(room, *args, **kwargs)

    instance.get_agent_from_room = Mock(side_effect=read)
    instance.infra_main()
    instance.tap_confirm.assert_called_once_with("train", training_slot=1)
    assert task.arrangement_failures["train"]["submitted_training_slot"] == (
        1,
        "迷迭香",
    )
    instance.task = task
    instance.infra_main()
    instance.get_agent_from_room.assert_called_with("train", strict_observation=True)
    assert instance.op_data.get_current_room("train", True) == occupants["train"]
    assert occupants[ROOM][2] == "流星"
    return instance, task, depot, occupants


def test_unreadable_training_panel_preserves_submitted_target_during_dorm_shift(
    pending_trainee,
):
    instance, task, _, occupants = pending_trainee
    original_time = task.time
    mastery_reader.read_main_panel.return_value = None
    instance.task = task
    instance.infra_main()

    assert occupants[ROOM][2] == "深巡"
    assert any(queued is task for queued in instance.tasks)
    assert task.plan == {"train": ["虎狼丸", "迷迭香"]} and task.time == original_time
    assert instance.op_data.get_current_room("train", True) == ["虎狼丸", "冻河"]
    instance._resume_failed_tasks()
    assert find_next_task([task]) is None
    assert [entry.args[0] for entry in instance.tap_confirm.call_args_list] == [
        "train",
        ROOM,
    ]


def test_unchanged_training_read_during_dorm_shift_does_not_resubmit(pending_trainee):
    instance, task, depot, occupants = pending_trainee
    original_time = task.time
    instance.task = task
    instance.infra_main()
    assert occupants[ROOM][2] == "深巡"
    submissions = instance.tap_confirm.call_args_list.copy()
    assert [entry.args[0] for entry in submissions] == ["train", ROOM]
    revision = instance.op_data.room_observations["train"]
    instance.get_agent_from_room("train", strict_observation=True)
    assert instance.op_data.room_observations["train"] > revision
    for _ in range(3):
        instance._resume_failed_tasks()
        if find_next_task([task]) is task:
            instance.task = task
            instance.infra_main()
    assert instance.tap_confirm.call_args_list == submissions
    instance.choose_train_ope.assert_called_once_with("迷迭香")
    assert task.plan == {"train": ["虎狼丸", "迷迭香"]} and task.time == original_time
    assert find_next_task(instance.tasks) is depot

    occupants["train"][1] = "迷迭香"
    instance.get_agent_from_room("train", strict_observation=True)
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    instance.task = task
    instance.infra_main()
    assert all(queued is not task for queued in instance.tasks)
    assert instance.tap_confirm.call_args_list == submissions


@pytest.mark.parametrize("during_recovery_read", [False, True])
def test_new_trainee_after_reload_releases_unconfirmed_submission(
    pending_trainee, during_recovery_read
):
    instance, task, depot, occupants = pending_trainee
    instance.task = task
    instance.infra_main()
    assert occupants[ROOM][2] == "深巡"
    task = pickle.loads(pickle.dumps(task))
    instance.task, instance.tasks = task, [task, depot]
    original_time = task.time
    assert task.confirmation_recovery_rooms["train"] == "consumed"
    for _ in range(2):
        instance.get_agent_from_room("train", strict_observation=True)
        instance._resume_failed_tasks()
        assert find_next_task(instance.tasks) is depot
    submissions = instance.tap_confirm.call_args_list.copy()
    occupants["train"][1] = "余"
    if during_recovery_read:
        # 新载入的原任务尚有一次补读机会。
        del task.confirmation_recovery_rooms
        assert instance._observe_failed_arrangement_confirmation()
    else:
        instance.get_agent_from_room("train", strict_observation=True)
        instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    assert instance.tap_confirm.call_args_list == submissions

    def settle(room, *, training_slot):
        assert (room, training_slot) == ("train", 1)
        occupants[room][training_slot] = "迷迭香"
        instance.scene.return_value = base.Scene.INFRA_DETAILS

    instance.tap_confirm.side_effect = settle
    instance.task = task
    instance.infra_main()
    assert (
        all(queued is not task for queued in instance.tasks)
        and task.time == original_time
    )
    assert instance.tap_confirm.call_count == len(submissions) + 1
    assert instance.op_data.get_current_room("train", True) == ["虎狼丸", "迷迭香"]


def test_product_reserved_bed_keeps_exhausted_training_room_held(
    training_dispatch, training_reader, monkeypatch
):
    instance, task, _ = training_dispatch
    monkeypatch.setattr(config.conf.product_switching, "enable", True)
    task.type = TaskTypes.RE_ORDER
    task.plan = {
        "train": ["Current", "迷迭香"],
        ROOM: ["Current", "Current", "深巡", "Current", "Current"],
    }
    original_time = task.time
    original_plan = copy.deepcopy(task.plan)
    training_reader.task, training_reader.tasks = task, instance.tasks
    training_reader.find_next_task.return_value = None
    training_reader.read_screen.side_effect = ["虎狼丸", "冻河"]
    instance.get_agent_from_room = Mock(
        return_value=training_reader.get_agent_from_room(
            "train", strict_observation=True
        )
    )
    instance.choose_train = Mock(
        side_effect=base.AgentPageNotAdvanced("训练干员列表已到末尾")
    )
    instance.infra_main()
    assert task.arrangement_failures["train"] and find_next_task([task]) is task
    attempts = instance.choose_train.call_count
    assert attempts > 0
    revision = instance.op_data.room_observations["train"]

    # 重派经过实际换班准备与床位冲突处理。
    for method in (
        "_prepare_group_shift",
        "_prepare_shift_cycle",
        "_defer_conflicting_product_shift_slots",
    ):
        delattr(instance, method)

    owner = SchedulerTask(
        original_time + timedelta(hours=1),
        {ROOM: ["Current", "Current", "伺夜", "Current", "Current"]},
        TaskTypes.SHIFT_OFF,
    )
    instance.tasks.append(owner)
    instance._reserve_deferred_product_shift(owner, {(ROOM, 2)})
    instance.task = task
    instance.infra_main()

    assert owner.product_lock_slots == {(ROOM, 2)}
    for _ in range(3):
        instance._resume_failed_tasks()
        (training_task,) = (
            queued for queued in instance.tasks if "train" in queued.plan
        )
        (dorm_task,) = (
            queued
            for queued in instance.tasks
            if queued is not owner and ROOM in queued.plan
        )
        assert training_task is task and dorm_task is task
        assert task.plan == original_plan and task.time == original_time
        assert find_next_task([task]) is None
    assert instance.op_data.room_observations["train"] == revision
    assert instance.choose_train.call_count == attempts

    # 宿舍仍被预约时，只有训练室读到了新的实际驻员。
    dorm_revision = instance.op_data.room_observations[ROOM]
    training_reader.read_screen.side_effect = ["虎狼丸", "余"]
    instance.get_agent_from_room.return_value = training_reader.get_agent_from_room(
        "train", strict_observation=True
    )
    assert instance.op_data.get_current_room("train", True) == ["虎狼丸", "余"]
    assert instance.op_data.room_observations["train"] > revision
    assert instance.op_data.room_observations[ROOM] == dorm_revision
    instance._resume_failed_tasks()
    assert find_next_task([task]) is task
    assert instance._blocked_arrangement_rooms(task) == {ROOM}
    instance.agent_arrange_room = Mock(wraps=instance.agent_arrange_room)
    instance.task = task
    instance.infra_main()
    assert [entry.args[1] for entry in instance.agent_arrange_room.call_args_list] == [
        "train"
    ]
    assert instance.choose_train.call_count > attempts
    assert find_next_task([task]) is None

    instance.tasks.remove(owner)
    instance._resume_failed_tasks()
    assert any(queued is task for queued in instance.tasks)
    assert task.plan == original_plan and task.time == original_time
    assert find_next_task([task]) is task
    assert instance._blocked_arrangement_rooms(task) == {"train"}
