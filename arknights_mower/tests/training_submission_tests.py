"""进驻信息遮住提交提示时，等待游戏更新驻员后再读取训练室。"""

import pickle
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers import mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.tests import (  # noqa: E402
    scheduler_recovery_preservation_tests as recovery,
)
from arknights_mower.tests import (  # noqa: E402
    training_occupancy_read_tests as occupancy,
)
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.image import loadres  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.recognize import Recognizer  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
    find_next_task,
)

FIXTURES = Path(__file__).parent / "fixtures" / "selection"
solver = occupancy.solver
training_reader = occupancy.training_reader
scheduler = recovery.scheduler


@pytest.fixture
def training_dispatch(scheduler, training_reader, monkeypatch):
    instance = scheduler.solver
    instance.op_data = training_reader.op_data
    now = scheduler.clock.now()
    task = SchedulerTask(now, {"train": ["Current", "余"]}, TaskTypes.SELF_CORRECTION)
    depot = SchedulerTask(now, task_type=TaskTypes.DEPOT)
    instance.task, instance.tasks = task, [task, depot]
    for method in (
        "back_to_infrastructure",
        "enter_room",
        "turn_on_room_detail",
        "refresh_current_room",
        "_prepare_shift_cycle",
        "_prepare_group_shift",
        "_switch_products_before_arrangement",
        "_defer_conflicting_product_shift_slots",
        "_fill_empty_dorms",
        "plan_metadata",
    ):
        setattr(instance, method, MagicMock())
    instance._complete_group_shift = MagicMock(return_value=True)
    instance.仓库扫描 = MagicMock()
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(config.conf, "performance_mode", "high")
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        lambda *a, **kw: mastery_reader.RoomState("empty"),
    )
    monkeypatch.setattr(base, "save_exception", MagicMock())
    return instance, task, depot


@pytest.mark.parametrize("failed_room", ["train", "dormitory_1"])
def test_one_room_failure_releases_independent_rooms_in_either_order(
    training_dispatch, monkeypatch, failed_room
):
    solver, task, depot = training_dispatch
    original_time = task.time
    task.type = TaskTypes.RE_ORDER
    task.meta_data = "副表内存收敛"
    task.plan = {"dormitory_1": ["深巡"], "train": ["Current", "迷迭香"]}
    targets = list(task.plan[failed_room])
    other = next(room for room in task.plan if room != failed_room)
    # 两种既定顺序都让故障房间先执行。
    monkeypatch.setattr(
        base,
        "_arrangement_room_order",
        lambda plan, _, **kwargs: [
            room for room in (failed_room, other) if room in plan
        ],
    )
    visits = []
    failing = True

    def arrange(new_plan, room, plan, **kwargs):
        visits.append(room)
        if room == failed_room and failing:
            raise base.RoomArrangementDeferred(
                room, base.AgentPageNotAdvanced("选人失败")
            )
        del plan[room]
        return new_plan

    solver.agent_arrange_room = arrange
    solver.infra_main()
    assert visits == [failed_room]
    assert find_next_task(solver.tasks) is task
    solver.task = task
    solver.infra_main()
    assert visits == [failed_room, other]
    assert task.plan == {failed_room: targets} and task.time == original_time
    assert task.execution_failure["rooms"] == (failed_room,)
    solver._complete_group_shift.assert_not_called()
    for _ in range(3):
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is depot
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task, depot]
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is depot
    failing = False
    solver.op_data.room_observations[failed_room] += 1
    solver._resume_failed_tasks()
    assert find_next_task([task]) is task
    solver.task = task
    solver.infra_main()
    assert visits == [failed_room, other, failed_room]
    assert task not in solver.tasks and task.plan == {} and task.time == original_time
    solver._complete_group_shift.assert_called_once_with(task)


