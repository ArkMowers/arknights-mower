import lzma
import math
import pickle
import tracemalloc
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers.depotREC import depotREC, 提取特征点
from arknights_mower.utils import vision_np

MODELS = Path(__file__).resolve().parents[1] / "models"


@pytest.fixture(scope="module", params=("CONSUME", "NORMAL"))
def model(request):
    with lzma.open(MODELS / f"{request.param}.pkl", "rb") as source:
        return pickle.load(source)


def test_shipped_training_rows_keep_their_item_identity(model):
    for row in (0, 15, 16, len(model["X"]) - 1):
        assert (
            vision_np.knn1_predict(
                model["X"][row].astype(np.float64),
                model["X"],
                model["y"],
                model["classes"],
            )
            == model["classes"][model["y"][row]]
        )


def test_real_hog_with_shipped_models_matches_independent_euclidean_distances(model):
    image = np.random.default_rng(18).integers(0, 256, (213, 213, 3), dtype=np.uint8)
    query = 提取特征点(image)
    nearest = min(
        range(len(model["X"])), key=lambda row: math.dist(query, model["X"][row])
    )
    assert (
        vision_np.knn1_predict(query, model["X"], model["y"], model["classes"])
        == model["classes"][model["y"][nearest]]
    )


def test_shipped_model_prediction_stays_below_four_mib_of_temporary_arrays(model):
    query = model["X"][0].astype(np.float64)
    tracemalloc.start()
    try:
        actual = vision_np.knn1_predict(query, model["X"], model["y"], model["classes"])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert actual == model["classes"][model["y"][0]]
    assert peak < 4 * 1024 * 1024


@pytest.mark.parametrize("rows", (1, 15, 16, 17, 33))
def test_last_training_row_can_be_the_nearest(rows):
    samples = np.full((rows, 3), 10, dtype=np.float32)
    samples[-1] = (1, 2, 3)
    actual = vision_np.knn1_predict(
        np.array([1, 2, 3], dtype=np.float64),
        samples,
        np.arange(rows),
        np.arange(rows),
    )
    assert actual == rows - 1


def test_equal_distances_keep_the_first_training_row_across_blocks():
    samples = np.full((33, 2), 10, dtype=np.float32)
    samples[15], samples[16], samples[32] = (1, 0), (-1, 0), (0, 1)
    assert (
        vision_np.knn1_predict(np.zeros(2), samples, np.arange(33), np.arange(33)) == 15
    )


def test_float64_query_preserves_a_difference_below_float32_precision():
    assert (
        vision_np.knn1_predict(
            np.array([1 + 2**-30], dtype=np.float64),
            np.array([[0], [2]], dtype=np.float32),
            np.array([0, 1]),
            np.array(["farther", "nearer"]),
        )
        == "nearer"
    )


def test_python_list_query_keeps_the_nearest_item():
    assert (
        vision_np.knn1_predict(
            [2, 3],
            np.array([[0, 0], [2, 3]], dtype=np.float32),
            np.array([0, 1]),
            np.array(["farther", "exact"]),
        )
        == "exact"
    )


def test_nearby_large_vectors_do_not_lose_their_distance_to_cancellation():
    assert (
        vision_np.knn1_predict(
            np.array([1e8, 0]),
            np.array([[1e8, 1], [1e8, 0]]),
            np.array([0, 1]),
            np.array(["farther", "exact"]),
        )
        == "exact"
    )


def test_integer_distances_keep_numpy_sum_type_promotion():
    assert (
        vision_np.knn1_predict(
            np.zeros(8, dtype=np.uint8),
            np.array([[6] * 8, [2] * 8], dtype=np.uint8),
            np.array([0, 1]),
            np.array(["farther", "nearer"]),
        )
        == "nearer"
    )


def test_noncontiguous_readonly_inputs_remain_unchanged():
    backing = np.arange(66 * 6, dtype=np.float32).reshape(66, 6)
    samples = backing[::2, ::2]
    query_storage = np.repeat(samples[16].astype(np.float64), 2)
    query = query_storage[::2]
    samples.flags.writeable = False
    query.flags.writeable = False
    before = backing.copy()
    assert vision_np.knn1_predict(query, samples, np.arange(33), np.arange(33)) == 16
    np.testing.assert_array_equal(backing, before)


def test_no_training_rows_retains_the_empty_argmin_error():
    with pytest.raises(ValueError, match="argmin"):
        vision_np.knn1_predict(
            np.zeros(3), np.empty((0, 3)), np.array([]), np.array([])
        )


def test_zero_features_keep_the_first_item():
    assert (
        vision_np.knn1_predict(
            np.empty(0),
            np.empty((17, 0)),
            np.arange(17),
            np.arange(17),
        )
        == 0
    )


def test_depot_uses_real_hog_and_keeps_the_confirmed_quantity():
    image = np.random.default_rng(18).integers(0, 256, (213, 213, 3), dtype=np.uint8)
    feature = 提取特征点(image)
    assert feature.dtype == np.float64
    assert feature.shape == (16200,)
    samples = np.repeat((feature + 1)[None, :], 33, axis=0)
    samples[32] = feature
    solver = depotREC.__new__(depotREC)
    solver.读取物品数字 = Mock(return_value=42)
    solver.读取龙门币数字 = Mock(side_effect=AssertionError("unexpected OCR"))
    gray = np.zeros((260, 260), dtype=np.uint8)
    assert solver.匹配物品一次(
        image,
        gray,
        {"X": samples, "y": np.arange(33), "classes": np.arange(33)},
    ) == [32, 42]
    np.testing.assert_array_equal(
        solver.读取物品数字.call_args.args[0], gray[160:210, 30:210]
    )
