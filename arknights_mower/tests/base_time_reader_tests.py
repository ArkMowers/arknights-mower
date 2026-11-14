import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, create_autospec, patch

import numpy as np

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils import recognize
from arknights_mower.utils.digit_reader import DigitReader
from arknights_mower.utils.recognize import Recognizer


class BaseTimeReaderTests(unittest.TestCase):
    def solver(self):
        solver = BaseMixin()
        solver.recog = MagicMock()
        solver.recog.gray = np.zeros((720, 1280), dtype=np.uint8)
        solver.digit_reader = create_autospec(DigitReader, instance=True)
        solver.read_screen = MagicMock(return_value="00:00:45")
        return solver

    def test_digit_reader_is_used_instead_of_general_ocr(self):
        solver = self.solver()
        solver.digit_reader.get_time.return_value = "00:02:22"
        before = datetime.now()
        result = solver.double_read_time(((1, 2), (3, 4)), use_digit_reader=True)
        self.assertAlmostEqual((result - before).total_seconds(), 142, delta=1)
        solver.digit_reader.get_time.assert_called_once_with(
            solver.recog.gray, 720, 1280
        )
        solver.read_screen.assert_not_called()

    def test_retry_keeps_digit_reader_and_starts_with_zero_errors(self):
        solver = self.solver()
        solver.digit_reader.get_time.side_effect = ["invalid"] * 4 + ["00:00:12"]
        before = datetime.now()
        result = solver.double_read_time(None, use_digit_reader=True)
        self.assertAlmostEqual((result - before).total_seconds(), 12, delta=1)
        self.assertEqual(solver.digit_reader.get_time.call_count, 5)
        solver.read_screen.assert_not_called()

    def test_default_reader_remains_general_ocr(self):
        solver = self.solver()
        before = datetime.now()
        result = solver.double_read_time(None)
        self.assertAlmostEqual((result - before).total_seconds(), 45, delta=1)
        solver.digit_reader.get_time.assert_not_called()

    def test_unreadable_time_preserves_fallback_without_inventing_countdown(self):
        solver = self.solver()
        solver.digit_reader.get_time.return_value = "invalid"
        before = datetime.now()
        with patch("arknights_mower.solvers.base_mixin.logger.warning") as warning:
            result = solver.double_read_time(None, use_digit_reader=True)
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, datetime.now())
        self.assertEqual(solver.digit_reader.get_time.call_count, 5)
        warning.assert_called_once_with(
            "贸易站订单倒计时识别失败，回退为当前时间；不能据此确认实际订单完成时间"
        )

    def test_slow_capture_and_recognition_do_not_extend_order_deadline(self):
        class Clock(datetime):
            @classmethod
            def now(cls):
                return cls.current

        Clock.current = Clock(2026, 10, 15, 9, 20)
        solver = self.solver()
        device = MagicMock()
        solver.recog = Recognizer(device)
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        def capture():
            Clock.current += timedelta(seconds=2)
            return None, frame, frame[:, :, 0]

        def read(*_args):
            Clock.current += timedelta(seconds=3)
            return "00:02:01"

        device.screencap.side_effect = capture
        solver.digit_reader.get_time.side_effect = read
        with (
            patch.object(base_mixin, "datetime", Clock),
            patch.object(recognize, "datetime", Clock),
        ):
            deadline = solver.double_read_time(None, use_digit_reader=True)

        self.assertEqual(deadline, datetime(2026, 10, 15, 9, 22, 1))
        self.assertEqual(Clock.current, datetime(2026, 10, 15, 9, 20, 5))
        solver.recog.clear()
        self.assertIsNone(solver.recog.capture_started_at)