def test_room_failures_resume_separately_after_reload(training_dispatch):
    solver, task, depot = training_dispatch
    task.plan.update(dormitory_1=["深巡"], dormitory_2=["伺夜"])
    visits = []
    unavailable = {"train", "dormitory_1"}

    def arrange(new_plan, room, plan, **kwargs):
        visits.append(room)
        if room in unavailable:
            raise base.RoomArrangementDeferred(
                room, base.AgentPageNotAdvanced("选人失败")
            )
        del plan[room]
        return new_plan

    solver.agent_arrange_room = arrange
    for _ in range(3):
        solver.task = task
        solver.infra_main()
    assert visits == ["train", "dormitory_1", "dormitory_2"]
    assert set(task.arrangement_failures) == set(task.plan) == unavailable
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task, depot]
    solver.op_data.room_observations["dormitory_2"] = 5
    for _ in range(3):
        solver._resume_failed_tasks()
        assert find_next_task(solver.tasks) is depot
    solver.op_data.room_observations["dormitory_1"] += 1
    unavailable.remove("dormitory_1")
    solver.task = task
    solver.infra_main()
    assert visits == ["train", "dormitory_1", "dormitory_2", "dormitory_1"]
    assert set(task.plan) == set(task.arrangement_failures) == {"train"}
    assert find_next_task(solver.tasks) is depot
    solver._complete_group_shift.assert_not_called()


def test_shared_targets_and_occupants_wait_for_the_failed_room(training_dispatch):
    solver, task, depot = training_dispatch
    solver.op_data.add(Operator("凛冬", "", current_room="meeting", current_index=0))
    task.plan.update(
        meeting=["余"],
        dormitory_1=["克莱门莎"],
        dormitory_2=["凛冬"],
        dormitory_3=["伺夜"],
    )
    visits = []

    def arrange(new_plan, room, plan, **kwargs):
        visits.append(room)
        if room == "train":
            raise base.RoomArrangementDeferred(room, ValueError("选人失败"))
        del plan[room]
        return new_plan

    solver.agent_arrange_room = arrange
    solver.infra_main()
    solver.task = task
    solver.infra_main()
    assert visits == ["train", "dormitory_3"]
    assert set(task.plan) == {"train", "meeting", "dormitory_1", "dormitory_2"}
    assert find_next_task(solver.tasks) is depot
    # 克莱门莎实际离开训练室后，宿舍一自行恢复，无需等其他房间。
    solver.op_data.operators["克莱门莎"].current_room = ""
    solver.op_data.operators["克莱门莎"].current_index = -1
    solver.task = task
    solver.infra_main()
    solver.task = task
    solver.infra_main()
    assert visits == ["train", "dormitory_3", "train", "dormitory_1"]
    assert find_next_task(solver.tasks) is depot


def test_source_bed_release_allows_a_new_training_selection(
    training_dispatch, monkeypatch
):
    solver, task, _ = training_dispatch
    source = "dormitory_2"
    solver.op_data.plan[source] = solver.op_data.plan["dormitory_1"].copy()
    trainee = Operator("迷迭香", "", current_room=source, current_index=2)
    solver.op_data.add(trainee)
    task.plan = {
        "train": ["Current", trainee.name],
        source: ["Current", "Current", "伺夜", "Current", "Current"],
    }
    time = task.time
    occupants = ["望", "冻河"]
    searches = []
    solver.get_agent_from_room = MagicMock(
        side_effect=lambda *a, **kw: [{"agent": name} for name in occupants]
    )
    monkeypatch.setattr(
        "arknights_mower.utils.schedule_roster.cached_training_requirement",
        lambda _: None,
    )

    def search(*args, **kwargs):
        searches.append(trainee.current_room)
        if trainee.current_room == source:
            raise base.TraineeCardUnavailable(
                trainee.name,
                solver.op_data,
                base.AgentPageNotAdvanced("训练干员列表已到末尾"),
            )
        occupants[1] = trainee.name

    solver.choose_train = MagicMock(side_effect=search)
    arrange_room = solver.agent_arrange_room

    def arrange(new_plan, room, plan, **kwargs):
        if room == "train":
            return arrange_room(new_plan, room, plan, **kwargs)
        assert room == source and plan[room][2] == "伺夜"
        trainee.current_room, trainee.current_index = "", -1
        del plan[room]
        return new_plan

    solver.agent_arrange_room = arrange
    solver.infra_main()
    assert searches == [source]
    reason = task.arrangement_failures["train"]["reason"]
    assert "迷迭香" in reason and "宿舍2第3位" in reason and "基础技能" in reason
    solver.task = task
    solver.infra_main()
    assert list(task.plan) == ["train"] and find_next_task([task]) is task
    solver.task = task
    solver.infra_main()
    assert searches == [source, ""]
    assert task not in solver.tasks and task.time == time
    solver._complete_group_shift.assert_called_once_with(task)


