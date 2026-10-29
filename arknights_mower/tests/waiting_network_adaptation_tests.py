from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import recognize, solver
from arknights_mower.utils.network_adaptation import get_network_adaptation
from arknights_mower.utils.recognize import Recognizer, Scene


@pytest.fixture
def waiting(monkeypatch):
    class Clock(datetime):
        seconds = 0.0

        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 28, 19, 0) + timedelta(seconds=cls.seconds)

        @classmethod
        def monotonic(cls):
            return cls.seconds

    conf = SimpleNamespace(
        run_order_delay=1,
        run_order_buffer_time=15,
        run_order_network_adaptive=False,
        waiting_scene_network_adaptive=True,
        waiting_scene=SimpleNamespace(
            CONNECTING=(1, 10),
            LOADING=(2, 30),
            LOGIN_LOADING=(3, 10),
            UNKNOWN=(1, 10),
        ),
    )
    monkeypatch.setattr(solver.config, "conf", conf)
    monkeypatch.setattr(solver, "datetime", Clock)
    monkeypatch.setattr(recognize, "datetime", Clock)
    monkeypatch.setattr(solver, "time", SimpleNamespace(monotonic=Clock.monotonic))
    monkeypatch.setattr(
        recognize, "time", SimpleNamespace(monotonic=Clock.monotonic, sleep=Mock())
    )
    monkeypatch.setattr(solver, "csleep", Mock())
    monkeypatch.setattr(solver, "logger", Mock())
    monkeypatch.setattr(recognize, "logger", Mock())
    device = SimpleNamespace(
        exit=Mock(), launch=Mock(), check_current_focus=Mock(return_value=False)
    )
    recog = Recognizer(device)
    recog.scene = Scene.CONNECTING
    subject = solver.BaseSolver(device, recog)
    subject.check_current_focus = Mock()
    state = SimpleNamespace(
        clock=Clock,
        conf=conf,
        solver=subject,
        recog=recog,
        device=device,
        delays=[],
        scene_at=lambda elapsed: Scene.CONNECTING,
        check_loading=False,
        login_connecting_at=lambda elapsed: False,
    )

    def sleep(seconds):
        state.delays.append(seconds)
        Clock.seconds += seconds
        recog.scene = state.scene_at(Clock.seconds)
        if state.check_loading:
            recog.check_loading_time()

    subject.sleep = sleep
    subject.find = Mock(
        side_effect=lambda resource, **kwargs: (
            ((760, 881), (1160, 920))
            if resource == "login_connecting"
            and state.login_connecting_at(Clock.seconds)
            else None
        )
    )
    return state


def remember(waiting, seconds, scene="CONNECTING", base=10):
    return get_network_adaptation(waiting.recog).record(
        scene,
        elapsed_seconds=seconds,
        base_seconds=base,
        observed_at=waiting.clock.now(),
    )


def test_next_same_scene_uses_base_plus_observation_without_extra_margin(waiting):
    remember(waiting, 30)
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 30 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 30
    assert waiting.delays == [1] * 30
    waiting.device.exit.assert_not_called()
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待结束，耗时30秒。"
    )
    solver.logger.info.assert_called_once_with(
        "近15分钟内出现过网络卡顿，本次【%s】的等待上限由%s秒延长至%s秒。",
        "正在提交反馈至神经",
        "10",
        "40",
    )


def test_timeout_records_lower_bound_before_restart(waiting):
    remember(waiting, 30)
    events_at_exit = []
    waiting.device.exit.side_effect = lambda: events_at_exit.append(
        get_network_adaptation(waiting.recog).peek_run_order(
            waiting.clock.now(), base_seconds=waiting.conf.run_order_buffer_time
        )
    )

    assert waiting.solver.waiting_solver() is False
    assert waiting.clock.seconds == 40
    assert events_at_exit[0].duration_seconds == 40
    assert events_at_exit[0].timed_out is True
    waiting.device.exit.assert_called_once_with()
    assert "_network_wait_guard" not in waiting.recog.__dict__
    assert "_network_wait_episode" not in waiting.recog.__dict__
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待超时，已等待40秒。"
    )


