"""Resource observations never recommend a mode and remain bounded to the target."""

import subprocess
from unittest.mock import patch

import pytest

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO


@pytest.mark.parametrize("cpu,cores", [("0", 1), ("0-3", 4), ("0-1,4,6-7", 5)])
def test_performance_io_reads_guest_cpu_and_memory_with_pinned_adb(cpu, cores):
    io = ProductionPreflightIO()
    with patch.object(
        io, "_run_adb", return_value=f"{cpu}\nMemTotal: 3932160 kB\n".encode()
    ) as run:
        assert io.performance_info("chosen-adb", "chosen-instance") == {
            "cpu_cores": cores,
            "memory_mb": 3840,
        }
    assert run.call_args.args[0] == [
        "chosen-adb",
        "-s",
        "chosen-instance",
        "shell",
        "cat /sys/devices/system/cpu/online; cat /proc/meminfo",
    ]
    assert run.call_args.kwargs["maximum"] == 3


@pytest.mark.parametrize(
    "output",
    [
        b"",
        b"0-3\nMemTotal: 0 kB",
        b"oops\nMemTotal: 4096000 kB",
        b"3-0\nMemTotal: 4096000 kB",
        b"0-999999999\nMemTotal: 4096000 kB",
        b"0-3,2\nMemTotal: 4096000 kB",
        b"0-3\nMemTotal: unknown kB",
        b"0-3\nMemAvailable: 4096000 kB",
        b"0-3\nMemTotal: 1024 MB",
    ],
)
def test_invalid_performance_information_is_rejected(output):
    io = ProductionPreflightIO()
    with patch.object(io, "_run_adb", return_value=output), pytest.raises(ValueError):
        io.performance_info("adb", "chosen")


def test_performance_io_uses_guarded_command_and_callers_remaining_budget():
    io = ProductionPreflightIO()
    with (
        patch("arknights_mower.utils.device.preflight_io.run_adb") as run,
        device_io_budget(lambda: 0.5),
    ):
        run.return_value.stdout = b"0-3\nMemTotal: 3932160 kB\n"
        io.performance_info("adb", "chosen")
    assert run.call_args.kwargs["timeout"] == 0.5
    assert run.call_args.args[0][:3] == ["adb", "-s", "chosen"]


@pytest.mark.parametrize(
    "cores,memory",
    [(1, 8192), (8, 1791), (2, 1792), (3, 8192), (4, 3583), (4, 3584), (8, 16384)],
)
def test_preflight_only_displays_resources_without_recommending_or_changing_profile(
    cores, memory
):
    io = PreflightIO()
    profile = DeviceProfile(last_serial="USB-123")
    before = profile.model_dump()
    with patch.object(
        io,
        "performance_info",
        create=True,
        return_value={"cpu_cores": cores, "memory_mb": memory},
    ) as read:
        result = PreflightService(io).check(profile)
    assert result.ok
    assert result.observations["performance"] == {
        "status": "available",
        "cpu_cores": cores,
        "memory_mb": memory,
    }
    read.assert_called_once_with(result.adb_path, "USB-123")
    assert profile.model_dump() == before


@pytest.mark.parametrize(
    "failure", [OSError(), subprocess.TimeoutExpired("adb", 3), ValueError()]
)
def test_unavailable_performance_information_does_not_fail_readiness(failure):
    io = PreflightIO()
    with patch.object(io, "performance_info", create=True, side_effect=failure):
        result = PreflightService(io).check(DeviceProfile(last_serial="USB-123"))
    assert result.ok
    assert result.error is None
    assert result.observations["performance"]["status"] == "unavailable"
    assert "recommended_mode" not in result.observations["performance"]


@pytest.mark.parametrize(
    "state,boot", [("offline", "1"), ("device", "0"), ("unauthorized", "1")]
)
def test_unready_targets_never_receive_performance_queries(state, boot):
    io = PreflightIO()
    io.targets, io.boot = [("USB-123", state)], boot
    with patch.object(io, "performance_info", create=True) as read:
        result = PreflightService(io).check(DeviceProfile(last_serial="USB-123"))
    assert not result.ok
    read.assert_not_called()
    assert "performance" not in result.observations


def test_performance_cancellation_propagates():
    io = PreflightIO()
    with (
        patch.object(io, "performance_info", create=True, side_effect=MowerExit()),
        pytest.raises(MowerExit),
    ):
        PreflightService(io).check(DeviceProfile(last_serial="USB-123"))
