"""跑单确认沿用已绑定的联网补偿，迟到的进驻结果不触发重复提交。"""

import copy
import pickle
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import base_schedule
from arknights_mower.tests.mass_mood_recovery_tests import NOW
from arknights_mower.tests.run_order_restoration_tests import (
    ORIGINAL,
    ROOM,
    prepare_order,
)
from arknights_mower.tests.run_order_restoration_tests import offline as offline
from arknights_mower.tests.run_order_restoration_tests import solver as solver
from arknights_mower.tests.waiting_network_adaptation_tests import waiting as waiting
from arknights_mower.utils import config, run_order_network, scheduler_task
from arknights_mower.utils import solver as solver_utils
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.dorm_candidates import retained_task_reservations
from arknights_mower.utils.network_adaptation import get_network_adaptation
from arknights_mower.utils.recognize import RecognizeError, Scene
from arknights_mower.utils.run_order_network import (
    begin_run_order_network,
    bind_run_order_network,
)


@pytest.fixture
def confirmation(solver, monkeypatch):
    task, place = prepare_order(solver, monkeypatch, buffer=1, adjusted=False)

    class Clock(datetime):
        seconds = 0.0

        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(seconds=cls.seconds)

    state = SimpleNamespace(
        solver=solver,
        task=task,
        clock=Clock,
        page="details",
        selected=None,
        physical=ORIGINAL.copy(),
        apply_after=2.4,
        apply_at=None,
        pending_target=None,
        close_on_apply=False,
        hide_after_first_click=False,
        clicks=[],
        click_states=[],
        saved_states=[],
        saved_before_first_click=None,
        reads=[],
        sleeps=[],
        first_submission=None,
        cancel_at=None,
        read_error=None,
        read_transform=None,
    )
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "monotonic", lambda: Clock.seconds)
    monkeypatch.setattr(
        solver_utils, "time", SimpleNamespace(monotonic=lambda: Clock.seconds)
    )
    monkeypatch.setattr(run_order_network, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(
        base_schedule,
        "save_current_state",
        MagicMock(
            side_effect=lambda: (
                state.saved_states.append(
                    copy.deepcopy(getattr(task, "run_order_confirmation_pending", None))
                )
                or True
            )
        ),
    )
    monkeypatch.setattr(base_schedule, "save_exception", MagicMock())
    monkeypatch.setattr(config, "screenshot_avg", 0)
    config.conf.run_order_network_adaptive = True
    config.conf.selection_poll_interval = 0.1
    solver._selection_profile_snapshot = SimpleNamespace(
        mode="xhigh",
        low_frame_rate=False,
        transition_timeout=2.5,
        screenshot_interval=100,
        poll_interval=0.1,
    )
    get_network_adaptation(solver.recog).record(
        "CONNECTING",
        elapsed_seconds=3,
        base_seconds=30,
        observed_at=Clock.now(),
    )
    bind_run_order_network([task], solver.recog, config.conf, Clock.now())
    begin_run_order_network(task, solver.recog, config.conf, Clock.now())
    task.execution_retained = True
    solver.get_order_remaining_time.return_value = 4
    solver.op_data.run_order_rooms[ROOM] = ["但书"]

    def update():
        if state.apply_at is not None and Clock.seconds >= state.apply_at:
            state.physical = state.pending_target.copy()
            state.pending_target = None
            state.apply_at = None
            if state.close_on_apply:
                state.page = "details"

    def sleep(interval=1):
        state.sleeps.append(interval)
        Clock.seconds += interval
        assert Clock.seconds < 30, "一次确认和恢复必须在有限时间内结束"
        if state.cancel_at is not None and Clock.seconds >= state.cancel_at:
            raise MowerExit()
        update()

    def find(name, *args, **kwargs):
        update()
        if name == "confirm_blue" and state.clicks and state.hide_after_first_click:
            return None
        visible = {"confirm_blue": "selection", "room_detail": "details"}
        return (1768, 1015) if visible.get(name) == state.page else None

    def select(names, room, **kwargs):
        assert room == ROOM and state.page == "selection"
        state.selected = names.copy()

    def tap(position, *args, **kwargs):
        if state.page == "details":
            state.page = "selection"
        else:
            assert state.page == "selection"
            assert position == (1768, 1015)
            state.clicks.append((Clock.seconds, state.selected.copy()))
            state.click_states.append(
                copy.deepcopy(getattr(task, "run_order_confirmation_pending", None))
            )
            if state.first_submission is None:
                state.saved_before_first_click = copy.deepcopy(state.saved_states)
                state.first_submission = Clock.seconds
            if state.pending_target is None:
                state.pending_target = state.selected.copy()
                state.apply_at = Clock.seconds + state.apply_after
        sleep(kwargs.get("interval", 1))

    def back(*args, **kwargs):
        state.page = "details" if state.page == "selection" else "map"
        sleep(kwargs.get("interval", args[0] if args else 1))

    def observe(room, *args, **kwargs):
        assert room == ROOM and state.page == "details"
        update()
        if state.first_submission is not None and state.read_error is not None:
            raise state.read_error
        state.reads.append((Clock.seconds, state.physical.copy()))
        place(state.physical)
        rows = [{"agent": name} for name in state.physical]
        return (
            state.read_transform(rows)
            if state.first_submission is not None and state.read_transform
            else rows
        )

    solver.recog.update.side_effect = update
    solver.scene.side_effect = lambda: (
        Scene.INFRA_MAIN
        if state.page == "map"
        else Scene.INFRA_ARRANGE
        if state.page == "selection"
        else Scene.INFRA_DETAILS
    )
    solver.find.side_effect = find
    solver.enter_room.side_effect = lambda room: setattr(state, "page", "details")
    solver.turn_on_room_detail.side_effect = lambda room: setattr(
        state, "page", "details"
    )
    solver.back.side_effect = back
    solver.sleep.side_effect = sleep
    solver.tap.side_effect = tap
    solver.choose_agent.side_effect = select
    solver.get_agent_from_room.side_effect = observe
    solver.tap_confirm = base_schedule.BaseSchedulerSolver.tap_confirm.__get__(solver)
    return state


@pytest.mark.parametrize("button", ["visible", "missing"])
def test_stuck_confirmation_reads_late_target_without_more_clicks(confirmation, button):
    ui = confirmation
    ui.hide_after_first_click = button == "missing"
    ui.apply_after = 3 if ui.hide_after_first_click else 2.4
    expected = ui.task.plan[ROOM].copy()

    ui.solver.agent_arrange_room({}, ROOM, ui.task.plan)

    assert ui.task.plan == {}
    assert ui.physical == expected
    assert len(ui.clicks) <= 4
    assert ui.solver.choose_agent.call_count == 1
    if button == "visible":
        assert any(at > ui.first_submission and row == ORIGINAL for at, row in ui.reads)
    else:
        assert ui.clock.seconds - ui.first_submission <= 2.4 + 3 + 0.2 + 1e-6
        deadlines = {
            pending["expires_at"]
            for pending in ui.saved_states
            if pending and pending["expires_at"] is not None
        }
        assert len(deadlines) == 1
    assert ui.reads[-1][1] == expected
    assert not getattr(ui.task, "run_order_confirmation_pending", None)


def test_insertion_and_restoration_confirm_their_own_target_rosters(confirmation):
    ui = confirmation
    inserted = ui.task.plan[ROOM].copy()
    original_time = ui.task.time

    ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.time == original_time
    assert ui.task.plan == {}
    assert ui.physical == ORIGINAL
    assert ui.solver.choose_agent.call_count == 2
    assert 1 <= sum(row == inserted for _, row in ui.clicks) <= 4
    assert 1 <= sum(row == ORIGINAL for _, row in ui.clicks) <= 4
    assert all(
        pending["restoring"] is (row == ORIGINAL)
        for (_, row), pending in zip(ui.clicks, ui.click_states)
    )
    observed = [row for _, row in ui.reads]
    assert observed[0] == observed[-1] == ORIGINAL
    assert inserted in observed
    assert not getattr(ui.task, "run_order_confirmation_pending", None)
    assert not getattr(ui.task, "run_order_restore_pending", False)
    assert not hasattr(ui.task, "run_order_original_roster")
    deadlines = {
        (tuple(pending["target"]), pending["expires_at"])
        for pending in ui.saved_states
        if pending and pending["expires_at"] is not None
    }
    assert len(deadlines) == 2
    assert dict(deadlines)[tuple(inserted)] < dict(deadlines)[tuple(ORIGINAL)]
    ui.solver.accept_order.assert_called_once_with()
    ui.solver.drone.assert_not_called()


def test_normal_confirmed_target_does_not_wait_out_allowance(confirmation):
    ui = confirmation
    ui.apply_after = 0
    ui.close_on_apply = True
    expected = ui.task.plan[ROOM].copy()

    ui.solver.agent_arrange_room({}, ROOM, ui.task.plan)

    assert ui.task.plan == {}
    assert ui.physical == expected
    assert len(ui.clicks) == 1
    assert ui.clock.seconds - ui.first_submission < 1


def test_actual_click_is_preceded_by_saved_submission_responsibility(confirmation):
    ui = confirmation
    ui.apply_after = 0
    ui.close_on_apply = True
    expected = ui.task.plan[ROOM].copy()

    ui.solver.agent_arrange_room({}, ROOM, ui.task.plan)

    submitted = [
        state for state in ui.saved_before_first_click if state and state["submitted"]
    ]
    assert submitted
    assert submitted[0]["target"] == expected
    assert submitted[0]["expires_at"] is None
    assert ui.click_states[0]["submitted"]


@pytest.mark.parametrize("excluded", ["disabled", "unbound", "drone", "grandet_off"])
def test_unprotected_confirmation_preserves_original_retry_limit(
    confirmation, excluded
):
    ui = confirmation
    ui.apply_after = 100
    if excluded == "disabled":
        config.conf.run_order_network_adaptive = False
    elif excluded == "unbound":
        del ui.task.run_order_network_timing
    elif excluded == "drone":
        ui.task.adjusted = True
    else:
        config.conf.run_order_grandet_mode.enable = False

    with pytest.raises(RecognizeError, match="干员确认"):
        ui.solver.agent_arrange_room({}, ROOM, ui.task.plan)

    assert len(ui.clicks) == 4
    assert ui.clock.seconds - ui.first_submission == pytest.approx(1.6)
    assert not getattr(ui.task, "run_order_confirmation_pending", None)


def test_unresolved_original_roster_keeps_task_and_one_deadline(confirmation):
    ui = confirmation
    ui.apply_after = 100
    original_time = ui.task.time

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.solver.task is ui.task and ui.solver.tasks == [ui.task]
    assert ui.task.time == original_time
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert ui.task.run_order_original_roster == {ROOM: ORIGINAL}
    assert ui.task.run_order_restore_pending
    pending = copy.deepcopy(ui.task.run_order_confirmation_pending)
    assert pending["target"] != ORIGINAL
    assert pending["submitted"]
    assert pending["expires_at"] <= ui.clock.now()
    assert pending["expires_at"] == NOW + timedelta(
        seconds=ui.first_submission + 1.6 + 3
    )
    restored = pickle.loads(pickle.dumps(ui.task))
    assert type(restored.run_order_confirmation_pending) is dict
    assert restored.run_order_confirmation_pending == pending
    assert len(ui.clicks) == 4
    assert ui.solver.choose_agent.call_count == 1
    deadline = pending["expires_at"]

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.run_order_confirmation_pending["expires_at"] == deadline
    assert ui.task.time == original_time
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert len(ui.clicks) == 4


def test_cancellation_keeps_submitted_confirmation_and_original_roster(confirmation):
    ui = confirmation
    ui.apply_after = 100
    ui.cancel_at = 2.3
    original_time = ui.task.time

    with pytest.raises(MowerExit):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.time == original_time
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert ui.task.run_order_original_roster == {ROOM: ORIGINAL}
    assert ui.task.run_order_restore_pending
    assert ui.task.run_order_confirmation_pending["submitted"]
    assert len(ui.clicks) <= 4


def test_reloaded_expired_confirmation_does_not_grant_another_allowance(confirmation):
    ui = confirmation
    ui.apply_after = 100
    original_time = ui.task.time
    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)
    pending = copy.deepcopy(ui.task.run_order_confirmation_pending)
    resumed = pickle.loads(pickle.dumps(ui.task))
    ui.solver.task = resumed
    ui.solver.tasks = [resumed]
    ui.solver.__dict__.pop("_run_order_confirmation_clock", None)
    before = ui.clock.seconds

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(resumed.plan)

    assert resumed.run_order_confirmation_pending == pending
    assert resumed.time == original_time
    assert resumed.plan == {ROOM: ORIGINAL}
    assert ui.clock.seconds == before
    assert len(ui.clicks) == 4
    ui.solver.accept_order.assert_not_called()


