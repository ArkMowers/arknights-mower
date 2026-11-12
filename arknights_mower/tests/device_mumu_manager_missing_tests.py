"""A MuMu manager that cannot be located must lower capability, not block ADB.

The vendor manager owns instance lifecycle and multi-instance queries. The
capture, touch and frame gates read the ADB transport, so a binding whose manager
is missing (empty saved path, MuMu moved by its own upgrade, stale install
directory) still has to reach the device when its serial is known.
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
    ADB_ONLY_FALLBACK_CODES,
    RETRYABLE_WAIT_CODES,
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


class DegradedObservationTests(unittest.TestCase):
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

    def test_missing_manager_degrades_to_the_saved_serial(self):
        with tempfile.TemporaryDirectory() as folder:
            adb, simulator = ADB(), SpySimulator()
            bound = self.session(adb, simulator, profile(installation_path=folder))
            observation = bound.observe(bound.begin_budget())
        self.assertEqual(observation.code, "manager_unavailable")
        self.assertEqual(observation.serial, SERIAL)
        self.assertEqual(observation.state, "absent")
        self.assertEqual(observation.instance_state, "unknown")
        self.assertIn("未找到模拟器管理程序", observation.message or "")
        self.assertEqual(bound.last.code, "manager_unavailable")

    def test_degraded_binding_is_retryable_so_a_reconnect_can_run(self):
        self.assertEqual(
            ADB_ONLY_FALLBACK_CODES, frozenset({"manager_missing", "binding_failed"})
        )
        self.assertIn("manager_unavailable", RETRYABLE_WAIT_CODES)
        with tempfile.TemporaryDirectory() as folder:
            bound = self.session(
                ADB(), SpySimulator(), profile(installation_path=folder)
            )
            observation = bound.observe(bound.begin_budget())
            # No SessionFailure: the transaction keeps its budget for the transport.
            bound._check_observation(observation)

    def test_other_binding_inspection_failures_also_degrade(self):
        # A rejected instance index is not a manager-capability verdict, but it is
        # still no reason to abandon a device whose serial is known.
        with tempfile.TemporaryDirectory() as folder:
            bound = self.session(
                ADB(),
                SpySimulator(),
                profile(installation_path=folder, instance_id="not-a-number"),
            )
            observation = bound.observe(bound.begin_budget())
        self.assertEqual(observation.code, "manager_unavailable")
        self.assertEqual(observation.serial, SERIAL)
        self.assertIn("实例编号", observation.message or "")

    def test_manual_serial_takes_precedence_over_the_saved_one(self):
        with tempfile.TemporaryDirectory() as folder:
            bound = self.session(
                ADB(),
                SpySimulator(),
                profile(installation_path=folder, mumu_manual_serial="127.0.0.1:7555"),
            )
            observation = bound.observe(bound.begin_budget())
        self.assertEqual(observation.serial, "127.0.0.1:7555")

    def test_missing_manager_without_any_serial_fails_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            adb, simulator = ADB(), SpySimulator()
            bound = self.session(
                adb, simulator, profile(installation_path=folder, last_serial="")
            )
            with self.assertRaises(SessionFailure) as raised:
                bound.ensure_ready()
        self.assertEqual(raised.exception.observation.code, "manager_missing")
        self.assertIn("重新检测", str(raised.exception))
        self.assertEqual(adb.actions, [])
        self.assertEqual(simulator.lifecycle, [])

    def test_degraded_transaction_reconnects_the_endpoint_and_then_reaches_ready(self):
        adb = ADB()

        def reconnect():
            # The device answers only after the manager-less reconnect.
            adb.rows = [(SERIAL, "device")]
            adb.boot = "1"

        adb.on_recover = reconnect
        simulator = SpySimulator()
        with tempfile.TemporaryDirectory() as folder:
            bound = self.session(adb, simulator, profile(installation_path=folder))
            ready = bound.ensure_ready()
        self.assertEqual(ready.state, "ready")
        self.assertEqual(ready.serial, SERIAL)
        # Degraded state carries no lifecycle authority: reconnect only.
        self.assertEqual(adb.actions, [SERIAL])
        self.assertEqual(simulator.lifecycle, [])
        self.assertEqual(ready.instance_state, "unknown")


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
