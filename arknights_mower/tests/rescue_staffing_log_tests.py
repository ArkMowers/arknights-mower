"""救急换班父摘要绑定真实任务，完成只认原始目标的新实读。"""

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import emergency_group_staffing_tests as existing
from arknights_mower.tests.emergency_staffing_replan_tests import reject_room
from arknights_mower.tests.raw_schedule_log_tests import capture
from arknights_mower.utils import log

staffing = existing.staffing
recovery_fixture = existing.recovery_fixture
legacy_solver = existing.legacy_solver


def parents(caplog):
    return [
        record
        for record in [*caplog.get_records("setup"), *caplog.records]
        if getattr(record, "log_event", {}).get("type") == "rescue-staffing"
    ]


def children(caplog):
    return [
        record
        for record in caplog.records
        if getattr(record, "log_event", {}).get("type") == "facility-arrangement"
    ]


@pytest.fixture(autouse=True)
def capture_before_fixture_setup(caplog, monkeypatch):
    capture(caplog, monkeypatch)


@pytest.fixture
def queued(staffing, caplog, monkeypatch):
    solver = staffing.solver
    capture(caplog, monkeypatch)
    assert solver._emergency_schedule_staffing()
    task = existing.staffing_task(solver)
    return solver, task, staffing


def use_room_pages(solver, task):
    physical = {room: solver.op_data.get_current_room(room, True) for room in task.plan}
    page = SimpleNamespace(room=None)
    solver.task = task
    solver.recog = SimpleNamespace(update=MagicMock(), w=1920, h=1080)
    solver.waiting_scene = []
    solver.enter_room = MagicMock(side_effect=lambda room: setattr(page, "room", room))
    solver.turn_on_room_detail = MagicMock()
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver._can_refresh_idle_dorm_search = MagicMock(return_value=False)
    solver.find = MagicMock(return_value=True)
    solver.scene = MagicMock(return_value=base.Scene.INFRA_DETAILS)
    solver.back = MagicMock()
    solver._wait_for_room_exit = MagicMock()
    solver._wait_for_room_entry_before_exit = MagicMock(return_value=False)
    solver.record_selection_success = MagicMock()
    solver.record_selection_failure = MagicMock()
    solver.last_room = ""
    solver.tap = MagicMock()
    chosen = {}

    class CardPageBoundary(Exception):
        pass

    solver.profession_filter = MagicMock(side_effect=CardPageBoundary)

    def choose(names, room, **kwargs):
        try:
            base.BaseSchedulerSolver.choose_agent(solver, names, room, **kwargs)
        except CardPageBoundary:
            pass
        chosen[room] = list(names)

    def confirm(room, new_plan):
        physical[room] = chosen[room]

    def read(room, *args, **kwargs):
        rows = [{"agent": name, "observed": True} for name in physical[room]]
        for index, name in enumerate(physical[room]):
            if name:
                solver.op_data.operators[name].current_room = room
                solver.op_data.operators[name].current_index = index
        solver._reconcile_room_observation(room, rows)
        return rows

    solver.choose_agent = MagicMock(side_effect=choose)
    solver.tap_confirm = MagicMock(side_effect=confirm)
    solver.get_agent_from_room = MagicMock(side_effect=read)
    return physical