@pytest.mark.parametrize("partial", ["missing_slot", "unobserved_slot"])
def test_partial_target_read_does_not_confirm_submission(confirmation, partial):
    ui = confirmation
    if partial == "missing_slot":
        ui.read_transform = lambda rows: rows[:-1]
    else:
        ui.read_transform = lambda rows: [
            {**row, "observed": index != 1} for index, row in enumerate(rows)
        ]

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.run_order_confirmation_pending["submitted"]
    assert ui.task.run_order_confirmation_pending["exhausted"]
    assert ui.task.run_order_restore_pending
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert len(ui.clicks) <= 4
    ui.solver.accept_order.assert_not_called()


def test_read_failure_preserves_submitted_target_and_original_roster(confirmation):
    ui = confirmation
    ui.read_error = RuntimeError("实读驻员失败")
    original_time = ui.task.time

    with pytest.raises(RuntimeError, match="实读驻员失败"):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.time == original_time
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert ui.task.run_order_original_roster == {ROOM: ORIGINAL}
    assert ui.task.run_order_restore_pending
    assert ui.task.run_order_confirmation_pending["submitted"]
    assert ui.task.run_order_confirmation_pending["expires_at"] is not None
    assert len(ui.clicks) == 4
    ui.solver.accept_order.assert_not_called()


