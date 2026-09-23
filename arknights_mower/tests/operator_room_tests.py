import unittest

import cv2

from arknights_mower.solvers.base_mixin import (
    OP_ROOM,
    OP_ROOM_WIDTH,
    BaseMixin,
    _foreground_width,
    _resolve_operator_room_prefix,
)


class TestOperatorRoomRecognition(unittest.TestCase):
    def test_prefix_operator_uses_long_name_when_extra_text_is_visible(self):
        result = _resolve_operator_room_prefix(
            "凯尔希",
            0.57,
            {"凯尔希": 0.57, "凯尔希·思衡托": 0.54},
            sample_width=237,
            template_widths={"凯尔希": 106, "凯尔希·思衡托": 254},
        )

        self.assertEqual(result, "凯尔希·思衡托")

    def test_prefix_operator_keeps_short_name_without_extra_text(self):
        result = _resolve_operator_room_prefix(
            "凯尔希",
            1.0,
            {"凯尔希": 1.0, "凯尔希·思衡托": 0.64},
            sample_width=106,
            template_widths={"凯尔希": 106, "凯尔希·思衡托": 254},
        )

        self.assertEqual(result, "凯尔希")

    def test_current_templates_keep_old_and_new_kaltsit_distinct(self):
        solver = BaseMixin()
        self.assertEqual(solver.read_operator_in_room(OP_ROOM["凯尔希"]), "凯尔希")
        self.assertEqual(
            solver.read_operator_in_room(OP_ROOM["凯尔希·思衡托"]), "凯尔希·思衡托"
        )

        old_score = cv2.minMaxLoc(
            cv2.matchTemplate(OP_ROOM["凯尔希"], OP_ROOM["凯尔希"], cv2.TM_CCORR_NORMED)
        )[1]
        new_score = cv2.minMaxLoc(
            cv2.matchTemplate(
                OP_ROOM["凯尔希"], OP_ROOM["凯尔希·思衡托"], cv2.TM_CCORR_NORMED
            )
        )[1]
        self.assertEqual(
            _resolve_operator_room_prefix(
                "凯尔希",
                old_score,
                {"凯尔希": old_score, "凯尔希·思衡托": new_score},
                _foreground_width(OP_ROOM["凯尔希"]),
                OP_ROOM_WIDTH,
            ),
            "凯尔希",
        )

    def test_empty_or_narrow_image_returns_empty_string(self):
        import numpy as np

        solver = BaseMixin()
        # Pure black image
        black = np.zeros((58, 344), dtype=np.uint8)
        self.assertEqual(solver.read_operator_in_room(black), "")

        # Extremely narrow noise (width < 20px)
        narrow = np.zeros((58, 344), dtype=np.uint8)
        narrow[10:30, 10:25] = 255
        self.assertEqual(solver.read_operator_in_room(narrow), "")

    def test_low_confidence_noise_rejected(self):
        import numpy as np

        solver = BaseMixin()
        # Random noise strokes that do not form any real operator
        noise = np.zeros((58, 344), dtype=np.uint8)
        noise[10:15, 20:60] = 255
        noise[30:35, 40:80] = 255
        self.assertEqual(solver.read_operator_in_room(noise), "")

    def test_get_agent_from_room_retries_inplace_on_empty_read(self):
        from unittest.mock import MagicMock, patch

        from arknights_mower.solvers.base_schedule import BaseSchedulerSolver

        solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        solver.leifeng_mode = False
        solver.task = None
        solver.tasks = []
        solver.op_data = MagicMock()
        solver.op_data.plan = {"room_1": [MagicMock()]}
        silverash = MagicMock()
        silverash.need_to_refresh.return_value = False
        silverash.current_mood.return_value = 24
        silverash.mood = 24
        silverash.depletion_rate = 0
        solver.op_data.operators = {"银灰": silverash}
        solver.op_data.update_detail.return_value = None
        solver.recog = MagicMock()
        solver.recog.gray = None
        solver.recog.update = MagicMock()
        solver.sleep = MagicMock()
        solver.find = MagicMock(return_value=None)
        solver.refresh_facility_state = MagicMock()
        solver.turn_on_room_detail = MagicMock()
        solver.detect_product_complete = MagicMock(return_value=False)
        solver.scroll_room_operators = MagicMock()

        # First call returns "" (low confidence), second returns "银灰"
        solver.read_screen = MagicMock(side_effect=["", "银灰"])
        solver.read_accurate_mood = MagicMock(return_value=24)

        with patch("arknights_mower.solvers.base_schedule.cropimg", return_value=None):
            result = solver.get_agent_from_room("room_1")

        self.assertEqual(result[0]["agent"], "银灰")
        self.assertEqual(solver.read_screen.call_count, 2)
        solver.sleep.assert_called_with(0.25)
        solver.recog.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
