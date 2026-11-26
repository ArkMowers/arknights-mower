"""验证定期无人机加速在制造暂停后让出派发，并按实际观测恢复。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import pytest

from arknights_mower.solvers import base_schedule as base
from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.image import bytes2img
from arknights_mower.utils.manufacture_product import product_task_meta
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.product_recognition import manufacture_detail_pause_state
from arknights_mower.utils.recognize import RecognizeError, Scene
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

ROOM = "room_1_2"
WORKER = "鸿雪"
MANUFACTURE_FIXTURES = Path(__file__).parent / "fixtures" / "manufacture"


@pytest.fixture
def routine_drone(monkeypatch, offline_maintenance):
    class Clock(datetime):
        current = datetime(2026, 11, 26, 19, 15, 10)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(base, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(
        config, "conf", config.Conf(drone_interval=1, maa_mall_enable=False)
    )
    monkeypatch.setattr(Operators, "current_room_changed_callback", None)
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(
        {
            "default_plan": Plan(
                {ROOM: [Room(WORKER, "", ["图耶"], "制造站")]},
                PlanConfig("", "", ""),
            ),
            "backup_plans": [],
        }
    )
    assert solver.op_data.init_and_validate() is None
    soldier = solver.op_data.operators[WORKER]
    soldier.current_room, soldier.current_index = "", -1
    solver.tasks, solver.task = [], None
    solver.planned, solver.todo_task = True, False
    solver.enable_party = False
    solver.drone_room = ROOM
    solver.drone_time = Clock.current - timedelta(hours=2)
    solver._routine_drone_pauses = {}
    solver.reload_time = None

    def reload():
        solver.reload_time = Clock.current

    solver.reload = Mock(side_effect=reload)
    solver.digit_reader = Mock()
    solver.digit_reader.get_drone.return_value = 199
    solver._confirm_drone_count = Mock()
    solver.sleep = Mock()
    state = SimpleNamespace(paused=True, page="overview")
    frames = {
        True: bytes2img(
            (MANUFACTURE_FIXTURES / "b303_product_settled_20261123.jpg").read_bytes()
        ),
        False: bytes2img((MANUFACTURE_FIXTURES / "adjusted_total.jpg").read_bytes()),
    }
    solver.recog = SimpleNamespace(w=1920, h=1080, img=None, gray=None)
    accelerate = ((1300, 900), (1350, 950))

    def enter(room):
        assert room == ROOM and state.page == "overview"
        state.page = "room"

    def find(resource):
        return {
            ("overview", "control_central"): ((960, 540), (1000, 580)),
            ("room", "arrange_check_in"): ((960, 540), (1000, 580)),
            ("product", "manufacture_accelerate"): accelerate,
            ("acceleration", "all_in"): ((1400, 900), (1450, 950)),
        }.get((state.page, resource))

    def tap(where, **kwargs):
        if state.page == "room":
            state.page = "product"
            solver.recog.img = frames[state.paused]
            solver.recog.gray = cv2.cvtColor(solver.recog.img, cv2.COLOR_RGB2GRAY)
        else:
            assert state.page == "product" and where == accelerate
            if not state.paused:
                state.page = "acceleration"

    def navigate(scene):
        assert scene == Scene.INFRA_MAIN
        state.page = "overview"

    def back(*, interval):
        assert state.page == "product"
        state.page = "room"

    solver.enter_room = Mock(side_effect=enter)
    solver.detect_room = Mock(return_value=ROOM)
    solver.back = Mock(side_effect=back)
    solver.find = Mock(side_effect=find)
    solver.tap = Mock(side_effect=tap)
    solver.scene_graph_navigation = Mock(side_effect=navigate)
    return solver, state, frames, Clock, accelerate


def test_routine_drone_releases_dispatch_until_actual_staffing_changes(routine_drone):
    solver, state, _, clock, accelerate = routine_drone
    previous_drone_time = solver.drone_time

    solver.infra_main()

    assert solver.todo_task and state.page == "overview"
    solver.reload.assert_called_once()
    assert solver.enter_room.call_count == 1
    assert all(call.args[0] != accelerate for call in solver.tap.call_args_list)
    solver.digit_reader.get_drone.assert_not_called()
    assert solver.drone_time is previous_drone_time
    assert solver.tasks == []
    assert solver.op_data.get_current_room(ROOM, bypass=True) == [""]
    for _ in range(3):
        clock.current += timedelta(minutes=30)
        solver._reconcile_room_observation(ROOM, [{"agent": "", "mood": -1}])
        solver.todo_task = False
        solver.infra_main()
    assert solver.enter_room.call_count == 1
    assert solver.drone_time is previous_drone_time

    worker = solver.op_data.operators[WORKER]
    worker.current_room, worker.current_index = ROOM, 0
    solver._reconcile_room_observation(
        ROOM, [{"agent": WORKER, "mood": -1, "observed": False}]
    )
    solver.todo_task = False
    solver.infra_main()
    assert solver.enter_room.call_count == 1
    assert solver.drone_time is previous_drone_time

    state.paused = False
    solver._reconcile_room_observation(ROOM, [{"agent": WORKER, "mood": 24}])
    solver.todo_task = False
    solver.infra_main()

    assert solver.enter_room.call_count == 2
    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == 1
    solver._confirm_drone_count.assert_called_once()
    assert solver.drone_time == clock.current

    solver.todo_task = False
    solver.infra_main()
    assert solver.enter_room.call_count == 2


@pytest.mark.parametrize("production", ["resumed", "paused", "unreadable"])
def test_routine_drone_rechecks_same_roster_after_fresh_read(routine_drone, production):
    solver, state, frames, clock, accelerate = routine_drone
    assert not solver._product_switching_enabled()
    assert not solver.op_data.mood_calculation_enabled
    roster = [{"agent": WORKER, "mood": 24}]
    worker = solver.op_data.operators[WORKER]
    worker.current_room, worker.current_index = ROOM, 0
    solver._reconcile_room_observation(ROOM, roster)
    previous_drone_time = solver.drone_time

    # 实际已离岗，暂停画面与上次读到的驻员名单不再一致。
    solver.infra_main()
    assert solver.enter_room.call_count == 1
    assert solver.drone_time is previous_drone_time
    solver.todo_task = False
    solver.infra_main()
    assert solver.enter_room.call_count == 1

    # 再次观测时已经有人进驻，期间没有读到空房。
    state.paused = production != "resumed"
    if production == "unreadable":
        frames[True][480:511, 1615:1755] = (255, 121, 0)
    for _ in range(3):
        solver._reconcile_room_observation(ROOM, roster)
        solver.todo_task = False
        solver.infra_main()

    assert solver.enter_room.call_count == 2
    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == (
        production == "resumed"
    )
    assert solver.sleep.call_count == (2 if production == "unreadable" else 0)
    if production == "resumed":
        solver._confirm_drone_count.assert_called_once()
        assert solver.drone_time == clock.current
    else:
        solver._confirm_drone_count.assert_not_called()
        assert solver.drone_time is previous_drone_time


@pytest.mark.parametrize("first_resample_has_accelerate", [True, False])
def test_routine_drone_resamples_uncertain_detail_during_recheck(
    routine_drone, first_resample_has_accelerate
):
    solver, state, frames, clock, accelerate = routine_drone
    soldier = solver.op_data.operators[WORKER]
    soldier.current_room, soldier.current_index = ROOM, 0
    roster = [{"agent": WORKER, "mood": 24}]
    solver._reconcile_room_observation(ROOM, roster)
    solver.infra_main()

    state.paused = False
    resumed_frame = frames[False]
    unsettled_frame = resumed_frame.copy()
    unsettled_frame[483:502, 1560:1584] = (255, 255, 255)
    frames[False] = unsettled_frame
    assert manufacture_detail_pause_state(unsettled_frame) is None

    find = solver.find.side_effect

    def find_in_frame(resource):
        if (
            resource == "manufacture_accelerate"
            and solver.sleep.call_count == 1
            and not first_resample_has_accelerate
        ):
            return None
        return find(resource)

    def read_resumed_frame(_interval):
        assert state.page == "product"
        solver.recog.img = resumed_frame
        solver.recog.gray = cv2.cvtColor(resumed_frame, cv2.COLOR_RGB2GRAY)

    solver.find.side_effect = find_in_frame
    solver.sleep.side_effect = read_resumed_frame
    solver._reconcile_room_observation(ROOM, roster)
    solver.todo_task = False
    solver.infra_main()

    assert solver.enter_room.call_count == 2
    assert solver.sleep.call_count == (1 if first_resample_has_accelerate else 2)
    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == 1
    solver._confirm_drone_count.assert_called_once()
    assert solver.drone_time == clock.current


@pytest.mark.parametrize("future_return", [False, True])
def test_routine_drone_skips_confirmed_empty_room_before_entering(
    routine_drone, future_return
):
    solver, state, _, clock, accelerate = routine_drone
    previous_drone_time = solver.drone_time
    if future_return:
        returning = SchedulerTask(
            time=clock.current + timedelta(hours=5),
            task_type=TaskTypes.SHIFT_ON,
            task_plan={ROOM: [WORKER]},
        )
        solver.tasks.append(returning)
        original_return_time = returning.time
    for _ in range(3):
        solver._reconcile_room_observation(ROOM, [{"agent": "", "mood": -1}])
        solver.todo_task = False
        solver.infra_main()
        clock.current += timedelta(minutes=30)

    solver.enter_room.assert_not_called()
    solver.tap.assert_not_called()
    solver.reload.assert_called_once()
    assert solver.drone_time is previous_drone_time
    assert len(solver.tasks) == int(future_return)
    if future_return:
        assert solver.tasks[0] is returning
        assert returning.time is original_return_time
        assert returning.plan == {ROOM: [WORKER]}
    solver._reconcile_room_observation(
        ROOM, [{"agent": WORKER, "mood": -1, "observed": False}]
    )
    solver._reconcile_room_observation("room_1_1", [{"agent": WORKER, "mood": 24}])
    solver.todo_task = False
    solver.infra_main()
    solver.enter_room.assert_not_called()

    state.paused = False
    worker = solver.op_data.operators[WORKER]
    worker.current_room, worker.current_index = ROOM, 0
    solver._reconcile_room_observation(ROOM, [{"agent": WORKER, "mood": 24}])
    solver.todo_task = False
    solver.infra_main()

    solver.enter_room.assert_called_once_with(ROOM)
    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == 1
    assert solver.drone_time == clock.current


@pytest.mark.parametrize("has_pending_switch", [False, True])
def test_unknown_product_of_empty_room_does_not_generate_a_switch(
    routine_drone, monkeypatch, has_pending_switch
):
    solver, _, _, _, _ = routine_drone
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    solver.op_data.products[ROOM] = "exp3"
    solver.op_data.update_facility_state(ROOM, "manufacture")
    solver._reconcile_room_observation(ROOM, [{"agent": "", "mood": -1}])
    switch = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT, meta_data=product_task_meta(ROOM, "exp3")
    )
    original_time = switch.time
    if has_pending_switch:
        solver.tasks.append(switch)
    for _ in range(3):
        solver.queue_product_switches()
    assert len(solver.tasks) == int(has_pending_switch)
    if has_pending_switch:
        assert solver.tasks[0] is switch and switch.time is original_time

    worker = solver.op_data.operators[WORKER]
    worker.current_room, worker.current_index = ROOM, 0
    solver._reconcile_room_observation(ROOM, [{"agent": WORKER, "mood": 24}])
    solver.op_data.update_facility_state(ROOM, "manufacture", "gold")
    solver.queue_product_switches()
    (selected,) = solver.tasks
    assert selected.meta_data == switch.meta_data
    if has_pending_switch:
        assert selected is switch and selected.time is original_time


@pytest.mark.parametrize("startup", [True, False])
def test_existing_staffing_repair_unblocks_product_switch_in_empty_room(
    routine_drone, monkeypatch, startup
):
    solver, _, _, clock, _ = routine_drone
    monkeypatch.setattr(config, "conf", config.Conf(product_switching={"enable": True}))
    solver.op_data.update_facility_state(ROOM, "manufacture", "gold")
    solver.op_data.products[ROOM] = "exp3"
    solver._initial_staffing_pending = startup
    solver.refresh_connecting = False
    solver._complete_group_shift = Mock(return_value=True)
    solver.plan_metadata = Mock()
    vacancy = [{"agent": "", "mood": -1}]
    solver._read_agent_mood = Mock(
        side_effect=lambda: solver._reconcile_room_observation(ROOM, vacancy)
    )
    if startup:
        solver._reconcile_room_observation(ROOM, vacancy)
        assert solver._reconcile_initial_staffing()
    else:
        assert solver.agent_get_mood() == "self_correction"
    (correction,) = solver.tasks
    assert correction.type == TaskTypes.SELF_CORRECTION
    assert correction.plan[ROOM] == [WORKER]
    assert correction.initial_staffing is startup
    solver.agent_get_mood(force=True, read_rooms=False)
    assert len(solver.tasks) == 1 and solver.tasks[0] is correction

    switch = SchedulerTask(
        time=clock.current - timedelta(minutes=1),
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta(ROOM, "exp3"),
    )
    solver.tasks.insert(0, switch)
    solver.task = switch
    original_time = switch.time
    sequence = []

    def arrange(plan, *args, **kwargs):
        sequence.append("staffing")
        assert plan[ROOM] == [WORKER]
        worker = solver.op_data.operators[WORKER]
        worker.current_room, worker.current_index = ROOM, 0
        solver._reconcile_room_observation(ROOM, [{"agent": WORKER, "mood": 24}])
        return True

    def switch_products(tasks, *, before_arrangement=False):
        if before_arrangement:
            raise base.ProductSwitchFailed("制造暂停，无法加速当前队列", [ROOM])
        sequence.append("product")
        assert solver.op_data.get_current_room(ROOM) == [WORKER]
        assert len(tasks) == 1 and tasks[0] is switch
        solver.op_data.update_facility_state(ROOM, "manufacture", "exp3")
        solver.tasks.remove(switch)

    solver.agent_arrange = Mock(side_effect=arrange)
    solver.switch_base_products = Mock(side_effect=switch_products)
    solver.infra_main()

    assert sequence == ["staffing"]
    assert len(solver.tasks) == 1 and solver.tasks[0] is switch
    assert switch.time is original_time
    assert solver.op_data.facility_states[ROOM]["product"] == "gold"

    solver.task = switch
    solver.infra_main()

    assert sequence == ["staffing", "product"]
    assert solver.tasks == []
    assert switch.time is original_time


def test_confirmed_product_page_can_release_routine_drone_without_staffing_change(
    routine_drone,
):
    solver, state, frames, clock, accelerate = routine_drone
    previous_drone_time = solver.drone_time
    solver.infra_main()

    # 只有同一制造站原有的产物页读取才能带来这项新证据。
    solver._product_switching_enabled = Mock(return_value=True)
    state.page = "room"
    assert solver._read_room_facility_product(ROOM, "manufacture", None, None, None)
    assert solver.op_data.facility_states[ROOM]["product"] == "gold"
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    solver.todo_task = False
    solver.infra_main()
    assert solver.enter_room.call_count == 1
    assert solver.drone_time is previous_drone_time

    unclear = frames[True].copy()
    unclear[480:511, 1615:1755] = (255, 121, 0)
    frames[True] = unclear
    state.page = "room"
    assert solver._read_room_facility_product(ROOM, "manufacture", None, None, None)
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    solver.todo_task = False
    solver.infra_main()
    assert solver.enter_room.call_count == 1
    assert solver.drone_time is previous_drone_time

    state.paused = False
    state.page = "room"
    assert solver._read_room_facility_product(ROOM, "manufacture", None, None, None)
    assert solver.op_data.get_current_room(ROOM, bypass=True) == [""]
    assert solver.drone_time is previous_drone_time
    solver.scene_graph_navigation(Scene.INFRA_MAIN)
    solver.todo_task = False
    solver.infra_main()

    assert solver.enter_room.call_count == 2
    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == 1
    solver._confirm_drone_count.assert_called_once()
    assert solver.drone_time == clock.current


def test_routine_drone_keeps_bounded_panel_failure_without_pause_text(routine_drone):
    solver, _, frames, _, accelerate = routine_drone
    previous_drone_time = solver.drone_time
    frames[True][480:511, 1615:1755] = (255, 121, 0)

    with pytest.raises(RecognizeError, match="all_in"):
        solver.infra_main()

    assert sum(call.args[0] == accelerate for call in solver.tap.call_args_list) == 3
    assert solver.drone_time is previous_drone_time
    assert not solver.todo_task
    assert not solver._routine_drone_pauses


@pytest.mark.parametrize(
    ("image", "status"),
    [
        ("b303_product_opening_20261123.jpg", True),
        ("b303_product_settled_20261123.jpg", True),
        ("adjusted_total.jpg", False),
        ("b303_room_20261123.jpg", None),
    ],
)
def test_manufacture_pause_status_from_capture(image, status):
    frame = bytes2img((MANUFACTURE_FIXTURES / image).read_bytes())
    assert manufacture_detail_pause_state(frame) is status


@pytest.mark.parametrize("step", ["survey", "accelerate", "switch"])
def test_product_switch_preserves_paused_queue_before_acceleration(routine_drone, step):
    solver, _, frames, _, _ = routine_drone
    solver.recog.img = frames[True]
    solver._open_manufacture_product_detail = Mock()
    solver._manufacture_is_idle = Mock(return_value=False)
    solver._start_product_switch_log = Mock()
    solver._tap_drone_accelerate = Mock()
    solver._select_manufacture_product = Mock()
    observation = {"room": ROOM, "current_product": "gold", "target_product": "exp3"}

    with pytest.raises(RecognizeError, match="制造暂停，无法加速当前制造队列"):
        if step == "survey":
            solver._survey_manufacture_switch(ROOM, "exp3")
        elif step == "accelerate":
            solver._execute_manufacture_acceleration(observation)
        else:
            solver._change_manufacture_product(observation)

    solver._manufacture_is_idle.assert_called_once()
    solver._tap_drone_accelerate.assert_not_called()
    solver._select_manufacture_product.assert_not_called()
