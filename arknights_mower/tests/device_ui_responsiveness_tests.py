import subprocess
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from arknights_mower.tests.device_anr_tests import (
    CLOSE_SYSTEM_UI,
    UI_DUMP_COMMAND,
    error_dialog,
)
from arknights_mower.tests.device_anr_tests import (
    system_ui_recovery as system_ui_recovery,
)
from arknights_mower.tests.device_ui_recovery_tests import ui_session as ui_session
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    UIUnresponsiveError,
)
from arknights_mower.utils.device.touch_backend import TouchFailure


@pytest.fixture
def probe_device(monkeypatch):
    monkeypatch.setattr(config, "stop_mower", Event())
    device = object.__new__(Device)
    device.client = Mock()
    device.client.run.return_value = b""
    return device


def test_responsive_dispatch_only_sends_unknown_key(probe_device):
    probe_device.check_ui_responsive()
    assert probe_device.client.run.call_args_list == [call("input keyevent 0")]


def test_one_slow_dispatch_does_not_authorize_restart(probe_device):
    probe_device.client.run.side_effect = [
        TimeoutError("dispatch"),
        b"mower-ui-probe\n",
        b"",
    ]
    probe_device.check_ui_responsive()
    assert probe_device.client.run.call_args_list == [
        call("input keyevent 0"),
        call("echo mower-ui-probe"),
        call("input keyevent 0"),
    ]


@pytest.mark.parametrize(
    "failure", [TimeoutError("dispatch"), b"Error: Input injection failed."]
)
def test_two_failed_dispatches_with_working_adb_report_ui_failure(
    probe_device, failure
):
    probe_device.client.run.side_effect = [
        failure,
        b"mower-ui-probe\n",
        failure,
        b"mower-ui-probe\n",
    ]
    with pytest.raises(UIUnresponsiveError):
        probe_device.check_ui_responsive()
    assert probe_device.client.run.call_count == 4


def test_transport_loss_after_second_dispatch_does_not_authorize_restart(probe_device):
    probe_device.client.run.side_effect = [
        TimeoutError("dispatch"),
        b"mower-ui-probe\n",
        TimeoutError("second read"),
        TimeoutError("adb lost"),
    ]
    with pytest.raises(DeviceRecoveryError) as failure:
        probe_device.check_ui_responsive()
    assert not isinstance(failure.value, UIUnresponsiveError)
    assert probe_device.client.run.call_count == 4


@pytest.mark.parametrize("echo", [b"", b"other target\n", TimeoutError("adb")])
def test_unconfirmed_transport_does_not_report_ui_failure(probe_device, echo):
    probe_device.client.run.side_effect = [TimeoutError("dispatch"), echo]
    with pytest.raises(DeviceRecoveryError) as failure:
        probe_device.check_ui_responsive()
    assert not isinstance(failure.value, UIUnresponsiveError)
    assert probe_device.client.run.call_count == 2


def test_permission_failure_is_not_a_frozen_ui(probe_device):
    probe_device.client.run.return_value = (
        b"java.lang.SecurityException: INJECT_EVENTS denied"
    )
    with pytest.raises(DeviceRecoveryError) as failure:
        probe_device.check_ui_responsive()
    assert not isinstance(failure.value, UIUnresponsiveError)
    probe_device.client.run.assert_called_once()


def test_timeout_before_delivery_does_not_authorize_restart(probe_device):
    error = TimeoutError("adb handshake")
    error.input_not_sent = True
    probe_device.client.run.side_effect = error
    with pytest.raises(DeviceRecoveryError) as failure:
        probe_device.check_ui_responsive()
    assert not isinstance(failure.value, UIUnresponsiveError)
    probe_device.client.run.assert_called_once()


def test_insufficient_parent_budget_does_not_send_probe(probe_device):
    with device_io_budget(lambda: 0.5), pytest.raises(DeviceRecoveryError):
        probe_device.check_ui_responsive()
    probe_device.client.run.assert_not_called()


