import json
import lzma
import os
import pickle
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from time import monotonic

import cv2
import numpy as np

from arknights_mower.data import key_mapping
from arknights_mower.utils import config, depot, vision_np
from arknights_mower.utils.graph import SceneGraphSolver

from .. import __rootdir__
from ..utils.device.device import Device
from ..utils.image import loadimg
from ..utils.log import logger
from ..utils.path import get_path
from ..utils.recognize import Recognizer, Scene
from ..utils.resource_pkg import resource_pkg_path, resource_ui_path

# 向下x变大 = 0
# 向右y变大 = 0
# 左上角物品y坐标 = 285
# 左上角物品x坐标 = 187
# 横排间隔 = 286
# 竖排间隔 = 234
# [140:1000, :]

_DEPOT_ITEM_ROWS = (144, 430, 715)
_DEPOT_PAGE_ROWS = slice(140, 990)


def 导入_数字模板():
    模板文件夹 = f"{__rootdir__}/resources/depot_num"
    数字模板列表 = []
    for 文件名 in sorted(os.listdir(模板文件夹)):
        文件路径 = os.path.join(模板文件夹, 文件名)
        数字模板列表.append(loadimg(文件路径, True))
    return 数字模板列表


def 提取特征点(模板):
    模板 = 模板[40:173, 40:173]
    return vision_np.hog(模板)


_COLOR_ICON_MASK = np.ones((133, 133), dtype=np.uint8)
# 屏蔽右下角数量区域，给模板的八像素位移留出余量。
_COLOR_ICON_MASK[97:, 72:] = 0


@lru_cache(maxsize=2)
def _color_templates(directory, classes):
    templates = []
    for name in classes:
        path = directory / f"{name}.webp"
        if not path.is_file():
            continue
        try:
            icon = loadimg(path)
        except (OSError, cv2.error):
            continue
        if icon is not None:
            icon = cv2.resize(icon, (213, 213))
            templates.append((name, icon[40:173, 40:173]))
    return templates


def _refine_item_color(item, predicted, classes):
    if classes is None:
        return predicted
    directory = resource_ui_path("depot")
    if directory is None:
        root = Path(__rootdir__).parent / "ui"
        directory = (
            root / ("public" if (root / "public/depot").is_dir() else "dist") / "depot"
        )
    templates = _color_templates(directory, tuple(classes))
    if not any(name == predicted for name, _ in templates):
        return predicted
    region = item[32:181, 32:181]
    scores = []
    for name, template in templates:
        result = cv2.matchTemplate(
            region, template, cv2.TM_CCORR_NORMED, mask=_COLOR_ICON_MASK
        )
        score = cv2.minMaxLoc(result)[1]
        if np.isfinite(score):
            scores.append((score, name))
    scores.sort(reverse=True)
    if len(scores) < 2 or scores[0][0] < 0.98:
        return predicted
    # 同图标的周年与感谢庆典凭证保留原模型结果，不用名称排序打破并列。
    if scores[0][0] - scores[1][0] < 0.025:
        return predicted
    return scores[0][1]


def _same_depot_icon_positions(before, after):
    search = 4
    right = before.shape[1] - search
    matched = False
    for y in _DEPOT_ITEM_ROWS:
        # 只比较图标主体，避开下方的数量和有效期提示。
        rows = slice(y - 74, y + 24)
        for x in range(search, right, 234):
            end = min(x + 234, right)
            template = before[rows, x:end]
            textured_before = cv2.meanStdDev(template)[1].item() >= 5
            textured_after = cv2.meanStdDev(after[rows, x:end])[1].item() >= 5
            if textured_before != textured_after:
                return False
            if not textured_before:
                continue
            region = after[rows, x - search : end + search]
            scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, position = cv2.minMaxLoc(scores)
            if score < 0.97 or position != (search, 0):
                return False
            matched = True
    return matched


