"""Bounded default-display preparation commands and input observations."""

import subprocess
import unittest
from unittest.mock import Mock

from arknights_mower.utils.device.preparation_io import ProductionPreparationIO


class PreparationIOTests(unittest.TestCase):
    def test_size_write_and_reset_only_address_the_explicit_default_display(self):
        commands = []

        def run(argv, **kwargs):
            commands.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        io = ProductionPreparationIO(run=run, probe=lambda timeout: None)
        io.set_size("chosen-adb", "USB-123", [1080, 1920])
        io.set_size("chosen-adb", "USB-123", None)
        self.assertEqual(
            [argv for argv, _ in commands],
            [
                ["chosen-adb", "-s", "USB-123", "shell", "wm", "size", "1080x1920"],
                ["chosen-adb", "-s", "USB-123", "shell", "wm", "size", "reset"],
            ],
        )
        for _, kwargs in commands:
            self.assertTrue(kwargs["check"])
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 10)
            self.assertFalse(kwargs.get("shell", False))

    def test_input_surface_reads_the_explicit_devices_default_viewport(self):
        for viewport in (
            "Viewport INTERNAL: displayId=0, uniqueId=local:1, port=0, orientation=1, "
            "logicalFrame=[0, 0, 1920, 1080], physicalFrame=[0, 0, 2560, 1440], "
            "deviceSize=[1440, 2560], isActive=[1]",
            "DisplayViewport{type=INTERNAL, valid=true, isActive=true, displayId=0, "
            "uniqueId='local:1', physicalPort=0, orientation=1, "
            "logicalFrame=Rect(0, 0 - 1920, 1080), "
            "physicalFrame=Rect(0, 0 - 2560, 1440), deviceWidth=1440, deviceHeight=2560}",
        ):
            with self.subTest(viewport=viewport):
                commands = []

                def run(argv, **kwargs):
                    commands.append(argv)
                    return subprocess.CompletedProcess(argv, 0, viewport.encode(), b"")

                io = ProductionPreparationIO(run=run, probe=lambda timeout: None)
                self.assertEqual(
                    io.input_surface("chosen-adb", "USB-123"), (1920, 1080)
                )
                self.assertEqual(
                    commands,
                    [["chosen-adb", "-s", "USB-123", "shell", "dumpsys", "input"]],
                )

    def test_unknown_ambiguous_inactive_or_offset_input_surfaces_are_rejected(self):
        native = (
            "Viewport INTERNAL: displayId=0, orientation=1, "
            "logicalFrame=[0, 0, 1920, 1080], isActive=[1]"
        )
        for output in (
            "",
            "logicalFrame=[0, 0, 1920, 1080]",
            native.replace("displayId=0", "displayId=1"),
            native.replace("INTERNAL", "VIRTUAL"),
            native.replace("isActive=[1]", "isActive=[0]"),
            native.replace("[0, 0, 1920", "[1, 0, 1920"),
            native.replace("logicalFrame=[0, 0, 1920, 1080]", "logicalFrame=unknown"),
            native + "\n" + native.replace("1920, 1080", "1080, 1920"),
            native.replace("displayId=0", "displayId=0, displayId=0"),
            native.replace("displayId=0", "displayId=0, displayId=unknown"),
            native.replace("isActive=[1]", "isActive=unknown"),
            native + ", logicalFrame=unknown",
            "DisplayViewport{type=INTERNAL, valid=false, displayId=0, "
            "logicalFrame=Rect(0, 0 - 1920, 1080)}",
        ):
            with self.subTest(output=output):
                run = Mock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, output.encode(), b""
                    )
                )
                io = ProductionPreparationIO(run=run, probe=lambda timeout: None)
                with self.assertRaises(ValueError):
                    io.input_surface("chosen-adb", "USB-123")

    def test_repeated_identical_input_viewports_are_one_surface(self):
        output = (
            "Viewport INTERNAL: displayId=0, orientation=1, "
            "logicalFrame=[0, 0, 1920, 1080], isActive=[1]\n"
        ) * 2
        run = Mock(
            return_value=subprocess.CompletedProcess([], 0, output.encode(), b"")
        )
        io = ProductionPreparationIO(run=run, probe=lambda timeout: None)
        self.assertEqual(io.input_surface("chosen-adb", "USB-123"), (1920, 1080))

    def test_size_write_rejects_nonzero_and_misleading_zero_exit(self):
        for result in (
            subprocess.CompletedProcess([], 1, b"", b"permission denied"),
            subprocess.CompletedProcess([], 0, b"Error: permission denied", b""),
            subprocess.CompletedProcess([], 0, b"", b"SecurityException"),
        ):
            with self.subTest(result=result):
                io = ProductionPreparationIO(
                    run=Mock(return_value=result), probe=lambda timeout: None
                )
                with self.assertRaises((subprocess.CalledProcessError, RuntimeError)):
                    io.set_size("chosen-adb", "USB-123", [1920, 1080])

    def test_invalid_write_targets_and_values_never_issue_a_command(self):
        run = Mock()
        io = ProductionPreparationIO(run=run, probe=lambda timeout: None)
        for adb, serial, value in (
            ("", "USB-123", [1920, 1080]),
            ("chosen-adb", "", [1920, 1080]),
            ("chosen-adb", "USB-123", "1920x1080; wm density reset"),
            ("chosen-adb", "USB-123", [0, 1080]),
            ("chosen-adb", "USB-123", [True, 1080]),
            ("chosen-adb", "USB-123", [1920]),
        ):
            with self.subTest(adb=adb, serial=serial, value=value):
                with self.assertRaises(ValueError):
                    io.set_size(adb, serial, value)
        run.assert_not_called()

    def test_read_observations_reuse_preflight_on_the_same_pinned_serial(self):
        reader = Mock()
        reader.devices.return_value = [("USB-123", "device")]
        reader.display_size.return_value = "Physical size: 1920x1080"
        io = ProductionPreparationIO(preflight=reader)
        self.assertEqual(io.devices("chosen-adb", "USB-123"), [("USB-123", "device")])
        self.assertEqual(
            io.display_size("chosen-adb", "USB-123"), "Physical size: 1920x1080"
        )
        reader.devices.assert_called_once_with("chosen-adb", "USB-123")
        reader.display_size.assert_called_once_with("chosen-adb", "USB-123")


if __name__ == "__main__":
    unittest.main()
