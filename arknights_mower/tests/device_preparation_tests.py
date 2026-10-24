"""Physical preparation behavior through the application boundary."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import Adapter
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.lifecycle import Shutdown


class SerialLocks:
    def __init__(self):
        self.held = set()

    def acquire(self, serial):
        if serial in self.held:
            raise RuntimeError("serial locked")
        self.held.add(serial)
        held = self.held

        class Lease:
            def close(self):
                held.discard(serial)

        return Lease()


class DisplayIO(PreflightIO):
    def __init__(self):
        super().__init__()
        self.physical = [2560, 1440]
        self.override = None
        self.writes = []
        self.before_write = lambda value: None
        self.surface = (1920, 1080)

    def display_size(self, adb_path, serial):
        size = f"Physical size: {self.physical[0]}x{self.physical[1]}"
        if self.override is not None:
            size += f"\nOverride size: {self.override[0]}x{self.override[1]}"
        return size

    def set_size(self, adb_path, serial, value):
        self.before_write(value)
        self.writes.append((serial, value))
        self.override = value

    def input_surface(self, adb_path, serial):
        return self.surface


class PhysicalPreparationTests(unittest.TestCase):
    def setUp(self):
        from arknights_mower.utils.device.preparation import PreparationSession
        from arknights_mower.utils.device.preparation_store import RecoveryStore

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = RecoveryStore(Path(directory.name))
        self.io = DisplayIO()
        self.locks = SerialLocks()
        self.conf = Conf(
            device={
                "preset_id": "manual.physical",
                "last_serial": "USB-123",
                "adb_path": "manual-adb",
                "screenshot_backend": "adb_gzip",
            }
        )
        self.preparation = PreparationSession(self.io, self.store, self.locks)
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=self.preparation,
        )
        self.addCleanup(self.control.close)

    def test_authorized_run_records_intent_before_write_and_restores_on_close(self):
        def recorded(value):
            if value is not None:
                record = self.store.load("USB-123")
                self.assertEqual(record["stage"], "intent")
                self.assertEqual(record["physical"], [2560, 1440])
                self.assertIsNone(record["original_override"])
                self.assertEqual(record["written"], [1920, 1080])
                self.assertTrue(record["run_id"])

        self.io.before_write = recorded
        result = self.control.start(preparation_serial="USB-123")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.store.load("USB-123")["stage"], "validated")
        self.assertTrue(self.control.close().ok)
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(self.io.writes, [("USB-123", [1920, 1080]), ("USB-123", None)])
        self.assertEqual(self.locks.held, set())

    def test_preparation_resolves_empty_and_aliased_adb_without_saving_profile(self):
        devices = self.io.devices
        for configured in ("", "@internal/adb"):
            with self.subTest(configured=configured):
                self.conf.device.adb_path = configured
                before = self.conf.model_dump()

                def verified_devices(adb_path, serial):
                    self.assertEqual(adb_path, "product-adb")
                    return devices(adb_path, serial)

                with (
                    patch.object(self.io, "devices", side_effect=verified_devices),
                    patch.object(
                        self.io,
                        "normalize_adb_path",
                        side_effect=lambda value: (
                            "product-adb" if value == "@internal/adb" else value
                        ),
                    ),
                ):
                    result = self.control.start(preparation_serial="USB-123")
                    self.assertTrue(result.ok, result.error)
                    self.assertTrue(self.control.close().ok)
                self.assertEqual(self.conf.model_dump(), before)

    def test_session_resolves_once_before_preparation_and_reuses_its_budget(self):
        from arknights_mower.tests.device_session_tests import ADB, Clock, Simulator
        from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

        clock, adb = Clock(), ADB()
        adb.rows, adb.boot = [("USB-123", "device")], "1"
        self.io.paths.add("verified-adb")
        self.conf.device.adb_path = ""
        before = self.conf.model_dump()
        session = DeviceSession(
            adb, Simulator(), clock=clock, policy=RecoveryPolicy(timeout=10)
        )
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=self.preparation,
            session=session,
        )
        self.addCleanup(self.control.close)
        devices = self.io.devices

        def resolve(profile, timeout):
            self.assertEqual(timeout, 10)
            clock.sleep(2)
            return "verified-adb"

        def verified_devices(adb_path, serial):
            self.assertEqual(adb_path, "verified-adb")
            self.assertEqual(clock.now, 2)
            return devices(adb_path, serial)

        with (
            patch.object(adb, "resolve_adb", side_effect=resolve) as resolution,
            patch.object(self.io, "devices", side_effect=verified_devices),
        ):
            result = self.control.start(preparation_serial="USB-123")
            self.assertTrue(result.ok, result.error)
            resolution.assert_called_once()
            self.assertEqual(session.remaining(), 8)
            self.assertTrue(self.control.close().ok)
        self.assertEqual(self.conf.model_dump(), before)

    def test_expired_adb_resolution_never_begins_physical_preparation(self):
        from arknights_mower.tests.device_session_tests import ADB, Clock, Simulator
        from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

        clock, adb = Clock(), ADB()
        session = DeviceSession(
            adb, Simulator(), clock=clock, policy=RecoveryPolicy(timeout=10)
        )
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=self.preparation,
            session=session,
        )
        self.addCleanup(self.control.close)

        def resolve(profile, timeout):
            clock.sleep(timeout)
            return "verified-adb"

        with (
            patch.object(adb, "resolve_adb", side_effect=resolve),
            patch.object(
                self.preparation, "begin", wraps=self.preparation.begin
            ) as begin,
        ):
            result = self.control.start(preparation_serial="USB-123")
        self.assertFalse(result.ok)
        begin.assert_not_called()
        self.assertEqual(self.io.writes, [])
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(self.locks.held, set())

    def test_adb_resolution_failure_does_not_reuse_a_previous_preflight(self):
        for ready_before in (True, False):
            with self.subTest(ready_before=ready_before):
                self.io.paths.add("manual-adb")
                self.io.targets = [("USB-123", "device" if ready_before else "offline")]
                self.assertEqual(self.control.preflight().ok, ready_before)
                self.io.paths.clear()
                result = self.control.start(preparation_serial="USB-123")
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "missing_adb")
                self.assertEqual(
                    self.control.settings_status()["error"]["code"], "missing_adb"
                )
                self.assertIsNone(self.control.settings_status()["preflight"])
                self.assertEqual(self.io.writes, [])
                self.assertEqual(self.locks.held, set())
                self.control.close()

    def test_shared_adb_rejection_is_a_device_failure_without_application_exit(self):
        from unittest.mock import Mock

        from arknights_mower.utils.device.adb_client.server import SharedADBError

        fatal = Mock()
        control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=self.preparation,
            on_fatal=fatal,
        )
        self.addCleanup(control.close)
        with patch.object(
            control._preflight,
            "resolve_adb",
            side_effect=SharedADBError("shared server unavailable"),
        ):
            result = control.start(preparation_serial="USB-123")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "adb_server_unavailable")
        self.assertEqual(self.io.writes, [])
        fatal.assert_not_called()

    def test_offline_end_blocks_work_until_next_run_compensates(self):
        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
        self.io.targets = [("USB-123", "offline")]
        self.assertEqual(self.control.close().error.code, "recovery_pending")
        self.assertEqual(self.store.load("USB-123")["stage"], "pending")
        self.assertFalse(self.control.start().ok)
        self.control.close()
        self.io.targets = [("USB-123", "device")]
        with self.control.run(preparation_serial="USB-123"):
            result = self.control.start()
            self.assertTrue(result.ok, result.error)
        self.assertEqual(
            self.io.writes,
            [
                ("USB-123", [1920, 1080]),
                ("USB-123", None),
                ("USB-123", [1920, 1080]),
                ("USB-123", None),
            ],
        )

    def test_reconnected_run_can_retry_a_previous_failed_close(self):
        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
        self.io.targets = []
        self.assertFalse(self.control.close().ok)
        self.io.targets = [("USB-123", "device")]
        with self.control.run(preparation_serial="USB-123"):
            self.assertTrue(self.control.start().ok)

    def test_default_is_read_only_and_authorization_is_not_reused(self):
        # A start without consent reads the device and never writes to it.
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.io.writes, [])
        with self.control.run(preparation_serial="USB-123"):
            self.assertTrue(self.control.start().ok)
        self.control.close()
        self.assertEqual(self.io.writes, [("USB-123", [1920, 1080]), ("USB-123", None)])
        # Without new consent the next start must not write again.
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.io.writes, [("USB-123", [1920, 1080]), ("USB-123", None)])

    def test_portrait_target_restores_original_override_exactly(self):
        self.io.physical, self.io.override = [1440, 2560], [1200, 2000]
        result = self.control.start(preparation_serial="USB-123")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.io.override, [1080, 1920])
        self.assertEqual(self.store.load("USB-123")["original_override"], [1200, 2000])
        self.control.close()
        self.assertEqual(self.io.override, [1200, 2000])

    def test_android_hides_override_equal_to_physical_and_original_still_restores(self):
        display_size = self.io.display_size

        def android_size(adb, serial):
            value = display_size(adb, serial)
            return (
                value.splitlines()[0] if self.io.override == self.io.physical else value
            )

        self.io.display_size = android_size
        for physical, original in (
            ([1920, 1080], [1600, 900]),
            ([1080, 1920], [900, 1600]),
        ):
            with self.subTest(physical=physical):
                self.io.physical, self.io.override = physical, original
                result = self.control.start(preparation_serial="USB-123")
                self.assertTrue(result.ok, result.error)
                self.assertTrue(self.control.close().ok)
                self.assertEqual(self.io.override, original)
                self.assertIsNone(self.store.load("USB-123"))

    def test_already_target_size_keeps_lease_and_validates_without_redundant_override(
        self,
    ):
        for physical, override in (
            ([1920, 1080], None),
            ([1080, 1920], None),
            ([2560, 1440], [1920, 1080]),
        ):
            with self.subTest(physical=physical, override=override):
                self.io.physical, self.io.override = physical, override
                self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
                self.assertEqual(self.io.writes, [])
                self.assertEqual(self.locks.held, {"USB-123"})
                self.assertIsNone(self.store.load("USB-123"))
                self.assertTrue(self.control.close().ok)
                self.assertEqual(self.io.override, override)
                self.assertEqual(self.locks.held, set())

    def test_no_write_preparation_still_rejects_changed_display_and_bad_input(self):
        self.io.physical = [1920, 1080]
        self.io.surface = (1080, 1920)
        self.assertEqual(
            self.control.start(preparation_serial="USB-123").error.code,
            "input_surface_mismatch",
        )
        self.control.close()
        self.io.surface = (1920, 1080)

        def frame_then_change(adb, serial, profile):
            self.io.override = [1600, 900]
            return self.io.frame

        self.io.capture_frame = frame_then_change
        self.assertEqual(
            self.control.start(preparation_serial="USB-123").error.code,
            "recovery_conflict",
        )
        self.assertEqual(self.io.override, [1600, 900])
        self.assertEqual(self.io.writes, [])
        self.assertIsNone(self.store.load("USB-123"))

    def test_unsafe_targets_never_write(self):
        cases = (
            ("USB-other", "manual.physical", [("USB-123", "device")], [2560, 1440]),
            ("USB-123", "manual.other", [("USB-123", "device")], [2560, 1440]),
            ("USB-123", "manual.physical", [("USB-123", "offline")], [2560, 1440]),
            ("USB-123", "manual.physical", [("USB-123", "device")] * 2, [2560, 1440]),
            ("USB-123", "manual.physical", [("OTHER", "device")], [2560, 1440]),
            ("USB-123", "manual.physical", [("USB-123", "unauthorized")], [2560, 1440]),
            ("USB-123", "manual.physical", [("USB-123", "device")], [1280, 720]),
        )
        for authorized, preset, targets, physical in cases:
            with self.subTest(
                authorized=authorized, preset=preset, targets=targets, physical=physical
            ):
                self.conf.device.preset_id = preset
                self.io.targets, self.io.physical = targets, physical
                self.assertFalse(self.control.start(preparation_serial=authorized).ok)
                self.control.close()
                self.assertEqual(self.io.writes, [])
                self.assertIsNone(self.store.load("USB-123"))

    def test_bad_frame_or_input_surface_restores_before_returning_failure(self):
        for kind in ("frame", "surface"):
            with self.subTest(kind=kind):
                self.io.frame = np.zeros(
                    (1920, 1080, 3) if kind == "frame" else (1080, 1920, 3), np.uint8
                )
                self.io.surface = (1080, 1920) if kind == "surface" else (1920, 1080)
                result = self.control.start(preparation_serial="USB-123")
                self.assertFalse(result.ok)
                self.assertEqual(
                    result.error.code,
                    "frame_size_mismatch"
                    if kind == "frame"
                    else "input_surface_mismatch",
                )
                self.assertIsNone(self.io.override)
                self.assertIsNone(self.store.load("USB-123"))
                self.control.close()

    def test_input_surface_verdict_restores_without_application_exit_and_can_retry(
        self,
    ):
        for unreadable in (False, True):
            with self.subTest(unreadable=unreadable):
                shutdown = Shutdown()
                devices = []

                class TrackingAdapter(Adapter):
                    def open_verified(self, configuration, result):
                        device = super().open_verified(configuration, result)
                        devices.append(device)
                        return device

                control = DeviceControl(
                    lambda: self.conf,
                    TrackingAdapter(),
                    preflight=PreflightService(self.io),
                    preparation=self.preparation,
                    on_fatal=shutdown.request,
                )
                try:
                    with patch.object(
                        self.io,
                        "input_surface",
                        return_value=(1080, 1920),
                        side_effect=OSError("surface unreadable")
                        if unreadable
                        else None,
                    ):
                        result = control.start(preparation_serial="USB-123")
                    self.assertFalse(result.ok)
                    self.assertEqual(result.error.code, "input_surface_mismatch")
                    self.assertFalse(shutdown.closing)
                    self.assertFalse(control.shutdown_requested)
                    self.assertFalse(control.active)
                    self.assertEqual(len(devices), 1)
                    self.assertTrue(devices[0].closed)
                    self.assertIsNone(self.io.override)
                    self.assertIsNone(self.store.load("USB-123"))
                    self.assertEqual(self.locks.held, set())

                    retried = control.start(preparation_serial="USB-123").unwrap()
                    self.assertEqual(retried.device_id, "USB-123")
                    self.assertEqual(len(devices), 2)
                    self.assertFalse(retried.closed)
                    self.assertTrue(control.close().ok)
                    self.assertTrue(retried.closed)
                    self.assertIsNone(self.io.override)
                    self.assertIsNone(self.store.load("USB-123"))
                    self.assertEqual(self.locks.held, set())
                    self.assertFalse(shutdown.closing)
                finally:
                    control.close()

    def test_third_party_change_is_not_overwritten_and_blocks_new_work(self):
        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
        self.io.override = [1600, 900]
        self.assertEqual(self.control.close().error.code, "recovery_conflict")
        self.assertEqual(self.io.override, [1600, 900])
        self.assertEqual(self.store.load("USB-123")["stage"], "conflict")
        self.assertEqual(
            self.control.start(preparation_serial="USB-123").error.code,
            "recovery_conflict",
        )
        self.assertEqual(self.io.writes, [("USB-123", [1920, 1080])])
        self.control.close()
        # Manual resolution to the original state is verified and clears the
        # record; the start itself performs no write.
        self.io.override = None
        self.assertTrue(self.control.start().ok)
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(len(self.io.writes), 1)

    def test_atomic_intent_failure_prevents_any_device_write(self):
        with patch("os.replace", side_effect=OSError("disk full")):
            self.assertFalse(self.control.start(preparation_serial="USB-123").ok)
        self.assertEqual(self.io.writes, [])
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(self.locks.held, set())

    def test_ambiguous_write_failure_still_restores_using_durable_intent(self):
        original_write = self.io.set_size

        def lost_response(adb, serial, value):
            original_write(adb, serial, value)
            if value == [1920, 1080]:
                raise ConnectionError("response lost after write")

        self.io.set_size = lost_response
        self.assertFalse(self.control.start(preparation_serial="USB-123").ok)
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))

    def test_invalid_display_output_cannot_authorize_mutation(self):
        self.io.display_size = lambda adb, serial: (
            "Physical size: 2560x1440\nOverride size: unknown"
        )
        result = self.control.start(preparation_serial="USB-123")
        self.assertEqual(result.error.code, "invalid_size")
        self.assertEqual(self.io.writes, [])

    def test_stale_intent_is_cleared_without_writing_already_original_state(self):
        from arknights_mower.tests.device_preparation_store_tests import recovery_record

        record = recovery_record("USB-123")
        record["physical"] = self.io.physical
        record["written"] = [1920, 1080]
        self.store.save(record)
        # The pending record is compensated before any new work, and a start
        # without consent still never writes to the device.
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.io.writes, [])
        self.assertIsNone(self.store.load("USB-123"))

    def test_durable_written_stage_precedes_actual_frame_validation(self):
        capture = self.io.capture_frame

        def capture_after_write(adb, serial, profile):
            self.assertEqual(self.store.load(serial)["stage"], "written")
            return capture(adb, serial, profile)

        self.io.capture_frame = capture_after_write
        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)

    def test_cleanup_failure_does_not_skip_display_restoration(self):
        device = self.control.start(preparation_serial="USB-123").unwrap()
        device.close = lambda: (_ for _ in ()).throw(OSError("helper cleanup failed"))
        result = self.control.close()
        self.assertFalse(result.ok)
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))

    def test_locked_serial_blocks_both_authorized_and_read_only_work(self):
        lease = self.locks.acquire("USB-123")
        self.addCleanup(lease.close)
        for authorized in (None, "USB-123"):
            with self.subTest(authorized=authorized):
                self.assertEqual(
                    self.control.start(preparation_serial=authorized).error.code,
                    "preparation_locked",
                )
                self.control.close()
        self.assertEqual(self.io.writes, [])

    def test_start_failure_remains_visible_after_worker_cleanup(self):
        lease = self.locks.acquire("USB-123")
        self.addCleanup(lease.close)
        with self.control.run(preparation_serial="USB-123"):
            self.assertFalse(self.control.start().ok)
        self.assertEqual(
            self.control.settings_status()["error"]["code"], "preparation_locked"
        )

    def test_whole_run_exit_restores_but_recoverable_child_error_does_not(self):
        for error in (None, RuntimeError("fatal"), MowerExit(), KeyboardInterrupt()):
            with self.subTest(error=error):
                try:
                    with self.control.run(preparation_serial="USB-123"):
                        self.assertTrue(self.control.start().ok)
                        child = self.control.execute(
                            lambda device: (_ for _ in ()).throw(ValueError("child"))
                        )
                        self.assertFalse(child.ok)
                        self.assertEqual(self.io.override, [1920, 1080])
                        self.assertEqual(
                            self.store.load("USB-123")["stage"], "validated"
                        )
                        if error:
                            raise error
                except BaseException as caught:
                    if caught is not error:
                        raise
                self.assertIsNone(self.io.override)
                self.assertIsNone(self.store.load("USB-123"))

    def test_interruption_during_input_ends_preparation_immediately(self):
        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
        result = self.control.execute(lambda device: (_ for _ in ()).throw(MowerExit()))
        self.assertEqual(result.error.code, "cancelled")
        self.assertIsNone(self.io.override)

    def test_helper_initialization_failure_restores_and_closes_lease(self):
        class FailingAdapter:
            def open_verified(self, configuration, result):
                raise RuntimeError("input helper failed")

        control = DeviceControl(
            lambda: self.conf,
            FailingAdapter(),
            preflight=PreflightService(self.io),
            preparation=self.preparation,
        )
        result = control.start(preparation_serial="USB-123")
        self.assertFalse(result.ok)
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))
        self.assertEqual(self.locks.held, set())

    def test_next_process_restores_pending_record_even_without_new_consent(self):
        from arknights_mower.utils.device.preparation import PreparationSession

        self.assertTrue(self.control.start(preparation_serial="USB-123").ok)
        self.io.targets = []
        self.control.close()
        self.io.targets = [("USB-123", "device")]
        next_control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            preparation=PreparationSession(self.io, self.store, self.locks),
        )
        self.addCleanup(next_control.close)
        result = next_control.start()
        # The new process compensates the pending record before anything else,
        # and the start itself stays read-only.
        self.assertTrue(result.ok, result.error)
        self.assertIsNone(self.io.override)
        self.assertIsNone(self.store.load("USB-123"))


if __name__ == "__main__":
    unittest.main()