@pytest.mark.parametrize(
    "reason",
    [
        "检测到干员选择错误，重新选择",
        "检测到安排干员未成功",
        "训练干员列表已到末尾，返回房间重试",
    ],
)
@pytest.mark.parametrize("changed_room", ["dormitory_1", "train"])
def test_legacy_failure_compares_only_saved_room_evidence(
    training_dispatch, reason, changed_room
):
    solver, task, _ = training_dispatch
    task.plan["dormitory_1"] = ["杜林"]
    op = Operator(
        "杜林", "", current_room="dormitory_1", current_index=0, time_stamp=task.time
    )
    solver.op_data.add(op)
    task.arrangement_retry_room, task.arrangement_retry_count = "train", 1
    solver._retain_failed_task(task, reason, ["train"])
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task]
    if changed_room == "dormitory_1":
        op.time_stamp = None
        solver.op_data.room_observations[changed_room] += 1
    else:
        solver.op_data.room_observations["train"] += 1
    solver._resume_failed_tasks()
    assert find_next_task([task]) is task
    expected = {"train"} if changed_room == "dormitory_1" else set()
    assert solver._blocked_arrangement_rooms(task) == expected
    for _ in range(3):
        solver._resume_failed_tasks()
        assert solver._blocked_arrangement_rooms(task) == expected


def test_other_bed_metadata_does_not_retry_training(training_dispatch):
    solver, task, _ = training_dispatch
    task.type = TaskTypes.SHIFT_ON
    task.plan["dormitory_1"] = ["深巡"]
    task.meta_data = "dorm0,dorm1"
    solver._retain_failed_task(task, "选人失败", ["train"], arrangement_room="train")
    solver._resume_failed_tasks()
    task.meta_data = "dorm1"
    solver._resume_failed_tasks()
    assert solver._blocked_arrangement_rooms(task) == {"train"}


def test_old_room_failure_releases_dorm_but_preserves_product_wait(training_dispatch):
    solver, task, depot = training_dispatch
    task.plan["dormitory_1"] = ["深巡"]
    task.arrangement_retry_room, task.arrangement_retry_count = "train", 1
    solver._retain_failed_task(task, "训练干员列表已到末尾，返回房间重试", ["train"])
    task = pickle.loads(pickle.dumps(task))
    solver.tasks = [task, depot]
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is task
    assert set(task.arrangement_failures) == {"train"}
    solver._retain_failed_task(
        task, "换班等待制造站切换产物", ["dormitory_1"], dependency=True
    )
    product_wait = task.execution_failure
    for _ in range(3):
        solver._resume_failed_tasks()
        assert (
            task.execution_failure is product_wait
            and find_next_task(solver.tasks) is depot
        )
    solver.op_data.room_observations["dormitory_1"] += 1
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is task
    assert solver._blocked_arrangement_rooms(task) == {"train"}