@pytest.mark.parametrize("restart", [False, True])
def test_protected_wait_owns_freeze_and_loading_restart_decisions(waiting, restart):
    remember(waiting, 120)
    waiting.check_loading = True

    assert waiting.solver.waiting_solver(restart_on_timeout=restart) is False
    assert waiting.clock.seconds == 130
    assert waiting.device.exit.call_count == int(restart)
    assert "_network_wait_guard" not in waiting.recog.__dict__
    assert waiting.recog.last_scene_time == waiting.clock.now()


def test_continuous_network_scene_switch_does_not_renew_budget(waiting):
    remember(waiting, 30)
    waiting.scene_at = lambda elapsed: (
        Scene.LOADING if elapsed >= 15 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 100
    latest = get_network_adaptation(waiting.recog).peek_run_order(
        waiting.clock.now(), base_seconds=waiting.conf.run_order_buffer_time
    )
    assert latest.scene == "CONNECTING"
    assert latest.duration_seconds == 15

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 100
    waiting.device.exit.assert_not_called()


def test_rebuilt_solver_and_game_restart_keep_recent_network_event(waiting):
    event = remember(waiting, 30)
    waiting.solver.restart_game()
    waiting.recog.scene = Scene.CONNECTING
    rebuilt = solver.BaseSolver(waiting.device, waiting.recog)
    rebuilt.sleep = waiting.solver.sleep
    rebuilt.check_current_focus = Mock()
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 20 else Scene.CONNECTING
    )

    assert rebuilt.waiting_solver() is True
    assert waiting.clock.seconds == 20
    assert (
        get_network_adaptation(waiting.recog)
        .peek_run_order(
            waiting.clock.now(), base_seconds=waiting.conf.run_order_buffer_time
        )
        .event_id
        != event.event_id
    )


def test_run_order_scope_extends_connecting_when_waiting_option_is_off(waiting):
    waiting.conf.waiting_scene_network_adaptive = False
    waiting.conf.run_order_network_adaptive = True
    waiting.recog._run_order_network_compensation = 30
    waiting.recog._run_order_network_active = True
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 30 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 30
    waiting.device.exit.assert_not_called()


def test_run_order_and_waiting_allowances_use_larger_value(waiting):
    remember(waiting, 30)
    waiting.conf.run_order_network_adaptive = True
    waiting.recog._run_order_network_compensation = 20
    waiting.recog._run_order_network_active = True

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 40


def test_new_non_network_observation_allows_a_later_protected_wait(waiting):
    remember(waiting, 30)
    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    waiting.recog.scene = Scene.INDEX
    assert waiting.solver.scene() == Scene.INDEX
    waiting.recog.scene = Scene.CONNECTING
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 65 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 65


def test_short_wait_keeps_unconsumed_slow_observation(waiting):
    event = remember(waiting, 30)
    waiting.conf.waiting_scene_network_adaptive = False
    waiting.conf.run_order_network_adaptive = True
    waiting.scene_at = lambda elapsed: Scene.INDEX

    assert waiting.solver.waiting_solver() is True
    assert (
        get_network_adaptation(waiting.recog)
        .take_wait("CONNECTING", waiting.clock.now(), base_seconds=10)
        .event_id
        == event.event_id
    )
    solver.logger.debug.assert_not_called()


def test_disabled_options_keep_existing_wait_count_and_emit_no_new_logs(waiting):
    waiting.conf.waiting_scene_network_adaptive = False

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.delays == [1] * 10
    waiting.device.exit.assert_not_called()
    solver.logger.debug.assert_not_called()
    solver.logger.info.assert_not_called()
    assert "network_adaptation" not in waiting.recog.__dict__


def test_unprotected_freeze_still_uses_existing_limit(waiting):
    waiting.recog.scene = waiting.recog.last_scene = Scene.INDEX
    waiting.recog.last_scene_time = waiting.clock.now() - timedelta(seconds=91)

    waiting.recog.check_freeze(waiting.clock.now())

    waiting.device.exit.assert_called_once_with()
    assert waiting.recog.scene == Scene.UNDEFINED


def test_unprotected_loading_check_still_restarts(waiting):
    waiting.recog.loading_time = waiting.recog.LOADING_TIME_LIMIT
    waiting.recog.check_loading_time()

    waiting.device.exit.assert_called_once_with()


def test_scene_change_keeps_the_new_scenes_full_base_budget(waiting):
    waiting.scene_at = lambda elapsed: (
        Scene.CONNECTING if elapsed < 5 else Scene.LOADING
    )

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 65
    waiting.device.exit.assert_not_called()


