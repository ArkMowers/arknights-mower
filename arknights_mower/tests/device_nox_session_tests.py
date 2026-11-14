import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.nox_discovery import NoxDiscoveryIO
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import (
    ProductionSessionADB,
    ProductionSimulator,
)

FIXTURES = Path(__file__).parent / "fixtures"
BOOT = "74e9de7c-0aa1-4a25-aec5-81d7e8a1acef"
OTHER_BOOT = "59d349d4-68a1-4c9e-aa90-7b48ac0b7685"


class NoxTransport:
    def __init__(self, root):
        self.root = Path(root)
        self.manager = self.root / "NoxConsole.exe"
        self.adb = self.root / "chosen-adb.exe"
        self.bundled = self.root / "nox_adb.exe"
        self.player = self.root / "Nox.exe"
        for path in (self.manager, self.adb, self.bundled, self.player):
            path.touch()
        self.vm = self.root / "BignoxVMS/Nox_2/Nox_2.vbox"
        self.vm.parent.mkdir(parents=True)
        self.vm.write_bytes((FIXTURES / "nox_vm.vbox").read_bytes())
        self.listing = (FIXTURES / "nox_single.txt").read_bytes()
        self.states = {"127.0.0.1:62125": "device", "127.0.0.1:62001": "device"}
        self.boots = {"127.0.0.1:62125": BOOT, "127.0.0.1:62001": OTHER_BOOT}
        self.calls = []
        self.lifecycle = []
        self.after_shell = lambda: None
        self.launch_delay = []
        self.pending_states = iter(())
        self.manager_boot = BOOT
        self.version = "Android Debug Bridge version 1.0.41"
        self.connect_state = None
        self.disconnected_states = {}
        self.after_connect = lambda: None
        self.after_disconnect = lambda: None
        self.after_list = lambda: None
        self.io = PreflightIO()
        self.io.host = "windows"
        self.io.paths.add(str(self.adb))
        self.io.installed.update([str(self.root), str(self.manager)])
        self.simulator = ProductionSimulator(run=self.run, probe=lambda timeout: None)
        self.discovery = DiscoveryService(
            NoxDiscoveryIO(
                run=self.run,
                registry_paths=lambda: [str(self.root)],
                fixed_paths=lambda: [],
                process_paths=lambda: [],
                platform="windows",
            ),
            self.simulator,
        )
        self.configuration = Conf()
        self.adapter = Mock(wraps=Adapter())
        self.control = DeviceControl(
            lambda: self.configuration,
            self.adapter,
            preflight=PreflightService(self.io),
            discovery=self.discovery,
            session=DeviceSession(
                ProductionSessionADB(
                    run=self.run,
                    probe=lambda timeout: None,
                    # Keep the first-frame probe off a live server; the decode seam
                    # is injected so this fixture only exercises the session policy.
                    frame=lambda *args: self.frame_size(),
                ),
                self.simulator,
                clock=Clock(),
                policy=RecoveryPolicy(timeout=12, local_wait=1),
            ),
        )
        self.control._session.adb.standard_frame_size = lambda *args: self.frame_size()
        candidate = self.control.discover().candidates[0]
        self.configuration = self.configuration.updated(
            {"device": {**candidate["binding"], "adb_path": str(self.adb)}}
        )
        self.io.targets = list(self.states.items())
        self.calls.clear()

    def frame_size(self):
        """Return the decoded frame the fixture declares, independent of size."""
        return self.io.frame.shape[1], self.io.frame.shape[0]

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] == str(self.player):
            if argv[1:] != ["-clone:Nox_2", "-quit"]:
                raise AssertionError(argv)
            self.lifecycle.append(("quit", "Nox_2"))
            self.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
            output = ""
        elif argv[0] == str(self.manager):
            if argv[1] == "list":
                self.after_list()
                return subprocess.CompletedProcess(argv, 0, self.listing, b"")
            if argv[1] in {"launch", "quit"}:
                self.lifecycle.append((argv[1], argv[2]))
                self.listing = (
                    FIXTURES
                    / ("nox_single.txt" if argv[1] == "launch" else "nox_stopped.txt")
                ).read_bytes()
                if argv[1] == "launch":
                    self.pending_states = iter(self.launch_delay)
                    self.advance_pending()
                output = ""
            elif argv[1] == "adb":
                if argv[2] != "-name:日常号":
                    raise AssertionError("NoxConsole expects the current unique title")
                output = self.manager_boot
            else:
                raise AssertionError(argv)
        elif argv[1] == "version":
            output = self.version
        elif argv[1] == "devices":
            output = "List of devices attached\n" + "\n".join(
                f"{serial}\t{state}" for serial, state in self.states.items()
            )
            if argv[0] == str(self.adb):
                self.advance_pending()
        elif argv[1] == "-s":
            if "getprop" in argv:
                output = "1"
            elif argv[3:] == ["shell", "wm", "size"]:
                output = self.io.size
            else:
                output = self.boots[argv[2]]
            self.after_shell()
        elif argv[1] == "disconnect":
            self.disconnected_states[argv[2]] = self.states.pop(argv[2], None)
            output = f"disconnected {argv[2]}"
            self.after_disconnect()
        elif argv[1] == "connect":
            state = self.connect_state or self.disconnected_states.pop(argv[2], None)
            if state is not None:
                self.states[argv[2]] = state
            output = f"connected to {argv[2]}"
            self.after_connect()
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def advance_pending(self):
        try:
            state = next(self.pending_states)
        except StopIteration:
            return
        if state is None:
            self.states.pop("127.0.0.1:62125", None)
        else:
            self.states["127.0.0.1:62125"] = state


class NoxSessionTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.fixture = NoxTransport(root)
        self.addCleanup(self.fixture.control.close)

    def test_peer_restart_restores_only_current_vm_registration_and_helpers(self):
        fixture = self.fixture
        recovery = SimpleNamespace(generation=0, recover=Mock(return_value=False))
        fixture.control._adb_recovery = recovery
        self.assertTrue(fixture.control.start().ok)
        original = fixture.configuration.model_dump()
        recovery.generation = 1
        fixture.states.clear()
        fixture.connect_state = "device"
        fixture.calls.clear()
        result = fixture.control.recover()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:62125")
        self.assertEqual(fixture.configuration.model_dump(), original)
        self.assertEqual(fixture.lifecycle, [])
        fixture.adapter.rebind.assert_called_once()
        self.assertEqual(
            [argv for argv, _ in fixture.calls if argv[1] == "connect"],
            [[str(fixture.adb), "connect", "127.0.0.1:62125"]],
        )
        self.assertFalse(any("127.0.0.1:62001" in argv for argv, _ in fixture.calls))

    def test_startup_registers_current_forward_without_using_saved_serial(self):
        fixture = self.fixture
        fixture.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
        fixture.states.clear()
        fixture.configuration.device.last_serial = "127.0.0.1:62001"
        fixture.connect_state = "device"
        result = fixture.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:62125")
        self.assertEqual(fixture.lifecycle, [("launch", "-name:日常号")])
        self.assertFalse(any("127.0.0.1:62001" in argv for argv, _ in fixture.calls))

    def test_offline_current_forward_is_reconnected_without_restart(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states["127.0.0.1:62125"] = "offline"
        fixture.connect_state = "device"
        fixture.calls.clear()
        result = fixture.control.recover()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(fixture.lifecycle, [])
        self.assertEqual(
            [
                argv[1:]
                for argv, _ in fixture.calls
                if argv[1] in {"connect", "disconnect"}
            ],
            [["disconnect", "127.0.0.1:62125"], ["connect", "127.0.0.1:62125"]],
        )

    def test_registered_forward_with_wrong_boot_never_rebuilds_helpers(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.connect_state = "device"
        fixture.boots["127.0.0.1:62125"] = OTHER_BOOT
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "endpoint_unresolved")
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_vm_change_during_registration_never_rebuilds_helpers(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.connect_state = "device"
        fixture.after_connect = lambda: setattr(
            fixture, "listing", fixture.listing.replace(b"1200", b"2400")
        )
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "binding_changed")
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_recreated_vm_is_rejected_before_registration(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        original = fixture.configuration.model_dump()
        fixture.states.clear()
        fixture.connect_state = "device"
        fixture.vm.write_text(
            fixture.vm.read_text().replace(
                "5e1aaadc-7991-419d-a2b6-f030b497b282",
                "bc63cd6d-39b1-4ea0-984c-f32dfe269e67",
            )
        )
        fixture.calls.clear()
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "topology_changed")
        self.assertEqual(fixture.configuration.model_dump(), original)
        self.assertFalse(any(argv[1] == "connect" for argv, _ in fixture.calls))
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_unavailable_registration_exhausts_only_existing_budget(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        original = fixture.configuration.model_dump()
        fixture.states.clear()
        fixture.calls.clear()
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "recovery_exhausted")
        self.assertLessEqual(fixture.control._session.actions, 3)
        self.assertEqual(fixture.configuration.model_dump(), original)
        fixture.adapter.rebind.assert_not_called()
        connections = [argv for argv, _ in fixture.calls if argv[1] == "connect"]
        self.assertGreater(len(connections), 0)
        self.assertLessEqual(len(connections), 3)
        self.assertTrue(all(argv[2] == "127.0.0.1:62125" for argv in connections))

    def test_registration_never_bypasses_vendor_shared_adb_guard(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.calls.clear()
        fixture.version = "Android Debug Bridge version 1.0.40"
        fixture.control._session.adb._probe = lambda timeout: 41
        with self.assertRaises(SharedADBError):
            fixture.control._session.adb.recover(str(fixture.adb), "", 6)
        self.assertFalse(any(argv[1] == "connect" for argv, _ in fixture.calls))
        self.assertEqual(fixture.lifecycle, [])

    def test_registration_cancellation_never_rebuilds_helpers(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.connect_state = "device"
        fixture.after_connect = fixture.control._session.begin_shutdown
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "cancelled")
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_registration_deadline_never_exposes_the_endpoint(self):
        fixture = self.fixture
        fixture.states.clear()
        fixture.connect_state = "device"
        now = [0]

        def run(argv, **kwargs):
            result = fixture.run(argv, **kwargs)
            if argv[1] == "connect":
                now[0] = 6
            return result

        adapter = ProductionSessionADB(
            run=run, probe=lambda timeout: None, monotonic=lambda: now[0]
        )
        adapter.bind(fixture.configuration.device)
        with self.assertRaises(SharedADBError):
            adapter.recover(str(fixture.adb), "", 6)
        self.assertEqual(
            [argv for argv, _ in fixture.calls if argv[1] == "connect"],
            [[str(fixture.adb), "connect", "127.0.0.1:62125"]],
        )
        self.assertEqual(fixture.lifecycle, [])

    def test_cancelled_registration_inventory_never_disconnects_or_connects(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.calls.clear()
        fixture.connect_state = "device"
        listings = [0]

        def cancel_during_action():
            listings[0] += 1
            if listings[0] == 3:
                fixture.control._session.begin_shutdown()

        fixture.after_list = cancel_during_action
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(listings[0], 3)
        self.assertFalse(
            any(argv[1] in {"disconnect", "connect"} for argv, _ in fixture.calls)
        )
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_cancelled_disconnect_never_sends_registration_connect(self):
        fixture = self.fixture
        self.assertTrue(fixture.control.start().ok)
        fixture.states.clear()
        fixture.calls.clear()
        fixture.connect_state = "device"
        fixture.after_disconnect = fixture.control._session.begin_shutdown
        result = fixture.control.recover()
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "cancelled")
        self.assertTrue(any(argv[1] == "disconnect" for argv, _ in fixture.calls))
        self.assertFalse(any(argv[1] == "connect" for argv, _ in fixture.calls))
        fixture.adapter.rebind.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_new_sessions_refresh_only_the_same_vm_and_validate_first_frame(self):
        fixture = self.fixture
        for port in (62125, 63218):
            serial = f"127.0.0.1:{port}"
            fixture.vm.write_text(
                (FIXTURES / "nox_vm.vbox")
                .read_text(encoding="utf-8")
                .replace("62125", str(port)),
                encoding="utf-8",
            )
            fixture.states[serial] = "device"
            fixture.boots[serial] = BOOT
            fixture.io.targets = list(fixture.states.items())
            result = fixture.control.start()
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.serial, serial)
            self.assertEqual(fixture.configuration.device.instance_id, "Nox_2")
            fixture.control.close()
        self.assertFalse(any("127.0.0.1:62001" in argv for argv, _ in fixture.calls))
        self.assertEqual(fixture.lifecycle, [])
        self.assertEqual(
            fixture.adapter.open_verified.call_args.args[1].observations["frame"],
            [1920, 1080],
        )

    def test_wrong_online_endpoint_is_rejected_without_switching_vm(self):
        fixture = self.fixture
        fixture.boots["127.0.0.1:62125"] = OTHER_BOOT
        result = fixture.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "endpoint_unresolved")
        fixture.adapter.open_verified.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])
        self.assertFalse(any("127.0.0.1:62001" in argv for argv, _ in fixture.calls))

    def test_same_name_recreated_vm_requires_confirmation_before_adb_or_lifecycle(self):
        fixture = self.fixture
        fixture.configuration.device.last_serial = "127.0.0.1:62001"
        fixture.vm.write_text(
            fixture.vm.read_text().replace(
                "5e1aaadc-7991-419d-a2b6-f030b497b282",
                "bc63cd6d-39b1-4ea0-984c-f32dfe269e67",
            )
        )
        result = fixture.control.start()
        self.assertEqual(result.error.code, "topology_changed")
        fixture.adapter.open_verified.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])
        self.assertFalse(
            any("-s" in argv or "devices" in argv for argv, _ in fixture.calls)
        )

    def test_deleted_vm_does_not_reuse_saved_endpoint(self):
        fixture = self.fixture
        fixture.listing = b""
        fixture.configuration.device.last_serial = "127.0.0.1:62001"
        result = fixture.control.start()
        self.assertEqual(result.error.code, "topology_changed")
        fixture.adapter.open_verified.assert_not_called()
        self.assertEqual(fixture.lifecycle, [])

    def test_stopped_vm_preflight_is_read_only_and_start_targets_current_title_once(
        self,
    ):
        fixture = self.fixture
        fixture.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
        result = fixture.control.preflight()
        self.assertEqual(result.error.code, "instance_stopped")
        self.assertEqual(fixture.lifecycle, [])
        result = fixture.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(fixture.lifecycle, [("launch", "-name:日常号")])

    def test_stopped_vm_waits_for_same_endpoint_to_leave_absent_and_offline(self):
        fixture = self.fixture
        fixture.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
        fixture.launch_delay = [None, "offline", "device"]
        result = fixture.control.start()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:62125")
        self.assertEqual(fixture.lifecycle, [("launch", "-name:日常号")])
        self.assertFalse(any("127.0.0.1:62001" in argv for argv, _ in fixture.calls))

    def test_pending_endpoint_exhausts_one_startup_budget_without_another_launch(self):
        fixture = self.fixture
        fixture.listing = (FIXTURES / "nox_stopped.txt").read_bytes()
        fixture.launch_delay = [None]
        result = fixture.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "recovery_exhausted")
        self.assertEqual(fixture.lifecycle, [("launch", "-name:日常号")])
        fixture.adapter.open_verified.assert_not_called()

    def test_unavailable_adb_preflight_never_runs_shell_commands_or_restarts(self):
        for state, code in (
            ("offline", "device_offline"),
            ("unauthorized", "device_unauthorized"),
            ("absent", "endpoint_unresolved"),
        ):
            with self.subTest(state=state):
                fixture = self.fixture
                fixture.states["127.0.0.1:62125"] = state
                fixture.calls.clear()
                result = fixture.control.preflight()
                self.assertEqual(result.error.code, code)
                self.assertFalse(
                    any(
                        "-s" in argv or "adb" in argv or "connect" in argv
                        for argv, _ in fixture.calls
                    )
                )
                self.assertEqual(fixture.lifecycle, [])
                fixture.control.close()

    def test_wrong_frame_is_rejected_after_identity_validation(self):
        import numpy as np

        fixture = self.fixture
        for size, code in (
            ("Physical size: 1280x720", "frame_failed"),
            ("Physical size: 1920x1080", "frame_failed"),
        ):
            fixture.io.size = size
            fixture.io.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            result = fixture.control.start()
            self.assertEqual(result.error.code, code)
            fixture.adapter.open_verified.assert_not_called()
            fixture.control.close()

    def test_a_portrait_reported_size_is_accepted_when_the_frame_matches(self):
        import numpy as np

        fixture = self.fixture
        # A tablet presentation reports portrait while already rendering the
        # landscape frame the templates need.
        fixture.io.size = "Physical size: 1080x1920"
        fixture.io.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = fixture.control.start()
        self.assertTrue(result.ok, result.error)
        fixture.adapter.open_verified.assert_called_once()
        fixture.control.close()

    def test_shared_adb_mismatch_blocks_vendor_command(self):
        fixture = self.fixture
        fixture.version = "Android Debug Bridge version 1.0.40"
        with self.assertRaises(SharedADBError):
            ProductionSimulator(run=fixture.run, probe=lambda timeout: 41).inspect(
                fixture.configuration.device, 6
            )
        self.assertFalse(any("adb" in argv for argv, _ in fixture.calls))

    def test_disabled_or_snapshot_forwarding_is_not_a_current_endpoint(self):
        fixture = self.fixture
        fixture.vm.write_text(
            fixture.vm.read_text().replace('enabled="true"', 'enabled="false"')
        )
        result = fixture.control.start()
        self.assertEqual(result.error.code, "endpoint_unresolved")
        self.assertFalse(any("-s" in argv for argv, _ in fixture.calls))

    def test_explicit_lifecycle_stop_uses_bound_vm_name_and_rechecks_topology(self):
        fixture = self.fixture
        self.assertTrue(fixture.simulator.stop(fixture.configuration.device, 6))
        self.assertEqual(fixture.lifecycle, [("quit", "Nox_2")])
        fixture.listing = b""
        with self.assertRaises(ValueError):
            fixture.simulator.start(fixture.configuration.device, 6)
        self.assertEqual(fixture.lifecycle, [("quit", "Nox_2")])

    def test_duplicate_titles_block_vendor_title_addressing(self):
        fixture = self.fixture
        other = fixture.root / "BignoxVMS/nox/nox.vbox"
        other.parent.mkdir(parents=True)
        other.write_text(
            fixture.vm.read_text()
            .replace("Nox_2", "nox")
            .replace(
                "5e1aaadc-7991-419d-a2b6-f030b497b282",
                "bc63cd6d-39b1-4ea0-984c-f32dfe269e67",
            )
        )
        fixture.listing += "nox,日常号,0,0,0,-1\n".encode()
        candidate = fixture.control.discover().candidates[0]
        fixture.configuration = fixture.configuration.updated(
            {"device": candidate["binding"]}
        )
        result = fixture.control.start()
        self.assertEqual(result.error.code, "binding_failed")
        self.assertEqual(fixture.lifecycle, [])
        self.assertFalse(any("adb" in argv for argv, _ in fixture.calls))

    def test_multiple_verified_forwardings_require_explicit_serial(self):
        fixture = self.fixture
        fixture.vm.write_text(
            fixture.vm.read_text().replace(
                "</NAT>",
                '<Forwarding name="other" proto="1" hostip="127.0.0.1" hostport="63333" guestport="5555"/></NAT>',
            )
        )
        fixture.states["127.0.0.1:63333"] = "device"
        fixture.boots["127.0.0.1:63333"] = BOOT
        result = fixture.control.preflight()
        self.assertEqual(result.error.code, "endpoint_ambiguous")
        fixture.configuration.device.last_serial = "127.0.0.1:62125"
        self.assertTrue(fixture.control.preflight().ok)

    def test_restarted_vm_during_identity_probe_is_rejected(self):
        fixture = self.fixture

        def restart():
            fixture.listing = fixture.listing.replace(b"1200", b"2400")

        fixture.after_shell = restart
        result = fixture.control.start()
        self.assertEqual(result.error.code, "binding_changed")
        fixture.adapter.open_verified.assert_not_called()


if __name__ == "__main__":
    unittest.main()