def test_submitted_training_slot_can_be_read_while_a_second_room_is_held(
    training_dispatch, monkeypatch
):
    solver, task, depot = training_dispatch
    task.plan["dormitory_1"] = ["深巡"]
    # 调整测试中的失败次序，使训练室先前的补读记录排在另一间房的失败之后。
    for room in ("dormitory_1", "train"):
        error = (
            base.TrainingSubmissionUnconfirmed(1, "余")
            if room == "train"
            else ValueError("选人失败")
        )
        solver._retain_failed_task(task, str(error), [room], arrangement_room=room)
        if room == "train":
            task.execution_failure["submitted_training_slot"] = error.slot
    solver._resume_failed_tasks()
    assert task.execution_failure["rooms"] == ("dormitory_1",)
    assert find_next_task(solver.tasks) is depot

    def read(room, *, strict_observation):
        assert room == "train" and strict_observation
        solver.op_data.room_observations[room] += 1
        return [{"agent": "望"}, {"agent": "余"}]

    solver.get_agent_from_room = MagicMock(side_effect=read)
    monkeypatch.setattr(base, "save_current_state", lambda: True)
    assert solver._observe_failed_arrangement_confirmation()
    assert solver._observe_failed_arrangement_confirmation() is False
    solver.get_agent_from_room.assert_called_once()
    assert solver._blocked_arrangement_rooms(task) == {"dormitory_1"}
    assert find_next_task(solver.tasks) is task


def test_failure_before_training_submit_yields_to_independent_task(
    scheduler, training_dispatch
):
    instance, task, depot = training_dispatch
    now = task.time
    instance.get_agent_from_room = MagicMock(
        return_value=[{"agent": "望"}, {"agent": ""}]
    )
    instance.choose_train = MagicMock(
        side_effect=base.AgentSelectionNotReady("未能打开训练室选人页，返回房间重试")
    )

    instance.infra_main()

    assert instance.choose_train.call_count == 2
    assert task.execution_failure["rooms"] == ("train",)
    assert task.time == now and task.plan == {"train": ["Current", "余"]}
    for _ in range(3):
        instance._resume_failed_tasks()
        assert find_next_task(instance.tasks) is depot
    instance.run()
    instance.仓库扫描.assert_called_once()
    assert task in instance.tasks and depot not in instance.tasks
    assert find_next_task([task]) is None
    assert instance.choose_train.call_count == 2
    assert not any(
        call.kwargs.get("strict_observation")
        for call in instance.get_agent_from_room.call_args_list
    )
    assert task.time == now and task.plan == {"train": ["Current", "余"]}
    scheduler.io.assert_not_called()