def test_queue_keeps_the_full_snapshot_and_actual_facility_work_updates_one_parent(
    queued, caplog
):
    solver, task, _ = queued
    original = deepcopy(task.plan)
    original_time = task.time
    logs = parents(caplog)
    assert [record.log_event["phase"] for record in logs] == ["queued"]
    queued_event = deepcopy(logs[0].log_event)
    assert logs[0].getMessage().startswith("已生成救急换班任务，等待执行：\n")
    assert [item["agents"] for item in queued_event["rooms"]] == list(original.values())
    assert all(item["status"] == "pending" for item in queued_event["rooms"])
    physical = use_room_pages(solver, task)
    rooms = list(original)

    for index, room in enumerate(rooms):
        solver.agent_arrange_room({}, room, task.plan)
        assert (
            not any(
                record.log_event["phase"] == "completed" for record in parents(caplog)
            )
            or index == len(rooms) - 1
        )

    logs = parents(caplog)
    assert logs[-1].log_event["phase"] == "completed"
    assert {record.log_event["id"] for record in logs} == {queued_event["id"]}
    assert all(item["status"] == "completed" for item in logs[-1].log_event["rooms"])
    assert all(
        [
            (item["room"], item["label"], item["agents"])
            for item in record.log_event["rooms"]
        ]
        == [
            (item["room"], item["label"], item["agents"])
            for item in queued_event["rooms"]
        ]
        for record in logs
    )
    assert all(getattr(record, "log_parent", None) is None for record in logs)
    assert all(
        record.log_parent["id"] == queued_event["id"]
        and record.log_parent["attempt"] == record.log_event["id"]
        for record in children(caplog)
    )
    details = [
        record
        for record in caplog.records
        if record.getMessage().startswith("安排干员：")
    ]
    assert len(details) == len(rooms)
    assert all(
        record.log_parent["room"] in original and record.log_parent["attempt"]
        for record in details
    )
    base.logger.info("设施范围外测试记录")
    assert getattr(caplog.records[-1], "log_parent", None) is None
    assert physical == original and not task.plan and task.time == original_time
    assert logs[0].log_event == queued_event


