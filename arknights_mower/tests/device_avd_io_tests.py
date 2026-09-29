"""SDK command-boundary fixtures; no Android SDK or live emulator required."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.avd import AVDController
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError


class EmulatorProcess:
    returncode = None

    def poll(self):
        return self.returncode


class SDKFixture:
    def __init__(self, root):
        self.manager = root / "Android SDK" / "emulator" / "emulator"
        self.manager.parent.mkdir(parents=True)
        self.manager.touch()
        self.manager.chmod(0o755)
        self.names = b"mower_api_35\n"
        self.version = b"Android emulator version 35.3.10.0 (build_id 12345)\n"
        self.devices = {}
        self.identities = {}
        self.commands = []
        self.launches = []
        self.process = EmulatorProcess()
        self.failure = None

    def run(self, argv, **kwargs):
        if kwargs.get("shell") or not isinstance(argv, list):
            raise AssertionError("SDK commands must use argv without a host shell")
        if not 0 < kwargs["timeout"] <= 3:
            raise AssertionError("SDK commands must share a bounded deadline")
        self.commands.append(argv)
        args = argv[1:]
        if self.failure is not None and args == ["-list-avds"]:
            if isinstance(self.failure, BaseException):
                raise self.failure
            return subprocess.CompletedProcess(argv, 0, b"", self.failure)
        if args == ["-version"]:
            output = self.version
        elif args == ["-list-avds"]:
            output = self.names
        elif args == ["devices", "-l"]:
            output = (
                "List of devices attached\n"
                + "\n".join(
                    f"{serial}\t{state}" for serial, state in self.devices.items()
                )
            ).encode()
        elif args[:1] == ["-s"] and args[2:] == ["emu", "avd", "name"]:
            output = self.identities[args[1]]
            if isinstance(output, BaseException):
                raise output
        elif args[:1] == ["-s"] and args[2:] == ["emu", "kill"]:
            output = b"OK: killing emulator, bye bye\nOK\n"
        else:
            raise AssertionError(f"Unexpected SDK command {argv!r}")
        return subprocess.CompletedProcess(argv, 0, output, b"")

    def spawn(self, argv, **kwargs):
        if kwargs.get("shell"):
            raise AssertionError("AVD startup must not use a shell")
        self.launches.append((argv, kwargs))
        return self.process

    def controller(self, **kwargs):
        return AVDController(
            run=self.run,
            spawn=self.spawn,
            probe=lambda timeout: None,
            environment={},
            home=self.manager.parent.parent.parent,
            which=lambda name: None,
            **kwargs,
        )

    def profile(self):
        return DeviceProfile(
            preset_id="linux.avd",
            installation_path=str(self.manager.parent.parent),
            manager_path=str(self.manager),
            instance_id="mower_api_35",
            adb_path=str(self.manager.parent.parent / "platform-tools/adb"),
        )

    def online(self, serial="emulator-5554", name="mower_api_35"):
        self.devices[serial] = "device"
        self.identities[serial] = f"{name}\nOK\n".encode()


class AVDIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sdk = SDKFixture(Path(self.temp.name))
        self.controller = self.sdk.controller()
        self.profile = self.sdk.profile()

    def discover(self, profile=None, host="linux"):
        return self.controller.discover(profile or self.profile, host)

    def assert_error(self, code, operation):
        with self.assertRaises(InstanceBindingError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        return str(raised.exception)

    def test_missing_sdk_and_unsupported_host_give_repair_fields(self):
        result = self.discover(DeviceProfile(preset_id="linux.avd"))
        self.assertEqual(result["errors"][0].code, "missing_sdk")
        self.assertIn("installation_path", result["errors"][0].fields)
        result = self.discover(host="windows")
        self.assertEqual(result["errors"][0].code, "unsupported_host")
        self.assertEqual(self.sdk.commands, [])

    def test_no_avd_has_creation_instructions(self):
        self.sdk.names = b""
        result = self.discover()
        self.assertEqual(result["errors"][0].code, "no_avd")
        self.assertIn("Device Manager", result["errors"][0].message)
        self.assertEqual(result["installations"], [])

    def test_single_and_multiple_avds_remain_name_bindings_without_serial(self):
        for names in (["mower_api_35"], ["mower_api_35", "other_api_34"]):
            with self.subTest(names=names):
                self.sdk.names = "\n".join(names).encode()
                result = self.discover()
                self.assertEqual(result["errors"], [])
                installation = result["installations"][0]
                self.assertEqual(installation["preset_id"], "linux.avd")
                self.assertEqual(
                    installation["manager_path"], str(self.sdk.manager.resolve())
                )
                self.assertEqual(
                    [row["instance_id"] for row in installation["instances"]], names
                )
                self.assertTrue(
                    all(row["serial"] == "" for row in installation["instances"])
                )
        self.assertEqual(self.sdk.launches, [])

    def test_macos_uses_official_sdk_layout(self):
        manager = Path(self.temp.name) / "Library/Android/sdk/emulator/emulator"
        manager.parent.mkdir(parents=True)
        manager.touch()
        manager.chmod(0o755)
        result = self.discover(DeviceProfile(preset_id="macos.avd"), host="macos")
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["installations"][0]["manager_path"], str(manager.resolve())
        )

    def test_error_word_is_a_valid_avd_name_when_not_a_diagnostic(self):
        self.sdk.names = b"Error\n"
        self.assertEqual(
            self.discover()["installations"][0]["instances"][0]["instance_id"],
            "Error",
        )
        profile = self.profile.model_copy(update={"instance_id": "Error"})
        self.sdk.online(name="Error")
        self.assertEqual(self.controller.inspect(profile, 10).serial, "emulator-5554")

    def test_explicit_path_wins_over_sdk_environment_and_path(self):
        self.controller.environment = {"ANDROID_SDK_ROOT": "/missing-sdk"}
        self.controller.which = lambda name: "/another/emulator"
        self.discover()
        self.assertEqual(
            self.sdk.commands[0], [str(self.sdk.manager.resolve()), "-version"]
        )
        self.assertEqual(
            self.sdk.commands[1], [str(self.sdk.manager.resolve()), "-list-avds"]
        )

    def test_explicit_sdk_root_resolves_emulator_without_a_manager_override(self):
        result = self.discover(self.profile.model_copy(update={"manager_path": ""}))
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["installations"][0]["manager_path"], str(self.sdk.manager.resolve())
        )

    def test_sdk_execution_permission_failure_does_not_run_the_binary(self):
        self.controller.environment = {
            "ANDROID_SDK_ROOT": str(self.sdk.manager.parent.parent)
        }
        with patch("arknights_mower.utils.device.avd.os.access", return_value=False):
            result = self.discover(DeviceProfile(preset_id="linux.avd"))
        self.assertEqual(result["errors"][0].code, "discovery_permission_denied")
        self.assertEqual(result["errors"][0].fields, ["manager_path"])
        self.assertEqual(self.sdk.commands, [])

    def test_sdk_filesystem_failures_return_actionable_errors(self):
        for operation in ("resolve", "is_file"):
            for failure, code in (
                (PermissionError("access denied"), "discovery_permission_denied"),
                (OSError("unreadable SDK volume"), "manager_failed"),
            ):
                with self.subTest(operation=operation, code=code):
                    with patch(
                        f"arknights_mower.utils.device.avd.Path.{operation}",
                        side_effect=failure,
                    ):
                        result = self.discover()
                    self.assertEqual(result["installations"], [])
                    self.assertEqual(result["errors"][0].code, code)
                    self.assertIn(str(failure), result["errors"][0].message)
                    self.assertEqual(
                        result["errors"][0].fields,
                        ["installation_path", "manager_path"],
                    )
        self.assertEqual(self.sdk.commands, [])

    def test_sdk_environment_then_path_are_verified(self):
        for source in ("ANDROID_SDK_ROOT", "ANDROID_HOME", "PATH"):
            with self.subTest(source=source):
                self.controller.environment = {}
                self.controller.which = lambda name: None
                if source == "PATH":
                    self.controller.which = lambda name: str(self.sdk.manager)
                else:
                    self.controller.environment[source] = str(
                        self.sdk.manager.parent.parent
                    )
                result = self.discover(DeviceProfile(preset_id="linux.avd"))
                self.assertEqual(result["errors"], [])
                self.assertEqual(
                    result["installations"][0]["manager_path"],
                    str(self.sdk.manager.resolve()),
                )

    def test_unverified_binary_and_malformed_avd_output_are_rejected(self):
        self.sdk.version = b"unrelated command version 1.2.3"
        self.assertEqual(self.discover()["errors"][0].code, "invalid_sdk")
        self.sdk.version = b"Android emulator version 35.3.10.0"
        for names in (b"name with spaces", b"one\none", b"FAILURE: missing image"):
            with self.subTest(names=names):
                self.sdk.names = names
                self.assertTrue(self.discover()["errors"])

    def test_stderr_zero_exit_nonzero_exit_and_timeout_are_explained(self):
        for failure, code, diagnostic in (
            (b"ERROR: cannot read AVD directory", "manager_failed", "cannot read"),
            (
                subprocess.CalledProcessError(
                    2, ["emulator", "-list-avds"], stderr=b"access denied"
                ),
                "manager_failed",
                "access denied",
            ),
            (
                subprocess.TimeoutExpired(["emulator", "-list-avds"], 3),
                "manager_timeout",
                "超时",
            ),
        ):
            with self.subTest(code=code, diagnostic=diagnostic):
                self.sdk.failure = failure
                error = self.discover()["errors"][0]
                self.assertEqual(error.code, code)
                self.assertIn(diagnostic, error.message)
                self.assertIn("-list-avds", error.message)

    def test_dynamic_serial_is_verified_by_avd_name_without_using_other_device(self):
        self.sdk.online("emulator-5554", "other_avd")
        self.sdk.online("emulator-5580")
        self.sdk.devices["usb-device"] = "device"
        result = self.controller.inspect(self.profile, 10)
        self.assertEqual((result.state, result.serial), ("running", "emulator-5580"))
        self.sdk.devices.pop("emulator-5580")
        self.sdk.online("emulator-5582")
        result = self.controller.inspect(self.profile, 10)
        self.assertEqual(result.serial, "emulator-5582")
        self.assertFalse(any("usb-device" in argv for argv in self.sdk.commands))
        self.assertFalse(any("-list-avds" in argv for argv in self.sdk.commands))

    def test_other_online_emulator_never_becomes_the_selected_endpoint(self):
        self.sdk.online(name="unrelated")
        result = self.controller.inspect(self.profile, 10)
        self.assertEqual((result.state, result.serial), ("stopped", None))
        self.assertEqual(self.sdk.launches, [])

    def test_unknown_offline_or_malformed_identity_does_not_authorize_start(self):
        self.sdk.online()
        for state, output in (
            ("offline", b"mower_api_35\nOK"),
            ("device", b"mower_api_35"),
            ("device", b"mower_api_35\nOK\nextraneous"),
            (
                "device",
                subprocess.CalledProcessError(1, "adb", stderr=b"console unavailable"),
            ),
        ):
            with self.subTest(state=state, output=output):
                self.sdk.devices["emulator-5554"] = state
                self.sdk.identities["emulator-5554"] = output
                result = self.controller.inspect(self.profile, 10)
                self.assertEqual((result.state, result.serial), ("starting", None))
                self.assert_error(
                    "avd_already_running",
                    lambda: self.controller.start_confirmed(self.profile, 10),
                )
        self.assertEqual(self.sdk.launches, [])

    def test_duplicate_names_are_ambiguous(self):
        self.sdk.online("emulator-5554")
        self.sdk.online("emulator-5556")
        self.assert_error(
            "endpoint_ambiguous", lambda: self.controller.inspect(self.profile, 10)
        )

    def test_unconfirmed_start_and_automatic_stop_never_launch_or_kill(self):
        self.assert_error(
            "start_confirmation_required",
            lambda: self.controller.start(self.profile, 10),
        )
        self.assert_error(
            "avd_restart_unsupported", lambda: self.controller.stop(self.profile, 10)
        )
        self.assertEqual(self.sdk.commands, [])
        self.assertEqual(self.sdk.launches, [])

    def test_confirmed_start_is_detached_and_preserves_an_unrelated_emulator(self):
        self.sdk.online(name="other_avd")
        self.assertTrue(self.controller.start_confirmed(self.profile, 10))
        self.assertEqual(
            self.sdk.launches[0][0],
            [str(self.sdk.manager.resolve()), "-avd", "mower_api_35"],
        )
        options = self.sdk.launches[0][1]
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["stdout"], subprocess.DEVNULL)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        result = self.controller.inspect(self.profile, 10)
        self.assertEqual((result.state, result.serial), ("starting", None))
        self.sdk.online("emulator-5590")
        self.assertEqual(
            self.controller.inspect(self.profile, 10).serial, "emulator-5590"
        )
        self.assertFalse(any("kill" in argv for argv in self.sdk.commands))

    def test_confirmation_on_a_manually_started_target_preflights_without_ownership(
        self,
    ):
        self.sdk.online()
        self.assertTrue(self.controller.start_confirmed(self.profile, 10))
        self.assertEqual(self.sdk.launches, [])
        self.assertEqual(
            self.controller.inspect(self.profile, 10).serial, "emulator-5554"
        )
        self.assertFalse(self.controller.stop_owned(self.profile, 10))
        self.assertFalse(any("kill" in argv for argv in self.sdk.commands))

    def test_startup_failure_returns_exit_code_and_manual_diagnostic_command(self):
        self.sdk.process.returncode = 7
        message = self.assert_error(
            "avd_start_failed",
            lambda: self.controller.start_confirmed(self.profile, 10),
        )
        self.assertIn("7", message)
        self.assertIn("emulator -avd mower_api_35", message)

    def test_direct_binding_cannot_start_an_unverified_emulator_binary(self):
        self.sdk.version = b"unrelated executable version 35.3.10.0"
        self.assert_error(
            "invalid_sdk", lambda: self.controller.start_confirmed(self.profile, 10)
        )
        self.assertEqual(self.sdk.launches, [])
        self.assertFalse(any("-list-avds" in argv for argv in self.sdk.commands))

    def test_delayed_startup_failure_is_visible_on_observation(self):
        self.controller.start_confirmed(self.profile, 10)
        self.sdk.process.returncode = 9
        message = self.assert_error(
            "avd_start_failed", lambda: self.controller.inspect(self.profile, 10)
        )
        self.assertIn("9", message)

    def test_user_can_confirm_a_new_attempt_after_owned_process_exits(self):
        self.controller.start_confirmed(self.profile, 10)
        self.sdk.process.returncode = 9
        self.sdk.process = EmulatorProcess()
        self.assertTrue(self.controller.start_confirmed(self.profile, 10))
        self.assertEqual(len(self.sdk.launches), 2)

    def test_removed_avd_cannot_be_started(self):
        self.sdk.names = b"other_avd"
        self.assert_error(
            "instance_missing",
            lambda: self.controller.start_confirmed(self.profile, 10),
        )
        self.assertEqual(self.sdk.launches, [])

    def test_task_end_only_stops_live_owned_and_still_matching_serial_once(self):
        self.sdk.online(name="other_avd")
        self.assertFalse(self.controller.stop_owned(self.profile, 10))
        self.controller.start_confirmed(self.profile, 10)
        self.assertFalse(self.controller.stop_owned(self.profile, 10))
        self.sdk.online("emulator-5590")
        self.controller.inspect(self.profile, 10)
        self.assertTrue(self.controller.stop_owned(self.profile, 10))
        self.assertFalse(self.controller.stop_owned(self.profile, 10))
        self.assertEqual(
            [argv[2] for argv in self.sdk.commands if "kill" in argv], ["emulator-5590"]
        )

    def test_task_end_does_not_kill_when_process_dies_serial_changes_or_name_changes(
        self,
    ):
        for scenario in ("exited", "serial_changed", "identity_changed"):
            with self.subTest(scenario=scenario):
                self.sdk.devices = {}
                self.sdk.process = EmulatorProcess()
                self.controller = self.sdk.controller()
                self.controller.start_confirmed(self.profile, 10)
                self.sdk.online("emulator-5590")
                self.controller.inspect(self.profile, 10)
                if scenario == "exited":
                    self.sdk.process.returncode = 0
                elif scenario == "serial_changed":
                    self.sdk.devices.pop("emulator-5590")
                    self.sdk.online("emulator-5592")
                else:
                    self.sdk.online("emulator-5590", "other_avd")
                self.assertFalse(self.controller.stop_owned(self.profile, 10))
        self.assertFalse(any("kill" in argv for argv in self.sdk.commands))


if __name__ == "__main__":
    unittest.main()
