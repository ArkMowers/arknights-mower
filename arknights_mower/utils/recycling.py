"""Read recycling rewards from the confirmed standard material popup."""

import json
import re
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.data import key_mapping
from arknights_mower.utils import rapidocr
from arknights_mower.utils.log import logger
from arknights_mower.utils.operation_drops import _icon_directory


def _ocr(image, *, use_det=True):
    if rapidocr.engine is None:
        rapidocr.initialize_ocr()
    result = (
        rapidocr.engine(image, use_det=use_det, use_cls=False, use_rec=True)[0] or []
    )
    if use_det:
        return result
    return [(None, text, confidence) for text, confidence in result]


@lru_cache(maxsize=128)
def _material_icon(directory, name):
    path = Path(directory) / f"{name}.webp"
    try:
        icon = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except (OSError, cv2.error):
        return None
    if icon is None or icon.ndim != 3 or icon.shape[2] != 4:
        return None
    icon = cv2.resize(icon, (220, 220))[:132]
    return icon[:, :, :3], (icon[:, :, 3] > 240).astype(np.uint8) * 255


def _collection_notifications(image):
    """Locate right-side collection tips by their gold stripe and dark panel."""
    # 收取截图中的提示从 y=90 开始，每项间隔 185 像素。
    # 只看左侧金色格纹和右侧黑底，避开随产物变化的图标及文字。
    right = cv2.cvtColor(image[90:785, 1412:], cv2.COLOR_RGB2HSV)
    regions = []
    for top in (0, 185, 370, 555):
        stripe = right[top + 5 : top + 140, :18]
        gold = cv2.inRange(stripe, (20, 100, 60), (40, 255, 255))
        dark = right[top + 5 : top + 140, 148:, 2] < 60
        if np.mean(gold > 0) >= 0.20 and np.mean(dark) >= 0.65:
            regions.append((top + 90, top + 245))
    return regions


def recycling_notifications_overlap_reward_row(image):
    """Return whether collection tips could hide rewards on a standard frame."""
    if (
        not isinstance(image, np.ndarray)
        or image.shape != (1080, 1920, 3)
        or image.dtype != np.uint8
    ):
        return False
    return any(
        top < 705 and bottom > 415 for top, bottom in _collection_notifications(image)
    )


def _unconfirmed(reason, **details):
    logger.debug("回收站材料识别未确认：%s；%s", reason, details)
    return None


def _label_evidence(labels):
    evidence = []
    for box, text, confidence in labels[:8]:
        try:
            score = float(confidence)
        except (TypeError, ValueError, OverflowError):
            score = None
        try:
            points = (
                None
                if box is None
                else [[float(point[0]), float(point[1])] for point in box[:4]]
            )
        except (TypeError, ValueError, IndexError, OverflowError):
            points = None
        evidence.append({"text": str(text)[:80], "confidence": score, "box": points})
    return evidence


def _best_material_icon(image, center, icons):
    left, right = max(0, round(center) - 140), min(1920, round(center) + 140)
    if right - left < 220:
        return None
    region = cv2.cvtColor(image[415:575, left:right], cv2.COLOR_RGB2BGR)
    best = None
    for name, (template, mask) in icons.items():
        scores = cv2.matchTemplate(region, template, cv2.TM_CCORR_NORMED, mask=mask)
        _, score, _, location = cv2.minMaxLoc(scores)
        if np.isfinite(score) and (best is None or score > best[1]):
            best = (name, score, left + location[0] + 110, location[1] - 5)
    return best


