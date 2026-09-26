"""中枢已耗尽干员不重读不存在的计时，恢复和正常工作计时保持不变。"""

import sys
from datetime import datetime, timedelta
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.operators import Operator, Operators  # noqa: E402
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes  # noqa: E402


@pytest.fixture
def room_reader():
    def make(room="central", name="歌蕾蒂娅", mood=0):
        target = SimpleNamespace(
            current_room=room,
            current_index=0,
            mood=mood,
            time_stamp=datetime.now(),
            depletion_rate=0,
            lower_limit=0,
            exhaust_time=None,
            need_to_refresh=MagicMock(return_value=True),
            current_mood=MagicMock(return_value=mood),
            is_working=MagicMock(return_value=not room.startswith("dorm")),
        )
        op_data = SimpleNamespace(
            operators={name: target},
            plan={room: [SimpleNamespace(agent="Free")]},
            true_exhaust_room={"central"},
            dorm=[],
            config=SimpleNamespace(free_room=False),
        )

        def update_detail(name, value, room, index, update_time):
            target.mood = value
            target.current_room = room
            target.current_index = index
            if update_time:
                target.time_stamp = datetime.now()

        op_data.update_detail = update_detail
        op_data.refresh_dorm_time = MethodType(Operators.refresh_dorm_time, op_data)
        solver = object.__new__(BaseSchedulerSolver)
        solver.op_data = op_data
        solver.tasks, solver.task = [], None
        solver.leifeng_mode = True
        solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
        solver.turn_on_room_detail = MagicMock()
        solver.detect_product_complete = MagicMock(return_value=None)
        solver.detect_room = MagicMock(return_value=room)

        def find(resource, scope=None):
            if resource == "room_detail":
                return ((1, 1), (2, 2))
            if resource == "infra_no_operator" and scope[0][1] == 344:
                return ((1, 1), (2, 2))
            return None

        solver.find = MagicMock(side_effect=find)
        solver.read_screen = MagicMock(return_value=name)
        solver.read_accurate_mood = MagicMock(return_value=mood)
        deadline = datetime.now() + timedelta(hours=1)
        solver.read_operator_time = MagicMock(return_value=deadline)
        return solver, target, deadline

    return make


def test_confirmed_exhausted_central_sets_real_exhaust_time_without_timer_ocr(
    room_reader,
):
    solver, target, _ = room_reader()
    before = datetime.now()
    result = solver.get_agent_from_room("central", [0])[0]
    after = datetime.now()
    assert before <= result["time"] <= after
    assert before <= target.exhaust_time <= after
    assert result["mood"] == 0
    solver.read_operator_time.assert_not_called()
    assert solver.read_screen.call_count == 2
    assert solver.read_accurate_mood.call_count == 2
    solver.recog.update.assert_called_once()


@pytest.mark.parametrize("room", ["dormitory_1", "train", "room_1_1", "contact"])
def test_zero_mood_outside_central_keeps_existing_countdown(room_reader, room):
    solver, _, deadline = room_reader(room=room)
    result = solver.get_agent_from_room(room, [0])[0]
    assert result["time"] == deadline
    solver.read_operator_time.assert_called_once_with(
        room, 0, ((1650, 270), (1780, 305))
    )
    solver.recog.update.assert_not_called()


def test_fiammetta_keeps_countdown_even_when_in_central(room_reader):
    solver, _, deadline = room_reader(name="菲亚梅塔")
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.read_operator_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("phase", ["move", "charge", "restore"])
def test_fiammetta_read_refreshes_reservation_from_actual_slot(room_reader, phase):
    room = "dormitory_1"
    solver, fia, deadline = room_reader(room=room, name="菲亚梅塔", mood=7.5)
    solver.op_data.experimental_dorm_logic = True
    solver.op_data.get_dorm_by_name = lambda name: (None, None)
    solver.op_data.plan[room][0].agent = "杜林"
    fia.current_room, fia.current_index = "dormitory_2", 2
    fia.need_to_refresh.return_value = False
    fia.mood = 24
    charge = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={room: ["伊内丝", "菲亚梅塔"]},
        meta_data="伊内丝",
    )
    restore = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA,
        task_plan={room: ["菲亚梅塔"], "central": ["伊内丝"]},
    )
    solver.task = {"move": None, "charge": charge, "restore": restore}[phase]
    reserved = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, time=deadline + timedelta(hours=5)
    )
    original_times = (charge.time, restore.time)
    solver.tasks = [charge, restore, reserved]
    result = solver.get_agent_from_room(room)
    solver.read_accurate_mood.assert_called_once()
    solver.read_operator_time.assert_called_once()
    assert fia.mood == result[0]["mood"] == 7.5
    assert reserved.time == result[0]["time"] == deadline
    assert (charge.time, restore.time) == original_times
    assert solver.tasks == [charge, restore, reserved]


