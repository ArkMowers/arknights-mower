import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import server
from arknights_mower.utils.maa_resource_update import MaaResourceRelease
from arknights_mower.utils.maa_update import MaaRelease, MaaUpdateError, ReleaseAsset


def _maa_release(version: str) -> MaaRelease:
    return MaaRelease(
        tag=version,
        runtime=ReleaseAsset(
            name=f"MAA-{version}-macos-runtime-universal.zip",
            url="https://example.test/maa.zip",
            size=1,
        ),
    )


class _FakeThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def is_alive(self):
        return False

    def start(self):
        self.started = True


class TestMaaUpdateRoutes(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.headers = {}
        if hasattr(server.app, "token"):
            self.headers["token"] = server.app.token
        self.temp = tempfile.TemporaryDirectory()
        self.target = str(Path(self.temp.name) / "MAA")
        server.maa_update_check.update(
            {
                "id": "",
                "target": "",
                "source": "",
                "channel": "",
                "installed_version": "",
                "latest_version": "",
            }
        )
        server.maa_resource_update_check.update(
            {
                "id": "",
                "target": "",
                "source": "",
                "current_version": "",
                "latest_version": "",
                "latest_release_note": "",
            }
        )
        server.maa_update_job.update({"thread": None, "status": "idle"})
        server.maa_resource_update_job.update({"thread": None, "status": "idle"})

    def tearDown(self):
        server.maa_update_job.update({"thread": None, "status": "idle"})
        server.maa_resource_update_job.update({"thread": None, "status": "idle"})
        self.temp.cleanup()

    def test_maa_busy_gate_uses_actual_maa_activity_not_mower_process(self):
        server.maa_check_job.update({"status": "idle"})
        with (
            patch.object(server, "_collect_maa_check_result"),
            patch.object(server, "mower_thread", _FakeThread()),
            patch("arknights_mower.utils.maa_backup.maa_in_use", return_value=False),
        ):
            self.assertIsNone(server._maa_busy_response())
        with (
            patch.object(server, "_collect_maa_check_result"),
            patch("arknights_mower.utils.maa_backup.maa_in_use", return_value=True),
        ):
            self.assertIn("MAA 正在使用中", server._maa_busy_response()["message"])

    def test_android_saved_mirror_config_uses_official_default_and_rejects_requests(
        self,
    ):
        with (
            patch.dict("os.environ", {"MOWER_ANDROID": "1"}),
            patch.object(server, "__system__", "linux"),
            patch.object(server.config.conf, "maa_mirrorchyan_token", "saved-token"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch.object(server, "active_job", return_value=False),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.5",
            ),
            patch("arknights_mower.utils.maa_update._request_mirrorchyan") as network,
        ):
            response = self.client.get(
                "/maa-update/info",
                query_string={"maa_path": self.target},
                headers=self.headers,
            )
            self.assertEqual(response.json["default_source"], "github")
            for route in (
                "/maa-update/check",
                "/maa-update/start",
                "/maa-update/mirrorchyan-status",
            ):
                with self.subTest(route=route):
                    response = self.client.post(
                        route,
                        json={
                            "maa_path": self.target,
                            "source": "mirrorchyan",
                            "channel": "beta",
                            "mirror_token": "saved-token",
                        },
                        headers=self.headers,
                    )
                    self.assertFalse(response.json["ok"])
                    self.assertIn("Android 暂不支持 Mirror酱", response.json["message"])
            network.assert_not_called()

    def test_portable_maa_path_is_resolved_consistently_by_all_update_routes(self):
        from arknights_mower.utils import path

        current = {"version": "2026-09-03 01:00:00.000", "release_note": ""}
        release = MaaResourceRelease(
            version="2026-09-04 01:07:54.000", source="github", available=True
        )
        with (
            patch.object(path, "_data_dir", Path(self.temp.name)),
            patch.object(path, "global_space", "other-instance"),
            patch.object(server.config.conf, "maa_path", "@app/MAA"),
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch.object(server, "mower_thread", None),
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "Thread", side_effect=_FakeThread) as launch,
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                return_value=release,
            ),
        ):
            for prefix in ("maa-update", "maa-resource-update"):
                info = self.client.get(
                    f"/{prefix}/info", headers=self.headers
                ).get_json()
                self.assertEqual(info["target"], self.target)
                payload = {
                    "maa_path": "@app/MAA",
                    "source": "github",
                    "channel": "stable",
                }
                checked = self.client.post(
                    f"/{prefix}/check", json=payload, headers=self.headers
                ).get_json()
                self.assertTrue(checked["ok"], checked)
                started = self.client.post(
                    f"/{prefix}/start",
                    json={**payload, "check_id": checked["check_id"]},
                    headers=self.headers,
                ).get_json()
                self.assertTrue(started["ok"], started)
                self.assertEqual(launch.call_args.kwargs["args"][0], self.target)
                server.maa_update_job.update({"thread": None, "status": "idle"})
                server.maa_resource_update_job.update(
                    {"thread": None, "status": "idle"}
                )
            resource = Path(self.target) / "resource"
            resource.mkdir(parents=True)
            (resource / "config.json").write_text(
                '{"connection":[{"configName":"CompatMac"}]}'
            )
            response = self.client.get("/maa-conn-preset", headers=self.headers)
            self.assertEqual(response.get_json(), ["CompatMac"])

    def test_maa_check_returns_check_id_only_for_new_version(self):
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ) as read_version,
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
        ):
            response = self.client.post(
                "/maa-update/check",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": "stable",
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["available"])
        self.assertTrue(data["check_id"])
        read_version.assert_called_once_with(self.target, fresh=True)

        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ),
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=_maa_release("v6.18.0"),
            ),
        ):
            response = self.client.post(
                "/maa-update/check",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": "stable",
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["available"])
        self.assertEqual(data["check_id"], "")

    def test_maa_info_returns_cached_latest_and_fresh_installed_version(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        server.maa_update_check.update(
            {
                "id": "",
                "target": target,
                "source": "github",
                "channel": channel,
                "installed_version": "v6.17.0",
                "latest_version": "v6.18.0",
            }
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ) as read_version,
        ):
            response = self.client.get(
                "/maa-update/info",
                query_string={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertEqual(data["latest"]["tag"], "v6.18.0")
        self.assertEqual(data["installed_version"], "v6.18.0")
        read_version.assert_called_once_with(Path(target), fresh=True)

    def test_windows_installed_maa_supports_check_and_update(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        release = MaaRelease(
            tag="v6.18.0",
            runtime=ReleaseAsset(
                name="MAAComponent-OTA-v6.17.0_v6.18.0-win-x64.zip",
                url="https://example.test/maa-ota.zip",
                size=1,
            ),
            package_type="ota",
        )
        with (
            patch.object(server, "__system__", "windows"),
            patch.object(server, "_maa_busy_response", return_value=None),
            patch.object(server, "Thread", _FakeThread),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
            patch(
                "arknights_mower.utils.maa_update.normalize_windows_arch",
                return_value="x64",
            ),
            patch(
                "arknights_mower.utils.maa_update.get_latest_release",
                return_value=release,
            ) as latest,
        ):
            info = self.client.get(
                "/maa-update/info",
                query_string={"maa_path": target, "channel": channel},
                headers=self.headers,
            ).get_json()
            checked = self.client.post(
                "/maa-update/check",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                },
                headers=self.headers,
            ).get_json()
            started = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                    "check_id": checked["check_id"],
                },
                headers=self.headers,
            ).get_json()

        self.assertTrue(info["supported"])
        self.assertTrue(info["check_required"])
        self.assertTrue(checked["available"])
        self.assertEqual(checked["latest"]["package_type"], "ota")
        self.assertTrue(started["ok"])
        latest.assert_called_once_with(
            system="windows",
            channel=channel,
            installed_version="v6.17.0",
        )

    def test_maa_update_start_requires_matching_successful_check(self):
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": self.target,
                    "source": "github",
                    "channel": server.config.conf.maa_update_channel,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("先检查 MAA 更新", data["message"])

    def test_maa_update_start_accepts_matching_successful_check(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        check_id = server._record_update_check(
            server.maa_update_check,
            server.maa_update_check_lock,
            target=target,
            source="github",
            channel=channel,
            installed_version="v6.17.0",
            latest_version="v6.18.0",
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "Thread", _FakeThread),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.17.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(server.maa_update_check["id"], "")

    def test_maa_update_start_rejects_equal_checked_version(self):
        target = str(Path(self.target).expanduser())
        channel = server.config.conf.maa_update_channel
        check_id = server._record_update_check(
            server.maa_update_check,
            server.maa_update_check_lock,
            target=target,
            source="github",
            channel=channel,
            installed_version="v6.18.0",
            latest_version="v6.18.0",
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch.object(server, "_mower_busy_response", return_value=None),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.read_installed_version",
                return_value="v6.18.0",
            ),
        ):
            response = self.client.post(
                "/maa-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "channel": channel,
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("发现新版本后再更新", data["message"])

    def test_resource_info_check_and_start_on_windows_and_android(self):
        current = {"version": "2026-09-03 01:00:00.000", "release_note": ""}
        for platform, android, source in (
            ("windows", "0", "github"),
            ("windows", "0", "mirrorchyan"),
            ("linux", "1", "github"),
            ("linux", "1", "mirrorchyan"),
        ):
            with (
                self.subTest(platform=platform, android=android, source=source),
                patch.dict("os.environ", {"MOWER_ANDROID": android}),
                patch.object(server, "__system__", platform),
                patch.object(server, "_maa_busy_response", return_value=None),
                patch.object(server, "active_job", return_value=False),
                patch.dict(
                    server.maa_resource_update_job, {"thread": None, "status": "idle"}
                ),
                patch.object(server, "Thread", side_effect=_FakeThread) as launch,
                patch.object(server.config, "save_conf"),
                patch.object(
                    server.config.conf, "maa_mirrorchyan_token", "fixture-token"
                ),
                patch(
                    "arknights_mower.utils.maa_update.has_maa_installation",
                    return_value=True,
                ),
                patch(
                    "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                    return_value=current,
                ),
                patch(
                    "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                    return_value=MaaResourceRelease(
                        version="2026-09-04 01:07:54.000", source=source
                    ),
                ),
            ):
                payload = {"maa_path": self.target, "source": source}
                info = self.client.get(
                    "/maa-resource-update/info",
                    query_string=payload,
                    headers=self.headers,
                ).get_json()
                self.assertTrue(info["supported"])
                self.assertEqual(info["platform"], platform)
                self.assertEqual(info["current"], current)

                unchecked = self.client.post(
                    "/maa-resource-update/start", json=payload, headers=self.headers
                ).get_json()
                self.assertFalse(unchecked["ok"])
                launch.assert_not_called()

                checked = self.client.post(
                    "/maa-resource-update/check", json=payload, headers=self.headers
                ).get_json()
                self.assertTrue(checked["ok"])
                self.assertTrue(checked["available"])
                self.assertTrue(checked["check_id"])
                started = self.client.post(
                    "/maa-resource-update/start",
                    json={**payload, "check_id": checked["check_id"]},
                    headers=self.headers,
                ).get_json()
                self.assertTrue(started["ok"])
                self.assertEqual(server.maa_resource_update_check["id"], "")
                launch.assert_called_once_with(
                    target=server._run_maa_resource_update,
                    args=(self.target, source, "fixture-token", platform),
                    daemon=True,
                )

    def test_unknown_resource_version_accepts_only_matching_checked_update(self):
        current = {"version": "", "release_note": ""}
        with (
            patch.object(server, "__system__", "windows"),
            patch.object(server, "_maa_busy_response", return_value=None),
            patch.object(server, "active_job", return_value=False),
            patch.object(server, "Thread", side_effect=_FakeThread) as launch,
            patch.object(server.config.conf, "maa_mirrorchyan_token", ""),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                return_value=MaaResourceRelease(
                    version="2026-10-09 23:31:13.000", source="github"
                ),
            ),
        ):
            payload = {"maa_path": self.target, "source": "github"}
            checked = self.client.post(
                "/maa-resource-update/check", json=payload, headers=self.headers
            ).get_json()
            self.assertTrue(checked["available"])
            for changes in (
                {"check_id": "wrong"},
                {"maa_path": self.target + "-other"},
                {"source": "mirrorchyan", "mirror_token": "fixture"},
            ):
                with (
                    self.subTest(changes=changes),
                    patch.object(server.config, "save_conf"),
                ):
                    rejected = self.client.post(
                        "/maa-resource-update/start",
                        json={**payload, "check_id": checked["check_id"], **changes},
                        headers=self.headers,
                    ).get_json()
                    self.assertFalse(rejected["ok"])
            launch.assert_not_called()
            started = self.client.post(
                "/maa-resource-update/start",
                json={**payload, "check_id": checked["check_id"]},
                headers=self.headers,
            ).get_json()
            self.assertTrue(started["ok"])
            launch.assert_called_once()
            self.assertEqual(server.maa_resource_update_check["id"], "")

    def test_connection_config_permission_failure_identifies_file(self):
        resource = Path(self.target) / "resource"
        resource.mkdir(parents=True)
        config_path = resource / "config.json"
        config_path.write_text('{"connection": []}', encoding="utf-8")
        with (
            patch.object(server.config.conf, "maa_path", self.target),
            patch.object(
                server, "open", side_effect=PermissionError("denied"), create=True
            ),
        ):
            response = self.client.get(
                "/maa-conn-preset", headers=self.headers
            ).get_json()
        self.assertFalse(response["ok"])
        self.assertIn(str(config_path), response["message"])
        self.assertIn("访问被拒绝", response["message"])

    def test_connection_config_missing_and_invalid_files_are_distinguished(self):
        resource = Path(self.target) / "resource"
        resource.mkdir(parents=True)
        config_path = resource / "config.json"
        with patch.object(server.config.conf, "maa_path", self.target):
            response = self.client.get(
                "/maa-conn-preset", headers=self.headers
            ).get_json()
            self.assertFalse(response["ok"])
            self.assertIn("文件不存在", response["message"])
            for content in (b"not json", b"\xff", b"{}", b'{"connection": null}'):
                with self.subTest(content=content):
                    config_path.write_bytes(content)
                    response = self.client.get(
                        "/maa-conn-preset", headers=self.headers
                    ).get_json()
                    self.assertFalse(response["ok"])
                    self.assertIn("格式无效", response["message"])
                    self.assertIn(str(config_path), response["message"])
                    self.assertNotIn("访问被拒绝", response["message"])

    def test_connection_config_presets_keep_successful_list_response(self):
        resource = Path(self.target) / "resource"
        resource.mkdir(parents=True)
        (resource / "config.json").write_text(
            '{"connection": [{"configName": "General"}]}', encoding="utf-8"
        )
        with patch.object(server.config.conf, "maa_path", self.target):
            response = self.client.get(
                "/maa-conn-preset", headers=self.headers
            ).get_json()
        self.assertEqual(response, ["General"])

    def test_resource_check_and_start_use_separate_check_result(self):
        current = {"version": "2026-09-03 01:00:00.000", "release_note": ""}
        release = MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
            available=True,
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.get_maa_resource_release",
                return_value=release,
            ),
        ):
            checked = self.client.post(
                "/maa-resource-update/check",
                json={"maa_path": self.target, "source": "github"},
                headers=self.headers,
            ).get_json()

        self.assertTrue(checked["available"])
        self.assertTrue(checked["check_id"])

        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value=current,
            ),
        ):
            response = self.client.post(
                "/maa-resource-update/start",
                json={"maa_path": self.target, "source": "github"},
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("先检查 MAA 资源更新", data["message"])

    def test_resource_info_returns_cached_latest_version(self):
        target = str(Path(self.target).expanduser())
        latest = "2026-09-04 01:07:54.000"
        server.maa_resource_update_check.update(
            {
                "id": "",
                "target": target,
                "source": "github",
                "current_version": "2026-09-03 01:00:00.000",
                "latest_version": latest,
                "latest_release_note": "测试活动",
            }
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value={"version": latest, "release_note": "测试活动"},
            ),
        ):
            response = self.client.get(
                "/maa-resource-update/info",
                query_string={"maa_path": target, "source": "github"},
                headers=self.headers,
            )

        data = response.get_json()
        self.assertEqual(data["latest"]["version"], latest)
        self.assertEqual(data["latest"]["release_note"], "测试活动")

    def test_resource_update_start_rejects_equal_checked_version(self):
        target = str(Path(self.target).expanduser())
        version = "2026-09-04 01:07:54.000"
        check_id = server._record_update_check(
            server.maa_resource_update_check,
            server.maa_resource_update_check_lock,
            target=target,
            source="github",
            current_version=version,
            latest_version=version,
        )
        with (
            patch.object(server, "__system__", "darwin"),
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value={"version": version, "release_note": ""},
            ),
        ):
            response = self.client.post(
                "/maa-resource-update/start",
                json={
                    "maa_path": target,
                    "source": "github",
                    "check_id": check_id,
                },
                headers=self.headers,
            )

        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("发现新版本后再更新", data["message"])


