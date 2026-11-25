"""Read the AEwide stage code in the ordinary or challenge preview panel."""

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from arknights_mower import __rootdir__


@lru_cache(maxsize=1)
def _model():
    with np.load(
        Path(__rootdir__) / "models/stage_code.npz", allow_pickle=False
    ) as data:
        return (
            str(data["alphabet"]),
            data["glyphs"].astype(np.float32) / 255,
            data["ratios"],
        )


def read_stage_code(frame) -> str | None:
    # The code is a separate best-fit text component between OPERATION and the medals.
    crop = frame[112:166, 1384:1525]
    if crop.shape[:2] != (54, 141):
        return None
    _, mask = cv2.threshold(crop.min(axis=2), 0, 255, cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    alphabet, templates, ratios = _model()
    result = []
    for index in sorted(range(1, count), key=lambda i: stats[i, cv2.CC_STAT_LEFT]):
        x, y, width, height, area = stats[index]
        if area < 8:
            continue
        if height < 7 and width < 7:
            continue  # Small flecks in the panel background.
        if (
            x == 0
            or x + width == mask.shape[1]
            or y == 0
            or y + height == mask.shape[0]
        ):
            return None
        glyph = (labels[y : y + height, x : x + width] == index).astype(np.float32)
        glyph = cv2.resize(glyph, (24, 32), interpolation=cv2.INTER_AREA)
        pixel_error = np.mean((templates - glyph) ** 2, axis=(2, 3))
        aspect_error = np.abs(np.log(ratios / (width / height)))
        scores = (pixel_error + 0.35 * np.minimum(aspect_error, 0.32)).min(axis=0)
        best, second = np.argsort(scores)[:2]
        if scores[best] > 0.36 or scores[second] - scores[best] < 0.008:
            return None
        result.append(alphabet[best])
    return "".join(result) or None
