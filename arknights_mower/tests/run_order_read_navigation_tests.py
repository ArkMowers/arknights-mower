import copy
import pickle
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.run_order_staffing_admission_tests import staffed_order


@pytest.fixture
def order_navigation(monkeypatch):
    return staffed_order.__wrapped__(monkeypatch)


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("first_room_grouped", [False, True])
def test_initial_idle_primary_keeps_first_assignment_after_priority_yield(
    order_navigation, restart, first_room_grouped
):
    from arknights_mower.tests.run_order_staffing_admission_tests import correction
    from arknights_mower.utils.recovery_execution import initial_idle_staffing_members

    ui = order_navigation
    solver = ui.solver
    ui.config.conf.enable_mastery = True
    solver.op_data.backup_plans = []
    solver.op_data.global_plan["backup_plans"] = []
    solver.op_data.plan_condition = []
    start = ui.clock.now()
    primary = solver.op_data.operators["图耶"]
    primary.rest_in_full = False
    primary.group = ""
    primary.current_room, primary.current_index, primary.time_stamp = "", -1, None
    assert 18 > primary.lower_limit
    solver.op_data.dorm_mood_estimates[primary.name] = (18, start)
    if first_room_grouped:
        first = solver.op_data.operators["鸿雪"]
        first.group = "首房"
        solver.op_data.groups[first.group] = [first.name]
        solver.op_data.group_shift_state[first.group] = False
        solver.op_data.plan["room_1_1"][0].group = first.group
        configured = solver.op_data.global_plan["default_plan"].plan
        configured["room_1_1"][0].group = first.group
    arrangement = correction(ui, {"room_1_1", "room_2_2"})
    arrangement.derived_correction = True
    arrangement.initial_staffing = True
    priority = ui.task(
        time=start + timedelta(seconds=180),
        task_type=ui.task_type.SWAP_SUPPORT,
        task_plan={"train": ["Current", "Current"]},
    )
    solver.tasks.append(priority)
    ui.durations["room_1_1"] = 120

    solver.infra_main()

    assert arrangement in solver.tasks and arrangement.time == start
    assert arrangement.plan == {"room_2_2": [primary.name]}
    assert arrangement.derived_correction_started
    if first_room_grouped:
        assert arrangement.group_shift_expected
    assert primary.name in arrangement.initial_staffing_idle_members
    assert not getattr(arrangement, "execution_failure", None)
    assert ui.clock.now() < priority.time
    solver.tasks.remove(priority)
    if restart:
        restored = pickle.loads(pickle.dumps(arrangement))
        solver.tasks[solver.tasks.index(arrangement)] = restored
        arrangement = restored
    ui.clock.current = priority.time + timedelta(seconds=1)
    solver.task = arrangement

    assert primary.name in arrangement.initial_staffing_idle_members
    assert initial_idle_staffing_members(
        solver.op_data, arrangement, now=ui.clock.now()
    ) == {primary.name}
    without_admission = copy.copy(arrangement)
    without_admission.initial_staffing_idle_members = set()
    assert not initial_idle_staffing_members(
        solver.op_data, without_admission, now=ui.clock.now()
    )
    solver.op_data.dorm_mood_estimates[primary.name] = (
        primary.lower_limit,
        ui.clock.now(),
    )
    assert not initial_idle_staffing_members(
        solver.op_data, arrangement, now=ui.clock.now()
    )
    solver.op_data.dorm_mood_estimates[primary.name] = (18, ui.clock.now())

    solver.infra_main()

    assert solver.op_data.operators[primary.name].current_room == "room_2_2"
    assert arrangement.time == start and arrangement.plan == {}
    assert arrangement not in solver.tasks
    assert [event[1] for event in ui.events if event[0] == "staffed"] == [
        "room_1_1",
        "room_2_2",
    ]


