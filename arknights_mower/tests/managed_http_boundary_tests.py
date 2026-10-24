"""Managed settings authorization through the instance HTTP request boundary."""

import os
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from flask import Request

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.config_profiles_tests import storage as storage
from arknights_mower.utils import (
    config,
    config_profiles,
    manager_common,
    network_settings,
    process_control,
)
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils.path import get_path


class ManagedHttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.enterContext(patch.dict(os.environ, {"MOWER_MANAGED": "1"}))
        self.enterContext(patch.object(config_profiles, "check_generation"))
        self.enterContext(patch.dict(self.server.app.config, {"UPDATES_ENABLED": True}))
        self.headers.update(
            {"X-Mower-Settings": "1", "X-Mower-Update": "1", "X-Mower-Control": "1"}
        )

    def test_hidden_operations_reject_before_parsing_or_side_effects(self):
        operations = (
            [
                ("POST", path)
                for path in (
                    "/device/preflight",
                    "/device/discover",
                    "/device/start",
                    "/device/avd/start",
                    "/device/redroid/start",
                    "/device/genymotion/start",
                    "/device/boss_key",
                    "/device/performance-test",
                    "/network/settings",
                    "/network/test",
                    "/software-update/settings",
                    "/software-update/auto-check",
                    "/software-update/source/remote",
                    "/software-update/source/check",
                    "/software-update/source/pr/check",
                    "/software-update/release/rollback-check",
                    "/software-update/start",
                    "/software-update/manual",
                    "/software-update/manual/inspect",
                    "/software-update/manual/discard",
                    "/software-update/cancel",
                    "/resource/install",
                    "/resource-update/manual",
                    "/maa-update/check",
                    "/maa-update/start",
                    "/maa-update/mirrorchyan-status",
                    "/maa-resource-update/check",
                    "/maa-resource-update/start",
                    "/config-backup/import",
                )
            ]
            + [("DELETE", "/device/performance-test")]
            + [
                (method, path)
                for method in ("GET", "HEAD")
                for path in (
                    "/check-maa",
                    "/maa-conn-preset",
                    "/test-custom-screenshot",
                    "/software-update/source/history",
                    "/software-update/source/pulls",
                    "/software-update/release/rollback-options",
                )
            ]
        )
        before = self.path.read_bytes()
        with (
            patch.object(
                Request, "get_json", side_effect=AssertionError("must not parse")
            ),
            patch.object(self.server.subprocess, "Popen") as process,
            patch.object(network_settings, "save_settings") as save,
            patch.object(self.control, "preflight") as preflight,
        ):
            for method, path in operations:
                for token in (None, "wrong", "device-token"):
                    with self.subTest(method=method, path=path, token=token):
                        headers = {**self.headers, "token": token} if token else {}
                        response = self.client.open(
                            path, method=method, headers=headers
                        )
                        self.assertEqual(response.status_code, 403)
                        if token == "device-token" and method != "HEAD":
                            self.assertEqual(
                                response.json["error"], "manager_owned_setting"
                            )
                        elif method != "HEAD":
                            self.assertIsNone(response.json)
            process.assert_not_called()
            save.assert_not_called()
            preflight.assert_not_called()
        self.assertEqual(before, self.path.read_bytes())

    def test_visibility_echo_uses_boolean_value_without_granting_write_permission(self):
        for current in (False, True):
            config.conf.extra_settings_visible = current
            for method in ("POST", "PATCH"):
                for submitted in (False, True, 0, 1):
                    with self.subTest(
                        current=current, method=method, submitted=submitted
                    ):
                        before = self.path.read_bytes()
                        response = self.client.open(
                            "/conf",
                            method=method,
                            headers=self.headers,
                            json={"extra_settings_visible": submitted, "theme": "dark"},
                        )
                        if submitted == current:
                            self.assertEqual(response.status_code, 200, response.json)
                            self.assertEqual(config.conf.theme, "dark")
                        else:
                            self.assertEqual(response.status_code, 403, response.json)
                            self.assertEqual(
                                response.json["error"], "manager_owned_setting"
                            )
                            self.assertEqual(self.path.read_bytes(), before)
                        self.assertIs(config.conf.extra_settings_visible, current)

    def test_configuration_locks_hidden_values_and_accepts_full_form_echo(self):
        for method in ("POST", "PATCH"):
            for payload in (
                {"maa_auto_update": True},
                {"maa_resource_auto_update": True},
                {"maa_mirrorchyan_token": "new-key"},
                {"maa_update_channel": "beta"},
                {"resource_update": {"enable": True}},
                {"screenshot": 0},
                {"screenshot_archive_limit_mb": 1},
                {"depot_history_limit": 12},
                {"depot_history_keep": 12},
                {"webview": {"port": 58001}},
                {"webview": {"token": "new-token"}},
            ):
                before = self.path.read_bytes()
                with self.subTest(method=method, payload=payload):
                    response = self.client.open(
                        "/conf", method=method, headers=self.headers, json=payload
                    )
                    self.assertEqual(response.status_code, 403, response.json)
                    self.assertEqual(self.path.read_bytes(), before)
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                **config.conf.model_dump(mode="json"),
                "theme": "dark",
                "account": "my-smtp",
                "ai_type": "custom-local",
                "maa_restore_theme_enable": True,
                "webview": {**config.conf.webview.model_dump(), "scale": 1.5},
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(config.conf.account, "my-smtp")
        self.assertEqual(config.conf.theme, "dark")
        self.assertEqual(config.conf.webview.scale, 1.5)
        self.assertTrue(config.conf.maa_restore_theme_enable)

    def test_explicit_extra_settings_and_standalone_allow_their_operations(self):
        updater = Mock()
        updater.check.return_value = {"ok": True}
        with patch.dict(
            self.server.app.extensions, {"software_update_provider": updater}
        ):
            for managed, visible in ((True, True), (False, False)):
                with patch.dict(os.environ, {"MOWER_MANAGED": "1" if managed else "0"}):
                    config.conf.extra_settings_visible = visible
                    with patch.object(
                        network_settings, "save_settings", return_value={}
                    ) as save:
                        response = self.client.post(
                            "/network/settings",
                            headers=self.headers,
                            json={"http_proxy": "", "github_proxy": ""},
                        )
                        self.assertEqual(response.status_code, 200, response.json)
                        save.assert_called_once()
                    response = self.client.post(
                        "/software-update/check",
                        headers=self.headers,
                        json={"channel": "stable"},
                    )
                    self.assertEqual(response.status_code, 200, response.json)
                    response = self.client.patch(
                        "/conf", headers=self.headers, json={"screenshot": 2}
                    )
                    self.assertEqual(response.status_code, 200, response.json)
                    response = self.client.post(
                        "/device/preflight",
                        headers=self.headers,
                        json={"unknown": True},
                    )
                    self.assertEqual(response.status_code, 403 if managed else 400)
            self.assertEqual(updater.check.call_count, 2)
        config.conf.extra_settings_visible = True
        with patch.dict(self.server.app.config, {"UPDATES_ENABLED": False}):
            for token in (None, "wrong", "device-token"):
                response = self.client.post(
                    "/software-update/check",
                    headers={**self.headers, "token": token or ""},
                )
                self.assertEqual(response.status_code, 403)
                if token == "device-token":
                    self.assertEqual(response.json["error"], "updates_disabled")
                else:
                    self.assertIsNone(response.json)

    def test_process_actions_preserve_visible_task_controls(self):
        with patch.object(
            process_control, "request_action", return_value={"ok": True}
        ) as action:
            for token in (None, "wrong"):
                with patch.object(
                    Request,
                    "get_json",
                    side_effect=AssertionError("must authenticate first"),
                ):
                    response = self.client.post(
                        "/process-control/action",
                        headers={**self.headers, "token": token or ""},
                    )
                    self.assertEqual(response.status_code, 403)
            action.assert_not_called()
            for selected in ("restart", "stop", "restart_resume", "apply_schedule"):
                response = self.client.post(
                    "/process-control/action",
                    headers=self.headers,
                    json={"action": selected},
                )
                self.assertEqual(
                    response.status_code,
                    403 if selected in {"restart", "stop"} else 200,
                )
            self.assertEqual(action.call_count, 2)
            self.assertEqual(
                [call.args[0] for call in action.call_args_list],
                ["restart_resume", "apply_schedule"],
            )

    def test_enabled_maintenance_keeps_maa_in_manager_and_allows_resource_policy(self):
        config.conf.extra_settings_visible = True
        for path in ("/maa-update/check", "/maa-resource-update/start", "/check-maa"):
            response = self.client.open(
                path,
                method="GET" if path == "/check-maa" else "POST",
                headers=self.headers,
                json={},
            )
            self.assertEqual(response.status_code, 403)
        response = self.client.patch(
            "/conf", headers=self.headers, json={"resource_update": {"enable": True}}
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(config.conf.resource_update.enable)
        with (
            patch.dict(os.environ, {"MOWER_MANAGED": "0"}),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=False,
            ) as installation,
        ):
            response = self.client.post(
                "/maa-update/check", headers=self.headers, json={}
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["ok"])
            installation.assert_called_once()

    def test_local_version_and_normal_task_reads_remain_available(self):
        with patch(
            "arknights_mower.utils.resource_version.check_resource_update",
            return_value={"version": "local"},
        ):
            response = self.client.get(
                "/resource-version?local=1", headers=self.headers
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.get("/conf", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/device/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        with patch.object(self.server, "_start_mower", return_value=True) as start:
            response = self.client.get("/start/0", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            start.assert_called_once_with("0")
        with patch(
            "arknights_mower.views.screenshot.latest_screenshot_response",
            return_value={"frame": "current"},
        ) as screenshot:
            response = self.client.get("/screenshot/latest", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            screenshot.assert_called_once_with()
        with patch.object(self.server, "clear_data") as clear:
            response = self.client.delete(
                "/record/clear-data", headers=self.headers, json={"date_time": 1000}
            )
            self.assertEqual(response.status_code, 200)
            clear.assert_called_once()
        store = Mock(folder=self.server.get_path("@app/screenshot"))
        store.delete_error_archive.return_value = True
        with patch(
            "arknights_mower.utils.log.get_screenshot_store", return_value=store
        ):
            response = self.client.delete(
                "/diagnostics/errors/123",
                headers={**self.headers, "X-Mower-Diagnostics": "1"},
            )
            self.assertEqual(response.status_code, 204)
            store.delete_error_archive.assert_called_once_with("123")

    def test_sidebar_version_checks_still_require_token_and_update_permission(self):
        updater = Mock()
        updater.check.return_value = {"ok": True}
        with (
            patch.dict(
                self.server.app.extensions, {"software_update_provider": updater}
            ),
            patch(
                "arknights_mower.utils.resource_version.check_resource_update",
                return_value={"version": "v1"},
            ) as resource,
        ):
            for token in (None, "wrong", "device-token"):
                headers = {**self.headers, "token": token or ""}
                response = self.client.post(
                    "/software-update/check",
                    headers=headers,
                    json={"channel": "stable"},
                )
                self.assertEqual(
                    response.status_code, 200 if token == "device-token" else 403
                )
                response = self.client.get("/resource-version", headers=headers)
                self.assertEqual(
                    response.status_code, 200 if token == "device-token" else 403
                )
            updater.check.assert_called_once_with("stable")
            resource.assert_called_once_with(local_only=False)
            for path in ("/software-update/start", "/resource/install"):
                response = self.client.post(path, headers=self.headers, json={})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json["error"], "manager_owned_setting")


@pytest.mark.parametrize("operation", ["create", "import", "activate"])
@pytest.mark.parametrize("extra_visible", [False, True])
def test_visible_profile_http_operations_preserve_hidden_values(
    storage, monkeypatch, operation, extra_visible
):
    import server

    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setattr(
        manager_common,
        "read_document",
        lambda: {
            "values": {},
            "instance_overrides": {
                manager_common.policy_key(get_path("@app")): {
                    "local_keys": ["screenshot", "screenshot_archive_limit_mb"],
                    "manager_values": {},
                }
            },
        },
    )
    monkeypatch.setattr(server.app, "token", "profile-token", raising=False)
    monkeypatch.setitem(server.app.config, "CONFIG_PROFILES_BUSY", lambda: False)
    monkeypatch.setitem(server.app.config, "CONFIGURATION_ACTIVATED", lambda: None)
    original = config_profiles.list_profiles()["active_id"]
    incoming = backup.export_archive()
    if operation == "activate":
        config_profiles.create_profile(
            "second", [], expected_generation=config_profiles.current_generation()
        )
    config.conf = config.conf.updated(
        {
            "extra_settings_visible": extra_visible,
            "screenshot": 7,
            "screenshot_archive_limit_mb": 987,
            "depot_history_limit": 123,
            "depot_history_keep": 22,
            "resource_update": {"enable": True},
            "maa_auto_update": True,
            "maa_mirrorchyan_token": "manager-key",
            "maa_path": "/manager/MAA",
            "webview": {"port": 19333, "token": "saved-token"},
        }
    )
    config.save_conf()
    headers = {
        "token": "profile-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": config_profiles.current_generation(),
    }
    client = server.app.test_client()
    if operation == "create":
        response = client.post(
            "/config-profiles", headers=headers, json={"name": "created", "inherit": []}
        )
    elif operation == "activate":
        response = client.post(
            f"/config-profiles/{original}/activate", headers=headers, json={"keep": []}
        )
    else:
        response = client.post(
            "/config-profiles/import",
            headers=headers,
            data={
                "name": "imported",
                "keep": "[]",
                "backup": (BytesIO(incoming), "incoming.zip"),
            },
        )
    assert response.status_code == 200, response.json
    config.load_conf()
    assert config.conf.screenshot == 7
    assert config.conf.screenshot_archive_limit_mb == 987
    assert config.conf.depot_history_limit == (3000 if extra_visible else 123)
    assert config.conf.depot_history_keep == (0 if extra_visible else 22)
    assert config.conf.resource_update.enable is (not extra_visible)
    assert config.conf.maa_auto_update
    assert config.conf.maa_mirrorchyan_token == "manager-key"
    assert config.conf.maa_path == "/manager/MAA"
    assert config.conf.webview.port == 19333
    assert config.conf.webview.token == "saved-token"
    assert config.conf.extra_settings_visible is extra_visible


class ManagedInheritedConfigurationTests(unittest.TestCase):
    def setUp(self):
        ManagedHttpBoundaryTests.setUp(self)
        config.conf = config.conf.updated(
            {
                "extra_settings_visible": True,
                "maa_path": "/local/maa",
                "screenshot": 7,
                "screenshot_archive_limit_mb": 987,
            }
        )
        config.save_conf()
        self.enterContext(
            patch.object(
                manager_common,
                "read_document",
                return_value={
                    "values": {
                        "maa_path": "/common/maa",
                        "screenshot": 2,
                        "screenshot_archive_limit_mb": 456,
                    },
                    "independent_instances": {},
                },
            )
        )
        launched, inherited = manager_common.launch_snapshot(config.conf, managed=True)
        config.conf = launched
        self.enterContext(patch.object(config, "manager_inherited_settings", inherited))

    def test_conf_reports_inherited_metadata_and_preserves_local_values_on_save(self):
        response = self.client.get("/conf", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json["manager_inherited_settings"],
            ["maa_path", "screenshot", "screenshot_archive_limit_mb"],
        )
        response = self.client.post(
            "/conf",
            headers=self.headers,
            json={"drone_count_limit": 77, "manager_inherited_settings": []},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(config.conf.screenshot, 2)
        self.assertEqual(
            config.manager_inherited_settings, manager_common.LOCAL_OVERRIDE_KEYS
        )
        import yaml

        saved = yaml.safe_load(self.path.read_text())
        self.assertEqual(saved["screenshot"], 7)
        self.assertEqual(saved["screenshot_archive_limit_mb"], 987)
        self.assertEqual(saved["maa_path"], "/local/maa")
        self.assertNotIn("manager_inherited_settings", saved)
        response = self.client.post(
            "/conf", headers=self.headers, json={"screenshot": 9}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(config.conf.screenshot, 2)
        self.assertEqual(yaml.safe_load(self.path.read_text())["screenshot"], 7)

    def test_conf_metadata_requires_token_before_reading_configuration(self):
        before = self.path.read_bytes()
        with patch(
            "arknights_mower.utils.workshop_config.read_user_config",
            side_effect=AssertionError("unauthorized read"),
        ) as read:
            for token in (None, "wrong"):
                response = self.client.get(
                    "/conf", headers={**self.headers, "token": token or ""}
                )
                self.assertEqual(response.status_code, 403)
            read.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_standalone_conf_does_not_report_manager_inherited_metadata(self):
        with patch.dict(os.environ, {"MOWER_MANAGED": "0"}):
            response = self.client.get("/conf", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("manager_inherited_settings", response.json)
