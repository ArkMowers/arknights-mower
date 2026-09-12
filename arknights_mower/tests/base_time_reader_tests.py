import unittest
from datetime import datetime
from unittest.mock import MagicMock, create_autospec

import numpy as np

from arknights_mower.solvers.base_mixin import BaseMixin
from arknights_mower.utils.digit_reader import DigitReader


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
        result = solver.double_read_time(None, use_digit_reader=True)
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, datetime.now())
        self.assertEqual(solver.digit_reader.get_time.call_count, 5)
