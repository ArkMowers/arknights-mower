import unittest
from pathlib import Path

import cv2
import numpy as np

from arknights_mower.solvers.base_mixin import (
    OP_ROOM,
    OP_ROOM_WIDTH,
    PREFIX_NAME_SCORE_RATIO,
    BaseMixin,
    _foreground_width,
    _resolve_operator_room_prefix,
    _room_name_candidates,
)
from arknights_mower.utils.image import loadimg, rgb2gray


def locked_honeyberry():
    # B304 上端原图的第二床姓名框，坐标从 (1460, 369) 到 (1785, 424)。
    path = (
        Path(__file__).parent / "fixtures/selection/room_honeyberry_lock_20261126.png"
    )
    return rgb2gray(loadimg(str(path)))


class TestOperatorRoomRecognition(unittest.TestCase):
    def test_binary_search_keeps_all_possible_name_and_prefix_matches(self):
        for name, y, x in [("Lancet-2", 0, 4), ("凯尔希·思衡托", 3, 0), ("夜刀", 4, 2)]:
            with self.subTest(name=name):
                template = OP_ROOM[name]
                height, width = template.shape
                sample = np.zeros((height + 4, width + 4), np.uint8)
                sample[y : y + height, x : x + width] = template
                sample[5:8, 1:12] = 255
                scores = {
                    operator: cv2.minMaxLoc(
                        cv2.matchTemplate(sample, other, cv2.TM_CCORR_NORMED)
                    )[1]
                    for operator, other in OP_ROOM.items()
                }
                cutoff = max(scores.values()) * PREFIX_NAME_SCORE_RATIO
                candidates = set(_room_name_candidates(sample))
                self.assertTrue(
                    {op for op, score in scores.items() if score >= cutoff}
                    <= candidates
                )
                self.assertLess(len(candidates), len(OP_ROOM))

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

    def test_recorded_honeyberry_with_and_without_resident_lock(self):
        name = locked_honeyberry()
        solver = BaseMixin()
        self.assertEqual(solver.read_screen(name[:, :90], type="name"), "蜜莓")
        self.assertEqual(solver.read_screen(name[:, 90:], type="name"), "")
        self.assertEqual(solver.read_screen(name, type="name"), "蜜莓")

    def test_unrecognized_symbol_on_resident_badge_keeps_name_unknown(self):
        name = locked_honeyberry()
        name[15:38, 98:119] = 255
        self.assertEqual(BaseMixin().read_screen(name, type="name"), "")

    def test_resident_lock_preserves_similar_names_and_separate_glyphs(self):
        source = locked_honeyberry()
        lock = source[:, 90:127]
        solver = BaseMixin()
        for name in ("W", "蜜蜡", "波卜", "凯尔希", "凯尔希·思衡托"):
            with self.subTest(name=name):
                sample = np.zeros_like(source)
                template = OP_ROOM[name]
                h, w = template.shape
                sample[6 : 6 + h, 8 : 8 + w] = template
                self.assertEqual(solver.read_screen(sample, type="name"), name)
                x, _, width, _ = cv2.boundingRect(sample)
                left = x + width + 9
                sample[:, left : left + lock.shape[1]] = lock
                self.assertEqual(solver.read_screen(sample, type="name"), name)

    def test_read_screen_uses_entire_pre_cropped_room_name(self):
        sample = np.zeros((55, 325), dtype=np.uint8)
        template = OP_ROOM["凯尔希·思衡托"]
        sample[4 : 4 + template.shape[0], 4 : 4 + template.shape[1]] = template

        self.assertEqual(BaseMixin().read_screen(sample, type="name"), "凯尔希·思衡托")

    def test_get_agent_from_room_retries_inplace_on_empty_read(self):
        from unittest.mock import MagicMock

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
        gray = np.arange(1080 * 1920, dtype=np.uint8).reshape(1080, 1920)
        solver.recog.gray = gray
        solver.recog.update = MagicMock()
        solver.sleep = MagicMock(side_effect=lambda _: solver.recog.update())
        solver.find = MagicMock(return_value=None)
        solver.refresh_facility_state = MagicMock()
        solver.turn_on_room_detail = MagicMock()
        solver.detect_product_complete = MagicMock(return_value=False)
        solver.scroll_room_operators = MagicMock()

        # First call returns "" (low confidence), second returns "银灰"
        solver.read_screen = MagicMock(side_effect=["", "银灰"])
        solver.read_accurate_mood = MagicMock(return_value=24)

        result = solver.get_agent_from_room("room_1")

        self.assertEqual(result[0]["agent"], "银灰")
        self.assertEqual(solver.read_screen.call_count, 2)
        np.testing.assert_array_equal(
            solver.read_screen.call_args_list[0][0][0], gray[160:215, 1460:1785]
        )
        solver.find.assert_any_call(
            "infra_no_operator", scope=((1288, 135), (1869, 326))
        )
        solver.sleep.assert_called_with(0.25)
        solver.recog.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