def test_normal_loading_can_finish_after_short_connecting_without_slow_history(waiting):
    waiting.scene_at = lambda elapsed: (
        Scene.CONNECTING
        if elapsed < 5
        else Scene.LOADING
        if elapsed < 25
        else Scene.INDEX
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 25
    waiting.device.exit.assert_not_called()
    solver.logger.info.assert_not_called()


def test_compensation_is_shared_once_across_network_scenes(waiting):
    remember(waiting, 30)
    waiting.scene_at = lambda elapsed: (
        Scene.CONNECTING if elapsed < 35 else Scene.LOADING
    )

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 100
    waiting.device.exit.assert_not_called()


def test_switching_back_does_not_refill_a_scenes_base_budget(waiting):
    waiting.scene_at = lambda elapsed: (
        Scene.LOADING if 5 <= elapsed < 15 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 20
    waiting.device.exit.assert_not_called()


@pytest.mark.parametrize("reset", ["restart", "external"])
def test_explicit_restart_clears_exhausted_episode_but_keeps_observations(
    waiting, reset
):
    remember(waiting, 30)
    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    if reset == "restart":
        waiting.solver.restart_game()
    else:
        waiting.recog.reset_after_external_control()
    assert "_network_wait_episode" not in waiting.recog.__dict__
    waiting.recog.scene = Scene.CONNECTING
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 65 else Scene.CONNECTING
    )
    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 65


@pytest.mark.parametrize("scene", [Scene.LOADING, Scene.LOGIN_LOADING])
def test_ordinary_loading_never_creates_network_evidence(waiting, scene):
    waiting.recog.scene = scene
    waiting.scene_at = lambda elapsed: Scene.INDEX if elapsed >= 24 else scene

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 24
    assert get_network_adaptation(waiting.recog).observations == ()
    solver.logger.debug.assert_not_called()
    waiting.device.exit.assert_not_called()


@pytest.mark.parametrize("scene", [Scene.LOADING, Scene.LOGIN_LOADING])
def test_loading_can_use_network_evidence_without_renewing_it(waiting, scene):
    evidence = remember(waiting, 30)
    label = "LOADING" if scene == Scene.LOADING else "LOGIN_LOADING"
    setattr(waiting.conf.waiting_scene, label, (1, 10))
    waiting.recog.scene = scene
    waiting.scene_at = lambda elapsed: Scene.INDEX if elapsed >= 25 else scene

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 25
    adaptation = get_network_adaptation(waiting.recog)
    assert adaptation.observations == (evidence,)
    assert (
        adaptation.peek_run_order(
            waiting.clock.now(), base_seconds=waiting.conf.run_order_buffer_time
        )
        == evidence
    )
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=10) is None
    )
    solver.logger.info.assert_called_once()
    solver.logger.debug.assert_not_called()
    waiting.device.exit.assert_not_called()


def test_login_logo_then_one_second_connecting_records_only_one_raw_second(waiting):
    waiting.conf.waiting_scene.LOGIN_LOADING = (1, 50)
    waiting.recog.scene = Scene.LOGIN_LOADING
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 31 else Scene.LOGIN_LOADING
    )
    waiting.login_connecting_at = lambda elapsed: 30 <= elapsed < 31

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 31
    adaptation = get_network_adaptation(waiting.recog)
    assert len(adaptation.observations) == 1
    event = adaptation.observations[0]
    assert event.scene == "LOGIN_CONNECTING"
    assert event.duration_seconds == 1
    assert event.base_seconds == 50
    assert (
        adaptation.take_wait("LOGIN_LOADING", waiting.clock.now(), base_seconds=50)
        is None
    )
    assert adaptation.peek_run_order(waiting.clock.now(), base_seconds=15) is None
    solver.logger.debug.assert_not_called()