class TestMaaUpdateWorkers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = str(Path(self.temp.name) / "MAA")
        self.client = server.app.test_client()
        self.headers = (
            {"token": server.app.token} if hasattr(server.app, "token") else {}
        )
        self.enterContext(patch.dict("os.environ", {"MOWER_ANDROID": "0"}))
        for job in (server.maa_update_job, server.maa_resource_update_job):
            self.enterContext(
                patch.dict(job, {"status": "running", "result": None}, clear=True)
            )

    def core_result(self, system):
        return {
            "target": self.target,
            "backup": self.target + ".old",
            "version": "v6.20.0",
            "source": "github",
            "channel": "stable",
            "operation": "update",
            "platform": system,
            "arch": "x64",
            "python_downloaded": 10,
            "python_full_size": 100,
        }

    def resource_result(self):
        return {
            "updated": True,
            "target": self.target,
            "backup": str(Path(self.target) / "resource.old"),
            "version": "2026-10-12 00:00:00.000",
            "source": "github",
        }

    def snapshot(self, kind):
        return self.client.get(
            f"/maa{kind}-update/status", headers=self.headers
        ).get_json()["job"]

    def test_resource_update_preserves_core_when_unloading_is_unsafe(self):
        for system in ("darwin", "linux", "windows"):
            with self.subTest(system=system):
                result = self.resource_result()
                with (
                    patch(
                        "arknights_mower.utils.maa_resource_update.install_maa_resource_update",
                        return_value=result,
                    ),
                    patch(
                        "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                        return_value={"version": result["version"]},
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.clear_loaded_maa_cache",
                        side_effect=MaaUpdateError("核心无法卸载，请重启 Mower"),
                    ) as clear,
                ):
                    server._run_maa_resource_update(self.target, "github", "", system)
                job = self.snapshot("-resource")
                self.assertEqual(job["status"], "success")
                self.assertEqual(job["result"]["backup"], result["backup"])
                self.assertEqual(
                    job["result"]["installed"]["version"], result["version"]
                )
                self.assertFalse(job["result"].get("restart_required"))
                clear.assert_not_called()

    def test_installed_core_update_preserves_result_when_restart_is_required(self):
        for system in ("darwin", "linux", "windows"):
            with self.subTest(system=system):
                result = self.core_result(system)
                with (
                    patch(
                        "arknights_mower.utils.maa_update.has_maa_installation",
                        return_value=True,
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.install_latest_maa",
                        return_value=result,
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.clear_loaded_maa_cache",
                        side_effect=MaaUpdateError("核心无法卸载，请重启 Mower"),
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.read_installed_version",
                        return_value=result["version"],
                    ) as probe,
                ):
                    server._run_maa_update(self.target, "github", "", system, "stable")
                job = self.snapshot("")
                self.assertEqual(job["status"], "success")
                self.assertEqual(job["progress"], 100)
                self.assertEqual(job["result"]["backup"], result["backup"])
                self.assertEqual(job["result"]["installed_version"], result["version"])
                self.assertTrue(job["result"]["restart_required"])
                self.assertIn("重启 Mower", job["message"])
                probe.assert_called_once_with(self.target, fresh=True)

    def test_completed_installation_with_successful_cleanup_and_probe_failure(self):
        for probe_error in (None, MaaUpdateError("版本探测失败")):
            with self.subTest(probe_error=probe_error):
                result = self.core_result("linux")
                with (
                    patch(
                        "arknights_mower.utils.maa_update.has_maa_installation",
                        return_value=True,
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.install_latest_maa",
                        return_value=result,
                    ),
                    patch(
                        "arknights_mower.utils.maa_update.clear_loaded_maa_cache",
                    ) as clear,
                    patch(
                        "arknights_mower.utils.maa_update.read_installed_version",
                        return_value=result["version"],
                        side_effect=probe_error,
                    ),
                ):
                    server._run_maa_update(self.target, "github", "", "linux", "stable")
                job = self.snapshot("")
                self.assertEqual(job["status"], "success")
                self.assertEqual(job["result"]["backup"], result["backup"])
                self.assertFalse(job["result"]["restart_required"])
                self.assertNotIn("重启 Mower", job["message"])
                clear.assert_called_once_with(self.target)
                if probe_error:
                    self.assertEqual(job["result"]["installed_version"], "")
                    self.assertIn("无法读取已安装核心版本", job["message"])
                else:
                    self.assertEqual(
                        job["result"]["installed_version"], result["version"]
                    )
                    self.assertNotIn("无法读取已安装核心版本", job["message"])

    def test_installation_failure_remains_an_error(self):
        with (
            patch(
                "arknights_mower.utils.maa_update.has_maa_installation",
                return_value=True,
            ),
            patch(
                "arknights_mower.utils.maa_update.install_latest_maa",
                side_effect=MaaUpdateError("目录替换失败"),
            ),
            patch("arknights_mower.utils.maa_update.clear_loaded_maa_cache") as clear,
        ):
            server._run_maa_update(self.target, "github", "", "windows", "stable")
        job = self.snapshot("")
        self.assertEqual(job["status"], "error")
        self.assertIsNone(job["result"])
        self.assertIn("目录替换失败", job["message"])
        clear.assert_not_called()

    def test_android_resource_update_still_packs_and_requires_service_restart(self):
        result = self.resource_result()
        pack = Mock()
        with (
            patch.dict("os.environ", {"MOWER_ANDROID": "1"}),
            patch.dict(
                "sys.modules",
                {"mower_android.managed": SimpleNamespace(pack_component=pack)},
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.install_maa_resource_update",
                return_value=result,
            ),
            patch(
                "arknights_mower.utils.maa_resource_update.read_maa_resource_info",
                return_value={"version": result["version"]},
            ),
        ):
            server._run_maa_resource_update(self.target, "github", "", "linux")
        job = self.snapshot("-resource")
        self.assertEqual(job["status"], "success")
        self.assertTrue(job["result"]["restart_required"])
        self.assertIn("重启安卓服务", job["message"])
        pack.assert_called_once_with(self.target)


if __name__ == "__main__":
    unittest.main()
