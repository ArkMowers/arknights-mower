"""宿舍执行名单独立核验，计划内离宿保留实测和绑组恢复边界。"""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.utils import config
from arknights_mower.utils.dorm_candidates import dorm_candidate_mood
from arknights_mower.utils.log import logger
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.scene import Scene
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


@pytest.mark.parametrize("first_read_fails", [False, True])
@pytest.mark.parametrize("already_in_selection", [False, True])
def test_staffing_reuses_only_product_read_in_this_visit(
    incident, first_read_fails, already_in_selection
):
    solver, physical, snapshots = incident
    room = "room_3_2"
    config.conf.product_switching.enable = True
    del solver.refresh_facility_state
    solver.detect_room_type = MagicMock(return_value="制造站")
    solver.detect_room = MagicMock(return_value=room)
    room_find = solver.find
    selecting = already_in_selection

    def open_selection(_):
        nonlocal selecting
        selecting = True

    def find(name, **kwargs):
        if name == "confirm_blue":
            return True if selecting else None
        if name in ("manufacture_accelerate", "connecting"):
            return None
        return room_find(name, **kwargs)

    solver._open_room_selection = open_selection
    solver.find = MagicMock(side_effect=find)
    solver._wait_drone_interface = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    solver.op_data.update_facility_state(room, "manufacture", "exp3")
    readings = ["gold", "exp3"]
    if first_read_fails:
        readings.insert(0, ValueError("无法读取产物"))
    solver.read_manufacture_product = MagicMock(side_effect=readings)

    for target, product in [("陈", "gold"), ("米格鲁", "exp3")]:
        original = physical[room].copy()
        task = SchedulerTask(
            task_type=TaskTypes.SELF_CORRECTION, task_plan={room: [target]}
        )
        solver.task, solver.tasks = task, [task]
        selecting = already_in_selection
        solver.agent_arrange_room({}, room, task.plan)
        assert snapshots[-2:] == [original, [target]]
        assert solver.op_data.facility_product(room) == product
        assert solver.choose_agent.call_args.kwargs["selection_product"] == (
            None
            if already_in_selection or (target == "陈" and first_read_fails)
            else product
        )
        assert room not in task.plan
    assert solver._wait_drone_interface.call_count == 2 + first_read_fails


@pytest.mark.parametrize(
    ("starts_open", "change", "fail_first"),
    [
        (True, False, False),
        (False, False, False),
        (True, True, False),
        (True, True, True),
        (False, True, True),
    ],
)
@pytest.mark.parametrize(
    ("strategy_name", "product"), [("开采协力", "orundum"), ("龙门商法", "lmd")]
)
def test_trade_staffing_reads_strategy_and_residents_in_current_panel_order(
    incident, starts_open, change, fail_first, strategy_name, product
):
    solver, physical, snapshots = incident
    room = "room_3_2"
    resident = physical[room][0]
    target = "陈" if change else resident
    task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={room: [target]}
    )
    solver.task, solver.tasks = task, [task]
    config.conf.product_switching.enable = True
    solver.op_data.update_facility_state(room, "trade", "lmd")
    solver.recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.recog.w, solver.recog.h = 1920, 1080
    solver.detect_room_type = lambda: "贸易站"
    room_titles = []

    def detect_room():
        # 第一帧仍显示上一站的房号，换帧后才提供当前房间身份。
        room_titles.append(room if solver.recog.update.call_count else "room_3_1")
        return room_titles[-1]

    solver.detect_room = detect_room
    solver.get_color = lambda point: np.array([255, 255, 255])
    del solver.refresh_facility_state
    del solver.turn_on_room_detail
    events = []
    page = "details" if starts_open else "room"
    closing = False
    original_find = solver.find

    def find(name, **kwargs):
        if name == "infra_no_operator":
            assert page == "details"
            assert solver.detect_room() == room
            events.append("roster")
            return original_find(name, **kwargs)
        if name == "bill_accelerate" and page == "orders":
            return (100, 200)
        if name in ("room_detail", "arrange_check_in_on") and page == "details":
            return (80, 410)
        if name == "arrange_check_in" and page == "room":
            return (80, 410)
        if name == "confirm_blue" and page == "selection":
            return (1500, 950)
        return None

    def tap(point, **kwargs):
        nonlocal page, closing
        if point == (80, 410):
            if page == "details":
                assert not closing
                closing = True
                events.append("close")
            else:
                assert page == "room"
                page = "details"
                events.append("open")
        elif point[0] < 100:
            assert page == "room"
            page = "orders"
        else:
            assert page == "details"
            page = "selection"
            events.append("select")

    def next_frame(_):
        nonlocal page, closing
        if closing:
            page, closing = "room", False

    def end_orders(_):
        nonlocal page
        assert page == "orders"
        page = "room"

    def strategy(_):
        assert page == "orders"
        assert solver.detect_room() == room
        events.append("strategy")
        return "" if fail_first and events.count("strategy") == 1 else strategy_name

    original_confirm = solver.tap_confirm.side_effect

    def confirm(*args):
        nonlocal page
        assert page == "selection"
        original_confirm(*args)
        page = "details"

    solver.find = find
    solver.tap = tap
    solver.sleep = next_frame
    solver.scene.side_effect = lambda: (
        Scene.RIIC_OPERATOR_SELECT if page == "selection" else Scene.INFRA_MAIN
    )
    solver.scene_graph_navigation = end_orders
    solver._product_ocr_text = strategy
    solver.tap_confirm.side_effect = confirm

    solver.agent_arrange_room({}, room, task.plan)

    expected = (
        ["roster", "close", "strategy"]
        if starts_open
        else ["strategy", "open", "roster"]
    )
    if change:
        if starts_open:
            expected.append("open")
        expected.extend(["select", "roster"])
        if fail_first:
            expected.extend(["close", "strategy"])
    assert events == expected
    assert room_titles[:2] == ["room_3_1", room]
    assert snapshots == ([[resident], [target]] if change else [[resident]])
    assert physical[room] == [target]
    assert task.plan == {}
    if change:
        assert solver.choose_agent.call_args.kwargs["selection_product"] == (
            None if fail_first else product
        )
    assert solver.op_data.facility_product_count("orundum") == int(product == "orundum")
    assert solver.op_data.facility_product_count("lmd") == int(product == "lmd")


