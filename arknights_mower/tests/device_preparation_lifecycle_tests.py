"""Run boundaries preserve preparation across subtasks and restore on exit."""

import importlib
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.tests.device_preparation_tests import DisplayIO, SerialLocks
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.preparation import PreparationSession
from arknights_mower.utils.device.preparation_store import RecoveryStore
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy


class PreparationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The scheduler import has unrelated SKLand network initialization.
        # Restore only SKLand; restoring all sys.modules invalidates native cv2.
        name = "arknights_mower.utils.skland"
        previous = sys.modules.get(name)
        sys.modules[name] = MagicMock()
        try:
            cls.main = importlib.import_module("arknights_mower.__main__")
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = RecoveryStore(Path(directory.name))
        self.io, self.locks = DisplayIO(), SerialLocks()
        self.io.paths.add("verified-adb")
        self.adb = ADB()
        self.adb.rows, self.adb.boot = [("USB-123", "device")], "1"
        self.conf = Conf(
            device={
                "preset_id": "manual.physical",
                "last_serial": "USB-123",
                "adb_path": "manual-adb",
                "screenshot_backend": "adb_gzip",
            }
        )
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=PreparationSession(self.io, self.store, self.locks),
            session=DeviceSession(
                self.adb,
                Simulator(),
                clock=Clock(),
                policy=RecoveryPolicy(attempts=2, timeout=10, local_wait=1),
            ),
        )
        self.addCleanup(self.control.close)
        self.schedulers = []
        self.validation_message = None
        self.step = lambda: None
        self.refresh = lambda: None
        self.enterContext(patch.object(config, "conf", self.conf))
        self.enterContext(patch.object(config, "stop_mower", Event()))
        self.enterContext(patch.object(self.main, "device_control", self.control))
        self.enterContext(patch.object(self.main, "resource_task_session", nullcontext))
        self.enterContext(patch.object(self.main, "refresh_resource_at_boundary"))
        self.enterContext(patch.object(self.main.rapidocr, "initialize_ocr"))
        self.enterContext(
            patch.object(self.main.NewsChecker, "get_maintenance", return_value=None)
        )
        self.enterContext(
            patch(
                "arknights_mower.utils.operators.build_global_plan",
                return_value=({}, {}),
            )
        )
        self.factory = self.enterContext(
            patch.object(self.main, "BaseSchedulerSolver", side_effect=self.scheduler)
        )

    def scheduler(self, *, device):
        scheduler = SimpleNamespace(
            device=device,
            initialize_operators=lambda: self.validation_message,
            op_data=SimpleNamespace(
                validate_backup_plans=lambda: {"success": True}, config=None
            ),
            run=lambda: self.step(),
            recog=SimpleNamespace(update=lambda: self.refresh()),
        )
        self.schedulers.append(scheduler)
        return scheduler

    def assert_prepared(self):
        self.assertEqual(self.io.override, [1920, 1080])
        self.assertEqual(self.store.load("USB-123")["stage"], "validated")
        self.assertEqual(self.locks.held, {"USB-123"})

    def assert_restored(self):
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(self.locks.held, set())
        self.assertEqual(self.io.writes, [("USB-123", [1920, 1080]), ("USB-123", None)])
        self.assertFalse(self.control.run_active)
        self.assertIsNone(self.main.base_scheduler)
        for scheduler in self.schedulers:
            self.assertTrue(scheduler.device.closed)

    def test_normal_scheduler_validation_return_restores_preparation(self):
        self.validation_message = "scheduler configuration rejected"
        self.assertIsNone(self.main.main({}, preparation_serial="USB-123"))
        self.assert_restored()

    def test_cancellation_in_worker_restores_preparation(self):
        def cancel():
            self.assert_prepared()
            raise MowerExit()

        self.step = cancel
        self.assertIsNone(self.main.main({}, preparation_serial="USB-123"))
        self.assert_restored()

    def test_fatal_worker_error_and_keyboard_interrupt_restore_preparation(self):
        for error in (DeviceRecoveryError("exhausted"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                self.io.writes.clear()

                def fail():
                    self.assert_prepared()
                    raise error

                self.step = fail
                with self.assertRaises(type(error)) as caught:
                    self.main.main({}, preparation_serial="USB-123")
                self.assertIs(caught.exception, error)
                self.assert_restored()

    def test_scheduler_initialization_failure_restores_before_propagating(self):
        def fail(*, device):
            self.assert_prepared()
            raise RuntimeError("scheduler initialization failed")

        self.factory.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "scheduler initialization failed"):
            self.main.main({}, preparation_serial="USB-123")
        self.assert_restored()

    def test_second_initialize_in_same_worker_retains_original_prepared_session(self):
        def initialize_again():
            self.assert_prepared()
            record = self.store.load("USB-123")
            previous = self.schedulers[0].device
            next_scheduler = self.main.initialize([])
            self.assertIs(next_scheduler.device, previous)
            self.assertFalse(previous.closed)
            self.assertEqual(self.store.load("USB-123")["run_id"], record["run_id"])
            self.assertEqual(self.io.writes, [("USB-123", [1920, 1080])])
            raise MowerExit()

        self.step = initialize_again
        self.main.main({}, preparation_serial="USB-123")
        self.assertEqual(len(self.schedulers), 2)
        self.assert_restored()

    def test_recoverable_subtask_failure_keeps_display_until_worker_exit(self):
        turns = []
        refreshed = []

        def step():
            turns.append(len(turns))
            self.assert_prepared()
            if len(turns) == 1:
                raise ValueError("one subtask failed")
            raise MowerExit()

        def refresh():
            self.assert_prepared()
            self.assertEqual(self.io.writes, [("USB-123", [1920, 1080])])
            refreshed.append(True)

        self.step, self.refresh = step, refresh
        self.main.main({}, preparation_serial="USB-123")
        self.assertEqual(turns, [0, 1])
        self.assertEqual(refreshed, [True])
        self.assert_restored()

    def test_actual_reconnection_restores_then_rejects_further_work(self):
        def reconnect():
            self.adb.rows = [("USB-123", "device")]
            self.io.targets = [("USB-123", "device")]

        self.adb.on_recover = reconnect
        with self.control.run(preparation_serial="USB-123"):
            self.control.start().unwrap()
            self.assert_prepared()
            self.adb.rows = self.io.targets = [("USB-123", "offline")]
            result = self.control.recover()
            self.assertEqual(result.error.code, "preparation_interrupted")
            self.assertIsNone(self.io.override)
            self.assertIsNone(self.store.load("USB-123"))
            later = self.control.execute(lambda device: self.fail("must not execute"))
            self.assertEqual(later.error.code, "preparation_interrupted")
        self.assertEqual(self.adb.actions, ["USB-123"])
        self.assert_restored()

    def test_http_stop_waits_until_live_worker_restores_the_display(self):
        server = importlib.import_module("server")
        prepared = Event()

        def await_stop():
            self.assert_prepared()
            prepared.set()
            config.stop_mower.wait(2)
            raise MowerExit()

        self.step = await_stop
        worker = Thread(
            target=self.main.main, args=({},), kwargs={"preparation_serial": "USB-123"}
        )
        self.enterContext(patch.object(server, "mower_thread", worker))
        self.enterContext(patch.object(server, "set_mower_thread"))
        self.enterContext(
            patch("arknights_mower.solvers.record.current_state", return_value={})
        )
        self.enterContext(patch("arknights_mower.solvers.record.save_state_to_db"))
        worker.start()
        try:
            self.assertTrue(
                prepared.wait(2), "worker never reached prepared scheduling"
            )
            response = server.app.test_client().get(
                "/stop", headers={"token": getattr(server.app, "token", "")}
            )
            self.assertEqual(response.get_data(as_text=True), "true")
            self.assertFalse(worker.is_alive())
            self.assert_restored()
        finally:
            config.stop_mower.set()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