@pytest.mark.parametrize("guard", ["retry", "initial", "legacy", "selected"])
def test_fiammetta_refresh_preserves_retry_and_initialization_guards(
    room_reader, guard
):
    solver, _, deadline = room_reader(room="dormitory_1", name="菲亚梅塔", mood=8)
    solver.op_data.experimental_dorm_logic = guard != "legacy"
    old_time = deadline + timedelta(hours=1)
    task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, time=old_time)
    solver.tasks = [task]
    if guard == "retry":
        task.fia_retry_after = old_time
    if guard == "initial":
        solver.defer_backup_plan_until_mood_read = True
    if guard == "selected":
        solver.task = task
    solver._refresh_fiammetta_task(deadline)
    assert task.time == old_time


def test_fiammetta_removed_from_dorm_invalidates_only_idle_reservation(room_reader):
    solver, _, deadline = room_reader(room="dormitory_1", name="菲亚梅塔", mood=8)
    solver.op_data.experimental_dorm_logic = True
    solver.op_data.get_dorm_by_name = lambda name: (None, None)
    solver.find.return_value = True
    solver.find.side_effect = None  # 实际房间已空，肥鸭离宿。
    timer = SchedulerTask(task_type=TaskTypes.FIAMMETTA, time=deadline)
    restore = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, task_plan={"dormitory_1": ["菲亚梅塔"]}
    )
    other = SchedulerTask(task_type=TaskTypes.SHIFT_ON)
    solver.tasks = [timer, restore, other]
    solver.get_agent_from_room("dormitory_1")
    assert solver.tasks == [restore, other]
    assert solver.op_data.operators["菲亚梅塔"].current_room == ""


@pytest.mark.parametrize("location", ["dormitory_2", "", "unexpected_occupant"])
def test_fiammetta_reschedules_from_actual_room_after_move(room_reader, location):
    solver, fia, deadline = room_reader(room="dormitory_2", name="菲亚梅塔", mood=24)
    fia.current_room = "dormitory_2" if location == "unexpected_occupant" else location
    solver.op_data.experimental_dorm_logic = True
    solver.op_data.run_order_rooms = {}
    solver.op_data.exhaust_agent = set()
    solver._sync_run_order_tasks = MagicMock()
    solver.check_fia = MagicMock(return_value=(["伊内丝"], "dormitory_1"))
    solver.enter_room, solver.back = MagicMock(), MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[
            {
                "agent": "杜林" if location == "unexpected_occupant" else "菲亚梅塔",
                "time": deadline,
            }
        ]
    )
    solver.run_order_solver()
    if location:
        solver.get_agent_from_room.assert_called_once_with("dormitory_2", [0])
    else:
        solver.enter_room.assert_not_called()
    assert bool(solver.tasks) == (location == "dormitory_2")
    if solver.tasks:
        assert solver.tasks[0].time == deadline


def test_fiammetta_swap_reads_target_and_fiammetta_mood(room_reader):
    target_solver, target, _ = room_reader(room="dormitory_1", name="伊内丝", mood=7.5)
    target_solver.task = SchedulerTask(
        task_type=TaskTypes.FIAMMETTA, meta_data="伊内丝"
    )
    target.need_to_refresh.return_value = True
    target_solver.read_accurate_mood.return_value = 24
    result = target_solver.get_agent_from_room("dormitory_1", [0])
    target_solver.read_accurate_mood.assert_called_once()
    assert result[0]["mood"] == target.mood == 24

    fia_solver, fia, _ = room_reader(room="dormitory_1", name="菲亚梅塔", mood=7.5)
    fia_solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data="伊内丝")
    fia.need_to_refresh.return_value = False
    fia_solver.op_data.update_detail = MagicMock(return_value=None)
    # 静态排班的该槽位是 Free；充能任务会临时把菲亚梅塔换入。
    fia_solver.get_agent_from_room("dormitory_1", [0], related_operators={0: "伊内丝"})
    fia_solver.read_accurate_mood.assert_called_once()
    fia_solver.op_data.update_detail.assert_called_once_with(
        "菲亚梅塔",
        7.5,
        "dormitory_1",
        0,
        True,
        related_operator="伊内丝",
        mood_event="fiammetta_charge",
    )


