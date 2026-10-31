"""Software version display preferences use the shared instance GUI file."""

import hashlib
import hmac
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
        self.key_path = self.path.with_name("gui-watermark.key")
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

    def save_watermark(self, visible):
        payload = {"watermark_visible": visible}
        if visible is False:
            payload["watermark_confirmation"] = "反馈问题时务必说明具体版本"
        return self.client.put("/gui/appearance", json=payload, headers=self.headers)

    def test_missing_preference_defaults_to_version_without_creating_files(self):
        response = self.read()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {
                "software_version_display": "version",
                "software_version_language": "en",
                "task_settings_layout": "checklist",
                "base_report_mode": "standard",
                "halloween_mode": "auto",
                "watermark_visible": True,
            },
        )
        self.assertEqual(gui.load_software_version_display(), "version")
        self.assertEqual(gui.load_base_report_mode(), "standard")
        self.assertEqual(gui.load_halloween_mode(), "auto")
        self.assertIs(gui.load_watermark_visible(), True)
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
                        "base_report_mode": "standard",
                        "halloween_mode": "auto",
                        "watermark_visible": True,
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
                        "base_report_mode": "standard",
                        "halloween_mode": "auto",
                        "watermark_visible": True,
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
            with (
                self.subTest(headers=headers),
                patch.object(gui, "read_gui_data") as read,
                patch.object(gui, "update_gui_data") as update,
                patch("arknights_mower.views.gui._request_json") as parse,
            ):
                self.assertEqual(
                    self.client.get("/gui/appearance", headers=headers).status_code, 403
                )
                for payload in (
                    {"software_version_display": "channel"},
                    {"base_report_mode": "stock"},
                    {"halloween_mode": "off"},
                ):
                    self.assertEqual(
                        self.client.put(
                            "/gui/appearance", json=payload, headers=headers
                        ).status_code,
                        403,
                    )
                read.assert_not_called()
                update.assert_not_called()
                parse.assert_not_called()
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

    def test_base_report_mode_round_trips_and_stays_independent_of_other_fields(self):
        gui.save_appearance(
            {
                "software_version_display": "channel",
                "software_version_language": "zh",
                "task_settings_layout": "waterfall",
            }
        )
        original = gui.read_gui_data()
        for value in ("stock", "standard"):
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/appearance",
                    json={"base_report_mode": value},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"base_report_mode": value})
                self.assertEqual(gui.load_base_report_mode(), value)
                self.assertEqual(self.read().json["base_report_mode"], value)
                self.assertEqual(
                    gui.read_gui_data(), {**original, "base_report_mode": value}
                )
        response = self.client.put(
            "/gui/appearance",
            json={
                "software_version_display": "version",
                "software_version_language": "en",
                "task_settings_layout": "checklist",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(gui.load_base_report_mode(), "standard")
        self.assertEqual(
            gui.read_gui_data(),
            {
                **original,
                "software_version_display": "version",
                "software_version_language": "en",
                "task_settings_layout": "checklist",
                "base_report_mode": "standard",
            },
        )

    def test_invalid_saved_base_report_modes_default_without_rewriting_the_file(self):
        for value in (None, True, 1, [], {}, "", "STOCK", " stock ", "stock-mode"):
            with self.subTest(value=value):
                gui._update_gui_data(base_report_mode=value)
                before = self.path.read_bytes()
                self.assertEqual(gui.load_base_report_mode(), "standard")
                response = self.read()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["base_report_mode"], "standard")
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_base_report_mode_rejects_the_entire_appearance_update(self):
        gui.save_appearance({"base_report_mode": "stock"})
        before = self.path.read_bytes()
        payloads = [
            {"base_report_mode": value}
            for value in (None, True, 1, [], {}, "", "STOCK", " stock ", "standard ")
        ]
        payloads.extend(
            (
                {"base_report_mode": "standard", "unknown_field": True},
                {"software_version_display": "invalid", "base_report_mode": "standard"},
                {"task_settings_layout": "grid", "base_report_mode": "stock"},
                {"base_report_mode": "stock", "sidebar": {}},
            )
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with patch.object(gui, "update_gui_data") as update:
                    response = self.client.put(
                        "/gui/appearance", json=payload, headers=self.headers
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json["ok"])
                    update.assert_not_called()
                    with self.assertRaises(ValueError):
                        gui.save_appearance(payload)
                    update.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(gui.load_base_report_mode(), "stock")
        response = self.client.put(
            "/gui/appearance",
            json={"base_report_mode": "standard"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(gui.load_base_report_mode(), "standard")

    def test_halloween_modes_round_trip_without_changing_other_preferences(self):
        gui.save_appearance(
            {"software_version_display": "channel", "base_report_mode": "stock"}
        )
        gui.save_window_mode("maximized")
        original = gui.read_gui_data()
        for value in ("off", "on", "auto"):
            with self.subTest(value=value):
                response = self.client.put(
                    "/gui/appearance",
                    json={"halloween_mode": value},
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"halloween_mode": value})
                self.assertEqual(gui.load_halloween_mode(), value)
                self.assertEqual(self.read().json["halloween_mode"], value)
                self.assertEqual(
                    gui.read_gui_data(), {**original, "halloween_mode": value}
                )
        gui.save_appearance({"halloween_mode": "off"})
        self.save("version")
        self.assertEqual(gui.load_halloween_mode(), "off")

    def test_invalid_saved_halloween_modes_default_without_rewriting_the_file(self):
        for value in (None, True, 1, [], {}, "", "ON", " off ", "disabled"):
            with self.subTest(value=value):
                gui._update_gui_data(halloween_mode=value)
                before = self.path.read_bytes()
                self.assertEqual(gui.load_halloween_mode(), "auto")
                response = self.read()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["halloween_mode"], "auto")
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_halloween_mode_rejects_the_entire_update_before_writing(self):
        gui.save_appearance({"halloween_mode": "off"})
        before = self.path.read_bytes()
        payloads = [
            {"halloween_mode": value, "software_version_display": "channel"}
            for value in (None, True, 1, [], {}, "", "ON", " off ", "disabled")
        ]
        payloads.extend(
            (
                {"halloween_mode": "on", "unknown_field": True},
                {"halloween_mode": "auto", "software_version_display": "invalid"},
            )
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with patch.object(gui, "update_gui_data") as update:
                    response = self.client.put(
                        "/gui/appearance", json=payload, headers=self.headers
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json["ok"])
                    update.assert_not_called()
                    with self.assertRaises(ValueError):
                        gui.save_appearance(payload)
                    update.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(gui.load_halloween_mode(), "off")

    def test_failed_halloween_mode_save_keeps_the_previous_choice(self):
        gui.save_appearance({"halloween_mode": "off"})
        before = self.path.read_bytes()
        with patch.object(gui, "atomic_write", side_effect=OSError("disk unavailable")):
            response = self.client.put(
                "/gui/appearance",
                json={"halloween_mode": "on"},
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.read().json["halloween_mode"], "off")

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
            self.read().json,
            {
                **response.json,
                "software_version_language": "en",
                "base_report_mode": "standard",
                "halloween_mode": "auto",
                "watermark_visible": True,
            },
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

    def test_watermark_visibility_round_trips_and_reloads_for_a_new_client(self):
        for value in (False, True):
            with self.subTest(value=value):
                response = self.save_watermark(value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"watermark_visible": value})
                self.assertIs(gui.read_gui_data()["watermark_visible"], value)
                self.assertIs(gui.load_watermark_visible(), value)
                reloaded_app = Flask(__name__)
                reloaded_app.token = self.app.token
                reloaded_app.register_blueprint(gui_bp)
                response = reloaded_app.test_client().get(
                    "/gui/appearance", headers=self.headers
                )
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json["watermark_visible"], value)

    def test_invalid_saved_watermark_visibility_defaults_without_rewriting(self):
        for value in (None, False, 0, 1, [], {}, "true", "false", "hidden"):
            with self.subTest(value=value):
                gui._update_gui_data(watermark_visible=value)
                before = self.path.read_bytes()
                response = self.read()
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json["watermark_visible"], True)
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_watermark_visibility_rejects_the_entire_appearance_update(self):
        gui.save_appearance(
            {"software_version_display": "channel", "watermark_visible": True}
        )
        before = self.path.read_bytes()
        for value in (None, 0, 1, [], {}, "", "true", "false"):
            with self.subTest(value=value):
                payload = {
                    "software_version_display": "version",
                    "watermark_visible": value,
                }
                with patch.object(gui, "update_gui_data") as update:
                    response = self.client.put(
                        "/gui/appearance", json=payload, headers=self.headers
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json["ok"])
                    update.assert_not_called()
                    with self.assertRaises(ValueError):
                        gui.save_appearance(payload)
                    update.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)

    def test_watermark_updates_preserve_all_other_gui_fields_in_both_directions(self):
        gui.save_appearance(
            {
                "software_version_display": "channel",
                "software_version_language": "zh",
                "task_settings_layout": "waterfall",
            }
        )
        gui.save_sidebar(
            {"version": 3, "knownKeys": [], "groups": [], "placements": []}
        )
        gui.save_window_mode("maximized")
        gui.save_window_launch_mode("last")
        gui.save_close_preference("exit", True)
        gui.save_window_ratio(WindowRatio(0.7, 0.8))
        gui._update_gui_data(private_setting={"theme": "custom"})
        original = gui.read_gui_data()
        response = self.save_watermark(False)
        self.assertEqual(response.status_code, 200)
        saved = gui.read_gui_data()
        self.assertEqual(len(saved.pop("watermark_signature")), 64)
        self.assertEqual(saved, {**original, "watermark_visible": False})
        self.save("version")
        gui.save_appearance(
            {"software_version_language": "en", "task_settings_layout": "checklist"}
        )
        gui.save_window_mode("normal")
        gui.save_window_launch_mode("normal")
        gui.save_close_preference("tray", False)
        gui.save_window_ratio(WindowRatio(0.6, 0.9))
        gui.save_sidebar(
            {"version": 3, "knownKeys": ["log"], "groups": [], "placements": []}
        )
        self.assertIs(self.read().json["watermark_visible"], False)
        self.assertEqual(gui.read_gui_data()["private_setting"], {"theme": "custom"})

    def test_watermark_routes_reject_missing_and_wrong_tokens_before_any_work(self):
        gui.save_appearance({"watermark_visible": True})
        before = self.path.read_bytes()
        for method in ("GET", "HEAD", "PUT"):
            for headers in ({}, {"token": "wrong-instance"}):
                with self.subTest(method=method, headers=headers):
                    with (
                        patch(
                            "arknights_mower.views.gui._request_json"
                        ) as parse_request,
                        patch.object(gui, "read_gui_data") as read_data,
                        patch.object(gui, "update_gui_data") as update_data,
                        patch.object(gui, "_watermark_key") as read_key,
                    ):
                        response = self.client.open(
                            "/gui/appearance",
                            method=method,
                            json={"watermark_visible": False},
                            headers=headers,
                        )
                        self.assertEqual(response.status_code, 403)
                        parse_request.assert_not_called()
                        read_data.assert_not_called()
                        update_data.assert_not_called()
                        read_key.assert_not_called()
                    self.assertEqual(self.path.read_bytes(), before)

    def test_watermark_storage_failure_keeps_preference_and_allows_retry(self):
        gui.save_appearance({"watermark_visible": True})
        before = self.path.read_bytes()
        for operation in ("atomic_write", "_gui_file_lock"):
            with self.subTest(operation=operation):
                with patch.object(gui, operation, side_effect=OSError("unavailable")):
                    response = self.save_watermark(False)
                self.assertEqual(response.status_code, 503)
                self.assertFalse(response.json["ok"])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertIs(self.read().json["watermark_visible"], True)
        response = self.save_watermark(False)
        self.assertEqual(response.status_code, 200)
        self.assertIs(self.read().json["watermark_visible"], False)

    def test_watermark_read_failure_returns_retryable_error_without_writing(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        before = self.path.read_bytes()
        with patch.object(
            gui,
            "load_watermark_visible",
            side_effect=gui.GuiStorageError("unavailable"),
        ):
            response = self.read()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["ok"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIs(self.read().json["watermark_visible"], False)

    def test_confirmed_hide_saves_hmac_without_exposing_confirmation_or_key(self):
        response = self.save_watermark(False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"watermark_visible": False})
        saved = gui.read_gui_data()
        key = bytes.fromhex(self.key_path.read_text(encoding="ascii"))
        self.assertEqual(len(key), 32)
        expected = hmac.new(
            key, b"arknights-mower:watermark-hidden:v1", hashlib.sha256
        ).hexdigest()
        self.assertEqual(
            saved, {"watermark_visible": False, "watermark_signature": expected}
        )
        self.assertNotIn("watermark_confirmation", self.read().json)
        self.assertNotIn("watermark_signature", self.read().json)
        self.assertNotIn(
            "反馈问题时务必说明具体版本", self.path.read_text(encoding="utf-8")
        )

    def test_enabling_clears_signature_so_editing_only_bool_cannot_hide(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        key_before = self.key_path.read_bytes()
        self.assertEqual(self.save_watermark(True).status_code, 200)
        self.assertNotIn("watermark_signature", gui.read_gui_data())
        gui._update_gui_data(watermark_visible=False)
        before = self.path.read_bytes()
        with patch.object(gui, "atomic_write") as write:
            self.assertIs(self.read().json["watermark_visible"], True)
            write.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.key_path.read_bytes(), key_before)

    def test_missing_or_invalid_signatures_show_watermark_without_rewriting(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        key_before = self.key_path.read_bytes()
        for signature in (None, False, 0, 1, [], {}, "", "0" * 64, "版本" * 32):
            with self.subTest(signature=signature):
                gui._update_gui_data(watermark_signature=signature)
                before = self.path.read_bytes()
                with (
                    patch.object(gui, "atomic_write") as write,
                    patch.object(gui.secrets, "token_bytes") as generate,
                ):
                    self.assertIs(self.read().json["watermark_visible"], True)
                    write.assert_not_called()
                    generate.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.key_path.read_bytes(), key_before)

    def test_missing_or_invalid_key_shows_watermark_without_creating_files(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        before_gui = self.path.read_bytes()
        self.key_path.unlink()
        for raw in (None, b"", b"invalid", b"z" * 64, b"a" * 65, b"\xff" * 64):
            with self.subTest(raw=raw):
                if raw is not None:
                    self.key_path.write_bytes(raw)
                with patch.object(gui, "atomic_write") as write:
                    self.assertIs(self.read().json["watermark_visible"], True)
                    write.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before_gui)
                if raw is None:
                    self.assertFalse(self.key_path.exists())
                else:
                    self.assertEqual(self.key_path.read_bytes(), raw)

    def test_other_instances_cannot_reuse_a_copied_hidden_preference(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        original_gui = self.path.read_bytes()
        original_key = self.key_path.read_bytes()
        other_path = self.path.parent.parent / "other" / "config" / "gui.yml"
        other_path.parent.mkdir(parents=True)
        other_path.write_bytes(original_gui)
        other_key_path = other_path.with_name("gui-watermark.key")
        with patch.object(gui, "gui_path", other_path):
            self.assertIs(self.read().json["watermark_visible"], True)
            self.assertFalse(other_key_path.exists())
            self.assertEqual(self.save_watermark(False).status_code, 200)
            self.assertNotEqual(other_key_path.read_bytes(), original_key)
            other_path.write_bytes(original_gui)
            before = other_path.read_bytes()
            self.assertIs(self.read().json["watermark_visible"], True)
            self.assertEqual(other_path.read_bytes(), before)
        self.assertIs(self.read().json["watermark_visible"], False)
        self.assertEqual(self.key_path.read_bytes(), original_key)

    def test_confirmation_must_match_and_only_accompany_hiding(self):
        gui.save_appearance({"software_version_display": "channel"})
        before = self.path.read_bytes()
        payloads = [
            {"watermark_visible": False},
            {"watermark_confirmation": "反馈问题时务必说明具体版本"},
            {
                "watermark_visible": True,
                "watermark_confirmation": "反馈问题时务必说明具体版本",
            },
            {
                "watermark_visible": False,
                "watermark_confirmation": "反馈问题时务必说明具体版本",
                "watermark_signature": "0" * 64,
            },
        ]
        for value in (
            None,
            False,
            0,
            1,
            [],
            {},
            "",
            "知道了",
            "反馈问题时务必说明具体版本 ",
        ):
            payloads.append(
                {
                    "software_version_display": "version",
                    "watermark_visible": False,
                    "watermark_confirmation": value,
                }
            )
        for payload in payloads:
            with self.subTest(payload=payload):
                with patch.object(gui, "update_gui_data") as update:
                    response = self.client.put(
                        "/gui/appearance", json=payload, headers=self.headers
                    )
                    self.assertEqual(response.status_code, 400)
                    update.assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)
                self.assertFalse(self.key_path.exists())

    def test_mixed_confirmed_update_returns_only_persisted_appearance_fields(self):
        response = self.client.put(
            "/gui/appearance",
            json={
                "software_version_display": "channel",
                "software_version_language": "zh",
                "watermark_visible": False,
                "watermark_confirmation": "反馈问题时务必说明具体版本",
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {
                "software_version_display": "channel",
                "software_version_language": "zh",
                "watermark_visible": False,
            },
        )
        self.assertNotIn("watermark_confirmation", gui.read_gui_data())
        self.assertIs(self.read().json["watermark_visible"], False)

    def test_gui_write_failure_retains_a_new_key_for_the_next_confirmed_retry(self):
        gui.save_appearance({"watermark_visible": True})
        before = self.path.read_bytes()
        real_write = gui.atomic_write

        def fail_gui_write(path, writer):
            if path == self.path:
                raise OSError("disk full")
            return real_write(path, writer)

        with patch.object(gui, "atomic_write", side_effect=fail_gui_write):
            response = self.save_watermark(False)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)
        key_before = self.key_path.read_bytes()
        with patch.object(gui.secrets, "token_bytes") as generate:
            self.assertEqual(self.save_watermark(False).status_code, 200)
            generate.assert_not_called()
        self.assertEqual(self.key_path.read_bytes(), key_before)
        self.assertIs(self.read().json["watermark_visible"], False)

    def test_existing_key_and_signed_preference_survive_failed_write(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        before_gui = self.path.read_bytes()
        before_key = self.key_path.read_bytes()
        for visible in (False, True):
            with self.subTest(visible=visible):
                with patch.object(
                    gui, "atomic_write", side_effect=OSError("disk full")
                ):
                    response = self.save_watermark(visible)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(self.path.read_bytes(), before_gui)
                self.assertEqual(self.key_path.read_bytes(), before_key)
                self.assertIs(self.read().json["watermark_visible"], False)
        self.assertEqual(self.save_watermark(True).status_code, 200)
        self.assertEqual(self.key_path.read_bytes(), before_key)

    def test_key_read_failure_does_not_change_saved_preference(self):
        self.assertEqual(self.save_watermark(False).status_code, 200)
        before_gui = self.path.read_bytes()
        before_key = self.key_path.read_bytes()
        real_open = type(self.key_path).open

        def fail_key_read(path, *args, **kwargs):
            if path == self.key_path:
                raise PermissionError("key unavailable")
            return real_open(path, *args, **kwargs)

        with patch.object(type(self.key_path), "open", fail_key_read):
            response = self.read()
            save_response = self.save_watermark(False)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(save_response.status_code, 503)
        self.assertEqual(self.path.read_bytes(), before_gui)
        self.assertEqual(self.key_path.read_bytes(), before_key)
        self.assertIs(self.read().json["watermark_visible"], False)

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
