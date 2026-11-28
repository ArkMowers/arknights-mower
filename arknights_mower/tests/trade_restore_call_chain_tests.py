"""当轮跑单通过真实选人、确认及房间复核完成原班恢复。"""

from datetime import datetime
from unittest.mock import Mock

import cv2
import pytest

from arknights_mower.tests.trade_restore_selection_tests import (
    FIXTURES,
    INSERTED,
    ORIGINAL,
    ROOM,
    restoration_solver,
)
from arknights_mower.tests.trade_restore_selection_tests import (
    selection_modules as selection_modules,
)


def run_order_screen(
    monkeypatch, selection_modules, mode, *, readback_works=True, inherited_order=None
):
    _, schedule = selection_modules
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import Operator
    from arknights_mower.utils.plan import Room
    from arknights_mower.utils.recognize import RecognizeError, Recognizer, Scene

    solver, task, selected, screen, events = restoration_solver(
        monkeypatch,
        selection_modules,
        mode,
        miss_cancel=False,
        inherited_order=inherited_order,
    )
    original_time = task.time

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return original_time

    monkeypatch.setattr(schedule, "datetime", FixedClock)
    monkeypatch.setattr(schedule, "save_exception", Mock())
    config.conf.run_order_grandet_mode.enable = True
    config.conf.run_order_grandet_mode.buffer_time = 1
    task.plan = {ROOM: INSERTED.copy()}
    task.meta_data = ROOM
    task.adjusted = False
    del task.run_order_restore_pending
    del task.run_order_original_roster
    solver.tasks = [task]
    solver.waiting_scene = []
    solver._can_refresh_idle_dorm_search = Mock(return_value=False)
    solver.drone_room = "room_9_9"
    solver.drone = Mock(side_effect=AssertionError("普通跑单不应改用无人机"))
    solver.get_order_remaining_time = Mock(
        side_effect=[config.conf.run_order_delay * 60, 20]
    )
    solver.op_data.plan[ROOM] = [Room(name, "", []) for name in ORIGINAL]
    for name in dict.fromkeys(ORIGINAL + INSERTED):
        solver.op_data.add(Operator(name, ""))
    cached = ORIGINAL.copy()
    occupants = ORIGINAL.copy()
    selected[:] = ORIGINAL
    screen["cleared"] = True
    screen["cards"] = ORIGINAL + [
        name for name in screen["cards"] if name not in ORIGINAL
    ]
    if inherited_order:
        front = ORIGINAL + ["龙舌兰", "但书"]
        screen["cards"] = front + [
            name for name in screen["cards"] if name not in front
        ]
    phase = {"page": "details", "restoring": False}
    confirmations = []
    observed = []
    capture = solver.recog.update.side_effect
    select = solver.tap.side_effect
    device = Mock()
    device.screencap.side_effect = AssertionError("原图回归不能读取真实设备")
    recognizer = Recognizer(
        device, (FIXTURES / "trade_restore_before_20261029.jpg").read_bytes()
    )

    def synchronize():
        for op in solver.op_data.operators.values():
            op._current_room, op.current_index = "", -1
        for index, name in enumerate(cached):
            op = solver.op_data.operators[name]
            op._current_room, op.current_index = ROOM, index

    synchronize()
    solver.op_data.get_current_room = lambda *args: cached.copy()

    def enter(*args, **kwargs):
        phase["page"] = "details"
        events.append(("enter", ROOM))

    def find(name, *args, **kwargs):
        if phase["page"] == "selection" and not screen["cleared"]:
            # 故障阶段保留原图并执行真实模板识别，包括完整重选前的页面安全检查。
            if recognizer._img is not solver.recog.img:
                recognizer._img = solver.recog.img
                recognizer._gray = cv2.cvtColor(solver.recog.img, cv2.COLOR_RGB2GRAY)
                recognizer._matcher = None
            return recognizer.find(name, *args, **kwargs)
        if name == "confirm_blue" and phase["page"] == "selection":
            return ((1724, 990), (1813, 1041))
        if name == "room_detail" and phase["page"] == "details":
            return ((1272, 0), (1678, 101))
        return None

    def tap(point, **kwargs):
        if phase["page"] == "details":
            phase["page"] = "selection"
            events.append(("open_selection", ROOM))
            capture()
            return
        if isinstance(point[0], (tuple, list)) and tuple(map(tuple, point)) == (
            (1724, 990),
            (1813, 1041),
        ):
            assert task.run_order_restore_pending
            assert task.run_order_original_roster == {ROOM: ORIGINAL}
            expected = ORIGINAL if phase["restoring"] else INSERTED
            assert selected == expected, "只能确认已完成真实选人校验的目标名单"
            confirmations.append(selected.copy())
            events.append(("confirm", tuple(selected)))
            occupants[:] = selected
            phase["page"] = "details"
            return
        if phase["restoring"] and not screen["missed"]:
            page = selection_modules[0].operator_list(solver.recog.img)
            positions = [(672, 378), (672, 810), (864, 378)]
            name = None
            if isinstance(point[0], tuple):
                name = next((name for name, scope in page if scope == point), None)
            elif tuple(point) in positions:
                name = page[positions.index(tuple(point))][0]
            if name == "龙舌兰":
                screen["missed"] = True
                events.append(("cancel_missed", name))
                capture()
                return
        select(point, **kwargs)

    def read(room, *args, **kwargs):
        assert room == ROOM
        assert phase["page"] == "details"
        if confirmations:
            assert task.run_order_restore_pending
            assert task.run_order_original_roster == {ROOM: ORIGINAL}
        observed.append(occupants.copy())
        events.append(("readback", tuple(occupants)))
        if phase["restoring"] and confirmations[-1:] == [ORIGINAL]:
            if not readback_works:
                raise RecognizeError("恢复后的房间驻员读取失败")
        cached[:] = occupants
        synchronize()
        return [{"agent": name} for name in occupants]

    def collect_order():
        assert confirmations == [INSERTED]
        assert cached == INSERTED
        assert task.run_order_restore_pending
        assert task.run_order_original_roster == {ROOM: ORIGINAL}
        phase["restoring"] = True
        screen.update(cleared=False, missed=False, page="first")
        events.append(("order_collected",))
        capture()

    solver.enter_room = Mock(side_effect=enter)
    solver.turn_on_room_detail = Mock(side_effect=enter)
    solver.detect_room = Mock(
        side_effect=lambda: ROOM if phase["page"] == "details" else ""
    )
    solver.find = Mock(side_effect=find)
    solver.scene = Mock(
        side_effect=lambda: {
            "selection": Scene.INFRA_ARRANGE_ORDER,
            "details": Scene.INFRA_DETAILS,
            "map": Scene.INFRA_MAIN,
        }[phase["page"]]
    )
    solver.tap = Mock(side_effect=tap)
    solver.back = Mock(side_effect=lambda *args, **kwargs: phase.update(page="map"))
    solver.get_agent_from_room = Mock(side_effect=read)
    solver.accept_order = Mock(side_effect=collect_order)
    capture()
    return solver, task, original_time, confirmations, observed, events