@pytest.mark.parametrize("run_enabled", [False, True])
def test_login_network_phase_records_its_own_duration_and_logs_only_qualified_use(
    waiting, run_enabled
):
    waiting.conf.run_order_network_adaptive = run_enabled
    waiting.conf.waiting_scene.LOGIN_LOADING = (1, 50)
    waiting.recog.scene = Scene.LOGIN_LOADING
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 31 else Scene.LOGIN_LOADING
    )
    waiting.login_connecting_at = lambda elapsed: 20 <= elapsed < 31

    assert waiting.solver.waiting_solver() is True
    adaptation = get_network_adaptation(waiting.recog)
    events = adaptation.observations
    assert len(events) == 1
    assert events[0].scene == "LOGIN_CONNECTING"
    assert events[0].duration_seconds == 11
    assert events[0].base_seconds == 50
    assert events[0].timed_out is False
    assert (
        adaptation.take_wait("LOGIN_LOADING", waiting.clock.now(), base_seconds=50)
        is None
    )
    assert solver.logger.debug.call_count == int(run_enabled)


def test_two_short_login_network_phases_are_not_added_together(waiting):
    waiting.conf.waiting_scene.LOGIN_LOADING = (1, 20)
    waiting.recog.scene = Scene.LOGIN_LOADING
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 14 else Scene.LOGIN_LOADING
    )
    waiting.login_connecting_at = lambda elapsed: elapsed < 6 or 8 <= elapsed < 14

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 14
    adaptation = get_network_adaptation(waiting.recog)
    assert [event.duration_seconds for event in adaptation.observations] == [6, 6]
    assert all(event.scene == "LOGIN_CONNECTING" for event in adaptation.observations)
    assert (
        adaptation.take_wait("LOGIN_LOADING", waiting.clock.now(), base_seconds=20)
        is None
    )
    solver.logger.debug.assert_not_called()


def test_network_phases_separated_by_loading_are_not_added_together(waiting):
    waiting.conf.waiting_scene.CONNECTING = (1, 20)
    waiting.scene_at = lambda elapsed: (
        Scene.CONNECTING
        if elapsed < 6
        else Scene.LOADING
        if elapsed < 8
        else Scene.CONNECTING
        if elapsed < 14
        else Scene.INDEX
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 14
    adaptation = get_network_adaptation(waiting.recog)
    assert [event.duration_seconds for event in adaptation.observations] == [6, 6]
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=20) is None
    )
    solver.logger.debug.assert_not_called()


def test_success_at_short_base_uses_its_half_instead_of_old_fixed_threshold(waiting):
    waiting.conf.waiting_scene.CONNECTING = (1, 2)
    waiting.scene_at = lambda elapsed: Scene.INDEX if elapsed >= 2 else Scene.CONNECTING

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 2
    adaptation = get_network_adaptation(waiting.recog)
    events = adaptation.observations
    assert len(events) == 1
    assert events[0].duration_seconds == events[0].base_seconds == 2
    assert events[0].timed_out is False
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=2)
        == events[0]
    )
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待结束，耗时2秒。"
    )


def test_actual_short_base_timeout_records_only_the_observed_lower_bound(waiting):
    waiting.conf.waiting_scene.CONNECTING = (1, 2)

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    events = get_network_adaptation(waiting.recog).observations
    assert len(events) == 1
    assert events[0].scene == "CONNECTING"
    assert events[0].duration_seconds == events[0].compensation_seconds == 2
    assert events[0].timed_out is True
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待超时，已等待2秒。"
    )
    waiting.device.exit.assert_not_called()


def test_timeout_keeps_short_raw_phases_separate_and_does_not_bypass_half(waiting):
    waiting.conf.waiting_scene.CONNECTING = (1, 4)
    waiting.conf.waiting_scene.LOADING = (1, 4)
    waiting.scene_at = lambda elapsed: (
        Scene.LOADING if int(elapsed) in (1, 3, 5) else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 7
    adaptation = get_network_adaptation(waiting.recog)
    events = adaptation.observations
    assert [event.duration_seconds for event in events] == [1, 1, 1, 1]
    assert [event.timed_out for event in events] == [False, False, False, True]
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=4) is None
    )
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待超时，已等待1秒。"
    )
    waiting.device.exit.assert_not_called()


@pytest.mark.parametrize(
    "run_enabled,wait_enabled",
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_network_evidence_is_observed_only_when_either_option_is_enabled(
    waiting, run_enabled, wait_enabled
):
    waiting.conf.run_order_network_adaptive = run_enabled
    waiting.conf.waiting_scene_network_adaptive = wait_enabled
    waiting.conf.waiting_scene.CONNECTING = (1, 20)
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 12 else Scene.CONNECTING
    )

    assert waiting.solver.waiting_solver() is True
    assert waiting.clock.seconds == 12
    adaptation = waiting.recog.__dict__.get("network_adaptation")
    if run_enabled or wait_enabled:
        assert len(adaptation.observations) == 1
        assert adaptation.observations[0].scene == "CONNECTING"
        assert adaptation.observations[0].duration_seconds == 12
        assert adaptation.observations[0].timed_out is False
        assert solver.logger.debug.call_count == 1
    else:
        assert adaptation is None
        solver.logger.debug.assert_not_called()


