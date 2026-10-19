"""JPEG color compatibility and native process failure containment, offline."""

import gc
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import weakref
from io import BytesIO
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from arknights_mower.tests.screenshot_pipeline_tests import wait_until
from arknights_mower.utils.jpeg_codec import MAX_RAW_BYTES, encode_jpeg, frame_shape
from arknights_mower.utils.jpeg_process import launch_jpeg_process
from arknights_mower.utils.jpeg_worker import MAPPING_BYTES
from arknights_mower.utils.screenshot import ScreenshotStore
from arknights_mower.utils.screenshot_encoding import ScreenshotEncoding, worker_command


class WorkerCommands:
    def __init__(self, first_mode):
        self.first_mode = first_mode
        self.calls = 0

    def __call__(self, path, port, token):
        self.calls += 1
        mode = self.first_mode if self.calls == 1 else "lean"
        return [
            sys.executable,
            "-m",
            "arknights_mower.tests.jpeg_worker_fixtures",
            mode,
            str(path),
            str(port),
            token,
        ]


class JpegCodecTests(unittest.TestCase):
    def test_rgb_strided_readonly_and_gray_images_keep_dimensions_and_colors(self):
        rgb = np.full((64, 96, 3), (255, 0, 0), np.uint8)
        rgb[:, 48:] = (0, 0, 255)
        rgb.flags.writeable = False
        before = rgb.copy()
        for source in (rgb, rgb[:, ::2]):
            with (
                self.subTest(shape=source.shape),
                Image.open(BytesIO(encode_jpeg(source))) as image,
            ):
                decoded = np.array(image)
                self.assertEqual(image.size, (source.shape[1], source.shape[0]))
                self.assertLess(
                    np.abs(decoded[32, 5].astype(int) - (255, 0, 0)).max(), 5
                )
                self.assertLess(
                    np.abs(decoded[32, -5].astype(int) - (0, 0, 255)).max(), 5
                )
        np.testing.assert_array_equal(rgb, before)
        gray = np.full((32, 48), 127, np.uint8)
        with Image.open(BytesIO(encode_jpeg(gray))) as image:
            self.assertEqual(image.mode, "L")
            self.assertEqual(image.size, (48, 32))
            self.assertEqual(image.getpixel((10, 10)), 127)

    def test_public_encoder_and_email_attachment_do_not_call_opencv(self):
        from arknights_mower.utils import config
        from arknights_mower.utils.email import Email
        from arknights_mower.utils.image import img2bytes

        rgb = np.full((32, 48, 3), (220, 30, 10), np.uint8)
        conf = SimpleNamespace(
            account="sender@example.invalid",
            recipient=["recipient@example.invalid"],
            custom_smtp_server=SimpleNamespace(enable=False),
        )
        with (
            patch("cv2.cvtColor", side_effect=AssertionError("OpenCV JPEG conversion")),
            patch("cv2.imencode", side_effect=AssertionError("OpenCV JPEG encoding")),
            patch.object(config, "conf", conf),
        ):
            encoded = img2bytes(rgb)
            email = Email("body", "subject", rgb)
        self.assertIsInstance(encoded, np.ndarray)
        self.assertEqual(encoded.dtype, np.uint8)
        attachment = next(
            part for part in email.msg.walk() if part.get_content_type() == "image/jpeg"
        )
        self.assertEqual(attachment.get_payload(decode=True), encoded.tobytes())

    def test_public_encoder_keeps_large_image_compatibility(self):
        rgb = np.zeros((1081, 1920, 3), np.uint8)
        with Image.open(BytesIO(encode_jpeg(rgb))) as image:
            self.assertEqual(image.size, (1920, 1081))


