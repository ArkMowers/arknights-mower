"""Offline regressions for native gestures and simulator command isolation."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.adb_client.core import query_mumu_adb_port
from arknights_mower.utils.device.mumu12ipc.core import MuMu12IPC
from arknights_mower.utils.device.mumu_info import (
    mumu_endpoint,
    normalize_mumu_endpoint,
    select_mumu_instance,
)
from arknights_mower.utils.device.session_io import (
    MANAGED_INSTANCE_PRESETS,
    ProductionSimulator,
)
from arknights_mower.utils.simulator import build_command_set, run_command


def test_native_multisegment_swipe_keeps_one_touch_sequence():
    ipc = object.__new__(MuMu12IPC)
    ipc.touch_down = Mock()
    ipc.touch_up = Mock()
    with patch("arknights_mower.utils.device.mumu12ipc.core.time.sleep"):
        ipc.swipe_ext([(1, 2), (3, 4), (5, 6)], [100, 100])
    assert ipc.touch_down.call_args_list[0].args == (1, 2)
    assert ipc.touch_down.call_args_list[-1].args == (5, 6)
    ipc.touch_up.assert_called_once_with()


@pytest.mark.parametrize("product", ["ReDroid", "MuMuPro", "Genymotion"])
def test_simulator_identifiers_are_literal_arguments(product):
    identifier = "instance; echo unexpected"
    commands = build_command_set(product, identifier)
    for command in (commands.start, commands.stop):
        assert isinstance(command, list)
        assert identifier in command
        with patch("arknights_mower.utils.simulator.subprocess.run") as run:
            run.return_value.returncode = 0
            assert run_command(command, "", 10, True)
        assert run.call_args.kwargs["shell"] is False


def test_simulator_option_cannot_be_an_instance_identifier():
    with pytest.raises(ValueError):
        build_command_set("ReDroid", "--all")


def test_manager_executable_with_spaces_is_resolved_without_a_shell(tmp_path):
    folder = tmp_path / "MuMu installation"
    folder.mkdir()
    executable = folder / "MuMuManager.exe"
    executable.touch()
    with patch("arknights_mower.utils.simulator.subprocess.run") as run:
        run.return_value.returncode = 0
        assert run_command([executable.name, "info"], str(folder), 5, True)
    assert run.call_args.args[0] == [str(executable.resolve()), "info"]
    assert run.call_args.kwargs["shell"] is False


@pytest.mark.parametrize("shape", ["direct", "keyed", "list"])
def test_mumu_selection_checks_id_and_name_for_every_shape(shape):
    entry = {"index": 2, "name": "chosen", "adb_port": 16384}
    payload = {"direct": entry, "keyed": {"2": entry}, "list": [entry]}[shape]
    output = json.dumps(payload)
    assert select_mumu_instance(output, "2", "chosen") == ("2", entry)
    assert select_mumu_instance(output, "", "chosen") == ("2", entry)
    for index, name in [("", ""), ("3", "chosen"), ("2", "other")]:
        with pytest.raises(ValueError):
            select_mumu_instance(output, index, name)


@pytest.mark.parametrize(
    "output",
    [
        '[{"index":2},{"index":2}]',
        '{"2":{"index":3}}',
        '{"2":{},"2":{}}',
        '{"2":{"name":"same"},"3":{"name":"same"}}',
    ],
)
def test_ambiguous_mumu_identity_is_rejected(output):
    with pytest.raises(ValueError):
        select_mumu_instance(
            output, "" if "same" in output else "2", "same" if "same" in output else ""
        )


@pytest.mark.parametrize("port", [0, 65536, True, "-1", "655360000", None])
def test_invalid_manager_ports_are_rejected(port):
    with pytest.raises(ValueError):
        mumu_endpoint({"adb_port": port})


def test_loopback_aliases_and_ipv6_format_are_consistent():
    endpoint = mumu_endpoint({"adb_port": 16384, "adb_host_ip": "::1"})
    assert endpoint == "[::1]:16384"
    assert normalize_mumu_endpoint(endpoint) == normalize_mumu_endpoint(
        "localhost:16384"
    )
    assert normalize_mumu_endpoint(endpoint) != normalize_mumu_endpoint(
        "192.0.2.1:16384"
    )


def test_legacy_manager_timeout_retains_the_selected_endpoint():
    import subprocess

    simulator = SimpleNamespace(name="MuMu12", simulator_folder="MuMu", index="2")
    with (
        patch("os.path.isfile", return_value=True),
        patch(
            "arknights_mower.utils.device.adb_client.core.subprocess.run",
            side_effect=subprocess.TimeoutExpired("MuMuManager.exe", 5),
        ),
    ):
        assert query_mumu_adb_port(simulator) is None


@pytest.mark.parametrize("start", [False, True])
def test_retired_mumu_lifecycle_never_spawns_or_kills(tmp_path, start):
    player = tmp_path / "NemuPlayer.exe"
    player.touch()
    profile = DeviceProfile(
        preset_id="windows.mumu6", manager_path=str(player), instance_id="1"
    )
    run, spawn = Mock(), Mock()
    simulator = ProductionSimulator(run=run, spawn=spawn)
    assert (simulator.start if start else simulator.stop)(profile, 5) is False
    run.assert_not_called()
    spawn.assert_not_called()
    assert "windows.mumu6" not in MANAGED_INSTANCE_PRESETS
    with pytest.raises(ValueError, match="不支持"):
        build_command_set("MuMu6", "1")


def test_retired_mumu_observation_does_not_invent_an_endpoint(tmp_path):
    player = tmp_path / "NemuPlayer.exe"
    player.touch()
    profile = DeviceProfile(
        preset_id="windows.mumu6", manager_path=str(player), instance_id="0"
    )
    run = Mock()
    observed = ProductionSimulator(run=run, spawn=Mock()).inspect(profile, 5)
    assert observed.state == "unknown"
    assert not observed.serial
    run.assert_not_called()