def test_parent_expiration_during_probe_does_not_authorize_restart(probe_device):
    remaining = [10.0]

    def expired(command):
        remaining[0] = 0
        raise TimeoutError("command deadline")

    def parent():
        if remaining[0] <= 0:
            raise TimeoutError("parent deadline")
        return remaining[0]

    probe_device.client.run.side_effect = expired
    with pytest.raises(DeviceRecoveryError) as failure, device_io_budget(parent):
        probe_device.check_ui_responsive()
    assert not isinstance(failure.value, UIUnresponsiveError)
    probe_device.client.run.assert_called_once()


def test_cancel_after_dispatch_failure_prevents_other_probe(probe_device):
    def cancel(command):
        config.stop_mower.set()
        raise TimeoutError("dispatch")

    probe_device.client.run.side_effect = cancel
    with pytest.raises(MowerExit):
        probe_device.check_ui_responsive()
    probe_device.client.run.assert_called_once()


def test_success_confirms_pending_ui_recovery(probe_device):
    class Control:
        executing = True
        confirm_ui_responsive = Mock()

    probe_device.session_control = Control()
    probe_device.check_ui_responsive()
    probe_device.session_control.confirm_ui_responsive.assert_called_once_with()


def test_same_scene_timeout_probes_before_exiting_game(monkeypatch):
    from datetime import datetime, timedelta

    from arknights_mower.utils.recognize import Recognizer, Scene

    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "run_order_delay", 1)
    calls = []
    device = SimpleNamespace(
        check_ui_responsive=lambda: calls.append("probe"),
        exit=lambda: calls.append("exit"),
        check_current_focus=lambda: False,
    )
    recog = Recognizer(device)
    recog.scene = recog.last_scene = Scene.INDEX
    now = datetime.now()
    recog.last_scene_time = now - timedelta(seconds=100)
    monkeypatch.setattr(
        "arknights_mower.utils.recognize.time.sleep", lambda seconds: None
    )
    recog.check_freeze(now)
    assert calls == ["probe", "exit"]


def test_failed_ui_probe_preserves_game_and_scene_for_session_recovery(monkeypatch):
    from datetime import datetime, timedelta

    from arknights_mower.utils.recognize import Recognizer, Scene

    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf, "run_order_delay", 1)
    device = SimpleNamespace(
        check_ui_responsive=Mock(side_effect=UIUnresponsiveError("stalled")),
        exit=Mock(),
    )
    recog = Recognizer(device)
    recog.scene = recog.last_scene = Scene.INDEX
    now = datetime.now()
    previous = now - timedelta(seconds=100)
    recog.last_scene_time = previous
    with pytest.raises(UIUnresponsiveError):
        recog.check_freeze(now)
    device.exit.assert_not_called()
    assert recog.last_scene_time == previous


def test_restored_focus_requires_responsive_dispatch_before_capture(monkeypatch):
    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config, "stop_mower", Event())
    device = SimpleNamespace(
        check_current_focus=Mock(return_value=True),
        check_ui_responsive=Mock(side_effect=UIUnresponsiveError("stalled")),
        screencap=Mock(),
    )
    recog = Recognizer(device)
    with pytest.raises(UIUnresponsiveError):
        recog.start()
    device.screencap.assert_not_called()


def test_ordinary_static_observation_does_not_probe_or_restart(monkeypatch):
    import numpy as np

    from arknights_mower.utils.recognize import Recognizer

    monkeypatch.setattr(config, "stop_mower", Event())
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    device = SimpleNamespace(
        check_current_focus=Mock(return_value=False),
        check_ui_responsive=Mock(),
        screencap=Mock(return_value=(None, frame, frame[:, :, 0])),
    )
    recog = Recognizer(device)
    for _ in range(3):
        recog.update()
        recog.start()
    device.check_ui_responsive.assert_not_called()