def test_final_order_read_reserves_mastery_handoff_before_another_read(
    order_navigation,
):
    from arknights_mower.tests.run_order_staffing_admission_tests import correction

    ui = order_navigation
    solver = ui.solver
    ui.config.conf.enable_mastery = True
    solver.op_data.backup_plans = []
    solver.op_data.global_plan["backup_plans"] = []
    solver.op_data.plan_condition = []
    start = ui.clock.now()
    ui.occupants.update({"room_1_1": ["孑"], "room_2_2": ["图耶"]})
    ui.states.update({"room_1_1": "active", "room_2_2": "active"})
    for room in ("room_1_1", "room_2_2"):
        solver.get_agent_from_room(room)
    ui.events.clear()
    arrangement = correction(ui, {"room_1_1"})
    refreshes = [
        ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=room)
        for room in ("room_1_1", "room_2_2")
    ]
    swap = ui.task(
        time=start + timedelta(seconds=400),
        task_type=ui.task_type.SWAP_SUPPORT,
        task_plan={"train": ["Current", "Current"]},
    )
    solver.tasks.extend([*refreshes, swap])
    ui.deadlines["room_1_1"] = start + timedelta(seconds=340)
    read_time = solver.read_time.side_effect

    def read_with_navigation_cost(*args, **kwargs):
        ui.clock.current += timedelta(seconds=50)
        return read_time(*args, **kwargs)

    solver.read_time.side_effect = read_with_navigation_cost

    solver.infra_main()

    assert [event[1] for event in ui.events if event[0] == "read"] == ["room_1_1"]
    assert ui.clock.now() == start + timedelta(seconds=70)
    assert swap.time == start + timedelta(seconds=99)
    assert arrangement not in solver.tasks and arrangement.time == start
    assert arrangement.plan == {}
    assert refreshes[0] not in solver.tasks
    assert refreshes[1] in solver.tasks
    assert not getattr(refreshes[1], "execution_failure", None)


@pytest.mark.parametrize("mastery_enabled", [False, True])
@pytest.mark.parametrize("priority_kind", ["SWAP_SUPPORT", "RELEASE_DORM"])
def test_final_reads_respect_priority_after_refresh_operator_moves(
    order_navigation, monkeypatch, mastery_enabled, priority_kind
):
    from arknights_mower.tests.run_order_staffing_admission_tests import correction

    ui = order_navigation
    solver = ui.solver
    ui.config.conf.enable_mastery = mastery_enabled
    solver.op_data.backup_plans = []
    solver.op_data.global_plan["backup_plans"] = []
    solver.op_data.plan_condition = []
    solver.op_data.global_plan["default_plan"].config.refresh_trading_config = ["鸿雪"]
    solver.op_data.config.refresh_trading_config = ["鸿雪"]
    ui.occupants.update({"room_1_1": ["孑"], "room_2_2": ["图耶"]})
    ui.states.update({"room_1_1": "active", "room_2_2": "active"})
    for room in ("room_1_1", "room_2_2"):
        solver.get_agent_from_room(room)
        solver.plan_run_order(room)
    solver.op_data.first_init = False
    solver.op_data.operators["鸿雪"].refresh_order_room = [True, []]
    monkeypatch.setattr(
        ui.operators, "current_room_changed_callback", solver.current_room_changed
    )
    ui.events.clear()
    ui.durations["room_1_1"] = 80
    task = correction(ui, {"room_1_1", "room_2_2"})
    original_time = task.time
    priority_at = ui.clock.now() + timedelta(seconds=100)
    priority = ui.task(
        time=priority_at,
        task_type=getattr(ui.task_type, priority_kind),
        task_plan=(
            {"dormitory_1": ["Current", "Current", "Free", "Current", "Current"]}
            if priority_kind == "RELEASE_DORM"
            else {"train": ["Current", "Current"]}
        ),
        strict_mood_limit=priority_kind == "RELEASE_DORM",
    )
    if priority_kind == "RELEASE_DORM":
        priority.mood_limit_deadline = priority_at + timedelta(seconds=90)
    solver.tasks.append(priority)
    read_time = solver.read_time.side_effect

    def read_with_navigation_cost(*args, **kwargs):
        ui.clock.current += timedelta(seconds=50)
        return read_time(*args, **kwargs)

    solver.read_time.side_effect = read_with_navigation_cost

    solver.infra_main()

    if not mastery_enabled and priority_kind == "SWAP_SUPPORT":
        assert task.plan == {} and task not in solver.tasks
        read_rooms = [event[1] for event in ui.events if event[0] == "read"]
        assert read_rooms.count("room_1_1") == read_rooms.count("room_2_2") == 1
        assert priority in solver.tasks
        return
    assert ui.clock.now() < priority_at
    if priority_kind == "SWAP_SUPPORT":
        assert task.plan == {"room_2_2": ["图耶"]}
    else:
        assert task.plan and "room_1_1" not in task.plan
    remaining_plan = copy.deepcopy(task.plan)
    assert task.time == original_time and task in solver.tasks
    assert [event[1] for event in ui.events if event[0] == "read"] == []
    waiting = next(
        pending
        for pending in solver.tasks
        if pending.type == ui.task_type.REFRESH_TIME and pending.meta_data == "room_2_2"
    )
    assert waiting.meta_data == "room_2_2"
    assert not getattr(waiting, "execution_failure", None)
    for _ in range(3):
        solver.task = task
        solver.infra_main()
        assert task.time == original_time and task.plan == remaining_plan
        assert waiting in solver.tasks
        assert [event[1] for event in ui.events if event[0] == "read"] == []

    ui.clock.current = priority_at + timedelta(minutes=1)
    solver.tasks.remove(priority)
    solver.task = task
    solver.infra_main()

    assert task.plan == {} and task not in solver.tasks
    assert task.time == original_time and waiting not in solver.tasks
    read_rooms = [event[1] for event in ui.events if event[0] == "read"]
    assert len(read_rooms) == 2
    assert set(read_rooms) == {"room_1_1", "room_2_2"}
    assert [call.args[0] for call in solver.choose_agent.call_args_list].count(
        ["鸿雪"]
    ) == 1