def test_failed_submission_checkpoint_prevents_the_actual_click(
    confirmation, monkeypatch
):
    ui = confirmation
    monkeypatch.setattr(
        base_schedule, "save_current_state", MagicMock(return_value=False)
    )

    with pytest.raises(RecognizeError, match="无法保存干员确认提交状态"):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.clicks == []
    assert not getattr(ui.task, "run_order_confirmation_pending", {}).get("submitted")
    assert ui.task.run_order_restore_pending
    assert ui.task.plan == {ROOM: ORIGINAL}


def test_raising_submission_checkpoint_prevents_the_actual_click(
    confirmation, monkeypatch
):
    ui = confirmation
    monkeypatch.setattr(
        base_schedule,
        "save_current_state",
        MagicMock(side_effect=OSError("存档写入失败")),
    )

    with pytest.raises(OSError, match="存档写入失败"):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.clicks == []
    assert not getattr(ui.task, "run_order_confirmation_pending", {}).get("submitted")
    assert ui.task.run_order_restore_pending
    assert ui.task.plan == {ROOM: ORIGINAL}


def test_failed_deadline_checkpoint_keeps_the_submitted_responsibility(
    confirmation, monkeypatch
):
    ui = confirmation
    monkeypatch.setattr(
        base_schedule,
        "save_current_state",
        lambda: ui.task.run_order_confirmation_pending["expires_at"] is None,
    )

    with pytest.raises(RecognizeError, match="无法保存干员确认观察期限"):
        ui.solver.agent_arrange(ui.task.plan)

    assert len(ui.clicks) == 4
    assert ui.task.run_order_confirmation_pending["submitted"]
    assert ui.task.run_order_confirmation_pending["expires_at"] is not None
    assert ui.task.run_order_restore_pending
    assert ui.task.plan == {ROOM: ORIGINAL}


