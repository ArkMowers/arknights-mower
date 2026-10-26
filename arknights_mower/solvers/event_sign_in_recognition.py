"""Recognize login progress and explicit reward receipts in card-list activities."""

from dataclasses import dataclass

import cv2
import numpy as np

from arknights_mower.utils.image import cropimg, loadres

Scope = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class Progress:
    total_days: int
    unlocked_days: int
    points: tuple[tuple[int, int], ...]
    day_scope: Scope
    card_scope: Scope
    drag_y: int
    scale: float


@dataclass(frozen=True)
class Card:
    day: int | None
    position: tuple[int, int]
    claimed: bool
    scope: Scope


def _scope(x0, y0, x1, y1, image):
    height, width = image.shape[:2]
    return (
        (max(0, round(x0)), max(0, round(y0))),
        (min(width, round(x1)), min(height, round(y1))),
    )


def _colored_centers(image, origin):
    pixels = image.astype(np.int16)
    mask = ((pixels.max(axis=2) >= 140) & (np.ptp(pixels, axis=2) >= 70)).astype(
        np.uint8
    ) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height = image.shape[0] / 0.32
    centers = []
    for contour in contours:
        x, y, width, length = cv2.boundingRect(contour)
        if (
            min(width, length) >= max(4, height * 0.007)
            and max(width, length) <= height * 0.11
            and 0.5 <= width / length <= 2
        ):
            centers.append((x + width / 2 + origin[0], y + length / 2 + origin[1]))
    return centers


def detect_progress(image):
    """Find a complete circular progress row without fixed endpoints or day count."""
    if image.ndim != 3 or image.shape[2] != 3:
        return None
    height, width = image.shape[:2]
    origin = (round(width * 0.25), round(height * 0.10))
    band = image[origin[1] : round(height * 0.42), origin[0] : round(width * 0.98)]
    gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
    candidates = []
    for radius_limit in (0.014, 0.018):
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            1,
            max(8, height * 0.012),
            param1=100,
            param2=10,
            minRadius=max(3, round(height * 0.005)),
            maxRadius=max(6, round(height * radius_limit)),
        )
        if circles is not None:
            candidates.extend(
                (float(x + origin[0]), float(y + origin[1]), float(radius))
                for x, y, radius in circles[0]
            )
    if not candidates:
        return None
    candidates.extend((x, y, 0) for x, y in _colored_centers(band, origin))
    edges = cv2.Canny(gray, 50, 120)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        max(20, round(width * 0.08)),
        minLineLength=round(width * 0.25),
        maxLineGap=round(height * 0.037),
    )
    if lines is None:
        return None
    horizontal = [
        (min(x0, x1) + origin[0], max(x0, x1) + origin[0], (y0 + y1) / 2 + origin[1])
        for x0, y0, x1, y1 in lines[:, 0]
        if abs(y1 - y0) <= max(2, height * 0.003)
    ]
    rows = []
    tolerance = max(3, height * 0.005)
    for _, center_y, _ in candidates:
        nearby_lines = [
            line for line in horizontal if abs(line[2] - center_y) <= tolerance
        ]
        if not nearby_lines:
            continue
        left, right, _ = max(nearby_lines, key=lambda line: line[1] - line[0])
        row = sorted(
            (x, y, priority)
            for x, y, priority in candidates
            if abs(y - center_y) <= tolerance
            and left - width * 0.025 <= x <= right + width * 0.025
        )
        merged = []
        for point in row:
            if merged and point[0] - merged[-1][0] < max(8, height * 0.014):
                if point[2] < merged[-1][2]:
                    merged[-1] = point
                continue
            merged.append(point)
        if len(merged) not in (7, 10):
            continue
        xs = np.asarray([point[0] for point in merged])
        spacing = float(np.median(np.diff(xs)))
        if (
            xs[-1] - xs[0] < width * 0.35
            or spacing < width * 0.025
            or np.any(np.abs(np.diff(xs) - spacing) > max(4, spacing * 0.09))
            or abs(xs[0] - left) > spacing * 0.75
            or abs(xs[-1] - right) > spacing * 0.75
        ):
            continue
        rows.append(merged)
    if not rows:
        return None
    row = max(rows, key=lambda points: points[-1][0] - points[0][0])
    points = tuple((round(x), round(y)) for x, y, _ in row)
    scale = (points[-1][0] - points[0][0]) / 1060
    row_y = float(np.median([y for _, y in points]))
    unlocked = 0
    radius = max(3, round(11 * scale))
    yy, xx = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    disk = xx * xx + yy * yy <= radius * radius
    for index, (x, y) in enumerate(points, 1):
        pixels = image[y - radius : y + radius + 1, x - radius : x + radius + 1][disk]
        pixels = pixels.astype(np.int16)
        white = (pixels.min(axis=1) >= 180) & (np.ptp(pixels, axis=1) <= 45)
        colored = (pixels.max(axis=1) >= 120) & (np.ptp(pixels, axis=1) >= 65)
        if np.mean(white | colored) >= 0.08:
            unlocked = index
    x0 = points[0][0] - 35 * scale
    x1 = points[-1][0] + 50 * scale
    return Progress(
        len(points),
        unlocked,
        points,
        _scope(x0, row_y + 95 * scale, x1, row_y + 470 * scale, image),
        _scope(x0, row_y + 95 * scale, x1, row_y + 670 * scale, image),
        round(row_y + 262 * scale),
        scale,
    )