@pytest.mark.parametrize(
    "feedback", ["room_retry", "settled", "old", "unreadable_mood", "legacy_save"]
)
def test_dispatch_reads_late_training_submission_once(
    scheduler, training_dispatch, training_reader, monkeypatch, feedback
):
    instance, task, depot = training_dispatch
    original_time = task.time
    residents = ["望", ""]
    page = Scene.INFRA_MAIN

    def show(scene):
        nonlocal page
        page = scene

    def enter(room):
        assert room == "train"
        if feedback == "room_retry" and instance.tap_confirm.called:
            residents[1] = "余"
        show(Scene.INFRA_DETAILS)

    instance.scene.side_effect = lambda: page
    instance.recog.w, instance.recog.h = 1920, 1080
    instance.enter_room.side_effect = enter
    instance.back_to_infrastructure.side_effect = lambda: show(Scene.INFRA_MAIN)
    instance.back = MagicMock(side_effect=lambda interval=1: show(Scene.INFRA_MAIN))
    instance.tap = MagicMock(side_effect=lambda pos: show(Scene.INFRA_ARRANGE_ORDER))
    instance._require_training_selection = MagicMock()
    instance.choose_train_ope = MagicMock()
    instance.tap_confirm = MagicMock(
        side_effect=lambda *a, **kw: show(Scene.INFRA_DETAILS)
    )
    training_reader.task, training_reader.tasks = task, instance.tasks
    training_reader.find_next_task.return_value = None
    training_reader.recog.gray[344:] = 1
    training_reader.find.side_effect = lambda res, **kw: (
        res == "infra_no_operator" and not residents[int(kw["scope"][0][1] == 344)]
    )
    training_reader.read_screen.side_effect = lambda crop, **kw: residents[crop[0, 0]]
    training_reader.selection_transition_timing = lambda: (0.25, 2)
    instance.get_agent_from_room = MagicMock(wraps=training_reader.get_agent_from_room)
    save = MagicMock(return_value=True)
    monkeypatch.setattr(base, "save_current_state", save)

    instance.infra_main()
    if feedback == "room_retry":
        assert task not in instance.tasks
        assert instance.op_data.get_current_room("train", True) == ["望", "余"]
        instance.tap_confirm.assert_called_once_with("train", training_slot=1)
        save.assert_not_called()
        return
    assert task.execution_failure["rooms"] == ("train",)
    assert "训练位提交后未确认" in task.execution_failure["reason"]
    assert task.time == original_time and task.plan == {"train": ["Current", "余"]}
    assert find_next_task(instance.tasks) is depot
    assert instance.op_data.get_current_room("train", True) == ["望", ""]
    if feedback == "legacy_save":
        task = pickle.loads(pickle.dumps(task))
        task.execution_failure.pop("submitted_training_slot", None)
        task.execution_failure["reason"] = (
            "训练室训练位提交后未确认目标驻员，返回房间重试"
        )
        instance.tasks = training_reader.tasks = [task, depot]
        instance.task = training_reader.task = task
    instance.get_agent_from_room.reset_mock()
    if feedback != "old":
        residents[1] = "余"
    if feedback == "unreadable_mood":
        training_reader.read_accurate_mood.return_value = -1

    instance.infra_main()

    instance.get_agent_from_room.assert_called_once_with(
        "train", strict_observation=True
    )
    instance.tap_confirm.assert_called_once_with("train", training_slot=1)
    instance.choose_train_ope.assert_called_once_with("余")
    save.assert_called_once()
    assert task.plan == {"train": ["Current", "余"]} and task.time == original_time
    if feedback in ("settled", "legacy_save"):
        assert find_next_task([task]) is task
        assert instance.op_data.get_current_room("train", True) == ["望", "余"]
        assert instance.op_data.operators["余"].mood == 18
        instance.task = task
        instance.infra_main()
        assert task not in instance.tasks
        instance.tap_confirm.assert_called_once()
    else:
        assert instance.op_data.get_current_room("train", True) == ["望", ""]
        for _ in range(3):
            instance._resume_failed_tasks()
            assert instance._observe_failed_arrangement_confirmation() is False
            assert find_next_task(instance.tasks) is depot
        assert instance.tasks == [task, depot] and task.time == original_time
        instance.get_agent_from_room.assert_called_once()
        if feedback == "old":
            residents[1] = "余"
            training_reader.get_agent_from_room("train", strict_observation=True)
            instance._resume_failed_tasks()
            assert find_next_task([task]) is task
            instance.tap_confirm.assert_called_once()
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("settles_after", [1, 3, None])
def test_late_training_occupant_after_submission(training_reader, settles_after):
    instance = training_reader
    for method in ("train_scene", "detect_room", "find", "read_screen"):
        delattr(instance, method)
    transition, settled = (
        Recognizer(
            None,
            screencap=(
                FIXTURES / f"training_trainee_{stage}_20261123.jpg"
            ).read_bytes(),
        )
        for stage in ("transition", "settled")
    )
    selection = Recognizer(
        None, screencap=(FIXTURES / "training_selected_yu_20261123.jpg").read_bytes()
    )
    instance.recog = transition
    find = instance.find
    instance.find = lambda resource, *args, **kwargs: (
        instance.recog.get_train_scene() == Scene.INFRA_DETAILS
        if resource == "room_detail"
        else find(resource, *args, **kwargs)
    )
    page = Scene.INFRA_DETAILS
    instance.scene = lambda: page
    selections = []
    waits = []
    submitted_revision = None

    def open_slot(pos, **kwargs):
        nonlocal page
        assert pos == (1920 * 0.82, 1080 * 0.36)
        assert not selections, "训练位提交后再次进入选人页"
        instance.recog = selection
        page = Scene.INFRA_ARRANGE_ORDER

    def submit(room, *, training_slot):
        nonlocal page, submitted_revision
        assert room == "train" and training_slot == 1
        submitted_revision = instance.op_data.room_observations["train"]
        instance.recog = transition
        page = Scene.INFRA_DETAILS

    def next_frame(interval=1):
        assert instance.op_data.room_observations["train"] == submitted_revision
        waits.append(interval)
        if len(waits) == settles_after:
            instance.recog = settled
        assert len(waits) < 12

    instance.tap = instance.ctap = open_slot
    instance.choose_train_ope = selections.append
    instance.tap_confirm = submit
    instance.sleep = next_frame
    instance.selection_transition_timing = lambda: (0.75, 6)
    if settles_after is None:
        with pytest.raises(base.AgentSelectionNotReady, match="训练位.*未确认"):
            instance.choose_train(["望", "余"])
        assert instance.op_data.get_current_room("train", True) == ["望", ""]
    else:
        instance.choose_train(["望", "余"])
        assert len(waits) == settles_after
        assert instance.op_data.get_current_room("train", True) == ["望", "余"]
    assert selections == ["余"]


