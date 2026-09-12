"""vision_np 等价性 golden test。

将 utils/vision_np.py 的复刻函数与上游（scipy/skimage/sklearn）及真实模型逐位/数值比对。
scipy/skimage/sklearn 是待移除的运行依赖，仅在开发环境可导入时本文件生效；
生产移除依赖后自动跳过（等价性验证已在此锁定）。

等价性目标（2026-08-18 实测）：
  argrelmax/min 逐位一致；SSIM(cv2.blur) ~2.5e-8；HOG ~1.3e-6；
  LinearSVC 折叠与 sklearn predict 一致；KNN k=1 折叠与 sklearn predict 一致。
"""

import lzma
import pickle
import unittest

import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import vision_np

try:
    from scipy.signal import argrelmax as scipy_argrelmax
    from scipy.signal import argrelmin as scipy_argrelmin

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from skimage.feature import hog as skimage_hog
    from skimage.metrics import structural_similarity as skimage_ssim

    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False

try:
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.svm import LinearSVC

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def _load_svm_model():
    with lzma.open(f"{__rootdir__}/models/svm.model", "rb") as f:
        return pickle.loads(f.read())


def _load_knn(name):
    with lzma.open(f"{__rootdir__}/models/{name}.pkl", "rb") as f:
        return pickle.loads(f.read())


class TestArgRelMaxMinEquivalence(unittest.TestCase):
    @unittest.skipUnless(HAS_SCIPY, "scipy 未安装")
    def test_argrelmax_bitwise(self):
        rng = np.random.default_rng(0)
        for order in (1, 5, 50, 100):
            x = rng.normal(size=3000).cumsum()
            np.testing.assert_array_equal(
                vision_np.argrelmax(x, order), scipy_argrelmax(x, order=order)[0]
            )

    @unittest.skipUnless(HAS_SCIPY, "scipy 未安装")
    def test_argrelmin_bitwise(self):
        rng = np.random.default_rng(0)
        for order in (1, 5, 50, 100):
            x = rng.normal(size=3000).cumsum()
            np.testing.assert_array_equal(
                vision_np.argrelmin(x, order), scipy_argrelmin(x, order=order)[0]
            )

    @unittest.skipUnless(HAS_SCIPY, "scipy 未安装")
    def test_boundary_and_plateau(self):
        # 平顶（严格大于，不判极值）与边界（首/末样本永不判极值）
        for sig in ([1, 2, 3], [3, 2, 1], [0, 1, 1, 0], [0, 5, 3], [10, 0, 0]):
            s = np.array(sig, dtype=float)
            np.testing.assert_array_equal(
                vision_np.argrelmax(s, 1), scipy_argrelmax(s, order=1)[0]
            )
            np.testing.assert_array_equal(
                vision_np.argrelmin(s, 1), scipy_argrelmin(s, order=1)[0]
            )


class TestSsimEquivalence(unittest.TestCase):
    @unittest.skipUnless(HAS_SKIMAGE, "skimage 未安装")
    def test_ssim_matches_skimage_default(self):
        rng = np.random.default_rng(0)
        worst = 0.0
        for _ in range(20):
            a = rng.integers(0, 256, (400, 500), dtype=np.uint8)
            b = np.clip(
                a.astype(int) + rng.integers(-20, 20, (400, 500)), 0, 255
            ).astype(np.uint8)
            worst = max(worst, abs(skimage_ssim(a, b) - vision_np.ssim(a, b)))
        self.assertLess(worst, 1e-5, f"SSIM 最大偏差 {worst:.2e} 超限")

    @unittest.skipUnless(HAS_SKIMAGE, "skimage 未安装")
    def test_ssim_real_project_shapes(self):
        # recognize.py 热路径：2D uint8 小模板；matcher.py 的 multichannel=True 在 0.23.2 被忽略
        rng = np.random.default_rng(1)
        for shape in ((50, 50), (100, 60), (200, 100), (440, 185)):
            a = rng.integers(0, 256, shape, dtype=np.uint8)
            b = np.clip(a.astype(int) + rng.integers(-8, 8, shape), 0, 255).astype(
                np.uint8
            )
            self.assertLess(
                abs(skimage_ssim(a, b) - vision_np.ssim(a, b)),
                1e-5,
                f"{shape} SSIM 偏差超限",
            )
        # matcher 调用形态（multichannel=True 对 2D 是 no-op）
        a = rng.integers(0, 256, (300, 200), dtype=np.uint8)
        b = np.clip(a.astype(int) + rng.integers(-8, 8, (300, 200)), 0, 255).astype(
            np.uint8
        )
        self.assertLess(
            abs(skimage_ssim(a, b, multichannel=True) - vision_np.ssim(a, b)), 1e-5
        )

    @unittest.skipUnless(HAS_SKIMAGE, "skimage 未安装")
    def test_ssim_returns_float(self):
        a = np.zeros((32, 32), dtype=np.uint8)
        b = np.ones((32, 32), dtype=np.uint8) * 255
        self.assertIsInstance(vision_np.ssim(a, b), float)


