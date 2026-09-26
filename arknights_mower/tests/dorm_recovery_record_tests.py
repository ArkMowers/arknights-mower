"""恢复记录的生命周期，以及不养闲人从生成到执行的回归。"""

from datetime import timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.tests import ling_xi_rest_limit_tests, shift_off_mood_tests
from arknights_mower.tests.ling_xi_rest_limit_tests import NOW
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import (
    TaskTypes,
    generate_plan_by_drom,
    plan_metadata,
)

solver = ling_xi_rest_limit_tests.solver
shift_solver = shift_off_mood_tests.solver
ROOM = "dormitory_1"


def populate(data):
    for bed in data.dorm:
        if bed.name:
            op = data.operators[bed.name]
            op.current_room, op.current_index = "", -1
        bed.reset()
    for index, name in enumerate(["诗怀雅", "赫默", "深巡"], 2):
        data.add(Operator(name, ""))
        op = data.operators[name]
        op.current_room, op.current_index = ROOM, index
        op.mood, op.time_stamp = 10, NOW
        bed = data.dorm[index - 2]
        bed.name, bed.time = name, NOW + timedelta(hours=index)


@pytest.mark.parametrize("elapsed", [False, True])
def test_repeated_read_preserves_deadline_in_test_mode(solver, elapsed):
    data = solver.op_data
    populate(data)
    bed = data.dorm[1]
    due = NOW + timedelta(minutes=-1 if elapsed else 90)
    bed.time = due
    data.update_detail("赫默", 24 if elapsed else 11, ROOM, 3)
    data.refresh_dorm_time(ROOM, 3, {"agent": "赫默", "time": NOW + timedelta(hours=5)})
    assert (bed.time == due) is data.experimental_dorm_logic
    if data.experimental_dorm_logic and elapsed:
        data.correct_dorm()
        assert data.operators["赫默"].mood == 24


@pytest.mark.parametrize(
    "destination", ["same", "ordinary_swap", "leave_single", "leave", "other_room"]
)
def test_recovery_record_lifecycle(solver, destination):
    data = solver.op_data
    populate(data)
    single = destination == "leave_single"
    name, source = ("诗怀雅", 2) if single else ("赫默", 3)
    room, index = {
        "same": (ROOM, source),
        "ordinary_swap": (ROOM, 4),
        "leave_single": (ROOM, 4),
        "leave": ("", -1),
        "other_room": ("dormitory_2", 3),
    }[destination]
    due = data.dorm[source - 2].time
    if destination == "ordinary_swap":
        # 先读另一个换位者；两人的旧记录都应失效。
        data.update_detail("深巡", 10, ROOM, 3)
    data.update_detail(name, 10, room, index)
    _, bed = data.get_dorm_by_name(name)
    kept = data.experimental_dorm_logic and destination == "same"
    assert (bed is not None and bed.time == due) is kept
    if destination in ("leave", "other_room"):
        assert not any(bed.name == name for bed in data.dorm)


@pytest.mark.parametrize("swapped", [False, True])
def test_daily_room_read_only_ocr_changed_positions(solver, monkeypatch, swapped):
    data = solver.op_data
    populate(data)
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *a, **kw: None
    )
    expected = [bed.time for bed in data.dorm]
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.find = MagicMock(return_value=None)
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.scroll_room_operators = MagicMock()
    solver.read_screen = MagicMock(
        side_effect=["冰酿", "闪灵", "诗怀雅"]
        + (["深巡", "赫默"] if swapped else ["赫默", "深巡"])
    )
    solver.read_accurate_mood = MagicMock(return_value=10)
    solver.read_operator_time = MagicMock(return_value=NOW + timedelta(hours=6))
    solver.get_agent_from_room(ROOM)
    if data.experimental_dorm_logic:
        assert solver.read_operator_time.call_count == (2 if swapped else 0)
        assert data.dorm[0].time == expected[0]
        if not swapped:
            assert [bed.time for bed in data.dorm] == expected
    else:
        assert solver.read_operator_time.call_count == 3