@pytest.mark.parametrize("input_feedback", ["delayed", "dropped", "absent"])
def test_training_slot_waits_for_its_own_input(monkeypatch, input_feedback):
    page = Scene.INFRA_DETAILS
    elapsed = 0
    taps = []
    occupants = ["望", ""]
    instance = MagicMock()
    instance.recog.w, instance.recog.h = 1920, 1080
    instance.scene.side_effect = lambda: page
    instance.get_agent_from_room.side_effect = lambda *args, **kwargs: [
        {"agent": name} for name in occupants
    ]
    monkeypatch.setattr(base, "monotonic", lambda: elapsed)

    def tap(pos):
        nonlocal page
        assert pos == (1920 * 0.82, 1080 * 0.36)
        taps.append(elapsed)
        if input_feedback == "dropped" and len(taps) == 2:
            page = Scene.INFRA_ARRANGE_ORDER

    def next_frame(interval=1):
        nonlocal elapsed, page
        elapsed += interval
        if input_feedback == "delayed" and elapsed >= 3:
            page = Scene.INFRA_ARRANGE_ORDER

    def confirm(room, *, training_slot):
        nonlocal page
        assert training_slot == 1
        occupants[1] = "余"
        page = Scene.INFRA_DETAILS

    instance.tap.side_effect = tap
    instance.sleep.side_effect = next_frame
    instance.tap_confirm.side_effect = confirm
    if input_feedback == "absent":
        with pytest.raises(base.AgentSelectionNotReady, match="未能打开"):
            BaseSchedulerSolver.choose_train(instance, ["Current", "余"])
        instance.choose_train_ope.assert_not_called()
    else:
        BaseSchedulerSolver.choose_train(instance, ["Current", "余"])
        instance.choose_train_ope.assert_called_once_with("余")
        assert occupants == ["望", "余"]
    assert taps == ([0] if input_feedback == "delayed" else [0, 10])


def captured_recognizer(submitting):
    filename = (
        "training_submission_20261010.jpg"
        if submitting
        else "training_submitted_20261010.jpg"
    )
    device = MagicMock()
    device.screencap.side_effect = AssertionError("离线重放不得请求设备截图")
    return Recognizer(device, screencap=(FIXTURES / filename).read_bytes())


def test_submission_behind_residence_panel_is_connecting():
    recog = captured_recognizer(True)
    assert recog.find("room_detail") is not None
    assert recog.get_scene() == Scene.CONNECTING
    recog.device.screencap.assert_not_called()


def test_submitted_training_room_remains_actionable():
    recog = captured_recognizer(False)
    assert recog.find("connecting") is None
    assert recog.get_scene() == Scene.INFRA_DETAILS


