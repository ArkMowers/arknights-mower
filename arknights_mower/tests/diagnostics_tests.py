"""验证按时间回看日志和截图。"""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from arknights_mower.utils.diagnostics import error_events, timeline


class DiagnosticTimelineTests(unittest.TestCase):
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