def test_failed_task_reuses_parent_uuid_while_each_facility_attempt_is_new(
    queued, caplog, monkeypatch
):
    solver, task, _ = queued
    parent_id = parents(caplog)[0].log_event["id"]
    original_time = task.time
    first, room, *_ = task.plan
    use_room_pages(solver, task)
    solver.agent_arrange_room({}, first, task.plan)

    reject_room(solver, task, room, monkeypatch)
    first_attempt = next(
        record.log_event["id"]
        for record in children(caplog)
        if record.log_event["room"] == room
    )
    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert [item["status"] for item in parents(caplog)[-1].log_event["rooms"]] == [
        "completed",
        "unconfirmed",
        "pending",
        "pending",
    ]
    assert (
        next(
            item
            for item in parents(caplog)[-1].log_event["rooms"]
            if item["room"] == first
        )["status"]
        == "completed"
    )
    use_room_pages(solver, task)
    for target_room in list(task.plan):
        solver.agent_arrange_room({}, target_room, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "completed"
    assert {record.log_event["id"] for record in parents(caplog)} == {parent_id}
    attempts = [
        record.log_event["id"]
        for record in children(caplog)
        if record.log_event["phase"] == "started" and record.log_event["room"] == room
    ]
    assert (
        len(attempts) == 2
        and attempts[0] == first_attempt
        and attempts[0] != attempts[1]
    )
    assert task.time == original_time
    errors = [
        record
        for record in caplog.records
        if record.levelname == "ERROR" and getattr(record, "log_parent", None)
    ]
    assert errors and errors[-1].log_parent == {
        "type": "rescue-staffing",
        "id": parent_id,
    }
    if target := os.environ.get("MOWER_RESCUE_LOG_RECORDS"):
        handler = log.LiveQueueHandler(Queue())
        web_handler = log.Handler()
        output = Queue()
        monkeypatch.setattr(log, "frontend_log_queue", output)
        monkeypatch.setattr(log, "should_archive_record", lambda record: False)
        delivered = []
        for record in [*caplog.get_records("setup"), *caplog.records]:
            if record.levelno < 20 or not (
                getattr(record, "log_event", None)
                or getattr(record, "log_parent", None)
            ):
                continue
            prepared = handler.prepare(record)
            prepared.asctime = datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S,%f"
            )[:-3]
            web_handler.emit(prepared)
            delivered.append(output.get_nowait())
        assert any(
            item.get("event", {}).get("phase") == "completed"
            and item["event"]["type"] == "rescue-staffing"
            for item in delivered
        )
        assert any(
            item.get("parent", {}).get("attempt")
            and item["msg"].startswith("安排干员：")
            for item in delivered
        )
        Path(target).write_text(
            json.dumps(
                {
                    "source": "rescue_staffing_log_tests.test_failed_task_reuses_parent_uuid_while_each_facility_attempt_is_new",
                    "boundary": "真实生成、设施执行、选人日志入口、确认与读房核销，经LiveQueueHandler.prepare和Handler.emit；卡片页筛选后的设备操作由夹具替代，仅关闭截图归档以避免截图IO，非实机日志。",
                    "records": delivered,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def test_cached_same_roster_and_plan_removal_are_not_fresh_completion(queued, caplog):
    solver, task, _ = queued
    original = deepcopy(task.plan)
    physical = use_room_pages(solver, task)
    for room, names in original.items():
        physical[room] = names
        for index, name in enumerate(names):
            (
                solver.op_data.operators[name].current_room,
                solver.op_data.operators[name].current_index,
            ) = room, index
    for room in list(task.plan):
        solver.agent_arrange_room({}, room, task.plan)
    assert not task.plan
    assert not any(
        record.log_event["phase"] == "completed" for record in parents(caplog)
    )
    assert parents(caplog)[-1].log_event["phase"] == "failed"


@pytest.mark.parametrize("observed", [[], [{"agent": "", "observed": False}]])
def test_empty_or_partial_observations_cannot_complete_original_targets(
    queued, caplog, observed
):
    solver, task, _ = queued
    solver.task = task
    for room in task.plan:
        solver._reconcile_room_observation(room, observed)
    assert [record.log_event["phase"] for record in parents(caplog)] == ["queued"]


def test_protected_targets_do_not_turn_current_or_removed_goals_into_completion(
    queued, caplog
):
    solver, task, _ = queued
    snapshot = deepcopy(parents(caplog)[0].log_event["rooms"])
    use_room_pages(solver, task)
    room = next(iter(task.plan))
    task.plan[room] = ["Current"] * len(task.plan[room])
    solver.agent_arrange_room({}, room, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert [
        (item["room"], item["agents"])
        for item in parents(caplog)[-1].log_event["rooms"]
    ] == [(item["room"], item["agents"]) for item in snapshot]
    assert not any(
        record.log_event["phase"] == "completed" for record in parents(caplog)
    )


def test_history_without_current_queue_anchor_has_only_independent_facility_logs(
    queued, caplog
):
    solver, task, _ = queued
    solver.__dict__.pop("_rescue_staffing_logs", None)
    caplog.clear()
    caplog.get_records("setup").clear()
    use_room_pages(solver, task)
    room = next(iter(task.plan))
    solver.agent_arrange_room({}, room, task.plan)
    assert not parents(caplog)
    assert children(caplog)
    assert all(
        getattr(record, "log_parent", None) is None for record in children(caplog)
    )


def test_actual_task_removal_closes_an_unfinished_parent_without_changing_time(
    queued, caplog
):
    solver, task, _ = queued
    original = deepcopy(vars(task))
    solver.tasks = [pending for pending in solver.tasks if pending is not task]
    solver._prune_rescue_staffing_logs()
    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert solver._rescue_staffing_logs == {}
    assert vars(task) == original


@pytest.mark.parametrize("before_entry", [False, True])
def test_interruption_keeps_task_and_time_and_restores_parent_scope(
    queued, caplog, before_entry
):
    solver, task, _ = queued
    use_room_pages(solver, task)
    original = deepcopy(vars(task))
    room = next(iter(task.plan))
    if before_entry:
        solver.enter_room = MagicMock(side_effect=base.MowerExit())
    else:
        solver.choose_agent = MagicMock(side_effect=base.MowerExit())
    with pytest.raises(base.MowerExit):
        solver.agent_arrange_room({}, room, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert parents(caplog)[-1].log_event["detail"] == "操作已中断"
    assert vars(task) == original and any(pending is task for pending in solver.tasks)
    assert any(
        record.log_event["phase"] == "started" for record in parents(caplog)
    ) is (not before_entry)
    base.logger.info("中断后的范围外记录")
    assert getattr(caplog.records[-1], "log_parent", None) is None


def test_adjusted_room_keeps_other_actual_room_attempts_on_the_same_parent(
    queued, caplog, monkeypatch
):
    from arknights_mower.solvers import mastery_reader

    solver, task, _ = queued
    parent_id = parents(caplog)[0].log_event["id"]
    use_room_pages(solver, task)
    protected, other, *_ = task.plan
    solver.agent_arrange = base.BaseSchedulerSolver.agent_arrange.__get__(solver)
    solver._track_idle_dorm_shift = MagicMock()
    solver._finish_idle_dorm_shift = MagicMock()
    solver._read_arrangement_order_times = MagicMock(return_value=False)
    solver.back_to_infrastructure = MagicMock()
    worker = solver.op_data.operators[task.plan[protected][0]]
    worker.current_room, worker.current_index = "train", 0
    monkeypatch.setattr(base.config.conf, "enable_mastery", False)
    monkeypatch.setattr(
        mastery_reader,
        "read_room_state",
        MagicMock(side_effect=base.RecognizeError("训练状态不可读")),
    )
    solver._arrange_with_shift_refresh_rules(task, False)

    assert not task.plan
    assert not any(
        record.log_event["phase"] == "completed" for record in parents(caplog)
    )
    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert {record.log_event["id"] for record in parents(caplog)} == {parent_id}
    following = [
        record for record in children(caplog) if record.log_event["room"] == other
    ]
    assert following and all(
        record.log_parent["id"] == parent_id for record in following
    )
    reason = next(
        record
        for record in caplog.records
        if record.getMessage().startswith("换人前训练室状态读取失败")
    )
    assert reason.log_parent == {"type": "rescue-staffing", "id": parent_id}
    assert (
        next(
            item
            for item in parents(caplog)[-1].log_event["rooms"]
            if item["room"] == protected
        )["status"]
        == "unconfirmed"
    )
    assert solver._rescue_staffing_log_entry(task) is not None


def test_registry_capacity_keeps_all_live_owners_and_falls_back_for_new_tasks(
    queued, caplog
):
    solver, first, _ = queued
    original_time = first.time
    for _ in range(31):
        task = base.SchedulerTask(task_plan=deepcopy(first.plan))
        task.emergency_staffing = True
        solver.tasks.append(task)
        assert solver._queue_rescue_staffing_log(task)
    ids = {record.log_event["id"] for record in parents(caplog)}
    assert len(ids) == len(solver._rescue_staffing_logs) == 32
    extra = base.SchedulerTask(task_plan=deepcopy(first.plan))
    solver.tasks.append(extra)
    assert solver._queue_rescue_staffing_log(extra) is False
    assert len(solver._rescue_staffing_logs) == 32
    assert (
        solver._rescue_staffing_log_entry(first) is not None
        and first.time == original_time
    )
    assert solver._rescue_staffing_log_parent(extra) is None


def test_display_failure_does_not_change_real_staffing_generation(
    staffing, caplog, monkeypatch
):
    solver = staffing.solver
    original = deepcopy(staffing.state["rescue_plan"])
    monkeypatch.setattr(
        solver,
        "_emit_rescue_staffing_log",
        MagicMock(side_effect=RuntimeError("display only")),
    )
    assert solver._emergency_schedule_staffing()
    task = existing.staffing_task(solver)
    assert task.plan == original
    assert solver._rescue_staffing_logs == {}
    assert not parents(caplog)


def test_explicit_empty_target_requires_an_actual_empty_read(staffing, caplog):
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.plan import Room

    solver = staffing.solver
    solver.op_data.plan["factory"] = [Room("褐果", "", [])]
    solver.op_data.add(Operator("褐果", "", current_room="factory", current_index=0))
    staffing.state["rescue_plan"]["factory"] = [""]
    assert solver._emergency_schedule_staffing()
    task = existing.staffing_task(solver)
    solver.task = task
    entry = solver._rescue_staffing_log_entry(task)
    solver._reconcile_room_observation("factory", [{"agent": "褐果", "observed": True}])
    assert (
        next(item for item in entry["rooms"] if item["room"] == "factory")["status"]
        != "completed"
    )
    solver._reconcile_room_observation("factory", [{"agent": "", "observed": True}])
    assert (
        next(item for item in entry["rooms"] if item["room"] == "factory")["status"]
        == "completed"
    )
    assert task.plan["factory"] == [""]


def test_failed_room_exit_cannot_be_completed_by_an_unrelated_fresh_read(
    queued, caplog
):
    solver, task, _ = queued
    use_room_pages(solver, task)
    for room in list(task.plan)[:-1]:
        solver.agent_arrange_room({}, room, task.plan)
    room = next(iter(task.plan))
    solver._wait_for_room_exit = MagicMock(
        side_effect=base.RecognizeError("退出校验未完成")
    )
    solver.scene = MagicMock(return_value=base.Scene.INFRA_MAIN)
    with pytest.raises(base.RoomArrangementDeferred):
        solver.agent_arrange_room({}, room, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "failed"

    solver.get_agent_from_room(room)

    assert parents(caplog)[-1].log_event["phase"] == "failed"
    assert any(
        item["status"] == "unconfirmed"
        for item in parents(caplog)[-1].log_event["rooms"]
    )
    solver._wait_for_room_exit.side_effect = None
    solver._wait_for_room_entry_before_exit.return_value = True
    solver.agent_arrange_room({}, room, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "completed"


def test_rescue_only_fixed_rooms_use_the_real_room_capacity(
    staffing, caplog, monkeypatch
):
    from arknights_mower.utils.operators import Operator

    solver = staffing.solver
    monkeypatch.setattr(base.config.conf, "enable_mastery", False)
    for name in ("泡普卡", "安赛尔"):
        solver.op_data.add(Operator(name, ""))
    staffing.state["rescue_plan"].update(
        {"factory": ["泡普卡"], "train": ["安赛尔", ""]}
    )
    assert "factory" not in solver.op_data.plan and "train" not in solver.op_data.plan
    assert solver._emergency_schedule_staffing()
    task = existing.staffing_task(solver)
    solver.task = task
    for room, names in task.plan.items():
        for index, name in enumerate(names):
            if name:
                (
                    solver.op_data.operators[name].current_room,
                    solver.op_data.operators[name].current_index,
                ) = room, index
        solver._reconcile_room_observation(
            room, [{"agent": name, "observed": True} for name in names]
        )
    assert parents(caplog)[-1].log_event["phase"] == "completed"
    fixed = [
        item
        for item in parents(caplog)[-1].log_event["rooms"]
        if item["room"] in ("factory", "train")
    ]
    assert len(fixed) == 2 and all(item["status"] == "completed" for item in fixed)


def test_successfully_settled_room_can_be_confirmed_again_after_a_temporary_move(
    queued, caplog
):
    solver, task, _ = queued
    room = next(iter(task.plan))
    previous = solver.op_data.get_current_room(room, True)
    target = list(task.plan[room])
    physical = use_room_pages(solver, task)
    solver.agent_arrange_room({}, room, task.plan)
    assert room not in task.plan
    physical[room] = previous
    solver.get_agent_from_room(room)
    assert not any(
        record.log_event["phase"] == "completed" for record in parents(caplog)
    )

    physical[room] = target
    solver.get_agent_from_room(room)

    entry = solver._rescue_staffing_log_entry(task)
    assert (
        next(item for item in entry["rooms"] if item["room"] == room)["status"]
        == "completed"
    )
    assert room not in task.plan
    for remaining in list(task.plan):
        solver.agent_arrange_room({}, remaining, task.plan)
    assert parents(caplog)[-1].log_event["phase"] == "completed"
