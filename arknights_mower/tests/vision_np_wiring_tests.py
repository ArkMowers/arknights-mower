import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from arknights_mower.solvers.auto_fight import AutoFight
from arknights_mower.solvers.credit_fight import CreditFight
from arknights_mower.utils.recognize import Recognizer


class TestFightVisionNpWiring(unittest.TestCase):
    def test_auto_fight_extrema_keep_order_50(self):
        solver = AutoFight.__new__(AutoFight)
        solver.recog = SimpleNamespace(
            gray=np.zeros((1080, 1920), dtype=np.uint8),
            img=np.zeros((1080, 1920, 3), dtype=np.uint8),
            update=lambda: None,
        )
        match_scores = np.zeros((1, 100), dtype=np.float32)

        with (
            patch(
                "arknights_mower.solvers.auto_fight.cropimg",
                return_value=np.zeros((18, 1920), dtype=np.uint8),
            ),
            patch(
                "arknights_mower.solvers.auto_fight.loadres",
                return_value=np.zeros((4, 4), dtype=np.uint8),
            ),
            patch(
                "arknights_mower.solvers.auto_fight.cv2.matchTemplate",
                return_value=match_scores,
            ),
            patch(
                "arknights_mower.solvers.auto_fight.vision_np.argrelmax",
                return_value=np.asarray([], dtype=int),
            ) as extrema,
        ):
            solver.update_operators()

        np.testing.assert_array_equal(extrema.call_args.args[0], match_scores[0])
        self.assertEqual(extrema.call_args.kwargs, {"order": 50})

    def test_credit_fight_extrema_keep_order_100(self):
        solver = CreditFight.__new__(CreditFight)
        solver.recog = SimpleNamespace(gray=np.zeros((1080, 1920), dtype=np.uint8))
        match_scores = np.zeros((1, 100), dtype=np.float32)

        with (
            patch(
                "arknights_mower.solvers.credit_fight.cropimg",
                return_value=np.zeros((75, 1839), dtype=np.uint8),
            ),
            patch(
                "arknights_mower.solvers.credit_fight.loadres",
                return_value=np.zeros((4, 4), dtype=np.uint8),
            ),
            patch(
                "arknights_mower.solvers.credit_fight.cv2.matchTemplate",
                return_value=match_scores,
            ),
            patch(
                "arknights_mower.solvers.credit_fight.vision_np.argrelmin",
                return_value=np.asarray([4]),
            ) as extrema,
        ):
            scope = solver.choose_support()

        self.assertEqual(scope, ((4, 908), (198, 983)))
        np.testing.assert_array_equal(extrema.call_args.args[0], match_scores[0])
        self.assertEqual(extrema.call_args.kwargs, {"order": 100})

    def test_auto_fight_pause_detection_uses_vision_np_ssim(self):
        solver = AutoFight.__new__(AutoFight)
        solver.device = Mock()
        solver.recog = Mock(gray=np.zeros((1080, 1920), dtype=np.uint8))
        image = np.zeros((32, 32), dtype=np.uint8)

        with (
            patch("arknights_mower.solvers.auto_fight.sleep"),
            patch("arknights_mower.solvers.auto_fight.cropimg", return_value=image),
            patch("arknights_mower.solvers.auto_fight.thres2", return_value=image),
            patch("arknights_mower.solvers.auto_fight.loadres", return_value=image),
            patch(
                "arknights_mower.solvers.auto_fight.vision_np.ssim",
                return_value=0.91,
            ) as ssim,
        ):
            solver.toggle_play()

        ssim.assert_called_once_with(image, image)
        self.assertFalse(solver.playing)


class TestRecognizerVisionNpWiring(unittest.TestCase):
    def test_color_match_keeps_ssim_threshold_0_9(self):
        recognizer = Recognizer.__new__(Recognizer)
        recognizer._img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        recognizer._gray = np.zeros((1080, 1920), dtype=np.uint8)
        resource = np.zeros((10, 20, 3), dtype=np.uint8)

        with (
            patch("arknights_mower.utils.recognize.loadres", return_value=resource),
            patch("arknights_mower.utils.recognize.cmatch", return_value=True),
            patch(
                "arknights_mower.utils.recognize.vision_np.ssim", return_value=0.9
            ) as ssim,
        ):
            scope = recognizer.find("1800")

        self.assertEqual(scope, ((158, 958), (178, 968)))
        self.assertEqual(ssim.call_count, 1)


if __name__ == "__main__":
    unittest.main()
