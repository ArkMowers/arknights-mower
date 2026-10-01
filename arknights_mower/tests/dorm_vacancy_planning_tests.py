"""集中恢复剩余空床复用统一候选，未知心情交给游戏选人确认。"""

from datetime import datetime

from arknights_mower.tests import dorm_release_tests
from arknights_mower.utils import resting_priority, scheduler_task
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

op_data = dorm_release_tests.op_data
ROOM = dorm_release_tests.ROOM


def open_bed(data, monkeypatch):
    monkeypatch.setattr(resting_priority, "agent_list", list(data.operators))
    data.operators["空爆"].current_room = "meeting"
    data.dorm[0].reset()


def test_rescue_fills_unreserved_vacancy_without_changing_other_residents(
    op_data, monkeypatch
):
    data = op_data
    open_bed(data, monkeypatch)
    data.rescue_mode = True
    tasks = []

    scheduler_task.try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert len(tasks) == 1
    assert tasks[0].type == TaskTypes.FILL_DORM
    assert tasks[0].plan == {ROOM: ["Current"] * 4 + ["红"]}
    assert tasks[0].simple_dorm_fill
    assert not data.dorm[0].name


def test_rescue_filling_cannot_take_an_occupied_bed(op_data, monkeypatch):
    monkeypatch.setattr(resting_priority, "agent_list", list(op_data.operators))
    op_data.rescue_mode = True
    tasks = []

    scheduler_task.try_add_release_dorm({}, None, op_data, tasks)

    assert tasks == []
    assert op_data.dorm[0].name == "空爆"


def test_rescue_vacancy_respects_pending_primary_arrangement(op_data, monkeypatch):
    data = op_data
    open_bed(data, monkeypatch)
    data.rescue_mode = True
    primary = SchedulerTask(
        datetime.now(), {ROOM: ["Current"] * 4 + ["银灰"]}, TaskTypes.SHIFT_OFF
    )
    tasks = [primary]

    scheduler_task.try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert tasks == [primary]


def test_unknown_cached_operator_does_not_bypass_game_mood_search(op_data, monkeypatch):
    data = op_data
    open_bed(data, monkeypatch)
    data.operators["红"].time_stamp = None
    tasks = []

    scheduler_task.try_add_release_dorm({}, None, data, tasks, empty_only=True)

    assert tasks[0].plan == {ROOM: ["Current"] * 4 + ["Free"]}
    assert data.operators["红"].dorm_mood_fallback == ""


def test_rescue_metadata_keeps_only_filling_actual_vacancies(op_data, monkeypatch):
    data = op_data
    open_bed(data, monkeypatch)
    data.rescue_mode = True
    monkeypatch.setattr(data, "rescue_needed", lambda: True)
    filling = SchedulerTask(
        datetime.now(), {ROOM: ["Current"] * 4 + ["红"]}, TaskTypes.FILL_DORM
    )

    assert filling in scheduler_task.plan_metadata(data, [filling])

    data.dorm[0].name = "空爆"
    data.operators["空爆"].current_room = ROOM
    data.operators["空爆"].current_index = 4
    assert filling not in scheduler_task.plan_metadata(data, [filling])


def test_full_resident_unknown_search_is_one_batch_and_stops_after_real_full_read(
    op_data, monkeypatch
):
    monkeypatch.setattr(resting_priority, "agent_list", list(op_data.operators))
    op_data.operators["红"].time_stamp = None
    tasks = []

    scheduler_task.try_add_release_dorm({}, None, op_data, tasks)
    scheduler_task.try_add_release_dorm({}, None, op_data, tasks)

    assert len(tasks) == 1
    assert tasks[0].plan == {ROOM: ["Current"] * 4 + ["Free"]}
    assert tasks[0].dorm_mood_residents == ["空爆"]
    op_data.stop_idle_dorm_search()
    tasks.clear()
    scheduler_task.try_add_release_dorm({}, None, op_data, tasks)
    assert tasks == []


def test_rescue_metadata_drops_filling_when_primary_later_reserves_same_bed(
    op_data, monkeypatch
):
    data = op_data
    open_bed(data, monkeypatch)
    data.rescue_mode = True
    monkeypatch.setattr(data, "rescue_needed", lambda: True)
    fill = SchedulerTask(
        datetime.now(), {ROOM: ["Current"] * 4 + ["红"]}, TaskTypes.FILL_DORM
    )
    primary = SchedulerTask(
        datetime.now(), {ROOM: ["Current"] * 4 + ["银灰"]}, TaskTypes.SHIFT_OFF
    )

    rebuilt = scheduler_task.plan_metadata(data, [fill, primary])

    assert primary in rebuilt
    assert fill not in rebuilt
