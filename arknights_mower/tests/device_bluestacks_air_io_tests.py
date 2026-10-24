"""Air fixtures run through DeviceControl with real preflight/transport policy."""

import gzip
import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_session_tests import Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import (
    ProductionSessionADB,
    ProductionSimulator,
)

SERIAL = "127.0.0.1:5555"
SCENARIOS = json.loads(
    (Path(__file__).parent / "fixtures/bluestacks_air.json").read_text(encoding="utf-8")
)


class AirCommandFixture:
    def __init__(self, root):
        self.app = Path(root) / "BlueStacks.app"
        self.adb = self.app / "Contents/MacOS/hd-adb"
        self.adb.parent.mkdir(parents=True)
        self.adb.touch()
        (self.app / "Contents/Info.plist").write_bytes(b"fixture bundle")
        self.conf = Conf(
            device={
                "preset_id": "macos.bluestacks_air",
                "installation_path": str(self.app),
                "screenshot_backend": "adb_gzip",
                "last_serial": "",
            }
        )
        self.calls = []
        self.rows = []
        self.after = [(SERIAL, "device")]
        self.reply = f"connected to {SERIAL}"
        self.boot = "1"
        self.size = "Physical size: 1920x1080"
        self.packages = "package:com.hypergryph.arknights"
        self.frame_size = (1920, 1080)
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(ProductionPreflightIO()),
            discovery=DiscoveryService(DiscoveryIO()),
        )

    def capture_adb_frame(self, adb_path, serial):
        """Stand in for the gzip capture, which opens its own ADB-server socket.

        The frame keeps the declared size so the size gate, not this seam, decides
        whether the capture is acceptable.
        """
        width, height = self.frame_size
        return np.zeros((height, width, 3), np.uint8)

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] != str(self.adb):
            raise OSError("unknown executable")
        if argv[1:] == ["version"]:
            output = "Android Debug Bridge version 1.0.41"
        elif argv[1:] == ["devices"]:
            output = "List of devices attached\n" + "\n".join(
                f"{serial}\t{state}" for serial, state in self.rows
            )
        elif argv[1:] == ["connect", SERIAL]:
            self.rows = self.after
            output = self.reply
        elif argv[1:] == ["disconnect", SERIAL]:
            output = f"disconnected {SERIAL}"
        elif argv[1:3] == ["-s", SERIAL]:
            if argv[3:] == ["shell", "getprop", "sys.boot_completed"]:
                output = self.boot
            elif argv[3:] == ["shell", "wm", "size"]:
                output = self.size
            elif argv[3:] == ["shell", "pm", "list", "packages"]:
                output = self.packages
            elif argv[3:] == ["exec-out", "screencap 2>/dev/null | gzip -1"]:
                width, height = self.frame_size
                output = gzip.compress(
                    struct.pack("<III", width, height, 1) + bytes(width * height * 4)
                )
            else:
                raise AssertionError(argv)
        else:
            raise AssertionError(argv)
        if isinstance(output, str):
            output = output.encode()
        return subprocess.CompletedProcess(argv, 0, output, b"")