def test_raw_wait_below_half_is_retained_without_debug_or_consumption(waiting):
    waiting.conf.waiting_scene.CONNECTING = (1, 4)
    waiting.scene_at = lambda elapsed: Scene.INDEX

    assert waiting.solver.waiting_solver() is True
    adaptation = get_network_adaptation(waiting.recog)
    event = adaptation.observations[0]
    assert event.duration_seconds == 1
    assert event.base_seconds == 4
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=4) is None
    )
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=2) == event
    )
    solver.logger.debug.assert_not_called()
    solver.logger.info.assert_not_called()


def test_nine_seconds_does_not_extend_thirty_second_wait_or_consume_evidence(waiting):
    waiting.conf.run_order_network_adaptive = True
    waiting.conf.waiting_scene.LOADING = (1, 30)
    event = remember(waiting, 9)
    waiting.recog.scene = Scene.LOADING
    waiting.scene_at = lambda elapsed: Scene.LOADING

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 30
    adaptation = get_network_adaptation(waiting.recog)
    assert adaptation.observations == (event,)
    assert adaptation.take_run_order(waiting.clock.now(), base_seconds=15) == event
    assert adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=30) is None
    assert (
        adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=10) == event
    )
    solver.logger.info.assert_not_called()
    solver.logger.debug.assert_not_called()
    waiting.device.exit.assert_not_called()


def test_nine_seconds_extends_ten_second_wait_to_nineteen_with_exact_info(waiting):
    waiting.conf.waiting_scene.LOADING = (1, 10)
    event = remember(waiting, 9)
    waiting.recog.scene = Scene.LOADING
    waiting.scene_at = lambda elapsed: Scene.LOADING

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 19
    adaptation = get_network_adaptation(waiting.recog)
    assert adaptation.peek_run_order(waiting.clock.now(), base_seconds=15) == event
    assert adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=10) is None
    solver.logger.info.assert_called_once_with(
        "近15分钟内出现过网络卡顿，本次【%s】的等待上限由%s秒延长至%s秒。",
        "场景跳转时的等待界面",
        "10",
        "19",
    )
    solver.logger.debug.assert_not_called()


@pytest.mark.parametrize("duration,extra", [(4.9, 0), (5, 5), (5.1, 5.1)])
def test_half_of_original_wait_timeout_is_inclusive_and_does_not_consume_below(
    waiting, duration, extra
):
    waiting.conf.waiting_scene.LOADING = (1, 10)
    event = remember(waiting, duration)
    waiting.recog.scene = Scene.LOADING
    waiting.scene_at = lambda elapsed: Scene.LOADING

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == pytest.approx(10 + extra)
    assert solver.logger.info.call_count == int(extra > 0)
    adaptation = get_network_adaptation(waiting.recog)
    if extra:
        assert (
            adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=8) is None
        )
    else:
        assert (
            adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=8)
            == event
        )


def test_recorded_source_base_and_debug_threshold_do_not_use_widened_timeout(waiting):
    remember(waiting, 9)
    waiting.scene_at = lambda elapsed: Scene.INDEX if elapsed >= 6 else Scene.CONNECTING

    assert waiting.solver.waiting_solver() is True
    adaptation = get_network_adaptation(waiting.recog)
    latest = adaptation.observations[-1]
    assert latest.duration_seconds == 6
    assert latest.base_seconds == 10
    assert (
        adaptation.take_wait("CONNECTING", waiting.clock.now(), base_seconds=10)
        == latest
    )
    solver.logger.debug.assert_called_once_with(
        "【正在提交反馈至神经】等待结束，耗时6秒。"
    )


