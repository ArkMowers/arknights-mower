"""Docker I/O safety observed through discovery and bound read-only preflight."""

import json
import os
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_redroid_tests import DockerFixture
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService


class RedroidIOTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.docker = DockerFixture(root)
        self.responses = {}
        self.elapsed = 0
        self.docker.controller.run = self.run_command
        self.io = PreflightIO()
        self.io.installed.update({str(root), str(self.docker.manager)})
        self.io.targets = [("USB-123", "device"), ("127.0.0.1:15555", "device")]
        self.conf = Conf(device={"preset_id": "linux.redroid"})
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.docker.controller, redroid=self.docker.controller
            ),
        )

    def run_command(self, argv, **options):
        result = self.docker.run(argv, **options)
        stage = next(name for name in ("version", "ls", "inspect") if name in argv)
        result = self.responses.get(stage, result)
        self.docker.clock.sleep(self.elapsed)
        if isinstance(result, BaseException):
            raise result
        return result

    def bind(self):
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})

    def test_local_socket_and_clean_environment_survive_remote_context_settings(self):
        remote = {
            "DOCKER_HOST": "ssh://remote.invalid",
            "DOCKER_CONTEXT": "remote-context",
            "DOCKER_TLS": "1",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": "/remote/certificates",
            "DOCKER_API_VERSION": "1.24",
        }
        with patch.dict(os.environ, {**remote, "MOWER_TEST_ENV": "retained"}):
            self.bind()
            checked = self.control.preflight()
        self.assertTrue(checked.ok, checked.error)
        self.assertEqual(checked.serial, "127.0.0.1:15555")
        for argv, options in self.docker.calls:
            self.assertIsInstance(argv, list)
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertEqual(
                argv[argv.index("--host") + 1], "unix:///var/run/docker.sock"
            )
            self.assertNotIn("--context", argv)
            self.assertFalse(options.get("shell", False))
            self.assertGreater(options["timeout"], 0)
            self.assertLessEqual(options["timeout"], 3)
            self.assertTrue(options["check"])
            self.assertEqual(options["env"]["MOWER_TEST_ENV"], "retained")
            self.assertTrue(set(remote).isdisjoint(options["env"]))
            self.assertFalse(
                {"start", "stop", "restart", "run", "exec"}.intersection(argv)
            )

    def test_other_hosts_reject_before_docker_or_adb_access(self):
        for host, controller_host in (
            ("windows", "linux"),
            ("macos", "linux"),
            ("linux", "win32"),
            ("linux", "darwin"),
        ):
            with self.subTest(host=host, controller_host=controller_host):
                self.io.host = host
                self.docker.controller.host = controller_host
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "unsupported_host")
                self.assertEqual(found.candidates, [])
                self.assertEqual(self.docker.calls, [])

    def test_podman_and_unidentified_servers_require_manual_configuration(self):
        for server in (
            {
                "Platform": {"Name": "linux/amd64/fedora-42"},
                "Components": [{"Name": "Podman Engine", "Version": "5.5.0"}],
            },
            {"Platform": {"Name": "Docker Engine - Community"}, "Components": []},
            {"Components": [{"Name": "Engine"}]},
        ):
            with self.subTest(server=server):
                self.docker.server = server
                self.docker.calls.clear()
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "redroid_manual_required")
                self.assertEqual(found.error.action, "manual")
                self.assertEqual(found.candidates, [])
                self.assertFalse(any("ls" in argv for argv, _ in self.docker.calls))

    def test_each_command_failure_returns_repair_without_changing_configuration(self):
        cases = (
            (subprocess.TimeoutExpired("docker", 3), "manager_timeout"),
            (PermissionError("denied"), "discovery_permission_denied"),
            (OSError("service unavailable"), "docker_unavailable"),
            (subprocess.CalledProcessError(1, "docker"), "docker_unavailable"),
            (subprocess.CompletedProcess([], 1, b"success", b""), "docker_unavailable"),
            (subprocess.CompletedProcess([], 0, b"", b"error"), "docker_unavailable"),
            (
                subprocess.CompletedProcess([], 0, b"\xff", b""),
                "manager_output_invalid",
            ),
            (
                subprocess.CompletedProcess([], 0, b"x" * (1024 * 1024 + 1), b""),
                "manager_output_invalid",
            ),
            (ValueError("manager output exceeds 1 MiB"), "manager_output_invalid"),
        )
        before = self.conf.model_dump()
        for stage in ("version", "ls", "inspect"):
            for response, expected in cases:
                with self.subTest(
                    stage=stage, expected=expected, response=type(response)
                ):
                    self.responses = {stage: response}
                    found = self.control.discover()
                    self.assertFalse(found.ok)
                    self.assertEqual(found.error.code, expected)
                    self.assertTrue(found.error.message)
                    self.assertEqual(found.candidates, [])
                    self.assertEqual(self.conf.model_dump(), before)

    def test_discovery_budget_covers_all_commands_and_checks_late_completion(self):
        for elapsed in (4, 10):
            with self.subTest(elapsed=elapsed):
                self.elapsed = elapsed
                self.docker.clock.now = 0
                self.docker.calls.clear()
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "manager_timeout")
                self.assertEqual(found.candidates, [])
                self.assertLessEqual(len(self.docker.calls), 3 if elapsed == 4 else 1)
                self.assertTrue(
                    all(options["timeout"] <= 3 for _, options in self.docker.calls)
                )

    def test_malformed_inspect_types_and_container_ids_never_select_another_instance(
        self,
    ):
        invalid = [
            (output, "manager_output_invalid")
            for output in self.docker.fixtures["malformed_inspect"]
        ]
        invalid.extend(
            (
                (json.dumps([{"Id": 123}]), "manager_output_invalid"),
                (json.dumps([{"Id": "b" * 64}]), "redroid_binding_changed"),
                (json.dumps([self.docker.rows[0]] * 2), "manager_output_invalid"),
            )
        )
        for output, expected in invalid:
            with self.subTest(output=output):
                self.docker.inspect_output = output
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, expected)
                self.assertEqual(found.candidates, [])
                self.assertIsNone(found.selected_key)

    def test_invalid_inspect_fields_are_rejected_instead_of_coerced(self):
        original = deepcopy(self.docker.rows[0])
        changes = (
            {"Name": None},
            {"Config": []},
            {"Config": {"Image": 12}},
            {"Config": {**original["Config"], "Labels": []}},
            {"HostConfig": None},
            {"State": {**original["State"], "Running": "true"}},
            {"State": {**original["State"], "Paused": "false"}},
            {"NetworkSettings": []},
            {"NetworkSettings": {"Ports": []}},
            {
                "NetworkSettings": {
                    "Ports": {"5555/tcp": [{"HostIp": "0.0.0.0", "HostPort": 5555}]}
                }
            },
            {
                "NetworkSettings": {
                    "Ports": {"5555/tcp": [{"HostIp": "0.0.0.0", "HostPort": "65536"}]}
                }
            },
        )
        for change in changes:
            with self.subTest(change=change):
                self.docker.rows = [{**deepcopy(original), **change}]
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "manager_output_invalid")
                self.assertEqual(found.candidates, [])

    def test_invalid_or_repeated_list_ids_are_not_inspected(self):
        for output in (b"short-id", b"a" * 64 + b"\n" + b"a" * 64, b"../container"):
            with self.subTest(output=output):
                self.responses = {"ls": subprocess.CompletedProcess([], 0, output, b"")}
                self.docker.calls.clear()
                found = self.control.discover()
                self.assertEqual(found.error.code, "manager_output_invalid")
                self.assertEqual(found.candidates, [])
                self.assertFalse(
                    any("inspect" in argv for argv, _ in self.docker.calls)
                )

    def test_nonstandard_network_or_orchestrator_requires_manual_configuration(self):
        original = deepcopy(self.docker.rows[0])
        changes = [
            {"HostConfig": {"NetworkMode": mode}}
            for mode in ("host", "none", "container:another-id", "custom-network")
        ]
        changes.extend(
            {"Config": {**original["Config"], "Labels": {label: "managed"}}}
            for label in ("io.kubernetes.pod.uid", "com.docker.swarm.service.id")
        )
        for change in changes:
            with self.subTest(change=change):
                self.docker.rows = [{**deepcopy(original), **change}]
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "redroid_manual_required")
                self.assertEqual(found.error.action, "manual")
                self.assertEqual(found.candidates, [])
        self.assertFalse(any("start" in argv for argv, _ in self.docker.calls))

    def test_remote_or_custom_socket_is_never_contacted(self):
        for socket in (
            "ssh://remote",
            "tcp://127.0.0.1:2375",
            "unix:///run/user/1000/docker.sock",
        ):
            with self.subTest(socket=socket):
                self.conf.device.config_path = socket
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.action, "manual")
                self.assertEqual(found.candidates, [])
                self.assertEqual(self.docker.calls, [])

    def test_custom_image_names_are_never_discovered_or_controlled(self):
        for image in (
            "redroid:latest",
            "example/redroid:latest",
            "registry.invalid/redroid/redroid:latest",
            "redroid/redroid-custom:latest",
            "example/redroid/redroid:latest",
        ):
            with self.subTest(image=image):
                self.docker.rows[0]["Config"]["Image"] = image
                found = self.control.discover()
                self.assertFalse(found.ok)
                self.assertEqual(found.error.code, "no_redroid")
                self.assertEqual(found.error.action, "manual")
                self.assertEqual(found.candidates, [])
        self.assertFalse(any("start" in argv for argv, _ in self.docker.calls))

    def test_changed_bound_id_stops_before_adb_even_when_saved_endpoint_is_online(self):
        self.bind()
        self.conf.device.last_serial = "USB-123"
        self.docker.inspect_output = json.dumps(
            [{**self.docker.rows[0], "Id": "d" * 64}]
        )
        before = self.conf.model_dump()
        with patch.object(self.io, "devices", wraps=self.io.devices) as devices:
            checked = self.control.preflight()
        self.assertFalse(checked.ok)
        self.assertEqual(checked.error.code, "redroid_binding_changed")
        self.assertEqual(checked.serial, "")
        devices.assert_not_called()
        self.assertEqual(self.conf.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
