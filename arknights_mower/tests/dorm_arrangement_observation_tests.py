"""宿舍执行名单独立核验，计划内离宿保留实测和绑组恢复边界。"""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes, plan_metadata

ROOM = "dormitory_1"


@pytest.fixture
def incident(monkeypatch, offline_maintenance):
    # 调度导入链的森空岛查询与本回归无关，替换范围限定在夹具内。
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", MagicMock())
    from arknights_mower.solvers import base_schedule, record

    monkeypatch.setattr(logger, "disabled", True)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    monkeypatch.setattr(record, "save_agent_action", lambda *a, **kw: None)
    monkeypatch.setattr(base_schedule, "_is_mastery_busy", lambda name: False)
    config.conf.enable_mastery = False
    config.conf.group_rest_in_full_on_mood_gap = False
    data = Operators(
        {
            "default_plan": Plan(
                {
                    "central": [Room("歌蕾蒂娅", "深海", ["黑角"])],
                    "room_3_2": [Room("斯卡蒂", "深海", ["米格鲁"])],
                    ROOM: [
                        Room(n, "", [])
                        for n in ["杜林", "琴柳", "Free", "Free", "Free"]
                    ],
                    "dormitory_2": [
                        Room(n, "", [])
                        for n in ["梓兰", "安赛尔", "Free", "Free", "Free"]
                    ],
                },
                PlanConfig("", "", "", free_room=True, ope_resting_priority="歌蕾蒂娅"),
            ),
            "backup_plans": [],
        }
    )
    assert data.init_and_validate() is None
    now = datetime.now()
    for name, mood in [("陈", 5), ("芬", 24), ("夜刀", 24)]:
        data.add(Operator(name, "", mood=mood, time_stamp=now))
    physical = {
        "central": ["黑角"],
        "room_3_2": ["米格鲁"],
        ROOM: ["杜林", "琴柳", "斯卡蒂", "芬", "夜刀"],
        "dormitory_2": ["梓兰", "安赛尔", "歌蕾蒂娅", "", ""],
    }
    for room, row in physical.items():
        for index, name in enumerate(row):
            if not name:
                continue
            op = data.operators[name]
            op._current_room, op.current_index = room, index
            op.mood, op.time_stamp = (5 if name == "歌蕾蒂娅" else 24), now
    for bed in data.dorm:
        op = data.get_current_operator(*bed.position)
        if op:
            bed.name = op.name
            bed.time = now + timedelta(hours=3) if op.name == "歌蕾蒂娅" else now
    data.commit_group_shifts({"深海": True})
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.op_data = data
    solver.tasks = plan_metadata(data, [])
    release = next(
        t
        for t in solver.tasks
        if t.type == TaskTypes.RELEASE_DORM and "斯卡蒂" in t.release_dorm_targets()
    )
    solver.task = release
    solver.find_next_task = MagicMock(return_value=None)
    solver.last_train_mood_read = now
    solver._suppress_train_correction = lambda plan: None
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.scene = MagicMock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.waiting_scene = []
    solver.back = MagicMock()
    solver.record_selection_success = MagicMock()
    solver.profession_filter = MagicMock()
    solver.switch_arrange_order = MagicMock()
    solver.swipe_left = MagicMock(return_value=0)
    solver.scan_agent = MagicMock(return_value=([], []))
    monkeypatch.setattr(
        base_schedule, "defer_dorm_before_priority_task", lambda *a: False
    )
    chosen = {}
    snapshots = []

    def choose(row, room, *a, **kw):
        assert "Free" not in row
        chosen[room] = list(row)

    solver.choose_agent = MagicMock(side_effect=choose)

    def confirm(room, previous):
        physical[room] = chosen[room] + [""] * (
            len(data.plan[room]) - len(chosen[room])
        )

    solver.tap_confirm = MagicMock(side_effect=confirm)
    reading = {}

    def find(name, **kwargs):
        if name != "infra_no_operator":
            return True
        index = reading["index"]
        reading["index"] += 1
        reading["name"] = physical[reading["room"]][index]
        return not reading["name"]

    solver.find = MagicMock(side_effect=find)
    solver.read_screen = MagicMock(side_effect=lambda *a, **kw: reading["name"])
    solver.read_accurate_mood = MagicMock(
        side_effect=lambda *a: data.operators[reading["name"]].mood
    )
    solver.read_operator_time = MagicMock(return_value=now + timedelta(hours=3))
    solver.refresh_facility_state = MagicMock()
    solver.wait_product_complete = MagicMock()
    solver.scroll_room_operators = MagicMock()

    def observe(room, *a, **kw):
        reading.update(room=room, index=0)
        result = base_schedule.BaseSchedulerSolver.get_agent_from_room(
            solver, room, *a, **kw
        )
        snapshots.append(physical[room].copy())
        return result

    solver.get_agent_from_room = MagicMock(side_effect=observe)
    return solver, physical, snapshots


