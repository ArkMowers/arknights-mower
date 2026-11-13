"""A manager that cannot be located must fail with an actionable verdict.

The vendor manager owns instance lifecycle and multi-instance queries, and for
MuMu 12 it also owns endpoint identity: the reported ADB port is cross-checked
against the saved creation timestamp. A saved serial is therefore not evidence
that the endpoint still belongs to the selected instance, so a missing manager
must stay terminal instead of silently reconnecting to an unverified address.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_session_tests import ADB, Clock
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.mumu12ipc.paths import resolve_mumu_paths
from arknights_mower.utils.device.screenshot_backend import ScreenshotSession
from arknights_mower.utils.device.session import (
    DeviceSession,
    ReadinessResult,
    RecoveryPolicy,
    SessionFailure,
)
from arknights_mower.utils.device.session_io import (
    ProductionSimulator,
    _CommandWindow,
    _MuMuManager,
)

SERIAL = "127.0.0.1:16384"


def profile(**updates):
    data = {
        "preset_id": "windows.mumu12",
        "instance_id": "0",
        "instance_name": "MuMu-0",
        "last_serial": SERIAL,
        "screenshot_backend": "adb_gzip",
        "touch_backend": "scrcpy",
    }
    data.update(updates)
    return DeviceProfile(**data)


def manager(profile_):
    """Build the real MuMu adapter against one profile, without any I/O."""
    window = _CommandWindow(lambda argv, **kw: "", lambda: 0.0, 10.0)
    return _MuMuManager(profile_, window)


class SpySimulator:
    """The production adapter, with lifecycle calls recorded instead of hidden."""

    def __init__(self):
        self.run = Mock()
        self.inner = ProductionSimulator(run=self.run)
        self.lifecycle = []

    def inspect(self, profile_, timeout):
        return self.inner.inspect(profile_, timeout)

    def start(self, profile_, timeout):
        self.lifecycle.append("start")
        return self.inner.start(profile_, timeout)

    def stop(self, profile_, timeout):
        self.lifecycle.append("stop")
        return self.inner.stop(profile_, timeout)


class ManagerPathTests(unittest.TestCase):
    def test_empty_saved_paths_never_return_a_candidate_that_does_not_exist(self):
        root, executable = resolve_mumu_paths("", "")
        self.assertEqual(executable, "")
        self.assertEqual(root, str(Path()))

    def test_installation_without_any_manager_returns_empty_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "shell").mkdir()
            root, executable = resolve_mumu_paths(folder)
        self.assertEqual(root, folder)
        self.assertEqual(executable, "")

    def test_existing_candidate_is_still_resolved(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "nx_main").mkdir()
            selected = Path(folder, "nx_main", "MuMuManager.exe")
            selected.write_bytes(b"MZ-stub")
            root, executable = resolve_mumu_paths(folder)
        self.assertEqual(root, folder)
        self.assertEqual(Path(executable), selected)

    def test_missing_manager_is_a_binding_failure_that_names_the_searched_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(InstanceBindingError) as raised:
                manager(profile(installation_path=folder))
        self.assertEqual(raised.exception.code, "manager_missing")
        self.assertEqual(raised.exception.fields, ["installation_path", "manager_path"])
        self.assertIn(folder, str(raised.exception))
        self.assertIn("重新检测并选择实例", str(raised.exception))

    def test_empty_saved_path_is_reported_as_not_filled(self):
        with self.assertRaises(InstanceBindingError) as raised:
            manager(profile())
        self.assertEqual(raised.exception.code, "manager_missing")
        self.assertIn("未填写", str(raised.exception))


class ManagerMissingIsTerminalTests(unittest.TestCase):
    def session(self, adb, simulator, profile_, attempts=3):
        bound = DeviceSession(
            adb,
            simulator,
            clock=Clock(),
            policy=RecoveryPolicy(
                attempts=attempts, timeout=180.0, local_wait=10.0, poll_interval=1.0
            ),
        )
        bound.bind(profile_)
        return bound

    def assertNotReady(self, observation):
        self.assertNotEqual(observation.state, "ready")
        self.assertEqual(observation.serial, "")

    def test_observe_reports_the_missing_manager_instead_of_a_saved_serial(self):
        with tempfile.TemporaryDirectory() as folder:
            adb, simulator = ADB(), SpySimulator()
            bound = self.session(adb, simulator, profile(installation_path=folder))
            observation = bound.observe(bound.begin_budget())
        self.assertNotReady(observation)
        self.assertEqual(observation.code, "manager_missing")
        self.assertIn("重新检测并选择实例", observation.message or "")
        self.assertEqual(adb.actions, [])
        self.assertEqual(simulator.lifecycle, [])

    def test_ensure_ready_stays_terminal_and_never_reconnects(self):
        with tempfile.TemporaryDirectory() as folder:
            adb, simulator = ADB(), SpySimulator()
            bound = self.session(adb, simulator, profile(installation_path=folder))
            with self.assertRaises(SessionFailure) as raised:
                bound.ensure_ready()
        self.assertEqual(raised.exception.observation.code, "manager_missing")
        self.assertIn("重新检测", str(raised.exception))
        # An unverified endpoint must never be used for capture or touch.
        self.assertEqual(adb.actions, [])
        self.assertEqual(simulator.lifecycle, [])

    def test_online_saved_serial_does_not_prove_the_binding(self):
        # The reviewer's scenario: the old address belongs to another instance
        # that is online and already booted. It must still not become ready.
        with tempfile.TemporaryDirectory() as folder:
            adb = ADB()
            adb.rows = [(SERIAL, "device")]
            adb.boot = "1"
            simulator = SpySimulator()
            bound = self.session(adb, simulator, profile(installation_path=folder))
            with self.assertRaises(SessionFailure):
                bound.ensure_ready()
        self.assertEqual(adb.actions, [])
        self.assertEqual(simulator.lifecycle, [])

    def test_rejected_instance_index_does_not_fall_back_to_the_saved_serial(self):
        # A non-numeric index is a configuration error, not a capability verdict.
        with tempfile.TemporaryDirectory() as folder:
            bound = self.session(
                ADB(),
                SpySimulator(),
                profile(installation_path=folder, instance_id="not-a-number"),
            )
            observation = bound.observe(bound.begin_budget())
        self.assertNotReady(observation)
        self.assertEqual(observation.code, "binding_failed")
        self.assertIn("实例编号", observation.message or "")

    def test_ldplayer_missing_manager_never_reaches_ready(self):
        # LDPlayer verifies the binding through its own endpoint resolver; a
        # missing manager must not skip that check and trust the saved serial.
        with tempfile.TemporaryDirectory() as folder:
            adb = ADB()
            adb.rows = [(SERIAL, "device")]
            adb.boot = "1"
            simulator = SpySimulator()
            bound = self.session(
                adb,
                simulator,
                profile(preset_id="windows.ldplayer9", installation_path=folder),
            )
            observation = bound.observe(bound.begin_budget())
        self.assertNotReady(observation)
        self.assertEqual(observation.code, "manager_missing")
        self.assertEqual(simulator.lifecycle, [])

    def test_nox_missing_manager_never_reaches_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            adb = ADB()
            adb.rows = [(SERIAL, "device")]
            adb.boot = "1"
            simulator = SpySimulator()
            bound = self.session(
                adb,
                simulator,
                profile(preset_id="windows.nox", installation_path=folder),
            )
            observation = bound.observe(bound.begin_budget())
        self.assertNotReady(observation)
        self.assertEqual(observation.code, "manager_missing")


class ScreenshotFailureCodeTests(unittest.TestCase):
    def test_session_failure_reports_its_observation_code(self):
        observation = ReadinessResult(
            "offline", "", code="binding_failed", message="找不到已绑定实例的管理程序"
        )
        session = ScreenshotSession(profile(), "windows")
        with patch(
            "arknights_mower.utils.device.screenshot_backend.logger.warning"
        ) as warning:
            session._report_failure(
                "recover", SessionFailure(observation, "找不到"), 0.0
            )
        self.assertEqual(warning.call_args.args[3], "binding_failed")

    def test_cause_without_a_code_still_names_its_class(self):
        session = ScreenshotSession(profile(), "windows")
        with patch(
            "arknights_mower.utils.device.screenshot_backend.logger.warning"
        ) as warning:
            session._report_failure("capture", TimeoutError("timed out"), 0.0)
        self.assertEqual(warning.call_args.args[3], "TimeoutError")


if __name__ == "__main__":
    unittest.main()