@pytest.mark.parametrize("priority_kind", ["RUN_ORDER", "SWAP_SUPPORT", "RELEASE_DORM"])
@pytest.mark.parametrize("offset", [-1, 60])
def test_final_reads_preserve_due_refresh_before_imminent_priority(
    order_navigation, priority_kind, offset
):
    ui = order_navigation
    solver = ui.solver
    ui.config.conf.enable_mastery = True
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={},
    )
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_1_1")
    priority = ui.task(
        time=ui.clock.now() + timedelta(seconds=offset),
        task_type=getattr(ui.task_type, priority_kind),
        task_plan={"dormitory_1": ["Current"] * 5},
        meta_data="room_2_2" if priority_kind == "RUN_ORDER" else "",
        strict_mood_limit=priority_kind == "RELEASE_DORM",
    )
    solver.task, solver.tasks = arrangement, [arrangement, refresh, priority]
    solver.op_data.products["room_2_2"] = "orundum"
    solver.op_data.refresh_run_order_rooms()
    before = copy.deepcopy(vars(refresh)), copy.deepcopy(vars(arrangement))

    for _ in range(3):
        solver._read_arrangement_order_times("room_1_1")

    assert not any(event[0] == "read" for event in ui.events)
    assert vars(refresh) == before[0]
    assert arrangement.time == before[1]["time"]
    assert arrangement.plan == before[1]["plan"]
    assert all(task in solver.tasks for task in (arrangement, refresh, priority))

    solver.tasks.remove(priority)
    ui.states["room_1_1"] = "active"
    solver._read_arrangement_order_times("room_1_1")

    assert [event[1] for event in ui.events if event[0] == "read"] == ["room_1_1"]
    assert refresh not in solver.tasks
    assert any(pending.type == ui.task_type.RUN_ORDER for pending in solver.tasks)
    assert arrangement.time == before[1]["time"]
    assert arrangement.plan == {}


def test_blocked_order_allows_independent_final_refresh(order_navigation):
    ui = order_navigation
    solver = ui.solver
    arrangement = ui.task(task_type=ui.task_type.SELF_CORRECTION)
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_1_1")
    restoration = ui.task(
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_2_2": ["图耶"]},
    )
    restoration.run_order_original_roster = copy.deepcopy(restoration.plan)
    restoration.run_order_restore_pending = True
    blocked = ui.task(
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_2_2": ["龙舌兰"]},
        meta_data="room_2_2",
    )
    blocked_time = blocked.time
    solver.task = arrangement
    solver.tasks = [arrangement, refresh, restoration, blocked]
    ui.states["room_1_1"] = "active"

    solver._read_arrangement_order_times("room_1_1")

    assert [event[1] for event in ui.events if event[0] == "read"] == ["room_1_1"]
    assert refresh not in solver.tasks
    assert blocked in solver.tasks and blocked.time == blocked_time
    assert restoration in solver.tasks and restoration.run_order_restore_pending