@pytest.mark.parametrize("active,expected", [(False, 10), (True, 19)])
def test_run_scope_can_take_half_qualified_wait_evidence_with_zero_run_compensation(
    waiting, active, expected
):
    waiting.conf.run_order_network_adaptive = True
    waiting.conf.waiting_scene_network_adaptive = False
    waiting.conf.waiting_scene.LOADING = (1, 10)
    event = remember(waiting, 9)
    waiting.recog._run_order_network_active = active
    waiting.recog._run_order_network_compensation = 0
    waiting.recog.scene = Scene.LOADING
    waiting.scene_at = lambda elapsed: Scene.LOADING

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == expected
    assert solver.logger.info.call_count == int(active)
    adaptation = get_network_adaptation(waiting.recog)
    assert adaptation.peek_run_order(waiting.clock.now(), base_seconds=15) == event
    if active:
        assert (
            adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=10)
            is None
        )
    else:
        assert (
            adaptation.take_wait("LOADING", waiting.clock.now(), base_seconds=10)
            == event
        )


def test_selected_run_compensation_protects_connecting_even_below_scene_half(waiting):
    waiting.conf.run_order_network_adaptive = True
    waiting.conf.waiting_scene_network_adaptive = False
    waiting.conf.waiting_scene.CONNECTING = (1, 30)
    event = remember(waiting, 9)
    adaptation = get_network_adaptation(waiting.recog)
    assert adaptation.take_run_order(waiting.clock.now(), base_seconds=15) == event
    waiting.recog._run_order_network_active = True
    waiting.recog._run_order_network_compensation = 9

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 39
    solver.logger.info.assert_called_once_with(
        "近15分钟内出现过网络卡顿，本次【%s】的等待上限由%s秒延长至%s秒。",
        "正在提交反馈至神经",
        "30",
        "39",
    )


@pytest.mark.parametrize("scene", [Scene.LOADING, Scene.LOGIN_LOADING])
def test_selected_run_compensation_does_not_force_ordinary_loading_below_its_half(
    waiting, scene
):
    waiting.conf.run_order_network_adaptive = True
    waiting.conf.waiting_scene_network_adaptive = False
    label = "LOADING" if scene == Scene.LOADING else "LOGIN_LOADING"
    setattr(waiting.conf.waiting_scene, label, (1, 30))
    remember(waiting, 9)
    waiting.recog._run_order_network_active = True
    waiting.recog._run_order_network_compensation = 9
    waiting.recog.scene = scene
    waiting.scene_at = lambda elapsed: scene

    assert waiting.solver.waiting_solver(restart_on_timeout=False) is False
    assert waiting.clock.seconds == 30
    solver.logger.info.assert_not_called()
    solver.logger.debug.assert_not_called()


@pytest.mark.parametrize("inside_scope", [False, True])
def test_real_run_scope_protects_waiting_without_qualifying_for_buffer_compensation(
    waiting, monkeypatch, inside_scope
):
    from arknights_mower.utils import run_order_network
    from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

    waiting.conf.run_order_network_adaptive = True
    waiting.conf.waiting_scene_network_adaptive = False
    waiting.conf.run_order_buffer_time = 50
    remember(waiting, 9)
    original_time = waiting.clock.now() + timedelta(minutes=1)
    task = SchedulerTask(
        original_time, {"room_1_1": ["但书"]}, TaskTypes.RUN_ORDER, "room_1_1"
    )
    waiting.solver.task = task
    waiting.solver.tasks = [task]
    waiting.solver.op_data = SimpleNamespace()
    monkeypatch.setattr(run_order_network, "datetime", waiting.clock)
    waiting.scene_at = lambda elapsed: (
        Scene.INDEX if elapsed >= 15 else Scene.CONNECTING
    )

    @run_order_network.with_run_order_network
    def arrange(subject):
        assert subject.recog._run_order_network_active is True
        assert subject.recog._run_order_network_compensation == 0
        assert not hasattr(task, "run_order_network_timing")
        return subject.waiting_solver(restart_on_timeout=False)

    result = (
        arrange(waiting.solver)
        if inside_scope
        else waiting.solver.waiting_solver(restart_on_timeout=False)
    )

    assert result is inside_scope
    assert waiting.clock.seconds == (15 if inside_scope else 10)
    assert waiting.conf.run_order_buffer_time == 50
    assert task.time == original_time
    assert not hasattr(task, "run_order_network_timing")
    assert "_run_order_network_active" not in waiting.recog.__dict__
    assert "_run_order_network_compensation" not in waiting.recog.__dict__
    waiting.device.exit.assert_not_called()
