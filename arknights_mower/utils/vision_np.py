"""复刻 scipy/scikit-image/scikit-learn 被用到的函数（纯 numpy + opencv，与上游数值等价）。

对齐版本：scipy 1.13.0 / scikit-image 0.23.2 / scikit-learn 1.4.2。
SSIM 的 7x7 均值窗用 cv2.blur（cv2 为本项目保留依赖，比 numpy 积分图快 1.5-2x，偏差 2.5e-8）。
HOG 的 cell 直方图用 np.add.at 向量化（比 skimage 的 Cython 更快，偏差 1.3e-6）。
"""

from typing import TypedDict

import cv2
import numpy as np


class LinearSvcModel(TypedDict):
    w: np.ndarray
    b: float


class Knn1Model(TypedDict):
    # 字段名与 sklearn 的属性对应：y 存放 classes 的下标（等价于 _y），不是标签本身。
    # MowerResource 资源包直接生成这三个键，改名会让已发布的模型文件无法加载。
    X: np.ndarray
    y: np.ndarray
    classes: np.ndarray


def _extrema(data, order, pick_max):
    """argrelmax/argrelmin 的公共实现：滑窗比较中心值与左右邻域，边界按 edge 补齐。"""
    d = np.asarray(data, dtype=float)
    n = d.size
    if n <= 2 * order:
        return np.array([], dtype=int)
    pad = np.pad(d, order, mode="edge")
    w = np.lib.stride_tricks.sliding_window_view(pad, 2 * order + 1)[:n]
    c = w[:, order]
    left, right = w[:, :order], w[:, order + 1 :]
    if pick_max:
        return np.flatnonzero((c > left.max(1)) & (c > right.max(1)))
    return np.flatnonzero((c < left.min(1)) & (c < right.min(1)))


def argrelmax(data, order=1):
    """复刻 scipy.signal.argrelmax(mode='clip')：严格大于邻域最大值，平顶/边界不判。"""
    return _extrema(data, order, pick_max=True)


def argrelmin(data, order=1):
    """复刻 scipy.signal.argrelmin(mode='clip')：严格小于邻域最小值，平顶/边界不判。"""
    return _extrema(data, order, pick_max=False)


def _box(img, size):
    """均值窗：cv2.blur 复刻 scipy.ndimage.uniform_filter(mode='reflect')。"""
    return cv2.blur(img.astype(np.float64), (size, size), borderType=cv2.BORDER_REFLECT)


def ssim(im1, im2, win_size=7, K1=0.01, K2=0.03):
    """复刻 skimage 0.23.2 默认路径：uniform 窗、data_range 由 dtype 推导、裁剪边框取均值。"""
    dr = (
        255.0
        if im1.dtype == np.uint8
        else float(max(im1.max(), im2.max()) - min(im1.min(), im2.min()))
    )
    C1 = (K1 * dr) ** 2
    C2 = (K2 * dr) ** 2
    ux, uy = _box(im1, win_size), _box(im2, win_size)
    vx = _box(im1.astype(float) ** 2, win_size) - ux * ux
    vy = _box(im2.astype(float) ** 2, win_size) - uy * uy
    vxy = _box(im1.astype(float) * im2.astype(float), win_size) - ux * uy
    cn = win_size * win_size / (win_size * win_size - 1)
    vx *= cn
    vy *= cn
    vxy *= cn
    s = ((2 * ux * uy + C1) * (2 * vxy + C2)) / (
        (ux * ux + uy * uy + C1) * (vx + vy + C2)
    )
    p = win_size // 2
    return float(s[p:-p, p:-p].mean())


def _grad(channel):
    """复刻 skimage._hog_channel_gradient：中心差分，边界置零。"""
    h, w = channel.shape
    g_row = np.zeros_like(channel)
    g_col = np.zeros_like(channel)
    g_row[1:-1, :] = channel[2:, :] - channel[:-2, :]
    g_col[:, 1:-1] = channel[:, 2:] - channel[:, :-2]
    return g_row, g_col


def hog(img, orientations=18, pixels_per_cell=(8, 8), cells_per_block=(2, 2)):
    """复刻 skimage.feature.hog：transform_sqrt + 彩色最佳通道 + 硬分箱 + L2-Hys。

    精度必须与 skimage 一致：它对 uint8 输入按 _supported_float_type 取 float64。
    用 float32 会让 arctan2 的舍入在方向落在分箱边界时跳到相邻箱，个别 block
    的能量整体错位，最大偏差可达 5e-2。
    """
    dt = np.float64
    src = np.sqrt(img.astype(dt))
    h, w, ch = src.shape
    gxs, gys, mags = [], [], np.zeros((h, w, ch), dt)
    for c in range(ch):
        gr, gc = _grad(src[..., c])
        gxs.append(gr)
        gys.append(gc)
        mags[..., c] = np.hypot(gr, gc)
    gx = np.stack(gxs, -1)
    gy = np.stack(gys, -1)
    best = mags.argmax(axis=2)
    gx_b = np.take_along_axis(gx, best[..., None], -1)[..., 0]
    gy_b = np.take_along_axis(gy, best[..., None], -1)[..., 0]
    mag = np.hypot(gx_b, gy_b).astype(np.float64)
    ori = np.degrees(np.arctan2(gx_b, gy_b)) % 180.0
    step = 180.0 / orientations
    bin_id = np.floor(ori / step).astype(int) % orientations
    c_row, c_col = pixels_per_cell
    ncr, ncc = h // c_row, w // c_col
    # 只统计完整 cell 覆盖的像素（与 skimage 一致，超出的边缘像素忽略）
    mr, mc = ncr * c_row, ncc * c_col
    mag = mag[:mr, :mc]
    bin_id = bin_id[:mr, :mc]
    hist = np.zeros((ncr, ncc, orientations))
    rr = (np.arange(mr) // c_row)[:, None] * np.ones((1, mc), int)
    cc = np.ones((mr, 1), int) * (np.arange(mc) // c_col)
    np.add.at(hist, (rr.ravel(), cc.ravel(), bin_id.ravel()), mag.ravel())
    hist /= c_row * c_col
    nbr, nbc = cells_per_block
    feat, eps = [], 1e-5
    for r in range(ncr - nbr + 1):
        for c in range(ncc - nbc + 1):
            b = hist[r : r + nbr, c : c + nbc].ravel()
            b = b / np.sqrt(np.sum(b**2) + eps)
            b = np.clip(b, 0, 0.2)
            b = b / np.sqrt(np.sum(b**2) + eps)
            feat.append(b)
    return np.concatenate(feat)


def linear_svc_predict(x, w, b):
    """复刻 sklearn Pipeline(StandardScaler+LinearSVC).predict：w·x + b > 0（严格大于）。"""
    return bool(np.dot(x, w) + b > 0)


def knn1_predict(x, X, y_idx, classes):
    """复刻 sklearn KNeighborsClassifier(k=1, weights='distance')：
    X=训练样本, y_idx=编码标签(_y), classes=类别名(classes_)，返回最近邻类别。"""
    idx = np.argmin(np.sum((X - x) ** 2, axis=1))
    return classes[y_idx[idx]]
