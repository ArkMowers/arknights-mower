"""Hermetic MuMu Pro CLI output and instance identity checks."""

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

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
        self.controller = MuMuProController(run=self.run)
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