def day_positions(result, progress):
    """Read large day numerals in the detected panel's local OCR coordinates."""
    positions = {}
    for box, text, score in result or []:
        text = text.strip()
        if (
            not np.isfinite(score)
            or score < 0.9
            or not text.isascii()
            or not text.isdecimal()
            or text.startswith("0")
            or not 1 <= int(text) <= progress.total_days
        ):
            continue
        points = np.asarray(box)
        left, top = points.min(axis=0)
        right, bottom = points.max(axis=0)
        if bottom - top < max(12, 60 * progress.scale):
            continue
        if left < 2 or right > progress.day_scope[1][0] - progress.day_scope[0][0] - 2:
            continue
        day = int(text)
        if day in positions:
            return {}
        positions[day] = (
            round((left + right) / 2 + progress.day_scope[0][0]),
            round((top + bottom) / 2 + progress.day_scope[0][1]),
        )
    ordered = sorted(positions, key=positions.get)
    if any(second <= first for first, second in zip(ordered, ordered[1:])):
        return {}
    return positions


def supplement_day_numbers(image, progress, result, recognize):
    """Supplement missed complete numerals without replacing detected identities."""
    result = list(result or [])
    accepted = [row for row in result if day_positions([row], progress)]
    if accepted and not day_positions(accepted, progress):
        return None
    band = cropimg(image, progress.day_scope)
    header = band[: min(band.shape[0], round(190 * progress.scale))]
    glyphs = []
    for lower, upper in (
        ((0, 0, 0), (180, 180, 180)),
        ((180, 180, 180), (255, 255, 255)),
    ):
        mask = cv2.inRange(header, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            if (
                max(12, 60 * progress.scale) <= height <= 150 * progress.scale
                and width <= height * 2
                and x >= 3
                and x + width <= band.shape[1] - 3
                and y > 0
                and y + height < header.shape[0]
            ):
                glyphs.append((x, y, width, height))
    if len(glyphs) > progress.total_days * 2:
        return None
    merged = []
    for x, y, width, height in sorted(glyphs):
        if merged:
            px, py, pw, ph = merged[-1]
            if (
                0 <= x - px - pw <= min(height, ph) * 0.6
                and x + width - px <= min(height, ph) * 2
                and abs(y - py) <= min(height, ph) * 0.15
                and abs(y + height - py - ph) <= min(height, ph) * 0.15
            ):
                merged[-1] = (
                    px,
                    min(y, py),
                    x + width - px,
                    max(y + height, py + ph) - min(y, py),
                )
                continue
        merged.append((x, y, width, height))
    glyphs = merged
    if len(glyphs) > progress.total_days:
        return None
    for x, y, width, height in glyphs:
        overlaps = [
            row
            for row in accepted
            if np.all(np.asarray(row[0]).min(axis=0) < (x + width, y + height))
            and np.all(np.asarray(row[0]).max(axis=0) > (x, y))
        ]
        if any(
            np.all(np.asarray(row[0]).min(axis=0) <= (x, y))
            and np.all(np.asarray(row[0]).max(axis=0) >= (x + width, y + height))
            for row in overlaps
        ):
            continue
        glyph = cv2.copyMakeBorder(
            band[y : y + height, x : x + width],
            8,
            8,
            8,
            8,
            cv2.BORDER_CONSTANT,
            value=(255, 255, 255),
        )
        reading = recognize(glyph, use_det=False)
        if not reading or len(reading) != 1:
            continue
        text, score = reading[0]
        box = [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]
        row = (box, text, score)
        if not day_positions([row], progress):
            continue
        if overlaps:
            if any(previous[1].strip() != text.strip() for previous in overlaps):
                return None
            continue
        result.append(row)
    if any(day_positions([row], progress) for row in result) and not day_positions(
        result, progress
    ):
        return None
    return result


def _receipt_positions(image, progress):
    gray = cv2.cvtColor(cropimg(image, progress.day_scope), cv2.COLOR_RGB2GRAY)
    template = loadres("event_sign_in/claimed", True)
    matches = []
    for factor in np.linspace(0.82, 1.18, 19):
        scale = progress.scale * factor
        resized = cv2.resize(template, None, fx=scale, fy=scale)
        if resized.shape[0] > gray.shape[0] or resized.shape[1] > gray.shape[1]:
            continue
        scores = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        for _ in range(5):
            _, score, _, location = cv2.minMaxLoc(scores)
            if score < 0.79:
                break
            x, y = location
            position = (
                round(x + 128 * scale + progress.day_scope[0][0]),
                round(y + 45 * scale + progress.day_scope[0][1]),
            )
            matches.append((score, position))
            x0, x1 = max(0, x - resized.shape[1] // 2), x + resized.shape[1] // 2
            y0, y1 = max(0, y - resized.shape[0] // 2), y + resized.shape[0] // 2
            scores[y0:y1, x0:x1] = -1
    positions = []
    for _, point in sorted(matches, reverse=True):
        if not any(
            abs(point[0] - prior[0]) < 100 * progress.scale for prior in positions
        ):
            positions.append(point)
    return positions


def read_cards(image, progress, ocr_result):
    """Keep explicit receipts and unreadable card slots separate from day numerals."""
    numbers = day_positions(ocr_result, progress)
    receipts = _receipt_positions(image, progress)
    header_y = (
        round(np.median([point[1] for point in numbers.values()]))
        if numbers
        else round(
            np.median([point[1] for point in progress.points]) + 182 * progress.scale
        )
    )
    for box, text, score in ocr_result or []:
        if score >= 0.9 and "已领取" in "".join(text.split()):
            points = np.asarray(box)
            x = (points[:, 0].min() + points[:, 0].max()) / 2
            receipts.append((round(x + progress.day_scope[0][0]), header_y))
    entries = [(point[0], point[1], day, False) for day, point in numbers.items()]
    for x, y in receipts:
        near = next(
            (
                i
                for i, point in enumerate(entries)
                if abs(point[0] - x) < 80 * progress.scale
            ),
            None,
        )
        if near is None:
            entries.append((x, y, None, True))
        else:
            old = entries[near]
            entries[near] = (*old[:3], True)
    if not entries:
        return ()
    entries.sort()
    expected_pitch = 280 * progress.scale
    gaps = np.diff([point[0] for point in entries])
    pitches = [gap / max(1, round(gap / expected_pitch)) for gap in gaps]
    pitch = float(np.median(pitches)) if pitches else expected_pitch
    if numbers:
        pitch = expected_pitch
    if not expected_pitch * 0.8 <= pitch <= expected_pitch * 1.2:
        return ()
    if numbers:
        anchor = next(iter(numbers.values()))[0]
        for index, (x, y, day, claimed) in enumerate(entries):
            aligned = anchor + round((x - anchor) / pitch) * pitch
            if day is None and claimed and abs(x - aligned) <= pitch * 0.15:
                entries[index] = (aligned, y, day, claimed)
    entries = [
        entry
        for entry in entries
        if entry[0] - pitch * 0.46 >= progress.card_scope[0][0]
        and entry[0] + pitch * 0.46 <= progress.card_scope[1][0]
    ]
    if not entries:
        return ()
    origin = entries[0][0]
    slots = {}
    for entry in entries:
        index = round((entry[0] - origin) / pitch)
        if abs(entry[0] - (origin + index * pitch)) > pitch * 0.15 or index in slots:
            return ()
        slots[index] = entry
    lower, upper = min(slots), max(slots)
    while origin + (lower - 1) * pitch - pitch * 0.46 >= progress.card_scope[0][0]:
        lower -= 1
    while origin + (upper + 1) * pitch + pitch * 0.46 <= progress.card_scope[1][0]:
        upper += 1
    number_origins = {
        day - round((position[0] - origin) / pitch)
        for day, position in numbers.items()
        if abs(position[0] - (origin + round((position[0] - origin) / pitch) * pitch))
        <= pitch * 0.15
    }
    if len(number_origins) > 1:
        return ()
    first_day = next(iter(number_origins), None)
    number_y = round(np.median([entry[1] for entry in entries]))
    cards = []
    row_y = np.median([point[1] for point in progress.points])
    for index in range(lower, upper + 1):
        x, y, day, claimed = slots.get(
            index, (origin + index * pitch, number_y, None, False)
        )
        if claimed and first_day is not None:
            day = first_day + index
        if day is not None and not 1 <= day <= progress.total_days:
            return ()
        scope = _scope(
            x - pitch * 0.46,
            row_y + 100 * progress.scale,
            x + pitch * 0.46,
            row_y + 650 * progress.scale,
            image,
        )
        cards.append(Card(day, (round(x), round(y)), claimed, scope))
    return tuple(cards)