@pytest.mark.parametrize("panel_open", [False, True])
def test_failed_order_open_yields_to_other_rooms_within_baseline_budget(
    order_navigation, monkeypatch, panel_open
):
    from types import SimpleNamespace

    from arknights_mower.utils import solver as runtime

    ui = order_navigation
    solver = ui.solver
    room, next_room = "room_1_1", "room_2_2"
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=room)
    next_refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=next_room)
    solver.tasks = [refresh, next_refresh]
    ui.states.update({room: "unrecognized", next_room: "active"})
    ui.config.conf.selection_transition_timeout = 6.0
    started_at = ui.clock.now()
    original_time = refresh.time

    def elapsed():
        return (ui.clock.now() - started_at).total_seconds()

    def sleep(seconds):
        ui.clock.current += timedelta(seconds=seconds)

    previous_find = solver.find
    taps = []
    close_panel = (1400, 200)
    open_orders = (96, 1026)

    def find(resource, *args):
        if (
            panel_open
            and solver._page["room"] == room
            and resource == "arrange_check_in_on"
            and ((room, close_panel) not in taps or elapsed() < 2)
        ):
            return close_panel
        return previous_find(resource)

    def tap(point):
        tapped_room = solver._page["room"]
        taps.append((tapped_room, point))
        if tapped_room == next_room and point == open_orders:
            solver._page["open"] = True

    monkeypatch.setattr(ui.base, "monotonic", elapsed)
    monkeypatch.setattr(runtime, "time", SimpleNamespace(monotonic=elapsed))
    monkeypatch.setattr(runtime, "csleep", sleep)
    solver.recog.find = find
    solver.device = SimpleNamespace(tap=tap)
    solver.find = runtime.BaseSolver.find.__get__(solver)
    solver.tap = runtime.BaseSolver.tap.__get__(solver)
    solver.sleep = runtime.BaseSolver.sleep.__get__(solver)

    solver._read_pending_order_times(room)

    assert any(task is refresh for task in solver.tasks)
    assert refresh.time == original_time
    assert refresh.execution_failure["reason"] == "未成功进入订单或制造详情界面"
    ((observed_room, observed_at),) = [
        event[1:] for event in ui.events if event[0] == "read"
    ]
    assert observed_room == next_room
    # 6 秒基线失败预算另加下一间房首次点击的 0.2 秒。
    assert (observed_at - started_at).total_seconds() <= 6.2
    failed_taps = [point for tapped_room, point in taps if tapped_room == room]
    assert failed_taps[0] == (close_panel if panel_open else open_orders)
    assert failed_taps.count(open_orders) >= 2
    assert [point for tapped_room, point in taps if tapped_room == next_room] == [
        open_orders
    ]
    assert all(task is not next_refresh for task in solver.tasks)
    assert any(
        task.type == ui.task_type.RUN_ORDER and task.meta_data == next_room
        for task in solver.tasks
    )