def read_recycling_materials(image):
    """Return complete name/count observations, or None on uncertainty.

    The caller confirms the material scene and collection source. The supplied
    standard popup has one reward row. Each circle selects its highest-scoring
    material icon; absent icons and uncertain counts do not produce estimates.
    """
    if (
        not isinstance(image, np.ndarray)
        or image.shape != (1080, 1920, 3)
        or image.dtype != np.uint8
    ):
        return _unconfirmed("画面尺寸或像素格式无效")
    notifications = _collection_notifications(image)
    if notifications:
        image = image.copy()
        for top, bottom in notifications:
            image[top:bottom, 1410:] = 0
    circles = cv2.HoughCircles(
        cv2.cvtColor(image[280:850], cv2.COLOR_RGB2GRAY),
        cv2.HOUGH_GRADIENT,
        1.2,
        160,
        param1=100,
        param2=50,
        minRadius=85,
        maxRadius=105,
    )
    labels = _ocr(image[640:705])
    if len(labels) > 64:
        logger.debug("回收站名称候选仅处理前 64 条：%s", len(labels))
        labels = labels[:64]
    if circles is None or not 1 <= len(circles[0]) <= 8:
        return _unconfirmed(
            "奖励圆数量无效",
            labels=len(labels),
            circles=0 if circles is None else len(circles[0]),
            candidates=_label_evidence(labels),
        )
    centers = sorted(float(circle[0]) for circle in circles[0])
    # 提示遮住奖励行时，可见材料仍须围绕屏幕中央排列；只剩左侧几件时
    # 不能据此确认整批材料，避免屏蔽提示时也漏掉其后方的真实奖励。
    row_occluded = any(top < 705 and bottom > 415 for top, bottom in notifications)
    if row_occluded and abs((centers[0] + centers[-1]) / 2 - 960) > 15:
        return _unconfirmed("提示遮挡后的奖励未居中", centers=centers)
    if any(not 515 <= circle[1] + 280 <= 545 for circle in circles[0]):
        return _unconfirmed("奖励圆纵向位置无效", circles=circles[0].tolist())
    if any(not 125 <= center <= 1795 for center in centers):
        return _unconfirmed("奖励圆横向位置无效", centers=centers)
    try:
        model = recycling_model()
        names = {row["name"] for row in model["ordinary"] + model["extra"]}
    except (OSError, ValueError, KeyError, TypeError):
        names = set()
    names = {
        name
        for name in names
        if isinstance(name, str)
        and (entry := key_mapping.get(name)) is not None
        and entry[3] == "MATERIAL"
    }
    required_names = names.copy()
    for _, text, _ in labels:
        name = re.sub(r"\s", "", text)
        entry = key_mapping.get(name)
        if entry is not None and entry[3] == "MATERIAL":
            names.add(name)
    directory = str(_icon_directory())
    icons = {}
    for name in sorted(names):
        icon = _material_icon(directory, name)
        if icon is None and name in required_names:
            return _unconfirmed("材料图标缺失", name=name, directory=directory)
        if icon is not None:
            icons[name] = icon
    rewards = []
    for center in centers:
        best = _best_material_icon(image, center, icons)
        if best is None or best[1] <= 0.90:
            return _unconfirmed(
                "材料图标未确认",
                center=center,
                match=best,
                candidates=_label_evidence(labels),
            )
        name, score, icon_center, vertical_offset = best
        if not 140 <= icon_center <= 1780 or abs(icon_center - center) > 15:
            return _unconfirmed(
                "材料图标与奖励圆位置不匹配",
                name=name,
                center=icon_center,
                circle=center,
                confidence=score,
            )
        if row_occluded and icon_center + 140 > 1410:
            return _unconfirmed("收取提示遮挡材料", name=name, center=icon_center)
        rewards.append((name, icon_center, vertical_offset))
    checked_centers = set()
    for box, _, _ in labels:
        try:
            if len(box) != 4 or any(len(point) != 2 for point in box):
                continue
            points = np.asarray(box, dtype=float)
            if not np.isfinite(points).all():
                continue
            left, top = points.min(axis=0)
            right, bottom = points.max(axis=0)
            if not (0 <= left < right <= 1920 and 0 <= top < bottom <= 65):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if any(value - 140 <= left < right <= value + 140 for value in centers):
            continue
        center = round((left + right) / 2)
        if center in checked_centers:
            continue
        checked_centers.add(center)
        left, right = max(0, center - 140), min(1920, center + 140)
        local_circles = cv2.HoughCircles(
            cv2.cvtColor(image[400:660, left:right], cv2.COLOR_RGB2GRAY),
            cv2.HOUGH_GRADIENT,
            1.2,
            160,
            param1=100,
            param2=50,
            minRadius=85,
            maxRadius=105,
        )
        if local_circles is None:
            continue
        for x, y, radius in local_circles[0]:
            if not (
                radius <= x <= right - left - radius and radius <= y <= 260 - radius
            ):
                continue
            x, y = float(x + left), float(y + 400)
            if (
                125 <= x <= 1795
                and 515 <= y <= 545
                and min(abs(value - x) for value in centers) > 15
            ):
                return _unconfirmed(
                    "存在未定位的奖励圆",
                    circle=(x, y, float(radius)),
                    circles=centers,
                    candidates=_label_evidence(labels),
                )
    materials = {}
    for name, center, vertical_offset in rewards:
        # 图标模板在标准奖励中的顶边为 y=420，数量区域随其实际位置平移。
        quantity = cv2.cvtColor(
            image[
                570 + vertical_offset : 625 + vertical_offset,
                center + 10 : center + 90,
            ],
            cv2.COLOR_RGB2GRAY,
        )
        quantity = cv2.threshold(quantity, 200, 255, cv2.THRESH_BINARY)[1]
        counts = _ocr(quantity, use_det=False)
        if len(counts) != 1:
            return _unconfirmed("数量结果数量无效", name=name, results=len(counts))
        _, count, confidence = counts[0]
        if (
            not np.isfinite(confidence)
            or confidence < 0.90
            or re.fullmatch(r"[1-9][0-9]{0,4}", count.strip()) is None
        ):
            return _unconfirmed(
                "材料数量未确认", name=name, text=count[:80], confidence=confidence
            )
        materials[name] = materials.get(name, 0) + int(count)
    logger.debug("回收站材料识别通过：%s", materials)
    return materials