def test_failed_deadline_checkpoint_cannot_be_bypassed_on_reentry(
    confirmation, monkeypatch
):
    ui = confirmation
    ui.apply_after = 100
    monkeypatch.setattr(
        base_schedule,
        "save_current_state",
        lambda: ui.task.run_order_confirmation_pending["expires_at"] is None,
    )
    with pytest.raises(RecognizeError, match="无法保存干员确认观察期限"):
        ui.solver.agent_arrange(ui.task.plan)
    pending = copy.deepcopy(ui.task.run_order_confirmation_pending)
    original_time = ui.task.time
    before = ui.clock.seconds
    monkeypatch.setattr(
        base_schedule, "save_current_state", MagicMock(return_value=True)
    )

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.run_order_confirmation_pending == pending
    assert ui.task.run_order_confirmation_pending["exhausted"]
    assert ui.clock.seconds == before
    assert ui.task.time == original_time
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert ui.task.run_order_restore_pending
    assert len(ui.clicks) == 4


def test_current_slot_target_is_fixed_before_late_roster_observations(confirmation):
    ui = confirmation
    ui.task.plan[ROOM] = ["但书", "Current"]
    expected = ["但书", ORIGINAL[1]]
    changed_original = [ORIGINAL[0], "斥罪"]
    original_tap = ui.solver.tap.side_effect

    def tap(*args, **kwargs):
        previously_unsubmitted = ui.first_submission is None
        result = original_tap(*args, **kwargs)
        if previously_unsubmitted and ui.first_submission is not None:
            ui.physical = changed_original.copy()
        return result

    ui.solver.tap.side_effect = tap

    ui.solver.agent_arrange_room({}, ROOM, ui.task.plan)

    assert ui.task.plan == {}
    assert ui.physical == expected
    assert all(pending["target"] == expected for pending in ui.click_states)
    assert changed_original in [row for _, row in ui.reads]
    assert ui.task.run_order_original_roster == {ROOM: ORIGINAL}
    assert len(ui.clicks) <= 4