def test_fiammetta_swap_writes_target_before_and_after_one_second_apart(
    monkeypatch,
):
    def operator(name, room, mood):
        return SimpleNamespace(
            name=name,
            current_room=room,
            current_index=0,
            mood=mood,
            time_stamp=datetime.now(),
            depletion_rate=0,
            lower_limit=0,
            exhaust_time=None,
            group="深海猎人" if name == "歌蕾蒂娅" else "",
            need_to_refresh=MagicMock(return_value=False),
            current_mood=MagicMock(return_value=mood),
            is_working=MagicMock(return_value=False),
            is_high=MagicMock(return_value=name == "歌蕾蒂娅"),
        )

    target = operator("歌蕾蒂娅", "control", 0)
    fia = operator("菲亚梅塔", "dormitory_2", 24)
    op_data = SimpleNamespace(
        operators={"歌蕾蒂娅": target, "菲亚梅塔": fia},
        plan={
            "dormitory_1": [
                SimpleNamespace(agent="Free"),
                SimpleNamespace(agent="Free"),
            ]
        },
        true_exhaust_room=set(),
        dorm=[],
        config=SimpleNamespace(free_room=False),
        update_detail=MagicMock(return_value=None),
        refresh_dorm_time=MagicMock(),
    )
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = op_data
    solver.tasks = []
    solver.task = SchedulerTask(task_type=TaskTypes.FIAMMETTA, meta_data="歌蕾蒂娅")
    solver.leifeng_mode = True
    solver.recog = MagicMock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.refresh_facility_state = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.detect_product_complete = MagicMock(return_value=False)
    solver.find = MagicMock(return_value=None)
    solver.read_screen = MagicMock(side_effect=["歌蕾蒂娅", "菲亚梅塔"])
    solver.read_accurate_mood = MagicMock(side_effect=[24, 0])
    solver.read_operator_time = MagicMock(return_value=datetime.now())
    save_history = MagicMock()
    monkeypatch.setattr(base, "save_agent_action", save_history)

    result = solver.get_agent_from_room(
        "dormitory_1", [0, 1], related_operators={1: "歌蕾蒂娅"}
    )

    assert [item["mood"] for item in result] == [24, 0]
    target_call, fia_call = op_data.update_detail.call_args_list
    assert target_call.args[:5] == ("歌蕾蒂娅", 24, "dormitory_1", 0, True)
    assert target_call.kwargs["mood_event"] == "fiammetta_after"
    assert fia_call.args[:5] == ("菲亚梅塔", 0, "dormitory_1", 1, True)
    assert fia_call.kwargs["mood_event"] == "fiammetta_charge"
    assert target_call.kwargs["recorded_at"] - fia_call.kwargs[
        "recorded_at"
    ] == timedelta(seconds=1)
    save_history.assert_called_once_with(
        "歌蕾蒂娅",
        "control",
        "dormitory_1",
        True,
        "深海猎人",
        0,
        related_operator="菲亚梅塔",
        mood_event="fiammetta_before",
        current_time=fia_call.kwargs["recorded_at"],
    )


@pytest.mark.parametrize("already_arranged", [False, True])
def test_fiammetta_arrangement_requests_both_mood_indexes(already_arranged):
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask(
        task_plan={"dormitory_1": ["伊内丝", "菲亚梅塔"]},
        task_type=TaskTypes.FIAMMETTA,
        meta_data="伊内丝",
    )
    solver.tasks = [solver.task]
    target = SimpleNamespace(room="meeting", time_stamp=datetime.now())
    fia = SimpleNamespace(room="dormitory_1", time_stamp=datetime.now())

    def current_room(room, _refresh=True):
        if room == "dormitory_1":
            return ["伊内丝" if already_arranged else "杜林", "菲亚梅塔"]
        return ["伊内丝"]

    solver.op_data = SimpleNamespace(
        operators={"伊内丝": target, "菲亚梅塔": fia},
        get_current_room=MagicMock(side_effect=current_room),
        run_order_rooms={},
        experimental_dorm_logic=already_arranged,
    )
    solver.enter_room = MagicMock()
    solver.turn_on_room_detail = MagicMock()
    solver.refresh_current_room = MagicMock(return_value=["杜林", "菲亚梅塔"])
    solver.ensure_dorm_recovery_order = MagicMock(return_value=False)
    solver.prepare_dorm_selection = MagicMock(return_value=None)
    solver.find = MagicMock(return_value=True)
    solver.choose_agent = MagicMock()
    solver.tap_confirm = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": "伊内丝"}, {"agent": "菲亚梅塔"}]
    )
    solver.scene = MagicMock()
    solver.waiting_scene = []
    solver.back = MagicMock()

    plan = solver.task.plan
    restored = solver.agent_arrange_room({}, "dormitory_1", plan)

    if already_arranged:
        solver.get_agent_from_room.assert_called_once_with("dormitory_1", [0, 1])
        solver.choose_agent.assert_not_called()
    else:
        solver.get_agent_from_room.assert_called_once_with(
            "dormitory_1", [0, 1], {1: "伊内丝"}
        )
    assert restored == {
        "dormitory_1": ["杜林", "菲亚梅塔"],
        "meeting": ["伊内丝"],
    }


