"""Read complete stage codes from the activity map's black-and-white labels."""

from zipfile import BadZipFile

import cv2
import numpy as np

from arknights_mower.utils.stage_code_glyphs import load_stage_glyphs, match_stage_glyph


def _read_code(panel, model) -> str | None:
    gray = cv2.cvtColor(panel, cv2.COLOR_RGB2GRAY)
    if np.mean(gray > 208) < 0.6:
        return None
    mask = cv2.inRange(gray, 0, 149)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    parts = sorted(
        (x, y, w, h, i)
        for i, (x, y, w, h, area) in enumerate(stats[1:], 1)
        if area >= 6
    )
    if not parts:
        return None
    # The code is centered on the whole plate, to the right of the hexagonal icon.
    left = parts[0][0]
    right = parts[-1][0] + parts[-1][2]
    if abs((left + right) / 2 - 73) > 6:
        return None
    characters = []
    for x, y, w, h, i in parts:
        if x == 0 or y == 0 or x + w == mask.shape[1] or y + h == mask.shape[0]:
            return None
        char, error, gap = match_stage_glyph(labels[y : y + h, x : x + w] == i, model)
        # The thin hyphen varies by a full pixel in height after rasterization.
        limit = 0.28 if char == "-" else 0.15
        if error > limit or gap < 0.025:
            return None
        characters.append(char)
    return "".join(characters)


def read_map_stage_labels(frame) -> list[tuple[str, tuple[int, int]]]:
    if (
        not isinstance(frame, np.ndarray)
        or frame.shape != (1080, 1920, 3)
        or frame.dtype != np.uint8
    ):
        return []
    try:
        model = load_stage_glyphs("stage_map_code.npz")
    except (OSError, ValueError, KeyError, BadZipFile):
        return []
    # At the canonical capture size each white label has a black OPERATION header
    # about 195 x 14 px. Anchor on it so adjoining map paths cannot extend the crop.
    dark = cv2.inRange(frame, (0, 0, 0), (48, 48, 48))
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    matches = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if (
            not 178 <= w <= 205
            or not 10 <= h <= 21
            or cv2.contourArea(contour) < 0.55 * w * h
        ):
            continue
        if x == 0 or x + w == frame.shape[1]:
            continue
        right, top = x + w, y + h + 2
        panel = frame[top : top + 44, right - 170 : right - 1]
        if panel.shape[:2] != (44, 169):
            continue
        code = _read_code(panel, model)
        if code is not None:
            matches.append((code, (right - 97, top + 22)))
    return matches