def test_new_timestamp_does_not_release_unresolved_task_but_target_roster_does(
    confirmation,
):
    ui = confirmation
    ui.apply_after = 100
    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)
    ui.solver._retain_failed_task(ui.task, "干员确认结果未决", [ROOM])
    failure = copy.deepcopy(ui.task.execution_failure)
    original_time = ui.task.time
    independent = scheduler_task.SchedulerTask(
        time=ui.clock.now(), task_type=scheduler_task.TaskTypes.DEPOT
    )
    ui.solver.tasks.append(independent)
    for _ in range(3):
        ui.clock.seconds += 60
        for name in ORIGINAL:
            ui.solver.op_data.operators[name].time_stamp = ui.clock.now()
        ui.solver._resume_failed_tasks()
        assert ui.task.execution_failure == failure
        assert ui.task.time == original_time
        assert scheduler_task.find_next_task(ui.solver.tasks) is independent
    ui.physical = ui.task.run_order_confirmation_pending["target"].copy()
    ui.page = "details"
    ui.solver.get_agent_from_room(ROOM)

    ui.solver._resume_failed_tasks()

    assert not getattr(ui.task, "execution_failure", None)
    assert ui.task.time == original_time
    assert ui.task.run_order_confirmation_pending["target"] == ui.physical
    assert len(ui.clicks) == 4


