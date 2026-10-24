"""Software version display preferences use the shared instance GUI file."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils.config import gui
from arknights_mower.utils.window_shell import WindowRatio
from arknights_mower.views.gui import gui_bp


class GuiAppearanceTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config" / "gui.yml"
        self.enterContext(patch.object(gui, "gui_path", self.path))
        self.app = Flask(__name__)
        self.app.token = "appearance-token"
        self.app.register_blueprint(gui_bp)
        self.client = self.app.test_client()
        self.headers = {"token": self.app.token}

    def read(self):
        return self.client.get("/gui/appearance", headers=self.headers)

    def save(self, value):
        return self.client.put(
            "/gui/appearance",
            json={"software_version_display": value},
            headers=self.headers,
        )

    def test_missing_preference_defaults_to_version_without_creating_files(self):
        response = self.read()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {
                "software_version_display": "version",
                "software_version_language": "en",
                "task_settings_layout": "checklist",
            },
        )
        self.assertEqual(gui.load_software_version_display(), "version")
        self.assertFalse(self.path.parent.exists())

    def test_valid_values_round_trip_in_gui_file(self):
        for value in ("channel", "version"):
            with self.subTest(value=value):
                response = self.save(value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"software_version_display": value})
                self.assertEqual(
                    self.read().json,
                    {
                        **response.json,
                        "software_version_language": "en",
                        "task_settings_layout": "checklist",
                    },
                )
                self.assertEqual(gui.load_software_version_display(), value)
                self.assertEqual(gui.read_gui_data()["software_version_display"], value)

    def test_invalid_saved_values_fall_back_without_rewriting_the_file(self):
        for value in (None, True, 1, [], {}, "nightly", "VERSION"):
            with self.subTest(value=value):
                gui._update_gui_data(software_version_display=value)
                before = self.path.read_bytes()
                response = self.read()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json,
                    {
                        "software_version_display": "version",
                        "software_version_language": "en",
                        "task_settings_layout": "checklist",
                    },
                )
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_requests_never_replace_saved_preferences(self):
        gui.save_software_version_display("channel")
        before = self.path.read_bytes()
        payloads = [
            None,
            [],
            {},
            {"software_version_display": "version", "other": True},
        ]
        payloads.extend(
            {"software_version_display": value}
            for value in (
                None,
                False,
                0,
                1,
                [],
                {},
                "",
                "alpha",
                "Version",
                " channel ",
            )
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.put(
                    "/gui/appearance", json=payload, headers=self.headers
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json["ok"])
                self.assertEqual(self.path.read_bytes(), before)
        for value in (True, 1, [], {}, "unsupported"):
            with self.subTest(direct=value), self.assertRaises(ValueError):
                gui.save_software_version_display(value)
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_and_oversized_requests_are_rejected(self):
        malformed = self.client.put(
            "/gui/appearance",
            data="{",
            headers=self.headers,
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)
        oversized = self.client.put(
            "/gui/appearance",
            data="x" * (1024 * 1024 + 1),
            headers=self.headers,
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertFalse(self.path.exists())

    def test_both_routes_require_the_current_instance_token(self):
        for headers in ({}, {"token": "wrong-instance"}):
            with self.subTest(headers=headers):
                self.assertEqual(
                    self.client.get("/gui/appearance", headers=headers).status_code, 403
                )
                self.assertEqual(
                    self.client.put(
                        "/gui/appearance",
                        json={"software_version_display": "channel"},
                        headers=headers,
                    ).status_code,
                    403,
                )
        self.assertFalse(self.path.exists())

    def test_saving_preserves_sidebar_window_and_unknown_fields_in_both_directions(
        self,
    ):
        sidebar = {
            "version": 3,
            "knownKeys": ["log"],
            "groups": [],
            "placements": [
                {
                    "id": "log",
                    "key": "log",
                    "group": "ungrouped",
                    "visible": True,
                    "pinned": False,
                }
            ],
        }
        gui.save_sidebar(sidebar)
        gui.save_window_ratio(WindowRatio(0.7, 0.8))
        gui.save_window_mode("maximized")
        gui.save_window_launch_mode("normal")
        gui.save_close_preference("exit", True)
        gui._update_gui_data(private_setting={"theme": "custom"})
        original = gui.read_gui_data()
        self.assertEqual(self.save("channel").status_code, 200)
        self.assertEqual(
            gui.read_gui_data(), {**original, "software_version_display": "channel"}
        )
        gui.save_window_mode("normal")
        self.assertEqual(gui.load_software_version_display(), "channel")
        self.assertEqual(gui.load_sidebar(), sidebar)
        self.assertEqual(gui.load_window_ratio(), WindowRatio(0.7, 0.8))
        self.assertEqual(gui.load_window_launch_mode(), "normal")
        self.assertEqual(
            gui.load_close_preference(), {"choice": "exit", "remember": True}
        )
        self.assertEqual(gui.read_gui_data()["private_setting"], {"theme": "custom"})

    def test_write_failure_retains_file_and_releases_the_shared_lock(self):
        gui.save_software_version_display("version")
        before = self.path.read_bytes()
        with patch.object(gui, "atomic_write", side_effect=OSError("disk full")):
            response = self.save("channel")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["ok"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.read().json["software_version_display"], "version")
        self.assertEqual(self.save("channel").status_code, 200)
        self.assertEqual(self.read().json["software_version_display"], "channel")

    def test_lock_timeout_retains_file_and_returns_retryable_failure(self):
        gui.save_software_version_display("version")
        before = self.path.read_bytes()
        with patch.object(gui, "_gui_file_lock", side_effect=TimeoutError("busy")):
            response = self.save("channel")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.save("channel").status_code, 200)

    def test_task_layout_round_trips_without_changing_other_gui_preferences(self):
        gui._update_gui_data(
            software_version_display="channel",
            sidebar={"version": 2, "groups": []},
            window_mode="maximized",
            window_launch_mode="last",
            close_preference={"choice": "exit", "remember": True},
            ratio={"width": 0.7, "height": 0.8},
            private_setting=True,
        )
        original = gui.read_gui_data()
        for value in ("waterfall", "checklist"):
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/appearance",
                    json={"task_settings_layout": value},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"task_settings_layout": value})
                self.assertEqual(gui.load_task_settings_layout(), value)
                self.assertEqual(
                    gui.read_gui_data(), {**original, "task_settings_layout": value}
                )
        gui.save_appearance({"task_settings_layout": "waterfall"})
        self.save("version")
        gui.save_window_mode("normal")
        gui.save_window_launch_mode("maximized")
        gui.save_close_preference("tray", False)
        gui.save_sidebar(
            {"version": 3, "knownKeys": [], "groups": [], "placements": []}
        )
        self.assertEqual(self.read().json["task_settings_layout"], "waterfall")

    def test_old_and_invalid_layouts_default_without_rewriting_the_file(self):
        for value in (None, True, 1, [], {}, "grid", "WATERFALL"):
            with self.subTest(value=value):
                gui._update_gui_data(task_settings_layout=value)
                before = self.path.read_bytes()
                self.assertEqual(self.read().json["task_settings_layout"], "checklist")
                self.assertEqual(self.path.read_bytes(), before)

    def test_mixed_appearance_updates_are_validated_before_any_write(self):
        gui.save_appearance(
            {"software_version_display": "channel", "task_settings_layout": "waterfall"}
        )
        before = self.path.read_bytes()
        for payload in (
            {"software_version_display": "version", "task_settings_layout": "invalid"},
            {
                "software_version_display": "invalid",
                "task_settings_layout": "checklist",
            },
            {"task_settings_layout": None},
            {"task_settings_layout": False},
            {"task_settings_layout": []},
            {"task_settings_layout": "checklist", "sidebar": {}},
        ):
            with self.subTest(payload=payload):
                response = self.client.put(
                    "/gui/appearance", json=payload, headers=self.headers
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.path.read_bytes(), before)
        response = self.client.put(
            "/gui/appearance",
            json={
                "software_version_display": "version",
                "task_settings_layout": "checklist",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.read().json, {**response.json, "software_version_language": "en"}
        )

    def test_version_language_round_trips_and_preserves_other_gui_preferences(self):
        gui.save_appearance(
            {"software_version_display": "channel", "task_settings_layout": "waterfall"}
        )
        gui.save_window_mode("maximized")
        gui._update_gui_data(private_setting={"theme": "custom"})
        original = gui.read_gui_data()
        for value in ("zh", "en"):
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/appearance",
                    json={"software_version_language": value},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"software_version_language": value})
                self.assertEqual(self.read().json["software_version_language"], value)
                self.assertEqual(
                    gui.read_gui_data(),
                    {**original, "software_version_language": value},
                )
        self.save("version")
        gui.save_appearance({"task_settings_layout": "checklist"})
        gui.save_window_mode("normal")
        self.assertEqual(gui.load_software_version_language(), "en")

    def test_invalid_saved_languages_default_without_rewriting_the_file(self):
        for value in (None, True, 1, [], {}, "ZH", "zh-CN", "中文"):
            with self.subTest(value=value):
                gui._update_gui_data(software_version_language=value)
                before = self.path.read_bytes()
                self.assertEqual(self.read().json["software_version_language"], "en")
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_version_language_rejects_the_entire_appearance_update(self):
        gui.save_appearance(
            {"software_version_display": "channel", "software_version_language": "zh"}
        )
        before = self.path.read_bytes()
        for value in (None, False, 0, [], {}, "ZH", "zh-CN", "中文"):
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/appearance",
                    json={
                        "software_version_display": "version",
                        "software_version_language": value,
                    },
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.path.read_bytes(), before)

    def test_version_language_write_failure_keeps_saved_language_and_allows_retry(self):
        gui.save_appearance({"software_version_language": "en"})
        before = self.path.read_bytes()
        with patch.object(gui, "atomic_write", side_effect=OSError("disk full")):
            response = self.client.put(
                "/gui/appearance",
                json={"software_version_language": "zh"},
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.put(
            "/gui/appearance",
            json={"software_version_language": "zh"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.read().json["software_version_language"], "zh")

    def test_task_layout_write_failure_keeps_saved_layout_and_allows_retry(self):
        gui.save_appearance({"task_settings_layout": "waterfall"})
        before = self.path.read_bytes()
        with patch.object(gui, "atomic_write", side_effect=OSError("disk full")):
            response = self.client.put(
                "/gui/appearance",
                json={"task_settings_layout": "checklist"},
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(gui.load_task_settings_layout(), "waterfall")
        response = self.client.put(
            "/gui/appearance",
            json={"task_settings_layout": "checklist"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(gui.load_task_settings_layout(), "checklist")

    def test_real_server_does_not_apply_saved_profile_generation_to_appearance(self):
        with patch("arknights_mower.utils.network_settings.start_proxy_sync"):
            import server

        with (
            patch.object(server.app, "token", self.app.token, create=True),
            patch(
                "arknights_mower.utils.config_profiles.check_generation",
                side_effect=AssertionError(
                    "GUI preferences are independent of profiles"
                ),
            ) as check,
        ):
            response = server.app.test_client().put(
                "/gui/appearance",
                json={"software_version_display": "channel"},
                headers={**self.headers, "X-Mower-Config-Generation": "obsolete"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {"software_version_display": "channel"})
            check.assert_not_called()
            blocked = server.app.test_client().put(
                "/gui/appearance",
                json={"software_version_display": "version"},
                headers={"token": "wrong-instance"},
            )
            self.assertEqual(blocked.status_code, 403)
            self.assertEqual(gui.load_software_version_display(), "channel")