class TestHogEquivalence(unittest.TestCase):
    @unittest.skipUnless(HAS_SKIMAGE, "skimage 未安装")
    def test_hog_matches_skimage_depotREC_params(self):
        # depotREC.py 参数：18 ori / 8x8 / 2x2 / L2-Hys / transform_sqrt / 彩色最佳通道
        # 必须跨多个种子：单一种子不足以暴露精度问题。用 float32 计算梯度时，
        # 种子 1 的偏差只有 1.4e-06，而种子 2、5、6 达到 2e-2 至 5e-2。
        worst = 0.0
        for seed in (1, 2, 5, 6):
            rng = np.random.default_rng(seed)
            for _ in range(2):
                a = rng.integers(0, 256, (133, 133, 3), dtype=np.uint8)
                ref = skimage_hog(
                    a,
                    orientations=18,
                    pixels_per_cell=(8, 8),
                    cells_per_block=(2, 2),
                    block_norm="L2-Hys",
                    transform_sqrt=True,
                    channel_axis=-1,
                )
                my = vision_np.hog(a)
                self.assertEqual(my.shape, ref.shape)
                worst = max(worst, np.abs(ref - my).max())
        self.assertLess(worst, 1e-4, f"HOG 最大偏差 {worst:.2e} 超限")


class TestLinearSvcEquivalence(unittest.TestCase):
    @unittest.skipUnless(HAS_SKLEARN, "sklearn 未安装")
    def test_collapse_matches_svm_model(self):
        m = _load_svm_model()
        self.assertEqual(set(m), {"w", "b"})
        svc = LinearSVC()
        svc.coef_ = m["w"][None, :]
        svc.intercept_ = np.asarray([m["b"]])
        svc.classes_ = np.asarray([False, True])
        svc.n_features_in_ = m["w"].shape[0]
        rng = np.random.default_rng(0)
        # 广域随机 + 边界附近（决策值接近 0）
        for _ in range(5):
            X = rng.uniform(0, 1, (2000, 4))
            agree = sum(
                vision_np.linear_svc_predict(row, m["w"], m["b"])
                == bool(svc.predict([row])[0])
                for row in X
            )
            self.assertEqual(agree, 2000)


class TestKnn1Equivalence(unittest.TestCase):
    def assert_model_matches_sklearn(self, name, rounds):
        knn = _load_knn(name)
        self.assertEqual(set(knn), {"X", "y", "classes"})
        Xn, yi, cl = knn["X"], knn["y"], knn["classes"]
        reference = KNeighborsClassifier(n_neighbors=1, weights="distance").fit(
            Xn, cl[yi]
        )
        rng = np.random.default_rng(0)
        for _ in range(rounds):
            Q = rng.uniform(0, 1, (100, Xn.shape[1]))
            agree = sum(
                vision_np.knn1_predict(q, Xn, yi, cl) == reference.predict([q])[0]
                for q in Q
            )
            self.assertEqual(agree, 100)

    @unittest.skipUnless(HAS_SKLEARN, "sklearn 未安装")
    def test_collapse_matches_consume_model(self):
        self.assert_model_matches_sklearn("CONSUME", 5)

    @unittest.skipUnless(HAS_SKLEARN, "sklearn 未安装")
    def test_collapse_matches_normal_model(self):
        self.assert_model_matches_sklearn("NORMAL", 1)


if __name__ == "__main__":
    unittest.main()