class ScreenshotEncodingTests(unittest.TestCase):
    def setUp(self):
        self.children = []

    def start_process(self, *args, **kwargs):
        child = launch_jpeg_process(*args, **kwargs)
        self.children.append(child)
        return child

    def bank(self, *, mode="lean", timeout=2, **options):
        commands = WorkerCommands(mode)
        bank = ScreenshotEncoding(
            timeout=timeout,
            process_factory=self.start_process,
            command_factory=commands,
            **options,
        )
        self.addCleanup(bank.close)
        return bank, commands

    @staticmethod
    def rgb():
        return np.full((32, 48, 3), (255, 0, 0), np.uint8)

    def test_real_lean_worker_reuses_one_child_for_rgb_strided_and_gray(self):
        bank, commands = self.bank()
        rgb = self.rgb()
        rgb.flags.writeable = False
        gray = np.full((32, 48), 127, np.uint8)
        for source in (rgb, rgb[:, ::2], gray, rgb):
            encoded = bank.encode(source)
            self.assertEqual(encoded, encode_jpeg(source))
            with Image.open(BytesIO(encoded)) as image:
                self.assertEqual(image.size, (source.shape[1], source.shape[0]))
                if source.ndim == 2:
                    self.assertEqual(image.getpixel((5, 5)), 127)
                else:
                    self.assertGreater(image.getpixel((5, 5))[0], 250)
        self.assertEqual(commands.calls, 1)
        self.assertEqual(len(self.children), 1)
        bank.close()
        self.assertTrue(all(child.poll() is not None for child in self.children))
        with self.assertRaises(RuntimeError):
            bank.encode(rgb)

    def test_real_child_exit_hang_error_partial_and_oversized_reply_recover_next_frame(
        self,
    ):
        for mode in (
            "exit",
            "hang",
            "error",
            "partial",
            "dribble",
            "oversized",
            "bad_jpeg",
            "startup_exit",
            "slow_start",
        ):
            with self.subTest(mode=mode):
                budget = 0.6 if mode == "dribble" else 1.5
                bank, commands = self.bank(mode=mode, timeout=budget)
                started = time.monotonic()
                with self.assertRaises(
                    (RuntimeError, TimeoutError, EOFError, OSError, ValueError)
                ):
                    bank.encode(self.rgb())
                self.assertLess(time.monotonic() - started, budget + 0.25)
                self.assertTrue(
                    all(child.poll() is not None for child in self.children)
                )
                for slot in bank._slots:
                    slot.timeout = 3
                with Image.open(BytesIO(bank.encode(self.rgb()))) as image:
                    self.assertEqual(image.size, (48, 32))
                self.assertEqual(commands.calls, 2)
                bank.close()

    def test_start_failure_cleans_mapping_and_later_frame_can_start(self):
        calls = []

        def launch(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                raise OSError("offline process creation failure")
            return self.start_process(command, **kwargs)

        bank = ScreenshotEncoding(process_factory=launch)
        self.addCleanup(bank.close)
        with self.assertRaises(OSError):
            bank.encode(self.rgb())
        self.assertIsNone(bank._slots[0]._mapping_path)
        self.assertIsNone(bank._slots[0]._mapping)
        self.assertTrue(bank.encode(self.rgb()).startswith(b"\xff\xd8"))

    def test_cleanup_failure_retains_child_ownership_and_prevents_replacement(self):
        child = Mock(pid=123, returncode=None)
        child.poll.side_effect = lambda: child.returncode
        child.kill.side_effect = OSError("offline kill failure")
        launch = Mock(return_value=child)
        bank = ScreenshotEncoding(process_factory=launch, timeout=0.2)
        try:
            with self.assertRaises(TimeoutError) as failed:
                bank.encode(self.rgb())
            self.assertTrue(failed.exception.__notes__)
            self.assertEqual(bank.remaining_workers(), [123])
            with self.assertRaisesRegex(RuntimeError, "尚未退出"):
                bank.encode(self.rgb())
            launch.assert_called_once()
            self.assertEqual(bank.remaining_workers(), [123])
        finally:
            child.returncode = 1
            bank.close()
        self.assertEqual(bank.remaining_workers(), [])

    def test_inherited_bank_never_closes_another_process_owned_children(self):
        bank, _ = self.bank()
        child = Mock(pid=123)
        child.poll.return_value = None
        bank._slots[0]._process = child
        with patch(
            "arknights_mower.utils.screenshot_encoding.os.getpid",
            return_value=bank._slots[0].owner_pid + 1,
        ):
            bank.close()
            with self.assertRaises(RuntimeError):
                bank.encode(self.rgb())
            self.assertEqual(bank.remaining_workers(), [])
        child.kill.assert_not_called()
        child.poll.return_value = 0
        bank.close()

    def test_two_slots_preserve_preview_while_history_child_hangs(self):
        bank, commands = self.bank(mode="hang", timeout=5)
        errors = []
        finished = Event()

        def history():
            try:
                bank.encode(self.rgb())
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = Thread(target=history)
        thread.start()
        wait_until(lambda: bank._slots[0]._channel is not None)
        result = bank.encode(self.rgb(), preview=True)
        self.assertTrue(result.startswith(b"\xff\xd8"))
        self.assertFalse(finished.is_set())
        self.assertEqual(commands.calls, 2)
        self.assertEqual(len(self.children), 2)
        bank.close()
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_sequential_history_and_preview_need_only_one_child(self):
        bank, commands = self.bank()
        for preview in (False, True, False, True):
            self.assertTrue(
                bank.encode(self.rgb(), preview=preview).startswith(b"\xff\xd8")
            )
        self.assertEqual(commands.calls, 1)
        self.assertEqual(len(bank.remaining_workers()), 1)
        self.assertIsNone(bank._slots[1]._process)

    def test_idle_auxiliary_is_reaped_without_new_frames_and_restarts_on_demand(self):
        bank, commands = self.bank(mode="hang", timeout=5, auxiliary_idle_timeout=0.1)
        errors = []

        def history():
            try:
                bank.encode(self.rgb())
            except Exception as exc:
                errors.append(exc)

        thread = Thread(target=history)
        thread.start()
        try:
            wait_until(lambda: bank._slots[0]._channel is not None)
            bank.encode(self.rgb(), preview=True)
            auxiliary = self.children[-1]
            mapping = bank._slots[1]._mapping_path
            # The process exits before its mapping is closed and unlinked.
            wait_until(lambda: bank._slots[1]._mapping_path is None)
            self.assertIsNone(bank._slots[1]._process)
            self.assertIsNotNone(auxiliary.poll())
            self.assertFalse(mapping.exists())
            self.assertTrue(thread.is_alive())
            self.assertEqual(len(bank.remaining_workers()), 1)
            self.assertTrue(
                bank.encode(self.rgb(), preview=True).startswith(b"\xff\xd8")
            )
            self.assertEqual(commands.calls, 3)
            self.assertNotEqual(auxiliary.pid, self.children[-1].pid)
        finally:
            bank.close()
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_idle_reaper_does_not_interrupt_an_active_auxiliary_frame(self):
        def command(path, port, token):
            return [
                sys.executable,
                "-m",
                "arknights_mower.tests.jpeg_worker_fixtures",
                "hang",
                str(path),
                str(port),
                token,
            ]

        bank = ScreenshotEncoding(
            timeout=5,
            auxiliary_idle_timeout=0.05,
            process_factory=self.start_process,
            command_factory=command,
        )
        self.addCleanup(bank.close)
        errors = []

        def encode(preview):
            try:
                bank.encode(self.rgb(), preview=preview)
            except Exception as exc:
                errors.append(exc)

        history = Thread(target=encode, args=(False,))
        preview = Thread(target=encode, args=(True,))
        history.start()
        try:
            wait_until(lambda: bank._slots[0]._channel is not None)
            preview.start()
            wait_until(lambda: bank._slots[1]._channel is not None)
            auxiliary = bank._slots[1]._process
            Event().wait(0.2)
            self.assertTrue(preview.is_alive())
            self.assertIsNone(auxiliary.poll())
            self.assertEqual(len(bank.remaining_workers()), 2)
        finally:
            bank.close()
            history.join(1)
            if preview.ident is not None:
                preview.join(1)
        self.assertFalse(history.is_alive())
        self.assertFalse(preview.is_alive())
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_shared_input_output_limits_reject_oversized_frame_without_child(self):
        bank, commands = self.bank()
        with self.assertRaises(ValueError):
            bank.encode(np.zeros((1081, 1920, 3), np.uint8))
        self.assertEqual(commands.calls, 0)
        self.assertEqual(self.children, [])

    def test_frozen_command_uses_early_worker_dispatch(self):
        with patch.object(sys, "frozen", True, create=True):
            self.assertEqual(
                worker_command(Path("frame.bin"), 12345, "token"),
                [sys.executable, "--jpeg-encode-worker", "frame.bin", "12345", "token"],
            )

    def test_desktop_worker_dispatch_encodes_without_launching_application(self):
        def desktop_command(path, port, token):
            return [
                sys.executable,
                str(Path(__file__).resolve().parents[2] / "webview_ui.py"),
                "--jpeg-encode-worker",
                str(path),
                str(port),
                token,
            ]

        bank = ScreenshotEncoding(
            process_factory=self.start_process, command_factory=desktop_command
        )
        self.addCleanup(bank.close)
        with Image.open(BytesIO(bank.encode(self.rgb()))) as image:
            self.assertEqual(image.size, (48, 32))
        bank.close()
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_worker_startup_connection_failure_releases_its_mapping_file(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "mower-jpeg-offline"
            directory.mkdir()
            path = directory / "frame.bin"
            with path.open("wb") as output:
                output.truncate(MAPPING_BYTES)
            child = self.start_process(
                worker_command(path, 0, "a" * 64),
                cwd=Path(__file__).resolve().parents[2],
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            child.wait(timeout=2)
            self.assertNotEqual(child.returncode, 0)
            self.assertFalse(path.exists())

    def test_store_discards_failed_raw_frame_once_then_publishes_new_capture(self):
        bank, commands = self.bank(mode="exit", timeout=1)
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenshotStore(Path(folder), lambda: 1, logger=Mock())
            self.addCleanup(store.close)
            store._encoding_workers = bank
            raw = []

            def inspect(frame):
                raw.append(weakref.ref(frame))
                return frame_shape(frame)

            with patch(
                "arknights_mower.utils.screenshot_encoding.frame_shape", new=inspect
            ):
                store.start()
                failed = store.submit_frame(self.rgb(), "run_order")
                wait_until(lambda: store.stats()["failed"] == 1)
                wait_until(lambda: store.stats()["pending_count"] == 0)
                gc.collect()
                self.assertTrue(all(reference() is None for reference in raw))
                self.assertEqual(store.stats()["encode_failed"], 1)
                self.assertEqual(commands.calls, 1)
                self.assertFalse((Path(folder) / failed).exists())
                newest = store.submit_frame(self.rgb())
                wait_until(
                    lambda: (
                        store.latest() is not None and store.latest().filename == newest
                    )
                )
                wait_until(lambda: store.stats()["pending_count"] == 0)
                self.assertEqual(
                    (Path(folder) / newest).read_bytes(), store.latest().data
                )
                self.assertEqual(commands.calls, 2)
                result = store.close(timeout=1)
                self.assertEqual(result["remaining_threads"], [])
                self.assertEqual(result["pending_bytes"], 0)
                self.assertEqual(result["raw_pending_bytes"], 0)
                self.assertTrue(
                    all(child.poll() is not None for child in self.children)
                )

    def test_store_flush_deadline_interrupts_hanging_child_and_releases_frame(self):
        bank, _ = self.bank(mode="hang", timeout=5)
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenshotStore(Path(folder), lambda: 1, logger=Mock())
            self.addCleanup(store.close)
            store._encoding_workers = bank
            store.start()
            store.submit_frame(np.zeros((1080, 1920, 3), np.uint8), "run_order")
            wait_until(lambda: bank._slots[0]._channel is not None)
            self.assertEqual(store.stats()["raw_pending_bytes"], MAX_RAW_BYTES)
            started = time.monotonic()
            result = store.close(timeout=0.5)
            self.assertLess(time.monotonic() - started, 0.65)
            self.assertEqual(result["remaining_threads"], [])
            self.assertEqual(result["pending_count"], 0)
            self.assertEqual(result["raw_pending_bytes"], 0)
            self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_hung_encoding_child_exits_and_removes_mapping_when_parent_dies(self):
        self.check_parent_death("parent")

    @unittest.skipUnless(sys.platform == "win32", "Windows kernel Job guarantee")
    def test_gil_held_native_encoding_and_startup_parent_death_reap_entire_job(self):
        for mode in ("parent_native", "parent_startup_native"):
            with self.subTest(mode=mode):
                self.check_parent_death(mode)

    def check_parent_death(self, mode):
        from arknights_mower.utils.update_runtime import process_alive

        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "owned.json"
            # The outer parent has no Job: only production JPEG ownership may reap.
            parent = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "arknights_mower.tests.jpeg_worker_fixtures",
                    mode,
                    str(report),
                    "0",
                    "unused",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.children.append(parent)
            try:
                wait_until(report.exists)
                owned = json.loads(report.read_text(encoding="utf-8"))
                self.assertTrue(process_alive(owned["pid"]))
                self.assertTrue(Path(owned["mapping"]).exists())
                parent.kill()
                parent.wait(timeout=1)
                wait_until(lambda: not process_alive(owned["pid"]))
                wait_until(lambda: not process_alive(owned["child_pid"]))
                if owned["descendant_pid"]:
                    wait_until(lambda: not process_alive(owned["descendant_pid"]))
                wait_until(lambda: not Path(owned["mapping"]).exists())
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=1)

    @unittest.skipUnless(sys.platform == "win32", "Windows kernel Job guarantee")
    def test_native_gil_hang_timeout_kills_launcher_and_descendants(self):
        from arknights_mower.utils.update_runtime import process_alive

        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "child.json"
            bank, _ = self.bank(mode="native_hang", timeout=2)
            with patch.dict(os.environ, MOWER_JPEG_FIXTURE_MARKER=str(marker)):
                with self.assertRaises(TimeoutError):
                    bank.encode(self.rgb())
            owned = json.loads(marker.read_text(encoding="utf-8"))
            wait_until(lambda: not process_alive(owned["pid"]))
            wait_until(lambda: not process_alive(owned["descendant_pid"]))
            self.assertTrue(all(child.poll() is not None for child in self.children))
            self.assertIsNone(bank._slots[0]._mapping_path)

    @unittest.skipUnless(sys.platform == "win32", "Windows kernel Job guarantee")
    def test_exited_launcher_reaps_gil_held_descendants_before_replacement(self):
        from arknights_mower.utils.update_runtime import process_alive

        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "child.json"
            bank, commands = self.bank(mode="wrapper_exit", timeout=3)
            with patch.dict(os.environ, MOWER_JPEG_FIXTURE_MARKER=str(marker)):
                with self.assertRaises(RuntimeError):
                    bank.encode(self.rgb())
            owned = json.loads(marker.read_text(encoding="utf-8"))
            self.assertFalse(process_alive(owned["pid"]))
            self.assertFalse(process_alive(owned["descendant_pid"]))
            self.assertTrue(bank.encode(self.rgb()).startswith(b"\xff\xd8"))
            self.assertEqual(commands.calls, 2)

    @unittest.skipUnless(sys.platform == "win32", "Windows kernel Job guarantee")
    def test_concurrent_stats_poll_cannot_close_a_handle_wait_is_using(self):
        child = self.start_process(
            [sys.executable, "-c", "import time; time.sleep(.15)"],
            cwd=Path(__file__).resolve().parents[2],
            env=os.environ.copy(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        kernel = child._kernel
        released = Event()
        stop = Event()
        failures = []

        class KernelWindow:
            def __getattr__(self, name):
                return getattr(kernel, name)

            def WaitForSingleObject(self, handle, milliseconds):
                if milliseconds:
                    # Expose the natural preemption before an unlocked handle wait.
                    if not released.wait(2):
                        raise TimeoutError("statistics poll did not release the window")
                return kernel.WaitForSingleObject(handle, milliseconds)

        child._kernel = KernelWindow()

        def statistics():
            try:
                while not stop.is_set():
                    if child.poll() is not None:
                        released.set()
                        return
                    stop.wait(0.001)
            except Exception as exc:
                failures.append(exc)
                released.set()

        observer = Thread(target=statistics)
        observer.start()
        try:
            self.assertEqual(child.wait(timeout=2), 0)
            self.assertEqual(failures, [])
        finally:
            stop.set()
            released.set()
            observer.join(1)
            child.kill()
            child.wait(timeout=1)
        self.assertFalse(observer.is_alive())

    def test_recognition_and_new_preview_continue_during_real_history_child_hang(self):
        from arknights_mower.utils import log
        from arknights_mower.utils.device.device import Device
        from arknights_mower.utils.recognize import Recognizer

        bank, _ = self.bank(mode="hang", timeout=5)
        rgb = np.full((1080, 1920, 3), (255, 0, 0), np.uint8)
        device = object.__new__(Device)
        device.check_current_focus = Mock(return_value=False)
        device.session_control = SimpleNamespace(
            capture=lambda: SimpleNamespace(unwrap=lambda: rgb)
        )
        with tempfile.TemporaryDirectory() as folder:
            store = ScreenshotStore(Path(folder), lambda: 1, logger=Mock())
            self.addCleanup(store.close)
            store._encoding_workers = bank
            store.start()
            store.submit_frame(rgb, "run_order")
            wait_until(lambda: bank._slots[0]._channel is not None)
            with patch.object(log, "_store", return_value=store):
                recog = Recognizer(device)
                self.assertIs(recog.img, rgb)
                self.assertEqual(int(recog.gray[0, 0]), 76)
                wait_until(lambda: store.latest() is not None)
                self.assertTrue(self.children[0].poll() is None)
            self.assertEqual(store.close(timeout=0.5)["remaining_threads"], [])
            self.assertTrue(all(child.poll() is not None for child in self.children))


if __name__ == "__main__":
    unittest.main()
