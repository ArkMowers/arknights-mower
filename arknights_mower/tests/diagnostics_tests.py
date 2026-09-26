"""验证按时间回看日志和截图。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from arknights_mower.utils.diagnostics import error_events, export_bundle, timeline


class DiagnosticTimelineTests(unittest.TestCase):
    def test_delete_route_removes_only_requested_archive(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_root = root / "screenshot" / "errors"
            for archive_id in ("123", "456"):
                folder = archive_root / archive_id
                folder.mkdir(parents=True)
                (folder / "event.json").write_text(
                    json.dumps({"time_ns": int(archive_id), "message": "运行失败"}),
                    encoding="utf-8",
                )
                (folder / f"{archive_id}.jpg").write_bytes(b"image")
            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch(
                    "arknights_mower.utils.log.get_screenshot_store", return_value=None
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                client = server.app.test_client()
                self.assertEqual(
                    client.delete("/diagnostics/errors/123").status_code, 403
                )
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/123", headers={"token": "diagnostics-test"}
                    ).status_code,
                    403,
                )
                headers = {"token": "diagnostics-test", "X-Mower-Diagnostics": "1"}
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/123",
                        headers={**headers, "Origin": "https://elsewhere.example"},
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/invalid", headers=headers
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/999", headers=headers
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/123", headers=headers
                    ).status_code,
                    204,
                )
                self.assertFalse((archive_root / "123").exists())
                self.assertTrue((archive_root / "456" / "456.jpg").is_file())
                self.assertEqual(
                    [
                        event["id"]
                        for event in client.get(
                            "/diagnostics/errors", headers=headers
                        ).json["events"]
                    ],
                    ["456"],
                )
                self.assertEqual(
                    client.get(
                        "/diagnostics/errors/123/export", headers=headers
                    ).status_code,
                    404,
                )

    def test_export_route_validates_time_and_returns_zip(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "log").mkdir()
            (root / "screenshot").mkdir()
            center = datetime.now().replace(microsecond=0)
            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                client = server.app.test_client()
                self.assertEqual(client.get("/diagnostics/export").status_code, 403)
                self.assertEqual(
                    client.get(
                        "/diagnostics/export?at=invalid",
                        headers={"token": "diagnostics-test"},
                    ).status_code,
                    400,
                )
                response = client.get(
                    f"/diagnostics/export?at={int(center.timestamp() * 1000)}",
                    headers={"token": "diagnostics-test"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "application/zip")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                with ZipFile(BytesIO(response.data)) as bundle:
                    self.assertIn("日志.txt", bundle.namelist())
                response.close()

    def test_log_rows_link_to_recent_screenshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            shots = root / "screenshot"
            logs.mkdir()
            center = datetime.now().replace(microsecond=0)
            image_time = center - timedelta(seconds=2)
            folder = shots / image_time.strftime("%Y%m%d-%H")
            folder.mkdir(parents=True)
            image = folder / f"{int(image_time.timestamp() * 10**9)}.jpg"
            image.write_bytes(b"image")
            (logs / "runtime.log").write_text(
                f"{center:%Y-%m-%d %H:%M:%S} task.py:1 INFO 画面已更新\n  更多说明\n",
                encoding="utf-8",
            )
            rows = timeline(logs, shots, center)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["screenshot"], image.relative_to(shots).as_posix())
            self.assertIn("更多说明", rows[0]["message"])

    def test_error_archive_is_listed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "errors" / "123"
            root.mkdir(parents=True)
            (root / "event.json").write_text(
                '{"time_ns": 123, "message": "运行失败"}', encoding="utf-8"
            )
            (root / "123.jpg").write_bytes(b"image")
            events = error_events(root.parent.parent)
            self.assertEqual(events[0]["screenshots"], ["errors/123/123.jpg"])

    def test_export_includes_window_logs_and_archived_screenshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            shots = root / "screenshot"
            logs.mkdir()
            center = datetime.now().replace(microsecond=0)
            archive_id = str(int(center.timestamp() * 10**9))
            archive = shots / "errors" / archive_id
            archive.mkdir(parents=True)
            (archive / "event.json").write_text(
                json.dumps({"time_ns": int(archive_id), "message": "运行失败"}),
                encoding="utf-8",
            )
            before = center - timedelta(minutes=4)
            after = center + timedelta(minutes=4)
            outside = center + timedelta(minutes=6)
            for when in (before, after, outside):
                (archive / f"{int(when.timestamp() * 10**9)}.jpg").write_bytes(
                    f"picture-{when.minute}".encode()
                )
            (logs / "runtime.log").write_text(
                "".join(
                    f"{when:%Y-%m-%d %H:%M:%S} task.py:1 INFO {label}\n"
                    for when, label in (
                        (before, "之前"),
                        (after, "之后"),
                        (outside, "窗口外"),
                    )
                ),
                encoding="utf-8",
            )
            archived_rows = [
                {
                    "time": f"{center:%Y-%m-%d %H:%M:%S}",
                    "message": "已保存日志",
                    "screenshot": None,
                }
            ]
            (archive / "logs.json").write_text(
                json.dumps(archived_rows, ensure_ascii=False), encoding="utf-8"
            )

            for selected_id, expected_log in (
                (None, "之前"),
                (archive_id, "已保存日志"),
            ):
                with self.subTest(selected_id=selected_id):
                    with export_bundle(logs, shots, center, selected_id) as data:
                        with ZipFile(data) as bundle:
                            names = bundle.namelist()
                            self.assertEqual(
                                len(
                                    [name for name in names if name.startswith("截图/")]
                                ),
                                2,
                            )
                            self.assertIn(
                                f"截图/errors/{archive_id}/{int(before.timestamp() * 10**9)}.jpg",
                                names,
                            )
                            self.assertNotIn(
                                f"截图/errors/{archive_id}/{int(outside.timestamp() * 10**9)}.jpg",
                                names,
                            )
                            exported_log = bundle.read("日志.txt").decode("utf-8")
                            self.assertIn(expected_log, exported_log)
                            self.assertNotIn("窗口外", exported_log)
