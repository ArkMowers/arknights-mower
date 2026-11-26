from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import dorm_recovery_evidence_tests
from arknights_mower.tests.dorm_recovery_continuation_tests import (
    NEW,
    OTHER,
    PEER,
    VIP,
    start_after_release,
)
from arknights_mower.tests.dorm_recovery_tests import ROOM
from arknights_mower.utils import crash_recovery, resting_priority
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_recovery import (
    active_recovery_position,
    keep_measured_dorm_swap,
    observed_recovery_recipient,
)
from arknights_mower.utils.scheduler_task import (
    TaskTypes,
    replan_update_tasks,
    try_add_release_dorm,
)

scheduler = dorm_recovery_evidence_tests.scheduler
dorm_dispatch = dorm_recovery_evidence_tests.dorm_dispatch


def restore_for_dispatch(dispatch, scheduler, monkeypatch):
    today = scheduler.clock.now().date()
    dispatch.daily_report = dispatch.daily_skland = today
    dispatch.daily_mail = dispatch.daily_visit_friend = today
    dispatch.task_count = 0
    assert record.save_current_state()
    saved = replan_update_tasks(record.load_state(strict=True))
    dispatch.task, dispatch.tasks, dispatch.op_data = None, [], None

    # 启动时从存档重新绑定干员和任务，到首次派发时交还给用例。
    main = scheduler.main
    with monkeypatch.context() as startup:
        startup.setattr(main, "initialize", Mock(return_value=dispatch))
        startup.setattr(main, "_recover_startup_scene", Mock(return_value=True))
        startup.setattr(main, "datetime", scheduler.clock)
        startup.setattr(main, "refresh_resource_at_boundary", Mock())
        startup.setattr(main.NewsChecker, "get_major_maintenance", lambda: None)
        startup.setattr(main.NewsChecker, "get_effective_maintenance", lambda: None)
        startup.setattr(crash_recovery, "checkpoint_start", Mock())
        startup.setattr(dispatch, "run", Mock(side_effect=MowerExit))
        main.simulate(saved)
        dispatch.run.assert_called_once_with()


@pytest.mark.usefixtures("income_db")
@pytest.mark.parametrize("correct", [True, False], ids=["already-correct", "repair"])
@pytest.mark.parametrize(
    "task_type,full_resident,other_recipient,bed_index",
    [
        (TaskTypes.FILL_DORM, OTHER, PEER, 4),
        (TaskTypes.NOT_SPECIFIC, PEER, OTHER, 2),
    ],
    ids=["vacancy", "takeover"],
)
def test_update_reads_committed_dorm_fill_before_replanning(
    scheduler,
    dorm_dispatch,
    monkeypatch,
    task_type,
    full_resident,
    other_recipient,
    bed_index,
    correct,
):
    dispatch, _, _ = dorm_dispatch
    start_after_release(dispatch, monkeypatch, bed=4)
    monkeypatch.setattr(scheduler.module, "try_add_release_dorm", try_add_release_dorm)
    monkeypatch.setattr(resting_priority, "agent_list", [])
    del dispatch._fill_empty_dorms, dispatch.plan_metadata, dispatch.backup_plan_solver
    dispatch._scan_card_moods = Mock(return_value=None)
    dispatch.task, dispatch.tasks = None, []
    scheduler.clock.current = datetime.now()

    if task_type == TaskTypes.FILL_DORM:
        dispatch.physical[bed_index] = ""
    dispatch.op_data.operators[full_resident].mood = 24
    rows = dispatch.get_agent_from_room(ROOM, read_dorm_evidence=True)
    swap = ["Current", "Current", VIP, PEER, "Current"]
    assert keep_measured_dorm_swap(dispatch.op_data, ROOM, swap, rows)
    try_add_release_dorm({}, None, dispatch.op_data, dispatch.tasks)
    (original,) = dispatch.tasks
    scheduled = original.time
    assert original.type == task_type
    assert original.dorm_fill_plan[ROOM][bed_index] == NEW
    final = dispatch.physical.copy()
    final[bed_index] = NEW
    recipient = VIP if correct else other_recipient
    submit = dispatch.tap_confirm.side_effect
    read_room = dispatch.get_agent_from_room.side_effect

    def deliver(room, plan):
        submit(room, plan)
        if dispatch.physical == final:
            dispatch.game_recipient = recipient if len(dispatch.confirms) == 1 else VIP

    def interrupt_after_room_cache(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        if dispatch.confirms:
            raise MowerExit
        return rows

    dispatch.tap_confirm.side_effect = deliver
    dispatch.get_agent_from_room.side_effect = interrupt_after_room_cache
    scheduler.clock.current += timedelta(seconds=2)
    with pytest.raises(MowerExit):
        dispatch.run()
    assert dispatch.confirms == [final]
    assert original.dorm_roommate_targets == {ROOM: (tuple(final), VIP)}
    assert not original.retains_execution and not getattr(
        original, "dorm_recovery_restore", ()
    )
    assert dispatch.op_data.get_current_room(ROOM, True) == final

    restore_for_dispatch(dispatch, scheduler, monkeypatch)
    restored = next(t for t in dispatch.tasks if t.type == task_type and ROOM in t.plan)
    assert restored.plan == {ROOM: final}
    assert restored.dorm_roommate_targets == original.dorm_roommate_targets
    assert dispatch.op_data.get_current_room(ROOM, True) == final
    dispatch.choose_agent.reset_mock()
    dispatch.tap_confirm.reset_mock()
    reads = []

    def observe(*args, **kwargs):
        rows = read_room(*args, **kwargs)
        reads.append(
            (
                dispatch.task,
                observed_recovery_recipient(rows, {}),
                dispatch.choose_agent.call_count,
                dispatch.tap_confirm.call_count,
            )
        )
        return rows

    dispatch.get_agent_from_room.side_effect = observe
    dispatch.run()
    assert reads and reads[0][0] is restored
    assert reads[0][1:] == (recipient, 0, 0)
    assert (
        dispatch.choose_agent.call_count
        == dispatch.tap_confirm.call_count
        == (0 if correct else 2)
    )
    if correct:
        assert len(reads) == 1
    else:
        assert dispatch.confirms[1] != final
    assert dispatch.physical == final
    vip = dispatch.op_data.operators[VIP]
    assert active_recovery_position(dispatch.op_data, vip) == (ROOM, 3)
    assert restored.time == scheduled and not restored.plan
    assert not getattr(restored, "dorm_roommate_targets", {})
    assert all(t is not restored for t in dispatch.tasks)
    scheduler.io.assert_not_called()