@pytest.mark.parametrize("timer", ["past", "future", "missing"])
def test_full_releases_have_identity_and_execute_individually(solver, timer):
    data = solver.op_data
    if not data.experimental_dorm_logic:
        return
    populate(data)
    data.config.free_room = True
    for bed in data.dorm:
        data.operators[bed.name].mood = 10 if timer == "past" else 24
        bed.time = (
            None
            if timer == "missing"
            else NOW + timedelta(minutes=-5 if timer == "past" else 5)
        )
    tasks = plan_metadata(data, [])
    releases = [task for task in tasks if task.type == TaskTypes.RELEASE_DORM]
    assert {task.meta_data for task in releases} == {"诗怀雅", "赫默", "深巡"}
    for task in releases:
        assert task.time <= NOW + timedelta(seconds=2)
        assert sum(names.count("Free") for names in task.plan.values()) == 1
        task.time = NOW  # 模拟调度等待到执行时刻。
        solver.task, solver.tasks = task, [task]
        solver.agent_arrange = MagicMock()
        expected = task.plan.copy()
        solver.infra_main()
        solver.agent_arrange.assert_called_once_with(expected, True)
    # 一次执行失败后仍占床，重算时仍须生成；已离宿后才停止。
    assert (
        len([t for t in plan_metadata(data, []) if t.type == TaskTypes.RELEASE_DORM])
        == 3
    )
    data = data.project_arrangements(
        [{ROOM: ["Current", "Current", "Free", "Free", "Free"]}]
    )
    assert not any(t.type == TaskTypes.RELEASE_DORM for t in plan_metadata(data, []))


def test_stale_named_release_cannot_evict_new_occupant(solver):
    data = solver.op_data
    if not data.experimental_dorm_logic:
        return
    populate(data)
    data.config.free_room = True
    tasks = plan_metadata(data, [])
    task = next(t for t in tasks if t.type == TaskTypes.RELEASE_DORM)
    op = data.operators[task.meta_data]
    op.current_room, op.current_index = "", -1
    task.time = NOW
    solver.task, solver.tasks = task, [task]
    solver.agent_arrange = MagicMock()
    solver.infra_main()
    solver.agent_arrange.assert_called_once_with({}, False)


def test_all_rescue_covers_prefer_higher_cached_mood_only_in_test_mode(
    solver, monkeypatch
):
    data = solver.op_data
    data.config.resting_threshold = 0.65
    monkeypatch.setattr(config.conf, "rescue_threshold", 0.75)
    for name, mood in [("结城理", 0), ("酒神", 10.3)]:
        data.add(Operator(name, ""))
        data.operators[name].mood, data.operators[name].time_stamp = mood, NOW
    op = data.operators["絮雨"]
    op.replacement = ["结城理", "酒神"]
    assert data.replacement_candidates(op) == (
        ["酒神", "结城理"] if data.experimental_dorm_logic else op.replacement
    )


def test_selected_work_cover_cannot_also_reserve_a_rest_bed(shift_solver):
    data = shift_solver.op_data
    if not data.experimental_dorm_logic:
        return
    cover = data.operators["伺夜"]
    cover.mood = 0
    shift_solver.total_agent.append(cover)
    plan = shift_solver.resting()
    assert plan["room_1_1"] == [cover.name]
    assert all(bed.name != cover.name for bed in data.dorm)


@pytest.mark.parametrize(
    "interval,gap,merged",
    [(10, 8, True), (10, 11, False), (5, 8, False), (15, 11, True)],
)
def test_named_releases_keep_original_merge_window(
    solver, monkeypatch, interval, gap, merged
):
    data = solver.op_data
    populate(data)
    data.config.free_room = True
    monkeypatch.setattr(config.conf, "merge_interval", interval)
    first, second = NOW + timedelta(minutes=1), NOW + timedelta(minutes=1 + gap)
    tasks = generate_plan_by_drom(
        {},
        data,
        release_tasks={first: ([data.dorm[0]], None), second: ([data.dorm[1]], None)},
    )
    assert len(tasks) == 2
    early = next(task for task in tasks if task.plan[ROOM][2] == "Free")
    late = next(task for task in tasks if task.plan[ROOM][3] == "Free")
    assert late.time == second
    assert early.time == (second + timedelta(seconds=1) if merged else first)
    if data.experimental_dorm_logic:
        assert (early.meta_data, late.meta_data) == ("诗怀雅", "赫默")


def test_default_merge_window_is_ten_minutes():
    assert config.Conf().merge_interval == 10
