"""Instance verification commands share their caller's monotonic deadline."""

import subprocess
import unittest
from contextlib import ExitStack, contextmanager, nullcontext
from unittest.mock import patch

from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.avd import AVDController
from arknights_mower.utils.device.bluestacks_endpoint import BlueStacksEndpointResolver
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.ldplayer_endpoint import LDPlayerEndpointResolver
from arknights_mower.utils.device.nox_endpoint import NoxBindingReader

BOOT_ID = b"42e9de7c-0aa1-4a25-aec5-81d7e8a1acef"
SERIAL = "127.0.0.1:5559"
ANDROID_ID = "0123456789abcdef"
PROVIDERS = ("ldplayer", "nox", "bluestacks", "avd")


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now


class EndpointBudgetTests(unittest.TestCase):
    @contextmanager
    def inspector(self, provider, clock, run):
        options = dict(run=run, probe=lambda timeout: None, monotonic=clock.monotonic)
        profile = DeviceProfile(
            instance_id="2",
            instance_name="chosen",
            adb_path="adb.exe",
            last_serial=SERIAL,
            instance_uuid=BOOT_ID.decode(),
            topology_fingerprint="topology",
        )
        with ExitStack() as patches:
            if provider == "ldplayer":
                patches.enter_context(patch("pathlib.Path.is_file", return_value=True))
                resolver = LDPlayerEndpointResolver(
                    **options, listener_ports=lambda pid, timeout: []
                )
                yield lambda timeout: resolver.inspect(
                    profile, "ldconsole.exe", timeout
                )
            elif provider == "nox":
                patches.enter_context(patch("pathlib.Path.is_file", return_value=True))
                patches.enter_context(
                    patch(
                        "arknights_mower.utils.device.nox_endpoint.nox_inventory",
                        return_value=[
                            {
                                "instance_id": profile.instance_id,
                                "instance_name": profile.instance_name,
                                "instance_uuid": profile.instance_uuid,
                                "topology_fingerprint": profile.topology_fingerprint,
                                "state": "running",
                                "pid": (223, 224),
                            }
                        ],
                    )
                )
                patches.enter_context(
                    patch(
                        "arknights_mower.utils.device.nox_endpoint._NoxObservation.candidates",
                        return_value=[SERIAL],
                    )
                )
                resolver = NoxBindingReader(**options)
                yield lambda timeout: resolver.inspect(
                    profile, "NoxConsole.exe", timeout
                )
            elif provider == "bluestacks":
                patches.enter_context(
                    patch.object(
                        BlueStacksEndpointResolver,
                        "_target",
                        return_value=(SERIAL, ANDROID_ID),
                    )
                )
                resolver = BlueStacksEndpointResolver(**options)
                yield lambda timeout: resolver.inspect(profile, timeout)
            else:
                patches.enter_context(
                    patch.object(AVDController, "_key", return_value=("emulator", "2"))
                )
                resolver = AVDController(**options)
                yield lambda timeout: resolver.inspect(profile, timeout)

    @staticmethod
    def response(provider, argv):
        if argv[1] == "list2":
            output = b"2,chosen,0,0,1,223,224\n"
        elif argv[1] == "list":
            output = b"inventory"
        elif argv[1] == "devices":
            serial = "emulator-5558" if provider == "avd" else SERIAL
            output = f"List of devices attached\n{serial}\tdevice\n".encode()
        elif "settings" in argv:
            output = ANDROID_ID.encode()
        elif "emu" in argv:
            output = b"2\nOK\n"
        else:
            output = BOOT_ID
        return subprocess.CompletedProcess(argv, 0, output, b"")

    def test_commands_use_the_tightest_deadline_and_per_command_limit(self):
        for provider in PROVIDERS:
            for budget, outer in ((0.25, None), (0.25, 1), (1, 0.25), (10, None)):
                with self.subTest(provider=provider, budget=budget, outer=outer):
                    clock = Clock()
                    timeouts = []

                    def run(argv, **kwargs):
                        maximum = min(3, budget - clock.now)
                        if outer is not None:
                            maximum = min(maximum, outer - clock.now)
                        self.assertGreater(kwargs["timeout"], 0)
                        self.assertLessEqual(kwargs["timeout"], maximum + 1e-9)
                        timeouts.append(kwargs["timeout"])
                        clock.now += 0.01
                        return self.response(provider, argv)

                    parent = (
                        device_io_budget(lambda: outer - clock.now)
                        if outer is not None
                        else nullcontext()
                    )
                    with self.inspector(provider, clock, run) as inspect, parent:
                        result = inspect(budget)
                    self.assertIn(result.state, {"running", "unknown"})
                    self.assertGreater(len(timeouts), 1)
                    if budget < 3 or outer is not None:
                        self.assertLess(timeouts[-1], timeouts[0])

    def test_later_command_cannot_extend_the_original_deadline(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                clock = Clock()
                timeouts = []

                def run(argv, **kwargs):
                    timeout = kwargs["timeout"]
                    timeouts.append(timeout)
                    clock.now += min(0.2, timeout)
                    if timeout <= 0.2:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    return self.response(provider, argv)

                with self.inspector(provider, clock, run) as inspect:
                    with self.assertRaises(
                        (TimeoutError, ValueError, subprocess.TimeoutExpired)
                    ):
                        inspect(0.25)
                self.assertEqual(len(timeouts), 2)
                self.assertAlmostEqual(timeouts[0], 0.25)
                self.assertAlmostEqual(timeouts[1], 0.05)
                self.assertAlmostEqual(clock.now, 0.25)

    def test_expired_deadline_prevents_the_first_command(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):

                def run(argv, **kwargs):
                    self.fail("An expired inspection cannot dispatch a command")

                with self.inspector(provider, Clock(), run) as inspect:
                    with self.assertRaises((TimeoutError, ValueError)):
                        inspect(0)


if __name__ == "__main__":
    unittest.main()