@pytest.mark.parametrize("next_room", ["room_2_2", "dormitory_1"])
@pytest.mark.parametrize("failed_stage", ["countdown", "return_to_map"])
def test_failed_final_order_read_restores_navigation_before_next_task(
    order_navigation, monkeypatch, next_room, failed_stage
):
    from arknights_mower.solvers import base_mixin

    ui = order_navigation
    solver = ui.solver
    page = solver._page
    scene = ui.base.Scene
    marker = ((100, 100), (200, 200))
    refresh = ui.task(
        task_type=ui.task_type.REFRESH_TIME,
        meta_data="room_1_1",
    )
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={},
    )
    solver.tasks = [arrangement, refresh]
    solver.task = arrangement
    solver.op_data.products["room_2_2"] = "orundum"
    solver.op_data.refresh_run_order_rooms()
    ui.states["room_1_1"] = "active"
    original_time = refresh.time
    if failed_stage == "countdown":
        solver.read_time.side_effect = ui.base.RecognizeError("订单数字未确认")
    else:
        working_back = solver.back
        solver.back = MagicMock()
        started_at = ui.clock.now()
        monkeypatch.setattr(
            ui.base, "monotonic", lambda: (ui.clock.now() - started_at).total_seconds()
        )

    def return_to_base(*args, **kwargs):
        page.update(room=None, open=False)

    solver.back_to_infrastructure = MagicMock(side_effect=return_to_base)
    solver.back_to_index = MagicMock(side_effect=return_to_base)

    solver._read_arrangement_order_times("room_1_1")

    assert refresh.execution_failure
    assert refresh.time == original_time
    if failed_stage == "return_to_map":
        assert "返回键未生效" in refresh.execution_failure["reason"]
        assert solver.back.call_count == 2
        solver.read_time.assert_called_once()
        solver.recog.update = MagicMock()
        with pytest.raises(ui.base.OrderReturnUnresolved):
            solver.transition()
        assert solver.back.call_count == 3
        solver.back_to_infrastructure.assert_not_called()
        assert page == {"room": "room_1_1", "open": True}
        solver.back.side_effect = working_back
        ui.base.BaseSchedulerSolver.scene_graph_navigation(solver, scene.INFRA_MAIN)
        assert solver.back.call_count == 5  # 订单页和房间各返回一次。
        assert page == {"room": None, "open": False}
        solver._read_pending_order_times()
        solver.read_time.assert_called_once()
        assert refresh.execution_failure and refresh.time == original_time
    assert arrangement.plan == {}
    assert arrangement in solver.tasks and refresh in solver.tasks

    def find(resource, *args, **kwargs):
        if resource == "control_central" and page["room"] is None:
            return marker
        return None

    def current_scene():
        if page["open"]:
            return scene.ORDER_LIST
        return scene.INFRA_MAIN if page["room"] is None else scene.INFRA_DETAILS

    def enter_target(*args, **kwargs):
        page.update(room=next_room, open=False)

    monkeypatch.setattr(
        base_mixin.segment,
        "base",
        lambda *args, **kwargs: {next_room: marker},
    )
    solver.find = MagicMock(side_effect=find)
    solver.scene = MagicMock(side_effect=current_scene)
    solver.detect_room = MagicMock(side_effect=lambda: page["room"])
    solver.adjust_room = MagicMock(return_value=marker)
    solver.tap = MagicMock(side_effect=enter_target)
    solver.sleep.reset_mock()
    entered_at = ui.clock.now()

    base_mixin.BaseMixin.enter_room(solver, next_room)

    assert page == {"room": next_room, "open": False}
    assert ui.clock.now() == entered_at
    solver.back_to_index.assert_not_called()
    solver.sleep.assert_not_called()