def test_training_readback_waits_for_submission_before_reselecting(monkeypatch):
    solver = object.__new__(BaseSchedulerSolver)
    solver.recog = captured_recognizer(True)
    pending = solver.recog
    pending_bytes = pending.screencap
    completed = captured_recognizer(False)
    pending.device.screencap.side_effect = None
    pending.device.screencap.return_value = (
        completed.screencap,
        completed.img,
        completed.gray,
    )
    waits = []
    monkeypatch.setattr("arknights_mower.utils.solver.csleep", waits.append)
    solver.tap = MagicMock(
        side_effect=AssertionError("提交过渡帧导致再次打开训练位选人")
    )
    reads = []

    def read_occupants(room, **kwargs):
        submitting = solver.recog.find("connecting") is not None
        # 原始提交截图仍显示黍；提交完成截图才显示桃金娘。
        name = "黍" if solver.recog.screencap == pending_bytes else "桃金娘"
        reads.append((submitting, name))
        return [{"agent": "褐果"}, {"agent": name}]

    solver.get_agent_from_room = MagicMock(side_effect=read_occupants)
    solver.choose_train_ope = MagicMock()
    solver.tap_confirm = MagicMock()

    solver.choose_train(["Current", "桃金娘"])

    assert reads == [(False, "桃金娘")]
    assert waits == [1]
    assert solver.recog is pending
    pending.device.screencap.assert_called_once_with()
    solver.tap.assert_not_called()
    solver.choose_train_ope.assert_not_called()
    solver.tap_confirm.assert_not_called()


def test_confirmation_waits_for_occluded_submission_without_reclicking(monkeypatch):
    monkeypatch.setattr(config.conf.waiting_scene, "CONNECTING", (1, 10))
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(run_order_rooms={})
    device = MagicMock()
    device.screencap.side_effect = AssertionError("离线重放不得请求设备截图")
    solver.recog = Recognizer(
        device,
        screencap=(FIXTURES / "training_tail_returned_20261010.jpg").read_bytes(),
    )
    # 重放的初始帧已安装；后续输入和等待分别安装真实提交帧与完成帧。
    solver.recog.update = MagicMock()

    def submit(*args, **kwargs):
        solver.recog = captured_recognizer(True)

    def finish(*args, **kwargs):
        solver.recog = captured_recognizer(False)

    solver.tap = MagicMock(side_effect=submit)
    solver.sleep = MagicMock(side_effect=finish)

    solver.tap_confirm("train")

    assert solver.tap.call_count == 1
    profile = solver.performance_profile
    solver.sleep.assert_called_once_with(
        max(profile.poll_interval, profile.screenshot_interval / 1000)
    )
    assert solver.recog.get_scene() == Scene.INFRA_DETAILS
    device.screencap.assert_not_called()


@pytest.mark.parametrize("with_panel", [False, True])
def test_complete_submission_prompt_preserves_existing_match(with_panel):
    recog = captured_recognizer(False)
    if not with_panel:
        recog._gray[0:110, 1231:1920] = 0
    prompt = loadres("connecting", True)
    h, w = prompt.shape
    recog._gray[978 : 978 + h, 1087 : 1087 + w] = prompt
    assert recog.find("connecting") == ((1087, 978), (1087 + w, 978 + h))


@pytest.mark.parametrize("missing", ["prompt", "panel"])
def test_partial_submission_requires_visible_text_and_residence_panel(missing):
    recog = captured_recognizer(True)
    if missing == "prompt":
        recog._gray[978:1015, 1087:1231] = 0
    else:
        recog._gray[0:110, 1231:1920] = 0
    assert recog.find("connecting") is None


def test_submission_text_outside_fixed_location_is_not_connecting():
    recog = captured_recognizer(False)
    prompt = loadres("connecting", True)
    h, w = prompt.shape
    recog._gray[900 : 900 + h, 1087 : 1087 + w] = prompt
    assert recog.find("connecting") is None


def test_training_room_without_prompt_does_not_use_feature_matcher():
    recog = captured_recognizer(False)
    recog._matcher = MagicMock()
    assert recog.find("connecting") is None
    recog._matcher.match.assert_not_called()


def test_unrelated_bright_footer_is_not_a_submission_prompt():
    recog = captured_recognizer(False)
    recog._gray[970:1020, 1080:1231] = np.full((50, 151), 220, dtype=np.uint8)
    assert recog.find("connecting") is None