@pytest.mark.parametrize("mode", ["xhigh", "high", "medium", "low"])
def test_current_run_restores_real_roster_before_confirm_and_readback(
    monkeypatch, selection_modules, mode
):
    solver, task, original_time, confirmed, observed, events = run_order_screen(
        monkeypatch, selection_modules, mode
    )

    solver.agent_arrange(task.plan)

    assert confirmed == [INSERTED, ORIGINAL]
    collect = events.index(("order_collected",))
    restore_confirm = events.index(("confirm", tuple(ORIGINAL)))
    restoration = events[collect:restore_confirm]
    assert ("archive", "wrong_roster") in restoration
    assert ("capacity_full", "蕾缪安") in restoration
    assert ("clear",) in restoration
    assert observed[0] == observed[-1] == ORIGINAL
    assert INSERTED in observed[1:-1]
    assert solver.task is task and task.time == original_time
    assert task.plan == {}
    assert not hasattr(task, "run_order_restore_pending")
    assert not hasattr(task, "run_order_original_roster")


def test_current_restore_readback_failure_retains_original_task(
    monkeypatch, selection_modules
):
    from arknights_mower.utils.recognize import RecognizeError

    solver, task, original_time, confirmed, _, events = run_order_screen(
        monkeypatch, selection_modules, "high", readback_works=False
    )

    with pytest.raises(RecognizeError, match="恢复后的房间驻员读取失败"):
        solver.agent_arrange(task.plan)

    assert confirmed == [INSERTED, ORIGINAL]
    assert ("archive", "wrong_roster") in events
    assert solver.task is task and task in solver.tasks
    assert task.time == original_time
    assert task.plan == task.run_order_original_roster == {ROOM: ORIGINAL}
    assert task.run_order_restore_pending
    assert task.meta_data == ""


