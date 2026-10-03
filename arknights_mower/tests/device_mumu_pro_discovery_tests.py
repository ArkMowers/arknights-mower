"""Hermetic MuMu Pro CLI output and instance identity checks."""

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.mumu_pro import (
    MuMuProController,
    parse_mumu_pro_info,
)


def instance(index, port):
    return {
        "index": index,
        "name": f"VM {index}",
        "bundle_path": f"/tmp/mumu-test/vms/{index}",
        "state": "running",
        "adb_port": port,
        "pid": 100 + index,
    }


def output(rows, *, selected=False):
    payload = rows[0] if selected else {"count": len(rows), "results": rows}
    return json.dumps({"errcode": 0, "message": "", "return": payload}).encode()


class MuMuProDiscoveryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = Path(directory.name) / "MuMuPlayer.app"
        manager = self.app / "Contents/MacOS/mumutool"
        manager.parent.mkdir(parents=True)
        manager.write_bytes(b"stub")
        manager.chmod(0o755)
        self.manager = str(manager)
        self.rows = [instance(0, 16384), instance(1, 16416)]

        def run(argv, **kwargs):
            selected = argv[-1] != "all"
            rows = [row for row in self.rows if str(row["index"]) == argv[-1]]
            if not selected:
                rows = self.rows
            return subprocess.CompletedProcess(
                argv, 0, output(rows, selected=selected), b""
            )

        self.run = Mock(side_effect=run)
        self.connect = MagicMock()
        self.controller = MuMuProController(run=self.run, connect=self.connect)
        self.profile = DeviceProfile(
            preset_id="macos.mumu_pro", manager_path=self.manager
        )

    def test_lists_two_distinct_instances_without_starting_them(self):
        result = self.controller.discover(self.profile)
        items = result["installations"][0]["instances"]
        self.assertEqual([item["instance_id"] for item in items], ["0", "1"])
        self.assertEqual(
            [item["serial"] for item in items],
            ["127.0.0.1:16384", "127.0.0.1:16416"],
        )
        self.assertNotEqual(
            items[0]["topology_fingerprint"], items[1]["topology_fingerprint"]
        )
        self.run.assert_called_once()
        self.assertEqual(
            self.run.call_args.args[0],
            [str(Path(self.manager).resolve()), "info", "all"],
        )
        self.assertLessEqual(self.run.call_args.kwargs["timeout"], 3)

    def test_running_before_adb_listener_is_ready_waits_without_endpoint(self):
        profile = self.selected_profile()
        self.connect.side_effect = ConnectionRefusedError()
        observed = self.controller.inspect(profile, 5)
        self.assertEqual(observed.state, "starting")
        self.assertIsNone(observed.serial)
        self.assertEqual(self.connect.call_args.args[0], ("127.0.0.1", 16416))
        self.assertLessEqual(self.connect.call_args.kwargs["timeout"], 1)
        self.connect.side_effect = None
        self.assertEqual(self.controller.inspect(profile, 5).serial, "127.0.0.1:16416")

    def test_bound_instance_is_rechecked_and_port_may_change(self):
        binding = self.controller.discover(self.profile)["installations"][0][
            "instances"
        ][0]
        profile = self.profile.model_copy(
            update={
                "instance_id": binding["instance_id"],
                "topology_fingerprint": binding["topology_fingerprint"],
            }
        )
        self.rows[0]["adb_port"] = 18000
        observed = self.controller.inspect(profile, 5)
        self.assertEqual(observed.serial, "127.0.0.1:18000")
        self.assertEqual(observed.state, "running")
        self.assertEqual(
            self.run.call_args.args[0], [str(Path(self.manager).resolve()), "info", "0"]
        )

    def test_recreated_index_rejects_endpoint_before_adb(self):
        binding = self.controller.discover(self.profile)["installations"][0][
            "instances"
        ][0]
        profile = self.profile.model_copy(
            update={
                "instance_id": "0",
                "topology_fingerprint": binding["topology_fingerprint"],
            }
        )
        self.rows[0]["bundle_path"] = "/tmp/mumu-test/recreated/0"
        with self.assertRaises(InstanceBindingError) as raised:
            self.controller.inspect(profile, 5)
        self.assertEqual(raised.exception.code, "mumu_pro_binding_changed")

    def test_manual_serial_without_fingerprint_does_not_query_manager(self):
        observed = self.controller.inspect(self.profile, 5)
        self.assertEqual(observed.state, "unknown")
        self.run.assert_not_called()

    def selected_profile(self):
        row = self.controller.discover(self.profile)["installations"][0]["instances"][1]
        self.run.reset_mock()
        return self.profile.model_copy(
            update={
                "instance_id": row["instance_id"],
                "topology_fingerprint": row["topology_fingerprint"],
            }
        )

    def test_lifecycle_verifies_and_operates_only_selected_instance(self):
        profile = self.selected_profile()
        self.rows[1]["state"] = "stopped"
        query = self.run.side_effect

        def run(argv, **kwargs):
            if argv[1] == "info":
                return query(argv, **kwargs)
            self.assertEqual(argv[-1], "1")
            return subprocess.CompletedProcess(argv, 0, b'{"errcode":0}', b"")

        self.run.side_effect = run
        self.assertTrue(self.controller.start(profile, 8))
        self.rows[1]["state"] = "running"
        self.assertTrue(self.controller.stop(profile, 8))
        self.assertEqual(
            [call.args[0][1:] for call in self.run.call_args_list],
            [
                ["info", "1"],
                ["open", "1"],
                ["info", "1"],
                ["close", "1"],
            ],
        )

    def test_invalid_or_unverified_targets_never_send_manager_commands(self):
        profile = self.selected_profile()
        for identifier in ("all", "0,1", "-1", "01", "１", ""):
            with (
                self.subTest(identifier=identifier),
                self.assertRaises(InstanceBindingError),
            ):
                self.controller.start(
                    profile.model_copy(update={"instance_id": identifier}), 5
                )
        with self.assertRaises(InstanceBindingError):
            self.controller.stop(self.profile, 5)
        self.run.assert_not_called()

    def test_changed_identity_prevents_lifecycle_commands(self):
        profile = self.selected_profile()
        self.rows[1]["bundle_path"] = "/tmp/recreated/1"
        with self.assertRaises(InstanceBindingError):
            self.controller.stop(profile, 5)
        self.assertEqual(
            [call.args[0][1] for call in self.run.call_args_list], ["info"]
        )

    def test_instance_error_preserves_inventory_and_blocks_lifecycle(self):
        profile = self.selected_profile()
        self.rows[1]["state"] = "error"
        result = self.controller.discover(self.profile)
        self.assertEqual(len(result["installations"][0]["instances"]), 2)
        self.run.reset_mock()
        for action in (
            self.controller.inspect,
            self.controller.start,
            self.controller.stop,
        ):
            with self.assertRaises(InstanceBindingError) as raised:
                action(profile, 5)
            self.assertEqual(raised.exception.code, "mumu_pro_instance_error")
        self.assertEqual(
            [call.args[0][1] for call in self.run.call_args_list], ["info"] * 3
        )

    def test_running_instance_start_is_idempotent(self):
        profile = self.selected_profile()
        self.assertTrue(self.controller.start(profile, 5))
        self.run.assert_called_once()
        self.assertEqual(self.run.call_args.args[0][1], "info")

    def test_failed_or_uncertain_command_is_not_replayed(self):
        profile = self.selected_profile()
        self.rows[1]["state"] = "stopped"
        query = self.run.side_effect
        failures = [
            b'{"errcode":false}',
            b'{"errcode":1}',
            b"invalid",
            subprocess.TimeoutExpired("mumutool", 5),
            b"x" * (1024 * 1024 + 1),
        ]
        for failure in failures:
            with self.subTest(failure=str(failure)[:30]):
                self.run.reset_mock()

                def run(argv, **kwargs):
                    if argv[1] == "info":
                        return query(argv, **kwargs)
                    if isinstance(failure, Exception):
                        raise failure
                    return subprocess.CompletedProcess(argv, 0, failure, b"")

                self.run.side_effect = run
                with self.assertRaises(InstanceBindingError) as raised:
                    self.controller.start(profile, 5)
                self.assertEqual(raised.exception.code, "mumu_pro_action_failed")
                self.assertEqual(self.run.call_count, 2)

    def test_validation_and_action_share_one_deadline(self):
        profile = self.selected_profile()
        self.rows[1]["state"] = "stopped"
        ticks = iter([0, 0, 4])
        self.controller._monotonic = lambda: next(ticks)
        self.run.side_effect = [
            subprocess.CompletedProcess(
                [], 0, output([self.rows[1]], selected=True), b""
            ),
            subprocess.CompletedProcess([], 0, b'{"errcode":0}', b""),
        ]
        self.assertTrue(self.controller.start(profile, 5))
        self.assertEqual(self.run.call_args.kwargs["timeout"], 1)

    def test_closed_manager_application_is_opened_once_without_vm_command(self):
        (self.app / "Contents/Info.plist").touch()
        self.run.side_effect = [
            subprocess.CalledProcessError(1, "port", stderr=b"Error: invalidPort\n"),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, output(self.rows), b""),
        ]
        self.assertTrue(self.controller.prepare_manager(self.profile, 6))
        self.assertEqual(
            [call.args[0] for call in self.run.call_args_list],
            [
                [str(Path(self.manager).resolve()), "port"],
                ["/usr/bin/open", "-a", str(self.app.resolve())],
                [str(Path(self.manager).resolve()), "info", "all"],
            ],
        )

    def test_running_manager_is_not_reopened(self):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, b'{"server-port":21001}', b""),
            subprocess.CompletedProcess([], 0, output([]), b""),
        ]
        self.assertTrue(self.controller.prepare_manager(self.profile, 6))
        self.assertEqual(
            [call.args[0][1:] for call in self.run.call_args_list],
            [["port"], ["info", "all"]],
        )

    def test_published_port_waits_for_valid_instance_query_before_ready(self):
        ticks = [0]
        self.controller._monotonic = lambda: ticks[0]
        self.controller._sleep = lambda interval: ticks.__setitem__(
            0, ticks[0] + interval
        )
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, b'{"server-port":21001}', b""),
            subprocess.CalledProcessError(1, "info", stderr=b"Error: serverNotReady"),
            subprocess.CompletedProcess([], 0, output([]), b""),
        ]
        self.assertTrue(self.controller.prepare_manager(self.profile, 6))
        self.assertEqual(self.run.call_count, 3)
        self.assertGreater(ticks[0], 0)

    def test_cold_manager_waits_for_instances_after_transient_empty_inventory(self):
        (self.app / "Contents/Info.plist").touch()
        ticks = [0]
        self.controller._monotonic = lambda: ticks[0]
        self.controller._sleep = lambda interval: ticks.__setitem__(
            0, ticks[0] + interval
        )
        self.run.side_effect = [
            subprocess.CalledProcessError(1, "port", stderr=b"Error: invalidPort"),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, output([]), b""),
            subprocess.CompletedProcess([], 0, output(self.rows), b""),
        ]
        self.assertTrue(self.controller.prepare_manager(self.profile, 6))
        self.assertEqual(self.run.call_count, 4)
        self.assertGreater(ticks[0], 0)

    def test_manager_readiness_timeout_never_replays_application_open(self):
        (self.app / "Contents/Info.plist").touch()
        ticks = [0]
        self.controller._monotonic = lambda: ticks[0]
        self.controller._sleep = lambda interval: ticks.__setitem__(
            0, ticks[0] + interval
        )

        def run(argv, **kwargs):
            if argv[0] == "/usr/bin/open":
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            raise subprocess.CalledProcessError(1, argv, stderr=b"Error: invalidPort")

        self.run.side_effect = run
        with self.assertRaises(InstanceBindingError):
            self.controller.prepare_manager(self.profile, 1)
        self.assertEqual(
            sum(call.args[0][0] == "/usr/bin/open" for call in self.run.call_args_list),
            1,
        )
        self.assertLessEqual(ticks[0], 1)

    def test_invalid_port_output_never_opens_application(self):
        for output in (b'{"server-port":false}', b'{"server-port":0}', b"unknown"):
            with self.subTest(output=output):
                self.run.reset_mock()
                self.run.side_effect = None
                self.run.return_value = subprocess.CompletedProcess([], 0, output, b"")
                with self.assertRaises(InstanceBindingError):
                    self.controller.prepare_manager(self.profile, 6)
                self.run.assert_called_once()

    def test_uncertain_application_open_is_not_replayed(self):
        (self.app / "Contents/Info.plist").touch()
        self.run.side_effect = [
            subprocess.CalledProcessError(1, "port", stderr=b"Error: invalidPort\n"),
            subprocess.TimeoutExpired("open", 3),
        ]
        with self.assertRaises(InstanceBindingError):
            self.controller.prepare_manager(self.profile, 6)
        self.assertEqual(self.run.call_count, 2)

    def test_read_only_closed_manager_reports_actionable_error(self):
        self.run.side_effect = subprocess.CalledProcessError(
            1, "info", stderr=b"Error: invalidPort\n"
        )
        with self.assertRaises(InstanceBindingError) as raised:
            self.controller.discover(self.profile)
        self.assertEqual(raised.exception.code, "mumu_pro_manager_stopped")
        self.run.assert_called_once()

    def test_starting_instance_without_port_stays_bound_without_exposing_endpoint(self):
        profile = self.selected_profile()
        for port in (None, 0):
            self.rows[1].update(state="starting", adb_port=port)
            observed = self.controller.inspect(profile, 3)
            self.assertEqual(observed.state, "starting")
            self.assertIsNone(observed.serial)
        for port in (False, -1, 70000, "16384"):
            self.rows[1]["adb_port"] = port
            with self.assertRaises(InstanceBindingError):
                self.controller.inspect(profile, 3)

    def test_malformed_and_ambiguous_output_fails_closed(self):
        cases = [
            b"not json",
            json.dumps({"errcode": 42001, "return": {}}).encode(),
            json.dumps({"errcode": False, "return": {}}).encode(),
            json.dumps(
                {"errcode": 0, "return": {"count": 2, "results": [self.rows[0]]}}
            ).encode(),
            output([self.rows[0], {**self.rows[1], "index": 0}]),
            output([self.rows[0], {**self.rows[1], "adb_port": 16384}]),
            output(
                [
                    self.rows[0],
                    {**self.rows[1], "bundle_path": self.rows[0]["bundle_path"]},
                ]
            ),
            output([{**self.rows[0], "bundle_path": "relative"}]),
        ]
        for value in cases:
            with self.subTest(value=value[:40]), self.assertRaises(ValueError):
                parse_mumu_pro_info(value)

    def test_selected_query_rejects_another_instance(self):
        with self.assertRaises(ValueError):
            parse_mumu_pro_info(output([self.rows[1]], selected=True), selected_id="0")