@pytest.mark.parametrize(
    "readback",
    [
        "trade",
        "other_room",
        "other_type",
        "order_marker",
        "no_arrow",
        "cancel_dialog",
        "late_arrow",
        "dropped_arrow",
    ],
)
def test_exhausted_trade_room_return_checks_room_and_uses_one_visible_arrow(
    order_navigation, monkeypatch, readback
):
    ui = order_navigation
    solver, scene = ui.solver, ui.base.Scene
    room = "room_1_1"
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=room)
    solver.tasks = [refresh]
    original_time = refresh.time
    ui.states[room] = "active"
    working_back = solver.back

    def stuck_in_room(**kwargs):
        if solver._page["open"]:
            working_back(**kwargs)

    solver.back = MagicMock(side_effect=stuck_in_room)
    monkeypatch.setattr(ui.base, "monotonic", lambda: ui.clock.now().timestamp())
    solver._read_pending_order_times()
    assert refresh.execution_failure and solver._page == {"room": room, "open": False}
    assert solver.back.call_count == 3
    old_actions = solver.tap.call_count
    arrow = ((20, 15), (380, 95))
    updates = []
    solver.recog.update = lambda: updates.append(True)
    advance = solver.sleep.side_effect

    def next_frame(interval):
        advance(interval)
        solver.recog.update()

    solver.sleep.side_effect = next_frame
    solver.detect_room = MagicMock(
        return_value="room_1_2" if readback == "other_room" else room
    )
    solver.detect_room_type = MagicMock(
        return_value="制造站" if readback == "other_type" else "贸易站"
    )
    if readback == "cancel_dialog":
        solver.scene.side_effect = lambda: scene.INFRA_ARRANGE_CONFIRM

    def find(name):
        if name == "order_label":
            return readback == "order_marker"
        if (
            name == "nav_button"
            and readback != "no_arrow"
            and (readback != "late_arrow" or len(updates) >= 3)
        ):
            return arrow

    solver.find.side_effect = find

    def tap(scope, *, x_rate, interval):
        assert len(updates) >= 2 and scope == arrow and x_rate == 0.08
        if readback != "dropped_arrow":
            solver._page.update(room=None, open=False)

    solver.tap.side_effect = tap
    if readback in ("trade", "late_arrow"):
        solver.transition()
        assert solver._page == {"room": None, "open": False}
        assert solver.tap.call_count == old_actions + 1
    else:
        with pytest.raises(ui.base.OrderReturnUnresolved):
            solver.transition()
        assert solver.tap.call_count == old_actions + int(readback == "dropped_arrow")
    assert 1 <= len(updates) <= solver.performance_profile.transition_attempts + 1
    assert solver.back.call_count == 3
    solver.read_time.assert_called_once()
    assert solver.tasks == [refresh] and refresh.time == original_time


@pytest.mark.parametrize("new_scene", ["INDEX", "LOGIN_MAIN", "CONNECTING"])
def test_exhausted_trade_view_resumes_navigation_after_reconnection(
    order_navigation, new_scene, monkeypatch
):
    ui = order_navigation
    solver, scene = ui.solver, ui.base.Scene
    scope = {"page": getattr(scene, new_scene)}
    solver._order_return_unresolved = scene.INFRA_DETAILS
    solver._order_return_room = "room_1_1"
    solver.recog.update = MagicMock()
    solver.scene.side_effect = lambda: scope["page"]
    solver.waiting_scene = [scene.CONNECTING]
    solver.waiting_solver = MagicMock(
        side_effect=lambda: scope.update(page=scene.INDEX) or True
    )
    solver.login = MagicMock(side_effect=lambda: scope.update(page=scene.INDEX))
    solver.tap_index_element = MagicMock(
        side_effect=lambda _: scope.update(page=scene.INFRA_MAIN)
    )
    monkeypatch.setattr(ui.base, "monotonic", lambda: ui.clock.now().timestamp())
    solver.transition()
    assert scope["page"] == scene.INFRA_MAIN
    assert solver.login.call_count == int(new_scene == "LOGIN_MAIN")
    assert solver.waiting_solver.call_count == int(new_scene == "CONNECTING")
    solver.tap_index_element.assert_called_once_with("infrastructure")
    solver.read_time.assert_not_called()
    solver.back.assert_not_called()
    solver.tap_confirm.assert_not_called()
    assert "_order_return_unresolved" not in vars(solver)


@pytest.mark.parametrize("initial", ["ORDER_LIST", "INFRA_ARRANGE_CONFIRM"])
def test_exhausted_order_navigation_checks_the_frame_before_input(
    order_navigation, monkeypatch, initial
):
    ui = order_navigation
    solver, scene = ui.solver, ui.base.Scene
    refresh = ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data="room_1_1")
    solver.tasks = [refresh]
    original_time = refresh.time
    ui.states["room_1_1"] = "active"
    frame = getattr(scene, initial)

    def countdown(*args, **kwargs):
        solver.scene.side_effect = lambda: frame
        solver.tap = MagicMock()
        return 3600

    def fresh_frame():
        nonlocal frame
        if initial == "ORDER_LIST":
            frame = scene.UNKNOWN

    solver.read_time.side_effect = countdown
    solver.back = MagicMock()
    solver.recog.update = fresh_frame
    monkeypatch.setattr(ui.base, "monotonic", lambda: ui.clock.now().timestamp())
    solver._read_pending_order_times()
    assert refresh.execution_failure
    if initial == "ORDER_LIST":
        solver.tap.assert_not_called()
        assert solver.back.call_count == 2
    else:
        solver.back.assert_not_called()
        assert solver.tap.call_args_list
        assert all(call.args == ((640, 1070),) for call in solver.tap.call_args_list)

    solver.tap.reset_mock()
    solver.back.reset_mock()
    for _ in range(2):
        with pytest.raises(ui.base.OrderReturnUnresolved):
            solver.transition()
    solver.tap.assert_not_called()
    solver.back.assert_not_called()
    solver.tap_confirm.assert_not_called()
    solver.read_time.assert_called_once()
    assert solver.tasks == [refresh] and refresh.time == original_time