@pytest.fixture
def foreground_ui_session(ui_session, system_ui_recovery):
    env = ui_session
    device, responses, clock = system_ui_recovery
    original = env.control._device
    device.device_id = device.client.device_id = "USB-A"
    device._profile = env.session.profile.model_copy(update={"recovery_timeout": 30})
    device.session_control = env.control
    device.input_alive = Mock(return_value=True)
    device.screencap = Mock()
    device.close = original.close
    state = SimpleNamespace(
        stalled=True,
        dump_timeout=10.0,
        dump_error=TimeoutError("uiautomator stalled"),
        dump_data=None,
        after_dump=lambda: None,
        after_echo=lambda: None,
    )
    run = responses.run

    def dispatch(command):
        if command == "input keyevent 0":
            responses.commands.append(command)
            if state.stalled:
                clock[0] += io_timeout(3)
                raise TimeoutError("InputDispatcher stalled")
            return b""
        if command == "echo mower-ui-probe":
            responses.commands.append(command)
            state.after_echo()
            return b"mower-ui-probe\n"
        return run(command)

    def hierarchy(args):
        assert args == ["shell", UI_DUMP_COMMAND]
        responses.commands.append(UI_DUMP_COMMAND)
        clock[0] += io_timeout(state.dump_timeout)
        state.after_dump()
        if state.dump_error is not None:
            raise state.dump_error
        return state.dump_data

    def rebind(target, result):
        assert target is device and original.closed
        env.events.append("rebind")
        original.closed = False
        device.device_id = device.client.device_id = result.serial
        state.stalled = False

    device.client.run.side_effect = dispatch
    device.client.cmd.side_effect = hierarchy
    env.control._adapter.rebind = rebind
    env.control._device = device
    try:
        yield SimpleNamespace(
            env=env, device=device, responses=responses, clock=clock, state=state
        )
    finally:
        env.control._device = original


