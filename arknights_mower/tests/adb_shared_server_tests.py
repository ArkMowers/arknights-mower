import json
import multiprocessing
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client import shared
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    SharedADBHandshakeTimeout,
)
from arknights_mower.utils.device.adb_client.shared import SharedADBRecovery


class Clock:
    def __init__(self):
        self.now = 0
        self.wall = 1000

    def monotonic(self):
        return self.now

    def wall_clock(self):
        return self.wall

    def sleep(self, seconds):
        self.now += seconds
        self.wall += seconds


@pytest.fixture
def service(tmp_path, monkeypatch):
    for name in (
        "ADB_SERVER_SOCKET",
        "ANDROID_ADB_SERVER_ADDRESS",
        "ANDROID_ADB_SERVER_PORT",
        "ADB_SERVER_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    clock = Clock()
    host = SimpleNamespace(version=41, mutations=[])

    def probe(timeout):
        if isinstance(host.version, Exception):
            raise host.version
        return host.version

    def kill(timeout):
        host.mutations.append("host:kill")
        host.version = None

    def run(argv, **kwargs):
        if argv[1] == "version":
            return subprocess.CompletedProcess(
                argv, 0, b"Android Debug Bridge version 1.0.41\n", b""
            )
        assert argv == ["selected-adb", "start-server"]
        host.mutations.append("start-server")
        host.version = 41
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    runner, observer, killer = (
        Mock(side_effect=run),
        Mock(side_effect=probe),
        Mock(side_effect=kill),
    )
    options = dict(
        lock_path=tmp_path / "shared.lock",
        run=runner,
        probe=observer,
        kill=killer,
        monotonic=clock.monotonic,
        wall_clock=clock.wall_clock,
        sleep=clock.sleep,
    )
    return SimpleNamespace(
        recovery=SharedADBRecovery(**options),
        options=options,
        clock=clock,
        host=host,
        runner=runner,
        probe=observer,
        kill=killer,
    )


def establish_failure(service):
    service.host.version = SharedADBHandshakeTimeout("host handshake stalled")
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    service.clock.sleep(30)


def test_healthy_host_does_not_restart_or_consume_action_even_if_devices_offline(
    service,
):
    action = Mock()
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is False
    assert service.recovery.adb_path == "selected-adb"
    assert service.recovery.generation == 0
    assert service.host.mutations == []
    assert all(
        call.args[0] == ["selected-adb", "version"]
        for call in service.runner.call_args_list
    )
    action.assert_not_called()


def test_absent_host_starts_selected_binary_without_kill(service):
    service.host.version = None
    action = Mock(side_effect=lambda operation: operation())
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is True
    action.assert_called_once()
    assert service.host.mutations == ["start-server"]
    assert service.recovery.generation == 1


def test_restart_requires_two_cycles_and_thirty_monotonic_seconds(service):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for advance in (0, 10, 19):
        service.clock.sleep(advance)
        with pytest.raises(SharedADBError, match="30 秒"):
            service.recovery.recover("selected-adb", timeout=5)
        assert service.host.mutations == []
        assert service.recovery.generation == 0
    service.clock.sleep(1)
    action = Mock(side_effect=lambda operation: operation())
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is True
    action.assert_called_once()
    assert service.host.mutations == ["host:kill", "start-server"]
    assert service.recovery.generation == 1


def test_wall_clock_jump_never_shortens_monotonic_failure_window(service):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    service.clock.wall += 100000
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


@pytest.mark.parametrize(
    "response",
    [
        41,
        None,
        SharedADBError("EOF"),
        SharedADBError("malformed"),
        0,
        "0029",
        PermissionError(),
        OSError("reset"),
    ],
)
def test_non_timeout_observation_resets_failure_window(service, response):
    establish_failure(service)
    service.host.version = response
    if response in (41, None):
        service.recovery.recover("selected-adb", timeout=5)
    else:
        with pytest.raises(SharedADBError):
            service.recovery.recover("selected-adb", timeout=5)
    service.host.mutations.clear()
    service.host.version = SharedADBHandshakeTimeout("stalled again")
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 1
    assert service.host.mutations == []


def test_gap_longer_than_sixty_seconds_does_not_count_as_sustained_failure(service):
    establish_failure(service)
    service.clock.sleep(31)
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


@pytest.mark.parametrize("locked_response", [41, 40, SharedADBError("malformed"), 0])
def test_locked_reprobe_prevents_restart_after_listener_recovers_or_changes(
    service, locked_response
):
    establish_failure(service)
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled"), locked_response]
    if locked_response == 41:
        assert service.recovery.recover("selected-adb", timeout=5) is False
    else:
        with pytest.raises(SharedADBError):
            service.recovery.recover("selected-adb", timeout=5)
    service.kill.assert_not_called()
    assert service.recovery._failed_probes == 0
    assert service.recovery.generation == 0


def test_initial_mismatch_never_authorizes_restart_from_old_timeout_window(service):
    establish_failure(service)
    service.host.version = 40
    with pytest.raises(SharedADBError, match="版本不一致"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_action_reprobes_immediately_before_mutating(service):
    establish_failure(service)

    def action(operation):
        service.host.version = 41
        assert operation() is True

    assert service.recovery.recover("selected-adb", timeout=5, action=action) is False
    assert service.host.mutations == []
    assert service.recovery.generation == 0


def test_action_budget_rejection_prevents_restart_and_generation_change(service):
    establish_failure(service)
    action = Mock(side_effect=RuntimeError("action budget exhausted"))
    with pytest.raises(RuntimeError, match="action budget"):
        service.recovery.recover("selected-adb", timeout=5, action=action)
    assert service.host.mutations == []
    assert service.recovery.generation == 0


@pytest.mark.parametrize("stage", ["initial", "probe", "action"])
def test_cancellation_never_authorizes_or_records_restart(service, stage):
    establish_failure(service)
    cancelled = [stage == "initial"]
    if stage == "probe":

        def observe(timeout):
            cancelled[0] = True
            raise SharedADBHandshakeTimeout("stalled")

        service.probe.side_effect = observe

    def action(operation):
        cancelled[0] = True
        return operation()

    with pytest.raises(MowerExit):
        service.recovery.recover(
            "selected-adb",
            timeout=5,
            cancelled=lambda: cancelled[0],
            action=action if stage == "action" else None,
        )
    assert service.recovery.generation == 0
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_cancellation_callable_can_raise_instead_of_returning_bool(service):
    cancelled = Mock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        service.recovery.recover("selected-adb", timeout=5, cancelled=cancelled)
    service.runner.assert_not_called()
    service.probe.assert_not_called()


def test_raising_cancellation_clears_previous_host_failure_window(service):
    establish_failure(service)
    with pytest.raises(MowerExit):
        service.recovery.recover(
            "selected-adb", timeout=5, cancelled=Mock(side_effect=MowerExit)
        )
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_total_probe_budget_exhaustion_is_not_a_host_failure(service):
    def observe(timeout):
        service.clock.sleep(5)
        raise SharedADBHandshakeTimeout("stalled")

    service.probe.side_effect = observe
    with pytest.raises(SharedADBError, match="时间预算"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_protocol_version_cannot_be_derived_from_unverified_binary(service):
    service.runner.return_value = subprocess.CompletedProcess(
        [], 0, b"unknown vendor", b""
    )
    service.runner.side_effect = None
    with pytest.raises(SharedADBError, match="协议版本"):
        service.recovery.recover("selected-adb", timeout=5)
    service.probe.assert_not_called()
    assert service.host.mutations == []


def test_failed_restart_persists_generation_before_kill_and_peer_observes_it(service):
    establish_failure(service)

    def kill(timeout):
        assert service.recovery.generation == 1
        record = json.loads(service.options["lock_path"].read_bytes()[1:])
        assert record["generation"] == 1
        raise SharedADBError("host:kill failed")

    service.kill.side_effect = kill
    with pytest.raises(SharedADBError, match="host:kill"):
        service.recovery.recover("selected-adb", timeout=5)
    service.host.version = 41
    peer = SharedADBRecovery(**service.options)
    assert peer.recover("selected-adb", timeout=5) is False
    assert peer.generation == service.recovery.generation == 1


def test_missing_service_can_start_inside_failed_kill_cooldown(service):
    establish_failure(service)

    def kill(timeout):
        service.host.version = None
        raise SharedADBError("kill ACK lost")

    service.kill.side_effect = kill
    with pytest.raises(SharedADBError, match="ACK"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation == 2
    service.kill.assert_called_once()
    assert service.host.mutations == ["start-server"]


def test_rejected_kill_reports_promptly_without_waiting_or_starting(service):
    establish_failure(service)
    service.kill.side_effect = SharedADBError("停止请求（FAIL）")
    with pytest.raises(SharedADBError, match="FAIL"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.clock.now == 30
    assert service.recovery.generation == 1
    assert service.host.mutations == []


def test_failed_start_keeps_generation_and_missing_service_can_retry(service):
    service.host.version = None
    original = service.runner.side_effect

    def run(argv, **kwargs):
        if argv[1] == "start-server":
            raise subprocess.CalledProcessError(1, argv, stderr=b"cannot listen")
        return original(argv, **kwargs)

    service.runner.side_effect = run
    with pytest.raises(SharedADBError, match="恢复失败"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery.generation == 1
    service.runner.side_effect = original
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation == 2


def test_peer_restart_cooldown_prevents_another_kill(service):
    peer = SharedADBRecovery(**service.options)
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for recovery in (service.recovery, peer):
        with pytest.raises(SharedADBError, match="30 秒"):
            recovery.recover("selected-adb", timeout=5)
    service.clock.sleep(30)
    service.kill.side_effect = SharedADBError("host:kill stalled")
    with pytest.raises(SharedADBError, match="host:kill"):
        service.recovery.recover("selected-adb", timeout=5)
    with pytest.raises(SharedADBError, match="冷却"):
        peer.recover("selected-adb", timeout=5)
    assert peer.generation == 1
    service.kill.assert_called_once()
    service.clock.sleep(30)
    service.kill.side_effect = None
    service.kill.return_value = None
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled")] * 3 + [
        None,
        None,
        41,
    ]
    assert peer.recover("selected-adb", timeout=5) is True
    assert peer.generation == 2


def test_host_that_ignores_kill_is_not_force_killed_or_started(service):
    establish_failure(service)
    service.kill.side_effect = None
    with pytest.raises(SharedADBError, match="时间预算"):
        service.recovery.recover("selected-adb", timeout=0.5)
    assert service.recovery.generation == 1
    service.kill.assert_called_once()
    assert not any(
        call.args[0][1] == "start-server" for call in service.runner.call_args_list
    )
    assert service.clock.now == pytest.approx(30.5)


def test_server_appearing_between_stop_and_start_is_not_replaced(service):
    establish_failure(service)
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled")] * 3 + [None, 40]
    with pytest.raises(SharedADBError, match="版本不一致"):
        service.recovery.recover("selected-adb", timeout=5)
    service.kill.assert_called_once()
    assert service.recovery.generation == 1
    assert not any(
        call.args[0][1] == "start-server" for call in service.runner.call_args_list
    )


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b"{}",
        b"x" * 1025,
        b'{"generation": -1, "last_attempt": 1}',
        b'{"generation": true, "last_attempt": 1}',
        b'{"generation": 1, "last_attempt": NaN}',
    ],
)
def test_invalid_coordination_state_fails_closed(service, content):
    service.options["lock_path"].write_bytes(b"\0" + content)
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError, match="恢复记录"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def test_invalid_marker_prefix_never_authorizes_restart(service):
    service.options["lock_path"].write_bytes(b"x")
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError, match="恢复记录"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def hold_lock(path, acquired, release):
    recovery = SharedADBRecovery(lock_path=path)
    with recovery._locked(time.monotonic() + 10, None):
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("test lock release timed out")


def test_cross_process_lock_is_bounded_and_releases_without_unlinking(service):
    context = multiprocessing.get_context("spawn")
    acquired, release = context.Event(), context.Event()
    process = context.Process(
        target=hold_lock, args=(service.options["lock_path"], acquired, release)
    )
    process.start()
    try:
        assert acquired.wait(5)
        assert service.recovery.recover("selected-adb", timeout=5) is False
        assert service.clock.now == 0
        service.host.version = None
        with pytest.raises(SharedADBError, match="时间预算"):
            service.recovery.recover("selected-adb", timeout=0.2)
        assert service.clock.now == pytest.approx(0.2)
        assert service.host.mutations == []
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0
    assert service.options["lock_path"].exists()
    service.host.version = 41
    assert service.recovery.recover("selected-adb", timeout=5) is False


def test_healthy_host_never_creates_coordination_marker(service):
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert not service.options["lock_path"].exists()
    assert service.recovery.generation == 0


def test_healthy_invalid_marker_warns_and_invalidates_helpers_once(
    service, monkeypatch
):
    service.options["lock_path"].write_bytes(b"\0partial-json")
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    for _ in range(3):
        assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 1
    assert service.clock.now == 0
    assert service.host.mutations == []
    assert service.options["lock_path"].read_bytes() == b"\0partial-json"
    log.warning.assert_called_once()
    assert "generation=%s" in log.warning.call_args.args[0]


def test_healthy_unreadable_marker_continues_without_mutation(service, monkeypatch):
    service.options["lock_path"].mkdir()
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 1
    assert service.host.mutations == []
    log.warning.assert_called_once()


def test_healthy_unwritable_marker_is_read_without_locking(service, monkeypatch):
    service.options["lock_path"].write_bytes(
        b'\0{"generation": 3, "last_attempt": 1000}'
    )
    monkeypatch.setattr(
        shared.os, "open", Mock(side_effect=PermissionError("read only"))
    )
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 3
    shared.os.open.assert_not_called()
    assert service.host.mutations == []


def test_unknown_generation_episode_then_restart_cannot_reuse_local_generation(service):
    marker = service.options["lock_path"]
    marker.write_bytes(b"\0partial-json")
    assert service.recovery.recover("selected-adb", timeout=5) is False
    helper_generation = service.recovery.generation
    marker.write_bytes(b'\0{"generation": 0, "last_attempt": 1000}')
    service.host.version = None
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation > helper_generation
    assert json.loads(marker.read_bytes()[1:])["generation"] == 1


@pytest.mark.parametrize("response", [None, 40, SharedADBHandshakeTimeout("stalled")])
def test_invalid_marker_never_authorizes_mutation_on_absent_mismatched_stalled_host(
    service, response
):
    service.options["lock_path"].write_bytes(b"\0partial-json")
    service.host.version = response
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def test_attempt_and_verified_outcome_log_generation_and_shared_blast_radius(
    service, monkeypatch
):
    establish_failure(service)
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    assert service.recovery.recover("selected-adb", timeout=5) is True
    log.warning.assert_called_once()
    log.info.assert_called_once()
    assert "其他主机工具" in log.warning.call_args.args[0]
    assert "generation=%s" in log.warning.call_args.args[0]
    assert "generation=%s" in log.info.call_args.args[0]
    assert log.warning.call_args.args[1] == log.info.call_args.args[1] == 1


def test_failed_attempt_logs_bounded_diagnostics_and_generation(service, monkeypatch):
    establish_failure(service)
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    service.kill.side_effect = SharedADBError("x" * 2000)
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    assert log.warning.call_count == 2
    assert log.warning.call_args.args[1] == 1
    assert len(log.warning.call_args.args[2]) == 1024
    log.info.assert_not_called()


def test_windows_empty_file_initializes_lock_byte_and_unlocks(service, monkeypatch):
    calls = []

    def locking(descriptor, mode, count):
        assert os.fstat(descriptor).st_size >= 1
        calls.append((mode, count))

    module = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", module)
    with monkeypatch.context() as windows:
        windows.setattr(shared.os, "name", "nt")
        with pytest.raises(RuntimeError, match="test failure"):
            with service.recovery._locked(5, None):
                raise RuntimeError("test failure")
    assert calls == [(1, 1), (2, 1)]
    assert service.options["lock_path"].read_bytes() == b"\0"


def test_default_lock_path_is_shared_independent_of_binary():
    assert SharedADBRecovery()._lock_path == SharedADBRecovery()._lock_path