@pytest.mark.parametrize(
    "error_name", ["DeviceRecoveryError", "SharedADBError", "MowerExit"]
)
def test_failed_final_read_propagates_navigation_recovery_failure(
    order_navigation, error_name
):
    ui = order_navigation
    solver = ui.solver
    refresh = ui.task(
        task_type=ui.task_type.REFRESH_TIME,
        meta_data="room_1_1",
    )
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={},
    )
    solver.tasks = [arrangement, refresh]
    solver.task = arrangement
    solver.op_data.products["room_2_2"] = "orundum"
    solver.op_data.refresh_run_order_rooms()
    ui.states["room_1_1"] = "active"
    solver.read_time.side_effect = ui.base.RecognizeError("订单数字未确认")
    failure = getattr(ui.base, error_name)("导航恢复中断")
    solver.back_to_infrastructure = MagicMock(side_effect=failure)

    with pytest.raises(type(failure)) as caught:
        solver._read_arrangement_order_times("room_1_1")

    assert caught.value is failure
    assert refresh.execution_failure["reason"] == "订单数字未确认"
    assert solver.tasks == [arrangement, refresh]
    assert arrangement.plan == {}
    solver.back_to_infrastructure.assert_called_once_with()


def test_restoration_with_old_room_metadata_does_not_interrupt_order_refreshes(
    order_navigation,
):
    from arknights_mower.utils.plan import Room

    ui = order_navigation
    solver = ui.solver
    solver.op_data.plan["room_3_3"] = [Room("孑", "", ["佩佩"])]
    solver.op_data.products["room_3_3"] = "lmd"
    solver.op_data.refresh_run_order_rooms()
    ui.states.update({"room_2_2": "active", "room_3_3": "active"})
    ui.deadlines["room_3_3"] = ui.clock.now() + timedelta(hours=4)
    arrangement = ui.task(
        task_type=ui.task_type.SELF_CORRECTION,
        task_plan={"dormitory_1": ["Current"]},
    )
    restoration = ui.task(
        task_type=ui.task_type.RUN_ORDER,
        task_plan={"room_1_1": ["鸿雪"]},
        meta_data="room_1_1",
    )
    restoration.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    restoration.run_order_restore_pending = True
    original_restoration = copy.deepcopy(vars(restoration))
    refreshes = [
        ui.task(task_type=ui.task_type.REFRESH_TIME, meta_data=room)
        for room in ("room_2_2", "room_3_3")
    ]
    solver.task = arrangement
    solver.tasks = [arrangement, restoration, *refreshes]

    solver._read_arrangement_order_times("room_2_2")

    assert not any(event[0] == "read" for event in ui.events)
    assert all(refresh in solver.tasks for refresh in refreshes)
    assert [task for task in solver.tasks if task.type == ui.task_type.RUN_ORDER] == [
        restoration
    ]
    assert arrangement.plan == {"dormitory_1": ["Current"]}
    arrangement.plan.clear()
    solver._read_arrangement_order_times("room_2_2")
    assert all(refresh not in solver.tasks for refresh in refreshes)
    orders = {
        task.meta_data: task
        for task in solver.tasks
        if task.type == ui.task_type.RUN_ORDER
    }
    assert set(orders) == {"room_1_1", "room_2_2", "room_3_3"}
    assert orders["room_1_1"] is restoration
    assert vars(restoration) == original_restoration
    for room in ("room_2_2", "room_3_3"):
        assert orders[room].time == ui.deadlines[room] - timedelta(minutes=3)
    assert arrangement.plan == {}
    solver.choose_agent.assert_not_called()
