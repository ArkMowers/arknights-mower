import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.utils import windows_shortcuts as shortcuts


class WindowsShortcutTests(unittest.TestCase):
    def test_source_and_other_platforms_do_not_launch_powershell(self):
        for platform, frozen in (("win32", False), ("darwin", True), ("linux", True)):
            with (
                self.subTest(platform=platform, frozen=frozen),
                patch.object(
                    shortcuts, "sys", SimpleNamespace(platform=platform, frozen=frozen)
                ),
                patch.object(shortcuts.subprocess, "run") as run,
            ):
                shortcuts.create_admin_shortcuts()
                run.assert_not_called()

    def test_frozen_windows_uses_real_executable_directory_and_bounded_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "中文 ' & $ Mower"
            root.mkdir()
            with (
                patch.object(
                    shortcuts,
                    "sys",
                    SimpleNamespace(
                        platform="win32",
                        frozen=True,
                        executable=str(root / "mower.exe"),
                    ),
                ),
                patch.object(shortcuts.subprocess, "run") as run,
            ):
                shortcuts.create_admin_shortcuts()
            command = run.call_args.args[0]
            self.assertEqual(
                command[:4],
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand"],
            )
            self.assertEqual(
                base64.b64decode(command[4]).decode("utf-16le"),
                shortcuts._CREATE_SHORTCUTS,
            )
            self.assertEqual(
                run.call_args.kwargs["env"]["MOWER_SHORTCUT_ROOT"], str(root.resolve())
            )
            self.assertEqual(run.call_args.kwargs["cwd"], root.resolve())
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
            self.assertTrue(run.call_args.kwargs["check"])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_creation_failure_is_logged_without_blocking_startup_or_retrying(self):
        for error in (
            PermissionError("read-only directory"),
            subprocess.TimeoutExpired("powershell", 5),
            subprocess.CalledProcessError(1, "powershell"),
        ):
            logger = Mock()
            temporary_paths = []

            def fail(*args, **kwargs):
                temporary = Path(kwargs["env"]["MOWER_SHORTCUT_TEMP"])
                (temporary / "incomplete.lnk").write_bytes(b"partial link")
                temporary_paths.append(temporary)
                raise error

            with (
                self.subTest(error=error),
                patch.object(
                    shortcuts,
                    "sys",
                    SimpleNamespace(
                        platform="win32",
                        frozen=True,
                        executable=str(Path.cwd() / "mower.exe"),
                    ),
                ),
                patch.object(shortcuts.subprocess, "run", side_effect=fail) as run,
                patch.dict(
                    sys.modules,
                    {"arknights_mower.utils.log": SimpleNamespace(logger=logger)},
                ),
            ):
                shortcuts.create_admin_shortcuts()
                run.assert_called_once()
                logger.warning.assert_called_once()
                self.assertFalse(temporary_paths[0].exists())

        logger = Mock()
        with (
            patch.object(
                shortcuts,
                "sys",
                SimpleNamespace(
                    platform="win32",
                    frozen=True,
                    executable=str(Path.cwd() / "mower.exe"),
                ),
            ),
            patch.object(
                shortcuts.tempfile,
                "TemporaryDirectory",
                side_effect=PermissionError("protected installation"),
            ),
            patch.object(shortcuts.subprocess, "run") as run,
            patch.dict(
                sys.modules,
                {"arknights_mower.utils.log": SimpleNamespace(logger=logger)},
            ),
        ):
            shortcuts.create_admin_shortcuts()
            run.assert_not_called()
            logger.warning.assert_called_once()

    def test_both_desktop_entry_points_create_shortcuts_before_opening_windows(self):
        import manager
        import webview_ui
        from arknights_mower.utils import update_runtime as runtime

        for entry in (manager.run_manager, webview_ui._run_desktop):
            with (
                self.subTest(entry=entry.__name__),
                patch.object(runtime, "active_job", return_value=False),
                patch.object(runtime, "read_json", return_value={}),
                patch.object(shortcuts, "create_admin_shortcuts") as create,
                patch.object(
                    webview_ui,
                    "exit_if_webview_backend_missing",
                    side_effect=RuntimeError("stop before GUI"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "stop before GUI"):
                    entry()
                create.assert_called_once_with()


@unittest.skipUnless(sys.platform == "win32", "Requires Windows Shell")
class NativeWindowsShortcutTests(unittest.TestCase):
    def test_native_links_target_both_executables_and_refresh_after_directory_move(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "中文 ' & $ Mower"
            root.mkdir()
            for name in ("mower.exe", "多开管理器.exe"):
                (root / name).touch()

            run = subprocess.run

            def run_checked(*args, **kwargs):
                try:
                    return run(*args, **kwargs)
                except subprocess.CalledProcessError as error:
                    self.fail(
                        "Native shortcut generation failed:\n"
                        + error.stderr.decode("utf-8", errors="replace")
                    )

            def create(directory):
                with (
                    patch.object(
                        shortcuts,
                        "sys",
                        SimpleNamespace(
                            platform="win32",
                            frozen=True,
                            executable=str(directory / "mower.exe"),
                        ),
                    ),
                    patch.object(shortcuts.subprocess, "run", side_effect=run_checked),
                ):
                    shortcuts.create_admin_shortcuts()

            def verify(directory):
                for name in ("mower", "多开管理器"):
                    link = directory / f"{name}（管理员启动）.lnk"
                    data = link.read_bytes()
                    self.assertEqual(struct.unpack_from("<I", data)[0], 0x4C)
                    self.assertTrue(struct.unpack_from("<I", data, 20)[0] & 0x2000)
                script = """
                [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
                $shell = New-Object -ComObject WScript.Shell
                @('mower', '多开管理器') | ForEach-Object {
                    $link = $shell.CreateShortcut((Join-Path $env:MOWER_SHORTCUT_ROOT ($_ + '（管理员启动）.lnk')))
                    @{ target = $link.TargetPath; directory = $link.WorkingDirectory }
                } | ConvertTo-Json -Compress
                """
                env = os.environ.copy()
                env["MOWER_SHORTCUT_ROOT"] = str(directory)
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-EncodedCommand",
                        base64.b64encode(script.encode("utf-16le")).decode("ascii"),
                    ],
                    env=env,
                    capture_output=True,
                    encoding="utf-8",
                    timeout=5,
                    check=True,
                )
                self.assertEqual(
                    json.loads(result.stdout),
                    [
                        {
                            "target": str(directory / "mower.exe"),
                            "directory": str(directory),
                        },
                        {
                            "target": str(directory / "多开管理器.exe"),
                            "directory": str(directory),
                        },
                    ],
                )

            create(root)
            verify(root)
            original = {
                link.name: (link.read_bytes(), link.stat().st_mtime_ns)
                for link in root.glob("*.lnk")
            }
            create(root)
            self.assertEqual(
                original,
                {
                    link.name: (link.read_bytes(), link.stat().st_mtime_ns)
                    for link in root.glob("*.lnk")
                },
            )
            moved = root.rename(Path(temporary) / "移动后的目录")
            create(moved)
            verify(moved)
            self.assertEqual(len(list(moved.glob("*.lnk"))), 2)
            self.assertEqual(len(list(moved.iterdir())), 4)


if __name__ == "__main__":
    unittest.main()