def test_nonzero_central_keeps_measured_working_countdown(room_reader):
    solver, target, deadline = room_reader(mood=8)
    result = solver.get_agent_from_room("central", [0])[0]
    assert result["time"] == target.exhaust_time == deadline
    solver.read_operator_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("change", ["room", "name", "mood", "detail", "connecting"])
def test_uncertain_second_observation_keeps_existing_countdown(room_reader, change):
    solver, _, deadline = room_reader()
    if change == "room":
        solver.detect_room.return_value = "dormitory_1"
    elif change == "name":
        solver.read_screen.side_effect = ["歌蕾蒂娅", "夕"]
    elif change == "mood":
        solver.read_accurate_mood.side_effect = [0, 3]
    elif change in ("detail", "connecting"):
        old_find = solver.find.side_effect

        def find(resource, **kwargs):
            if resource == "room_detail" and change == "detail":
                return None
            if resource == "connecting" and change == "connecting":
                return ((1, 1), (2, 2))
            return old_find(resource, **kwargs)

        solver.find.side_effect = find
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.read_operator_time.assert_called_once()


def test_cached_zero_mood_is_not_an_exhaustion_measurement(room_reader):
    solver, target, deadline = room_reader()
    target.need_to_refresh.return_value = False
    # 只有读完缓存后才出现的时间请求，不能把估算的零心情变成已确认耗尽。
    solver.op_data.update_detail = MagicMock(return_value=0)
    assert solver.get_agent_from_room("central")[0]["time"] == deadline
    solver.read_accurate_mood.assert_not_called()
    solver.read_operator_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("condition", ["not_working", "not_exhaust_room"])
def test_zero_mood_without_working_exhaustion_semantics_keeps_countdown(
    room_reader, condition
):
    solver, target, deadline = room_reader()
    if condition == "not_working":
        target.is_working.return_value = False
    else:
        solver.op_data.true_exhaust_room.clear()
    assert solver.get_agent_from_room("central", [0])[0]["time"] == deadline
    solver.read_operator_time.assert_called_once()
    solver.recog.update.assert_not_called()


@pytest.mark.parametrize("experimental", [False, True])
@pytest.mark.parametrize("rest_in_full", [False, True])
@pytest.mark.parametrize("lower,mood", [(0, 2), (10, 12), (12, 12), (12, 11)])
def test_exhaust_task_uses_custom_lower_limit_with_original_preparation_margin(
    monkeypatch, experimental, rest_in_full, lower, mood
):
    now = datetime(2026, 9, 26, 12)
    clock = MagicMock()
    clock.now.return_value = now
    monkeypatch.setattr(base, "datetime", clock)
    op = Operator("银灰", "room_1_1", operator_type="high")
    op.current_room, op.current_index = "room_1_1", 0
    op.time_stamp, op.mood = now, mood
    op.lower_limit, op.upper_limit = lower, 20
    op.exhaust_require, op.rest_in_full = True, rest_in_full
    solver = object.__new__(BaseSchedulerSolver)
    solver.tasks, solver.task = [], None
    solver.op_data = SimpleNamespace(
        operators={op.name: op},
        plan={},
        run_order_rooms={},
        exhaust_agent={op.name},
        rest_in_full_group={op.name} if rest_in_full else set(),
        experimental_dorm_logic=experimental,
    )
    solver._sync_run_order_tasks = MagicMock()
    solver.check_fia = MagicMock(return_value=(None, None))
    solver.enter_room = MagicMock()
    solver.back = MagicMock()
    solver.get_agent_from_room = MagicMock(
        return_value=[{"agent": op.name, "time": now + timedelta(hours=6)}]
    )
    solver.run_order_solver()
    assert len(solver.tasks) == 1
    task = solver.tasks[0]
    remaining = 6 * ((mood - lower) / mood if experimental else 1)
    expected = max(
        now,
        now
        + timedelta(hours=remaining)
        - timedelta(minutes=10 if rest_in_full else 30),
    )
    assert task.type == TaskTypes.EXHAUST_OFF
    assert task.time == expected