@pytest.mark.parametrize("sample", ["measured", "prediction", "unknown"])
@pytest.mark.parametrize("single_target", [False, True])
def test_generated_idle_release_preserves_resting_group(
    incident, single_target, sample
):
    solver, physical, snapshots = incident
    data = solver.op_data
    if single_target:
        data.config.ope_resting_priority.append("陈")
    before = [
        (t, t.time, deepcopy(t.plan))
        for t in solver.tasks
        if t.type == TaskTypes.SHIFT_ON
    ]
    assert before
    completed = data.operators["斯卡蒂"]
    measured_at = completed.time_stamp
    if sample == "prediction":
        completed.mood_is_prediction = True
    elif sample == "unknown":
        completed.time_stamp = None

    assert solver.arrange_release_dorm()[0] is not False

    assert physical[ROOM] == ["杜林", "琴柳", "陈", "芬", "夜刀"]
    count = len(solver.tasks)
    for _ in range(3):
        assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
        assert len(solver.tasks) == count
    assert any("" in row for row in snapshots) == single_target
    completed = data.operators["斯卡蒂"]
    assert not completed.current_room
    assert completed.time_stamp is not None
    assert completed.time_stamp >= measured_at
    assert completed.mood == 24
    assert not completed.mood_is_prediction
    assert completed.depletion_rate == 0
    assert data.operators["歌蕾蒂娅"].is_resting()
    assert data.operators["歌蕾蒂娅"].mood == 5
    assert data.group_is_resting("深海")
    assert all(
        t in solver.tasks and t.time == when and t.plan == plan
        for t, when, plan in before
    )
    # 清退后仍正常补入新住客，并按需确认单回。
    assert data.operators["陈"].current_room == ROOM
    assert data.operators["陈"].dorm_recovery_room == (ROOM if single_target else "")


@pytest.mark.parametrize("sample", ["measured", "prediction", "unknown"])
def test_charge_temporary_roster_preserves_completed_resting_member(incident, sample):
    solver, physical, _ = incident
    data = solver.op_data
    now = datetime.now()
    data.add(Operator("菲亚梅塔", ROOM, index=0, mood=24, time_stamp=now))
    data.plan[ROOM][0].agent = "菲亚梅塔"
    data.operators.pop("杜林")
    fia = data.operators["菲亚梅塔"]
    fia._current_room, fia.current_index = ROOM, 0
    physical[ROOM][0] = fia.name
    original = physical[ROOM].copy()
    returning = next(t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON)
    charge = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={ROOM: ["陈", "菲亚梅塔"]},
        meta_data="陈",
    )
    solver.task, solver.tasks = charge, [charge, returning]
    completed = data.operators["斯卡蒂"]
    if sample == "prediction":
        completed.mood_is_prediction = True
    elif sample == "unknown":
        completed.time_stamp = None

    solver.agent_arrange(charge.plan, get_time=True)

    assert physical[ROOM] == ["陈", "菲亚梅塔", "", "", ""]
    correction = solver.agent_get_mood(read_rooms=False, return_plan=True)
    assert "central" not in correction
    assert "room_3_2" not in correction
    assert data.operators["斯卡蒂"].time_stamp is not None
    assert not data.operators["斯卡蒂"].mood_is_prediction
    assert data.group_is_resting("深海")
    restoration = next(
        t for t in solver.tasks if t is not charge and t.type == TaskTypes.FIAMMETTA
    )
    assert restoration.plan == {ROOM: original}
    solver.task = restoration

    solver.agent_arrange(restoration.plan, get_time=True)

    assert physical[ROOM] == original
    assert data.operators["斯卡蒂"].is_resting()
    assert returning in solver.tasks
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}


def test_local_arrangement_readback_does_not_use_outer_task_roster(incident):
    solver, physical, _ = incident
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    outer = SchedulerTask(task_type=TaskTypes.WORKSHOP, meta_data="陈")
    solver.task = outer
    solver.tasks = [outer, *[t for t in solver.tasks if t.type == TaskTypes.SHIFT_ON]]
    local = {ROOM: ["杜林", "琴柳", "陈", "芬", "夜刀"]}

    solver.agent_arrange(local, get_time=True)

    assert not local
    assert not outer.plan
    assert physical[ROOM] == ["杜林", "琴柳", "陈", "芬", "夜刀"]
    assert solver.op_data.operators["斯卡蒂"].time_stamp is not None
    assert solver.agent_get_mood(read_rooms=False, return_plan=True) == {}