def _same_depot_labels(before, after):
    def label_bands(frame):
        return np.concatenate([frame[y + 39 : y + 134] for y in _DEPOT_ITEM_ROWS])

    def strokes(labels):
        # 提取数量和有效期的浅色笔画，滤掉大面积背景亮度变化。
        contrast = cv2.morphologyEx(labels, cv2.MORPH_TOPHAT, np.ones((7, 7), np.uint8))
        return cv2.inRange(labels, 195, 255) & cv2.inRange(contrast, 40, 255)

    first = label_bands(before)
    second = label_bands(after)
    changed = cv2.inRange(cv2.absdiff(first, second), 50, 255)
    if not cv2.countNonZero(changed):
        return True
    changed &= strokes(first) | strokes(second)
    local_change = cv2.boxFilter(changed // 255, cv2.CV_16U, (16, 16), normalize=False)
    return local_change.max() < 24


def 识别空物品(物品灰):
    物品灰 = 物品灰[0:130, 130:260]
    _, 二值图 = cv2.threshold(物品灰, 60, 255, cv2.THRESH_BINARY)
    白像素个数 = cv2.countNonZero(二值图)
    所有像素个数 = 二值图.shape[0] * 二值图.shape[1]
    白像素比值 = int((白像素个数 / 所有像素个数) * 100)

    if 白像素比值 > 99:
        logger.debug("仓库扫描：跳过空物品格")

        return False
    else:
        return True


def 切图(圆心x坐标, 圆心y坐标, 拼接结果, 正方形边长=130):
    图片 = []
    for x in 圆心x坐标:
        for y in 圆心y坐标:
            左上角坐标 = (x - 正方形边长, y - 正方形边长)
            右下角坐标 = (x + 正方形边长, y + 正方形边长)
            正方形 = 拼接结果[
                左上角坐标[1] : 右下角坐标[1],
                左上角坐标[0] : 右下角坐标[0],
            ]
            正方形灰 = cv2.cvtColor(正方形, cv2.COLOR_RGB2GRAY)
            if 识别空物品(正方形灰):
                id = str(datetime.now().timestamp())
                正方形切 = 正方形[26:239, 26:239]
                图片.append([正方形切, 正方形灰, id])
    return 图片


class _DepotGameRestarted(Exception):
    pass


class _DepotRecoveryExhausted(Exception):
    pass


class _DepotScanIncomplete(Exception):
    pass


class depotREC(SceneGraphSolver):
    CATEGORY_SWIPE_LIMIT = 32
    CATEGORY_SCAN_TIMEOUT = 60

    def __init__(self, device: Device = None, recog: Recognizer = None) -> None:
        super().__init__(device, recog)

        start_time = monotonic()

        # sift = cv2.SIFT_create()
        orb = cv2.ORB_create()
        bf = cv2.BFMatcher(cv2.NORM_HAMMING2, crossCheck=True)
        self.detector = orb
        self.matcher = bf

        self.仓库输出 = get_path("@app/tmp/depotresult.csv")

        with lzma.open(
            str(resource_pkg_path("arknights_mower/models/CONSUME.pkl")), "rb"
        ) as pkl:
            self.knn模型_CONSUME = pickle.load(pkl)
        with lzma.open(
            str(resource_pkg_path("arknights_mower/models/NORMAL.pkl")), "rb"
        ) as pkl:
            self.knn模型_NORMAL = pickle.load(pkl)
        self.物品数字 = 导入_数字模板()
        self._category_scopes = {
            x: {
                key_mapping[name][2]
                for name in model["classes"]
                if name in key_mapping and not depot.is_skland_only_item(name)
            }
            for x, model in (
                (1063, self.knn模型_CONSUME),
                (1298, self.knn模型_NORMAL),
            )
        }

        self.结果字典 = {}

        logger.debug("仓库扫描：初始化识别模型用时 %.2f 秒", monotonic() - start_time)

    def 切图主程序(self, 拼接好的图片, 横坐标=None):
        if 横坐标 is None:
            横坐标 = [188 + 234 * i for i in range(0, 8)]
        切图列表 = 切图(横坐标, _DEPOT_ITEM_ROWS, 拼接好的图片)
        return 切图列表

    def 读取物品数字(self, 数字图片, 距离阈值=5, 阈值=0.85):
        结果 = {}
        for idx, 模板图片 in enumerate(self.物品数字):
            res = cv2.matchTemplate(数字图片, 模板图片, cv2.TM_CCORR_NORMED)
            loc = np.where(res >= 阈值)
            for i in range(len(loc[0])):
                pos_x = loc[1][i]
                accept = True
                for o in 结果:
                    if abs(o - pos_x) < 距离阈值:
                        accept = False
                        break
                if accept:
                    结果[loc[1][i]] = idx

        物品个数 = ""
        for k in sorted(结果):
            物品个数 += (
                str(结果[k]) if 结果[k] < 10 else ("万" if 结果[k] == 10 else ".")
            )

        matches = re.findall(r"\d+\.\d+|\d+", 物品个数)
        if not matches:
            return None
        格式化数字 = int(float("".join(matches)) * (10000 if "万" in 物品个数 else 1))
        return 格式化数字

    def 匹配物品一次(self, 物品, 物品灰, knn模型: vision_np.Knn1Model):
        物品特征 = 提取特征点(物品)
        predicted_label = vision_np.knn1_predict(
            物品特征,
            knn模型["X"],
            knn模型["y"],
            knn模型["classes"],
        )

        predicted_label = _refine_item_color(物品, predicted_label, knn模型["classes"])
        if depot.is_skland_only_item(predicted_label):
            return [predicted_label, None]
        数字区域 = 物品灰[160:210, 30:210]
        return [predicted_label, self.读取物品数字(数字区域)]

    def run(self, *, report_progress=None) -> bool:
        self._game_restart_used = False
        self.check_current_focus()
        for _ in range(2):
            try:
                return self.transition(report_progress)
            except _DepotGameRestarted:
                self.结果字典 = {}
                if report_progress is not None:
                    report_progress("正在重新进入游戏内仓库")
                logger.info("仓库扫描: 游戏已重启，完成登录后重新进入仓库完整扫描")
            except _DepotRecoveryExhausted:
                self.结果字典 = {}
                logger.warning("仓库扫描: 游戏恢复后仍未就绪，本次扫描失败")
                return False
            except _DepotScanIncomplete:
                self.结果字典 = {}
                logger.warning("仓库扫描: 未确认分类扫描范围，本次扫描失败")
                return False
        return False

    def waiting_solver(self):
        restart_allowed = not self._game_restart_used
        if super().waiting_solver(restart_on_timeout=restart_allowed):
            return True
        if not restart_allowed:
            raise _DepotRecoveryExhausted
        self._game_restart_used = True
        raise _DepotGameRestarted

    def restart_game(self):
        if self._game_restart_used:
            raise _DepotRecoveryExhausted
        super().restart_game()
        self._game_restart_used = True
        raise _DepotGameRestarted

    def back_to_index(self):
        # 在识别器的同场景重启之前结束无进展的登录导航。
        timeout = min(120, config.conf.run_order_delay * 90)
        self._navigation_deadline = monotonic() + timeout
        try:
            self.recog.reset_after_external_control()
            super().back_to_index()
        finally:
            self._navigation_deadline = None

    def scene(self) -> int:
        deadline = getattr(self, "_navigation_deadline", None)
        if deadline is not None and monotonic() >= deadline:
            raise _DepotRecoveryExhausted
        return super().scene()

    def _wait_for_depot_ready(self) -> bool:
        if not self.wait_for_scene_stable(Scene.DEPOT):
            logger.warning("仓库扫描: 未能进入仓库，本次扫描失败")
            return False
        if not self.wait_for_scene_stable(timeout_seconds=5, interval_seconds=0.2):
            logger.warning("仓库扫描: 仓库画面未稳定，本次扫描失败")
            return False
        if self.scene() != Scene.DEPOT:
            logger.warning("仓库扫描: 已离开仓库，本次扫描失败")
            return False
        return True

    def transition(self, report_progress=None) -> bool:
        self.结果字典 = {}
        self._seen_names = set()
        self._unconfirmed_names = set()
        zero_scope = set()
        logger.debug("仓库扫描：返回游戏首页")
        self.back_to_index()
        if self.scene() == Scene.INDEX:
            self.tap_index_element("warehouse")

            if not self._wait_for_depot_ready():
                return False
            logger.info("已进入游戏内仓库")

            任务组 = [
                (1063, self.knn模型_CONSUME, "消耗物品"),
                (1298, self.knn模型_NORMAL, "基础物品"),
            ]

            有非空分类 = 0
            森空岛已覆盖分类 = 0
            for 任务 in 任务组:
                self._category_x = 任务[0]
                self.tap((任务[0], 70))
                if not self._wait_for_depot_ready():
                    return False
                if not self._category_selected(任务[0]):
                    raise _DepotScanIncomplete
                if report_progress is not None:
                    report_progress(f"正在识别{任务[2]}")
                if not self.find("depot_empty"):
                    有非空分类 += 1
                    start_time = monotonic()
                    森空岛已覆盖分类 += self.分类扫描(任务[1])
                    logger.debug(
                        "仓库扫描：识别%s用时 %.2f 秒",
                        任务[2],
                        monotonic() - start_time,
                    )
                else:
                    logger.debug("仓库扫描：%s分类为空", 任务[2])
                zero_scope.update(self._category_scopes[任务[0]])
            if not self.结果字典 and 有非空分类 != 森空岛已覆盖分类:
                logger.warning("仓库扫描: 未确认任何物品数量，本次扫描失败")
                return False
            logger.debug("仓库扫描结果：%s", self.结果字典)
            if report_progress is not None:
                report_progress("正在保存库存")
            扫描时刻 = int(datetime.now().timestamp())
            result = [
                扫描时刻,
                json.dumps(
                    {
                        **dict.fromkeys(zero_scope - self._seen_names, 0),
                        **self.结果字典,
                    },
                    ensure_ascii=False,
                ),
                {"森空岛输出仅占位": ""},
            ]
            import csv

            with open(self.仓库输出, "a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(result)
        else:
            logger.warning("仓库扫描: 未能返回首页，本次扫描失败")
            return False
        ## 读取的时候会存入数据库；扫描成功时顺手记一条完整库存快照（材料就靠它进历史），
        ## 用同一个时间戳，读取端才能把两条记录并成一条完整快照。
        depot.读取仓库(记录快照时刻=扫描时刻)
        # 保留条数由设置决定（0 = 不清理）；放在这里是因为一次扫描才写一次文件。
        depot.清理历史()
        if self.结果字典:
            logger.info(
                f"仓库扫描：已识别{len(self.结果字典)}种物品\n"
                + "\n".join(
                    f"{name}：{count}" for name, count in self.结果字典.items()
                ),
                extra={
                    "log_inventory": {
                        "items": [
                            {"name": name, "count": count}
                            for name, count in self.结果字典.items()
                        ]
                    }
                },
            )
        else:
            logger.info("仓库扫描：未发现需要额外识别的物品")
        return True

    def 对比截图(self, image1, image2):
        image1 = cv2.cvtColor(image1, cv2.COLOR_RGB2GRAY)
        image2 = cv2.cvtColor(image2, cv2.COLOR_RGB2GRAY)
        keypoints1, descriptors1 = self.detector.detectAndCompute(image1, None)
        keypoints2, descriptors2 = self.detector.detectAndCompute(image2, None)
        matches = self.matcher.match(descriptors1, descriptors2)
        similarity = len(matches) / max(len(descriptors1), len(descriptors2))
        return similarity * 100

    def _category_selected(self, x):
        gray = self.recog.gray
        return np.median(gray[80:90, x - 50 : x + 50]) < 100 and all(
            np.median(gray[80:90, other - 50 : other + 50]) > 150
            for other in (835, 1063, 1298)
            if other != x
        )

    @staticmethod
    def _same_depot_view(before, after):
        before = cv2.cvtColor(before[_DEPOT_PAGE_ROWS], cv2.COLOR_RGB2GRAY)
        after = cv2.cvtColor(after[_DEPOT_PAGE_ROWS], cv2.COLOR_RGB2GRAY)
        if np.array_equal(before, after):
            return True
        old_view, new_view = before[:810], after[:810]
        if np.mean(cv2.absdiff(old_view, new_view)) >= 0.5:
            if min(np.std(old_view), np.std(new_view)) < 5:
                return False
            # 边界处的背景和物品特效仍会变化，先比较原位置的整体内容。
            score = cv2.matchTemplate(old_view, new_view, cv2.TM_CCOEFF_NORMED)[0, 0]
            if score < 0.995 and not _same_depot_icon_positions(old_view, new_view):
                return False
        return _same_depot_labels(before, after)

    @staticmethod
    def _depot_scroll_distance(before, after):
        before = cv2.cvtColor(before[_DEPOT_PAGE_ROWS], cv2.COLOR_RGB2GRAY)
        after = cv2.cvtColor(after[_DEPOT_PAGE_ROWS], cv2.COLOR_RGB2GRAY)
        template = before[:, 900:1400]
        if np.std(template) < 5:
            raise _DepotScanIncomplete
        scores = cv2.matchTemplate(after[:, 100:1400], template, cv2.TM_CCOEFF_NORMED)
        _, score, _, position = cv2.minMaxLoc(scores)
        if score < 0.9:
            raise _DepotScanIncomplete
        distance = 800 - position[0]
        near_best = np.flatnonzero(scores[0] >= score - 0.0001)
        peaks = np.split(near_best, np.flatnonzero(np.diff(near_best) > 8) + 1)
        if len(peaks) > 1:
            # 重复图标可能有多个近似峰值，用重叠区域的标签判定实际位移。
            if len(peaks) > 8:
                raise _DepotScanIncomplete
            candidates = [800 - peak[scores[0, peak].argmax()] for peak in peaks]
            width = after.shape[1]
            matched = [
                candidate
                for candidate in candidates
                if _same_depot_labels(
                    before[:, candidate:], after[:, : width - candidate]
                )
            ]
            if len(matched) != 1:
                raise _DepotScanIncomplete
            distance = int(matched[0])
        if not 0 < distance <= 800:
            raise _DepotScanIncomplete
        return distance

    def _category_frames(self):
        deadline = monotonic() + self.CATEGORY_SCAN_TIMEOUT

        def move(start, movement, *, retry):
            if monotonic() >= deadline:
                raise _DepotScanIncomplete
            self.swipe_noinertia(start, movement, retry=retry, capture=True)
            if (
                not self._wait_for_depot_ready()
                or not self._category_selected(self._category_x)
                or monotonic() >= deadline
            ):
                raise _DepotScanIncomplete
            return self.recog.img.copy()

        frame = self.recog.img
        offset = 0
        for start, direction in (((400, 900), 1), ((1600, 900), -1)):
            retry = False
            for _ in range(self.CATEGORY_SWIPE_LIMIT):
                distance = (234 if retry else 702) * direction
                after = move(start, (distance, 0), retry=retry)
                if self._same_depot_view(frame, after):
                    if retry:
                        frame = after
                        break
                    # 未推进时只复核一列，避免前一次手势延迟生效后跳过新列。
                    retry = True
                    continue
                retry = False
                if direction < 0:
                    offset += self._depot_scroll_distance(frame, after)
                    yield offset, after
                frame = after
            else:
                raise _DepotScanIncomplete
            if direction > 0:
                yield offset, frame

    def 分类扫描(self, knn模型: vision_np.Knn1Model):
        seen_columns = set()
        visible_items = 0
        已覆盖物品数 = 0
        for offset, frame in self._category_frames():
            first = max(0, (offset - 58 + 233) // 234)
            last = (offset + 1652) // 234
            columns = [i for i in range(first, last + 1) if i not in seen_columns]
            if not columns:
                continue
            centers = [188 + 234 * i - offset for i in columns]
            items = self.切图主程序(frame[140:1000], centers)
            seen_columns.update(columns)
            visible_items += len(items)
            for 物品, 物品灰, _ in items:
                物品名称, 物品数字 = self.匹配物品一次(物品, 物品灰, knn模型)
                if 物品名称 in key_mapping:
                    物品名称 = key_mapping[物品名称][2]
                self._seen_names.add(物品名称)
                if depot.is_skland_only_item(物品名称):
                    已覆盖物品数 += 1
                    continue
                if 物品数字 is None:
                    self._unconfirmed_names.add(物品名称)
                    self.结果字典.pop(物品名称, None)
                    logger.warning(f"仓库扫描: 无法识别 {物品名称} 的数量，跳过")
                    continue
                if 物品名称 not in self._unconfirmed_names:
                    self.结果字典[物品名称] = self.结果字典.get(物品名称, 0) + 物品数字
        return visible_items > 0 and 已覆盖物品数 == visible_items
