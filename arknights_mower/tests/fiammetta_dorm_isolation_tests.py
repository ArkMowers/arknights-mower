"""肥鸭任务的明确名单不参与普通宿舍清退；选目标前补读失效心情。"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests import dorm_group_tests
from arknights_mower.tests.choose_agent_filter_tests import selection_solver
from arknights_mower.utils import config
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "dormitory_1"
solver = dorm_group_tests.solver


def test_real_selection_keeps_full_charge_target(solver, monkeypatch):
    data = solver.op_data
    data.config.free_room = True
    data.add(Operator("菲亚梅塔", ROOM, index=3))
    data.operators["伊内丝"].mood = 24
    instance, selected = selection_solver(
        monkeypatch, residents=["塑心", "冰酿", "泥岩", "能天使", "年"]
    )
    instance.op_data = data
    instance.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data="伊内丝")
    agents = ["伊内丝", "菲亚梅塔"]

    instance.choose_agent(agents, ROOM)

    assert agents == selected == ["伊内丝", "菲亚梅塔"]
    instance.get_free_list.assert_not_called()


@pytest.mark.parametrize("free_room", [False, True])
@pytest.mark.parametrize("phase", ["charge", "restore"])
def test_fiammetta_exact_roster_survives_dorm_normalization(solver, free_room, phase):
    data = solver.op_data
    data.config.free_room = free_room
    data.add(Operator("菲亚梅塔", ROOM, index=3))
    data.operators["伊内丝"].mood = 24
    data.operators["伊内丝"].depletion_rate = 3
    data.operators["泥岩"].mood = 24
    # 原住者保床也不能覆盖临时充能名单。
    data.config.free_room_exclusions = ["泥岩"]
    agents = (
        ["伊内丝", "菲亚梅塔"]
        if phase == "charge"
        else ["塑心", "冰酿", "泥岩", "菲亚梅塔", "年"]
    )
    solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: agents.copy()},
        meta_data="伊内丝" if phase == "charge" else "",
    )
    solver.tasks = [solver.task]
    # 这两个入口分别覆盖测试宿舍执行边界和稳定逻辑选人边界。
    solver.preserve_resting_crafters(agents, ROOM)
    assert solver.prepare_dorm_selection(agents, ROOM) == []

    assert agents == solver.task.plan[ROOM]
    assert data.operators["伊内丝"].depletion_rate == 3


def test_fia_does_not_retain_idle_excluded_resident_in_target_slot(solver):
    data = solver.op_data
    data.config.free_room = True
    data.config.free_room_exclusions = ["泥岩"]
    target = data.operators["伊内丝"]
    target.mood = target.upper_limit = 12
    data.config.operator_mood_limits[target.name] = {"lower": 0, "upper": 12}
    agents = ["塑心", "冰酿", target.name, "菲亚梅塔"]
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data=target.name)

    solver.prepare_dorm_selection(agents, ROOM)

    assert agents[2] == target.name


def test_plan_fia_refreshes_zero_rate_cache_before_full_mood_decision(
    solver, monkeypatch
):
    target = solver.op_data.operators["伊内丝"]
    target.group = ""
    target.mood = 24
    target.depletion_rate = 0
    target.time_stamp = datetime.now() - timedelta(minutes=40)
    solver.check_fia = lambda: ([target.name], ROOM)
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.enter_room = MagicMock()
    solver.back = MagicMock()

    def read(room, indexes):
        assert (room, indexes) == ("meeting", [0])
        solver.op_data.update_detail(target.name, 20, room, 0, True)

    solver.get_agent_from_room = MagicMock(side_effect=read)
    monkeypatch.setattr(config.conf, "fia_fool", True)
    solver.plan_fia()

    assert target.mood == 20
    assert target.depletion_rate > 0
    assert solver.tasks[0].plan == {ROOM: [target.name, "菲亚梅塔"]}
    solver.enter_room.assert_called_once_with("meeting")
    solver.back.assert_called_once()


@pytest.mark.parametrize("cause", ["expired", "zero_rate", "resting"])
def test_fia_refresh_groups_candidate_reads_by_actual_room(solver, cause):
    names = ["伊内丝", "银灰"]
    room = ROOM if cause == "resting" else "meeting"
    for index, name in enumerate(names):
        op = solver.op_data.operators[name]
        op.current_room, op.current_index = room, index
        op.depletion_rate = 0 if cause == "zero_rate" else 1
        op.time_stamp = datetime.now() - timedelta(hours=3 if cause == "expired" else 0)
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock()
    solver.back = MagicMock()

    solver._refresh_fia_candidate_moods(names)

    solver.enter_room.assert_called_once_with(room)
    solver.get_agent_from_room.assert_called_once_with(room, [0, 1])
    solver.back.assert_called_once()


def test_fia_fresh_working_cache_needs_no_extra_room_visit(solver):
    target = solver.op_data.operators["伊内丝"]
    target.depletion_rate = 1
    solver._refresh_fia_candidate_moods([target.name])
    solver.enter_room.assert_not_called()


def test_fia_failed_mood_read_does_not_schedule_from_stale_cache(solver):
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA)
    solver.check_fia = lambda: (["伊内丝"], ROOM)
    solver.enter_room = MagicMock()
    solver.get_agent_from_room = MagicMock(side_effect=RuntimeError("read failed"))
    solver.back = MagicMock()
    with pytest.raises(RuntimeError, match="read failed"):
        solver.plan_fia()
    assert solver.tasks == []


@pytest.mark.parametrize("read_mood", [False, True])
def test_charge_return_keeps_work_rate_and_later_work_can_recalibrate(
    solver, monkeypatch, read_mood
):
    import numpy as np

    data = solver.op_data
    target = data.operators["讯使"]
    target._current_room, target.current_index = ROOM, 2
    target.mood, target.time_stamp, target.depletion_rate = 24, datetime.now(), 3.25
    solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, task_plan={"contact": ["讯使"]}
    )
    solver.tasks = [solver.task]
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.find = MagicMock(return_value=None)
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.scroll_room_operators = MagicMock()
    solver.read_screen = MagicMock(return_value="讯使")
    solver.read_accurate_mood = MagicMock(return_value=24)
    solver.read_operator_time = MagicMock(return_value=datetime.now())
    monkeypatch.setattr(target, "need_to_refresh", lambda **kw: read_mood)
    monkeypatch.setattr(
        "arknights_mower.solvers.record.save_agent_action", lambda *a, **kw: None
    )
    solver.get_agent_from_room("contact")
    assert target.current_room == "contact"
    assert target.depletion_rate == 3.25
    assert target.mood == 24
    half_hour = target.time_stamp + timedelta(minutes=30)
    assert target.current_mood(half_hour) == pytest.approx(22.375)
    # 正常工作实读仍校准速度，充能保护不是永久锁定速度。
    target.time_stamp = datetime.now() - timedelta(hours=1)
    data.update_detail(target.name, 20, "contact", 0, True)
    assert target.depletion_rate == pytest.approx(4, abs=0.01)
