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
from arknights_mower.utils.operation_drops import _icon_directory


def _ocr(image):
    if rapidocr.engine is None:
        rapidocr.initialize_ocr()
    return rapidocr.engine(image, use_det=True, use_cls=False, use_rec=True)[0] or []


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


def recycling_notifications_visible(image):
    """Detect the gold checkerboard and dark panel of right-side collection tips."""
    if (
        not isinstance(image, np.ndarray)
        or image.shape != (1080, 1920, 3)
        or image.dtype != np.uint8
    ):
        return False
    # 收取截图中的提示从 y=90 开始，每项间隔 185 像素。
    # 只看左侧金色格纹和右侧黑底，避开随产物变化的图标及文字。
    right = cv2.cvtColor(image[90:785, 1412:], cv2.COLOR_RGB2HSV)
    for top in (0, 185, 370, 555):
        stripe = right[top + 5 : top + 140, :18]
        gold = cv2.inRange(stripe, (20, 100, 60), (40, 255, 255))
        dark = right[top + 5 : top + 140, 148:, 2] < 60
        if np.mean(gold > 0) >= 0.20 and np.mean(dark) >= 0.65:
            return True
    return False


def read_recycling_materials(image):
    """Return complete name/count observations, or None on uncertainty.

    The caller confirms the material scene and collection source. The supplied
    standard popup has one row of name plates at y=640..705; unsupported rows,
    unknown names, absent icons and uncertain counts do not produce estimates.
    """
    if (
        not isinstance(image, np.ndarray)
        or image.shape != (1080, 1920, 3)
        or image.dtype != np.uint8
    ):
        return None
    labels = _ocr(image[640:705])
    if not 1 <= len(labels) <= 8:
        return None
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
    if circles is None or len(circles[0]) != len(labels):
        return None
    centers = sorted(float(circle[0]) for circle in circles[0])
    if any(not 515 <= circle[1] + 280 <= 545 for circle in circles[0]):
        return None
    materials = {}
    matched_centers = set()
    for box, text, confidence in labels:
        name = re.sub(r"\s", "", text)
        entry = key_mapping.get(name)
        if (
            not np.isfinite(confidence)
            or confidence < 0.90
            or entry is None
            or entry[3] != "MATERIAL"
        ):
            return None
        center = round(
            (min(point[0] for point in box) + max(point[0] for point in box)) / 2
        )
        if center < 140 or center > 1780:
            return None
        nearest = min(centers, key=lambda value: abs(value - center))
        if abs(nearest - center) > 15 or nearest in matched_centers:
            return None
        matched_centers.add(nearest)
        icon = _material_icon(str(_icon_directory()), name)
        if icon is None:
            return None
        template, mask = icon
        region = cv2.cvtColor(
            image[415:575, center - 140 : center + 140], cv2.COLOR_RGB2BGR
        )
        scores = cv2.matchTemplate(region, template, cv2.TM_CCORR_NORMED, mask=mask)
        score = cv2.minMaxLoc(scores)[1]
        if not np.isfinite(score) or score < 0.90:
            return None
        counts = _ocr(image[570:625, center + 10 : center + 90])
        if len(counts) != 1:
            return None
        _, count, confidence = counts[0]
        if (
            not np.isfinite(confidence)
            or confidence < 0.90
            or re.fullmatch(r"[1-9][0-9]{0,4}", count.strip()) is None
        ):
            return None
        materials[name] = materials.get(name, 0) + int(count)
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