@pytest.mark.parametrize("dump_timeout", [10, 15])
@pytest.mark.parametrize("timeout_type", [TimeoutError, subprocess.TimeoutExpired])
def test_system_ui_hierarchy_timeout_diagnoses_stalled_input_before_restart(
    foreground_ui_session, dump_timeout, timeout_type
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session
    case.state.dump_timeout = dump_timeout
    case.state.dump_error = (
        subprocess.TimeoutExpired(["adb", "shell", UI_DUMP_COMMAND], dump_timeout)
        if timeout_type is subprocess.TimeoutExpired
        else TimeoutError("uiautomator stalled")
    )
    with pytest.raises(UIUnresponsiveError):
        Recognizer(case.device).start()

    assert case.responses.commands[-4:] == [
        "input keyevent 0",
        "echo mower-ui-probe",
        "input keyevent 0",
        "echo mower-ui-probe",
    ]
    assert CLOSE_SYSTEM_UI not in case.responses.commands
    assert not any(
        command.startswith("am start") for command in case.responses.commands
    )
    case.device.screencap.assert_not_called()
    assert case.env.control.recover().ok
    assert case.env.events == ["close", "stop", "start", "rebind"]
    assert case.env.simulator.actions == ["stop", "start"]


def test_system_ui_timeout_with_responsive_input_preserves_foreground_failure(
    foreground_ui_session,
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session
    case.state.stalled = False
    with pytest.raises(DeviceRecoveryError) as failure:
        Recognizer(case.device).start()

    assert not isinstance(failure.value, UIUnresponsiveError)
    assert failure.value.__cause__ is case.state.dump_error
    assert case.responses.commands.count("input keyevent 0") == 1
    case.device.screencap.assert_not_called()
    assert case.env.control.recover().ok
    assert case.env.simulator.actions == []


@pytest.mark.parametrize("failure", [PermissionError("denied"), b"not XML"])
def test_unverified_system_ui_hierarchy_does_not_diagnose_or_restart(
    foreground_ui_session, failure
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session
    case.state.dump_timeout = 0
    case.state.dump_error = failure if isinstance(failure, Exception) else None
    case.state.dump_data = failure if isinstance(failure, bytes) else None
    with pytest.raises(DeviceRecoveryError) as caught:
        Recognizer(case.device).start()

    assert not isinstance(caught.value, UIUnresponsiveError)
    assert "input keyevent 0" not in case.responses.commands
    assert CLOSE_SYSTEM_UI not in case.responses.commands
    case.device.screencap.assert_not_called()
    assert case.env.control.recover().ok
    assert case.env.simulator.actions == []


def test_cancel_after_system_ui_timeout_prevents_diagnosis_or_restart(
    foreground_ui_session,
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session
    case.state.after_dump = config.stop_mower.set
    with pytest.raises(MowerExit):
        Recognizer(case.device).start()

    assert "input keyevent 0" not in case.responses.commands
    assert case.env.simulator.actions == []
    case.device.screencap.assert_not_called()


@pytest.mark.parametrize("change", ["serial", "client_serial", "client", "profile"])
def test_target_change_after_system_ui_timeout_prevents_diagnosis_or_restart(
    foreground_ui_session, change
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session

    def change_target():
        if change == "serial":
            case.device.device_id = case.device.client.device_id = "USB-Z"
        elif change == "client_serial":
            case.device.client.device_id = "USB-Z"
        elif change == "client":
            case.device.client = Mock(device_id="USB-A")
        else:
            case.device._profile = case.device.profile.model_copy(
                update={"instance_id": "1"}
            )

    case.state.after_dump = change_target
    with pytest.raises(DeviceRecoveryError) as failure:
        Recognizer(case.device).start()

    assert failure.value.__cause__ is case.state.dump_error
    assert "input keyevent 0" not in case.responses.commands
    assert case.env.simulator.actions == []
    case.device.screencap.assert_not_called()


def test_uncertain_system_ui_close_preserves_pause_without_diagnosis_or_replay(
    foreground_ui_session,
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session
    case.state.dump_timeout = 0
    case.state.dump_error = None
    case.state.dump_data = error_dialog()
    case.responses.close_error = TimeoutError("close delivery unknown")
    recognizer = Recognizer(case.device)
    with pytest.raises(TouchFailure) as failure:
        recognizer.start()

    assert failure.value.delivery_unknown
    recovered = case.env.control.recover()
    assert recovered.ok and recovered.status == "paused"
    with pytest.raises(TouchFailure) as paused:
        recognizer.start()

    assert paused.value is failure.value
    assert "input keyevent 0" not in case.responses.commands
    assert case.responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert case.env.simulator.actions == []
    case.device.screencap.assert_not_called()


def test_target_change_during_system_ui_diagnosis_prevents_restart(
    foreground_ui_session,
):
    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session

    def change_target():
        case.device.device_id = case.device.client.device_id = "USB-Z"

    case.state.after_echo = change_target
    with pytest.raises(DeviceRecoveryError) as failure:
        Recognizer(case.device).start()

    assert failure.value.__cause__ is case.state.dump_error
    assert case.responses.commands.count("input keyevent 0") == 1
    assert case.env.simulator.actions == []
    case.device.screencap.assert_not_called()


@pytest.mark.parametrize(("budget", "probes"), [(10, 0), (11, 0), (14, 1)])
@pytest.mark.parametrize("budget_owner", ["parent", "profile"])
def test_system_ui_timeout_diagnosis_preserves_remaining_recovery_budget(
    foreground_ui_session, budget, probes, budget_owner
):
    from contextlib import nullcontext

    from arknights_mower.utils.recognize import Recognizer

    case = foreground_ui_session

    def remaining():
        seconds = budget - case.clock[0]
        if seconds <= 0:
            raise TimeoutError("parent budget exhausted")
        return seconds

    if budget_owner == "profile":
        case.device._profile = case.device.profile.model_copy(
            update={"recovery_timeout": budget}
        )
    scope = device_io_budget(remaining) if budget_owner == "parent" else nullcontext()
    with pytest.raises(DeviceRecoveryError) as failure, scope:
        Recognizer(case.device).start()

    assert failure.value.__cause__ is case.state.dump_error
    assert case.clock[0] <= budget
    assert case.responses.commands.count("input keyevent 0") == probes
    assert case.env.simulator.actions == []
    case.device.screencap.assert_not_called()