@pytest.mark.parametrize(
    "mode, inherited_order",
    [
        ("low", ("技能", True)),
        ("high", ("心情", False)),
        ("high", ("效率", True)),
        ("medium", ("工作状态", False)),
    ],
)
def test_mixed_visible_professions_keep_inherited_order_and_request_slot_order(
    monkeypatch, selection_modules, mode, inherited_order
):
    solver, task, _, confirmed, observed, events = run_order_screen(
        monkeypatch, selection_modules, mode, inherited_order=inherited_order
    )
    assert (
        selection_modules[0].BaseMixin.detect_arrange_order(solver, ROOM)
        == inherited_order
    )

    solver.agent_arrange(task.plan)

    first_confirm = events.index(("confirm", tuple(INSERTED)))
    entry = events[events.index(("open_selection", ROOM)) + 1 : first_confirm]
    assert [event[1] for event in entry if event[0] == "select"] == [
        "但书",
        "龙舌兰",
    ]
    assert not any(e[0] in ("clear", "sort") for e in entry), entry
    assert confirmed == [INSERTED, ORIGINAL]
    assert INSERTED in observed and observed[-1] == ORIGINAL
    assert task.plan == {}


def test_inherited_and_configured_trust_switch_before_deselecting_residents(
    monkeypatch, selection_modules
):
    solver, task, _, confirmed, _, events = run_order_screen(
        monkeypatch, selection_modules, "high"
    )
    solver.get_order.return_value = False, ("信赖值", True)
    order = ("信赖值", True)
    solver.detect_arrange_order.side_effect = lambda room: order
    sort = solver.switch_arrange_order.side_effect

    def change_order(criterion, room, ascending=False, **kwargs):
        nonlocal order
        assert criterion != "信赖值"
        order = criterion, ascending
        return sort(criterion, room, ascending, **kwargs)

    solver.switch_arrange_order.side_effect = change_order
    solver.agent_arrange(task.plan)
    entry = events.index(("open_selection", ROOM))
    actions = [
        e for e in events[entry:] if e[0] in ("sort", "select", "cancel", "clear")
    ]
    assert actions[0] == ("sort", "工作状态")
    assert confirmed == [INSERTED, ORIGINAL]