@pytest.mark.parametrize("action", ["sleep", "find", "tap", "back"])
def test_nested_observation_deadline_bounds_real_solver_actions(monkeypatch, action):
    clock = {"seconds": 0.0}
    subject = object.__new__(solver_utils.BaseSolver)
    subject.device = MagicMock()
    subject.recog = SimpleNamespace(
        update=MagicMock(), find=MagicMock(return_value=True)
    )
    monkeypatch.setattr(
        solver_utils, "time", SimpleNamespace(monotonic=lambda: clock["seconds"])
    )
    monkeypatch.setattr(
        solver_utils,
        "csleep",
        lambda seconds: clock.update(seconds=clock["seconds"] + seconds),
    )

    with subject.observation_deadline(2):
        with subject.observation_deadline(10):
            if action == "find":
                assert subject.find("room_detail") is True
                clock["seconds"] = 2
            operation = {
                "sleep": lambda: subject.sleep(10),
                "find": lambda: subject.find("room_detail"),
                "tap": lambda: subject.tap((20, 30), interval=10),
                "back": lambda: subject.back(interval=10),
            }[action]
            with pytest.raises(solver_utils.ObservationTimeout):
                operation()
            with pytest.raises(solver_utils.ObservationTimeout):
                subject.tap((20, 30))
            with pytest.raises(solver_utils.ObservationTimeout):
                subject.back()

    assert clock["seconds"] == 2
    assert "_observation_deadline" not in subject.__dict__
    assert subject.device.tap.call_count == int(action == "tap")
    assert subject.device.send_keyevent.call_count == int(action == "back")
    assert subject.recog.find.call_count == int(action == "find")


def test_nested_network_wait_records_one_bounded_observation_without_restart(
    waiting, monkeypatch
):
    ui = waiting
    advance = ui.solver.sleep
    ui.solver.sleep = solver_utils.BaseSolver.sleep.__get__(ui.solver)
    ui.recog.update = MagicMock()
    monkeypatch.setattr(solver_utils, "csleep", advance)

    with ui.solver.observation_deadline(2.5):
        with pytest.raises(solver_utils.ObservationTimeout):
            ui.solver.waiting_solver()

    assert ui.clock.seconds == 2.5
    assert ui.delays == [1, 1, 0.5]
    observations = get_network_adaptation(ui.recog).observations
    assert len(observations) == 1
    assert observations[0].duration_seconds == 2.5
    assert observations[0].timed_out
    assert "_network_wait_guard" not in ui.recog.__dict__
    assert "_observation_deadline" not in ui.solver.__dict__
    ui.device.exit.assert_not_called()
    ui.solver.check_current_focus.assert_not_called()


def test_nested_room_read_cannot_overrun_confirmation_allowance(
    confirmation, monkeypatch
):
    ui = confirmation
    advance = ui.solver.sleep.side_effect
    read = ui.solver.get_agent_from_room.side_effect
    ui.solver.sleep = solver_utils.BaseSolver.sleep.__get__(ui.solver)
    monkeypatch.setattr(solver_utils, "csleep", advance)

    def delayed_read(*args, **kwargs):
        if ui.first_submission is not None:
            ui.solver.sleep(10)
        return read(*args, **kwargs)

    ui.solver.get_agent_from_room.side_effect = delayed_read

    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.clock.seconds == pytest.approx(ui.first_submission + 1.6 + 3)
    assert ui.task.run_order_confirmation_pending["exhausted"]
    assert ui.task.run_order_restore_pending
    assert ui.task.plan == {ROOM: ORIGINAL}
    assert len(ui.clicks) == 4
    assert "_observation_deadline" not in ui.solver.__dict__


def test_outer_deadline_does_not_shorten_the_next_ordinary_network_wait(
    waiting, monkeypatch
):
    ui = waiting
    advance = ui.solver.sleep
    ui.solver.sleep = solver_utils.BaseSolver.sleep.__get__(ui.solver)
    ui.recog.update = MagicMock()
    monkeypatch.setattr(solver_utils, "csleep", advance)
    with ui.solver.observation_deadline(2.5):
        with pytest.raises(solver_utils.ObservationTimeout):
            ui.solver.waiting_solver()
    ui.scene_at = lambda elapsed: Scene.INDEX if elapsed >= 3.5 else Scene.CONNECTING

    assert ui.solver.waiting_solver() is True

    assert ui.clock.seconds == 3.5
    ui.device.exit.assert_not_called()
    ui.solver.check_current_focus.assert_not_called()


