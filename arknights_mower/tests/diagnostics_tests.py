"""验证按时间回看日志和截图。"""

import json
import logging
import sys
import tempfile
import tracemalloc
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from arknights_mower.utils.diagnostics import (
    archive_window,
    error_events,
    export_bundle,
    timeline,
)


class DiagnosticTimelineTests(unittest.TestCase):
    def test_recent_limit_does_not_read_the_entire_hour(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "runtime.log"
            prefix = "2026-10-18 12:30:00 task.py:1 DEBUG "
            with path.open("w", encoding="utf-8") as stream:
                for number in range(50000):
                    stream.write(f"{prefix}{number}: " + "x" * 100 + "\n")
            opened = Path.open
            bytes_read = 0

            class Reader:
                def __init__(self, stream):
                    self.stream = stream

                def seek(self, *args):
                    return self.stream.seek(*args)

                def read(self, *args):
                    nonlocal bytes_read
                    data = self.stream.read(*args)
                    bytes_read += len(data)
                    return data

                def __iter__(self):
                    nonlocal bytes_read
                    for line in self.stream:
                        bytes_read += len(line.encode("utf-8"))
                        yield line

            @contextmanager
            def track(file, *args, **kwargs):
                with opened(file, *args, **kwargs) as stream:
                    yield Reader(stream) if file == path else stream

            with patch.object(Path, "open", track):
                rows = timeline(
                    root, root, datetime(2026, 10, 18, 12, 30), 2, images=[]
                )
            self.assertEqual(
                [row["message"] for row in rows],
                [f"{prefix}{i}: " + "x" * 100 for i in (49998, 49999)],
            )
            self.assertLess(bytes_read, 256 * 1024)

    def test_recent_records_preserve_unicode_newlines_and_long_details(self):
        center = datetime(2026, 10, 18, 12, 30)
        header = "2026-10-18 12:30:00 task.py:1 ERROR 中文"
        details = [str(i) + "界" * 2000 for i in range(40)]
        long_header = "2026-10-18 12:30:01 task.py:1 INFO " + "中" * 30000
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for ending in ("\n", "\r\n", "\r"):
                for final_newline in ("", ending):
                    with self.subTest(ending=repr(ending), final=bool(final_newline)):
                        (root / "runtime.log").write_bytes(
                            (
                                ending.join([header, *details, long_header])
                                + final_newline
                            ).encode("utf-8")
                        )
                        rows = timeline(root, root, center, limit=2, images=[])
                        self.assertEqual(
                            [row["message"] for row in rows],
                            ["\n".join([header, *details[:4]]), long_header],
                        )

    def test_recent_records_keep_file_order_when_timestamps_move_backwards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime.log").write_text(
                "2026-10-18 12:31:00 task.py:1 INFO first\n"
                "2026-10-18 12:30:00 task.py:2 INFO second\n"
                "2026-10-18 10:00:00 task.py:3 INFO outside\n"
                "  outside detail\n"
                "2026-10-18 12:29:00 task.py:4 INFO last\n"
                "  last detail",
                encoding="utf-8",
            )
            rows = timeline(root, root, datetime(2026, 10, 18, 12, 30), 2, images=[])
            self.assertEqual(
                [row["message"] for row in rows],
                [
                    "2026-10-18 12:30:00 task.py:2 INFO second",
                    "2026-10-18 12:29:00 task.py:4 INFO last\n  last detail",
                ],
            )

    def test_export_custom_range_reads_rotated_logs_and_archived_frames(self):
        import server

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            shots = root / "screenshot"
            logs.mkdir()
            center = datetime(2026, 10, 20, 14, 30)
            start = center - timedelta(hours=6)
            end = center + timedelta(minutes=5)
            detail = "  完整错误详情\n" * 1200
            (logs / "runtime.log.2026-10-20_08").write_text(
                "2026-10-20 08:29:59 task.py:1 INFO 范围外\n"
                "2026-10-20 08:30:00 task.py:1 ERROR 开始\n" + detail,
                encoding="utf-8",
            )
            (logs / "runtime.log").write_text(
                "2026-10-20 14:00:00 task.py:1 INFO 中间\n"
                * 1100
                + "2026-10-20 14:35:00 task.py:1 INFO 结束\n"
                "2026-10-20 14:35:01 task.py:1 INFO 范围外\n",
                encoding="utf-8",
            )
            archive = shots / "errors" / str(int(start.timestamp() * 10**9))
            archive.mkdir(parents=True)
            image = archive / f"{int(start.timestamp() * 10**9)}.jpg"
            image.write_bytes(b"archived image")
            (archive / "logs.json").write_text("[]", encoding="utf-8")
            with (
                patch.object(
                    server, "get_path", side_effect=lambda name: root / name[5:]
                ),
                patch.object(server.app, "token", "diagnostics-test", create=True),
            ):
                for screenshots in ("0", "1"):
                    with self.subTest(screenshots=screenshots):
                        response = server.app.test_client().get(
                            "/diagnostics/export",
                            query_string={
                                "at": int(center.timestamp() * 1000),
                                "start": int(start.timestamp() * 1000),
                                "end": int(end.timestamp() * 1000),
                                "screenshots": screenshots,
                            },
                            headers={"token": "diagnostics-test"},
                        )
                        self.assertEqual(response.status_code, 200)
                        with ZipFile(BytesIO(response.data)) as bundle:
                            text = bundle.read("日志.txt").decode("utf-8")
                            self.assertIn("开始\n" + detail, text)
                            self.assertEqual(text.count("中间"), 1100)
                            self.assertIn("结束", text)
                            self.assertNotIn("范围外", text)
                            manifest = bundle.read("说明.txt").decode("utf-8")
                            self.assertIn("08:30:00 至 2026-10-20 14:35:00", manifest)
                            self.assertIn("日志：1102 条", manifest)
                            self.assertEqual(
                                f"截图/{image.relative_to(shots).as_posix()}"
                                in bundle.namelist(),
                                screenshots == "1",
                            )
                        response.close()

    def test_export_range_validation_precedes_file_access(self):
        import server

        center = int(datetime.now().timestamp() * 1000)
        invalid = (
            {"start": center},
            {"end": center},
            {"start": "invalid", "end": center},
            {"start": -1, "end": center},
            {"start": center, "end": center},
            {"start": center, "end": center - 1},
            {"start": center - 8 * 86400000, "end": center},
            {"start": center, "end": center + 7200000},
            {"screenshots": "invalid"},
        )
        with (
            patch.object(server.app, "token", "diagnostics-test", create=True),
            patch.object(server, "get_path") as get_path,
            patch.object(server, "export_bundle") as export,
        ):
            for params in invalid:
                with self.subTest(params=params):
                    response = server.app.test_client().get(
                        "/diagnostics/export",
                        query_string={"at": center, **params},
                        headers={"token": "diagnostics-test"},
                    )
                    self.assertEqual(response.status_code, 400)
            get_path.assert_not_called()
            export.assert_not_called()

    def test_long_export_streams_log_text_with_bounded_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "log"
            logs.mkdir()
            center = datetime(2026, 10, 20, 12)
            with (logs / "runtime.log").open("w", encoding="utf-8") as stream:
                for number in range(10000):
                    stream.write(
                        f"2026-10-20 12:00:00 task.py:1 DEBUG {number}: "
                        + "x" * 1024
                        + "\n"
                    )
            tracemalloc.start()
            try:
                with export_bundle(
                    logs, root / "screenshot", center, include_screenshots=False
                ) as data:
                    _, peak = tracemalloc.get_traced_memory()
                    self.assertLess(peak, 4 * 1024**2)
                    with ZipFile(data) as bundle:
                        self.assertIn(
                            "日志：10000 条", bundle.read("说明.txt").decode("utf-8")
                        )
            finally:
                tracemalloc.stop()

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


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("screenshots", [None, "0", "1"])
def test_export_contents_include_current_plan(
    tmp_path, monkeypatch, archived, screenshots
):
    import server
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.utils.config.plan import PlanModel

    center = datetime.now().replace(microsecond=0)
    timestamp = int(center.timestamp() * 10**9)
    shots = tmp_path / "screenshot"
    ordinary = shots / center.strftime("%Y%m%d-%H")
    archive = shots / "errors" / str(timestamp)
    logs = tmp_path / "log"
    for folder in (ordinary, archive, logs):
        folder.mkdir(parents=True)
    (ordinary / f"{timestamp}.jpg").write_bytes(b"ordinary")
    (archive / f"{timestamp + 1}.jpg").write_bytes(b"archived")
    (archive / "event.json").write_text(
        json.dumps({"time_ns": timestamp}), encoding="utf-8"
    )
    saved_message = "归档的完整日志\n  异常详情"
    (archive / "logs.json").write_text(
        json.dumps([{"message": saved_message}], ensure_ascii=False), encoding="utf-8"
    )
    message = f"{center:%Y-%m-%d %H:%M:%S} task.py:1 INFO 当前日志\n  更多说明"
    (logs / "runtime.log").write_text(message + "\n", encoding="utf-8")
    plan = PlanModel.model_validate(
        {"conf": {"exhaust_require": "能天使"}, "backup_plans": [{"name": "测试副表"}]}
    )
    conf = Conf()
    conf.resting_threshold = 0.6
    conf.webview.token = "private-token"
    monkeypatch.setattr(server.config, "plan", plan)
    monkeypatch.setattr(server.config, "conf", conf)
    monkeypatch.setattr(server, "get_path", lambda name: tmp_path / name[5:])
    monkeypatch.setattr(server.app, "token", "diagnostics-test", raising=False)
    headers = {"token": "diagnostics-test"}
    client = server.app.test_client()
    path = (
        f"/diagnostics/errors/{timestamp}/export?"
        if archived
        else f"/diagnostics/export?at={int(center.timestamp() * 1000)}&"
    )
    if screenshots is not None:
        path += f"screenshots={screenshots}"
    with client.get(path, headers=headers) as response:
        assert response.status_code == 200
        with ZipFile(BytesIO(response.data)) as bundle:
            assert (
                bundle.read("日志.txt").decode()
                == (saved_message if archived else message) + "\n"
            )
            exported_plan = json.loads(bundle.read("plan.json"))
            assert exported_plan == client.get("/export-json", headers=headers).json
            assert exported_plan["conf"]["exhaust_require"] == "能天使"
            assert exported_plan["backup_plans"][0]["name"] == "测试副表"
            assert exported_plan["advanced_settings"]["resting_threshold"] == 0.6
            assert "private-token" not in bundle.read("plan.json").decode()
            images = [name for name in bundle.namelist() if name.startswith("截图/")]
            assert len(images) == (0 if screenshots == "0" else (1 if archived else 2))
            assert "当前保存" in bundle.read("说明.txt").decode()


def test_text_export_skips_screenshot_enumeration(tmp_path):
    with patch(
        "arknights_mower.utils.diagnostics.screenshots_between",
        side_effect=AssertionError("不应扫描截图"),
    ):
        with export_bundle(
            tmp_path / "log",
            tmp_path / "screenshot",
            datetime.now(),
            include_screenshots=False,
        ) as data:
            with ZipFile(data) as bundle:
                assert bundle.read("日志.txt") == b""