@pytest.mark.parametrize("panel", ["arrange_check_in_on", "arrange_check_in"])
@pytest.mark.parametrize("detected_room", ["room_3_1", ""])
def test_stale_trade_room_cannot_publish_strategy_or_residents(
    incident, panel, detected_room
):
    from arknights_mower.utils.recognize import RecognizeError

    solver, physical, snapshots = incident
    room = "room_3_2"
    config.conf.product_switching.enable = True
    solver.task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={room: ["陈"]}
    )
    solver.op_data.update_facility_state(room, "trade", "lmd")
    solver.recog._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    solver.detect_room_type = lambda: "贸易站"
    solver.detect_room = lambda: detected_room
    solver.find = lambda name, **kw: (80, 410) if name == panel else None
    del solver.refresh_facility_state
    solver._wait_drone_interface = MagicMock()
    observed = set()

    with pytest.raises(RecognizeError, match="房号"):
        solver.get_agent_from_room(room, observed_facilities=observed)

    assert not observed and not snapshots
    assert solver.op_data.get_current_room(room, True) == physical[room]
    assert solver.op_data.facility_product(room) == "lmd"
    solver._wait_drone_interface.assert_not_called()
    solver.read_screen.assert_not_called()


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
    # 全满原班直接换入。该夹具不提供同帧倒计时，不能把入住成功当成单回确认。
    assert all("" not in row for row in snapshots)
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
    assert not data.operators["陈"].dorm_recovery_room


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


def test_only_adding_residents_reuses_single_recovery_readback(incident):
    solver, physical, snapshots = incident
    target = ["杜林", "琴柳", "歌蕾蒂娅", "斯卡蒂", "陈"]
    empty = [""] * len(target)
    temporary = [*target[:3], "", ""]
    physical[ROOM] = empty.copy()
    solver.task = SchedulerTask(
        task_type=TaskTypes.SELF_CORRECTION, task_plan={ROOM: target.copy()}
    )
    solver.tasks = [solver.task]

    solver.agent_arrange_room({}, ROOM, solver.task.plan, get_time=True)

    assert snapshots == [empty, temporary, target]
    assert solver.choose_agent.call_count == solver.tap_confirm.call_count == 2
    assert solver.op_data.operators["歌蕾蒂娅"].current_index == 2
    assert solver.op_data.operators["歌蕾蒂娅"].dorm_recovery_index == -1
    assert not solver.task.plan


@pytest.mark.parametrize("sample", ["measured", "prediction", "unknown"])
def test_departure_below_mood_cap_preserves_only_measured_sample(incident, sample):
    solver, physical, _ = incident
    data = solver.op_data
    name = "望"
    data.add(Operator(name, "", current_room=ROOM, current_index=3))
    physical[ROOM][3] = name
    data.dorm_mood_estimates[name] = (24, datetime.now())
    data.update_detail(name, 19.35, ROOM, 3, update_time=True)
    operator = data.operators[name]
    operator.depletion_rate = -2
    observed_at = operator.time_stamp
    assert name not in data.dorm_mood_estimates
    if sample == "prediction":
        operator.mood_is_prediction = True
    elif sample == "unknown":
        operator.time_stamp = None
    bed = next(bed for bed in data.dorm if bed.position == (ROOM, 3))
    bed.name, bed.time = name, datetime.now() + timedelta(hours=3)
    physical[ROOM][3] = ""
    solver.task = SchedulerTask(
        task_type=TaskTypes.RE_ORDER, task_plan={ROOM: physical[ROOM].copy()}
    )

    solver._reconcile_room_observation(
        ROOM, [{"agent": occupant} for occupant in physical[ROOM]]
    )

    assert (operator.current_room, operator.current_index) == ("", -1)
    assert (bed.name, bed.time) == ("", None)
    if sample == "measured":
        assert (operator.mood, operator.time_stamp) == (19.35, observed_at)
        assert operator.depletion_rate == 0
        assert dorm_candidate_mood(data, name) == 19.35
        assert operator.current_mood(datetime.now() + timedelta(hours=2)) == 19.35
    else:
        assert operator.time_stamp is None
        assert dorm_candidate_mood(data, name) is None