@pytest.mark.parametrize("case", ["short", "unresolved_free", "empty_tail"])
def test_ordinary_retry_confirms_all_three_positions(
    monkeypatch, selection_modules, case
):
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver, task, original_time, _, _, _ = run_order_screen(
        monkeypatch, selection_modules, "high"
    )
    target = (
        ORIGINAL[:2]
        if case != "unresolved_free"
        else [ORIGINAL[0], "Free", ORIGINAL[2]]
    )
    occupants = [*ORIGINAL[:2], ""] if case == "empty_tail" else ORIGINAL.copy()
    if case == "unresolved_free":
        occupants[1] = ""
    task.type = TaskTypes.SELF_CORRECTION
    task.arrangement_retry_room, task.arrangement_retry_count = ROOM, 1
    task.plan = {ROOM: target}
    solver.op_data.get_current_room = lambda *args, **kwargs: occupants.copy()
    solver.get_agent_from_room.side_effect = lambda *args, **kwargs: [
        {"agent": name} for name in occupants
    ]

    def select(names, *args, **kwargs):
        if "Free" in names:
            names[names.index("Free")] = ORIGINAL[1]

    def confirm(*args, **kwargs):
        occupants[:] = target + [""] * (3 - len(target))

    solver.choose_agent = Mock(side_effect=select)
    solver.tap_confirm = Mock(side_effect=confirm)
    solver.agent_arrange_room({}, ROOM, task.plan)

    assert task.time == original_time and not task.plan
    assert occupants == (ORIGINAL if case == "unresolved_free" else [*ORIGINAL[:2], ""])
    assert (
        solver.choose_agent.call_count
        == solver.tap_confirm.call_count
        == int(case != "empty_tail")
    )


@pytest.mark.parametrize("tail", ["still_occupied", "unread", "missing"])
def test_short_ordinary_plan_stays_pending_until_tail_is_confirmed_empty(
    monkeypatch, selection_modules, tail
):
    from arknights_mower.solvers.base_schedule import RoomArrangementDeferred
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver, task, original_time, _, _, _ = run_order_screen(
        monkeypatch, selection_modules, "high"
    )
    target = ORIGINAL[:2]
    task.type = TaskTypes.SELF_CORRECTION
    task.arrangement_retry_room, task.arrangement_retry_count = ROOM, 1
    task.plan = {ROOM: target.copy()}
    rows = [{"agent": name} for name in ORIGINAL]
    if tail == "missing":
        rows.pop()
    elif tail == "unread":
        rows[-1] = {"agent": "", "observed": False}
    solver.get_agent_from_room.side_effect = None
    solver.get_agent_from_room.return_value = rows
    solver.choose_agent = Mock(return_value=True)
    solver.tap_confirm = Mock()
    with pytest.raises(RoomArrangementDeferred):
        solver.agent_arrange_room({}, ROOM, task.plan)

    assert task.plan == {ROOM: target} and task.time == original_time
    if tail == "still_occupied":
        assert 0 < solver.tap_confirm.call_count <= 3
    else:
        solver.tap_confirm.assert_not_called()


@pytest.mark.parametrize("same_room", [False, True])
def test_room_capacity_reaches_selection_only_with_matching_room_title(
    monkeypatch, selection_modules, same_room
):
    import numpy as np

    from arknights_mower.solvers.base_schedule import RoomArrangementDeferred
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.image import loadimg
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver, task, original_time, confirmed, _, events = run_order_screen(
        monkeypatch, selection_modules, "high"
    )
    task.type = TaskTypes.SELF_CORRECTION
    task.plan = {ROOM: INSERTED[:2]}
    bands = loadimg(str(FIXTURES / "manufacturing_capacity.webp"))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[1006:1056, 1650:1920] = bands[77:127, :270]
    solver.recog._img = frame
    solver.detect_room = Mock(return_value=ROOM if same_room else "room_3_2")
    solver.choose_agent = Mock(side_effect=MowerExit)
    if same_room:
        with pytest.raises(MowerExit):
            solver.agent_arrange(task.plan)
        assert solver.choose_agent.call_args.kwargs["two_slot_room"] is True
    else:
        with pytest.raises(RoomArrangementDeferred, match="未确认目标房间"):
            solver.agent_arrange(task.plan)
        assert ("open_selection", ROOM) not in events
        solver.choose_agent.assert_not_called()
        assert not confirmed
        assert task.plan == {ROOM: INSERTED[:2]} and task.time == original_time