class BlueStacksAirIOTests(unittest.TestCase):
    def setUp(self):
        self.fixture = AirCommandFixture(
            self.enterContext(tempfile.TemporaryDirectory())
        )
        self.enterContext(patch("platform.system", return_value="Darwin"))
        self.enterContext(
            patch("subprocess.Popen", side_effect=AssertionError("unexpected process"))
        )
        for target in (
            "arknights_mower.utils.device.preflight_io.run_command",
            "arknights_mower.utils.device.adb_client.server.run_command",
            "arknights_mower.utils.device.session_io.run_command",
        ):
            self.enterContext(patch(target, side_effect=self.fixture.run))
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=None,
            )
        )
        # ADB gzip capture uses sockets separately from CLI command execution.
        # Inject the frame instead of reaching a real server.
        self.enterContext(
            patch(
                "arknights_mower.utils.device.preflight_io.capture_adb_frame",
                side_effect=self.fixture.capture_adb_frame,
            )
        )

    def test_candidate_requires_successful_connect_response_even_if_device_appears(
        self,
    ):
        self.fixture.reply = "failed to connect"
        result = self.fixture.control.discover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "air_adb_unavailable")
        self.assertFalse(any("-s" in argv for argv, _ in self.fixture.calls))

    def test_a_new_device_during_candidate_connection_requires_explicit_serial(self):
        self.fixture.after = [("phone", "device"), (SERIAL, "device")]
        result = self.fixture.control.discover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "multiple_devices")
        self.assertEqual(result.serial, "")
        self.assertEqual(result.profile_patch, {})

    def test_completed_connection_still_requires_every_read_only_preflight_gate(self):
        fixture = self.fixture
        for field, value, code in (
            ("boot", "0", "boot_incomplete"),
            # Only an unreadable or ambiguous size still stops before capture.
            ("size", "Physical size: not-a-size", "invalid_size"),
            (
                "size",
                "Physical size: 1920x1080\nOverride size: unavailable",
                "invalid_size",
            ),
            ("frame_size", (1280, 720), "frame_size_mismatch"),
            ("packages", "", "package_missing"),
            (
                "packages",
                "package:com.hypergryph.arknights\npackage:com.hypergryph.arknights.bilibili",
                "package_ambiguous",
            ),
        ):
            with self.subTest(code=code, field=field):
                original = getattr(fixture, field)
                setattr(fixture, field, value)
                try:
                    result = fixture.control.preflight()
                    self.assertFalse(result.ok)
                    self.assertEqual(result.error.code, code)
                    self.assertEqual(result.profile_patch, {})
                finally:
                    setattr(fixture, field, original)

    def test_multiple_devices_only_allow_the_explicit_target(self):
        self.fixture.rows = [("phone", "device"), (SERIAL, "device")]
        self.fixture.conf.device.last_serial = SERIAL
        result = self.fixture.control.preflight()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, SERIAL)
        self.assertFalse(any("phone" in argv for argv, _ in self.fixture.calls))
        self.assertFalse(any("connect" in argv for argv, _ in self.fixture.calls))

    def test_start_and_failed_recovery_never_use_simulator_lifecycle_or_another_device(
        self,
    ):
        fixture = self.fixture
        fixture.conf.device.last_serial = SERIAL
        fixture.rows = [(SERIAL, "device"), ("phone", "device")]
        session = DeviceSession(
            ProductionSessionADB(
                probe=lambda timeout: None,
                # Keep the first-frame probe off a live server; the decode seam is
                # injected so this test only exercises the session lifecycle.
                frame=lambda *args: (1920, 1080),
            ),
            ProductionSimulator(),
            clock=Clock(),
            policy=RecoveryPolicy(attempts=1, timeout=12, local_wait=1),
        )
        control = DeviceControl(
            lambda: fixture.conf,
            Adapter(),
            preflight=PreflightService(ProductionPreflightIO()),
            discovery=DiscoveryService(DiscoveryIO()),
            session=session,
        )
        self.addCleanup(control.close)
        result = control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, SERIAL)
        self.assertEqual(session.actions, 0)
        fixture.rows = fixture.after = [("phone", "device")]
        recovered = control.recover()
        self.assertFalse(recovered.ok)
        self.assertEqual(session.actions, 1)
        for argv, _ in fixture.calls:
            self.assertEqual(argv[0], str(fixture.adb))
            self.assertNotIn("phone", argv)
            self.assertNotIn("kill-server", argv)

    def test_fixtures_cover_missing_disabled_stale_ready_and_multiple_devices(self):
        for name, row in SCENARIOS.items():
            with self.subTest(name=name):
                fixture = self.fixture
                fixture.conf.device.installation_path = str(
                    fixture.app if row["installed"] else fixture.app / "missing"
                )
                fixture.rows, fixture.after = row["before"], row["after"]
                fixture.reply = row["reply"]
                fixture.calls.clear()
                before = fixture.conf.model_dump()
                result = fixture.control.discover()
                self.assertEqual(result.ok, row["ok"], result.error)
                if not row["ok"]:
                    self.assertEqual(result.error.code, row["code"])
                    self.assertEqual(result.error.action, "retry")
                    self.assertEqual(result.profile_patch, {})
                else:
                    self.assertEqual(result.serial, SERIAL)
                    self.assertEqual(result.adb_path, str(fixture.adb))
                    self.assertEqual(result.observations["frame"], [1920, 1080])
                    self.assertEqual(result.game_package, "com.hypergryph.arknights")
                self.assertEqual(fixture.conf.model_dump(), before)
                for argv, options in fixture.calls:
                    self.assertIsInstance(argv, list)
                    self.assertGreater(options["timeout"], 0)
                    self.assertLessEqual(options["timeout"], 10)
                    self.assertNotIn("shell", options)
                    self.assertNotIn("phone", argv)


if __name__ == "__main__":
    unittest.main()