def test_secondary_confirmation_appearing_during_allowance_is_not_cancelled(
    confirmation,
):
    ui = confirmation
    target = ui.task.plan[ROOM].copy()
    ui.solver._prepare_run_order_confirmation(ROOM, target)
    ui.page = "selection"
    clicks = []
    advance = ui.solver.sleep.side_effect

    def find(name, *args, **kwargs):
        if not clicks:
            return (1768, 1015) if name == "confirm_blue" else None
        if len(clicks) == 1:
            return (
                (1250, 800)
                if name == "arrange_confirm" and ui.clock.seconds >= 2.7
                else None
            )
        return (100, 100) if name == "room_detail" else None

    def tap(position, *args, **kwargs):
        clicks.append(position)
        advance(kwargs.get("interval", 1))

    ui.solver.find.side_effect = find
    ui.solver.tap.side_effect = tap

    ui.solver.tap_confirm(ROOM, {})

    assert len(clicks) == 2
    assert clicks[0] == (1768, 1015)
    assert ui.clock.seconds >= 2.7
    ui.solver.back.assert_not_called()


@pytest.mark.parametrize("expired_at", ["entry", "scene_read"])
def test_expired_outer_deadline_never_restarts_the_game(waiting, expired_at):
    ui = waiting
    if expired_at == "entry":
        ui.clock.seconds = 2.5
    else:

        def scene():
            ui.clock.seconds = 3
            return Scene.CONNECTING

        ui.solver.scene = scene

    with ui.solver.observation_deadline(2.5):
        with pytest.raises(solver_utils.ObservationTimeout):
            ui.solver.waiting_solver()

    ui.device.exit.assert_not_called()
    ui.solver.check_current_focus.assert_not_called()
    assert ui.delays == []


@pytest.fixture
def unseen_pending_target(confirmation):
    ui = confirmation
    ui.apply_after = 100
    with pytest.raises(RecognizeError):
        ui.solver.agent_arrange(ui.task.plan)
    for slot in ui.solver.op_data.plan[ROOM]:
        slot.replacement = []
        slot.group_bindings = []
    assert ui.solver.op_data.get_current_room(ROOM, True) == ORIGINAL
    assert "但书" in ui.task.run_order_confirmation_pending["target"]
    assert "但书" not in ui.task.plan[ROOM]
    return ui


def test_unseen_submitted_target_is_reserved_after_configuration_changes(
    unseen_pending_target,
):
    ui = unseen_pending_target

    names, slots = retained_task_reservations(ui.solver.op_data, [ui.task])

    assert "但书" in names
    assert set(ORIGINAL).issubset(names)
    assert {(ROOM, 0), (ROOM, 1)}.issubset(slots)


def test_unseen_submitted_target_blocks_only_orders_using_its_operators(
    unseen_pending_target,
):
    ui = unseen_pending_target
    shared = scheduler_task.SchedulerTask(
        time=ui.clock.now(),
        task_type=scheduler_task.TaskTypes.RUN_ORDER,
        task_plan={"room_1_2": ["但书"]},
        meta_data="room_1_2",
    )
    other_order = scheduler_task.SchedulerTask(
        time=ui.clock.now(),
        task_type=scheduler_task.TaskTypes.RUN_ORDER,
        task_plan={"room_1_3": ["龙舌兰"]},
        meta_data="room_1_3",
    )
    independent = scheduler_task.SchedulerTask(
        time=ui.clock.now(), task_type=scheduler_task.TaskTypes.DEPOT
    )

    blocked = scheduler_task.blocked_run_order_ids(
        [ui.task, shared, independent, other_order], ui.solver.op_data
    )

    assert id(shared) in blocked
    assert id(independent) not in blocked
    assert id(other_order) not in blocked


def test_cancelled_submission_keeps_reservations_without_an_earlier_failure(
    confirmation,
):
    ui = confirmation
    ui.task.__dict__.pop("execution_retained", None)
    ui.apply_after = 100
    ui.cancel_at = 2.3

    with pytest.raises(MowerExit):
        ui.solver.agent_arrange(ui.task.plan)

    assert ui.task.run_order_confirmation_pending["submitted"]
    restored = pickle.loads(pickle.dumps(ui.task))
    assert restored.retains_execution
    names, _ = retained_task_reservations(ui.solver.op_data, [restored])
    assert set(restored.run_order_confirmation_pending["target"]) <= names
