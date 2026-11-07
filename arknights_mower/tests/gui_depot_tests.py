"""Depot preferences persist across browser sessions in the instance GUI file."""

import copy
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from arknights_mower.utils.config import gui
from arknights_mower.utils.window_shell import WindowRatio
from arknights_mower.views.gui import gui_bp


def depot_preferences():
    return {
        "favorites": ["龙门币", "赤金"],
        "view": {
            "stockFilter": "favorite",
            "deltaFilter": "changed",
            "showDerived": False,
            "sortMode": "count-desc",
            "showcaseTab": "favorites",
        },
        "baseline": {
            "mode": "time",
            "preset": "custom",
            "range": [1700000000000, 1800000000000],
            "followLatest": False,
            "startKey": "1700000000",
            "endKey": "1800000000",
        },
    }


class GuiDepotTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "config" / "gui.yml"
        self.enterContext(patch.object(gui, "gui_path", self.path))
        self.app = Flask(__name__)
        self.app.token = "depot-token"
        self.app.register_blueprint(gui_bp)
        self.client = self.app.test_client()
        self.headers = {"token": self.app.token}

    def read(self):
        return self.client.get("/gui/depot", headers=self.headers)

    def save(self, value, **extra):
        return self.client.put(
            "/gui/depot", json={"depot": value, **extra}, headers=self.headers
        )

    def test_missing_preference_does_not_create_files(self):
        response = self.read()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"depot": None})
        self.assertFalse(self.path.parent.exists())

    def test_token_is_checked_before_reading_or_parsing(self):
        with (
            patch.object(gui, "read_gui_data") as read,
            patch("arknights_mower.views.gui._request_json") as parse,
            patch.object(gui, "atomic_write") as write,
        ):
            for method in ("GET", "HEAD", "PUT"):
                for token in (None, "another-instance"):
                    with self.subTest(method=method, token=token):
                        stream = BytesIO(b'{"depot":{}}')
                        response = self.client.open(
                            "/gui/depot",
                            method=method,
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
            read.assert_not_called()
            parse.assert_not_called()
            write.assert_not_called()
        self.assertFalse(self.path.parent.exists())

    def test_round_trip_preserves_window_settings_and_unknown_fields(self):
        gui._update_gui_data(private_setting={"enabled": True}, sidebar={"version": 1})
        gui.save_window_ratio(WindowRatio(0.7, 0.8))
        gui.save_window_mode("maximized")
        gui.save_close_preference("exit", True)
        gui.save_window_launch_mode("normal")
        value = depot_preferences()
        response = self.save(value)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"depot": value})
        self.assertEqual(gui.read_gui_data()["depot"], value)
        gui.save_window_ratio(WindowRatio(0.6, 0.75))
        self.assertEqual(self.read().json, {"depot": value})
        self.assertEqual(gui.load_window_ratio(), WindowRatio(0.6, 0.75))
        self.assertEqual(gui.load_window_mode(), "maximized")
        self.assertEqual(gui.load_window_launch_mode(), "normal")
        self.assertEqual(
            gui.load_close_preference(), {"choice": "exit", "remember": True}
        )
        self.assertEqual(gui.read_gui_data()["private_setting"], {"enabled": True})
        self.assertEqual(gui.read_gui_data()["sidebar"], {"version": 1})

    def test_partial_groups_do_not_replace_other_saved_choices(self):
        value = depot_preferences()
        self.save(value)
        response = self.save({"favorites": []})
        expected = {**value, "favorites": []}
        self.assertEqual(response.json, {"depot": expected})
        view = {**value["view"], "sortMode": "name"}
        response = self.save({"view": view})
        expected["view"] = view
        self.assertEqual(response.json, {"depot": expected})
        self.assertEqual(self.read().json, {"depot": expected})

    def test_new_partial_preferences_fill_existing_defaults(self):
        response = self.save({"favorites": ["赤金", "赤金"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["depot"]["favorites"], ["赤金"])
        self.assertEqual(response.json["depot"]["view"]["stockFilter"], "all")
        self.assertEqual(response.json["depot"]["baseline"]["preset"], "previous")

    def test_first_migration_wins_over_stale_browser_preferences(self):
        first = depot_preferences()
        self.assertEqual(self.save(first, migrate=True).json, {"depot": first})
        stale = copy.deepcopy(first)
        stale["favorites"] = ["合成玉"]
        response = self.save(stale, migrate=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"depot": first})
        self.assertEqual(self.read().json, {"depot": first})

    def test_migration_rechecks_latest_preferences_inside_the_file_lock(self):
        first = depot_preferences()
        stale = copy.deepcopy(first)
        stale["favorites"] = ["合成玉"]
        waiting = threading.Event()
        finished = threading.Event()
        results = []

        def migrate():
            waiting.set()
            results.append(gui.save_depot(stale, migrate=True))
            finished.set()

        worker = threading.Thread(target=migrate)
        try:
            with gui._gui_lock:
                worker.start()
                self.assertTrue(waiting.wait(5))
                gui.save_depot(first)
                self.assertFalse(finished.is_set())
        finally:
            if worker.ident is not None:
                worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [first])
        self.assertEqual(self.read().json, {"depot": first})

    def test_snapshot_baseline_discards_time_range(self):
        value = depot_preferences()
        value["baseline"]["mode"] = "snapshot"
        response = self.save(value)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json["depot"]["baseline"]["range"])
        self.assertIsNone(self.read().json["depot"]["baseline"]["range"])

    def test_snapshot_numeric_keys_match_browser_decimal_syntax(self):
        for key in ("0", "-1", "+2.5", ".5", "1.", "1.7e9", " 1700000000 "):
            with self.subTest(key=key):
                value = depot_preferences()
                value["baseline"]["startKey"] = key
                response = self.save(value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["depot"]["baseline"]["startKey"], key)

    def test_invalid_saved_preferences_are_absent_without_rewriting(self):
        for invalid in (None, [], {}, {"favorites": "bad"}, {"unknown": True}):
            with self.subTest(invalid=invalid):
                gui._update_gui_data(depot=invalid)
                before = self.path.read_bytes()
                self.assertEqual(self.read().json, {"depot": None})
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_updates_preserve_saved_file(self):
        valid = depot_preferences()
        self.save(valid)
        before = self.path.read_bytes()
        variants = [None, [], {}, {"extra": True}, {"favorites": [1]}]
        variants.extend(
            {"favorites": names}
            for names in ([""], [" \t\n"], ["x" * 129], ["x"] * 1001)
        )
        for field, invalid in (
            ("stockFilter", "missing"),
            ("deltaFilter", True),
            ("showDerived", 1),
            ("sortMode", "missing"),
            ("showcaseTab", []),
            ("unknown", "value"),
        ):
            variants.append({"view": {**valid["view"], field: invalid}})
        variants.extend(({"view": {}}, {"baseline": {}}))
        for field, invalid in (
            ("mode", "missing"),
            ("preset", "missing"),
            ("followLatest", 1),
            ("startKey", "NaN"),
            ("startKey", "1_0"),
            ("startKey", "١٠"),
            ("startKey", "0x10"),
            ("startKey", "1" * 101),
            ("startKey", " " * 101),
            ("endKey", 10),
            ("range", [2, 1]),
            ("range", [True, False]),
            ("range", [None, None]),
            ("range", [0, float("inf")]),
            ("range", [0, 10**400]),
            ("range", "missing"),
            ("unknown", "value"),
        ):
            variants.append({"baseline": {**valid["baseline"], field: invalid}})
        for invalid in variants:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.save(invalid).status_code, 400)
                self.assertEqual(self.path.read_bytes(), before)
        for extra in ({"migrate": 1}, {"migrate": None}, {"unknown": True}):
            with self.subTest(extra=extra):
                self.assertEqual(self.save(valid, **extra).status_code, 400)
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.save({"favorites": []}, migrate=True).status_code, 400)
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_and_oversized_json_is_rejected(self):
        for raw in (b"null", b"[]", b"{}", b"{", b'{"depot":{}}'):
            with self.subTest(raw=raw):
                response = self.client.put(
                    "/gui/depot",
                    data=raw,
                    content_type="application/json",
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 400)
        raw = b"x" * (1024 * 1024 + 2)
        response = self.client.put(
            "/gui/depot",
            data=raw,
            content_type="application/json",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 413)
        stream = BytesIO(raw)
        response = self.client.put(
            "/gui/depot",
            headers=self.headers,
            content_type="application/json",
            environ_overrides={
                "CONTENT_LENGTH": "",
                "wsgi.input_terminated": True,
                "wsgi.input": stream,
            },
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(stream.tell(), 1024 * 1024 + 1)
        self.assertFalse(self.path.exists())

    def test_storage_failures_preserve_file_and_report_unavailable(self):
        self.save(depot_preferences())
        before = self.path.read_bytes()
        for error in (OSError("full"), TimeoutError("busy")):
            with (
                self.subTest(error=error),
                patch.object(gui, "atomic_write", side_effect=error),
            ):
                self.assertEqual(self.save({"favorites": []}).status_code, 503)
                self.assertEqual(self.path.read_bytes(), before)
        self.path.write_text("broken: [", encoding="utf-8")
        before = self.path.read_bytes()
        self.assertEqual(self.read().status_code, 503)
        self.assertEqual(self.save({"favorites": []}).status_code, 503)
        self.assertEqual(self.path.read_bytes(), before)

    def test_real_server_gui_saves_are_independent_of_profile_generation(self):
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
                "/gui/depot",
                json={"depot": depot_preferences()},
                headers={**self.headers, "X-Mower-Config-Generation": "obsolete"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, {"depot": depot_preferences()})
            check.assert_not_called()
            blocked = server.app.test_client().put(
                "/gui/depot",
                json={"depot": {"favorites": []}},
                headers={"token": "wrong"},
            )
            self.assertEqual(blocked.status_code, 403)
            self.assertEqual(gui.load_depot(), depot_preferences())


if __name__ == "__main__":
    unittest.main()