@lru_cache(maxsize=1)
def recycling_model():
    """Load the supplied calculator's probability and valuation snapshot."""
    return json.loads(
        (Path(__rootdir__) / "data/recycling_model.json").read_text("utf-8")
    )


def recycling_expectation(materials, unknown_collections=0, valuation=None):
    """Compare equal material quantities using the calculator's long-run mixture."""
    model = recycling_model()
    if valuation is None:
        from arknights_mower.utils.recycling_valuation import default_valuation

        valuation = default_valuation()
    ordinary, extra = model["ordinary"], model["extra"]
    normal_weight = sum(item["weight"] for item in ordinary)
    extra_weight = sum(item["weight"] for item in extra)
    extra_rate = (
        sum(item["weight"] * item["points"] / normal_weight for item in ordinary)
        / model["point_threshold"]
    )
    valuations = valuation["prices"]
    normal_ev = sum(
        valuations[item["name"]] * item["weight"] / normal_weight for item in ordinary
    )
    extra_ev = sum(
        valuations[item["name"]] * item["weight"] / extra_weight for item in extra
    )
    per_material = (normal_ev + extra_rate * extra_ev) / (1 + extra_rate)
    probabilities = {}
    for pool, weight, rate in (
        (ordinary, normal_weight, 1),
        (extra, extra_weight, extra_rate),
    ):
        for item in pool:
            rarity = item["rarity"]
            probabilities[rarity] = probabilities.get(rarity, 0) + item[
                "weight"
            ] / weight * rate / (1 + extra_rate)
    count = sum(item["count"] for item in materials)
    unknown = [item["name"] for item in materials if item["name"] not in valuations]
    actual = sum(item["count"] * valuations.get(item["name"], 0) for item in materials)
    complete = not unknown and not unknown_collections
    modeled = {item["name"] for item in ordinary + extra}
    unmodeled = [item["name"] for item in materials if item["name"] not in modeled]
    expected = count * per_material
    ratios = valuation["ratios"]
    daily = (normal_ev + extra_rate * extra_ev) / 2
    manufacture = (
        daily
        / valuation["lmd_sanity"]
        * (ratios["gold"] + ratios["order"])
        / ratios["experience"]
        / 8000
    )
    calculator = {
        "daily_sanity": daily,
        "configured_daily_sanity": daily * ratios["efficiency"],
        "manufacturing_equivalent": manufacture * ratios["efficiency"],
        "elite0_equivalent": manufacture * 0.2,
        "elite2_equivalent": manufacture * 0.3,
    }
    return {
        "actual_sanity": actual if complete else None,
        "known_sanity": actual,
        "expected_sanity": expected if complete and not unmodeled else None,
        "difference": actual - expected if complete and not unmodeled else None,
        "per_material": per_material,
        "ordinary_sanity": normal_ev,
        "extra_sanity": extra_ev,
        "extra_rate": extra_rate,
        "unknown_materials": unknown,
        "unmodeled_materials": unmodeled,
        "unknown_collections": unknown_collections,
        "qualities": [
            {
                "rarity": rarity,
                "probability": probability,
                "expected_count": count * probability,
            }
            for rarity, probability in sorted(probabilities.items())
        ],
        "source": {key: model[key] for key in ("source", "sheet", "ranges")},
        "valuation": valuation,
        "calculator": {
            **calculator,
            "replacement": {
                key: value / (1 + extra_rate) for key, value in calculator.items()
            },
        },
    }
