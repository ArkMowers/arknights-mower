import unittest
from unittest.mock import patch

import numpy as np

from arknights_mower.solvers.depotREC import depotREC, 提取特征点
from arknights_mower.utils.matcher import SVC_MODEL, Matcher


class TestMatcherModelWiring(unittest.TestCase):
    def test_match_uses_folded_svm_model(self):
        matcher = Matcher.__new__(Matcher)
        rect = [[1, 2], [3, 4]]
        score = (0.1, 0.2, 0.3, 0.4)

        with (
            patch.object(matcher, "score", return_value=(rect, score)),
            patch(
                "arknights_mower.utils.matcher.vision_np.linear_svc_predict",
                return_value=False,
            ) as predict,
        ):
            self.assertIsNone(matcher.match(np.zeros((8, 8), dtype=np.uint8)))

        predict.assert_called_once_with(score, SVC_MODEL["w"], SVC_MODEL["b"])


class TestDepotModelWiring(unittest.TestCase):
    def test_feature_extraction_uses_cropped_vision_np_hog(self):
        image = np.zeros((213, 213, 3), dtype=np.uint8)
        expected = np.asarray([1.0])

        with patch(
            "arknights_mower.solvers.depotREC.vision_np.hog", return_value=expected
        ) as hog:
            actual = 提取特征点(image)

        self.assertIs(actual, expected)
        np.testing.assert_array_equal(hog.call_args.args[0], image[40:173, 40:173])

    def test_item_match_uses_folded_knn_model(self):
        solver = depotREC.__new__(depotREC)
        solver.读取物品数字 = lambda image: 42
        model = {
            "X": np.zeros((1, 2)),
            "y_idx": np.asarray([0]),
            "classes": np.asarray(["物品"]),
        }

        with (
            patch(
                "arknights_mower.solvers.depotREC.提取特征点",
                return_value=np.asarray([0.0, 0.0]),
            ),
            patch(
                "arknights_mower.solvers.depotREC.vision_np.knn1_predict",
                return_value="物品",
            ) as predict,
        ):
            actual = solver.匹配物品一次(
                np.zeros((213, 213, 3), dtype=np.uint8),
                np.zeros((213, 213), dtype=np.uint8),
                model,
            )

        self.assertEqual(actual, ["物品", 42])
        predict.assert_called_once()
        np.testing.assert_array_equal(predict.call_args.args[1], model["X"])
        np.testing.assert_array_equal(predict.call_args.args[2], model["y_idx"])
        np.testing.assert_array_equal(predict.call_args.args[3], model["classes"])


if __name__ == "__main__":
    unittest.main()
