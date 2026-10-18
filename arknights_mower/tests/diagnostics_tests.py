"""验证按时间回看日志和截图。"""

import json
import logging
import sys
import tempfile
import tracemalloc
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from arknights_mower.utils.diagnostics import (
    archive_window,
    error_events,
    export_bundle,
    timeline,
)


class DiagnosticTimelineTests(unittest.TestCase):
    def test_positive_limit_bounds_memory_while_reading_large_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            center = datetime(2026, 10, 18, 12, 30)
            path = root / "runtime.log"
            with path.open("w", encoding="utf-8") as stream:
                for number in range(6000):
                    stream.write(
                        f"2026-10-18 12:30:00 task.py:1 DEBUG {number}: "
                        + "x" * 1024
                        + "\n"
                    )
            tracemalloc.start()
            try:
                rows = timeline(root, root, center, limit=3, images=[])
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(
                [row["message"].split(": ", 1)[0] for row in rows],
                [
                    f"2026-10-18 12:30:00 task.py:1 DEBUG {number}"
                    for number in (5997, 5998, 5999)
                ],
            )
            self.assertLess(peak, 1024**2)

    def test_limits_keep_multiline_hour_order_and_legacy_slices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            center = datetime(2026, 3, 1)
            (root / "runtime.log.2026-02-28_23").write_text(
                "2026-02-28 23:59:58 task.py:1 INFO first\n"
                "  first detail\n"
                "2026-02-28 23:59:59 task.py:2 INFO second\n",
                encoding="utf-8",
            )
            (root / "runtime.log").write_text(
                "orphan detail\n"
                "2026-03-01 00:00:00 task.py:3 INFO third\n"
                "  third detail\n"
                "2026-03-01 00:00:01 task.py:4 INFO fourth\n"
                "  fourth detail\n",
                encoding="utf-8",
            )
            expected = [
                "2026-02-28 23:59:58 task.py:1 INFO first\n  first detail",
                "2026-02-28 23:59:59 task.py:2 INFO second",
                "2026-03-01 00:00:00 task.py:3 INFO third\n  third detail",
                "2026-03-01 00:00:01 task.py:4 INFO fourth\n  fourth detail",
            ]
            for limit, retained in (
                (1, expected[-1:]),
                (2, expected[-2:]),
                (1001, expected),
                (None, expected),
                (0, expected),
                (-2, expected[2:]),
            ):
                with self.subTest(limit=limit):
                    rows = timeline(root, root, center, limit=limit, images=[])
                    self.assertIsInstance(rows, list)
                    self.assertEqual([row["message"] for row in rows], retained)

    def test_invalid_dates_and_outside_window_details_are_not_attached(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            center = datetime(2024, 2, 29, 12)
            first = "2024-02-29 12:00:00,123 task.py:1 CRITICAL valid leap day"
            second = "2024-02-29 12:00:01 task.py:2 INFO next"
            (root / "runtime.log").write_text(
                first + "\n  retained detail\n"
                "2023-02-29 12:00:00 task.py:2 ERROR invalid day\n"
                "  invalid day detail\n"
                "0000-02-29 12:00:00 task.py:2 ERROR invalid year\n"
                "2024-02-29 24:00:00 task.py:2 ERROR invalid hour\n"
                "2024-02-29 12:06:00 task.py:2 ERROR outside\n"
                "  outside detail\n" + second + "\n",
                encoding="utf-8",
            )
            rows = timeline(root, root, center, images=[])
            self.assertEqual(
                [row["message"] for row in rows],
                [first + "\n  retained detail", second],
            )

    def test_missing_log_folder_returns_list_for_each_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            for limit in (None, 3, 0, -2):
                with self.subTest(limit=limit):
                    self.assertEqual(
                        timeline(missing, missing, datetime.now(), limit=limit), []
                    )

    def test_formatted_multiline_logs_preserve_newlines_and_exception_details(self):
        from arknights_mower.utils import log

        center = datetime(2026, 10, 9, 14, 15, 43)
        try:
            try:
                raise ValueError("inner failure")
            except ValueError as error:
                raise RuntimeError("outer failure") from error
        except RuntimeError:
            exception = sys.exc_info()

        messages = []
        for level, message, exc_info in (
            (logging.DEBUG, "sending operation\n  payload\n\n  end", None),
            (logging.ERROR, "dispatch failed", exception),
            (logging.INFO, "ordinary message", None),
        ):
            record = logging.LogRecord(
                log.logger.name,
                level,
                r"C:\Program Files\Mower\arknights_mower\utils\device\device.py",
                661,
                message,
                (),
                exc_info,
                "dispatch",
            )
            record.created = center.timestamp() + 0.152
            record.msecs = 152
            log.filter.filter(record)
            messages.append(log.basic_formatter.format(record))

        for newline in ("\n", "\r\n"):
            with (
                self.subTest(newline=newline),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                logs = root / "log"
                logs.mkdir()
                (logs / "runtime.log").write_text(
                    ("\n".join(messages) + "\n").replace("\n", newline),
                    encoding="utf-8",
                    newline="",
                )

                rows = timeline(logs, root / "screenshot", center)

                self.assertEqual([row["message"] for row in rows], messages)
                self.assertEqual(
                    [row["time"] for row in rows], ["2026-10-09 14:15:43"] * 3
                )

    def test_ordinary_window_lists_unlinked_frames_and_reports_log_truncation(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            logs.mkdir()
            center = datetime(2026, 9, 26, 12, 58)
            shots = root / "screenshot" / "20260926-12"
            shots.mkdir(parents=True)
            image = (
                shots
                / f"{int((center + timedelta(seconds=60)).timestamp() * 10**9)}.jpg"
            )
            image.write_bytes(b"image")
            (logs / "runtime.log").write_text(
                "2026-09-26 12:58:00,123 task.py:1 INFO run: retained\n" * 1001,
                encoding="utf-8",
            )
            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                client = server.app.test_client()
                response = client.get(
                    f"/diagnostics/timeline?at={int(center.timestamp() * 1000)}",
                    headers={"token": "diagnostics-test"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["logs"]), 1000)
            self.assertTrue(response.json["truncated"])
            self.assertTrue(
                all(row["screenshot"] is None for row in response.json["logs"])
            )
            self.assertEqual(
                response.json["screenshots"],
                [image.relative_to(root / "screenshot").as_posix()],
            )

    def test_multiline_records_do_not_cross_window_or_file_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            logs.mkdir()
            center = datetime(2026, 9, 26, 12, 58)
            (logs / "runtime.log.2026-09-26_12").write_text(
                "2026-09-26 12:58:00,123 task.py:1 ERROR run: failure\n"
                "Traceback\n  ValueError: retained\n"
                "2026-09-26 13:04:00,123 task.py:1 ERROR run: outside\n"
                "  outside detail\n",
                encoding="utf-8",
            )
            (logs / "runtime.log").write_text(
                "orphan detail\n2026-09-26 12:59:00,123 task.py:1 INFO run: next\n",
                encoding="utf-8",
            )
            rows = timeline(logs, root / "screenshot", center)
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                rows[0]["message"],
                "2026-09-26 12:58:00,123 task.py:1 ERROR run: failure\n"
                "Traceback\n  ValueError: retained",
            )
            self.assertNotIn("detail", rows[0]["message"])

    def test_merged_archive_export_uses_first_to_last_error_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            shots = root / "screenshot"
            logs.mkdir()
            first = datetime(2026, 9, 26, 12, 58)
            last = first + timedelta(hours=1, minutes=9)
            archive_id = str(int(first.timestamp() * 10**9))
            archive = shots / "errors" / archive_id
            archive.mkdir(parents=True)
            (archive / "event.json").write_text(
                json.dumps(
                    {
                        "time_ns": int(archive_id),
                        "last_error_ns": int(last.timestamp() * 10**9),
                        "error_count": 3,
                        "message": "首次失败",
                    }
                ),
                encoding="utf-8",
            )
            (logs / "runtime.log.2026-09-26_12").write_text(
                "2026-09-26 12:58:00 task.py:1 ERROR 首次失败\n",
                encoding="utf-8",
            )
            (logs / "runtime.log").write_text(
                "2026-09-26 14:07:00 task.py:2 ERROR 再次失败\n",
                encoding="utf-8",
            )
            start, end = archive_window(archive, first)
            self.assertEqual(start, first - timedelta(minutes=5))
            self.assertEqual(end, last + timedelta(minutes=5))
            with export_bundle(logs, shots, first, archive_id) as data:
                with ZipFile(data) as bundle:
                    text = bundle.read("日志.txt").decode("utf-8")
                    self.assertIn("首次失败", text)
                    self.assertIn("再次失败", text)
                    self.assertIn("14:12:00", bundle.read("说明.txt").decode("utf-8"))

            import server

            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                response = server.app.test_client().get(
                    f"/diagnostics/errors/{archive_id}/logs",
                    headers={"token": "diagnostics-test"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["logs"]), 2)

    def test_active_archive_detail_includes_more_than_1000_logs(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            logs.mkdir()
            center = datetime(2026, 9, 26, 12, 58)
            archive_id = str(int(center.timestamp() * 10**9))
            archive = root / "screenshot" / "errors" / archive_id
            archive.mkdir(parents=True)
            (archive / "event.json").write_text(
                json.dumps({"time_ns": int(archive_id), "message": "首次失败"}),
                encoding="utf-8",
            )
            (logs / "runtime.log").write_text(
                "2026-09-26 12:58:00 task.py:1 ERROR 首次失败\n"
                + "2026-09-26 12:58:01 task.py:2 INFO 后续日志\n" * 1000,
                encoding="utf-8",
            )
            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                response = server.app.test_client().get(
                    f"/diagnostics/errors/{archive_id}/logs",
                    headers={"token": "diagnostics-test"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json["logs"]), 1001)
            self.assertIn("首次失败", response.json["logs"][0]["message"])

    def test_delete_route_removes_only_requested_archive(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_root = root / "screenshot" / "errors"
            for archive_id in ("123", "456", "789"):
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
                for origin, base_url in (
                    ("http://localhost:5174", "http://localhost:8000"),
                    ("https://localhost:5173", "http://localhost:8000"),
                    ("http://localhost:5173.evil.example", "http://localhost:8000"),
                    ("http://localhost:5173", "http://example.org:8000"),
                ):
                    self.assertEqual(
                        client.delete(
                            "/diagnostics/errors/123",
                            headers={**headers, "Origin": origin},
                            base_url=base_url,
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
                self.assertEqual(
                    client.delete(
                        "/diagnostics/errors/789",
                        headers={**headers, "Origin": "http://localhost:5173"},
                        base_url="http://localhost:8000",
                    ).status_code,
                    204,
                )
                self.assertFalse((archive_root / "123").exists())
                self.assertFalse((archive_root / "789").exists())
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
                    self.assertNotIn("日志.json", bundle.namelist())
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
