"""Offline sidebar persistence and cross-process GUI preference regressions."""

import copy
import multiprocessing
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from flask import Flask

from arknights_mower.utils.config import gui
from arknights_mower.utils.window_shell import WindowRatio
from arknights_mower.views.gui import gui_bp


def sidebar_layout():
    return {
        "version": 3,
        "knownKeys": ["log", "plan-editor"],
        "groups": [{"key": "work", "title": "工作", "collapsed": False}],
        "placements": [
            {
                "id": "log",
                "key": "log",
                "group": "ungrouped",
                "visible": True,
                "pinned": False,
            },
            {
                "id": "plan",
                "key": "plan-editor",
                "group": "work",
                "visible": True,
                "pinned": True,
            },
            {
                "id": "chat",
                "key": "chat",
                "group": "footer",
                "visible": True,
                "pinned": False,
            },
        ],
    }


def _paused_window_write(path, entered, release):
    gui.gui_path = Path(path)
    original_write = gui.atomic_write

    def paused_write(target, writer):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("Test writer was not released")
        original_write(target, writer)

    gui.atomic_write = paused_write
    gui.save_window_mode("maximized")


class GuiSidebarTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "config" / "gui.yml"
        patcher = mock.patch.object(gui, "gui_path", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        app = Flask(__name__)
        app.token = "test-token"
        app.register_blueprint(gui_bp)
        self.client = app.test_client()
        self.headers = {"token": app.token}

    def test_missing_sidebar_read_does_not_create_configuration(self):
        response = self.client.get("/gui/sidebar", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"sidebar": None})
        self.assertFalse(self.path.parent.exists())

    def test_both_routes_require_the_instance_token(self):
        self.assertEqual(self.client.get("/gui/sidebar").status_code, 403)
        self.assertEqual(
            self.client.put(
                "/gui/sidebar", json={"sidebar": sidebar_layout()}
            ).status_code,
            403,
        )

    def test_round_trip_preserves_all_window_preferences_and_unknown_fields(self):
        gui._update_gui_data(private_setting={"enabled": True})
        gui.save_window_ratio(WindowRatio(0.7, 0.8))
        gui.save_window_mode("maximized")
        gui.save_close_preference("exit", True)
        gui.save_window_launch_mode("normal")
        layout = sidebar_layout()
        response = self.client.put(
            "/gui/sidebar", json={"sidebar": layout}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"sidebar": layout})
        gui.save_window_ratio(WindowRatio(0.6, 0.75))
        self.assertEqual(
            self.client.get("/gui/sidebar", headers=self.headers).json,
            {"sidebar": layout},
        )
        self.assertEqual(gui.load_window_ratio(), WindowRatio(0.6, 0.75))
        self.assertEqual(gui.load_window_mode(), "maximized")
        self.assertEqual(gui.load_window_launch_mode(), "normal")
        self.assertEqual(
            gui.load_close_preference(), {"choice": "exit", "remember": True}
        )
        self.assertEqual(gui.read_gui_data()["private_setting"], {"enabled": True})

    def test_zero_named_groups_and_ungrouped_entries_are_saved(self):
        layout = sidebar_layout()
        layout["groups"] = []
        layout["placements"] = [layout["placements"][0]]
        self.assertEqual(gui.save_sidebar(layout), layout)
        self.assertEqual(gui.load_sidebar(), layout)

    def test_invalid_layouts_never_replace_saved_preferences(self):
        valid = sidebar_layout()
        gui.save_sidebar(valid)
        before = self.path.read_bytes()
        variants = []
        for field, replacement in (
            ("version", 2),
            ("version", True),
            ("groups", valid["groups"] * 21),
            ("knownKeys", ["log"] * 101),
            ("knownKeys", ["bad key"]),
            ("placements", valid["placements"] * 734),
        ):
            value = copy.deepcopy(valid)
            value[field] = replacement
            variants.append(value)
        for field, replacement in (
            ("key", "ungrouped"),
            ("title", "x" * 81),
            ("collapsed", 1),
        ):
            value = copy.deepcopy(valid)
            value["groups"][0][field] = replacement
            variants.append(value)
        for field, replacement in (
            ("id", "bad id"),
            ("group", "missing"),
            ("visible", 1),
            ("pinned", None),
        ):
            value = copy.deepcopy(valid)
            value["placements"][0][field] = replacement
            variants.append(value)
        duplicate = copy.deepcopy(valid)
        duplicate["placements"].append(copy.deepcopy(duplicate["placements"][0]))
        variants.extend([duplicate, None, [], {}])
        for value in variants:
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/sidebar", json={"sidebar": value}, headers=self.headers
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.path.read_bytes(), before)

    def test_missing_body_and_oversized_requests_are_rejected(self):
        self.assertEqual(
            self.client.put("/gui/sidebar", json={}, headers=self.headers).status_code,
            400,
        )
        response = self.client.put(
            "/gui/sidebar",
            data="x" * (1024 * 1024 + 1),
            headers=self.headers,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.path.exists())

    def test_legacy_layout_reads_without_rewriting_the_file(self):
        for version in (1, 2):
            value = sidebar_layout()
            value["version"] = version
            gui._update_gui_data(sidebar=value)
            before = self.path.read_bytes()
            self.assertEqual(gui.load_sidebar(), value)
            self.assertEqual(self.path.read_bytes(), before)
        gui._update_gui_data(sidebar={"version": 3, "groups": "broken"})
        self.assertIsNone(gui.load_sidebar())

    def test_failed_write_retains_bytes_and_releases_the_lock(self):
        gui.save_sidebar(sidebar_layout())
        before = self.path.read_bytes()
        with mock.patch.object(gui, "atomic_write", side_effect=OSError("disk full")):
            response = self.client.put(
                "/gui/sidebar", json={"sidebar": sidebar_layout()}, headers=self.headers
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        gui.save_window_mode("maximized")
        self.assertEqual(gui.load_window_mode(), "maximized")
        self.assertEqual(gui.load_sidebar(), sidebar_layout())

    def test_unreadable_gui_reports_storage_failure_without_publishing_defaults(self):
        for path in ("/gui/sidebar", "/gui/appearance"):
            for method in ("get", "head"):
                with (
                    self.subTest(path=path, method=method),
                    mock.patch.object(
                        Path, "open", side_effect=PermissionError("unreadable")
                    ),
                    mock.patch.object(Path, "is_file", return_value=True),
                ):
                    response = getattr(self.client, method)(path, headers=self.headers)
                    self.assertEqual(response.status_code, 503)

    def test_damaged_gui_returns_storage_failure_and_preserves_original_bytes(self):
        self.path.parent.mkdir(parents=True)
        for original in (b"sidebar: [", b"- invalid\n", b"\xff"):
            self.path.write_bytes(original)
            for path, payload in (
                ("/gui/sidebar", {"sidebar": sidebar_layout()}),
                ("/gui/appearance", {"software_version_display": "channel"}),
            ):
                with self.subTest(original=original, path=path):
                    response = self.client.get(path, headers=self.headers)
                    self.assertEqual(response.status_code, 503)
                    response = self.client.put(path, json=payload, headers=self.headers)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(self.path.read_bytes(), original)

    def test_streamed_oversized_gui_json_is_bounded_before_saving(self):
        raw = b'{"padding":"' + b"x" * (1024 * 1024) + b'"}'
        for path in ("/gui/sidebar", "/gui/appearance"):
            with self.subTest(path=path):
                stream = BytesIO(raw)
                response = self.client.put(
                    path,
                    headers=self.headers,
                    content_type="application/json",
                    environ_overrides={
                        "CONTENT_LENGTH": "",
                        "wsgi.input_terminated": True,
                        "wsgi.input": stream,
                    },
                )
                self.assertEqual(response.status_code, 413)
                self.assertLessEqual(stream.tell(), 1024 * 1024 + 1)
                self.assertFalse(self.path.exists())

    def test_streamed_gui_body_is_not_read_without_the_current_token(self):
        for path in ("/gui/sidebar", "/gui/appearance"):
            for token in (None, "another-instance"):
                with self.subTest(path=path, token=token):
                    stream = BytesIO(b"x" * (1024 * 1024 + 2))
                    response = self.client.put(
                        path,
                        headers={} if token is None else {"token": token},
                        content_type="application/json",
                        environ_overrides={
                            "CONTENT_LENGTH": "",
                            "wsgi.input_terminated": True,
                            "wsgi.input": stream,
                        },
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(stream.tell(), 0)
                    self.assertFalse(self.path.parent.exists())

    def test_other_process_cannot_overwrite_a_new_sidebar_with_old_window_data(self):
        context = multiprocessing.get_context("spawn")
        entered, release = context.Event(), context.Event()
        process = context.Process(
            target=_paused_window_write, args=(str(self.path), entered, release)
        )
        process.start()
        errors = []
        finished = threading.Event()

        def save_sidebar():
            try:
                gui.save_sidebar(sidebar_layout())
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        writer = threading.Thread(target=save_sidebar)
        try:
            self.assertTrue(entered.wait(10), "Window process did not acquire its lock")
            with self.assertRaises(TimeoutError), gui._gui_file_lock(timeout=0):
                self.fail("A held process lock must exhaust a zero timeout")
            writer.start()
            self.assertFalse(
                finished.wait(0.2), "Sidebar write bypassed the window process lock"
            )
        finally:
            release.set()
            process.join(10)
            if writer.ident is not None:
                writer.join(10)
            if process.is_alive():
                process.terminate()
                process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(gui.load_window_mode(), "maximized")
        self.assertEqual(gui.load_sidebar(), sidebar_layout())


if __name__ == "__main__":
    unittest.main()
