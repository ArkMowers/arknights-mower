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


if __name__ == "__main__":
    unittest.main()
