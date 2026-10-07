"""Read visible settlement totals; unknown slots never become estimated drops."""

import unicodedata
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from arknights_mower import __rootdir__
from arknights_mower.utils import rapidocr
from arknights_mower.utils.resource_pkg import resource_ui_path


def _icon_directory():
    selected = resource_ui_path("depot")
    if selected is not None:
        return selected
    root = Path(__rootdir__).parent / "ui"
    return root / ("public" if (root / "public/depot").is_dir() else "dist") / "depot"


@lru_cache(maxsize=2)
def _templates(directory):
    templates = []
    for path in sorted(Path(directory).glob("*.webp")):
        try:
            icon = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        except (OSError, cv2.error):
            return []
        if icon is None:
            return []
        if icon is None or icon.ndim != 3 or icon.shape[2] != 4:
            continue
        # Settlement circles are larger than the depot web assets. Excluding
        # the lower icon band prevents the quantity overlay affecting identity.
        icon = cv2.resize(icon, (118, 118))[:75]
        mask = (icon[:, :, 3] > 240).astype(np.uint8) * 255
        if cv2.countNonZero(mask) < 1000:
            continue
        templates.append((path.stem, icon[:, :, :3], mask))
    return templates


def _slot_positions(image):
    # Standard 16:9 settlement: horizontal separators describe groups of
    # 138px item cells. Unsupported/moving/partly clipped rows are rejected.
    line = np.max(image[636:638], axis=(0, 2)) > 45
    if np.any(line[-5:]):
        return None
    edges = np.diff(np.r_[False, line, False].astype(np.int8))
    spans = [
        (int(start), int(end))
        for start, end in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
        if end - start >= 8
    ]
    if not spans or abs(spans[0][0] - 67) > 3:
        return None
    positions = []
    for start, end in spans:
        width = end - start
        count = round(width / 138)
        if not 1 <= count <= 8 or abs(width - count * 138) > 3 or end >= 1275:
            return None
        positions.extend(start + index * 138 for index in range(count))
    return positions if 1 <= len(positions) <= 8 else None


def _read_icon(image, left, templates):
    region = image[500:598, left : left + 138]
    scores = []
    for name, template, mask in templates:
        result = cv2.matchTemplate(region, template, cv2.TM_CCORR_NORMED, mask=mask)
        score = cv2.minMaxLoc(result)[1]
        if np.isfinite(score):
            scores.append((score, name))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 0.97:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.025:
        return None
    return scores[0][1]


def _read_quantity(image, left):
    # Search the complete count band, including leading digits of 4/5-digit
    # rewards. Fixed narrow OCR crops can silently drop an isolated prefix.
    region = image[588:624, left + 15 : left + 130]
    white = cv2.inRange(region, (190, 190, 190), (255, 255, 255))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    glyphs = sorted(
        (x, y, width, height)
        for x, y, width, height in map(cv2.boundingRect, contours)
        if height >= 11 and 10 <= y <= 15 and 24 <= y + height <= 29
    )
    if not glyphs or len(glyphs) > 5:
        return None
    mask = np.zeros_like(white)
    previous_end = None
    for x, y, width, height in glyphs:
        if x == 0 or x + width >= white.shape[1]:
            return None
        if previous_end is not None and x - previous_end > 6:
            return None
        mask[y : y + height, x : x + width] = white[y : y + height, x : x + width]
        previous_end = x + width
    x, y, width, height = cv2.boundingRect(mask)
    padded = cv2.copyMakeBorder(
        mask[y : y + height, x : x + width],
        6,
        6,
        6,
        6,
        cv2.BORDER_CONSTANT,
        value=0,
    )
    result, _ = rapidocr.engine(
        cv2.resize(padded, None, fx=3, fy=3),
        use_det=False,
        use_cls=False,
        use_rec=True,
    )
    if not result or len(result) != 1:
        return None
    text, confidence = result[0]
    text = unicodedata.normalize("NFKC", text).strip()
    if not 0.90 <= confidence <= 1 or not text.isascii() or not text.isdecimal():
        return None
    if len(text) != len(glyphs):
        return None
    quantity = int(text)
    return quantity if 0 < quantity <= 99999 else None


def read_operation_drops(image, stage_id=None):
    """Return complete visible batch quantities by name, or None on uncertainty.

    Caller must confirm OPERATOR_FINISH, compare consecutive observations and
    apply once per completed batch. Quantities already include consecutive runs;
    stage_id is context only and never supplies expected quantities or drop rates.
    """
    if (
        not isinstance(image, np.ndarray)
        or image.shape != (1080, 1920, 3)
        or image.dtype != np.uint8
    ):
        return None
    frame = cv2.cvtColor(cv2.resize(image, (1280, 720)), cv2.COLOR_RGB2BGR)
    slots = _slot_positions(frame)
    if slots is None:
        return None
    templates = _templates(str(_icon_directory()))
    if not templates:
        return None
    if rapidocr.engine is None:
        rapidocr.initialize_ocr()
    drops = {}
    for left in slots:
        name = _read_icon(frame, left, templates)
        if name is None:
            return None
        quantity = _read_quantity(frame, left)
        if quantity is None:
            return None
        drops[name] = drops.get(name, 0) + quantity
    return drops
